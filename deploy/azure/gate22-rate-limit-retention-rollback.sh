#!/usr/bin/env bash

# Rehearse a schema-compatible rollback from the cumulative accounting image to
# the prior hardened image, then restore the cumulative image automatically.

set -Eeuo pipefail
set +x
umask 077

ABDA_RETENTION_ROLLBACK_DIRECTORY="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd
)"
ABDA_RETENTION_ROLLBACK_SHARED_GATE="$ABDA_RETENTION_ROLLBACK_DIRECTORY/gate10-rollback-rehearsal.sh"
ABDA_RETENTION_ROLLBACK_SHARED_GATE_SHA256='a1a41ff17038894a255c4175b06c44422b6887e09f47c36f5b66a91845039273'
ABDA_RETENTION_ROLLBACK_SHARED_GATE_TEMPORARY='false'
if [[ ! -f "$ABDA_RETENTION_ROLLBACK_SHARED_GATE" ]]; then
  ABDA_RETENTION_ROLLBACK_SHARED_GATE="$(
    mktemp /tmp/abda-nl-rollback-gate-library.XXXXXX
  )"
  ABDA_RETENTION_ROLLBACK_SHARED_GATE_TEMPORARY='true'
  curl --fail --silent --show-error --location \
    --proto '=https' --tlsv1.2 \
    'https://raw.githubusercontent.com/Liu-Hy/ABDA-NL/830302fc1bf30bf0f00c457fdfe8bc190b3562fe/deploy/azure/gate10-rollback-rehearsal.sh' \
    --output "$ABDA_RETENTION_ROLLBACK_SHARED_GATE"
fi
printf '%s  %s\n' \
  "$ABDA_RETENTION_ROLLBACK_SHARED_GATE_SHA256" \
  "$ABDA_RETENTION_ROLLBACK_SHARED_GATE" | sha256sum --check >/dev/null
# shellcheck source=deploy/azure/gate10-rollback-rehearsal.sh
source "$ABDA_RETENTION_ROLLBACK_SHARED_GATE"
if [[ "$ABDA_RETENTION_ROLLBACK_SHARED_GATE_TEMPORARY" == 'true' ]]; then
  rm -f -- "$ABDA_RETENTION_ROLLBACK_SHARED_GATE"
fi

ABDA_ROLLBACK_SCRIPT_REVISION='accounting-3'
ABDA_CURRENT_SOURCE_COMMIT='050ce2cda65838b4c875079239e91f5161a4bbbe'
ABDA_CURRENT_IMAGE_SHA256='2ff479555d21a5ea44506e6d74a080551ddfc0fa4f5122cf7cc96f1e26afb50d'
ABDA_ROLLBACK_SOURCE_COMMIT='51702e175bd14d4cb54075808f839d173d561324'
ABDA_ROLLBACK_IMAGE_SHA256='a0b3ba24aff06ecf461f86547131d86451c541e306a7ecfc278f280fcef5c0bc'
ABDA_CURRENT_REVISION='abda-nl-stg-web--account-050ce2c'
ABDA_ROLLBACK_SUFFIX='rollback-51702e1'
ABDA_ROLLBACK_REVISION='abda-nl-stg-web--rollback-51702e1'
ABDA_RESTORE_SUFFIX='restore-050ce2c'
ABDA_RESTORE_REVISION='abda-nl-stg-web--restore-050ce2c'

ABDA_RETENTION_ROLLBACK_PUBLIC_FUNCTION="$(
  declare -f abda_rollback_public_acceptance
)"
eval "${ABDA_RETENTION_ROLLBACK_PUBLIC_FUNCTION/abda_rollback_public_acceptance/abda_retention_rollback_base_public_acceptance}"
unset ABDA_RETENTION_ROLLBACK_PUBLIC_FUNCTION

abda_rollback_public_acceptance() {
  local prefix=$1
  local require_retention=${2:-false}
  abda_retention_rollback_base_public_acceptance "$@"
  if [[ "$require_retention" == 'true' ]]; then
    grep -Fq \
      'Expired records are removed at application startup or by an hourly cleanup triggered by subsequent traffic.' \
      "$prefix-privacy.html" || \
      abda_rollback_fail 'the restored rate-limit retention disclosure is missing'
    grep -Fq 'Last updated September 4, 2026' "$prefix-privacy.html" || \
      abda_rollback_fail 'the restored privacy notice date is stale'
    grep -Fq \
      'If a provider request may have started but the service receives no reliable billing result' \
      "$prefix-terms.html" || \
      abda_rollback_fail 'the restored provider-billing disclosure is missing'
    grep -Fq 'Last updated September 4, 2026' "$prefix-terms.html" || \
      abda_rollback_fail 'the restored terms date is stale'
  fi
}

abda_rollback_print_status() {
  printf '\nABDA-NL Gate 22 rate-limit retention rollback status:\n'
  printf 'script_revision: %s\n' "$ABDA_ROLLBACK_SCRIPT_REVISION"
  printf 'current_source_commit: %s\n' "$ABDA_CURRENT_SOURCE_COMMIT"
  printf 'current_image_digest: sha256:%s\n' "$ABDA_CURRENT_IMAGE_SHA256"
  printf 'rollback_source_commit: %s\n' "$ABDA_ROLLBACK_SOURCE_COMMIT"
  printf 'rollback_image_digest: sha256:%s\n' "$ABDA_ROLLBACK_IMAGE_SHA256"
  printf 'subscription_id: %s\n' "$ABDA_EXPECTED_SUBSCRIPTION"
  printf 'resource_group: %s\n' "$ABDA_RESOURCE_GROUP"
  printf 'rollback_revision: %s\n' "$ABDA_ROLLBACK_REVISION"
  printf 'restored_revision: %s\n' "$ABDA_RESTORE_REVISION"
  printf 'public_origin: %s\n' "$ABDA_CUSTOM_ORIGIN"
  printf 'migration_rerun: false\n'
  printf 'secrets_changed: false\n'
  printf 'settings_changed: false\n'
  printf 'trial_max_users: 10\n'
  printf 'openrouter_failover_enabled: false\n'
  printf 'rollback_acceptance: passed\n'
  printf 'restored_acceptance: passed\n'
  printf 'rate_limit_retention_disclosure: verified\n'
  printf 'privacy_notice_date: verified\n'
  printf 'conservative_provider_billing_disclosure: verified\n'
  printf 'terms_notice_date: verified\n'
  printf 'result: COMPATIBLE_RETENTION_IMAGE_ROLLBACK_AND_RESTORE_VERIFIED\n'
  printf '%s\n' \
    'The current cumulative image is healthy again. Continue with the bounded public promotion only after its external prerequisites are complete.'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_rollback_main "$@"
fi
