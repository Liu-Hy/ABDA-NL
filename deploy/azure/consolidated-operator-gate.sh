#!/usr/bin/env bash

# Download, verify, and run one exact gate from the consolidated release
# sequence. This helper deliberately has no run-all mode. Each mutating gate
# retains its own explicit confirmation and resume boundary.

set -Eeuo pipefail
set +x
umask 077

ABDA_OPERATOR_SCRIPT_REVISION='9'
ABDA_OPERATOR_SOURCE_COMMIT='e6d3d96a9ce84fd8b5022f39b31c323a2ca979f7'
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
  deploy    Deploy only the source-security application image
  audit     Run the read-only release and sanitized-log audit
  byok      Run the browser-assisted, no-storage BYOK acceptance
  privacy   Run or resume the disposable-account privacy acceptance
  hostname  Verify the Cloudflare redirect and public DNS boundary
  alerts    Deploy and test the bounded Azure Monitor resources
  rollback  Rehearse the compatible image rollback and automatic restoration
  promote   Promote 10 users to 100 and enable bounded outage fallback
  final-audit
            Run the read-only audit against the promoted public limits

There is intentionally no run-all phase. Browser and cloud mutations retain
their individual confirmations and recovery boundaries.
EOF
}

abda_operator_gate_metadata() {
  local phase=$1
  case "$phase" in
    deploy)
      printf '%s\n' \
        'deploy/azure/gate19-source-security-image.sh' \
        '56f1c612bf3c97e5d332f023cea50c05a8b411e4ab173515a80b6a683eb1cb55' \
        'bash' \
        'Changes only the existing web image and revision suffix.'
      ;;
    audit)
      printf '%s\n' \
        'deploy/azure/gate9-observability-audit.sh' \
        'f67abb753fd23fd47624bad57f09c75a6355be6c805a9254e15cf45df9549dcb' \
        'bash' \
        'Read-only Azure, HTTPS, release, and count-only log checks.'
      ;;
    byok)
      printf '%s\n' \
        'deploy/azure/gate10-byok-browser-acceptance.sh' \
        'e372c39b3141957da6ab4aa39bd3936eb9000f18899d204952e02b29e74a7844' \
        'bash' \
        'One browser BYOK call, no Azure configuration change.'
      ;;
    privacy)
      printf '%s\n' \
        'deploy/azure/gate11-privacy-acceptance.sh' \
        'a7a772e6ec850c51456205120fbdf0b93b0fc3fdf60bdbaee3567f3dc3816a6e' \
        'bash' \
        'Changes only one disposable account after exact confirmations.'
      ;;
    hostname)
      printf '%s\n' \
        'deploy/cloudflare/gate16_public_hostname_boundary.py' \
        'bb528ff37e21a0b4219e5ced7f3f1e5ffbd2ea2324f2cdcda1fdc6e010f94d7c' \
        'python3' \
        'Read-only HTTPS and DNS checks for the friendly public hostnames.'
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
        'c4e2f56d6172a64b22a21894fe29d94836bb3ceb8b9af54aa73fb4e705c68398' \
        'bash' \
        'Changes only the web image twice and restores the candidate.'
      ;;
    promote)
      printf '%s\n' \
        'deploy/azure/gate12-public-budget-promotion.sh' \
        'a5330f5e0a452ebdbecfe7df5a9c90cd52145b602192713a9e6dc7a9a13e19ac' \
        'bash' \
        'Changes only three reviewed trial and fallback settings.'
      ;;
    final-audit)
      printf '%s\n' \
        'deploy/azure/gate9-observability-audit.sh' \
        'f67abb753fd23fd47624bad57f09c75a6355be6c805a9254e15cf45df9549dcb' \
        'bash' \
        'Read-only audit of the promoted 100-user public boundary.'
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
    for gate in deploy audit byok privacy hostname alerts rollback promote final-audit; do
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
  local gate_arguments=()
  case "$phase" in
    audit)
      gate_arguments=(--pilot)
      ;;
    final-audit)
      gate_arguments=(--public)
      ;;
  esac
  "$interpreter" "$gate_path" "${gate_arguments[@]}"
}

trap abda_operator_cleanup EXIT
abda_operator_main "$@"
