"""External acceptance check for an ABDA-NL public release."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
import sys
from typing import Any, Sequence
from urllib.parse import urlsplit, urlunsplit

import httpx


class ReleaseCheckError(RuntimeError):
    """Raised when a public release invariant is not satisfied."""


_FORBIDDEN_CONFIG_KEYS = {
    "apikey",
    "authorization",
    "baseurl",
    "clientsecret",
    "credential",
    "endpoint",
    "secret",
    "token",
}
_FORBIDDEN_CONFIG_VALUE_PARTS = (
    ".services.ai.azure.com",
    "/anthropic/v1/messages",
    "api.anthropic.com",
    "api.openai.com",
    "api.openrouter.ai",
    "generativelanguage.googleapis.com",
)
_EXPECTED_BYOK_PROVIDERS = {"anthropic", "google", "openai", "openrouter"}
_REQUIRED_METRICS = {
    "abda_database_pool_capacity",
    "abda_database_pool_checked_out",
    "abda_http_requests_total",
    "abda_llm_usage_events_total",
    "abda_openrouter_budget_microusd",
    "abda_openrouter_enabled",
    "abda_openrouter_reserved_microusd",
    "abda_openrouter_spent_microusd",
    "abda_openrouter_uncertain_charged_microusd",
    "abda_openrouter_uncertain_charged_reservations",
    "abda_trial_activations",
    "abda_trial_allocated_microusd",
    "abda_trial_budget_microusd",
    "abda_trial_enabled",
    "abda_trial_grant_microusd",
    "abda_trial_max_users",
    "abda_trial_reserved_microusd",
    "abda_trial_spent_microusd",
    "abda_trial_uncertain_charged_microusd",
    "abda_trial_uncertain_charged_reservations",
}

_TRIAL_MAX_USERS = 100
_TRIAL_GRANT_MICROUSD = 5_000_000
_TRIAL_BUDGET_MICROUSD = 500_000_000
_DATABASE_POOL_CAPACITY = 5


def _normalize_origin(raw_origin: str) -> str:
    value = raw_origin.strip().rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ReleaseCheckError(
            "the public origin must be one HTTPS origin without credentials, path, query, or fragment"
        )
    return value


def _request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    expected_status: int,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    try:
        response = client.request(method, url, headers=headers)
    except httpx.HTTPError as exc:
        raise ReleaseCheckError(f"{method} {url} failed: {type(exc).__name__}") from exc
    if response.status_code != expected_status:
        raise ReleaseCheckError(
            f"{method} {url} returned {response.status_code}, expected {expected_status}"
        )
    return response


def _json_object(response: httpx.Response, path: str) -> dict[str, Any]:
    try:
        value = response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise ReleaseCheckError(f"{path} did not return valid JSON") from exc
    if not isinstance(value, dict):
        raise ReleaseCheckError(f"{path} did not return a JSON object")
    return value


def _assert_security_headers(response: httpx.Response) -> None:
    required_exact = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "no-referrer",
        "cross-origin-opener-policy": "same-origin",
        "cross-origin-resource-policy": "same-origin",
    }
    for name, expected in required_exact.items():
        actual = response.headers.get(name)
        if actual != expected:
            raise ReleaseCheckError(
                f"the root response header {name} was {actual!r}, expected {expected!r}"
            )

    permissions = response.headers.get("permissions-policy", "")
    for directive in ("camera=()", "microphone=()", "geolocation=()", "payment=()"):
        if directive not in permissions:
            raise ReleaseCheckError(f"Permissions-Policy is missing {directive}")

    hsts = response.headers.get("strict-transport-security", "")
    if "max-age=31536000" not in hsts:
        raise ReleaseCheckError("Strict-Transport-Security is missing the one-year max-age")

    csp = response.headers.get("content-security-policy", "")
    for directive in (
        "default-src 'self'",
        "base-uri 'none'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "script-src 'self'",
        "connect-src 'self'",
        "upgrade-insecure-requests",
    ):
        if directive not in csp:
            raise ReleaseCheckError(f"Content-Security-Policy is missing {directive}")


def _assert_config_has_no_private_fields(value: Any, path: str = "config") -> None:
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key)
            normalized = key.lower().replace("_", "").replace("-", "")
            if key != "byok_keys_stored" and any(
                fragment in normalized for fragment in _FORBIDDEN_CONFIG_KEYS
            ):
                raise ReleaseCheckError(f"/config exposes forbidden field {path}.{key}")
            _assert_config_has_no_private_fields(child, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _assert_config_has_no_private_fields(child, f"{path}[{index}]")
        return
    if isinstance(value, str):
        lowered = value.lower()
        if any(part in lowered for part in _FORBIDDEN_CONFIG_VALUE_PARTS):
            raise ReleaseCheckError(f"/config exposes a private provider address at {path}")


def _assert_public_config(
    config: dict[str, Any], expected_profiles: Sequence[str]
) -> dict[str, Any]:
    required_flags = {
        "llm_enabled": True,
        "llm_auth_required": True,
        "byok_enabled": True,
        "byok_keys_stored": False,
    }
    for name, expected in required_flags.items():
        if config.get(name) is not expected:
            raise ReleaseCheckError(f"/config requires {name}={expected!r}")

    profiles = config.get("profiles")
    if not isinstance(profiles, list) or any(not isinstance(item, dict) for item in profiles):
        raise ReleaseCheckError("/config profiles must be a list of objects")
    profile_ids = sorted(str(item.get("id", "")) for item in profiles)
    expected_ids = sorted(set(expected_profiles))
    if profile_ids != expected_ids:
        raise ReleaseCheckError(
            f"/config funded profiles were {profile_ids!r}, expected {expected_ids!r}"
        )
    if config.get("default_profile") not in expected_ids:
        raise ReleaseCheckError("/config default_profile is not an expected funded profile")

    providers = config.get("byok_providers")
    if not isinstance(providers, list) or any(not isinstance(item, dict) for item in providers):
        raise ReleaseCheckError("/config byok_providers must be a list of objects")
    provider_ids = {str(item.get("id", "")) for item in providers}
    if provider_ids != _EXPECTED_BYOK_PROVIDERS:
        raise ReleaseCheckError(
            f"/config BYOK providers were {sorted(provider_ids)!r}, "
            f"expected {sorted(_EXPECTED_BYOK_PROVIDERS)!r}"
        )
    byok_model_counts: dict[str, int] = {}
    for provider in providers:
        provider_id = str(provider["id"])
        models = provider.get("models")
        if not isinstance(models, list) or not models:
            raise ReleaseCheckError(f"/config provider {provider_id} has no BYOK models")
        model_ids = [str(item.get("id", "")) for item in models if isinstance(item, dict)]
        if len(model_ids) != len(models) or len(set(model_ids)) != len(model_ids):
            raise ReleaseCheckError(f"/config provider {provider_id} has invalid model IDs")
        if provider.get("default_model") not in model_ids:
            raise ReleaseCheckError(
                f"/config provider {provider_id} has an unavailable default model"
            )
        byok_model_counts[provider_id] = len(model_ids)

    _assert_config_has_no_private_fields(config)
    return {
        "default_profile": config["default_profile"],
        "funded_profiles": profile_ids,
        "byok_model_counts": byok_model_counts,
    }


def _assert_plain_http_redirects_or_refuses(
    client: httpx.Client, origin: str
) -> str:
    parsed = urlsplit(origin)
    http_origin = urlunsplit(("http", parsed.netloc, "", "", ""))
    try:
        response = client.get(http_origin)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
        return "refused"
    if response.status_code not in {301, 302, 307, 308}:
        raise ReleaseCheckError(
            f"plaintext HTTP returned {response.status_code} instead of refusing or redirecting"
        )
    location = response.headers.get("location", "")
    if not location.startswith(origin):
        raise ReleaseCheckError("plaintext HTTP did not redirect to the checked HTTPS origin")
    return "redirected"


def _metric_integer(metrics: str, name: str) -> int:
    values: list[str] = []
    for raw_line in metrics.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) == 2 and fields[0] == name:
            values.append(fields[1])
    if len(values) != 1:
        raise ReleaseCheckError(f"metrics must contain exactly one {name} sample")
    try:
        value = Decimal(values[0])
    except InvalidOperation as exc:
        raise ReleaseCheckError(f"metric {name} is not numeric") from exc
    if not value.is_finite() or value < 0 or value != value.to_integral_value():
        raise ReleaseCheckError(f"metric {name} must be a nonnegative integer")
    return int(value)


def _assert_budget_metrics(
    metrics: str,
    *,
    expected_trial_enabled: bool,
    expected_trial_max_users: int,
    expected_trial_grant_microusd: int,
    expected_trial_budget_microusd: int,
    expected_openrouter_enabled: bool,
    expected_openrouter_budget_microusd: int,
) -> dict[str, int]:
    values = {
        name: _metric_integer(metrics, name)
        for name in (
            "abda_trial_enabled",
            "abda_trial_max_users",
            "abda_trial_grant_microusd",
            "abda_trial_budget_microusd",
            "abda_trial_activations",
            "abda_trial_allocated_microusd",
            "abda_trial_spent_microusd",
            "abda_trial_reserved_microusd",
            "abda_openrouter_enabled",
            "abda_openrouter_budget_microusd",
            "abda_openrouter_spent_microusd",
            "abda_openrouter_reserved_microusd",
            "abda_trial_uncertain_charged_reservations",
            "abda_trial_uncertain_charged_microusd",
            "abda_openrouter_uncertain_charged_reservations",
            "abda_openrouter_uncertain_charged_microusd",
        )
    }
    if values["abda_trial_enabled"] != int(expected_trial_enabled):
        raise ReleaseCheckError(
            "the trial enabled state does not match the release expectation"
        )
    if values["abda_trial_max_users"] != expected_trial_max_users:
        raise ReleaseCheckError(
            "the trial user cap does not match the release expectation"
        )
    if values["abda_trial_grant_microusd"] != expected_trial_grant_microusd:
        raise ReleaseCheckError(
            "the trial grant does not match the release expectation"
        )
    if values["abda_trial_budget_microusd"] != expected_trial_budget_microusd:
        raise ReleaseCheckError(
            "the trial budget does not match the release expectation"
        )
    activations = values["abda_trial_activations"]
    allocated = values["abda_trial_allocated_microusd"]
    trial_spent = values["abda_trial_spent_microusd"]
    trial_reserved = values["abda_trial_reserved_microusd"]
    if activations > expected_trial_max_users:
        raise ReleaseCheckError("trial activations exceed the configured user cap")
    if allocated != activations * expected_trial_grant_microusd:
        raise ReleaseCheckError("trial allocation does not match activations and grant size")
    if trial_spent + trial_reserved > allocated:
        raise ReleaseCheckError("trial spending and reservations exceed allocation")
    if trial_reserved:
        raise ReleaseCheckError("trial reservations are not idle during the release check")

    openrouter_enabled = values["abda_openrouter_enabled"]
    if openrouter_enabled != int(expected_openrouter_enabled):
        raise ReleaseCheckError(
            "the OpenRouter enabled state does not match the release expectation"
        )
    openrouter_budget = values["abda_openrouter_budget_microusd"]
    openrouter_spent = values["abda_openrouter_spent_microusd"]
    openrouter_reserved = values["abda_openrouter_reserved_microusd"]
    if openrouter_budget != expected_openrouter_budget_microusd:
        raise ReleaseCheckError(
            "the OpenRouter budget does not match the release expectation"
        )
    if openrouter_spent + openrouter_reserved > openrouter_budget:
        raise ReleaseCheckError("OpenRouter spending and reservations exceed its budget")
    if openrouter_reserved:
        raise ReleaseCheckError(
            "OpenRouter reservations are not idle during the release check"
        )
    return {
        "trial_enabled": values["abda_trial_enabled"],
        "trial_max_users": values["abda_trial_max_users"],
        "trial_grant_microusd": values["abda_trial_grant_microusd"],
        "trial_budget_microusd": values["abda_trial_budget_microusd"],
        "trial_activations": activations,
        "trial_allocated_microusd": allocated,
        "trial_spent_microusd": trial_spent,
        "trial_uncertain_charged_reservations": values[
            "abda_trial_uncertain_charged_reservations"
        ],
        "trial_uncertain_charged_microusd": values[
            "abda_trial_uncertain_charged_microusd"
        ],
        "openrouter_enabled": openrouter_enabled,
        "openrouter_budget_microusd": openrouter_budget,
        "openrouter_spent_microusd": openrouter_spent,
        "openrouter_uncertain_charged_reservations": values[
            "abda_openrouter_uncertain_charged_reservations"
        ],
        "openrouter_uncertain_charged_microusd": values[
            "abda_openrouter_uncertain_charged_microusd"
        ],
    }


def _assert_database_pool_metrics(metrics: str) -> dict[str, int]:
    capacity = _metric_integer(metrics, "abda_database_pool_capacity")
    checked_out = _metric_integer(metrics, "abda_database_pool_checked_out")
    if capacity != _DATABASE_POOL_CAPACITY:
        raise ReleaseCheckError(
            "the database pool capacity does not match the B1ms release budget"
        )
    if checked_out > capacity:
        raise ReleaseCheckError("database pool occupancy exceeds its capacity")
    return {"capacity": capacity, "checked_out": checked_out}


def check_public_release(
    origin: str,
    *,
    metrics_token: str | None,
    expected_profiles: Sequence[str] = ("balanced",),
    expected_trial_enabled: bool = True,
    expected_trial_max_users: int = _TRIAL_MAX_USERS,
    expected_trial_grant_microusd: int = _TRIAL_GRANT_MICROUSD,
    expected_trial_budget_microusd: int = _TRIAL_BUDGET_MICROUSD,
    expected_openrouter_enabled: bool = True,
    expected_openrouter_budget_microusd: int = 500_000_000,
    check_plain_http: bool = True,
    transport: httpx.BaseTransport | None = None,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    """Check one deployed origin and return a sanitized evidence record."""
    normalized_origin = _normalize_origin(origin)
    if metrics_token is None or len(metrics_token) < 32:
        raise ReleaseCheckError(
            "a metrics token of at least 32 characters is required through the selected environment variable"
        )
    if not 0 <= expected_openrouter_budget_microusd <= 1_000_000_000:
        raise ReleaseCheckError(
            "the expected OpenRouter budget must be between $0 and $1,000"
        )
    if not 0 <= expected_trial_max_users <= _TRIAL_MAX_USERS:
        raise ReleaseCheckError("the expected trial user cap must be between 0 and 100")
    if expected_trial_grant_microusd != _TRIAL_GRANT_MICROUSD:
        raise ReleaseCheckError("the expected trial grant must remain $5.00")
    if not 0 <= expected_trial_budget_microusd <= _TRIAL_BUDGET_MICROUSD:
        raise ReleaseCheckError("the expected trial budget must be between $0 and $500")
    if (
        expected_trial_max_users * expected_trial_grant_microusd
        > expected_trial_budget_microusd
    ):
        raise ReleaseCheckError(
            "the expected trial user cap and grant exceed the expected trial budget"
        )

    with httpx.Client(
        follow_redirects=False,
        timeout=timeout_seconds,
        transport=transport,
        headers={"User-Agent": "ABDA-NL-release-check/1"},
    ) as client:
        live = _json_object(
            _request(
                client,
                "GET",
                f"{normalized_origin}/health/live",
                expected_status=200,
            ),
            "/health/live",
        )
        if live != {"status": "ok"}:
            raise ReleaseCheckError("/health/live did not report status ok")

        ready = _json_object(
            _request(
                client,
                "GET",
                f"{normalized_origin}/health/ready",
                expected_status=200,
            ),
            "/health/ready",
        )
        if ready != {"status": "ready"}:
            raise ReleaseCheckError("/health/ready did not report status ready")

        root = _request(client, "GET", normalized_origin + "/", expected_status=200)
        if not root.headers.get("content-type", "").startswith("text/html"):
            raise ReleaseCheckError("the root response is not HTML")
        _assert_security_headers(root)

        for policy_path in ("/privacy.html", "/terms.html"):
            policy = _request(
                client,
                "GET",
                normalized_origin + policy_path,
                expected_status=200,
            )
            if not policy.headers.get("content-type", "").startswith("text/html"):
                raise ReleaseCheckError(f"{policy_path} is not HTML")

        config = _json_object(
            _request(
                client,
                "GET",
                f"{normalized_origin}/config",
                expected_status=200,
            ),
            "/config",
        )
        config_evidence = _assert_public_config(config, expected_profiles)

        unauthorized_metrics = _request(
            client,
            "GET",
            f"{normalized_origin}/internal/metrics",
            expected_status=401,
        )
        if unauthorized_metrics.headers.get("www-authenticate", "").lower() != "bearer":
            raise ReleaseCheckError("unauthorized metrics response lacks a Bearer challenge")
        metrics = _request(
            client,
            "GET",
            f"{normalized_origin}/internal/metrics",
            expected_status=200,
            headers={"Authorization": f"Bearer {metrics_token}"},
        )
        missing_metrics = sorted(name for name in _REQUIRED_METRICS if name not in metrics.text)
        if missing_metrics:
            raise ReleaseCheckError(
                f"authorized metrics response is missing {', '.join(missing_metrics)}"
            )
        budget_evidence = _assert_budget_metrics(
            metrics.text,
            expected_trial_enabled=expected_trial_enabled,
            expected_trial_max_users=expected_trial_max_users,
            expected_trial_grant_microusd=expected_trial_grant_microusd,
            expected_trial_budget_microusd=expected_trial_budget_microusd,
            expected_openrouter_enabled=expected_openrouter_enabled,
            expected_openrouter_budget_microusd=expected_openrouter_budget_microusd,
        )
        database_pool_evidence = _assert_database_pool_metrics(metrics.text)

        http_behavior = (
            _assert_plain_http_redirects_or_refuses(client, normalized_origin)
            if check_plain_http
            else "not_checked"
        )

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "origin": normalized_origin,
        "checks": {
            "https_certificate": "verified",
            "plain_http": http_behavior,
            "liveness": "passed",
            "readiness": "passed",
            "policy_pages": "passed",
            "security_headers": "passed",
            "config_exposure": "passed",
            "metrics_authentication": "passed",
            "budget_metrics": "passed",
            "database_pool": "passed",
        },
        "config": config_evidence,
        "budgets": budget_evidence,
        "database_pool": database_pool_evidence,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check the external safety and readiness of an ABDA-NL release"
    )
    parser.add_argument("origin", help="deployed HTTPS origin without a path")
    parser.add_argument(
        "--metrics-token-env",
        default="ABDA_METRICS_TOKEN",
        help="environment variable containing the metrics bearer token",
    )
    parser.add_argument(
        "--expected-profile",
        action="append",
        dest="expected_profiles",
        help="expected public funded profile ID, repeat for multiple profiles",
    )
    parser.add_argument(
        "--expected-trial-enabled",
        choices=("true", "false"),
        default="true",
        help="expected funded-trial activation state",
    )
    parser.add_argument(
        "--expected-trial-max-users",
        type=int,
        default=_TRIAL_MAX_USERS,
        help="expected funded-trial user cap",
    )
    parser.add_argument(
        "--expected-trial-budget-microusd",
        type=int,
        default=_TRIAL_BUDGET_MICROUSD,
        help="expected funded-trial total budget in microdollars",
    )
    parser.add_argument(
        "--expected-openrouter-enabled",
        choices=("true", "false"),
        default="true",
        help="expected OpenRouter outage-fallback state",
    )
    parser.add_argument(
        "--expected-openrouter-budget-microusd",
        type=int,
        default=500_000_000,
        help="expected owner-funded OpenRouter hard limit in microdollars",
    )
    parser.add_argument(
        "--skip-plain-http",
        action="store_true",
        help="skip the plaintext HTTP refusal or redirect check",
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    metrics_token = os.getenv(args.metrics_token_env)
    try:
        evidence = check_public_release(
            args.origin,
            metrics_token=metrics_token,
            expected_profiles=args.expected_profiles or ("balanced",),
            expected_trial_enabled=args.expected_trial_enabled == "true",
            expected_trial_max_users=args.expected_trial_max_users,
            expected_trial_budget_microusd=args.expected_trial_budget_microusd,
            expected_openrouter_enabled=args.expected_openrouter_enabled == "true",
            expected_openrouter_budget_microusd=(
                args.expected_openrouter_budget_microusd
            ),
            check_plain_http=not args.skip_plain_http,
            timeout_seconds=args.timeout,
        )
    except ReleaseCheckError as exc:
        print(f"release check failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
