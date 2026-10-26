"""Backup consistente e restauração somente em destinos novos."""

import os
import shutil
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

from flask import current_app
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url
from psycopg.conninfo import make_conninfo


def project_path(value):
    path = Path(value).resolve()
    root = Path(__file__).resolve().parents[2]
    if not path.is_relative_to(root):
        raise ValueError("O arquivo deve permanecer dentro do projeto.")
    return path


def validate_sqlite(path):
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        if (
            db.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            or db.execute("PRAGMA foreign_key_check").fetchone()
        ):
            raise ValueError("Snapshot SQLite inválido; operação cancelada.")


def backup_sqlite(source, output):
    source, output = project_path(source), project_path(output)
    if not source.is_file():
        raise ValueError("Banco de origem inexistente.")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Criação exclusiva: nunca substitui um backup ou banco existente.
    with output.open("xb"):
        pass
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as origin:
        with closing(sqlite3.connect(output)) as target:
            origin.backup(target)
    validate_sqlite(output)
    return output


def postgres_environment(value):
    url = make_url(value)
    if url.drivername not in {"postgresql", "postgres", "postgresql+psycopg"}:
        raise ValueError("A conexão deve ser PostgreSQL.")
    env = os.environ.copy()
    env["PGPASSWORD"] = url.password or ""
    env["PGCONNECT_TIMEOUT"] = "5"
    values = {
        "user": url.username,
        "host": url.host,
        "port": url.port,
        "dbname": url.database,
        **url.query,
    }
    # libpq não interpreta '+' como espaço numa URI; conninfo preserva options/TLS.
    safe = make_conninfo(
        **{key: value for key, value in values.items() if value is not None}
    )
    return safe, env


def run_postgres_tool(tool, arguments, value):
    executable = shutil.which(tool)
    if executable is None:
        raise ValueError(
            f"Instale os clientes PostgreSQL e disponibilize {tool} no PATH."
        )
    dsn, env = postgres_environment(value)
    result = subprocess.run(
        [executable, *arguments, "--dbname", dsn],
        env=env,
        capture_output=True,
        timeout=300,
    )
    if result.returncode:
        raise ValueError(
            "Ferramenta PostgreSQL falhou; detalhes privados foram omitidos."
        )


def backup_postgres(value, output):
    output = project_path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb"):
        pass
    run_postgres_tool(
        "pg_dump",
        ["--format=custom", "--no-owner", "--no-privileges", "--file", str(output)],
        value,
    )
    if not output.stat().st_size:
        raise ValueError("Backup vazio; não prossiga com a migração.")
    return output


def restore_postgres(source, target):
    source = project_path(source)
    if not source.is_file():
        raise ValueError("Arquivo de backup inexistente.")
    destination = make_url(target).set(drivername="postgresql+psycopg")
    configured = current_app.config["DATABASE_URL"]
    if configured:
        current = make_url(configured)
        # Nome distinto também evita contornar a proteção usando alias de host.
        if destination.database == current.database:
            raise ValueError(
                "Restaure em outro banco, nunca no banco configurado da aplicação."
            )
    engine = create_engine(
        destination, hide_parameters=True, connect_args={"connect_timeout": 5}
    )
    try:
        with engine.connect() as conn:
            if any(
                inspect(conn).get_table_names(schema=schema)
                for schema in inspect(conn).get_schema_names()
                if schema not in {"information_schema", "pg_catalog"}
            ):
                raise ValueError("O destino de restauração deve estar vazio.")
    finally:
        engine.dispose()
    run_postgres_tool(
        "pg_restore",
        [
            "--exit-on-error",
            "--single-transaction",
            "--no-owner",
            "--no-privileges",
            str(source),
        ],
        destination,
    )
