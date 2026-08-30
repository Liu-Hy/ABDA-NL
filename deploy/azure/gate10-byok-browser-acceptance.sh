#!/usr/bin/env bash

# Validate one real public-browser BYOK request without receiving the provider
# key. The gate uses protected aggregate metrics and count-only logs. Its small
# content-free state file makes every post-call check safe to resume.

ABDA_BYOK_SCRIPT_REVISION='2'
ABDA_BYOK_APPLICATION_SOURCE_COMMIT='0b2a2aad93427dfec65c11def7f6434ed1c9abfb'
ABDA_BYOK_IMAGE_SHA256='ffea9cff567b8694cc556aa4ba91a67e8ab5001cffc3f54c97f2aaaf6a2b4593'
ABDA_BYOK_EXPECTED_REVISION='abda-nl-stg-web--revoke-0b2a2aa'
ABDA_BYOK_ROOT=''
ABDA_BYOK_STATE_PATH=''
ABDA_BYOK_COMPLETE=0

abda_byok_cleanup() {
  local exit_code=$?
  set +e
  if [[ "${ABDA_BYOK_ROOT:-}" == /tmp/abda-nl-gate10-byok.* &&
        -d "${ABDA_BYOK_ROOT:-}" ]]; then
    rm -rf -- "$ABDA_BYOK_ROOT"
  fi
  if (( ABDA_BYOK_COMPLETE == 1 )) && [[ -n "${ABDA_BYOK_STATE_PATH:-}" ]]; then
    rm -f -- "$ABDA_BYOK_STATE_PATH"
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
    'If the browser call already succeeded, do not repeat it. The content-free resume state was preserved.' \
    'No Azure configuration was changed. Send only the visible section and exit code.' >&2
  exit "$exit_code"
}

abda_byok_interrupt() {
  trap - ERR INT
  printf '\nSTOP: BYOK acceptance was interrupted in section: %s\n' \
    "${ABDA_BYOK_SECTION:-unknown}" >&2
  printf '%s\n' \
    'Clear the browser key and sign out.' \
    'If the one paid call already succeeded, do not repeat it. Rerun the same pinned gate to resume.' >&2
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
    "ABDA_MCP_TOKEN_PEPPER": "mcp-token-pepper",
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

abda_byok_load_metrics_token() {
  local secrets_path=$1
  local config_path=$2
  python3 - "$secrets_path" "$config_path" <<'PY'
import json
import os
import sys

secrets_path, config_path = sys.argv[1:]
with open(secrets_path, encoding="utf-8") as handle:
    values = json.load(handle)
expected = {
    "database-url",
    "session-secret",
    "mcp-token-pepper",
    "metrics-token",
    "oidc-client-secret",
    "foundry-api-key",
    "openrouter-api-key",
}
if {item.get("name") for item in values} != expected:
    raise SystemExit("STOP: the protected secret inventory changed")
matches = [
    str(item.get("value") or "")
    for item in values
    if item.get("name") == "metrics-token"
]
if len(matches) != 1 or len(matches[0]) < 32 or any(char.isspace() for char in matches[0]):
    raise SystemExit("STOP: the protected metrics token is invalid")
escaped = matches[0].replace("\\", "\\\\").replace('"', '\\"')
descriptor = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
    handle.write(f'header = "Authorization: Bearer {escaped}"\n')
PY
}

abda_byok_metrics_snapshot() {
  local metrics_path=$1
  local output_path=$2
  python3 - "$metrics_path" "$output_path" <<'PY'
import json
import os
import sys

metrics_path, output_path = sys.argv[1:]
samples = {}
with open(metrics_path, encoding="utf-8") as handle:
    for raw_line in handle:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) == 2:
            samples.setdefault(fields[0], []).append(fields[1])

names = (
    "abda_trial_enabled",
    "abda_trial_max_users",
    "abda_trial_grant_microusd",
    "abda_trial_budget_microusd",
    "abda_trial_activations",
    "abda_trial_allocated_microusd",
    "abda_trial_spent_microusd",
    "abda_trial_reserved_microusd",
    "abda_trial_uncertain_charged_reservations",
    "abda_trial_uncertain_charged_microusd",
    "abda_openrouter_enabled",
    "abda_openrouter_budget_microusd",
    "abda_openrouter_spent_microusd",
    "abda_openrouter_reserved_microusd",
    "abda_openrouter_uncertain_charged_reservations",
    "abda_openrouter_uncertain_charged_microusd",
    "abda_llm_usage_events_total",
)
values = {}
for name in names:
    found = samples.get(name) or []
    if len(found) != 1:
        raise SystemExit(f"STOP: metrics must contain exactly one {name} sample")
    try:
        value = int(found[0])
    except ValueError as exc:
        raise SystemExit(f"STOP: metric {name} is not an integer") from exc
    if value < 0:
        raise SystemExit(f"STOP: metric {name} is negative")
    values[name] = value

if (
    values["abda_trial_enabled"],
    values["abda_trial_max_users"],
    values["abda_trial_grant_microusd"],
    values["abda_trial_budget_microusd"],
) != (1, 10, 5_000_000, 50_000_000):
    raise SystemExit("STOP: the funded trial cap changed")
if values["abda_trial_allocated_microusd"] != (
    values["abda_trial_activations"] * values["abda_trial_grant_microusd"]
):
    raise SystemExit("STOP: trial allocation no longer reconciles")
if values["abda_trial_spent_microusd"] + values["abda_trial_reserved_microusd"] > values["abda_trial_allocated_microusd"]:
    raise SystemExit("STOP: trial usage exceeds allocated credit")
if any(
    values[name]
    for name in (
        "abda_trial_reserved_microusd",
        "abda_trial_uncertain_charged_reservations",
        "abda_trial_uncertain_charged_microusd",
        "abda_openrouter_enabled",
        "abda_openrouter_reserved_microusd",
        "abda_openrouter_uncertain_charged_reservations",
        "abda_openrouter_uncertain_charged_microusd",
    )
):
    raise SystemExit("STOP: one or more accounting boundaries are not safely idle")
if values["abda_openrouter_budget_microusd"] != 500_000_000:
    raise SystemExit("STOP: the OpenRouter owner budget changed")

descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
    json.dump(values, handle, sort_keys=True)
PY
}

abda_byok_create_state() {
  local snapshot_path=$1
  local state_path=$2
  local started_at=$3
  python3 - "$snapshot_path" "$state_path" "$started_at" \
    "$ABDA_BYOK_APPLICATION_SOURCE_COMMIT" "$ABDA_BYOK_IMAGE_SHA256" \
    "$ABDA_BYOK_EXPECTED_REVISION" <<'PY'
from datetime import datetime
import json
import os
import sys

snapshot_path, state_path, started_at, commit, digest, revision = sys.argv[1:]
datetime.fromisoformat(started_at.replace("Z", "+00:00"))
with open(snapshot_path, encoding="utf-8") as handle:
    metrics = json.load(handle)
state = {
    "schema": 2,
    "phase": "awaiting_call",
    "started_at": started_at,
    "source_commit": commit,
    "image_sha256": digest,
    "revision": revision,
    "metrics_before": metrics,
}
descriptor = os.open(state_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
    json.dump(state, handle, sort_keys=True)
PY
}

abda_byok_state_phase() {
  local state_path=$1
  python3 - "$state_path" "$ABDA_BYOK_APPLICATION_SOURCE_COMMIT" \
    "$ABDA_BYOK_IMAGE_SHA256" "$ABDA_BYOK_EXPECTED_REVISION" <<'PY'
from datetime import datetime, timezone
import json
import os
import sys

path, commit, digest, revision = sys.argv[1:]
if os.path.islink(path):
    raise SystemExit("STOP: the BYOK resume state must not be a symbolic link")
if os.stat(path).st_mode & 0o077:
    raise SystemExit("STOP: the BYOK resume state is not private")
with open(path, encoding="utf-8") as handle:
    state = json.load(handle)
if state.get("schema") != 2:
    raise SystemExit("STOP: the BYOK resume state schema changed")
if state.get("source_commit") != commit or state.get("image_sha256") != digest:
    raise SystemExit("STOP: the BYOK resume state belongs to another image")
if state.get("revision") != revision:
    raise SystemExit("STOP: the BYOK resume state belongs to another revision")
phase = state.get("phase")
if phase not in {"awaiting_call", "call_confirmed", "reload_confirmed", "browser_confirmed"}:
    raise SystemExit("STOP: the BYOK resume phase is invalid")
started = datetime.fromisoformat(str(state.get("started_at") or "").replace("Z", "+00:00"))
age = (datetime.now(timezone.utc) - started).total_seconds()
if age < -60 or age > 10_800:
    raise SystemExit("STOP: the BYOK resume state is outside its three-hour audit window")
metrics = state.get("metrics_before")
if not isinstance(metrics, dict) or not metrics:
    raise SystemExit("STOP: the BYOK baseline metrics are absent")
print(phase)
PY
}

abda_byok_state_value() {
  local state_path=$1
  local name=$2
  python3 - "$state_path" "$name" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    state = json.load(handle)
value = state.get(sys.argv[2])
if not isinstance(value, str) or not value:
    raise SystemExit("STOP: the BYOK resume state value is absent")
print(value)
PY
}

abda_byok_transition_state() {
  local state_path=$1
  local expected=$2
  local target=$3
  python3 - "$state_path" "$expected" "$target" <<'PY'
import json
import os
import sys

path, expected, target = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    state = json.load(handle)
if state.get("phase") != expected:
    raise SystemExit("STOP: the BYOK resume phase changed unexpectedly")
state["phase"] = target
temporary = path + ".new"
descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
    json.dump(state, handle, sort_keys=True)
os.replace(temporary, path)
PY
}

abda_byok_compare_metrics() {
  local state_path=$1
  local after_path=$2
  local result_path=$3
  python3 - "$state_path" "$after_path" "$result_path" <<'PY'
import json
import os
import sys

state_path, after_path, result_path = sys.argv[1:]
with open(state_path, encoding="utf-8") as handle:
    before = json.load(handle)["metrics_before"]
with open(after_path, encoding="utf-8") as handle:
    after = json.load(handle)
event_name = "abda_llm_usage_events_total"
for name, value in before.items():
    if name != event_name and after.get(name) != value:
        raise SystemExit(f"STOP: BYOK changed protected aggregate metric {name}")
delta = after[event_name] - before[event_name]
if not 1 <= delta <= 4:
    raise SystemExit("STOP: the browser action did not create a bounded model-event increase")
descriptor = os.open(result_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
    handle.write(f"llm_usage_event_delta: {delta}\n")
    handle.write(f"trial_spent_microusd: {after['abda_trial_spent_microusd']}\n")
    handle.write(f"openrouter_emergency_spent_microusd: {after['abda_openrouter_spent_microusd']}\n")
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
if row["byok_route_logs"] > 12:
    raise SystemExit("STOP: the BYOK log window contains too many accepted-route entries")
for name in names[1:]:
    if row[name] != 0:
        raise SystemExit(f"STOP: Log Analytics found {row[name]} unsafe entries")
for name in names:
    print(f"{name}: {row[name]}")
PY
}

abda_byok_fetch_metrics() {
  local prefix=$1
  local unauthenticated_status=''
  unauthenticated_status="$(curl --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 --output "$prefix-metrics-unauth.json" \
    --write-out '%{http_code}' "$ABDA_PUBLIC_ORIGIN/internal/metrics")"
  [[ "$unauthenticated_status" == '401' ]] || \
    abda_byok_fail 'the metrics endpoint is not protected'
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    --config "$ABDA_BYOK_ROOT/metrics-curl-config" \
    "$ABDA_PUBLIC_ORIGIN/internal/metrics" --output "$prefix-metrics.txt"
  abda_byok_metrics_snapshot "$prefix-metrics.txt" "$prefix-snapshot.json"
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
    'This resume-safe gate validates one real OpenRouter BYOK browser call.' \
    'Enter the provider key only at demo.abda-nl.org, never in this terminal.' \
    'It reads aggregate metrics and count-only logs and changes no Azure configuration.'

  abda_byok_set_constants
  local command_name=''
  for command_name in az curl date mkdir python3 timeout; do
    command -v "$command_name" >/dev/null 2>&1 || \
      abda_byok_fail "required command is unavailable: $command_name"
  done
  [[ -t 0 ]] || abda_byok_fail 'BYOK acceptance requires an interactive Cloud Shell terminal'
  ABDA_BYOK_ROOT="$(mktemp -d /tmp/abda-nl-gate10-byok.XXXXXX)"
  chmod 700 "$ABDA_BYOK_ROOT"
  local state_dir="$HOME/.abda-nl-acceptance"
  [[ ! -L "$state_dir" ]] || abda_byok_fail 'the acceptance state directory must not be a symbolic link'
  mkdir -p -- "$state_dir"
  chmod 700 "$state_dir"
  ABDA_BYOK_STATE_PATH="$state_dir/byok-v2.json"

  ABDA_BYOK_SECTION='Azure identity verification'
  printf '\n[1/7] Verifying the exact Azure identity...\n'
  az account show --output json >"$ABDA_BYOK_ROOT/account.json"
  abda_byok_validate_identity "$ABDA_BYOK_ROOT/account.json"
  az account show \
    --query '{Name:name,TenantId:tenantId,User:user.name,State:state}' \
    --output table

  ABDA_BYOK_SECTION='application and public boundary verification'
  printf '\n[2/7] Verifying the exact deployed image and public BYOK boundary...\n'
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_BYOK_ROOT/app.json"
  abda_byok_validate_app "$ABDA_BYOK_ROOT/app.json"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_PUBLIC_ORIGIN/health/ready" --output "$ABDA_BYOK_ROOT/ready.json"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_PUBLIC_ORIGIN/config" --output "$ABDA_BYOK_ROOT/config.json"
  abda_byok_validate_ready "$ABDA_BYOK_ROOT/ready.json"
  abda_byok_validate_config "$ABDA_BYOK_ROOT/config.json"
  printf 'application_revision: %s\n' "$ABDA_BYOK_EXPECTED_REVISION"
  printf 'byok_enabled: true\n'
  printf 'byok_keys_stored: false\n'

  ABDA_BYOK_SECTION='protected metrics loading'
  printf '\n[3/7] Loading the protected metrics credential without displaying it...\n'
  az containerapp secret list \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --show-values --output json >"$ABDA_BYOK_ROOT/secrets.json"
  abda_byok_load_metrics_token \
    "$ABDA_BYOK_ROOT/secrets.json" "$ABDA_BYOK_ROOT/metrics-curl-config"
  printf 'protected_secret_inventory: verified\n'

  ABDA_BYOK_SECTION='baseline or resume verification'
  printf '\n[4/7] Establishing or resuming the content-free accounting baseline...\n'
  local phase=''
  if [[ -e "$ABDA_BYOK_STATE_PATH" ]]; then
    phase="$(abda_byok_state_phase "$ABDA_BYOK_STATE_PATH")"
    printf 'resume_phase: %s\n' "$phase"
    printf 'A prior baseline was found. Do not repeat a successful browser model call.\n'
  else
    abda_byok_fetch_metrics "$ABDA_BYOK_ROOT/before"
    local started_at=''
    started_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
    abda_byok_create_state \
      "$ABDA_BYOK_ROOT/before-snapshot.json" "$ABDA_BYOK_STATE_PATH" "$started_at"
    phase='awaiting_call'
    printf 'resume_phase: new_baseline\n'
  fi

  ABDA_BYOK_SECTION='browser BYOK acceptance'
  printf '\n[5/7] Completing one browser call and key-lifetime checks...\n'
  if [[ "$phase" == 'awaiting_call' ]]; then
    printf '%s\n' \
      'In the same verified account at demo.abda-nl.org:' \
      '  1. Open Research workspace, then AI access.' \
      '  2. Choose Own provider key, OpenRouter, and Gemini 3.7 Flash.' \
      '  3. Paste the current OpenRouter key only into the browser password field.' \
      '  4. Ask exactly one short question and wait for a useful Own key answer.' \
      'If this call already succeeded before an interruption, do not repeat it.'
    local confirmation=''
    read -r -p 'Type BYOK_OPENROUTER_CALL_CONFIRMED after that one call: ' confirmation
    [[ "$confirmation" == 'BYOK_OPENROUTER_CALL_CONFIRMED' ]] || \
      abda_byok_fail 'the successful browser call was not confirmed'
    abda_byok_transition_state "$ABDA_BYOK_STATE_PATH" awaiting_call call_confirmed
    phase='call_confirmed'
  fi
  if [[ "$phase" == 'call_confirmed' ]]; then
    printf 'Reload the page and confirm that the provider-key field is empty.\n'
    local confirmation=''
    read -r -p 'Type BYOK_RELOAD_CLEAR_CONFIRMED: ' confirmation
    [[ "$confirmation" == 'BYOK_RELOAD_CLEAR_CONFIRMED' ]] || \
      abda_byok_fail 'reload clearing was not confirmed'
    abda_byok_transition_state "$ABDA_BYOK_STATE_PATH" call_confirmed reload_confirmed
    phase='reload_confirmed'
  fi
  if [[ "$phase" == 'reload_confirmed' ]]; then
    printf '%s\n' \
      'Re-enter and apply the key without calling the model.' \
      'Sign out, sign back in, and confirm that the provider-key field is empty.'
    local confirmation=''
    read -r -p 'Type BYOK_SIGNOUT_CLEAR_CONFIRMED: ' confirmation
    [[ "$confirmation" == 'BYOK_SIGNOUT_CLEAR_CONFIRMED' ]] || \
      abda_byok_fail 'sign-out clearing was not confirmed'
    abda_byok_transition_state "$ABDA_BYOK_STATE_PATH" reload_confirmed browser_confirmed
    phase='browser_confirmed'
  fi
  [[ "$phase" == 'browser_confirmed' ]] || \
    abda_byok_fail 'the browser acceptance phase did not complete'
  printf 'browser_byok_call: confirmed\n'
  printf 'browser_reload_cleared_key: confirmed\n'
  printf 'browser_signout_cleared_key: confirmed\n'

  ABDA_BYOK_SECTION='aggregate accounting verification'
  printf '\n[6/7] Proving funded and emergency ledgers were unchanged...\n'
  abda_byok_fetch_metrics "$ABDA_BYOK_ROOT/after"
  abda_byok_compare_metrics \
    "$ABDA_BYOK_STATE_PATH" "$ABDA_BYOK_ROOT/after-snapshot.json" \
    "$ABDA_BYOK_ROOT/metrics-result.txt"
  cat "$ABDA_BYOK_ROOT/metrics-result.txt"

  ABDA_BYOK_SECTION='count-only log audit'
  printf '\n[7/7] Waiting up to three minutes for sanitized route evidence...\n'
  az monitor log-analytics workspace show \
    --workspace-name "$ABDA_LOGS_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_BYOK_ROOT/workspace.json"
  az containerapp env show \
    --name "$ABDA_ENVIRONMENT_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_BYOK_ROOT/environment.json"
  local workspace_id=''
  workspace_id="$(abda_byok_validate_logging_configuration \
    "$ABDA_BYOK_ROOT/workspace.json" "$ABDA_BYOK_ROOT/environment.json")"
  local started_at=''
  started_at="$(abda_byok_state_value "$ABDA_BYOK_STATE_PATH" started_at)"
  local logs_query=""
  logs_query="$(cat <<KQL
ContainerAppConsoleLogs_CL
| where TimeGenerated >= datetime($started_at)
    and ContainerAppName_s == 'abda-nl-stg-web'
    and RevisionName_s == '$ABDA_BYOK_EXPECTED_REVISION'
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

with open(sys.argv[1], "x", encoding="utf-8") as handle:
    json.dump({"query": sys.argv[2], "timespan": "PT3H"}, handle)
PY
  local token_status=0
  set +e
  timeout --foreground --signal=TERM --kill-after=5s 30s \
    az account get-access-token \
      --resource https://api.loganalytics.io \
      --only-show-errors --output json >"$ABDA_BYOK_ROOT/log-token.json"
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
      "$ABDA_BYOK_ROOT/log-result.txt" \
      "$ABDA_BYOK_ROOT/log-validation.err"
    local log_status=0
    set +e
    curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
      --connect-timeout 10 --max-time 30 \
      --config "$ABDA_BYOK_ROOT/log-curl-config" \
      --header 'Content-Type: application/json' --request POST \
      --data-binary "@$ABDA_BYOK_ROOT/log-query.json" \
      "https://api.loganalytics.azure.com/v1/workspaces/$workspace_id/query" \
      --output "$ABDA_BYOK_ROOT/log-api-response.json"
    log_status=$?
    set -e
    if (( log_status == 0 )); then
      abda_byok_convert_log_api_response \
        "$ABDA_BYOK_ROOT/log-api-response.json" "$ABDA_BYOK_ROOT/log-summary.json"
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
  (( log_ready == 1 )) || \
    abda_byok_fail 'BYOK log evidence was not ingested within three minutes'

  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_BYOK_ROOT/final-app.json"
  abda_byok_validate_app "$ABDA_BYOK_ROOT/final-app.json"
  printf '\nABDA-NL live BYOK acceptance status:\n'
  printf 'script_revision: %s\n' "$ABDA_BYOK_SCRIPT_REVISION"
  printf 'application_source_commit: %s\n' "$ABDA_BYOK_APPLICATION_SOURCE_COMMIT"
  printf 'image_digest: sha256:%s\n' "$ABDA_BYOK_IMAGE_SHA256"
  printf 'subscription_id: %s\n' "$ABDA_EXPECTED_SUBSCRIPTION"
  printf 'resource_group: %s\n' "$ABDA_RESOURCE_GROUP"
  printf 'application_revision: %s\n' "$ABDA_BYOK_EXPECTED_REVISION"
  printf 'public_origin: %s\n' "$ABDA_PUBLIC_ORIGIN"
  cat "$ABDA_BYOK_ROOT/metrics-result.txt"
  cat "$ABDA_BYOK_ROOT/log-result.txt"
  printf 'provider: openrouter\n'
  printf 'model: gemini-3.7-flash\n'
  printf 'billing_source: byok\n'
  printf 'trial_ledger_unchanged: true\n'
  printf 'openrouter_emergency_ledger_unchanged: true\n'
  printf 'browser_reload_cleared_key: confirmed\n'
  printf 'browser_signout_cleared_key: confirmed\n'
  printf 'provider_key_entered_in_shell: false\n'
  printf 'secret_values_printed: false\n'
  printf 'raw_log_messages_printed: false\n'
  printf 'azure_configuration_changed: false\n'
  printf 'result: LIVE_BYOK_PRIVACY_AND_ACCOUNTING_ACCEPTANCE_VERIFIED\n'
  printf 'Send this status and the shell exit code to Codex.\n'
  ABDA_BYOK_COMPLETE=1
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_byok_main "$@"
fi
