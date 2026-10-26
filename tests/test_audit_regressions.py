from conftest import company_context

"""Reproduções de defeitos identificados na auditoria, sempre em SQLite isolado."""

import time
import random
import string
from datetime import datetime
from html.parser import HTMLParser

import pytest
from flask import template_rendered

from app import create_app
from app.database import get_db
from app.services.schedule_service import save_assignment
from conftest import post


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.items.append(dict(attrs))


def rendered_context(app, client, path):
    contexts = []

    def record(sender, template, context, **extra):
        contexts.append(context)

    with template_rendered.connected_to(record, app):
        response = client.get(path)
    assert response.status_code == 200
    return contexts[-1]


@pytest.mark.parametrize(
    "path", ["/employees/{}/edit", "/shifts/{}/edit", "/schedules/{}/edit"]
)
def test_out_of_range_path_id_is_404(auth, path):
    assert auth.get(path.format("9" * 30)).status_code == 404


def test_huge_form_integer_is_validation_error(app, auth, seeded):
    response = post(
        auth,
        "/schedules/",
        {"employee_id": "9" * 400, "shift_id": "1", "work_date": "2026-10-12"},
    )
    assert response.status_code == 422
    with company_context(app):
        assert get_db().execute("SELECT count(*) FROM schedules").fetchone()[0] == 0


def test_logged_out_cookie_cannot_be_replayed(app, auth):
    original = auth.get_cookie("session").value
    assert post(auth, "/logout").status_code == 302
    replay = app.test_client()
    replay.set_cookie("session", original)
    assert replay.get("/dashboard").status_code == 302


def test_session_has_absolute_eight_hour_expiration(auth, monkeypatch):
    issued = time.time()
    monkeypatch.setattr(time, "time", lambda: issued + 7 * 3600)
    assert auth.get("/dashboard").status_code == 200
    monkeypatch.setattr(time, "time", lambda: issued + 9 * 3600)
    assert auth.get("/dashboard").status_code == 302


@pytest.mark.parametrize("debug_flag", ["2", "enabled", " true "])
def test_all_flask_truthy_debug_flags_rejected_in_production(monkeypatch, debug_flag):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("FLASK_DEBUG", debug_flag)
    with pytest.raises(RuntimeError, match="FLASK_DEBUG"):
        create_app({"TESTING": True, "SECRET_KEY": "audit-" + "x" * 40})


def test_explicit_debug_rejected_in_production():
    with pytest.raises(RuntimeError, match="FLASK_DEBUG"):
        create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "audit-" + "x" * 40,
                "PRODUCTION": True,
                "DEBUG": True,
            }
        )


def test_dashboard_total_uses_unrounded_hours(app, auth, seeded, monkeypatch):
    monkeypatch.setattr(
        "app.routes.dashboard.local_now", lambda: datetime(2026, 10, 12, 12)
    )
    with company_context(app):
        db = get_db()
        db.execute("UPDATE shifts SET end_time='08:20',break_minutes=0 WHERE id=1")
        db.commit()
        for day in ["2026-10-12", "2026-10-13", "2026-10-14"]:
            save_assignment({"employee_id": "1", "shift_id": "1", "work_date": day})
    context = rendered_context(app, auth, "/dashboard")
    assert context["total_hours"] == 1.0


def test_sunday_night_warns_about_next_week_limit(app, seeded):
    with company_context(app):
        db = get_db()
        db.execute("UPDATE employees SET weekly_hours=8 WHERE id=1")
        db.commit()
        save_assignment(
            {"employee_id": "1", "shift_id": "1", "work_date": "2026-10-12"}
        )
        alerts = save_assignment(
            {"employee_id": "1", "shift_id": "2", "work_date": "2026-10-11"}
        )
    assert any("jornada configurada" in alert for alert in alerts)


def test_sunday_assignment_warns_about_rest_before_monday(app, seeded):
    with company_context(app):
        db = get_db()
        db.execute("UPDATE company_settings SET min_rest_hours=20")
        db.commit()
        save_assignment(
            {"employee_id": "1", "shift_id": "1", "work_date": "2026-10-12"}
        )
        alerts = save_assignment(
            {"employee_id": "1", "shift_id": "1", "work_date": "2026-10-11"}
        )
    assert any("descanso de 15.0h" in alert for alert in alerts)


def test_many_alerts_do_not_overflow_session_cookie(auth, monkeypatch):
    # A quantidade de alertas não pode tornar o cookie maior que o limite dos navegadores.
    generator = random.Random(42)
    alerts = [
        f"{''.join(generator.choices(string.ascii_letters, k=80))}: descanso de {i % 12}.0h; mínimo de 12h."
        for i in range(100)
    ]
    monkeypatch.setattr("app.routes.schedules.save_assignment", lambda *args: alerts)
    response = post(auth, "/schedules/", {"work_date": "2026-10-12"})
    assert response.status_code == 302
    with auth.session_transaction() as session:
        assert len(session.get("_flashes", [])) <= 5
    assert all(len(header) < 4093 for header in response.headers.getlist("Set-Cookie"))


def test_add_calendar_link_during_edit_opens_new_assignment(app, auth, seeded):
    with company_context(app):
        save_assignment(
            {"employee_id": "1", "shift_id": "1", "work_date": "2026-10-12"}
        )
    parser = Links()
    parser.feed(auth.get("/schedules/1/edit?week=2026-10-12").text)
    link = next(link for link in parser.items if link.get("class") == "add-day")
    assert link["href"].startswith("/schedules/?")
    assert "day=2026-10-12" in link["href"]
    context = rendered_context(app, auth, link["href"].split("#")[0])
    assert context["assignment"] is None


def test_removing_missing_unavailability_is_404(auth):
    assert post(auth, "/schedules/unavailability/999/delete").status_code == 404


@pytest.mark.parametrize("day", ["2000-01-01", "2100-12-31"])
def test_calendar_date_limits_do_not_generate_broken_week_links(app, auth, day):
    page = auth.get(f"/schedules/?week={day}")
    assert page.status_code == 200
    parser = Links()
    parser.feed(page.text)
    for link in parser.items:
        if link.get("aria-label") in {
            "Semana anterior",
            "Próxima semana",
        } or "export.pdf" in link.get("href", ""):
            assert auth.get(link["href"]).status_code == 200


def test_invalid_unavailability_keeps_entered_values(auth, seeded):
    data = {
        "employee_id": "1",
        "start_at": "2026-10-14T10:00",
        "end_at": "2026-10-14T09:00",
        "reason": "Ausência agendada",
    }
    response = post(auth, "/schedules/unavailability?week=2026-10-12", data)
    assert response.status_code == 422
    assert 'value="2026-10-14T10:00"' in response.text
    assert 'value="Ausência agendada"' in response.text


def test_same_shift_reassignment_after_time_change_is_validation_error(
    app, auth, seeded
):
    with company_context(app):
        save_assignment(
            {"employee_id": "1", "shift_id": "1", "work_date": "2026-10-12"}
        )
        db = get_db()
        # O snapshot antigo não se sobrepõe à nova definição do mesmo turno.
        db.execute(
            "UPDATE shifts SET start_time='18:00',end_time='22:00',break_minutes=0 WHERE id=1"
        )
        db.commit()
    response = post(
        auth,
        "/schedules/",
        {"employee_id": "1", "shift_id": "1", "work_date": "2026-10-12"},
    )
    assert response.status_code == 422
    with company_context(app):
        rows = get_db().execute("SELECT start_at FROM schedules").fetchall()
        assert len(rows) == 1 and rows[0]["start_at"] == "2026-10-12T08:00:00"
