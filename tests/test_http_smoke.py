"""Integração pela pilha HTTP real, em loopback e porta temporária."""

import re
from http.cookiejar import CookieJar
from threading import Thread
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from werkzeug.serving import make_server


def test_local_http_login_pages_pdf_and_logout(app):
    server = make_server("127.0.0.1", 0, app)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    jar = CookieJar()
    client = build_opener(HTTPCookieProcessor(jar))
    try:
        with client.open(base + "/", timeout=5) as response:
            assert response.status == 200
        with client.open(base + "/dashboard", timeout=5) as response:
            assert response.geturl().endswith("/login")
        with client.open(base + "/login", timeout=5) as response:
            login_page = response.read()
            assert b'href="/register"' in login_page
            assert b'href="/forgot-password"' in login_page
            assert "Criar conta gratuitamente" in login_page.decode()
            assert "Esqueceu sua senha?" in login_page.decode()
            csrf_token = (
                re.search(rb'name="csrf_token" value="([^"]+)"', login_page)
                .group(1)
                .decode()
            )
        body = urlencode(
            {
                "email": "admin@example.test",
                "password": "test-password-123",
                "csrf_token": csrf_token,
            }
        ).encode()
        with client.open(Request(base + "/login", data=body), timeout=5) as response:
            assert response.status == 200 and response.geturl().endswith("/dashboard")
        for path in [
            "/employees/",
            "/shifts/",
            "/schedules/",
            "/settings",
            "/schedules/export.pdf",
        ]:
            with client.open(base + path, timeout=5) as response:
                assert response.status == 200
                if path.endswith(".pdf"):
                    assert response.read().startswith(b"%PDF-")
        with client.open(base + "/employees/", timeout=5) as response:
            csrf_token = (
                re.search(rb'name="csrf_token" value="([^"]+)"', response.read())
                .group(1)
                .decode()
            )
        original_cookie = next(
            cookie.value for cookie in jar if cookie.name == "session"
        )
        with client.open(
            Request(
                base + "/logout", data=urlencode({"csrf_token": csrf_token}).encode()
            ),
            timeout=5,
        ) as response:
            assert response.geturl().endswith("/login")
        replay = Request(
            base + "/dashboard", headers={"Cookie": f"session={original_cookie}"}
        )
        with urlopen(replay, timeout=5) as response:
            assert response.geturl().endswith("/login")

        def submit(path, fields, source=None):
            with client.open(base + (source or path), timeout=5) as response:
                csrf_token = (
                    re.search(rb'name="csrf_token" value="([^"]+)"', response.read())
                    .group(1)
                    .decode()
                )
            with client.open(
                Request(
                    base + path,
                    data=urlencode({**fields, "csrf_token": csrf_token}).encode(),
                ),
                timeout=5,
            ) as response:
                return response.geturl(), response.read()

        target, _page = submit(
            "/register",
            {
                "name": "HTTP Novo Admin",
                "company_name": "HTTP Empresa Nova",
                "email": "http@example.test",
                "password": "SenhaHttpForte123!",
                "confirm_password": "SenhaHttpForte123!",
            },
        )
        assert target.endswith("/verify/signup")
        code = app.extensions["email_outbox"][-1][1]
        target, _page = submit("/verify/signup", {"code": code})
        assert target.endswith("/login")
        target, page = submit(
            "/login", {"email": "http@example.test", "password": "SenhaHttpForte123!"}
        )
        assert target.endswith("/dashboard") and "Sua equipe" in page.decode()
        target, _page = submit("/logout", {}, source="/dashboard")
        assert target.endswith("/login")
        target, _page = submit("/forgot-password", {"email": "http@example.test"})
        assert target.endswith("/verify/reset")
        code = app.extensions["email_outbox"][-1][1]
        target, _page = submit("/verify/reset", {"code": code})
        assert target.endswith("/reset-password")
        target, _page = submit(
            "/reset-password",
            {"password": "SenhaHttpNova456!", "confirm_password": "SenhaHttpNova456!"},
        )
        assert target.endswith("/login")
        target, _page = submit(
            "/login", {"email": "http@example.test", "password": "SenhaHttpNova456!"}
        )
        assert target.endswith("/dashboard")
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
