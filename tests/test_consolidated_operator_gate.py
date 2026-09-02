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
        "d7883de84d792b5bb93d3e744e8048cf38553a81",
        "gate19-source-security-image.sh",
        "gate9-observability-audit.sh",
        "gate10-byok-browser-acceptance.sh",
        "gate11-privacy-acceptance.sh",
        "gate16_public_hostname_boundary.py",
        "gate14_observability_alerts.py",
        "gate10-rollback-rehearsal.sh",
        "gate12-public-budget-promotion.sh",
        "56f1c612bf3c97e5d332f023cea50c05a8b411e4ab173515a80b6a683eb1cb55",
        "f67abb753fd23fd47624bad57f09c75a6355be6c805a9254e15cf45df9549dcb",
        "e372c39b3141957da6ab4aa39bd3936eb9000f18899d204952e02b29e74a7844",
        "31571966b1f1bc589dc7f1f050e62c3bd99afef4a07f6c9df5a78d13b12091cd",
        "bb528ff37e21a0b4219e5ced7f3f1e5ffbd2ea2324f2cdcda1fdc6e010f94d7c",
        "b2fe0ab9433583e7c5d2ff6fa5a1ea0fee37aa51ba3435d4bd00e5d9c5003c05",
        "c4e2f56d6172a64b22a21894fe29d94836bb3ceb8b9af54aa73fb4e705c68398",
        "a5330f5e0a452ebdbecfe7df5a9c90cd52145b602192713a9e6dc7a9a13e19ac",
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
            "hostname",
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
