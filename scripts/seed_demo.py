"""Gera uma base fictícia nova; nunca lê .env nem reutiliza uma base existente."""

import argparse
import json
from contextlib import closing, contextmanager
from datetime import date, timedelta
import os
from pathlib import Path
import secrets
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DEMO_EMAIL = "admin.demo@example.com"


def demo_path(value: str) -> Path:
    if not value:
        raise ValueError("Informe --database ou DEMO_DATABASE_PATH explicitamente.")
    supplied = Path(value)
    path = supplied if supplied.is_absolute() else ROOT / supplied
    reserved = ROOT / "instance" / "demo"
    # Recusa links, inclusive nos diretórios ancestrais, e qualquer outra base.
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("Links simbólicos não são aceitos para a demonstração.")
    path = path.resolve()
    if path.parent != reserved.resolve() or not path.name.endswith(".demo.sqlite3"):
        raise ValueError("Use instance/demo/<nome>.demo.sqlite3, sem subdiretórios.")
    return path


@contextmanager
def isolated_environment(path: Path):
    original = os.environ.copy()
    try:
        # A factory não recebe credenciais, URL, opções Flask ou SMTP herdadas.
        keep = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "TZ"}
        os.environ.clear()
        os.environ.update(
            {key: value for key, value in original.items() if key in keep}
        )
        os.environ.update(
            PYTHON_DOTENV_DISABLED="1",
            APP_ENV="development",
            FLASK_DEBUG="0",
            SECRET_KEY=secrets.token_urlsafe(48),
            DATABASE_PATH=str(path),
            DATABASE_URL="",
            MAIL_TRANSPORT="disabled",
            EMAIL_DELIVERY_MODE="memory",
        )
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


def create_demo_app(path: Path):
    from app import create_app

    with isolated_environment(path):
        app = create_app()

    # Defesa adicional: nenhum transporte de rede, mesmo se chamado por engano.
    def refuse_delivery(*_args, **_kwargs):
        raise RuntimeError("Envio de e-mail desativado na demonstração.")

    app.extensions["email_sender"] = refuse_delivery
    return app


def require_demo(path: Path) -> None:
    if not path.is_file():
        raise ValueError("Gere primeiro um banco fictício novo com seed_demo.py.")
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            marker = db.execute("SELECT kind FROM demo_metadata WHERE id=1").fetchone()
            if marker != ("escalapro-fictional-v1",):
                raise ValueError
            if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError
            if db.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError
    except sqlite3.Error, ValueError:
        raise ValueError(
            "Base sem identificação ou integridade de demonstração."
        ) from None


def seed_demo(value: str, *, week: date | None = None) -> tuple[Path, str, date]:
    path = demo_path(value)
    if path.exists():
        raise ValueError(
            "Destino existente: nenhuma alteração foi realizada. Escolha outro nome."
        )
    day = week or date.today()
    monday = day - timedelta(days=day.weekday())
    if not date(2000, 1, 3) <= monday <= date(2099, 12, 14):
        raise ValueError(
            "Use uma semana entre 2000 e 2099, com duas semanas disponíveis."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    # O_EXCL recusa inclusive uma criação concorrente. Não há opção de reset.
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    password = secrets.token_urlsafe(18)
    app = create_demo_app(path)
    from flask import g
    from app.database import get_db, init_db
    from app.models.company import create_company
    from app.models.employee import save_employee
    from app.models.settings import save_settings
    from app.models.shift import save_shift
    from app.models.user import create_user, find_by_email
    from app.services.schedule_service import add_unavailability, save_assignment

    with app.app_context():
        init_db()
        db = get_db()
        company = create_company("TechNova Serviços — demonstração fictícia")
        db.commit()
        create_user("Administrador Fictício", DEMO_EMAIL, password, company_id=company)
        g.user = find_by_email(DEMO_EMAIL)
        save_settings("TechNova Serviços — demonstração fictícia", 11, True)
        shifts = [
            save_shift(
                dict(
                    name=name,
                    start_time=start,
                    end_time=end,
                    break_minutes=30,
                    color=color,
                )
            )
            for name, start, end, color in (
                ("Manhã · demo", "06:00", "14:00", "#2563EB"),
                ("Tarde · demo", "14:00", "22:00", "#64748B"),
                ("Noite · demo", "22:00", "06:00", "#1E40AF"),
            )
        ]
        employees = [
            save_employee(
                dict(
                    name=f"Pessoa Fictícia {index + 1:02}",
                    role=(
                        "Analista fictício",
                        "Técnico fictício",
                        "Assistente fictício",
                    )[index % 3],
                    department=("Operações demo", "Suporte demo", "Atendimento demo")[
                        index % 3
                    ],
                    email=f"demo.funcionario{index + 1:02}@example.com",
                    weekly_hours=24 if index == 0 else 40,
                )
            )
            for index in range(15)
        ]
        for offset in (0, 7):
            for index, employee in enumerate(employees):
                for workday in range(5):
                    day_index = (workday + index % 3) % 7
                    shift = shifts[index % 3]
                    # Descanso reduzido de 8h gera alerta real, sem sobreposição.
                    if index == 0 and workday == 0:
                        shift = shifts[2]
                    elif index == 0 and workday == 1:
                        shift = shifts[1]
                    save_assignment(
                        dict(
                            employee_id=employee,
                            shift_id=shift,
                            work_date=(
                                monday + timedelta(days=offset + day_index)
                            ).isoformat(),
                        )
                    )
        for index in (0, 3, 6):
            # Folga fora das atribuições existentes; bloqueios não são burlados.
            day = monday + timedelta(days=5)
            add_unavailability(
                dict(
                    employee_id=employees[index],
                    start_at=f"{day}T08:00",
                    end_at=f"{day}T18:00",
                    reason="Folga fictícia — demonstração",
                )
            )
        db.execute(
            "CREATE TABLE demo_metadata(id INTEGER PRIMARY KEY CHECK(id=1), kind TEXT NOT NULL, week TEXT NOT NULL)"
        )
        db.execute(
            "INSERT INTO demo_metadata VALUES(1,:kind,:week)",
            {"kind": "escalapro-fictional-v1", "week": monday.isoformat()},
        )
        db.commit()
    require_demo(path)
    return path, password, monday


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=os.getenv("DEMO_DATABASE_PATH", ""))
    parser.add_argument(
        "--week",
        type=date.fromisoformat,
        help="Data opcional na semana desejada (AAAA-MM-DD).",
    )
    args = parser.parse_args()
    try:
        path, password, monday = seed_demo(args.database, week=args.week)
    except ValueError, OSError:
        parser.exit(
            1,
            "Demonstração recusada. Use um caminho novo instance/demo/<nome>.demo.sqlite3 e uma semana válida.\n",
        )
    print(f"Base fictícia criada: {path.relative_to(ROOT).as_posix()}")
    print(f"Duas semanas a partir de {monday}; 15 pessoas e 150 atribuições fictícias.")
    credentials = path.with_suffix(".credentials.json")
    with credentials.open("x", encoding="utf-8") as stream:
        json.dump(
            {
                "purpose": "DEMONSTRAÇÃO LOCAL FICTÍCIA",
                "email": DEMO_EMAIL,
                "password": password,
            },
            stream,
            indent=2,
            ensure_ascii=False,
        )
    print(
        f"Credenciais fictícias no arquivo privado: {credentials.relative_to(ROOT).as_posix()}"
    )
    print("Nenhum e-mail enviado. Não use esta base em um serviço público.")


if __name__ == "__main__":
    main()
