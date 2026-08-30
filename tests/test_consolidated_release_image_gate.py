"""Contracts for the consolidated release-candidate image gate."""

from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate15-consolidated-release-image.sh"


def test_consolidated_release_image_gate_is_pinned_and_narrow():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)
    source = GATE.read_text(encoding="utf-8")

    for expected in (
        "3faf6ebd94c4dcb69fa36cb1aba481db15a9f973",
        "ffea9cff567b8694cc556aa4ba91a67e8ab5001cffc3f54c97f2aaaf6a2b4593",
        "78481da1f49f9b049509eafc61da1c95d55ac42e425c4ab1dbb04d700971b55d",
        "abda-nl-stg-web--revoke-0b2a2aa",
        "abda-nl-stg-web--release-3faf6eb",
        "DEPLOY_ABDA_CONSOLIDATED_RELEASE",
        "CONSOLIDATED_RELEASE_IMAGE_DEPLOYED_AUTOMATED_ACCEPTANCE_REQUIRED",
        "1bfebc7b9d8a76bf01332205260778aa1e9bd409377f1a8bb50e211d63c9379f",
        "1eb9fd852a306de9ab00d6412491426bb0cd78c9",
    ):
        assert expected in source
    assert "gate10-mcp-command-image.sh" in source
    assert "az " not in source
    assert source.count("\n  curl ") == 1
    assert "raw.githubusercontent.com/Liu-Hy/ABDA-NL" in source
    assert "read -r -s" not in source
    assert "\N{EN DASH}" not in source and "\N{EM DASH}" not in source


def test_consolidated_release_wrapper_sets_exact_shared_gate_values():
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {GATE}; "
                "printf '%s\\n' "
                '"$ABDA_MCP_IMAGE_SOURCE_COMMIT" '
                '"$ABDA_MCP_IMAGE_NEW_IMAGE_SHA256" '
                '"$ABDA_MCP_IMAGE_TARGET_REVISION" '
                '"$ABDA_MCP_IMAGE_CONFIRMATION"'
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.splitlines() == [
        "3faf6ebd94c4dcb69fa36cb1aba481db15a9f973",
        "78481da1f49f9b049509eafc61da1c95d55ac42e425c4ab1dbb04d700971b55d",
        "abda-nl-stg-web--release-3faf6eb",
        "DEPLOY_ABDA_CONSOLIDATED_RELEASE",
    ]
