"""Tests for the portable local and managed-demo server entrypoint."""
from __future__ import annotations

import os
import socket
import sys
from types import SimpleNamespace

import pytest

import app.cli.serve as serve
from app.cli.serve import (
    _browser_host,
    _choose_port,
    _configure_llm,
    _llm_is_configured,
    _open_browser_when_ready,
    _uvicorn_log_config,
)


def test_choose_requested_available_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    assert _choose_port("127.0.0.1", port) == port


def test_requested_occupied_port_fails():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
        with pytest.raises(RuntimeError, match="already in use"):
            _choose_port("127.0.0.1", port)


def test_browser_host_maps_wildcard_to_loopback():
    assert _browser_host("0.0.0.0") == "127.0.0.1"
    assert _browser_host("127.0.0.1") == "127.0.0.1"


def test_browser_host_brackets_ipv6_loopback_for_urls():
    assert _browser_host("::1") == "[::1]"


def test_auto_mode_detects_anthropic_key(monkeypatch):
    monkeypatch.setenv("ABDA_LLM_BACKEND", "claude")
    monkeypatch.setenv("ABDA_CLAUDE_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert _llm_is_configured() is True


def test_explicit_basic_mode_wins(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert _configure_llm("off") is False
    assert os.environ["ABDA_ENABLE_LLM"] == "0"


def test_explicit_llm_mode_wins(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert _configure_llm("on") is True
    assert os.environ["ABDA_ENABLE_LLM"] == "1"


def test_browser_opens_only_after_readiness(monkeypatch):
    opened: list[str] = []

    class ReadyResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(serve.urllib.request, "urlopen", lambda *_args, **_kwargs: ReadyResponse())
    monkeypatch.setattr(serve.webbrowser, "open", opened.append)

    _open_browser_when_ready("http://127.0.0.1:8000", timeout_seconds=0.1)

    assert opened == ["http://127.0.0.1:8000"]


def test_server_disables_query_string_access_logs(monkeypatch):
    called: dict = {}
    fake_uvicorn = SimpleNamespace(run=lambda *args, **kwargs: called.update(kwargs))
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.setattr(serve, "_load_environment", lambda: None)
    monkeypatch.setattr(serve, "_choose_port", lambda _host, requested: requested or 8000)
    monkeypatch.setattr(serve, "_configure_llm", lambda _mode: False)

    assert serve.main(["--port", "8765", "--no-browser"]) == 0
    assert called["host"] == "127.0.0.1"
    assert called["port"] == 8765
    assert called["access_log"] is False
    assert called["log_config"]["loggers"]["app"] == {
        "handlers": ["default"],
        "level": "INFO",
        "propagate": False,
    }


def test_application_log_config_is_an_independent_copy():
    first = _uvicorn_log_config()
    first["loggers"]["app"]["level"] = "ERROR"
    second = _uvicorn_log_config()

    assert second["loggers"]["app"]["level"] == "INFO"
