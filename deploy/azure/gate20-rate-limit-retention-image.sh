#!/usr/bin/env bash

# Deploy the cumulative service-integrity and account-suspension hardening as
# one image-only Container App update. The shared gate proves that every
# application setting and secret reference remains unchanged and reruns the
# public checks.

set -Eeuo pipefail
set +x
umask 077

ABDA_MCP_IMAGE_SCRIPT_REVISION='6'
ABDA_MCP_IMAGE_SOURCE_COMMIT='ed241c1509739f16b2433ced686da76fe1ed1d94'
ABDA_MCP_IMAGE_OLD_IMAGE_SHA256='a0b3ba24aff06ecf461f86547131d86451c541e306a7ecfc278f280fcef5c0bc'
ABDA_MCP_IMAGE_NEW_IMAGE_SHA256='b7025d4322e05a698e79eb120a233c68cf638d5cdd44c8f58223681ff15ae1c5'
ABDA_MCP_IMAGE_OLD_REVISION='abda-nl-stg-web--harden-51702e1'
ABDA_MCP_IMAGE_TARGET_SUFFIX='gpl-ed241c1'
ABDA_MCP_IMAGE_TARGET_REVISION='abda-nl-stg-web--gpl-ed241c1'
ABDA_MCP_IMAGE_GATE_TITLE='cumulative service-integrity and suspension image'
ABDA_MCP_IMAGE_CONFIRMATION='PRIVACY_DELETION_VERIFIED_DEPLOY_ABDA_SERVICE_IMAGE'
ABDA_MCP_IMAGE_RESULT='SERVICE_INTEGRITY_IMAGE_DEPLOYED_AUDIT_REQUIRED'
ABDA_MCP_IMAGE_POST_ACTION_ONE='Run one short funded browser request, then continue with the pinned audit.'
ABDA_MCP_IMAGE_POST_ACTION_TWO='Keep public OpenRouter failover disabled until the later promotion.'

ABDA_RETENTION_GATE_DIRECTORY="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd
)"
ABDA_RETENTION_SHARED_GATE="$ABDA_RETENTION_GATE_DIRECTORY/gate10-mcp-command-image.sh"
ABDA_RETENTION_SHARED_GATE_SHA256='1bfebc7b9d8a76bf01332205260778aa1e9bd409377f1a8bb50e211d63c9379f'
ABDA_RETENTION_SHARED_GATE_TEMPORARY='false'
if [[ ! -f "$ABDA_RETENTION_SHARED_GATE" ]]; then
  ABDA_RETENTION_SHARED_GATE="$(
    mktemp /tmp/abda-nl-image-gate-library.XXXXXX
  )"
  ABDA_RETENTION_SHARED_GATE_TEMPORARY='true'
  curl --fail --silent --show-error --location \
    --proto '=https' --tlsv1.2 \
    'https://raw.githubusercontent.com/Liu-Hy/ABDA-NL/1eb9fd852a306de9ab00d6412491426bb0cd78c9/deploy/azure/gate10-mcp-command-image.sh' \
    --output "$ABDA_RETENTION_SHARED_GATE"
fi
printf '%s  %s\n' \
  "$ABDA_RETENTION_SHARED_GATE_SHA256" "$ABDA_RETENTION_SHARED_GATE" | \
  sha256sum --check >/dev/null
# shellcheck source=deploy/azure/gate10-mcp-command-image.sh
source "$ABDA_RETENTION_SHARED_GATE"
if [[ "$ABDA_RETENTION_SHARED_GATE_TEMPORARY" == 'true' ]]; then
  rm -f -- "$ABDA_RETENTION_SHARED_GATE"
fi

# The corrected distribution must not inherit the historical MIT label check.
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
    "org.opencontainers.image.licenses": "GPL-3.0-only",
}
if any(labels.get(name) != value for name, value in expected.items()):
    raise SystemExit("STOP: GHCR image provenance labels changed")
PY
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
  grep -Fq \
    'Expired records are removed at application startup or by an hourly cleanup triggered by subsequent traffic.' \
    "$prefix-privacy.html" || \
    abda_mcp_image_fail 'the deployed rate-limit retention disclosure is missing'
  grep -Fq 'Last updated September 4, 2026' "$prefix-privacy.html" || \
    abda_mcp_image_fail 'the deployed privacy notice date is stale'
  grep -Fq \
    'If a provider request may have started but the service receives no reliable billing result' \
    "$prefix-terms.html" || \
    abda_mcp_image_fail 'the conservative provider-billing disclosure is missing'
  grep -Fq 'Last updated September 4, 2026' "$prefix-terms.html" || \
    abda_mcp_image_fail 'the deployed terms date is stale'

  local save_status=''
  save_status="$(curl --silent --show-error \
    --proto '=https' --tlsv1.2 --connect-timeout 10 --max-time 30 \
    --header 'Content-Type: application/json' \
    --header "Origin: $ABDA_CUSTOM_ORIGIN" \
    --header 'Sec-Fetch-Site: same-origin' \
    --data '{"source_id":"popov_v_hayashi","diff_ops":[],"save_as_id":"popov_v_hayashi","title":"Rate-limit retention acceptance","overwrite":false}' \
    --output "$prefix-managed-save.json" --write-out '%{http_code}' \
    "$ABDA_CUSTOM_ORIGIN/scenarios")"
  [[ "$save_status" == '403' ]] || \
    abda_mcp_image_fail "managed filesystem save returned HTTP $save_status instead of 403"
  python3 - "$prefix-managed-save.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
expected = "filesystem saves are disabled; save this work as a private project"
if payload != {"detail": expected}:
    raise SystemExit("STOP: the managed filesystem-save response changed")
PY
  printf 'managed_filesystem_save: rejected_without_mutation\n'
  printf 'rate_limit_retention_disclosure: verified\n'
  printf 'privacy_notice_date: verified\n'
  printf 'conservative_provider_billing_disclosure: verified\n'
  printf 'terms_notice_date: verified\n'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_mcp_image_main
fi
