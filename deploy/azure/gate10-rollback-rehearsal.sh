#!/usr/bin/env bash

# Rehearse one schema-compatible image rollback, then restore the current image.
# The gate changes only the web image and revision suffix. It never runs a
# migration, changes a secret or setting, calls a model, or changes DNS/Auth0.

ABDA_ROLLBACK_SCRIPT_REVISION='5'
ABDA_CURRENT_SOURCE_COMMIT='51702e175bd14d4cb54075808f839d173d561324'
ABDA_CURRENT_IMAGE_SHA256='a0b3ba24aff06ecf461f86547131d86451c541e306a7ecfc278f280fcef5c0bc'
ABDA_ROLLBACK_SOURCE_COMMIT='b873112040dbfe645683d1b5e7d9adb122173ed2'
ABDA_ROLLBACK_IMAGE_SHA256='567ec34602e1b5ab1e1a9b01864f2a67219910dc3080300bc108eb33d569856c'
ABDA_CURRENT_REVISION='abda-nl-stg-web--harden-51702e1'
ABDA_ROLLBACK_SUFFIX='rollback-b873112'
ABDA_ROLLBACK_REVISION='abda-nl-stg-web--rollback-b873112'
ABDA_RESTORE_SUFFIX='restore-51702e1'
ABDA_RESTORE_REVISION='abda-nl-stg-web--restore-51702e1'
ABDA_ROLLBACK_ROOT=''

abda_rollback_cleanup() {
  local exit_code=$?
  set +e
  unset ABDA_REGISTRY_TOKEN
  if [[ "${ABDA_ROLLBACK_ROOT:-}" == /tmp/abda-nl-gate10-rollback.* &&
        -d "${ABDA_ROLLBACK_ROOT:-}" ]]; then
    rm -rf -- "$ABDA_ROLLBACK_ROOT"
  fi
  printf '\nGate 10 shell exit code: %s\n' "$exit_code"
}

abda_rollback_error() {
  local exit_code=$?
  trap - ERR
  printf '\nSTOP: Gate 10 failed in section: %s\n' \
    "${ABDA_ROLLBACK_SECTION:-unknown}" >&2
  printf '%s\n' \
    'Do not delete resources or issue a separate Azure update.' \
    'Rerun this exact pinned gate. It recognizes an interrupted rollback and restores safely.' \
    'Send the visible status and shell exit code to Codex.' >&2
  exit "$exit_code"
}

abda_rollback_interrupt() {
  trap - ERR INT
  printf '\nSTOP: Gate 10 was interrupted in section: %s\n' \
    "${ABDA_ROLLBACK_SECTION:-unknown}" >&2
  printf '%s\n' \
    'Do not issue a separate Azure update. Rerun this exact pinned gate.' >&2
  exit 130
}

abda_rollback_fail() {
  printf 'STOP: %s\n' "$*" >&2
  return 1
}

abda_rollback_set_constants() {
  ABDA_EXPECTED_SUBSCRIPTION='00e62f6e-2174-40b2-b428-8ebfd7c2ac54'
  ABDA_EXPECTED_TENANT='040f05eb-33ab-462f-af54-fb4bedb055ae'
  ABDA_EXPECTED_USER='hliu2@cloudbank.org'
  ABDA_RESOURCE_GROUP='abda-nl-staging'
  ABDA_APP_NAME='abda-nl-stg-web'
  ABDA_IMAGE_REPOSITORY='ghcr.io/liu-hy/abda-nl'
  ABDA_GENERATED_HOSTNAME='abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io'
  ABDA_CUSTOM_HOSTNAME='demo.abda-nl.org'
  ABDA_CUSTOM_ORIGIN="https://$ABDA_CUSTOM_HOSTNAME"
  ABDA_CERTIFICATE_ID='/subscriptions/00e62f6e-2174-40b2-b428-8ebfd7c2ac54/resourceGroups/abda-nl-staging/providers/Microsoft.App/managedEnvironments/abda-nl-stg-environment/managedCertificates/mc-abda-nl-stg-en-demo-abda-nl-org-1928'
  ABDA_OIDC_METADATA_URL='https://login.abda-nl.org/.well-known/openid-configuration'
  ABDA_OIDC_ISSUER='https://login.abda-nl.org/'
}

abda_rollback_validate_identity() {
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

abda_rollback_validate_registry_image() {
  local headers_path=$1
  local manifest_path=$2
  local config_path=$3
  local expected_digest=$4
  local expected_commit=$5
  python3 - "$headers_path" "$manifest_path" "$config_path" \
    "$expected_digest" "$expected_commit" <<'PY'
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
if not str((manifest.get("config") or {}).get("digest") or "").startswith("sha256:"):
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

abda_rollback_fetch_registry_image() {
  local label=$1
  local digest=$2
  local commit=$3
  local manifest_path="$ABDA_ROLLBACK_ROOT/$label-manifest.json"
  local headers_path="$ABDA_ROLLBACK_ROOT/$label-manifest.headers"
  local config_path="$ABDA_ROLLBACK_ROOT/$label-config.json"
  curl --fail --silent --show-error \
    --header "Authorization: Bearer $ABDA_REGISTRY_TOKEN" \
    --header 'Accept: application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json' \
    --dump-header "$headers_path" --output "$manifest_path" \
    "https://ghcr.io/v2/liu-hy/abda-nl/manifests/sha256:$digest"
  local config_digest=''
  config_digest="$(python3 - "$manifest_path" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(str((json.load(handle).get("config") or {}).get("digest") or ""))
PY
)"
  [[ "$config_digest" == sha256:* ]] || \
    abda_rollback_fail "the $label image config digest is invalid"
  curl --location --fail --silent --show-error \
    --header "Authorization: Bearer $ABDA_REGISTRY_TOKEN" \
    --output "$config_path" \
    "https://ghcr.io/v2/liu-hy/abda-nl/blobs/$config_digest"
  abda_rollback_validate_registry_image \
    "$headers_path" "$manifest_path" "$config_path" "$digest" "$commit"
}

abda_rollback_validate_app_phase() {
  local path=$1
  python3 - "$path" "$ABDA_APP_NAME" "$ABDA_GENERATED_HOSTNAME" \
    "$ABDA_CUSTOM_HOSTNAME" "$ABDA_CERTIFICATE_ID" \
    "$ABDA_IMAGE_REPOSITORY@sha256:$ABDA_CURRENT_IMAGE_SHA256" \
    "$ABDA_IMAGE_REPOSITORY@sha256:$ABDA_ROLLBACK_IMAGE_SHA256" \
    "$ABDA_CURRENT_REVISION" "$ABDA_ROLLBACK_REVISION" \
    "$ABDA_RESTORE_REVISION" "$ABDA_OIDC_METADATA_URL" \
    "$ABDA_OIDC_ISSUER" <<'PY'
import json
import sys
from urllib.parse import urlsplit

(
    path,
    expected_app,
    generated_hostname,
    custom_hostname,
    certificate_id,
    current_image,
    rollback_image,
    current_revision,
    rollback_revision,
    restore_revision,
    oidc_metadata_url,
    oidc_issuer,
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
if properties.get("workloadProfileName") != "Consumption":
    raise SystemExit("STOP: the Container App workload profile changed")
if (
    ingress.get("fqdn") != generated_hostname
    or ingress.get("external") is not True
    or ingress.get("allowInsecure") is not False
    or ingress.get("targetPort") != 8000
    or str(ingress.get("transport") or "auto").lower() != "auto"
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
if container.get("name") != "web":
    raise SystemExit("STOP: the web container identity changed")
resources = container.get("resources") or {}
if float(resources.get("cpu") or 0) != 0.5 or resources.get("memory") != "1Gi":
    raise SystemExit("STOP: the web container resources changed")
scale = template.get("scale") or {}
if scale.get("minReplicas") != 1 or scale.get("maxReplicas") != 3:
    raise SystemExit("STOP: the web scaling boundary changed")
if template.get("terminationGracePeriodSeconds") != 30:
    raise SystemExit("STOP: the termination grace period changed")

expected_probes = {
    "Startup": "/health/live",
    "Liveness": "/health/live",
    "Readiness": "/health/ready",
}
probes = container.get("probes") or []
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
environment = {str(item.get("name") or ""): item for item in env_items}
if len(environment) != len(env_items):
    raise SystemExit("STOP: duplicate environment variable names are present")
expected_values = {
    "ABDA_ENVIRONMENT": "staging",
    "ABDA_ENABLE_LLM": "1",
    "ABDA_AUTH_MODE": "oidc",
    "ABDA_AUTO_CREATE_DB": "0",
    "ABDA_DATABASE_POOL_SIZE": "4",
    "ABDA_DATABASE_MAX_OVERFLOW": "1",
    "ABDA_DATABASE_POOL_TIMEOUT_SECONDS": "10",
    "ABDA_PUBLIC_BASE_URL": f"https://{custom_hostname}",
    "ABDA_TRUSTED_HOSTS": f"{generated_hostname},{custom_hostname}",
    "ABDA_SESSION_COOKIE": "__Host-abda_session",
    "ABDA_COOKIE_SECURE": "1",
    "ABDA_OIDC_METADATA_URL": oidc_metadata_url,
    "ABDA_OIDC_ISSUER": oidc_issuer,
    "ABDA_TRIAL_ENABLED": "true",
    "ABDA_TRIAL_MAX_USERS": "10",
    "ABDA_TRIAL_GRANT_MICROUSD": "5000000",
    "ABDA_TRIAL_BUDGET_MICROUSD": "50000000",
    "ABDA_LLM_BACKEND": "claude",
    "ABDA_CLAUDE_PROVIDER": "foundry",
    "ABDA_LLM_DEFAULT_PROFILE": "balanced",
    "ABDA_LLM_ALLOW_BYOK": "1",
    "ABDA_LLM_REQUIRE_AUTH": "1",
    "ABDA_OPENROUTER_FAILOVER_ENABLED": "false",
    "ABDA_OPENROUTER_BUDGET_MICROUSD": "500000000",
    "ABDA_OPENROUTER_BUDGET_ACK": "",
    "ABDA_PROXY_MODE": "azure-container-apps",
    "ABDA_ABUSE_PROTECTION_ENABLED": "1",
    "ABDA_MAX_REQUEST_BODY_BYTES": "2000000",
    "ABDA_ANONYMOUS_REQUESTS_PER_MINUTE": "120",
    "ABDA_MUTATION_REQUESTS_PER_MINUTE": "60",
    "ABDA_LLM_REQUESTS_PER_MINUTE": "20",
    "ANTHROPIC_FOUNDRY_CLAUDE_SONNET_4_6_MODEL": "claude-sonnet-4-6",
}
expected_secret_refs = {
    "ABDA_DATABASE_URL": "database-url",
    "ABDA_SESSION_SECRET": "session-secret",
    "ABDA_MCP_TOKEN_PEPPER": "mcp-token-pepper",
    "ABDA_METRICS_TOKEN": "metrics-token",
    "ABDA_OIDC_CLIENT_SECRET": "oidc-client-secret",
    "AZURE_OPENAI_API_KEY": "foundry-api-key",
    "OPENROUTER_API_KEY": "openrouter-api-key",
}
opaque_values = {"ABDA_OIDC_CLIENT_ID", "AZURE_ANTHROPIC_ENDPOINT"}
if set(environment) != set(expected_values) | set(expected_secret_refs) | opaque_values:
    raise SystemExit("STOP: the web environment variable inventory changed")
for name, expected in expected_values.items():
    actual = str(environment.get(name, {}).get("value") or "")
    if name in {"ABDA_TRIAL_ENABLED", "ABDA_OPENROUTER_FAILOVER_ENABLED"}:
        actual = actual.lower()
    if actual != expected:
        raise SystemExit(f"STOP: deployed setting {name} changed")
for name, expected in expected_secret_refs.items():
    if environment.get(name, {}).get("secretRef") != expected:
        raise SystemExit(f"STOP: deployed secret reference {name} changed")
client_id = str(environment.get("ABDA_OIDC_CLIENT_ID", {}).get("value") or "")
if not 20 <= len(client_id) <= 128 or any(character.isspace() for character in client_id):
    raise SystemExit("STOP: the OIDC client identifier is invalid")
foundry_endpoint = str(environment.get("AZURE_ANTHROPIC_ENDPOINT", {}).get("value") or "")
parsed_foundry = urlsplit(foundry_endpoint)
if (
    parsed_foundry.scheme != "https"
    or not str(parsed_foundry.hostname or "").endswith(".services.ai.azure.com")
    or parsed_foundry.path.rstrip("/") != "/anthropic"
    or parsed_foundry.username is not None
    or parsed_foundry.password is not None
    or parsed_foundry.query
    or parsed_foundry.fragment
):
    raise SystemExit("STOP: the Foundry Anthropic endpoint boundary changed")
secret_names = {str(item.get("name") or "") for item in configuration.get("secrets") or []}
if secret_names != set(expected_secret_refs.values()):
    raise SystemExit("STOP: the Container App secret inventory changed")
if any("ADMIN" in name.upper() or "PASSWORD" in name.upper() for name in environment):
    raise SystemExit("STOP: an administrator credential setting reached the web app")

image = str(container.get("image") or "")
latest = str(properties.get("latestRevisionName") or "")
ready = str(properties.get("latestReadyRevisionName") or "")
if image == current_image and latest == current_revision and ready == current_revision:
    print("current")
elif image == current_image and latest == restore_revision:
    print("restored" if ready == restore_revision else "restore_pending")
elif image == rollback_image and latest == rollback_revision:
    print("rollback" if ready == rollback_revision else "rollback_pending")
else:
    raise SystemExit("STOP: the image and revision are outside the reviewed rehearsal states")
PY
}

abda_rollback_compare_application_contract() {
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


left = selected(sys.argv[1])
right = selected(sys.argv[2])
if left == right:
    raise SystemExit(0)


def changed_paths(left_value, right_value, prefix=""):
    if type(left_value) is not type(right_value):
        return [prefix or "<root>"]
    if isinstance(left_value, dict):
        paths = []
        for key in sorted(set(left_value) | set(right_value)):
            child = f"{prefix}.{key}" if prefix else str(key)
            if key not in left_value or key not in right_value:
                paths.append(child)
            else:
                paths.extend(changed_paths(left_value[key], right_value[key], child))
        return paths
    if isinstance(left_value, list):
        if len(left_value) != len(right_value):
            return [prefix]
        paths = []
        for index, (left_item, right_item) in enumerate(zip(left_value, right_value)):
            paths.extend(changed_paths(left_item, right_item, f"{prefix}[{index}]"))
        return paths
    return [] if left_value == right_value else [prefix]


paths = changed_paths(left, right)
raise SystemExit(
    "STOP: settings outside the image and revision changed at: " + ", ".join(paths)
)
PY
}

abda_rollback_validate_revision() {
  local revision_path=$1
  local replicas_path=$2
  local expected_revision=$3
  local expected_image=$4
  python3 - "$revision_path" "$replicas_path" \
    "$expected_revision" "$expected_image" <<'PY'
import json
import sys

revision_path, replicas_path, expected_revision, expected_image = sys.argv[1:]
with open(revision_path, encoding="utf-8") as handle:
    revision = json.load(handle)
with open(replicas_path, encoding="utf-8") as handle:
    replicas = json.load(handle)
properties = revision.get("properties") or {}
containers = (properties.get("template") or {}).get("containers") or []
if revision.get("name") != expected_revision:
    raise SystemExit("STOP: Azure returned an unexpected revision")
if properties.get("active") is not True:
    raise SystemExit("STOP: the revision is not active")
if properties.get("healthState") != "Healthy":
    raise SystemExit("STOP: the revision is not healthy")
if properties.get("provisioningState") != "Provisioned":
    raise SystemExit("STOP: the revision is not provisioned")
if len(containers) != 1 or containers[0].get("image") != expected_image:
    raise SystemExit("STOP: the revision image changed")
if not isinstance(replicas, list) or not 1 <= len(replicas) <= 3:
    raise SystemExit("STOP: the revision has an unexpected replica count")
for replica in replicas:
    replica_properties = replica.get("properties") or {}
    if replica_properties.get("runningState") != "Running":
        raise SystemExit("STOP: a replica is not running")
    replica_containers = replica_properties.get("containers") or []
    if not replica_containers or any(item.get("ready") is not True for item in replica_containers):
        raise SystemExit("STOP: a replica container is not ready")
PY
}

abda_rollback_wait_for_revision() {
  local revision=$1
  local image=$2
  local label=$3
  local attempt=0
  local state=''
  for attempt in $(seq 1 60); do
    if az containerapp show \
      --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
      --output json >"$ABDA_ROLLBACK_ROOT/$label-app.json" 2>/dev/null && \
      az containerapp revision show \
        --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
        --revision "$revision" --output json \
        >"$ABDA_ROLLBACK_ROOT/$label-revision.json" 2>/dev/null && \
      az containerapp replica list \
        --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
        --revision "$revision" --output json \
        >"$ABDA_ROLLBACK_ROOT/$label-replicas.json" 2>/dev/null; then
      state="$(python3 - "$ABDA_ROLLBACK_ROOT/$label-app.json" \
        "$ABDA_ROLLBACK_ROOT/$label-revision.json" \
        "$ABDA_ROLLBACK_ROOT/$label-replicas.json" "$revision" "$image" <<'PY'
import json
import sys

app_path, revision_path, replicas_path, expected_revision, expected_image = sys.argv[1:]
with open(app_path, encoding="utf-8") as handle:
    app = json.load(handle)
with open(revision_path, encoding="utf-8") as handle:
    revision = json.load(handle)
with open(replicas_path, encoding="utf-8") as handle:
    replicas = json.load(handle)
app_properties = app.get("properties") or {}
revision_properties = revision.get("properties") or {}
containers = (app_properties.get("template") or {}).get("containers") or []
running = sum(
    1 for item in replicas
    if (item.get("properties") or {}).get("runningState") == "Running"
)
ready = sum(
    1 for item in replicas
    if (item.get("properties") or {}).get("containers")
    and all(
        container.get("ready") is True
        for container in (item.get("properties") or {}).get("containers") or []
    )
)
values = (
    app_properties.get("provisioningState"),
    app_properties.get("runningStatus"),
    app_properties.get("latestRevisionName"),
    app_properties.get("latestReadyRevisionName"),
    revision_properties.get("provisioningState"),
    revision_properties.get("healthState"),
    revision_properties.get("active"),
    str(containers[0].get("image") or "") if len(containers) == 1 else "",
    len(replicas),
    running,
    ready,
)
print("|".join(str(value) for value in values))
if (
    values[0] == "Succeeded"
    and values[1] == "Running"
    and values[2] == expected_revision
    and values[3] == expected_revision
    and values[4] == "Provisioned"
    and values[5] == "Healthy"
    and values[6] is True
    and values[7] == expected_image
    and 1 <= values[8] <= 3
    and values[9] == values[8]
    and values[10] == values[8]
):
    raise SystemExit(0)
raise SystemExit(1)
PY
)" && {
        printf '%s revision state: %s\n' "$label" "$state"
        abda_rollback_validate_revision \
          "$ABDA_ROLLBACK_ROOT/$label-revision.json" \
          "$ABDA_ROLLBACK_ROOT/$label-replicas.json" "$revision" "$image"
        return 0
      }
    fi
    if (( attempt == 1 || attempt % 6 == 0 )); then
      printf '%s revision state: %s (attempt %s/60)\n' \
        "$label" "${state:-waiting}" "$attempt"
    fi
    sleep 5
  done
  abda_rollback_fail "the $label revision did not become healthy"
}

abda_rollback_validate_public_contract() {
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

abda_rollback_public_acceptance() {
  local prefix=$1
  local require_shared_fix=${2:-false}
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_CUSTOM_ORIGIN/" --output "$prefix-root.html"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_CUSTOM_ORIGIN/health/live" --output "$prefix-live.json"
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
  [[ -s "$prefix-root.html" && -s "$prefix-live.json" && \
     -s "$prefix-privacy.html" && -s "$prefix-terms.html" ]] || \
    abda_rollback_fail 'a public page returned an empty response'
  local metrics_status=''
  metrics_status="$(curl --silent --show-error \
    --proto '=https' --tlsv1.2 --connect-timeout 10 --max-time 30 \
    --output "$prefix-metrics.json" --write-out '%{http_code}' \
    "$ABDA_CUSTOM_ORIGIN/internal/metrics")"
  [[ "$metrics_status" == '401' ]] || \
    abda_rollback_fail 'the metrics endpoint is not protected'
  abda_rollback_validate_public_contract "$prefix"
  if [[ "$require_shared_fix" == 'true' ]]; then
    curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
      --connect-timeout 10 --max-time 30 \
      "$ABDA_CUSTOM_ORIGIN/workspace.js?source=$ABDA_CURRENT_SOURCE_COMMIT" \
      --output "$prefix-workspace.js"
    curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
      --connect-timeout 10 --max-time 30 \
      "$ABDA_CUSTOM_ORIGIN/app.js?source=$ABDA_CURRENT_SOURCE_COMMIT" \
      --output "$prefix-app.js"
    grep -Fq \
      "if (state.readOnly) return { tab: null, message: 'Chat and edits are disabled in a shared read-only view.' };" \
      "$prefix-workspace.js" || \
      abda_rollback_fail 'the restored shared-view access rule is missing'
    grep -Fq 'if (accessIssue.tab) openWorkspace(accessIssue.tab);' \
      "$prefix-app.js" || \
      abda_rollback_fail 'the restored chat action guard is missing'
  fi
}

abda_rollback_update_image() {
  local digest=$1
  local suffix=$2
  az containerapp update \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --container-name web \
    --image "$ABDA_IMAGE_REPOSITORY@sha256:$digest" \
    --revision-suffix "$suffix" \
    --only-show-errors --output none
}

abda_rollback_print_status() {
  printf '\nABDA-NL Gate 10 rollback rehearsal status:\n'
  printf 'script_revision: %s\n' "$ABDA_ROLLBACK_SCRIPT_REVISION"
  printf 'current_source_commit: %s\n' "$ABDA_CURRENT_SOURCE_COMMIT"
  printf 'current_image_digest: sha256:%s\n' "$ABDA_CURRENT_IMAGE_SHA256"
  printf 'rollback_source_commit: %s\n' "$ABDA_ROLLBACK_SOURCE_COMMIT"
  printf 'rollback_image_digest: sha256:%s\n' "$ABDA_ROLLBACK_IMAGE_SHA256"
  printf 'subscription_id: %s\n' "$ABDA_EXPECTED_SUBSCRIPTION"
  printf 'resource_group: %s\n' "$ABDA_RESOURCE_GROUP"
  printf 'rollback_revision: %s\n' "$ABDA_ROLLBACK_REVISION"
  printf 'restored_revision: %s\n' "$ABDA_RESTORE_REVISION"
  printf 'public_origin: %s\n' "$ABDA_CUSTOM_ORIGIN"
  printf 'migration_rerun: false\n'
  printf 'secrets_changed: false\n'
  printf 'settings_changed: false\n'
  printf 'trial_max_users: 10\n'
  printf 'openrouter_failover_enabled: false\n'
  printf 'rollback_acceptance: passed\n'
  printf 'restored_acceptance: passed\n'
  printf 'result: COMPATIBLE_IMAGE_ROLLBACK_AND_RESTORE_VERIFIED\n'
  printf '%s\n' \
    'The current security-hardened image is healthy again. Send this status and the shell exit code to Codex.'
}

abda_rollback_main() {
  set -Eeuo pipefail
  set +x
  umask 077
  unset HISTFILE
  trap abda_rollback_error ERR
  trap abda_rollback_cleanup EXIT
  trap abda_rollback_interrupt INT
  ABDA_ROLLBACK_SECTION='bootstrap'

  printf 'ABDA-NL Gate 10 rollback rehearsal script revision: %s\n' \
    "$ABDA_ROLLBACK_SCRIPT_REVISION"
  printf '%s\n' \
    'This resume-safe gate temporarily deploys one recorded compatible image,' \
    'proves it is healthy, and automatically restores the current image.' \
    'Only the web image and revision suffix change. No migration or model call runs.'

  abda_rollback_set_constants
  local command_name=''
  for command_name in az curl grep python3; do
    command -v "$command_name" >/dev/null 2>&1 || \
      abda_rollback_fail "required command is unavailable: $command_name"
  done
  ABDA_ROLLBACK_ROOT="$(mktemp -d /tmp/abda-nl-gate10-rollback.XXXXXX)"
  chmod 700 "$ABDA_ROLLBACK_ROOT"
  az containerapp update --help >"$ABDA_ROLLBACK_ROOT/containerapp-update.help"
  grep -Fq -- '--container-name' "$ABDA_ROLLBACK_ROOT/containerapp-update.help"
  grep -Fq -- '--image' "$ABDA_ROLLBACK_ROOT/containerapp-update.help"
  grep -Fq -- '--revision-suffix' "$ABDA_ROLLBACK_ROOT/containerapp-update.help"

  ABDA_ROLLBACK_SECTION='Azure identity verification'
  printf '\n[1/9] Verifying the exact Azure identity...\n'
  az account show --output json >"$ABDA_ROLLBACK_ROOT/account.json"
  abda_rollback_validate_identity "$ABDA_ROLLBACK_ROOT/account.json"
  az account show \
    --query '{Name:name,TenantId:tenantId,User:user.name,State:state}' \
    --output table

  ABDA_ROLLBACK_SECTION='immutable image verification'
  printf '\n[2/9] Verifying both immutable public images and provenance labels...\n'
  ABDA_REGISTRY_TOKEN="$(curl --fail --silent --show-error --get \
    --data-urlencode 'scope=repository:liu-hy/abda-nl:pull' \
    --data-urlencode 'service=ghcr.io' 'https://ghcr.io/token' | \
    python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')"
  abda_rollback_fetch_registry_image \
    current "$ABDA_CURRENT_IMAGE_SHA256" "$ABDA_CURRENT_SOURCE_COMMIT"
  abda_rollback_fetch_registry_image \
    rollback "$ABDA_ROLLBACK_IMAGE_SHA256" "$ABDA_ROLLBACK_SOURCE_COMMIT"
  unset ABDA_REGISTRY_TOKEN
  printf 'Verified current and rollback image provenance.\n'

  ABDA_ROLLBACK_SECTION='application state verification'
  printf '\n[3/9] Verifying the exact application and selecting a resume phase...\n'
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_ROLLBACK_ROOT/entry-app.json"
  local phase=''
  phase="$(abda_rollback_validate_app_phase "$ABDA_ROLLBACK_ROOT/entry-app.json")"
  printf 'rehearsal_phase: %s\n' "$phase"

  if [[ "$phase" == 'restored' ]]; then
    ABDA_ROLLBACK_SECTION='restored application acceptance'
    printf '\n[4/9] The completed restored revision is already active.\n'
    printf '[5/9] The rollback transition was already completed.\n'
    printf '[6/9] The rollback acceptance was already completed.\n'
    printf '[7/9] The restore transition was already completed.\n'
    printf '[8/9] Rechecking the restored public application...\n'
    abda_rollback_public_acceptance "$ABDA_ROLLBACK_ROOT/restored" true
    printf '[9/9] Rehearsal state is complete and idempotent.\n'
    abda_rollback_print_status
    return 0
  fi

  if [[ "$phase" == 'current' ]]; then
    ABDA_ROLLBACK_SECTION='pre-rehearsal public acceptance'
    printf '\n[4/9] Verifying the current public application before mutation...\n'
    abda_rollback_public_acceptance "$ABDA_ROLLBACK_ROOT/before" true
    printf '\nThis rehearsal performs two reviewed image-only updates:\n'
    printf '  1. current sha256:%s -> rollback sha256:%s\n' \
      "$ABDA_CURRENT_IMAGE_SHA256" "$ABDA_ROLLBACK_IMAGE_SHA256"
    printf '  2. rollback sha256:%s -> current sha256:%s\n' \
      "$ABDA_ROLLBACK_IMAGE_SHA256" "$ABDA_CURRENT_IMAGE_SHA256"
    printf '%s\n' \
      'The previous image uses the same database schema and public configuration.' \
      'Azure single revision mode retains a ready revision during each transition.' \
      'Type RUN_ABDA_ROLLBACK_REHEARSAL to continue, or press Enter to cancel.'
    local confirmation=''
    IFS= read -r -p 'Confirmation: ' confirmation
    if [[ "$confirmation" != 'RUN_ABDA_ROLLBACK_REHEARSAL' ]]; then
      printf 'Cancelled without changing Azure.\n'
      return 0
    fi
    ABDA_ROLLBACK_SECTION='rollback image update'
    printf '\n[5/9] Deploying the recorded compatible rollback image...\n'
    abda_rollback_update_image \
      "$ABDA_ROLLBACK_IMAGE_SHA256" "$ABDA_ROLLBACK_SUFFIX"
    phase='rollback_pending'
  else
    printf '\n[4/9] Resuming the exact previously confirmed rehearsal state.\n'
    if [[ "$phase" == 'rollback' || "$phase" == 'rollback_pending' ]]; then
      printf '[5/9] The rollback image was already submitted.\n'
    else
      printf '[5/9] The rollback image and acceptance were already completed.\n'
    fi
  fi

  if [[ "$phase" == 'rollback' || "$phase" == 'rollback_pending' ]]; then
    ABDA_ROLLBACK_SECTION='rollback revision verification'
    printf '\n[6/9] Waiting for and accepting the rollback revision...\n'
    abda_rollback_wait_for_revision \
      "$ABDA_ROLLBACK_REVISION" \
      "$ABDA_IMAGE_REPOSITORY@sha256:$ABDA_ROLLBACK_IMAGE_SHA256" rollback
    az containerapp show \
      --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
      --output json >"$ABDA_ROLLBACK_ROOT/rollback-app.json"
    [[ "$(abda_rollback_validate_app_phase "$ABDA_ROLLBACK_ROOT/rollback-app.json")" == 'rollback' ]] || \
      abda_rollback_fail 'the rollback application did not settle in the reviewed state'
    if [[ -f "$ABDA_ROLLBACK_ROOT/entry-app.json" && \
          "$(abda_rollback_validate_app_phase "$ABDA_ROLLBACK_ROOT/entry-app.json")" == 'current' ]]; then
      abda_rollback_compare_application_contract \
        "$ABDA_ROLLBACK_ROOT/entry-app.json" "$ABDA_ROLLBACK_ROOT/rollback-app.json"
    fi
    abda_rollback_public_acceptance "$ABDA_ROLLBACK_ROOT/rollback-public" false
    printf 'rollback_acceptance: passed\n'

    ABDA_ROLLBACK_SECTION='current image restoration'
    printf '\n[7/9] Restoring the current security-hardened image automatically...\n'
    abda_rollback_update_image \
      "$ABDA_CURRENT_IMAGE_SHA256" "$ABDA_RESTORE_SUFFIX"
    phase='restore_pending'
  else
    printf '\n[6/9] The rollback revision and public acceptance were already completed.\n'
    printf '[7/9] The current image was already submitted for restoration.\n'
  fi

  ABDA_ROLLBACK_SECTION='restored revision verification'
  printf '\n[8/9] Waiting for and accepting the restored current revision...\n'
  abda_rollback_wait_for_revision \
    "$ABDA_RESTORE_REVISION" \
    "$ABDA_IMAGE_REPOSITORY@sha256:$ABDA_CURRENT_IMAGE_SHA256" restored
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_ROLLBACK_ROOT/restored-app.json"
  [[ "$(abda_rollback_validate_app_phase "$ABDA_ROLLBACK_ROOT/restored-app.json")" == 'restored' ]] || \
    abda_rollback_fail 'the current application did not settle in the restored state'
  if [[ -f "$ABDA_ROLLBACK_ROOT/rollback-app.json" ]]; then
    abda_rollback_compare_application_contract \
      "$ABDA_ROLLBACK_ROOT/rollback-app.json" "$ABDA_ROLLBACK_ROOT/restored-app.json"
  else
    abda_rollback_compare_application_contract \
      "$ABDA_ROLLBACK_ROOT/entry-app.json" "$ABDA_ROLLBACK_ROOT/restored-app.json"
  fi

  ABDA_ROLLBACK_SECTION='restored public acceptance'
  printf '\n[9/9] Verifying the restored public application and shared-view fix...\n'
  abda_rollback_public_acceptance "$ABDA_ROLLBACK_ROOT/restored-public" true
  abda_rollback_print_status
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_rollback_main "$@"
fi
