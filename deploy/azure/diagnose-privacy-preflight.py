#!/usr/bin/env python3
"""Read count-only failure evidence for the reported Gate 11 execution."""

from __future__ import annotations

import ast
import base64
import hashlib
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
PREPARATION_EXECUTION = "abda-nl-stg-migrate-7tlx9gq"
REVIEWED_RUNNERS = {
    "41dae6e04d0ae1af2214aeb1cc2b44cb3cabd1cf2f161854d52322af906bcd4f": "privacy_revision_8",
    "76702829f146c76381e02d73fbaa316fd233a5fe474e09c48130acacf19a1237": "privacy_revision_10",
}
EXPECTED_IMAGE = (
    "ghcr.io/liu-hy/abda-nl@sha256:"
    "a0b3ba24aff06ecf461f86547131d86451c541e306a7ecfc278f280fcef5c0bc"
)

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
    "preparation_success": "result: PRIVACY_ACCEPTANCE_PREPARED_WAIT_15_MINUTES",
    "preparation_resumed": "preparation_resumed: true",
    "export_validated": "private_export_validated_and_removed: true",
    "deletion_success": "result: LIVE_PRIVACY_EXPORT_AND_DELETION_VERIFIED",
    "migration_completed": "Database migration and restricted application role provisioning completed.",
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


def logs_query(execution_name: str = EXECUTION) -> str:
    if execution_name not in {EXECUTION, PREPARATION_EXECUTION}:
        raise DiagnosticError("the execution is outside this diagnostic")
    predicates = ",\n    ".join(
        f"{label}=countif(Message contains {json.dumps(pattern)})"
        for label, pattern in PATTERNS.items()
    )
    return f"""union withsource=LogTable ContainerAppConsoleLogs_CL, ContainerAppSystemLogs_CL
| where TimeGenerated >= ago(7d)
| where tostring(column_ifexists('ContainerGroupName_s', '')) startswith '{execution_name}'
    or tostring(pack_all()) contains '{execution_name}'
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


def describe_command(containers: object) -> dict[str, str]:
    """Classify saved commands without executing code or printing argument values."""
    description = {"execution_command": "unrecognized", "runner_source": "unrecognized"}
    if not isinstance(containers, list) or len(containers) != 1 or not isinstance(containers[0], dict):
        return {"execution_command": "template_unavailable", "runner_source": "unavailable"}
    container = containers[0]
    description["reviewed_privacy_image"] = str(container.get("image") == EXPECTED_IMAGE).lower()
    command = container.get("command")
    args = container.get("args")
    if command != ["/opt/venv/bin/python"] or not isinstance(args, list):
        return description
    if args == ["-m", "app.cli.migrate"]:
        description.update(execution_command="database_migration", runner_source="migration_module")
        return description
    if (
        len(args) != 4 or args[0] != "-c" or not isinstance(args[2], str)
        or args[2] not in {"prepare", "preflight-delete", "delete"}
    ):
        return description
    if args[3] != "PRIV-ACCEPT-20260830-01" or not isinstance(args[1], str) or len(args[1]) > 131072:
        return description
    description["execution_command"] = f"privacy_{args[2]}"
    try:
        tree = ast.parse(args[1])
        payloads = [
            node.args[0].value for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "base64"
            and node.func.attr == "b64decode" and len(node.args) == 1
            and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
        ]
        if len(payloads) == 1:
            expected_wrapper = (
                "import base64;exec(compile(base64.b64decode("
                + repr(payloads[0]) + "),'<privacy-acceptance>','exec'))"
            )
            if args[1] != expected_wrapper:
                return description
            digest = hashlib.sha256(base64.b64decode(payloads[0], validate=True)).hexdigest()
            description["runner_source"] = REVIEWED_RUNNERS.get(digest, "unrecognized")
    except (ValueError, SyntaxError, RecursionError):
        pass
    return description


def main(argv: list[str] | None = None) -> int:
    arguments = argv or []
    if arguments not in ([], ["--preparation"]):
        raise DiagnosticError("only the optional --preparation argument is supported")
    execution_name = PREPARATION_EXECUTION if arguments else EXECUTION
    print("ABDA-NL privacy preflight diagnostic revision: 2", flush=True)
    print("Read-only: inspects one recorded execution and requests log counts only.", flush=True)
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
        "--job-execution-name", execution_name,
        "--query", (
            "{name:name,status:properties.status,"
            "containers:properties.template.containers[].{name:name,image:image,command:command,args:args}}"
        ),
        label="Execution lookup",
    )
    if not isinstance(execution, dict) or execution.get("name") != execution_name:
        raise DiagnosticError("Azure returned a different execution")
    state = execution.get("status")
    if state not in {"Failed", "Degraded", "Stopped", "Running", "Processing", "Succeeded", "Unknown"}:
        raise DiagnosticError("Azure returned an unrecognized execution state")
    print(f"privacy_job_execution: {execution_name}", flush=True)
    print(f"privacy_job_state: {state}", flush=True)
    command_description = describe_command(execution.get("containers"))
    for name, value in command_description.items():
        print(f"{name}: {value}", flush=True)

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
            "--data-binary", json.dumps({"query": logs_query(execution_name), "timespan": "P7D"}),
            f"https://api.loganalytics.azure.com/v1/workspaces/{workspace_id}/query",
        ],
        label="Count-only log query", stdin=f'header = "Authorization: Bearer {token}"\n',
    )
    token = ""
    counts = parse_counts(response)
    print("\nABDA-NL privacy preflight diagnostic status:")
    print(f"execution: {execution_name}")
    print(f"execution_state: {state}")
    for name, value in command_description.items():
        print(f"{name}: {value}")
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
        code = main(sys.argv[1:])
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
