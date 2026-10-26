from pathlib import Path
import sqlite3
from contextlib import closing

from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from app.database import get_db, init_db
from app.migrations import migrate


def test_legacy_migration_preserves_ids_passwords_history_and_settings(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "legacy-migration-" + "x" * 40,
            "DATABASE": str(tmp_path / "legacy.sqlite3"),
        }
    )
    password_hash = generate_password_hash("SenhaLegada123!")
    with app.app_context():
        db = get_db()
        db.executescript(
            (Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text(
                encoding="utf-8"
            )
        )
        db.execute(
            "INSERT INTO users(id,name,email,password_hash) VALUES(17,'Legado','legado@example.test',?)",
            (password_hash,),
        )
        db.execute(
            "INSERT INTO employees(id,name,role,department,weekly_hours) VALUES(28,'Pessoa Legada','Analista','Equipe',36)"
        )
        db.execute(
            "INSERT INTO shifts(id,name,start_time,end_time,break_minutes,color) VALUES(39,'Legado','22:00','06:00',60,'#2563EB')"
        )
        db.execute(
            "INSERT INTO schedules(id,employee_id,shift_id,work_date,start_at,end_at,shift_name,break_minutes,color) "
            "VALUES(40,28,39,'2026-10-12','2026-10-12T22:00:00','2026-10-13T06:00:00','Legado',60,'#2563EB')"
        )
        db.execute(
            "INSERT INTO unavailabilities(id,employee_id,start_at,end_at,reason) VALUES(51,28,'2026-10-14T00:00:00','2026-10-15T00:00:00','Folga')"
        )
        db.execute(
            "UPDATE settings SET company_name='Empresa Legada',min_rest_hours=11,weekly_alerts=0 WHERE id=1"
        )
        db.commit()
    runner = app.test_cli_runner()
    assert runner.invoke(args=["migrate-db"]).exit_code == 0
    assert runner.invoke(args=["migrate-db"]).exit_code == 0
    with app.app_context():
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id=17").fetchone()
        assert user["company_id"] == 1 and user["email_verified"] == 1
        assert user["password_hash"] == password_hash and check_password_hash(
            user["password_hash"], "SenhaLegada123!"
        )
        for table, record_id in [
            ("employees", 28),
            ("shifts", 39),
            ("schedules", 40),
            ("unavailabilities", 51),
        ]:
            assert (
                db.execute(
                    f"SELECT company_id FROM {table} WHERE id=?", (record_id,)
                ).fetchone()[0]
                == 1
            )
        assert (
            db.execute("SELECT start_at FROM schedules WHERE id=40").fetchone()[0]
            == "2026-10-12T22:00:00"
        )
        settings = db.execute(
            "SELECT * FROM company_settings WHERE company_id=1"
        ).fetchone()
        assert (
            settings["company_name"],
            settings["min_rest_hours"],
            settings["weekly_alerts"],
        ) == ("Empresa Legada", 11, 0)
        assert db.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM companies").fetchone()[0] == 1
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    backups = list((tmp_path / "backups").glob("*.sqlite3"))
    assert len(backups) == 2
    with closing(sqlite3.connect(backups[0])) as backup:
        assert (
            backup.execute("SELECT password_hash FROM users WHERE id=17").fetchone()[0]
            == password_hash
        )


def test_migration_rolls_back_atomically_on_legacy_invalid_foreign_key(tmp_path):
    import pytest

    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "legacy-invalid-" + "x" * 40,
            "DATABASE": str(tmp_path / "invalid.sqlite3"),
        }
    )
    with app.app_context():
        db = get_db()
        db.executescript(
            (Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text(
                encoding="utf-8"
            )
        )
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute(
            "INSERT INTO unavailabilities(employee_id,start_at,end_at,reason) VALUES(999,'2026-10-12','2026-10-13','Inválido')"
        )
        db.commit()
        db.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(RuntimeError, match="referências inválidas"):
            migrate(db)
        assert "company_id" not in {
            row["name"] for row in db.execute("PRAGMA table_info(users)")
        }
        assert db.execute("SELECT count(*) FROM unavailabilities").fetchone()[0] == 1


def test_migration_backup_closes_every_sqlite_connection(app, monkeypatch):
    import pytest

    original = sqlite3.connect
    connections = []

    def connect(*args, **kwargs):
        connection = original(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)
    assert app.test_cli_runner().invoke(args=["migrate-db"]).exit_code == 0
    assert len(connections) >= 2
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")
