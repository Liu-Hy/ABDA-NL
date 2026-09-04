"""Contracts for the rate-limit retention image deployment gate."""

from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate20-rate-limit-retention-image.sh"


def test_rate_limit_retention_image_gate_is_pinned_and_narrow():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)
    source = GATE.read_text(encoding="utf-8")

    for expected in (
        "e008067e3dc9c96862cf4f75228bdf0250848665",
        "a0b3ba24aff06ecf461f86547131d86451c541e306a7ecfc278f280fcef5c0bc",
        "b20cfe100f94d22e5734badaf5ec4e52e3445b72fcdc1879339f7b905109eb29",
        "abda-nl-stg-web--harden-51702e1",
        "abda-nl-stg-web--retain-e008067",
        "PRIVACY_DELETION_VERIFIED_DEPLOY_ABDA_RETENTION_IMAGE",
        "RATE_LIMIT_RETENTION_IMAGE_DEPLOYED_AUDIT_REQUIRED",
        "1bfebc7b9d8a76bf01332205260778aa1e9bd409377f1a8bb50e211d63c9379f",
        "1eb9fd852a306de9ab00d6412491426bb0cd78c9",
    ):
        assert expected in source
    assert "gate10-mcp-command-image.sh" in source
    assert "az " not in source
    assert "read -r -s" not in source
    assert "\N{EN DASH}" not in source and "\N{EM DASH}" not in source


def test_rate_limit_retention_check_preserves_prior_managed_boundaries():
    source = GATE.read_text(encoding="utf-8")
    assert '"save_as_id":"popov_v_hayashi"' in source
    assert '"overwrite":false' in source
    assert "save_status\" == '403'" in source
    assert "filesystem saves are disabled; save this work as a private project" in source
    assert "rejected_without_mutation" in source
    assert '"overwrite":true' not in source
    assert (
        "Expired records are removed at application startup or by an hourly cleanup "
        "triggered by subsequent traffic."
    ) in source
    assert "Last updated September 4, 2026" in source


def test_rate_limit_retention_wrapper_sets_exact_shared_gate_values():
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {GATE}; "
                "printf '%s\\n' "
                '"$ABDA_MCP_IMAGE_SOURCE_COMMIT" '
                '"$ABDA_MCP_IMAGE_OLD_IMAGE_SHA256" '
                '"$ABDA_MCP_IMAGE_NEW_IMAGE_SHA256" '
                '"$ABDA_MCP_IMAGE_OLD_REVISION" '
                '"$ABDA_MCP_IMAGE_TARGET_REVISION" '
                '"$ABDA_MCP_IMAGE_CONFIRMATION"'
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.splitlines() == [
        "e008067e3dc9c96862cf4f75228bdf0250848665",
        "a0b3ba24aff06ecf461f86547131d86451c541e306a7ecfc278f280fcef5c0bc",
        "b20cfe100f94d22e5734badaf5ec4e52e3445b72fcdc1879339f7b905109eb29",
        "abda-nl-stg-web--harden-51702e1",
        "abda-nl-stg-web--retain-e008067",
        "PRIVACY_DELETION_VERIFIED_DEPLOY_ABDA_RETENTION_IMAGE",
    ]
