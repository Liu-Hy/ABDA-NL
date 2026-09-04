"""Contracts for the rate-limit retention public promotion wrapper."""

from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate23-rate-limit-retention-promotion.sh"


def test_rate_limit_retention_promotion_is_pinned_and_narrow():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)
    source = GATE.read_text(encoding="utf-8")

    for expected in (
        "e008067e3dc9c96862cf4f75228bdf0250848665",
        "b20cfe100f94d22e5734badaf5ec4e52e3445b72fcdc1879339f7b905109eb29",
        "abda-nl-stg-web--restore-e008067",
        "abda-nl-stg-web--public-100-e008067",
        "712f0206fc330249e15d0d59793ad9a6e5c317a6fc752b6f2dccfa384c2bb04d",
        "830302fc1bf30bf0f00c457fdfe8bc190b3562fe",
    ):
        assert expected in source
    assert "gate12-public-budget-promotion.sh" in source
    assert "az " not in source
    assert "read -r" not in source
    assert "\N{EN DASH}" not in source and "\N{EM DASH}" not in source


def test_rate_limit_retention_promotion_sets_exact_shared_gate_values():
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {GATE}; "
                "printf '%s\\n' "
                '"$ABDA_PROMOTION_APPLICATION_SOURCE_COMMIT" '
                '"$ABDA_PROMOTION_IMAGE_SHA256" '
                '"$ABDA_PROMOTION_OLD_REVISION" '
                '"$ABDA_PROMOTION_TARGET_REVISION"'
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.splitlines() == [
        "e008067e3dc9c96862cf4f75228bdf0250848665",
        "b20cfe100f94d22e5734badaf5ec4e52e3445b72fcdc1879339f7b905109eb29",
        "abda-nl-stg-web--restore-e008067",
        "abda-nl-stg-web--public-100-e008067",
    ]
