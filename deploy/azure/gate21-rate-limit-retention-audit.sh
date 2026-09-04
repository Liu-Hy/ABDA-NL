#!/usr/bin/env bash

# Run the existing read-only release and observability audit against the exact
# cumulative accounting-integrity image. The pilot mode follows Gate 20. The
# public mode follows the bounded promotion of the same immutable image.

set -Eeuo pipefail
set +x
umask 077

ABDA_RETENTION_AUDIT_DIRECTORY="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd
)"
ABDA_RETENTION_AUDIT_SHARED_GATE="$ABDA_RETENTION_AUDIT_DIRECTORY/gate9-observability-audit.sh"
ABDA_RETENTION_AUDIT_SHARED_GATE_SHA256='59db2e3f304fcd8dfc7fadad87c25d68dbe45b0e17440b9a7277467e24bf7857'
ABDA_RETENTION_AUDIT_SHARED_GATE_TEMPORARY='false'
if [[ ! -f "$ABDA_RETENTION_AUDIT_SHARED_GATE" ]]; then
  ABDA_RETENTION_AUDIT_SHARED_GATE="$(
    mktemp /tmp/abda-nl-audit-gate-library.XXXXXX
  )"
  ABDA_RETENTION_AUDIT_SHARED_GATE_TEMPORARY='true'
  curl --fail --silent --show-error --location \
    --proto '=https' --tlsv1.2 \
    'https://raw.githubusercontent.com/Liu-Hy/ABDA-NL/830302fc1bf30bf0f00c457fdfe8bc190b3562fe/deploy/azure/gate9-observability-audit.sh' \
    --output "$ABDA_RETENTION_AUDIT_SHARED_GATE"
fi
printf '%s  %s\n' \
  "$ABDA_RETENTION_AUDIT_SHARED_GATE_SHA256" \
  "$ABDA_RETENTION_AUDIT_SHARED_GATE" | sha256sum --check >/dev/null
# shellcheck source=deploy/azure/gate9-observability-audit.sh
source "$ABDA_RETENTION_AUDIT_SHARED_GATE"
if [[ "$ABDA_RETENTION_AUDIT_SHARED_GATE_TEMPORARY" == 'true' ]]; then
  rm -f -- "$ABDA_RETENTION_AUDIT_SHARED_GATE"
fi

ABDA_AUDIT_SCRIPT_REVISION='accounting-3'
ABDA_AUDIT_SOURCE_COMMIT='050ce2cda65838b4c875079239e91f5161a4bbbe'
ABDA_AUDIT_IMAGE_SHA256='2ff479555d21a5ea44506e6d74a080551ddfc0fa4f5122cf7cc96f1e26afb50d'

abda_audit_set_constants() {
  local release_stage="${1:---pilot}"
  ABDA_EXPECTED_SUBSCRIPTION='00e62f6e-2174-40b2-b428-8ebfd7c2ac54'
  ABDA_EXPECTED_TENANT='040f05eb-33ab-462f-af54-fb4bedb055ae'
  ABDA_EXPECTED_USER='hliu2@cloudbank.org'
  ABDA_RESOURCE_GROUP='abda-nl-staging'
  ABDA_APP_NAME='abda-nl-stg-web'
  ABDA_CONTAINER_NAME='web'
  ABDA_ENVIRONMENT_NAME='abda-nl-stg-environment'
  ABDA_LOGS_NAME='abda-nl-stg-logs-bgjhpbgw'
  ABDA_IMAGE_REPOSITORY='ghcr.io/liu-hy/abda-nl'
  ABDA_PUBLIC_ORIGIN='https://demo.abda-nl.org'
  ABDA_TRIAL_GRANT_MICROUSD='5000000'
  ABDA_OPENROUTER_BUDGET_MICROUSD='500000000'
  case "$release_stage" in
    --pilot)
      ABDA_AUDIT_RELEASE_STAGE='accounting-pilot'
      ABDA_AUDIT_REVISION='abda-nl-stg-web--account-050ce2c'
      ABDA_TRIAL_MAX_USERS='10'
      ABDA_TRIAL_BUDGET_MICROUSD='50000000'
      ABDA_OPENROUTER_ENABLED='false'
      ABDA_AUDIT_RESULT='RATE_LIMIT_RETENTION_RELEASE_AND_OBSERVABILITY_AUDIT_VERIFIED'
      ;;
    --public)
      ABDA_AUDIT_RELEASE_STAGE='accounting-public'
      ABDA_AUDIT_REVISION='abda-nl-stg-web--public-100-050ce2c'
      ABDA_TRIAL_MAX_USERS='100'
      ABDA_TRIAL_BUDGET_MICROUSD='500000000'
      ABDA_OPENROUTER_ENABLED='true'
      ABDA_AUDIT_RESULT='FINAL_PUBLIC_RELEASE_AND_OBSERVABILITY_AUDIT_VERIFIED'
      ;;
    *)
      abda_audit_fail 'usage: gate21-rate-limit-retention-audit.sh [--pilot|--public]'
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_audit_main "$@"
fi
