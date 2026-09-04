"""Tests for the release container vulnerability and secret policy."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from deploy.container_security_policy import evaluate_reports


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "deploy" / "container_security_policy.py"


def _report(
    *,
    vulnerabilities: list[dict[str, str]] | None = None,
    secrets: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {"Target": "abda-nl", "Class": "os-pkgs"}
    if vulnerabilities is not None:
        result["Vulnerabilities"] = vulnerabilities
    if secrets is not None:
        result["Secrets"] = secrets
    return {
        "SchemaVersion": 2,
        "ArtifactName": "abda-nl-ci:test",
        "ArtifactType": "container_image",
        "Results": [result],
    }


def _baseline(*entries: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "accepted_unfixed_high_critical": list(entries),
    }


def test_policy_allows_unfixed_high_findings_but_blocks_fixed_high_findings():
    safe = _report(
        vulnerabilities=[
            {
                "VulnerabilityID": "CVE-UNFIXED",
                "PkgName": "base-package",
                "InstalledVersion": "1",
                "FixedVersion": "",
                "Severity": "CRITICAL",
            },
            {
                "VulnerabilityID": "CVE-MEDIUM",
                "PkgName": "library",
                "InstalledVersion": "1",
                "FixedVersion": "2",
                "Severity": "MEDIUM",
            },
        ]
    )
    secrets = _report(secrets=[])

    accepted_unfixed = frozenset(
        {("CRITICAL", "CVE-UNFIXED", "base-package", "1")}
    )
    safe_summary = evaluate_reports(safe, secrets, accepted_unfixed)

    assert safe_summary.passed
    assert safe_summary.high_critical_vulnerabilities == 1
    assert safe_summary.reviewed_unfixed_high_critical == 1
    assert not safe_summary.unreviewed_unfixed_high_critical
    assert not safe_summary.actionable_high_critical

    unsafe = _report(
        vulnerabilities=[
            {
                "VulnerabilityID": "CVE-FIXED",
                "PkgName": "library",
                "InstalledVersion": "1",
                "FixedVersion": "2",
                "Severity": "HIGH",
            }
        ]
    )

    unsafe_summary = evaluate_reports(unsafe, secrets, accepted_unfixed)

    assert not unsafe_summary.passed
    assert unsafe_summary.actionable_high_critical[0].identifier == "CVE-FIXED"


def test_policy_blocks_an_unreviewed_unfixed_high_finding():
    vulnerabilities = _report(
        vulnerabilities=[
            {
                "VulnerabilityID": "CVE-NEW",
                "PkgName": "base-package",
                "InstalledVersion": "1",
                "FixedVersion": "",
                "Severity": "HIGH",
            }
        ]
    )

    summary = evaluate_reports(vulnerabilities, _report(secrets=[]), frozenset())

    assert not summary.passed
    assert summary.unreviewed_unfixed_high_critical[0].identifier == "CVE-NEW"


def test_policy_blocks_secrets_without_printing_secret_material(tmp_path: Path):
    vulnerability_path = tmp_path / "vulnerabilities.json"
    secret_path = tmp_path / "secrets.json"
    baseline_path = tmp_path / "baseline.json"
    vulnerability_path.write_text(json.dumps(_report(vulnerabilities=[])), encoding="utf-8")
    secret_path.write_text(
        json.dumps(
            _report(
                secrets=[
                    {
                        "RuleID": "private-key",
                        "Match": "must-never-appear-in-policy-output",
                    }
                ]
            )
        ),
        encoding="utf-8",
    )
    baseline_path.write_text(json.dumps(_baseline()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(POLICY),
            str(vulnerability_path),
            "--secret-report",
            str(secret_path),
            "--unfixed-baseline",
            str(baseline_path),
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 1
    assert "secret_findings: 1" in result.stdout
    assert "must-never-appear-in-policy-output" not in result.stdout
    assert "CONTAINER_SECURITY_POLICY_FAILED" in result.stdout


def test_policy_rejects_a_non_container_report(tmp_path: Path):
    vulnerability_path = tmp_path / "vulnerabilities.json"
    secret_path = tmp_path / "secrets.json"
    baseline_path = tmp_path / "baseline.json"
    vulnerability_path.write_text(
        json.dumps({"ArtifactType": "filesystem", "Results": [{}]}),
        encoding="utf-8",
    )
    secret_path.write_text(json.dumps(_report(secrets=[])), encoding="utf-8")
    baseline_path.write_text(json.dumps(_baseline()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(POLICY),
            str(vulnerability_path),
            "--secret-report",
            str(secret_path),
            "--unfixed-baseline",
            str(baseline_path),
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 2
    assert "report is not for a container image" in result.stdout
    assert "CONTAINER_SECURITY_POLICY_FAILED" in result.stdout
