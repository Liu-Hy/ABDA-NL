#!/usr/bin/env bash

# Read-only recovery audit for the first live Gate 7 call. The call reached the
# reviewed fallback but its 32-token completion did not include the marker.

ABDA_RECOVERY_SCRIPT_REVISION='1'
ABDA_RECOVERY_APP_SOURCE_COMMIT='448510936c69d485cf9b4e834adea69becf6b114'
ABDA_RECOVERY_IMAGE_SHA256='11861402c8fa3fd677848f94155e29065ebafd9a4a76b03e41b1cf48312e5c58'
ABDA_RECOVERY_REVISION='abda-nl-stg-web--rc-4485109'
ABDA_RECOVERY_TRIAL_SPENT_BEFORE='60626'
ABDA_RECOVERY_OPENROUTER_SPENT_BEFORE='0'
ABDA_RECOVERY_MAX_DRILL_COST='25000'
ABDA_RECOVERY_ROOT=''

abda_recovery_cleanup() {
  local exit_code=$?
  set +e
  if [[ "${ABDA_RECOVERY_ROOT:-}" == /tmp/abda-nl-gate7-recovery.* &&
        -d "${ABDA_RECOVERY_ROOT:-}" ]]; then
    rm -rf -- "$ABDA_RECOVERY_ROOT"
  fi
  printf '\nGate 7 recovery shell exit code: %s\n' "$exit_code"
}

abda_recovery_error() {
  local exit_code=$?
  trap - ERR
  printf '\nSTOP: Gate 7 recovery audit failed in section: %s\n' \
    "${ABDA_RECOVERY_SECTION:-unknown}" >&2
  printf '%s\n' \
    'No Azure configuration or provider call was made.' \
    'Do not rerun the paid outage drill. Send this status to Codex.' >&2
  exit "$exit_code"
}

abda_recovery_fail() {
  printf 'STOP: %s\n' "$*" >&2
  return 1
}

abda_recovery_set_constants() {
  ABDA_EXPECTED_SUBSCRIPTION='00e62f6e-2174-40b2-b428-8ebfd7c2ac54'
  ABDA_EXPECTED_TENANT='040f05eb-33ab-462f-af54-fb4bedb055ae'
  ABDA_EXPECTED_USER='hliu2@cloudbank.org'
  ABDA_RESOURCE_GROUP='abda-nl-staging'
  ABDA_APP_NAME='abda-nl-stg-web'
  ABDA_IMAGE_REPOSITORY='ghcr.io/liu-hy/abda-nl'
  ABDA_PUBLIC_ORIGIN='https://demo.abda-nl.org'
  ABDA_TRIAL_MAX_USERS='10'
  ABDA_TRIAL_GRANT_MICROUSD='5000000'
  ABDA_TRIAL_BUDGET_MICROUSD='50000000'
  ABDA_OPENROUTER_BUDGET_MICROUSD='500000000'
  ABDA_OPENROUTER_MODELS_URL='https://openrouter.ai/api/v1/models'
}

abda_recovery_validate_identity() {
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

abda_recovery_validate_app() {
  local path=$1
  python3 - "$path" "$ABDA_APP_NAME" "$ABDA_RECOVERY_REVISION" \
    "$ABDA_IMAGE_REPOSITORY@sha256:$ABDA_RECOVERY_IMAGE_SHA256" \
    "$ABDA_PUBLIC_ORIGIN" <<'PY'
import json
import sys

path, expected_app, expected_revision, expected_image, expected_origin = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    app = json.load(handle)
properties = app.get("properties") or {}
containers = ((properties.get("template") or {}).get("containers") or [])
if app.get("name") != expected_app or len(containers) != 1:
    raise SystemExit("STOP: the Container App identity changed")
if properties.get("provisioningState") != "Succeeded" or properties.get("runningStatus") != "Running":
    raise SystemExit("STOP: the Container App is not healthy")
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
    "ABDA_OPENROUTER_FAILOVER_ENABLED": "false",
}
for name, wanted in expected.items():
    actual = str(environment.get(name, {}).get("value") or "")
    if name in {"ABDA_TRIAL_ENABLED", "ABDA_OPENROUTER_FAILOVER_ENABLED"}:
        actual = actual.lower()
    if actual != wanted:
        raise SystemExit(f"STOP: deployed setting {name} changed")
if environment.get("ABDA_METRICS_TOKEN", {}).get("secretRef") != "metrics-token":
    raise SystemExit("STOP: the protected metrics secret reference changed")
PY
}

abda_recovery_validate_model_metadata() {
  local path=$1
  python3 - "$path" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    data = json.load(handle)
matches = [item for item in data.get("data", []) if item.get("id") == "google/gemini-3.7-flash"]
if len(matches) != 1:
    raise SystemExit("STOP: OpenRouter did not return the exact reviewed model")
model = matches[0]
reasoning = model.get("reasoning") or {}
if (
    reasoning.get("mandatory") is not True
    or reasoning.get("default_enabled") is not True
    or reasoning.get("default_effort") != "medium"
):
    raise SystemExit("STOP: the reviewed model reasoning contract changed")
supported = set(model.get("supported_parameters") or [])
if not {"max_tokens", "reasoning"}.issubset(supported):
    raise SystemExit("STOP: the reviewed model parameter contract changed")
print("openrouter_model: google/gemini-3.7-flash")
print("reasoning_mandatory: true")
print("reasoning_default_enabled: true")
print("reasoning_default_effort: medium")
PY
}

abda_recovery_write_metrics_config() {
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

abda_recovery_validate_metrics() {
  local path=$1
  python3 - "$path" "$ABDA_TRIAL_MAX_USERS" \
    "$ABDA_TRIAL_GRANT_MICROUSD" "$ABDA_TRIAL_BUDGET_MICROUSD" \
    "$ABDA_OPENROUTER_BUDGET_MICROUSD" \
    "$ABDA_RECOVERY_TRIAL_SPENT_BEFORE" \
    "$ABDA_RECOVERY_OPENROUTER_SPENT_BEFORE" \
    "$ABDA_RECOVERY_MAX_DRILL_COST" <<'PY'
import sys

(
    path,
    max_users,
    grant_microusd,
    trial_budget_microusd,
    openrouter_budget_microusd,
    trial_spent_before,
    openrouter_spent_before,
    max_drill_cost,
) = sys.argv[1:]
samples = {}
with open(path, encoding="utf-8") as handle:
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


trial_enabled = integer("abda_trial_enabled")
trial_max_users = integer("abda_trial_max_users")
trial_grant = integer("abda_trial_grant_microusd")
trial_budget = integer("abda_trial_budget_microusd")
activations = integer("abda_trial_activations")
allocated = integer("abda_trial_allocated_microusd")
trial_spent = integer("abda_trial_spent_microusd")
trial_reserved = integer("abda_trial_reserved_microusd")
trial_uncertain_count = integer("abda_trial_uncertain_charged_reservations")
trial_uncertain_cost = integer("abda_trial_uncertain_charged_microusd")
openrouter_enabled = integer("abda_openrouter_enabled")
openrouter_budget = integer("abda_openrouter_budget_microusd")
openrouter_spent = integer("abda_openrouter_spent_microusd")
openrouter_reserved = integer("abda_openrouter_reserved_microusd")
openrouter_uncertain_count = integer("abda_openrouter_uncertain_charged_reservations")
openrouter_uncertain_cost = integer("abda_openrouter_uncertain_charged_microusd")
if (trial_enabled, trial_max_users, trial_grant, trial_budget) != (
    1,
    int(max_users),
    int(grant_microusd),
    int(trial_budget_microusd),
):
    raise SystemExit("STOP: the live funded trial boundary changed")
if not 1 <= activations <= trial_max_users or allocated != activations * trial_grant:
    raise SystemExit("STOP: trial allocation does not reconcile")
if openrouter_enabled != 0 or openrouter_budget != int(openrouter_budget_microusd):
    raise SystemExit("STOP: the OpenRouter safety boundary changed")
if any(
    (
        trial_reserved,
        trial_uncertain_count,
        trial_uncertain_cost,
        openrouter_reserved,
        openrouter_uncertain_count,
        openrouter_uncertain_cost,
    )
):
    raise SystemExit("STOP: a post-drill reservation or uncertain charge remains")
trial_delta = trial_spent - int(trial_spent_before)
openrouter_delta = openrouter_spent - int(openrouter_spent_before)
if not 1 <= openrouter_delta <= int(max_drill_cost):
    raise SystemExit("STOP: the OpenRouter spend delta is outside the reviewed drill ceiling")
if trial_delta != openrouter_delta:
    raise SystemExit("STOP: the trial and OpenRouter ledger deltas differ")
if trial_spent > allocated:
    raise SystemExit("STOP: trial spending exceeds allocated credit")
print(f"trial_spent_microusd_before: {trial_spent_before}")
print(f"trial_spent_microusd_after: {trial_spent}")
print(f"openrouter_spent_microusd_before: {openrouter_spent_before}")
print(f"openrouter_spent_microusd_after: {openrouter_spent}")
print(f"settled_cost_microusd: {openrouter_delta}")
print("trial_reserved_microusd: 0")
print("openrouter_reserved_microusd: 0")
print("openrouter_enabled_restored: true")
PY
}

abda_recovery_main() {
  set -Eeuo pipefail
  set +x
  umask 077
  unset HISTFILE
  trap abda_recovery_error ERR
  trap abda_recovery_cleanup EXIT
  ABDA_RECOVERY_SECTION='bootstrap'

  printf 'ABDA-NL Gate 7 marker-failure recovery script revision: %s\n' \
    "$ABDA_RECOVERY_SCRIPT_REVISION"
  printf '%s\n' \
    'This audit is read-only and specific to the already completed Gate 7 call.' \
    'It does not enter the container, call a model, or change Azure configuration.'

  abda_recovery_set_constants
  local command_name=''
  for command_name in az curl python3 tee; do
    command -v "$command_name" >/dev/null 2>&1 || \
      abda_recovery_fail "required command is unavailable: $command_name"
  done
  ABDA_RECOVERY_ROOT="$(mktemp -d /tmp/abda-nl-gate7-recovery.XXXXXX)"
  chmod 700 "$ABDA_RECOVERY_ROOT"

  ABDA_RECOVERY_SECTION='Azure identity verification'
  printf '\n[1/5] Verifying the exact Azure identity...\n'
  az account show --output json >"$ABDA_RECOVERY_ROOT/account.json"
  abda_recovery_validate_identity "$ABDA_RECOVERY_ROOT/account.json"
  az account show \
    --query '{Name:name,TenantId:tenantId,User:user.name,State:state}' \
    --output table

  ABDA_RECOVERY_SECTION='release-candidate boundary verification'
  printf '\n[2/5] Verifying the unchanged release candidate and public readiness...\n'
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_RECOVERY_ROOT/app.json"
  abda_recovery_validate_app "$ABDA_RECOVERY_ROOT/app.json"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_PUBLIC_ORIGIN/health/ready" --output "$ABDA_RECOVERY_ROOT/ready.json"
  python3 - "$ABDA_RECOVERY_ROOT/ready.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    if json.load(handle) != {"status": "ready"}:
        raise SystemExit("STOP: the public origin is not ready")
PY
  printf 'application_revision: %s\n' "$ABDA_RECOVERY_REVISION"
  printf 'public_openrouter_failover_enabled: false\n'

  ABDA_RECOVERY_SECTION='protected ledger recovery audit'
  printf '\n[3/5] Verifying the settled deltas and restored safety state...\n'
  az containerapp secret list \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --show-values --only-show-errors --output json \
    >"$ABDA_RECOVERY_ROOT/secrets.json"
  abda_recovery_write_metrics_config \
    "$ABDA_RECOVERY_ROOT/secrets.json" \
    "$ABDA_RECOVERY_ROOT/metrics-curl-config"
  rm -f -- "$ABDA_RECOVERY_ROOT/secrets.json"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    --config "$ABDA_RECOVERY_ROOT/metrics-curl-config" \
    "$ABDA_PUBLIC_ORIGIN/internal/metrics" \
    --output "$ABDA_RECOVERY_ROOT/metrics.txt"
  abda_recovery_validate_metrics "$ABDA_RECOVERY_ROOT/metrics.txt" \
    | tee "$ABDA_RECOVERY_ROOT/result.txt"

  ABDA_RECOVERY_SECTION='public model contract diagnostic'
  printf '\n[4/5] Checking the current mandatory-reasoning model metadata...\n'
  if curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
      --connect-timeout 10 --max-time 30 \
      "$ABDA_OPENROUTER_MODELS_URL" \
      --output "$ABDA_RECOVERY_ROOT/models.json" && \
      abda_recovery_validate_model_metadata \
        "$ABDA_RECOVERY_ROOT/models.json" \
        >"$ABDA_RECOVERY_ROOT/model-contract.txt" 2>/dev/null; then
    cat "$ABDA_RECOVERY_ROOT/model-contract.txt"
    printf 'model_contract_diagnostic: confirmed\n'
  else
    printf '%s\n' \
      'model_contract_diagnostic: unavailable_or_changed' \
      'The ledger recovery remains valid because this public metadata check is diagnostic.'
  fi

  ABDA_RECOVERY_SECTION='final recovery status'
  printf '\n[5/5] Reporting the content-free recovery receipt...\n'
  printf '\nABDA-NL Gate 7 marker-failure recovery status:\n'
  printf 'script_revision: %s\n' "$ABDA_RECOVERY_SCRIPT_REVISION"
  printf 'application_source_commit: %s\n' "$ABDA_RECOVERY_APP_SOURCE_COMMIT"
  printf 'image_digest: sha256:%s\n' "$ABDA_RECOVERY_IMAGE_SHA256"
  printf 'subscription_id: %s\n' "$ABDA_EXPECTED_SUBSCRIPTION"
  printf 'resource_group: %s\n' "$ABDA_RESOURCE_GROUP"
  printf 'application_revision: %s\n' "$ABDA_RECOVERY_REVISION"
  printf 'public_origin: %s\n' "$ABDA_PUBLIC_ORIGIN"
  cat "$ABDA_RECOVERY_ROOT/result.txt"
  printf 'provider_call_repeated: false\n'
  printf 'azure_configuration_changed: false\n'
  printf 'result: EXISTING_GATE7_CALL_LEDGER_RECOVERY_VERIFIED\n'
  printf 'Send this status and the shell exit code to Codex.\n'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_recovery_main "$@"
fi
