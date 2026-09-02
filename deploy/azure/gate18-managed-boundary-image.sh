#!/usr/bin/env bash

# Deploy the managed-service filesystem boundary and deterministic example
# cache as one image-only Container App update. The postdeployment check uses
# an existing scenario identifier, so an older image can return only a safe
# collision response and cannot create a filesystem entry.

set -Eeuo pipefail
set +x
umask 077

ABDA_MCP_IMAGE_SCRIPT_REVISION='1'
ABDA_MCP_IMAGE_SOURCE_COMMIT='b873112040dbfe645683d1b5e7d9adb122173ed2'
ABDA_MCP_IMAGE_OLD_IMAGE_SHA256='78481da1f49f9b049509eafc61da1c95d55ac42e425c4ab1dbb04d700971b55d'
ABDA_MCP_IMAGE_NEW_IMAGE_SHA256='567ec34602e1b5ab1e1a9b01864f2a67219910dc3080300bc108eb33d569856c'
ABDA_MCP_IMAGE_OLD_REVISION='abda-nl-stg-web--release-3faf6eb'
ABDA_MCP_IMAGE_TARGET_SUFFIX='secure-b873112'
ABDA_MCP_IMAGE_TARGET_REVISION='abda-nl-stg-web--secure-b873112'
ABDA_MCP_IMAGE_GATE_TITLE='managed-boundary image'
ABDA_MCP_IMAGE_CONFIRMATION='DEPLOY_ABDA_MANAGED_BOUNDARY'
ABDA_MCP_IMAGE_RESULT='MANAGED_BOUNDARY_IMAGE_DEPLOYED_CAPACITY_SMOKE_REQUIRED'
ABDA_MCP_IMAGE_POST_ACTION_ONE='Do not perform a separate browser check at this checkpoint.'
ABDA_MCP_IMAGE_POST_ACTION_TWO='Continue with the bounded public capacity smoke.'

ABDA_MANAGED_GATE_DIRECTORY="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd
)"
ABDA_MANAGED_SHARED_GATE="$ABDA_MANAGED_GATE_DIRECTORY/gate10-mcp-command-image.sh"
ABDA_MANAGED_SHARED_GATE_SHA256='1bfebc7b9d8a76bf01332205260778aa1e9bd409377f1a8bb50e211d63c9379f'
ABDA_MANAGED_SHARED_GATE_TEMPORARY='false'
if [[ ! -f "$ABDA_MANAGED_SHARED_GATE" ]]; then
  ABDA_MANAGED_SHARED_GATE="$(
    mktemp /tmp/abda-nl-image-gate-library.XXXXXX
  )"
  ABDA_MANAGED_SHARED_GATE_TEMPORARY='true'
  curl --fail --silent --show-error --location \
    --proto '=https' --tlsv1.2 \
    'https://raw.githubusercontent.com/Liu-Hy/ABDA-NL/1eb9fd852a306de9ab00d6412491426bb0cd78c9/deploy/azure/gate10-mcp-command-image.sh' \
    --output "$ABDA_MANAGED_SHARED_GATE"
fi
printf '%s  %s\n' \
  "$ABDA_MANAGED_SHARED_GATE_SHA256" "$ABDA_MANAGED_SHARED_GATE" | \
  sha256sum --check >/dev/null
# shellcheck source=deploy/azure/gate10-mcp-command-image.sh
source "$ABDA_MANAGED_SHARED_GATE"
if [[ "$ABDA_MANAGED_SHARED_GATE_TEMPORARY" == 'true' ]]; then
  rm -f -- "$ABDA_MANAGED_SHARED_GATE"
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
    --data '{"source_id":"popov_v_hayashi","diff_ops":[],"save_as_id":"popov_v_hayashi","title":"Managed boundary acceptance","overwrite":false}' \
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
