#!/usr/bin/env python3
"""Run one read-only database inspection to explain the privacy account selector."""

from __future__ import annotations

import base64
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time


DIAGNOSTIC_URL = (
    "https://raw.githubusercontent.com/Liu-Hy/ABDA-NL/"
    "99aff5ea06606f3226ede972cf0b1493bfffd80d/deploy/azure/diagnose-privacy-preflight.py"
)
DIAGNOSTIC_SHA256 = "864434762fe616c904d72f00965835076edbe6e5257392bf5114619a4e032751"
COUNT_FIELDS = (
    "original_selector_matches", "both_names_any_status", "both_names_active",
    "both_names_prepared", "both_names_other_status", "both_names_unverified",
    "both_names_archived_only", "named_project_accounts", "named_credential_accounts",
    "prepared_accounts", "prepared_verified_accounts", "prepared_with_named_project",
    "prepared_with_named_credential", "prepared_without_projects",
    "prepared_without_credentials", "prepared_updated_during_original_execution",
    "preparation_bearer_window_matches", "prepared_bearer_window_matches",
    "archived_bearer_window_matches", "unverified_bearer_window_matches",
)
RESULT_FIELDS = ("inspection_receipts", "inspection_errors", *COUNT_FIELDS)


class InspectionError(RuntimeError):
    """A fixed diagnostic message that never embeds private response content."""


RUNNER = r'''
import os
from datetime import datetime
from urllib.parse import quote

def main():
    if not os.environ.get("ABDA_DATABASE_URL"):
        password = os.environ.pop("ABDA_DATABASE_APP_PASSWORD", "")
        host = os.environ.pop("ABDA_POSTGRES_HOST", "")
        if not password or host != "abda-nl-stg-postgres-bgjhpbgw.postgres.database.azure.com":
            raise ValueError("database configuration")
        os.environ["ABDA_DATABASE_URL"] = (
            "postgresql+psycopg://abda_app:" + quote(password, safe="")
            + "@" + host + ":5432/abda?sslmode=require&connect_timeout=15"
        )
        password = ""
    from sqlalchemy import and_, exists, func, select, text
    from app.db.models import MCPAccessToken, Project, ShareLink, User
    from app.db.session import get_session_factory

    start = datetime.fromisoformat(os.environ["ABDA_PRIVACY_PREPARED_START"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(os.environ["ABDA_PRIVACY_PREPARED_END"].replace("Z", "+00:00"))
    if start.tzinfo is None or end.tzinfo is None or not 0 < (end - start).total_seconds() <= 3600:
        raise ValueError("preparation interval")
    marker = "Privacy acceptance disposable"
    named_project = exists(select(Project.id).where(Project.owner_user_id == User.id, Project.name == marker))
    live_project = exists(select(Project.id).where(
        Project.owner_user_id == User.id, Project.name == marker, Project.archived_at.is_(None),
    ))
    named_token = exists(select(MCPAccessToken.id).where(
        MCPAccessToken.user_id == User.id, MCPAccessToken.name == marker,
    ))
    both = and_(named_project, named_token)
    prepared = User.status == "deletion_pending"
    verified = User.email_verified.is_(True)
    share_window = exists(select(ShareLink.id).join(Project, Project.id == ShareLink.project_id).where(
        Project.owner_user_id == User.id, Project.name == marker,
        ShareLink.revoked_at >= start, ShareLink.revoked_at <= end,
    ))
    token_window = exists(select(MCPAccessToken.id).where(
        MCPAccessToken.user_id == User.id, MCPAccessToken.name == marker,
        MCPAccessToken.revoked_at >= start, MCPAccessToken.revoked_at <= end,
    ))
    original_window = and_(share_window, token_window)
    predicates = {
        "original_selector_matches": and_(verified, User.status.in_(("active", "deletion_pending")), live_project, named_token),
        "both_names_any_status": both,
        "both_names_active": and_(both, User.status == "active"),
        "both_names_prepared": and_(both, prepared),
        "both_names_other_status": and_(both, User.status.not_in(("active", "deletion_pending"))),
        "both_names_unverified": and_(both, User.email_verified.is_not(True)),
        "both_names_archived_only": and_(both, ~live_project),
        "named_project_accounts": named_project,
        "named_credential_accounts": named_token,
        "prepared_accounts": prepared,
        "prepared_verified_accounts": and_(prepared, verified),
        "prepared_with_named_project": and_(prepared, named_project),
        "prepared_with_named_credential": and_(prepared, named_token),
        "prepared_without_projects": and_(prepared, ~exists(select(Project.id).where(Project.owner_user_id == User.id))),
        "prepared_without_credentials": and_(prepared, ~exists(select(MCPAccessToken.id).where(MCPAccessToken.user_id == User.id))),
        "prepared_updated_during_original_execution": and_(prepared, User.updated_at >= start, User.updated_at <= end),
        "preparation_bearer_window_matches": original_window,
        "prepared_bearer_window_matches": and_(original_window, prepared),
        "archived_bearer_window_matches": and_(original_window, ~live_project),
        "unverified_bearer_window_matches": and_(original_window, User.email_verified.is_not(True)),
    }
    with get_session_factory()() as session:
        if session.get_bind().dialect.name == "postgresql":
            session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            session.execute(text("SET TRANSACTION READ ONLY"))
            session.execute(text("SET LOCAL statement_timeout = '15s'"))
        elif session.get_bind().dialect.name == "sqlite":
            session.execute(text("PRAGMA query_only = ON"))
        else:
            raise ValueError("unsupported database")
        counts = {
            name: int(session.scalar(select(func.count()).select_from(User).where(predicate)) or 0)
            for name, predicate in predicates.items()
        }
        session.rollback()
    for name, count in counts.items():
        print(f"privacy_match_count {name}={count}", flush=True)
    print("result: PRIVACY_ACCOUNT_MATCH_INSPECTION_COMPLETE", flush=True)

try:
    main()
except Exception:
    print("privacy_match_error: inspection_failed", flush=True)
    raise SystemExit(1)
'''


def load_diagnostic(directory: Path):
    source = subprocess.run(
        ["curl", "-fsSL", "--proto", "=https", "--connect-timeout", "10", "--max-time", "30", DIAGNOSTIC_URL],
        capture_output=True, timeout=40, check=True,
    ).stdout
    if hashlib.sha256(source).hexdigest() != DIAGNOSTIC_SHA256:
        raise InspectionError("diagnostic checksum mismatch")
    path = directory / "diagnostic.py"
    path.write_bytes(source)
    spec = importlib.util.spec_from_file_location("abda_privacy_diagnostic", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def preparation_interval(response: dict, diagnostic) -> tuple[str, str]:
    properties = response.get("properties") or {}
    if response.get("name") != diagnostic.PREPARATION_EXECUTION or properties.get("status") != "Succeeded":
        raise InspectionError("the original preparation execution is not successful")
    description = diagnostic.describe_command((properties.get("template") or {}).get("containers"))
    if description != {
        "execution_command": "privacy_prepare", "runner_source": "privacy_revision_8",
        "reviewed_privacy_image": "true",
    }:
        raise InspectionError("the recorded preparation command differs")
    start, end = properties.get("startTime"), properties.get("endTime")
    first, last = (datetime.fromisoformat(value.replace("Z", "+00:00")) for value in (start, end))
    if first.tzinfo is None or last.tzinfo is None or not 0 < (last - first).total_seconds() <= 3600:
        raise InspectionError("the preparation time interval is invalid")
    return start, end


def template(image: str, start: str, end: str) -> dict:
    payload = base64.b64encode(RUNNER.encode()).decode()
    return {"containers": [{
        "name": "migrate", "image": image, "command": ["/opt/venv/bin/python"],
        "args": ["-c", "import base64;exec(compile(base64.b64decode(" + repr(payload) + "),'<privacy-match-inspection>','exec'))"],
        "env": [
            {"name": "ABDA_DATABASE_APP_PASSWORD", "secretRef": "app-database-password"},
            {"name": "ABDA_POSTGRES_HOST", "value": "abda-nl-stg-postgres-bgjhpbgw.postgres.database.azure.com"},
            {"name": "ABDA_PRIVACY_PREPARED_START", "value": start},
            {"name": "ABDA_PRIVACY_PREPARED_END", "value": end},
            {"name": "ABDA_AUTO_CREATE_DB", "value": "0"},
            {"name": "ABDA_DATABASE_POOL_SIZE", "value": "1"},
            {"name": "ABDA_DATABASE_MAX_OVERFLOW", "value": "0"},
        ], "resources": {"cpu": 0.25, "memory": "0.5Gi"},
    }]}


def receipt_query(execution: str) -> str:
    if not re.fullmatch(r"abda-nl-stg-migrate-[a-z0-9]+", execution):
        raise InspectionError("invalid inspection execution name")
    counters = ",\n".join(
        f"{name}=max(toint(extract('privacy_match_count {name}=([0-9]+)', 1, Log_s)))"
        for name in COUNT_FIELDS
    )
    return f"""ContainerAppConsoleLogs_CL
| where TimeGenerated >= ago(1d) and ContainerGroupName_s startswith '{execution}'
| summarize inspection_receipts=countif(Log_s contains 'result: PRIVACY_ACCOUNT_MATCH_INSPECTION_COMPLETE'),
inspection_errors=countif(Log_s contains 'privacy_match_error:'),
{counters}
"""


def run(directory: Path, diagnostic) -> int:
    d = diagnostic
    az = d.az_json
    print("\n[1/4] Checking Azure identity and the original preparation...", flush=True)
    account = az("account", "show", label="Azure identity")
    if (account.get("id"), account.get("tenantId"), (account.get("user") or {}).get("name"), account.get("state")) != (
        d.SUBSCRIPTION, d.TENANT, d.AZURE_USER, "Enabled",
    ):
        raise InspectionError("Azure identity changed")
    common = ("--name", d.JOB, "--resource-group", d.RESOURCE_GROUP, "--subscription", d.SUBSCRIPTION)
    original = az("containerapp", "job", "execution", "show", *common,
                  "--job-execution-name", d.PREPARATION_EXECUTION, label="Original preparation")
    start, end = preparation_interval(original, d)
    job = az("containerapp", "job", "show", *common, label="Manual job validation")
    properties = job.get("properties") or {}
    configuration = properties.get("configuration") or {}
    if (
        job.get("name") != d.JOB or properties.get("provisioningState") != "Succeeded"
        or configuration.get("triggerType") != "Manual" or configuration.get("replicaRetryLimit") != 0
        or configuration.get("manualTriggerConfig", {}).get("parallelism") != 1
        or configuration.get("manualTriggerConfig", {}).get("replicaCompletionCount") != 1
        or not str(properties.get("environmentId", "")).endswith("/managedEnvironments/abda-nl-stg-environment")
        or "app-database-password" not in {secret.get("name") for secret in configuration.get("secrets", [])}
    ):
        raise InspectionError("manual job boundary changed")
    executions = az("containerapp", "job", "execution", "list", *common, label="Active job check")
    if not isinstance(executions, list) or any(
        (item.get("properties") or item).get("status") not in {"Succeeded", "Failed", "Degraded", "Stopped"}
        for item in executions
    ):
        raise InspectionError("another job execution is active or unknown")

    print("\n[2/4] Starting one database inspection with SQL read-only enforcement...", flush=True)
    path = directory / "inspection.json"
    path.write_text(json.dumps(template(d.EXPECTED_IMAGE, start, end)), encoding="utf-8")
    launched = az("containerapp", "job", "start", *common, "--yaml", str(path), label="Read-only inspection start")
    execution = launched.get("name", "")
    query = receipt_query(execution)
    print(f"inspection_execution: {execution}", flush=True)
    print("\n[3/4] Waiting for that inspection (five-minute limit)...", flush=True)
    deadline = time.monotonic() + 300
    state = "Unknown"
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        state = az("containerapp", "job", "execution", "show", *common,
                   "--job-execution-name", execution, "--query", "properties.status", label="Inspection status")
        if attempt % 6 == 1:
            safe_state = state if state in {"Succeeded", "Failed", "Degraded", "Stopped", "Running", "Processing"} else "Unknown"
            print(f"inspection_progress: {safe_state}", flush=True)
        if state in {"Succeeded", "Failed", "Degraded", "Stopped"}:
            break
        time.sleep(5)
    safe_state = state if state in {"Succeeded", "Failed", "Degraded", "Stopped", "Running", "Processing"} else "Unknown"
    print(f"inspection_state: {safe_state}", flush=True)

    print("\n[4/4] Retrieving only the inspection counters...", flush=True)
    workspace_id = az("monitor", "log-analytics", "workspace", "show", "--resource-group", d.RESOURCE_GROUP,
                      "--workspace-name", d.WORKSPACE, "--subscription", d.SUBSCRIPTION,
                      "--query", "customerId", label="Log workspace")
    if not isinstance(workspace_id, str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", workspace_id):
        raise InspectionError("invalid workspace identifier")
    token = az("account", "get-access-token", "--resource", "https://api.loganalytics.io",
               "--subscription", d.SUBSCRIPTION, "--query", "accessToken", label="Log API authentication")
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_.~-]+", token):
        raise InspectionError("invalid access token")
    d.FIELDS = RESULT_FIELDS
    for attempt in range(6):
        response = d.run_json([
            "curl", "--fail", "--silent", "--show-error", "--proto", "=https", "--tlsv1.2",
            "--connect-timeout", "10", "--max-time", "60", "--config", "-",
            "--header", "Content-Type: application/json", "--header", "Prefer: wait=45",
            "--data-binary", json.dumps({"query": query, "timespan": "P1D"}),
            f"https://api.loganalytics.azure.com/v1/workspaces/{workspace_id}/query",
        ], label="Inspection receipt query", stdin=f'header = "Authorization: Bearer {token}"\n')
        tables = response.get("tables", []) if isinstance(response, dict) else []
        rows = tables[0].get("rows", []) if len(tables) == 1 else []
        if len(rows) != 1 or len(rows[0]) != len(RESULT_FIELDS) or response.get("error"):
            raise InspectionError("unexpected receipt response")
        if rows[0][0] or rows[0][1]:
            break
        print(f"receipt_ingestion_attempt: {attempt + 1}/6", flush=True)
        if attempt < 5:
            time.sleep(15)
    token = ""
    if state != "Succeeded" or not rows[0][0] or rows[0][1]:
        print("result: PRIVACY_MATCH_INSPECTION_NOT_VERIFIED")
        return 2
    counts = d.parse_counts(response)
    print("\nABDA-NL privacy account matching status:")
    print(f"inspection_execution: {execution}")
    for name, value in counts.items():
        print(f"{name}: {value}")
    print("sql_read_only: true")
    print("account_data_changed: false")
    print("azure_configuration_changed: false")
    print("raw_log_messages_retrieved: false")
    print("result: PRIVACY_ACCOUNT_MATCH_COUNTS_VERIFIED")
    return 0


if __name__ == "__main__":
    print("ABDA-NL privacy account matching inspection revision: 1", flush=True)
    print("Starts one temporary execution of the existing job, with a read-only database transaction.", flush=True)
    print("It does not prepare or delete an account, run migrations, or change the saved job configuration.", flush=True)
    diagnostic = None
    try:
        with tempfile.TemporaryDirectory(prefix="abda-privacy-match-") as root:
            directory = Path(root)
            diagnostic = load_diagnostic(directory)
            code = run(directory, diagnostic)
    except KeyboardInterrupt:
        print("Inspection interrupted. A started read-only job may still finish; do not repeat it yet.")
        code = 130
    except Exception as exc:
        if isinstance(exc, InspectionError) or (diagnostic and isinstance(exc, diagnostic.DiagnosticError)):
            print(f"STOP: {exc}")
        else:
            print("STOP: inspection could not complete; private error details suppressed.")
        print("Send the visible step and execution name. Do not repeat a started inspection yet.")
        code = 1
    print(f"Privacy matching inspection exit code: {code}")
    raise SystemExit(code)
