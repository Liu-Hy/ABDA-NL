"""Tests for the read-only public hostname boundary Gate."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "cloudflare" / "gate16_public_hostname_boundary.py"


def _module():
    spec = importlib.util.spec_from_file_location("gate16_public_hostname_boundary", GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _dns_snapshot() -> dict[tuple[str, str], list[str]]:
    return {
        ("abda-nl.org", "A"): ["104.21.10.20", "172.67.20.30"],
        ("www.abda-nl.org", "A"): ["104.21.10.20", "172.67.20.30"],
        ("demo.abda-nl.org", "CNAME"): [
            "abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io."
        ],
        ("login.abda-nl.org", "CNAME"): [
            "abda-nl-public-cd-agj741h5jp2wla4l.edge.tenants.us.auth0.com."
        ],
        ("send.auth.abda-nl.org", "MX"): [
            "10 feedback-smtp.us-east-1.amazonses.com."
        ],
        ("send.auth.abda-nl.org", "TXT"): [
            '"v=spf1 include:amazonses.com ~all"'
        ],
        ("resend._domainkey.auth.abda-nl.org", "TXT"): [
            '"p=' + "a" * 128 + '"'
        ],
        ("_dmarc.auth.abda-nl.org", "TXT"): ['"v=DMARC1; p=none;"'],
    }


def test_gate_is_fixed_read_only_and_content_free() -> None:
    source = GATE.read_text(encoding="utf-8")
    assert 'SCRIPT_REVISION = "1"' in source
    assert "PUBLIC_HOSTNAME_AND_EMAIL_DNS_BOUNDARY_VERIFIED" in source
    assert 'request(\n            "GET"' in source
    for forbidden in (
        "cloudflare_api_token",
        "Authorization",
        "az ",
        "subprocess.run([\"curl\"",
        "DELETE",
        "PATCH",
        "POST",
        "PUT",
    ):
        assert forbidden not in source
    assert "\N{EM DASH}" not in source and "\N{EN DASH}" not in source


def test_redirect_validation_requires_exact_301_location() -> None:
    module = _module()
    valid = module.HTTPResult(
        301,
        {"location": "https://demo.abda-nl.org/privacy.html?source=test"},
        b"",
    )
    module.validate_redirect(
        valid, "https://demo.abda-nl.org/privacy.html?source=test"
    )
    with pytest.raises(module.AcceptanceError, match="HTTP 301"):
        module.validate_redirect(
            module.HTTPResult(302, valid.headers, b""),
            "https://demo.abda-nl.org/privacy.html?source=test",
        )
    with pytest.raises(module.AcceptanceError, match="redirect target"):
        module.validate_redirect(valid, "https://login.abda-nl.org/")


def test_plain_http_accepts_direct_or_safe_https_apex_redirect(monkeypatch) -> None:
    module = _module()
    direct = module.HTTPResult(
        301,
        {"location": "https://demo.abda-nl.org/health/ready"},
        b"",
    )
    module.validate_http_entry(direct, "/health/ready")

    first_hop = module.HTTPResult(
        308,
        {"location": "https://abda-nl.org/health/ready"},
        b"",
    )
    second_hop = module.HTTPResult(
        301,
        {"location": "https://demo.abda-nl.org/health/ready"},
        b"",
    )
    monkeypatch.setattr(module, "request", lambda _url: second_hop)
    module.validate_http_entry(first_hop, "/health/ready")

    with pytest.raises(module.AcceptanceError, match="plaintext apex"):
        module.validate_http_entry(
            module.HTTPResult(302, {"location": "https://example.org/"}, b""),
            "/health/ready",
        )


def test_dns_validation_preserves_demo_auth0_and_email_boundaries() -> None:
    module = _module()
    records = _dns_snapshot()
    module.validate_dns_snapshot(records)

    records[("demo.abda-nl.org", "CNAME")] = ["wrong.example.org."]
    with pytest.raises(module.AcceptanceError, match="demo CNAME changed"):
        module.validate_dns_snapshot(records)


def test_dns_validation_rejects_missing_email_authentication() -> None:
    module = _module()
    records = _dns_snapshot()
    records[("_dmarc.auth.abda-nl.org", "TXT")] = []
    with pytest.raises(module.AcceptanceError, match="DMARC"):
        module.validate_dns_snapshot(records)


def test_json_validation_requires_exact_content() -> None:
    module = _module()
    module.validate_json(
        module.HTTPResult(200, {}, b'{"status":"ready"}'),
        {"status": "ready"},
        "readiness",
    )
    with pytest.raises(module.AcceptanceError, match="unexpected response"):
        module.validate_json(
            module.HTTPResult(200, {}, b'{"status":"starting"}'),
            {"status": "ready"},
            "readiness",
        )
