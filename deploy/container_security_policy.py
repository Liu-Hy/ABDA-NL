#!/usr/bin/env python3
"""Apply the ABDA-NL release policy to sanitized Trivy JSON reports."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


BLOCKING_SEVERITIES = frozenset({"HIGH", "CRITICAL"})
FindingKey = tuple[str, str, str, str]


class ReportError(ValueError):
    """Raised when a scanner report does not have the expected structure."""


@dataclass(frozen=True)
class Vulnerability:
    identifier: str
    package: str
    installed_version: str
    fixed_version: str
    severity: str


@dataclass(frozen=True)
class ScanSummary:
    total_vulnerabilities: int
    high_critical_vulnerabilities: int
    reviewed_unfixed_high_critical: int
    unreviewed_unfixed_high_critical: tuple[Vulnerability, ...]
    stale_baseline_entries: int
    actionable_high_critical: tuple[Vulnerability, ...]
    secret_findings: int
    misconfiguration_failures: int

    @property
    def passed(self) -> bool:
        return (
            not self.actionable_high_critical
            and not self.unreviewed_unfixed_high_critical
            and self.secret_findings == 0
            and self.misconfiguration_failures == 0
        )


def _load_report(path: Path, *, artifact_type: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReportError(f"cannot read a valid JSON report: {path}") from exc
    if not isinstance(value, dict):
        raise ReportError(f"report root must be an object: {path}")
    if value.get("ArtifactType") != artifact_type:
        raise ReportError(f"report has unexpected artifact type: {path}")
    results = value.get("Results")
    if not isinstance(results, list) or not results:
        raise ReportError(f"report has no scanner results: {path}")
    return value


def _result_items(report: dict[str, Any], key: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for result in report["Results"]:
        if not isinstance(result, dict):
            raise ReportError("scanner result must be an object")
        result_items = result.get(key) or []
        if not isinstance(result_items, list):
            raise ReportError(f"scanner result field {key} must be a list")
        for item in result_items:
            if not isinstance(item, dict):
                raise ReportError(f"scanner result field {key} contains a non-object")
            items.append(item)
    return items


def _finding_key(finding: Vulnerability) -> FindingKey:
    return (
        finding.severity,
        finding.identifier,
        finding.package,
        finding.installed_version,
    )


def _load_unfixed_baseline(path: Path) -> frozenset[FindingKey]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReportError(f"cannot read a valid unfixed baseline: {path}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ReportError(f"unfixed baseline has an unsupported schema: {path}")
    entries = value.get("accepted_unfixed_high_critical")
    if not isinstance(entries, list):
        raise ReportError(f"unfixed baseline entries must be a list: {path}")

    accepted: set[FindingKey] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ReportError("unfixed baseline contains a non-object entry")
        severity = entry.get("severity")
        identifier = entry.get("vulnerability_id")
        packages = entry.get("packages")
        if severity not in BLOCKING_SEVERITIES or not isinstance(identifier, str):
            raise ReportError("unfixed baseline contains an invalid vulnerability")
        if not isinstance(packages, dict) or not packages:
            raise ReportError("unfixed baseline vulnerability has no packages")
        for package, installed_version in packages.items():
            if not isinstance(package, str) or not isinstance(installed_version, str):
                raise ReportError("unfixed baseline contains an invalid package")
            key = (severity, identifier, package, installed_version)
            if key in accepted:
                raise ReportError("unfixed baseline contains a duplicate package finding")
            accepted.add(key)
    return frozenset(accepted)


def evaluate_reports(
    vulnerability_report: dict[str, Any],
    secret_report: dict[str, Any],
    misconfiguration_report: dict[str, Any],
    accepted_unfixed: frozenset[FindingKey],
) -> ScanSummary:
    vulnerabilities = _result_items(vulnerability_report, "Vulnerabilities")
    secrets = _result_items(secret_report, "Secrets")
    misconfigurations = _result_items(
        misconfiguration_report,
        "Misconfigurations",
    )
    high_critical = 0
    reviewed_unfixed_high_critical = 0
    unreviewed_unfixed: list[Vulnerability] = []
    observed_unfixed: set[FindingKey] = set()
    actionable: list[Vulnerability] = []

    for item in vulnerabilities:
        severity = str(item.get("Severity") or "UNKNOWN").upper()
        if severity not in BLOCKING_SEVERITIES:
            continue
        high_critical += 1
        finding = Vulnerability(
            identifier=str(item.get("VulnerabilityID") or "UNKNOWN"),
            package=str(item.get("PkgName") or "UNKNOWN"),
            installed_version=str(item.get("InstalledVersion") or "UNKNOWN"),
            fixed_version=str(item.get("FixedVersion") or "").strip(),
            severity=severity,
        )
        if not finding.fixed_version:
            key = _finding_key(finding)
            observed_unfixed.add(key)
            if key in accepted_unfixed:
                reviewed_unfixed_high_critical += 1
            else:
                unreviewed_unfixed.append(finding)
            continue
        actionable.append(finding)

    def finding_sort_key(item: Vulnerability) -> tuple[str, str, str, str]:
        return (
            item.severity,
            item.identifier,
            item.package,
            item.installed_version,
        )

    return ScanSummary(
        total_vulnerabilities=len(vulnerabilities),
        high_critical_vulnerabilities=high_critical,
        reviewed_unfixed_high_critical=reviewed_unfixed_high_critical,
        unreviewed_unfixed_high_critical=tuple(
            sorted(unreviewed_unfixed, key=finding_sort_key)
        ),
        stale_baseline_entries=len(accepted_unfixed - observed_unfixed),
        actionable_high_critical=tuple(sorted(actionable, key=finding_sort_key)),
        secret_findings=len(secrets),
        misconfiguration_failures=sum(
            str(item.get("Status") or "").upper() == "FAIL"
            for item in misconfigurations
        ),
    )


def render_summary(summary: ScanSummary) -> str:
    lines = [
        f"total_vulnerabilities: {summary.total_vulnerabilities}",
        f"high_critical_vulnerabilities: {summary.high_critical_vulnerabilities}",
        f"reviewed_unfixed_high_critical: {summary.reviewed_unfixed_high_critical}",
        (
            "unreviewed_unfixed_high_critical: "
            f"{len(summary.unreviewed_unfixed_high_critical)}"
        ),
        f"stale_baseline_entries: {summary.stale_baseline_entries}",
        f"actionable_high_critical: {len(summary.actionable_high_critical)}",
        f"secret_findings: {summary.secret_findings}",
        f"misconfiguration_failures: {summary.misconfiguration_failures}",
    ]
    for finding in summary.unreviewed_unfixed_high_critical[:20]:
        lines.append(
            "unreviewed_finding: "
            f"{finding.severity} {finding.identifier} {finding.package} "
            f"{finding.installed_version}"
        )
    for finding in summary.actionable_high_critical[:20]:
        lines.append(
            "actionable_finding: "
            f"{finding.severity} {finding.identifier} {finding.package} "
            f"{finding.installed_version} -> {finding.fixed_version}"
        )
    lines.append(
        "result: "
        + (
            "CONTAINER_SECURITY_POLICY_VERIFIED"
            if summary.passed
            else "CONTAINER_SECURITY_POLICY_FAILED"
        )
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vulnerability_report", type=Path)
    parser.add_argument("--secret-report", required=True, type=Path)
    parser.add_argument("--misconfiguration-report", required=True, type=Path)
    parser.add_argument("--unfixed-baseline", required=True, type=Path)
    args = parser.parse_args()

    try:
        vulnerability_report = _load_report(
            args.vulnerability_report,
            artifact_type="container_image",
        )
        secret_report = _load_report(
            args.secret_report,
            artifact_type="container_image",
        )
        misconfiguration_report = _load_report(
            args.misconfiguration_report,
            artifact_type="filesystem",
        )
        accepted_unfixed = _load_unfixed_baseline(args.unfixed_baseline)
        summary = evaluate_reports(
            vulnerability_report,
            secret_report,
            misconfiguration_report,
            accepted_unfixed,
        )
    except ReportError as exc:
        print(f"container_security_report_error: {exc}")
        print("result: CONTAINER_SECURITY_POLICY_FAILED")
        return 2

    print(render_summary(summary))
    return 0 if summary.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
