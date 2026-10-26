"""Configuração externa; nenhum segredo é versionado."""

import os
from datetime import timedelta
from ipaddress import ip_network


def boolean(name, default=False):
    value = os.getenv(name, str(default)).strip().lower()
    if value not in {"true", "false", "1", "0", "yes", "no"}:
        raise RuntimeError(f"{name}: use true ou false.")
    return value in {"true", "1", "yes"}


def integer(name, default, minimum, maximum):
    try:
        value = int(os.getenv(name, str(default)))
        if not minimum <= value <= maximum:
            raise ValueError
        return value
    except ValueError:
        raise RuntimeError(f"{name}: valor numérico inválido.") from None


class Config:
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_REFRESH_EACH_REQUEST = False
    MAX_CONTENT_LENGTH = 1024 * 1024
    WTF_CSRF_TIME_LIMIT = 8 * 60 * 60
    CODE_TTL = 600
    CODE_RESEND_INTERVAL = 60
    CODE_MAX_ATTEMPTS = 5

    def __init__(self):
        # Avaliado a cada factory, depois de carregar o .env.
        self.SECRET_KEY = os.getenv("SECRET_KEY")
        self.DATABASE = os.getenv("DATABASE_PATH")
        self.APP_TIMEZONE = os.getenv("APP_TIMEZONE", "America/Sao_Paulo")
        self.APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
        if self.APP_ENV not in {"development", "testing", "production"}:
            raise RuntimeError("APP_ENV deve ser development, testing ou production.")
        self.PRODUCTION = self.APP_ENV == "production"
        self.DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
        self.DB_POOL_SIZE = integer("DB_POOL_SIZE", 3, 1, 20)
        self.DB_TIMEOUT = integer("DB_TIMEOUT", 3, 1, 10)
        self.TRUSTED_HOSTS = [
            host.strip()
            for host in os.getenv("TRUSTED_HOSTS", "").split(",")
            if host.strip()
        ] or None
        self.TRUSTED_PROXY_NETWORKS = [
            ip_network(value.strip())
            for value in os.getenv("TRUSTED_PROXY_NETWORKS", "").split(",")
            if value.strip()
        ]
        self.PROXY_HOPS = integer("PROXY_HOPS", 0, 0, 5)
        self.PROXY_FOR_HOPS = integer("PROXY_FOR_HOPS", self.PROXY_HOPS, 0, 5)
        self.PROXY_PROTO_HOPS = integer("PROXY_PROTO_HOPS", self.PROXY_HOPS, 0, 5)
        if (
            self.PROXY_FOR_HOPS or self.PROXY_PROTO_HOPS
        ) and not self.TRUSTED_PROXY_NETWORKS:
            raise RuntimeError("Configure TRUSTED_PROXY_NETWORKS ao ativar PROXY_HOPS.")
        self.SESSION_COOKIE_SECURE = self.PRODUCTION
        self.SMTP_HOST = os.getenv("SMTP_HOST", "")
        self.SMTP_PORT = integer("SMTP_PORT", 587, 1, 65535)
        self.SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
        self.SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
        self.SMTP_FROM = os.getenv("SMTP_FROM", "")
        self.SMTP_STARTTLS = boolean("SMTP_STARTTLS", True)
        self.SMTP_SSL = boolean("SMTP_SSL")
        self.MAIL_TRANSPORT = os.getenv("MAIL_TRANSPORT", "smtp").strip().lower()
        if self.MAIL_TRANSPORT not in {"smtp", "resend", "disabled"}:
            raise RuntimeError("MAIL_TRANSPORT deve ser smtp, resend ou disabled.")
        self.RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
        self.MAIL_FROM = os.getenv("MAIL_FROM", "") or self.SMTP_FROM
        self.EMAIL_DELIVERY_MODE = os.getenv(
            "EMAIL_DELIVERY_MODE", "outbox" if self.PRODUCTION else "memory"
        )
        if self.EMAIL_DELIVERY_MODE not in {"memory", "outbox"}:
            raise RuntimeError("EMAIL_DELIVERY_MODE deve ser memory ou outbox.")
        self.EMAIL_OUTBOX_KEY = os.getenv("EMAIL_OUTBOX_KEY", "")
        if self.SMTP_SSL and self.SMTP_STARTTLS:
            raise RuntimeError("Escolha SMTP_SSL ou SMTP_STARTTLS, sem ativar ambos.")
        if (
            self.PRODUCTION
            and self.MAIL_TRANSPORT == "smtp"
            and self.SMTP_HOST
            and not (self.SMTP_SSL or self.SMTP_STARTTLS)
        ):
            raise RuntimeError("SMTP requer TLS em produção.")
