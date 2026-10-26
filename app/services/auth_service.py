"""Cadastro pendente, verificação e recuperação sem confiar em dados do navegador."""

import hashlib
import hmac
import re
import secrets
import time

from flask import current_app, request
from werkzeug.security import generate_password_hash

from app.models.user import find_by_email
from app.models import verification
from app.security import consume_rate_limit
from app.services.email_service import queue_code
from app.services.outbox_service import enqueue
from app.services.validation import email_value, text_value


def validate_password(password, confirmation):
    if not (
        12 <= len(password) <= 128
        and re.search(r"[a-z]", password)
        and re.search(r"[A-Z]", password)
        and re.search(r"[0-9]", password)
        and re.search(r"[^\w\s]", password)
    ):
        raise ValueError(
            "Use de 12 a 128 caracteres, com maiúscula, minúscula, número e símbolo."
        )
    if password != confirmation:
        raise ValueError("A confirmação da senha não confere.")
    return password


def code_digest(challenge_id, purpose, code):
    message = f"{challenge_id}|{purpose}|{code}".encode()
    return hmac.new(
        current_app.secret_key.encode(), message, hashlib.sha256
    ).hexdigest()


def allowed(action, email=""):
    ip = request.remote_addr or "unknown"
    if action == "signup":
        limit, window = 5, 3600
    else:
        limit, window = (20, 900) if action == "verify" else (10, 900)
    ip_allowed = consume_rate_limit(f"{action}:ip", ip, limit, window)
    email_allowed = consume_rate_limit(
        f"{action}:email", email, 20 if action == "verify" else 3, 900
    )
    return ip_allowed and email_allowed


def request_code(purpose, form):
    email = email_value(form.get("email", ""), required=True)
    name = company_name = password_hash = None
    if purpose == "signup":
        name = text_value(form.get("name", ""), "Nome completo", 2, 80)
        company_name = text_value(
            form.get("company_name", ""), "Nome da empresa", 2, 100
        )
        password = validate_password(
            form.get("password", ""), form.get("confirm_password", "")
        )
    if not allowed(purpose, email):
        return None
    if purpose == "signup":
        password_hash = generate_password_hash(password)
    user = find_by_email(email)
    challenge_id = secrets.token_urlsafe(32)
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = time.time()
    data = {
        "id": challenge_id,
        "purpose": purpose,
        "email": email,
        "user_id": user["id"] if user and user["email_verified"] else None,
        "name": name,
        "company_name": company_name,
        "password_hash": password_hash,
        "code_hash": code_digest(challenge_id, purpose, code),
        "created_at": now,
        "sent_at": now,
        "expires_at": now + current_app.config["CODE_TTL"],
    }
    deliver = purpose == "signup" or bool(user and user["email_verified"])
    durable = current_app.config["EMAIL_DELIVERY_MODE"] == "outbox"
    verification.create_challenge(
        data, (lambda row: enqueue(row, code)) if durable and deliver else None
    )
    if not durable:
        queue_code(
            email,
            code,
            purpose,
            deliver=deliver,
        )
    return challenge_id


def resend_code(challenge_id, purpose):
    row = verification.get_challenge(challenge_id, purpose)
    email = row["email"] if row else ""
    if not allowed("resend", email):
        return False
    code = f"{secrets.randbelow(1_000_000):06d}"
    if row and hmac.compare_digest(
        code_digest(challenge_id, purpose, code), row["code_hash"] or ""
    ):
        # Mesmo em uma coincidência aleatória, o valor numérico anterior é invalidado.
        code = f"{(int(code)+1) % 1_000_000:06d}"
    previous = verification.rotate_code(
        challenge_id,
        purpose,
        code_digest(challenge_id, purpose, code),
        (
            (lambda updated: enqueue(updated, code))
            if current_app.config["EMAIL_DELIVERY_MODE"] == "outbox"
            and row
            and (purpose == "signup" or row["user_id"] is not None)
            else None
        ),
    )
    if previous and current_app.config["EMAIL_DELIVERY_MODE"] != "outbox":
        queue_code(
            email,
            code,
            purpose,
            deliver=purpose == "signup" or previous["user_id"] is not None,
        )
    return previous is not None


def verify_code(challenge_id, purpose, code):
    row = verification.get_challenge(challenge_id, purpose)
    if not allowed("verify", row["email"] if row else ""):
        return False, None
    supplied = code if re.fullmatch(r"[0-9]{6}", code) else "invalid"
    token = secrets.token_urlsafe(32) if purpose == "reset" else None
    success = verification.consume_code(
        challenge_id, purpose, code_digest(challenge_id, purpose, supplied), token
    )
    return success, token if success else None


def change_password(challenge_id, token, form):
    password = validate_password(
        form.get("password", ""), form.get("confirm_password", "")
    )
    return verification.finish_reset(
        challenge_id, token, generate_password_hash(password)
    )
