"""Demonstração isolada, proteções de caminho e integração sem envio real."""

from datetime import date, timedelta
from contextlib import closing
import hashlib
from io import BytesIO
import os
import sqlite3

from flask import g
from pypdf import PdfReader
import pytest

from conftest import post
from scripts import seed_demo as demo


@pytest.fixture
def demo_database(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "ROOT", tmp_path)
    value = "instance/demo/integration.demo.sqlite3"
    path, password, monday = demo.seed_demo(value, week=date(2026, 10, 18))
    return path, password, monday


@pytest.mark.parametrize(
    "value",
    [
        "",
        "instance/escalapro.sqlite3",
        "postgresql://localhost/demo",
        "../other.demo.sqlite3",
        "instance/demo/main.sqlite3",
        "instance/demo/nested/a.demo.sqlite3",
    ],
)
def test_demo_refuses_unreserved_paths(value):
    with pytest.raises(ValueError):
        demo.demo_path(value)


def test_demo_never_overwrites_existing_database(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "ROOT", tmp_path)
    target = tmp_path / "instance/demo/existing.demo.sqlite3"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"Existing file must remain byte-for-byte intact")
    before = hashlib.sha256(target.read_bytes()).digest()
    with pytest.raises(ValueError, match="existente"):
        demo.seed_demo(str(target))
    assert hashlib.sha256(target.read_bytes()).digest() == before


def test_demo_environment_discards_credentials_and_restores_process(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATABASE_URL", "invalid-sentinel-url")
    monkeypatch.setenv("SECRET_KEY", "private-sentinel-never-used")
    monkeypatch.setenv("SMTP_HOST", "must-not-contact.invalid")
    monkeypatch.setenv("MAIL_TRANSPORT", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "must-not-use")
    monkeypatch.setenv("FLASK_DEBUG", "1")
    original = os.environ.copy()
    app = demo.create_demo_app(tmp_path / "safe.demo.sqlite3")
    assert app.config["DATABASE_URL"] == ""
    assert app.config["SECRET_KEY"] != original["SECRET_KEY"]
    assert app.config["MAIL_TRANSPORT"] == "disabled"
    assert app.config["SMTP_HOST"] == app.config["RESEND_API_KEY"] == ""
    assert not app.debug
    assert os.environ == original
    with pytest.raises(RuntimeError, match="desativado"):
        app.extensions["email_sender"]("unused", "unused", "unused")


def test_unmarked_or_invalid_database_cannot_run_as_demo(tmp_path):
    path = tmp_path / "unknown.demo.sqlite3"
    with pytest.raises(ValueError):
        demo.require_demo(path)
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE real_like_data(id INTEGER)")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="identificação"):
        demo.require_demo(path)
    assert path.read_bytes() == before


def test_seeded_demo_has_fictional_data_alerts_and_no_mail(demo_database):
    from app.database import get_db
    from app.models.user import find_by_email
    from app.services.schedule_service import week_alerts, week_period

    path, _password, monday = demo_database
    demo.require_demo(path)
    app = demo.create_demo_app(path)
    with app.app_context():
        db = get_db()
        g.user = find_by_email(demo.DEMO_EMAIL)
        assert g.user["email_verified"] == 1
        assert db.execute("SELECT count(*) FROM employees").fetchone()[0] == 15
        assert db.execute("SELECT count(*) FROM schedules").fetchone()[0] == 150
        assert db.execute("SELECT count(*) FROM unavailabilities").fetchone()[0] == 3
        assert db.execute("SELECT count(*) FROM shifts").fetchone()[0] == 3
        assert all(
            row[0].endswith("@example.com")
            for row in db.execute(
                "SELECT email FROM employees UNION ALL SELECT email FROM users"
            )
        )
        assert db.execute("SELECT count(*) FROM email_outbox").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM email_challenges").fetchone()[0] == 0
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        alerts = week_alerts(*week_period(monday.isoformat()))
        assert any("jornada" in alert for alert in alerts)
        assert any("descanso" in alert for alert in alerts)
        assert (
            db.execute(
                "SELECT count(*) FROM schedules WHERE substr(end_at,1,10)>work_date"
            ).fetchone()[0]
            > 0
        )


def test_demo_login_pages_pdf_and_company_isolation(demo_database):
    from app.database import get_db
    from app.models.company import create_company
    from app.models.user import create_user, find_by_email

    path, password, monday = demo_database
    app = demo.create_demo_app(path)
    app.config["TESTING"] = True
    client = app.test_client()
    response = post(
        client, "/login", {"email": demo.DEMO_EMAIL, "password": password}, "/login"
    )
    assert response.status_code == 302
    for url in (
        "/dashboard",
        "/employees/",
        "/shifts/",
        f"/schedules/?week={monday}",
        "/settings",
        "/health/ready",
    ):
        assert client.get(url).status_code == 200
    assert "Pessoa Fictícia 01" in client.get("/employees/").text
    pdf = client.get(f"/schedules/export.pdf?week={monday}")
    assert pdf.status_code == 200 and pdf.mimetype == "application/pdf"
    text = "".join(page.extract_text() for page in PdfReader(BytesIO(pdf.data)).pages)
    assert "TechNova" in text and "Pessoa Fictícia" in text and "Noite" in text
    with app.app_context():
        company = create_company("Outra Empresa Fictícia")
        get_db().commit()
        create_user(
            "Outro Admin Fictício",
            "outro.demo@example.com",
            "DemoOnly-OtherPassword123",
            company_id=company,
        )
    other = app.test_client()
    assert (
        post(
            other,
            "/login",
            {
                "email": "outro.demo@example.com",
                "password": "DemoOnly-OtherPassword123",
            },
            "/login",
        ).status_code
        == 302
    )
    assert "Pessoa Fictícia 01" not in other.get("/employees/").text
    assert other.get("/employees/1/edit").status_code == 404
    assert other.get("/schedules/1/edit").status_code == 404
    with app.app_context():
        assert find_by_email(demo.DEMO_EMAIL)["company_id"] != company


def test_demo_cli_refuses_existing_and_does_not_echo_credentials(
    demo_database, monkeypatch, capsys
):
    path, password, _monday = demo_database
    monkeypatch.setattr("sys.argv", ["seed_demo.py", "--database", str(path)])
    with pytest.raises(SystemExit) as result:
        demo.main()
    assert result.value.code == 1
    captured = capsys.readouterr()
    assert password not in captured.out + captured.err
