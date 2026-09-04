"""Contracts for the rate-limit retention rollback wrapper."""

from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate22-rate-limit-retention-rollback.sh"


def test_rate_limit_retention_rollback_is_pinned_and_narrow():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)
    source = GATE.read_text(encoding="utf-8")

    for expected in (
        "e008067e3dc9c96862cf4f75228bdf0250848665",
        "b20cfe100f94d22e5734badaf5ec4e52e3445b72fcdc1879339f7b905109eb29",
        "51702e175bd14d4cb54075808f839d173d561324",
        "a0b3ba24aff06ecf461f86547131d86451c541e306a7ecfc278f280fcef5c0bc",
        "abda-nl-stg-web--retain-e008067",
        "abda-nl-stg-web--rollback-51702e1",
        "abda-nl-stg-web--restore-e008067",
        "COMPATIBLE_RETENTION_IMAGE_ROLLBACK_AND_RESTORE_VERIFIED",
        "a1a41ff17038894a255c4175b06c44422b6887e09f47c36f5b66a91845039273",
        "830302fc1bf30bf0f00c457fdfe8bc190b3562fe",
    ):
        assert expected in source
    assert "gate10-rollback-rehearsal.sh" in source
    assert "az " not in source
    assert "read -r" not in source
    assert "\N{EN DASH}" not in source and "\N{EM DASH}" not in source


def test_rate_limit_retention_rollback_requires_disclosure_after_restore():
    source = GATE.read_text(encoding="utf-8")
    assert "abda_retention_rollback_base_public_acceptance" in source
    assert "require_retention" in source
    assert (
        "Expired records are removed at application startup or by an hourly cleanup "
        "triggered by subsequent traffic."
    ) in source
    assert "Last updated September 4, 2026" in source
    assert "rate_limit_retention_disclosure: verified" in source


def test_rate_limit_retention_rollback_sets_exact_shared_gate_values():
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {GATE}; "
                "printf '%s\\n' "
                '"$ABDA_CURRENT_SOURCE_COMMIT" '
                '"$ABDA_CURRENT_IMAGE_SHA256" '
                '"$ABDA_ROLLBACK_SOURCE_COMMIT" '
                '"$ABDA_ROLLBACK_IMAGE_SHA256" '
                '"$ABDA_CURRENT_REVISION" '
                '"$ABDA_ROLLBACK_REVISION" '
                '"$ABDA_RESTORE_REVISION"'
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.splitlines() == [
        "e008067e3dc9c96862cf4f75228bdf0250848665",
        "b20cfe100f94d22e5734badaf5ec4e52e3445b72fcdc1879339f7b905109eb29",
        "51702e175bd14d4cb54075808f839d173d561324",
        "a0b3ba24aff06ecf461f86547131d86451c541e306a7ecfc278f280fcef5c0bc",
        "abda-nl-stg-web--retain-e008067",
        "abda-nl-stg-web--rollback-51702e1",
        "abda-nl-stg-web--restore-e008067",
    ]
