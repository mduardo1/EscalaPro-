"""Regressões da auditoria atual; somente fixtures fictícias e isoladas."""

import pytest

from app.database import get_db
from app.services.schedule_service import save_assignment
from conftest import company_context, post
from test_audit_regressions import rendered_context


@pytest.mark.parametrize("day", ["20261112", "2026-W46-4", "2026W464"])
def test_assignment_rejects_noncanonical_date_before_writing(app, auth, seeded, day):
    response = post(
        auth,
        "/schedules/?month=2026-11",
        {"employee_id": "1", "shift_id": "1", "work_date": day},
    )
    assert response.status_code == 422
    with company_context(app):
        assert get_db().execute("SELECT count(*) FROM schedules").fetchone()[0] == 0


@pytest.mark.parametrize("day", ["20261112", "2026-W46-4", "2026W464"])
def test_week_query_rejects_noncanonical_dates(auth, day):
    assert auth.get("/schedules/", query_string={"week": day}).status_code == 400


@pytest.mark.parametrize("view", ["month=2026-11", "week=2026-11-02"])
def test_edit_selects_assignment_day_within_displayed_period(app, auth, seeded, view):
    with company_context(app):
        save_assignment(
            {"employee_id": "1", "shift_id": "1", "work_date": "2026-11-05"}
        )
    ctx = rendered_context(app, auth, f"/schedules/1/edit?{view}")
    assert ctx["selected_day"] == "2026-11-05"
    assert len(ctx["selected_events"]) == 1


def test_edit_continuation_selects_first_visible_day(app, auth, seeded):
    with company_context(app):
        save_assignment(
            {"employee_id": "1", "shift_id": "2", "work_date": "2026-10-31"}
        )
    ctx = rendered_context(app, auth, "/schedules/1/edit?month=2026-11")
    assert ctx["selected_day"] == "2026-11-01"
    assert len(ctx["selected_events"]) == 1


def test_explicit_day_selection_is_preserved_while_editing(app, auth, seeded):
    with company_context(app):
        save_assignment(
            {"employee_id": "1", "shift_id": "2", "work_date": "2026-11-05"}
        )
    ctx = rendered_context(app, auth, "/schedules/1/edit?month=2026-11&day=2026-11-06")
    assert ctx["selected_day"] == "2026-11-06"
    assert len(ctx["selected_events"]) == 1


def test_http_employee_shift_monthly_assignment_lifecycle(app, employee_data):
    """Exercita cookies, CSRF, redirects e downloads pela pilha HTTP real."""
    import re
    from http.cookiejar import CookieJar
    from io import BytesIO
    from threading import Thread
    from urllib.parse import urlencode
    from urllib.request import HTTPCookieProcessor, Request, build_opener

    from pypdf import PdfReader
    from werkzeug.serving import make_server

    server = make_server("127.0.0.1", 0, app)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    client = build_opener(HTTPCookieProcessor(CookieJar()))

    def get(path):
        with client.open(base + path, timeout=5) as response:
            return response.geturl(), response.read()

    def submit(path, fields, source):
        page = get(source)[1]
        csrf = re.search(rb'name="csrf_token" value="([^"]+)"', page).group(1).decode()
        request = Request(
            base + path, data=urlencode({**fields, "csrf_token": csrf}).encode()
        )
        with client.open(request, timeout=5) as response:
            return response.geturl(), response.read()

    try:
        assert submit(
            "/login",
            {"email": "admin@example.test", "password": "test-password-123"},
            "/login",
        )[0].endswith("/dashboard")
        assert submit("/employees/new", employee_data, "/employees/new")[0].endswith(
            "/employees/"
        )
        submit(
            "/shifts/",
            {
                "name": "Noite HTTP",
                "start_time": "22:00",
                "end_time": "06:00",
                "break_minutes": "60",
                "color": "#2563EB",
            },
            "/shifts/",
        )
        url = "/schedules/?month=2026-11&day=2026-11-30"
        data = {"employee_id": "1", "shift_id": "1", "work_date": "2026-11-30"}
        target, page = submit(url, data, url)
        assert "month=2026-11" in target and "Noite HTTP" in page.decode()
        assert (
            "Continuação" in get("/schedules/?month=2026-12&day=2026-12-01")[1].decode()
        )
        _, pdf = get("/schedules/export.pdf?month=2026-11")
        text = " ".join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
        assert "Pessoa Fictícia" in text and "01/12/2026 06:00" in text
        submit(
            "/schedules/1/edit?month=2026-11", {**data, "work_date": "2026-11-29"}, url
        )
        submit("/employees/1/toggle", {}, "/employees/")
        with company_context(app):
            db = get_db()
            row = db.execute("SELECT work_date FROM schedules WHERE id=1").fetchone()
            assert row[0] == "2026-11-29"
            assert (
                db.execute("SELECT active FROM employees WHERE id=1").fetchone()[0] == 0
            )
        submit("/schedules/1/delete?month=2026-11", {}, url)
        _, empty_pdf = get("/schedules/export.pdf?month=2026-11")
        empty_text = " ".join(
            page.extract_text() for page in PdfReader(BytesIO(empty_pdf)).pages
        )
        assert "Nenhuma atribuição" in empty_text and "Noite HTTP" not in empty_text
        with company_context(app):
            assert get_db().execute("SELECT count(*) FROM schedules").fetchone()[0] == 0
        assert submit("/logout", {}, "/employees/")[0].endswith("/login")
        assert get("/schedules/")[0].endswith("/login")
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
