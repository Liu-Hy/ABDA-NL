"""Tests for the external public-release acceptance command."""
from __future__ import annotations

import json

import httpx
import pytest

from app.cli.release_check import ReleaseCheckError, check_public_release


ORIGIN = "https://abda-nl.ischool.illinois.edu"
METRICS_TOKEN = "release-check-metrics-token-with-32-characters"


def _config() -> dict:
    return {
        "llm_enabled": True,
        "llm_auth_required": True,
        "byok_enabled": True,
        "byok_keys_stored": False,
        "default_profile": "balanced",
        "profiles": [
            {
                "id": "balanced",
                "display_name": "Balanced",
                "description": "CloudBank primary with bounded outage fallback",
            }
        ],
        "byok_providers": [
            {
                "id": provider,
                "display_name": provider.title(),
                "default_model": model,
                "models": [{"id": model, "display_name": model}],
            }
            for provider, model in (
                ("anthropic", "claude-sonnet-5"),
                ("google", "gemini-3.7-flash"),
                ("openai", "gpt-5.6-terra"),
                ("openrouter", "gemini-3.7-flash"),
            )
        ],
    }


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "text/html; charset=utf-8",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        "Strict-Transport-Security": "max-age=31536000",
        "Content-Security-Policy": (
            "default-src 'self'; base-uri 'none'; object-src 'none'; "
            "frame-ancestors 'none'; script-src 'self'; connect-src 'self'; "
            "upgrade-insecure-requests"
        ),
    }


def _transport(*, config: dict | None = None, omit_header: str | None = None):
    public_config = config or _config()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.scheme == "http":
            return httpx.Response(308, headers={"Location": ORIGIN + "/"})
        if request.url.path == "/health/live":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/health/ready":
            return httpx.Response(200, json={"status": "ready"})
        if request.url.path == "/config":
            return httpx.Response(200, json=public_config)
        if request.url.path == "/internal/metrics":
            if request.headers.get("authorization") != f"Bearer {METRICS_TOKEN}":
                return httpx.Response(401, headers={"WWW-Authenticate": "Bearer"})
            metrics = "\n".join(
                [
                    "abda_database_pool_capacity 5",
                    "abda_database_pool_checked_out 1",
                    "abda_http_requests_total 1",
                    "abda_llm_usage_events_total 0",
                    "abda_openrouter_budget_microusd 500000000",
                    "abda_openrouter_reserved_microusd 0",
                    "abda_openrouter_spent_microusd 0",
                    "abda_openrouter_uncertain_charged_reservations 0",
                    "abda_openrouter_uncertain_charged_microusd 0",
                    "abda_trial_max_users 100",
                    "abda_trial_grant_microusd 5000000",
                    "abda_trial_budget_microusd 500000000",
                    "abda_trial_activations 0",
                    "abda_trial_allocated_microusd 0",
                    "abda_trial_reserved_microusd 0",
                    "abda_trial_spent_microusd 0",
                    "abda_trial_uncertain_charged_reservations 0",
                    "abda_trial_uncertain_charged_microusd 0",
                ]
            )
            return httpx.Response(200, text=metrics)
        headers = _headers()
        if omit_header:
            headers.pop(omit_header)
        if request.url.path in {"/", "/privacy.html", "/terms.html"}:
            return httpx.Response(200, text="<!doctype html>", headers=headers)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_public_release_check_returns_sanitized_evidence():
    evidence = check_public_release(
        ORIGIN,
        metrics_token=METRICS_TOKEN,
        transport=_transport(),
    )

    assert evidence["origin"] == ORIGIN
    assert evidence["checks"]["plain_http"] == "redirected"
    assert evidence["checks"]["budget_metrics"] == "passed"
    assert evidence["checks"]["database_pool"] == "passed"
    assert evidence["database_pool"] == {"capacity": 5, "checked_out": 1}
    assert evidence["budgets"] == {
        "trial_max_users": 100,
        "trial_grant_microusd": 5_000_000,
        "trial_budget_microusd": 500_000_000,
        "trial_activations": 0,
        "trial_allocated_microusd": 0,
        "trial_spent_microusd": 0,
        "trial_uncertain_charged_reservations": 0,
        "trial_uncertain_charged_microusd": 0,
        "openrouter_budget_microusd": 500_000_000,
        "openrouter_spent_microusd": 0,
        "openrouter_uncertain_charged_reservations": 0,
        "openrouter_uncertain_charged_microusd": 0,
    }
    assert evidence["config"]["funded_profiles"] == ["balanced"]
    serialized = json.dumps(evidence)
    assert METRICS_TOKEN not in serialized


def test_public_release_check_rejects_private_config_fields():
    config = _config()
    config["foundry_endpoint"] = "https://resource.services.ai.azure.com"

    with pytest.raises(ReleaseCheckError, match="forbidden field"):
        check_public_release(
            ORIGIN,
            metrics_token=METRICS_TOKEN,
            transport=_transport(config=config),
        )


def test_public_release_check_rejects_missing_security_header():
    with pytest.raises(ReleaseCheckError, match="x-frame-options"):
        check_public_release(
            ORIGIN,
            metrics_token=METRICS_TOKEN,
            transport=_transport(omit_header="X-Frame-Options"),
        )


@pytest.mark.parametrize(
    "origin",
    [
        "http://abda-nl.ischool.illinois.edu",
        "https://abda-nl.ischool.illinois.edu/path",
        "https://user@example.edu",
    ],
)
def test_public_release_check_rejects_non_origin_urls(origin: str):
    with pytest.raises(ReleaseCheckError, match="public origin"):
        check_public_release(
            origin,
            metrics_token=METRICS_TOKEN,
            transport=_transport(),
        )


def test_public_release_check_requires_metrics_secret_without_echoing_it():
    with pytest.raises(ReleaseCheckError, match="environment variable") as captured:
        check_public_release(ORIGIN, metrics_token=None, transport=_transport())

    assert METRICS_TOKEN not in str(captured.value)


@pytest.mark.parametrize(
    ("metric", "value", "message"),
    [
        ("abda_trial_reserved_microusd", "1", "trial reservations are not idle"),
        (
            "abda_openrouter_reserved_microusd",
            "1",
            "OpenRouter reservations are not idle",
        ),
        ("abda_trial_activations", "101", "trial activations exceed"),
    ],
)
def test_public_release_check_rejects_unsafe_budget_state(
    metric: str,
    value: str,
    message: str,
):
    base = _transport()

    def handler(request: httpx.Request) -> httpx.Response:
        response = base.handle_request(request)
        if request.url.path == "/internal/metrics" and response.status_code == 200:
            replacements = {metric: value}
            if metric == "abda_trial_reserved_microusd":
                replacements.update(
                    {
                        "abda_trial_activations": "1",
                        "abda_trial_allocated_microusd": "5000000",
                    }
                )
            lines = [
                (
                    f"{name} {replacements[name]}"
                    if (name := line.split(" ", 1)[0]) in replacements
                    else line
                )
                for line in response.text.splitlines()
            ]
            return httpx.Response(200, text="\n".join(lines))
        return response

    with pytest.raises(ReleaseCheckError, match=message):
        check_public_release(
            ORIGIN,
            metrics_token=METRICS_TOKEN,
            transport=httpx.MockTransport(handler),
        )


def test_public_release_check_requires_the_expected_openrouter_cap():
    with pytest.raises(ReleaseCheckError, match="does not match"):
        check_public_release(
            ORIGIN,
            metrics_token=METRICS_TOKEN,
            expected_openrouter_budget_microusd=1_000_000_000,
            transport=_transport(),
        )


@pytest.mark.parametrize(
    ("metric", "value", "message"),
    [
        ("abda_database_pool_capacity", "6", "B1ms release budget"),
        ("abda_database_pool_checked_out", "6", "exceeds its capacity"),
    ],
)
def test_public_release_check_rejects_unsafe_database_pool(
    metric: str, value: str, message: str
):
    base = _transport()

    def handler(request: httpx.Request) -> httpx.Response:
        response = base.handle_request(request)
        if request.url.path == "/internal/metrics" and response.status_code == 200:
            lines = [
                f"{metric} {value}" if line.startswith(f"{metric} ") else line
                for line in response.text.splitlines()
            ]
            return httpx.Response(200, text="\n".join(lines))
        return response

    with pytest.raises(ReleaseCheckError, match=message):
        check_public_release(
            ORIGIN,
            metrics_token=METRICS_TOKEN,
            transport=httpx.MockTransport(handler),
        )
