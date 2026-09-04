#!/usr/bin/env bash

# Promote the restored cumulative service-integrity image from the ten-user pilot to
# the reviewed 100-user caps and bounded OpenRouter outage fallback.

set -Eeuo pipefail
set +x
umask 077

ABDA_RETENTION_PROMOTION_DIRECTORY="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd
)"
ABDA_RETENTION_PROMOTION_SHARED_GATE="$ABDA_RETENTION_PROMOTION_DIRECTORY/gate12-public-budget-promotion.sh"
ABDA_RETENTION_PROMOTION_SHARED_GATE_SHA256='712f0206fc330249e15d0d59793ad9a6e5c317a6fc752b6f2dccfa384c2bb04d'
ABDA_RETENTION_PROMOTION_SHARED_GATE_TEMPORARY='false'
if [[ ! -f "$ABDA_RETENTION_PROMOTION_SHARED_GATE" ]]; then
  ABDA_RETENTION_PROMOTION_SHARED_GATE="$(
    mktemp /tmp/abda-nl-promotion-gate-library.XXXXXX
  )"
  ABDA_RETENTION_PROMOTION_SHARED_GATE_TEMPORARY='true'
  curl --fail --silent --show-error --location \
    --proto '=https' --tlsv1.2 \
    'https://raw.githubusercontent.com/Liu-Hy/ABDA-NL/830302fc1bf30bf0f00c457fdfe8bc190b3562fe/deploy/azure/gate12-public-budget-promotion.sh' \
    --output "$ABDA_RETENTION_PROMOTION_SHARED_GATE"
fi
printf '%s  %s\n' \
  "$ABDA_RETENTION_PROMOTION_SHARED_GATE_SHA256" \
  "$ABDA_RETENTION_PROMOTION_SHARED_GATE" | sha256sum --check >/dev/null
# shellcheck source=deploy/azure/gate12-public-budget-promotion.sh
source "$ABDA_RETENTION_PROMOTION_SHARED_GATE"
if [[ "$ABDA_RETENTION_PROMOTION_SHARED_GATE_TEMPORARY" == 'true' ]]; then
  rm -f -- "$ABDA_RETENTION_PROMOTION_SHARED_GATE"
fi

ABDA_PROMOTION_SCRIPT_REVISION='integrity-4'
ABDA_PROMOTION_APPLICATION_SOURCE_COMMIT='e09fb727da2c34f78f97f28f8591f2b5cc33eeb1'
ABDA_PROMOTION_IMAGE_SHA256='0a33ffa9dac2e5bf6a69855140698c086bced30c12c780318759c5a375307d49'
ABDA_PROMOTION_OLD_REVISION='abda-nl-stg-web--restore-e09fb72'
ABDA_PROMOTION_TARGET_SUFFIX='public-100-e09fb72'
ABDA_PROMOTION_TARGET_REVISION='abda-nl-stg-web--public-100-e09fb72'

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_promotion_main "$@"
fi
