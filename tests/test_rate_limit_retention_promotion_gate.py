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
        "db216b83d8df6b2ea487cd8358f05e81e65f8be9",
        "614cd03d6f87b46e056d6dd736c060b8b652ae024334f9f0bb4eb50d750deac2",
        "abda-nl-stg-web--restore-db216b8",
        "abda-nl-stg-web--public-100-db216b8",
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
        "db216b83d8df6b2ea487cd8358f05e81e65f8be9",
        "614cd03d6f87b46e056d6dd736c060b8b652ae024334f9f0bb4eb50d750deac2",
        "abda-nl-stg-web--restore-db216b8",
        "abda-nl-stg-web--public-100-db216b8",
    ]
