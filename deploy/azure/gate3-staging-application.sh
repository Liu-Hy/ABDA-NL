#!/usr/bin/env bash

# Deploy the first ABDA-NL staging migration job and web application.
# This gate is intentionally bound to one Azure subscription, one recovered
# infrastructure deployment, and one verified public image digest.

ABDA_GATE_SCRIPT_REVISION='4'
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
ABDA_SOURCE_COMMIT='ef91e88226abf9f916f976d9e668ad3536f1fe46'
ABDA_IMAGE_REPOSITORY='ghcr.io/liu-hy/abda-nl'
ABDA_IMAGE_SHA256='c3f6ec80972850d30850ec2e72d28fd673e835187bebdc45a8f9cda4a8ad1a55'
ABDA_BICEP_VERSION='v0.46.1'
ABDA_OIDC_METADATA_URL='https://login.abda-nl.org/.well-known/openid-configuration'
ABDA_OIDC_ISSUER='https://login.abda-nl.org/'
ABDA_OPENROUTER_BUDGET_MICROUSD='500000000'

abda_fail() {
  printf 'STOP: %s\n' "$*" >&2
  return 1
}

abda_require_command() {
  command -v "$1" >/dev/null 2>&1 || abda_fail "required command is unavailable: $1"
}

abda_read_secret() {
  local variable_name=$1
  local prompt=$2
  local minimum_length=$3
  local secret_value=''

  IFS= read -r -s -p "$prompt" secret_value
  printf '\n'
  if (( ${#secret_value} < minimum_length )); then
    abda_fail "$prompt must contain at least $minimum_length characters"
  fi
  if [[ "$secret_value" =~ ^[[:space:]] || "$secret_value" =~ [[:space:]]$ ]]; then
    abda_fail "$prompt must not begin or end with whitespace"
  fi
  printf -v "$variable_name" '%s' "$secret_value"
  export "${variable_name?}"
}

abda_read_confirmed_secret() {
  local variable_name=$1
  local prompt=$2
  local minimum_length=$3
  local first_value=''
  local second_value=''

  IFS= read -r -s -p "$prompt" first_value
  printf '\n'
  IFS= read -r -s -p 'Enter it again: ' second_value
  printf '\n'
  if [[ "$first_value" != "$second_value" ]]; then
    abda_fail "$prompt entries did not match"
  fi
  if (( ${#first_value} < minimum_length )); then
    abda_fail "$prompt must contain at least $minimum_length characters"
  fi
  if [[ "$first_value" =~ ^[[:space:]] || "$first_value" =~ [[:space:]]$ ]]; then
    abda_fail "$prompt must not begin or end with whitespace"
  fi
  printf -v "$variable_name" '%s' "$first_value"
  export "${variable_name?}"
}

abda_validate_what_if() {
  local result_path=$1
  local allowed_resource_id=$2
  local label=$3

  python3 - "$result_path" "$allowed_resource_id" "$label" <<'PY'
import json
import sys

path, allowed_id, label = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    document = json.load(handle)

payload = document.get("properties", document)
status = payload.get("status")
if status not in (None, "Succeeded"):
    raise SystemExit(f"STOP: {label} what-if status was {status!r}")

changes = payload.get("changes")
if not isinstance(changes, list):
    raise SystemExit(f"STOP: {label} what-if did not return a changes list")

allowed = allowed_id.lower()
dangerous = []
mutating = []
known = {"Create", "Delete", "Deploy", "Ignore", "Modify", "NoChange", "Unsupported"}
for change in changes:
    if not isinstance(change, dict):
        dangerous.append("malformed change entry")
        continue
    change_type = str(change.get("changeType", ""))
    resource_id = str(
        change.get("resourceId")
        or (change.get("after") or {}).get("id")
        or (change.get("before") or {}).get("id")
        or ""
    )
    if change_type not in known:
        dangerous.append(f"unknown change type {change_type!r} for {resource_id!r}")
        continue
    if change_type in {"Delete", "Unsupported"}:
        dangerous.append(f"{change_type} {resource_id}")
        continue
    if change_type in {"Create", "Deploy", "Modify"}:
        mutating.append((change_type, resource_id))
        if resource_id.lower() != allowed:
            dangerous.append(f"unexpected {change_type} target {resource_id}")

print(f"{label} planned Azure changes:")
if mutating:
    for change_type, resource_id in mutating:
        print(f"  {change_type:<7} {resource_id}")
else:
    print("  No resource mutation reported. The existing target will be verified before use.")

if dangerous:
    for item in dangerous:
        print(f"STOP: {item}", file=sys.stderr)
    raise SystemExit(1)
PY
}

abda_validate_identity() {
  local identity_path=$1
  python3 - "$identity_path" \
    "$ABDA_EXPECTED_SUBSCRIPTION" "$ABDA_EXPECTED_TENANT" "$ABDA_EXPECTED_USER" <<'PY'
import json
import sys

path, subscription, tenant, user = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    value = json.load(handle)
actual = {
    "subscription": str(value.get("id", "")),
    "tenant": str(value.get("tenantId", "")),
    "user": str((value.get("user") or {}).get("name", "")),
    "state": str(value.get("state", "")),
}
expected = {
    "subscription": subscription,
    "tenant": tenant,
    "user": user,
    "state": "Enabled",
}
if actual != expected:
    raise SystemExit(f"STOP: Azure identity mismatch: {actual!r}")
PY
}

abda_validate_oidc_discovery() {
  local discovery_path=$1
  python3 - "$discovery_path" "$ABDA_OIDC_ISSUER" <<'PY'
import json
import sys
from urllib.parse import urlsplit

path, issuer = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    value = json.load(handle)
if value.get("issuer") != issuer:
    raise SystemExit("STOP: Auth0 discovery returned an unexpected issuer")
for name in ("authorization_endpoint", "token_endpoint", "jwks_uri", "end_session_endpoint"):
    endpoint = str(value.get(name, ""))
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or parsed.hostname != "login.abda-nl.org":
        raise SystemExit(f"STOP: Auth0 discovery returned an unexpected {name}")
PY
}

abda_validate_infrastructure() {
  local outputs_path=$1
  local environment_path=$2
  local postgres_path=$3
  local jobs_path=$4
  local apps_path=$5

  python3 - "$outputs_path" "$environment_path" "$postgres_path" \
    "$jobs_path" "$apps_path" "$ABDA_ENVIRONMENT_NAME" \
    "$ABDA_MIGRATION_JOB_NAME" "$ABDA_APP_NAME" "$ABDA_POSTGRES_HOST" \
    "$ABDA_GENERATED_ORIGIN" <<'PY'
import json
import sys

(
    outputs_path,
    environment_path,
    postgres_path,
    jobs_path,
    apps_path,
    expected_environment,
    expected_job,
    expected_app,
    expected_postgres,
    expected_origin,
) = sys.argv[1:]

def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)

outputs = load(outputs_path)

def output(name):
    entry = outputs.get(name)
    if not isinstance(entry, dict):
        raise SystemExit(f"STOP: infrastructure output {name} is absent")
    return str(entry.get("value", ""))

expected_outputs = {
    "containerAppsEnvironmentName": expected_environment,
    "migrationJobName": expected_job,
    "expectedAppName": expected_app,
    "postgresHost": expected_postgres,
    "expectedPublicOrigin": expected_origin,
    "postgresDatabase": "abda",
    "postgresAdminLogin": "abdaadmin",
}
for name, expected in expected_outputs.items():
    actual = output(name)
    if actual != expected:
        raise SystemExit(
            f"STOP: infrastructure output {name} was {actual!r}, expected {expected!r}"
        )

environment = load(environment_path)
if environment.get("name") != expected_environment:
    raise SystemExit("STOP: the Container Apps environment name changed")
if (environment.get("properties") or {}).get("provisioningState") != "Succeeded":
    raise SystemExit("STOP: the Container Apps environment is not ready")

postgres = load(postgres_path)
if postgres.get("name") != expected_postgres.split(".", 1)[0]:
    raise SystemExit("STOP: the PostgreSQL server name changed")
if postgres.get("fullyQualifiedDomainName") != expected_postgres:
    raise SystemExit("STOP: the PostgreSQL server hostname changed")
if postgres.get("state") != "Ready":
    raise SystemExit("STOP: PostgreSQL is not ready")
if postgres.get("publicNetworkAccess") != "Disabled":
    raise SystemExit("STOP: PostgreSQL public network access is not disabled")

jobs = load(jobs_path)
apps = load(apps_path)
if not isinstance(jobs, list) or not isinstance(apps, list):
    raise SystemExit("STOP: Azure did not return application resource lists")
unexpected_jobs = sorted(str(item.get("name", "")) for item in jobs if item.get("name") != expected_job)
unexpected_apps = sorted(str(item.get("name", "")) for item in apps if item.get("name") != expected_app)
if unexpected_jobs or unexpected_apps:
    raise SystemExit(
        f"STOP: unexpected application resources exist: jobs={unexpected_jobs!r}, apps={unexpected_apps!r}"
    )
PY
}

abda_validate_job() {
  local job_path=$1
  local expected_image="${ABDA_IMAGE_REPOSITORY}@sha256:${ABDA_IMAGE_SHA256}"
  python3 - "$job_path" "$expected_image" "$ABDA_MIGRATION_JOB_NAME" <<'PY'
import json
import sys

path, expected_image, expected_name = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    job = json.load(handle)
properties = job.get("properties") or {}
configuration = properties.get("configuration") or {}
containers = (properties.get("template") or {}).get("containers") or []
if job.get("name") != expected_name or len(containers) != 1:
    raise SystemExit("STOP: migration job identity or container count changed")
container = containers[0]
if container.get("image") != expected_image:
    raise SystemExit("STOP: migration job does not use the verified image digest")
if container.get("command") != ["/opt/venv/bin/python"]:
    raise SystemExit("STOP: migration job command changed")
if container.get("args") != ["-m", "app.cli.migrate"]:
    raise SystemExit("STOP: migration job arguments changed")
if configuration.get("triggerType") != "Manual":
    raise SystemExit("STOP: migration job is not manual")
if configuration.get("replicaRetryLimit") != 0:
    raise SystemExit("STOP: migration job retry limit changed")
env = {entry.get("name"): entry for entry in container.get("env") or []}
if env.get("ABDA_DATABASE_URL", {}).get("secretRef") != "admin-database-url":
    raise SystemExit("STOP: migration job administrator credential boundary changed")
if env.get("ABDA_DATABASE_APP_PASSWORD", {}).get("secretRef") != "app-database-password":
    raise SystemExit("STOP: migration job application credential boundary changed")
PY
}

abda_validate_application() {
  local app_path=$1
  local expected_image="${ABDA_IMAGE_REPOSITORY}@sha256:${ABDA_IMAGE_SHA256}"
  python3 - "$app_path" "$expected_image" "$ABDA_APP_NAME" \
    "${ABDA_GENERATED_ORIGIN#https://}" <<'PY'
import json
import sys

path, expected_image, expected_name, expected_fqdn = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    app = json.load(handle)
properties = app.get("properties") or {}
configuration = properties.get("configuration") or {}
ingress = configuration.get("ingress") or {}
containers = (properties.get("template") or {}).get("containers") or []
if app.get("name") != expected_name or len(containers) != 1:
    raise SystemExit("STOP: web application identity or container count changed")
container = containers[0]
if container.get("image") != expected_image:
    raise SystemExit("STOP: web application does not use the verified image digest")
if ingress.get("fqdn") != expected_fqdn:
    raise SystemExit("STOP: web application hostname changed")
if ingress.get("external") is not True or ingress.get("allowInsecure") is not False:
    raise SystemExit("STOP: web ingress safety settings changed")
if ingress.get("targetPort") != 8000:
    raise SystemExit("STOP: web ingress target port changed")

env = {entry.get("name"): entry for entry in container.get("env") or []}
required_values = {
    "ABDA_ENVIRONMENT": "staging",
    "ABDA_AUTH_MODE": "oidc",
    "ABDA_AUTO_CREATE_DB": "0",
    "ABDA_PUBLIC_BASE_URL": f"https://{expected_fqdn}",
    "ABDA_TRIAL_ENABLED": "false",
    "ABDA_OPENROUTER_FAILOVER_ENABLED": "false",
}
for name, expected in required_values.items():
    if str(env.get(name, {}).get("value", "")).lower() != expected.lower():
        raise SystemExit(f"STOP: web application {name} changed")
if env.get("ABDA_DATABASE_URL", {}).get("secretRef") != "database-url":
    raise SystemExit("STOP: web application database boundary changed")
if any("ADMIN" in str(name) for name in env):
    raise SystemExit("STOP: an administrator setting reached the web application")
PY
}

abda_smoke_generated_origin() {
  local root=$1
  local origin=$ABDA_GENERATED_ORIGIN
  local ready_path="$root/ready.json"
  local ready=0

  for _ in $(seq 1 60); do
    if curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
      --connect-timeout 10 --max-time 30 \
      "$origin/health/ready" --output "$ready_path"; then
      if python3 - "$ready_path" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    if json.load(handle) != {"status": "ready"}:
        raise SystemExit(1)
PY
      then
        ready=1
        break
      fi
    fi
    sleep 5
  done
  if (( ready != 1 )); then
    abda_fail "the generated origin did not become ready"
  fi

  curl --fail --silent --show-error --proto '=https' --tlsv1.2 --http1.1 \
    --connect-timeout 10 --max-time 30 \
    --dump-header "$root/root.headers" --output "$root/root.html" "$origin/"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    --output "$root/live.json" "$origin/health/live"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    --output "$root/config.json" "$origin/config"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    --output "$root/privacy.html" "$origin/privacy.html"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    --output "$root/terms.html" "$origin/terms.html"

  local unauthorized_status
  unauthorized_status="$(curl --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 --output "$root/metrics-unauthorized.json" \
    --write-out '%{http_code}' "$origin/internal/metrics")"
  [[ "$unauthorized_status" == '401' ]] || \
    abda_fail "unauthenticated metrics returned HTTP $unauthorized_status instead of 401"

  printf 'header = "Authorization: Bearer %s"\n' \
    "$ABDA_DEPLOY_METRICS_TOKEN" >"$root/metrics.curl"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    --config "$root/metrics.curl" \
    --output "$root/metrics.txt" "$origin/internal/metrics"

  python3 - "$root" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
with (root / "live.json").open(encoding="utf-8") as handle:
    if json.load(handle) != {"status": "ok"}:
        raise SystemExit("STOP: liveness response changed")
with (root / "config.json").open(encoding="utf-8") as handle:
    config = json.load(handle)
for name, expected in {
    "llm_enabled": True,
    "llm_auth_required": True,
    "byok_enabled": True,
    "byok_keys_stored": False,
}.items():
    if config.get(name) is not expected:
        raise SystemExit(f"STOP: public config {name} changed")
profiles = config.get("profiles") or []
if [item.get("id") for item in profiles] != ["balanced"]:
    raise SystemExit("STOP: generated origin exposes an unexpected funded profile")
providers = {item.get("id") for item in config.get("byok_providers") or []}
if providers != {"anthropic", "google", "openai", "openrouter"}:
    raise SystemExit("STOP: generated origin exposes unexpected BYOK providers")

headers = {}
for line in (root / "root.headers").read_text(encoding="utf-8").splitlines():
    if ":" in line:
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
required_headers = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
}
for name, expected in required_headers.items():
    if headers.get(name) != expected:
        raise SystemExit(f"STOP: generated origin header {name} changed")
if "max-age=31536000" not in headers.get("strict-transport-security", ""):
    raise SystemExit("STOP: generated origin HSTS header changed")
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
        raise SystemExit(f"STOP: generated origin CSP is missing {directive}")

metrics = {}
for raw_line in (root / "metrics.txt").read_text(encoding="utf-8").splitlines():
    fields = raw_line.strip().split()
    if len(fields) == 2 and "{" not in fields[0]:
        metrics[fields[0]] = fields[1]
expected_metrics = {
    "abda_trial_enabled": "0",
    "abda_trial_max_users": "100",
    "abda_trial_grant_microusd": "5000000",
    "abda_trial_budget_microusd": "500000000",
    "abda_openrouter_enabled": "0",
    "abda_openrouter_budget_microusd": "500000000",
    "abda_trial_reserved_microusd": "0",
    "abda_openrouter_reserved_microusd": "0",
    "abda_database_pool_capacity": "5",
}
for name, expected in expected_metrics.items():
    if metrics.get(name) != expected:
        raise SystemExit(f"STOP: generated origin metric {name} changed")
PY
}

abda_gate_cleanup() {
  local exit_code=$?
  set +e
  unset ABDA_DEPLOY_POSTGRES_ADMIN_PASSWORD
  unset ABDA_DEPLOY_POSTGRES_APP_PASSWORD
  unset ABDA_DEPLOY_SESSION_SECRET
  unset ABDA_DEPLOY_MCP_TOKEN_PEPPER
  unset ABDA_DEPLOY_METRICS_TOKEN
  unset ABDA_DEPLOY_OIDC_CLIENT_SECRET
  unset ABDA_DEPLOY_FOUNDRY_API_KEY
  unset ABDA_DEPLOY_OPENROUTER_API_KEY
  unset ABDA_REGISTRY_TOKEN
  if [[ "${ABDA_GATE_ROOT:-}" == /tmp/abda-nl-gate3.* &&
        -d "${ABDA_GATE_ROOT:-}" ]]; then
    rm -rf -- "$ABDA_GATE_ROOT"
  fi
  printf '\nGate 3 shell exit code: %s\n' "$exit_code"
}

abda_gate_error() {
  local exit_code=$?
  printf '\nSTOP: Gate 3 failed in section: %s\n' "${ABDA_GATE_SECTION:-unknown}" >&2
  printf 'Do not delete resources or rerun blindly. Send the visible status to Codex.\n' >&2
  return "$exit_code"
}

abda_gate_main() {
  set -Eeuo pipefail
  set +x
  umask 077
  unset HISTFILE

  ABDA_GATE_SECTION='startup'
  ABDA_GATE_ROOT=''
  trap abda_gate_error ERR
  trap abda_gate_cleanup EXIT

  printf 'ABDA-NL Gate 3 staging application script revision: %s\n' \
    "$ABDA_GATE_SCRIPT_REVISION"
  printf 'This gate deploys the reviewed migration job and web app only after one confirmation.\n'
  printf 'It does not change Auth0, Cloudflare, DNS, trial activation, or OpenRouter failover.\n\n'

  for command_name in az curl git python3 sha256sum; do
    abda_require_command "$command_name"
  done

  ABDA_GATE_ROOT="$(mktemp -d /tmp/abda-nl-gate3.XXXXXX)"

  ABDA_GATE_SECTION='Azure identity verification'
  printf '[1/10] Verifying the exact Azure identity and subscription...\n'
  az account show --output json >"$ABDA_GATE_ROOT/account.json"
  abda_validate_identity "$ABDA_GATE_ROOT/account.json"
  az account show \
    --query '{Name:name,TenantId:tenantId,User:user.name,State:state}' \
    --output table

  ABDA_GATE_SECTION='immutable source and image verification'
  printf '\n[2/10] Verifying the immutable source, Bicep compiler, and public image...\n'
  git clone --quiet --filter=blob:none --no-checkout \
    "$ABDA_SOURCE_REPOSITORY" "$ABDA_GATE_ROOT/source"
  git -C "$ABDA_GATE_ROOT/source" checkout --quiet --detach "$ABDA_SOURCE_COMMIT"
  [[ "$(git -C "$ABDA_GATE_ROOT/source" rev-parse HEAD)" == "$ABDA_SOURCE_COMMIT" ]] || \
    abda_fail 'the checked-out source commit changed'
  (
    cd "$ABDA_GATE_ROOT/source"
    sha256sum --check --quiet <<'ABDA_BICEP_CHECKSUMS'
b05bbb83171240019cc513db9541912398e34c0da2479d4708d97ffe5f3b93b4  deploy/azure/migration-job.bicep
2b441af73e207fd52c9a4fb0a507ac2ea4f571cc1bd9d4addf9c117ab1f39b21  deploy/azure/migration-job.bicepparam
c18cccafb53e13f9366f6b77fb472b330f8cade0861d3ab07e5dea0141ced6f2  deploy/azure/app.bicep
5c04b1e73346c0eec704fecfc82ad155423c5ca8859fc274afbebb6c209f801a  deploy/azure/app.bicepparam
ABDA_BICEP_CHECKSUMS
  )

  if ! az bicep version 2>/dev/null | grep -Fq "${ABDA_BICEP_VERSION#v}"; then
    az bicep install --version "$ABDA_BICEP_VERSION"
  fi
  az bicep version
  az bicep version | grep -Fq "${ABDA_BICEP_VERSION#v}" || \
    abda_fail "Bicep $ABDA_BICEP_VERSION is not active"

  ABDA_REGISTRY_TOKEN="$(curl --fail --silent --show-error --get \
    --data-urlencode 'scope=repository:liu-hy/abda-nl:pull' \
    'https://ghcr.io/token' | python3 -c \
    'import json,sys; print(json.load(sys.stdin)["token"])')"
  curl --fail --silent --show-error \
    --header "Authorization: Bearer $ABDA_REGISTRY_TOKEN" \
    --header 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json' \
    --dump-header "$ABDA_GATE_ROOT/manifest.headers" \
    --output "$ABDA_GATE_ROOT/manifest.json" \
    "https://ghcr.io/v2/liu-hy/abda-nl/manifests/sha256:$ABDA_IMAGE_SHA256"
  ABDA_REGISTRY_DIGEST="$(awk '
    tolower($1) == "docker-content-digest:" {
      gsub("\\r", "", $2)
      value = $2
    }
    END { print value }
  ' "$ABDA_GATE_ROOT/manifest.headers")"
  [[ "$ABDA_REGISTRY_DIGEST" == "sha256:$ABDA_IMAGE_SHA256" ]] || \
    abda_fail 'the public registry returned an unexpected image digest'
  unset ABDA_REGISTRY_TOKEN
  printf 'Verified source commit: %s\n' "$ABDA_SOURCE_COMMIT"
  printf 'Verified public image: %s@sha256:%s\n' \
    "$ABDA_IMAGE_REPOSITORY" "$ABDA_IMAGE_SHA256"

  ABDA_GATE_SECTION='recovered infrastructure verification'
  printf '\n[3/10] Verifying the recovered private infrastructure and application boundary...\n'
  ABDA_INFRA_STATE="$(az deployment group show \
    --name "$ABDA_INFRA_DEPLOYMENT" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --query properties.provisioningState --output tsv)"
  [[ "$ABDA_INFRA_STATE" == 'Succeeded' ]] || \
    abda_fail "infrastructure deployment state is $ABDA_INFRA_STATE"
  az deployment group show \
    --name "$ABDA_INFRA_DEPLOYMENT" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --query properties.outputs --output json >"$ABDA_GATE_ROOT/infra-outputs.json"
  az containerapp env show \
    --name "$ABDA_ENVIRONMENT_NAME" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_GATE_ROOT/environment.json"
  az postgres flexible-server show \
    --name "${ABDA_POSTGRES_HOST%%.*}" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --query '{name:name,state:state,fullyQualifiedDomainName:fullyQualifiedDomainName,publicNetworkAccess:network.publicNetworkAccess}' \
    --output json >"$ABDA_GATE_ROOT/postgres.json"
  az containerapp job list \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_GATE_ROOT/jobs.json"
  az containerapp list \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_GATE_ROOT/apps.json"
  abda_validate_infrastructure \
    "$ABDA_GATE_ROOT/infra-outputs.json" \
    "$ABDA_GATE_ROOT/environment.json" \
    "$ABDA_GATE_ROOT/postgres.json" \
    "$ABDA_GATE_ROOT/jobs.json" \
    "$ABDA_GATE_ROOT/apps.json"

  python3 - "$ABDA_GATE_ROOT/jobs.json" "$ABDA_MIGRATION_JOB_NAME" \
    "$ABDA_RESOURCE_GROUP" <<'PY'
import json
import subprocess
import sys

path, job_name, resource_group = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    jobs = json.load(handle)
if jobs:
    result = subprocess.run(
        [
            "az", "containerapp", "job", "execution", "list",
            "--name", job_name,
            "--resource-group", resource_group,
            "--output", "json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    executions = json.loads(result.stdout)
    active = [
        item.get("name", "")
        for item in executions
        if (item.get("properties") or {}).get("status")
        not in {"Succeeded", "Failed", "Stopped"}
    ]
    if active:
        raise SystemExit(f"STOP: migration executions are still active: {active!r}")
PY
  printf 'Verified infrastructure deployment: %s\n' "$ABDA_INFRA_DEPLOYMENT"
  printf 'Verified generated origin: %s\n' "$ABDA_GENERATED_ORIGIN"

  ABDA_GATE_SECTION='Auth0 discovery verification'
  printf '\n[4/10] Verifying the public Auth0 discovery contract...\n'
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    --output "$ABDA_GATE_ROOT/oidc-discovery.json" "$ABDA_OIDC_METADATA_URL"
  abda_validate_oidc_discovery "$ABDA_GATE_ROOT/oidc-discovery.json"
  printf 'Verified OIDC issuer: %s\n' "$ABDA_OIDC_ISSUER"

  ABDA_GATE_SECTION='private configuration input'
  printf '\n[5/10] Loading saved credentials with hidden prompts...\n'
  printf 'Use values from your password manager and private Delta .env.\n'
  printf 'Nothing entered at a hidden prompt is displayed or added to shell history.\n\n'

  abda_read_confirmed_secret \
    ABDA_DEPLOY_POSTGRES_ADMIN_PASSWORD \
    'Saved staging PostgreSQL administrator password: ' 16
  abda_read_confirmed_secret \
    ABDA_DEPLOY_POSTGRES_APP_PASSWORD \
    'Saved staging PostgreSQL application password: ' 32
  if [[ "$ABDA_DEPLOY_POSTGRES_ADMIN_PASSWORD" == "$ABDA_DEPLOY_POSTGRES_APP_PASSWORD" ]]; then
    abda_fail 'the administrator and application database passwords must differ'
  fi

  IFS= read -r -p 'Saved Auth0 application Client ID: ' ABDA_DEPLOY_OIDC_CLIENT_ID
  [[ "$ABDA_DEPLOY_OIDC_CLIENT_ID" =~ ^[A-Za-z0-9_-]{8,128}$ ]] || \
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
  [[ "$ABDA_DEPLOY_CLAUDE_DEPLOYMENT" =~ ^[A-Za-z0-9._-]{1,128}$ ]] || \
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
      if [[ "${!ABDA_SECRET_NAMES[ABDA_LEFT]}" == "${!ABDA_SECRET_NAMES[ABDA_RIGHT]}" ]]; then
        abda_fail 'the database, session, MCP, and metrics secrets must be independent'
      fi
    done
  done

  export ABDA_DEPLOY_LOCATION="$ABDA_LOCATION"
  export ABDA_DEPLOY_ENVIRONMENT_NAME="$ABDA_ENVIRONMENT_NAME"
  export ABDA_DEPLOY_MIGRATION_JOB_NAME="$ABDA_MIGRATION_JOB_NAME"
  export ABDA_DEPLOY_APP_NAME="$ABDA_APP_NAME"
  export ABDA_DEPLOY_IMAGE_REPOSITORY="$ABDA_IMAGE_REPOSITORY"
  export ABDA_DEPLOY_IMAGE_SHA256="$ABDA_IMAGE_SHA256"
  export ABDA_DEPLOY_POSTGRES_HOST="$ABDA_POSTGRES_HOST"
  export ABDA_DEPLOY_POSTGRES_ADMIN_LOGIN='abdaadmin'
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

  ABDA_GATE_SECTION='provider-validated deployment review'
  printf '\n[6/10] Validating both templates and reviewing their exact resource boundaries...\n'
  az deployment group validate \
    --name "$ABDA_MIGRATION_DEPLOYMENT" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --parameters "$ABDA_GATE_ROOT/source/deploy/azure/migration-job.bicepparam" \
    --output none
  az deployment group validate \
    --name "$ABDA_APP_DEPLOYMENT" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --parameters "$ABDA_GATE_ROOT/source/deploy/azure/app.bicepparam" \
    --output none

  az deployment group what-if \
    --name "$ABDA_MIGRATION_DEPLOYMENT" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --parameters "$ABDA_GATE_ROOT/source/deploy/azure/migration-job.bicepparam" \
    --result-format ResourceIdOnly --no-pretty-print --output json \
    >"$ABDA_GATE_ROOT/migration-what-if.json"
  az deployment group what-if \
    --name "$ABDA_APP_DEPLOYMENT" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --parameters "$ABDA_GATE_ROOT/source/deploy/azure/app.bicepparam" \
    --result-format ResourceIdOnly --no-pretty-print --output json \
    >"$ABDA_GATE_ROOT/app-what-if.json"

  ABDA_MIGRATION_RESOURCE_ID="/subscriptions/$ABDA_EXPECTED_SUBSCRIPTION/resourceGroups/$ABDA_RESOURCE_GROUP/providers/Microsoft.App/jobs/$ABDA_MIGRATION_JOB_NAME"
  ABDA_APP_RESOURCE_ID="/subscriptions/$ABDA_EXPECTED_SUBSCRIPTION/resourceGroups/$ABDA_RESOURCE_GROUP/providers/Microsoft.App/containerApps/$ABDA_APP_NAME"
  abda_validate_what_if \
    "$ABDA_GATE_ROOT/migration-what-if.json" "$ABDA_MIGRATION_RESOURCE_ID" 'Migration job'
  abda_validate_what_if \
    "$ABDA_GATE_ROOT/app-what-if.json" "$ABDA_APP_RESOURCE_ID" 'Web application'

  printf '\nThis gate will now:\n'
  printf '  1. Create or update one manual migration job at the verified image digest.\n'
  printf '  2. Run it once to migrate the database and provision the restricted web role.\n'
  printf '  3. Create or update one public Container App with one minimum replica.\n'
  printf '  4. Keep trial activation and OpenRouter failover disabled.\n'
  printf 'It will not delete resources or change Auth0, Cloudflare, or DNS.\n'
  printf 'The job execution and web replica incur Azure usage charges.\n'
  IFS= read -r -p \
    'Type DEPLOY_ABDA_STAGING_APPLICATION to continue, or press Enter to cancel: ' \
    ABDA_DEPLOY_CONFIRMATION
  [[ "$ABDA_DEPLOY_CONFIRMATION" == 'DEPLOY_ABDA_STAGING_APPLICATION' ]] || {
    printf 'Cancelled without deploying the migration job or web application.\n'
    return 0
  }

  ABDA_GATE_SECTION='migration job deployment'
  printf '\n[7/10] Deploying and verifying the manual migration job...\n'
  az deployment group create \
    --name "$ABDA_MIGRATION_DEPLOYMENT" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --parameters "$ABDA_GATE_ROOT/source/deploy/azure/migration-job.bicepparam" \
    --mode Incremental --output none
  az containerapp job show \
    --name "$ABDA_MIGRATION_JOB_NAME" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_GATE_ROOT/job.json"
  abda_validate_job "$ABDA_GATE_ROOT/job.json"

  ABDA_GATE_SECTION='migration execution'
  printf '\n[8/10] Running the database migration and restricted-role provisioning...\n'
  ABDA_MIGRATION_EXECUTION="$(az containerapp job start \
    --name "$ABDA_MIGRATION_JOB_NAME" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --query name --output tsv)"
  [[ -n "$ABDA_MIGRATION_EXECUTION" ]] || \
    abda_fail 'Azure did not return a migration execution name'
  printf 'Migration execution: %s\n' "$ABDA_MIGRATION_EXECUTION"

  ABDA_LAST_MIGRATION_STATUS=''
  ABDA_MIGRATION_SUCCEEDED=0
  for _ in $(seq 1 210); do
    if ABDA_MIGRATION_STATUS="$(az containerapp job execution show \
      --name "$ABDA_MIGRATION_JOB_NAME" \
      --resource-group "$ABDA_RESOURCE_GROUP" \
      --job-execution-name "$ABDA_MIGRATION_EXECUTION" \
      --query properties.status --output tsv 2>/dev/null)"; then
      if [[ "$ABDA_MIGRATION_STATUS" != "$ABDA_LAST_MIGRATION_STATUS" ]]; then
        printf 'Migration state: %s\n' "$ABDA_MIGRATION_STATUS"
        ABDA_LAST_MIGRATION_STATUS=$ABDA_MIGRATION_STATUS
      fi
      case "$ABDA_MIGRATION_STATUS" in
        Succeeded)
          ABDA_MIGRATION_SUCCEEDED=1
          break
          ;;
        Failed|Stopped)
          abda_fail "migration execution ended in state $ABDA_MIGRATION_STATUS"
          ;;
      esac
    fi
    sleep 5
  done
  (( ABDA_MIGRATION_SUCCEEDED == 1 )) || \
    abda_fail 'migration execution did not succeed before the timeout'

  ABDA_GATE_SECTION='web application deployment'
  printf '\n[9/10] Deploying the web application after the successful migration...\n'
  unset ABDA_DEPLOY_POSTGRES_ADMIN_PASSWORD
  az deployment group create \
    --name "$ABDA_APP_DEPLOYMENT" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --parameters "$ABDA_GATE_ROOT/source/deploy/azure/app.bicepparam" \
    --mode Incremental --output none

  ABDA_APP_READY=0
  ABDA_LAST_APP_STATUS=''
  for _ in $(seq 1 180); do
    az containerapp show \
      --name "$ABDA_APP_NAME" \
      --resource-group "$ABDA_RESOURCE_GROUP" \
      --output json >"$ABDA_GATE_ROOT/app.json"
    ABDA_APP_STATUS="$(python3 - "$ABDA_GATE_ROOT/app.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    app = json.load(handle)
properties = app.get("properties") or {}
print(
    "|".join(
        str(value or "")
        for value in (
            properties.get("provisioningState"),
            properties.get("latestRevisionName"),
            properties.get("latestReadyRevisionName"),
        )
    )
)
PY
    )"
    if [[ "$ABDA_APP_STATUS" != "$ABDA_LAST_APP_STATUS" ]]; then
      printf 'Web application state: %s\n' "$ABDA_APP_STATUS"
      ABDA_LAST_APP_STATUS=$ABDA_APP_STATUS
    fi
    IFS='|' read -r ABDA_PROVISIONING_STATE ABDA_LATEST_REVISION ABDA_READY_REVISION \
      <<<"$ABDA_APP_STATUS"
    if [[ "$ABDA_PROVISIONING_STATE" == 'Failed' ]]; then
      abda_fail 'the web application provisioning state is Failed'
    fi
    if [[ "$ABDA_PROVISIONING_STATE" == 'Succeeded' &&
          -n "$ABDA_LATEST_REVISION" &&
          "$ABDA_LATEST_REVISION" == "$ABDA_READY_REVISION" ]]; then
      ABDA_APP_READY=1
      break
    fi
    sleep 5
  done
  (( ABDA_APP_READY == 1 )) || \
    abda_fail 'the web application did not produce a ready latest revision before the timeout'
  abda_validate_application "$ABDA_GATE_ROOT/app.json"

  ABDA_GATE_SECTION='generated-origin acceptance'
  printf '\n[10/10] Checking the generated HTTPS origin, safe configuration, and protected metrics...\n'
  abda_smoke_generated_origin "$ABDA_GATE_ROOT"

  ABDA_APP_DEPLOYMENT_STATE="$(az deployment group show \
    --name "$ABDA_APP_DEPLOYMENT" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --query properties.provisioningState --output tsv)"
  ABDA_MIGRATION_DEPLOYMENT_STATE="$(az deployment group show \
    --name "$ABDA_MIGRATION_DEPLOYMENT" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --query properties.provisioningState --output tsv)"

  printf '\nABDA-NL Gate 3 staging application status:\n'
  printf 'script_revision: %s\n' "$ABDA_GATE_SCRIPT_REVISION"
  printf 'source_commit: %s\n' "$ABDA_SOURCE_COMMIT"
  printf 'image_digest: sha256:%s\n' "$ABDA_IMAGE_SHA256"
  printf 'subscription_id: %s\n' "$ABDA_EXPECTED_SUBSCRIPTION"
  printf 'resource_group: %s\n' "$ABDA_RESOURCE_GROUP"
  printf 'migration_deployment_state: %s\n' "$ABDA_MIGRATION_DEPLOYMENT_STATE"
  printf 'migration_execution: %s\n' "$ABDA_MIGRATION_EXECUTION"
  printf 'migration_execution_state: Succeeded\n'
  printf 'application_deployment_state: %s\n' "$ABDA_APP_DEPLOYMENT_STATE"
  printf 'application_revision: %s\n' "$ABDA_READY_REVISION"
  printf 'application_origin: %s\n' "$ABDA_GENERATED_ORIGIN"
  printf 'trial_activation_enabled: false\n'
  printf 'openrouter_failover_enabled: false\n'
  printf 'generated_origin_acceptance: passed\n'
  printf 'result: STAGING_APPLICATION_READY_CUSTOM_DOMAIN_NOT_CONFIGURED\n'
  printf 'Stop here. Send this status and the shell exit code to Codex.\n'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_gate_main "$@"
fi
