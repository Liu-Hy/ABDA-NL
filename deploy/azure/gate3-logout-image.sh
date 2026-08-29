#!/usr/bin/env bash

# Deploy the tested OIDC logout repair as one image-only Container App update.
# This gate does not read user-entered credentials or rerun the migration.

ABDA_LOGOUT_SCRIPT_REVISION='3'
ABDA_LOGOUT_SOURCE_COMMIT='9abd0264c715596401d87b83d08ed2e82ab5e34b'
ABDA_LOGOUT_BASE_GATE_SHA256='9edf0eeb385a60184e7ee53f243e34e410a5ccbb26f8a991edc097676fecf0fa'
ABDA_LOGOUT_WORKSPACE_SHA256='3382ba705376229eb63fc7bd1e74fa999beffdc2fef6510e6af67dbccd046804'
ABDA_LOGOUT_OLD_IMAGE_SHA256='c3f6ec80972850d30850ec2e72d28fd673e835187bebdc45a8f9cda4a8ad1a55'
ABDA_LOGOUT_NEW_IMAGE_SHA256='71f759c7bbfe25cc2ae974f006b8fed853ef87e5db260fc875fa3f50257739f9'
ABDA_LOGOUT_OLD_REVISION='abda-nl-stg-web--0000001'
ABDA_LOGOUT_TARGET_SUFFIX='logout-9abd026'
ABDA_LOGOUT_TARGET_REVISION='abda-nl-stg-web--logout-9abd026'
ABDA_LOGOUT_ROOT=''

abda_logout_cleanup() {
  local exit_code=$?
  set +e
  unset ABDA_DEPLOY_METRICS_TOKEN
  unset ABDA_REGISTRY_TOKEN
  if [[ "${ABDA_LOGOUT_ROOT:-}" == /tmp/abda-nl-logout-image.* &&
        -d "${ABDA_LOGOUT_ROOT:-}" ]]; then
    rm -rf -- "$ABDA_LOGOUT_ROOT"
  fi
  printf '\nLogout image gate shell exit code: %s\n' "$exit_code"
}

abda_logout_error() {
  local exit_code=$?
  trap - ERR
  printf '\nSTOP: logout image gate failed in section: %s\n' \
    "${ABDA_LOGOUT_SECTION:-unknown}" >&2
  printf '%s\n' \
    'Do not delete resources or rerun blindly.' \
    'Send the visible status and shell exit code to Codex.' >&2
  exit "$exit_code"
}

abda_logout_interrupt() {
  trap - ERR INT
  printf '\nSTOP: logout image gate was interrupted in section: %s\n' \
    "${ABDA_LOGOUT_SECTION:-unknown}" >&2
  exit 130
}

abda_logout_bootstrap_fail() {
  printf 'STOP: %s\n' "$*" >&2
  return 1
}

abda_logout_set_constants() {
  ABDA_EXPECTED_SUBSCRIPTION='00e62f6e-2174-40b2-b428-8ebfd7c2ac54'
  ABDA_EXPECTED_TENANT='040f05eb-33ab-462f-af54-fb4bedb055ae'
  ABDA_EXPECTED_USER='hliu2@cloudbank.org'
  ABDA_RESOURCE_GROUP='abda-nl-staging'
  ABDA_INFRA_DEPLOYMENT='abda-nl-stg-infra'
  ABDA_MIGRATION_DEPLOYMENT='abda-nl-stg-migration'
  ABDA_APP_DEPLOYMENT='abda-nl-stg-app'
  ABDA_ENVIRONMENT_NAME='abda-nl-stg-environment'
  ABDA_MIGRATION_JOB_NAME='abda-nl-stg-migrate'
  ABDA_APP_NAME='abda-nl-stg-web'
  ABDA_POSTGRES_HOST='abda-nl-stg-postgres-bgjhpbgw.postgres.database.azure.com'
  ABDA_GENERATED_HOSTNAME='abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io'
  ABDA_GENERATED_ORIGIN="https://$ABDA_GENERATED_HOSTNAME"
  ABDA_SOURCE_REPOSITORY='https://github.com/Liu-Hy/ABDA-NL.git'
  ABDA_SOURCE_COMMIT=$ABDA_LOGOUT_SOURCE_COMMIT
  ABDA_IMAGE_REPOSITORY='ghcr.io/liu-hy/abda-nl'
  ABDA_IMAGE_SHA256=$ABDA_LOGOUT_NEW_IMAGE_SHA256
  ABDA_OIDC_METADATA_URL='https://login.abda-nl.org/.well-known/openid-configuration'
  ABDA_OIDC_ISSUER='https://login.abda-nl.org/'
  ABDA_GATE_ROOT=$ABDA_LOGOUT_ROOT
}

abda_logout_validate_registry_image() {
  local headers_path=$1
  local manifest_path=$2
  local config_path=$3
  python3 - "$headers_path" "$manifest_path" "$config_path" \
    "$ABDA_LOGOUT_NEW_IMAGE_SHA256" "$ABDA_LOGOUT_SOURCE_COMMIT" <<'PY'
import json
import sys

headers_path, manifest_path, config_path, digest, commit = sys.argv[1:]
headers = open(headers_path, encoding="utf-8").read().lower()
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

abda_logout_validate_current_state() {
  local app_path=$1
  local revisions_path=$2
  local executions_path=$3
  python3 - "$app_path" "$revisions_path" "$executions_path" \
    "$ABDA_APP_NAME" "$ABDA_GENERATED_HOSTNAME" \
    "${ABDA_IMAGE_REPOSITORY}@sha256:${ABDA_LOGOUT_OLD_IMAGE_SHA256}" \
    "${ABDA_IMAGE_REPOSITORY}@sha256:${ABDA_LOGOUT_NEW_IMAGE_SHA256}" \
    "$ABDA_LOGOUT_OLD_REVISION" "$ABDA_LOGOUT_TARGET_REVISION" <<'PY'
import json
import sys

(
    app_path,
    revisions_path,
    executions_path,
    expected_app,
    expected_fqdn,
    old_image,
    target_image,
    old_revision,
    target_revision,
) = sys.argv[1:]


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


app = load(app_path)
revisions = load(revisions_path)
executions = load(executions_path)
properties = app.get("properties") or {}
configuration = properties.get("configuration") or {}
ingress = configuration.get("ingress") or {}
template = properties.get("template") or {}
containers = template.get("containers") or []
if app.get("name") != expected_app or len(containers) != 1:
    raise SystemExit("STOP: current Container App identity changed")
if str(configuration.get("activeRevisionsMode") or "").lower() != "single":
    raise SystemExit("STOP: current Container App is not in single revision mode")
if properties.get("provisioningState") != "Succeeded":
    raise SystemExit("STOP: current Container App provisioning is not settled")
if properties.get("runningStatus") != "Running":
    raise SystemExit("STOP: current Container App is not running")
if ingress.get("fqdn") != expected_fqdn:
    raise SystemExit("STOP: generated ingress hostname changed")
if ingress.get("external") is not True or ingress.get("allowInsecure") is not False:
    raise SystemExit("STOP: ingress safety settings changed")
if ingress.get("targetPort") != 8000:
    raise SystemExit("STOP: ingress target port changed")
if ingress.get("customDomains") or []:
    raise SystemExit("STOP: a custom domain already exists; do not run this gate")
traffic = ingress.get("traffic") or []
if len(traffic) != 1 or traffic[0].get("latestRevision") is not True or traffic[0].get("weight") != 100:
    raise SystemExit("STOP: ingress traffic policy changed")

container = containers[0]
if container.get("name") != "web":
    raise SystemExit("STOP: web container identity changed")
image = str(container.get("image") or "")
latest = str(properties.get("latestRevisionName") or "")
latest_ready = str(properties.get("latestReadyRevisionName") or "")
if image == old_image and latest == old_revision and latest_ready == old_revision:
    phase = "old"
    current_revision = old_revision
elif image == target_image and latest == target_revision and latest_ready in {
    old_revision,
    target_revision,
}:
    phase = "target"
    current_revision = target_revision
else:
    raise SystemExit(
        "STOP: current image and revision do not match the reviewed old or target state"
    )

resources = container.get("resources") or {}
if str(resources.get("cpu")) != "0.5" or resources.get("memory") != "1Gi":
    raise SystemExit("STOP: web container resources changed")
scale = template.get("scale") or {}
if scale.get("minReplicas") != 1 or scale.get("maxReplicas") != 3:
    raise SystemExit("STOP: web scaling boundary changed")
if template.get("terminationGracePeriodSeconds") != 30:
    raise SystemExit("STOP: termination grace period changed")

env = {str(item.get("name") or ""): item for item in container.get("env") or []}
expected_values = {
    "ABDA_ENVIRONMENT": "staging",
    "ABDA_ENABLE_LLM": "1",
    "ABDA_AUTH_MODE": "oidc",
    "ABDA_AUTO_CREATE_DB": "0",
    "ABDA_PUBLIC_BASE_URL": f"https://{expected_fqdn}",
    "ABDA_TRUSTED_HOSTS": expected_fqdn,
    "ABDA_COOKIE_SECURE": "1",
    "ABDA_LLM_ALLOW_BYOK": "1",
    "ABDA_LLM_REQUIRE_AUTH": "1",
    "ABDA_TRIAL_ENABLED": "false",
    "ABDA_TRIAL_BUDGET_MICROUSD": "500000000",
    "ABDA_OPENROUTER_FAILOVER_ENABLED": "false",
    "ABDA_OPENROUTER_BUDGET_MICROUSD": "500000000",
}
for name, expected in expected_values.items():
    if str(env.get(name, {}).get("value") or "").lower() != expected.lower():
        raise SystemExit(f"STOP: application setting {name} changed")
expected_secret_refs = {
    "ABDA_DATABASE_URL": "database-url",
    "ABDA_SESSION_SECRET": "session-secret",
    "ABDA_MCP_TOKEN_PEPPER": "mcp-token-pepper",
    "ABDA_METRICS_TOKEN": "metrics-token",
    "ABDA_OIDC_CLIENT_SECRET": "oidc-client-secret",
    "AZURE_OPENAI_API_KEY": "foundry-api-key",
    "OPENROUTER_API_KEY": "openrouter-api-key",
}
for name, expected in expected_secret_refs.items():
    if env.get(name, {}).get("secretRef") != expected:
        raise SystemExit(f"STOP: application secret reference {name} changed")
if any("ADMIN" in name.upper() for name in env):
    raise SystemExit("STOP: an administrator setting reached the web application")

expected_probe_paths = {
    "Startup": "/health/live",
    "Liveness": "/health/live",
    "Readiness": "/health/ready",
}
probes = container.get("probes") or []
if len(probes) != 3:
    raise SystemExit("STOP: health probe count changed")
for probe in probes:
    probe_type = str(probe.get("type") or "")
    request = probe.get("httpGet") or {}
    if expected_probe_paths.get(probe_type) != request.get("path"):
        raise SystemExit("STOP: health probe route changed")
    if request.get("port") != 8000 or request.get("scheme") != "HTTP":
        raise SystemExit("STOP: health probe transport changed")
    if request.get("httpHeaders") != [{"name": "Host", "value": expected_fqdn}]:
        raise SystemExit("STOP: health probe trusted Host header changed")

if not isinstance(revisions, list):
    raise SystemExit("STOP: Azure did not return a revision list")
matches = [item for item in revisions if item.get("name") == current_revision]
if len(matches) != 1:
    raise SystemExit("STOP: current revision is absent or ambiguous")
revision_properties = matches[0].get("properties") or {}
if phase == "old":
    if revision_properties.get("active") is not True:
        raise SystemExit("STOP: old revision is not active")
    if revision_properties.get("healthState") != "Healthy":
        raise SystemExit("STOP: old revision is not healthy")
    if revision_properties.get("provisioningState") != "Provisioned":
        raise SystemExit("STOP: old revision is not provisioned")

if not isinstance(executions, list):
    raise SystemExit("STOP: Azure did not return migration executions")
statuses = [str((item.get("properties") or item).get("status") or "") for item in executions]
if "Succeeded" not in statuses:
    raise SystemExit("STOP: no successful migration execution exists")
active_statuses = [status for status in statuses if status not in {"Succeeded", "Failed", "Stopped"}]
if active_statuses:
    raise SystemExit("STOP: a migration execution is still active")
print(phase)
PY
}

abda_logout_compare_configuration() {
  local before_path=$1
  local after_path=$2
  python3 - "$before_path" "$after_path" <<'PY'
import copy
import json
import sys


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def canonical(value):
    if isinstance(value, dict):
        return {key: canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        items = [canonical(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
    return value


def snapshot(app):
    properties = app.get("properties") or {}
    template = copy.deepcopy(properties.get("template") or {})
    template.pop("revisionSuffix", None)
    for container in template.get("containers") or []:
        container.pop("image", None)
    return canonical(
        {
            "name": app.get("name"),
            "location": app.get("location"),
            "environmentId": properties.get("environmentId"),
            "workloadProfileName": properties.get("workloadProfileName"),
            "configuration": properties.get("configuration") or {},
            "templateWithoutImage": template,
        }
    )


before = snapshot(load(sys.argv[1]))
after = snapshot(load(sys.argv[2]))
if before != after:
    raise SystemExit("STOP: Container App configuration changed beyond image and revision suffix")
PY
}

abda_logout_wait_for_target() {
  local attempt=0
  local state=''
  local state_code=0
  local previous_state=''

  for attempt in $(seq 1 120); do
    if az containerapp show \
      --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
      --output json >"$ABDA_LOGOUT_ROOT/target-app.json" 2>/dev/null &&
      az containerapp revision show \
        --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
        --revision "$ABDA_LOGOUT_TARGET_REVISION" --output json \
        >"$ABDA_LOGOUT_ROOT/target-revision.json" 2>/dev/null &&
      az containerapp replica list \
        --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
        --revision "$ABDA_LOGOUT_TARGET_REVISION" --output json \
        >"$ABDA_LOGOUT_ROOT/target-replicas.json" 2>/dev/null; then
      if state="$(python3 - \
        "$ABDA_LOGOUT_ROOT/target-app.json" \
        "$ABDA_LOGOUT_ROOT/target-revision.json" \
        "$ABDA_LOGOUT_ROOT/target-replicas.json" \
        "$ABDA_LOGOUT_TARGET_REVISION" \
        "${ABDA_IMAGE_REPOSITORY}@sha256:${ABDA_LOGOUT_NEW_IMAGE_SHA256}" <<'PY'
import json
import sys

paths = sys.argv[1:4]
expected_revision, expected_image = sys.argv[4:]
values = []
for path in paths:
    with open(path, encoding="utf-8") as handle:
        values.append(json.load(handle))
app, revision, replicas = values
properties = app.get("properties") or {}
containers = (properties.get("template") or {}).get("containers") or []
revision_properties = revision.get("properties") or {}
image = str(containers[0].get("image") or "") if len(containers) == 1 else ""
running = 0
ready = 0
for replica in replicas if isinstance(replicas, list) else []:
    replica_properties = replica.get("properties") or {}
    if replica_properties.get("runningState") == "Running":
        running += 1
    if any(item.get("ready") is True for item in replica_properties.get("containers") or []):
        ready += 1
fields = (
    properties.get("provisioningState"),
    properties.get("runningStatus"),
    properties.get("latestRevisionName"),
    properties.get("latestReadyRevisionName"),
    revision_properties.get("provisioningState"),
    revision_properties.get("healthState"),
    revision_properties.get("active"),
    len(replicas) if isinstance(replicas, list) else 0,
    running,
    ready,
)
print("|".join(str(value if value is not None else "") for value in fields))
if properties.get("provisioningState") == "Failed" or revision_properties.get("provisioningState") == "Failed":
    raise SystemExit(2)
is_ready = (
    image == expected_image
    and properties.get("provisioningState") == "Succeeded"
    and properties.get("runningStatus") == "Running"
    and properties.get("latestRevisionName") == expected_revision
    and properties.get("latestReadyRevisionName") == expected_revision
    and revision.get("name") == expected_revision
    and revision_properties.get("provisioningState") == "Provisioned"
    and revision_properties.get("healthState") == "Healthy"
    and revision_properties.get("active") is True
    and isinstance(replicas, list)
    and 1 <= len(replicas) <= 3
    and running == len(replicas)
    and ready == len(replicas)
)
raise SystemExit(0 if is_ready else 1)
PY
)"; then
        state_code=0
      else
        # A status of 1 means Azure is still converging. Keeping the command
        # in an explicit conditional prevents the ERR trap from treating this
        # expected transition as a script failure.
        state_code=$?
      fi
      if [[ "$state" != "$previous_state" ]]; then
        printf 'Target application state: %s\n' "$state"
        previous_state=$state
      fi
      if (( state_code == 0 )); then
        return 0
      fi
      if (( state_code == 2 )); then
        abda_fail 'the target revision entered a failed provisioning state'
      fi
    fi
    sleep 5
  done
  abda_fail 'the target revision did not become healthy within ten minutes'
}

abda_logout_load_metrics_token() {
  local secrets_path=$1
  ABDA_DEPLOY_METRICS_TOKEN="$(python3 - "$secrets_path" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    values = json.load(handle)
if not isinstance(values, list):
    raise SystemExit("STOP: Azure did not return an application secret list")
secrets = {str(item.get("name") or ""): str(item.get("value") or "") for item in values}
expected = {
    "database-url",
    "session-secret",
    "mcp-token-pepper",
    "metrics-token",
    "oidc-client-secret",
    "foundry-api-key",
    "openrouter-api-key",
}
if set(secrets) != expected or any(not value for value in secrets.values()):
    raise SystemExit("STOP: protected application secret inventory changed")
token = secrets["metrics-token"]
if len(token) < 32 or token != token.strip() or any(char in token for char in "\r\n\0"):
    raise SystemExit("STOP: protected metrics token format changed")
print(token, end="")
PY
)"
  export ABDA_DEPLOY_METRICS_TOKEN
}

abda_logout_validate_deployed_contract() {
  local root=$1
  local origin=$ABDA_GENERATED_ORIGIN
  local login_status=''
  local logout_status=''

  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$origin/workspace.js" --output "$root/workspace.js"
  [[ "$(sha256sum "$root/workspace.js" | awk '{print $1}')" == \
      "$ABDA_LOGOUT_WORKSPACE_SHA256" ]] ||
    abda_fail 'the deployed browser workspace does not contain the tested logout repair'

  login_status="$(curl --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    --dump-header "$root/login.headers" --output "$root/login.body" \
    --write-out '%{http_code}' "$origin/auth/login")"
  [[ "$login_status" =~ ^30[2378]$ ]] ||
    abda_fail "OIDC login returned HTTP $login_status instead of a redirect"

  logout_status="$(curl --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 --request POST \
    --header "Origin: $origin" \
    --header "Referer: $origin/" \
    --header 'Sec-Fetch-Site: same-origin' \
    --header 'Accept: application/json' \
    --dump-header "$root/logout.headers" --output "$root/logout.json" \
    --write-out '%{http_code}' "$origin/api/auth/logout")"
  [[ "$logout_status" == '200' ]] ||
    abda_fail "same-origin logout API returned HTTP $logout_status instead of 200"

  python3 - "$root/login.headers" "$root/logout.json" "$origin" <<'PY'
import json
import sys
from urllib.parse import parse_qs, urlsplit

headers_path, logout_path, origin = sys.argv[1:]
locations = []
with open(headers_path, encoding="utf-8") as handle:
    for line in handle:
        if line.lower().startswith("location:"):
            locations.append(line.split(":", 1)[1].strip())
if len(locations) != 1:
    raise SystemExit("STOP: OIDC login returned an ambiguous redirect")
login = urlsplit(locations[0])
login_query = parse_qs(login.query)
if login.scheme != "https" or login.hostname != "login.abda-nl.org":
    raise SystemExit("STOP: OIDC login redirect host changed")
if login_query.get("redirect_uri") != [f"{origin}/auth/callback"]:
    raise SystemExit("STOP: OIDC login callback changed")
if login_query.get("response_type") != ["code"]:
    raise SystemExit("STOP: OIDC login response type changed")
if login_query.get("code_challenge_method") != ["S256"]:
    raise SystemExit("STOP: OIDC login PKCE mode changed")
for name in ("state", "nonce", "code_challenge"):
    if len(login_query.get(name) or []) != 1 or not login_query[name][0]:
        raise SystemExit(f"STOP: OIDC login parameter {name} is missing")

with open(logout_path, encoding="utf-8") as handle:
    logout_payload = json.load(handle)
logout = urlsplit(str(logout_payload.get("logout_url") or ""))
logout_query = parse_qs(logout.query)
if logout.scheme != "https" or logout.hostname != "login.abda-nl.org":
    raise SystemExit("STOP: logout API returned an unexpected identity-provider host")
if logout_query.get("post_logout_redirect_uri") != [f"{origin}/"]:
    raise SystemExit("STOP: logout API returned an unexpected return URL")
if len(logout_query.get("client_id") or []) != 1 or not logout_query["client_id"][0]:
    raise SystemExit("STOP: logout API omitted the Auth0 client ID")
PY
}

abda_logout_main() {
  set -Eeuo pipefail
  set +x
  umask 077
  unset HISTFILE
  trap abda_logout_error ERR
  trap abda_logout_cleanup EXIT
  trap abda_logout_interrupt INT
  ABDA_LOGOUT_SECTION='bootstrap'

  printf 'ABDA-NL Gate 3 logout image script revision: %s\n' \
    "$ABDA_LOGOUT_SCRIPT_REVISION"
  printf '%s\n' \
    'This resume-safe gate updates only the web container image.' \
    'It does not rerun migrations, change secrets, Auth0, DNS, trial credit,' \
    'OpenRouter failover, scaling, probes, or database resources.'

  abda_logout_set_constants
  local command_name=''
  for command_name in az awk curl git grep python3 sha256sum; do
    command -v "$command_name" >/dev/null 2>&1 ||
      abda_logout_bootstrap_fail "required command is unavailable: $command_name"
  done

  ABDA_LOGOUT_ROOT="$(mktemp -d /tmp/abda-nl-logout-image.XXXXXX)"
  chmod 700 "$ABDA_LOGOUT_ROOT"

  # Read each help page completely before searching it. Piping the Azure CLI
  # directly into `grep -q` can close stdout early and make Azure CLI fail with
  # BrokenPipeError when pipefail is enabled.
  az containerapp update --help >"$ABDA_LOGOUT_ROOT/containerapp-update.help"
  grep -Fq -- '--revision-suffix' \
    "$ABDA_LOGOUT_ROOT/containerapp-update.help"
  az containerapp secret list --help \
    >"$ABDA_LOGOUT_ROOT/containerapp-secret-list.help"
  grep -Fq -- '--show-values' \
    "$ABDA_LOGOUT_ROOT/containerapp-secret-list.help"

  ABDA_LOGOUT_SECTION='immutable source verification'
  printf '\n[1/8] Verifying the immutable repair source...\n'
  git clone --quiet --filter=blob:none --no-checkout \
    "$ABDA_SOURCE_REPOSITORY" "$ABDA_LOGOUT_ROOT/source"
  git -C "$ABDA_LOGOUT_ROOT/source" checkout --quiet --detach \
    "$ABDA_LOGOUT_SOURCE_COMMIT"
  [[ "$(git -C "$ABDA_LOGOUT_ROOT/source" rev-parse HEAD)" == \
      "$ABDA_LOGOUT_SOURCE_COMMIT" ]] ||
    abda_logout_bootstrap_fail 'the checked-out source commit changed'
  (
    cd "$ABDA_LOGOUT_ROOT/source"
    sha256sum --check --quiet <<ABDA_LOGOUT_CHECKSUMS
$ABDA_LOGOUT_BASE_GATE_SHA256  deploy/azure/gate3-staging-application.sh
$ABDA_LOGOUT_WORKSPACE_SHA256  app/static/workspace.js
ABDA_LOGOUT_CHECKSUMS
  )

  # The checksum-pinned Gate 3 file provides the established identity,
  # infrastructure, OIDC, application, and HTTPS acceptance helpers.
  # shellcheck disable=SC1091
  source "$ABDA_LOGOUT_ROOT/source/deploy/azure/gate3-staging-application.sh"
  abda_logout_set_constants
  printf 'Verified logout repair source commit: %s\n' \
    "$ABDA_LOGOUT_SOURCE_COMMIT"

  ABDA_LOGOUT_SECTION='Azure identity and infrastructure verification'
  printf '\n[2/8] Verifying Azure identity and settled infrastructure...\n'
  az account show --output json >"$ABDA_LOGOUT_ROOT/account.json"
  abda_validate_identity "$ABDA_LOGOUT_ROOT/account.json"
  az account show \
    --query '{Name:name,TenantId:tenantId,User:user.name,State:state}' \
    --output table
  local deployment_name=''
  local deployment_state=''
  for deployment_name in \
    "$ABDA_INFRA_DEPLOYMENT" "$ABDA_MIGRATION_DEPLOYMENT" "$ABDA_APP_DEPLOYMENT"; do
    deployment_state="$(az deployment group show \
      --name "$deployment_name" --resource-group "$ABDA_RESOURCE_GROUP" \
      --query properties.provisioningState --output tsv)"
    [[ "$deployment_state" == 'Succeeded' ]] ||
      abda_fail "deployment $deployment_name is $deployment_state"
  done
  az deployment group show \
    --name "$ABDA_INFRA_DEPLOYMENT" --resource-group "$ABDA_RESOURCE_GROUP" \
    --query properties.outputs --output json \
    >"$ABDA_LOGOUT_ROOT/infra-outputs.json"
  az containerapp env show \
    --name "$ABDA_ENVIRONMENT_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_LOGOUT_ROOT/environment.json"
  az postgres flexible-server show \
    --name "${ABDA_POSTGRES_HOST%%.*}" --resource-group "$ABDA_RESOURCE_GROUP" \
    --query '{name:name,state:state,fullyQualifiedDomainName:fullyQualifiedDomainName,publicNetworkAccess:network.publicNetworkAccess}' \
    --output json >"$ABDA_LOGOUT_ROOT/postgres.json"
  az containerapp job list --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_LOGOUT_ROOT/jobs.json"
  az containerapp list --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_LOGOUT_ROOT/apps.json"
  abda_validate_infrastructure \
    "$ABDA_LOGOUT_ROOT/infra-outputs.json" \
    "$ABDA_LOGOUT_ROOT/environment.json" \
    "$ABDA_LOGOUT_ROOT/postgres.json" \
    "$ABDA_LOGOUT_ROOT/jobs.json" "$ABDA_LOGOUT_ROOT/apps.json"

  ABDA_LOGOUT_SECTION='public image and identity-provider verification'
  printf '\n[3/8] Verifying the published image and Auth0 discovery...\n'
  ABDA_REGISTRY_TOKEN="$(curl --fail --silent --show-error --get \
    --data-urlencode 'scope=repository:liu-hy/abda-nl:pull' \
    'https://ghcr.io/token' | python3 -c \
    'import json,sys; print(json.load(sys.stdin)["token"])')"
  curl --fail --silent --show-error \
    --header "Authorization: Bearer $ABDA_REGISTRY_TOKEN" \
    --header 'Accept: application/vnd.oci.image.manifest.v1+json' \
    --dump-header "$ABDA_LOGOUT_ROOT/manifest.headers" \
    --output "$ABDA_LOGOUT_ROOT/manifest.json" \
    "https://ghcr.io/v2/liu-hy/abda-nl/manifests/sha256:$ABDA_LOGOUT_NEW_IMAGE_SHA256"
  local config_digest=''
  config_digest="$(python3 - "$ABDA_LOGOUT_ROOT/manifest.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(str((json.load(handle).get("config") or {}).get("digest") or ""))
PY
)"
  [[ "$config_digest" == sha256:* ]] ||
    abda_fail 'the published image config digest is invalid'
  curl --location --fail --silent --show-error \
    --header "Authorization: Bearer $ABDA_REGISTRY_TOKEN" \
    --output "$ABDA_LOGOUT_ROOT/image-config.json" \
    "https://ghcr.io/v2/liu-hy/abda-nl/blobs/$config_digest"
  abda_logout_validate_registry_image \
    "$ABDA_LOGOUT_ROOT/manifest.headers" \
    "$ABDA_LOGOUT_ROOT/manifest.json" \
    "$ABDA_LOGOUT_ROOT/image-config.json"
  unset ABDA_REGISTRY_TOKEN
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_OIDC_METADATA_URL" --output "$ABDA_LOGOUT_ROOT/oidc.json"
  abda_validate_oidc_discovery "$ABDA_LOGOUT_ROOT/oidc.json"
  printf 'Verified image digest, source label, and Auth0 issuer.\n'

  ABDA_LOGOUT_SECTION='current application state verification'
  printf '\n[4/8] Verifying the exact current or safely resumed state...\n'
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_LOGOUT_ROOT/before-app.json"
  az containerapp revision list \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_LOGOUT_ROOT/revisions.json"
  az containerapp job execution list \
    --name "$ABDA_MIGRATION_JOB_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_LOGOUT_ROOT/executions.json"
  local phase=''
  phase="$(abda_logout_validate_current_state \
    "$ABDA_LOGOUT_ROOT/before-app.json" \
    "$ABDA_LOGOUT_ROOT/revisions.json" \
    "$ABDA_LOGOUT_ROOT/executions.json")"
  printf 'deployment_phase: %s\n' "$phase"

  if [[ "$phase" == 'old' ]]; then
    printf '\nThis mutation updates only %s from the verified old image to:\n' \
      "$ABDA_APP_NAME"
    printf '  %s@sha256:%s\n' \
      "$ABDA_IMAGE_REPOSITORY" "$ABDA_LOGOUT_NEW_IMAGE_SHA256"
    printf '%s\n' \
      'Azure single revision mode keeps the current healthy revision serving' \
      'until the new revision passes its startup and readiness probes.' \
      'Type DEPLOY_ABDA_LOGOUT_FIX to continue, or press Enter to cancel.'
    local confirmation=''
    IFS= read -r -p 'Confirmation: ' confirmation
    if [[ "$confirmation" != 'DEPLOY_ABDA_LOGOUT_FIX' ]]; then
      printf 'Cancelled without changing Azure.\n'
      return 0
    fi

    ABDA_LOGOUT_SECTION='image-only Container App update'
    printf '\n[5/8] Submitting the one image-only update...\n'
    az containerapp update \
      --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
      --container-name web \
      --image "$ABDA_IMAGE_REPOSITORY@sha256:$ABDA_LOGOUT_NEW_IMAGE_SHA256" \
      --revision-suffix "$ABDA_LOGOUT_TARGET_SUFFIX" \
      --only-show-errors --output none
  else
    printf '\n[5/8] The exact target image is already submitted. Resuming verification.\n'
  fi

  ABDA_LOGOUT_SECTION='healthy target revision verification'
  printf '\n[6/8] Waiting for the exact target revision to become healthy...\n'
  abda_logout_wait_for_target
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_LOGOUT_ROOT/after-app.json"
  abda_logout_compare_configuration \
    "$ABDA_LOGOUT_ROOT/before-app.json" "$ABDA_LOGOUT_ROOT/after-app.json"
  abda_validate_application "$ABDA_LOGOUT_ROOT/after-app.json"
  printf 'Verified that only the image and revision suffix changed.\n'

  ABDA_LOGOUT_SECTION='protected acceptance credential loading'
  printf '\n[7/8] Loading the existing metrics token from Azure without displaying it...\n'
  az containerapp secret list \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --show-values --output json >"$ABDA_LOGOUT_ROOT/current-secrets.json"
  abda_logout_load_metrics_token "$ABDA_LOGOUT_ROOT/current-secrets.json"
  printf 'Validated the protected application secret inventory.\n'

  ABDA_LOGOUT_SECTION='generated-origin acceptance'
  printf '\n[8/8] Running complete HTTPS and logout-contract acceptance...\n'
  mkdir -p "$ABDA_LOGOUT_ROOT/acceptance"
  abda_smoke_generated_origin "$ABDA_LOGOUT_ROOT/acceptance"
  abda_logout_validate_deployed_contract "$ABDA_LOGOUT_ROOT/acceptance"

  printf '\nABDA-NL Gate 3 logout image status:\n'
  printf 'script_revision: %s\n' "$ABDA_LOGOUT_SCRIPT_REVISION"
  printf 'source_commit: %s\n' "$ABDA_LOGOUT_SOURCE_COMMIT"
  printf 'image_digest: sha256:%s\n' "$ABDA_LOGOUT_NEW_IMAGE_SHA256"
  printf 'subscription_id: %s\n' "$ABDA_EXPECTED_SUBSCRIPTION"
  printf 'resource_group: %s\n' "$ABDA_RESOURCE_GROUP"
  printf 'previous_revision: %s\n' "$ABDA_LOGOUT_OLD_REVISION"
  printf 'application_revision: %s\n' "$ABDA_LOGOUT_TARGET_REVISION"
  printf 'application_origin: %s\n' "$ABDA_GENERATED_ORIGIN"
  printf 'migration_rerun: false\n'
  printf 'secrets_changed: false\n'
  printf 'trial_activation_enabled: false\n'
  printf 'openrouter_failover_enabled: false\n'
  printf 'generated_origin_acceptance: passed\n'
  printf 'logout_contract_acceptance: passed\n'
  printf 'result: LOGOUT_FIX_DEPLOYED_BROWSER_RETEST_REQUIRED\n'
  printf '%s\n' \
    'Stop here. Sign in once in the browser, click Sign out, and report the result.'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_logout_main "$@"
fi
