"""Contracts for the immutable post-privacy operator helper."""

from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "post-privacy-operator-gate.sh"


def test_post_privacy_helper_is_pinned_and_ordered():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)
    source = GATE.read_text(encoding="utf-8")

    for expected in (
        "9ccbab542a93898c02223b94dfc9e0e1d4eacb7e",
        "gate20-rate-limit-retention-image.sh",
        "e99f824b5921d792405d0aa8a74e7d3763dc80c0ae8c6c45b8c8c2174d239f27",
        "gate21-rate-limit-retention-audit.sh",
        "4295903c77e4af6cd12b2ef891ffc63d51727a5643d33228fdffbc087f4fa748",
        "gate22-rate-limit-retention-rollback.sh",
        "35ac2c7c0805080613245e311e4fe39ae6618bec244cf22d348e52de06525f59",
        "gate23-rate-limit-retention-promotion.sh",
        "aa41db0844ea0792dcb5a195d276e15f820c02d37220a80c842399ca0f1e8a7a",
        "gate16_public_hostname_boundary.py",
        "bb528ff37e21a0b4219e5ced7f3f1e5ffbd2ea2324f2cdcda1fdc6e010f94d7c",
        "ALL_POST_PRIVACY_OPERATOR_GATES_VERIFIED",
    ):
        assert expected in source
    assert "run-all" in source
    assert "privacy" not in _phase_loop(source)
    assert "\N{EN DASH}" not in source and "\N{EM DASH}" not in source


def _phase_loop(source: str) -> str:
    marker = "for gate in "
    start = source.index(marker) + len(marker)
    return source[start : source.index("; do", start)]


def test_post_privacy_helper_dispatches_exact_audit_modes():
    source = GATE.read_text(encoding="utf-8")
    assert "gate_arguments=(--pilot)" in source
    assert "gate_arguments=(--public)" in source
    assert 'for gate in deploy audit hostname rollback promote final-audit' in source


def test_post_privacy_helper_help_requires_no_network():
    result = subprocess.run(
        ["bash", str(GATE), "help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Phases, in required order:" in result.stdout
    assert "deploy" in result.stdout
    assert "final-audit" in result.stdout
    assert "no run-all phase" in result.stdout
