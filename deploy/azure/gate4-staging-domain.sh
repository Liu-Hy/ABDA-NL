#!/usr/bin/env bash

# Resume-safe staging custom-domain gate for demo.abda-nl.org. The script
# reports the next manual checkpoint when DNS or Auth0 is not ready, and it
# mutates Azure only after an exact confirmation for the current stage.

ABDA_DOMAIN_SCRIPT_REVISION='1'
ABDA_DOMAIN_SOURCE_COMMIT='9abd0264c715596401d87b83d08ed2e82ab5e34b'
ABDA_DOMAIN_BASE_GATE_SHA256='9edf0eeb385a60184e7ee53f243e34e410a5ccbb26f8a991edc097676fecf0fa'
ABDA_DOMAIN_APP_BICEP_SHA256='c18cccafb53e13f9366f6b77fb472b330f8cade0861d3ab07e5dea0141ced6f2'
ABDA_DOMAIN_APP_PARAMETERS_SHA256='5c04b1e73346c0eec704fecfc82ad155423c5ca8859fc274afbebb6c209f801a'
ABDA_DOMAIN_ROOT=''

abda_domain_cleanup() {
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
  if [[ "${ABDA_DOMAIN_ROOT:-}" == /tmp/abda-nl-domain.* &&
        -d "${ABDA_DOMAIN_ROOT:-}" ]]; then
    rm -rf -- "$ABDA_DOMAIN_ROOT"
  fi
  printf '\nGate 4 shell exit code: %s\n' "$exit_code"
}

abda_domain_error() {
  local exit_code=$?
  trap - ERR
  printf '\nSTOP: Gate 4 failed in section: %s\n' \
    "${ABDA_DOMAIN_SECTION:-unknown}" >&2
  printf '%s\n' \
    'Do not delete resources or improvise a recovery command.' \
    'Send the visible status and shell exit code to Codex.' >&2
  exit "$exit_code"
}

abda_domain_interrupt() {
  trap - ERR INT
  printf '\nSTOP: Gate 4 was interrupted in section: %s\n' \
    "${ABDA_DOMAIN_SECTION:-unknown}" >&2
  exit 130
}

abda_domain_bootstrap_fail() {
  printf 'STOP: %s\n' "$*" >&2
  return 1
}

abda_domain_set_constants() {
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
  ABDA_GENERATED_HOSTNAME='abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io'
  ABDA_GENERATED_ORIGIN="https://$ABDA_GENERATED_HOSTNAME"
  ABDA_CUSTOM_HOSTNAME='demo.abda-nl.org'
  ABDA_CUSTOM_ORIGIN="https://$ABDA_CUSTOM_HOSTNAME"
  ABDA_SERVICE_DOMAIN='abda-nl.org'
  ABDA_SOURCE_REPOSITORY='https://github.com/Liu-Hy/ABDA-NL.git'
  ABDA_SOURCE_COMMIT=$ABDA_DOMAIN_SOURCE_COMMIT
  ABDA_IMAGE_REPOSITORY='ghcr.io/liu-hy/abda-nl'
  ABDA_IMAGE_SHA256='71f759c7bbfe25cc2ae974f006b8fed853ef87e5db260fc875fa3f50257739f9'
  ABDA_BICEP_VERSION='v0.46.1'
  ABDA_OIDC_METADATA_URL='https://login.abda-nl.org/.well-known/openid-configuration'
  ABDA_OIDC_ISSUER='https://login.abda-nl.org/'
  ABDA_OPENROUTER_BUDGET_MICROUSD='500000000'
  ABDA_GATE_ROOT=$ABDA_DOMAIN_ROOT
}

abda_domain_validate_healthy_app() {
  local app_path=$1
  local revision_path=$2
  local replicas_path=$3
  python3 - "$app_path" "$revision_path" "$replicas_path" \
    "$ABDA_APP_NAME" "$ABDA_GENERATED_HOSTNAME" "$ABDA_CUSTOM_HOSTNAME" \
    "${ABDA_IMAGE_REPOSITORY}@sha256:${ABDA_IMAGE_SHA256}" <<'PY'
import json
import sys

(
    app_path,
    revision_path,
    replicas_path,
    expected_app,
    generated_hostname,
    custom_hostname,
    expected_image,
) = sys.argv[1:]


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


app = load(app_path)
revision = load(revision_path)
replicas = load(replicas_path)
properties = app.get("properties") or {}
configuration = properties.get("configuration") or {}
ingress = configuration.get("ingress") or {}
containers = (properties.get("template") or {}).get("containers") or []

if app.get("name") != expected_app or len(containers) != 1:
    raise SystemExit("STOP: the Container App identity or container count changed")
if properties.get("provisioningState") != "Succeeded":
    raise SystemExit("STOP: the Container App provisioning state is not Succeeded")
if properties.get("runningStatus") != "Running":
    raise SystemExit("STOP: the Container App running status is not Running")
latest = str(properties.get("latestRevisionName") or "")
ready = str(properties.get("latestReadyRevisionName") or "")
if not latest or latest != ready or revision.get("name") != latest:
    raise SystemExit("STOP: the latest Container App revision is not ready")

revision_properties = revision.get("properties") or {}
if revision_properties.get("active") is not True:
    raise SystemExit("STOP: the latest revision is not active")
if revision_properties.get("healthState") != "Healthy":
    raise SystemExit("STOP: the latest revision is not healthy")
if revision_properties.get("provisioningState") != "Provisioned":
    raise SystemExit("STOP: the latest revision is not provisioned")
if not isinstance(replicas, list) or not 1 <= len(replicas) <= 3:
    raise SystemExit("STOP: the ready revision has an unexpected replica count")
for replica in replicas:
    replica_properties = replica.get("properties") or {}
    if replica_properties.get("runningState") != "Running":
        raise SystemExit("STOP: a current replica is not running")
    replica_containers = replica_properties.get("containers") or []
    if not replica_containers or any(item.get("ready") is not True for item in replica_containers):
        raise SystemExit("STOP: a current replica container is not ready")

if ingress.get("fqdn") != generated_hostname:
    raise SystemExit("STOP: the generated application hostname changed")
if ingress.get("external") is not True or ingress.get("allowInsecure") is not False:
    raise SystemExit("STOP: the public ingress safety settings changed")
if ingress.get("targetPort") != 8000:
    raise SystemExit("STOP: the public ingress target port changed")

container = containers[0]
if container.get("name") != "web" or container.get("image") != expected_image:
    raise SystemExit("STOP: the deployed web image changed")
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
    if http_get.get("port") != 8000 or http_get.get("scheme") != "HTTP":
        raise SystemExit("STOP: a health probe transport changed")
    if http_get.get("httpHeaders") != [
        {"name": "Host", "value": generated_hostname}
    ]:
        raise SystemExit("STOP: a health probe lost its exact trusted Host header")

env = {item.get("name"): item for item in container.get("env") or []}
required_values = {
    "ABDA_ENVIRONMENT": "staging",
    "ABDA_AUTH_MODE": "oidc",
    "ABDA_AUTO_CREATE_DB": "0",
    "ABDA_TRIAL_ENABLED": "false",
    "ABDA_OPENROUTER_FAILOVER_ENABLED": "false",
}
for name, expected in required_values.items():
    if str(env.get(name, {}).get("value", "")).lower() != expected:
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

custom_domains = ingress.get("customDomains") or []
if len(custom_domains) > 1:
    raise SystemExit("STOP: the app has more than one custom-domain binding")
if custom_domains and custom_domains[0].get("name") != custom_hostname:
    raise SystemExit("STOP: the app has an unexpected custom-domain binding")

public_origin = str(env.get("ABDA_PUBLIC_BASE_URL", {}).get("value") or "")
trusted_hosts = str(env.get("ABDA_TRUSTED_HOSTS", {}).get("value") or "")
generated_origin = f"https://{generated_hostname}"
custom_origin = f"https://{custom_hostname}"

if not custom_domains:
    if public_origin != generated_origin or trusted_hosts != generated_hostname:
        raise SystemExit("STOP: unbound application origin settings changed")
    print("unbound")
    raise SystemExit(0)

binding = custom_domains[0]
certificate_id = str(binding.get("certificateId") or "")
binding_type = str(binding.get("bindingType") or "")
if not certificate_id:
    if binding_type not in {"", "Disabled"}:
        raise SystemExit("STOP: the unbound hostname has an unexpected binding type")
    if public_origin != generated_origin or trusted_hosts != generated_hostname:
        raise SystemExit("STOP: partially bound application origin settings changed")
    print("hostname_added")
    raise SystemExit(0)
if binding_type != "SniEnabled":
    raise SystemExit("STOP: the custom hostname is not SNI enabled")

if public_origin == generated_origin and trusted_hosts == generated_hostname:
    print("bound_unpromoted")
elif (
    public_origin == custom_origin
    and trusted_hosts == f"{generated_hostname},{custom_hostname}"
):
    print("promoted")
else:
    raise SystemExit("STOP: custom-domain application origin settings are inconsistent")
PY
}

abda_domain_certificate_id() {
  local app_path=$1
  python3 - "$app_path" "$ABDA_CUSTOM_HOSTNAME" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    app = json.load(handle)
domains = (((app.get("properties") or {}).get("configuration") or {}).get("ingress") or {}).get("customDomains") or []
matches = [item for item in domains if item.get("name") == sys.argv[2]]
if len(matches) == 1:
    print(str(matches[0].get("certificateId") or ""))
PY
}

abda_domain_validate_certificate() {
  local certificates_path=$1
  local expected_id=$2
  python3 - "$certificates_path" "$expected_id" "$ABDA_CUSTOM_HOSTNAME" \
    "$ABDA_ENVIRONMENT_NAME" <<'PY'
import json
import sys

path, expected_id, expected_hostname, expected_environment = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    certificates = json.load(handle)
if not isinstance(certificates, list):
    raise SystemExit("STOP: Azure did not return a managed-certificate list")
matches = [item for item in certificates if str(item.get("id") or "").lower() == expected_id.lower()]
if len(matches) != 1:
    raise SystemExit("STOP: the bound managed certificate is absent or ambiguous")
certificate = matches[0]
expected_fragment = f"/managedEnvironments/{expected_environment}/managedCertificates/".lower()
if expected_fragment not in expected_id.lower():
    raise SystemExit("STOP: the certificate belongs to an unexpected environment")
properties = certificate.get("properties") or {}
subject = str(properties.get("subjectName") or "")
if subject.lower().removeprefix("cn=") != expected_hostname.lower():
    raise SystemExit("STOP: the managed certificate subject changed")
if properties.get("provisioningState") != "Succeeded":
    raise SystemExit("STOP: the managed certificate is not ready")
if properties.get("domainControlValidation") != "CNAME":
    raise SystemExit("STOP: the managed certificate validation method changed")
PY
}

abda_domain_check_dns() {
  local verification_id=$1
  local nameserver=''
  local cname=''
  local txt=''
  local public_cname=''
  local caa=''
  local dns_ready=1
  local -a nameservers=()

  mapfile -t nameservers < <(dig +short "$ABDA_SERVICE_DOMAIN" NS | \
    sed 's/[.]$//' | LC_ALL=C sort -u)
  if (( ${#nameservers[@]} < 2 )); then
    printf 'DNS check: fewer than two authoritative nameservers resolved.\n'
    dns_ready=0
  fi
  for nameserver in "${nameservers[@]}"; do
    cname="$(dig +short "@$nameserver" "$ABDA_CUSTOM_HOSTNAME" CNAME | \
      sed -n '1p')"
    txt="$(dig +short "@$nameserver" "asuid.$ABDA_CUSTOM_HOSTNAME" TXT | \
      sed -n '1p' | tr -d '"')"
    printf 'authoritative_nameserver: %s\n' "$nameserver"
    printf 'authoritative_cname: %s\n' "${cname:-ABSENT}"
    printf 'authoritative_asuid_txt: %s\n' "${txt:-ABSENT}"
    if [[ "${cname%.}" != "$ABDA_GENERATED_HOSTNAME" ||
          "$txt" != "$verification_id" ]]; then
      dns_ready=0
    fi
  done

  public_cname="$(dig +short "$ABDA_CUSTOM_HOSTNAME" CNAME | sed -n '1p')"
  printf 'recursive_cname: %s\n' "${public_cname:-ABSENT}"
  if [[ "${public_cname%.}" != "$ABDA_GENERATED_HOSTNAME" ]]; then
    dns_ready=0
  fi

  caa="$(dig +short "$ABDA_SERVICE_DOMAIN" CAA)"
  printf 'root_caa: %s\n' "${caa:-ABSENT_PERMITTED}"
  if [[ -n "$caa" ]] && ! grep -Eiq '^[[:space:]]*[0-9]+[[:space:]]+issue[[:space:]]+"?digicert[.]com([;"]|$)' <<<"$caa"; then
    printf '%s\n' \
      'DNS check: a root CAA record exists but does not authorize DigiCert.'
    dns_ready=0
  fi

  if (( dns_ready == 1 )); then
    return 0
  fi
  return 1
}

abda_domain_print_dns_checkpoint() {
  local verification_id=$1
  printf '\nABDA-NL Gate 4 Cloudflare DNS checkpoint:\n'
  printf 'script_revision: %s\n' "$ABDA_DOMAIN_SCRIPT_REVISION"
  printf 'custom_hostname: %s\n' "$ABDA_CUSTOM_HOSTNAME"
  printf 'cname_name: demo\n'
  printf 'cname_target: %s\n' "$ABDA_GENERATED_HOSTNAME"
  printf 'cname_proxy_status: DNS only (gray cloud)\n'
  printf 'cname_ttl: Auto\n'
  printf 'txt_name: asuid.demo\n'
  printf 'txt_value: %s\n' "$verification_id"
  printf 'txt_ttl: Auto\n'
  printf 'result: WAITING_FOR_CLOUDFLARE_DNS\n'
  printf '%s\n' \
    'Create or correct only these two records in Cloudflare.' \
    'If a CAA warning appeared above, also add CAA @ 0 issue digicert.com.' \
    'Do not change Auth0 yet. Rerun this same Gate 4 script after DNS resolves.'
}

abda_domain_print_auth0_checkpoint() {
  printf '\nABDA-NL Gate 4 Auth0 transition checkpoint:\n'
  printf 'application: ABDA-NL Public Service\n'
  printf 'allowed_callback_urls:\n'
  printf '  %s/auth/callback\n' "$ABDA_GENERATED_ORIGIN"
  printf '  %s/auth/callback\n' "$ABDA_CUSTOM_ORIGIN"
  printf 'allowed_logout_urls:\n'
  printf '  %s/\n' "$ABDA_GENERATED_ORIGIN"
  printf '  %s/\n' "$ABDA_CUSTOM_ORIGIN"
  printf 'allowed_web_origins:\n'
  printf '  %s\n' "$ABDA_GENERATED_ORIGIN"
  printf '  %s\n' "$ABDA_CUSTOM_ORIGIN"
  printf 'result: DOMAIN_BOUND_AUTH0_UPDATE_REQUIRED\n'
  printf '%s\n' \
    'In Auth0, keep every generated-origin value and add each exact custom-origin value.' \
    'Use comma-separated exact URLs. Do not use a wildcard or remove the generated origin.' \
    'Save Changes, then rerun this same Gate 4 script.'
}

abda_domain_wait_for_binding() {
  local attempt=0
  local certificate_id=''
  local certificate_state=''

  for attempt in $(seq 1 60); do
    az containerapp show \
      --name "$ABDA_APP_NAME" \
      --resource-group "$ABDA_RESOURCE_GROUP" \
      --output json >"$ABDA_DOMAIN_ROOT/app-after-bind.json"
    az containerapp env certificate list \
      --name "$ABDA_ENVIRONMENT_NAME" \
      --resource-group "$ABDA_RESOURCE_GROUP" \
      --managed-certificates-only --output json \
      >"$ABDA_DOMAIN_ROOT/certificates-after-bind.json"
    certificate_id="$(abda_domain_certificate_id \
      "$ABDA_DOMAIN_ROOT/app-after-bind.json")"
    if [[ -n "$certificate_id" ]]; then
      certificate_state="$(python3 - \
        "$ABDA_DOMAIN_ROOT/certificates-after-bind.json" "$certificate_id" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    values = json.load(handle)
matches = [item for item in values if str(item.get("id") or "").lower() == sys.argv[2].lower()]
if len(matches) == 1:
    print(str((matches[0].get("properties") or {}).get("provisioningState") or ""))
PY
)"
      if [[ "$certificate_state" == 'Succeeded' ]]; then
        ABDA_CUSTOM_DOMAIN_CERTIFICATE_ID=$certificate_id
        export ABDA_CUSTOM_DOMAIN_CERTIFICATE_ID
        return 0
      fi
    fi
    printf 'Managed certificate state: %s (attempt %s/60)\n' \
      "${certificate_state:-waiting}" "$attempt"
    sleep 10
  done
  abda_fail 'the managed custom-domain certificate did not become ready'
}

abda_domain_load_current_configuration() {
  local app_path=$1
  local secrets_path=$2
  local values_path="$ABDA_DOMAIN_ROOT/runtime-values.bin"

  python3 - "$app_path" "$secrets_path" "$values_path" \
    "$ABDA_POSTGRES_HOST" <<'PY'
import json
import os
import re
import sys
from urllib.parse import parse_qs, unquote, urlsplit

app_path, secrets_path, output_path, expected_postgres_host = sys.argv[1:]
with open(app_path, encoding="utf-8") as handle:
    app = json.load(handle)
with open(secrets_path, encoding="utf-8") as handle:
    raw_secrets = json.load(handle)
if not isinstance(raw_secrets, list):
    raise SystemExit("STOP: Azure did not return a secret list")
secrets = {str(item.get("name") or ""): str(item.get("value") or "") for item in raw_secrets}
expected_secret_names = {
    "database-url",
    "session-secret",
    "mcp-token-pepper",
    "metrics-token",
    "oidc-client-secret",
    "foundry-api-key",
    "openrouter-api-key",
}
if set(secrets) != expected_secret_names or any(not value for value in secrets.values()):
    raise SystemExit("STOP: the deployed application secret inventory changed")

containers = ((app.get("properties") or {}).get("template") or {}).get("containers") or []
if len(containers) != 1:
    raise SystemExit("STOP: the deployed application container inventory changed")
env = {str(item.get("name") or ""): item for item in containers[0].get("env") or []}

database_url = urlsplit(secrets["database-url"])
query = parse_qs(database_url.query, keep_blank_values=True)
if (
    database_url.scheme != "postgresql+psycopg"
    or database_url.username != "abda_app"
    or database_url.hostname != expected_postgres_host
    or database_url.port != 5432
    or database_url.path != "/abda"
    or query != {"sslmode": ["require"]}
    or not database_url.password
):
    raise SystemExit("STOP: the deployed database secret boundary changed")

values = {
    "ABDA_DEPLOY_POSTGRES_APP_PASSWORD": unquote(database_url.password),
    "ABDA_DEPLOY_SESSION_SECRET": secrets["session-secret"],
    "ABDA_DEPLOY_MCP_TOKEN_PEPPER": secrets["mcp-token-pepper"],
    "ABDA_DEPLOY_METRICS_TOKEN": secrets["metrics-token"],
    "ABDA_DEPLOY_OIDC_CLIENT_SECRET": secrets["oidc-client-secret"],
    "ABDA_DEPLOY_FOUNDRY_API_KEY": secrets["foundry-api-key"],
    "ABDA_DEPLOY_OPENROUTER_API_KEY": secrets["openrouter-api-key"],
    "ABDA_DEPLOY_OIDC_CLIENT_ID": str(env.get("ABDA_OIDC_CLIENT_ID", {}).get("value") or ""),
    "ABDA_DEPLOY_FOUNDRY_ENDPOINT": str(env.get("AZURE_ANTHROPIC_ENDPOINT", {}).get("value") or ""),
    "ABDA_DEPLOY_CLAUDE_DEPLOYMENT": str(env.get("ANTHROPIC_FOUNDRY_CLAUDE_SONNET_4_6_MODEL", {}).get("value") or ""),
}
endpoint = urlsplit(values["ABDA_DEPLOY_FOUNDRY_ENDPOINT"])
if (
    endpoint.scheme != "https"
    or not endpoint.hostname
    or endpoint.username is not None
    or endpoint.password is not None
    or endpoint.query
    or endpoint.fragment
    or not (
        endpoint.hostname.endswith(".services.ai.azure.com")
        or endpoint.hostname.endswith(".openai.azure.com")
    )
):
    raise SystemExit("STOP: the deployed Foundry endpoint boundary changed")
if values["ABDA_DEPLOY_CLAUDE_DEPLOYMENT"] != "claude-sonnet-4-6":
    raise SystemExit("STOP: the deployed Foundry model name changed")
if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", values["ABDA_DEPLOY_OIDC_CLIENT_ID"]):
    raise SystemExit("STOP: the deployed Auth0 Client ID is invalid")
for name, value in values.items():
    minimum = 32 if name in {
        "ABDA_DEPLOY_POSTGRES_APP_PASSWORD",
        "ABDA_DEPLOY_SESSION_SECRET",
        "ABDA_DEPLOY_MCP_TOKEN_PEPPER",
        "ABDA_DEPLOY_METRICS_TOKEN",
    } else 16 if name in {
        "ABDA_DEPLOY_OIDC_CLIENT_SECRET",
        "ABDA_DEPLOY_FOUNDRY_API_KEY",
        "ABDA_DEPLOY_OPENROUTER_API_KEY",
    } else 1
    if len(value) < minimum or value != value.strip() or "\0" in value or "\n" in value or "\r" in value:
        raise SystemExit(f"STOP: deployed value {name} is invalid")

with open(output_path, "wb") as handle:
    os.chmod(output_path, 0o600)
    for name, value in values.items():
        handle.write(name.encode("utf-8") + b"\0" + value.encode("utf-8") + b"\0")
PY

  local variable_name=''
  local variable_value=''
  while IFS= read -r -d '' variable_name && \
        IFS= read -r -d '' variable_value; do
    case "$variable_name" in
      ABDA_DEPLOY_POSTGRES_APP_PASSWORD|ABDA_DEPLOY_SESSION_SECRET|\
      ABDA_DEPLOY_MCP_TOKEN_PEPPER|ABDA_DEPLOY_METRICS_TOKEN|\
      ABDA_DEPLOY_OIDC_CLIENT_SECRET|ABDA_DEPLOY_FOUNDRY_API_KEY|\
      ABDA_DEPLOY_OPENROUTER_API_KEY|ABDA_DEPLOY_OIDC_CLIENT_ID|\
      ABDA_DEPLOY_FOUNDRY_ENDPOINT|ABDA_DEPLOY_CLAUDE_DEPLOYMENT)
        printf -v "$variable_name" '%s' "$variable_value"
        export "$variable_name"
        ;;
      *)
        abda_fail 'the protected runtime-value reader returned an unexpected name'
        ;;
    esac
  done <"$values_path"
}

abda_domain_validate_promotion_what_if() {
  local result_path=$1
  local expected_id=$2
  python3 - "$result_path" "$expected_id" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    document = json.load(handle)
payload = document.get("properties", document)
if payload.get("status") not in {None, "Succeeded"}:
    raise SystemExit("STOP: custom-domain what-if did not succeed")
changes = payload.get("changes")
if not isinstance(changes, list):
    raise SystemExit("STOP: custom-domain what-if did not return a changes list")

expected_id = sys.argv[2].lower()
mutations = []
problems = []
known = {"Create", "Delete", "Deploy", "Ignore", "Modify", "NoChange", "Unsupported"}
for change in changes:
    if not isinstance(change, dict):
        problems.append("malformed change entry")
        continue
    change_type = str(change.get("changeType") or "")
    resource_id = str(
        change.get("resourceId")
        or (change.get("after") or {}).get("id")
        or (change.get("before") or {}).get("id")
        or ""
    )
    if change_type not in known:
        problems.append(f"unknown change type {change_type!r}")
    elif change_type in {"Delete", "Unsupported", "Create"}:
        problems.append(f"unexpected {change_type} {resource_id}")
    elif change_type in {"Deploy", "Modify"}:
        mutations.append((change_type, resource_id))
        if resource_id.lower() != expected_id:
            problems.append(f"unexpected {change_type} target {resource_id}")

print("Custom-domain promotion planned Azure changes:")
for change_type, resource_id in mutations:
    print(f"  {change_type:<7} {resource_id}")
if len(mutations) != 1:
    problems.append(f"expected one Container App mutation, observed {len(mutations)}")
if problems:
    for problem in problems:
        print(f"STOP: {problem}", file=sys.stderr)
    raise SystemExit(1)
PY
}

abda_domain_wait_for_promoted_revision() {
  local previous_revision=$1
  local attempt=0
  local state=''

  for attempt in $(seq 1 60); do
    az containerapp show \
      --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
      --output json >"$ABDA_DOMAIN_ROOT/promoted-app.json"
    ABDA_PROMOTED_REVISION="$(python3 - \
      "$ABDA_DOMAIN_ROOT/promoted-app.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle)
print(str((value.get("properties") or {}).get("latestRevisionName") or ""))
PY
)"
    if [[ -n "$ABDA_PROMOTED_REVISION" &&
          "$ABDA_PROMOTED_REVISION" != "$previous_revision" ]]; then
      az containerapp revision show \
        --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
        --revision "$ABDA_PROMOTED_REVISION" --output json \
        >"$ABDA_DOMAIN_ROOT/promoted-revision.json"
      az containerapp replica list \
        --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
        --revision "$ABDA_PROMOTED_REVISION" --output json \
        >"$ABDA_DOMAIN_ROOT/promoted-replicas.json"
      if state="$(abda_domain_validate_healthy_app \
        "$ABDA_DOMAIN_ROOT/promoted-app.json" \
        "$ABDA_DOMAIN_ROOT/promoted-revision.json" \
        "$ABDA_DOMAIN_ROOT/promoted-replicas.json")" &&
        [[ "$state" == 'promoted' ]]; then
        export ABDA_PROMOTED_REVISION
        return 0
      fi
    fi
    printf 'Promoted revision state: waiting (attempt %s/60)\n' "$attempt"
    sleep 10
  done
  abda_fail 'the custom-domain application revision did not become healthy'
}

abda_domain_smoke_custom_origin() {
  local saved_origin=$ABDA_GENERATED_ORIGIN
  ABDA_GENERATED_ORIGIN=$ABDA_CUSTOM_ORIGIN
  abda_smoke_generated_origin "$ABDA_DOMAIN_ROOT/custom-origin"
  ABDA_GENERATED_ORIGIN=$saved_origin

  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$saved_origin/health/ready" \
    --output "$ABDA_DOMAIN_ROOT/generated-origin-ready.json"
  python3 - "$ABDA_DOMAIN_ROOT/generated-origin-ready.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    if json.load(handle) != {"status": "ready"}:
        raise SystemExit("STOP: the generated-origin readiness response changed")
PY
}

abda_domain_bind() {
  local state=$1
  printf '\nThis mutation adds only %s and its free managed certificate.\n' \
    "$ABDA_CUSTOM_HOSTNAME"
  printf '%s\n' \
    'It does not redeploy application code, rerun migrations, change Auth0,' \
    'enable trial credit, enable OpenRouter failover, or delete a resource.' \
    'Type BIND_ABDA_STAGING_DOMAIN to continue, or press Enter to cancel.'
  local confirmation=''
  IFS= read -r -p 'Confirmation: ' confirmation
  if [[ "$confirmation" != 'BIND_ABDA_STAGING_DOMAIN' ]]; then
    printf 'Cancelled without changing Azure.\n'
    return 0
  fi

  ABDA_DOMAIN_SECTION='custom hostname and managed certificate binding'
  if [[ "$state" == 'unbound' ]]; then
    az containerapp hostname add \
      --name "$ABDA_APP_NAME" \
      --resource-group "$ABDA_RESOURCE_GROUP" \
      --hostname "$ABDA_CUSTOM_HOSTNAME" --output none
  fi
  az containerapp hostname bind \
    --name "$ABDA_APP_NAME" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --hostname "$ABDA_CUSTOM_HOSTNAME" \
    --environment "$ABDA_ENVIRONMENT_NAME" \
    --validation-method CNAME --output none

  ABDA_DOMAIN_SECTION='managed certificate verification'
  abda_domain_wait_for_binding
  abda_domain_validate_certificate \
    "$ABDA_DOMAIN_ROOT/certificates-after-bind.json" \
    "$ABDA_CUSTOM_DOMAIN_CERTIFICATE_ID"
  abda_domain_print_auth0_checkpoint
}

abda_domain_promote() {
  local app_path=$1
  local certificate_id=$2
  local previous_revision=''
  local auth0_confirmation=''
  local deployment_confirmation=''

  abda_domain_print_auth0_checkpoint
  printf '%s\n' \
    'Type AUTH0_CUSTOM_URLS_SAVED only if all six exact entries above are saved,' \
    'or press Enter to stop without reading secrets or changing Azure.'
  IFS= read -r -p 'Auth0 checkpoint: ' auth0_confirmation
  if [[ "$auth0_confirmation" != 'AUTH0_CUSTOM_URLS_SAVED' ]]; then
    printf 'Stopped without changing Azure.\n'
    return 0
  fi

  ABDA_DOMAIN_SECTION='protected current-configuration loading'
  printf '\nLoading existing application secrets directly from Azure without displaying them...\n'
  az containerapp secret list \
    --name "$ABDA_APP_NAME" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --show-values --output json >"$ABDA_DOMAIN_ROOT/current-secrets.json"
  abda_domain_load_current_configuration \
    "$app_path" "$ABDA_DOMAIN_ROOT/current-secrets.json"
  printf 'Loaded and validated the existing secret inventory in the protected temporary directory.\n'

  export ABDA_DEPLOY_LOCATION=$ABDA_LOCATION
  export ABDA_DEPLOY_APP_NAME=$ABDA_APP_NAME
  export ABDA_DEPLOY_ENVIRONMENT_NAME=$ABDA_ENVIRONMENT_NAME
  export ABDA_DEPLOY_IMAGE_REPOSITORY=$ABDA_IMAGE_REPOSITORY
  export ABDA_DEPLOY_IMAGE_SHA256=$ABDA_IMAGE_SHA256
  export ABDA_DEPLOY_ENVIRONMENT='staging'
  export ABDA_DEPLOY_CUSTOM_HOSTNAME=$ABDA_CUSTOM_HOSTNAME
  export ABDA_DEPLOY_CUSTOM_DOMAIN_CERTIFICATE_ID=$certificate_id
  export ABDA_DEPLOY_OIDC_METADATA_URL=$ABDA_OIDC_METADATA_URL
  export ABDA_DEPLOY_OIDC_ISSUER=$ABDA_OIDC_ISSUER
  export ABDA_DEPLOY_POSTGRES_HOST=$ABDA_POSTGRES_HOST
  export ABDA_DEPLOY_POSTGRES_APP_LOGIN='abda_app'
  export ABDA_DEPLOY_OPENROUTER_BUDGET_MICROUSD=$ABDA_OPENROUTER_BUDGET_MICROUSD
  export ABDA_DEPLOY_TRIAL_ENABLED='false'
  export ABDA_DEPLOY_TRIAL_MAX_USERS='100'
  export ABDA_DEPLOY_TRIAL_BUDGET_MICROUSD='500000000'
  export ABDA_DEPLOY_OPENROUTER_FAILOVER_ENABLED='false'

  if ! az bicep version 2>/dev/null | grep -Fq "${ABDA_BICEP_VERSION#v}"; then
    az bicep install --version "$ABDA_BICEP_VERSION"
  fi
  az bicep version | grep -Fq "${ABDA_BICEP_VERSION#v}" ||
    abda_fail "Bicep $ABDA_BICEP_VERSION is not active"

  ABDA_DOMAIN_SECTION='custom-domain application deployment review'
  az deployment group validate \
    --name "$ABDA_APP_DEPLOYMENT" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --parameters "$ABDA_DOMAIN_ROOT/source/deploy/azure/app.bicepparam" \
    --output none
  az deployment group what-if \
    --name "$ABDA_APP_DEPLOYMENT" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --parameters "$ABDA_DOMAIN_ROOT/source/deploy/azure/app.bicepparam" \
    --result-format ResourceIdOnly --no-pretty-print --output json \
    >"$ABDA_DOMAIN_ROOT/domain-promotion-what-if.json"
  local app_resource_id="/subscriptions/$ABDA_EXPECTED_SUBSCRIPTION/resourceGroups/$ABDA_RESOURCE_GROUP/providers/Microsoft.App/containerApps/$ABDA_APP_NAME"
  abda_domain_validate_promotion_what_if \
    "$ABDA_DOMAIN_ROOT/domain-promotion-what-if.json" "$app_resource_id"

  printf '%s\n' \
    'This deployment preserves the exact image, secrets, certificate, and disabled spending flags.' \
    'It changes the canonical origin and trusted-host list on this Container App only.' \
    'Type PROMOTE_ABDA_STAGING_DOMAIN to continue, or press Enter to cancel.'
  IFS= read -r -p 'Deployment confirmation: ' deployment_confirmation
  if [[ "$deployment_confirmation" != 'PROMOTE_ABDA_STAGING_DOMAIN' ]]; then
    printf 'Cancelled without changing Azure.\n'
    return 0
  fi

  previous_revision="$(python3 - "$app_path" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle)
print(str((value.get("properties") or {}).get("latestRevisionName") or ""))
PY
)"
  ABDA_DOMAIN_SECTION='custom-domain canonical-origin deployment'
  az deployment group create \
    --name "$ABDA_APP_DEPLOYMENT" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --parameters "$ABDA_DOMAIN_ROOT/source/deploy/azure/app.bicepparam" \
    --mode Incremental --output none

  ABDA_DOMAIN_SECTION='promoted revision verification'
  abda_domain_wait_for_promoted_revision "$previous_revision"
  az containerapp env certificate list \
    --name "$ABDA_ENVIRONMENT_NAME" \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --managed-certificates-only --output json \
    >"$ABDA_DOMAIN_ROOT/promoted-certificates.json"
  abda_domain_validate_certificate \
    "$ABDA_DOMAIN_ROOT/promoted-certificates.json" "$certificate_id"

  ABDA_DOMAIN_SECTION='custom and generated origin acceptance'
  mkdir -p "$ABDA_DOMAIN_ROOT/custom-origin"
  abda_domain_smoke_custom_origin

  printf '\nABDA-NL Gate 4 staging custom-domain status:\n'
  printf 'script_revision: %s\n' "$ABDA_DOMAIN_SCRIPT_REVISION"
  printf 'source_commit: %s\n' "$ABDA_DOMAIN_SOURCE_COMMIT"
  printf 'image_digest: sha256:%s\n' "$ABDA_IMAGE_SHA256"
  printf 'subscription_id: %s\n' "$ABDA_EXPECTED_SUBSCRIPTION"
  printf 'resource_group: %s\n' "$ABDA_RESOURCE_GROUP"
  printf 'application_revision: %s\n' "$ABDA_PROMOTED_REVISION"
  printf 'generated_origin: %s\n' "$ABDA_GENERATED_ORIGIN"
  printf 'custom_origin: %s\n' "$ABDA_CUSTOM_ORIGIN"
  printf 'managed_certificate_id: %s\n' "$certificate_id"
  printf 'trial_activation_enabled: false\n'
  printf 'openrouter_failover_enabled: false\n'
  printf 'custom_origin_acceptance: passed\n'
  printf 'generated_origin_readiness: passed\n'
  printf 'result: CUSTOM_DOMAIN_DEPLOYED_BROWSER_AUTH_REQUIRED\n'
  printf '%s\n' \
    'Stop here. Do not remove the generated Auth0 URLs yet.' \
    'Send this status and shell exit code to Codex for browser authentication acceptance.'
}

abda_domain_main() {
  set -Eeuo pipefail
  set +x
  umask 077
  unset HISTFILE
  trap abda_domain_error ERR
  trap abda_domain_cleanup EXIT
  trap abda_domain_interrupt INT
  ABDA_DOMAIN_SECTION='bootstrap'

  printf 'ABDA-NL Gate 4 staging custom-domain script revision: %s\n' \
    "$ABDA_DOMAIN_SCRIPT_REVISION"
  printf '%s\n' \
    'This resume-safe gate reports the next DNS or Auth0 checkpoint.' \
    'It changes Azure only after an exact stage-specific confirmation.' \
    'It never changes Cloudflare, Auth0, migrations, trial credit, or OpenRouter failover.'

  abda_domain_set_constants

  local command_name=''
  for command_name in az curl dig git grep python3 sed sha256sum; do
    command -v "$command_name" >/dev/null 2>&1 ||
      abda_domain_bootstrap_fail "required command is unavailable: $command_name"
  done
  az containerapp hostname bind --help >/dev/null
  az containerapp secret list --help | grep -Fq -- '--show-values'
  az containerapp env certificate list --help >/dev/null

  ABDA_DOMAIN_ROOT="$(mktemp -d /tmp/abda-nl-domain.XXXXXX)"
  chmod 700 "$ABDA_DOMAIN_ROOT"
  git clone --quiet --filter=blob:none --no-checkout \
    "$ABDA_SOURCE_REPOSITORY" "$ABDA_DOMAIN_ROOT/source"
  git -C "$ABDA_DOMAIN_ROOT/source" checkout --quiet --detach \
    "$ABDA_DOMAIN_SOURCE_COMMIT"
  [[ "$(git -C "$ABDA_DOMAIN_ROOT/source" rev-parse HEAD)" == \
      "$ABDA_DOMAIN_SOURCE_COMMIT" ]] ||
    abda_domain_bootstrap_fail 'the checked-out source commit changed'
  (
    cd "$ABDA_DOMAIN_ROOT/source"
    sha256sum --check --quiet <<ABDA_DOMAIN_CHECKSUMS
$ABDA_DOMAIN_BASE_GATE_SHA256  deploy/azure/gate3-staging-application.sh
$ABDA_DOMAIN_APP_BICEP_SHA256  deploy/azure/app.bicep
$ABDA_DOMAIN_APP_PARAMETERS_SHA256  deploy/azure/app.bicepparam
ABDA_DOMAIN_CHECKSUMS
  )

  # The checksum-pinned Gate 3 file supplies established identity,
  # infrastructure, OIDC, and generated-origin acceptance helpers.
  # shellcheck disable=SC1091
  source "$ABDA_DOMAIN_ROOT/source/deploy/azure/gate3-staging-application.sh"
  abda_domain_set_constants

  ABDA_DOMAIN_SECTION='Azure identity and infrastructure verification'
  printf '\n[1/6] Verifying Azure identity and the recovered infrastructure...\n'
  az account show --output json >"$ABDA_DOMAIN_ROOT/account.json"
  abda_validate_identity "$ABDA_DOMAIN_ROOT/account.json"
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
    >"$ABDA_DOMAIN_ROOT/infra-outputs.json"
  az containerapp env show \
    --name "$ABDA_ENVIRONMENT_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_DOMAIN_ROOT/environment.json"
  az postgres flexible-server show \
    --name "${ABDA_POSTGRES_HOST%%.*}" --resource-group "$ABDA_RESOURCE_GROUP" \
    --query '{name:name,state:state,fullyQualifiedDomainName:fullyQualifiedDomainName,publicNetworkAccess:network.publicNetworkAccess}' \
    --output json >"$ABDA_DOMAIN_ROOT/postgres.json"
  az containerapp job list --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_DOMAIN_ROOT/jobs.json"
  az containerapp list --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_DOMAIN_ROOT/apps.json"
  abda_validate_infrastructure \
    "$ABDA_DOMAIN_ROOT/infra-outputs.json" \
    "$ABDA_DOMAIN_ROOT/environment.json" \
    "$ABDA_DOMAIN_ROOT/postgres.json" \
    "$ABDA_DOMAIN_ROOT/jobs.json" "$ABDA_DOMAIN_ROOT/apps.json"

  ABDA_DOMAIN_SECTION='healthy repaired application verification'
  printf '\n[2/6] Verifying the repaired healthy application and exact probe headers...\n'
  az containerapp show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --output json >"$ABDA_DOMAIN_ROOT/current-app.json"
  local current_revision=''
  current_revision="$(python3 - "$ABDA_DOMAIN_ROOT/current-app.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle)
print(str((value.get("properties") or {}).get("latestRevisionName") or ""))
PY
)"
  [[ -n "$current_revision" ]] || abda_fail 'the current revision is absent'
  az containerapp revision show \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --revision "$current_revision" --output json \
    >"$ABDA_DOMAIN_ROOT/current-revision.json"
  az containerapp replica list \
    --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
    --revision "$current_revision" --output json \
    >"$ABDA_DOMAIN_ROOT/current-replicas.json"
  local domain_state=''
  domain_state="$(abda_domain_validate_healthy_app \
    "$ABDA_DOMAIN_ROOT/current-app.json" \
    "$ABDA_DOMAIN_ROOT/current-revision.json" \
    "$ABDA_DOMAIN_ROOT/current-replicas.json")"
  printf 'application_revision: %s\n' "$current_revision"
  printf 'custom_domain_state: %s\n' "$domain_state"

  ABDA_DOMAIN_SECTION='public dependency verification'
  printf '\n[3/6] Rechecking generated-origin readiness and Auth0 discovery...\n'
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_GENERATED_ORIGIN/health/ready" \
    --output "$ABDA_DOMAIN_ROOT/ready.json"
  python3 - "$ABDA_DOMAIN_ROOT/ready.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    if json.load(handle) != {"status": "ready"}:
        raise SystemExit("STOP: the generated origin is not ready")
PY
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 30 \
    "$ABDA_OIDC_METADATA_URL" --output "$ABDA_DOMAIN_ROOT/oidc.json"
  abda_validate_oidc_discovery "$ABDA_DOMAIN_ROOT/oidc.json"

  ABDA_DOMAIN_SECTION='DNS and managed-certificate inspection'
  printf '\n[4/6] Inspecting exact DNS records and current certificate binding...\n'
  local verification_id=''
  verification_id="$(python3 - "$ABDA_DOMAIN_ROOT/current-app.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle)
print(str((value.get("properties") or {}).get("customDomainVerificationId") or ""))
PY
)"
  [[ "$verification_id" =~ ^[A-Za-z0-9_-]{16,512}$ ]] ||
    abda_fail 'the Azure custom-domain verification ID is invalid'

  local dns_ready=0
  if abda_domain_check_dns "$verification_id"; then
    dns_ready=1
    printf 'dns_validation: passed\n'
  else
    printf 'dns_validation: waiting\n'
  fi

  local certificate_id=''
  certificate_id="$(abda_domain_certificate_id \
    "$ABDA_DOMAIN_ROOT/current-app.json")"
  if [[ -n "$certificate_id" ]]; then
    az containerapp env certificate list \
      --name "$ABDA_ENVIRONMENT_NAME" \
      --resource-group "$ABDA_RESOURCE_GROUP" \
      --managed-certificates-only --output json \
      >"$ABDA_DOMAIN_ROOT/current-certificates.json"
    abda_domain_validate_certificate \
      "$ABDA_DOMAIN_ROOT/current-certificates.json" "$certificate_id"
    printf 'managed_certificate: verified\n'
  else
    printf 'managed_certificate: not bound\n'
  fi

  if (( dns_ready != 1 )); then
    abda_domain_print_dns_checkpoint "$verification_id"
    return 0
  fi

  printf '\n[5/6] Selecting the safe next transition from current state...\n'
  case "$domain_state" in
    unbound|hostname_added)
      abda_domain_bind "$domain_state"
      ;;
    bound_unpromoted)
      [[ -n "$certificate_id" ]] ||
        abda_fail 'the bound custom hostname has no certificate ID'
      abda_domain_promote "$ABDA_DOMAIN_ROOT/current-app.json" "$certificate_id"
      ;;
    promoted)
      [[ -n "$certificate_id" ]] ||
        abda_fail 'the promoted custom hostname has no certificate ID'
      ABDA_DOMAIN_SECTION='existing custom-origin acceptance'
      printf '\n[6/6] Revalidating the already promoted custom origin...\n'
      az containerapp secret list \
        --name "$ABDA_APP_NAME" --resource-group "$ABDA_RESOURCE_GROUP" \
        --show-values --output json >"$ABDA_DOMAIN_ROOT/current-secrets.json"
      abda_domain_load_current_configuration \
        "$ABDA_DOMAIN_ROOT/current-app.json" \
        "$ABDA_DOMAIN_ROOT/current-secrets.json"
      mkdir -p "$ABDA_DOMAIN_ROOT/custom-origin"
      abda_domain_smoke_custom_origin
      printf '\nABDA-NL Gate 4 staging custom-domain status:\n'
      printf 'script_revision: %s\n' "$ABDA_DOMAIN_SCRIPT_REVISION"
      printf 'application_revision: %s\n' "$current_revision"
      printf 'generated_origin: %s\n' "$ABDA_GENERATED_ORIGIN"
      printf 'custom_origin: %s\n' "$ABDA_CUSTOM_ORIGIN"
      printf 'managed_certificate_id: %s\n' "$certificate_id"
      printf 'custom_origin_acceptance: passed\n'
      printf 'generated_origin_readiness: passed\n'
      printf 'result: CUSTOM_DOMAIN_DEPLOYED_BROWSER_AUTH_REQUIRED\n'
      ;;
    *)
      abda_fail "unsupported custom-domain state: $domain_state"
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_domain_main "$@"
fi
