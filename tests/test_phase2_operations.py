import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from alembic import command
from flask import request

from app import create_app
from app.config import Config
from app.database import get_db, migration_config
from app.services.backup_service import (
    backup_sqlite,
    postgres_environment,
    restore_postgres,
)


@pytest.mark.parametrize("value", ["prod", "unknown", ""])
def test_unknown_environment_is_rejected(monkeypatch, value):
    monkeypatch.setenv("APP_ENV", value)
    with pytest.raises(RuntimeError, match="APP_ENV"):
        Config()


def test_environment_normalization_and_strict_boolean(monkeypatch):
    monkeypatch.setenv("APP_ENV", " Production ")
    assert Config().PRODUCTION
    monkeypatch.setenv("SMTP_SSL", "maybe")
    with pytest.raises(RuntimeError, match="SMTP_SSL"):
        Config()


@pytest.mark.parametrize(
    "changes",
    [
        {"DATABASE_URL": ""},
        {"DATABASE_URL": "sqlite:///forbidden.sqlite3"},
        {"DATABASE_URL": "postgresql://fake:private@localhost/test?sslmode=disable"},
        {"TRUSTED_HOSTS": None},
        {"EMAIL_DELIVERY_MODE": "memory"},
        {"MAIL_TRANSPORT": "resend", "RESEND_API_KEY": "", "MAIL_FROM": ""},
        {"MAIL_TRANSPORT": "smtp", "SMTP_HOST": "", "SMTP_FROM": ""},
        {"DATABASE_URL": "malformed-private-database-url"},
    ],
)
def test_production_fails_closed(changes):
    cfg = {
        "SECRET_KEY": "fake-" + "x" * 40,
        "PRODUCTION": True,
        "DATABASE_URL": "postgresql://fake:private@localhost/test?sslmode=require",
        "TRUSTED_HOSTS": ["localhost"],
        "EMAIL_DELIVERY_MODE": "outbox",
        "MAIL_TRANSPORT": "disabled",
        **changes,
    }
    with pytest.raises(RuntimeError) as error:
        create_app(cfg)
    assert "private" not in str(error.value)


@pytest.mark.parametrize("key", ["invalid", "", "short"])
def test_outbox_requires_valid_separate_key(key):
    with pytest.raises(RuntimeError, match="EMAIL_OUTBOX_KEY"):
        create_app(
            {
                "SECRET_KEY": "fake-" + "x" * 40,
                "EMAIL_DELIVERY_MODE": "outbox",
                "EMAIL_OUTBOX_KEY": key,
            }
        )


@pytest.mark.parametrize("trusted", [False, True])
def test_proxy_headers_only_from_configured_peer(app, trusted):
    from app.proxy import TrustedProxy
    from ipaddress import ip_network

    app.wsgi_app = TrustedProxy(app.wsgi_app.app, [ip_network("10.20.0.0/24")], 1)

    @app.get("/proxy-test")
    def probe():
        return {
            "ip": request.remote_addr,
            "secure": request.is_secure,
            "host": request.host,
        }

    response = app.test_client().get(
        "/proxy-test",
        headers={
            "X-Forwarded-For": "203.0.113.5",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "attacker.test",
        },
        environ_overrides={"REMOTE_ADDR": "10.20.0.9" if trusted else "198.51.100.4"},
    )
    assert response.json == {
        "ip": "203.0.113.5" if trusted else "198.51.100.4",
        "secure": trusted,
        "host": "localhost",
    }


def test_proxy_configuration_requires_networks(monkeypatch):
    monkeypatch.setenv("PROXY_HOPS", "1")
    with pytest.raises(RuntimeError, match="TRUSTED_PROXY_NETWORKS"):
        Config()


def test_readiness_checks_schema_and_never_returns_details(app, client, tmp_path):
    assert client.get("/health/live").json == {"status": "ok"}
    response = client.get("/health/ready")
    assert response.status_code == 200 and response.json == {"status": "ok"}
    assert "Set-Cookie" not in response.headers
    with app.app_context():
        get_db().execute("UPDATE alembic_version SET version_num='old'")
        get_db().commit()
    assert client.get("/health/ready").status_code == 503
    missing = tmp_path / "missing.sqlite3"
    app.config["DATABASE"] = str(missing)
    response = client.get("/health/ready")
    assert response.status_code == 503 and response.json == {"status": "unavailable"}
    assert not missing.exists()
    assert client.get("/health/live").status_code == 200


def test_allowed_hosts_and_redacted_database_error(app, client, caplog, monkeypatch):
    app.config["TRUSTED_HOSTS"] = ["localhost"]
    assert client.get("/login", headers={"Host": "bad.example.test"}).status_code == 400

    def fail(*args):
        raise sqlite3.OperationalError("private-url password-sentinel")

    monkeypatch.setattr("app.models.user.find_session_user", fail)
    monkeypatch.setattr("app.routes.auth.find_session_user", fail)
    response = client.get("/login")
    assert response.status_code == 503
    assert (
        "password-sentinel" not in response.text
        and "password-sentinel" not in caplog.text
    )


def test_sqlite_backup_and_restore_preserve_hashes_and_refuse_overwrite(app, tmp_path):
    backup = tmp_path / "backup.sqlite3"
    with app.app_context():
        original = get_db().execute("SELECT password_hash FROM users").fetchone()[0]
    runner = app.test_cli_runner()
    assert runner.invoke(args=["backup-db", "--output", str(backup)]).exit_code == 0
    restored = tmp_path / "restored.sqlite3"
    assert (
        runner.invoke(
            args=["restore-sqlite", "--source", str(backup), "--output", str(restored)]
        ).exit_code
        == 0
    )
    from contextlib import closing

    with closing(sqlite3.connect(restored)) as db:
        assert db.execute("SELECT password_hash FROM users").fetchone()[0] == original
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    before = restored.read_bytes()
    assert (
        runner.invoke(
            args=["restore-sqlite", "--source", str(backup), "--output", str(restored)]
        ).exit_code
        == 1
    )
    assert restored.read_bytes() == before
    assert (
        runner.invoke(
            args=[
                "restore-sqlite",
                "--source",
                str(backup),
                "--output",
                app.config["DATABASE"],
            ]
        ).exit_code
        == 1
    )
    assert runner.invoke(args=["backup-db", "--output", str(backup)]).exit_code == 1


def test_backup_validation_rejects_external_and_corrupt_files(tmp_path):
    from app.services.backup_service import project_path, validate_sqlite

    with pytest.raises(ValueError):
        project_path(Path.cwd().parent / "outside.sqlite3")
    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_text("not sqlite", encoding="utf-8")
    with pytest.raises(sqlite3.DatabaseError):
        validate_sqlite(corrupt)


def test_pg_password_not_in_subprocess_arguments(app, tmp_path, monkeypatch):
    from app.services.backup_service import run_postgres_tool

    captured = {}
    monkeypatch.setattr("app.services.backup_service.shutil.which", lambda _: "pg_dump")

    def fake_run(args, **kwargs):
        captured.update(args=args, **kwargs)
        return MagicMock(returncode=0)

    monkeypatch.setattr("app.services.backup_service.subprocess.run", fake_run)
    run_postgres_tool(
        "pg_dump", ["--version"], "postgresql://fake:password-sentinel@localhost/test"
    )
    assert "password-sentinel" not in " ".join(captured["args"])
    assert captured["env"]["PGPASSWORD"] == "password-sentinel"
    assert "password-sentinel" not in repr(
        postgres_environment("postgresql://fake:password-sentinel@localhost/test")[0]
    )


def test_migration_outbox_can_reverse_without_losing_business_data(app):
    with app.app_context():
        original = get_db().execute("SELECT password_hash FROM users").fetchone()[0]
        cfg = migration_config()
        command.downgrade(cfg, "0001_baseline")
        command.upgrade(cfg, "head")
        assert (
            get_db().execute("SELECT password_hash FROM users").fetchone()[0]
            == original
        )
        assert (
            get_db().execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == "0002_outbox"
        )
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
        assert (
            get_db().execute("SELECT password_hash FROM users").fetchone()[0]
            == original
        )


def test_restore_pg_never_targets_current_database(app, tmp_path):
    app.config["DATABASE_URL"] = "postgresql://fake:secret@localhost/original"
    archive = tmp_path / "snapshot.dump"
    archive.write_bytes(b"dummy archive")
    with app.app_context():
        with pytest.raises(ValueError, match="outro banco"):
            restore_postgres(archive, "postgresql://fake:changed@localhost/original")
        with pytest.raises(ValueError, match="outro banco"):
            restore_postgres(archive, "postgresql://fake:changed@127.0.0.1/original")


def test_auth_cleanup_only_removes_expired_records(app, client):
    from test_account_flows import signup

    signup(client)
    with app.app_context():
        db = get_db()
        db.execute("UPDATE email_challenges SET created_at=0")
        db.execute(
            "INSERT INTO auth_sessions(token_hash,user_id,expires_at) VALUES('expired',1,0)"
        )
        db.commit()
    assert app.test_cli_runner().invoke(args=["cleanup-auth"]).exit_code == 0
    with app.app_context():
        assert (
            get_db().execute("SELECT count(*) FROM email_challenges").fetchone()[0] == 0
        )
        assert get_db().execute("SELECT count(*) FROM auth_sessions").fetchone()[0] == 0
        assert get_db().execute("SELECT count(*) FROM users").fetchone()[0] == 1


def test_libpq_options_preserve_spaces_without_putting_password_in_dsn():
    from psycopg.conninfo import conninfo_to_dict

    dsn, env = postgres_environment(
        "postgresql://fake:password-sentinel@localhost/test?options=-c+search_path%3Dexample&sslmode=require"
    )
    values = conninfo_to_dict(dsn)
    assert values["options"] == "-c search_path=example"
    assert values["sslmode"] == "require" and "password" not in values
    assert env["PGPASSWORD"] == "password-sentinel"


def test_proxy_can_have_distinct_for_and_proto_hop_counts(app):
    from app.proxy import TrustedProxy
    from ipaddress import ip_network

    app.wsgi_app = TrustedProxy(app.wsgi_app.app, [ip_network("10.20.0.0/24")], 2, 1)

    @app.get("/proxy-count-test")
    def probe():
        return {"ip": request.remote_addr, "secure": request.is_secure}

    response = app.test_client().get(
        "/proxy-count-test",
        headers={
            "X-Forwarded-For": "203.0.113.8, 10.20.0.2",
            "X-Forwarded-Proto": "https",
        },
        environ_overrides={"REMOTE_ADDR": "10.20.0.3"},
    )
    assert response.json == {"ip": "203.0.113.8", "secure": True}


def test_automatic_migration_validates_backup_before_schema_update(app):
    with app.app_context():
        db = get_db()
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute(
            "INSERT INTO employees(name,role,department,email,active,weekly_hours,company_id) VALUES('Inválido','Analista','Equipe','',1,40,999)"
        )
        db.commit()
        revision = db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    result = app.test_cli_runner().invoke(args=["migrate-db"])
    assert result.exit_code == 1 and "backup sem integridade" in result.output
    with app.app_context():
        assert (
            get_db().execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == revision
        )
        assert get_db().execute("SELECT count(*) FROM users").fetchone()[0] == 1
