"""Migrações aditivas, transacionais e idempotentes para bancos existentes."""

import time


def migrate(db):
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at REAL NOT NULL)"
        )
        if db.execute("SELECT 1 FROM schema_migrations WHERE version=1").fetchone():
            db.commit()
            return
        db.execute(
            "CREATE TABLE IF NOT EXISTS companies(id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        legacy = db.execute(
            "SELECT company_name,min_rest_hours,weekly_alerts FROM settings WHERE id=1"
        ).fetchone()
        db.execute(
            "INSERT OR IGNORE INTO companies(id,name) VALUES(1,?)",
            (legacy["company_name"],),
        )
        db.execute("""CREATE TABLE IF NOT EXISTS company_settings(
            company_id INTEGER PRIMARY KEY REFERENCES companies(id) ON DELETE RESTRICT,
            company_name TEXT NOT NULL,
            min_rest_hours REAL NOT NULL DEFAULT 0 CHECK(min_rest_hours BETWEEN 0 AND 72),
            weekly_alerts INTEGER NOT NULL DEFAULT 1 CHECK(weekly_alerts IN (0,1)))""")
        db.execute(
            "INSERT OR IGNORE INTO company_settings VALUES(1,?,?,?)", tuple(legacy)
        )
        for table in ("users", "employees", "shifts", "schedules", "unavailabilities"):
            columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
            if "company_id" not in columns:
                db.execute(
                    f"ALTER TABLE {table} ADD COLUMN company_id INTEGER REFERENCES companies(id) ON DELETE RESTRICT"
                )
            db.execute(f"UPDATE {table} SET company_id=1 WHERE company_id IS NULL")
            db.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_company ON {table}(company_id,id)"
            )
            # ALTER TABLE não permite acrescentar NOT NULL sem um valor padrão.
            # Os gatilhos evitam um padrão silencioso que misturaria empresas.
            db.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_company_required
                BEFORE INSERT ON {table} WHEN NEW.company_id IS NULL
                BEGIN SELECT RAISE(ABORT,'company_id is required'); END""")
            db.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_company_immutable
                BEFORE UPDATE OF company_id ON {table} WHEN OLD.company_id IS NOT NEW.company_id
                BEGIN SELECT RAISE(ABORT,'company_id is immutable'); END""")
        columns = {row["name"] for row in db.execute("PRAGMA table_info(users)")}
        if "email_verified" not in columns:
            db.execute(
                "ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 1 CHECK(email_verified IN (0,1))"
            )
        for action in ("INSERT", "UPDATE OF employee_id,shift_id,company_id"):
            suffix = "insert" if action == "INSERT" else "update"
            db.execute(f"""CREATE TRIGGER IF NOT EXISTS schedule_tenant_{suffix}
                BEFORE {action} ON schedules
                WHEN NOT EXISTS(SELECT 1 FROM employees WHERE id=NEW.employee_id AND company_id=NEW.company_id)
                  OR NOT EXISTS(SELECT 1 FROM shifts WHERE id=NEW.shift_id AND company_id=NEW.company_id)
                BEGIN SELECT RAISE(ABORT,'cross-company assignment'); END""")
        for action in ("INSERT", "UPDATE OF employee_id,company_id"):
            suffix = "insert" if action == "INSERT" else "update"
            db.execute(f"""CREATE TRIGGER IF NOT EXISTS unavailability_tenant_{suffix}
                BEFORE {action} ON unavailabilities
                WHEN NOT EXISTS(SELECT 1 FROM employees WHERE id=NEW.employee_id AND company_id=NEW.company_id)
                BEGIN SELECT RAISE(ABORT,'cross-company unavailability'); END""")
        db.execute("""CREATE TABLE IF NOT EXISTS email_challenges(
            id TEXT PRIMARY KEY,
            purpose TEXT NOT NULL CHECK(purpose IN ('signup','reset')),
            email TEXT NOT NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            name TEXT, company_name TEXT, password_hash TEXT,
            code_hash TEXT,
            created_at REAL NOT NULL, sent_at REAL NOT NULL, expires_at REAL NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
            used_at REAL,
            reset_token_hash TEXT, reset_expires_at REAL)""")
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_challenges_email ON email_challenges(email,purpose)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_challenges_expiry ON email_challenges(expires_at)"
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS rate_limits(
            identifier TEXT PRIMARY KEY, count INTEGER NOT NULL, expires_at REAL NOT NULL)"""
        )
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError(
                "Há referências inválidas no banco; a migração foi cancelada."
            )
        db.execute(
            "INSERT INTO schema_migrations(version,applied_at) VALUES(1,?)",
            (time.time(),),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
