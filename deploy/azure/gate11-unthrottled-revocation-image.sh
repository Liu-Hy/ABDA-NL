#!/usr/bin/env bash

# Deploy the image that keeps authenticated MCP credential revocation
# available even when the separate credential-creation throttle is exhausted.

set -Eeuo pipefail
set +x
umask 077

ABDA_MCP_IMAGE_SCRIPT_REVISION='1'
ABDA_MCP_IMAGE_SOURCE_COMMIT='0b2a2aad93427dfec65c11def7f6434ed1c9abfb'
ABDA_MCP_IMAGE_OLD_IMAGE_SHA256='2df0bf98401adb6f72d1b930d83ab68bd2466de756b0bead3864f3d41d30b9d0'
ABDA_MCP_IMAGE_NEW_IMAGE_SHA256='ffea9cff567b8694cc556aa4ba91a67e8ab5001cffc3f54c97f2aaaf6a2b4593'
ABDA_MCP_IMAGE_OLD_REVISION='abda-nl-stg-web--mcp-c55aa0d'
ABDA_MCP_IMAGE_TARGET_SUFFIX='revoke-0b2a2aa'
ABDA_MCP_IMAGE_TARGET_REVISION='abda-nl-stg-web--revoke-0b2a2aa'
ABDA_MCP_IMAGE_GATE_TITLE='unthrottled credential revocation image'
ABDA_MCP_IMAGE_CONFIRMATION='DEPLOY_ABDA_UNTHROTTLED_REVOCATION'
ABDA_MCP_IMAGE_RESULT='UNTHROTTLED_CREDENTIAL_REVOCATION_DEPLOYED_BROWSER_TEST_REQUIRED'
ABDA_MCP_IMAGE_POST_ACTION_ONE='Sign in and create one short-lived read-only MCP token.'
ABDA_MCP_IMAGE_POST_ACTION_TWO='Revoke it immediately and confirm that the Revoke button disappears after Refresh.'

ABDA_REVOCATION_GATE_DIRECTORY="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd
)"
ABDA_REVOCATION_SHARED_GATE="$ABDA_REVOCATION_GATE_DIRECTORY/gate10-mcp-command-image.sh"
ABDA_REVOCATION_SHARED_GATE_SHA256='1bfebc7b9d8a76bf01332205260778aa1e9bd409377f1a8bb50e211d63c9379f'
ABDA_REVOCATION_SHARED_GATE_TEMPORARY='false'
if [[ ! -f "$ABDA_REVOCATION_SHARED_GATE" ]]; then
  ABDA_REVOCATION_SHARED_GATE="$(
    mktemp /tmp/abda-nl-image-gate-library.XXXXXX
  )"
  ABDA_REVOCATION_SHARED_GATE_TEMPORARY='true'
  curl --fail --silent --show-error --location \
    --proto '=https' --tlsv1.2 \
    'https://raw.githubusercontent.com/Liu-Hy/ABDA-NL/1eb9fd852a306de9ab00d6412491426bb0cd78c9/deploy/azure/gate10-mcp-command-image.sh' \
    --output "$ABDA_REVOCATION_SHARED_GATE"
fi
printf '%s  %s\n' \
  "$ABDA_REVOCATION_SHARED_GATE_SHA256" "$ABDA_REVOCATION_SHARED_GATE" | \
  sha256sum --check >/dev/null
# shellcheck source=deploy/azure/gate10-mcp-command-image.sh
source "$ABDA_REVOCATION_SHARED_GATE"
if [[ "$ABDA_REVOCATION_SHARED_GATE_TEMPORARY" == 'true' ]]; then
  rm -f -- "$ABDA_REVOCATION_SHARED_GATE"
fi

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_mcp_image_main
fi
