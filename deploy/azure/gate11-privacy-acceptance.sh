#!/usr/bin/env bash

# Exercise the deployed privacy export and two-phase deletion workflow against
# one disposable, blocked staging account. The gate changes application data
# only after an exact phase-specific confirmation. It never changes Azure
# configuration, Auth0, DNS, secrets, trial settings, or provider routing.

ABDA_PRIVACY_SCRIPT_REVISION='1'
ABDA_PRIVACY_APPLICATION_SOURCE_COMMIT='6d0fb4403c01b37d101f0d03bd9c3070b8f1e343'
ABDA_PRIVACY_IMAGE_SHA256='282a2cb13cbdabe7f60a7efaa41c5fded7b1a4efeb467cc758064c7cadf30f13'
ABDA_PRIVACY_EXPECTED_REVISION='abda-nl-stg-web--restore-6d0fb44'
ABDA_PRIVACY_REQUEST_REFERENCE='PRIV-ACCEPT-20260829-01'
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
  ABDA_CONTAINER_NAME='web'
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
    raise SystemExit("STOP: run and verify Gate 10 before Gate 11")
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

abda_privacy_select_replica() {
  local path=$1
  python3 - "$path" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    replicas = json.load(handle)
ready = []
for replica in replicas if isinstance(replicas, list) else []:
    properties = replica.get("properties") or {}
    containers = properties.get("containers") or []
    if (
        properties.get("runningState") == "Running"
        and containers
        and all(item.get("ready") is True for item in containers)
    ):
        ready.append(str(replica.get("name") or ""))
if not ready or not ready[0]:
    raise SystemExit("STOP: no ready staging replica is available")
print(sorted(ready)[0])
PY
}

abda_privacy_runner_source() {
  cat <<'PY'
from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import getpass
import io
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

from sqlalchemy import func, select

from app.cli import privacy as privacy_cli
from app.db.models import MCPAccessToken, Project, ShareLink, TrialGrant, User
from app.db.session import get_session_factory
from app.services.accounts import normalize_email
from app.services.privacy_requests import inspect_privacy_account


REFERENCE = "PRIV-ACCEPT-20260829-01"
EMAIL_ENV = "ABDA_PRIVACY_USER_EMAIL"
CONFIRMATION_ENV = "ABDA_PRIVACY_CONFIRMATION"


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


email = getpass.getpass("Verified disposable ABDA-NL account email: ")
try:
    normalized = normalize_email(email)
except Exception:
    fail("enter a valid verified email address")
email = ""
os.environ[EMAIL_ENV] = normalized

factory = get_session_factory()
with factory() as session:
    user = session.scalar(select(User).where(User.email == normalized))
    if user is None:
        fail("the disposable account does not exist in ABDA-NL")
    if user.email_verified is not True:
        fail("the disposable account is not verified")
    user_id = user.id
    status = user.status
    updated_at = user.updated_at
    has_trial = session.get(TrialGrant, user_id) is not None
    shares_before = active_share_count(session, user_id)
    mcp_before = active_mcp_count(session, user_id)

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
    fail("use an isolated account that has never activated trial credit or called a model")

if status == "active":
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
    confirmation = input("Type PREPARE_PRIVACY_ACCEPTANCE to suspend and revoke the disposable account: ")
    if confirmation != "PREPARE_PRIVACY_ACCEPTANCE":
        fail("preparation was cancelled without changing the account")
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
    print(f"account_fingerprint: {account.get('account_fingerprint')}")
    print(f"project_count: {summary.active_project_count + summary.archived_project_count}")
    print(f"revoked_share_count: {shares_before}")
    print(f"revoked_mcp_token_count: {mcp_before}")
    print("private_export_validated_and_removed: true")
    print("trial_credit_ever_activated: false")
    print("result: PRIVACY_ACCEPTANCE_PREPARED_WAIT_15_MINUTES")
elif status == "deletion_pending":
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
    confirmation = input("Type DELETE_PRIVACY_ACCEPTANCE to permanently delete local disposable data: ")
    if confirmation != "DELETE_PRIVACY_ACCEPTANCE":
        fail("deletion was cancelled without changing the prepared account")
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
    with factory() as session:
        if session.scalar(select(User.id).where(User.id == user_id)) is not None:
            fail("the local disposable account still exists after deletion")
    print("ABDA-NL Gate 11 privacy acceptance status:")
    print("phase: deleted")
    print(f"account_fingerprint: {receipt.get('deleted_account_fingerprint')}")
    print(f"deleted_identity_count: {receipt.get('deleted_identity_count')}")
    print(f"deleted_project_count: {receipt.get('deleted_project_count')}")
    print(f"deleted_share_link_count: {receipt.get('deleted_share_link_count')}")
    print(f"deleted_mcp_token_count: {receipt.get('deleted_mcp_token_count')}")
    print("private_export_removed: true")
    print("result: LIVE_PRIVACY_EXPORT_AND_DELETION_VERIFIED")
else:
    fail("the disposable account is not active or deletion_pending")

os.environ.pop(EMAIL_ENV, None)
PY
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
    'It never changes Azure configuration, Auth0, trial limits, or provider routing.'

  abda_privacy_set_constants
  local command_name=''
  for command_name in az base64 curl grep python3 tee tr; do
    command -v "$command_name" >/dev/null 2>&1 || \
      abda_privacy_fail "required command is unavailable: $command_name"
  done
  [[ -t 0 ]] || abda_privacy_fail 'Gate 11 requires an interactive Cloud Shell terminal'
  ABDA_PRIVACY_ROOT="$(mktemp -d /tmp/abda-nl-gate11-privacy.XXXXXX)"
  chmod 700 "$ABDA_PRIVACY_ROOT"
  az containerapp exec --help >"$ABDA_PRIVACY_ROOT/containerapp-exec.help"
  for option in --name --resource-group --revision --replica --container --command; do
    grep -Fq -- "$option" "$ABDA_PRIVACY_ROOT/containerapp-exec.help" || \
      abda_privacy_fail "az containerapp exec does not support $option"
  done

  ABDA_PRIVACY_SECTION='Azure identity verification'
  printf '\n[1/6] Verifying the exact Azure identity...\n'
  az account show --output json >"$ABDA_PRIVACY_ROOT/account.json"
  abda_privacy_validate_identity "$ABDA_PRIVACY_ROOT/account.json"
  az account show \
    --query '{Name:name,TenantId:tenantId,User:user.name,State:state}' \
    --output table

  ABDA_PRIVACY_SECTION='restored release verification'
  printf '\n[2/6] Verifying the exact post-rollback application...\n'
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_PRIVACY_ROOT/app.json"
  abda_privacy_validate_app "$ABDA_PRIVACY_ROOT/app.json"
  az containerapp replica list \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --revision "$ABDA_PRIVACY_EXPECTED_REVISION" --output json \
    >"$ABDA_PRIVACY_ROOT/replicas.json"
  local replica_name=''
  replica_name="$(abda_privacy_select_replica "$ABDA_PRIVACY_ROOT/replicas.json")"
  printf 'application_revision: %s\n' "$ABDA_PRIVACY_EXPECTED_REVISION"
  printf 'selected_ready_replica: %s\n' "$replica_name"

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
    'The account must contain one disposable project, active share, and active MCP token.' \
    'It must never have activated trial credit or called a model.' \
    'Type RUN_ABDA_PRIVACY_ACCEPTANCE to continue, or press Enter to cancel.'
  local confirmation=''
  IFS= read -r -p 'Confirmation: ' confirmation
  if [[ "$confirmation" != 'RUN_ABDA_PRIVACY_ACCEPTANCE' ]]; then
    printf 'Cancelled without changing application data.\n'
    return 0
  fi

  ABDA_PRIVACY_SECTION='isolated privacy workflow execution'
  printf '\n[5/6] Running the privacy workflow inside the exact healthy replica...\n'
  printf '%s\n' \
    'Enter only the blocked disposable account email at the hidden prompt.' \
    'The runner will select preparation or deletion from the current database state.'
  local runner_payload=''
  runner_payload="$(abda_privacy_runner_source | base64 | tr -d '\n')"
  [[ -n "$runner_payload" ]] || abda_privacy_fail 'the privacy runner payload is empty'
  local exec_status=0
  set +e
  az containerapp exec \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --revision "$ABDA_PRIVACY_EXPECTED_REVISION" --replica "$replica_name" \
    --container "$ABDA_CONTAINER_NAME" \
    --command "/opt/venv/bin/python -c \"import base64;exec(compile(base64.b64decode('$runner_payload'),'<privacy-acceptance>','exec'))\"" \
    2>&1 | tee "$ABDA_PRIVACY_ROOT/container-exec.log"
  exec_status=${PIPESTATUS[0]}
  set -e
  (( exec_status == 0 )) || \
    abda_privacy_fail "Azure container exec exited with status $exec_status"

  ABDA_PRIVACY_SECTION='content-free receipt verification'
  printf '\n[6/6] Verifying the content-free privacy receipt...\n'
  local prepared_count=0
  local deleted_count=0
  prepared_count="$(grep -Fc \
    'result: PRIVACY_ACCEPTANCE_PREPARED_WAIT_15_MINUTES' \
    "$ABDA_PRIVACY_ROOT/container-exec.log" || true)"
  deleted_count="$(grep -Fc \
    'result: LIVE_PRIVACY_EXPORT_AND_DELETION_VERIFIED' \
    "$ABDA_PRIVACY_ROOT/container-exec.log" || true)"
  if (( prepared_count + deleted_count != 1 )); then
    abda_privacy_fail 'the container output did not contain exactly one privacy acceptance receipt'
  fi
  if grep -Eiq '(api[_ -]?key|bearer|client[_ -]?secret|token_hash)[[:space:]]*[:=][[:space:]]*[^[:space:]]+' \
      "$ABDA_PRIVACY_ROOT/container-exec.log"; then
    abda_privacy_fail 'the container output may contain secret material'
  fi
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_PUBLIC_ORIGIN/health/ready" \
    --output "$ABDA_PRIVACY_ROOT/final-ready.json"
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_PRIVACY_ROOT/final-app.json"
  abda_privacy_validate_app "$ABDA_PRIVACY_ROOT/final-app.json"

  printf '\nABDA-NL Gate 11 wrapper status:\n'
  printf 'script_revision: %s\n' "$ABDA_PRIVACY_SCRIPT_REVISION"
  printf 'application_source_commit: %s\n' \
    "$ABDA_PRIVACY_APPLICATION_SOURCE_COMMIT"
  printf 'image_digest: sha256:%s\n' "$ABDA_PRIVACY_IMAGE_SHA256"
  printf 'subscription_id: %s\n' "$ABDA_EXPECTED_SUBSCRIPTION"
  printf 'resource_group: %s\n' "$ABDA_RESOURCE_GROUP"
  printf 'application_revision: %s\n' "$ABDA_PRIVACY_EXPECTED_REVISION"
  printf 'public_origin: %s\n' "$ABDA_PUBLIC_ORIGIN"
  if (( prepared_count == 1 )); then
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
