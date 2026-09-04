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
        "7cc17be94cc5e63c1a02ee77fafe97dde19f6f6c",
        "gate20-rate-limit-retention-image.sh",
        "f7f064f665563d7d4e1d517173bf85fd20e20aece5dd789364654d5f44b62a0c",
        "gate21-rate-limit-retention-audit.sh",
        "fd46ad2db4aadf392833a1eec563842d1519439253461785b1e5b02c0d7b9746",
        "gate22-rate-limit-retention-rollback.sh",
        "d85311b982ba7d78823ae4ddba7e5083f188e88a1fcf227b1e57f4437bd6f3d6",
        "gate23-rate-limit-retention-promotion.sh",
        "b3d0cb1fbbf3d7739717eb773a9b69e319ddc68ed9637ac34934c478e7bed352",
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
