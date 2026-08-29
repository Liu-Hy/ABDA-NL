#!/usr/bin/env bash

# Deploy the tested Claude MCP setup correction as one image-only Container App update.
# The gate preserves the complete application configuration and does not rerun
# migrations or change secrets, Auth0, DNS, trial limits, or provider routing.

ABDA_MCP_IMAGE_SCRIPT_REVISION='1'
ABDA_MCP_IMAGE_SOURCE_COMMIT='82f97fb7cc6882c823f9a1876ee6d628d0c01986'
ABDA_MCP_IMAGE_OLD_IMAGE_SHA256='282a2cb13cbdabe7f60a7efaa41c5fded7b1a4efeb467cc758064c7cadf30f13'
ABDA_MCP_IMAGE_NEW_IMAGE_SHA256='a1488eaf90d21f68c3e2a1e4398ee4ecadea24677fa8a08e882894d7b41cece7'
ABDA_MCP_IMAGE_OLD_REVISION='abda-nl-stg-web--restore-6d0fb44'
ABDA_MCP_IMAGE_TARGET_SUFFIX='mcp-82f97fb'
ABDA_MCP_IMAGE_TARGET_REVISION='abda-nl-stg-web--mcp-82f97fb'
ABDA_MCP_IMAGE_ROOT=''

abda_mcp_image_cleanup() {
  local exit_code=$?
  set +e
  unset ABDA_REGISTRY_TOKEN
  if [[ "${ABDA_MCP_IMAGE_ROOT:-}" == /tmp/abda-nl-mcp-command.* &&
        -d "${ABDA_MCP_IMAGE_ROOT:-}" ]]; then
    rm -rf -- "$ABDA_MCP_IMAGE_ROOT"
  fi
  printf '\nMCP command image gate shell exit code: %s\n' "$exit_code"
}

abda_mcp_image_error() {
  local exit_code=$?
  trap - ERR
  printf '\nSTOP: MCP command image gate failed in section: %s\n' \
    "${ABDA_MCP_IMAGE_SECTION:-unknown}" >&2
  printf '%s\n' \
    'Do not delete resources or rerun blindly.' \
    'Send the visible status and shell exit code to Codex.' >&2
  exit "$exit_code"
}

abda_mcp_image_interrupt() {
  trap - ERR INT
  printf '\nSTOP: MCP command image gate was interrupted in section: %s\n' \
    "${ABDA_MCP_IMAGE_SECTION:-unknown}" >&2
  exit 130
}

abda_mcp_image_fail() {
  printf 'STOP: %s\n' "$*" >&2
  return 1
}

abda_mcp_image_set_constants() {
  ABDA_EXPECTED_SUBSCRIPTION='00e62f6e-2174-40b2-b428-8ebfd7c2ac54'
  ABDA_EXPECTED_TENANT='040f05eb-33ab-462f-af54-fb4bedb055ae'
  ABDA_EXPECTED_USER='hliu2@cloudbank.org'
  ABDA_RESOURCE_GROUP='abda-nl-staging'
  ABDA_APP_NAME='abda-nl-stg-web'
  ABDA_IMAGE_REPOSITORY='ghcr.io/liu-hy/abda-nl'
  ABDA_GENERATED_HOSTNAME='abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io'
  ABDA_CUSTOM_HOSTNAME='demo.abda-nl.org'
  ABDA_CUSTOM_ORIGIN="https://$ABDA_CUSTOM_HOSTNAME"
}

abda_mcp_image_validate_identity() {
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

abda_mcp_image_validate_registry_image() {
  local headers_path=$1
  local manifest_path=$2
  local config_path=$3
  python3 - "$headers_path" "$manifest_path" "$config_path" \
    "$ABDA_MCP_IMAGE_NEW_IMAGE_SHA256" "$ABDA_MCP_IMAGE_SOURCE_COMMIT" <<'PY'
import json
import sys

headers_path, manifest_path, config_path, digest, commit = sys.argv[1:]
with open(headers_path, encoding="utf-8") as handle:
    headers = handle.read().lower()
if f"docker-content-digest: sha256:{digest}" not in headers:
    raise SystemExit("STOP: GHCR returned an unexpected image digest")
with open(manifest_path, encoding="utf-8") as handle:
    manifest = json.load(handle)
if manifest.get("schemaVersion") != 2:
    raise SystemExit("STOP: GHCR returned an unexpected manifest schema")
config_descriptor = manifest.get("config") or {}
if not str(config_descriptor.get("digest") or "").startswith("sha256:"):
    raise SystemExit("STOP: GHCR image config digest is missing")
with open(config_path, encoding="utf-8") as handle:
    config = json.load(handle)
labels = (config.get("config") or {}).get("Labels") or {}
expected = {
    "org.opencontainers.image.source": "https://github.com/Liu-Hy/ABDA-NL",
    "org.opencontainers.image.revision": commit,
    "org.opencontainers.image.licenses": "MIT",
}
if any(labels.get(name) != value for name, value in expected.items()):
    raise SystemExit("STOP: GHCR image provenance labels changed")
PY
}

abda_mcp_image_validate_app_phase() {
  local app_path=$1
  python3 - "$app_path" "$ABDA_APP_NAME" "$ABDA_GENERATED_HOSTNAME" \
    "$ABDA_CUSTOM_HOSTNAME" \
    "$ABDA_IMAGE_REPOSITORY@sha256:$ABDA_MCP_IMAGE_OLD_IMAGE_SHA256" \
    "$ABDA_IMAGE_REPOSITORY@sha256:$ABDA_MCP_IMAGE_NEW_IMAGE_SHA256" \
    "$ABDA_MCP_IMAGE_OLD_REVISION" "$ABDA_MCP_IMAGE_TARGET_REVISION" <<'PY'
import json
import sys

(
    path,
    expected_app,
    generated_hostname,
    custom_hostname,
    old_image,
    target_image,
    old_revision,
    target_revision,
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
if str(configuration.get("activeRevisionsMode") or "").lower() != "single":
    raise SystemExit("STOP: the Container App is not in single revision mode")
if (
    ingress.get("fqdn") != generated_hostname
    or ingress.get("external") is not True
    or ingress.get("allowInsecure") is not False
    or ingress.get("targetPort") != 8000
):
    raise SystemExit("STOP: the public ingress contract changed")
domains = ingress.get("customDomains") or []
if len(domains) != 1 or domains[0].get("name") != custom_hostname:
    raise SystemExit("STOP: the custom-domain binding changed")
container = containers[0]
if container.get("name") != "web":
    raise SystemExit("STOP: the web container identity changed")
env_items = container.get("env") or []
env = {str(item.get("name") or ""): item for item in env_items}
if len(env) != len(env_items):
    raise SystemExit("STOP: duplicate environment variable names are present")
expected_values = {
    "ABDA_ENVIRONMENT": "staging",
    "ABDA_AUTH_MODE": "oidc",
    "ABDA_PUBLIC_BASE_URL": f"https://{custom_hostname}",
    "ABDA_TRIAL_ENABLED": "true",
    "ABDA_TRIAL_MAX_USERS": "10",
    "ABDA_TRIAL_GRANT_MICROUSD": "5000000",
    "ABDA_TRIAL_BUDGET_MICROUSD": "50000000",
    "ABDA_LLM_ALLOW_BYOK": "1",
    "ABDA_LLM_REQUIRE_AUTH": "1",
    "ABDA_OPENROUTER_FAILOVER_ENABLED": "false",
    "ABDA_OPENROUTER_BUDGET_MICROUSD": "500000000",
}
for name, expected in expected_values.items():
    actual = str(env.get(name, {}).get("value") or "")
    if name in {"ABDA_TRIAL_ENABLED", "ABDA_OPENROUTER_FAILOVER_ENABLED"}:
        actual = actual.lower()
    if actual != expected:
        raise SystemExit(f"STOP: deployed setting {name} changed")
image = str(container.get("image") or "")
latest = str(properties.get("latestRevisionName") or "")
ready = str(properties.get("latestReadyRevisionName") or "")
if image == old_image and latest == old_revision and ready == old_revision:
    print("old")
elif image == target_image and latest == target_revision:
    print("target" if ready == target_revision else "target_pending")
else:
    raise SystemExit("STOP: the image and revision are outside the reviewed old or target state")
PY
}

abda_mcp_image_validate_revision() {
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
    if replica_properties.get("runningState") != "Running":
        raise SystemExit("STOP: a replica is not running")
    containers = replica_properties.get("containers") or []
    if not containers or any(item.get("ready") is not True for item in containers):
        raise SystemExit("STOP: a replica container is not ready")
PY
}

abda_mcp_image_fetch_healthy_revision() {
  local revision=$1
  local prefix=$2
  az containerapp revision show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --revision "$revision" --output json >"$prefix-revision.json"
  az containerapp replica list \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --revision "$revision" --output json >"$prefix-replicas.json"
  abda_mcp_image_validate_revision \
    "$prefix-revision.json" "$prefix-replicas.json" "$revision"
}

abda_mcp_image_compare_application_contract() {
  local before_path=$1
  local after_path=$2
  python3 - "$before_path" "$after_path" <<'PY'
import json
import sys


def selected(path):
    with open(path, encoding="utf-8") as handle:
        app = json.load(handle)
    properties = app.get("properties") or {}
    template = json.loads(json.dumps(properties.get("template") or {}))
    template["revisionSuffix"] = "<reviewed-image-revision>"
    containers = template.get("containers") or []
    if len(containers) != 1 or containers[0].get("name") != "web":
        raise SystemExit("STOP: the web container identity changed")
    containers[0]["image"] = "<reviewed-image>"
    return {
        "identity": app.get("identity"),
        "environmentId": properties.get("environmentId"),
        "managedEnvironmentId": properties.get("managedEnvironmentId"),
        "workloadProfileName": properties.get("workloadProfileName"),
        "configuration": properties.get("configuration"),
        "template": template,
    }


before = selected(sys.argv[1])
after = selected(sys.argv[2])
if before == after:
    raise SystemExit(0)


def changed_paths(left, right, prefix=""):
    if type(left) is not type(right):
        return [prefix or "<root>"]
    if isinstance(left, dict):
        paths = []
        for key in sorted(set(left) | set(right)):
            child = f"{prefix}.{key}" if prefix else str(key)
            if key not in left or key not in right:
                paths.append(child)
            else:
                paths.extend(changed_paths(left[key], right[key], child))
        return paths
    if isinstance(left, list):
        if len(left) != len(right):
            return [prefix]
        paths = []
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            paths.extend(changed_paths(left_item, right_item, f"{prefix}[{index}]"))
        return paths
    return [] if left == right else [prefix]


paths = changed_paths(before, after)
raise SystemExit("STOP: settings outside the image and revision changed at: " + ", ".join(paths))
PY
}

abda_mcp_image_validate_public_contract() {
  local prefix=$1
  python3 - "$prefix-ready.json" "$prefix-config.json" <<'PY'
import json
import sys

ready_path, config_path = sys.argv[1:]
with open(ready_path, encoding="utf-8") as handle:
    if json.load(handle) != {"status": "ready"}:
        raise SystemExit("STOP: the custom origin is not ready")
with open(config_path, encoding="utf-8") as handle:
    config = json.load(handle)
expected = {
    "llm_enabled": True,
    "llm_auth_required": True,
    "byok_enabled": True,
    "byok_keys_stored": False,
}
for name, value in expected.items():
    if config.get(name) is not value:
        raise SystemExit(f"STOP: /config requires {name}={value!r}")
if config.get("default_profile") != "balanced":
    raise SystemExit("STOP: the funded model profile changed")
PY
}

abda_mcp_image_public_acceptance() {
  local prefix=$1
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_CUSTOM_ORIGIN/" --output "$prefix-root.html"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_CUSTOM_ORIGIN/health/ready" --output "$prefix-ready.json"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_CUSTOM_ORIGIN/config" --output "$prefix-config.json"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_CUSTOM_ORIGIN/privacy.html" --output "$prefix-privacy.html"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_CUSTOM_ORIGIN/terms.html" --output "$prefix-terms.html"
  [[ -s "$prefix-root.html" && -s "$prefix-privacy.html" && \
     -s "$prefix-terms.html" ]] || \
    abda_mcp_image_fail 'a public page returned an empty response'
  local metrics_status=''
  metrics_status="$(curl --silent --show-error \
    --proto '=https' --tlsv1.2 --connect-timeout 10 --max-time 30 \
    --output "$prefix-metrics.json" --write-out '%{http_code}' \
    "$ABDA_CUSTOM_ORIGIN/internal/metrics")"
  [[ "$metrics_status" == '401' ]] || \
    abda_mcp_image_fail 'the metrics endpoint is not protected'
  abda_mcp_image_validate_public_contract "$prefix"
}

abda_mcp_image_validate_static_fix() {
  local prefix=$1
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_CUSTOM_ORIGIN/workspace.js?source=$ABDA_MCP_IMAGE_SOURCE_COMMIT" \
    --output "$prefix-workspace.js"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_CUSTOM_ORIGIN/app.js?source=$ABDA_MCP_IMAGE_SOURCE_COMMIT" \
    --output "$prefix-app.js"
  grep -Fq \
    "if (state.readOnly) return { tab: null, message: 'Chat and edits are disabled in a shared read-only view.' };" \
    "$prefix-workspace.js" || \
    abda_mcp_image_fail 'the deployed shared-view access rule is missing'
  grep -Fq 'if (accessIssue.tab) openWorkspace(accessIssue.tab);' \
    "$prefix-app.js" || \
    abda_mcp_image_fail 'the deployed chat action guard is missing'
}

abda_mcp_image_wait_for_target() {
  local attempt=0
  local state=''
  for attempt in $(seq 1 60); do
    if az containerapp show \
      --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
      --output json >"$ABDA_MCP_IMAGE_ROOT/wait-app.json" 2>/dev/null && \
      az containerapp revision show \
        --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
        --revision "$ABDA_MCP_IMAGE_TARGET_REVISION" --output json \
        >"$ABDA_MCP_IMAGE_ROOT/wait-revision.json" 2>/dev/null && \
      az containerapp replica list \
        --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
        --revision "$ABDA_MCP_IMAGE_TARGET_REVISION" --output json \
        >"$ABDA_MCP_IMAGE_ROOT/wait-replicas.json" 2>/dev/null; then
      state="$(python3 - "$ABDA_MCP_IMAGE_ROOT/wait-app.json" \
        "$ABDA_MCP_IMAGE_ROOT/wait-revision.json" \
        "$ABDA_MCP_IMAGE_ROOT/wait-replicas.json" \
        "$ABDA_MCP_IMAGE_TARGET_REVISION" \
        "$ABDA_IMAGE_REPOSITORY@sha256:$ABDA_MCP_IMAGE_NEW_IMAGE_SHA256" <<'PY'
import json
import sys

app_path, revision_path, replicas_path, target_revision, target_image = sys.argv[1:]
with open(app_path, encoding="utf-8") as handle:
    app = json.load(handle)
with open(revision_path, encoding="utf-8") as handle:
    revision = json.load(handle)
with open(replicas_path, encoding="utf-8") as handle:
    replicas = json.load(handle)
properties = app.get("properties") or {}
containers = (properties.get("template") or {}).get("containers") or []
revision_properties = revision.get("properties") or {}
image = str(containers[0].get("image") or "") if len(containers) == 1 else ""
running = sum(
    1
    for replica in replicas
    if (replica.get("properties") or {}).get("runningState") == "Running"
)
ready = sum(
    1
    for replica in replicas
    if (replica.get("properties") or {}).get("containers")
    and all(
        item.get("ready") is True
        for item in (replica.get("properties") or {}).get("containers") or []
    )
)
values = (
    properties.get("provisioningState"),
    properties.get("runningStatus"),
    properties.get("latestRevisionName"),
    properties.get("latestReadyRevisionName"),
    revision_properties.get("provisioningState"),
    revision_properties.get("healthState"),
    revision_properties.get("active"),
    image,
    len(replicas),
    running,
    ready,
)
print("|".join(str(value) for value in values))
if (
    values[0] == "Succeeded"
    and values[1] == "Running"
    and values[2] == target_revision
    and values[3] == target_revision
    and values[4] == "Provisioned"
    and values[5] == "Healthy"
    and values[6] is True
    and values[7] == target_image
    and 1 <= values[8] <= 3
    and values[9] == values[8]
    and values[10] == values[8]
):
    raise SystemExit(0)
raise SystemExit(1)
PY
)" && {
        printf 'MCP command image state: %s\n' "$state"
        abda_mcp_image_validate_revision \
          "$ABDA_MCP_IMAGE_ROOT/wait-revision.json" \
          "$ABDA_MCP_IMAGE_ROOT/wait-replicas.json" "$ABDA_MCP_IMAGE_TARGET_REVISION"
        return 0
      }
    fi
    if (( attempt == 1 || attempt % 6 == 0 )); then
      printf 'MCP command revision state: %s (attempt %s/60)\n' \
        "${state:-waiting}" "$attempt"
    fi
    sleep 5
  done
  abda_mcp_image_fail 'the MCP command revision did not become healthy'
}

abda_mcp_image_main() {
  set -Eeuo pipefail
  set +x
  umask 077
  unset HISTFILE
  trap abda_mcp_image_error ERR
  trap abda_mcp_image_cleanup EXIT
  trap abda_mcp_image_interrupt INT
  ABDA_MCP_IMAGE_SECTION='bootstrap'

  printf 'ABDA-NL MCP command image script revision: %s\n' \
    "$ABDA_MCP_IMAGE_SCRIPT_REVISION"
  printf '%s\n' \
    'This resume-safe gate updates only the existing web container image.' \
    'It does not rerun migrations or change secrets, Auth0, DNS, certificates,' \
    'trial limits, provider routing, scaling, probes, or database resources.'

  abda_mcp_image_set_constants
  local command_name=''
  for command_name in az curl grep python3; do
    command -v "$command_name" >/dev/null 2>&1 || \
      abda_mcp_image_fail "required command is unavailable: $command_name"
  done
  ABDA_MCP_IMAGE_ROOT="$(mktemp -d /tmp/abda-nl-mcp-command.XXXXXX)"
  chmod 700 "$ABDA_MCP_IMAGE_ROOT"
  az containerapp update --help >"$ABDA_MCP_IMAGE_ROOT/containerapp-update.help"
  grep -Fq -- '--container-name' "$ABDA_MCP_IMAGE_ROOT/containerapp-update.help"
  grep -Fq -- '--image' "$ABDA_MCP_IMAGE_ROOT/containerapp-update.help"
  grep -Fq -- '--revision-suffix' "$ABDA_MCP_IMAGE_ROOT/containerapp-update.help"

  ABDA_MCP_IMAGE_SECTION='Azure identity verification'
  printf '\n[1/8] Verifying the exact Azure identity...\n'
  az account show --output json >"$ABDA_MCP_IMAGE_ROOT/account.json"
  abda_mcp_image_validate_identity "$ABDA_MCP_IMAGE_ROOT/account.json"
  az account show \
    --query '{Name:name,TenantId:tenantId,User:user.name,State:state}' \
    --output table

  ABDA_MCP_IMAGE_SECTION='immutable image verification'
  printf '\n[2/8] Verifying anonymous access and provenance labels for the exact image...\n'
  ABDA_REGISTRY_TOKEN="$(curl --fail --silent --show-error --get \
    --data-urlencode 'scope=repository:liu-hy/abda-nl:pull' \
    --data-urlencode 'service=ghcr.io' 'https://ghcr.io/token' | \
    python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')"
  curl --fail --silent --show-error \
    --header "Authorization: Bearer $ABDA_REGISTRY_TOKEN" \
    --header 'Accept: application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json' \
    --dump-header "$ABDA_MCP_IMAGE_ROOT/manifest.headers" \
    --output "$ABDA_MCP_IMAGE_ROOT/manifest.json" \
    "https://ghcr.io/v2/liu-hy/abda-nl/manifests/sha256:$ABDA_MCP_IMAGE_NEW_IMAGE_SHA256"
  local config_digest=''
  config_digest="$(python3 - "$ABDA_MCP_IMAGE_ROOT/manifest.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(str((json.load(handle).get("config") or {}).get("digest") or ""))
PY
)"
  [[ "$config_digest" == sha256:* ]] || \
    abda_mcp_image_fail 'the published image config digest is invalid'
  curl --location --fail --silent --show-error \
    --header "Authorization: Bearer $ABDA_REGISTRY_TOKEN" \
    --output "$ABDA_MCP_IMAGE_ROOT/image-config.json" \
    "https://ghcr.io/v2/liu-hy/abda-nl/blobs/$config_digest"
  abda_mcp_image_validate_registry_image \
    "$ABDA_MCP_IMAGE_ROOT/manifest.headers" "$ABDA_MCP_IMAGE_ROOT/manifest.json" \
    "$ABDA_MCP_IMAGE_ROOT/image-config.json"
  unset ABDA_REGISTRY_TOKEN
  printf 'Verified image digest and source commit: %s\n' "$ABDA_MCP_IMAGE_SOURCE_COMMIT"

  ABDA_MCP_IMAGE_SECTION='current application state verification'
  printf '\n[3/8] Verifying the current healthy application and bounded pilot...\n'
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_MCP_IMAGE_ROOT/before-app.json"
  local phase=''
  phase="$(abda_mcp_image_validate_app_phase "$ABDA_MCP_IMAGE_ROOT/before-app.json")"
  if [[ "$phase" == 'old' ]]; then
    abda_mcp_image_fetch_healthy_revision \
      "$ABDA_MCP_IMAGE_OLD_REVISION" "$ABDA_MCP_IMAGE_ROOT/before"
  elif [[ "$phase" == 'target' ]]; then
    abda_mcp_image_fetch_healthy_revision \
      "$ABDA_MCP_IMAGE_TARGET_REVISION" "$ABDA_MCP_IMAGE_ROOT/before"
  fi
  printf 'deployment_phase: %s\n' "$phase"

  ABDA_MCP_IMAGE_SECTION='predeployment public acceptance'
  printf '\n[4/8] Verifying public HTTPS and the protected metrics boundary...\n'
  abda_mcp_image_public_acceptance "$ABDA_MCP_IMAGE_ROOT/before"

  if [[ "$phase" == 'old' ]]; then
    printf '\nThis mutation updates only %s from the current image to:\n' \
      "$ABDA_APP_NAME"
    printf '  %s@sha256:%s\n' \
      "$ABDA_IMAGE_REPOSITORY" "$ABDA_MCP_IMAGE_NEW_IMAGE_SHA256"
    printf '%s\n' \
      'Azure single revision mode keeps the current healthy revision serving' \
      'until the replacement passes its startup and readiness probes.' \
      'Type DEPLOY_ABDA_MCP_COMMAND_FIX to continue, or press Enter to cancel.'
    local confirmation=''
    IFS= read -r -p 'Confirmation: ' confirmation
    if [[ "$confirmation" != 'DEPLOY_ABDA_MCP_COMMAND_FIX' ]]; then
      printf 'Cancelled without changing Azure.\n'
      return 0
    fi

    ABDA_MCP_IMAGE_SECTION='image-only Container App update'
    printf '\n[5/8] Submitting the one image-only update...\n'
    az containerapp update \
      --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
      --container-name web \
      --image "$ABDA_IMAGE_REPOSITORY@sha256:$ABDA_MCP_IMAGE_NEW_IMAGE_SHA256" \
      --revision-suffix "$ABDA_MCP_IMAGE_TARGET_SUFFIX" \
      --only-show-errors --output none
  else
    printf '\n[5/8] The exact target image is already submitted. Resuming verification.\n'
  fi

  ABDA_MCP_IMAGE_SECTION='healthy target revision verification'
  printf '\n[6/8] Waiting for the exact target revision to become healthy...\n'
  abda_mcp_image_wait_for_target

  ABDA_MCP_IMAGE_SECTION='postdeployment application contract verification'
  printf '\n[7/8] Proving that only the image and revision suffix changed...\n'
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_MCP_IMAGE_ROOT/after-app.json"
  [[ "$(abda_mcp_image_validate_app_phase "$ABDA_MCP_IMAGE_ROOT/after-app.json")" == 'target' ]] || \
    abda_mcp_image_fail 'the target application did not settle in the reviewed state'
  abda_mcp_image_compare_application_contract \
    "$ABDA_MCP_IMAGE_ROOT/before-app.json" "$ABDA_MCP_IMAGE_ROOT/after-app.json"
  abda_mcp_image_fetch_healthy_revision \
    "$ABDA_MCP_IMAGE_TARGET_REVISION" "$ABDA_MCP_IMAGE_ROOT/after"

  ABDA_MCP_IMAGE_SECTION='postdeployment public acceptance'
  printf '\n[8/8] Verifying public HTTPS and the retained shared-view fix...\n'
  abda_mcp_image_public_acceptance "$ABDA_MCP_IMAGE_ROOT/after"
  abda_mcp_image_validate_static_fix "$ABDA_MCP_IMAGE_ROOT/after"

  printf '\nABDA-NL MCP command image status:\n'
  printf 'script_revision: %s\n' "$ABDA_MCP_IMAGE_SCRIPT_REVISION"
  printf 'source_commit: %s\n' "$ABDA_MCP_IMAGE_SOURCE_COMMIT"
  printf 'image_digest: sha256:%s\n' "$ABDA_MCP_IMAGE_NEW_IMAGE_SHA256"
  printf 'subscription_id: %s\n' "$ABDA_EXPECTED_SUBSCRIPTION"
  printf 'resource_group: %s\n' "$ABDA_RESOURCE_GROUP"
  printf 'previous_revision: %s\n' "$ABDA_MCP_IMAGE_OLD_REVISION"
  printf 'application_revision: %s\n' "$ABDA_MCP_IMAGE_TARGET_REVISION"
  printf 'public_origin: %s\n' "$ABDA_CUSTOM_ORIGIN"
  printf 'trial_max_users: 10\n'
  printf 'openrouter_failover_enabled: false\n'
  printf 'migration_rerun: false\n'
  printf 'secrets_changed: false\n'
  printf 'application_contract_preserved: true\n'
  printf 'public_acceptance: passed\n'
  printf 'result: MCP_COMMAND_FIX_DEPLOYED_CLIENT_TEST_REQUIRED\n'
  printf '%s\n' \
    'Sign in, create a short-lived read-only MCP token, and inspect its Claude command.' \
    'Confirm that --header appears before the abda-nl server name.' \
    'Then send this status and the shell exit code to Codex for client acceptance.'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_mcp_image_main "$@"
fi
