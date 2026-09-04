"""Contracts for the rate-limit retention observability audit wrapper."""

from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate21-rate-limit-retention-audit.sh"


def _settings(stage: str) -> list[str]:
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {GATE}; abda_audit_set_constants {stage}; "
                "printf '%s\\n' "
                '"$ABDA_AUDIT_SOURCE_COMMIT" '
                '"$ABDA_AUDIT_IMAGE_SHA256" '
                '"$ABDA_AUDIT_RELEASE_STAGE" '
                '"$ABDA_AUDIT_REVISION" '
                '"$ABDA_TRIAL_MAX_USERS" '
                '"$ABDA_TRIAL_BUDGET_MICROUSD" '
                '"$ABDA_OPENROUTER_ENABLED" '
                '"$ABDA_AUDIT_RESULT"'
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()


def test_rate_limit_retention_audit_is_pinned_and_read_only():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)
    source = GATE.read_text(encoding="utf-8")

    for expected in (
        "084817fcefdcbee36e223ff6932d6c344618e1c3",
        "ef13b298df3eea1f1a52cd6f546d1c3f81cbc67cf73486b916bb2938f48b56b3",
        "59db2e3f304fcd8dfc7fadad87c25d68dbe45b0e17440b9a7277467e24bf7857",
        "830302fc1bf30bf0f00c457fdfe8bc190b3562fe",
        "gate9-observability-audit.sh",
        "SERVICE_INTEGRITY_RELEASE_AND_OBSERVABILITY_AUDIT_VERIFIED",
        "FINAL_PUBLIC_RELEASE_AND_OBSERVABILITY_AUDIT_VERIFIED",
    ):
        assert expected in source
    assert "az " not in source
    assert "read -r" not in source
    assert "\N{EN DASH}" not in source and "\N{EM DASH}" not in source


def test_rate_limit_retention_pilot_audit_settings_are_exact():
    assert _settings("--pilot") == [
        "084817fcefdcbee36e223ff6932d6c344618e1c3",
        "ef13b298df3eea1f1a52cd6f546d1c3f81cbc67cf73486b916bb2938f48b56b3",
        "suspension-pilot",
        "abda-nl-stg-web--suspend-084817f",
        "10",
        "50000000",
        "false",
        "SERVICE_INTEGRITY_RELEASE_AND_OBSERVABILITY_AUDIT_VERIFIED",
    ]


def test_rate_limit_retention_public_audit_settings_are_exact():
    assert _settings("--public") == [
        "084817fcefdcbee36e223ff6932d6c344618e1c3",
        "ef13b298df3eea1f1a52cd6f546d1c3f81cbc67cf73486b916bb2938f48b56b3",
        "suspension-public",
        "abda-nl-stg-web--public-100-084817f",
        "100",
        "500000000",
        "true",
        "FINAL_PUBLIC_RELEASE_AND_OBSERVABILITY_AUDIT_VERIFIED",
    ]
