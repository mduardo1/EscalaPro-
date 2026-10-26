"""Conexão configurada pela aplicação; não lê nem registra uma URL literal."""

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

cfg = context.config
url = cfg.attributes.get("url")
if url is None:
    from app import create_app
    from sqlalchemy.engine import URL

    app = create_app()
    url = app.config["DATABASE_URL"] or URL.create(
        "sqlite", database=app.config["DATABASE"]
    )

engine = create_engine(url, poolclass=NullPool, hide_parameters=True)
with engine.connect() as connection:
    if connection.dialect.name == "postgresql":
        connection.exec_driver_sql("SELECT pg_advisory_lock(828416022)")
        connection.commit()
    context.configure(
        connection=connection, target_metadata=None, transactional_ddl=True
    )
    try:
        with context.begin_transaction():
            context.run_migrations()
    finally:
        if connection.in_transaction():
            connection.rollback()
        if connection.dialect.name == "postgresql":
            connection.exec_driver_sql("SELECT pg_advisory_unlock(828416022)")
            connection.commit()
engine.dispose()
