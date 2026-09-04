#!/usr/bin/env bash

# Promote the restored rate-limit retention image from the ten-user pilot to
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

ABDA_PROMOTION_SCRIPT_REVISION='retention-2'
ABDA_PROMOTION_APPLICATION_SOURCE_COMMIT='e008067e3dc9c96862cf4f75228bdf0250848665'
ABDA_PROMOTION_IMAGE_SHA256='b20cfe100f94d22e5734badaf5ec4e52e3445b72fcdc1879339f7b905109eb29'
ABDA_PROMOTION_OLD_REVISION='abda-nl-stg-web--restore-e008067'
ABDA_PROMOTION_TARGET_SUFFIX='public-100-e008067'
ABDA_PROMOTION_TARGET_REVISION='abda-nl-stg-web--public-100-e008067'

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_promotion_main "$@"
fi
