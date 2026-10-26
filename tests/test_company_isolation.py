"""Defesa contra IDOR em cada módulo, com duas empresas autenticadas."""

import sqlite3
from datetime import datetime
from io import BytesIO

import pytest
from pypdf import PdfReader

from app.database import get_db
from app.models.company import create_company
from app.models.employee import get_employee, save_employee
from app.models.shift import get_shift, save_shift
from app.models.schedule import get_schedule
from app.models.settings import get_settings, save_settings
from app.models.user import create_user
from app.services.schedule_service import (
    add_unavailability,
    save_assignment,
    week_alerts,
    week_period,
)
from conftest import company_context, post
from test_account_flows import PASSWORD, login


@pytest.fixture
def two_companies(app):
    with app.app_context():
        company_b = create_company("Companhia Privada Beta")
        create_user("Admin Beta", "beta@example.test", PASSWORD, company_id=company_b)
    records = {}
    for user_id, name in [(1, "Alfa"), (2, "Beta")]:
        with company_context(app, user_id):
            employee = save_employee(
                {
                    "name": f"Profissional Privado {name}",
                    "role": "Analista",
                    "department": f"Setor {name}",
                    "email": "",
                    "weekly_hours": 1 if user_id == 1 else 40,
                }
            )
            shift = save_shift(
                {
                    "name": f"Turno Privado {name}",
                    "start_time": "08:00",
                    "end_time": "17:00",
                    "break_minutes": 60,
                    "color": "#2563EB",
                }
            )
            save_settings(f"Companhia Privada {name}", 0, True)
            save_assignment(
                {
                    "employee_id": str(employee),
                    "shift_id": str(shift),
                    "work_date": "2026-10-12",
                }
            )
            add_unavailability(
                {
                    "employee_id": str(employee),
                    "start_at": "2026-10-14T00:00",
                    "end_at": "2026-10-15T00:00",
                    "reason": f"Ausência Privada {name}",
                }
            )
            db = get_db()
            schedule = db.execute(
                "SELECT id FROM schedules WHERE employee_id=?", (employee,)
            ).fetchone()[0]
            unavailable = db.execute(
                "SELECT id FROM unavailabilities WHERE employee_id=?", (employee,)
            ).fetchone()[0]
            records[name] = {
                "employee": employee,
                "shift": shift,
                "schedule": schedule,
                "unavailable": unavailable,
            }
    first, second = app.test_client(), app.test_client()
    assert login(first, "admin@example.test", "test-password-123").status_code == 302
    assert login(second, "beta@example.test", PASSWORD).status_code == 302
    return first, second, records


def test_lists_dashboard_alerts_settings_and_pdf_are_scoped(
    app, two_companies, monkeypatch
):
    first, second, records = two_companies
    monkeypatch.setattr(
        "app.routes.dashboard.local_now", lambda: datetime(2026, 10, 12, 12)
    )
    for client, own, other in [(first, "Alfa", "Beta"), (second, "Beta", "Alfa")]:
        for path in [
            "/employees/",
            "/employees/?q=Privado",
            "/shifts/",
            "/schedules/?week=2026-10-12",
            "/settings",
            "/dashboard",
        ]:
            response = client.get(path)
            assert response.status_code == 200
            assert f"Privado {other}" not in response.text
            assert f"Privada {other}" not in response.text
        pdf = client.get("/schedules/export.pdf?week=2026-10-12")
        text = " ".join(
            page.extract_text() for page in PdfReader(BytesIO(pdf.data)).pages
        )
        assert (
            f"Companhia Privada {own}" in text and f"Profissional Privado {own}" in text
        )
        assert f"Privado {other}" not in text and f"Privada {other}" not in text
    with company_context(app, 1):
        assert len(week_alerts(*week_period("2026-10-12"))) == 1
    with company_context(app, 2):
        assert week_alerts(*week_period("2026-10-12")) == []


def test_all_foreign_read_edit_and_delete_ids_return_404(app, two_companies):
    first, second, records = two_companies
    for client, foreign_name, owner in [(first, "Beta", 2), (second, "Alfa", 1)]:
        foreign = records[foreign_name]
        for path in [
            f"/employees/{foreign['employee']}/edit",
            f"/shifts/{foreign['shift']}/edit",
            f"/schedules/{foreign['schedule']}/edit",
        ]:
            assert client.get(path).status_code == 404
            assert post(client, path, {"name": "Tentativa"}).status_code == 404
        for path in [
            f"/employees/{foreign['employee']}/toggle",
            f"/schedules/{foreign['schedule']}/delete",
            f"/schedules/unavailability/{foreign['unavailable']}/delete",
        ]:
            assert post(client, path).status_code == 404
        with company_context(app, owner):
            assert get_employee(foreign["employee"])["active"] == 1
            assert (
                get_shift(foreign["shift"])["name"] == f"Turno Privado {foreign_name}"
            )
            assert get_schedule(foreign["schedule"]) is not None
            assert (
                get_db()
                .execute(
                    "SELECT reason FROM unavailabilities WHERE id=?",
                    (foreign["unavailable"],),
                )
                .fetchone()[0]
                == f"Ausência Privada {foreign_name}"
            )


def test_foreign_references_rejected_and_browser_company_id_ignored(app, two_companies):
    first, _second, records = two_companies
    a, b = records["Alfa"], records["Beta"]
    for employee, shift in [(b["employee"], a["shift"]), (a["employee"], b["shift"])]:
        response = post(
            first,
            "/schedules/",
            {
                "employee_id": str(employee),
                "shift_id": str(shift),
                "work_date": "2026-10-13",
                "company_id": "2",
            },
        )
        assert response.status_code == 422
    assert (
        post(
            first,
            "/schedules/unavailability",
            {
                "employee_id": str(b["employee"]),
                "start_at": "2026-10-18T00:00",
                "end_at": "2026-10-19T00:00",
                "reason": "Tentativa",
                "company_id": "2",
            },
        ).status_code
        == 422
    )
    assert (
        post(
            first,
            "/employees/new",
            {
                "name": "Novo Alfa",
                "role": "Analista",
                "department": "Equipe",
                "email": "",
                "weekly_hours": "40",
                "company_id": "2",
            },
        ).status_code
        == 302
    )
    assert (
        post(
            first,
            "/settings",
            {
                "company_name": "Alfa alterada",
                "min_rest_hours": "12",
                "company_id": "2",
            },
        ).status_code
        == 302
    )
    with app.app_context():
        assert (
            get_db()
            .execute("SELECT company_id FROM employees WHERE name='Novo Alfa'")
            .fetchone()[0]
            == 1
        )
    with company_context(app, 2):
        assert get_settings()["company_name"] == "Companhia Privada Beta"
        assert get_settings()["min_rest_hours"] == 0


def test_models_fail_closed_without_identity_and_database_rejects_cross_links(
    app, two_companies
):
    _first, _second, records = two_companies
    a, b = records["Alfa"], records["Beta"]
    with app.app_context():
        with pytest.raises(RuntimeError, match="autenticado"):
            get_employee(a["employee"])
    with company_context(app, 1):
        assert get_employee(b["employee"]) is None
        assert get_shift(b["shift"]) is None
        assert get_schedule(b["schedule"]) is None
        db = get_db()
        with pytest.raises(sqlite3.IntegrityError, match="cross-company"):
            db.execute(
                "INSERT INTO schedules(employee_id,shift_id,work_date,start_at,end_at,shift_name,break_minutes,color,company_id) "
                "VALUES(?,?,'2026-10-13','2026-10-13T08:00:00','2026-10-13T17:00:00','Inválido',60,'#2563EB',1)",
                (b["employee"], a["shift"]),
            )
        db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("UPDATE employees SET company_id=2 WHERE id=?", (a["employee"],))
        db.rollback()
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
