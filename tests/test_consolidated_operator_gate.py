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
        "335611df6bc4b749f491320c9713cc259773ca92",
        "gate19-source-security-image.sh",
        "gate9-observability-audit.sh",
        "gate10-byok-browser-acceptance.sh",
        "gate11-privacy-acceptance.sh",
        "gate16_public_hostname_boundary.py",
        "gate14_observability_alerts.py",
        "gate10-rollback-rehearsal.sh",
        "gate12-public-budget-promotion.sh",
        "3ffb0e7a2c1f42627c45c530d6dcfb289f4afed47ed1849ca7dedffe0e00ed4e",
        "59db2e3f304fcd8dfc7fadad87c25d68dbe45b0e17440b9a7277467e24bf7857",
        "e372c39b3141957da6ab4aa39bd3936eb9000f18899d204952e02b29e74a7844",
        "f6571d299893492339ed179759ca313f81bf87b67cd50f588aa0454515635507",
        "bb528ff37e21a0b4219e5ced7f3f1e5ffbd2ea2324f2cdcda1fdc6e010f94d7c",
        "b2fe0ab9433583e7c5d2ff6fa5a1ea0fee37aa51ba3435d4bd00e5d9c5003c05",
        "a1a41ff17038894a255c4175b06c44422b6887e09f47c36f5b66a91845039273",
        "712f0206fc330249e15d0d59793ad9a6e5c317a6fc752b6f2dccfa384c2bb04d",
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
