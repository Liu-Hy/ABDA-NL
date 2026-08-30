"""Contracts for the live public-browser accessibility gate."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate13_public_browser_accessibility.py"


def _module():
    spec = importlib.util.spec_from_file_location("public_browser_gate", GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_gate_is_executable_content_free_and_syntactically_valid() -> None:
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["python", "-m", "py_compile", str(GATE)], check=True)
    source = GATE.read_text(encoding="utf-8")
    for expected in (
        "LIVE_PUBLIC_CHROMIUM_FIREFOX_ACCESSIBILITY_VERIFIED",
        "wcag22aa",
        "reduced_motion=\"reduce\"",
        "#oidc-login-link",
        "to_be_focused",
        "200-percent-equivalent",
        "policy_links_before_registration: passed",
    ):
        assert expected in source
    for forbidden in (
        "api_key",
        "client_secret",
        "containerapp update",
        "az deployment",
        "page.screenshot",
    ):
        assert forbidden not in source.lower()
    assert "\N{EN DASH}" not in source and "\N{EM DASH}" not in source


@pytest.mark.parametrize(
    "value",
    (
        "http://demo.abda-nl.org",
        "https://demo.abda-nl.org/path",
        "https://user@demo.abda-nl.org",
        "https://example.org",
    ),
)
def test_gate_rejects_any_origin_outside_the_exact_public_service(value: str) -> None:
    with pytest.raises(ValueError):
        _module().validated_origin(value)


def test_gate_accepts_the_exact_public_origin_with_one_optional_slash() -> None:
    module = _module()
    assert module.validated_origin("https://demo.abda-nl.org") == (
        "https://demo.abda-nl.org"
    )
    assert module.validated_origin("https://demo.abda-nl.org/") == (
        "https://demo.abda-nl.org"
    )
