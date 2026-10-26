from conftest import company_context

"""Cenários adicionais funcionais, defensivos e de integridade do MVP."""

import hashlib
import sqlite3
import time
from datetime import datetime, timedelta
from io import BytesIO

import pytest
from flask import url_for
from pypdf import PdfReader

from app.database import get_db, init_db
from app.models.employee import list_employees
from app.services.pdf_service import weekly_pdf
from app.services.schedule_service import save_assignment, week_period
from conftest import post, token
from test_audit_regressions import rendered_context


def test_unknown_login_same_generic_message(client):
    response = post(
        client,
        "/login",
        {"email": "unknown@example.test", "password": "anything"},
        "/login",
    )
    assert response.status_code == 401
    assert "E-mail ou senha inválidos." in response.text
    assert "password_hash" not in response.text
    assert "anything" not in response.text


def test_login_sql_injection_does_not_authenticate(client):
    response = post(
        client, "/login", {"email": "' OR 1=1 --", "password": "anything"}, "/login"
    )
    assert response.status_code == 401
    assert client.get("/dashboard").status_code == 302


def test_forged_session_cookie_is_rejected(app, auth):
    value = auth.get_cookie("session").value
    payload, timestamp, signature = value.rsplit(".", 2)
    tampered = (
        f"{payload}.{timestamp}.{'A' if signature[0] != 'A' else 'B'}{signature[1:]}"
    )
    attacker = app.test_client()
    attacker.set_cookie("session", tampered)
    assert attacker.get("/dashboard").status_code == 302


def test_auth_session_hash_logout_and_other_device(app, auth):
    other = app.test_client()
    assert (
        post(
            other,
            "/login",
            {"email": "admin@example.test", "password": "test-password-123"},
            "/login",
        ).status_code
        == 302
    )
    with auth.session_transaction() as session:
        auth_token = session["auth_token"]
    with company_context(app):
        row = (
            get_db()
            .execute(
                "SELECT * FROM auth_sessions WHERE token_hash=?",
                (hashlib.sha256(auth_token.encode()).hexdigest(),),
            )
            .fetchone()
        )
        assert row is not None and row["token_hash"] != auth_token
        assert row["expires_at"] - time.time() <= 8 * 3600
    assert post(auth, "/logout").status_code == 302
    assert other.get("/dashboard").status_code == 200


def test_legacy_user_id_cookie_without_server_session_is_rejected(client):
    with client.session_transaction() as session:
        session["user_id"] = 1
    assert client.get("/dashboard").status_code == 302


def test_csrf_is_bound_to_client_and_expires(app, auth, monkeypatch):
    victim_token = token(auth, "/employees/")
    other = app.test_client()
    assert other.post("/login", data={"csrf_token": victim_token}).status_code == 400
    issued = time.time()
    monkeypatch.setattr(time, "time", lambda: issued + 8 * 3600 + 1)
    assert auth.post("/logout", data={"csrf_token": victim_token}).status_code == 400


def test_every_admin_write_requires_authentication_and_csrf(app, client, seeded):
    csrf_token = token(client)
    paths = [
        "/employees/new",
        "/employees/1/edit",
        "/employees/1/toggle",
        "/shifts/",
        "/shifts/1/edit",
        "/schedules/",
        "/schedules/1/edit",
        "/schedules/1/delete",
        "/schedules/unavailability",
        "/schedules/unavailability/1/delete",
        "/settings",
        "/logout",
    ]
    for path in paths:
        assert client.post(path).status_code == 400
        response = client.post(path, data={"csrf_token": csrf_token})
        assert response.status_code == 302 and response.location.endswith("/login")
    with company_context(app):
        assert get_db().execute("SELECT count(*) FROM schedules").fetchone()[0] == 0


def test_rate_limit_expires_without_real_sleep(client, monkeypatch):
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
    issued = time.time()
    monkeypatch.setattr(time, "time", lambda: issued + 901)
    assert (
        post(
            client,
            "/login",
            {"email": "admin@example.test", "password": "test-password-123"},
            "/login",
        ).status_code
        == 302
    )


def test_employee_department_search_persistence_and_duplicate_policy(
    app, auth, employee_data
):
    # Sem matrícula/CPF obrigatório, homônimos e e-mails repetidos são permitidos.
    for _ in range(2):
        assert post(auth, "/employees/new", employee_data).status_code == 302
    with company_context(app):
        assert len(list_employees("Operações")) == 2
        assert len(list_employees("Outro setor")) == 0
        assert get_db().execute("SELECT count(*) FROM employees").fetchone()[0] == 2
    assert (
        post(
            auth, "/employees/1/edit", {**employee_data, "email": "invalid"}
        ).status_code
        == 422
    )
    with company_context(app):
        assert (
            get_db().execute("SELECT email FROM employees WHERE id=1").fetchone()[0]
            == employee_data["email"]
        )


def test_shift_duplicates_and_referenced_shift_delete_restricted(app, auth, seeded):
    data = {
        "name": "Diurno",
        "start_time": "08:00",
        "end_time": "17:00",
        "break_minutes": "60",
        "color": "#2563EB",
    }
    assert post(auth, "/shifts/", data).status_code == 302
    with company_context(app):
        save_assignment(
            {"employee_id": "1", "shift_id": "1", "work_date": "2026-10-12"}
        )
        db = get_db()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM shifts WHERE id=1")
        db.rollback()
        assert (
            db.execute("SELECT count(*) FROM shifts WHERE name='Diurno'").fetchone()[0]
            == 2
        )
        assert db.execute("SELECT count(*) FROM schedules").fetchone()[0] == 1
    assert (
        auth.post(
            "/shifts/1/delete", data={"csrf_token": token(auth, "/shifts/")}
        ).status_code
        == 404
    )


def test_year_transition_week_and_midnight_end(app, auth, seeded):
    with company_context(app):
        db = get_db()
        db.execute(
            "UPDATE shifts SET start_time='20:00',end_time='00:00',break_minutes=0 WHERE id=2"
        )
        db.commit()
        save_assignment(
            {"employee_id": "1", "shift_id": "2", "work_date": "2026-12-31"}
        )
        row = db.execute("SELECT * FROM schedules").fetchone()
        assert row["end_at"] == "2027-01-01T00:00:00"
    start, end = week_period("2027-01-01")
    assert start == datetime(2026, 12, 28) and end == datetime(2027, 1, 4)
    page = auth.get("/schedules/?week=2027-01-01")
    assert page.status_code == 200 and "31/12" in page.text
    context = rendered_context(app, auth, "/schedules/?week=2027-01-04")
    assert len(context["schedules"]) == 0


def test_time_off_and_same_time_different_employees(app, auth, seeded):
    with company_context(app):
        db = get_db()
        db.execute(
            "INSERT INTO employees(name,role,department,weekly_hours,company_id) VALUES('Outra Pessoa','Analista','Equipe',40,1)"
        )
        db.commit()
    data = {
        "employee_id": "1",
        "start_at": "2026-10-13T00:00",
        "end_at": "2026-10-14T00:00",
        "reason": "Folga",
    }
    assert post(auth, "/schedules/unavailability", data).status_code == 302
    with company_context(app):
        save_assignment(
            {"employee_id": "1", "shift_id": "1", "work_date": "2026-10-12"}
        )
        save_assignment(
            {"employee_id": "2", "shift_id": "1", "work_date": "2026-10-12"}
        )
        with pytest.raises(ValueError, match="indisponível"):
            save_assignment(
                {"employee_id": "1", "shift_id": "1", "work_date": "2026-10-13"}
            )
        save_assignment(
            {"employee_id": "1", "shift_id": "1", "work_date": "2026-10-14"}
        )


def test_failed_edit_rolls_back_original_assignment(app, seeded):
    with company_context(app):
        save_assignment(
            {"employee_id": "1", "shift_id": "2", "work_date": "2026-10-12"}
        )
        save_assignment(
            {"employee_id": "1", "shift_id": "1", "work_date": "2026-10-14"}
        )
        with pytest.raises(ValueError, match="Conflito"):
            save_assignment(
                {"employee_id": "1", "shift_id": "3", "work_date": "2026-10-13"},
                schedule_id=2,
            )
        row = (
            get_db()
            .execute("SELECT work_date,shift_id FROM schedules WHERE id=2")
            .fetchone()
        )
        assert tuple(row) == ("2026-10-14", 1)


def test_dashboard_metrics_match_database(app, auth, seeded, monkeypatch):
    monkeypatch.setattr(
        "app.routes.dashboard.local_now", lambda: datetime(2026, 10, 13, 1)
    )
    with company_context(app):
        db = get_db()
        db.execute(
            "INSERT INTO employees(name,role,department,weekly_hours,active,company_id) VALUES('Inativa','Analista','Equipe',40,0,1)"
        )
        db.execute("UPDATE employees SET weekly_hours=10 WHERE id=1")
        db.commit()
        for day, shift in [
            ("2026-10-12", "2"),
            ("2026-10-13", "1"),
            ("2026-10-20", "1"),
        ]:
            save_assignment({"employee_id": "1", "shift_id": shift, "work_date": day})
    context = rendered_context(app, auth, "/dashboard")
    assert len(context["employees"]) == 1
    assert len(context["shifts"]) == 3
    assert len(context["schedules"]) == 2
    assert len(context["alerts"]) == 1
    assert len(context["upcoming"]) == 2
    assert context["chart"] == [1.8, 13.2, 0, 0, 0, 0, 0]
    assert context["total_hours"] == 15


def test_pdf_special_characters_round_trip(app):
    rows = [
        {
            "employee_name": "João Dvořák & Ana Łucja",
            "department": "Operações <Equipe>",
            "shift_name": "Plantão — noite",
            "start_at": "2026-10-12T22:00:00",
            "end_at": "2026-10-13T06:00:00",
            "break_minutes": 60,
        }
    ]
    with company_context(app):
        pdf = weekly_pdf(
            "Companhia São José & Filhos",
            datetime(2026, 10, 12),
            datetime(2026, 10, 19),
            rows,
        )
    reader = PdfReader(pdf)
    text = " ".join(page.extract_text() for page in reader.pages)
    for expected in [
        "João Dvořák & Ana Łucja",
        "Operações <Equipe>",
        "Plantão — noite",
        "Companhia São José & Filhos",
    ]:
        assert expected in text


def test_pdf_many_employees_long_fields_and_repeated_headers(app):
    rows = [
        {
            "employee_name": f"Profissional {i:03d} " + "Sobrenome " * 7,
            "department": "Departamento de Operações e Atendimento " * 2,
            "shift_name": "Plantão noturno de atendimento especial",
            "start_at": "2026-10-12T22:00:00",
            "end_at": "2026-10-13T06:00:00",
            "break_minutes": 60,
        }
        for i in range(80)
    ]
    with company_context(app):
        pdf = weekly_pdf(
            "Empresa de Revisão " * 5,
            datetime(2026, 10, 12),
            datetime(2026, 10, 19),
            rows,
        )
    reader = PdfReader(pdf)
    assert len(reader.pages) > 2
    all_text = " ".join(page.extract_text() for page in reader.pages)
    for i in range(80):
        assert f"Profissional {i:03d}" in all_text
    for page in reader.pages:
        assert "Funcionário" in page.extract_text()
        assert "Página" in page.extract_text()


def test_database_schema_init_is_additive_and_integrity_valid(app, seeded):
    with company_context(app):
        save_assignment(
            {"employee_id": "1", "shift_id": "1", "work_date": "2026-10-12"}
        )
        # Simula o schema anterior à correção de revogação de sessões.
        get_db().execute("DROP TABLE auth_sessions")
        get_db().commit()
        init_db()
        db = get_db()
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT count(*) FROM schedules").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM auth_sessions").fetchone()[0] == 0


def test_parallel_assignments_cannot_create_overlap(app, seeded):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    barrier = Barrier(2)

    def assign():
        with company_context(app):
            barrier.wait(timeout=5)
            try:
                save_assignment(
                    {"employee_id": "1", "shift_id": "1", "work_date": "2026-10-12"}
                )
                return "saved"
            except ValueError as exc:
                assert "Conflito" in str(exc)
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(assign) for _ in range(2)]
        assert sorted(future.result(timeout=15) for future in futures) == [
            "conflict",
            "saved",
        ]
    with company_context(app):
        assert get_db().execute("SELECT count(*) FROM schedules").fetchone()[0] == 1


def test_production_actual_set_cookie_flags(app):
    import re
    from http.cookies import SimpleCookie

    app.config.update(PRODUCTION=True, SESSION_COOKIE_SECURE=True)
    client = app.test_client()
    response = client.get("/login", base_url="https://localhost")
    csrf_token = (
        re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        .group(1)
        .decode()
    )
    response = client.post(
        "/login",
        base_url="https://localhost",
        headers={"Referer": "https://localhost/login"},
        data={
            "email": "admin@example.test",
            "password": "test-password-123",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 302
    cookies = SimpleCookie()
    cookies.load(response.headers["Set-Cookie"])
    assert cookies["session"]["secure"] and cookies["session"]["httponly"]
    assert cookies["session"]["samesite"] == "Lax"


def test_errors_do_not_expose_exception_details(app, auth, monkeypatch):
    monkeypatch.setattr(
        "app.routes.employees.list_employees",
        lambda *_: (_ for _ in ()).throw(
            sqlite3.OperationalError("sensitive-sql-canary")
        ),
    )
    response = auth.get("/employees/")
    assert response.status_code == 503
    assert (
        "sensitive-sql-canary" not in response.text and "Traceback" not in response.text
    )
    app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)
    monkeypatch.setattr(
        "app.routes.employees.list_employees",
        lambda *_: (_ for _ in ()).throw(RuntimeError("private-exception-canary")),
    )
    response = auth.get("/employees/")
    assert response.status_code == 500
    assert (
        "private-exception-canary" not in response.text
        and "Traceback" not in response.text
    )


def test_missing_fields_and_xss_in_all_text_domains(auth, employee_data, seeded):
    for path in [
        "/employees/new",
        "/shifts/",
        "/schedules/",
        "/schedules/unavailability",
        "/settings",
    ]:
        assert post(auth, path, {}).status_code == 422
    payload = '<img src=x onerror="alert(1)">'
    assert (
        post(
            auth, "/settings", {"company_name": payload, "min_rest_hours": "0"}
        ).status_code
        == 302
    )
    assert (
        post(
            auth,
            "/shifts/",
            {
                "name": payload,
                "start_time": "10:00",
                "end_time": "11:00",
                "break_minutes": "0",
                "color": "#2563EB",
            },
        ).status_code
        == 302
    )
    assert payload not in auth.get("/shifts/").text
    assert "&lt;img" in auth.get("/settings").text
    assert (
        post(
            auth,
            "/schedules/unavailability",
            {
                "employee_id": "1",
                "start_at": "2026-10-14T00:00",
                "end_at": "2026-10-15T00:00",
                "reason": payload,
            },
        ).status_code
        == 302
    )
    assert payload not in auth.get("/schedules/").text


def test_request_size_and_post_only_endpoints(auth):
    response = auth.post(
        "/employees/new",
        data=b"x" * (1024 * 1024 + 1),
        content_type="application/x-www-form-urlencoded",
    )
    assert response.status_code == 413
    for path in [
        "/employees/1/toggle",
        "/schedules/1/delete",
        "/schedules/unavailability",
        "/logout",
    ]:
        assert auth.get(path).status_code == 405
