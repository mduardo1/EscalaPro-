import hashlib
import secrets
import time

from flask import current_app
from werkzeug.security import generate_password_hash

from app.database import get_db, parameters


def find_by_email(email):
    return (
        get_db()
        .execute(
            "SELECT * FROM users WHERE lower(email) = lower(:p0)", parameters((email,))
        )
        .fetchone()
    )


def find_by_id(user_id):
    return (
        get_db()
        .execute(
            "SELECT id, name, email, company_id, email_verified FROM users WHERE id = :p0",
            parameters((user_id,)),
        )
        .fetchone()
    )


def create_user(name, email, password, *, company_id, verified=True):
    """Provisionamento confiável por CLI; o cadastro público usa uma pendência."""
    db = get_db()
    db.execute(
        "INSERT INTO users(name,email,password_hash,company_id,email_verified) VALUES(:p0,:p1,:p2,:p3,:p4)",
        parameters(
            (name, email, generate_password_hash(password), company_id, int(verified))
        ),
    )
    db.commit()


def create_auth_session(user_id):
    token = secrets.token_urlsafe(32)
    now = time.time()
    expires_at = now + current_app.permanent_session_lifetime.total_seconds()
    db = get_db()
    db.execute("DELETE FROM auth_sessions WHERE expires_at <= :p0", parameters((now,)))
    db.execute(
        "INSERT INTO auth_sessions(token_hash,user_id,expires_at) VALUES(:p0,:p1,:p2)",
        parameters((hashlib.sha256(token.encode()).hexdigest(), user_id, expires_at)),
    )
    db.commit()
    return token


def find_session_user(token):
    if not isinstance(token, str) or len(token) != 43:
        return None
    return (
        get_db()
        .execute(
            "SELECT u.id,u.name,u.email,u.company_id FROM auth_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=:p0 AND s.expires_at > :p1 AND u.email_verified=1",
            parameters((hashlib.sha256(token.encode()).hexdigest(), time.time())),
        )
        .fetchone()
    )


def revoke_auth_session(token):
    if isinstance(token, str):
        db = get_db()
        db.execute(
            "DELETE FROM auth_sessions WHERE token_hash=:p0",
            parameters((hashlib.sha256(token.encode()).hexdigest(),)),
        )
        db.commit()
