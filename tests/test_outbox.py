import json
from types import SimpleNamespace
from contextlib import nullcontext
from urllib.error import HTTPError
from io import BytesIO

import pytest
from alembic import command
from cryptography.fernet import Fernet

from app import create_app
from app.database import get_db, migration_config
from app.services.outbox_service import claim, finish, process_one
from app.services.email_service import send_code, EmailDeliveryError
from conftest import post
from test_account_flows import signup


@pytest.fixture
def durable(app):
    app.config.update(
        EMAIL_DELIVERY_MODE="outbox", EMAIL_OUTBOX_KEY=Fernet.generate_key().decode()
    )
    return app


def task_row(app):
    with app.app_context():
        return dict(
            get_db()
            .execute("SELECT * FROM email_outbox ORDER BY created_at DESC LIMIT 1")
            .fetchone()
        )


def test_outbox_is_encrypted_and_survives_new_application(durable, client):
    assert signup(client).status_code == 302
    assert durable.extensions["email_outbox"] == []
    row = task_row(durable)
    assert (
        row["payload"].startswith("gAAAA") and "nova@example.test" not in row["payload"]
    )
    restored = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": durable.secret_key,
            "DATABASE": durable.config["DATABASE"],
            "EMAIL_DELIVERY_MODE": "outbox",
            "EMAIL_OUTBOX_KEY": durable.config["EMAIL_OUTBOX_KEY"],
        }
    )
    sent = []
    restored.extensions["email_sender"] = lambda *args: sent.append(args)
    with restored.app_context():
        assert process_one() and not process_one()
    assert sent[0][0] == "nova@example.test" and len(sent[0][1]) == 6
    assert (
        task_row(durable)["status"] == "sent" and task_row(durable)["payload"] is None
    )


def test_enqueue_failure_rolls_back_challenge_and_task(durable, client, monkeypatch):
    def fail(*args):
        raise RuntimeError("fictitious encryption failure")

    monkeypatch.setattr("app.services.auth_service.enqueue", fail)
    with pytest.raises(RuntimeError):
        signup(client)
    with durable.app_context():
        assert (
            get_db().execute("SELECT count(*) FROM email_challenges").fetchone()[0] == 0
        )
        assert get_db().execute("SELECT count(*) FROM email_outbox").fetchone()[0] == 0


def test_resend_cancels_old_queued_code(durable, client):
    signup(client)
    with durable.app_context():
        get_db().execute("UPDATE email_challenges SET sent_at=sent_at-61")
        get_db().commit()
    assert (
        post(client, "/verify/signup/resend", {}, "/verify/signup").status_code == 302
    )
    with durable.app_context():
        assert process_one() and process_one()
        assert [
            row[0]
            for row in get_db()
            .execute("SELECT status FROM email_outbox ORDER BY created_at,id")
            .fetchall()
        ] == ["cancelled", "sent"]
    assert len(durable.extensions["email_outbox"]) == 1


def test_expired_task_is_purged_without_sending(durable, client):
    signup(client)
    with durable.app_context():
        get_db().execute("UPDATE email_outbox SET expires_at=0")
        get_db().commit()
        assert not process_one()
    assert (
        task_row(durable)["status"] == "cancelled"
        and task_row(durable)["payload"] is None
    )
    assert not durable.extensions["email_outbox"]


def test_leases_recover_and_stale_worker_cannot_ack(durable, client):
    signup(client)
    with durable.app_context():
        first = claim()
        assert claim() is None
        get_db().execute("UPDATE email_outbox SET lease_until=0")
        get_db().commit()
        second = claim()
        assert (
            second["id"] == first["id"]
            and second["lease_token"] != first["lease_token"]
        )
        finish(first, "sent")
        assert (
            get_db().execute("SELECT status FROM email_outbox").fetchone()[0]
            == "sending"
        )
        finish(second, "sent")
    assert task_row(durable)["status"] == "sent"


def test_retry_limit_and_logs_redact_transport_errors(durable, client, caplog):
    signup(client)

    def fail(*args):
        raise EmailDeliveryError("private-recipient private-code private-key")

    durable.extensions["email_sender"] = fail
    with durable.app_context():
        for _ in range(5):
            get_db().execute("UPDATE email_outbox SET available_at=0")
            get_db().commit()
            assert process_one()
    row = task_row(durable)
    assert row["status"] == "failed" and row["payload"] is None and row["attempts"] == 5
    assert "private-" not in caplog.text


def test_wrong_encryption_key_fails_closed(durable, client):
    signup(client)
    durable.config["EMAIL_OUTBOX_KEY"] = Fernet.generate_key().decode()
    with durable.app_context():
        assert process_one()
    assert (
        task_row(durable)["status"] == "failed"
        and not durable.extensions["email_outbox"]
    )


def test_unknown_reset_remains_neutral_without_delivery(durable, client):
    response = post(
        client,
        "/forgot-password",
        {"email": "unknown@example.test"},
        "/forgot-password",
    )
    assert response.status_code == 302
    with durable.app_context():
        assert get_db().execute("SELECT count(*) FROM email_outbox").fetchone()[0] == 0


def test_worker_cli_and_downgrade_guard(durable, client):
    signup(client)
    with durable.app_context():
        with pytest.raises(RuntimeError, match="Rollback recusado"):
            command.downgrade(migration_config(), "0001_baseline")
    assert (
        durable.test_cli_runner().invoke(args=["mail-worker", "--once"]).exit_code == 0
    )
    assert task_row(durable)["status"] == "sent"


def fake_api(app, monkeypatch, *, response=None, error=None):
    captured = {}

    def factory(*handlers):
        assert handlers[0]._context.check_hostname

        def open_request(request, **kwargs):
            captured.update(request=request, **kwargs)
            if error:
                raise error
            return nullcontext(
                response
                or SimpleNamespace(status=200, read=lambda limit: b'{"id":"fake-id"}')
            )

        return SimpleNamespace(open=open_request)

    monkeypatch.setattr("app.services.email_service.build_opener", factory)
    app.extensions.pop("email_sender", None)
    app.config.update(
        MAIL_TRANSPORT="resend",
        RESEND_API_KEY="fake-private-api-key",
        MAIL_FROM="sender@example.test",
    )
    return captured


def test_resend_https_payload_tls_and_idempotency(app, monkeypatch, caplog):
    captured = fake_api(app, monkeypatch)
    with app.app_context():
        send_code(
            "recipient@example.test",
            "012345",
            "signup",
            idempotency_key="escalapro/fake-task",
        )
    req = captured["request"]
    assert req.full_url == "https://api.resend.com/emails"
    assert req.get_header("Idempotency-key") == "escalapro/fake-task"
    payload = json.loads(req.data)
    assert payload["to"] == ["recipient@example.test"]
    assert "012345" in payload["html"] and "012345" in payload["text"]
    assert captured["timeout"] == 10 and "fake-private-api-key" not in caplog.text


@pytest.mark.parametrize(
    ("status", "retryable"),
    [(401, False), (422, False), (429, True), (503, True), (302, False)],
)
def test_resend_failures_never_expose_response(app, monkeypatch, status, retryable):
    error = HTTPError(
        "https://api.resend.com/emails",
        status,
        "private-code",
        {},
        BytesIO(b"private-body"),
    )
    fake_api(app, monkeypatch, error=error)
    with app.app_context():
        with pytest.raises(EmailDeliveryError) as result:
            send_code("recipient@example.test", "123456", "reset")
    assert result.value.retryable is retryable and "private" not in str(result.value)


def test_invalid_api_response_is_not_success(app, monkeypatch):
    fake_api(
        app, monkeypatch, response=SimpleNamespace(status=200, read=lambda limit: b"[]")
    )
    with app.app_context():
        with pytest.raises(EmailDeliveryError):
            send_code("recipient@example.test", "123456", "reset")


def test_abandoned_tasks_stop_after_attempt_limit(durable, client):
    signup(client)
    with durable.app_context():
        get_db().execute(
            "UPDATE email_outbox SET status='sending',lease_until=0,attempts=5"
        )
        get_db().commit()
        assert claim() is None
    assert (
        task_row(durable)["status"] == "failed" and task_row(durable)["payload"] is None
    )


def test_disabled_worker_preserves_pending_tasks(durable, client):
    signup(client)
    durable.extensions.pop("email_sender")
    durable.config["MAIL_TRANSPORT"] = "disabled"
    result = durable.test_cli_runner().invoke(args=["mail-worker", "--once"])
    assert result.exit_code == 1
    assert (
        task_row(durable)["status"] == "pending"
        and task_row(durable)["payload"] is not None
    )
