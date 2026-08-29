#!/usr/bin/env bash

# Deploy the reviewed release-candidate image to the existing healthy staging
# Container App. The only Azure mutation is the web container image and its
# revision suffix. Trial limits stay at the ten-user pilot and public
# OpenRouter failover stays disabled.

ABDA_RC_SCRIPT_REVISION='1'
ABDA_RC_SOURCE_COMMIT='448510936c69d485cf9b4e834adea69becf6b114'
ABDA_RC_OLD_IMAGE_SHA256='71f759c7bbfe25cc2ae974f006b8fed853ef87e5db260fc875fa3f50257739f9'
ABDA_RC_NEW_IMAGE_SHA256='11861402c8fa3fd677848f94155e29065ebafd9a4a76b03e41b1cf48312e5c58'
ABDA_RC_OLD_REVISION='abda-nl-stg-web--trial-pilot-v1'
ABDA_RC_TARGET_SUFFIX='rc-4485109'
ABDA_RC_TARGET_REVISION='abda-nl-stg-web--rc-4485109'
ABDA_RC_ROOT=''

abda_rc_cleanup() {
  local exit_code=$?
  set +e
  unset ABDA_REGISTRY_TOKEN
  if [[ "${ABDA_RC_ROOT:-}" == /tmp/abda-nl-release-candidate.* &&
        -d "${ABDA_RC_ROOT:-}" ]]; then
    rm -rf -- "$ABDA_RC_ROOT"
  fi
  printf '\nGate 6 shell exit code: %s\n' "$exit_code"
}

abda_rc_error() {
  local exit_code=$?
  trap - ERR
  printf '\nSTOP: Gate 6 failed in section: %s\n' \
    "${ABDA_RC_SECTION:-unknown}" >&2
  printf '%s\n' \
    'Do not delete resources or rerun blindly.' \
    'Send the visible status and shell exit code to Codex.' >&2
  exit "$exit_code"
}

abda_rc_interrupt() {
  trap - ERR INT
  printf '\nSTOP: Gate 6 was interrupted in section: %s\n' \
    "${ABDA_RC_SECTION:-unknown}" >&2
  exit 130
}

abda_rc_fail() {
  printf 'STOP: %s\n' "$*" >&2
  return 1
}

abda_rc_set_constants() {
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
  ABDA_PILOT_MAX_USERS='10'
  ABDA_PILOT_GRANT_MICROUSD='5000000'
  ABDA_PILOT_BUDGET_MICROUSD='50000000'
  ABDA_OPENROUTER_BUDGET_MICROUSD='500000000'
}

abda_rc_validate_identity() {
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

abda_rc_validate_registry_image() {
  local headers_path=$1
  local manifest_path=$2
  local config_path=$3
  python3 - "$headers_path" "$manifest_path" "$config_path" \
    "$ABDA_RC_NEW_IMAGE_SHA256" "$ABDA_RC_SOURCE_COMMIT" <<'PY'
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

abda_rc_validate_app_phase() {
  local app_path=$1
  python3 - "$app_path" "$ABDA_APP_NAME" "$ABDA_GENERATED_HOSTNAME" \
    "$ABDA_CUSTOM_HOSTNAME" "$ABDA_CERTIFICATE_ID" \
    "$ABDA_IMAGE_REPOSITORY@sha256:$ABDA_RC_OLD_IMAGE_SHA256" \
    "$ABDA_IMAGE_REPOSITORY@sha256:$ABDA_RC_NEW_IMAGE_SHA256" \
    "$ABDA_RC_OLD_REVISION" "$ABDA_RC_TARGET_REVISION" \
    "$ABDA_OIDC_METADATA_URL" "$ABDA_OIDC_ISSUER" \
    "$ABDA_PILOT_MAX_USERS" \
    "$ABDA_PILOT_GRANT_MICROUSD" "$ABDA_PILOT_BUDGET_MICROUSD" \
    "$ABDA_OPENROUTER_BUDGET_MICROUSD" <<'PY'
import json
import sys
from urllib.parse import urlsplit

(
    path,
    expected_app,
    generated_hostname,
    custom_hostname,
    certificate_id,
    old_image,
    target_image,
    old_revision,
    target_revision,
    oidc_metadata_url,
    oidc_issuer,
    pilot_max_users,
    grant_microusd,
    pilot_budget_microusd,
    openrouter_budget_microusd,
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
env = {str(item.get("name") or ""): item for item in env_items}
if len(env) != len(env_items):
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
    "ABDA_TRIAL_MAX_USERS": pilot_max_users,
    "ABDA_TRIAL_GRANT_MICROUSD": grant_microusd,
    "ABDA_TRIAL_BUDGET_MICROUSD": pilot_budget_microusd,
    "ABDA_LLM_BACKEND": "claude",
    "ABDA_CLAUDE_PROVIDER": "foundry",
    "ABDA_LLM_DEFAULT_PROFILE": "balanced",
    "ABDA_LLM_ALLOW_BYOK": "1",
    "ABDA_LLM_REQUIRE_AUTH": "1",
    "ABDA_OPENROUTER_FAILOVER_ENABLED": "false",
    "ABDA_OPENROUTER_BUDGET_MICROUSD": openrouter_budget_microusd,
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
expected_names = set(expected_values) | set(expected_secret_refs) | opaque_values
if set(env) != expected_names:
    raise SystemExit("STOP: the web environment variable inventory changed")
for name, expected in expected_values.items():
    actual = str(env.get(name, {}).get("value") or "")
    if name in {"ABDA_TRIAL_ENABLED", "ABDA_OPENROUTER_FAILOVER_ENABLED"}:
        actual = actual.lower()
    if actual != expected:
        raise SystemExit(f"STOP: deployed setting {name} changed")
for name, secret_ref in expected_secret_refs.items():
    if env.get(name, {}).get("secretRef") != secret_ref:
        raise SystemExit(f"STOP: deployed secret reference {name} changed")
client_id = str(env.get("ABDA_OIDC_CLIENT_ID", {}).get("value") or "")
if not 20 <= len(client_id) <= 128 or any(character.isspace() for character in client_id):
    raise SystemExit("STOP: the OIDC client identifier is invalid")
foundry_endpoint = str(env.get("AZURE_ANTHROPIC_ENDPOINT", {}).get("value") or "")
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
if any("ADMIN" in name.upper() or "PASSWORD" in name.upper() for name in env):
    raise SystemExit("STOP: an administrator credential setting reached the web app")

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

abda_rc_compare_opaque_settings() {
  local before_path=$1
  local after_path=$2
  python3 - "$before_path" "$after_path" <<'PY'
import json
import sys


def selected(path):
    with open(path, encoding="utf-8") as handle:
        app = json.load(handle)
    containers = ((app.get("properties") or {}).get("template") or {}).get(
        "containers"
    ) or []
    if len(containers) != 1:
        raise SystemExit("STOP: the web container identity changed")
    env = {str(item.get("name") or ""): item for item in containers[0].get("env") or []}
    return {
        name: str(env.get(name, {}).get("value") or "")
        for name in ("ABDA_OIDC_CLIENT_ID", "AZURE_ANTHROPIC_ENDPOINT")
    }


if selected(sys.argv[1]) != selected(sys.argv[2]):
    raise SystemExit("STOP: an opaque identity or provider setting changed")
PY
}

abda_rc_validate_revision() {
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

abda_rc_fetch_healthy_revision() {
  local revision=$1
  local prefix=$2
  az containerapp revision show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --revision "$revision" --output json >"$prefix-revision.json"
  az containerapp replica list \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --revision "$revision" --output json >"$prefix-replicas.json"
  abda_rc_validate_revision \
    "$prefix-revision.json" "$prefix-replicas.json" "$revision"
}

abda_rc_load_metrics_token() {
  local secrets_path=$1
  local config_path="$ABDA_RC_ROOT/metrics-curl-config"
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
names = {item.get("name") for item in values}
if names != expected:
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
    abda_rc_fail 'the protected metrics curl configuration could not be created'
}

abda_rc_validate_acceptance() {
  local root_headers_path=$1
  local ready_path=$2
  local config_path=$3
  local metrics_path=$4
  python3 - "$root_headers_path" "$ready_path" "$config_path" \
    "$metrics_path" "$ABDA_PILOT_MAX_USERS" \
    "$ABDA_PILOT_GRANT_MICROUSD" "$ABDA_PILOT_BUDGET_MICROUSD" \
    "$ABDA_OPENROUTER_BUDGET_MICROUSD" <<'PY'
import json
import sys

(
    root_headers_path,
    ready_path,
    config_path,
    metrics_path,
    max_users,
    grant_microusd,
    trial_budget_microusd,
    openrouter_budget_microusd,
) = sys.argv[1:]

with open(root_headers_path, encoding="utf-8") as handle:
    header_lines = handle.read().splitlines()
headers = {}
for line in header_lines:
    name, separator, value = line.partition(":")
    if separator:
        headers[name.strip().lower()] = value.strip()
required_exact = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
}
for name, expected in required_exact.items():
    if headers.get(name) != expected:
        raise SystemExit(f"STOP: the root security header {name} changed")
for directive in ("camera=()", "microphone=()", "geolocation=()", "payment=()"):
    if directive not in headers.get("permissions-policy", ""):
        raise SystemExit(f"STOP: Permissions-Policy is missing {directive}")
if "max-age=31536000" not in headers.get("strict-transport-security", ""):
    raise SystemExit("STOP: Strict-Transport-Security changed")
for directive in (
    "default-src 'self'",
    "base-uri 'none'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    "script-src 'self'",
    "connect-src 'self'",
    "upgrade-insecure-requests",
):
    if directive not in headers.get("content-security-policy", ""):
        raise SystemExit(f"STOP: Content-Security-Policy is missing {directive}")

with open(ready_path, encoding="utf-8") as handle:
    if json.load(handle) != {"status": "ready"}:
        raise SystemExit("STOP: the custom origin is not ready")
with open(config_path, encoding="utf-8") as handle:
    config = json.load(handle)
required_flags = {
    "llm_enabled": True,
    "llm_auth_required": True,
    "byok_enabled": True,
    "byok_keys_stored": False,
}
for name, expected in required_flags.items():
    if config.get(name) is not expected:
        raise SystemExit(f"STOP: /config requires {name}={expected!r}")
if config.get("default_profile") != "balanced":
    raise SystemExit("STOP: the funded default profile changed")
profiles = config.get("profiles") or []
if [item.get("id") for item in profiles] != ["balanced"]:
    raise SystemExit("STOP: the funded profile allowlist changed")
providers = config.get("byok_providers") or []
provider_ids = {str(item.get("id") or "") for item in providers if isinstance(item, dict)}
if provider_ids != {"anthropic", "google", "openai", "openrouter"}:
    raise SystemExit("STOP: the BYOK provider allowlist changed")
for provider in providers:
    models = provider.get("models") or []
    model_ids = [str(item.get("id") or "") for item in models if isinstance(item, dict)]
    if not model_ids or len(model_ids) != len(models) or len(set(model_ids)) != len(model_ids):
        raise SystemExit("STOP: a BYOK provider model allowlist is invalid")
    if provider.get("default_model") not in model_ids:
        raise SystemExit("STOP: a BYOK default model is not allowlisted")

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
database_pool_capacity = integer("abda_database_pool_capacity")

if (trial_enabled, trial_max_users, trial_grant, trial_budget) != (
    1,
    int(max_users),
    int(grant_microusd),
    int(trial_budget_microusd),
):
    raise SystemExit("STOP: the live trial cap differs from the reviewed pilot")
if not 1 <= activations <= trial_max_users or allocated != activations * trial_grant:
    raise SystemExit("STOP: trial allocation does not reconcile")
if trial_spent <= 0 or trial_spent + trial_reserved > allocated:
    raise SystemExit("STOP: trial spending does not reconcile")
if trial_reserved or trial_uncertain_count or trial_uncertain_cost:
    raise SystemExit("STOP: trial reservations are not safely idle")
if (
    openrouter_enabled != 0
    or openrouter_budget != int(openrouter_budget_microusd)
    or openrouter_spent
    or openrouter_reserved
    or openrouter_uncertain_count
    or openrouter_uncertain_cost
):
    raise SystemExit("STOP: OpenRouter is not in the reviewed disabled and unused state")
if database_pool_capacity != 5:
    raise SystemExit("STOP: the database pool capacity changed")

print(f"trial_activations: {activations}")
print(f"trial_allocated_microusd: {allocated}")
print(f"trial_spent_microusd: {trial_spent}")
print(f"trial_reserved_microusd: {trial_reserved}")
print(f"openrouter_enabled: {openrouter_enabled}")
print(f"openrouter_spent_microusd: {openrouter_spent}")
print(f"openrouter_reserved_microusd: {openrouter_reserved}")
print(f"database_pool_capacity: {database_pool_capacity}")
PY
}

abda_rc_public_acceptance() {
  local prefix=$1
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    --dump-header "$prefix-root.headers" \
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
    abda_rc_fail 'a public page returned an empty response'
  local unauthenticated_status=''
  unauthenticated_status="$(curl --silent --show-error \
    --proto '=https' --tlsv1.2 --connect-timeout 10 --max-time 30 \
    --output "$prefix-metrics-unauth.json" --write-out '%{http_code}' \
    "$ABDA_CUSTOM_ORIGIN/internal/metrics")"
  [[ "$unauthenticated_status" == '401' ]] || \
    abda_rc_fail 'the metrics endpoint is not protected'
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    --config "$ABDA_RC_ROOT/metrics-curl-config" \
    "$ABDA_CUSTOM_ORIGIN/internal/metrics" --output "$prefix-metrics.txt"
  abda_rc_validate_acceptance \
    "$prefix-root.headers" "$prefix-ready.json" "$prefix-config.json" \
    "$prefix-metrics.txt"
}

abda_rc_wait_for_target() {
  local attempt=0
  local state=''
  for attempt in $(seq 1 60); do
    if az containerapp show \
      --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
      --output json >"$ABDA_RC_ROOT/wait-app.json" 2>/dev/null && \
      az containerapp revision show \
        --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
        --revision "$ABDA_RC_TARGET_REVISION" --output json \
        >"$ABDA_RC_ROOT/wait-revision.json" 2>/dev/null && \
      az containerapp replica list \
        --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
        --revision "$ABDA_RC_TARGET_REVISION" --output json \
        >"$ABDA_RC_ROOT/wait-replicas.json" 2>/dev/null; then
      state="$(python3 - "$ABDA_RC_ROOT/wait-app.json" \
        "$ABDA_RC_ROOT/wait-revision.json" \
        "$ABDA_RC_ROOT/wait-replicas.json" \
        "$ABDA_RC_TARGET_REVISION" \
        "$ABDA_IMAGE_REPOSITORY@sha256:$ABDA_RC_NEW_IMAGE_SHA256" <<'PY'
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
        printf 'Release-candidate state: %s\n' "$state"
        abda_rc_validate_app_phase "$ABDA_RC_ROOT/wait-app.json" | \
          grep -Fxq target
        abda_rc_validate_revision \
          "$ABDA_RC_ROOT/wait-revision.json" \
          "$ABDA_RC_ROOT/wait-replicas.json" "$ABDA_RC_TARGET_REVISION"
        return 0
      }
    fi
    if (( attempt == 1 || attempt % 6 == 0 )); then
      printf 'Release-candidate revision state: %s (attempt %s/60)\n' \
        "${state:-waiting}" "$attempt"
    fi
    sleep 5
  done
  abda_rc_fail 'the release-candidate revision did not become healthy'
}

abda_rc_main() {
  set -Eeuo pipefail
  set +x
  umask 077
  unset HISTFILE
  trap abda_rc_error ERR
  trap abda_rc_cleanup EXIT
  trap abda_rc_interrupt INT
  ABDA_RC_SECTION='bootstrap'

  printf 'ABDA-NL Gate 6 release-candidate image script revision: %s\n' \
    "$ABDA_RC_SCRIPT_REVISION"
  printf '%s\n' \
    'This resume-safe gate updates only the existing web container image.' \
    'It does not rerun migrations or change secrets, Auth0, DNS, certificates,' \
    'trial limits, OpenRouter failover, scaling, probes, or database resources.'

  abda_rc_set_constants
  local command_name=''
  for command_name in az curl grep python3; do
    command -v "$command_name" >/dev/null 2>&1 || \
      abda_rc_fail "required command is unavailable: $command_name"
  done
  ABDA_RC_ROOT="$(mktemp -d /tmp/abda-nl-release-candidate.XXXXXX)"
  chmod 700 "$ABDA_RC_ROOT"
  az containerapp update --help >"$ABDA_RC_ROOT/containerapp-update.help"
  grep -Fq -- '--container-name' "$ABDA_RC_ROOT/containerapp-update.help"
  grep -Fq -- '--image' "$ABDA_RC_ROOT/containerapp-update.help"
  grep -Fq -- '--revision-suffix' "$ABDA_RC_ROOT/containerapp-update.help"
  az containerapp secret list --help >"$ABDA_RC_ROOT/containerapp-secret-list.help"
  grep -Fq -- '--show-values' "$ABDA_RC_ROOT/containerapp-secret-list.help"

  ABDA_RC_SECTION='Azure identity verification'
  printf '\n[1/8] Verifying the exact Azure identity...\n'
  az account show --output json >"$ABDA_RC_ROOT/account.json"
  abda_rc_validate_identity "$ABDA_RC_ROOT/account.json"
  az account show \
    --query '{Name:name,TenantId:tenantId,User:user.name,State:state}' \
    --output table

  ABDA_RC_SECTION='immutable image verification'
  printf '\n[2/8] Verifying anonymous access and provenance labels for the exact image...\n'
  ABDA_REGISTRY_TOKEN="$(curl --fail --silent --show-error --get \
    --data-urlencode 'scope=repository:liu-hy/abda-nl:pull' \
    --data-urlencode 'service=ghcr.io' 'https://ghcr.io/token' | \
    python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')"
  curl --fail --silent --show-error \
    --header "Authorization: Bearer $ABDA_REGISTRY_TOKEN" \
    --header 'Accept: application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json' \
    --dump-header "$ABDA_RC_ROOT/manifest.headers" \
    --output "$ABDA_RC_ROOT/manifest.json" \
    "https://ghcr.io/v2/liu-hy/abda-nl/manifests/sha256:$ABDA_RC_NEW_IMAGE_SHA256"
  local config_digest=''
  config_digest="$(python3 - "$ABDA_RC_ROOT/manifest.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(str((json.load(handle).get("config") or {}).get("digest") or ""))
PY
)"
  [[ "$config_digest" == sha256:* ]] || \
    abda_rc_fail 'the published image config digest is invalid'
  curl --location --fail --silent --show-error \
    --header "Authorization: Bearer $ABDA_REGISTRY_TOKEN" \
    --output "$ABDA_RC_ROOT/image-config.json" \
    "https://ghcr.io/v2/liu-hy/abda-nl/blobs/$config_digest"
  abda_rc_validate_registry_image \
    "$ABDA_RC_ROOT/manifest.headers" "$ABDA_RC_ROOT/manifest.json" \
    "$ABDA_RC_ROOT/image-config.json"
  unset ABDA_REGISTRY_TOKEN
  printf 'Verified image digest and source commit: %s\n' "$ABDA_RC_SOURCE_COMMIT"

  ABDA_RC_SECTION='current application state verification'
  printf '\n[3/8] Verifying the current healthy pilot and protected secret inventory...\n'
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_RC_ROOT/before-app.json"
  local phase=''
  phase="$(abda_rc_validate_app_phase "$ABDA_RC_ROOT/before-app.json")"
  if [[ "$phase" == 'old' ]]; then
    abda_rc_fetch_healthy_revision \
      "$ABDA_RC_OLD_REVISION" "$ABDA_RC_ROOT/before"
  elif [[ "$phase" == 'target' ]]; then
    abda_rc_fetch_healthy_revision \
      "$ABDA_RC_TARGET_REVISION" "$ABDA_RC_ROOT/before"
  fi
  az containerapp secret list \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --show-values --only-show-errors --output json \
    >"$ABDA_RC_ROOT/current-secrets.json"
  abda_rc_load_metrics_token "$ABDA_RC_ROOT/current-secrets.json"
  printf 'deployment_phase: %s\n' "$phase"
  printf 'Validated the protected application secret inventory.\n'

  ABDA_RC_SECTION='predeployment public acceptance'
  printf '\n[4/8] Verifying HTTPS, security headers, model profile, and both ledgers...\n'
  abda_rc_public_acceptance "$ABDA_RC_ROOT/before"

  if [[ "$phase" == 'old' ]]; then
    printf '\nThis mutation updates only %s from the current image to:\n' \
      "$ABDA_APP_NAME"
    printf '  %s@sha256:%s\n' \
      "$ABDA_IMAGE_REPOSITORY" "$ABDA_RC_NEW_IMAGE_SHA256"
    printf '%s\n' \
      'Azure single revision mode keeps the current healthy revision serving' \
      'until the replacement passes its startup and readiness probes.' \
      'Type DEPLOY_ABDA_RELEASE_CANDIDATE to continue, or press Enter to cancel.'
    local confirmation=''
    IFS= read -r -p 'Confirmation: ' confirmation
    if [[ "$confirmation" != 'DEPLOY_ABDA_RELEASE_CANDIDATE' ]]; then
      printf 'Cancelled without changing Azure.\n'
      return 0
    fi

    ABDA_RC_SECTION='image-only Container App update'
    printf '\n[5/8] Submitting the one image-only update...\n'
    az containerapp update \
      --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
      --container-name web \
      --image "$ABDA_IMAGE_REPOSITORY@sha256:$ABDA_RC_NEW_IMAGE_SHA256" \
      --revision-suffix "$ABDA_RC_TARGET_SUFFIX" \
      --only-show-errors --output none
  else
    printf '\n[5/8] The exact target image is already submitted. Resuming verification.\n'
  fi

  ABDA_RC_SECTION='healthy target revision verification'
  printf '\n[6/8] Waiting for the exact target revision to become healthy...\n'
  abda_rc_wait_for_target

  ABDA_RC_SECTION='postdeployment application contract verification'
  printf '\n[7/8] Rechecking the complete protected application contract...\n'
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_RC_ROOT/after-app.json"
  [[ "$(abda_rc_validate_app_phase "$ABDA_RC_ROOT/after-app.json")" == 'target' ]] || \
    abda_rc_fail 'the target application did not settle in the reviewed state'
  abda_rc_compare_opaque_settings \
    "$ABDA_RC_ROOT/before-app.json" "$ABDA_RC_ROOT/after-app.json"
  abda_rc_fetch_healthy_revision \
    "$ABDA_RC_TARGET_REVISION" "$ABDA_RC_ROOT/after"
  printf 'Verified the image, revision, ingress, domain, probes, scaling, environment, and secret references.\n'

  ABDA_RC_SECTION='postdeployment public acceptance'
  printf '\n[8/8] Rechecking HTTPS, security headers, model profile, and both ledgers...\n'
  abda_rc_public_acceptance "$ABDA_RC_ROOT/after"

  printf '\nABDA-NL Gate 6 release-candidate image status:\n'
  printf 'script_revision: %s\n' "$ABDA_RC_SCRIPT_REVISION"
  printf 'source_commit: %s\n' "$ABDA_RC_SOURCE_COMMIT"
  printf 'image_digest: sha256:%s\n' "$ABDA_RC_NEW_IMAGE_SHA256"
  printf 'subscription_id: %s\n' "$ABDA_EXPECTED_SUBSCRIPTION"
  printf 'resource_group: %s\n' "$ABDA_RESOURCE_GROUP"
  printf 'previous_revision: %s\n' "$ABDA_RC_OLD_REVISION"
  printf 'application_revision: %s\n' "$ABDA_RC_TARGET_REVISION"
  printf 'public_origin: %s\n' "$ABDA_CUSTOM_ORIGIN"
  printf 'trial_max_users: %s\n' "$ABDA_PILOT_MAX_USERS"
  printf 'trial_budget_microusd: %s\n' "$ABDA_PILOT_BUDGET_MICROUSD"
  printf 'openrouter_failover_enabled: false\n'
  printf 'migration_rerun: false\n'
  printf 'secrets_changed: false\n'
  printf 'public_acceptance: passed\n'
  printf 'result: RELEASE_CANDIDATE_IMAGE_DEPLOYED_BROWSER_AND_OUTAGE_DRILL_REQUIRED\n'
  printf '%s\n' \
    'Stop here. Test sign-in and sign-out in the browser.' \
    'Do not enable public OpenRouter failover yet.' \
    'Send this status and the shell exit code to Codex before the controlled outage drill.'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_rc_main "$@"
fi
