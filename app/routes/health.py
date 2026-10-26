"""Saúde sem sessão, dados de empresa ou detalhes de conexão."""

from flask import Blueprint, jsonify
from flask import current_app
from pathlib import Path
from app.database import get_db, postgres

bp = Blueprint("health", __name__)
SCHEMA_REVISION = "0002_outbox"


@bp.get("/health/live")
def live():
    return jsonify(status="ok")


@bp.get("/health/ready")
def ready():
    try:
        if not postgres() and not Path(current_app.config["DATABASE"]).is_file():
            raise RuntimeError
        db = get_db()
        if postgres():
            db.execute("SET LOCAL statement_timeout=1200")
            db.execute("SET LOCAL lock_timeout=1000")
        row = db.execute("SELECT version_num FROM alembic_version").fetchone()
        if row is None or row[0] != SCHEMA_REVISION:
            raise RuntimeError
        db.execute("SELECT company_id FROM company_settings LIMIT 1").fetchone()
        db.execute("SELECT id FROM email_outbox LIMIT 1").fetchone()
        return jsonify(status="ok")
    except Exception:
        return jsonify(status="unavailable"), 503
