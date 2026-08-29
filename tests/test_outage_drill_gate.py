"""Contracts for the live Azure OpenRouter outage-drill gate."""

from __future__ import annotations

import json
from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate7-openrouter-outage-drill.sh"
APP = "abda-nl-stg-web"
REVISION = "abda-nl-stg-web--rc-4485109"
IMAGE = (
    "ghcr.io/liu-hy/abda-nl@sha256:"
    "11861402c8fa3fd677848f94155e29065ebafd9a4a76b03e41b1cf48312e5c58"
)


def _run_function(function: str, *arguments: Path | str) -> subprocess.CompletedProcess[str]:
    quoted = " ".join(shlex.quote(str(argument)) for argument in arguments)
    return subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {shlex.quote(str(GATE))}; "
                f"abda_drill_set_constants; {function} {quoted}"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _app(*, failover: str = "False") -> dict:
    values = {
        "ABDA_ENVIRONMENT": "staging",
        "ABDA_PUBLIC_BASE_URL": "https://demo.abda-nl.org",
        "ABDA_TRIAL_ENABLED": "True",
        "ABDA_TRIAL_MAX_USERS": "10",
        "ABDA_TRIAL_GRANT_MICROUSD": "5000000",
        "ABDA_TRIAL_BUDGET_MICROUSD": "50000000",
        "ABDA_LLM_DEFAULT_PROFILE": "balanced",
        "ABDA_OPENROUTER_FAILOVER_ENABLED": failover,
        "ABDA_OPENROUTER_BUDGET_MICROUSD": "500000000",
    }
    environment = [{"name": name, "value": value} for name, value in values.items()]
    environment.extend(
        {"name": name, "secretRef": secret_ref}
        for name, secret_ref in {
            "ABDA_DATABASE_URL": "database-url",
            "ABDA_METRICS_TOKEN": "metrics-token",
            "OPENROUTER_API_KEY": "openrouter-api-key",
        }.items()
    )
    return {
        "name": APP,
        "properties": {
            "provisioningState": "Succeeded",
            "runningStatus": "Running",
            "latestRevisionName": REVISION,
            "latestReadyRevisionName": REVISION,
            "template": {
                "containers": [
                    {
                        "name": "web",
                        "image": IMAGE,
                        "env": environment,
                    }
                ]
            },
        },
    }


def _metrics(
    *,
    trial_spent: int = 22_387,
    openrouter_spent: int = 0,
    events: int = 1,
    openrouter_enabled: int = 0,
) -> str:
    return "\n".join(
        (
            "abda_trial_enabled 1",
            "abda_trial_max_users 10",
            "abda_trial_grant_microusd 5000000",
            "abda_trial_budget_microusd 50000000",
            "abda_trial_activations 1",
            "abda_trial_allocated_microusd 5000000",
            f"abda_trial_spent_microusd {trial_spent}",
            "abda_trial_reserved_microusd 0",
            "abda_trial_uncertain_charged_reservations 0",
            "abda_trial_uncertain_charged_microusd 0",
            f"abda_openrouter_enabled {openrouter_enabled}",
            "abda_openrouter_budget_microusd 500000000",
            f"abda_openrouter_spent_microusd {openrouter_spent}",
            "abda_openrouter_reserved_microusd 0",
            "abda_openrouter_uncertain_charged_reservations 0",
            "abda_openrouter_uncertain_charged_microusd 0",
            f"abda_llm_usage_events_total {events}",
        )
    )


def _receipt(cost: int = 106) -> dict:
    return {
        "action": "openrouter-outage-drill",
        "environment": "staging",
        "public_origin": "https://demo.abda-nl.org",
        "profile": "balanced",
        "primary_route": "cloudbank-claude-sonnet-4-6",
        "injected_primary_status": 503,
        "fallback_route": "openrouter-gemini-3.7-flash",
        "max_output_tokens": 32,
        "request_id": f"outage-drill-{'a' * 32}",
        "marker_verified": True,
        "mutated": True,
        "result": "OPENROUTER_OUTAGE_DRILL_PASSED",
        "audit": {
            "settled_cost_microusd": cost,
            "trial_recorded_cost_microusd": cost,
            "openrouter_recorded_cost_microusd": cost,
            "provider_attempt_count": 1,
            "trial_reserved_microusd": 0,
            "openrouter_reserved_microusd": 0,
            "openrouter_enabled_restored": True,
        },
    }


def test_outage_drill_gate_is_executable_and_has_valid_bash_syntax():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)


def test_outage_drill_gate_has_one_paid_exec_and_no_azure_mutation():
    source = GATE.read_text(encoding="utf-8")
    for expected in (
        "448510936c69d485cf9b4e834adea69becf6b114",
        IMAGE.split("sha256:", 1)[1],
        REVISION,
        "RUN_ABDA_GATE7_OUTAGE_DRILL",
        "RUN_STAGING_OPENROUTER_OUTAGE_DRILL",
        "CONTROLLED_OPENROUTER_OUTAGE_DRILL_VERIFIED",
    ):
        assert expected in source
    assert source.count("az containerapp exec --help") == 1
    assert source.count("\n  az containerapp exec \\\n") == 1
    assert source.count("python -m app.cli.outage_drill") == 1
    for forbidden in (
        "az containerapp update",
        "az containerapp secret set",
        "az deployment group create",
        "az containerapp job start",
        "az containerapp job create",
        "--set-env-vars",
        "set -x",
    ):
        assert forbidden not in source
    assert "set +x" in source
    assert "unset HISTFILE" in source


def test_outage_drill_gate_accepts_only_the_exact_disabled_candidate(tmp_path: Path):
    app_path = tmp_path / "app.json"
    _write_json(app_path, _app())
    accepted = _run_function("abda_drill_validate_app", app_path)
    assert accepted.returncode == 0, accepted.stderr

    _write_json(app_path, _app(failover="true"))
    rejected = _run_function("abda_drill_validate_app", app_path)
    assert rejected.returncode != 0
    assert "ABDA_OPENROUTER_FAILOVER_ENABLED" in rejected.stderr


def test_outage_drill_gate_selects_only_a_ready_web_replica(tmp_path: Path):
    replicas_path = tmp_path / "replicas.json"
    _write_json(
        replicas_path,
        [
            {
                "name": f"{REVISION}-replica",
                "properties": {
                    "runningState": "Running",
                    "containers": [{"name": "web", "ready": True, "started": True}],
                },
            }
        ],
    )
    accepted = _run_function("abda_drill_select_replica", replicas_path)
    assert accepted.returncode == 0, accepted.stderr
    assert accepted.stdout.strip() == f"{REVISION}-replica"

    value = json.loads(replicas_path.read_text(encoding="utf-8"))
    value[0]["properties"]["containers"][0]["ready"] = False
    _write_json(replicas_path, value)
    rejected = _run_function("abda_drill_select_replica", replicas_path)
    assert rejected.returncode != 0
    assert "no ready" in rejected.stderr


def test_outage_drill_gate_reconciles_receipt_and_live_metrics(tmp_path: Path):
    before_metrics = tmp_path / "before.metrics"
    after_metrics = tmp_path / "after.metrics"
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    receipt = tmp_path / "receipt.json"
    before_metrics.write_text(_metrics(), encoding="utf-8")
    after_metrics.write_text(
        _metrics(trial_spent=22_493, openrouter_spent=106, events=2),
        encoding="utf-8",
    )
    assert _run_function("abda_drill_metric_snapshot", before_metrics, before).returncode == 0
    assert _run_function("abda_drill_metric_snapshot", after_metrics, after).returncode == 0
    _write_json(receipt, _receipt())
    accepted = _run_function("abda_drill_validate_result", before, receipt, after)
    assert accepted.returncode == 0, accepted.stderr
    assert "settled_cost_microusd: 106" in accepted.stdout
    assert "openrouter_enabled_restored: true" in accepted.stdout

    broken = _receipt()
    broken["audit"]["openrouter_recorded_cost_microusd"] = 105
    _write_json(receipt, broken)
    rejected = _run_function("abda_drill_validate_result", before, receipt, after)
    assert rejected.returncode != 0
    assert "reconcile both ledgers" in rejected.stderr


def test_outage_drill_gate_extracts_one_sanitized_receipt(tmp_path: Path):
    log = tmp_path / "exec.log"
    output = tmp_path / "receipt.json"
    log.write_text(
        "INFO: Connecting to container\n"
        "Verified ABDA-NL trial account email: \n"
        + json.dumps(_receipt(), indent=2)
        + "\nINFO: Disconnecting\n",
        encoding="utf-8",
    )
    accepted = _run_function("abda_drill_extract_receipt", log, output)
    assert accepted.returncode == 0, accepted.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["marker_verified"] is True

    log.write_text(log.read_text(encoding="utf-8") + json.dumps(_receipt()), encoding="utf-8")
    output.unlink()
    rejected = _run_function("abda_drill_extract_receipt", log, output)
    assert rejected.returncode != 0
    assert "exactly one" in rejected.stderr
