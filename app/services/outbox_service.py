"""Entrega durável com payload autenticado, lease e retentativas limitadas."""

import json
import random
import secrets
import time

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

from app.database import get_db, begin_write, postgres


def enqueue(challenge, code):
    """Participa da mesma transação que cria/rotaciona o desafio."""
    task_id = secrets.token_hex(24)
    data = {
        "task_id": task_id,
        "challenge_id": challenge["id"],
        "code_hash": challenge["code_hash"],
        "recipient": challenge["email"],
        "code": code,
        "purpose": challenge["purpose"],
    }
    payload = (
        Fernet(current_app.config["EMAIL_OUTBOX_KEY"].encode())
        .encrypt(json.dumps(data).encode())
        .decode()
    )
    get_db().execute(
        "INSERT INTO email_outbox(id,challenge_id,code_hash,payload,status,available_at,expires_at,created_at) VALUES(:id,:challenge,:digest,:payload,'pending',:now,:expires,:now)",
        {
            "id": task_id,
            "challenge": challenge["id"],
            "digest": challenge["code_hash"],
            "payload": payload,
            "now": time.time(),
            "expires": challenge["expires_at"],
        },
    )


def claim():
    now = time.time()
    db = get_db()
    begin_write()
    try:
        # Expira leases abandonados; o token impede ACK de um trabalhador antigo.
        db.execute(
            "UPDATE email_outbox SET status='pending',lease_token=NULL,lease_until=NULL WHERE status='sending' AND lease_until<=:now",
            {"now": now},
        )
        db.execute(
            "UPDATE email_outbox SET status='cancelled',payload=NULL WHERE status IN ('pending','sending') AND expires_at<=:now",
            {"now": now},
        )
        suffix = " FOR UPDATE SKIP LOCKED" if postgres() else ""
        db.execute(
            "UPDATE email_outbox SET status='failed',payload=NULL WHERE status='pending' AND attempts>=5"
        )
        row = db.execute(
            "SELECT * FROM email_outbox WHERE status='pending' AND available_at<=:now AND expires_at>:now ORDER BY created_at,id LIMIT 1"
            + suffix,
            {"now": now},
        ).fetchone()
        if row is None:
            db.commit()
            return None
        token = secrets.token_urlsafe(24)
        db.execute(
            "UPDATE email_outbox SET status='sending',attempts=attempts+1,lease_until=:lease,lease_token=:token WHERE id=:id",
            {"lease": now + 90, "token": token, "id": row["id"]},
        )
        db.commit()
        return {**dict(row), "lease_token": token, "attempts": row["attempts"] + 1}
    except Exception:
        db.rollback()
        raise


def finish(task, status, *, retry=False):
    now = time.time()
    if retry and task["attempts"] < 5 and task["expires_at"] > now:
        status = "pending"
    keep = status == "pending"
    get_db().execute(
        "UPDATE email_outbox SET status=:status,payload=:payload,available_at=:available,lease_token=NULL,lease_until=NULL WHERE id=:id AND status='sending' AND lease_token=:lease",
        {
            "status": status,
            "payload": task["payload"] if keep else None,
            "available": now
            + min(120, 5 * 2 ** task["attempts"])
            + random.uniform(0, 3),
            "id": task["id"],
            "lease": task["lease_token"],
        },
    )
    get_db().commit()


def process_one():
    from app.services.email_service import send_code, EmailDeliveryError

    task = claim()
    if task is None:
        return False
    row = (
        get_db()
        .execute(
            "SELECT code_hash,used_at,expires_at FROM email_challenges WHERE id=:id",
            {"id": task["challenge_id"]},
        )
        .fetchone()
    )
    if (
        row is None
        or row["used_at"] is not None
        or row["expires_at"] <= time.time()
        or row["code_hash"] != task["code_hash"]
    ):
        finish(task, "cancelled")
        return True
    try:
        payload = json.loads(
            Fernet(current_app.config["EMAIL_OUTBOX_KEY"].encode()).decrypt(
                task["payload"].encode()
            )
        )
        if (payload["task_id"], payload["challenge_id"], payload["code_hash"]) != (
            task["id"],
            task["challenge_id"],
            task["code_hash"],
        ):
            raise InvalidToken
        send_code(
            payload["recipient"],
            payload["code"],
            payload["purpose"],
            idempotency_key="escalapro/" + task["id"],
        )
    except EmailDeliveryError as exc:
        finish(task, "failed", retry=exc.retryable)
        current_app.logger.warning("outbox_delivery_failed")
    except InvalidToken, ValueError, KeyError, TypeError:
        finish(task, "failed")
        current_app.logger.warning("outbox_payload_invalid")
    else:
        finish(task, "sent")
    return True
