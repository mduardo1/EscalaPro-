"""Conexões por requisição, integridade e comandos de configuração."""

import os
import hashlib
from contextlib import closing
import sqlite3
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import click
from flask import current_app, g

if TYPE_CHECKING:
    from app.persistence import PostgresConnection


def get_db() -> "sqlite3.Connection | PostgresConnection":
    if "db" not in g:
        if current_app.config["DATABASE_URL"]:
            from app.persistence import PostgresConnection

            g.db = PostgresConnection(current_app.extensions["database_engine"])
            return g.db
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA busy_timeout = 10000")
    return g.db


def parameters(values):
    """Converte uma sequência de valores em parâmetros nomeados; não altera SQL."""
    if isinstance(values, dict):
        return values
    return {f"p{index}": value for index, value in enumerate(values)}


def postgres():
    return bool(current_app.config["DATABASE_URL"])


def begin_write(lock_name=None):
    db = get_db()
    if not postgres():
        db.execute("BEGIN IMMEDIATE")
    elif lock_name is not None:
        key = int.from_bytes(
            hashlib.sha256(lock_name.encode()).digest()[:8], "big", signed=True
        )
        db.execute("SELECT pg_advisory_xact_lock(:key)", {"key": key})


def lock_employees(employee_ids):
    if postgres():
        from app.tenant import company_id

        for employee_id in sorted(set(employee_ids)):
            get_db().execute(
                "SELECT id FROM employees WHERE id=:id AND company_id=:company FOR UPDATE",
                {"id": employee_id, "company": company_id()},
            ).fetchone()


def lock_schedule(schedule_id):
    if postgres() and schedule_id:
        from app.tenant import company_id

        get_db().execute(
            "SELECT id FROM schedules WHERE id=:id AND company_id=:company FOR UPDATE",
            {"id": schedule_id, "company": company_id()},
        ).fetchone()


def migration_config():
    from alembic.config import Config
    from sqlalchemy.engine import URL

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.attributes["url"] = current_app.config["DATABASE_URL"] or URL.create(
        "sqlite", database=current_app.config["DATABASE"]
    )
    return cfg


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    from alembic import command

    if postgres():
        command.upgrade(migration_config(), "head")
        return
    db = get_db()
    db.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
    db.commit()
    from app.migrations import migrate

    migrate(db)
    command.upgrade(migration_config(), "head")


def init_app(app):
    if app.config["DATABASE_URL"]:
        from sqlalchemy import create_engine
        from sqlalchemy.exc import ArgumentError
        from sqlalchemy.engine import make_url

        try:
            url = make_url(app.config["DATABASE_URL"])
            if url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
                raise ValueError
            url = url.set(drivername="postgresql+psycopg")
            if app.config["PRODUCTION"] and url.query.get("sslmode") not in {
                "require",
                "verify-ca",
                "verify-full",
            }:
                raise ValueError
        except ValueError, TypeError, ArgumentError:
            raise RuntimeError(
                "DATABASE_URL deve ser PostgreSQL; em produção, configure TLS obrigatório."
            ) from None
        app.config["DATABASE_URL"] = url
        options = (
            url.query.get("options", "")
            + " -c statement_timeout=5000 -c lock_timeout=5000"
        )
        app.extensions["database_engine"] = create_engine(
            url,
            pool_size=app.config["DB_POOL_SIZE"],
            max_overflow=0,
            pool_timeout=app.config["DB_TIMEOUT"],
            pool_pre_ping=True,
            hide_parameters=True,
            connect_args={
                "connect_timeout": app.config["DB_TIMEOUT"],
                "options": options,
            },
        )
    app.teardown_appcontext(close_db)

    @app.cli.command("mail-worker")
    @click.option("--once", is_flag=True, help="Processa no máximo uma tarefa.")
    def mail_worker(once):
        from app.services.outbox_service import process_one
        from app.services.email_service import mail_ready
        import time

        if current_app.config["EMAIL_DELIVERY_MODE"] != "outbox":
            raise click.ClickException("Configure EMAIL_DELIVERY_MODE=outbox.")
        if not mail_ready():
            raise click.ClickException(
                "Transporte de e-mail indisponível; a outbox foi preservada."
            )
        while True:
            try:
                processed = process_one()
            finally:
                close_db()
            if once:
                break
            if not processed:
                time.sleep(2)

    @app.cli.command("cleanup-auth")
    def cleanup_auth():
        import time

        now = time.time()
        db = get_db()
        try:
            db.execute(
                "DELETE FROM email_challenges WHERE created_at<:limit",
                {"limit": now - 86400},
            )
            db.execute("DELETE FROM auth_sessions WHERE expires_at<=:now", {"now": now})
            for table in ("login_attempts", "rate_limits"):
                db.execute(f"DELETE FROM {table} WHERE expires_at<=:now", {"now": now})
            db.commit()
        except Exception:
            db.rollback()
            raise click.ClickException(
                "Limpeza indisponível; detalhes privados omitidos."
            ) from None
        click.echo("Registros de autenticação expirados removidos.")

    @app.cli.command("init-db")
    def init_db_command():
        """Cria tabelas ausentes sem apagar registros."""
        if postgres():
            from sqlalchemy import inspect

            if (
                "users"
                in inspect(current_app.extensions["database_engine"]).get_table_names()
            ):
                raise click.ClickException(
                    "PostgreSQL já possui schema; use migrate-db com --backup."
                )
        init_db()
        click.echo("Banco inicializado; registros existentes preservados.")

    @app.cli.command("migrate-db")
    @click.option(
        "--backup",
        type=click.Path(),
        help="Arquivo novo para pg_dump antes de migrar PostgreSQL existente.",
    )
    def migrate_db_command(backup):
        """Aplica migrações aditivas sem recriar tabelas ou registros."""
        database_path = Path(current_app.config["DATABASE"])
        if postgres():
            from sqlalchemy import inspect, text
            from app.services.backup_service import backup_postgres

            with current_app.extensions["database_engine"].connect() as conn:
                existing = "users" in inspect(conn).get_table_names()
            if existing and not backup:
                raise click.ClickException(
                    "PostgreSQL com usuários requer --backup antes de migrar."
                )
            if backup:
                try:
                    backup_postgres(current_app.config["DATABASE_URL"], backup)
                except (ValueError, OSError) as exc:
                    raise click.ClickException(str(exc)) from None
        if not postgres() and database_path.exists() and database_path.stat().st_size:
            backup_directory = database_path.parent / "backups"
            backup_directory.mkdir(exist_ok=True)
            filename = f"pre-migration-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{secrets.token_hex(3)}.sqlite3"
            with closing(sqlite3.connect(backup_directory / filename)) as backup:
                get_db().backup(backup)
            from app.services.backup_service import validate_sqlite

            try:
                validate_sqlite(backup_directory / filename)
            except sqlite3.Error, ValueError:
                raise click.ClickException(
                    "Migração cancelada: backup sem integridade válida."
                ) from None
            click.echo("Backup consistente criado na pasta backups ao lado do banco.")
        init_db()
        click.echo("Migrações aplicadas; registros existentes preservados.")

    @app.cli.command("backup-db")
    @click.option("--output", required=True, type=click.Path())
    def backup_db_command(output):
        from app.services.backup_service import backup_sqlite, backup_postgres

        try:
            if postgres():
                backup_postgres(current_app.config["DATABASE_URL"], output)
            else:
                backup_sqlite(current_app.config["DATABASE"], output)
        except (ValueError, OSError) as exc:
            raise click.ClickException(str(exc)) from None
        click.echo("Backup criado; proteja o arquivo e mantenha cópia externa.")

    @app.cli.command("restore-sqlite")
    @click.option("--source", required=True, type=click.Path(exists=True))
    @click.option("--output", required=True, type=click.Path())
    def restore_sqlite_command(source, output):
        from app.services.backup_service import (
            backup_sqlite,
            validate_sqlite,
            project_path,
        )

        try:
            if project_path(output) == Path(current_app.config["DATABASE"]).resolve():
                raise ValueError(
                    "Escolha um destino novo, diferente do banco da aplicação."
                )
            validate_sqlite(project_path(source))
            backup_sqlite(source, output)
        except (ValueError, OSError) as exc:
            raise click.ClickException(str(exc)) from None
        click.echo("Restauração validada em arquivo separado; banco atual preservado.")

    @app.cli.command("restore-postgres")
    @click.option("--source", required=True, type=click.Path(exists=True))
    def restore_postgres_command(source):
        from app.services.backup_service import restore_postgres

        target = os.getenv("RESTORE_DATABASE_URL", "")
        if not target:
            raise click.ClickException(
                "Defina RESTORE_DATABASE_URL para um banco novo e separado."
            )
        try:
            restore_postgres(source, target)
        except (ValueError, OSError) as exc:
            raise click.ClickException(str(exc)) from None
        click.echo(
            "Restauração concluída em destino separado; valide antes de trocar a conexão."
        )

    @app.cli.command("import-sqlite")
    @click.option("--source", required=True, type=click.Path(exists=True))
    def import_sqlite_command(source):
        from app.services.data_transfer import import_sqlite_snapshot

        try:
            summary = import_sqlite_snapshot(source)
        except Exception:
            raise click.ClickException(
                "Importação recusada ou inválida; dados do destino revertidos. Confira o snapshot e os requisitos."
            ) from None
        click.echo("Registros validados por tabela: " + str(summary))

    @app.cli.command("create-admin")
    def create_admin_command():
        """Cria administrador usando ADMIN_EMAIL, ADMIN_NAME e ADMIN_PASSWORD."""
        from app.models.user import create_user, find_by_email
        from app.services.validation import email_value, text_value

        try:
            email = email_value(os.getenv("ADMIN_EMAIL", ""), required=True)
            name = text_value(os.getenv("ADMIN_NAME", "Administrador"), "Nome", 2, 80)
            password = os.getenv("ADMIN_PASSWORD", "")
            if len(password) < 12 or len(password) > 128:
                raise ValueError("ADMIN_PASSWORD deve ter entre 12 e 128 caracteres.")
            if find_by_email(email):
                raise ValueError("Administrador já existe; a senha não foi alterada.")
            create_user(name, email, password, company_id=1)
        except (ValueError, sqlite3.OperationalError) as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo("Administrador criado com sucesso.")
