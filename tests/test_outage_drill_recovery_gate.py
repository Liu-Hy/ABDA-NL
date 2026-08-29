"""Contracts for the read-only Gate 7 marker-failure recovery audit."""

from __future__ import annotations

import json
from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate7-marker-failure-recovery.sh"


def _run_function(function: str, *arguments: Path | str) -> subprocess.CompletedProcess[str]:
    quoted = " ".join(shlex.quote(str(argument)) for argument in arguments)
    return subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {shlex.quote(str(GATE))}; "
                f"abda_recovery_set_constants; {function} {quoted}"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _metrics(*, trial_spent: int = 60_732, openrouter_spent: int = 106) -> str:
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
            "abda_openrouter_enabled 0",
            "abda_openrouter_budget_microusd 500000000",
            f"abda_openrouter_spent_microusd {openrouter_spent}",
            "abda_openrouter_reserved_microusd 0",
            "abda_openrouter_uncertain_charged_reservations 0",
            "abda_openrouter_uncertain_charged_microusd 0",
        )
    )


def test_recovery_gate_is_executable_and_has_valid_bash_syntax():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)


def test_recovery_gate_is_read_only_and_pinned_to_the_failed_call():
    source = GATE.read_text(encoding="utf-8")
    for expected in (
        "448510936c69d485cf9b4e834adea69becf6b114",
        "11861402c8fa3fd677848f94155e29065ebafd9a4a76b03e41b1cf48312e5c58",
        "abda-nl-stg-web--rc-4485109",
        "ABDA_RECOVERY_TRIAL_SPENT_BEFORE='60626'",
        "EXISTING_GATE7_CALL_LEDGER_RECOVERY_VERIFIED",
    ):
        assert expected in source
    for forbidden in (
        "az containerapp exec",
        "az containerapp update",
        "az containerapp secret set",
        "az containerapp job start",
        "az deployment group create",
        "OPENROUTER_API_KEY",
        "--execute",
        "set -x",
    ):
        assert forbidden not in source
    assert "set +x" in source
    assert "for command_name in az curl python3 tee" in source
    assert source.index("protected ledger recovery audit") < source.index(
        "public model contract diagnostic"
    )
    assert "The ledger recovery remains valid" in source


def test_recovery_gate_verifies_equal_positive_ledger_deltas(tmp_path: Path):
    metrics = tmp_path / "metrics.txt"
    metrics.write_text(_metrics(), encoding="utf-8")
    accepted = _run_function("abda_recovery_validate_metrics", metrics)
    assert accepted.returncode == 0, accepted.stderr
    assert "settled_cost_microusd: 106" in accepted.stdout
    assert "openrouter_enabled_restored: true" in accepted.stdout

    metrics.write_text(_metrics(trial_spent=60_733), encoding="utf-8")
    rejected = _run_function("abda_recovery_validate_metrics", metrics)
    assert rejected.returncode != 0
    assert "ledger deltas differ" in rejected.stderr


def test_recovery_gate_verifies_mandatory_reasoning_metadata(tmp_path: Path):
    metadata = tmp_path / "models.json"
    metadata.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "id": "google/gemini-3.7-flash",
                        "reasoning": {
                            "mandatory": True,
                            "default_enabled": True,
                            "default_effort": "medium",
                        },
                        "supported_parameters": ["max_tokens", "reasoning"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    accepted = _run_function("abda_recovery_validate_model_metadata", metadata)
    assert accepted.returncode == 0, accepted.stderr
    assert "reasoning_mandatory: true" in accepted.stdout

    value = json.loads(metadata.read_text(encoding="utf-8"))
    value["data"][0]["reasoning"]["mandatory"] = False
    metadata.write_text(json.dumps(value), encoding="utf-8")
    rejected = _run_function("abda_recovery_validate_model_metadata", metadata)
    assert rejected.returncode != 0
    assert "reasoning contract changed" in rejected.stderr
