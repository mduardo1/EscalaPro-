"""Integração real somente em database _test, com schema descartável próprio."""

import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import create_app
from app.database import init_db, get_db
from app.models.company import create_company
from app.models.employee import save_employee, get_employee
from app.models.shift import save_shift
from app.models.user import create_user
from app.services.schedule_service import save_assignment, add_unavailability
from conftest import company_context
from test_account_flows import signup, verify, login, PASSWORD


@pytest.fixture
def pg_app(monkeypatch, tmp_path, request):
    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        pytest.skip("Configure TEST_DATABASE_URL para integração PostgreSQL isolada.")
    url = make_url(value).set(drivername="postgresql+psycopg")
    if not url.database.endswith("_test") or url.host not in {
        "localhost",
        "127.0.0.1",
        "postgres",
    }:
        pytest.fail("Integração exige database _test local/CI.")
    namespace = "escalapro_test_" + secrets.token_hex(8)
    admin = create_engine(url, hide_parameters=True)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{namespace}"'))
    isolated = url.update_query_dict({"options": "-c search_path=" + namespace})
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "pg-test-" + "x" * 40,
            "DATABASE": str(tmp_path / "unused.sqlite3"),
            "DATABASE_URL": isolated,
        }
    )
    # Durante integração os erros do banco devem falhar com o traceback fictício.
    app.error_handler_spec[None][None].pop(SQLAlchemyError)
    try:
        with app.app_context():
            init_db()
            if getattr(request, "param", None) != "empty":
                create_user(
                    "Admin Teste",
                    "admin@example.test",
                    "test-password-123",
                    company_id=1,
                )
        app.extensions["email_outbox"] = []
        app.extensions["email_sender"] = lambda *args: app.extensions[
            "email_outbox"
        ].append(args)
        yield app
    finally:
        app.extensions["database_engine"].dispose()
        assert (
            namespace.startswith("escalapro_test_")
            and namespace[len("escalapro_test_") :].isalnum()
        )
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{namespace}" CASCADE'))
        admin.dispose()


def test_pg_accounts_reset_and_company_isolation(pg_app):
    first = pg_app.test_client()
    assert signup(first).status_code == 302
    code = pg_app.extensions["email_outbox"][-1][1]
    assert verify(first, "signup", code).status_code == 302
    assert login(first, "nova@example.test", PASSWORD).status_code == 302
    assert first.get("/dashboard").status_code == 200
    assert first.get("/employees/").status_code == 200
    assert first.get("/schedules/").status_code == 200
    assert first.get("/schedules/export.pdf").data.startswith(b"%PDF-")
    with company_context(pg_app, 1):
        employee = save_employee(
            {
                "name": "Privado Alfa",
                "role": "Analista",
                "department": "Equipe",
                "email": "",
                "weekly_hours": 40,
            }
        )
    assert first.get(f"/employees/{employee}/edit").status_code == 404
    assert "Privado Alfa" not in first.get("/employees/").text
    reset = pg_app.test_client()
    from conftest import post

    assert (
        post(
            reset,
            "/forgot-password",
            {"email": "nova@example.test"},
            "/forgot-password",
        ).status_code
        == 302
    )
    assert (
        verify(reset, "reset", pg_app.extensions["email_outbox"][-1][1]).status_code
        == 302
    )
    assert (
        post(
            reset,
            "/reset-password",
            {
                "password": "OutraSenhaForte123!",
                "confirm_password": "OutraSenhaForte123!",
            },
            "/reset-password",
        ).status_code
        == 302
    )
    assert first.get("/dashboard").status_code == 302


@pytest.fixture
def pg_seeded(pg_app):
    with company_context(pg_app):
        employee = save_employee(
            {
                "name": "Pessoa Teste",
                "role": "Analista",
                "department": "Equipe",
                "email": "",
                "weekly_hours": 40,
            }
        )
        shift = save_shift(
            {
                "name": "Noturno",
                "start_time": "22:00",
                "end_time": "06:00",
                "break_minutes": 60,
                "color": "#2563EB",
            }
        )
    return pg_app, employee, shift


@pytest.mark.parametrize("absence", [False, True])
def test_pg_concurrent_writes_cannot_overlap(pg_seeded, absence):
    app, employee, shift = pg_seeded
    barrier = Barrier(2)

    def write(index):
        with company_context(app):
            barrier.wait(timeout=10)
            try:
                if absence and index:
                    add_unavailability(
                        {
                            "employee_id": str(employee),
                            "start_at": "2026-10-13T05:00",
                            "end_at": "2026-10-13T09:00",
                            "reason": "Folga",
                        }
                    )
                else:
                    save_assignment(
                        {
                            "employee_id": str(employee),
                            "shift_id": str(shift),
                            "work_date": "2026-10-12",
                        }
                    )
                return "saved"
            except ValueError:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, [0, 1])) == ["conflict", "saved"]


def test_pg_constraints_and_shared_rate_limits(pg_seeded):
    app, employee, shift = pg_seeded
    from app.security import consume_rate_limit

    with app.app_context():
        company = create_company("Outra empresa")
        get_db().commit()
    with company_context(app):
        db = get_db()
        with pytest.raises(IntegrityError):
            db.execute(
                "UPDATE employees SET company_id=:company WHERE id=:id",
                {"company": company, "id": employee},
            )
        db.rollback()
        with pytest.raises(IntegrityError):
            db.execute(
                "INSERT INTO schedules(employee_id,shift_id,work_date,start_at,end_at,shift_name,break_minutes,color,company_id) VALUES(:employee,:shift,'2026-10-12','2026-10-12T22:00:00','2026-10-13T06:00:00','Inválido',60,'#2563EB',:company)",
                {"employee": employee, "shift": shift, "company": company},
            )
        db.rollback()
        assert consume_rate_limit("shared", "fake", 1, 900)
    with app.app_context():
        assert not consume_rate_limit("shared", "fake", 1, 900)


def test_pg_code_consumed_once_under_concurrency(pg_app):
    client = pg_app.test_client()
    signup(client)
    from app.models.verification import consume_code
    from app.services.auth_service import code_digest

    with client.session_transaction() as session:
        challenge = session["pending_signup"]
    with pg_app.app_context():
        digest = code_digest(
            challenge, "signup", pg_app.extensions["email_outbox"][-1][1]
        )
    barrier = Barrier(2)

    def confirm():
        with pg_app.app_context():
            barrier.wait(timeout=10)
            return consume_code(challenge, "signup", digest)

    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(confirm) for _ in range(2)]
        assert sorted(task.result(timeout=20) for task in tasks) == [False, True]


@pytest.mark.parametrize("pg_app", ["empty"], indirect=True)
def test_snapshot_import_preserves_two_companies_ids_hashes_and_history(
    app, seeded, pg_app
):
    from pathlib import Path
    from app.services.data_transfer import import_sqlite_snapshot

    with company_context(app):
        save_assignment(
            {"employee_id": "1", "shift_id": "2", "work_date": "2026-10-12"}
        )
        original_hash = (
            get_db().execute("SELECT password_hash FROM users WHERE id=1").fetchone()[0]
        )
        second = create_company("Outra empresa fictícia")
        create_user("Outro Admin", "other@example.test", PASSWORD, company_id=second)
    source = Path(app.config["DATABASE"])
    before = source.read_bytes()
    with pg_app.app_context():
        result = import_sqlite_snapshot(source)
        assert (
            result["users"] == 2
            and result["companies"] == 2
            and result["schedules"] == 1
        )
        assert (
            get_db().execute("SELECT password_hash FROM users WHERE id=1").fetchone()[0]
            == original_hash
        )
        schedule = get_db().execute("SELECT * FROM schedules WHERE id=1").fetchone()
        assert (
            schedule["start_at"] == "2026-10-12T22:00:00"
            and schedule["end_at"] == "2026-10-13T06:00:00"
        )
        with pytest.raises(ValueError, match="já contém"):
            import_sqlite_snapshot(source)
    with company_context(pg_app, 2):
        assert get_employee(1) is None
    with company_context(pg_app, 1):
        new_id = save_employee(
            {
                "name": "Novo ID",
                "role": "Analista",
                "department": "Equipe",
                "email": "",
                "weekly_hours": 40,
            }
        )
        assert new_id > 1
        assert create_company("Empresa após importação") > second
        get_db().commit()
    assert source.read_bytes() == before
    client = pg_app.test_client()
    assert login(client, "admin@example.test", "test-password-123").status_code == 302
    assert client.get("/schedules/export.pdf?week=2026-10-12").data.startswith(b"%PDF-")


@pytest.mark.parametrize("pg_app", ["empty"], indirect=True)
def test_import_refuses_corrupt_source_without_partial_target(app, seeded, pg_app):
    from app.services.data_transfer import import_sqlite_snapshot

    with app.app_context():
        db = get_db()
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute(
            "INSERT INTO employees(id,name,role,department,email,active,weekly_hours,company_id) VALUES(999,'Inválido','Analista','Equipe','',1,40,999)"
        )
        db.commit()
    with pg_app.app_context():
        with pytest.raises(ValueError, match="Snapshot"):
            import_sqlite_snapshot(app.config["DATABASE"])
        assert get_db().execute("SELECT count(*) FROM users").fetchone()[0] == 0
        assert (
            get_db().execute("SELECT name FROM companies").fetchone()[0]
            == "Minha empresa"
        )


def test_pg_migrations_round_trip_and_require_backup_for_existing_users(pg_app):
    from alembic import command
    from app.database import migration_config

    with pg_app.app_context():
        original_hash = (
            get_db().execute("SELECT password_hash FROM users").fetchone()[0]
        )
        get_db().rollback()
        command.downgrade(migration_config(), "0001_baseline")
        command.upgrade(migration_config(), "head")
        assert (
            get_db().execute("SELECT password_hash FROM users").fetchone()[0]
            == original_hash
        )
    result = pg_app.test_cli_runner().invoke(args=["migrate-db"])
    assert result.exit_code == 1 and "--backup" in result.output


def test_pg_outbox_claims_once_under_concurrency(pg_app):
    from cryptography.fernet import Fernet
    from app.services.outbox_service import claim, finish

    pg_app.config.update(
        EMAIL_DELIVERY_MODE="outbox", EMAIL_OUTBOX_KEY=Fernet.generate_key().decode()
    )
    assert signup(pg_app.test_client()).status_code == 302
    barrier = Barrier(2)

    def take():
        with pg_app.app_context():
            barrier.wait(timeout=10)
            task = claim()
            if task:
                finish(task, "sent")
            return bool(task)

    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(take) for _ in range(2)]
        assert sorted(task.result(timeout=20) for task in tasks) == [False, True]


def test_pg_dump_restore_into_new_database(pg_app, tmp_path):
    import shutil

    if not shutil.which("pg_dump") or not shutil.which("pg_restore"):
        pytest.skip("Clientes PostgreSQL disponíveis na imagem Linux de testes.")
    from app.services.backup_service import backup_postgres, restore_postgres

    original = pg_app.config["DATABASE_URL"]
    target_name = "escalapro_restore_" + secrets.token_hex(8) + "_test"
    target = original.set(database=target_name)
    admin = create_engine(original, isolation_level="AUTOCOMMIT", hide_parameters=True)
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{target_name}"'))
    restored = None
    try:
        with pg_app.app_context():
            original_hash = (
                get_db().execute("SELECT password_hash FROM users").fetchone()[0]
            )
            get_db().rollback()
            archive = backup_postgres(original, tmp_path / "pg.snapshot.dump")
            assert archive.stat().st_size > 0
            restore_postgres(archive, target)
            with pytest.raises(ValueError, match="vazio"):
                restore_postgres(archive, target)
        restored = create_engine(target, hide_parameters=True)
        with restored.connect() as connection:
            assert (
                connection.execute(text("SELECT password_hash FROM users")).scalar()
                == original_hash
            )
            assert (
                connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()
                == "0002_outbox"
            )
    finally:
        if restored:
            restored.dispose()
        assert target_name.startswith("escalapro_restore_") and target_name.endswith(
            "_test"
        )
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{target_name}"'))
        admin.dispose()


def test_linux_gunicorn_serves_database_readiness_without_logging_queries(pg_app):
    import importlib.util
    import subprocess
    import sys
    import socket
    import time
    from pathlib import Path
    from urllib.request import urlopen
    from urllib.error import URLError

    if importlib.util.find_spec("gunicorn") is None or sys.platform == "win32":
        pytest.skip("Gunicorn é executado no teste Linux.")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = os.environ.copy()
    env.update(
        APP_ENV="testing",
        SECRET_KEY=pg_app.secret_key,
        DATABASE_URL=pg_app.config["DATABASE_URL"].render_as_string(
            hide_password=False
        ),
        PORT=str(port),
        MAIL_TRANSPORT="disabled",
        PYTHON_DOTENV_DISABLED="1",
        FLASK_DEBUG="0",
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "gunicorn",
            "--config",
            "gunicorn.conf.py",
            "app:create_app()",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                with urlopen(
                    f"http://127.0.0.1:{port}/health/ready", timeout=1
                ) as response:
                    assert response.status == 200
                break
            except URLError:
                if time.monotonic() > deadline or process.poll() is not None:
                    pytest.fail("Gunicorn não ficou pronto no ambiente isolado.")
                time.sleep(0.1)
        with urlopen(
            f"http://127.0.0.1:{port}/login?q=private-query-sentinel", timeout=3
        ) as response:
            assert "Criar conta gratuitamente" in response.read().decode()
    finally:
        process.terminate()
        stdout, stderr = process.communicate(timeout=15)
    assert b"private-query-sentinel" not in stdout + stderr


@pytest.mark.parametrize("pg_app", ["empty"], indirect=True)
def test_empty_pg_baseline_reverses_and_recreates(pg_app):
    from alembic import command
    from app.database import migration_config

    with pg_app.app_context():
        command.downgrade(migration_config(), "base")
        command.upgrade(migration_config(), "head")
        assert get_db().execute("SELECT count(*) FROM users").fetchone()[0] == 0
        assert (
            get_db().execute("SELECT name FROM companies").fetchone()[0]
            == "Minha empresa"
        )


def test_populated_pg_baseline_cannot_be_destroyed(pg_app):
    from alembic import command
    from app.database import migration_config

    with pg_app.app_context():
        with pytest.raises(RuntimeError, match="com dados preservada"):
            command.downgrade(migration_config(), "base")
        assert get_db().execute("SELECT count(*) FROM users").fetchone()[0] == 1
        assert (
            get_db().execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == "0002_outbox"
        )
