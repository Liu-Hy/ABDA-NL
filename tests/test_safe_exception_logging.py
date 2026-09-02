"""Unexpected failures retain diagnostics without logging exception messages."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.core.safe_logging import exception_diagnostic
from app.mcp.server import MCPToolUserError, _tool_boundary


def _raise_private_message() -> None:
    raise RuntimeError("private-account@example.edu bearer-private-value")


def test_exception_diagnostic_omits_the_exception_message() -> None:
    try:
        _raise_private_message()
    except RuntimeError as exc:
        diagnostic = exception_diagnostic(exc)
    else:  # pragma: no cover
        raise AssertionError("the test exception was not raised")

    assert diagnostic.kind == "RuntimeError"
    assert diagnostic.location.startswith(
        "test_safe_exception_logging.py:_raise_private_message:"
    )
    rendered = f"{diagnostic.kind} {diagnostic.location}"
    assert "private-account" not in rendered
    assert "bearer-private-value" not in rendered


def test_mcp_unexpected_failure_log_and_response_omit_private_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR, logger="app.mcp.server"):
        with pytest.raises(MCPToolUserError) as caught:
            with _tool_boundary("safe-log-test"):
                _raise_private_message()

    assert str(caught.value) == (
        "ABDA-NL could not complete this operation. Try again later."
    )
    assert "MCP tool failed operation=safe-log-test" in caplog.text
    assert "exception=RuntimeError" in caplog.text
    assert "location=test_safe_exception_logging.py:_raise_private_message:" in caplog.text
    assert "private-account@example.edu" not in caplog.text
    assert "bearer-private-value" not in caplog.text


def test_application_sources_do_not_use_exception_message_traceback_logging() -> None:
    app_root = Path(__file__).resolve().parents[1] / "app"
    offenders = [
        path.relative_to(app_root).as_posix()
        for path in app_root.rglob("*.py")
        if "log.exception(" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
