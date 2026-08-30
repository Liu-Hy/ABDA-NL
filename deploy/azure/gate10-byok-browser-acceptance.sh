#!/usr/bin/env bash

# Validate one real browser BYOK request against the current staging image.
# The provider key is entered only in the browser and never enters this script.
# The gate reads application, database, and count-only Log Analytics evidence.

ABDA_BYOK_SCRIPT_REVISION='1'
ABDA_BYOK_APPLICATION_SOURCE_COMMIT='c55aa0d67562d2a08ea4fa158aab262e432ddb88'
ABDA_BYOK_IMAGE_SHA256='2df0bf98401adb6f72d1b930d83ab68bd2466de756b0bead3864f3d41d30b9d0'
ABDA_BYOK_EXPECTED_REVISION='abda-nl-stg-web--mcp-c55aa0d'
ABDA_BYOK_ROOT=''

abda_byok_cleanup() {
  local exit_code=$?
  set +e
  if [[ "${ABDA_BYOK_ROOT:-}" == /tmp/abda-nl-gate10-byok.* &&
        -d "${ABDA_BYOK_ROOT:-}" ]]; then
    rm -rf -- "$ABDA_BYOK_ROOT"
  fi
  printf '\nBYOK acceptance shell exit code: %s\n' "$exit_code"
}

abda_byok_error() {
  local exit_code=$?
  trap - ERR
  printf '\nSTOP: BYOK acceptance failed in section: %s\n' \
    "${ABDA_BYOK_SECTION:-unknown}" >&2
  printf '%s\n' \
    'Do not paste a provider key into the terminal or send it to Codex.' \
    'No Azure configuration was changed. Send only the visible section and exit code.' >&2
  exit "$exit_code"
}

abda_byok_interrupt() {
  trap - ERR INT
  printf '\nSTOP: BYOK acceptance was interrupted in section: %s\n' \
    "${ABDA_BYOK_SECTION:-unknown}" >&2
  printf '%s\n' \
    'Clear the browser key, sign out, and send only this visible section to Codex.' >&2
  exit 130
}

abda_byok_fail() {
  printf 'STOP: %s\n' "$*" >&2
  return 1
}

abda_byok_set_constants() {
  ABDA_EXPECTED_SUBSCRIPTION='00e62f6e-2174-40b2-b428-8ebfd7c2ac54'
  ABDA_EXPECTED_TENANT='040f05eb-33ab-462f-af54-fb4bedb055ae'
  ABDA_EXPECTED_USER='hliu2@cloudbank.org'
  ABDA_RESOURCE_GROUP='abda-nl-staging'
  ABDA_APP_NAME='abda-nl-stg-web'
  ABDA_CONTAINER_NAME='web'
  ABDA_ENVIRONMENT_NAME='abda-nl-stg-environment'
  ABDA_LOGS_NAME='abda-nl-stg-logs-bgjhpbgw'
  ABDA_IMAGE_REPOSITORY='ghcr.io/liu-hy/abda-nl'
  ABDA_PUBLIC_ORIGIN='https://demo.abda-nl.org'
}

abda_byok_validate_identity() {
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

abda_byok_validate_app() {
  local path=$1
  python3 - "$path" "$ABDA_APP_NAME" "$ABDA_BYOK_EXPECTED_REVISION" \
    "$ABDA_IMAGE_REPOSITORY@sha256:$ABDA_BYOK_IMAGE_SHA256" \
    "$ABDA_PUBLIC_ORIGIN" <<'PY'
import json
import sys

path, expected_app, expected_revision, expected_image, expected_origin = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    app = json.load(handle)
properties = app.get("properties") or {}
configuration = properties.get("configuration") or {}
template = properties.get("template") or {}
containers = template.get("containers") or []
if app.get("name") != expected_app or len(containers) != 1:
    raise SystemExit("STOP: the Container App identity or container count changed")
if properties.get("provisioningState") != "Succeeded":
    raise SystemExit("STOP: the Container App provisioning state changed")
if properties.get("runningStatus") != "Running":
    raise SystemExit("STOP: the Container App is not running")
if (
    properties.get("latestRevisionName") != expected_revision
    or properties.get("latestReadyRevisionName") != expected_revision
):
    raise SystemExit("STOP: the deployed application revision changed")
if configuration.get("activeRevisionsMode") != "Single":
    raise SystemExit("STOP: the Container App is not in single revision mode")
ingress = configuration.get("ingress") or {}
if (
    ingress.get("external") is not True
    or ingress.get("allowInsecure") is not False
    or ingress.get("targetPort") != 8000
):
    raise SystemExit("STOP: the public ingress boundary changed")
if not any(
    item.get("name") == "demo.abda-nl.org"
    for item in ingress.get("customDomains") or []
):
    raise SystemExit("STOP: the custom domain binding is absent")
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
    "ABDA_PUBLIC_BASE_URL": expected_origin,
    "ABDA_LLM_ALLOW_BYOK": "1",
    "ABDA_LLM_REQUIRE_AUTH": "1",
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
expected_secrets = {
    "ABDA_DATABASE_URL": "database-url",
    "ABDA_SESSION_SECRET": "session-secret",
    "ABDA_METRICS_TOKEN": "metrics-token",
    "ABDA_OIDC_CLIENT_SECRET": "oidc-client-secret",
    "AZURE_OPENAI_API_KEY": "foundry-api-key",
    "OPENROUTER_API_KEY": "openrouter-api-key",
}
for name, expected in expected_secrets.items():
    if env.get(name, {}).get("secretRef") != expected:
        raise SystemExit(f"STOP: deployed secret reference {name} changed")
PY
}

abda_byok_validate_config() {
  local path=$1
  python3 - "$path" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    config = json.load(handle)
if config.get("llm_enabled") is not True or config.get("llm_auth_required") is not True:
    raise SystemExit("STOP: the public LLM access boundary changed")
if config.get("byok_enabled") is not True or config.get("byok_keys_stored") is not False:
    raise SystemExit("STOP: the public BYOK storage boundary changed")
providers = {item.get("id"): item for item in config.get("byok_providers") or []}
if set(providers) != {"anthropic", "google", "openai", "openrouter"}:
    raise SystemExit("STOP: the public BYOK provider set changed")
models = {item.get("id") for item in providers["openrouter"].get("models") or []}
if "gemini-3.7-flash" not in models:
    raise SystemExit("STOP: the accepted OpenRouter BYOK model is absent")
PY
}

abda_byok_validate_ready() {
  local path=$1
  python3 - "$path" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    if json.load(handle) != {"status": "ready"}:
        raise SystemExit("STOP: the public origin is not ready")
PY
}

abda_byok_select_replica() {
  local path=$1
  python3 - "$path" "$ABDA_CONTAINER_NAME" <<'PY'
import json
import sys

path, expected_container = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    replicas = json.load(handle)
eligible = []
for replica in replicas if isinstance(replicas, list) else []:
    properties = replica.get("properties") or {}
    containers = properties.get("containers") or []
    if properties.get("runningState") != "Running" or len(containers) != 1:
        continue
    container = containers[0]
    if container.get("name") == expected_container and container.get("ready") is True:
        eligible.append(str(replica.get("name") or ""))
if not eligible or any(not name for name in eligible):
    raise SystemExit("STOP: no ready current-revision replica is available")
print(sorted(eligible)[0])
PY
}

abda_byok_validate_logging_configuration() {
  local workspace_path=$1
  local environment_path=$2
  python3 - "$workspace_path" "$environment_path" \
    "$ABDA_LOGS_NAME" "$ABDA_ENVIRONMENT_NAME" <<'PY'
import json
import sys

workspace_path, environment_path, workspace_name, environment_name = sys.argv[1:]
with open(workspace_path, encoding="utf-8") as handle:
    workspace = json.load(handle)
with open(environment_path, encoding="utf-8") as handle:
    environment = json.load(handle)
if workspace.get("name") != workspace_name or workspace.get("retentionInDays") != 30:
    raise SystemExit("STOP: the Log Analytics workspace boundary changed")
customer_id = str(workspace.get("customerId") or "").lower()
if not customer_id:
    raise SystemExit("STOP: the Log Analytics workspace customer ID is absent")
if environment.get("name") != environment_name:
    raise SystemExit("STOP: the Container Apps environment identity changed")
configuration = ((environment.get("properties") or {}).get("appLogsConfiguration") or {})
if configuration.get("destination") != "log-analytics":
    raise SystemExit("STOP: the Container Apps log destination changed")
configured_id = str(
    (configuration.get("logAnalyticsConfiguration") or {}).get("customerId") or ""
).lower()
if configured_id != customer_id:
    raise SystemExit("STOP: the Container Apps environment uses another log workspace")
print(customer_id)
PY
}

abda_byok_write_log_api_auth() {
  local token_path=$1
  local config_path=$2
  python3 - "$token_path" "$config_path" <<'PY'
import json
import os
from pathlib import Path
import re
import sys

token_path, config_path = sys.argv[1:]
with open(token_path, encoding="utf-8") as handle:
    payload = json.load(handle)
token = str(payload.get("accessToken") or "")
if not re.fullmatch(r"[A-Za-z0-9._~-]{32,}", token):
    raise SystemExit("STOP: Azure returned an invalid Log Analytics access token")
descriptor = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
    handle.write(f'header = "Authorization: Bearer {token}"\n')
Path(token_path).unlink()
PY
}

abda_byok_convert_log_api_response() {
  local input_path=$1
  local output_path=$2
  python3 - "$input_path" "$output_path" <<'PY'
import json
import sys

input_path, output_path = sys.argv[1:]
with open(input_path, encoding="utf-8") as handle:
    response = json.load(handle)
tables = response.get("tables") if isinstance(response, dict) else None
if not isinstance(tables, list) or len(tables) != 1:
    raise SystemExit("STOP: Log Analytics returned an unexpected table count")
table = tables[0]
columns = table.get("columns") if isinstance(table, dict) else None
rows = table.get("rows") if isinstance(table, dict) else None
if not isinstance(columns, list) or not isinstance(rows, list) or len(rows) != 1:
    raise SystemExit("STOP: Log Analytics returned an unexpected result shape")
names = [item.get("name") for item in columns]
if any(not isinstance(name, str) or not name for name in names) or len(set(names)) != len(names):
    raise SystemExit("STOP: Log Analytics returned invalid result columns")
row = rows[0]
if not isinstance(row, list) or len(row) != len(names):
    raise SystemExit("STOP: Log Analytics returned an invalid result row")
with open(output_path, "x", encoding="utf-8") as handle:
    json.dump(dict(zip(names, row)), handle)
PY
}

abda_byok_validate_log_summary() {
  local path=$1
  python3 - "$path" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    row = json.load(handle)
names = (
    "byok_route_logs",
    "provider_key_like",
    "api_key_field_like",
    "email_like",
    "bearer_like",
)
for name in names:
    value = row.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SystemExit(f"STOP: Log Analytics returned an invalid {name} count")
if row["byok_route_logs"] < 1:
    raise SystemExit("WAITING_FOR_BYOK_LOG_INGESTION")
for name in names[1:]:
    if row[name] != 0:
        raise SystemExit(f"STOP: Log Analytics found {row[name]} unsafe entries")
for name in names:
    print(f"{name}: {row[name]}")
PY
}

abda_byok_runner_source() {
  cat <<'PY'
from __future__ import annotations

import getpass
import hashlib
import json
import re

from sqlalchemy import select

from app.db.models import (
    EmergencyBudget,
    EmergencyUsageReservation,
    LLMUsageEvent,
    MCPAccessToken,
    Project,
    ShareLink,
    TrialGrant,
    UsageReservation,
    User,
)
from app.db.session import get_session_factory
from app.services.accounts import normalize_email


EXPECTED_PROVIDER = "openrouter"
EXPECTED_MODEL = "gemini-3.7-flash"
EXPECTED_ROUTE = "byok:openrouter:gemini-3.7-flash"


def fail(message: str) -> None:
    raise SystemExit(f"BYOK acceptance refused: {message}")


def private_state_digest(session, user_id: str) -> str:
    projects = list(
        session.scalars(
            select(Project)
            .where(Project.owner_user_id == user_id)
            .order_by(Project.id)
        )
    )
    project_ids = [item.id for item in projects]
    shares = list(
        session.scalars(
            select(ShareLink)
            .where(ShareLink.project_id.in_(project_ids) if project_ids else False)
            .order_by(ShareLink.id)
        )
    )
    mcp_tokens = list(
        session.scalars(
            select(MCPAccessToken)
            .where(MCPAccessToken.user_id == user_id)
            .order_by(MCPAccessToken.id)
        )
    )
    payload = {
        "user": {
            "email": session.get(User, user_id).email,
            "email_verified": session.get(User, user_id).email_verified,
            "display_name": session.get(User, user_id).display_name,
            "status": session.get(User, user_id).status,
        },
        "projects": [
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "source_scenario_id": item.source_scenario_id,
                "scenario_json": item.scenario_json,
                "version": item.version,
                "created_at": str(item.created_at),
                "updated_at": str(item.updated_at),
                "archived_at": str(item.archived_at or ""),
            }
            for item in projects
        ],
        "shares": [
            {
                "id": item.id,
                "project_id": item.project_id,
                "token_hash": item.token_hash,
                "permission": item.permission,
                "created_at": str(item.created_at),
                "expires_at": str(item.expires_at or ""),
                "revoked_at": str(item.revoked_at or ""),
            }
            for item in shares
        ],
        "mcp_tokens": [
            {
                "id": item.id,
                "name": item.name,
                "token_prefix": item.token_prefix,
                "token_hash": item.token_hash,
                "scopes": item.scopes,
                "created_at": str(item.created_at),
                "expires_at": str(item.expires_at),
                "last_used_at": str(item.last_used_at or ""),
                "revoked_at": str(item.revoked_at or ""),
            }
            for item in mcp_tokens
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def snapshot(session, user_id: str) -> dict:
    trial = session.get(TrialGrant, user_id)
    emergency = session.get(EmergencyBudget, "openrouter")
    if emergency is None:
        fail("the OpenRouter emergency budget record is absent")
    trial_state = None
    if trial is not None:
        trial_state = (
            trial.granted_microusd,
            trial.spent_microusd,
            trial.reserved_microusd,
        )
    trial_reservations = tuple(
        (
            item.id,
            item.status,
            item.reserved_microusd,
            item.actual_microusd,
        )
        for item in session.scalars(
            select(UsageReservation)
            .where(UsageReservation.user_id == user_id)
            .order_by(UsageReservation.id)
        )
    )
    emergency_reservations = tuple(
        (
            item.id,
            item.status,
            item.reserved_microusd,
            item.actual_microusd,
        )
        for item in session.scalars(
            select(EmergencyUsageReservation)
            .where(EmergencyUsageReservation.user_id == user_id)
            .order_by(EmergencyUsageReservation.id)
        )
    )
    events = tuple(
        session.scalars(
            select(LLMUsageEvent)
            .where(LLMUsageEvent.user_id == user_id)
            .order_by(LLMUsageEvent.created_at, LLMUsageEvent.id)
        )
    )
    return {
        "trial": trial_state,
        "trial_reservations": trial_reservations,
        "emergency": (
            emergency.enabled,
            emergency.hard_limit_microusd,
            emergency.spent_microusd,
            emergency.reserved_microusd,
        ),
        "emergency_reservations": emergency_reservations,
        "event_ids": frozenset(item.id for item in events),
        "event_count": len(events),
        "private_state": private_state_digest(session, user_id),
    }


email = getpass.getpass("Verified ABDA-NL BYOK test account email: ")
try:
    normalized = normalize_email(email)
except Exception:
    fail("enter a valid verified account email")
email = ""
factory = get_session_factory()
with factory() as session:
    user = session.scalar(select(User).where(User.email == normalized))
    if user is None or user.email_verified is not True or user.status != "active":
        fail("the account is not an active verified ABDA-NL user")
    user_id = user.id
    before = snapshot(session, user_id)
normalized = ""

print("browser_test_ready: true", flush=True)
print(f"byok_events_before: {before['event_count']}", flush=True)

confirmation = input(
    "After one successful OpenRouter Gemini 3.7 Flash browser call, type "
    "BYOK_OPENROUTER_CALL_CONFIRMED: "
)
if confirmation != "BYOK_OPENROUTER_CALL_CONFIRMED":
    fail("the successful browser call was not confirmed")
confirmation = input(
    "After reload shows an empty provider-key field, type BYOK_RELOAD_CLEAR_CONFIRMED: "
)
if confirmation != "BYOK_RELOAD_CLEAR_CONFIRMED":
    fail("reload clearing was not confirmed")
confirmation = input(
    "After sign-out, sign-in, and an empty key field, type "
    "BYOK_SIGNOUT_CLEAR_CONFIRMED: "
)
if confirmation != "BYOK_SIGNOUT_CLEAR_CONFIRMED":
    fail("sign-out clearing was not confirmed")

with factory() as session:
    user = session.get(User, user_id)
    if user is None or user.email_verified is not True or user.status != "active":
        fail("the verified account boundary changed during the browser test")
    after = snapshot(session, user_id)
    new_events = list(
        session.scalars(
            select(LLMUsageEvent)
            .where(
                LLMUsageEvent.user_id == user_id,
                LLMUsageEvent.id.not_in(before["event_ids"]),
            )
            .order_by(LLMUsageEvent.created_at, LLMUsageEvent.id)
        )
    )

if not 1 <= len(new_events) <= 4:
    fail("the browser action did not create a bounded set of new BYOK events")
request_ids = {item.request_id for item in new_events}
if None in request_ids or len(request_ids) != 1:
    fail("the new BYOK events do not belong to one browser request")
for item in new_events:
    if (
        item.provider != EXPECTED_PROVIDER
        or item.route != EXPECTED_ROUTE
        or item.model != EXPECTED_MODEL
        or item.billing_source != "byok"
        or item.request_kind != "chat"
        or item.status not in {"failed", "succeeded"}
    ):
        fail("a new model event crossed the accepted BYOK route boundary")
safe_event_text = " ".join(
    str(value or "")
    for item in new_events
    for value in (
        item.provider,
        item.route,
        item.model,
        item.billing_source,
        item.request_kind,
        item.status,
        item.error_type,
    )
)
if re.search(r"(?i)(sk-[a-z0-9_-]{20,}|aiza[a-z0-9_-]{20,})", safe_event_text):
    fail("a provider-key pattern appeared in database event metadata")
succeeded = [item for item in new_events if item.status == "succeeded"]
if not succeeded:
    fail("the browser request has no successful BYOK provider event")
if sum(item.input_tokens + item.output_tokens for item in succeeded) <= 0:
    fail("the successful BYOK event recorded no token usage")
settled_cost = sum(item.cost_microusd for item in new_events)
if settled_cost <= 0:
    fail("the BYOK provider events recorded no settled cost")
if before["trial"] != after["trial"]:
    fail("the BYOK request changed the trial balance")
if before["trial_reservations"] != after["trial_reservations"]:
    fail("the BYOK request changed trial reservations")
if before["emergency"] != after["emergency"]:
    fail("the BYOK request changed the owner-funded OpenRouter budget")
if before["emergency_reservations"] != after["emergency_reservations"]:
    fail("the BYOK request changed emergency reservations")
if before["private_state"] != after["private_state"]:
    fail("the BYOK request changed private projects, shares, or MCP metadata")
forbidden_columns = {
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "prompt",
    "provider_api_key",
    "request_body",
    "response_body",
}
database_models = (
    User,
    Project,
    ShareLink,
    MCPAccessToken,
    TrialGrant,
    UsageReservation,
    EmergencyBudget,
    EmergencyUsageReservation,
    LLMUsageEvent,
)
database_columns = {
    item.name.lower()
    for model in database_models
    for item in model.__table__.columns
}
if forbidden_columns.intersection(database_columns):
    fail("the deployed application schema contains a forbidden secret field")

print("ABDA-NL BYOK browser acceptance status:")
print(f"script_revision: {1}")
print(f"new_byok_provider_events: {len(new_events)}")
print(f"successful_byok_provider_events: {len(succeeded)}")
print(f"settled_byok_cost_microusd: {settled_cost}")
print("provider: openrouter")
print("model: gemini-3.7-flash")
print("billing_source: byok")
print("trial_ledger_unchanged: true")
print("openrouter_emergency_ledger_unchanged: true")
print("private_project_state_unchanged: true")
print("browser_reload_cleared_key: confirmed")
print("browser_signout_cleared_key: confirmed")
print("database_secret_fields_absent: true")
print("result: BYOK_BROWSER_AND_DATABASE_ACCEPTANCE_VERIFIED_LOG_AUDIT_REQUIRED")
PY
}

abda_byok_main() {
  set -Eeuo pipefail
  set +x
  umask 077
  unset HISTFILE
  trap abda_byok_error ERR
  trap abda_byok_cleanup EXIT
  trap abda_byok_interrupt INT
  ABDA_BYOK_SECTION='bootstrap'

  printf 'ABDA-NL BYOK browser acceptance script revision: %s\n' \
    "$ABDA_BYOK_SCRIPT_REVISION"
  printf '%s\n' \
    'This gate validates one real OpenRouter BYOK call from the public browser.' \
    'Enter the provider key only at demo.abda-nl.org, never in this terminal.' \
    'The browser call is paid by that provider account. The gate changes no Azure configuration.'

  abda_byok_set_constants
  local command_name=''
  for command_name in az base64 curl grep python3 tee timeout tr; do
    command -v "$command_name" >/dev/null 2>&1 || \
      abda_byok_fail "required command is unavailable: $command_name"
  done
  [[ -t 0 ]] || abda_byok_fail 'BYOK acceptance requires an interactive Cloud Shell terminal'
  ABDA_BYOK_ROOT="$(mktemp -d /tmp/abda-nl-gate10-byok.XXXXXX)"
  chmod 700 "$ABDA_BYOK_ROOT"
  az containerapp exec --help >"$ABDA_BYOK_ROOT/containerapp-exec.help"
  for option in --name --resource-group --revision --replica --container --command; do
    grep -Fq -- "$option" "$ABDA_BYOK_ROOT/containerapp-exec.help" || \
      abda_byok_fail "az containerapp exec does not support $option"
  done

  ABDA_BYOK_SECTION='Azure identity verification'
  printf '\n[1/7] Verifying the exact Azure identity...\n'
  az account show --output json >"$ABDA_BYOK_ROOT/account.json"
  abda_byok_validate_identity "$ABDA_BYOK_ROOT/account.json"
  az account show \
    --query '{Name:name,TenantId:tenantId,User:user.name,State:state}' \
    --output table

  ABDA_BYOK_SECTION='application and replica verification'
  printf '\n[2/7] Verifying the exact approved application and one ready replica...\n'
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_BYOK_ROOT/app.json"
  abda_byok_validate_app "$ABDA_BYOK_ROOT/app.json"
  az containerapp replica list \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --revision "$ABDA_BYOK_EXPECTED_REVISION" --output json \
    >"$ABDA_BYOK_ROOT/replicas.json"
  local replica_name=''
  replica_name="$(abda_byok_select_replica "$ABDA_BYOK_ROOT/replicas.json")"
  printf 'application_revision: %s\n' "$ABDA_BYOK_EXPECTED_REVISION"
  printf 'selected_ready_replica: %s\n' "$replica_name"

  ABDA_BYOK_SECTION='public BYOK configuration verification'
  printf '\n[3/7] Verifying public readiness and the advertised BYOK boundary...\n'
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_PUBLIC_ORIGIN/health/ready" \
    --output "$ABDA_BYOK_ROOT/ready.json"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_PUBLIC_ORIGIN/config" \
    --output "$ABDA_BYOK_ROOT/config.json"
  abda_byok_validate_ready "$ABDA_BYOK_ROOT/ready.json"
  abda_byok_validate_config "$ABDA_BYOK_ROOT/config.json"
  printf 'byok_enabled: true\n'
  printf 'byok_keys_stored: false\n'
  printf 'accepted_provider: openrouter\n'
  printf 'accepted_model: gemini-3.7-flash\n'

  ABDA_BYOK_SECTION='interactive browser and database acceptance'
  printf '\n[4/7] Preparing one browser call and its read-only database audit...\n'
  printf '%s\n' \
    'Keep this Cloud Shell open and use the same verified account in a normal browser.' \
    'After the hidden email prompt reports browser_test_ready: true:' \
    '  1. Open Research workspace, then AI access.' \
    '  2. Choose Own provider key, OpenRouter, and Gemini 3.7 Flash.' \
    '  3. Paste the current OpenRouter key only into the password field and apply.' \
    '  4. Ask exactly one short chat question and wait for a useful answer.' \
    '  5. Confirm the page labels the result Own key, then return here.' \
    '  6. After the first confirmation, reload and verify the key field is empty.' \
    '  7. Re-enter and apply the key without calling the model, sign out, sign in,' \
    '     and verify that the key field is empty again.' \
    'Do not create, edit, share, or use MCP while this gate is waiting.'
  local runner_payload=''
  runner_payload="$(abda_byok_runner_source | base64 | tr -d '\n')"
  [[ -n "$runner_payload" ]] || abda_byok_fail 'the BYOK runner payload is empty'
  local exec_status=0
  set +e
  az containerapp exec \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --revision "$ABDA_BYOK_EXPECTED_REVISION" --replica "$replica_name" \
    --container "$ABDA_CONTAINER_NAME" \
    --command "/opt/venv/bin/python -c \"import base64;exec(compile(base64.b64decode('$runner_payload'),'<byok-browser-acceptance>','exec'))\"" \
    2>&1 | tee "$ABDA_BYOK_ROOT/container-exec.log"
  exec_status=${PIPESTATUS[0]}
  set -e
  (( exec_status == 0 )) || \
    abda_byok_fail "Azure container exec exited with status $exec_status"
  if [[ "$(grep -Fc 'result: BYOK_BROWSER_AND_DATABASE_ACCEPTANCE_VERIFIED_LOG_AUDIT_REQUIRED' "$ABDA_BYOK_ROOT/container-exec.log" || true)" != 1 ]]; then
    abda_byok_fail 'the container output did not contain exactly one BYOK database receipt'
  fi
  if grep -Eiq '(sk-[a-z0-9_-]{20,}|aiza[a-z0-9_-]{20,}|bearer[[:space:]]+[a-z0-9._~-]{16,})' \
      "$ABDA_BYOK_ROOT/container-exec.log"; then
    abda_byok_fail 'the visible container output may contain provider or bearer key material'
  fi

  ABDA_BYOK_SECTION='Log Analytics configuration verification'
  printf '\n[5/7] Verifying the exact count-only logging boundary...\n'
  az monitor log-analytics workspace show \
    --workspace-name "$ABDA_LOGS_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_BYOK_ROOT/workspace.json"
  az containerapp env show \
    --name "$ABDA_ENVIRONMENT_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_BYOK_ROOT/environment.json"
  local workspace_id=''
  workspace_id="$(abda_byok_validate_logging_configuration \
    "$ABDA_BYOK_ROOT/workspace.json" "$ABDA_BYOK_ROOT/environment.json")"
  printf 'log_analytics_retention_days: 30\n'

  ABDA_BYOK_SECTION='sanitized BYOK log audit'
  printf '\n[6/7] Waiting up to three minutes for count-only BYOK log evidence...\n'
  local logs_query=''
  logs_query="$(cat <<'KQL'
ContainerAppConsoleLogs_CL
| where TimeGenerated >= ago(2h)
    and ContainerAppName_s == 'abda-nl-stg-web'
    and RevisionName_s == 'abda-nl-stg-web--mcp-c55aa0d'
| extend Message=tostring(Log_s)
| summarize
    byok_route_logs=countif(Message contains 'route=byok:openrouter:gemini-3.7-flash'),
    provider_key_like=countif(tolower(Message) matches regex '(sk-[a-z0-9_-]{20,}|aiza[a-z0-9_-]{20,})'),
    api_key_field_like=countif(tolower(Message) contains 'api_key' or tolower(Message) contains 'x-goog-api-key' or tolower(Message) contains 'authorization:'),
    email_like=countif(Message matches regex '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}'),
    bearer_like=countif(tolower(Message) matches regex 'bearer +[a-z0-9._~-]{16,}')
KQL
)"
  python3 - "$ABDA_BYOK_ROOT/log-query.json" "$logs_query" <<'PY'
import json
import sys

path, query = sys.argv[1:]
with open(path, "x", encoding="utf-8") as handle:
    json.dump({"query": query, "timespan": "PT2H"}, handle)
PY
  local token_status=0
  set +e
  timeout --foreground --signal=TERM --kill-after=5s 30s \
    az account get-access-token \
      --resource https://api.loganalytics.io \
      --only-show-errors --output json \
      >"$ABDA_BYOK_ROOT/log-token.json"
  token_status=$?
  set -e
  if (( token_status == 124 )); then
    abda_byok_fail 'Azure access-token acquisition timed out after 30 seconds'
  fi
  (( token_status == 0 )) || \
    abda_byok_fail "Azure access-token acquisition exited with status $token_status"
  abda_byok_write_log_api_auth \
    "$ABDA_BYOK_ROOT/log-token.json" "$ABDA_BYOK_ROOT/log-curl-config"
  local log_ready=0
  local attempt=0
  for (( attempt=1; attempt<=12; attempt++ )); do
    rm -f -- \
      "$ABDA_BYOK_ROOT/log-api-response.json" \
      "$ABDA_BYOK_ROOT/log-summary.json" \
      "$ABDA_BYOK_ROOT/log-result.txt"
    local log_status=0
    set +e
    curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
      --connect-timeout 10 --max-time 30 \
      --config "$ABDA_BYOK_ROOT/log-curl-config" \
      --header 'Content-Type: application/json' \
      --request POST \
      --data-binary "@$ABDA_BYOK_ROOT/log-query.json" \
      "https://api.loganalytics.azure.com/v1/workspaces/$workspace_id/query" \
      --output "$ABDA_BYOK_ROOT/log-api-response.json"
    log_status=$?
    set -e
    if (( log_status == 0 )); then
      abda_byok_convert_log_api_response \
        "$ABDA_BYOK_ROOT/log-api-response.json" \
        "$ABDA_BYOK_ROOT/log-summary.json"
      local summary_status=0
      set +e
      abda_byok_validate_log_summary "$ABDA_BYOK_ROOT/log-summary.json" \
        >"$ABDA_BYOK_ROOT/log-result.txt" 2>"$ABDA_BYOK_ROOT/log-validation.err"
      summary_status=$?
      set -e
      if (( summary_status == 0 )); then
        log_ready=1
        printf 'log_ingestion_attempt: %s/12 passed\n' "$attempt"
        break
      fi
      if ! grep -Fq 'WAITING_FOR_BYOK_LOG_INGESTION' \
          "$ABDA_BYOK_ROOT/log-validation.err"; then
        cat "$ABDA_BYOK_ROOT/log-validation.err" >&2
        abda_byok_fail 'the BYOK log summary failed its safety boundary'
      fi
    elif (( log_status == 28 )); then
      printf 'log_ingestion_attempt: %s/12 timed out\n' "$attempt"
    else
      abda_byok_fail "Log Analytics API exited with curl status $log_status"
    fi
    printf 'log_ingestion_attempt: %s/12 waiting\n' "$attempt"
    if (( attempt < 12 )); then
      sleep 15
    fi
  done
  rm -f -- "$ABDA_BYOK_ROOT/log-curl-config"
  (( log_ready == 1 )) || \
    abda_byok_fail 'BYOK log evidence was not ingested within three minutes'

  ABDA_BYOK_SECTION='final BYOK receipt'
  printf '\n[7/7] Verifying unchanged deployment and reporting the content-free receipt...\n'
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_BYOK_ROOT/final-app.json"
  abda_byok_validate_app "$ABDA_BYOK_ROOT/final-app.json"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_PUBLIC_ORIGIN/health/ready" \
    --output "$ABDA_BYOK_ROOT/final-ready.json"
  abda_byok_validate_ready "$ABDA_BYOK_ROOT/final-ready.json"

  printf '\nABDA-NL live BYOK acceptance status:\n'
  printf 'script_revision: %s\n' "$ABDA_BYOK_SCRIPT_REVISION"
  printf 'application_source_commit: %s\n' \
    "$ABDA_BYOK_APPLICATION_SOURCE_COMMIT"
  printf 'image_digest: sha256:%s\n' "$ABDA_BYOK_IMAGE_SHA256"
  printf 'subscription_id: %s\n' "$ABDA_EXPECTED_SUBSCRIPTION"
  printf 'resource_group: %s\n' "$ABDA_RESOURCE_GROUP"
  printf 'application_revision: %s\n' "$ABDA_BYOK_EXPECTED_REVISION"
  printf 'public_origin: %s\n' "$ABDA_PUBLIC_ORIGIN"
  grep -E '^(new_byok_provider_events|successful_byok_provider_events|settled_byok_cost_microusd|provider|model|billing_source|trial_ledger_unchanged|openrouter_emergency_ledger_unchanged|private_project_state_unchanged|browser_reload_cleared_key|browser_signout_cleared_key|database_secret_fields_absent):' \
    "$ABDA_BYOK_ROOT/container-exec.log"
  cat "$ABDA_BYOK_ROOT/log-result.txt"
  printf 'provider_key_entered_in_shell: false\n'
  printf 'raw_log_messages_printed: false\n'
  printf 'azure_configuration_changed: false\n'
  printf 'result: LIVE_BYOK_PRIVACY_AND_ACCOUNTING_ACCEPTANCE_VERIFIED\n'
  printf 'Send this status and the shell exit code to Codex.\n'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_byok_main "$@"
fi
