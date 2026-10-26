from conftest import company_context
import pytest

from app.database import get_db
from conftest import post


def test_create_edit_search_deactivate(app, auth, employee_data):
    assert post(auth, "/employees/new", employee_data).status_code == 302
    assert "Pessoa Fictícia" in auth.get("/employees/?q=Fictícia").text
    assert "Pessoa Fictícia" not in auth.get("/employees/?q=Inexistente").text
    assert (
        post(
            auth, "/employees/1/edit", {**employee_data, "name": "Nome Atualizado"}
        ).status_code
        == 302
    )
    assert "Nome Atualizado" in auth.get("/employees/").text
    assert post(auth, "/employees/1/toggle").status_code == 302
    with company_context(app):
        assert get_db().execute("SELECT active FROM employees").fetchone()[0] == 0
    assert post(auth, "/employees/1/toggle").status_code == 302


@pytest.mark.parametrize(
    "key,value",
    [
        ("name", ""),
        ("role", "a"),
        ("department", ""),
        ("email", "bad"),
        ("weekly_hours", "0"),
        ("weekly_hours", "169"),
        ("weekly_hours", "nan"),
        ("weekly_hours", "inf"),
        ("name", "x" * 101),
    ],
)
def test_invalid_employee_fields(app, auth, employee_data, key, value):
    assert (
        post(auth, "/employees/new", {**employee_data, key: value}).status_code == 422
    )
    with company_context(app):
        assert get_db().execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 0


def test_optional_email_escape_and_sql_search(auth, employee_data):
    data = {**employee_data, "name": "<script>alert(1)</script>", "email": ""}
    assert post(auth, "/employees/new", data).status_code == 302
    page = auth.get("/employees/").text
    assert "&lt;script&gt;" in page
    assert "<script>alert(1)</script>" not in page
    assert auth.get("/employees/?q=' OR 1=1 --").status_code == 200
    assert "&lt;script&gt;" not in auth.get("/employees/?q=%25").text


def test_create_edit_shift(app, auth):
    data = {
        "name": "Noturno",
        "start_time": "22:00",
        "end_time": "06:00",
        "break_minutes": "60",
        "color": "#2563EB",
    }
    assert post(auth, "/shifts/", data).status_code == 302
    assert auth.get("/shifts/1/edit").status_code == 200
    assert post(auth, "/shifts/1/edit", {**data, "name": "Plantão"}).status_code == 302
    with company_context(app):
        assert get_db().execute("SELECT name FROM shifts").fetchone()[0] == "Plantão"


@pytest.mark.parametrize(
    "changes",
    [
        {"start_time": "25:00"},
        {"end_time": "22:00"},
        {"break_minutes": "480"},
        {"break_minutes": "-1"},
        {"color": "red"},
        {"name": ""},
        {"break_minutes": "1.5"},
    ],
)
def test_invalid_shift(auth, changes):
    data = {
        "name": "Noturno",
        "start_time": "22:00",
        "end_time": "06:00",
        "break_minutes": "60",
        "color": "#2563EB",
    }
    assert post(auth, "/shifts/", {**data, **changes}).status_code == 422
