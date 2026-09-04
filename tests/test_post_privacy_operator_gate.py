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
        "6d418dd09ae0ff495ddf25566a3d740cec94306b",
        "gate20-rate-limit-retention-image.sh",
        "ee612a3298b93fb9bc330436bf9a4fd2e2fa0ffe5732716d5c2c01c2093c421b",
        "gate21-rate-limit-retention-audit.sh",
        "35f757bb3dfcbbc4e079b8a4b89656322f5471d72d6e41965e6dbe3fce57927c",
        "gate22-rate-limit-retention-rollback.sh",
        "14140ca96cfec5d67bd0a3abdd20563c32b79f555eb8a9b7a21be8e4757490f4",
        "gate23-rate-limit-retention-promotion.sh",
        "f270c1ab02e188f559cbd8ea0efbdc8c9c0652a86cbb6dd12a1572fbae6f9619",
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
