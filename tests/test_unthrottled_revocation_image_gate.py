"""Contracts for the image-only unthrottled credential revocation gate."""

from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate11-unthrottled-revocation-image.sh"
SHARED_GATE = ROOT / "deploy" / "azure" / "gate10-mcp-command-image.sh"


def test_unthrottled_revocation_gate_is_pinned_and_narrow():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)
    source = GATE.read_text(encoding="utf-8")

    for expected in (
        "0b2a2aad93427dfec65c11def7f6434ed1c9abfb",
        "2df0bf98401adb6f72d1b930d83ab68bd2466de756b0bead3864f3d41d30b9d0",
        "ffea9cff567b8694cc556aa4ba91a67e8ab5001cffc3f54c97f2aaaf6a2b4593",
        "abda-nl-stg-web--mcp-c55aa0d",
        "abda-nl-stg-web--revoke-0b2a2aa",
        "DEPLOY_ABDA_UNTHROTTLED_REVOCATION",
        "UNTHROTTLED_CREDENTIAL_REVOCATION_DEPLOYED_BROWSER_TEST_REQUIRED",
    ):
        assert expected in source
    assert "gate10-mcp-command-image.sh" in source
    assert "az " not in source
    assert "curl " not in source
    assert "read -r -s" not in source
    assert "\u2013" not in source and "\u2014" not in source


def test_shared_image_gate_supports_exact_wrapper_overrides():
    source = SHARED_GATE.read_text(encoding="utf-8")
    for expected in (
        '"${ABDA_MCP_IMAGE_SOURCE_COMMIT:-',
        '"${ABDA_MCP_IMAGE_NEW_IMAGE_SHA256:-',
        '"${ABDA_MCP_IMAGE_CONFIRMATION:-',
        '"${ABDA_MCP_IMAGE_RESULT:-',
        '"$ABDA_MCP_IMAGE_CONFIRMATION"',
        '"$ABDA_MCP_IMAGE_RESULT"',
    ):
        assert expected in source

    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {GATE}; "
                "printf '%s\\n' "
                '"$ABDA_MCP_IMAGE_SOURCE_COMMIT" '
                '"$ABDA_MCP_IMAGE_NEW_IMAGE_SHA256" '
                '"$ABDA_MCP_IMAGE_CONFIRMATION" "$ABDA_MCP_IMAGE_RESULT"'
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.splitlines() == [
        "0b2a2aad93427dfec65c11def7f6434ed1c9abfb",
        "ffea9cff567b8694cc556aa4ba91a67e8ab5001cffc3f54c97f2aaaf6a2b4593",
        "DEPLOY_ABDA_UNTHROTTLED_REVOCATION",
        "UNTHROTTLED_CREDENTIAL_REVOCATION_DEPLOYED_BROWSER_TEST_REQUIRED",
    ]
