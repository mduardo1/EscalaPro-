from conftest import company_context
from werkzeug.security import check_password_hash

from app.database import get_db, init_db
from conftest import post


def test_factory_and_public_home(client):
    assert client.get("/").status_code == 200
    assert client.get("/login").status_code == 200


def test_protected_routes(client):
    for url in [
        "/dashboard",
        "/employees/",
        "/employees/new",
        "/shifts/",
        "/schedules/",
        "/settings",
        "/schedules/export.pdf",
    ]:
        response = client.get(url)
        assert response.status_code == 302
        assert response.location.endswith("/login")


def test_login_logout_and_hash(app, client):
    response = post(
        client, "/login", {"email": "admin@example.test", "password": "wrong"}, "/login"
    )
    assert response.status_code == 401
    response = post(
        client,
        "/login",
        {"email": "admin@example.test", "password": "test-password-123"},
        "/login",
    )
    assert response.status_code == 302
    assert client.get("/dashboard").status_code == 200
    with company_context(app):
        password_hash = (
            get_db().execute("SELECT password_hash FROM users").fetchone()[0]
        )
        assert password_hash != "test-password-123"
        assert check_password_hash(password_hash, "test-password-123")
    assert post(client, "/logout").status_code == 302
    assert client.get("/dashboard").status_code == 302


def test_csrf_required(auth):
    assert auth.post("/logout").status_code == 400
    assert (
        auth.post("/employees/new", data={"csrf_token": "invalid"}).status_code == 400
    )


def test_login_csrf(client):
    assert (
        client.post(
            "/login",
            data={"email": "admin@example.test", "password": "test-password-123"},
        ).status_code
        == 400
    )


def test_login_rate_limit(client):
    for _ in range(5):
        assert (
            post(
                client,
                "/login",
                {"email": "admin@example.test", "password": "wrong"},
                "/login",
            ).status_code
            == 401
        )
    assert (
        post(
            client,
            "/login",
            {"email": "admin@example.test", "password": "test-password-123"},
            "/login",
        ).status_code
        == 429
    )


def test_headers_and_errors(auth):
    response = auth.get("/dashboard")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]
    assert auth.get("/not-found").status_code == 404
    assert auth.get("/logout").status_code == 405


def test_cli_admin_and_idempotent_init(app, monkeypatch):
    runner = app.test_cli_runner()
    assert runner.invoke(args=["init-db"]).exit_code == 0
    monkeypatch.setenv("ADMIN_EMAIL", "new@example.test")
    monkeypatch.setenv("ADMIN_NAME", "Nova Conta")
    monkeypatch.setenv("ADMIN_PASSWORD", "short")
    assert runner.invoke(args=["create-admin"]).exit_code == 1
    monkeypatch.setenv("ADMIN_PASSWORD", "long-test-password-456")
    assert runner.invoke(args=["create-admin"]).exit_code == 0
    assert runner.invoke(args=["create-admin"]).exit_code == 1
    with company_context(app):
        init_db()
        assert get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2
