"""Persistência dos códigos e consumo atômico de cada etapa da autenticação."""

import hashlib
import hmac
import time

from flask import current_app

from app.database import get_db, parameters, begin_write, postgres
from app.models.company import create_company


def get_challenge(challenge_id, purpose):
    if not isinstance(challenge_id, str) or len(challenge_id) != 43:
        return None
    return (
        get_db()
        .execute(
            "SELECT * FROM email_challenges WHERE id=:p0 AND purpose=:p1",
            parameters((challenge_id, purpose)),
        )
        .fetchone()
    )


def create_challenge(data, delivery=None):
    db = get_db()
    now = data["created_at"]
    begin_write("auth:" + data["email"])
    try:
        db.execute(
            "DELETE FROM email_challenges WHERE created_at < :p0",
            parameters((now - 86400,)),
        )
        db.execute(
            "UPDATE email_challenges SET used_at=:p0,code_hash=NULL,password_hash=NULL,reset_token_hash=NULL WHERE email=:p1 AND purpose=:p2",
            parameters((now, data["email"], data["purpose"])),
        )
        db.execute(
            "INSERT INTO email_challenges(id,purpose,email,user_id,name,company_name,password_hash,code_hash,created_at,sent_at,expires_at) "
            "VALUES(:id,:purpose,:email,:user_id,:name,:company_name,:password_hash,:code_hash,:created_at,:sent_at,:expires_at)",
            data,
        )
        if delivery:
            delivery(data)
        db.commit()
    except Exception:
        db.rollback()
        raise


def begin_challenge_write(challenge_id, purpose):
    if postgres():
        row = get_challenge(challenge_id, purpose)
        begin_write("auth:" + (row["email"] if row else str(challenge_id)))
    else:
        begin_write()


def rotate_code(challenge_id, purpose, code_hash, delivery=None):
    db = get_db()
    now = time.time()
    begin_challenge_write(challenge_id, purpose)
    try:
        row = get_challenge(challenge_id, purpose)
        valid = (
            row is not None
            and row["used_at"] is None
            and row["created_at"] > now - 86400
        )
        if (
            not valid
            or now - row["sent_at"] < current_app.config["CODE_RESEND_INTERVAL"]
        ):
            db.rollback()
            return None
        db.execute(
            "UPDATE email_challenges SET code_hash=:p0,sent_at=:p1,expires_at=:p2,attempts=0 WHERE id=:p3",
            parameters(
                (code_hash, now, now + current_app.config["CODE_TTL"], challenge_id)
            ),
        )
        if delivery:
            delivery(
                {
                    **dict(row),
                    "code_hash": code_hash,
                    "sent_at": now,
                    "expires_at": now + current_app.config["CODE_TTL"],
                }
            )
        db.commit()
        return row
    except Exception:
        db.rollback()
        raise


def consume_code(challenge_id, purpose, code_hash, reset_token=None):
    db = get_db()
    now = time.time()
    begin_challenge_write(challenge_id, purpose)
    try:
        row = get_challenge(challenge_id, purpose)
        matches = hmac.compare_digest(
            row["code_hash"] if row and row["code_hash"] else "0" * 64, code_hash
        )
        eligible = (
            row is not None
            and row["used_at"] is None
            and row["expires_at"] > now
            and row["attempts"] < current_app.config["CODE_MAX_ATTEMPTS"]
        )
        if not eligible:
            db.rollback()
            return False
        if not matches or (purpose == "reset" and row["user_id"] is None):
            attempts = row["attempts"] + 1
            db.execute(
                "UPDATE email_challenges SET attempts=:p0 WHERE id=:p1",
                parameters((attempts, challenge_id)),
            )
            db.commit()
            return False
        if purpose == "signup":
            exists = db.execute(
                "SELECT id FROM users WHERE email=:p0", parameters((row["email"],))
            ).fetchone()
            if exists is None:
                company_id = create_company(row["company_name"])
                db.execute(
                    "INSERT INTO users(name,email,password_hash,company_id,email_verified) VALUES(:p0,:p1,:p2,:p3,1)",
                    parameters(
                        (row["name"], row["email"], row["password_hash"], company_id)
                    ),
                )
            db.execute(
                "UPDATE email_challenges SET used_at=:p0,code_hash=NULL,password_hash=NULL WHERE id=:p1",
                parameters((now, challenge_id)),
            )
        else:
            db.execute(
                "UPDATE email_challenges SET used_at=:p0,code_hash=NULL,reset_token_hash=:p1,reset_expires_at=:p2 WHERE id=:p3",
                parameters(
                    (
                        now,
                        hashlib.sha256(reset_token.encode()).hexdigest(),
                        now + 600,
                        challenge_id,
                    )
                ),
            )
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def reset_grant(challenge_id, token):
    if not isinstance(token, str) or len(token) != 43:
        return None
    return (
        get_db()
        .execute(
            "SELECT * FROM email_challenges WHERE id=:p0 AND purpose='reset' AND reset_token_hash=:p1 AND reset_expires_at>:p2 AND user_id IS NOT NULL",
            parameters(
                (challenge_id, hashlib.sha256(token.encode()).hexdigest(), time.time())
            ),
        )
        .fetchone()
    )


def finish_reset(challenge_id, token, password_hash):
    db = get_db()
    begin_challenge_write(challenge_id, "reset")
    try:
        row = reset_grant(challenge_id, token)
        if row is None:
            db.rollback()
            return False
        db.execute(
            "UPDATE users SET password_hash=:p0 WHERE id=:p1 AND email_verified=1",
            parameters((password_hash, row["user_id"])),
        )
        db.execute(
            "DELETE FROM auth_sessions WHERE user_id=:p0", parameters((row["user_id"],))
        )
        db.execute(
            "UPDATE email_challenges SET reset_token_hash=NULL,reset_expires_at=NULL WHERE email=:p0 AND purpose='reset'",
            parameters((row["email"],)),
        )
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
