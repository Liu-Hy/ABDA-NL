"""Tests for the portable local and managed-demo server entrypoint."""
from __future__ import annotations

import os
import socket

import pytest

import app.cli.serve as serve
from app.cli.serve import (
    _browser_host,
    _choose_port,
    _configure_llm,
    _llm_is_configured,
    _open_browser_when_ready,
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


def test_auto_mode_detects_anthropic_key(monkeypatch):
    monkeypatch.setenv("ABDA_LLM_BACKEND", "claude")
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
