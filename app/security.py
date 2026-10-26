"""Autorização e limitação persistente de tentativas de login."""

import hashlib
import time
from functools import wraps

from flask import g, redirect, request, url_for

from app.database import get_db, parameters


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


def login_key(email):
    return hashlib.sha256(f"{request.remote_addr}|{email}".encode()).hexdigest()


def login_blocked(identifier):
    row = (
        get_db()
        .execute(
            "SELECT * FROM login_attempts WHERE identifier=:p0",
            parameters((identifier,)),
        )
        .fetchone()
    )
    return row is not None and row["expires_at"] > time.time() and row["failures"] >= 5


def record_login(identifier, success):
    db = get_db()
    now = time.time()
    db.execute("DELETE FROM login_attempts WHERE expires_at < :p0", parameters((now,)))
    if success:
        db.execute(
            "DELETE FROM login_attempts WHERE identifier=:p0", parameters((identifier,))
        )
    else:
        db.execute(
            "INSERT INTO login_attempts(identifier,failures,expires_at) VALUES(:p0,1,:p1) ON CONFLICT(identifier) DO UPDATE SET failures=login_attempts.failures+1",
            parameters((identifier, now + 900)),
        )
    db.commit()


def consume_rate_limit(scope, identity, limit, window):
    """Contagem atômica e persistente, inclusive para identidades inexistentes."""
    identifier = hashlib.sha256(f"{scope}|{identity}".encode()).hexdigest()
    now = time.time()
    db = get_db()
    db.execute("DELETE FROM rate_limits WHERE expires_at <= :p0", parameters((now,)))
    row = db.execute(
        "INSERT INTO rate_limits(identifier,count,expires_at) VALUES(:p0,1,:p1) ON CONFLICT(identifier) DO UPDATE SET count=rate_limits.count+1 RETURNING count",
        parameters((identifier, now + window)),
    ).fetchone()
    db.commit()
    return row["count"] <= limit
