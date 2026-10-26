"""Importação auditável de um snapshot SQLite para PostgreSQL vazio."""

import sqlite3
from contextlib import closing

from app.database import get_db, postgres, begin_write
from app.services.backup_service import project_path, validate_sqlite

TABLES = {
    "companies": ("id", "name"),
    "company_settings": (
        "company_id",
        "company_name",
        "min_rest_hours",
        "weekly_alerts",
    ),
    "users": ("id", "name", "email", "password_hash", "company_id", "email_verified"),
    "employees": (
        "id",
        "name",
        "role",
        "department",
        "email",
        "active",
        "weekly_hours",
        "company_id",
    ),
    "shifts": (
        "id",
        "name",
        "start_time",
        "end_time",
        "break_minutes",
        "color",
        "company_id",
    ),
    "schedules": (
        "id",
        "employee_id",
        "shift_id",
        "work_date",
        "start_at",
        "end_at",
        "shift_name",
        "break_minutes",
        "color",
        "company_id",
    ),
    "unavailabilities": (
        "id",
        "employee_id",
        "start_at",
        "end_at",
        "reason",
        "company_id",
    ),
    "settings": ("id", "company_name", "min_rest_hours", "weekly_alerts"),
}


def import_sqlite_snapshot(source):
    if not postgres():
        raise ValueError("Importação requer um destino PostgreSQL.")
    source = project_path(source)
    validate_sqlite(source)
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as origin:
        origin.row_factory = sqlite3.Row
        data = {
            table: [
                dict(row)
                for row in origin.execute(
                    f"SELECT {','.join(columns)} FROM {table} ORDER BY {columns[0]}"
                )
            ]
            for table, columns in TABLES.items()
        }
    db = get_db()
    begin_write("escalapro-snapshot-import")
    try:
        for table in (
            "users",
            "employees",
            "shifts",
            "schedules",
            "unavailabilities",
            "email_challenges",
            "auth_sessions",
            "email_outbox",
        ):
            if db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]:
                raise ValueError("O destino já contém registros; importação recusada.")
        company_rows = db.execute(
            "SELECT id,name FROM companies ORDER BY id"
        ).fetchall()
        if [tuple(row) for row in company_rows] != [(1, "Minha empresa")]:
            raise ValueError("O destino não é uma baseline nova.")
        preferences = db.execute(
            "SELECT * FROM company_settings WHERE company_id=1"
        ).fetchone()
        if (
            preferences is None
            or preferences["company_name"] != "Minha empresa"
            or preferences["min_rest_hours"] != 0
            or preferences["weekly_alerts"] != 1
        ):
            raise ValueError("Preferências do destino já foram alteradas.")
        for table in ("company_settings", "companies", "settings"):
            db.execute(f"DELETE FROM {table}")
        for table, columns in TABLES.items():
            statement = f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join(':'+key for key in columns)})"
            for row in data[table]:
                db.execute(statement, row)
            copied = [
                dict(row)
                for row in db.execute(
                    f"SELECT {','.join(columns)} FROM {table} ORDER BY {columns[0]}"
                ).fetchall()
            ]
            if copied != data[table]:
                raise ValueError("Validação de dados divergente; importação revertida.")
        for table in (
            "companies",
            "users",
            "employees",
            "shifts",
            "schedules",
            "unavailabilities",
        ):
            db.execute(
                f"SELECT setval(pg_get_serial_sequence(:table,'id'),COALESCE((SELECT max(id) FROM {table}),1),EXISTS(SELECT 1 FROM {table}))",
                {"table": table},
            )
        db.commit()
        return {table: len(rows) for table, rows in data.items()}
    except Exception:
        db.rollback()
        raise
