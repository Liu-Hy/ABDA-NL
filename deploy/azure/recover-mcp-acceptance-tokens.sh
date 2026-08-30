#!/usr/bin/env bash

# Revoke only the two disposable MCP acceptance credentials when the public
# revocation endpoint is temporarily blocked by its legacy shared rate limit.

ABDA_MCP_RECOVERY_SCRIPT_REVISION='1'
ABDA_MCP_RECOVERY_EXPECTED_REVISION='abda-nl-stg-web--mcp-c55aa0d'
ABDA_MCP_RECOVERY_IMAGE_SHA256='2df0bf98401adb6f72d1b930d83ab68bd2466de756b0bead3864f3d41d30b9d0'
ABDA_MCP_RECOVERY_ROOT=''

abda_mcp_recovery_cleanup() {
  local exit_code=$?
  set +e
  if [[ "${ABDA_MCP_RECOVERY_ROOT:-}" == /tmp/abda-nl-mcp-recovery.* &&
        -d "${ABDA_MCP_RECOVERY_ROOT:-}" ]]; then
    rm -rf -- "$ABDA_MCP_RECOVERY_ROOT"
  fi
  printf '\nMCP acceptance token recovery shell exit code: %s\n' "$exit_code"
}

abda_mcp_recovery_error() {
  local exit_code=$?
  trap - ERR
  printf '\nSTOP: MCP acceptance token recovery failed in section: %s\n' \
    "${ABDA_MCP_RECOVERY_SECTION:-unknown}" >&2
  printf '%s\n' \
    'No Azure configuration was changed.' \
    'Do not tell the waiting Gate that the tokens are revoked.' >&2
  exit "$exit_code"
}

abda_mcp_recovery_fail() {
  printf 'STOP: %s\n' "$*" >&2
  return 1
}

abda_mcp_recovery_set_constants() {
  ABDA_EXPECTED_SUBSCRIPTION='00e62f6e-2174-40b2-b428-8ebfd7c2ac54'
  ABDA_EXPECTED_TENANT='040f05eb-33ab-462f-af54-fb4bedb055ae'
  ABDA_EXPECTED_USER='hliu2@cloudbank.org'
  ABDA_RESOURCE_GROUP='abda-nl-staging'
  ABDA_APP_NAME='abda-nl-stg-web'
  ABDA_CONTAINER_NAME='web'
  ABDA_IMAGE_REPOSITORY='ghcr.io/liu-hy/abda-nl'
}

abda_mcp_recovery_validate_identity() {
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

abda_mcp_recovery_validate_app() {
  local path=$1
  python3 - "$path" "$ABDA_APP_NAME" "$ABDA_MCP_RECOVERY_EXPECTED_REVISION" \
    "$ABDA_IMAGE_REPOSITORY@sha256:$ABDA_MCP_RECOVERY_IMAGE_SHA256" <<'PY'
import json
import sys

path, expected_app, expected_revision, expected_image = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    app = json.load(handle)
properties = app.get("properties") or {}
template = properties.get("template") or {}
containers = template.get("containers") or []
if app.get("name") != expected_app or len(containers) != 1:
    raise SystemExit("STOP: the Container App identity or container count changed")
if properties.get("provisioningState") != "Succeeded":
    raise SystemExit("STOP: the Container App provisioning state is not Succeeded")
if properties.get("runningStatus") != "Running":
    raise SystemExit("STOP: the Container App is not running")
if properties.get("latestReadyRevisionName") != expected_revision:
    raise SystemExit("STOP: the ready application revision changed")
if containers[0].get("name") != "web" or containers[0].get("image") != expected_image:
    raise SystemExit("STOP: the deployed application image changed")
PY
}

abda_mcp_recovery_select_replica() {
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

abda_mcp_recovery_runner_source() {
  cat <<'PY'
from __future__ import annotations

from collections import Counter
import getpass

from sqlalchemy import func, select

from app.db.models import MCPAccessToken, User, utc_now
from app.db.session import get_session_factory
from app.services.accounts import normalize_email


TOKEN_NAMES = (
    "MCP scope read acceptance",
    "MCP scoped write acceptance",
)
CONFIRMATION = "REVOKE_TWO_MCP_ACCEPTANCE_TOKENS"


def fail(message: str) -> None:
    raise SystemExit(f"acceptance token recovery refused: {message}")


email = normalize_email(
    getpass.getpass("Verified email for the waiting MCP acceptance Gate: ")
)
if not email:
    fail("the verified email is empty")

factory = get_session_factory()
with factory() as session:
    users = list(
        session.scalars(
            select(User).where(func.lower(User.email) == email.lower()).limit(2)
        )
    )
    if len(users) != 1:
        fail("the verified account was not found uniquely")
    user = users[0]
    active = list(
        session.scalars(
            select(MCPAccessToken).where(
                MCPAccessToken.user_id == user.id,
                MCPAccessToken.name.in_(TOKEN_NAMES),
                MCPAccessToken.revoked_at.is_(None),
            )
        )
    )
    counts = Counter(item.name for item in active)
    if any(counts[name] > 1 for name in TOKEN_NAMES):
        fail("more than one active credential has the same acceptance name")
    if any(item.name not in TOKEN_NAMES for item in active):
        fail("the active credential selection escaped the reviewed names")

    print(f"matching_active_acceptance_tokens: {len(active)}")
    if not active:
        print("result: MCP_ACCEPTANCE_TOKENS_ALREADY_REVOKED")
        raise SystemExit(0)

    typed = input(
        "Type REVOKE_TWO_MCP_ACCEPTANCE_TOKENS to revoke only the matching "
        "acceptance credentials: "
    )
    if typed != CONFIRMATION:
        fail("the exact revocation confirmation was not entered")

    revoked_at = utc_now()
    for record in active:
        record.revoked_at = revoked_at
    session.commit()

    remaining = int(
        session.scalar(
            select(func.count(MCPAccessToken.id)).where(
                MCPAccessToken.user_id == user.id,
                MCPAccessToken.name.in_(TOKEN_NAMES),
                MCPAccessToken.revoked_at.is_(None),
            )
        )
        or 0
    )
    if remaining != 0:
        fail("one or more matching acceptance credentials remain active")

print(f"revoked_acceptance_tokens: {len(active)}")
print("unrelated_credentials_changed: false")
print("rate_limit_buckets_changed: false")
print("result: MCP_ACCEPTANCE_TOKENS_REVOKED")
PY
}

abda_mcp_recovery_main() {
  set -Eeuo pipefail
  set +x
  umask 077
  unset HISTFILE
  trap abda_mcp_recovery_error ERR
  trap abda_mcp_recovery_cleanup EXIT
  ABDA_MCP_RECOVERY_SECTION='bootstrap'
  abda_mcp_recovery_set_constants

  printf 'ABDA-NL MCP acceptance token recovery revision: %s\n' \
    "$ABDA_MCP_RECOVERY_SCRIPT_REVISION"
  printf '%s\n' \
    'This recovery revokes only active credentials with the two exact acceptance names.' \
    'It does not clear rate limits, print tokens or email, or change Azure configuration.'

  local command_name=''
  for command_name in az base64 python3 tee tr; do
    command -v "$command_name" >/dev/null 2>&1 || \
      abda_mcp_recovery_fail "required command is unavailable: $command_name"
  done
  [[ -t 0 ]] || abda_mcp_recovery_fail 'an interactive Azure Cloud Shell is required'
  ABDA_MCP_RECOVERY_ROOT="$(mktemp -d /tmp/abda-nl-mcp-recovery.XXXXXX)"
  chmod 700 "$ABDA_MCP_RECOVERY_ROOT"

  ABDA_MCP_RECOVERY_SECTION='Azure identity verification'
  printf '\n[1/4] Verifying the exact Azure identity...\n'
  az account show --output json >"$ABDA_MCP_RECOVERY_ROOT/account.json"
  abda_mcp_recovery_validate_identity "$ABDA_MCP_RECOVERY_ROOT/account.json"
  az account show \
    --query '{Name:name,TenantId:tenantId,User:user.name,State:state}' \
    --output table

  ABDA_MCP_RECOVERY_SECTION='application and replica verification'
  printf '\n[2/4] Verifying the exact application image and a ready replica...\n'
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_MCP_RECOVERY_ROOT/app.json"
  abda_mcp_recovery_validate_app "$ABDA_MCP_RECOVERY_ROOT/app.json"
  az containerapp replica list \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --revision "$ABDA_MCP_RECOVERY_EXPECTED_REVISION" --output json \
    >"$ABDA_MCP_RECOVERY_ROOT/replicas.json"
  local replica_name=''
  replica_name="$(abda_mcp_recovery_select_replica "$ABDA_MCP_RECOVERY_ROOT/replicas.json")"
  printf 'application_revision: %s\n' "$ABDA_MCP_RECOVERY_EXPECTED_REVISION"
  printf 'selected_ready_replica: %s\n' "$replica_name"

  ABDA_MCP_RECOVERY_SECTION='bounded database revocation'
  printf '\n[3/4] Running the exact-name revocation inside the ready replica...\n'
  printf '%s\n' \
    'Enter the verified email used by the waiting Gate at the hidden prompt.' \
    'No email address, token, token identifier, or token hash will be printed.'
  local runner_payload=''
  runner_payload="$(abda_mcp_recovery_runner_source | base64 | tr -d '\n')"
  local exec_status=0
  set +e
  az containerapp exec \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --revision "$ABDA_MCP_RECOVERY_EXPECTED_REVISION" --replica "$replica_name" \
    --container "$ABDA_CONTAINER_NAME" \
    --command "/opt/venv/bin/python -c \"import base64;exec(compile(base64.b64decode('$runner_payload'),'<mcp-acceptance-recovery>','exec'))\"" \
    2>&1 | tee "$ABDA_MCP_RECOVERY_ROOT/container-exec.log"
  exec_status=${PIPESTATUS[0]}
  set -e
  (( exec_status == 0 )) || \
    abda_mcp_recovery_fail "Azure container exec exited with status $exec_status"

  ABDA_MCP_RECOVERY_SECTION='content-free receipt verification'
  printf '\n[4/4] Verifying the content-free recovery receipt...\n'
  local receipt_count=0
  receipt_count="$(grep -Ec \
    'result: MCP_ACCEPTANCE_TOKENS_(REVOKED|ALREADY_REVOKED)' \
    "$ABDA_MCP_RECOVERY_ROOT/container-exec.log" || true)"
  (( receipt_count == 1 )) || \
    abda_mcp_recovery_fail 'the container output did not contain exactly one recovery receipt'

  printf '\nABDA-NL MCP acceptance token recovery status:\n'
  printf 'script_revision: %s\n' "$ABDA_MCP_RECOVERY_SCRIPT_REVISION"
  printf 'application_revision: %s\n' "$ABDA_MCP_RECOVERY_EXPECTED_REVISION"
  printf 'acceptance_credentials_active: false\n'
  printf 'unrelated_credentials_changed: false\n'
  printf 'rate_limit_buckets_changed: false\n'
  printf 'azure_configuration_changed: false\n'
  printf 'result: MCP_ACCEPTANCE_TOKEN_RECOVERY_VERIFIED\n'
  printf '%s\n' \
    'Return to the waiting Gate, type TOKENS_REVOKED, and send its final receipt to Codex.'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_mcp_recovery_main "$@"
fi
