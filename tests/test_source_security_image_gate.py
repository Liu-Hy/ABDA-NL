"""Contracts for the source-security image deployment gate."""

from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate19-source-security-image.sh"


def test_source_security_image_gate_is_pinned_and_narrow():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)
    source = GATE.read_text(encoding="utf-8")

    for expected in (
        "c173dd5983ba209b17c585c0c82aeb33c2e49028",
        "567ec34602e1b5ab1e1a9b01864f2a67219910dc3080300bc108eb33d569856c",
        "ecf7531064fe6f86d3d647e9f0239bfbe5e082d71c5fcdd5e7e7fb91e9b32a64",
        "abda-nl-stg-web--secure-b873112",
        "abda-nl-stg-web--harden-c173dd5",
        "DEPLOY_ABDA_SOURCE_SECURITY_IMAGE",
        "SOURCE_SECURITY_IMAGE_DEPLOYED_AUDIT_REQUIRED",
        "1bfebc7b9d8a76bf01332205260778aa1e9bd409377f1a8bb50e211d63c9379f",
        "1eb9fd852a306de9ab00d6412491426bb0cd78c9",
    ):
        assert expected in source
    assert "gate10-mcp-command-image.sh" in source
    assert "az " not in source
    assert "read -r -s" not in source
    assert "\N{EN DASH}" not in source and "\N{EM DASH}" not in source


def test_source_security_check_cannot_create_a_scenario():
    source = GATE.read_text(encoding="utf-8")
    assert '"save_as_id":"popov_v_hayashi"' in source
    assert '"overwrite":false' in source
    assert "save_status\" == '403'" in source
    assert "filesystem saves are disabled; save this work as a private project" in source
    assert "rejected_without_mutation" in source
    assert '"overwrite":true' not in source


def test_source_security_wrapper_sets_exact_shared_gate_values():
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
        "c173dd5983ba209b17c585c0c82aeb33c2e49028",
        "567ec34602e1b5ab1e1a9b01864f2a67219910dc3080300bc108eb33d569856c",
        "ecf7531064fe6f86d3d647e9f0239bfbe5e082d71c5fcdd5e7e7fb91e9b32a64",
        "abda-nl-stg-web--secure-b873112",
        "abda-nl-stg-web--harden-c173dd5",
        "DEPLOY_ABDA_SOURCE_SECURITY_IMAGE",
    ]
