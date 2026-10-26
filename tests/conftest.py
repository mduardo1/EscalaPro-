import re
from contextlib import contextmanager
from pathlib import Path

import pytest
from flask import g

from app import create_app
from app.database import get_db, init_db
from app.models.user import create_user, find_by_id


@contextmanager
def company_context(app, user_id=1):
    with app.app_context():
        g.user = find_by_id(user_id)
        yield


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    # A auditoria nunca carrega credenciais locais nem seleciona o banco principal.
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("FLASK_DEBUG", "0")
    monkeypatch.setenv("APP_TIMEZONE", "America/Sao_Paulo")
    monkeypatch.setenv("DATABASE_PATH", "tmp/unused-test-default.sqlite3")
    for name in (
        "DATABASE_URL",
        "RESEND_API_KEY",
        "MAIL_FROM",
        "EMAIL_OUTBOX_KEY",
        "TRUSTED_HOSTS",
        "TRUSTED_PROXY_NETWORKS",
    ):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("MAIL_TRANSPORT", "smtp")
    monkeypatch.setenv("EMAIL_DELIVERY_MODE", "memory")
    monkeypatch.setenv("PROXY_HOPS", "0")
    monkeypatch.delenv("PROXY_FOR_HOPS", raising=False)
    monkeypatch.delenv("PROXY_PROTO_HOPS", raising=False)
    for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM"):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("SMTP_STARTTLS", "true")
    monkeypatch.setenv("SMTP_SSL", "false")
    monkeypatch.setenv("SMTP_PORT", "587")


def pytest_configure(config):
    # Todos os arquivos temporários de testes ficam dentro deste projeto.
    (Path(__file__).resolve().parents[1] / "tmp").mkdir(exist_ok=True)


@pytest.fixture
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-only-" + "x" * 40,
            "DATABASE": str(tmp_path / "test.sqlite3"),
            "SESSION_COOKIE_SECURE": False,
        }
    )
    with app.app_context():
        init_db()
        create_user(
            "Admin de teste", "admin@example.test", "test-password-123", company_id=1
        )
    app.extensions["email_outbox"] = []
    app.extensions["email_sender"] = lambda recipient, code, purpose: app.extensions[
        "email_outbox"
    ].append((recipient, code, purpose))
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def token(client, url="/login"):
    response = client.get(url)
    match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
    assert match, response.data[:500]
    return match.group(1).decode()


def post(client, url, data=None, source="/employees/"):
    return client.post(url, data={**(data or {}), "csrf_token": token(client, source)})


@pytest.fixture
def auth(client):
    response = post(
        client,
        "/login",
        {"email": "admin@example.test", "password": "test-password-123"},
        "/login",
    )
    assert response.status_code == 302
    return client


@pytest.fixture
def employee_data():
    return {
        "name": "Pessoa Fictícia",
        "role": "Analista",
        "department": "Operações",
        "email": "pessoa@example.test",
        "weekly_hours": "40",
    }


@pytest.fixture
def seeded(app):
    with company_context(app):
        db = get_db()
        db.execute(
            "INSERT INTO employees(name,role,department,weekly_hours,company_id) VALUES('Pessoa Teste','Analista','Equipe',40,1)"
        )
        db.execute(
            "INSERT INTO shifts(name,start_time,end_time,break_minutes,color,company_id) VALUES('Diurno','08:00','17:00',60,'#2563EB',1)"
        )
        db.execute(
            "INSERT INTO shifts(name,start_time,end_time,break_minutes,color,company_id) VALUES('Noturno','22:00','06:00',60,'#1E40AF',1)"
        )
        db.execute(
            "INSERT INTO shifts(name,start_time,end_time,break_minutes,color,company_id) VALUES('Madrugada','05:00','09:00',0,'#64748B',1)"
        )
        db.commit()
