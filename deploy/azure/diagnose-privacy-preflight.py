#!/usr/bin/env python3
"""Read count-only failure evidence for the reported Gate 11 execution."""

from __future__ import annotations

import json
import re
import subprocess
import sys


SUBSCRIPTION = "00e62f6e-2174-40b2-b428-8ebfd7c2ac54"
TENANT = "040f05eb-33ab-462f-af54-fb4bedb055ae"
AZURE_USER = "hliu2@cloudbank.org"
RESOURCE_GROUP = "abda-nl-staging"
WORKSPACE = "abda-nl-stg-logs-bgjhpbgw"
JOB = "abda-nl-stg-migrate"
EXECUTION = "abda-nl-stg-migrate-n9lelb6"

# All labels and patterns are fixed code. Log text never leaves Log Analytics.
PATTERNS = {
    "runner_refusals": "privacy acceptance refused:",
    "account_match_refused": "exactly one disposable account must match",
    "account_phase_refused": "account state does not match the confirmed privacy phase",
    "trial_or_model_use_refused": "activated trial credit or called a model",
    "hold_refused": "more seconds before permanent deletion",
    "active_bearer_refused": "prepared account still has active share or MCP access",
    "reservation_refused": "prepared account has an unsettled model reservation",
    "database_input_refused": "application database input is unavailable",
    "cli_refused": "deployed privacy command refused the reviewed operation",
    "preflight_success": "result: PRIVACY_DELETION_PREFLIGHT_VERIFIED",
    "tracebacks": "Traceback (most recent call last)",
    "attribute_error": "AttributeError:",
    "type_error": "TypeError:",
    "name_error": "NameError:",
    "syntax_error": "SyntaxError:",
    "import_error": "ImportError:",
    "module_not_found": "ModuleNotFoundError:",
    "value_error": "ValueError:",
    "detached_instance": "DetachedInstanceError:",
    "operational_error": "OperationalError:",
    "programming_error": "ProgrammingError:",
    "permission_denied": "permission denied",
    "password_authentication_failed": "password authentication failed",
    "database_connection_failed": "connection failed",
    "dns_resolution_failed": "could not translate host name",
    "undefined_table": "UndefinedTable",
    "undefined_column": "UndefinedColumn",
    "out_of_memory": "OOMKilled",
    "image_pull_error": "ErrImagePull",
    "image_pull_backoff": "ImagePullBackOff",
    "container_config_error": "CreateContainerConfigError",
    "deadline_exceeded": "DeadlineExceeded",
}
FIELDS = ("total_logs", "console_logs", "system_logs", "runner_error_line", *PATTERNS)


class DiagnosticError(RuntimeError):
    """A message that contains no private API output."""


def run_json(arguments: list[str], *, label: str, stdin: str | None = None) -> object:
    try:
        result = subprocess.run(
            arguments, input=stdin, text=True, capture_output=True, timeout=70, check=False,
        )
    except subprocess.TimeoutExpired:
        raise DiagnosticError(f"{label} timed out after 70 seconds") from None
    except OSError:
        raise DiagnosticError(f"{label} could not start") from None
    if result.returncode:
        # In particular, never print Azure token errors or curl response bodies.
        raise DiagnosticError(f"{label} exited with code {result.returncode}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise DiagnosticError(f"{label} returned invalid JSON") from None


def az_json(*arguments: str, label: str) -> object:
    return run_json(
        ["az", *arguments, "--only-show-errors", "--output", "json"], label=label,
    )


def logs_query() -> str:
    predicates = ",\n    ".join(
        f"{label}=countif(Message contains {json.dumps(pattern)})"
        for label, pattern in PATTERNS.items()
    )
    return f"""union withsource=LogTable ContainerAppConsoleLogs_CL, ContainerAppSystemLogs_CL
| where TimeGenerated >= ago(7d)
| where tostring(column_ifexists('ContainerGroupName_s', '')) startswith '{EXECUTION}'
    or tostring(pack_all()) contains '{EXECUTION}'
| extend Message=tostring(column_ifexists('Log_s', ''))
| summarize total_logs=count(),
    console_logs=countif(LogTable contains 'ConsoleLogs'),
    system_logs=countif(LogTable contains 'SystemLogs'),
    runner_error_line=max(toint(extract('File "<privacy-acceptance>", line ([0-9]+)', 1, Message))),
    {predicates}
"""


def parse_counts(response: object) -> dict[str, int]:
    if not isinstance(response, dict) or response.get("error"):
        raise DiagnosticError("Log Analytics reported a query error")
    tables = response.get("tables")
    if not isinstance(tables, list) or len(tables) != 1:
        raise DiagnosticError("Log Analytics returned an unexpected table count")
    table = tables[0]
    columns = [column.get("name") for column in table.get("columns", [])]
    rows = table.get("rows", [])
    if tuple(columns) != FIELDS or len(rows) != 1 or len(rows[0]) != len(FIELDS):
        raise DiagnosticError("Log Analytics returned an unexpected summary shape")
    counts = {}
    for name, value in zip(columns, rows[0], strict=True):
        if name == "runner_error_line" and value is None:
            value = 0
        if type(value) is not int or value < 0:
            raise DiagnosticError("Log Analytics returned a nonnumeric count")
        counts[name] = value
    return counts


def main() -> int:
    print("ABDA-NL privacy preflight diagnostic revision: 1", flush=True)
    print("Read-only: inspects the failed execution and requests log counts only.", flush=True)
    print("It does not start a job or read account data or raw log messages.", flush=True)

    print("\n[1/3] Checking Azure identity and the reported execution...", flush=True)
    account = az_json("account", "show", label="Azure identity lookup")
    if not isinstance(account, dict) or (
        account.get("id"), account.get("tenantId"),
        str((account.get("user") or {}).get("name", "")).lower(), account.get("state"),
    ) != (SUBSCRIPTION, TENANT, AZURE_USER, "Enabled"):
        raise DiagnosticError("the active Azure identity or subscription differs")
    execution = az_json(
        "containerapp", "job", "execution", "show", "--name", JOB,
        "--resource-group", RESOURCE_GROUP, "--subscription", SUBSCRIPTION,
        "--job-execution-name", EXECUTION,
        "--query", "{name:name,status:properties.status}", label="Execution lookup",
    )
    if not isinstance(execution, dict) or execution.get("name") != EXECUTION:
        raise DiagnosticError("Azure returned a different execution")
    state = execution.get("status")
    if state not in {"Failed", "Degraded", "Stopped", "Running", "Processing", "Succeeded", "Unknown"}:
        raise DiagnosticError("Azure returned an unrecognized execution state")
    print(f"privacy_job_execution: {EXECUTION}", flush=True)
    print(f"privacy_job_state: {state}", flush=True)

    print("\n[2/3] Resolving the existing Log Analytics workspace...", flush=True)
    workspace_id = az_json(
        "monitor", "log-analytics", "workspace", "show", "--resource-group", RESOURCE_GROUP,
        "--workspace-name", WORKSPACE, "--subscription", SUBSCRIPTION,
        "--query", "customerId", label="Workspace lookup",
    )
    if not isinstance(workspace_id, str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", workspace_id):
        raise DiagnosticError("Azure returned an invalid workspace identifier")
    token = az_json(
        "account", "get-access-token", "--resource", "https://api.loganalytics.io",
        "--subscription", SUBSCRIPTION, "--query", "accessToken", label="Log API authentication",
    )
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_.~-]+", token):
        raise DiagnosticError("Azure returned an invalid Log Analytics token")

    print("\n[3/3] Reading fixed error-category counts (60-second query limit)...", flush=True)
    response = run_json(
        [
            "curl", "--fail", "--silent", "--show-error", "--proto", "=https",
            "--tlsv1.2", "--connect-timeout", "10", "--max-time", "60", "--config", "-",
            "--header", "Content-Type: application/json", "--header", "Prefer: wait=45",
            "--data-binary", json.dumps({"query": logs_query(), "timespan": "P7D"}),
            f"https://api.loganalytics.azure.com/v1/workspaces/{workspace_id}/query",
        ],
        label="Count-only log query", stdin=f'header = "Authorization: Bearer {token}"\n',
    )
    token = ""
    counts = parse_counts(response)
    print("\nABDA-NL privacy preflight diagnostic status:")
    print(f"execution: {EXECUTION}")
    for name, value in counts.items():
        print(f"{name}: {value}")
    print("raw_log_messages_retrieved: false")
    print("azure_configuration_changed: false")
    print("job_started: false")
    print("account_data_changed: false")
    if not counts["total_logs"]:
        print("result: PRIVACY_EXECUTION_LOG_EVIDENCE_NOT_AVAILABLE")
        return 2
    print("result: READ_ONLY_PRIVACY_FAILURE_DIAGNOSTIC_COMPLETE")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except DiagnosticError as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        code = 1
    except KeyboardInterrupt:
        print("Diagnostic interrupted; no mutation was requested.", file=sys.stderr)
        code = 130
    except Exception:
        print("STOP: unexpected diagnostic response; private details suppressed.", file=sys.stderr)
        code = 1
    print(f"Privacy diagnostic exit code: {code}")
    raise SystemExit(code)
