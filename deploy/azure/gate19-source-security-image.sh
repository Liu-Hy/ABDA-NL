#!/usr/bin/env bash

# Deploy the source-security candidate as one image-only Container App update.
# The underlying shared gate proves that every application setting and secret
# reference remains unchanged and reruns the existing public acceptance checks.

set -Eeuo pipefail
set +x
umask 077

ABDA_MCP_IMAGE_SCRIPT_REVISION='1'
ABDA_MCP_IMAGE_SOURCE_COMMIT='c173dd5983ba209b17c585c0c82aeb33c2e49028'
ABDA_MCP_IMAGE_OLD_IMAGE_SHA256='567ec34602e1b5ab1e1a9b01864f2a67219910dc3080300bc108eb33d569856c'
ABDA_MCP_IMAGE_NEW_IMAGE_SHA256='ecf7531064fe6f86d3d647e9f0239bfbe5e082d71c5fcdd5e7e7fb91e9b32a64'
ABDA_MCP_IMAGE_OLD_REVISION='abda-nl-stg-web--secure-b873112'
ABDA_MCP_IMAGE_TARGET_SUFFIX='harden-c173dd5'
ABDA_MCP_IMAGE_TARGET_REVISION='abda-nl-stg-web--harden-c173dd5'
ABDA_MCP_IMAGE_GATE_TITLE='source-security image'
ABDA_MCP_IMAGE_CONFIRMATION='DEPLOY_ABDA_SOURCE_SECURITY_IMAGE'
ABDA_MCP_IMAGE_RESULT='SOURCE_SECURITY_IMAGE_DEPLOYED_AUDIT_REQUIRED'
ABDA_MCP_IMAGE_POST_ACTION_ONE='No separate browser check is required for this logging-only change.'
ABDA_MCP_IMAGE_POST_ACTION_TWO='Continue with the read-only release and sanitized-log audit.'

ABDA_SECURITY_GATE_DIRECTORY="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd
)"
ABDA_SECURITY_SHARED_GATE="$ABDA_SECURITY_GATE_DIRECTORY/gate10-mcp-command-image.sh"
ABDA_SECURITY_SHARED_GATE_SHA256='1bfebc7b9d8a76bf01332205260778aa1e9bd409377f1a8bb50e211d63c9379f'
ABDA_SECURITY_SHARED_GATE_TEMPORARY='false'
if [[ ! -f "$ABDA_SECURITY_SHARED_GATE" ]]; then
  ABDA_SECURITY_SHARED_GATE="$(
    mktemp /tmp/abda-nl-image-gate-library.XXXXXX
  )"
  ABDA_SECURITY_SHARED_GATE_TEMPORARY='true'
  curl --fail --silent --show-error --location \
    --proto '=https' --tlsv1.2 \
    'https://raw.githubusercontent.com/Liu-Hy/ABDA-NL/1eb9fd852a306de9ab00d6412491426bb0cd78c9/deploy/azure/gate10-mcp-command-image.sh' \
    --output "$ABDA_SECURITY_SHARED_GATE"
fi
printf '%s  %s\n' \
  "$ABDA_SECURITY_SHARED_GATE_SHA256" "$ABDA_SECURITY_SHARED_GATE" | \
  sha256sum --check >/dev/null
# shellcheck source=deploy/azure/gate10-mcp-command-image.sh
source "$ABDA_SECURITY_SHARED_GATE"
if [[ "$ABDA_SECURITY_SHARED_GATE_TEMPORARY" == 'true' ]]; then
  rm -f -- "$ABDA_SECURITY_SHARED_GATE"
fi

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

  local save_status=''
  save_status="$(curl --silent --show-error \
    --proto '=https' --tlsv1.2 --connect-timeout 10 --max-time 30 \
    --header 'Content-Type: application/json' \
    --header "Origin: $ABDA_CUSTOM_ORIGIN" \
    --header 'Sec-Fetch-Site: same-origin' \
    --data '{"source_id":"popov_v_hayashi","diff_ops":[],"save_as_id":"popov_v_hayashi","title":"Source security acceptance","overwrite":false}' \
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
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_mcp_image_main
fi
