"""Cadastro e recuperação usam transporte em memória; nenhum e-mail real é enviado."""

import hashlib
import time

import pytest
from werkzeug.security import check_password_hash

from app.database import get_db
from app.models.user import create_user
from conftest import company_context, post, token

PASSWORD = "AcessoForte123!"


def signup(client, email="nova@example.test", **overrides):
    data = {
        "name": "Nova Administradora",
        "company_name": "Empresa Nova",
        "email": email,
        "password": PASSWORD,
        "confirm_password": PASSWORD,
        **overrides,
    }
    return post(client, "/register", data, "/register")


def verify(client, purpose, code):
    return post(client, f"/verify/{purpose}", {"code": code}, f"/verify/{purpose}")


def login(client, email, password):
    return post(client, "/login", {"email": email, "password": password}, "/login")


def test_registration_stays_pending_then_creates_verified_company(app, client):
    assert signup(client).status_code == 302
    recipient, code, purpose = app.extensions["email_outbox"][-1]
    assert (
        recipient == "nova@example.test"
        and purpose == "signup"
        and len(code) == 6
        and code.isdigit()
    )
    with app.app_context():
        db = get_db()
        pending = db.execute("SELECT * FROM email_challenges").fetchone()
        assert pending["code_hash"] != code and len(pending["code_hash"]) == 64
        assert pending["password_hash"] != PASSWORD and check_password_hash(
            pending["password_hash"], PASSWORD
        )
        assert (
            db.execute(
                "SELECT count(*) FROM users WHERE email=?", (recipient,)
            ).fetchone()[0]
            == 0
        )
        assert pending["expires_at"] - pending["sent_at"] == 600
    assert login(app.test_client(), recipient, PASSWORD).status_code == 401
    assert verify(client, "signup", code).status_code == 302
    with app.app_context():
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email=?", (recipient,)).fetchone()
        assert user["email_verified"] == 1 and user["company_id"] != 1
        assert (
            db.execute(
                "SELECT name FROM companies WHERE id=?", (user["company_id"],)
            ).fetchone()[0]
            == "Empresa Nova"
        )
        assert (
            db.execute(
                "SELECT company_name FROM company_settings WHERE company_id=?",
                (user["company_id"],),
            ).fetchone()[0]
            == "Empresa Nova"
        )
        assert (
            db.execute("SELECT password_hash FROM email_challenges").fetchone()[0]
            is None
        )
    assert login(client, recipient, PASSWORD).status_code == 302
    assert client.get("/dashboard").status_code == 200


@pytest.mark.parametrize(
    "changes",
    [
        {"password": "short", "confirm_password": "short"},
        {"password": "semmaiuscula123!", "confirm_password": "semmaiuscula123!"},
        {"password": "SEM_MINUSCULAS123!", "confirm_password": "SEM_MINUSCULAS123!"},
        {"password": "SemNumerosForte!", "confirm_password": "SemNumerosForte!"},
        {"password": "SemSimbolo12345", "confirm_password": "SemSimbolo12345"},
        {"confirm_password": "OutroValor123!"},
        {"email": "invalid"},
        {"name": ""},
        {"company_name": ""},
    ],
)
def test_registration_validation_does_not_send_or_persist(app, client, changes):
    assert signup(client, **changes).status_code == 422
    assert app.extensions["email_outbox"] == []
    with app.app_context():
        assert (
            get_db().execute("SELECT count(*) FROM email_challenges").fetchone()[0] == 0
        )


def test_duplicate_email_never_overwrites_existing_credentials_or_company(app, client):
    assert (
        signup(
            client, "admin@example.test", company_name="Tentativa de outra empresa"
        ).status_code
        == 302
    )
    assert (
        verify(client, "signup", app.extensions["email_outbox"][-1][1]).status_code
        == 302
    )
    with app.app_context():
        db = get_db()
        row = db.execute(
            "SELECT * FROM users WHERE email='admin@example.test'"
        ).fetchone()
        assert check_password_hash(row["password_hash"], "test-password-123")
        assert not check_password_hash(row["password_hash"], PASSWORD)
        assert row["company_id"] == 1
        assert db.execute("SELECT count(*) FROM companies").fetchone()[0] == 1


def test_registration_and_reset_responses_do_not_enumerate(app):
    for endpoint in ("/register", "/forgot-password"):
        results = []
        for email in ("admin@example.test", "unknown@example.test"):
            client = app.test_client()
            response = (
                signup(client, email)
                if endpoint == "/register"
                else post(client, endpoint, {"email": email}, endpoint)
            )
            page = client.get(response.location)
            results.append(
                (
                    response.status_code,
                    response.location,
                    page.status_code,
                    page.text.split("<form")[0],
                )
            )
        assert results[0] == results[1]


def test_resend_cooldown_old_code_invalidation_and_attempt_limit(
    app, client, monkeypatch
):
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    monkeypatch.setattr(
        "app.services.auth_service.secrets.randbelow", lambda _limit: 123456
    )
    assert signup(client).status_code == 302
    assert app.extensions["email_outbox"][-1][1] == "123456"
    assert (
        post(client, "/verify/signup/resend", {}, "/verify/signup").status_code == 302
    )
    assert len(app.extensions["email_outbox"]) == 1
    monkeypatch.setattr(time, "time", lambda: now + 61)
    assert (
        post(client, "/verify/signup/resend", {}, "/verify/signup").status_code == 302
    )
    new_code = app.extensions["email_outbox"][-1][1]
    assert new_code != "123456"
    assert verify(client, "signup", "123456").status_code == 422
    assert verify(client, "signup", new_code).status_code == 302


def test_expired_and_reused_codes_cannot_activate_accounts(app, client, monkeypatch):
    now = time.time()
    assert signup(client).status_code == 302
    code = app.extensions["email_outbox"][-1][1]
    monkeypatch.setattr(time, "time", lambda: now + 601)
    assert verify(client, "signup", code).status_code == 422
    with app.app_context():
        assert get_db().execute("SELECT count(*) FROM users").fetchone()[0] == 1


def test_code_is_consumed_once_and_tied_to_pending_request(app, client):
    assert signup(client).status_code == 302
    code = app.extensions["email_outbox"][-1][1]
    cookie = client.get_cookie("session").value
    assert verify(client, "signup", code).status_code == 302
    replay = app.test_client()
    replay.set_cookie("session", cookie)
    assert verify(replay, "signup", code).status_code == 422
    with app.app_context():
        assert get_db().execute("SELECT count(*) FROM users").fetchone()[0] == 2


def test_five_incorrect_codes_block_even_correct_value(app, client):
    assert signup(client).status_code == 302
    code = app.extensions["email_outbox"][-1][1]
    wrong = "111111" if code != "111111" else "222222"
    for _ in range(5):
        assert verify(client, "signup", wrong).status_code == 422
    assert verify(client, "signup", code).status_code == 422
    with app.app_context():
        row = get_db().execute("SELECT attempts FROM email_challenges").fetchone()
        assert row["attempts"] == 5


def test_unverified_user_never_receives_login_session(app, client):
    with app.app_context():
        create_user(
            "Não verificada",
            "pending@example.test",
            PASSWORD,
            company_id=1,
            verified=False,
        )
    assert login(client, "pending@example.test", PASSWORD).status_code == 401
    with app.app_context():
        assert get_db().execute("SELECT count(*) FROM auth_sessions").fetchone()[0] == 0


def prepare_reset(app, client, email="admin@example.test"):
    assert (
        post(
            client, "/forgot-password", {"email": email}, "/forgot-password"
        ).status_code
        == 302
    )
    code = app.extensions["email_outbox"][-1][1]
    assert verify(client, "reset", code).status_code == 302
    return code


def test_reset_password_revokes_every_old_session_and_grant_is_single_use(app, auth):
    cookie = auth.get_cookie("session").value
    other_device = app.test_client()
    assert (
        login(other_device, "admin@example.test", "test-password-123").status_code
        == 302
    )
    reset = app.test_client()
    prepare_reset(app, reset)
    old_grant_cookie = reset.get_cookie("session").value
    password = "NovaSenhaSegura456!"
    response = post(
        reset,
        "/reset-password",
        {"password": password, "confirm_password": password},
        "/reset-password",
    )
    assert response.status_code == 302
    replay = app.test_client()
    replay.set_cookie("session", cookie)
    assert replay.get("/dashboard").status_code == 302
    assert other_device.get("/dashboard").status_code == 302
    assert (
        login(app.test_client(), "admin@example.test", "test-password-123").status_code
        == 401
    )
    assert login(app.test_client(), "admin@example.test", password).status_code == 302
    reset.set_cookie("session", old_grant_cookie)
    assert reset.get("/reset-password").status_code == 302
    with app.app_context():
        row = (
            get_db()
            .execute(
                "SELECT code_hash,reset_token_hash FROM email_challenges WHERE purpose='reset'"
            )
            .fetchone()
        )
        assert tuple(row) == (None, None)


def test_recovery_unknown_email_and_invalid_or_expired_grant(app, client, monkeypatch):
    response = post(
        client,
        "/forgot-password",
        {"email": "unknown@example.test"},
        "/forgot-password",
    )
    assert response.status_code == 302 and app.extensions["email_outbox"] == []
    assert client.get("/reset-password").status_code == 302
    now = time.time()
    prepare_reset(app, client)
    monkeypatch.setattr(time, "time", lambda: now + 601)
    assert client.get("/reset-password").status_code == 302


def test_new_reset_invalidates_previous_code_and_grant(app):
    first, second = app.test_client(), app.test_client()
    prepare_reset(app, first)
    assert first.get("/reset-password").status_code == 200
    assert (
        post(
            second,
            "/forgot-password",
            {"email": "admin@example.test"},
            "/forgot-password",
        ).status_code
        == 302
    )
    assert first.get("/reset-password").status_code == 302


def test_auth_endpoints_have_csrf_and_do_not_echo_passwords(app, client):
    for path in [
        "/register",
        "/forgot-password",
        "/verify/signup",
        "/verify/reset",
        "/verify/signup/resend",
        "/reset-password",
    ]:
        assert client.post(path).status_code == 400
    response = signup(client, confirm_password="different")
    assert PASSWORD not in response.text
    assert client.get("/verify/unexpected").status_code == 404


def test_email_and_registration_rate_limits_include_unknown_accounts(app, client):
    for _ in range(3):
        assert (
            post(
                client,
                "/forgot-password",
                {"email": "unknown@example.test"},
                "/forgot-password",
            ).status_code
            == 302
        )
    assert (
        post(
            client,
            "/forgot-password",
            {"email": "unknown@example.test"},
            "/forgot-password",
        ).status_code
        == 429
    )
    assert app.extensions["email_outbox"] == []


def test_unconfigured_smtp_fails_safely_without_logging_secrets(app, client, caplog):
    del app.extensions["email_sender"]
    response = signup(client)
    assert response.status_code == 503
    assert PASSWORD not in response.text and PASSWORD not in caplog.text


def test_signup_ip_limit_and_resend_limit(app, monkeypatch):
    for index in range(5):
        assert (
            signup(app.test_client(), f"pessoa{index}@example.test").status_code == 302
        )
    assert signup(app.test_client(), "sexta@example.test").status_code == 429
    assert len(app.extensions["email_outbox"]) == 5


def test_resend_has_email_rate_limit(app, client, monkeypatch):
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    signup(client)
    for seconds in (61, 122, 183):
        monkeypatch.setattr(time, "time", lambda seconds=seconds: now + seconds)
        post(client, "/verify/signup/resend", {}, "/verify/signup")
    assert len(app.extensions["email_outbox"]) == 4
    monkeypatch.setattr(time, "time", lambda: now + 244)
    post(client, "/verify/signup/resend", {}, "/verify/signup")
    assert len(app.extensions["email_outbox"]) == 4


def test_leading_zero_code_and_code_from_other_request(app, monkeypatch):
    values = iter([7, 765432])
    monkeypatch.setattr(
        "app.services.auth_service.secrets.randbelow", lambda _limit: next(values)
    )
    first, second = app.test_client(), app.test_client()
    signup(first, "first@example.test")
    signup(second, "second@example.test")
    assert app.extensions["email_outbox"][0][1] == "000007"
    assert verify(second, "signup", "000007").status_code == 422
    assert verify(first, "signup", "000007").status_code == 302


def test_recovery_code_wrong_expired_and_used_cannot_be_reused(
    app, client, monkeypatch
):
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    post(
        client, "/forgot-password", {"email": "admin@example.test"}, "/forgot-password"
    )
    code = app.extensions["email_outbox"][-1][1]
    wrong = "000000" if code != "000000" else "999999"
    assert verify(client, "reset", wrong).status_code == 422
    old_cookie = client.get_cookie("session").value
    assert verify(client, "reset", code).status_code == 302
    replay = app.test_client()
    replay.set_cookie("session", old_cookie)
    assert verify(replay, "reset", code).status_code == 422
    other = app.test_client()
    post(other, "/forgot-password", {"email": "admin@example.test"}, "/forgot-password")
    new_code = app.extensions["email_outbox"][-1][1]
    monkeypatch.setattr(time, "time", lambda: now + 601)
    assert verify(other, "reset", new_code).status_code == 422


def test_invalid_new_password_preserves_credentials_and_grant(app, client):
    prepare_reset(app, client)
    response = post(
        client,
        "/reset-password",
        {"password": "short", "confirm_password": "short"},
        "/reset-password",
    )
    assert response.status_code == 422
    assert client.get("/reset-password").status_code == 200
    with app.app_context():
        row = get_db().execute("SELECT password_hash FROM users WHERE id=1").fetchone()
        assert check_password_hash(row[0], "test-password-123")


def test_code_consumption_is_atomic_under_parallel_requests(app, client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.services.auth_service import verify_code

    signup(client)
    code = app.extensions["email_outbox"][-1][1]
    with client.session_transaction() as session:
        challenge_id = session["pending_signup"]
    barrier = Barrier(2)

    def consume():
        with app.test_request_context("/verify/signup", method="POST"):
            barrier.wait(timeout=5)
            return verify_code(challenge_id, "signup", code)[0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(consume) for _ in range(2)]
        assert sorted(future.result(timeout=15) for future in futures) == [False, True]
    with app.app_context():
        assert (
            get_db()
            .execute("SELECT count(*) FROM users WHERE email='nova@example.test'")
            .fetchone()[0]
            == 1
        )


def test_employee_record_is_not_a_login_and_registration_cannot_join_existing_company(
    app, client
):
    from app.models.employee import save_employee

    with company_context(app):
        save_employee(
            {
                "name": "Pessoa da equipe original",
                "role": "Analista",
                "department": "Legado",
                "email": "worker@example.test",
                "weekly_hours": 40,
            }
        )
    assert login(client, "worker@example.test", PASSWORD).status_code == 401
    assert (
        signup(
            client, "worker@example.test", company_name="Minha empresa", company_id="1"
        ).status_code
        == 302
    )
    assert (
        verify(client, "signup", app.extensions["email_outbox"][-1][1]).status_code
        == 302
    )
    assert login(client, "worker@example.test", PASSWORD).status_code == 302
    assert "Pessoa da equipe original" not in client.get("/employees/").text
    with app.app_context():
        assert (
            get_db()
            .execute("SELECT company_id FROM users WHERE email='worker@example.test'")
            .fetchone()[0]
            != 1
        )


def test_validation_rate_limit_is_independent_of_per_challenge_attempts(app, client):
    app.config["CODE_MAX_ATTEMPTS"] = 100
    signup(client)
    code = app.extensions["email_outbox"][-1][1]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(21):
        assert verify(client, "signup", wrong).status_code == 422
    with app.app_context():
        assert (
            get_db().execute("SELECT attempts FROM email_challenges").fetchone()[0]
            == 20
        )
