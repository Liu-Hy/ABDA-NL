#!/usr/bin/env bash

# Promote the restored cumulative accounting image from the ten-user pilot to
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

ABDA_PROMOTION_SCRIPT_REVISION='accounting-3'
ABDA_PROMOTION_APPLICATION_SOURCE_COMMIT='050ce2cda65838b4c875079239e91f5161a4bbbe'
ABDA_PROMOTION_IMAGE_SHA256='2ff479555d21a5ea44506e6d74a080551ddfc0fa4f5122cf7cc96f1e26afb50d'
ABDA_PROMOTION_OLD_REVISION='abda-nl-stg-web--restore-050ce2c'
ABDA_PROMOTION_TARGET_SUFFIX='public-100-050ce2c'
ABDA_PROMOTION_TARGET_REVISION='abda-nl-stg-web--public-100-050ce2c'

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_promotion_main "$@"
fi
