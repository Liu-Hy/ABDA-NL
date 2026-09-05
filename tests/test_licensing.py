"""Distribution notices and SPDX metadata must agree across artifact types."""

import hashlib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_original_license_texts_are_preserved_byte_for_byte():
    # GPL bytes from upstream ABDA at 6e7a45c; MIT bytes from ABDA-NL before
    # the GPL distribution correction. Neither legal text may be paraphrased.
    expected = {
        "LICENSE": "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986",
        "LICENSES/ABDA-NL-MIT.txt":
            "56582fa54ed6605931f1adbc6ae1bf450aa3067a51c04263d990c8003fc7daba",
    }
    for name, digest in expected.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest


def test_distribution_metadata_and_notices_use_gpl_version_three_only():
    project = (ROOT / "pyproject.toml").read_text()
    dockerfile = (ROOT / "Dockerfile").read_text()
    citation = yaml.safe_load((ROOT / "CITATION.cff").read_text())
    publish = (ROOT / ".github/workflows/publish-service-image.yml").read_text()
    assert 'license = "GPL-3.0-only"' in project
    assert 'license-files = ["LICENSE", "THIRD_PARTY_NOTICES.md", "LICENSES/*.txt"]' in project
    assert citation["license"] == "GPL-3.0-only"
    assert 'org.opencontainers.image.licenses="GPL-3.0-only"' in dockerfile
    assert "org.opencontainers.image.licenses=GPL-3.0-only" in publish
    assert "COPY --chown=abda:abda THIRD_PARTY_NOTICES.md ./" in dockerfile
    assert "COPY --chown=abda:abda LICENSES ./LICENSES" in dockerfile
    assert "archive/${ABDA_IMAGE_COMMIT}.tar.gz" in publish


def test_built_artifact_checks_cover_original_mit_and_attribution():
    for name in ("ci.yml", "publish-service-image.yml"):
        workflow = (ROOT / ".github/workflows" / name).read_text()
        assert "for ABDA_NOTICE in THIRD_PARTY_NOTICES.md LICENSES/ABDA-NL-MIT.txt" in workflow
        assert 'cat "/srv/abda/$ABDA_NOTICE" | cmp --silent "$ABDA_NOTICE" -' in workflow
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    assert 'metadata["License-Expression"] != "GPL-3.0-only"' in ci
    assert 'wheel.read(license_root + notice) != Path(notice).read_bytes()' in ci


def test_engine_attribution_identifies_import_and_dated_modifications():
    notice = (ROOT / "THIRD_PARTY_NOTICES.md").read_text()
    assert "6e7a45c40150fbf6bb5377271bf238d8fcd32463" in notice
    assert "90b7338da35d8a33b36ad4c877f9a61c99c61d7c" in notice
    assert "Martin Caminada" in notice
    assert "Sören Uebis" in notice
    for name in (
        "ABDAShell.py", "ArgumentationSystem/Argument.py",
        "ArgumentationSystem/ArgumentBuilder.py", "ArgumentationSystem/ArgumentationGraph.py",
        "GraphVisualization/GraphConvert.py", "KnowledgeBase/DefeasibleRule.py",
        "KnowledgeBase/StrictRule.py",
    ):
        assert name in notice
        source = (ROOT / "app/abda" / name).read_text()
        assert source.startswith("# SPDX-License-Identifier: GPL-3.0-only\n")
        assert "Modification notice added 2026-09-05" in source
