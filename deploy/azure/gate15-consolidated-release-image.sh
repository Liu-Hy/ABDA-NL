#!/usr/bin/env bash

# Deploy the consolidated release-candidate image after its complete CI,
# exact-digest container smoke test, and GitHub provenance attestation pass.

set -Eeuo pipefail
set +x
umask 077

ABDA_MCP_IMAGE_SCRIPT_REVISION='1'
ABDA_MCP_IMAGE_SOURCE_COMMIT='3faf6ebd94c4dcb69fa36cb1aba481db15a9f973'
ABDA_MCP_IMAGE_OLD_IMAGE_SHA256='ffea9cff567b8694cc556aa4ba91a67e8ab5001cffc3f54c97f2aaaf6a2b4593'
ABDA_MCP_IMAGE_NEW_IMAGE_SHA256='78481da1f49f9b049509eafc61da1c95d55ac42e425c4ab1dbb04d700971b55d'
ABDA_MCP_IMAGE_OLD_REVISION='abda-nl-stg-web--revoke-0b2a2aa'
ABDA_MCP_IMAGE_TARGET_SUFFIX='release-3faf6eb'
ABDA_MCP_IMAGE_TARGET_REVISION='abda-nl-stg-web--release-3faf6eb'
ABDA_MCP_IMAGE_GATE_TITLE='consolidated release-candidate image'
ABDA_MCP_IMAGE_CONFIRMATION='DEPLOY_ABDA_CONSOLIDATED_RELEASE'
ABDA_MCP_IMAGE_RESULT='CONSOLIDATED_RELEASE_IMAGE_DEPLOYED_AUTOMATED_ACCEPTANCE_REQUIRED'
ABDA_MCP_IMAGE_POST_ACTION_ONE='Do not perform a separate browser check at this checkpoint.'
ABDA_MCP_IMAGE_POST_ACTION_TWO='Continue with the consolidated automated and operator acceptance batch.'

ABDA_RELEASE_GATE_DIRECTORY="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd
)"
ABDA_RELEASE_SHARED_GATE="$ABDA_RELEASE_GATE_DIRECTORY/gate10-mcp-command-image.sh"
ABDA_RELEASE_SHARED_GATE_SHA256='1bfebc7b9d8a76bf01332205260778aa1e9bd409377f1a8bb50e211d63c9379f'
ABDA_RELEASE_SHARED_GATE_TEMPORARY='false'
if [[ ! -f "$ABDA_RELEASE_SHARED_GATE" ]]; then
  ABDA_RELEASE_SHARED_GATE="$(
    mktemp /tmp/abda-nl-image-gate-library.XXXXXX
  )"
  ABDA_RELEASE_SHARED_GATE_TEMPORARY='true'
  curl --fail --silent --show-error --location \
    --proto '=https' --tlsv1.2 \
    'https://raw.githubusercontent.com/Liu-Hy/ABDA-NL/1eb9fd852a306de9ab00d6412491426bb0cd78c9/deploy/azure/gate10-mcp-command-image.sh' \
    --output "$ABDA_RELEASE_SHARED_GATE"
fi
printf '%s  %s\n' \
  "$ABDA_RELEASE_SHARED_GATE_SHA256" "$ABDA_RELEASE_SHARED_GATE" | \
  sha256sum --check >/dev/null
# shellcheck source=deploy/azure/gate10-mcp-command-image.sh
source "$ABDA_RELEASE_SHARED_GATE"
if [[ "$ABDA_RELEASE_SHARED_GATE_TEMPORARY" == 'true' ]]; then
  rm -f -- "$ABDA_RELEASE_SHARED_GATE"
fi

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_mcp_image_main
fi
