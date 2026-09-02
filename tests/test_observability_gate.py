"""Contracts for the read-only Azure release and observability audit."""

from __future__ import annotations

import json
from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate9-observability-audit.sh"
APP = "abda-nl-stg-web"
REVISION = "abda-nl-stg-web--harden-c173dd5"
PUBLIC_REVISION = "abda-nl-stg-web--public-100-c173dd5"
IMAGE = (
    "ghcr.io/liu-hy/abda-nl@sha256:"
    "ecf7531064fe6f86d3d647e9f0239bfbe5e082d71c5fcdd5e7e7fb91e9b32a64"
)


def _run_function(function: str, *arguments: Path | str) -> subprocess.CompletedProcess[str]:
    quoted = " ".join(shlex.quote(str(argument)) for argument in arguments)
    return subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {shlex.quote(str(GATE))}; "
                f"abda_audit_set_constants; {function} {quoted}"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _run_public_function(
    function: str, *arguments: Path | str
) -> subprocess.CompletedProcess[str]:
    quoted = " ".join(shlex.quote(str(argument)) for argument in arguments)
    return subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {shlex.quote(str(GATE))}; "
                f"abda_audit_set_constants --public; {function} {quoted}"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _environment(*, public: bool = False) -> list[dict[str, str]]:
    values = {
        "ABDA_ENVIRONMENT": "staging",
        "ABDA_AUTH_MODE": "oidc",
        "ABDA_PUBLIC_BASE_URL": "https://demo.abda-nl.org",
        "ABDA_TRIAL_ENABLED": "True",
        "ABDA_TRIAL_MAX_USERS": "100" if public else "10",
        "ABDA_TRIAL_GRANT_MICROUSD": "5000000",
        "ABDA_TRIAL_BUDGET_MICROUSD": "500000000" if public else "50000000",
        "ABDA_LLM_ALLOW_BYOK": "1",
        "ABDA_LLM_REQUIRE_AUTH": "1",
        "ABDA_OPENROUTER_FAILOVER_ENABLED": "True" if public else "False",
        "ABDA_OPENROUTER_BUDGET_MICROUSD": "500000000",
    }
    environment = [{"name": name, "value": value} for name, value in values.items()]
    for name, secret_ref in {
        "ABDA_DATABASE_URL": "database-url",
        "ABDA_SESSION_SECRET": "session-secret",
        "ABDA_MCP_TOKEN_PEPPER": "mcp-token-pepper",
        "ABDA_METRICS_TOKEN": "metrics-token",
        "ABDA_OIDC_CLIENT_SECRET": "oidc-client-secret",
        "AZURE_OPENAI_API_KEY": "foundry-api-key",
        "OPENROUTER_API_KEY": "openrouter-api-key",
    }.items():
        environment.append({"name": name, "secretRef": secret_ref})
    return environment


def _app(*, public: bool = False) -> dict:
    return {
        "name": APP,
        "properties": {
            "provisioningState": "Succeeded",
            "runningStatus": "Running",
            "latestRevisionName": PUBLIC_REVISION if public else REVISION,
            "latestReadyRevisionName": PUBLIC_REVISION if public else REVISION,
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
                "scale": {"minReplicas": 1, "maxReplicas": 3},
                "containers": [
                    {
                        "name": "web",
                        "image": IMAGE,
                        "env": _environment(public=public),
                    }
                ],
            },
        },
    }


def _release_receipt(*, public: bool = False) -> dict:
    return {
        "origin": "https://demo.abda-nl.org",
        "checks": {
            "https_certificate": "verified",
            "plain_http": "redirected",
            "liveness": "passed",
            "readiness": "passed",
            "policy_pages": "passed",
            "security_headers": "passed",
            "config_exposure": "passed",
            "metrics_authentication": "passed",
            "budget_metrics": "passed",
            "database_pool": "passed",
        },
        "config": {
            "default_profile": "balanced",
            "funded_profiles": ["balanced"],
            "byok_model_counts": {
                "anthropic": 1,
                "google": 1,
                "openai": 1,
                "openrouter": 1,
            },
        },
        "budgets": {
            "trial_enabled": 1,
            "trial_max_users": 100 if public else 10,
            "trial_grant_microusd": 5_000_000,
            "trial_budget_microusd": 500_000_000 if public else 50_000_000,
            "trial_activations": 1,
            "trial_allocated_microusd": 5_000_000,
            "trial_spent_microusd": 60_775,
            "openrouter_enabled": 1 if public else 0,
            "openrouter_budget_microusd": 500_000_000,
            "openrouter_spent_microusd": 149,
        },
        "database_pool": {"capacity": 5, "checked_out": 1},
    }


def test_observability_gate_is_executable_valid_and_read_only():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)
    source = GATE.read_text(encoding="utf-8")
    for expected in (
        REVISION,
        IMAGE.split("sha256:", 1)[1],
        "ContainerAppConsoleLogs_CL",
        "ContainerAppSystemLogs_CL",
        '"timespan": "P2D"',
        "https://api.loganalytics.azure.com/v1/workspaces/$workspace_id/query",
        "--max-time 75",
        "timeout --foreground --signal=INT --kill-after=5s 120s",
        "--expected-trial-max-users $ABDA_TRIAL_MAX_USERS",
        "--expected-openrouter-enabled $ABDA_OPENROUTER_ENABLED",
        "private_identifier_field_like",
        "log_ingestion_attempt:",
        "RELEASE_AND_OBSERVABILITY_AUDIT_VERIFIED",
        "FINAL_PUBLIC_RELEASE_AND_OBSERVABILITY_AUDIT_VERIFIED",
    ):
        assert expected in source
    for forbidden in (
        "az deployment group create",
        "az containerapp update",
        "az containerapp revision restart",
        "az containerapp secret set",
        "az containerapp secret list",
        "az monitor diagnostic-settings create",
        "az monitor metrics alert create",
        "az monitor log-analytics query",
        "--show-values",
        "read -r -s",
    ):
        assert forbidden not in source
    assert "set +x" in source
    assert "unset HISTFILE" in source
    assert "set -x" not in source


def test_observability_gate_converts_direct_log_api_response(tmp_path: Path):
    response = tmp_path / "response.json"
    summary = tmp_path / "summary.json"
    columns = [
        "total_logs",
        "console_logs",
        "system_logs",
        "current_revision_logs",
        "current_revision_request_logs",
        "request_logs",
        "request_query_markers",
        "email_like",
        "bearer_like",
        "share_fragment_like",
        "oidc_code_like",
        "provider_key_like",
        "private_identifier_field_like",
    ]
    values = [500, 350, 150, 300, 200, 250, 0, 0, 0, 0, 0, 0, 0]
    _write_json(
        response,
        {
            "tables": [
                {
                    "name": "PrimaryResult",
                    "columns": [
                        {"name": name, "type": "long"} for name in columns
                    ],
                    "rows": [values],
                }
            ]
        },
    )
    result = _run_function("abda_audit_convert_log_api_response", response, summary)
    assert result.returncode == 0, result.stderr
    assert json.loads(summary.read_text(encoding="utf-8")) == [
        dict(zip(columns, values, strict=True))
    ]

    value = json.loads(response.read_text(encoding="utf-8"))
    value["tables"][0]["rows"] = []
    _write_json(response, value)
    summary.unlink()
    result = _run_function("abda_audit_convert_log_api_response", response, summary)
    assert result.returncode != 0
    assert "result shape" in result.stderr


def test_observability_gate_keeps_log_api_token_in_mode_600_file(tmp_path: Path):
    token = tmp_path / "token.json"
    config = tmp_path / "curl-config"
    _write_json(token, {"accessToken": "a" * 40 + "." + "b" * 40})
    result = _run_function("abda_audit_write_log_api_auth", token, config)
    assert result.returncode == 0, result.stderr
    assert not token.exists()
    assert config.stat().st_mode & 0o777 == 0o600
    assert config.read_text(encoding="utf-8").startswith(
        'header = "Authorization: Bearer '
    )

    token = tmp_path / "invalid-token.json"
    _write_json(token, {"accessToken": "unsafe\nheader"})
    result = _run_function("abda_audit_write_log_api_auth", token, tmp_path / "bad")
    assert result.returncode != 0
    assert not (tmp_path / "bad").exists()


def test_observability_gate_accepts_exact_current_application(tmp_path: Path):
    path = tmp_path / "app.json"
    _write_json(path, _app())
    result = _run_function("abda_audit_validate_app", path)
    assert result.returncode == 0, result.stderr

    changed = _app()
    environment = changed["properties"]["template"]["containers"][0]["env"]
    next(item for item in environment if item["name"] == "ABDA_TRIAL_MAX_USERS")[
        "value"
    ] = "100"
    _write_json(path, changed)
    result = _run_function("abda_audit_validate_app", path)
    assert result.returncode != 0
    assert "ABDA_TRIAL_MAX_USERS" in result.stderr


def test_observability_gate_accepts_only_exact_promoted_application(
    tmp_path: Path,
):
    path = tmp_path / "public-app.json"
    _write_json(path, _app(public=True))
    result = _run_public_function("abda_audit_validate_app", path)
    assert result.returncode == 0, result.stderr

    changed = _app(public=True)
    environment = changed["properties"]["template"]["containers"][0]["env"]
    next(
        item
        for item in environment
        if item["name"] == "ABDA_OPENROUTER_FAILOVER_ENABLED"
    )["value"] = "False"
    _write_json(path, changed)
    result = _run_public_function("abda_audit_validate_app", path)
    assert result.returncode != 0
    assert "ABDA_OPENROUTER_FAILOVER_ENABLED" in result.stderr


def test_observability_gate_validates_workspace_destination(tmp_path: Path):
    workspace = tmp_path / "workspace.json"
    environment = tmp_path / "environment.json"
    _write_json(
        workspace,
        {
            "name": "abda-nl-stg-logs-bgjhpbgw",
            "retentionInDays": 30,
            "customerId": "ABCD-1234",
            "sku": {"name": "PerGB2018"},
        },
    )
    _write_json(
        environment,
        {
            "name": "abda-nl-stg-environment",
            "properties": {
                "appLogsConfiguration": {
                    "destination": "log-analytics",
                    "logAnalyticsConfiguration": {"customerId": "abcd-1234"},
                }
            },
        },
    )
    result = _run_function(
        "abda_audit_validate_logging_configuration", workspace, environment
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "abcd-1234"

    value = json.loads(workspace.read_text(encoding="utf-8"))
    value["retentionInDays"] = 7
    _write_json(workspace, value)
    result = _run_function(
        "abda_audit_validate_logging_configuration", workspace, environment
    )
    assert result.returncode != 0
    assert "retention" in result.stderr


def test_observability_gate_accepts_counts_and_rejects_secret_indicators(tmp_path: Path):
    summary = tmp_path / "logs.json"
    values = {
        "total_logs": 500,
        "console_logs": 350,
        "system_logs": 150,
        "current_revision_logs": 300,
        "current_revision_request_logs": 200,
        "request_logs": 250,
        "request_query_markers": 0,
        "email_like": 0,
        "bearer_like": 0,
        "share_fragment_like": 0,
        "oidc_code_like": 0,
        "provider_key_like": 0,
        "private_identifier_field_like": 0,
    }
    _write_json(summary, [values])
    result = _run_function("abda_audit_validate_log_summary", summary)
    assert result.returncode == 0, result.stderr
    assert "request_logs: 250" in result.stdout
    readiness = _run_function("abda_audit_current_revision_logs_ready", summary)
    assert readiness.returncode == 0, readiness.stderr

    values["share_fragment_like"] = 1
    _write_json(summary, [values])
    result = _run_function("abda_audit_validate_log_summary", summary)
    assert result.returncode != 0
    assert "share_fragment_like" in result.stderr
    assert "#share=" not in result.stderr

    values["share_fragment_like"] = 0
    values["private_identifier_field_like"] = 1
    _write_json(summary, [values])
    result = _run_function("abda_audit_validate_log_summary", summary)
    assert result.returncode != 0
    assert "private_identifier_field_like" in result.stderr
    assert "project_id" not in result.stderr

    values["private_identifier_field_like"] = 0
    values["current_revision_request_logs"] = 0
    _write_json(summary, [values])
    result = _run_function("abda_audit_validate_log_summary", summary)
    assert result.returncode != 0
    assert "current_revision_request_logs" in result.stderr
    readiness = _run_function("abda_audit_current_revision_logs_ready", summary)
    assert readiness.returncode != 0


def test_observability_gate_extracts_and_validates_sanitized_release_receipt(
    tmp_path: Path,
):
    raw = tmp_path / "container.log"
    receipt = tmp_path / "receipt.json"
    raw.write_text(
        "INFO: Connecting to the container\n"
        + json.dumps(_release_receipt(), indent=2)
        + "\nINFO: received success status from cluster\n",
        encoding="utf-8",
    )
    result = _run_function("abda_audit_extract_release_check", raw, receipt)
    assert result.returncode == 0, result.stderr
    result = _run_function("abda_audit_validate_release_check", receipt)
    assert result.returncode == 0, result.stderr
    assert "release_check: passed" in result.stdout
    assert "openrouter_spent_microusd: 149" in result.stdout

    value = json.loads(receipt.read_text(encoding="utf-8"))
    value["budgets"]["trial_max_users"] = 100
    receipt.unlink()
    _write_json(receipt, value)
    result = _run_function("abda_audit_validate_release_check", receipt)
    assert result.returncode != 0
    assert "trial_max_users" in result.stderr


def test_observability_gate_validates_promoted_release_receipt(tmp_path: Path):
    receipt = tmp_path / "public-receipt.json"
    _write_json(receipt, _release_receipt(public=True))
    result = _run_public_function("abda_audit_validate_release_check", receipt)
    assert result.returncode == 0, result.stderr
    assert "release_check: passed" in result.stdout

    value = json.loads(receipt.read_text(encoding="utf-8"))
    value["budgets"]["openrouter_enabled"] = 0
    _write_json(receipt, value)
    result = _run_public_function("abda_audit_validate_release_check", receipt)
    assert result.returncode != 0
    assert "openrouter_enabled" in result.stderr
