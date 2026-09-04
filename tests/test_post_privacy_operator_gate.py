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
        "fc01896d53820b22cc1f440916e228690b6de26d",
        "gate20-rate-limit-retention-image.sh",
        "73237cbacd2e1582226bb41c8ab1fa4db252a143dea616d3777189881c92a676",
        "gate21-rate-limit-retention-audit.sh",
        "1d61dd3ca61a90789e277aa1ce2952b9dfd68cfdf34b8763c3a3edfcbff46c91",
        "gate22-rate-limit-retention-rollback.sh",
        "baccf323ab35b65979a3cf7a777d43d25b4beecad90bd7a2d413a39d81672317",
        "gate23-rate-limit-retention-promotion.sh",
        "c751bb23fafa1fb0971fdb777c1b093499b3e0fca6591cb79f67b7942618d0c6",
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
