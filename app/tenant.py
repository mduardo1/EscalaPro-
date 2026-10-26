"""A empresa vem exclusivamente da identidade autenticada no servidor."""

from flask import g


def company_id() -> int:
    user = getattr(g, "user", None)
    if user is None:
        raise RuntimeError("A operação requer um administrador autenticado.")
    return user["company_id"]
