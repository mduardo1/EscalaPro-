import smtplib

import pytest

from app.services.email_service import EmailDeliveryError, queue_code, send_code


def test_smtp_uses_starttls_and_never_logs_credentials(app, monkeypatch, caplog):
    del app.extensions["email_sender"]
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, **kwargs):
            calls.append(("connect", host, port, kwargs))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self, **kwargs):
            calls.append(("tls", kwargs))

        def login(self, user, password):
            calls.append(("login", user, password))

        def send_message(self, message):
            calls.append(("message", message))

    monkeypatch.setattr("app.services.email_service.smtplib.SMTP", FakeSMTP)
    app.config.update(
        SMTP_HOST="smtp.example.test",
        SMTP_PORT=587,
        SMTP_USERNAME="test-user",
        SMTP_PASSWORD="temporary-mail-secret",
        SMTP_FROM="no-reply@example.test",
        SMTP_STARTTLS=True,
        SMTP_SSL=False,
    )
    with app.app_context():
        send_code("destino@example.test", "012345", "signup")
    assert [call[0] for call in calls] == ["connect", "tls", "login", "message"]
    message = calls[-1][1]
    assert message.get_content_type() == "multipart/alternative"
    assert "012345" in message.get_body(preferencelist=("plain",)).get_content()
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "012345" in html and "Confirme seu cadastro" in html
    assert "#2563EB" in html and "10 minutos" in html
    assert "012345" not in caplog.text and "temporary-mail-secret" not in caplog.text


def test_mail_failure_is_redacted(app, caplog):
    def fail(*args):
        raise smtplib.SMTPException("sensitive-code-123456 password-sentinel")

    app.extensions["email_sender"] = fail
    with app.app_context():
        queue_code("destino@example.test", "123456", "reset")
    assert "Falha no transporte" in caplog.text
    assert (
        "123456" not in caplog.text
        and "password-sentinel" not in caplog.text
        and "destino@example.test" not in caplog.text
    )


def test_mail_is_not_sent_for_unknown_recovery_and_queue_is_bounded(app):
    class InlineExecutor:
        def __init__(self):
            self.calls = 0

        def submit(self, fn):
            self.calls += 1
            fn()

    from threading import BoundedSemaphore

    executor = InlineExecutor()
    app.extensions["email_pool"] = executor
    app.extensions["email_capacity"] = BoundedSemaphore(1)
    app.config["TESTING"] = False
    with app.app_context():
        queue_code("unknown@example.test", "123456", "reset", deliver=False)
        queue_code("known@example.test", "123456", "reset")
        assert executor.calls == 2 and len(app.extensions["email_outbox"]) == 1
        app.extensions["email_capacity"].acquire()
        queue_code("known@example.test", "111111", "reset")
        assert executor.calls == 2


def test_smtp_ssl_and_starttls_cannot_both_be_enabled(monkeypatch):
    from app.config import Config

    monkeypatch.setenv("SMTP_SSL", "true")
    monkeypatch.setenv("SMTP_STARTTLS", "true")
    with pytest.raises(RuntimeError, match="sem ativar ambos"):
        Config()


def test_ssl_transport_validates_certificate_and_never_calls_starttls(app, monkeypatch):
    del app.extensions["email_sender"]
    calls = []

    class FakeSSL:
        def __init__(self, *args, **kwargs):
            assert kwargs["context"].check_hostname is True
            calls.append("ssl")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def send_message(self, message):
            calls.append("send")

        def starttls(self, **kwargs):
            raise AssertionError("STARTTLS não deve ser combinado com SSL")

    monkeypatch.setattr("app.services.email_service.smtplib.SMTP_SSL", FakeSSL)
    app.config.update(
        SMTP_HOST="smtp.example.test",
        SMTP_FROM="sender@example.test",
        SMTP_SSL=True,
        SMTP_STARTTLS=False,
    )
    with app.app_context():
        send_code("recipient@example.test", "000001", "reset")
    assert calls == ["ssl", "send"]


def test_production_smtp_requires_transport_encryption(monkeypatch):
    from app.config import Config

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_STARTTLS", "false")
    monkeypatch.setenv("SMTP_SSL", "false")
    with pytest.raises(RuntimeError, match="TLS em produção"):
        Config()


@pytest.mark.parametrize(
    ("purpose", "title", "description"),
    [
        ("signup", "Confirme seu cadastro", "ativar o espaço da sua empresa"),
        ("reset", "Recuperação de senha", "redefinição da sua senha"),
    ],
)
def test_smtp_message_has_matching_plain_and_html_content(
    app, monkeypatch, purpose, title, description
):
    del app.extensions["email_sender"]
    messages = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self, **kwargs):
            pass

        def send_message(self, message):
            messages.append(message)

    monkeypatch.setattr("app.services.email_service.smtplib.SMTP", FakeSMTP)
    app.config.update(SMTP_HOST="smtp.example.test", SMTP_FROM="sender@example.test")
    with app.app_context():
        send_code("recipient@example.test", "000123", purpose)
    message = messages[0]
    plain = message.get_body(preferencelist=("plain",)).get_content()
    html = message.get_body(preferencelist=("html",)).get_content()
    assert message["Subject"] == f"EscalaPro — {title}"
    assert title in plain and title in html and description in html
    assert "000123" in plain and "000123" in html
    assert "Não compartilhe" in plain and "Não compartilhe" in html
    assert '<html lang="pt-BR">' in html and 'role="presentation"' in html
