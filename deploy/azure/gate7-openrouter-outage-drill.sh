#!/usr/bin/env bash

# Execute one isolated OpenRouter outage drill inside the exact healthy staging
# web revision. Azure configuration and public failover remain unchanged.

ABDA_DRILL_SCRIPT_REVISION='1'
ABDA_DRILL_SOURCE_COMMIT='448510936c69d485cf9b4e834adea69becf6b114'
ABDA_DRILL_IMAGE_SHA256='11861402c8fa3fd677848f94155e29065ebafd9a4a76b03e41b1cf48312e5c58'
ABDA_DRILL_REVISION='abda-nl-stg-web--rc-4485109'
ABDA_DRILL_ROOT=''

abda_drill_cleanup() {
  local exit_code=$?
  set +e
  if [[ "${ABDA_DRILL_ROOT:-}" == /tmp/abda-nl-outage-drill.* &&
        -d "${ABDA_DRILL_ROOT:-}" ]]; then
    rm -rf -- "$ABDA_DRILL_ROOT"
  fi
  printf '\nGate 7 shell exit code: %s\n' "$exit_code"
}

abda_drill_error() {
  local exit_code=$?
  trap - ERR
  printf '\nSTOP: Gate 7 failed in section: %s\n' \
    "${ABDA_DRILL_SECTION:-unknown}" >&2
  printf '%s\n' \
    'Do not enable public OpenRouter failover or rerun the paid drill blindly.' \
    'Send the visible status and shell exit code to Codex.' >&2
  exit "$exit_code"
}

abda_drill_interrupt() {
  trap - ERR INT
  printf '\nSTOP: Gate 7 was interrupted in section: %s\n' \
    "${ABDA_DRILL_SECTION:-unknown}" >&2
  printf '%s\n' \
    'Do not rerun the paid drill until the ledgers and temporary switch are inspected.' >&2
  exit 130
}

abda_drill_fail() {
  printf 'STOP: %s\n' "$*" >&2
  return 1
}

abda_drill_set_constants() {
  ABDA_EXPECTED_SUBSCRIPTION='00e62f6e-2174-40b2-b428-8ebfd7c2ac54'
  ABDA_EXPECTED_TENANT='040f05eb-33ab-462f-af54-fb4bedb055ae'
  ABDA_EXPECTED_USER='hliu2@cloudbank.org'
  ABDA_RESOURCE_GROUP='abda-nl-staging'
  ABDA_APP_NAME='abda-nl-stg-web'
  ABDA_CONTAINER_NAME='web'
  ABDA_IMAGE_REPOSITORY='ghcr.io/liu-hy/abda-nl'
  ABDA_PUBLIC_ORIGIN='https://demo.abda-nl.org'
  ABDA_TRIAL_MAX_USERS='10'
  ABDA_TRIAL_GRANT_MICROUSD='5000000'
  ABDA_TRIAL_BUDGET_MICROUSD='50000000'
  ABDA_OPENROUTER_BUDGET_MICROUSD='500000000'
}

abda_drill_validate_identity() {
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

abda_drill_validate_app() {
  local path=$1
  python3 - "$path" "$ABDA_APP_NAME" "$ABDA_DRILL_REVISION" \
    "$ABDA_IMAGE_REPOSITORY@sha256:$ABDA_DRILL_IMAGE_SHA256" \
    "$ABDA_PUBLIC_ORIGIN" "$ABDA_TRIAL_MAX_USERS" \
    "$ABDA_TRIAL_GRANT_MICROUSD" "$ABDA_TRIAL_BUDGET_MICROUSD" \
    "$ABDA_OPENROUTER_BUDGET_MICROUSD" <<'PY'
import json
import sys

(
    path,
    expected_app,
    expected_revision,
    expected_image,
    expected_origin,
    max_users,
    grant_microusd,
    trial_budget_microusd,
    openrouter_budget_microusd,
) = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    app = json.load(handle)
properties = app.get("properties") or {}
template = properties.get("template") or {}
containers = template.get("containers") or []
if app.get("name") != expected_app or len(containers) != 1:
    raise SystemExit("STOP: the Container App identity changed")
if properties.get("provisioningState") != "Succeeded":
    raise SystemExit("STOP: the Container App is not provisioned")
if properties.get("runningStatus") != "Running":
    raise SystemExit("STOP: the Container App is not running")
if (
    properties.get("latestRevisionName") != expected_revision
    or properties.get("latestReadyRevisionName") != expected_revision
):
    raise SystemExit("STOP: the exact release-candidate revision is not ready")
container = containers[0]
if container.get("name") != "web" or container.get("image") != expected_image:
    raise SystemExit("STOP: the exact release-candidate image is not deployed")
environment = {str(item.get("name") or ""): item for item in container.get("env") or []}
expected = {
    "ABDA_ENVIRONMENT": "staging",
    "ABDA_PUBLIC_BASE_URL": expected_origin,
    "ABDA_TRIAL_ENABLED": "true",
    "ABDA_TRIAL_MAX_USERS": max_users,
    "ABDA_TRIAL_GRANT_MICROUSD": grant_microusd,
    "ABDA_TRIAL_BUDGET_MICROUSD": trial_budget_microusd,
    "ABDA_LLM_DEFAULT_PROFILE": "balanced",
    "ABDA_OPENROUTER_FAILOVER_ENABLED": "false",
    "ABDA_OPENROUTER_BUDGET_MICROUSD": openrouter_budget_microusd,
}
for name, wanted in expected.items():
    actual = str(environment.get(name, {}).get("value") or "")
    if name in {"ABDA_TRIAL_ENABLED", "ABDA_OPENROUTER_FAILOVER_ENABLED"}:
        actual = actual.lower()
    if actual != wanted:
        raise SystemExit(f"STOP: deployed setting {name} changed")
for name, secret_ref in {
    "ABDA_DATABASE_URL": "database-url",
    "ABDA_METRICS_TOKEN": "metrics-token",
    "OPENROUTER_API_KEY": "openrouter-api-key",
}.items():
    if environment.get(name, {}).get("secretRef") != secret_ref:
        raise SystemExit(f"STOP: deployed secret reference {name} changed")
PY
}

abda_drill_select_replica() {
  local path=$1
  python3 - "$path" "$ABDA_CONTAINER_NAME" <<'PY'
import json
import sys

path, expected_container = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    replicas = json.load(handle)
if not isinstance(replicas, list) or not 1 <= len(replicas) <= 3:
    raise SystemExit("STOP: the release candidate has an unexpected replica count")
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
    raise SystemExit("STOP: no ready release-candidate replica is available")
print(sorted(eligible)[0])
PY
}

abda_drill_write_metrics_config() {
  local secrets_path=$1
  local config_path=$2
  python3 - "$secrets_path" "$config_path" <<'PY'
import json
import os
import sys

secrets_path, config_path = sys.argv[1:]
with open(secrets_path, encoding="utf-8") as handle:
    items = json.load(handle)
matches = [str(item.get("value") or "") for item in items if item.get("name") == "metrics-token"]
if len(matches) != 1 or not 32 <= len(matches[0]) <= 512 or any(c.isspace() for c in matches[0]):
    raise SystemExit("STOP: the protected metrics token is invalid")
with open(config_path, "x", encoding="utf-8") as handle:
    handle.write(f'header = "Authorization: Bearer {matches[0]}"\n')
os.chmod(config_path, 0o600)
PY
}

abda_drill_metric_snapshot() {
  local metrics_path=$1
  local output_path=$2
  python3 - "$metrics_path" "$output_path" \
    "$ABDA_TRIAL_MAX_USERS" "$ABDA_TRIAL_GRANT_MICROUSD" \
    "$ABDA_TRIAL_BUDGET_MICROUSD" "$ABDA_OPENROUTER_BUDGET_MICROUSD" <<'PY'
import json
import sys

(
    metrics_path,
    output_path,
    max_users,
    grant_microusd,
    trial_budget_microusd,
    openrouter_budget_microusd,
) = sys.argv[1:]
samples = {}
with open(metrics_path, encoding="utf-8") as handle:
    for raw_line in handle:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) == 2:
            samples.setdefault(fields[0], []).append(fields[1])


def integer(name):
    values = samples.get(name) or []
    if len(values) != 1:
        raise SystemExit(f"STOP: metrics must contain exactly one {name} sample")
    try:
        value = int(values[0])
    except ValueError as exc:
        raise SystemExit(f"STOP: metric {name} is not an integer") from exc
    if value < 0:
        raise SystemExit(f"STOP: metric {name} is negative")
    return value


snapshot = {
    name: integer(f"abda_{name}")
    for name in (
        "trial_enabled",
        "trial_max_users",
        "trial_grant_microusd",
        "trial_budget_microusd",
        "trial_activations",
        "trial_allocated_microusd",
        "trial_spent_microusd",
        "trial_reserved_microusd",
        "trial_uncertain_charged_reservations",
        "trial_uncertain_charged_microusd",
        "openrouter_enabled",
        "openrouter_budget_microusd",
        "openrouter_spent_microusd",
        "openrouter_reserved_microusd",
        "openrouter_uncertain_charged_reservations",
        "openrouter_uncertain_charged_microusd",
        "llm_usage_events_total",
    )
}
if (
    snapshot["trial_enabled"] != 1
    or snapshot["trial_max_users"] != int(max_users)
    or snapshot["trial_grant_microusd"] != int(grant_microusd)
    or snapshot["trial_budget_microusd"] != int(trial_budget_microusd)
):
    raise SystemExit("STOP: the live funded trial boundary changed")
if not 1 <= snapshot["trial_activations"] <= snapshot["trial_max_users"]:
    raise SystemExit("STOP: the trial activation count is outside the pilot boundary")
if snapshot["trial_allocated_microusd"] != (
    snapshot["trial_activations"] * snapshot["trial_grant_microusd"]
):
    raise SystemExit("STOP: trial allocation does not reconcile")
if snapshot["trial_spent_microusd"] > snapshot["trial_allocated_microusd"]:
    raise SystemExit("STOP: trial spending exceeds allocated credit")
if (
    snapshot["trial_reserved_microusd"]
    or snapshot["trial_uncertain_charged_reservations"]
    or snapshot["trial_uncertain_charged_microusd"]
):
    raise SystemExit("STOP: the trial ledger is not safely idle")
if snapshot["openrouter_enabled"] != 0:
    raise SystemExit("STOP: the OpenRouter emergency switch is not disabled")
if snapshot["openrouter_budget_microusd"] != int(openrouter_budget_microusd):
    raise SystemExit("STOP: the OpenRouter emergency budget changed")
if (
    snapshot["openrouter_reserved_microusd"]
    or snapshot["openrouter_uncertain_charged_reservations"]
    or snapshot["openrouter_uncertain_charged_microusd"]
):
    raise SystemExit("STOP: the OpenRouter ledger is not safely idle")
with open(output_path, "x", encoding="utf-8") as handle:
    json.dump(snapshot, handle, sort_keys=True)
PY
}

abda_drill_extract_receipt() {
  local log_path=$1
  local receipt_path=$2
  python3 - "$log_path" "$receipt_path" <<'PY'
import json
import re
import sys

log_path, receipt_path = sys.argv[1:]
with open(log_path, encoding="utf-8", errors="replace") as handle:
    text = handle.read().replace("\r", "")
text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
decoder = json.JSONDecoder()
receipts = []
for index, character in enumerate(text):
    if character != "{":
        continue
    try:
        value, _ = decoder.raw_decode(text[index:])
    except json.JSONDecodeError:
        continue
    if isinstance(value, dict) and value.get("action") == "openrouter-outage-drill":
        receipts.append(value)
if len(receipts) != 1:
    raise SystemExit("STOP: the container output did not contain exactly one drill receipt")
with open(receipt_path, "x", encoding="utf-8") as handle:
    json.dump(receipts[0], handle, sort_keys=True)
PY
}

abda_drill_validate_result() {
  local before_path=$1
  local receipt_path=$2
  local after_path=$3
  python3 - "$before_path" "$receipt_path" "$after_path" <<'PY'
import json
import re
import sys

before_path, receipt_path, after_path = sys.argv[1:]
with open(before_path, encoding="utf-8") as handle:
    before = json.load(handle)
with open(receipt_path, encoding="utf-8") as handle:
    receipt = json.load(handle)
with open(after_path, encoding="utf-8") as handle:
    after = json.load(handle)
if receipt.get("result") != "OPENROUTER_OUTAGE_DRILL_PASSED":
    raise SystemExit("STOP: the container drill did not pass")
expected = {
    "environment": "staging",
    "public_origin": "https://demo.abda-nl.org",
    "profile": "balanced",
    "primary_route": "cloudbank-claude-sonnet-4-6",
    "injected_primary_status": 503,
    "fallback_route": "openrouter-gemini-3.7-flash",
    "max_output_tokens": 32,
    "marker_verified": True,
    "mutated": True,
}
for name, wanted in expected.items():
    if receipt.get(name) != wanted:
        raise SystemExit(f"STOP: drill receipt field {name} changed")
request_id = str(receipt.get("request_id") or "")
if not re.fullmatch(r"outage-drill-[0-9a-f]{32}", request_id):
    raise SystemExit("STOP: the drill request identifier is invalid")
audit = receipt.get("audit") or {}
cost = audit.get("settled_cost_microusd")
if not isinstance(cost, int) or not 1 <= cost <= 25_000:
    raise SystemExit("STOP: the drill settled cost is outside its reviewed ceiling")
if (
    audit.get("trial_recorded_cost_microusd") != cost
    or audit.get("openrouter_recorded_cost_microusd") != cost
    or audit.get("provider_attempt_count") != 1
    or audit.get("trial_reserved_microusd") != 0
    or audit.get("openrouter_reserved_microusd") != 0
    or audit.get("openrouter_enabled_restored") is not True
):
    raise SystemExit("STOP: the drill receipt did not reconcile both ledgers")
if after["trial_spent_microusd"] < before["trial_spent_microusd"] + cost:
    raise SystemExit("STOP: the aggregate trial ledger did not retain the receipt cost")
if after["openrouter_spent_microusd"] != before["openrouter_spent_microusd"] + cost:
    raise SystemExit("STOP: the aggregate OpenRouter ledger delta differs from the receipt")
if after["llm_usage_events_total"] < before["llm_usage_events_total"] + 1:
    raise SystemExit("STOP: the aggregate usage-event count did not retain the drill event")
for name in (
    "trial_enabled",
    "trial_max_users",
    "trial_grant_microusd",
    "trial_budget_microusd",
    "trial_activations",
    "trial_allocated_microusd",
    "openrouter_budget_microusd",
):
    if after[name] != before[name]:
        raise SystemExit(f"STOP: live boundary {name} changed during the drill")
for name in (
    "trial_reserved_microusd",
    "trial_uncertain_charged_reservations",
    "trial_uncertain_charged_microusd",
    "openrouter_enabled",
    "openrouter_reserved_microusd",
    "openrouter_uncertain_charged_reservations",
    "openrouter_uncertain_charged_microusd",
):
    if after[name] != 0:
        raise SystemExit(f"STOP: post-drill state {name} is not safely idle")
print(f"request_id: {request_id}")
print(f"settled_cost_microusd: {cost}")
print(f"trial_spent_microusd: {after['trial_spent_microusd']}")
print(f"openrouter_spent_microusd: {after['openrouter_spent_microusd']}")
print("openrouter_enabled_restored: true")
PY
}

abda_drill_fetch_metrics() {
  local output_path=$1
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    --config "$ABDA_DRILL_ROOT/metrics-curl-config" \
    "$ABDA_PUBLIC_ORIGIN/internal/metrics" --output "$output_path"
}

abda_drill_main() {
  set -Eeuo pipefail
  set +x
  umask 077
  unset HISTFILE
  trap abda_drill_error ERR
  trap abda_drill_cleanup EXIT
  trap abda_drill_interrupt INT
  ABDA_DRILL_SECTION='bootstrap'

  printf 'ABDA-NL Gate 7 OpenRouter outage drill script revision: %s\n' \
    "$ABDA_DRILL_SCRIPT_REVISION"
  printf '%s\n' \
    'This gate runs one content-free, at-most-32-token paid fallback call.' \
    'It injects a synthetic CloudBank 503 inside the operator process.' \
    'It does not change Azure configuration or enable public OpenRouter failover.'

  abda_drill_set_constants
  local command_name=''
  for command_name in az curl grep python3 tee; do
    command -v "$command_name" >/dev/null 2>&1 || \
      abda_drill_fail "required command is unavailable: $command_name"
  done
  [[ -t 0 ]] || abda_drill_fail 'Gate 7 requires an interactive Cloud Shell terminal'
  ABDA_DRILL_ROOT="$(mktemp -d /tmp/abda-nl-outage-drill.XXXXXX)"
  chmod 700 "$ABDA_DRILL_ROOT"
  az containerapp exec --help >"$ABDA_DRILL_ROOT/containerapp-exec.help"
  for option in --name --resource-group --revision --replica --container --command; do
    grep -Fq -- "$option" "$ABDA_DRILL_ROOT/containerapp-exec.help" || \
      abda_drill_fail "az containerapp exec does not support $option"
  done

  ABDA_DRILL_SECTION='Azure identity verification'
  printf '\n[1/7] Verifying the exact Azure identity...\n'
  az account show --output json >"$ABDA_DRILL_ROOT/account.json"
  abda_drill_validate_identity "$ABDA_DRILL_ROOT/account.json"
  az account show \
    --query '{Name:name,TenantId:tenantId,User:user.name,State:state}' \
    --output table

  ABDA_DRILL_SECTION='release-candidate revision verification'
  printf '\n[2/7] Verifying the deployed candidate and selecting a ready replica...\n'
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_DRILL_ROOT/app.json"
  abda_drill_validate_app "$ABDA_DRILL_ROOT/app.json"
  az containerapp replica list \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --revision "$ABDA_DRILL_REVISION" --output json \
    >"$ABDA_DRILL_ROOT/replicas.json"
  local replica_name=''
  replica_name="$(abda_drill_select_replica "$ABDA_DRILL_ROOT/replicas.json")"
  printf 'release_candidate_revision: %s\n' "$ABDA_DRILL_REVISION"
  printf 'selected_ready_replica: %s\n' "$replica_name"

  ABDA_DRILL_SECTION='protected pre-drill accounting verification'
  printf '\n[3/7] Verifying readiness and the safely idle accounting state...\n'
  az containerapp secret list \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --show-values --only-show-errors --output json \
    >"$ABDA_DRILL_ROOT/secrets.json"
  abda_drill_write_metrics_config \
    "$ABDA_DRILL_ROOT/secrets.json" "$ABDA_DRILL_ROOT/metrics-curl-config"
  rm -f -- "$ABDA_DRILL_ROOT/secrets.json"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_PUBLIC_ORIGIN/health/ready" \
    --output "$ABDA_DRILL_ROOT/ready.json"
  python3 - "$ABDA_DRILL_ROOT/ready.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    if json.load(handle) != {"status": "ready"}:
        raise SystemExit("STOP: the public origin is not ready")
PY
  abda_drill_fetch_metrics "$ABDA_DRILL_ROOT/before.metrics"
  abda_drill_metric_snapshot \
    "$ABDA_DRILL_ROOT/before.metrics" "$ABDA_DRILL_ROOT/before.json"
  python3 - "$ABDA_DRILL_ROOT/before.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    state = json.load(handle)
if state["openrouter_spent_microusd"] != 0:
    raise SystemExit(
        "STOP: a prior OpenRouter spend exists; inspect it before any paid rerun"
    )
print(f"trial_spent_microusd_before: {state['trial_spent_microusd']}")
print("openrouter_enabled_before: 0")
print("openrouter_spent_microusd_before: 0")
print("all_reservations_before: 0")
PY

  printf '\n[4/7] Awaiting the one controlled-drill confirmation...\n'
  printf '%s\n' \
    'The next command asks for the verified email of an active trial account.' \
    'The email prompt is hidden and the value is not placed in shell history.' \
    'The container command then asks for its own exact confirmation.' \
    'Type RUN_ABDA_GATE7_OUTAGE_DRILL to continue, or press Enter to cancel.'
  local confirmation=''
  IFS= read -r -p 'Confirmation: ' confirmation
  if [[ "$confirmation" != 'RUN_ABDA_GATE7_OUTAGE_DRILL' ]]; then
    printf 'Cancelled without a provider call or state change.\n'
    return 0
  fi

  ABDA_DRILL_SECTION='isolated container outage drill execution'
  printf '\n[5/7] Running the isolated drill inside the exact healthy replica...\n'
  printf '%s\n' \
    'At the hidden email prompt, enter the same account that activated the trial.' \
    'At the next prompt, type RUN_STAGING_OPENROUTER_OUTAGE_DRILL.'
  local exec_status=0
  set +e
  az containerapp exec \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --revision "$ABDA_DRILL_REVISION" --replica "$replica_name" \
    --container "$ABDA_CONTAINER_NAME" \
    --command "/opt/venv/bin/python -m app.cli.outage_drill --expected-origin $ABDA_PUBLIC_ORIGIN --execute" \
    2>&1 | tee "$ABDA_DRILL_ROOT/container-exec.log"
  exec_status=${PIPESTATUS[0]}
  set -e

  ABDA_DRILL_SECTION='post-drill accounting recovery verification'
  printf '\n[6/7] Verifying restoration and settled accounting...\n'
  abda_drill_fetch_metrics "$ABDA_DRILL_ROOT/after.metrics"
  abda_drill_metric_snapshot \
    "$ABDA_DRILL_ROOT/after.metrics" "$ABDA_DRILL_ROOT/after.json"
  if (( exec_status != 0 )); then
    abda_drill_fail "Azure container exec exited with status $exec_status"
  fi
  abda_drill_extract_receipt \
    "$ABDA_DRILL_ROOT/container-exec.log" "$ABDA_DRILL_ROOT/receipt.json"
  abda_drill_validate_result \
    "$ABDA_DRILL_ROOT/before.json" "$ABDA_DRILL_ROOT/receipt.json" \
    "$ABDA_DRILL_ROOT/after.json" \
    | tee "$ABDA_DRILL_ROOT/sanitized-result.txt"

  ABDA_DRILL_SECTION='final public safety verification'
  printf '\n[7/7] Rechecking the public origin and disabled deployment setting...\n'
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_PUBLIC_ORIGIN/health/ready" --output "$ABDA_DRILL_ROOT/final-ready.json"
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_DRILL_ROOT/final-app.json"
  abda_drill_validate_app "$ABDA_DRILL_ROOT/final-app.json"

  printf '\nABDA-NL Gate 7 OpenRouter outage drill status:\n'
  printf 'script_revision: %s\n' "$ABDA_DRILL_SCRIPT_REVISION"
  printf 'application_source_commit: %s\n' "$ABDA_DRILL_SOURCE_COMMIT"
  printf 'image_digest: sha256:%s\n' "$ABDA_DRILL_IMAGE_SHA256"
  printf 'subscription_id: %s\n' "$ABDA_EXPECTED_SUBSCRIPTION"
  printf 'resource_group: %s\n' "$ABDA_RESOURCE_GROUP"
  printf 'application_revision: %s\n' "$ABDA_DRILL_REVISION"
  printf 'public_origin: %s\n' "$ABDA_PUBLIC_ORIGIN"
  cat "$ABDA_DRILL_ROOT/sanitized-result.txt"
  printf 'public_openrouter_failover_enabled: false\n'
  printf 'azure_configuration_changed: false\n'
  printf 'result: CONTROLLED_OPENROUTER_OUTAGE_DRILL_VERIFIED\n'
  printf '%s\n' \
    'Stop here. Do not enable public OpenRouter failover yet.' \
    'Send this status and the shell exit code to Codex.'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_drill_main "$@"
fi
