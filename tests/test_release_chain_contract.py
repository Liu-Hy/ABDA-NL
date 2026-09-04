"""Cross-file contracts for the active public-service release sequence."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
AZURE = ROOT / "deploy" / "azure"
DEPLOY = AZURE / "gate19-source-security-image.sh"
AUDIT = AZURE / "gate9-observability-audit.sh"
PRIVACY = AZURE / "gate11-privacy-acceptance.sh"
ROLLBACK = AZURE / "gate10-rollback-rehearsal.sh"
PROMOTION = AZURE / "gate12-public-budget-promotion.sh"
OPERATOR_HELPER = AZURE / "consolidated-operator-gate.sh"
RETENTION_DEPLOY = AZURE / "gate20-rate-limit-retention-image.sh"
RETENTION_AUDIT = AZURE / "gate21-rate-limit-retention-audit.sh"
RETENTION_ROLLBACK = AZURE / "gate22-rate-limit-retention-rollback.sh"
RETENTION_PROMOTION = AZURE / "gate23-rate-limit-retention-promotion.sh"
POST_PRIVACY_HELPER = AZURE / "post-privacy-operator-gate.sh"


def _assignment(path: Path, name: str) -> str:
    pattern = re.compile(rf"^{re.escape(name)}='([^']*)'$", re.MULTILINE)
    matches = pattern.findall(path.read_text(encoding="utf-8"))
    assert len(matches) == 1, f"expected one {name} assignment in {path.name}"
    return matches[0]


def _assigned_values(path: Path, name: str) -> set[str]:
    pattern = re.compile(rf"^\s*{re.escape(name)}='([^']*)'$", re.MULTILINE)
    return set(pattern.findall(path.read_text(encoding="utf-8")))


def test_active_release_gates_form_one_consistent_image_chain():
    source_commit = _assignment(DEPLOY, "ABDA_MCP_IMAGE_SOURCE_COMMIT")
    image_digest = _assignment(DEPLOY, "ABDA_MCP_IMAGE_NEW_IMAGE_SHA256")
    pilot_revision = _assignment(DEPLOY, "ABDA_MCP_IMAGE_TARGET_REVISION")

    assert _assignment(AUDIT, "ABDA_AUDIT_SOURCE_COMMIT") == source_commit
    assert _assignment(AUDIT, "ABDA_AUDIT_IMAGE_SHA256") == image_digest
    audit_revisions = _assigned_values(AUDIT, "ABDA_AUDIT_REVISION")
    assert pilot_revision in audit_revisions

    assert _assignment(PRIVACY, "ABDA_PRIVACY_APPLICATION_SOURCE_COMMIT") == source_commit
    assert _assignment(PRIVACY, "ABDA_PRIVACY_IMAGE_SHA256") == image_digest
    assert _assignment(PRIVACY, "ABDA_PRIVACY_EXPECTED_REVISION") == pilot_revision

    assert _assignment(ROLLBACK, "ABDA_CURRENT_SOURCE_COMMIT") == source_commit
    assert _assignment(ROLLBACK, "ABDA_CURRENT_IMAGE_SHA256") == image_digest
    assert _assignment(ROLLBACK, "ABDA_CURRENT_REVISION") == pilot_revision
    restored_revision = _assignment(ROLLBACK, "ABDA_RESTORE_REVISION")

    assert _assignment(PROMOTION, "ABDA_PROMOTION_APPLICATION_SOURCE_COMMIT") == source_commit
    assert _assignment(PROMOTION, "ABDA_PROMOTION_IMAGE_SHA256") == image_digest
    assert _assignment(PROMOTION, "ABDA_PROMOTION_OLD_REVISION") == restored_revision
    public_revision = _assignment(PROMOTION, "ABDA_PROMOTION_TARGET_REVISION")
    assert public_revision in audit_revisions


def test_active_privacy_runbook_names_the_exact_deploy_target():
    privacy_runbook = (
        ROOT / "docs" / "operations" / "privacy-requests.md"
    ).read_text(encoding="utf-8")
    pilot_revision = _assignment(DEPLOY, "ABDA_MCP_IMAGE_TARGET_REVISION")
    image_digest = _assignment(DEPLOY, "ABDA_MCP_IMAGE_NEW_IMAGE_SHA256")

    assert f"`{pilot_revision}`" in privacy_runbook
    assert f"`sha256:{image_digest}`" in privacy_runbook


def test_post_privacy_chain_bridges_from_the_privacy_accepted_image():
    old_source = _assignment(DEPLOY, "ABDA_MCP_IMAGE_SOURCE_COMMIT")
    old_digest = _assignment(DEPLOY, "ABDA_MCP_IMAGE_NEW_IMAGE_SHA256")
    old_revision = _assignment(DEPLOY, "ABDA_MCP_IMAGE_TARGET_REVISION")
    assert _assignment(PRIVACY, "ABDA_PRIVACY_APPLICATION_SOURCE_COMMIT") == old_source
    assert _assignment(PRIVACY, "ABDA_PRIVACY_IMAGE_SHA256") == old_digest
    assert _assignment(PRIVACY, "ABDA_PRIVACY_EXPECTED_REVISION") == old_revision

    assert _assignment(RETENTION_DEPLOY, "ABDA_MCP_IMAGE_OLD_IMAGE_SHA256") == old_digest
    assert _assignment(RETENTION_DEPLOY, "ABDA_MCP_IMAGE_OLD_REVISION") == old_revision
    source = _assignment(RETENTION_DEPLOY, "ABDA_MCP_IMAGE_SOURCE_COMMIT")
    digest = _assignment(RETENTION_DEPLOY, "ABDA_MCP_IMAGE_NEW_IMAGE_SHA256")
    pilot_revision = _assignment(RETENTION_DEPLOY, "ABDA_MCP_IMAGE_TARGET_REVISION")

    assert _assignment(RETENTION_AUDIT, "ABDA_AUDIT_SOURCE_COMMIT") == source
    assert _assignment(RETENTION_AUDIT, "ABDA_AUDIT_IMAGE_SHA256") == digest
    assert pilot_revision in _assigned_values(RETENTION_AUDIT, "ABDA_AUDIT_REVISION")

    assert _assignment(RETENTION_ROLLBACK, "ABDA_CURRENT_SOURCE_COMMIT") == source
    assert _assignment(RETENTION_ROLLBACK, "ABDA_CURRENT_IMAGE_SHA256") == digest
    assert _assignment(RETENTION_ROLLBACK, "ABDA_CURRENT_REVISION") == pilot_revision
    assert _assignment(RETENTION_ROLLBACK, "ABDA_ROLLBACK_SOURCE_COMMIT") == old_source
    assert _assignment(RETENTION_ROLLBACK, "ABDA_ROLLBACK_IMAGE_SHA256") == old_digest

    restored_revision = _assignment(RETENTION_ROLLBACK, "ABDA_RESTORE_REVISION")
    assert (
        _assignment(RETENTION_PROMOTION, "ABDA_PROMOTION_APPLICATION_SOURCE_COMMIT")
        == source
    )
    assert _assignment(RETENTION_PROMOTION, "ABDA_PROMOTION_IMAGE_SHA256") == digest
    assert (
        _assignment(RETENTION_PROMOTION, "ABDA_PROMOTION_OLD_REVISION")
        == restored_revision
    )
    public_revision = _assignment(
        RETENTION_PROMOTION, "ABDA_PROMOTION_TARGET_REVISION"
    )
    assert public_revision in _assigned_values(RETENTION_AUDIT, "ABDA_AUDIT_REVISION")


def test_operator_runbook_keeps_privacy_before_rollback_and_promotion():
    runbook = (
        ROOT / "docs" / "operations" / "final-operator-batch.md"
    ).read_text(encoding="utf-8")

    cursor = 0
    for command in (
        'bash "$p" deploy',
        'bash "$p" audit',
        'bash "$p" privacy',
        'bash "$q" deploy',
        'bash "$q" audit',
        'bash "$p" hostname',
        'bash "$q" rollback',
        'bash "$q" promote',
        'bash "$q" final-audit',
    ):
        cursor = runbook.index(command, cursor) + len(command)


def test_operator_runbook_pins_the_exact_current_helper():
    runbook = (
        ROOT / "docs" / "operations" / "final-operator-batch.md"
    ).read_text(encoding="utf-8")
    helper_sha256 = hashlib.sha256(OPERATOR_HELPER.read_bytes()).hexdigest()

    assert "4d62e92c443480d1a72530d3dcc4022a0e5adbfd" in runbook
    assert helper_sha256 == "41e992c4e5a1d98ec1c48975ab61ea66750af4281051b7f0810adc142879eb7c"
    assert f"s='{helper_sha256}'" in runbook

    post_privacy_sha256 = hashlib.sha256(POST_PRIVACY_HELPER.read_bytes()).hexdigest()
    assert "3d23869304474c0119456ca53f76b9d2e34c58a5" in runbook
    assert (
        post_privacy_sha256
        == "c7cdf2bfcfe25f3752d16b60f86c4f5c5628ff96cfda221affa06a78784bbc3e"
    )
    assert f"s2='{post_privacy_sha256}'" in runbook


def test_operator_runbook_names_the_queued_retention_artifact():
    runbook = (
        ROOT / "docs" / "operations" / "final-operator-batch.md"
    ).read_text(encoding="utf-8")
    source = _assignment(RETENTION_DEPLOY, "ABDA_MCP_IMAGE_SOURCE_COMMIT")
    digest = _assignment(RETENTION_DEPLOY, "ABDA_MCP_IMAGE_NEW_IMAGE_SHA256")
    revision = _assignment(RETENTION_DEPLOY, "ABDA_MCP_IMAGE_TARGET_REVISION")

    assert f"`{source}`" in runbook
    assert f"`sha256:{digest}`" in runbook
    assert f"`{revision}`" in runbook
    assert "PRIVACY_DELETION_VERIFIED_DEPLOY_ABDA_SERVICE_IMAGE" in runbook


def test_shareable_privacy_gate_receipt_has_no_email_derived_fingerprint():
    gate = PRIVACY.read_text(encoding="utf-8")
    runbook = (
        ROOT / "docs" / "operations" / "final-operator-batch.md"
    ).read_text(encoding="utf-8")

    assert 'print(f"account_fingerprint:' not in gate
    assert "shareable Gate receipts omit both the email address" in runbook
