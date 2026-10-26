"""Evita iniciar silenciosamente uma segunda instância na mesma porta."""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def entry(app, monkeypatch):
    monkeypatch.setattr("app.create_app", lambda: app)
    spec = importlib.util.spec_from_file_location(
        "tested_run", Path(__file__).resolve().parents[1] / "run.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_entry_refuses_to_start_when_port_already_responds(entry, monkeypatch):
    run = MagicMock()
    connection = MagicMock()
    monkeypatch.setattr(
        entry.socket, "create_connection", lambda *args, **kwargs: connection
    )
    monkeypatch.setattr(entry.app, "run", run)
    with pytest.raises(SystemExit, match="já está em uso"):
        entry.main()
    run.assert_not_called()
    connection.__exit__.assert_called_once()


def test_entry_starts_when_no_server_is_listening(entry, monkeypatch):
    def refused(*args, **kwargs):
        raise ConnectionRefusedError

    run = MagicMock()
    monkeypatch.setattr(entry.socket, "create_connection", refused)
    monkeypatch.setattr(entry.app, "run", run)
    entry.main()
    run.assert_called_once_with(host="127.0.0.1", port=5000)


def test_entry_fails_safely_when_port_check_times_out(entry, monkeypatch):
    def timeout(*args, **kwargs):
        raise TimeoutError

    run = MagicMock()
    monkeypatch.setattr(entry.socket, "create_connection", timeout)
    monkeypatch.setattr(entry.app, "run", run)
    with pytest.raises(SystemExit, match="verificar a porta"):
        entry.main()
    run.assert_not_called()


def test_development_server_refuses_production(entry, monkeypatch):
    entry.app.config["PRODUCTION"] = True
    run = MagicMock()
    monkeypatch.setattr(entry.app, "run", run)
    with pytest.raises(SystemExit, match="Gunicorn"):
        entry.main()
    run.assert_not_called()
