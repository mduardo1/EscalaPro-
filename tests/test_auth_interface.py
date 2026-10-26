"""Contratos HTTP das telas públicas; nenhuma conexão SMTP real."""

from html.parser import HTMLParser

import pytest
from flask import url_for

from conftest import post


class Page(HTMLParser):
    def __init__(self, response):
        super().__init__()
        self.elements = []
        self.links = []
        self.anchor = None
        self.feed(response.get_data(as_text=True))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs))
        if tag == "a":
            self.anchor = {**attrs, "text": ""}

    def handle_data(self, data):
        if self.anchor is not None:
            self.anchor["text"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor is not None:
            self.anchor["text"] = " ".join(self.anchor["text"].split())
            self.links.append(self.anchor)
            self.anchor = None


def test_login_has_prominent_real_account_links(app, client):
    response = client.get("/login")
    assert response.status_code == 200
    page = Page(response)
    with app.test_request_context():
        register = url_for("auth.register")
        recovery = url_for("auth.forgot_password")
    signup_link = next(link for link in page.links if link["href"] == register)
    recovery_link = next(link for link in page.links if link["href"] == recovery)
    assert signup_link["text"] == "Criar conta gratuitamente"
    assert {"button", "secondary", "full"} <= set(signup_link["class"].split())
    assert recovery_link["text"] == "Esqueceu sua senha?"
    assert "Ainda não possui uma conta?" in response.get_data(as_text=True)
    assert "Entrar na plataforma" in response.get_data(as_text=True)
    for link in (signup_link, recovery_link):
        assert client.get(link["href"]).status_code == 200


@pytest.mark.parametrize(
    ("path", "field_names", "submit_text"),
    [
        ("/login", {"email", "password"}, "Entrar na plataforma"),
        (
            "/register",
            {"name", "company_name", "email", "password", "confirm_password"},
            "Criar minha conta",
        ),
        ("/forgot-password", {"email"}, "Solicitar código"),
    ],
)
def test_initial_auth_pages_render_accessible_forms(
    client, path, field_names, submit_text
):
    response = client.get(path)
    assert response.status_code == 200
    page = Page(response)
    inputs = {attrs["name"]: attrs for tag, attrs in page.elements if tag == "input"}
    assert field_names | {"csrf_token"} == set(inputs)
    for name in field_names:
        assert "required" in inputs[name]
        assert any(
            tag == "label" and attrs.get("for") == inputs[name]["id"]
            for tag, attrs in page.elements
        )
    assert submit_text in response.get_data(as_text=True)
    assert any(
        tag == "form" and "data-auth-form" in attrs for tag, attrs in page.elements
    )
    assert any(
        tag == "p" and attrs.get("role") == "status" for tag, attrs in page.elements
    )
    for name in field_names & {"password", "confirm_password"}:
        assert inputs[name]["type"] == "password" and "value" not in inputs[name]
        assert any(
            tag == "button"
            and attrs.get("aria-controls") == name
            and attrs.get("type") == "button"
            and attrs.get("aria-pressed") == "false"
            for tag, attrs in page.elements
        )


@pytest.mark.parametrize("purpose", ["signup", "reset"])
def test_code_and_reset_pages_render_only_after_starting_flow(app, client, purpose):
    start = "/register" if purpose == "signup" else "/forgot-password"
    fields = {"email": "admin@example.test"}
    if purpose == "signup":
        fields.update(
            name="Nova Pessoa",
            company_name="Nova Empresa",
            password="NovaSenhaForte123!",
            confirm_password="NovaSenhaForte123!",
        )
    assert post(client, start, fields, start).status_code == 302
    path = f"/verify/{purpose}"
    response = client.get(path)
    assert response.status_code == 200
    page = Page(response)
    code_input = next(
        attrs for tag, attrs in page.elements if attrs.get("name") == "code"
    )
    assert code_input["autocomplete"] == "one-time-code"
    assert code_input["inputmode"] == "numeric" and code_input["pattern"] == "[0-9]{6}"
    with app.test_request_context():
        resend = url_for("auth.resend", purpose=purpose)
    assert any(
        tag == "form" and attrs.get("action") == resend for tag, attrs in page.elements
    )
    assert client.post(resend).status_code == 400
    if purpose == "reset":
        code = app.extensions["email_outbox"][-1][1]
        assert post(client, path, {"code": code}, path).location.endswith(
            "/reset-password"
        )
        reset = client.get("/reset-password")
        assert reset.status_code == 200
        password_inputs = [
            attrs
            for tag, attrs in Page(reset).elements
            if attrs.get("name") in {"password", "confirm_password"}
        ]
        assert len(password_inputs) == 2 and all(
            attrs["type"] == "password" for attrs in password_inputs
        )
        assert client.post("/reset-password").status_code == 400


def test_auth_routes_are_registered_with_expected_methods(app, client):
    expected = {
        "auth.register": {"GET", "POST"},
        "auth.forgot_password": {"GET", "POST"},
        "auth.verify_email": {"GET", "POST"},
        "auth.resend": {"POST"},
        "auth.reset_password": {"GET", "POST"},
    }
    rules = {
        rule.endpoint: rule.methods - {"HEAD", "OPTIONS"}
        for rule in app.url_map.iter_rules()
    }
    for endpoint, methods in expected.items():
        assert rules[endpoint] == methods
    for path in (
        "/dashboard",
        "/employees/",
        "/shifts/",
        "/schedules/",
        "/settings",
        "/schedules/export.pdf",
    ):
        assert client.get(path).status_code == 302
    assert client.get("/verify/signup").location.endswith("/register")
    assert client.get("/verify/reset").location.endswith("/forgot-password")
    assert client.get("/reset-password").location.endswith("/forgot-password")


def test_factory_loads_smtp_from_isolated_dotenv(tmp_path, monkeypatch):
    from app import create_app

    project = tmp_path / "smtp-config"
    (project / "app").mkdir(parents=True)
    fake_values = {
        "SMTP_HOST": "smtp.example.test",
        "SMTP_PORT": "465",
        "SMTP_USERNAME": "fake-smtp-user",
        "SMTP_PASSWORD": "fake-smtp-password",
        "SMTP_FROM": "sender@example.test",
        "SMTP_STARTTLS": "false",
        "SMTP_SSL": "true",
    }
    (project / ".env").write_text(
        "\n".join(f"{name}={value}" for name, value in fake_values.items()),
        encoding="utf-8",
    )
    monkeypatch.setattr("app.__file__", str(project / "app" / "__init__.py"))
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    for name in fake_values:
        monkeypatch.delenv(name, raising=False)
    isolated = create_app({"TESTING": True, "SECRET_KEY": "fake-test-key-" + "x" * 40})
    for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM"):
        assert isolated.config[name] == fake_values[name]
    assert isolated.config["SMTP_PORT"] == 465
    assert (
        isolated.config["SMTP_SSL"] is True
        and isolated.config["SMTP_STARTTLS"] is False
    )
