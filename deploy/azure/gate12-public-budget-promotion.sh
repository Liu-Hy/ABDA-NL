#!/usr/bin/env bash

# Promote the validated staging pilot to the originally requested public caps.
# This gate changes only the trial user cap, total trial budget, and the public
# OpenRouter outage-fallback switch on the existing immutable web image.

ABDA_PROMOTION_SCRIPT_REVISION='3'
ABDA_PROMOTION_APPLICATION_SOURCE_COMMIT='b873112040dbfe645683d1b5e7d9adb122173ed2'
ABDA_PROMOTION_IMAGE_SHA256='567ec34602e1b5ab1e1a9b01864f2a67219910dc3080300bc108eb33d569856c'
ABDA_PROMOTION_OLD_REVISION='abda-nl-stg-web--restore-b873112'
ABDA_PROMOTION_TARGET_SUFFIX='public-100-b873112'
ABDA_PROMOTION_TARGET_REVISION='abda-nl-stg-web--public-100-b873112'
ABDA_PROMOTION_ROOT=''

abda_promotion_cleanup() {
  local exit_code=$?
  set +e
  if [[ "${ABDA_PROMOTION_ROOT:-}" == /tmp/abda-nl-gate12-promotion.* &&
        -d "${ABDA_PROMOTION_ROOT:-}" ]]; then
    rm -rf -- "$ABDA_PROMOTION_ROOT"
  fi
  printf '\nGate 12 shell exit code: %s\n' "$exit_code"
}

abda_promotion_error() {
  local exit_code=$?
  trap - ERR
  printf '\nSTOP: Gate 12 failed in section: %s\n' \
    "${ABDA_PROMOTION_SECTION:-unknown}" >&2
  printf '%s\n' \
    'Do not delete resources or issue a separate Azure update.' \
    'Send the visible status and shell exit code to Codex.' >&2
  exit "$exit_code"
}

abda_promotion_interrupt() {
  trap - ERR INT
  printf '\nSTOP: Gate 12 was interrupted in section: %s\n' \
    "${ABDA_PROMOTION_SECTION:-unknown}" >&2
  printf '%s\n' \
    'Do not issue a separate Azure update. Rerun this exact pinned gate.' >&2
  exit 130
}

abda_promotion_fail() {
  printf 'STOP: %s\n' "$*" >&2
  return 1
}

abda_promotion_set_constants() {
  ABDA_EXPECTED_SUBSCRIPTION='00e62f6e-2174-40b2-b428-8ebfd7c2ac54'
  ABDA_EXPECTED_TENANT='040f05eb-33ab-462f-af54-fb4bedb055ae'
  ABDA_EXPECTED_USER='hliu2@cloudbank.org'
  ABDA_RESOURCE_GROUP='abda-nl-staging'
  ABDA_APP_NAME='abda-nl-stg-web'
  ABDA_GENERATED_HOSTNAME='abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io'
  ABDA_CUSTOM_HOSTNAME='demo.abda-nl.org'
  ABDA_PUBLIC_ORIGIN="https://$ABDA_CUSTOM_HOSTNAME"
  ABDA_IMAGE_REPOSITORY='ghcr.io/liu-hy/abda-nl'
  ABDA_CERTIFICATE_ID='/subscriptions/00e62f6e-2174-40b2-b428-8ebfd7c2ac54/resourceGroups/abda-nl-staging/providers/Microsoft.App/managedEnvironments/abda-nl-stg-environment/managedCertificates/mc-abda-nl-stg-en-demo-abda-nl-org-1928'
  ABDA_PILOT_MAX_USERS='10'
  ABDA_PILOT_BUDGET_MICROUSD='50000000'
  ABDA_PUBLIC_MAX_USERS='100'
  ABDA_GRANT_MICROUSD='5000000'
  ABDA_PUBLIC_TRIAL_BUDGET_MICROUSD='500000000'
  ABDA_OPENROUTER_BUDGET_MICROUSD='500000000'
}

abda_promotion_validate_identity() {
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

abda_promotion_phase() {
  local path=$1
  python3 - "$path" "$ABDA_APP_NAME" "$ABDA_GENERATED_HOSTNAME" \
    "$ABDA_CUSTOM_HOSTNAME" "$ABDA_CERTIFICATE_ID" \
    "$ABDA_IMAGE_REPOSITORY@sha256:$ABDA_PROMOTION_IMAGE_SHA256" \
    "$ABDA_PROMOTION_OLD_REVISION" "$ABDA_PROMOTION_TARGET_REVISION" \
    "$ABDA_PILOT_MAX_USERS" "$ABDA_PILOT_BUDGET_MICROUSD" \
    "$ABDA_PUBLIC_MAX_USERS" "$ABDA_GRANT_MICROUSD" \
    "$ABDA_PUBLIC_TRIAL_BUDGET_MICROUSD" \
    "$ABDA_OPENROUTER_BUDGET_MICROUSD" <<'PY'
import json
import sys

(
    path,
    expected_app,
    generated_hostname,
    custom_hostname,
    certificate_id,
    expected_image,
    old_revision,
    target_revision,
    pilot_max_users,
    pilot_budget,
    public_max_users,
    grant,
    public_budget,
    openrouter_budget,
) = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    app = json.load(handle)
properties = app.get("properties") or {}
configuration = properties.get("configuration") or {}
ingress = configuration.get("ingress") or {}
template = properties.get("template") or {}
containers = template.get("containers") or []
if app.get("name") != expected_app or len(containers) != 1:
    raise SystemExit("STOP: the Container App identity or container count changed")
if properties.get("provisioningState") != "Succeeded":
    raise SystemExit("STOP: the Container App provisioning state is not Succeeded")
if properties.get("runningStatus") != "Running":
    raise SystemExit("STOP: the Container App running status is not Running")
if configuration.get("activeRevisionsMode") != "Single":
    raise SystemExit("STOP: the Container App is not in single revision mode")
if (
    ingress.get("fqdn") != generated_hostname
    or ingress.get("external") is not True
    or ingress.get("allowInsecure") is not False
    or ingress.get("targetPort") != 8000
):
    raise SystemExit("STOP: the public ingress contract changed")
traffic = ingress.get("traffic") or []
if (
    len(traffic) != 1
    or traffic[0].get("latestRevision") is not True
    or traffic[0].get("weight") != 100
):
    raise SystemExit("STOP: the ingress traffic contract changed")
domains = ingress.get("customDomains") or []
if len(domains) != 1:
    raise SystemExit("STOP: the custom-domain count changed")
domain = domains[0]
if (
    domain.get("name") != custom_hostname
    or domain.get("bindingType") != "SniEnabled"
    or str(domain.get("certificateId") or "").lower() != certificate_id.lower()
):
    raise SystemExit("STOP: the custom-domain certificate binding changed")
container = containers[0]
if container.get("name") != "web" or container.get("image") != expected_image:
    raise SystemExit("STOP: the deployed web image changed")
resources = container.get("resources") or {}
if float(resources.get("cpu") or 0) != 0.5 or resources.get("memory") != "1Gi":
    raise SystemExit("STOP: the web container resources changed")
scale = template.get("scale") or {}
if scale.get("minReplicas") != 1 or scale.get("maxReplicas") != 3:
    raise SystemExit("STOP: the web scaling boundary changed")
probes = container.get("probes") or []
expected_probes = {
    "Startup": "/health/live",
    "Liveness": "/health/live",
    "Readiness": "/health/ready",
}
if len(probes) != len(expected_probes):
    raise SystemExit("STOP: the health probe count changed")
for probe in probes:
    probe_type = str(probe.get("type") or "")
    http_get = probe.get("httpGet") or {}
    if probe_type not in expected_probes or http_get.get("path") != expected_probes[probe_type]:
        raise SystemExit("STOP: a health probe route changed")
    if http_get.get("port") != 8000 or str(http_get.get("scheme") or "").upper() != "HTTP":
        raise SystemExit("STOP: a health probe transport changed")
    if http_get.get("httpHeaders") != [{"name": "Host", "value": generated_hostname}]:
        raise SystemExit("STOP: a health probe lost its trusted Host header")
env_items = container.get("env") or []
env = {item.get("name"): item for item in env_items}
if len(env) != len(env_items):
    raise SystemExit("STOP: duplicate environment variable names are present")
required_values = {
    "ABDA_ENVIRONMENT": "staging",
    "ABDA_ENABLE_LLM": "1",
    "ABDA_AUTH_MODE": "oidc",
    "ABDA_AUTO_CREATE_DB": "0",
    "ABDA_PUBLIC_BASE_URL": f"https://{custom_hostname}",
    "ABDA_TRUSTED_HOSTS": f"{generated_hostname},{custom_hostname}",
    "ABDA_SESSION_COOKIE": "__Host-abda_session",
    "ABDA_COOKIE_SECURE": "1",
    "ABDA_TRIAL_ENABLED": "true",
    "ABDA_TRIAL_GRANT_MICROUSD": grant,
    "ABDA_LLM_BACKEND": "claude",
    "ABDA_CLAUDE_PROVIDER": "foundry",
    "ABDA_LLM_DEFAULT_PROFILE": "balanced",
    "ABDA_LLM_ALLOW_BYOK": "1",
    "ABDA_LLM_REQUIRE_AUTH": "1",
    "ABDA_OPENROUTER_BUDGET_MICROUSD": openrouter_budget,
    "ABDA_OPENROUTER_BUDGET_ACK": "",
    "ABDA_PROXY_MODE": "azure-container-apps",
    "ABDA_ABUSE_PROTECTION_ENABLED": "1",
}
for name, expected in required_values.items():
    actual = str(env.get(name, {}).get("value") or "")
    if actual != expected:
        raise SystemExit(f"STOP: deployed setting {name} changed")
for name, secret_ref in {
    "ABDA_DATABASE_URL": "database-url",
    "ABDA_SESSION_SECRET": "session-secret",
    "ABDA_MCP_TOKEN_PEPPER": "mcp-token-pepper",
    "ABDA_METRICS_TOKEN": "metrics-token",
    "ABDA_OIDC_CLIENT_SECRET": "oidc-client-secret",
    "AZURE_OPENAI_API_KEY": "foundry-api-key",
    "OPENROUTER_API_KEY": "openrouter-api-key",
}.items():
    if env.get(name, {}).get("secretRef") != secret_ref:
        raise SystemExit(f"STOP: deployed secret reference {name} changed")
secret_names = {item.get("name") for item in configuration.get("secrets") or []}
if secret_names != {
    "database-url",
    "session-secret",
    "mcp-token-pepper",
    "metrics-token",
    "oidc-client-secret",
    "foundry-api-key",
    "openrouter-api-key",
}:
    raise SystemExit("STOP: the Container App secret inventory changed")

trial_max_users = str(env.get("ABDA_TRIAL_MAX_USERS", {}).get("value") or "")
trial_budget = str(env.get("ABDA_TRIAL_BUDGET_MICROUSD", {}).get("value") or "")
openrouter_enabled = str(
    env.get("ABDA_OPENROUTER_FAILOVER_ENABLED", {}).get("value") or ""
).strip().lower()
latest = str(properties.get("latestRevisionName") or "")
ready = str(properties.get("latestReadyRevisionName") or "")
if (trial_max_users, trial_budget, openrouter_enabled) == (
    pilot_max_users,
    pilot_budget,
    "false",
):
    if latest != old_revision or ready != old_revision:
        raise SystemExit("STOP: the post-rollback pilot revision changed")
    print("pilot")
elif (trial_max_users, trial_budget, openrouter_enabled) == (
    public_max_users,
    public_budget,
    "true",
):
    if latest != target_revision:
        raise SystemExit("STOP: the public promotion revision name changed")
    print("public" if ready == target_revision else "public_pending")
else:
    raise SystemExit("STOP: budget settings are outside the reviewed pilot or public state")
PY
}

abda_promotion_validate_revision() {
  local revision_path=$1
  local replicas_path=$2
  local expected_revision=$3
  python3 - "$revision_path" "$replicas_path" "$expected_revision" <<'PY'
import json
import sys

revision_path, replicas_path, expected_revision = sys.argv[1:]
with open(revision_path, encoding="utf-8") as handle:
    revision = json.load(handle)
with open(replicas_path, encoding="utf-8") as handle:
    replicas = json.load(handle)
properties = revision.get("properties") or {}
if revision.get("name") != expected_revision:
    raise SystemExit("STOP: Azure returned an unexpected revision")
if properties.get("active") is not True:
    raise SystemExit("STOP: the revision is not active")
if properties.get("healthState") != "Healthy":
    raise SystemExit("STOP: the revision is not healthy")
if properties.get("provisioningState") != "Provisioned":
    raise SystemExit("STOP: the revision is not provisioned")
if not isinstance(replicas, list) or not 1 <= len(replicas) <= 3:
    raise SystemExit("STOP: the revision has an unexpected replica count")
for replica in replicas:
    replica_properties = replica.get("properties") or {}
    containers = replica_properties.get("containers") or []
    if replica_properties.get("runningState") != "Running":
        raise SystemExit("STOP: a replica is not running")
    if not containers or any(item.get("ready") is not True for item in containers):
        raise SystemExit("STOP: a replica container is not ready")
PY
}

abda_promotion_fetch_revision() {
  local app_path=$1
  local prefix=$2
  local revision=''
  revision="$(python3 - "$app_path" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(str((json.load(handle).get("properties") or {}).get("latestRevisionName") or ""))
PY
)"
  [[ -n "$revision" ]] || abda_promotion_fail 'the latest revision is absent'
  az containerapp revision show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --revision "$revision" --output json >"$prefix-revision.json"
  az containerapp replica list \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --revision "$revision" --output json >"$prefix-replicas.json"
  abda_promotion_validate_revision \
    "$prefix-revision.json" "$prefix-replicas.json" "$revision"
}

abda_promotion_compare_update() {
  local before_path=$1
  local after_path=$2
  python3 - "$before_path" "$after_path" <<'PY'
import copy
import json
import sys


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def projected(app):
    properties = app.get("properties") or {}
    configuration = copy.deepcopy(properties.get("configuration") or {})
    template = copy.deepcopy(properties.get("template") or {})
    template.pop("revisionSuffix", None)
    for container in template.get("containers") or []:
        for item in container.get("env") or []:
            if item.get("name") in {
                "ABDA_TRIAL_MAX_USERS",
                "ABDA_TRIAL_BUDGET_MICROUSD",
                "ABDA_OPENROUTER_FAILOVER_ENABLED",
            }:
                item["value"] = "<reviewed-public-setting>"
        container["env"] = sorted(
            [
                {
                    "name": item.get("name"),
                    "value": item.get("value"),
                    "secretRef": item.get("secretRef"),
                }
                for item in container.get("env") or []
            ],
            key=lambda item: str(item.get("name") or ""),
        )
    ingress = configuration.get("ingress") or {}
    ingress["traffic"] = [
        {
            "latestRevision": item.get("latestRevision"),
            "weight": item.get("weight"),
            "label": item.get("label"),
        }
        for item in ingress.get("traffic") or []
    ]
    configuration["secrets"] = sorted(
        [{"name": item.get("name")} for item in configuration.get("secrets") or []],
        key=lambda item: str(item.get("name") or ""),
    )
    return {
        "identity": app.get("identity") or {},
        "configuration": configuration,
        "template": template,
        "workloadProfileName": properties.get("workloadProfileName"),
    }


if projected(load(sys.argv[1])) != projected(load(sys.argv[2])):
    raise SystemExit("STOP: settings outside the three reviewed public values changed")
PY
}

abda_promotion_load_metrics_token() {
  local secrets_path=$1
  local config_path="$ABDA_PROMOTION_ROOT/metrics-curl-config"
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
matches = [str(item.get("value") or "") for item in values if item.get("name") == "metrics-token"]
if len(matches) != 1 or len(matches[0]) < 32 or any(character.isspace() for character in matches[0]):
    raise SystemExit("STOP: the protected metrics token is invalid")
escaped = matches[0].replace("\\", "\\\\").replace('"', '\\"')
descriptor = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
    handle.write(f'header = "Authorization: Bearer {escaped}"\n')
PY
  [[ -s "$config_path" ]] || \
    abda_promotion_fail 'the protected metrics curl configuration could not be created'
}

abda_promotion_validate_metrics() {
  local metrics_path=$1
  local expected_phase=$2
  local snapshot_path=$3
  python3 - "$metrics_path" "$expected_phase" "$snapshot_path" \
    "$ABDA_PILOT_MAX_USERS" "$ABDA_PILOT_BUDGET_MICROUSD" \
    "$ABDA_PUBLIC_MAX_USERS" "$ABDA_GRANT_MICROUSD" \
    "$ABDA_PUBLIC_TRIAL_BUDGET_MICROUSD" \
    "$ABDA_OPENROUTER_BUDGET_MICROUSD" <<'PY'
import json
import os
import sys

(
    metrics_path,
    expected_phase,
    snapshot_path,
    pilot_max_users,
    pilot_budget,
    public_max_users,
    grant,
    public_budget,
    openrouter_budget,
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


trial_enabled = integer("abda_trial_enabled")
max_users = integer("abda_trial_max_users")
trial_grant = integer("abda_trial_grant_microusd")
trial_budget = integer("abda_trial_budget_microusd")
activations = integer("abda_trial_activations")
allocated = integer("abda_trial_allocated_microusd")
trial_spent = integer("abda_trial_spent_microusd")
trial_reserved = integer("abda_trial_reserved_microusd")
trial_uncertain_count = integer("abda_trial_uncertain_charged_reservations")
trial_uncertain_cost = integer("abda_trial_uncertain_charged_microusd")
openrouter_enabled = integer("abda_openrouter_enabled")
openrouter_budget_value = integer("abda_openrouter_budget_microusd")
openrouter_spent = integer("abda_openrouter_spent_microusd")
openrouter_reserved = integer("abda_openrouter_reserved_microusd")
openrouter_uncertain_count = integer("abda_openrouter_uncertain_charged_reservations")
openrouter_uncertain_cost = integer("abda_openrouter_uncertain_charged_microusd")
expected_caps = (
    (int(pilot_max_users), int(pilot_budget), 0)
    if expected_phase == "pilot"
    else (int(public_max_users), int(public_budget), 1)
)
if (trial_enabled, max_users, trial_grant, trial_budget) != (
    1,
    expected_caps[0],
    int(grant),
    expected_caps[1],
):
    raise SystemExit("STOP: trial metrics do not match the reviewed phase")
if activations > max_users or allocated != activations * trial_grant:
    raise SystemExit("STOP: trial allocations do not reconcile")
if trial_spent + trial_reserved > allocated:
    raise SystemExit("STOP: trial spending exceeds allocated credit")
if trial_reserved or trial_uncertain_count or trial_uncertain_cost:
    raise SystemExit("STOP: trial reservations are not safely idle")
if openrouter_enabled != expected_caps[2]:
    raise SystemExit("STOP: OpenRouter metrics do not match the reviewed phase")
if openrouter_budget_value != int(openrouter_budget):
    raise SystemExit("STOP: the OpenRouter hard limit changed")
if openrouter_spent + openrouter_reserved > openrouter_budget_value:
    raise SystemExit("STOP: OpenRouter spending exceeds its hard limit")
if openrouter_reserved or openrouter_uncertain_count or openrouter_uncertain_cost:
    raise SystemExit("STOP: OpenRouter reservations are not safely idle")
snapshot = {
    "trial_activations": activations,
    "trial_allocated_microusd": allocated,
    "trial_spent_microusd": trial_spent,
    "openrouter_spent_microusd": openrouter_spent,
}
descriptor = os.open(snapshot_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
    json.dump(snapshot, handle, sort_keys=True)
    handle.write("\n")
print(f"trial_max_users: {max_users}")
print(f"trial_grant_microusd: {trial_grant}")
print(f"trial_budget_microusd: {trial_budget}")
print(f"trial_activations: {activations}")
print(f"trial_spent_microusd: {trial_spent}")
print(f"trial_reserved_microusd: {trial_reserved}")
print(f"openrouter_enabled: {openrouter_enabled}")
print(f"openrouter_budget_microusd: {openrouter_budget_value}")
print(f"openrouter_spent_microusd: {openrouter_spent}")
print(f"openrouter_reserved_microusd: {openrouter_reserved}")
PY
}

abda_promotion_compare_metrics() {
  local before_path=$1
  local after_path=$2
  python3 - "$before_path" "$after_path" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    before = json.load(handle)
with open(sys.argv[2], encoding="utf-8") as handle:
    after = json.load(handle)
if before != after:
    raise SystemExit("STOP: accounting totals changed during the configuration-only promotion")
PY
}

abda_promotion_public_acceptance() {
  local expected_phase=$1
  local prefix=$2
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_PUBLIC_ORIGIN/health/ready" --output "$prefix-ready.json"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_PUBLIC_ORIGIN/config" --output "$prefix-config.json"
  python3 - "$prefix-ready.json" "$prefix-config.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    if json.load(handle) != {"status": "ready"}:
        raise SystemExit("STOP: the public origin is not ready")
with open(sys.argv[2], encoding="utf-8") as handle:
    config = json.load(handle)
if config.get("llm_enabled") is not True or config.get("llm_auth_required") is not True:
    raise SystemExit("STOP: the public LLM authentication contract changed")
if config.get("byok_enabled") is not True or config.get("byok_keys_stored") is not False:
    raise SystemExit("STOP: the public BYOK contract changed")
if config.get("default_profile") != "balanced":
    raise SystemExit("STOP: the funded default profile changed")
if [item.get("id") for item in config.get("profiles") or []] != ["balanced"]:
    raise SystemExit("STOP: the funded profile allowlist changed")
PY
  local unauthenticated_status=''
  unauthenticated_status="$(curl --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 --output "$prefix-metrics-unauth.json" \
    --write-out '%{http_code}' "$ABDA_PUBLIC_ORIGIN/internal/metrics")"
  [[ "$unauthenticated_status" == '401' ]] || \
    abda_promotion_fail 'the metrics endpoint is not protected'
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    --config "$ABDA_PROMOTION_ROOT/metrics-curl-config" \
    "$ABDA_PUBLIC_ORIGIN/internal/metrics" --output "$prefix-metrics.txt"
  abda_promotion_validate_metrics \
    "$prefix-metrics.txt" "$expected_phase" "$prefix-snapshot.json"
}

abda_promotion_wait_for_target() {
  local attempt=0
  local phase=''
  for attempt in $(seq 1 60); do
    az containerapp show \
      --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
      --output json >"$ABDA_PROMOTION_ROOT/wait-app.json"
    if phase="$(abda_promotion_phase "$ABDA_PROMOTION_ROOT/wait-app.json" 2>/dev/null)" && \
       [[ "$phase" == 'public' ]]; then
      abda_promotion_fetch_revision \
        "$ABDA_PROMOTION_ROOT/wait-app.json" "$ABDA_PROMOTION_ROOT/wait"
      return 0
    fi
    if (( attempt == 1 || attempt % 6 == 0 )); then
      printf 'Public promotion revision state: %s (attempt %s/60)\n' \
        "${phase:-waiting}" "$attempt"
    fi
    sleep 5
  done
  abda_promotion_fail 'the public promotion revision did not become healthy'
}

abda_promotion_main() {
  set -Eeuo pipefail
  set +x
  umask 077
  unset HISTFILE
  trap abda_promotion_error ERR
  trap abda_promotion_cleanup EXIT
  trap abda_promotion_interrupt INT
  ABDA_PROMOTION_SECTION='bootstrap'

  printf 'ABDA-NL Gate 12 public budget promotion script revision: %s\n' \
    "$ABDA_PROMOTION_SCRIPT_REVISION"
  printf '%s\n' \
    'This resume-safe gate raises the funded trial from 10 to 100 verified users.' \
    'It raises the total trial cap from $50 to $500 and enables outage-only OpenRouter fallback.' \
    'The independent OpenRouter owner-exposure hard limit remains $500.' \
    'No image, secret, migration, Auth0, DNS, certificate, or database resource is changed.'

  abda_promotion_set_constants
  local command_name=''
  for command_name in az curl grep python3; do
    command -v "$command_name" >/dev/null 2>&1 || \
      abda_promotion_fail "required command is unavailable: $command_name"
  done
  ABDA_PROMOTION_ROOT="$(mktemp -d /tmp/abda-nl-gate12-promotion.XXXXXX)"
  chmod 700 "$ABDA_PROMOTION_ROOT"
  az containerapp update --help >"$ABDA_PROMOTION_ROOT/containerapp-update.help"
  grep -Fq -- '--set-env-vars' "$ABDA_PROMOTION_ROOT/containerapp-update.help"
  grep -Fq -- '--revision-suffix' "$ABDA_PROMOTION_ROOT/containerapp-update.help"
  az containerapp secret list --help >"$ABDA_PROMOTION_ROOT/containerapp-secret-list.help"
  grep -Fq -- '--show-values' "$ABDA_PROMOTION_ROOT/containerapp-secret-list.help"

  ABDA_PROMOTION_SECTION='Azure identity verification'
  printf '\n[1/6] Verifying the exact Azure identity...\n'
  az account show --output json >"$ABDA_PROMOTION_ROOT/account.json"
  abda_promotion_validate_identity "$ABDA_PROMOTION_ROOT/account.json"
  az account show \
    --query '{Name:name,TenantId:tenantId,User:user.name,State:state}' \
    --output table

  ABDA_PROMOTION_SECTION='application state verification'
  printf '\n[2/6] Verifying the exact post-acceptance application...\n'
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_PROMOTION_ROOT/before-app.json"
  local phase=''
  phase="$(abda_promotion_phase "$ABDA_PROMOTION_ROOT/before-app.json")"
  if [[ "$phase" == 'public_pending' ]]; then
    printf 'A previously submitted public revision is still settling. Resuming verification.\n'
    abda_promotion_wait_for_target
    cp "$ABDA_PROMOTION_ROOT/wait-app.json" "$ABDA_PROMOTION_ROOT/before-app.json"
    phase='public'
  else
    abda_promotion_fetch_revision \
      "$ABDA_PROMOTION_ROOT/before-app.json" "$ABDA_PROMOTION_ROOT/before"
  fi
  printf 'deployment_phase: %s\n' "$phase"

  ABDA_PROMOTION_SECTION='protected metrics loading'
  printf '\n[3/6] Loading the existing metrics token from Azure without displaying it...\n'
  az containerapp secret list \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --show-values --only-show-errors --output json \
    >"$ABDA_PROMOTION_ROOT/current-secrets.json"
  abda_promotion_load_metrics_token "$ABDA_PROMOTION_ROOT/current-secrets.json"
  printf 'Validated the protected application secret inventory.\n'

  ABDA_PROMOTION_SECTION='predeployment public acceptance'
  printf '\n[4/6] Verifying HTTPS, BYOK, and safely idle accounting...\n'
  abda_promotion_public_acceptance "$phase" "$ABDA_PROMOTION_ROOT/before"

  if [[ "$phase" == 'pilot' ]]; then
    printf '\nThis mutation changes exactly three Container App environment values:\n'
    printf '  ABDA_TRIAL_MAX_USERS: %s -> %s\n' \
      "$ABDA_PILOT_MAX_USERS" "$ABDA_PUBLIC_MAX_USERS"
    printf '  ABDA_TRIAL_BUDGET_MICROUSD: %s -> %s\n' \
      "$ABDA_PILOT_BUDGET_MICROUSD" "$ABDA_PUBLIC_TRIAL_BUDGET_MICROUSD"
    printf '  ABDA_OPENROUTER_FAILOVER_ENABLED: false -> true\n'
    printf '%s\n' \
      'CloudBank remains primary. OpenRouter is used only for qualifying temporary outages.' \
      'Both owner-funded programs retain independent $500 hard caps.' \
      'Type PROMOTE_ABDA_PUBLIC_BUDGETS to continue, or press Enter to cancel.'
    local confirmation=''
    IFS= read -r -p 'Confirmation: ' confirmation
    if [[ "$confirmation" != 'PROMOTE_ABDA_PUBLIC_BUDGETS' ]]; then
      printf 'Cancelled without changing Azure.\n'
      return 0
    fi

    ABDA_PROMOTION_SECTION='public settings deployment'
    printf '\n[5/6] Submitting the reviewed three-setting revision...\n'
    az containerapp update \
      --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
      --container-name web --revision-suffix "$ABDA_PROMOTION_TARGET_SUFFIX" \
      --set-env-vars \
        "ABDA_TRIAL_MAX_USERS=$ABDA_PUBLIC_MAX_USERS" \
        "ABDA_TRIAL_BUDGET_MICROUSD=$ABDA_PUBLIC_TRIAL_BUDGET_MICROUSD" \
        ABDA_OPENROUTER_FAILOVER_ENABLED=true \
      --only-show-errors --output none
    abda_promotion_wait_for_target
    cp "$ABDA_PROMOTION_ROOT/wait-app.json" "$ABDA_PROMOTION_ROOT/after-app.json"
    abda_promotion_compare_update \
      "$ABDA_PROMOTION_ROOT/before-app.json" "$ABDA_PROMOTION_ROOT/after-app.json"
    printf 'Verified that only the three reviewed settings and revision suffix changed.\n'
  else
    printf '\n[5/6] The exact public promotion revision is already active. No Azure change was made.\n'
  fi

  ABDA_PROMOTION_SECTION='public promotion acceptance'
  printf '\n[6/6] Verifying promoted hard caps and unchanged accounting...\n'
  abda_promotion_public_acceptance public "$ABDA_PROMOTION_ROOT/after"
  if [[ -f "$ABDA_PROMOTION_ROOT/before-snapshot.json" ]]; then
    abda_promotion_compare_metrics \
      "$ABDA_PROMOTION_ROOT/before-snapshot.json" \
      "$ABDA_PROMOTION_ROOT/after-snapshot.json"
  fi

  printf '\nABDA-NL Gate 12 public budget promotion status:\n'
  printf 'script_revision: %s\n' "$ABDA_PROMOTION_SCRIPT_REVISION"
  printf 'application_source_commit: %s\n' \
    "$ABDA_PROMOTION_APPLICATION_SOURCE_COMMIT"
  printf 'image_digest: sha256:%s\n' "$ABDA_PROMOTION_IMAGE_SHA256"
  printf 'subscription_id: %s\n' "$ABDA_EXPECTED_SUBSCRIPTION"
  printf 'resource_group: %s\n' "$ABDA_RESOURCE_GROUP"
  printf 'application_revision: %s\n' "$ABDA_PROMOTION_TARGET_REVISION"
  printf 'public_origin: %s\n' "$ABDA_PUBLIC_ORIGIN"
  printf 'trial_max_users: %s\n' "$ABDA_PUBLIC_MAX_USERS"
  printf 'trial_grant_microusd: %s\n' "$ABDA_GRANT_MICROUSD"
  printf 'trial_budget_microusd: %s\n' "$ABDA_PUBLIC_TRIAL_BUDGET_MICROUSD"
  printf 'openrouter_failover_enabled: true\n'
  printf 'openrouter_budget_microusd: %s\n' "$ABDA_OPENROUTER_BUDGET_MICROUSD"
  printf 'result: PUBLIC_BUDGETS_AND_OUTAGE_FALLBACK_PROMOTED\n'
  printf '%s\n' \
    'Run the final browser, MCP, privacy, and presentation checks before announcing general availability.'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_promotion_main "$@"
fi
