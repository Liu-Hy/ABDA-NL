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
        "54937e1dd716cfa0e3dd7ca3eb6f93a11bde472c",
        "gate20-rate-limit-retention-image.sh",
        "782bfff583f9c3f9770c7e5af22bc47dea9f0b32e89d302776f2549f3669b4b3",
        "gate21-rate-limit-retention-audit.sh",
        "88f291c01ef4c8e6184aaa0392e6552f38409662beb7e7a9c90a05b101d65bcf",
        "gate22-rate-limit-retention-rollback.sh",
        "f1c78216e10eb4c2a2426795b2f40e04446430a2cc0c7255121d65bc7a93ab0e",
        "gate23-rate-limit-retention-promotion.sh",
        "e9489a5fe7d6203a36ccf42d264777baf6d856ff7a52af8415f0f9973f3a31cb",
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
