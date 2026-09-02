"""Contracts for the short consolidated Cloud Shell helper."""

from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "azure" / "consolidated-operator-gate.sh"


def test_operator_helper_is_valid_pinned_and_non_mutating_itself():
    assert SCRIPT.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    source = SCRIPT.read_text(encoding="utf-8")
    for expected in (
        "d86715ec08d5a9ec10fb738a15ee956f8436f653",
        "gate15-consolidated-release-image.sh",
        "gate9-observability-audit.sh",
        "gate10-byok-browser-acceptance.sh",
        "gate11-privacy-acceptance.sh",
        "gate14_observability_alerts.py",
        "gate10-rollback-rehearsal.sh",
        "gate12-public-budget-promotion.sh",
        "final-audit",
        "gate_arguments=(--pilot)",
        "gate_arguments=(--public)",
        "ALL_CONSOLIDATED_OPERATOR_GATES_VERIFIED",
    ):
        assert expected in source
    for forbidden in (
        "az ",
        "az\n",
        "--set-env-vars",
        "deployment group create",
        "containerapp update",
        "group delete",
        "read -r -s",
    ):
        assert forbidden not in source
    assert "run-all" in source
    assert "\N{EN DASH}" not in source and "\N{EM DASH}" not in source


def test_operator_helper_help_is_local_and_lists_ordered_phases():
    result = subprocess.run(
        ["bash", str(SCRIPT), "help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    positions = [
        result.stdout.index(f"  {phase}")
        for phase in (
            "verify",
            "deploy",
            "audit",
            "byok",
            "privacy",
            "alerts",
            "rollback",
            "promote",
            "final-audit",
        )
    ]
    assert positions == sorted(positions)
    assert "no run-all phase" in result.stdout


def test_operator_helper_rejects_unknown_phase_without_network():
    result = subprocess.run(
        ["bash", str(SCRIPT), "unknown"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "Unknown phase: unknown" in result.stderr
