#!/usr/bin/env bash

# Read-only release and Log Analytics acceptance for the current staging image.
# The gate executes the image's own release checker and summarizes log counts.
# It never prints raw log messages or secret values.

ABDA_AUDIT_SCRIPT_REVISION='7'
ABDA_AUDIT_SOURCE_COMMIT='51702e175bd14d4cb54075808f839d173d561324'
ABDA_AUDIT_IMAGE_SHA256='a0b3ba24aff06ecf461f86547131d86451c541e306a7ecfc278f280fcef5c0bc'
ABDA_AUDIT_RELEASE_STAGE=''
ABDA_AUDIT_REVISION=''
ABDA_AUDIT_RESULT=''
ABDA_AUDIT_ROOT=''

abda_audit_cleanup() {
  local exit_code=$?
  set +e
  if [[ "${ABDA_AUDIT_ROOT:-}" == /tmp/abda-nl-gate9-audit.* &&
        -d "${ABDA_AUDIT_ROOT:-}" ]]; then
    rm -rf -- "$ABDA_AUDIT_ROOT"
  fi
  printf '\nGate 9 shell exit code: %s\n' "$exit_code"
}

abda_audit_error() {
  local exit_code=$?
  trap - ERR
  printf '\nSTOP: Gate 9 failed in section: %s\n' \
    "${ABDA_AUDIT_SECTION:-unknown}" >&2
  printf '%s\n' \
    'No Azure resource configuration, application data, or model provider was changed.' \
    'Send the visible status and shell exit code to Codex.' >&2
  exit "$exit_code"
}

abda_audit_interrupt() {
  trap - ERR INT
  printf '\nSTOP: Gate 9 was interrupted in section: %s\n' \
    "${ABDA_AUDIT_SECTION:-unknown}" >&2
  exit 130
}

abda_audit_fail() {
  printf 'STOP: %s\n' "$*" >&2
  return 1
}

abda_audit_set_constants() {
  local release_stage="${1:---pilot}"
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
  ABDA_TRIAL_GRANT_MICROUSD='5000000'
  ABDA_OPENROUTER_BUDGET_MICROUSD='500000000'
  case "$release_stage" in
    --pilot)
      ABDA_AUDIT_RELEASE_STAGE='pilot'
      ABDA_AUDIT_REVISION='abda-nl-stg-web--harden-51702e1'
      ABDA_TRIAL_MAX_USERS='10'
      ABDA_TRIAL_BUDGET_MICROUSD='50000000'
      ABDA_OPENROUTER_ENABLED='false'
      ABDA_AUDIT_RESULT='RELEASE_AND_OBSERVABILITY_AUDIT_VERIFIED'
      ;;
    --public)
      ABDA_AUDIT_RELEASE_STAGE='public'
      ABDA_AUDIT_REVISION='abda-nl-stg-web--public-100-51702e1'
      ABDA_TRIAL_MAX_USERS='100'
      ABDA_TRIAL_BUDGET_MICROUSD='500000000'
      ABDA_OPENROUTER_ENABLED='true'
      ABDA_AUDIT_RESULT='FINAL_PUBLIC_RELEASE_AND_OBSERVABILITY_AUDIT_VERIFIED'
      ;;
    *)
      abda_audit_fail 'usage: gate9-observability-audit.sh [--pilot|--public]'
      ;;
  esac
}

abda_audit_validate_identity() {
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

abda_audit_validate_app() {
  local path=$1
  python3 - "$path" "$ABDA_APP_NAME" "$ABDA_AUDIT_REVISION" \
    "$ABDA_IMAGE_REPOSITORY@sha256:$ABDA_AUDIT_IMAGE_SHA256" \
    "$ABDA_PUBLIC_ORIGIN" "$ABDA_TRIAL_MAX_USERS" \
    "$ABDA_TRIAL_GRANT_MICROUSD" "$ABDA_TRIAL_BUDGET_MICROUSD" \
    "$ABDA_OPENROUTER_ENABLED" "$ABDA_OPENROUTER_BUDGET_MICROUSD" <<'PY'
import json
import sys

(
    path,
    expected_app,
    expected_revision,
    expected_image,
    expected_origin,
    trial_max_users,
    trial_grant,
    trial_budget,
    openrouter_enabled,
    openrouter_budget,
) = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    app = json.load(handle)
properties = app.get("properties") or {}
containers = ((properties.get("template") or {}).get("containers") or [])
if app.get("name") != expected_app or len(containers) != 1:
    raise SystemExit("STOP: the Container App identity changed")
if properties.get("provisioningState") != "Succeeded":
    raise SystemExit("STOP: the Container App provisioning state changed")
if properties.get("runningStatus") != "Running":
    raise SystemExit("STOP: the Container App is not running")
if (
    properties.get("latestRevisionName") != expected_revision
    or properties.get("latestReadyRevisionName") != expected_revision
):
    raise SystemExit("STOP: the exact shared-view revision is not ready")
container = containers[0]
if container.get("name") != "web" or container.get("image") != expected_image:
    raise SystemExit("STOP: the exact shared-view image is not deployed")
template = properties.get("template") or {}
scale = template.get("scale") or {}
if scale.get("minReplicas") != 1 or scale.get("maxReplicas") != 3:
    raise SystemExit("STOP: the staging replica boundary changed")
configuration = properties.get("configuration") or {}
if configuration.get("activeRevisionsMode") != "Single":
    raise SystemExit("STOP: the revision mode changed")
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
environment = {
    str(item.get("name") or ""): item
    for item in container.get("env") or []
}
expected_values = {
    "ABDA_ENVIRONMENT": "staging",
    "ABDA_AUTH_MODE": "oidc",
    "ABDA_PUBLIC_BASE_URL": expected_origin,
    "ABDA_TRIAL_ENABLED": "true",
    "ABDA_TRIAL_MAX_USERS": trial_max_users,
    "ABDA_TRIAL_GRANT_MICROUSD": trial_grant,
    "ABDA_TRIAL_BUDGET_MICROUSD": trial_budget,
    "ABDA_LLM_ALLOW_BYOK": "1",
    "ABDA_LLM_REQUIRE_AUTH": "1",
    "ABDA_OPENROUTER_FAILOVER_ENABLED": openrouter_enabled,
    "ABDA_OPENROUTER_BUDGET_MICROUSD": openrouter_budget,
}
for name, expected in expected_values.items():
    actual = str(environment.get(name, {}).get("value") or "")
    if name in {"ABDA_TRIAL_ENABLED", "ABDA_OPENROUTER_FAILOVER_ENABLED"}:
        actual = actual.lower()
    if actual != expected:
        raise SystemExit(f"STOP: deployed setting {name} changed")
expected_secrets = {
    "ABDA_DATABASE_URL": "database-url",
    "ABDA_SESSION_SECRET": "session-secret",
    "ABDA_MCP_TOKEN_PEPPER": "mcp-token-pepper",
    "ABDA_METRICS_TOKEN": "metrics-token",
    "ABDA_OIDC_CLIENT_SECRET": "oidc-client-secret",
    "AZURE_OPENAI_API_KEY": "foundry-api-key",
    "OPENROUTER_API_KEY": "openrouter-api-key",
}
for name, expected in expected_secrets.items():
    if environment.get(name, {}).get("secretRef") != expected:
        raise SystemExit(f"STOP: deployed secret reference {name} changed")
PY
}

abda_audit_select_replica() {
  local path=$1
  python3 - "$path" "$ABDA_CONTAINER_NAME" <<'PY'
import json
import sys

path, expected_container = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    replicas = json.load(handle)
if not isinstance(replicas, list) or not 1 <= len(replicas) <= 3:
    raise SystemExit("STOP: the current revision has an unexpected replica count")
eligible = []
for replica in replicas:
    properties = replica.get("properties") or {}
    containers = properties.get("containers") or []
    if properties.get("runningState") != "Running" or len(containers) != 1:
        continue
    container = containers[0]
    if (
        container.get("name") == expected_container
        and container.get("ready") is True
        and container.get("started") is not False
    ):
        eligible.append(str(replica.get("name") or ""))
if not eligible or any(not name for name in eligible):
    raise SystemExit("STOP: no ready current-revision replica is available")
print(sorted(eligible)[0])
PY
}

abda_audit_validate_logging_configuration() {
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
if workspace.get("name") != workspace_name:
    raise SystemExit("STOP: the Log Analytics workspace identity changed")
if workspace.get("retentionInDays") != 30:
    raise SystemExit("STOP: Log Analytics retention is not 30 days")
if (workspace.get("sku") or {}).get("name") != "PerGB2018":
    raise SystemExit("STOP: the Log Analytics workspace SKU changed")
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

abda_audit_write_log_api_auth() {
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

abda_audit_convert_log_api_response() {
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
    raise SystemExit("STOP: Log Analytics API returned an unexpected table count")
table = tables[0]
columns = table.get("columns") if isinstance(table, dict) else None
rows = table.get("rows") if isinstance(table, dict) else None
if not isinstance(columns, list) or not isinstance(rows, list) or len(rows) != 1:
    raise SystemExit("STOP: Log Analytics API returned an unexpected result shape")
names = []
for column in columns:
    name = column.get("name") if isinstance(column, dict) else None
    if not isinstance(name, str) or not name or name in names:
        raise SystemExit("STOP: Log Analytics API returned invalid result columns")
    names.append(name)
row = rows[0]
if not isinstance(row, list) or len(row) != len(names):
    raise SystemExit("STOP: Log Analytics API returned an invalid result row")
with open(output_path, "x", encoding="utf-8") as handle:
    json.dump([dict(zip(names, row))], handle)
PY
}

abda_audit_validate_log_summary() {
  local path=$1
  python3 - "$path" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    rows = json.load(handle)
if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
    raise SystemExit("STOP: Log Analytics returned an unexpected summary shape")
row = rows[0]
names = (
    "total_logs",
    "console_logs",
    "system_logs",
    "current_revision_logs",
    "current_revision_request_logs",
    "request_logs",
    "request_query_markers",
    "email_like",
    "bearer_like",
    "share_fragment_like",
    "oidc_code_like",
    "provider_key_like",
    "private_identifier_field_like",
)
values = {}
for name in names:
    value = row.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SystemExit(f"STOP: Log Analytics returned an invalid {name} count")
    values[name] = value
for name in (
    "total_logs",
    "console_logs",
    "system_logs",
    "current_revision_logs",
    "current_revision_request_logs",
    "request_logs",
):
    if values[name] == 0:
        raise SystemExit(f"STOP: Log Analytics has no {name} in the audit window")
unsafe = (
    "request_query_markers",
    "email_like",
    "bearer_like",
    "share_fragment_like",
    "oidc_code_like",
    "provider_key_like",
    "private_identifier_field_like",
)
for name in unsafe:
    if values[name] != 0:
        raise SystemExit(f"STOP: Log Analytics found {values[name]} {name} entries")
for name in names:
    print(f"{name}: {values[name]}")
PY
}

abda_audit_current_revision_logs_ready() {
  local path=$1
  python3 - "$path" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    rows = json.load(handle)
if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
    raise SystemExit(1)
row = rows[0]
for name in ("current_revision_logs", "current_revision_request_logs"):
    value = row.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SystemExit(1)
PY
}

abda_audit_extract_release_check() {
  local input_path=$1
  local output_path=$2
  python3 - "$input_path" "$output_path" <<'PY'
import json
import re
import sys

input_path, output_path = sys.argv[1:]
with open(input_path, encoding="utf-8", errors="replace") as handle:
    text = handle.read()
text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text).replace("\r", "")
decoder = json.JSONDecoder()
matches = []
for index, character in enumerate(text):
    if character != "{":
        continue
    try:
        value, _ = decoder.raw_decode(text[index:])
    except json.JSONDecodeError:
        continue
    if (
        isinstance(value, dict)
        and value.get("origin") == "https://demo.abda-nl.org"
        and isinstance(value.get("checks"), dict)
        and isinstance(value.get("budgets"), dict)
    ):
        matches.append(value)
if len(matches) != 1:
    raise SystemExit("STOP: the container output did not contain exactly one release receipt")
with open(output_path, "x", encoding="utf-8") as handle:
    json.dump(matches[0], handle)
PY
}

abda_audit_validate_release_check() {
  local path=$1
  python3 - "$path" "$ABDA_TRIAL_MAX_USERS" \
    "$ABDA_TRIAL_GRANT_MICROUSD" "$ABDA_TRIAL_BUDGET_MICROUSD" \
    "$ABDA_OPENROUTER_ENABLED" "$ABDA_OPENROUTER_BUDGET_MICROUSD" <<'PY'
import json
import sys

(
    path,
    trial_max_users_text,
    trial_grant_text,
    trial_budget_text,
    openrouter_enabled_text,
    openrouter_budget_text,
) = sys.argv[1:]
trial_max_users = int(trial_max_users_text)
trial_grant = int(trial_grant_text)
trial_budget = int(trial_budget_text)
openrouter_enabled = int(openrouter_enabled_text.lower() == "true")
openrouter_budget = int(openrouter_budget_text)
with open(path, encoding="utf-8") as handle:
    value = json.load(handle)
checks = value.get("checks") or {}
expected_checks = {
    "https_certificate": "verified",
    "liveness": "passed",
    "readiness": "passed",
    "policy_pages": "passed",
    "security_headers": "passed",
    "config_exposure": "passed",
    "metrics_authentication": "passed",
    "budget_metrics": "passed",
    "database_pool": "passed",
}
for name, expected in expected_checks.items():
    if checks.get(name) != expected:
        raise SystemExit(f"STOP: release check {name} did not pass")
if checks.get("plain_http") not in {"redirected", "refused"}:
    raise SystemExit("STOP: plaintext HTTP was neither redirected nor refused")
config = value.get("config") or {}
if config.get("default_profile") != "balanced" or config.get("funded_profiles") != ["balanced"]:
    raise SystemExit("STOP: the public funded profile contract changed")
if set((config.get("byok_model_counts") or {}).keys()) != {
    "anthropic", "google", "openai", "openrouter"
}:
    raise SystemExit("STOP: the public BYOK provider set changed")
budgets = value.get("budgets") or {}
expected_budget_values = {
    "trial_enabled": 1,
    "trial_max_users": trial_max_users,
    "trial_grant_microusd": trial_grant,
    "trial_budget_microusd": trial_budget,
    "openrouter_enabled": openrouter_enabled,
    "openrouter_budget_microusd": openrouter_budget,
}
for name, expected in expected_budget_values.items():
    if budgets.get(name) != expected:
        raise SystemExit(f"STOP: release receipt {name} changed")
activations = budgets.get("trial_activations")
allocated = budgets.get("trial_allocated_microusd")
trial_spent = budgets.get("trial_spent_microusd")
openrouter_spent = budgets.get("openrouter_spent_microusd")
if (
    isinstance(activations, bool)
    or not isinstance(activations, int)
    or not 1 <= activations <= trial_max_users
    or allocated != activations * trial_grant
    or isinstance(trial_spent, bool)
    or not isinstance(trial_spent, int)
    or not 0 <= trial_spent <= allocated
    or isinstance(openrouter_spent, bool)
    or not isinstance(openrouter_spent, int)
    or not 0 <= openrouter_spent <= openrouter_budget
):
    raise SystemExit("STOP: the release receipt ledgers do not reconcile")
pool = value.get("database_pool") or {}
if pool.get("capacity") != 5 or not 0 <= int(pool.get("checked_out", -1)) <= 5:
    raise SystemExit("STOP: the database pool boundary changed")
print("release_check: passed")
print(f"trial_activations: {activations}")
print(f"trial_allocated_microusd: {allocated}")
print(f"trial_spent_microusd: {trial_spent}")
print(f"openrouter_spent_microusd: {openrouter_spent}")
print(f"database_pool_checked_out: {pool['checked_out']}")
PY
}

abda_audit_main() {
  set -Eeuo pipefail
  set +x
  umask 077
  unset HISTFILE
  trap abda_audit_error ERR
  trap abda_audit_interrupt INT
  trap abda_audit_cleanup EXIT
  ABDA_AUDIT_SECTION='bootstrap'

  if (( $# > 1 )); then
    abda_audit_fail 'usage: gate9-observability-audit.sh [--pilot|--public]'
  fi
  abda_audit_set_constants "${1:---pilot}"

  printf 'ABDA-NL Gate 9 release and observability audit revision: %s\n' \
    "$ABDA_AUDIT_SCRIPT_REVISION"
  printf 'release_stage: %s\n' "$ABDA_AUDIT_RELEASE_STAGE"
  printf '%s\n' \
    'This gate is read-only. It runs HTTPS checks and count-only log queries.' \
    'It does not print log messages or secret values, call a model, deploy, restart, or change Azure configuration.'

  local command_name=''
  for command_name in az curl python3 tee timeout; do
    command -v "$command_name" >/dev/null 2>&1 || \
      abda_audit_fail "required command is unavailable: $command_name"
  done
  [[ -t 0 ]] || abda_audit_fail 'Gate 9 requires an interactive Cloud Shell terminal'
  ABDA_AUDIT_ROOT="$(mktemp -d /tmp/abda-nl-gate9-audit.XXXXXX)"
  chmod 700 "$ABDA_AUDIT_ROOT"

  ABDA_AUDIT_SECTION='Azure identity verification'
  printf '\n[1/6] Verifying the exact Azure identity...\n'
  az account show --output json >"$ABDA_AUDIT_ROOT/account.json"
  abda_audit_validate_identity "$ABDA_AUDIT_ROOT/account.json"
  az account show \
    --query '{Name:name,TenantId:tenantId,User:user.name,State:state}' \
    --output table

  ABDA_AUDIT_SECTION='application and replica verification'
  printf '\n[2/6] Verifying the exact healthy release image and one ready replica...\n'
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_AUDIT_ROOT/app.json"
  abda_audit_validate_app "$ABDA_AUDIT_ROOT/app.json"
  az containerapp replica list \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --revision "$ABDA_AUDIT_REVISION" --output json \
    >"$ABDA_AUDIT_ROOT/replicas.json"
  local replica_name=''
  replica_name="$(abda_audit_select_replica "$ABDA_AUDIT_ROOT/replicas.json")"
  printf 'application_revision: %s\n' "$ABDA_AUDIT_REVISION"
  printf 'selected_ready_replica: %s\n' "$replica_name"

  ABDA_AUDIT_SECTION='Log Analytics configuration verification'
  printf '\n[3/6] Verifying the exact workspace, destination, and 30-day retention...\n'
  az monitor log-analytics workspace show \
    --workspace-name "$ABDA_LOGS_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_AUDIT_ROOT/workspace.json"
  az containerapp env show \
    --name "$ABDA_ENVIRONMENT_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_AUDIT_ROOT/environment.json"
  local workspace_id=''
  workspace_id="$(abda_audit_validate_logging_configuration \
    "$ABDA_AUDIT_ROOT/workspace.json" "$ABDA_AUDIT_ROOT/environment.json")"
  printf 'log_analytics_workspace: %s\n' "$ABDA_LOGS_NAME"
  printf 'log_analytics_retention_days: 30\n'

  ABDA_AUDIT_SECTION='sanitized log ingestion audit'
  printf '\n[4/6] Querying 48 hours of count-only log evidence with a 75-second limit...\n'
  local logs_query=''
  logs_query="$(cat <<KQL
let ConsoleLogs = ContainerAppConsoleLogs_CL
| where TimeGenerated >= ago(48h) and ContainerAppName_s == 'abda-nl-stg-web'
| project TimeGenerated, Kind='console', Revision=tostring(RevisionName_s), Message=tostring(Log_s);
let SystemLogs = ContainerAppSystemLogs_CL
| where TimeGenerated >= ago(48h) and ContainerAppName_s == 'abda-nl-stg-web'
| project TimeGenerated, Kind='system', Revision=tostring(RevisionName_s), Message=tostring(Log_s);
ConsoleLogs
| union SystemLogs
| summarize
    total_logs=count(),
    console_logs=countif(Kind == 'console'),
    system_logs=countif(Kind == 'system'),
    current_revision_logs=countif(Revision == '$ABDA_AUDIT_REVISION'),
    current_revision_request_logs=countif(
      Revision == '$ABDA_AUDIT_REVISION'
      and Kind == 'console'
      and Message contains 'request_complete'
    ),
    request_logs=countif(Kind == 'console' and Message contains 'request_complete'),
    request_query_markers=countif(Kind == 'console' and Message contains 'request_complete' and Message contains '?'),
    email_like=countif(Message matches regex '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}'),
    bearer_like=countif(tolower(Message) matches regex '(abda_mcp_[a-z0-9_-]{16,}|bearer +[a-z0-9._~-]{16,})'),
    share_fragment_like=countif(tolower(Message) contains '#share='),
    oidc_code_like=countif(tolower(Message) matches regex '[?&]code=[a-z0-9._~-]{8,}'),
    provider_key_like=countif(tolower(Message) matches regex '(sk-[a-z0-9_-]{20,}|aiza[a-z0-9_-]{20,})'),
    private_identifier_field_like=countif(
      Revision == '$ABDA_AUDIT_REVISION'
      and tolower(Message) matches regex '(^| )(account_id|credential_id|project_id|scenario_id|proposer_id|context_id|task|stop_reason)='
    )
KQL
)"
  python3 - "$ABDA_AUDIT_ROOT/log-query.json" "$logs_query" <<'PY'
import json
import sys

path, query = sys.argv[1:]
with open(path, "x", encoding="utf-8") as handle:
    json.dump({"query": query, "timespan": "P2D"}, handle)
PY
  local token_status=0
  set +e
  timeout --foreground --signal=TERM --kill-after=5s 30s \
    az account get-access-token \
      --resource https://api.loganalytics.io \
      --only-show-errors --output json \
      >"$ABDA_AUDIT_ROOT/log-token.json"
  token_status=$?
  set -e
  if (( token_status == 124 )); then
    abda_audit_fail 'Azure access-token acquisition timed out after 30 seconds'
  fi
  (( token_status == 0 )) || \
    abda_audit_fail "Azure access-token acquisition exited with status $token_status"
  abda_audit_write_log_api_auth \
    "$ABDA_AUDIT_ROOT/log-token.json" "$ABDA_AUDIT_ROOT/log-curl-config"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_PUBLIC_ORIGIN/health/ready" \
    --output "$ABDA_AUDIT_ROOT/log-seed-ready.json"
  local log_api_status=0
  local log_ingestion_ready='false'
  local log_attempt=0
  for log_attempt in {1..12}; do
    set +e
    curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
      --connect-timeout 10 --max-time 75 \
      --config "$ABDA_AUDIT_ROOT/log-curl-config" \
      --header 'Content-Type: application/json' \
      --request POST \
      --data-binary "@$ABDA_AUDIT_ROOT/log-query.json" \
      "https://api.loganalytics.azure.com/v1/workspaces/$workspace_id/query" \
      --output "$ABDA_AUDIT_ROOT/log-api-response.json"
    log_api_status=$?
    set -e
    if (( log_api_status == 28 )); then
      abda_audit_fail 'Log Analytics API timed out after 75 seconds'
    fi
    (( log_api_status == 0 )) || \
      abda_audit_fail "Log Analytics API exited with curl status $log_api_status"
    rm -f -- "$ABDA_AUDIT_ROOT/log-summary.json"
    abda_audit_convert_log_api_response \
      "$ABDA_AUDIT_ROOT/log-api-response.json" \
      "$ABDA_AUDIT_ROOT/log-summary.json"
    if abda_audit_current_revision_logs_ready \
      "$ABDA_AUDIT_ROOT/log-summary.json"; then
      printf 'log_ingestion_attempt: %s/12 passed\n' "$log_attempt"
      log_ingestion_ready='true'
      break
    fi
    printf 'log_ingestion_attempt: %s/12 waiting\n' "$log_attempt"
    sleep 15
  done
  rm -f -- "$ABDA_AUDIT_ROOT/log-curl-config"
  [[ "$log_ingestion_ready" == 'true' ]] || \
    abda_audit_fail 'current-revision request logs were not ingested within three minutes'
  abda_audit_validate_log_summary "$ABDA_AUDIT_ROOT/log-summary.json" \
    | tee "$ABDA_AUDIT_ROOT/log-result.txt"

  ABDA_AUDIT_SECTION='authorized release check'
  printf '\n[5/6] Running the deployed image release checker without displaying its metrics token...\n'
  local exec_status=0
  set +e
  timeout --foreground --signal=INT --kill-after=5s 120s \
    az containerapp exec \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --revision "$ABDA_AUDIT_REVISION" --replica "$replica_name" \
    --container "$ABDA_CONTAINER_NAME" \
    --command "/opt/venv/bin/python -m app.cli.release_check --metrics-token-env ABDA_METRICS_TOKEN --expected-trial-enabled true --expected-trial-max-users $ABDA_TRIAL_MAX_USERS --expected-trial-budget-microusd $ABDA_TRIAL_BUDGET_MICROUSD --expected-openrouter-enabled $ABDA_OPENROUTER_ENABLED --expected-openrouter-budget-microusd $ABDA_OPENROUTER_BUDGET_MICROUSD $ABDA_PUBLIC_ORIGIN" \
    2>&1 | tee "$ABDA_AUDIT_ROOT/release-check.log"
  exec_status=${PIPESTATUS[0]}
  set -e
  if (( exec_status == 124 )); then
    abda_audit_fail 'Azure container release check timed out after 120 seconds'
  fi
  if (( exec_status != 0 )); then
    abda_audit_fail "Azure container exec exited with status $exec_status"
  fi
  abda_audit_extract_release_check \
    "$ABDA_AUDIT_ROOT/release-check.log" "$ABDA_AUDIT_ROOT/release-check.json"
  abda_audit_validate_release_check "$ABDA_AUDIT_ROOT/release-check.json" \
    | tee "$ABDA_AUDIT_ROOT/release-result.txt"

  ABDA_AUDIT_SECTION='final audit receipt'
  printf '\n[6/6] Reporting the content-free audit receipt...\n'
  printf '\nABDA-NL Gate 9 release and observability status:\n'
  printf 'script_revision: %s\n' "$ABDA_AUDIT_SCRIPT_REVISION"
  printf 'release_stage: %s\n' "$ABDA_AUDIT_RELEASE_STAGE"
  printf 'application_source_commit: %s\n' "$ABDA_AUDIT_SOURCE_COMMIT"
  printf 'image_digest: sha256:%s\n' "$ABDA_AUDIT_IMAGE_SHA256"
  printf 'subscription_id: %s\n' "$ABDA_EXPECTED_SUBSCRIPTION"
  printf 'resource_group: %s\n' "$ABDA_RESOURCE_GROUP"
  printf 'application_revision: %s\n' "$ABDA_AUDIT_REVISION"
  printf 'public_origin: %s\n' "$ABDA_PUBLIC_ORIGIN"
  printf 'log_analytics_workspace: %s\n' "$ABDA_LOGS_NAME"
  printf 'log_analytics_retention_days: 30\n'
  cat "$ABDA_AUDIT_ROOT/log-result.txt"
  cat "$ABDA_AUDIT_ROOT/release-result.txt"
  printf 'raw_log_messages_printed: false\n'
  printf 'secret_values_printed: false\n'
  printf 'model_provider_called: false\n'
  printf 'azure_configuration_changed: false\n'
  printf 'result: %s\n' "$ABDA_AUDIT_RESULT"
  printf 'Send this status and the shell exit code to Codex.\n'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_audit_main "$@"
fi
