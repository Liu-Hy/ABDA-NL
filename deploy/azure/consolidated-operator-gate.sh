#!/usr/bin/env bash

# Download, verify, and run one exact gate from the consolidated release
# sequence. This helper deliberately has no run-all mode. Each mutating gate
# retains its own explicit confirmation and resume boundary.

set -Eeuo pipefail
set +x
umask 077

ABDA_OPERATOR_SCRIPT_REVISION='3'
ABDA_OPERATOR_SOURCE_COMMIT='9919911c0bb280e0a9e5762f50c4a7da89efbc0a'
ABDA_OPERATOR_ROOT=''

abda_operator_cleanup() {
  local exit_code=$?
  set +e
  if [[ "${ABDA_OPERATOR_ROOT:-}" == /tmp/abda-nl-operator-gate.* &&
        -d "${ABDA_OPERATOR_ROOT:-}" ]]; then
    rm -rf -- "$ABDA_OPERATOR_ROOT"
  fi
  return "$exit_code"
}

abda_operator_usage() {
  cat <<'EOF'
Usage: consolidated-operator-gate.sh PHASE

Phases, in required order:
  verify    Download and hash-check every pinned gate without running one
  deploy    Deploy only the consolidated application image
  audit     Run the read-only release and sanitized-log audit
  byok      Run the browser-assisted, no-storage BYOK acceptance
  privacy   Run or resume the disposable-account privacy acceptance
  alerts    Deploy and test the bounded Azure Monitor resources
  rollback  Rehearse the compatible image rollback and automatic restoration
  promote   Promote 10 users to 100 and enable bounded outage fallback

There is intentionally no run-all phase. Browser and cloud mutations retain
their individual confirmations and recovery boundaries.
EOF
}

abda_operator_gate_metadata() {
  local phase=$1
  case "$phase" in
    deploy)
      printf '%s\n' \
        'deploy/azure/gate15-consolidated-release-image.sh' \
        '1ecd495299bd63ef5edcb6ecc730df7a3942008382402e4ddd53d9f9f4838614' \
        'bash' \
        'Changes only the existing web image and revision suffix.'
      ;;
    audit)
      printf '%s\n' \
        'deploy/azure/gate9-observability-audit.sh' \
        'ceed8f2eb5e31bb568844de3675f2bf43b6cf2da2b766d89d8fb4e581ed43523' \
        'bash' \
        'Read-only Azure, HTTPS, release, and count-only log checks.'
      ;;
    byok)
      printf '%s\n' \
        'deploy/azure/gate10-byok-browser-acceptance.sh' \
        'de70312f42133940ca2311a4679e9ef256659d9b2944416d846bde2bed0b325a' \
        'bash' \
        'One browser BYOK call, no Azure configuration change.'
      ;;
    privacy)
      printf '%s\n' \
        'deploy/azure/gate11-privacy-acceptance.sh' \
        'b343a60f7a28608f59b1ff08de93ba16de3eedc6d39590025119d0a919ab4cce' \
        'bash' \
        'Changes only one disposable account after exact confirmations.'
      ;;
    alerts)
      printf '%s\n' \
        'deploy/azure/gate14_observability_alerts.py' \
        'b2fe0ab9433583e7c5d2ff6fa5a1ea0fee37aa51ba3435d4bd00e5d9c5003c05' \
        'python3' \
        'Creates or updates only six reviewed Azure Monitor resources.'
      ;;
    rollback)
      printf '%s\n' \
        'deploy/azure/gate10-rollback-rehearsal.sh' \
        '155df59251eafcdef9edeb8d4b1cd643e06964e0ce7deda45b5fe54bb0c9107c' \
        'bash' \
        'Changes only the web image twice and restores the candidate.'
      ;;
    promote)
      printf '%s\n' \
        'deploy/azure/gate12-public-budget-promotion.sh' \
        'e117c6a50227d80ee5322a6b596eb6d890cacc6c56de1dd276fde69b0217a39e' \
        'bash' \
        'Changes only three reviewed trial and fallback settings.'
      ;;
    *)
      return 1
      ;;
  esac
}

abda_operator_download() {
  local phase=$1
  local metadata=''
  metadata="$(abda_operator_gate_metadata "$phase")" || return 1
  local relative_path=''
  local expected_sha256=''
  local interpreter=''
  local boundary=''
  mapfile -t fields <<<"$metadata"
  relative_path="${fields[0]}"
  expected_sha256="${fields[1]}"
  interpreter="${fields[2]}"
  boundary="${fields[3]}"
  local destination="$ABDA_OPERATOR_ROOT/${relative_path##*/}"
  curl --fail --silent --show-error --location \
    --proto '=https' --tlsv1.2 \
    "https://raw.githubusercontent.com/Liu-Hy/ABDA-NL/$ABDA_OPERATOR_SOURCE_COMMIT/$relative_path" \
    --output "$destination"
  printf '%s  %s\n' "$expected_sha256" "$destination" | \
    sha256sum --check --status
  printf '%s\n' "$destination" "$interpreter" "$boundary"
}

abda_operator_main() {
  local phase="${1:-}"
  if [[ "$phase" == 'help' || "$phase" == '--help' || "$phase" == '-h' ]]; then
    abda_operator_usage
    return 0
  fi
  if [[ -z "$phase" ]]; then
    abda_operator_usage >&2
    return 2
  fi

  for command_name in curl sha256sum; do
    command -v "$command_name" >/dev/null 2>&1 || {
      printf 'Required command is unavailable: %s\n' "$command_name" >&2
      return 1
    }
  done
  ABDA_OPERATOR_ROOT="$(mktemp -d /tmp/abda-nl-operator-gate.XXXXXX)"
  chmod 700 "$ABDA_OPERATOR_ROOT"

  printf 'ABDA-NL consolidated operator helper revision: %s\n' \
    "$ABDA_OPERATOR_SCRIPT_REVISION"
  printf 'Pinned gate source commit: %s\n' "$ABDA_OPERATOR_SOURCE_COMMIT"

  if [[ "$phase" == 'verify' ]]; then
    local gate=''
    for gate in deploy audit byok privacy alerts rollback promote; do
      abda_operator_download "$gate" >/dev/null
      printf 'verified: %s\n' "$gate"
    done
    printf 'result: ALL_CONSOLIDATED_OPERATOR_GATES_VERIFIED\n'
    return 0
  fi

  local metadata=''
  metadata="$(abda_operator_gate_metadata "$phase")" || {
    printf 'Unknown phase: %s\n\n' "$phase" >&2
    abda_operator_usage >&2
    return 2
  }
  local download_result=''
  download_result="$(abda_operator_download "$phase")"
  mapfile -t downloaded <<<"$download_result"
  local gate_path="${downloaded[0]}"
  local interpreter="${downloaded[1]}"
  local boundary="${downloaded[2]}"
  command -v "$interpreter" >/dev/null 2>&1 || {
    printf 'Required interpreter is unavailable: %s\n' "$interpreter" >&2
    return 1
  }
  printf 'phase: %s\n' "$phase"
  printf 'boundary: %s\n\n' "$boundary"
  "$interpreter" "$gate_path"
}

trap abda_operator_cleanup EXIT
abda_operator_main "$@"
