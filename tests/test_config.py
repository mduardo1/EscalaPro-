from conftest import company_context
import pytest

from app import create_app
from app.database import get_db


def test_secret_required():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app({"SECRET_KEY": "short"})


def test_production_cookies_and_hsts(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("FLASK_DEBUG", "0")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://unused:unused@localhost/unused?sslmode=require"
    )
    monkeypatch.setenv("TRUSTED_HOSTS", "localhost")
    monkeypatch.setenv("EMAIL_DELIVERY_MODE", "outbox")
    monkeypatch.setenv("MAIL_TRANSPORT", "disabled")
    app = create_app({"TESTING": True, "SECRET_KEY": "x" * 40})
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert "max-age=" in app.test_client().get("/").headers["Strict-Transport-Security"]


def test_production_rejects_debug(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("FLASK_DEBUG", "true")
    with pytest.raises(RuntimeError, match="FLASK_DEBUG"):
        create_app({"SECRET_KEY": "x" * 40})


def test_foreign_keys_and_connection_lifecycle(app):
    with company_context(app):
        connection = get_db()
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert get_db() is connection
    import sqlite3

    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
