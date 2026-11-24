"""Calendário mensal com os mesmos limites e regras do planejamento semanal."""

from datetime import date, datetime
from html.parser import HTMLParser
from io import BytesIO

import pytest
from pypdf import PdfReader

from app.database import get_db
from app.models.settings import save_settings
from app.services.schedule_service import month_period, save_assignment
from conftest import company_context, post
from test_audit_regressions import rendered_context
from test_company_isolation import two_companies  # noqa: F401


class CalendarHTML(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.days, self.links = [], []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "data-calendar-day" in attrs:
            self.days.append(attrs["data-calendar-day"])
        if tag == "a":
            self.links.append(attrs)


@pytest.mark.parametrize(
    "month,count",
    [
        ("2026-02", 28),
        ("2028-02", 29),
        ("2026-11", 30),
        ("2026-12", 31),
        ("2000-02", 29),
        ("2100-02", 28),
    ],
)
def test_complete_months_and_monday_alignment(app, auth, month, count):
    page = auth.get(f"/schedules/?month={month}")
    assert page.status_code == 200
    assert CalendarHTML(page.text).days == [
        f"{month}-{day:02}" for day in range(1, count + 1)
    ]
    ctx = rendered_context(app, auth, f"/schedules/?month={month}")
    assert ctx["view"] == "month"
    assert len(ctx["days"]) == count
    assert all(len(week) == 7 for week in ctx["calendar_weeks"])
    assert (
        ctx["calendar_weeks"][0].index(1) == date.fromisoformat(month + "-01").weekday()
    )


def test_default_month_today_and_year_navigation(app, auth, monkeypatch):
    monkeypatch.setattr(
        "app.routes.schedules.local_now", lambda: datetime(2026, 11, 9, 12)
    )
    ctx = rendered_context(app, auth, "/schedules/")
    assert ctx["view"] == "month" and ctx["selected_day"] == "2026-11-09"
    assert len(ctx["days"]) == 30
    assert 'aria-current="date"' in auth.get("/schedules/").text
    for month, previous, following in [
        ("2026-12", "2026-11", "2027-01"),
        ("2027-01", "2026-12", "2027-02"),
    ]:
        ctx = rendered_context(app, auth, f"/schedules/?month={month}")
        assert (ctx["previous"], ctx["following"]) == (previous, following)
        for other in [previous, following]:
            assert auth.get(f"/schedules/?month={other}").status_code == 200


@pytest.mark.parametrize("month", ["2000-01", "2100-12"])
def test_month_navigation_limits(auth, month):
    page = auth.get(f"/schedules/?month={month}")
    assert page.status_code == 200
    for link in CalendarHTML(page.text).links:
        if link.get("aria-label") in {"Mês anterior", "Próximo mês"}:
            assert auth.get(link["href"]).status_code == 200


@pytest.mark.parametrize(
    "value",
    [
        "invalid",
        "2026-13",
        "2026-00",
        "2026-2",
        "2026-02-01",
        "1999-12",
        "2101-01",
        "",
        "2026-W01",
    ],
)
def test_invalid_month_rejected(auth, value):
    for path in ["/schedules/", "/schedules/export.pdf"]:
        assert auth.get(path, query_string={"month": value}).status_code == 400
    with pytest.raises(ValueError):
        month_period(value)


@pytest.mark.parametrize("day", ["2026-11-01", "2026-11-15", "2026-11-30"])
def test_day_prefill_assignment_edit_delete_and_refresh(app, auth, seeded, day):
    query = f"?month=2026-11&day={day}"
    ctx = rendered_context(app, auth, "/schedules/" + query)
    assert ctx["selected_day"] == day and ctx["assignment"] is None
    data = {"employee_id": "1", "shift_id": "1", "work_date": day}
    response = post(auth, "/schedules/" + query, data)
    assert response.status_code == 302 and "month=2026-11" in response.location
    ctx = rendered_context(app, auth, response.location)
    assert len(ctx["events_by_day"][day]) == 1
    edit = post(auth, "/schedules/1/edit" + query, {**data, "shift_id": "2"})
    assert edit.status_code == 302
    ctx = rendered_context(app, auth, edit.location)
    assert ctx["selected_events"][0]["shift_name"] == "Noturno"
    response = post(auth, "/schedules/1/delete?month=2026-11")
    assert response.status_code == 302 and "month=2026-11" in response.location
    ctx = rendered_context(app, auth, response.location)
    assert ctx["selected_events"] == []


@pytest.mark.parametrize("day", ["invalid", "2026-10-31", "2026-12-01"])
def test_day_must_belong_to_selected_month(auth, day):
    assert (
        auth.get(
            "/schedules/", query_string={"month": "2026-11", "day": day}
        ).status_code
        == 400
    )


@pytest.mark.parametrize("day", ["2028-02-29", "2026-12-31", "2027-01-01"])
def test_assignment_on_leap_day_and_year_boundary(app, auth, seeded, day):
    response = post(
        auth,
        f"/schedules/?month={day[:7]}",
        {"employee_id": "1", "shift_id": "1", "work_date": day},
    )
    assert response.status_code == 302
    assert f"month={day[:7]}" in response.location
    ctx = rendered_context(app, auth, response.location)
    assert ctx["events_by_day"][day][0]["work_date"] == day


def test_month_conflicts_unavailability_and_failed_edit_keep_data(app, auth, seeded):
    url = "/schedules/?month=2026-11"
    data = {"employee_id": "1", "shift_id": "2", "work_date": "2026-11-15"}
    assert post(auth, url, data).status_code == 302
    assert (
        post(
            auth, url, {**data, "shift_id": "3", "work_date": "2026-11-16"}
        ).status_code
        == 422
    )
    unavailable = {
        "employee_id": "1",
        "start_at": "2026-11-30T00:00",
        "end_at": "2026-12-01T00:00",
        "reason": "Férias",
    }
    assert (
        post(auth, "/schedules/unavailability?month=2026-11", unavailable).status_code
        == 302
    )
    failed = post(
        auth, "/schedules/1/edit?month=2026-11", {**data, "work_date": "2026-11-30"}
    )
    assert failed.status_code == 422
    assert 'value="2026-11-30"' in failed.text and "indisponível" in failed.text
    with company_context(app):
        assert (
            get_db().execute("SELECT work_date FROM schedules WHERE id=1").fetchone()[0]
            == "2026-11-15"
        )
    assert post(auth, "/employees/1/toggle").status_code == 302
    assert post(auth, url, {**data, "work_date": "2026-11-20"}).status_code == 422
    assert "Pessoa Teste" in auth.get(url).text


def test_overnight_continuations_month_edges_and_pdf(app, auth, seeded):
    with company_context(app):
        for day in ["2026-10-31", "2026-11-30", "2026-12-02"]:
            save_assignment({"employee_id": "1", "shift_id": "2", "work_date": day})
    ctx = rendered_context(app, auth, "/schedules/?month=2026-11")
    assert ctx["events_by_day"]["2026-11-01"][0]["work_date"] == "2026-10-31"
    assert len(ctx["schedules"]) == 2
    assert "Continuação" in auth.get("/schedules/?month=2026-11").text
    pdf = auth.get("/schedules/export.pdf?month=2026-11")
    assert pdf.status_code == 200 and pdf.mimetype == "application/pdf"
    assert "escalapro-2026-11.pdf" in pdf.headers["Content-Disposition"]
    reader = PdfReader(BytesIO(pdf.data))
    text = " ".join(page.extract_text() for page in reader.pages)
    for expected in [
        "Escala mensal",
        "01/11/2026 a 30/11/2026",
        "Minha empresa",
        "Pessoa Teste",
        "Noturno",
        "31/10/2026 22:00",
        "01/12/2026 06:00",
    ]:
        assert expected in text
    assert "02/12/2026" not in text
    empty = auth.get("/schedules/export.pdf?month=2027-02")
    assert (
        "Nenhuma atribuição" in PdfReader(BytesIO(empty.data)).pages[0].extract_text()
    )


def test_crowded_day_summary_and_complete_details(app, auth, seeded):
    with company_context(app):
        db = get_db()
        for i in range(4):
            db.execute(
                "INSERT INTO employees(name,role,department,weekly_hours,company_id) VALUES(?, 'Analista', 'Equipe', 40, 1)",
                (f"Profissional {i}",),
            )
        db.commit()
        for i in range(1, 6):
            save_assignment(
                {"employee_id": str(i), "shift_id": "1", "work_date": "2026-11-20"}
            )
    page = auth.get("/schedules/?month=2026-11&day=2026-11-20")
    assert page.text.count('class="schedule-event compact-event"') == 3
    more = next(
        link
        for link in CalendarHTML(page.text).links
        if link.get("class") == "more-events"
    )
    assert "day=2026-11-20" in more["href"] and more["href"].endswith("#day-detail")
    ctx = rendered_context(app, auth, more["href"].split("#")[0])
    assert len(ctx["selected_events"]) == 5


def test_monthly_alerts_use_complete_weeks_and_keep_rest_rules(app, auth, seeded):
    with company_context(app):
        db = get_db()
        db.execute("UPDATE employees SET weekly_hours=8 WHERE id=1")
        db.commit()
        save_settings("Minha empresa", 12, True)
        for day, shift in [
            ("2026-10-30", "1"),
            ("2026-11-01", "1"),
            ("2026-11-15", "2"),
            ("2026-11-16", "1"),
        ]:
            save_assignment({"employee_id": "1", "shift_id": shift, "work_date": day})
    ctx = rendered_context(app, auth, "/schedules/?month=2026-11")
    assert any(
        "Semana de 26/10/2026" in alert and "16.0h" in alert for alert in ctx["alerts"]
    )
    assert any("descanso de 2.0h" in alert for alert in ctx["alerts"])


def test_monthly_company_isolation_and_authorization(two_companies):
    first, second, records = two_companies
    for client, own, other in [(first, "Alfa", "Beta"), (second, "Beta", "Alfa")]:
        page = client.get("/schedules/?month=2026-10&day=2026-10-12")
        assert f"Profissional Privado {own}" in page.text
        assert (
            f"Privado {other}" not in page.text and f"Privada {other}" not in page.text
        )
        pdf = client.get("/schedules/export.pdf?month=2026-10")
        text = " ".join(
            page.extract_text() for page in PdfReader(BytesIO(pdf.data)).pages
        )
        assert f"Companhia Privada {own}" in text and f"Privado {other}" not in text
        foreign = records[other]
        assert (
            client.get(
                f"/schedules/{foreign['schedule']}/edit?month=2026-10"
            ).status_code
            == 404
        )
        assert (
            post(
                client, f"/schedules/{foreign['schedule']}/delete?month=2026-10"
            ).status_code
            == 404
        )
        assert (
            post(
                client,
                "/schedules/?month=2026-10",
                {
                    "employee_id": str(foreign["employee"]),
                    "shift_id": str(foreign["shift"]),
                    "work_date": "2026-10-20",
                },
            ).status_code
            == 422
        )


def test_monthly_csrf_and_login_required(app, auth, seeded):
    client = app.test_client()
    assert client.get("/schedules/?month=2026-11").status_code == 302
    assert client.get("/schedules/export.pdf?month=2026-11").status_code == 302
    assert (
        auth.post(
            "/schedules/?month=2026-11",
            data={"employee_id": "1", "shift_id": "1", "work_date": "2026-11-10"},
        ).status_code
        == 400
    )
