"""New distribution labels must not be confused with historical MIT labels."""

import json
from pathlib import Path
import re
import shlex
import subprocess

import pytest


AZURE = Path(__file__).resolve().parents[1] / "deploy/azure"


def _value(script, variable):
    return re.search(rf"^{variable}='([^']+)'$", script.read_text(), re.MULTILINE)[1]


@pytest.mark.parametrize("gate, target", [
    ("gate20-rate-limit-retention-image.sh", "current"),
    ("gate22-rate-limit-retention-rollback.sh", "current"),
    ("gate22-rate-limit-retention-rollback.sh", "rollback"),
])
@pytest.mark.parametrize("license_id", ["GPL-3.0-only", "MIT", "GPL-3.0-or-later", ""])
def test_gate_requires_the_exact_license_for_each_pinned_artifact(tmp_path, gate, target, license_id):
    script = AZURE / gate
    if "gate20" in gate:
        commit = _value(script, "ABDA_MCP_IMAGE_SOURCE_COMMIT")
        digest = _value(script, "ABDA_MCP_IMAGE_NEW_IMAGE_SHA256")
        function = "abda_mcp_image_validate_registry_image"
        extra_args = []
    else:
        prefix = "ABDA_CURRENT" if target == "current" else "ABDA_ROLLBACK"
        commit = _value(script, prefix + "_SOURCE_COMMIT")
        digest = _value(script, prefix + "_IMAGE_SHA256")
        function = "abda_rollback_validate_registry_image"
        extra_args = [digest, commit]
    headers = tmp_path / "headers"
    manifest = tmp_path / "manifest.json"
    config = tmp_path / "config.json"
    headers.write_text(f"docker-content-digest: sha256:{digest}\n")
    manifest.write_text(json.dumps({"schemaVersion": 2, "config": {"digest": "sha256:" + "a" * 64}}))
    config.write_text(json.dumps({"config": {"Labels": {
        "org.opencontainers.image.source": "https://github.com/Liu-Hy/ABDA-NL",
        "org.opencontainers.image.revision": commit,
        "org.opencontainers.image.licenses": license_id,
    }}}))
    args = " ".join(shlex.quote(str(x)) for x in [headers, manifest, config, *extra_args])
    result = subprocess.run(
        ["bash", "-c", f"source {shlex.quote(str(script))}; {function} {args}"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    expected = "GPL-3.0-only" if target == "current" else "MIT"
    assert (result.returncode == 0) == (license_id == expected), result.stderr
