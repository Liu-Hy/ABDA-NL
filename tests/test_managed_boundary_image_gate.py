"""Contracts for the managed-service boundary image gate."""

from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate18-managed-boundary-image.sh"


def test_managed_boundary_image_gate_is_pinned_and_narrow():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)
    source = GATE.read_text(encoding="utf-8")

    for expected in (
        "b873112040dbfe645683d1b5e7d9adb122173ed2",
        "78481da1f49f9b049509eafc61da1c95d55ac42e425c4ab1dbb04d700971b55d",
        "567ec34602e1b5ab1e1a9b01864f2a67219910dc3080300bc108eb33d569856c",
        "abda-nl-stg-web--release-3faf6eb",
        "abda-nl-stg-web--secure-b873112",
        "DEPLOY_ABDA_MANAGED_BOUNDARY",
        "MANAGED_BOUNDARY_IMAGE_DEPLOYED_CAPACITY_SMOKE_REQUIRED",
        "1bfebc7b9d8a76bf01332205260778aa1e9bd409377f1a8bb50e211d63c9379f",
        "1eb9fd852a306de9ab00d6412491426bb0cd78c9",
    ):
        assert expected in source
    assert "gate10-mcp-command-image.sh" in source
    assert "az " not in source
    assert "read -r -s" not in source
    assert "\N{EN DASH}" not in source and "\N{EM DASH}" not in source


def test_managed_boundary_check_cannot_create_a_scenario():
    source = GATE.read_text(encoding="utf-8")
    assert '"save_as_id":"popov_v_hayashi"' in source
    assert '"overwrite":false' in source
    assert "save_status\" == '403'" in source
    assert "filesystem saves are disabled; save this work as a private project" in source
    assert "rejected_without_mutation" in source
    assert '"overwrite":true' not in source


def test_managed_boundary_wrapper_sets_exact_shared_gate_values():
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
        "b873112040dbfe645683d1b5e7d9adb122173ed2",
        "78481da1f49f9b049509eafc61da1c95d55ac42e425c4ab1dbb04d700971b55d",
        "567ec34602e1b5ab1e1a9b01864f2a67219910dc3080300bc108eb33d569856c",
        "abda-nl-stg-web--release-3faf6eb",
        "abda-nl-stg-web--secure-b873112",
        "DEPLOY_ABDA_MANAGED_BOUNDARY",
    ]
