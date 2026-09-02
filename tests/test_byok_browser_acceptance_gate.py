"""Contracts for the resumable public-browser BYOK acceptance gate."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate10-byok-browser-acceptance.sh"
EXPECTED_REVISION = "abda-nl-stg-web--secure-b873112"
EXPECTED_IMAGE = (
    "ghcr.io/liu-hy/abda-nl@sha256:"
    "567ec34602e1b5ab1e1a9b01864f2a67219910dc3080300bc108eb33d569856c"
)


def _run_function(function: str, *arguments: Path | str) -> subprocess.CompletedProcess[str]:
    quoted = " ".join(shlex.quote(str(argument)) for argument in arguments)
    return subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {shlex.quote(str(GATE))}; "
                f"abda_byok_set_constants; {function} {quoted}"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _application(*, revision: str = EXPECTED_REVISION) -> dict:
    environment = {
        "ABDA_ENVIRONMENT": "staging",
        "ABDA_AUTH_MODE": "oidc",
        "ABDA_PUBLIC_BASE_URL": "https://demo.abda-nl.org",
        "ABDA_LLM_ALLOW_BYOK": "1",
        "ABDA_LLM_REQUIRE_AUTH": "1",
        "ABDA_TRIAL_ENABLED": "True",
        "ABDA_TRIAL_MAX_USERS": "10",
        "ABDA_TRIAL_GRANT_MICROUSD": "5000000",
        "ABDA_TRIAL_BUDGET_MICROUSD": "50000000",
        "ABDA_OPENROUTER_FAILOVER_ENABLED": "False",
        "ABDA_OPENROUTER_BUDGET_MICROUSD": "500000000",
    }
    values = [{"name": name, "value": value} for name, value in environment.items()]
    values.extend(
        {"name": name, "secretRef": secret}
        for name, secret in {
            "ABDA_DATABASE_URL": "database-url",
            "ABDA_SESSION_SECRET": "session-secret",
            "ABDA_MCP_TOKEN_PEPPER": "mcp-token-pepper",
            "ABDA_METRICS_TOKEN": "metrics-token",
            "ABDA_OIDC_CLIENT_SECRET": "oidc-client-secret",
            "AZURE_OPENAI_API_KEY": "foundry-api-key",
            "OPENROUTER_API_KEY": "openrouter-api-key",
        }.items()
    )
    return {
        "name": "abda-nl-stg-web",
        "properties": {
            "provisioningState": "Succeeded",
            "runningStatus": "Running",
            "latestRevisionName": revision,
            "latestReadyRevisionName": revision,
            "configuration": {
                "activeRevisionsMode": "Single",
                "ingress": {
                    "external": True,
                    "allowInsecure": False,
                    "targetPort": 8000,
                    "customDomains": [{"name": "demo.abda-nl.org"}],
                },
            },
            "template": {
                "containers": [
                    {
                        "name": "web",
                        "image": EXPECTED_IMAGE,
                        "env": values,
                    }
                ]
            },
        },
    }


def _public_config() -> dict:
    return {
        "llm_enabled": True,
        "llm_auth_required": True,
        "byok_enabled": True,
        "byok_keys_stored": False,
        "byok_providers": [
            {"id": "anthropic", "models": []},
            {"id": "openai", "models": []},
            {"id": "google", "models": []},
            {
                "id": "openrouter",
                "models": [{"id": "gemini-3.7-flash"}],
            },
        ],
    }


def _metric_values() -> dict[str, int]:
    return {
        "abda_trial_enabled": 1,
        "abda_trial_max_users": 10,
        "abda_trial_grant_microusd": 5_000_000,
        "abda_trial_budget_microusd": 50_000_000,
        "abda_trial_activations": 1,
        "abda_trial_allocated_microusd": 5_000_000,
        "abda_trial_spent_microusd": 60_775,
        "abda_trial_reserved_microusd": 0,
        "abda_trial_uncertain_charged_reservations": 0,
        "abda_trial_uncertain_charged_microusd": 0,
        "abda_openrouter_enabled": 0,
        "abda_openrouter_budget_microusd": 500_000_000,
        "abda_openrouter_spent_microusd": 149,
        "abda_openrouter_reserved_microusd": 0,
        "abda_openrouter_uncertain_charged_reservations": 0,
        "abda_openrouter_uncertain_charged_microusd": 0,
        "abda_llm_usage_events_total": 10,
    }


def _write_metrics(path: Path, values: dict[str, int]) -> None:
    path.write_text(
        "\n".join(f"{name} {value}" for name, value in values.items()) + "\n",
        encoding="utf-8",
    )


def test_gate_is_read_only_secret_safe_resumable_and_syntactically_valid() -> None:
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)
    source = GATE.read_text(encoding="utf-8")
    for expected in (
        "LIVE_BYOK_PRIVACY_AND_ACCOUNTING_ACCEPTANCE_VERIFIED",
        EXPECTED_REVISION,
        "BYOK_OPENROUTER_CALL_CONFIRMED",
        "BYOK_RELOAD_CLEAR_CONFIRMED",
        "BYOK_SIGNOUT_CLEAR_CONFIRMED",
        "A prior baseline was found. Do not repeat a successful browser model call.",
        "provider_key_entered_in_shell: false",
        "raw_log_messages_printed: false",
        "secret_values_printed: false",
    ):
        assert expected in source
    for forbidden in (
        "az containerapp exec",
        "az containerapp ssh",
        "az containerapp update",
        "az containerapp delete",
        "az deployment",
        "az group delete",
        "read -r -s",
        "getpass.getpass",
    ):
        assert forbidden not in source
    assert "OpenRouter key only into the browser password field" in source
    assert "\N{EM DASH}" not in source and "\N{EN DASH}" not in source


def test_preflights_accept_only_the_approved_app_and_public_config(tmp_path: Path) -> None:
    valid_app = tmp_path / "app.json"
    valid_app.write_text(json.dumps(_application()), encoding="utf-8")
    result = _run_function("abda_byok_validate_app", valid_app)
    assert result.returncode == 0, result.stderr

    wrong_app = tmp_path / "wrong-app.json"
    wrong_app.write_text(
        json.dumps(_application(revision="abda-nl-stg-web--other")),
        encoding="utf-8",
    )
    result = _run_function("abda_byok_validate_app", wrong_app)
    assert result.returncode != 0
    assert "application revision changed" in result.stderr

    valid_config = tmp_path / "config.json"
    valid_config.write_text(json.dumps(_public_config()), encoding="utf-8")
    result = _run_function("abda_byok_validate_config", valid_config)
    assert result.returncode == 0, result.stderr

    invalid = _public_config()
    invalid["byok_keys_stored"] = True
    invalid_config = tmp_path / "invalid-config.json"
    invalid_config.write_text(json.dumps(invalid), encoding="utf-8")
    result = _run_function("abda_byok_validate_config", invalid_config)
    assert result.returncode != 0
    assert "storage boundary changed" in result.stderr


def test_metrics_snapshot_and_comparison_prove_independent_ledgers(tmp_path: Path) -> None:
    values = _metric_values()
    before_metrics = tmp_path / "before.metrics"
    before_snapshot = tmp_path / "before.json"
    _write_metrics(before_metrics, values)
    result = _run_function("abda_byok_metrics_snapshot", before_metrics, before_snapshot)
    assert result.returncode == 0, result.stderr

    state = tmp_path / "state.json"
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = _run_function(
        "abda_byok_create_state",
        before_snapshot,
        state,
        started_at,
    )
    assert result.returncode == 0, result.stderr
    assert state.stat().st_mode & 0o077 == 0

    after_values = dict(values)
    after_values["abda_llm_usage_events_total"] += 1
    after_metrics = tmp_path / "after.metrics"
    after_snapshot = tmp_path / "after.json"
    _write_metrics(after_metrics, after_values)
    result = _run_function("abda_byok_metrics_snapshot", after_metrics, after_snapshot)
    assert result.returncode == 0, result.stderr
    comparison = tmp_path / "comparison.txt"
    result = _run_function(
        "abda_byok_compare_metrics",
        state,
        after_snapshot,
        comparison,
    )
    assert result.returncode == 0, result.stderr
    assert "llm_usage_event_delta: 1" in comparison.read_text(encoding="utf-8")

    changed_values = dict(after_values)
    changed_values["abda_trial_spent_microusd"] += 1
    changed_metrics = tmp_path / "changed.metrics"
    changed_snapshot = tmp_path / "changed.json"
    _write_metrics(changed_metrics, changed_values)
    assert _run_function(
        "abda_byok_metrics_snapshot", changed_metrics, changed_snapshot
    ).returncode == 0
    result = _run_function(
        "abda_byok_compare_metrics",
        state,
        changed_snapshot,
        tmp_path / "changed-result.txt",
    )
    assert result.returncode != 0
    assert "abda_trial_spent_microusd" in result.stderr


def test_resume_state_records_each_irreversible_browser_checkpoint(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.json"
    metrics.write_text(json.dumps(_metric_values()), encoding="utf-8")
    state = tmp_path / "state.json"
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert _run_function(
        "abda_byok_create_state", metrics, state, started_at
    ).returncode == 0

    phase = _run_function("abda_byok_state_phase", state)
    assert phase.returncode == 0, phase.stderr
    assert phase.stdout.strip() == "awaiting_call"
    for expected, target in (
        ("awaiting_call", "call_confirmed"),
        ("call_confirmed", "reload_confirmed"),
        ("reload_confirmed", "browser_confirmed"),
    ):
        result = _run_function("abda_byok_transition_state", state, expected, target)
        assert result.returncode == 0, result.stderr
        phase = _run_function("abda_byok_state_phase", state)
        assert phase.stdout.strip() == target


def test_log_summary_requires_route_evidence_and_zero_secret_indicators(tmp_path: Path) -> None:
    valid = tmp_path / "valid.json"
    valid.write_text(
        json.dumps(
            {
                "byok_route_logs": 2,
                "provider_key_like": 0,
                "api_key_field_like": 0,
                "email_like": 0,
                "bearer_like": 0,
            }
        ),
        encoding="utf-8",
    )
    result = _run_function("abda_byok_validate_log_summary", valid)
    assert result.returncode == 0, result.stderr

    missing = tmp_path / "missing.json"
    payload = json.loads(valid.read_text(encoding="utf-8"))
    payload["byok_route_logs"] = 0
    missing.write_text(json.dumps(payload), encoding="utf-8")
    result = _run_function("abda_byok_validate_log_summary", missing)
    assert result.returncode != 0
    assert "WAITING_FOR_BYOK_LOG_INGESTION" in result.stderr

    unsafe = tmp_path / "unsafe.json"
    payload["byok_route_logs"] = 1
    payload["provider_key_like"] = 1
    unsafe.write_text(json.dumps(payload), encoding="utf-8")
    result = _run_function("abda_byok_validate_log_summary", unsafe)
    assert result.returncode != 0
    assert "unsafe entries" in result.stderr


def test_logging_preflight_accepts_real_azure_cli_workspace_shape(
    tmp_path: Path,
) -> None:
    customer_id = "7c934e73-9e5a-45da-8387-fb65442be197"
    workspace = tmp_path / "workspace.json"
    workspace.write_text(
        json.dumps(
            {
                "name": "abda-nl-stg-logs-bgjhpbgw",
                "customerId": customer_id,
                "retentionInDays": 30,
                "provisioningState": "Succeeded",
            }
        ),
        encoding="utf-8",
    )
    environment = tmp_path / "environment.json"
    environment.write_text(
        json.dumps(
            {
                "name": "abda-nl-stg-environment",
                "properties": {
                    "appLogsConfiguration": {
                        "destination": "log-analytics",
                        "logAnalyticsConfiguration": {
                            "customerId": customer_id.upper(),
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = _run_function(
        "abda_byok_validate_logging_configuration", workspace, environment
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == customer_id

    payload = json.loads(workspace.read_text(encoding="utf-8"))
    payload["retentionInDays"] = 7
    workspace.write_text(json.dumps(payload), encoding="utf-8")
    result = _run_function(
        "abda_byok_validate_logging_configuration", workspace, environment
    )
    assert result.returncode != 0
    assert "workspace boundary changed" in result.stderr
