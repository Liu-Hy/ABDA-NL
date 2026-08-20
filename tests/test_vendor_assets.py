"""Integrity checks for browser libraries committed with the demo."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


VENDOR_ROOT = Path(__file__).resolve().parents[1] / "app" / "static" / "vendor"


def test_vendored_assets_match_manifest_and_include_licenses():
    manifest = json.loads((VENDOR_ROOT / "manifest.json").read_text())
    assert manifest["schema_version"] == 1
    for filename, metadata in manifest["assets"].items():
        payload = (VENDOR_ROOT / filename).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == metadata["sha256"]
        for license_name in metadata["license_files"]:
            license_path = VENDOR_ROOT / license_name
            assert license_path.is_file()
            assert license_path.read_text().strip()
