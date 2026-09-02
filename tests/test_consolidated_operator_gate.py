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
        "9835f8068614532a7be20fdde7049245cf415bd6",
        "gate18-managed-boundary-image.sh",
        "gate9-observability-audit.sh",
        "gate10-byok-browser-acceptance.sh",
        "gate11-privacy-acceptance.sh",
        "gate14_observability_alerts.py",
        "gate10-rollback-rehearsal.sh",
        "gate12-public-budget-promotion.sh",
        "e9bcbc6a54867ee37d7849c1d35cedc8a7b345bf946f612413211b78594d24af",
        "27b923a061135fb29fbd9e2481a66f54e483b2f65c68ee63aab8331f76764a2d",
        "e372c39b3141957da6ab4aa39bd3936eb9000f18899d204952e02b29e74a7844",
        "31571966b1f1bc589dc7f1f050e62c3bd99afef4a07f6c9df5a78d13b12091cd",
        "b2fe0ab9433583e7c5d2ff6fa5a1ea0fee37aa51ba3435d4bd00e5d9c5003c05",
        "e816ea15b771c38f42055655b7ed8b1bf4f9cbc8edc167d74c0ebf06dce859b3",
        "43ef8ad7955a4916415cdb645661e00aa67edbe05df9b6f4211afe45fc29df73",
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
