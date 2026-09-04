#!/usr/bin/env bash

# Exercise the deployed privacy export and two-phase deletion workflow against
# one disposable, blocked staging account. The gate uses a one-time execution
# override on the existing manual migration job so it does not depend on the
# Azure Container Apps interactive WebSocket. The override changes no job or
# application configuration. It never changes Auth0, DNS, secrets, trial
# settings, or provider routing.

ABDA_PRIVACY_SCRIPT_REVISION='10'
ABDA_PRIVACY_APPLICATION_SOURCE_COMMIT='51702e175bd14d4cb54075808f839d173d561324'
ABDA_PRIVACY_IMAGE_SHA256='a0b3ba24aff06ecf461f86547131d86451c541e306a7ecfc278f280fcef5c0bc'
ABDA_PRIVACY_EXPECTED_REVISION='abda-nl-stg-web--harden-51702e1'
ABDA_PRIVACY_REQUEST_REFERENCE='PRIV-ACCEPT-20260830-01'
ABDA_PRIVACY_ROOT=''

abda_privacy_cleanup() {
  local exit_code=$?
  set +e
  if [[ "${ABDA_PRIVACY_ROOT:-}" == /tmp/abda-nl-gate11-privacy.* &&
        -d "${ABDA_PRIVACY_ROOT:-}" ]]; then
    rm -rf -- "$ABDA_PRIVACY_ROOT"
  fi
  printf '\nGate 11 shell exit code: %s\n' "$exit_code"
}

abda_privacy_error() {
  local exit_code=$?
  trap - ERR
  printf '\nSTOP: Gate 11 failed in section: %s\n' \
    "${ABDA_PRIVACY_SECTION:-unknown}" >&2
  printf '%s\n' \
    'Do not delete the Azure resource group or edit database rows manually.' \
    'Keep the disposable Auth0 user blocked and send the visible status to Codex.' >&2
  exit "$exit_code"
}

abda_privacy_interrupt() {
  trap - ERR INT
  printf '\nSTOP: Gate 11 was interrupted in section: %s\n' \
    "${ABDA_PRIVACY_SECTION:-unknown}" >&2
  printf '%s\n' \
    'Keep the disposable Auth0 user blocked. Rerun this exact pinned gate after inspection.' >&2
  exit 130
}

abda_privacy_fail() {
  printf 'STOP: %s\n' "$*" >&2
  return 1
}

abda_privacy_set_constants() {
  ABDA_EXPECTED_SUBSCRIPTION='00e62f6e-2174-40b2-b428-8ebfd7c2ac54'
  ABDA_EXPECTED_TENANT='040f05eb-33ab-462f-af54-fb4bedb055ae'
  ABDA_EXPECTED_USER='hliu2@cloudbank.org'
  ABDA_RESOURCE_GROUP='abda-nl-staging'
  ABDA_APP_NAME='abda-nl-stg-web'
  ABDA_MIGRATION_JOB_NAME='abda-nl-stg-migrate'
  ABDA_CONTAINER_APPS_ENVIRONMENT='abda-nl-stg-environment'
  ABDA_POSTGRES_HOST='abda-nl-stg-postgres-bgjhpbgw.postgres.database.azure.com'
  ABDA_PUBLIC_ORIGIN='https://demo.abda-nl.org'
  ABDA_IMAGE_REPOSITORY='ghcr.io/liu-hy/abda-nl'
}

abda_privacy_validate_identity() {
  local path=$1
  python3 - "$path" "$ABDA_EXPECTED_SUBSCRIPTION" \
    "$ABDA_EXPECTED_TENANT" "$ABDA_EXPECTED_USER" <<'PY'
import json
import sys

path, expected_subscription, expected_tenant, expected_user = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    account = json.load(handle)
if account.get("id") != expected_subscription:
    raise SystemExit("STOP: the active Azure subscription changed")
if account.get("tenantId") != expected_tenant:
    raise SystemExit("STOP: the active Azure tenant changed")
if str((account.get("user") or {}).get("name") or "").lower() != expected_user.lower():
    raise SystemExit("STOP: the active Azure user changed")
if account.get("state") != "Enabled":
    raise SystemExit("STOP: the active Azure subscription is not enabled")
PY
}

abda_privacy_validate_app() {
  local path=$1
  python3 - "$path" "$ABDA_APP_NAME" "$ABDA_PRIVACY_EXPECTED_REVISION" \
    "$ABDA_IMAGE_REPOSITORY@sha256:$ABDA_PRIVACY_IMAGE_SHA256" <<'PY'
import json
import sys

path, expected_app, expected_revision, expected_image = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    app = json.load(handle)
properties = app.get("properties") or {}
configuration = properties.get("configuration") or {}
template = properties.get("template") or {}
containers = template.get("containers") or []
if app.get("name") != expected_app or len(containers) != 1:
    raise SystemExit("STOP: the Container App identity or container count changed")
if properties.get("provisioningState") != "Succeeded":
    raise SystemExit("STOP: the Container App provisioning state is not Succeeded")
if properties.get("runningStatus") != "Running":
    raise SystemExit("STOP: the Container App running status is not Running")
if (
    properties.get("latestRevisionName") != expected_revision
    or properties.get("latestReadyRevisionName") != expected_revision
):
    raise SystemExit("STOP: the deployed application revision changed before Gate 11")
if configuration.get("activeRevisionsMode") != "Single":
    raise SystemExit("STOP: the Container App is not in single revision mode")
container = containers[0]
if container.get("name") != "web" or container.get("image") != expected_image:
    raise SystemExit("STOP: the deployed web image changed")
env_items = container.get("env") or []
env = {item.get("name"): item for item in env_items}
if len(env) != len(env_items):
    raise SystemExit("STOP: duplicate environment variable names are present")
expected_values = {
    "ABDA_ENVIRONMENT": "staging",
    "ABDA_AUTH_MODE": "oidc",
    "ABDA_PUBLIC_BASE_URL": "https://demo.abda-nl.org",
    "ABDA_TRIAL_ENABLED": "true",
    "ABDA_TRIAL_MAX_USERS": "10",
    "ABDA_TRIAL_GRANT_MICROUSD": "5000000",
    "ABDA_TRIAL_BUDGET_MICROUSD": "50000000",
    "ABDA_OPENROUTER_FAILOVER_ENABLED": "false",
    "ABDA_OPENROUTER_BUDGET_MICROUSD": "500000000",
}
for name, expected in expected_values.items():
    actual = str(env.get(name, {}).get("value") or "").strip().lower()
    if actual != expected.lower():
        raise SystemExit(f"STOP: deployed setting {name} changed")
if env.get("ABDA_DATABASE_URL", {}).get("secretRef") != "database-url":
    raise SystemExit("STOP: the application database secret reference changed")
PY
}

abda_privacy_validate_job() {
  local path=$1
  python3 - "$path" "$ABDA_MIGRATION_JOB_NAME" \
    "$ABDA_CONTAINER_APPS_ENVIRONMENT" <<'PY'
import json
import sys

path, expected_name, expected_environment = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    job = json.load(handle)
properties = job.get("properties") or {}
configuration = properties.get("configuration") or {}
template = properties.get("template") or {}
containers = template.get("containers") or []
if job.get("name") != expected_name or len(containers) != 1:
    raise SystemExit("STOP: migration job identity or container count changed")
if properties.get("provisioningState") != "Succeeded":
    raise SystemExit("STOP: migration job is not provisioned")
if not str(properties.get("environmentId") or "").endswith(
    f"/managedEnvironments/{expected_environment}"
):
    raise SystemExit("STOP: migration job environment changed")
if configuration.get("triggerType") != "Manual":
    raise SystemExit("STOP: migration job is not manual")
if configuration.get("replicaRetryLimit") != 0:
    raise SystemExit("STOP: migration job retry limit changed")
manual = configuration.get("manualTriggerConfig") or {}
if manual.get("parallelism") != 1 or manual.get("replicaCompletionCount") != 1:
    raise SystemExit("STOP: migration job execution cardinality changed")
secret_names = {str(item.get("name") or "") for item in configuration.get("secrets") or []}
if "app-database-password" not in secret_names:
    raise SystemExit("STOP: migration job application password secret is absent")
container = containers[0]
if container.get("name") != "migrate":
    raise SystemExit("STOP: migration job container changed")
if container.get("command") != ["/opt/venv/bin/python"]:
    raise SystemExit("STOP: migration job command changed")
if container.get("args") != ["-m", "app.cli.migrate"]:
    raise SystemExit("STOP: migration job arguments changed")
env = {str(item.get("name") or ""): item for item in container.get("env") or []}
if env.get("ABDA_DATABASE_URL", {}).get("secretRef") != "admin-database-url":
    raise SystemExit("STOP: migration administrator credential boundary changed")
if env.get("ABDA_DATABASE_APP_PASSWORD", {}).get("secretRef") != "app-database-password":
    raise SystemExit("STOP: migration application credential boundary changed")
PY
}

abda_privacy_compare_job_configuration() {
  local before_path=$1
  local after_path=$2
  python3 - "$before_path" "$after_path" <<'PY'
import json
import sys

def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)

def stable_configuration(job):
    properties = job.get("properties") or {}
    return {
        "name": job.get("name"),
        "location": job.get("location"),
        "identity": job.get("identity"),
        "tags": job.get("tags"),
        "environmentId": properties.get("environmentId"),
        "workloadProfileName": properties.get("workloadProfileName"),
        "configuration": properties.get("configuration"),
        "template": properties.get("template"),
    }

if stable_configuration(load(sys.argv[1])) != stable_configuration(load(sys.argv[2])):
    raise SystemExit("STOP: the migration job configuration changed")
PY
}

abda_privacy_write_job_template() {
  local path=$1
  local runner_payload=$2
  local action=$3
  local image="${ABDA_IMAGE_REPOSITORY}@sha256:${ABDA_PRIVACY_IMAGE_SHA256}"
  python3 - "$path" "$runner_payload" "$action" "$image" \
    "$ABDA_POSTGRES_HOST" "$ABDA_PRIVACY_REQUEST_REFERENCE" <<'PY'
import json
from pathlib import Path
import sys

path, payload, action, image, postgres_host, request_reference = sys.argv[1:]
if action not in {"prepare", "preflight-delete", "delete"}:
    raise SystemExit("STOP: invalid privacy execution action")
document = {
    "containers": [
        {
            "name": "migrate",
            "image": image,
            "command": ["/opt/venv/bin/python"],
            "args": [
                "-c",
                (
                    "import base64;exec(compile(base64.b64decode("
                    + repr(payload)
                    + "),'<privacy-acceptance>','exec'))"
                ),
                action,
                request_reference,
            ],
            "env": [
                {
                    "name": "ABDA_DATABASE_APP_PASSWORD",
                    "secretRef": "app-database-password",
                },
                {"name": "ABDA_POSTGRES_HOST", "value": postgres_host},
                {"name": "ABDA_AUTO_CREATE_DB", "value": "0"},
                {"name": "ABDA_DATABASE_POOL_SIZE", "value": "1"},
                {"name": "ABDA_DATABASE_MAX_OVERFLOW", "value": "0"},
            ],
            "resources": {"cpu": 0.25, "memory": "0.5Gi"},
        }
    ]
}
Path(path).write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
PY
  chmod 600 "$path"
}

abda_privacy_load_execution_details() {
  local list_path=$1
  local output_path=$2
  local details_root=$3
  local names_path="$details_root/names.txt"
  local manifest_path="$details_root/manifest.txt"
  mkdir -p "$details_root"
  chmod 700 "$details_root"
  python3 - "$list_path" "$ABDA_MIGRATION_JOB_NAME" >"$names_path" <<'PY'
import json
import re
import sys


with open(sys.argv[1], encoding="utf-8") as handle:
    executions = json.load(handle)
job_name = sys.argv[2]
if not isinstance(executions, list):
    raise SystemExit("STOP: Azure returned an invalid job execution list")
rows = []
for execution in executions:
    name = str(execution.get("name") or "")
    if not re.fullmatch(re.escape(job_name) + r"-[a-z0-9]+", name):
        raise SystemExit("STOP: Azure returned an invalid job execution name")
    properties = execution.get("properties") or execution
    rows.append((str(properties.get("startTime") or ""), name))
if len(rows) > 50:
    raise SystemExit("STOP: too many migration job executions require inspection")
for _, name in sorted(rows, reverse=True):
    print(name)
PY

  : >"$manifest_path"
  local execution_name=''
  local detail_path=''
  local detail_index=0
  while IFS= read -r execution_name; do
    [[ -n "$execution_name" ]] || continue
    detail_index=$((detail_index + 1))
    detail_path="$details_root/execution-$detail_index.json"
    az containerapp job execution show \
      --name "$ABDA_MIGRATION_JOB_NAME" \
      --resource-group "$ABDA_RESOURCE_GROUP" \
      --job-execution-name "$execution_name" \
      --output json >"$detail_path"
    python3 - "$detail_path" "$execution_name" <<'PY'
import json
import sys


with open(sys.argv[1], encoding="utf-8") as handle:
    execution = json.load(handle)
if execution.get("name") != sys.argv[2]:
    raise SystemExit("STOP: Azure returned a different job execution")
properties = execution.get("properties") or {}
if not isinstance(properties.get("template"), dict):
    raise SystemExit("STOP: Azure omitted a job execution template")
PY
    printf '%s\n' "$detail_path" >>"$manifest_path"
  done <"$names_path"

  python3 - "$manifest_path" "$output_path" <<'PY'
import json
from pathlib import Path
import sys


manifest = Path(sys.argv[1])
executions = []
for line in manifest.read_text(encoding="utf-8").splitlines():
    with open(line, encoding="utf-8") as handle:
        executions.append(json.load(handle))
Path(sys.argv[2]).write_text(
    json.dumps(executions, separators=(",", ":")),
    encoding="utf-8",
)
PY
  chmod 600 "$output_path"
}

abda_privacy_classify_executions() {
  local executions_path=$1
  local template_path=$2
  local failed_retry=${3:-false}
  python3 - "$executions_path" "$template_path" "$failed_retry" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    executions = json.load(handle)
with open(sys.argv[2], encoding="utf-8") as handle:
    expected_template = json.load(handle)
failed_retry = sys.argv[3] == "true"
if not isinstance(executions, list):
    raise SystemExit("STOP: Azure returned an invalid job execution list")

def signature(template):
    containers = (template or {}).get("containers") or []
    init_containers = (template or {}).get("initContainers") or []
    if len(containers) != 1 or init_containers:
        return None
    container = containers[0]
    environment = sorted(
        (
            str(item.get("name") or ""),
            str(item.get("value") or ""),
            str(item.get("secretRef") or ""),
        )
        for item in container.get("env") or []
    )
    resources = container.get("resources") or {}
    try:
        cpu = float(resources.get("cpu"))
    except (TypeError, ValueError):
        return None
    return {
        "name": container.get("name"),
        "image": container.get("image"),
        "command": container.get("command") or [],
        "args": container.get("args") or [],
        "env": environment,
        "cpu": cpu,
        "memory": str(resources.get("memory") or "").replace(" ", ""),
    }

expected = signature(expected_template)
if expected is None:
    raise SystemExit("STOP: the generated privacy execution template is invalid")

active_states = {"Processing", "Running", "Unknown"}
terminal_failure_states = {"Degraded", "Failed", "Stopped"}
active = []
matching = []
for execution in executions:
    properties = execution.get("properties") or execution
    name = str(execution.get("name") or "")
    status = str(properties.get("status") or "")
    matches = signature(properties.get("template") or {}) == expected
    if status in active_states:
        active.append((name, matches))
    if matches:
        matching.append(
            (
                str(properties.get("startTime") or ""),
                name,
                status,
            )
        )

if len(active) > 1 or any(not matches for _, matches in active):
    raise SystemExit("STOP: another migration job execution is active")
if active:
    print(f"active|{active[0][0]}")
    raise SystemExit(0)
if not matching:
    print("new|")
    raise SystemExit(0)
_, name, status = max(matching)
if status == "Succeeded":
    print(f"succeeded|{name}")
elif status in terminal_failure_states:
    if failed_retry:
        print("new|")
    else:
        print(f"failed|{name}")
else:
    raise SystemExit("STOP: the matching privacy execution has an unknown state")
PY
}

abda_privacy_runner_source() {
  cat <<'PY'
from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from urllib.parse import quote


if not os.environ.get("ABDA_DATABASE_URL"):
    application_password = os.environ.pop("ABDA_DATABASE_APP_PASSWORD", "")
    postgres_host = os.environ.pop("ABDA_POSTGRES_HOST", "")
    if not application_password or not postgres_host.endswith(".postgres.database.azure.com"):
        raise SystemExit("privacy acceptance refused: application database input is unavailable")
    os.environ["ABDA_DATABASE_URL"] = (
        "postgresql+psycopg://abda_app:"
        + quote(application_password, safe="")
        + f"@{postgres_host}:5432/abda?sslmode=require"
    )
    application_password = ""
    postgres_host = ""

from sqlalchemy import func, select

from app.cli import privacy as privacy_cli
from app.db.models import MCPAccessToken, Project, ShareLink, TrialGrant, User
from app.db.session import get_session_factory
from app.services.privacy_requests import (
    inspect_privacy_account,
    validate_privacy_request_reference,
)


EMAIL_ENV = "ABDA_PRIVACY_USER_EMAIL"
CONFIRMATION_ENV = "ABDA_PRIVACY_CONFIRMATION"
PROJECT_NAME = "Privacy acceptance disposable"
TOKEN_NAME = "Privacy acceptance disposable"


def fail(message: str) -> None:
    raise SystemExit(f"privacy acceptance refused: {message}")


def cli_call(arguments: list[str], *, confirmation: str | None = None) -> dict:
    previous = os.environ.get(CONFIRMATION_ENV)
    if confirmation is None:
        os.environ.pop(CONFIRMATION_ENV, None)
    else:
        os.environ[CONFIRMATION_ENV] = confirmation
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = privacy_cli.main(arguments)
    finally:
        if previous is None:
            os.environ.pop(CONFIRMATION_ENV, None)
        else:
            os.environ[CONFIRMATION_ENV] = previous
    if status != 0:
        fail("the deployed privacy command refused the reviewed operation")
    try:
        return json.loads(stdout.getvalue())
    except json.JSONDecodeError:
        fail("the deployed privacy command returned an invalid receipt")


def active_share_count(session, user_id: str) -> int:
    project_ids = select(Project.id).where(Project.owner_user_id == user_id)
    return int(
        session.scalar(
            select(func.count(ShareLink.id)).where(
                ShareLink.project_id.in_(project_ids),
                ShareLink.revoked_at.is_(None),
            )
        )
        or 0
    )


def active_mcp_count(session, user_id: str) -> int:
    now = datetime.now(timezone.utc)
    return int(
        session.scalar(
            select(func.count(MCPAccessToken.id)).where(
                MCPAccessToken.user_id == user_id,
                MCPAccessToken.revoked_at.is_(None),
                MCPAccessToken.expires_at > now,
            )
        )
        or 0
    )


def validate_export(payload: dict, normalized_email: str) -> None:
    account = payload.get("account") or {}
    if account.get("email") != normalized_email or account.get("email_verified") is not True:
        fail("the private export did not contain the expected verified account")
    if not payload.get("projects") or not payload.get("mcp_tokens"):
        fail("the private export did not contain the disposable project and MCP metadata")
    forbidden = {
        "api_key",
        "cookie",
        "mcp_token_pepper",
        "provider_api_key",
        "session_secret",
        "share_token",
        "token_hash",
    }

    def visit(value):
        if isinstance(value, dict):
            if forbidden.intersection(value):
                fail("the private export contained a forbidden secret field")
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)


def prepared_age_seconds(updated_at: datetime) -> int:
    value = updated_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - value).total_seconds()))


if len(sys.argv) != 3 or sys.argv[1] not in {
    "prepare",
    "preflight-delete",
    "delete",
}:
    fail("the execution must select exactly one reviewed privacy phase")
action = sys.argv[1]
REFERENCE = validate_privacy_request_reference(sys.argv[2])

factory = get_session_factory()
with factory() as session:
    candidates = list(
        session.scalars(
            select(User)
            .join(Project, Project.owner_user_id == User.id)
            .join(MCPAccessToken, MCPAccessToken.user_id == User.id)
            .where(
                User.email_verified.is_(True),
                User.status.in_(("active", "deletion_pending")),
                Project.name == PROJECT_NAME,
                Project.archived_at.is_(None),
                MCPAccessToken.name == TOKEN_NAME,
            )
            .distinct()
        )
    )
    if len(candidates) != 1:
        fail("exactly one disposable account must match the reviewed project and credential names")
    user = candidates[0]
    user_id = user.id
    normalized = user.email
    status = user.status
    updated_at = user.updated_at
    has_trial = session.get(TrialGrant, user_id) is not None
    shares_before = active_share_count(session, user_id)
    mcp_before = active_mcp_count(session, user_id)

os.environ[EMAIL_ENV] = normalized
with factory() as session:
    summary = inspect_privacy_account(session, normalized)
if has_trial or any(
    (
        summary.trial_granted_microusd,
        summary.trial_spent_microusd,
        summary.trial_reserved_microusd,
        summary.trial_reservation_count,
        summary.llm_usage_event_count,
        summary.emergency_reservation_count,
    )
):
    fail("the selected disposable account activated trial credit or called a model")

if action == "prepare" and status == "active":
    if summary.active_project_count < 1 or shares_before < 1 or mcp_before < 1:
        fail("create one disposable project, active share, and active MCP credential first")
    inspected = cli_call(["inspect"])
    if inspected.get("mutated") is not False:
        fail("the inspection unexpectedly mutated data")
    export_root = Path(tempfile.mkdtemp(prefix="abda-privacy-acceptance-"))
    os.chmod(export_root, 0o700)
    export_path = export_root / "access.json"
    try:
        exported = cli_call(["export", "--output", str(export_path)])
        if exported.get("mutated") is not False or exported.get("output_mode") != "0600":
            fail("the private export receipt changed")
        if stat.S_IMODE(export_path.stat().st_mode) != 0o600:
            fail("the private export was not written with mode 600")
        validate_export(json.loads(export_path.read_text(encoding="utf-8")), normalized)
    finally:
        shutil.rmtree(export_root, ignore_errors=True)
    planned = cli_call(["prepare-delete", "--request-reference", REFERENCE])
    if planned.get("mutated") is not False:
        fail("the preparation dry run unexpectedly mutated data")
    prepared = cli_call(
        ["prepare-delete", "--request-reference", REFERENCE, "--execute"],
        confirmation=f"PREPARE:{REFERENCE}",
    )
    account = prepared.get("account") or {}
    if prepared.get("mutated") is not True or account.get("status") != "deletion_pending":
        fail("the preparation receipt changed")
    with factory() as session:
        if active_share_count(session, user_id) != 0 or active_mcp_count(session, user_id) != 0:
            fail("preparation did not revoke every active share and MCP credential")
    print("ABDA-NL Gate 11 privacy acceptance status:")
    print("phase: prepared")
    print(f"project_count: {summary.active_project_count + summary.archived_project_count}")
    print(f"revoked_share_count: {shares_before}")
    print(f"revoked_mcp_token_count: {mcp_before}")
    print("private_export_validated_and_removed: true")
    print("trial_credit_ever_activated: false")
    print("result: PRIVACY_ACCEPTANCE_PREPARED_WAIT_15_MINUTES")
elif action == "prepare" and status == "deletion_pending":
    if shares_before != 0 or mcp_before != 0:
        fail("the previously prepared account still has active bearer access")
    print("ABDA-NL Gate 11 privacy acceptance status:")
    print("phase: prepared")
    print("preparation_resumed: true")
    print("trial_credit_ever_activated: false")
    print("result: PRIVACY_ACCEPTANCE_PREPARED_WAIT_15_MINUTES")
elif action == "preflight-delete" and status == "deletion_pending":
    age = prepared_age_seconds(updated_at)
    if age < 900:
        fail(f"wait {900 - age} more seconds before permanent deletion")
    if shares_before != 0 or mcp_before != 0:
        fail("the prepared account still has active share or MCP access")
    if summary.pending_trial_reservation_count or summary.pending_emergency_reservation_count:
        fail("the prepared account has an unsettled model reservation")
    print("ABDA-NL Gate 11 privacy deletion preflight status:")
    print(f"prepare_hold_seconds: {age}")
    print("active_share_count: 0")
    print("active_mcp_token_count: 0")
    print("trial_credit_ever_activated: false")
    print("result: PRIVACY_DELETION_PREFLIGHT_VERIFIED")
elif action == "delete" and status == "deletion_pending":
    age = prepared_age_seconds(updated_at)
    if age < 900:
        fail(f"wait {900 - age} more seconds before permanent deletion")
    if shares_before != 0 or mcp_before != 0:
        fail("the prepared account still has active share or MCP access")
    if summary.pending_trial_reservation_count or summary.pending_emergency_reservation_count:
        fail("the prepared account has an unsettled model reservation")
    planned = cli_call(["delete", "--request-reference", REFERENCE])
    if planned.get("mutated") is not False:
        fail("the deletion dry run unexpectedly mutated data")
    deleted = cli_call(
        ["delete", "--request-reference", REFERENCE, "--execute"],
        confirmation=f"DELETE:{REFERENCE}",
    )
    receipt = deleted.get("receipt") or {}
    if deleted.get("mutated") is not True:
        fail("the deletion receipt changed")
    if any(
        int(receipt.get(name) or 0) < 1
        for name in (
            "deleted_identity_count",
            "deleted_project_count",
            "deleted_share_link_count",
            "deleted_mcp_token_count",
        )
    ):
        fail("the deletion receipt does not cover the disposable acceptance data")
    if any(
        int(receipt.get(name) or 0)
        for name in (
            "retained_trial_granted_microusd",
            "retained_trial_spent_microusd",
        )
    ):
        fail("the disposable account unexpectedly retained trial liability")
    print("ABDA-NL Gate 11 privacy acceptance status:")
    print("phase: deleted")
    print(f"deleted_identity_count: {receipt.get('deleted_identity_count')}")
    print(f"deleted_project_count: {receipt.get('deleted_project_count')}")
    print(f"deleted_share_link_count: {receipt.get('deleted_share_link_count')}")
    print(f"deleted_mcp_token_count: {receipt.get('deleted_mcp_token_count')}")
    print("private_export_removed: true")
    print("result: LIVE_PRIVACY_EXPORT_AND_DELETION_VERIFIED")
else:
    fail("the disposable account state does not match the confirmed privacy phase")

os.environ.pop(EMAIL_ENV, None)
PY
}

abda_privacy_run_job() {
  local runner_payload=$1
  local action=$2
  local template_path="$ABDA_PRIVACY_ROOT/privacy-execution.yaml"
  abda_privacy_write_job_template "$template_path" "$runner_payload" "$action"

  az containerapp job execution list \
    --name "$ABDA_MIGRATION_JOB_NAME" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_PRIVACY_ROOT/execution-list.json"
  abda_privacy_load_execution_details \
    "$ABDA_PRIVACY_ROOT/execution-list.json" \
    "$ABDA_PRIVACY_ROOT/executions-before.json" \
    "$ABDA_PRIVACY_ROOT/execution-details"
  local classification=''
  local failed_retry='false'
  if [[ "$action" == 'preflight-delete' ]]; then
    failed_retry='true'
  fi
  classification="$(abda_privacy_classify_executions \
    "$ABDA_PRIVACY_ROOT/executions-before.json" "$template_path" "$failed_retry")"
  local execution_phase=${classification%%|*}
  ABDA_PRIVACY_EXECUTION_NAME=${classification#*|}
  ABDA_PRIVACY_EXECUTION_RESUMED='false'

  case "$execution_phase" in
    new)
      az containerapp job start \
        --name "$ABDA_MIGRATION_JOB_NAME" \
        --resource-group "$ABDA_RESOURCE_GROUP" \
        --yaml "$template_path" \
        --output json >"$ABDA_PRIVACY_ROOT/execution-start.json"
      ABDA_PRIVACY_EXECUTION_NAME="$(python3 - \
        "$ABDA_PRIVACY_ROOT/execution-start.json" "$ABDA_MIGRATION_JOB_NAME" <<'PY'
import json
import re
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    response = json.load(handle)
name = str(response.get("name") or "")
if not re.fullmatch(re.escape(sys.argv[2]) + r"-[a-z0-9]+", name):
    raise SystemExit("STOP: Azure returned an invalid privacy job execution name")
print(name)
PY
)"
      ;;
    active)
      ABDA_PRIVACY_EXECUTION_RESUMED='true'
      printf 'Resuming the exact in-progress privacy job execution.\n'
      ;;
    succeeded)
      ABDA_PRIVACY_EXECUTION_RESUMED='true'
      printf 'The exact privacy job execution already succeeded. No new execution was started.\n'
      ;;
    failed)
      abda_privacy_fail \
        'an exact prior mutating privacy job execution failed; inspect it before any retry'
      ;;
    *)
      abda_privacy_fail 'the privacy job execution classification was invalid'
      ;;
  esac
  [[ -n "$ABDA_PRIVACY_EXECUTION_NAME" ]] || \
    abda_privacy_fail 'Azure did not return a privacy job execution name'
  printf 'privacy_job_execution: %s\n' "$ABDA_PRIVACY_EXECUTION_NAME"

  if [[ "$execution_phase" == 'succeeded' ]]; then
    ABDA_PRIVACY_EXECUTION_STATE='Succeeded'
    return 0
  fi

  local attempt=0
  local last_state=''
  ABDA_PRIVACY_EXECUTION_STATE=''
  for (( attempt=1; attempt<=120; attempt++ )); do
    if ABDA_PRIVACY_EXECUTION_STATE="$(az containerapp job execution show \
      --name "$ABDA_MIGRATION_JOB_NAME" \
      --resource-group "$ABDA_RESOURCE_GROUP" \
      --job-execution-name "$ABDA_PRIVACY_EXECUTION_NAME" \
      --query properties.status --output tsv 2>/dev/null)"; then
      if [[ "$ABDA_PRIVACY_EXECUTION_STATE" != "$last_state" ]]; then
        printf 'privacy_job_state: %s\n' "$ABDA_PRIVACY_EXECUTION_STATE"
        last_state=$ABDA_PRIVACY_EXECUTION_STATE
      fi
      case "$ABDA_PRIVACY_EXECUTION_STATE" in
        Succeeded)
          return 0
          ;;
        Degraded|Failed|Stopped)
          abda_privacy_fail \
            "privacy job execution ended in state $ABDA_PRIVACY_EXECUTION_STATE"
          ;;
      esac
    fi
    sleep 5
  done
  abda_privacy_fail 'privacy job execution did not reach a terminal state in ten minutes'
}

abda_privacy_main() {
  set -Eeuo pipefail
  set +x
  umask 077
  unset HISTFILE
  trap abda_privacy_error ERR
  trap abda_privacy_cleanup EXIT
  trap abda_privacy_interrupt INT
  ABDA_PRIVACY_SECTION='bootstrap'

  printf 'ABDA-NL Gate 11 privacy acceptance script revision: %s\n' \
    "$ABDA_PRIVACY_SCRIPT_REVISION"
  printf '%s\n' \
    'This gate validates export, suspension, access revocation, and permanent deletion.' \
    'It is destructive only to one disposable staging account after exact confirmations.' \
    'It uses one or two execution-only overrides of the existing manual migration job.' \
    'It never changes Azure configuration, Auth0, trial limits, or provider routing.'

  abda_privacy_set_constants
  local command_name=''
  for command_name in az base64 curl grep python3 tr; do
    command -v "$command_name" >/dev/null 2>&1 || \
      abda_privacy_fail "required command is unavailable: $command_name"
  done
  [[ -t 0 ]] || abda_privacy_fail 'Gate 11 requires an interactive Cloud Shell terminal'
  ABDA_PRIVACY_ROOT="$(mktemp -d /tmp/abda-nl-gate11-privacy.XXXXXX)"
  chmod 700 "$ABDA_PRIVACY_ROOT"
  az containerapp job start --help >"$ABDA_PRIVACY_ROOT/containerapp-job-start.help"
  for option in --name --resource-group --yaml; do
    grep -Fq -- "$option" "$ABDA_PRIVACY_ROOT/containerapp-job-start.help" || \
      abda_privacy_fail "az containerapp job start does not support $option"
  done

  ABDA_PRIVACY_SECTION='Azure identity verification'
  printf '\n[1/6] Verifying the exact Azure identity...\n'
  az account show --output json >"$ABDA_PRIVACY_ROOT/account.json"
  abda_privacy_validate_identity "$ABDA_PRIVACY_ROOT/account.json"
  az account show \
    --query '{Name:name,TenantId:tenantId,User:user.name,State:state}' \
    --output table

  ABDA_PRIVACY_SECTION='approved application and job verification'
  printf '\n[2/6] Verifying the exact approved application and manual job...\n'
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_PRIVACY_ROOT/app.json"
  abda_privacy_validate_app "$ABDA_PRIVACY_ROOT/app.json"
  az containerapp job show \
    --name "$ABDA_MIGRATION_JOB_NAME" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_PRIVACY_ROOT/job-before.json"
  abda_privacy_validate_job "$ABDA_PRIVACY_ROOT/job-before.json"
  printf 'application_revision: %s\n' "$ABDA_PRIVACY_EXPECTED_REVISION"
  printf 'manual_job: %s\n' "$ABDA_MIGRATION_JOB_NAME"

  ABDA_PRIVACY_SECTION='public readiness verification'
  printf '\n[3/6] Rechecking public readiness...\n'
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_PUBLIC_ORIGIN/health/ready" \
    --output "$ABDA_PRIVACY_ROOT/ready.json"
  python3 - "$ABDA_PRIVACY_ROOT/ready.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    if json.load(handle) != {"status": "ready"}:
        raise SystemExit("STOP: the public origin is not ready")
PY

  ABDA_PRIVACY_SECTION='operator confirmation'
  printf '\n[4/6] Awaiting the disposable-account confirmation...\n'
  printf '%s\n' \
    'Before continuing, the exact disposable Auth0 user must be blocked.' \
    'On the first run, it must contain the exact disposable project, active share, and MCP token.' \
    'On the second run, keep the prepared account and Auth0 user unchanged.' \
    'It must never have activated trial credit or called a model.' \
    'Type RUN_ABDA_PRIVACY_ACCEPTANCE to continue, or press Enter to cancel.'
  local confirmation=''
  IFS= read -r -p 'Confirmation: ' confirmation
  if [[ "$confirmation" != 'RUN_ABDA_PRIVACY_ACCEPTANCE' ]]; then
    printf 'Cancelled without changing application data.\n'
    return 0
  fi

  printf '%s\n' \
    'For the first run, type PREPARE_PRIVACY_ACCEPTANCE.' \
    'After its successful receipt and a wait of at least 15 minutes, type DELETE_PRIVACY_ACCEPTANCE.'
  local phase_confirmation=''
  local privacy_action=''
  IFS= read -r -p 'Privacy phase: ' phase_confirmation
  case "$phase_confirmation" in
    PREPARE_PRIVACY_ACCEPTANCE)
      privacy_action='prepare'
      ;;
    DELETE_PRIVACY_ACCEPTANCE)
      privacy_action='delete'
      ;;
    *)
      printf 'Cancelled without changing application data.\n'
      return 0
      ;;
  esac

  ABDA_PRIVACY_SECTION='isolated privacy workflow execution'
  printf '\n[5/6] Running the privacy workflow as isolated manual job executions...\n'
  printf '%s\n' \
    'The runner selects exactly one account by the two disposable object names.' \
    'No email address is entered in the terminal or stored in the execution template.' \
    'The web application is not restarted and the migration command is not run.'
  local runner_payload=''
  runner_payload="$(abda_privacy_runner_source | base64 | tr -d '\n')"
  [[ -n "$runner_payload" ]] || abda_privacy_fail 'the privacy runner payload is empty'
  local preflight_execution_name=''
  local preflight_execution_state=''
  if [[ "$privacy_action" == 'delete' ]]; then
    printf 'Running a read-only database-state and 15-minute-hold preflight first.\n'
    abda_privacy_run_job "$runner_payload" preflight-delete
    preflight_execution_name=$ABDA_PRIVACY_EXECUTION_NAME
    preflight_execution_state=$ABDA_PRIVACY_EXECUTION_STATE
    [[ "$preflight_execution_state" == 'Succeeded' ]] || \
      abda_privacy_fail 'the deletion preflight did not succeed'
  fi
  abda_privacy_run_job "$runner_payload" "$privacy_action"

  ABDA_PRIVACY_SECTION='content-free receipt verification'
  printf '\n[6/6] Verifying the content-free privacy receipt...\n'
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_PUBLIC_ORIGIN/health/ready" \
    --output "$ABDA_PRIVACY_ROOT/final-ready.json"
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_PRIVACY_ROOT/final-app.json"
  abda_privacy_validate_app "$ABDA_PRIVACY_ROOT/final-app.json"
  az containerapp job show \
    --name "$ABDA_MIGRATION_JOB_NAME" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_PRIVACY_ROOT/job-after.json"
  abda_privacy_validate_job "$ABDA_PRIVACY_ROOT/job-after.json"
  abda_privacy_compare_job_configuration \
    "$ABDA_PRIVACY_ROOT/job-before.json" "$ABDA_PRIVACY_ROOT/job-after.json"

  printf '\nABDA-NL Gate 11 wrapper status:\n'
  printf 'script_revision: %s\n' "$ABDA_PRIVACY_SCRIPT_REVISION"
  printf 'application_source_commit: %s\n' \
    "$ABDA_PRIVACY_APPLICATION_SOURCE_COMMIT"
  printf 'image_digest: sha256:%s\n' "$ABDA_PRIVACY_IMAGE_SHA256"
  printf 'subscription_id: %s\n' "$ABDA_EXPECTED_SUBSCRIPTION"
  printf 'resource_group: %s\n' "$ABDA_RESOURCE_GROUP"
  printf 'application_revision: %s\n' "$ABDA_PRIVACY_EXPECTED_REVISION"
  printf 'public_origin: %s\n' "$ABDA_PUBLIC_ORIGIN"
  printf 'privacy_job: %s\n' "$ABDA_MIGRATION_JOB_NAME"
  printf 'privacy_job_execution: %s\n' "$ABDA_PRIVACY_EXECUTION_NAME"
  printf 'privacy_job_execution_state: %s\n' "$ABDA_PRIVACY_EXECUTION_STATE"
  printf 'privacy_job_execution_resumed: %s\n' "$ABDA_PRIVACY_EXECUTION_RESUMED"
  if [[ "$privacy_action" == 'delete' ]]; then
    printf 'privacy_preflight_execution: %s\n' "$preflight_execution_name"
    printf 'privacy_preflight_execution_state: %s\n' "$preflight_execution_state"
  fi
  printf 'job_configuration_changed: false\n'
  printf 'application_changed: false\n'
  printf 'email_entered_in_terminal: false\n'
  printf 'model_provider_called: false\n'
  if [[ "$privacy_action" == 'prepare' ]]; then
    printf 'result: PRIVACY_ACCEPTANCE_PREPARED_WAIT_15_MINUTES\n'
    printf '%s\n' \
      'Keep the Auth0 user blocked. Wait at least 15 minutes, then rerun this exact gate.'
  else
    printf 'result: LIVE_PRIVACY_EXPORT_AND_DELETION_VERIFIED\n'
    printf '%s\n' \
      'Delete the still-blocked disposable user from Auth0, then send this status to Codex.'
  fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_privacy_main "$@"
fi
