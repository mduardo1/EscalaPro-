from conftest import company_context
from datetime import datetime
from io import BytesIO

import pytest
from pypdf import PdfReader

from app.database import get_db
from app.services.schedule_validator import net_hours
from conftest import post


def assign(auth, day="2026-10-12", shift="1", url="/schedules/?week=2026-10-12"):
    return post(auth, url, {"employee_id": "1", "shift_id": shift, "work_date": day})


def test_assignment_edit_remove_and_week_view(app, auth, seeded):
    assert assign(auth).status_code == 302
    page = auth.get("/schedules/?week=2026-10-12")
    assert page.status_code == 200
    assert b"Pessoa Teste" in page.data
    assert auth.get("/schedules/1/edit?week=2026-10-12").status_code == 200
    assert (
        assign(auth, "2026-10-13", "2", "/schedules/1/edit?week=2026-10-12").status_code
        == 302
    )
    with company_context(app):
        row = get_db().execute("SELECT * FROM schedules").fetchone()
        assert row["end_at"] == "2026-10-14T06:00:00"
    assert post(auth, "/schedules/1/delete").status_code == 302
    with company_context(app):
        assert get_db().execute("SELECT COUNT(*) FROM schedules").fetchone()[0] == 0


def test_overnight_overlap_and_exclude_self(app, auth, seeded):
    assert assign(auth, "2026-10-12", "2").status_code == 302
    assert assign(auth, "2026-10-13", "3").status_code == 422
    assert assign(auth, "2026-10-12", "2").status_code == 422
    assert assign(auth, "2026-10-12", "2", "/schedules/1/edit").status_code == 302
    with company_context(app):
        assert get_db().execute("SELECT COUNT(*) FROM schedules").fetchone()[0] == 1


def test_adjacent_turns_allowed(app, auth, seeded):
    with company_context(app):
        get_db().execute("UPDATE shifts SET start_time='06:00' WHERE id=3")
        get_db().commit()
    assert assign(auth, shift="2").status_code == 302
    assert assign(auth, "2026-10-13", "3").status_code == 302


def test_unavailable_blocks_assignment_and_reverse(auth, seeded):
    data = {
        "employee_id": "1",
        "start_at": "2026-10-13T05:30",
        "end_at": "2026-10-13T10:00",
        "reason": "Folga",
    }
    assert post(auth, "/schedules/unavailability", data).status_code == 302
    assert assign(auth, shift="2").status_code == 422
    assert post(auth, "/schedules/unavailability/1/delete").status_code == 302
    assert assign(auth, shift="2").status_code == 302
    assert post(auth, "/schedules/unavailability", data).status_code == 422
    assert (
        post(
            auth, "/schedules/unavailability", {**data, "end_at": "2026-10-12T00:00"}
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"employee_id": "999"},
        {"shift_id": "999"},
        {"work_date": "bad"},
        {"work_date": "1800-01-01"},
        {"employee_id": "1.5"},
        {"employee_id": "99999999999999999999"},
    ],
)
def test_invalid_assignment(auth, seeded, changes):
    data = {"employee_id": "1", "shift_id": "1", "work_date": "2026-10-12"}
    assert post(auth, "/schedules/", {**data, **changes}).status_code == 422


def test_deactivated_employee_retains_history(app, auth, seeded):
    assert assign(auth).status_code == 302
    assert post(auth, "/employees/1/toggle").status_code == 302
    assert assign(auth, "2026-10-13").status_code == 422
    assert "Pessoa Teste" in auth.get("/schedules/?week=2026-10-12").text


def test_shift_edit_preserves_snapshot(auth, app, seeded):
    assert assign(auth).status_code == 302
    assert (
        post(
            auth,
            "/shifts/1/edit",
            {
                "name": "Novo",
                "start_time": "10:00",
                "end_time": "18:00",
                "break_minutes": "0",
                "color": "#2563EB",
            },
        ).status_code
        == 302
    )
    with company_context(app):
        row = get_db().execute("SELECT * FROM schedules").fetchone()
        assert row["start_at"] == "2026-10-12T08:00:00"
        assert row["shift_name"] == "Diurno"


def test_configurable_weekly_and_rest_alerts(auth, app, seeded):
    assert (
        post(
            auth,
            "/settings",
            {
                "company_name": "Empresa Teste",
                "min_rest_hours": "12",
                "weekly_alerts": "on",
            },
        ).status_code
        == 302
    )
    assert assign(auth, shift="2").status_code == 302
    assert assign(auth, "2026-10-13").status_code == 302
    with company_context(app):
        get_db().execute("UPDATE employees SET weekly_hours=8 WHERE id=1")
        get_db().commit()
    page = auth.get("/schedules/?week=2026-10-12").text
    assert "descanso de 2.0h" in page
    assert "jornada configurada de 8h" in page
    assert (
        post(
            auth, "/settings", {"company_name": "Empresa Teste", "min_rest_hours": "0"}
        ).status_code
        == 302
    )
    page = auth.get("/schedules/?week=2026-10-12").text
    assert "descanso de" not in page
    assert "jornada configurada de" not in page


def test_week_boundary_night_hours(auth, app, seeded):
    assert assign(auth, "2026-10-11", "2").status_code == 302
    assert "Continuação" in auth.get("/schedules/?week=2026-10-12").text
    with company_context(app):
        row = get_db().execute("SELECT * FROM schedules").fetchone()
        assert net_hours(
            row, datetime(2026, 10, 12), datetime(2026, 10, 19)
        ) == pytest.approx(5.25)


def test_pdf_export_and_empty_week(auth, seeded):
    assert assign(auth, shift="2").status_code == 302
    response = auth.get("/schedules/export.pdf?week=2026-10-12")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert "attachment" in response.headers["Content-Disposition"]
    assert response.data.startswith(b"%PDF-")
    text = " ".join(
        page.extract_text() for page in PdfReader(BytesIO(response.data)).pages
    )
    for expected in [
        "Minha empresa",
        "Pessoa Teste",
        "Noturno",
        "12/10/2026 22:00",
        "13/10/2026 06:00",
        "Gerado em",
    ]:
        assert expected in text
    response = auth.get("/schedules/export.pdf?week=2027-01-04")
    assert (
        "Nenhuma atribuição"
        in PdfReader(BytesIO(response.data)).pages[0].extract_text()
    )


def test_bad_week_and_settings(auth):
    assert auth.get("/schedules/?week=invalid").status_code == 400
    assert auth.get("/schedules/export.pdf?week=invalid").status_code == 400
    assert (
        post(
            auth, "/settings", {"company_name": "AB", "min_rest_hours": "nan"}
        ).status_code
        == 422
    )
    assert auth.get("/settings").status_code == 200
    assert auth.get("/employees/999/edit").status_code == 404
    assert auth.get("/shifts/999/edit").status_code == 404
    assert auth.get("/schedules/999/edit").status_code == 404
