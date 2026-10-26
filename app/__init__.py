"""Application factory do EscalaPro."""

import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, g, redirect, render_template, request, url_for
from flask.helpers import get_debug_flag
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.routing import IntegerConverter
from werkzeug.exceptions import SecurityError


class SQLiteIDConverter(IntegerConverter):
    """Limita IDs antes de convertê-los ou enviá-los ao SQLite."""

    regex = r"[1-9]\d{0,18}"

    def __init__(self, url_map):
        super().__init__(url_map, min=1, max=2**63 - 1)


def create_app(test_config=None):
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env", override=False)
    from app.config import Config

    app = Flask(
        __name__, instance_path=str(root / "instance"), instance_relative_config=True
    )
    app.config.from_object(Config())
    if test_config:
        app.config.update(test_config)
    if not app.config["SECRET_KEY"] or len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError(
            "Defina SECRET_KEY com pelo menos 32 caracteres no .env. Consulte .env.example."
        )
    if app.config["PRODUCTION"] and (app.debug or get_debug_flag()):
        raise RuntimeError("Desative FLASK_DEBUG em produção.")
    if app.config["PRODUCTION"]:
        if not app.config["DATABASE_URL"]:
            raise RuntimeError(
                "Produção requer DATABASE_URL PostgreSQL; SQLite não é fallback."
            )
        if not app.config["TRUSTED_HOSTS"]:
            raise RuntimeError("Produção requer TRUSTED_HOSTS.")
        if app.config["EMAIL_DELIVERY_MODE"] != "outbox":
            raise RuntimeError("Produção requer outbox persistente.")
        if app.config["MAIL_TRANSPORT"] == "resend" and not (
            app.config["RESEND_API_KEY"] and app.config["MAIL_FROM"]
        ):
            raise RuntimeError("Configure RESEND_API_KEY e MAIL_FROM para produção.")
        if app.config["MAIL_TRANSPORT"] == "smtp" and not (
            app.config["SMTP_HOST"] and app.config["SMTP_FROM"]
        ):
            raise RuntimeError("Configure SMTP_HOST e SMTP_FROM para produção.")
    if (
        app.config["EMAIL_DELIVERY_MODE"] == "outbox"
        and app.config["MAIL_TRANSPORT"] != "disabled"
    ):
        from cryptography.fernet import Fernet

        try:
            Fernet(app.config["EMAIL_OUTBOX_KEY"].encode())
            if app.config["EMAIL_OUTBOX_KEY"] == app.config["SECRET_KEY"]:
                raise ValueError
        except ValueError, TypeError:
            raise RuntimeError(
                "Configure EMAIL_OUTBOX_KEY com uma chave Fernet válida."
            ) from None
    Path(app.instance_path).mkdir(exist_ok=True)
    database_path = Path(
        app.config.get("DATABASE") or root / "instance" / "escalapro.sqlite3"
    )
    if not database_path.is_absolute():
        database_path = root / database_path
    if not database_path.resolve().is_relative_to(root):
        raise RuntimeError("DATABASE_PATH deve permanecer dentro da pasta EscalaPro.")
    app.config["DATABASE"] = str(database_path)

    from app.proxy import TrustedProxy

    app.wsgi_app = TrustedProxy(
        app.wsgi_app,
        app.config["TRUSTED_PROXY_NETWORKS"],
        app.config["PROXY_FOR_HOPS"],
        app.config["PROXY_PROTO_HOPS"],
    )

    from app import database

    database.init_app(app)
    CSRFProtect(app)
    app.url_map.converters["dbid"] = SQLiteIDConverter

    from app.routes import auth, dashboard, employees, schedules, shifts, health

    for module in (auth, dashboard, employees, shifts, schedules, health):
        app.register_blueprint(module.bp)

    @app.errorhandler(SecurityError)
    def invalid_host(_error):
        return (
            "Solicitação inválida.",
            400,
            {"Content-Type": "text/plain; charset=utf-8"},
        )

    @app.get("/")
    def index():
        if g.user:
            return redirect(url_for("dashboard.index"))
        return render_template("index.html", title="Gestão de escalas com clareza")

    @app.context_processor
    def shared_context():
        return {"current_user": getattr(g, "user", None)}

    @app.template_filter("datetime_br")
    def datetime_br(value):
        from datetime import datetime

        return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M")

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
        )
        if app.config["PRODUCTION"]:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(CSRFError)
    def csrf_error(_error):
        return (
            render_template(
                "error.html",
                title="Sessão do formulário expirada",
                code=400,
                message="Atualize a página e envie o formulário novamente.",
            ),
            400,
        )

    def http_error(error):
        return (
            render_template(
                "error.html",
                title="Não foi possível abrir esta página",
                code=error.code,
                message=error.description,
            ),
            error.code,
        )

    for code in (400, 404, 405, 413, 429):
        app.register_error_handler(code, http_error)

    @app.errorhandler(sqlite3.OperationalError)
    def database_error(error):
        app.logger.error("Falha no acesso ao banco de dados.")
        return (
            render_template(
                "error.html",
                title="Banco indisponível",
                code=503,
                message="Verifique se o banco foi inicializado e tente novamente.",
            ),
            503,
        )

    @app.errorhandler(500)
    def server_error(_error):
        return (
            render_template(
                "error.html",
                title="Erro interno",
                code=500,
                message="Não foi possível concluir a operação. Tente novamente.",
            ),
            500,
        )

    from sqlalchemy.exc import SQLAlchemyError

    app.register_error_handler(SQLAlchemyError, database_error)
    return app
