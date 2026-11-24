"""Validação real em Chromium, com cópia descartável de uma demo identificada.

Não lê .env, não usa perfil pessoal e não envia e-mails. Instale os requisitos
opcionais e o navegador conforme docs/screenshots/README.md.
"""

import argparse
from contextlib import closing
import json
import logging
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
from threading import Thread
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Instalação isolada usada nesta auditoria; a instalação opcional no venv também serve.
if (ROOT / "tmp/browser-tools/playwright").is_dir():
    sys.path.insert(0, str(ROOT / "tmp/browser-tools"))
if (ROOT / "tmp/browser-browsers").is_dir():
    os.environ.setdefault(
        "PLAYWRIGHT_BROWSERS_PATH", str(ROOT / "tmp/browser-browsers")
    )

from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

from scripts.seed_demo import create_demo_app, demo_path, require_demo

VIEWPORTS = [(1920, 1080), (1366, 768), (768, 1024), (390, 844)]


def project_path(value):
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Artefatos devem permanecer dentro do projeto.")
    return path


def clone_demo(source):
    """A base preparada e suas credenciais nunca são modificadas."""
    require_demo(source)
    target = demo_path(f"instance/demo/browser-run-{secrets.token_hex(6)}.demo.sqlite3")
    with target.open("xb"):
        pass
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as origin:
        with closing(sqlite3.connect(target)) as copy:
            origin.backup(copy)
    require_demo(target)
    return target


def run(source, output, screenshots):
    output.mkdir(parents=True, exist_ok=True)
    screenshots.mkdir(parents=True, exist_ok=True)
    credentials = json.loads(
        source.with_suffix(".credentials.json").read_text(encoding="utf-8")
    )
    target = clone_demo(source)
    # Nomes sintéticos distintos tornam os resumos pequenos mais identificáveis.
    names = [
        "Ana Fictícia",
        "Bruno Fictício",
        "Clara Fictícia",
        "Diego Fictício",
        "Elisa Fictícia",
        "Fábio Fictício",
        "Gabriela Fictícia",
        "Hugo Fictício",
        "Iara Fictícia",
        "João Fictício",
        "Lia Fictícia",
        "Marcos Fictício",
        "Nina Fictícia",
        "Otávio Fictício",
        "Paula Fictícia",
    ]
    with closing(sqlite3.connect(target)) as db:
        employee_ids = [
            row[0] for row in db.execute("SELECT id FROM employees ORDER BY id")
        ]
        assert len(employee_ids) == 15
        for employee_id, name in zip(employee_ids, names):
            db.execute("UPDATE employees SET name=? WHERE id=?", (name, employee_id))
        db.commit()
    app = create_demo_app(target)
    mailbox = []
    app.extensions["email_sender"] = lambda recipient, code, purpose: mailbox.append(
        (recipient, code, purpose)
    )
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    result = {
        "run_database": target.relative_to(ROOT).as_posix(),
        "sandbox_enabled": True,
        "mail_transport": "memory-only",
        "checks": [],
        "layouts": [],
        "screenshots": [],
        "page_errors": [],
        "console_errors": [],
        "failed_requests": [],
        "http_errors": [],
    }
    expected_http = set()

    def record(name):
        result["checks"].append({"name": name, "status": "passed"})
        print(f"OK: {name}", flush=True)

    def sql(statement, values=()):
        with closing(sqlite3.connect(target.as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            return db.execute(statement, values).fetchall()

    def monitor(page):
        page.on("pageerror", lambda error: result["page_errors"].append(str(error)))
        page.on(
            "console",
            lambda msg: (
                result["console_errors"].append(
                    {
                        "message": msg.text,
                        "path": urlsplit(msg.location.get("url", "")).path,
                    }
                )
                if msg.type == "error"
                else None
            ),
        )
        page.on(
            "requestfailed",
            lambda request: result["failed_requests"].append(
                {
                    "host": urlsplit(request.url).hostname,
                    "path": urlsplit(request.url).path,
                    "failure": request.failure,
                }
            ),
        )

        def response_seen(response):
            if response.status >= 400:
                key = (
                    response.request.method,
                    urlsplit(response.url).path,
                    response.status,
                )
                result["http_errors"].append(
                    {
                        "method": key[0],
                        "path": key[1],
                        "status": key[2],
                        "expected": key in expected_http,
                    }
                )

        page.on("response", response_seen)
        page.on("dialog", lambda dialog: dialog.accept())

    def go(page, path):
        response = page.goto(base + path, wait_until="domcontentloaded")
        if response is None:
            # Uma mudança somente da âncora não produz outra resposta HTTP.
            assert page.url == base + path
        else:
            assert response.status == 200
        return response

    def login(page, email, password):
        go(page, "/login")
        page.locator("#email").fill(email)
        page.locator("#password").fill(password)
        page.get_by_role("button", name="Entrar na plataforma").click()
        expect(page).to_have_url(base + "/dashboard")

    def logout(page):
        if page.locator(".menu-toggle").is_visible():
            page.locator(".menu-toggle").click()
        page.get_by_role("button", name="Sair da conta").click()
        expect(page).to_have_url(base + "/login")

    def code_for(email, purpose):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            matches = [
                code
                for recipient, code, kind in mailbox
                if recipient == email and kind == purpose
            ]
            if matches:
                return matches[-1]
            time.sleep(0.05)
        raise AssertionError("Remetente simulado não recebeu o código.")

    def shot(page, name, full_page=True):
        page.evaluate("document.fonts.ready")
        page.screenshot(path=str(screenshots / name), full_page=full_page)
        result["screenshots"].append(
            {"file": name, "viewport": page.viewport_size, "full_page": full_page}
        )

    page = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                channel="chromium", headless=True, chromium_sandbox=True
            )
            result["browser_version"] = browser.version
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
                accept_downloads=True,
            )
            page = context.new_page()
            monitor(page)
            go(page, "/dashboard")
            expect(page).to_have_url(base + "/login")
            shot(page, "01-login.png")
            record("Proteção de páginas privadas e login vazio")
            page.locator("#email").fill(credentials["email"])
            page.locator("#password").fill("invalid-fictitious-password")
            expected_http.add(("POST", "/login", 401))
            with page.expect_response(
                lambda r: r.request.method == "POST"
                and urlsplit(r.url).path == "/login"
            ) as response:
                page.get_by_role("button", name="Entrar na plataforma").click()
            assert response.value.status == 401
            expect(page.locator(".flash")).to_contain_text("E-mail ou senha inválidos")
            login(page, credentials["email"], credentials["password"])
            record("Login inválido rejeitado e login administrativo válido")
            shot(page, "02-dashboard.png")
            expect(page.locator("#weekly-chart")).to_be_visible()
            assert page.evaluate("typeof Chart === 'function'")
            record("Dashboard e gráfico JavaScript renderizado")

            # Conta separada, criada pela interface e ativada sem e-mail real.
            other = browser.new_context(
                viewport={"width": 1366, "height": 768}, locale="pt-BR"
            )
            account = other.new_page()
            monitor(account)
            email = f"browser-{secrets.token_hex(5)}@example.test"
            password = secrets.token_urlsafe(18) + "aA1!"
            go(account, "/register")
            for field, value in {
                "name": "Administrador de teste",
                "company_name": "Empresa Fictícia de Testes",
                "email": email,
                "password": password,
                "confirm_password": password,
            }.items():
                account.locator("#" + field).fill(value)
            account.get_by_role("button", name="Criar minha conta").click()
            expect(account).to_have_url(base + "/verify/signup")
            assert account.locator("#resend-code").is_disabled()
            account.locator("#code").fill(code_for(email, "signup"))
            account.get_by_role("button", name="Confirmar código").click()
            expect(account).to_have_url(base + "/login")
            login(account, email, password)
            record("Cadastro de empresa, código simulado e cooldown de reenvio")
            go(account, "/employees/")
            expect(account.get_by_text("Sua equipe começa aqui")).to_be_visible()
            assert "Ana Fictícia" not in account.locator("main").inner_text()
            expected_http.add(("GET", "/employees/1/edit", 404))
            assert account.goto(base + "/employees/1/edit").status == 404
            record("Isolamento da empresa e rejeição de identificador alheio")
            go(account, "/employees/new")
            account.get_by_role("button", name="Salvar funcionário").click()
            assert account.locator("#name").evaluate("e => e.validity.valueMissing")
            for field, value in {
                "name": "Profissional Fictício UI",
                "role": "Analista",
                "department": "Qualidade",
                "email": "profissional-ui@example.test",
                "weekly_hours": "40",
            }.items():
                account.locator("#" + field).fill(value)
            account.get_by_role("button", name="Salvar funcionário").click()
            expect(account).to_have_url(base + "/employees/")
            account.get_by_role("link", name="Editar", exact=True).click()
            account.locator("#name").fill("Profissional Fictício Ajustado")
            account.get_by_role("button", name="Salvar funcionário").click()
            account.get_by_role("button", name="Desativar", exact=True).click()
            expect(account.get_by_text("Inativo", exact=True)).to_be_visible()
            account.get_by_role("button", name="Reativar", exact=True).click()
            expect(account.get_by_text("Ativo", exact=True)).to_be_visible()
            employee = sql(
                "SELECT id FROM employees WHERE name=?",
                ("Profissional Fictício Ajustado",),
            )[0]["id"]
            record("Funcionário: validação, cadastro, edição, desativação e reativação")
            go(account, "/shifts/")
            for field, value in {
                "name": "Noturno fictício UI",
                "start_time": "20:00",
                "end_time": "20:00",
                "break_minutes": "30",
            }.items():
                account.locator("#" + field).fill(value)
            expected_http.add(("POST", "/shifts/", 422))
            with account.expect_response(
                lambda r: r.request.method == "POST"
                and urlsplit(r.url).path == "/shifts/"
            ) as response:
                account.get_by_role("button", name="Salvar turno").click()
            assert response.value.status == 422
            account.locator("#end_time").fill("04:00")
            account.get_by_role("button", name="Salvar turno").click()
            account.get_by_role("link", name="Editar", exact=True).click()
            account.locator("#name").fill("Noturno fictício ajustado")
            account.get_by_role("button", name="Salvar turno").click()
            shift = sql(
                "SELECT id FROM shifts WHERE name=?", ("Noturno fictício ajustado",)
            )[0]["id"]
            record("Turno: horário inválido, cadastro noturno e edição")
            go(account, "/schedules/?month=2028-02")
            account.locator('[data-calendar-day="2028-02-29"] .add-day').click()
            expect(account.locator("#work_date")).to_have_value("2028-02-29")
            expect(account.locator("#employee_id")).to_be_focused()
            account.locator("#employee_id").select_option(str(employee))
            account.locator("#shift_id").select_option(str(shift))
            account.get_by_role("button", name="Salvar atribuição").click()
            expect(account.locator("#day-detail")).to_contain_text(
                "Noturno fictício ajustado"
            )
            row = sql(
                "SELECT id,work_date,end_at FROM schedules WHERE employee_id=?",
                (employee,),
            )[0]
            assert row["work_date"] == "2028-02-29" and row["end_at"].startswith(
                "2028-03-01"
            )
            record("Clique no dia, foco, data gravada e noite em ano bissexto")
            expected_http.add(("POST", "/schedules/", 422))
            account.locator("#employee_id").select_option(str(employee))
            account.locator("#shift_id").select_option(str(shift))
            with account.expect_response(
                lambda r: r.request.method == "POST"
                and urlsplit(r.url).path == "/schedules/"
            ) as response:
                account.get_by_role("button", name="Salvar atribuição").click()
            assert response.value.status == 422
            assert (
                len(sql("SELECT id FROM schedules WHERE employee_id=?", (employee,)))
                == 1
            )
            record("Conflito de escala bloqueado sem duplicação")
            go(account, "/schedules/?month=2028-03&day=2028-03-01")
            expect(account.locator("#day-detail")).to_contain_text("Continuação")
            account.locator("#day-detail").get_by_role(
                "link", name="Editar", exact=True
            ).click()
            account.locator("#work_date").fill("2028-03-02")
            account.get_by_role("button", name="Salvar atribuição").click()
            assert (
                sql("SELECT work_date FROM schedules WHERE id=?", (row["id"],))[0][0]
                == "2028-03-02"
            )
            account.locator("#day-detail").get_by_role(
                "button", name="Remover turno", exact=False
            ).click()
            assert not sql("SELECT id FROM schedules WHERE id=?", (row["id"],))
            record("Continuação, edição e exclusão de escala com confirmação JS")
            account.locator("#unavailable_employee").select_option(str(employee))
            account.locator("#start_at").fill("2028-03-02T00:00")
            account.locator("#end_at").fill("2028-03-04T00:00")
            account.locator("#reason").fill("Férias fictícias")
            account.get_by_role("button", name="Registrar período").click()
            account.locator("#employee_id").select_option(str(employee))
            account.locator("#shift_id").select_option(str(shift))
            account.locator("#work_date").fill("2028-03-02")
            with account.expect_response(
                lambda r: r.request.method == "POST"
                and urlsplit(r.url).path == "/schedules/"
            ) as response:
                account.get_by_role("button", name="Salvar atribuição").click()
            assert response.value.status == 422
            expect(account.locator(".flash")).to_contain_text("indisponível")
            account.locator("table tbody tr").get_by_role(
                "button", name="Remover", exact=True
            ).click()
            record("Indisponibilidade, férias, conflito e remoção via interface")
            go(account, "/settings")
            account.locator("#company_name").fill("Empresa Fictícia UI Validada")
            account.locator("#min_rest_hours").fill("12")
            account.get_by_role("button", name="Salvar configurações").click()
            assert sql(
                "SELECT company_name FROM company_settings WHERE company_name=?",
                ("Empresa Fictícia UI Validada",),
            )
            record("Configurações da empresa gravadas")
            logout(account)
            go(account, "/forgot-password")
            account.locator("#email").fill(email)
            account.get_by_role("button", name="Solicitar código").click()
            expect(account).to_have_url(base + "/verify/reset")
            account.locator("#code").fill(code_for(email, "reset"))
            account.get_by_role("button", name="Confirmar código").click()
            expect(account).to_have_url(base + "/reset-password")
            new_password = secrets.token_urlsafe(18) + "bB2!"
            account.locator("#password").fill(new_password)
            account.locator("#confirm_password").fill(new_password)
            account.get_by_role("button", name="Salvar nova senha").click()
            expect(account).to_have_url(base + "/login")
            login(account, email, new_password)
            logout(account)
            record("Recuperação com e-mail simulado, nova senha de teste e logout")
            other.close()

            # Demonstração original do administrador: navegação e responsividade.
            for month, count in [
                ("2026-02", 28),
                ("2028-02", 29),
                ("2026-11", 30),
                ("2026-12", 31),
            ]:
                go(page, "/schedules/?month=" + month)
                expect(page.locator("[data-calendar-day]")).to_have_count(count)
            page.get_by_role("link", name="Próximo mês", exact=True).click()
            expect(page.locator(".calendar-toolbar h2")).to_have_text("Janeiro de 2027")
            page.get_by_role("link", name="Mês anterior", exact=True).click()
            expect(page.locator(".calendar-toolbar h2")).to_have_text(
                "Dezembro de 2026"
            )
            page.get_by_role("link", name="Hoje", exact=True).click()
            from app.services.clock import local_now

            with app.app_context():
                today = local_now().date().isoformat()
            expect(page.locator(f'[data-calendar-day="{today}"]')).to_have_class(
                re.compile("is-today")
            )
            record("28/29/30/31 dias, dezembro/janeiro e botão Hoje")
            go(page, "/schedules/?month=2026-11")
            page.locator('[data-calendar-day="2026-11-23"] .more-events').click()
            expect(page.locator("#day-detail .schedule-event")).to_have_count(10)
            expect(page.locator("#day-detail")).to_be_focused()
            record("Múltiplas atribuições e lista completa do dia com foco")
            for width, height in VIEWPORTS:
                page.set_viewport_size({"width": width, "height": height})
                for route in [
                    "/dashboard",
                    "/employees/",
                    "/employees/new",
                    "/shifts/",
                    "/schedules/?month=2026-11",
                    "/schedules/?week=2026-11-23",
                    "/settings",
                ]:
                    go(page, route)
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth + 2"
                    )
                    assert page.locator("input:not([type=hidden])").evaluate_all(
                        "es => es.every(e=>!!e.labels?.length || !!e.getAttribute('aria-label'))"
                    )
                    if "month=" in route:
                        cards = page.locator(".schedule-forms > .panel")
                        a, b = cards.nth(0).bounding_box(), cards.nth(1).bounding_box()
                        if width <= 980:
                            assert (
                                abs(a["x"] - b["x"]) < 2
                                and b["y"] >= a["y"] + a["height"] - 2
                            )
                            assert (
                                page.locator("#employee_id").bounding_box()["width"]
                                >= 240
                            )
                        assert page.locator("[data-calendar-day]").count() == 30
                    if page.locator(".menu-toggle").is_visible():
                        page.locator(".menu-toggle").click()
                        expect(page.locator(".menu-toggle")).to_have_attribute(
                            "aria-expanded", "true"
                        )
                        expect(page.locator("#sidebar")).to_be_in_viewport()
                        page.keyboard.press("Escape")
                        expect(page.locator(".menu-toggle")).to_have_attribute(
                            "aria-expanded", "false"
                        )
                    result["layouts"].append(
                        {"viewport": [width, height], "route": route, "passed": True}
                    )
                record(f"Responsividade e acessibilidade básica {width}x{height}")

            # Capturas somente após os testes; não incluem senhas/códigos/perfis reais.
            page.set_viewport_size({"width": 1920, "height": 1080})
            for route, name in [
                ("/employees/", "03-funcionarios.png"),
                ("/shifts/", "04-turnos.png"),
                ("/schedules/?month=2026-11", "05-calendario-mensal.png"),
            ]:
                go(page, route)
                shot(page, name)
            go(page, "/schedules/?month=2026-11&day=2026-11-30#assignment-form")
            page.locator("#employee_id").select_option(str(employee_ids[0]))
            page.locator("#shift_id").select_option(index=1)
            page.locator("#assignment-form").evaluate(
                "e => e.scrollIntoView({block:'center',behavior:'instant'})"
            )
            expect(page.locator("#assignment-form")).to_be_in_viewport(ratio=0.9)
            shot(page, "06-atribuicao-escala.png", False)
            go(page, "/schedules/?month=2026-11&day=2026-11-23")
            page.get_by_role("link", name="Ver semana", exact=True).click()
            expect(page.locator(".week-grid")).to_be_visible()
            shot(page, "07-calendario-semanal.png")
            pdf_paths = []
            for route, label in [
                ("/schedules/?month=2026-11", "mensal"),
                ("/schedules/?week=2026-11-23", "semanal"),
            ]:
                go(page, route)
                with page.expect_download() as downloaded:
                    page.get_by_role(
                        "link", name="Exportar PDF " + label, exact=True
                    ).click()
                pdf_path = output / f"report-{label}.pdf"
                downloaded.value.save_as(pdf_path)
                assert pdf_path.read_bytes().startswith(b"%PDF-")
                pdf_paths.append(pdf_path)
            record("Alternância semanal e downloads PDF mensal/semanal no navegador")
            preview = context.new_page()
            monitor(preview)
            preview.goto(pdf_paths[0].as_uri())
            preview.wait_for_timeout(1500)
            preview.screenshot(path=str(screenshots / "08-relatorio-pdf.png"))
            result["screenshots"].append(
                {
                    "file": "08-relatorio-pdf.png",
                    "viewport": preview.viewport_size,
                    "source": "PDF exportado no visualizador Chromium",
                }
            )
            preview.close()
            for width, height, name in [
                (768, 1024, "09-versao-tablet.png"),
                (390, 844, "10-versao-mobile.png"),
            ]:
                page.set_viewport_size({"width": width, "height": height})
                go(page, "/dashboard")
                shot(page, name, False)
            logout(page)
            go(page, "/dashboard")
            expect(page).to_have_url(base + "/login")
            record("Logout e proteção final de sessão")
            browser.close()
        assert not result["page_errors"], result["page_errors"]
        assert not [r for r in result["http_errors"] if not r["expected"]], result[
            "http_errors"
        ]
        result["status"] = "passed"
        return result
    except Exception as error:
        result["status"] = "failed"
        result["failure"] = str(error)
        if page and not page.is_closed():
            try:
                page.screenshot(path=str(output / "failure.png"), full_page=True)
            except Exception:
                pass
        raise
    finally:
        (output / "browser-results.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        required=True,
        help="Demo já preparada; será copiada sem alterações.",
    )
    parser.add_argument(
        "--artifacts",
        default="tmp/browser-validation",
        help="Diretório de evidências privadas.",
    )
    parser.add_argument("--screenshots", default="docs/screenshots")
    args = parser.parse_args()
    result = run(
        demo_path(args.database),
        project_path(args.artifacts),
        project_path(args.screenshots),
    )
    print(
        json.dumps(
            {
                "checks": len(result["checks"]),
                "layouts": len(result["layouts"]),
                "screenshots": len(result["screenshots"]),
                "browser": result["browser_version"],
                "status": result["status"],
            }
        )
    )


if __name__ == "__main__":
    main()
