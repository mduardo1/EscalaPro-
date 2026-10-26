"""SMTP com TLS; sem códigos em logs ou filas persistentes em texto puro."""

import smtplib
import ssl
import json
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
from urllib.error import HTTPError
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from threading import BoundedSemaphore, Lock

from flask import current_app, render_template

_pool_lock = Lock()


class EmailDeliveryError(Exception):
    def __init__(self, message="Envio de e-mail indisponível.", *, retryable=True):
        super().__init__(message)
        self.retryable = retryable


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_resend(payload, idempotency_key=None):
    headers = {
        "Authorization": "Bearer " + current_app.config["RESEND_API_KEY"],
        "Content-Type": "application/json",
        "User-Agent": "EscalaPro/1",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    req = Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    opener = build_opener(
        HTTPSHandler(context=ssl.create_default_context()), NoRedirect()
    )
    try:
        with opener.open(req, timeout=10) as response:
            body = json.loads(response.read(4096))
            if (
                not 200 <= response.status < 300
                or not isinstance(body, dict)
                or not isinstance(body.get("id"), str)
            ):
                raise ValueError
    except HTTPError as exc:
        exc.close()
        raise EmailDeliveryError(
            retryable=exc.code in {408, 409, 429} or exc.code >= 500
        ) from None
    except OSError, ValueError:
        raise EmailDeliveryError() from None


def mail_ready():
    return bool(
        current_app.extensions.get("email_sender")
        or (
            current_app.config["MAIL_TRANSPORT"] == "resend"
            and current_app.config["RESEND_API_KEY"]
            and current_app.config["MAIL_FROM"]
        )
        or (
            current_app.config["MAIL_TRANSPORT"] == "smtp"
            and current_app.config["SMTP_HOST"]
            and current_app.config["SMTP_FROM"]
        )
    )


def send_code(recipient, code, purpose, *, idempotency_key=None):
    """Transporte síncrono. O chamador de produção o executa fora da requisição."""
    sender = current_app.extensions.get("email_sender")
    if sender:
        sender(recipient, code, purpose)
        return
    cfg = current_app.config
    if not mail_ready():
        raise EmailDeliveryError("Envio de e-mail indisponível.")
    message = EmailMessage()
    title = "Confirme seu cadastro" if purpose == "signup" else "Recuperação de senha"
    message["Subject"] = f"EscalaPro — {title}"
    message["From"] = cfg["SMTP_FROM"]
    message["To"] = recipient
    message.set_content(
        f"{title}\n\nSeu código EscalaPro é: {code}\n\n"
        "Ele expira em 10 minutos. Não compartilhe este código.\n"
        "Se não fez a solicitação, ignore esta mensagem. Seus dados não serão alterados.\n"
    )
    message.add_alternative(
        render_template(
            "emails/verification.html", title=title, code=code, purpose=purpose
        ),
        subtype="html",
    )
    if cfg["MAIL_TRANSPORT"] == "resend":
        post_resend(
            {
                "from": cfg["MAIL_FROM"],
                "to": [recipient],
                "subject": str(message["Subject"]),
                "text": message.get_body(preferencelist=("plain",)).get_content(),
                "html": message.get_body(preferencelist=("html",)).get_content(),
            },
            idempotency_key,
        )
        return
    try:
        transport = smtplib.SMTP_SSL if cfg["SMTP_SSL"] else smtplib.SMTP
        options = {"timeout": 10}
        if cfg["SMTP_SSL"]:
            options["context"] = ssl.create_default_context()
        with transport(cfg["SMTP_HOST"], cfg["SMTP_PORT"], **options) as server:
            if cfg["SMTP_STARTTLS"]:
                server.starttls(context=ssl.create_default_context())
            if cfg["SMTP_USERNAME"]:
                server.login(cfg["SMTP_USERNAME"], cfg["SMTP_PASSWORD"])
            server.send_message(message)
    except OSError, smtplib.SMTPException, ValueError:
        raise EmailDeliveryError("Não foi possível enviar o e-mail.") from None


def queue_code(recipient, code, purpose, *, deliver=True):
    app = current_app._get_current_object()

    def send():
        try:
            if deliver:
                with app.app_context():
                    send_code(recipient, code, purpose)
        except Exception:
            # Exceções SMTP podem conter credenciais, destinatários ou a mensagem.
            app.logger.warning(
                "Falha no transporte de e-mail; confira a configuração SMTP."
            )

    if app.testing:
        send()
        return
    with _pool_lock:
        if "email_pool" not in app.extensions:
            app.extensions["email_pool"] = ThreadPoolExecutor(
                max_workers=2, thread_name_prefix="escalapro-mail"
            )
            app.extensions["email_capacity"] = BoundedSemaphore(32)
    capacity = app.extensions["email_capacity"]
    if not capacity.acquire(blocking=False):
        app.logger.warning("Fila de e-mail temporariamente cheia.")
        return

    def task():
        try:
            send()
        finally:
            capacity.release()

    try:
        app.extensions["email_pool"].submit(task)
    except RuntimeError:
        capacity.release()
        app.logger.warning("Fila de e-mail indisponível.")
