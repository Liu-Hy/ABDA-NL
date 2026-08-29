#!/usr/bin/env bash

# Repair the first staging Container App revision after Azure health probes
# exposed a strict Host header mismatch. This gate never reruns the migration.

ABDA_REPAIR_SCRIPT_REVISION='1'
ABDA_REPAIR_SOURCE_COMMIT='ef91e88226abf9f916f976d9e668ad3536f1fe46'
ABDA_REPAIR_BASE_GATE_SHA256='05536276ebfe23731677611792a26b2fac90e9a57d935b673e339022f3a6a64e'
ABDA_REPAIR_APP_BICEP_SHA256='c18cccafb53e13f9366f6b77fb472b330f8cade0861d3ab07e5dea0141ced6f2'
ABDA_REPAIR_APP_PARAMETERS_SHA256='5c04b1e73346c0eec704fecfc82ad155423c5ca8859fc274afbebb6c209f801a'
ABDA_REPAIR_EXPECTED_REVISION='abda-nl-stg-web--ztv7ycn'
ABDA_REPAIR_ROOT=''

abda_repair_cleanup() {
  local exit_code=$?
  set +e
  unset ABDA_DEPLOY_POSTGRES_APP_PASSWORD
  unset ABDA_DEPLOY_SESSION_SECRET
  unset ABDA_DEPLOY_MCP_TOKEN_PEPPER
  unset ABDA_DEPLOY_METRICS_TOKEN
  unset ABDA_DEPLOY_OIDC_CLIENT_SECRET
  unset ABDA_DEPLOY_FOUNDRY_API_KEY
  unset ABDA_DEPLOY_OPENROUTER_API_KEY
  unset ABDA_REGISTRY_TOKEN
  if [[ "${ABDA_REPAIR_ROOT:-}" == /tmp/abda-nl-probe-repair.* &&
        -d "${ABDA_REPAIR_ROOT:-}" ]]; then
    rm -rf -- "$ABDA_REPAIR_ROOT"
  fi
  printf '\nProbe repair shell exit code: %s\n' "$exit_code"
}

abda_repair_error() {
  local exit_code=$?
  trap - ERR
  printf '\nSTOP: probe repair failed in section: %s\n' \
    "${ABDA_REPAIR_SECTION:-unknown}" >&2
  printf 'Do not rerun or change Azure resources. Send the visible output to Codex.\n' >&2
  exit "$exit_code"
}

abda_repair_interrupt() {
  trap - ERR INT
  printf '\nSTOP: probe repair interrupted in section: %s\n' \
    "${ABDA_REPAIR_SECTION:-unknown}" >&2
  exit 130
}

abda_repair_bootstrap_fail() {
  printf 'STOP: %s\n' "$*" >&2
  return 1
}

abda_repair_set_constants() {
  ABDA_EXPECTED_SUBSCRIPTION='00e62f6e-2174-40b2-b428-8ebfd7c2ac54'
  ABDA_EXPECTED_TENANT='040f05eb-33ab-462f-af54-fb4bedb055ae'
  ABDA_EXPECTED_USER='hliu2@cloudbank.org'
  ABDA_RESOURCE_GROUP='abda-nl-staging'
  ABDA_LOCATION='eastus2'
  ABDA_INFRA_DEPLOYMENT='abda-nl-stg-infra'
  ABDA_MIGRATION_DEPLOYMENT='abda-nl-stg-migration'
  ABDA_APP_DEPLOYMENT='abda-nl-stg-app'
  ABDA_ENVIRONMENT_NAME='abda-nl-stg-environment'
  ABDA_MIGRATION_JOB_NAME='abda-nl-stg-migrate'
  ABDA_APP_NAME='abda-nl-stg-web'
  ABDA_POSTGRES_HOST='abda-nl-stg-postgres-bgjhpbgw.postgres.database.azure.com'
  ABDA_GENERATED_ORIGIN='https://abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io'
  ABDA_SOURCE_REPOSITORY='https://github.com/Liu-Hy/ABDA-NL.git'
  ABDA_SOURCE_COMMIT=$ABDA_REPAIR_SOURCE_COMMIT
  ABDA_IMAGE_REPOSITORY='ghcr.io/liu-hy/abda-nl'
  ABDA_IMAGE_SHA256='c3f6ec80972850d30850ec2e72d28fd673e835187bebdc45a8f9cda4a8ad1a55'
  ABDA_BICEP_VERSION='v0.46.1'
  ABDA_OIDC_METADATA_URL='https://login.abda-nl.org/.well-known/openid-configuration'
  ABDA_OIDC_ISSUER='https://login.abda-nl.org/'
  ABDA_OPENROUTER_BUDGET_MICROUSD='500000000'
  ABDA_GATE_ROOT=$ABDA_REPAIR_ROOT
}

abda_validate_repair_what_if() {
  local result_path=$1
  local allowed_resource_id=$2
  python3 - "$result_path" "$allowed_resource_id" <<'PY'
import json
import sys

path, allowed_id = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    document = json.load(handle)
payload = document.get("properties", document)
if payload.get("status") not in (None, "Succeeded"):
    raise SystemExit("STOP: application what-if did not succeed")
changes = payload.get("changes")
if not isinstance(changes, list):
    raise SystemExit("STOP: application what-if did not return changes")

allowed = allowed_id.lower()
mutations = []
errors = []
known = {"Create", "Delete", "Deploy", "Ignore", "Modify", "NoChange", "Unsupported"}
for change in changes:
    if not isinstance(change, dict):
        errors.append("malformed change entry")
        continue
    change_type = str(change.get("changeType", ""))
    resource_id = str(
        change.get("resourceId")
        or (change.get("after") or {}).get("id")
        or (change.get("before") or {}).get("id")
        or ""
    )
    if change_type not in known:
        errors.append(f"unknown change type {change_type!r} for {resource_id!r}")
    elif change_type in {"Create", "Delete", "Unsupported"}:
        errors.append(f"unexpected {change_type} {resource_id}")
    elif change_type in {"Deploy", "Modify"}:
        mutations.append((change_type, resource_id))
        if resource_id.lower() != allowed:
            errors.append(f"unexpected {change_type} target {resource_id}")

print("Probe repair planned Azure changes:")
for change_type, resource_id in mutations:
    print(f"  {change_type:<7} {resource_id}")
if not mutations:
    errors.append("no Container App mutation was reported")
if len(mutations) != 1:
    errors.append(f"expected one mutation, received {len(mutations)}")
if errors:
    for error in errors:
        print(f"STOP: {error}", file=sys.stderr)
    raise SystemExit(1)
PY
}

abda_validate_repair_starting_state() {
  local app_path=$1
  local revision_path=$2
  local replicas_path=$3
  local executions_path=$4
  local expected_image="${ABDA_IMAGE_REPOSITORY}@sha256:${ABDA_IMAGE_SHA256}"
  python3 - "$app_path" "$revision_path" "$replicas_path" \
    "$executions_path" "$ABDA_APP_NAME" "$ABDA_REPAIR_EXPECTED_REVISION" \
    "$expected_image" "${ABDA_GENERATED_ORIGIN#https://}" <<'PY'
import json
import sys

(
    app_path,
    revision_path,
    replicas_path,
    executions_path,
    expected_app,
    expected_revision,
    expected_image,
    expected_fqdn,
) = sys.argv[1:]


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


app = load(app_path)
revision = load(revision_path)
replicas = load(replicas_path)
executions = load(executions_path)
properties = app.get("properties") or {}
configuration = properties.get("configuration") or {}
ingress = configuration.get("ingress") or {}
containers = (properties.get("template") or {}).get("containers") or []
if app.get("name") != expected_app or len(containers) != 1:
    raise SystemExit("STOP: current Container App identity changed")
container = containers[0]
if container.get("image") != expected_image:
    raise SystemExit("STOP: current Container App image changed")
if properties.get("latestRevisionName") != expected_revision:
    raise SystemExit("STOP: current Container App revision changed")
if ingress.get("fqdn") != expected_fqdn:
    raise SystemExit("STOP: current Container App hostname changed")
if ingress.get("external") is not True or ingress.get("allowInsecure") is not False:
    raise SystemExit("STOP: current ingress boundary changed")
if ingress.get("targetPort") != 8000:
    raise SystemExit("STOP: current ingress port changed")

env = {entry.get("name"): entry for entry in container.get("env") or []}
for name, expected in {
    "ABDA_ENVIRONMENT": "staging",
    "ABDA_AUTH_MODE": "oidc",
    "ABDA_AUTO_CREATE_DB": "0",
    "ABDA_PUBLIC_BASE_URL": f"https://{expected_fqdn}",
    "ABDA_TRIAL_ENABLED": "false",
    "ABDA_OPENROUTER_FAILOVER_ENABLED": "false",
}.items():
    if str(env.get(name, {}).get("value", "")).lower() != expected.lower():
        raise SystemExit(f"STOP: current application setting {name} changed")
if env.get("ABDA_DATABASE_URL", {}).get("secretRef") != "database-url":
    raise SystemExit("STOP: current restricted database credential changed")
if any("ADMIN" in str(name) for name in env):
    raise SystemExit("STOP: an administrator setting reached the web application")

expected_probes = {
    "Startup": ("/health/live", 8000),
    "Liveness": ("/health/live", 8000),
    "Readiness": ("/health/ready", 8000),
}
probes = container.get("probes") or []
if len(probes) != 3:
    raise SystemExit("STOP: current health-probe count changed")
for probe in probes:
    probe_type = probe.get("type")
    request = probe.get("httpGet") or {}
    if expected_probes.get(probe_type) != (request.get("path"), request.get("port")):
        raise SystemExit(f"STOP: current {probe_type!r} probe changed")
    headers = request.get("httpHeaders") or []
    if any(str(item.get("name", "")).lower() == "host" for item in headers):
        raise SystemExit("STOP: probe Host repair already exists; do not redeploy")

revision_properties = revision.get("properties") or {}
if revision.get("name") != expected_revision:
    raise SystemExit("STOP: inspected revision identity changed")
if revision_properties.get("healthState") not in {"Unhealthy", "Degraded"}:
    raise SystemExit("STOP: diagnosed revision is no longer unhealthy")
if revision_properties.get("provisioningState") != "Provisioned":
    raise SystemExit("STOP: diagnosed revision provisioning state changed")

if not isinstance(replicas, list) or not replicas:
    raise SystemExit("STOP: diagnosed revision has no observable replica")
ready = []
for replica in replicas:
    replica_properties = replica.get("properties") or {}
    for replica_container in replica_properties.get("containers") or []:
        ready.append(replica_container.get("ready") is True)
if any(ready):
    raise SystemExit("STOP: diagnosed revision unexpectedly has a ready container")

if not isinstance(executions, list):
    raise SystemExit("STOP: migration executions were not returned")
statuses = [str((item.get("properties") or item).get("status") or "") for item in executions]
if "Succeeded" not in statuses:
    raise SystemExit("STOP: no successful migration execution exists")
active = [status for status in statuses if status not in {"Succeeded", "Failed", "Stopped"}]
if active:
    raise SystemExit(f"STOP: migration execution is still active: {active!r}")
PY
}

abda_validate_repaired_probes() {
  local app_path=$1
  local expected_fqdn="${ABDA_GENERATED_ORIGIN#https://}"
  python3 - "$app_path" "$expected_fqdn" <<'PY'
import json
import sys

path, expected_fqdn = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    app = json.load(handle)
containers = ((app.get("properties") or {}).get("template") or {}).get("containers") or []
if len(containers) != 1:
    raise SystemExit("STOP: repaired application container count changed")
expected = {
    "Startup": ("/health/live", 8000),
    "Liveness": ("/health/live", 8000),
    "Readiness": ("/health/ready", 8000),
}
probes = containers[0].get("probes") or []
if len(probes) != 3:
    raise SystemExit("STOP: repaired health-probe count is not three")
for probe in probes:
    probe_type = probe.get("type")
    request = probe.get("httpGet") or {}
    if expected.get(probe_type) != (request.get("path"), request.get("port")):
        raise SystemExit(f"STOP: repaired {probe_type!r} probe changed")
    headers = request.get("httpHeaders") or []
    normalized = {
        str(item.get("name", "")).lower(): str(item.get("value", ""))
        for item in headers
    }
    if normalized != {"host": expected_fqdn}:
        raise SystemExit(f"STOP: repaired {probe_type} Host header changed")
PY
}

abda_repair_wait_for_healthy_revision() {
  local previous_revision=$1
  local latest_revision=''
  local last_status=''
  local status=''
  local healthy=0

  for _ in $(seq 1 120); do
    if az containerapp show \
      --name "$ABDA_APP_NAME" \
      --resource-group "$ABDA_RESOURCE_GROUP" \
      --output json >"$ABDA_REPAIR_ROOT/repaired-app.json"; then
      latest_revision="$(python3 - "$ABDA_REPAIR_ROOT/repaired-app.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle)
print((value.get("properties") or {}).get("latestRevisionName") or "")
PY
)"
      if [[ -n "$latest_revision" && "$latest_revision" != "$previous_revision" ]] &&
        az containerapp revision show \
          --name "$ABDA_APP_NAME" \
          --resource-group "$ABDA_RESOURCE_GROUP" \
          --revision "$latest_revision" \
          --output json >"$ABDA_REPAIR_ROOT/repaired-revision.json" 2>/dev/null &&
        az containerapp replica list \
          --name "$ABDA_APP_NAME" \
          --resource-group "$ABDA_RESOURCE_GROUP" \
          --revision "$latest_revision" \
          --output json >"$ABDA_REPAIR_ROOT/repaired-replicas.json" 2>/dev/null; then
        status="$(python3 - \
          "$ABDA_REPAIR_ROOT/repaired-app.json" \
          "$ABDA_REPAIR_ROOT/repaired-revision.json" \
          "$ABDA_REPAIR_ROOT/repaired-replicas.json" <<'PY'
import json
import sys

values = []
for path in sys.argv[1:]:
    with open(path, encoding="utf-8") as handle:
        values.append(json.load(handle))
app, revision, replicas = values
app_properties = app.get("properties") or {}
revision_properties = revision.get("properties") or {}
running = 0
ready = 0
for replica in replicas:
    replica_properties = replica.get("properties") or {}
    if replica_properties.get("runningState") == "Running":
        running += 1
    if any(
        item.get("ready") is True
        for item in replica_properties.get("containers") or []
    ):
        ready += 1
print(
    "|".join(
        str(value or "")
        for value in (
            app_properties.get("provisioningState"),
            revision.get("name"),
            revision_properties.get("provisioningState"),
            revision_properties.get("healthState"),
            revision_properties.get("replicas"),
            running,
            ready,
        )
    )
)
PY
)"
        if [[ "$status" != "$last_status" ]]; then
          printf 'Repaired application state: %s\n' "$status"
          last_status=$status
        fi
        IFS='|' read -r ABDA_APP_STATE ABDA_NEW_REVISION \
          ABDA_REVISION_STATE ABDA_HEALTH_STATE ABDA_REPLICA_COUNT \
          ABDA_RUNNING_REPLICAS ABDA_READY_REPLICAS <<<"$status"
        if [[ "$ABDA_APP_STATE" == 'Succeeded' &&
              "$ABDA_REVISION_STATE" == 'Provisioned' &&
              "$ABDA_HEALTH_STATE" == 'Healthy' &&
              "$ABDA_REPLICA_COUNT" =~ ^[1-9][0-9]*$ &&
              "$ABDA_RUNNING_REPLICAS" =~ ^[1-9][0-9]*$ &&
              "$ABDA_READY_REPLICAS" =~ ^[1-9][0-9]*$ ]]; then
          healthy=1
          break
        fi
      fi
    fi
    sleep 5
  done

  (( healthy == 1 )) || abda_fail 'the repaired revision did not become healthy'
  ABDA_REPAIRED_REVISION=$latest_revision
}

abda_repair_main() {
  set -Eeuo pipefail
  set +x
  umask 077
  unset HISTFILE

  ABDA_REPAIR_SECTION='startup'
  trap abda_repair_error ERR
  trap abda_repair_cleanup EXIT
  trap abda_repair_interrupt INT

  printf 'ABDA-NL Gate 3 probe repair revision: %s\n' \
    "$ABDA_REPAIR_SCRIPT_REVISION"
  printf '%s\n' \
    'This gate repairs only the three Container App probe Host headers.' \
    'It does not rerun migrations, change Auth0 or DNS, enable paid access, or delete resources.'

  for command_name in az awk curl git python3 sha256sum; do
    command -v "$command_name" >/dev/null 2>&1 ||
      abda_repair_bootstrap_fail "required command is unavailable: $command_name"
  done

  ABDA_REPAIR_ROOT="$(mktemp -d /tmp/abda-nl-probe-repair.XXXXXX)"

  ABDA_REPAIR_SECTION='immutable source verification'
  printf '\n[1/9] Verifying the immutable repair source and Bicep compiler...\n'
  git clone --quiet --filter=blob:none --no-checkout \
    'https://github.com/Liu-Hy/ABDA-NL.git' "$ABDA_REPAIR_ROOT/source"
  git -C "$ABDA_REPAIR_ROOT/source" checkout --quiet --detach \
    "$ABDA_REPAIR_SOURCE_COMMIT"
  [[ "$(git -C "$ABDA_REPAIR_ROOT/source" rev-parse HEAD)" == \
      "$ABDA_REPAIR_SOURCE_COMMIT" ]] ||
    abda_repair_bootstrap_fail 'the checked-out repair source changed'
  (
    cd "$ABDA_REPAIR_ROOT/source"
    sha256sum --check --quiet <<ABDA_REPAIR_CHECKSUMS
$ABDA_REPAIR_BASE_GATE_SHA256  deploy/azure/gate3-staging-application.sh
$ABDA_REPAIR_APP_BICEP_SHA256  deploy/azure/app.bicep
$ABDA_REPAIR_APP_PARAMETERS_SHA256  deploy/azure/app.bicepparam
ABDA_REPAIR_CHECKSUMS
  )

  # Reuse the already reviewed secret readers, identity checks, application
  # boundary validation, OIDC validation, and generated-origin acceptance.
  # The sourced file is checksum-pinned above and its main function does not run.
  # shellcheck disable=SC1091
  source "$ABDA_REPAIR_ROOT/source/deploy/azure/gate3-staging-application.sh"
  abda_repair_set_constants

  if ! az bicep version 2>/dev/null | grep -Fq "${ABDA_BICEP_VERSION#v}"; then
    az bicep install --version "$ABDA_BICEP_VERSION"
  fi
  az bicep version
  az bicep version | grep -Fq "${ABDA_BICEP_VERSION#v}" ||
    abda_fail "Bicep $ABDA_BICEP_VERSION is not active"
  printf 'Verified repair source commit: %s\n' "$ABDA_REPAIR_SOURCE_COMMIT"

  ABDA_REPAIR_SECTION='Azure identity and current-state verification'
  printf '\n[2/9] Verifying Azure identity, successful migration, and diagnosed revision...\n'
  az account show --output json >"$ABDA_REPAIR_ROOT/account.json"
  abda_validate_identity "$ABDA_REPAIR_ROOT/account.json"
  az account show \
    --query '{Name:name,TenantId:tenantId,User:user.name,State:state}' \
    --output table

  for ABDA_DEPLOYMENT_NAME in \
    "$ABDA_INFRA_DEPLOYMENT" "$ABDA_MIGRATION_DEPLOYMENT" "$ABDA_APP_DEPLOYMENT"; do
    ABDA_DEPLOYMENT_STATE="$(az deployment group show \
      --name "$ABDA_DEPLOYMENT_NAME" \
      --resource-group "$ABDA_RESOURCE_GROUP" \
      --query properties.provisioningState --output tsv)"
    [[ "$ABDA_DEPLOYMENT_STATE" == 'Succeeded' ]] ||
      abda_fail "deployment $ABDA_DEPLOYMENT_NAME is $ABDA_DEPLOYMENT_STATE"
  done

  az deployment group show \
    --name "$ABDA_INFRA_DEPLOYMENT" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --query properties.outputs --output json \
    >"$ABDA_REPAIR_ROOT/infra-outputs.json"
  az containerapp env show \
    --name "$ABDA_ENVIRONMENT_NAME" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_REPAIR_ROOT/environment.json"
  az postgres flexible-server show \
    --name "${ABDA_POSTGRES_HOST%%.*}" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --query '{name:name,state:state,fullyQualifiedDomainName:fullyQualifiedDomainName,publicNetworkAccess:network.publicNetworkAccess}' \
    --output json >"$ABDA_REPAIR_ROOT/postgres.json"
  az containerapp job list \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_REPAIR_ROOT/jobs.json"
  az containerapp list \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_REPAIR_ROOT/apps.json"
  abda_validate_infrastructure \
    "$ABDA_REPAIR_ROOT/infra-outputs.json" \
    "$ABDA_REPAIR_ROOT/environment.json" \
    "$ABDA_REPAIR_ROOT/postgres.json" \
    "$ABDA_REPAIR_ROOT/jobs.json" \
    "$ABDA_REPAIR_ROOT/apps.json"

  az containerapp job execution list \
    --name "$ABDA_MIGRATION_JOB_NAME" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_REPAIR_ROOT/executions.json"
  az containerapp show \
    --name "$ABDA_APP_NAME" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_REPAIR_ROOT/current-app.json"
  az containerapp revision show \
    --name "$ABDA_APP_NAME" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --revision "$ABDA_REPAIR_EXPECTED_REVISION" \
    --output json >"$ABDA_REPAIR_ROOT/current-revision.json"
  az containerapp replica list \
    --name "$ABDA_APP_NAME" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --revision "$ABDA_REPAIR_EXPECTED_REVISION" \
    --output json >"$ABDA_REPAIR_ROOT/current-replicas.json"
  abda_validate_repair_starting_state \
    "$ABDA_REPAIR_ROOT/current-app.json" \
    "$ABDA_REPAIR_ROOT/current-revision.json" \
    "$ABDA_REPAIR_ROOT/current-replicas.json" \
    "$ABDA_REPAIR_ROOT/executions.json"
  printf 'Verified diagnosed unhealthy revision: %s\n' \
    "$ABDA_REPAIR_EXPECTED_REVISION"

  ABDA_REPAIR_SECTION='public dependency verification'
  printf '\n[3/9] Rechecking the public image digest and Auth0 discovery...\n'
  ABDA_REGISTRY_TOKEN="$(curl --fail --silent --show-error --get \
    --data-urlencode 'scope=repository:liu-hy/abda-nl:pull' \
    'https://ghcr.io/token' | python3 -c \
    'import json,sys; print(json.load(sys.stdin)["token"])')"
  curl --fail --silent --show-error \
    --header "Authorization: Bearer $ABDA_REGISTRY_TOKEN" \
    --header 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json' \
    --dump-header "$ABDA_REPAIR_ROOT/manifest.headers" \
    --output "$ABDA_REPAIR_ROOT/manifest.json" \
    "https://ghcr.io/v2/liu-hy/abda-nl/manifests/sha256:$ABDA_IMAGE_SHA256"
  ABDA_REGISTRY_DIGEST="$(awk '
    tolower($1) == "docker-content-digest:" {
      gsub("\\r", "", $2)
      value = $2
    }
    END { print value }
  ' "$ABDA_REPAIR_ROOT/manifest.headers")"
  [[ "$ABDA_REGISTRY_DIGEST" == "sha256:$ABDA_IMAGE_SHA256" ]] ||
    abda_fail 'the public registry returned an unexpected image digest'
  unset ABDA_REGISTRY_TOKEN
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    --output "$ABDA_REPAIR_ROOT/oidc-discovery.json" "$ABDA_OIDC_METADATA_URL"
  abda_validate_oidc_discovery "$ABDA_REPAIR_ROOT/oidc-discovery.json"
  printf 'Verified unchanged public image and OIDC issuer.\n'

  ABDA_REPAIR_SECTION='private configuration input'
  printf '\n[4/9] Loading the same saved application credentials with hidden prompts...\n'
  printf '%s\n' \
    'Use the values previously saved for Gate 3.' \
    'This repair does not ask for the PostgreSQL administrator password.' \
    'Nothing entered at a hidden prompt is displayed or added to shell history.'

  abda_read_confirmed_secret ABDA_DEPLOY_POSTGRES_APP_PASSWORD \
    'Saved staging PostgreSQL application password: ' 32
  IFS= read -r -p 'Saved Auth0 application Client ID: ' ABDA_DEPLOY_OIDC_CLIENT_ID
  [[ "$ABDA_DEPLOY_OIDC_CLIENT_ID" =~ ^[A-Za-z0-9_-]{8,128}$ ]] ||
    abda_fail 'the Auth0 Client ID format is invalid'
  export ABDA_DEPLOY_OIDC_CLIENT_ID
  abda_read_secret ABDA_DEPLOY_OIDC_CLIENT_SECRET \
    'Saved Auth0 application Client Secret: ' 16
  abda_read_confirmed_secret ABDA_DEPLOY_SESSION_SECRET \
    'Saved ABDA-NL session secret: ' 32
  abda_read_confirmed_secret ABDA_DEPLOY_MCP_TOKEN_PEPPER \
    'Saved ABDA-NL MCP token pepper: ' 32
  abda_read_confirmed_secret ABDA_DEPLOY_METRICS_TOKEN \
    'Saved ABDA-NL metrics bearer token: ' 32

  IFS= read -r -p 'Foundry Anthropic endpoint from the private .env: ' \
    ABDA_DEPLOY_FOUNDRY_ENDPOINT
  python3 - "$ABDA_DEPLOY_FOUNDRY_ENDPOINT" <<'PY'
import sys
from urllib.parse import urlsplit

value = sys.argv[1].strip().rstrip("/")
parsed = urlsplit(value)
if (
    value != sys.argv[1]
    or parsed.scheme != "https"
    or not parsed.hostname
    or parsed.username is not None
    or parsed.password is not None
    or parsed.query
    or parsed.fragment
    or not (
        parsed.hostname.endswith(".services.ai.azure.com")
        or parsed.hostname.endswith(".openai.azure.com")
    )
):
    raise SystemExit("STOP: Foundry endpoint format is invalid")
PY
  export ABDA_DEPLOY_FOUNDRY_ENDPOINT

  IFS= read -r -p 'Foundry Claude Sonnet 4.6 deployment name from the private .env: ' \
    ABDA_DEPLOY_CLAUDE_DEPLOYMENT
  [[ "$ABDA_DEPLOY_CLAUDE_DEPLOYMENT" =~ ^[A-Za-z0-9._-]{1,128}$ ]] ||
    abda_fail 'the Foundry deployment name format is invalid'
  export ABDA_DEPLOY_CLAUDE_DEPLOYMENT
  abda_read_secret ABDA_DEPLOY_FOUNDRY_API_KEY \
    'CloudBank Foundry API key from the private .env: ' 16
  abda_read_secret ABDA_DEPLOY_OPENROUTER_API_KEY \
    'Current OpenRouter API key from the private .env: ' 16

  ABDA_SECRET_NAMES=(
    ABDA_DEPLOY_POSTGRES_APP_PASSWORD
    ABDA_DEPLOY_SESSION_SECRET
    ABDA_DEPLOY_MCP_TOKEN_PEPPER
    ABDA_DEPLOY_METRICS_TOKEN
  )
  for (( ABDA_LEFT = 0; ABDA_LEFT < ${#ABDA_SECRET_NAMES[@]}; ABDA_LEFT++ )); do
    for (( ABDA_RIGHT = ABDA_LEFT + 1; ABDA_RIGHT < ${#ABDA_SECRET_NAMES[@]}; ABDA_RIGHT++ )); do
      if [[ "${!ABDA_SECRET_NAMES[ABDA_LEFT]}" == \
            "${!ABDA_SECRET_NAMES[ABDA_RIGHT]}" ]]; then
        abda_fail 'the database, session, MCP, and metrics secrets must be independent'
      fi
    done
  done

  export ABDA_DEPLOY_LOCATION="$ABDA_LOCATION"
  export ABDA_DEPLOY_ENVIRONMENT_NAME="$ABDA_ENVIRONMENT_NAME"
  export ABDA_DEPLOY_APP_NAME="$ABDA_APP_NAME"
  export ABDA_DEPLOY_IMAGE_REPOSITORY="$ABDA_IMAGE_REPOSITORY"
  export ABDA_DEPLOY_IMAGE_SHA256="$ABDA_IMAGE_SHA256"
  export ABDA_DEPLOY_POSTGRES_HOST="$ABDA_POSTGRES_HOST"
  export ABDA_DEPLOY_POSTGRES_APP_LOGIN='abda_app'
  export ABDA_DEPLOY_ENVIRONMENT='staging'
  export ABDA_DEPLOY_CUSTOM_HOSTNAME=''
  export ABDA_DEPLOY_CUSTOM_DOMAIN_CERTIFICATE_ID=''
  export ABDA_DEPLOY_OIDC_METADATA_URL="$ABDA_OIDC_METADATA_URL"
  export ABDA_DEPLOY_OIDC_ISSUER="$ABDA_OIDC_ISSUER"
  export ABDA_DEPLOY_TRIAL_ENABLED='false'
  export ABDA_DEPLOY_TRIAL_MAX_USERS='100'
  export ABDA_DEPLOY_TRIAL_BUDGET_MICROUSD='500000000'
  export ABDA_DEPLOY_OPENROUTER_FAILOVER_ENABLED='false'
  export ABDA_DEPLOY_OPENROUTER_BUDGET_MICROUSD="$ABDA_OPENROUTER_BUDGET_MICROUSD"

  ABDA_REPAIR_SECTION='provider-validated repair review'
  printf '\n[5/9] Validating and reviewing the one-resource repair...\n'
  az deployment group validate \
    --name "$ABDA_APP_DEPLOYMENT" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --parameters "$ABDA_REPAIR_ROOT/source/deploy/azure/app.bicepparam" \
    --output none
  az deployment group what-if \
    --name "$ABDA_APP_DEPLOYMENT" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --parameters "$ABDA_REPAIR_ROOT/source/deploy/azure/app.bicepparam" \
    --result-format ResourceIdOnly --no-pretty-print --output json \
    >"$ABDA_REPAIR_ROOT/app-what-if.json"
  ABDA_APP_RESOURCE_ID="/subscriptions/$ABDA_EXPECTED_SUBSCRIPTION/resourceGroups/$ABDA_RESOURCE_GROUP/providers/Microsoft.App/containerApps/$ABDA_APP_NAME"
  abda_validate_repair_what_if \
    "$ABDA_REPAIR_ROOT/app-what-if.json" "$ABDA_APP_RESOURCE_ID"

  printf '\nThis repair will update only %s.\n' "$ABDA_APP_NAME"
  printf '%s\n' \
    'It keeps the current image and application settings, adds a trusted Host header to all three probes,' \
    'creates one replacement revision, and does not rerun the migration.' \
    'Type REPAIR_ABDA_STAGING_PROBES to continue, or press Enter to cancel.'
  IFS= read -r -p 'Confirmation: ' ABDA_REPAIR_CONFIRMATION
  [[ "$ABDA_REPAIR_CONFIRMATION" == 'REPAIR_ABDA_STAGING_PROBES' ]] || {
    printf 'Cancelled without changing Azure.\n'
    return 0
  }

  ABDA_REPAIR_SECTION='Container App probe repair deployment'
  printf '\n[6/9] Deploying the reviewed Container App probe repair...\n'
  az deployment group create \
    --name "$ABDA_APP_DEPLOYMENT" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --parameters "$ABDA_REPAIR_ROOT/source/deploy/azure/app.bicepparam" \
    --mode Incremental --output none

  ABDA_REPAIR_SECTION='repaired revision verification'
  printf '\n[7/9] Waiting for a healthy replacement revision and ready replica...\n'
  abda_repair_wait_for_healthy_revision "$ABDA_REPAIR_EXPECTED_REVISION"
  abda_validate_application "$ABDA_REPAIR_ROOT/repaired-app.json"
  abda_validate_repaired_probes "$ABDA_REPAIR_ROOT/repaired-app.json"

  ABDA_REPAIR_SECTION='generated-origin acceptance'
  printf '\n[8/9] Running complete generated-origin acceptance...\n'
  abda_smoke_generated_origin "$ABDA_REPAIR_ROOT"

  ABDA_REPAIR_SECTION='final repair state verification'
  printf '\n[9/9] Verifying the final Azure deployment state...\n'
  ABDA_APP_DEPLOYMENT_STATE="$(az deployment group show \
    --name "$ABDA_APP_DEPLOYMENT" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --query properties.provisioningState --output tsv)"
  [[ "$ABDA_APP_DEPLOYMENT_STATE" == 'Succeeded' ]] ||
    abda_fail "application deployment is $ABDA_APP_DEPLOYMENT_STATE"

  printf '\nABDA-NL Gate 3 probe repair status:\n'
  printf 'script_revision: %s\n' "$ABDA_REPAIR_SCRIPT_REVISION"
  printf 'source_commit: %s\n' "$ABDA_REPAIR_SOURCE_COMMIT"
  printf 'image_digest: sha256:%s\n' "$ABDA_IMAGE_SHA256"
  printf 'subscription_id: %s\n' "$ABDA_EXPECTED_SUBSCRIPTION"
  printf 'resource_group: %s\n' "$ABDA_RESOURCE_GROUP"
  printf 'previous_revision: %s\n' "$ABDA_REPAIR_EXPECTED_REVISION"
  printf 'repaired_revision: %s\n' "$ABDA_REPAIRED_REVISION"
  printf 'application_deployment_state: %s\n' "$ABDA_APP_DEPLOYMENT_STATE"
  printf 'application_origin: %s\n' "$ABDA_GENERATED_ORIGIN"
  printf 'probe_host_header: %s\n' "${ABDA_GENERATED_ORIGIN#https://}"
  printf 'migration_rerun: false\n'
  printf 'trial_activation_enabled: false\n'
  printf 'openrouter_failover_enabled: false\n'
  printf 'generated_origin_acceptance: passed\n'
  printf 'result: STAGING_PROBE_REPAIR_COMPLETE_CUSTOM_DOMAIN_NOT_CONFIGURED\n'
  printf 'Stop here. Send this status and the shell exit code to Codex.\n'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_repair_main "$@"
fi
