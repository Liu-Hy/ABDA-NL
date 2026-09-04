#!/usr/bin/env bash

# Download, verify, and run one exact gate from the post-privacy cumulative
# release sequence. The prepared privacy Gate remains independently pinned so
# this helper cannot bypass or alter its deletion boundary.

set -Eeuo pipefail
set +x
umask 077

ABDA_POST_PRIVACY_SCRIPT_REVISION='4'
ABDA_POST_PRIVACY_SOURCE_COMMIT='54937e1dd716cfa0e3dd7ca3eb6f93a11bde472c'
ABDA_POST_PRIVACY_ROOT=''

abda_post_privacy_cleanup() {
  local exit_code=$?
  set +e
  if [[ "${ABDA_POST_PRIVACY_ROOT:-}" == /tmp/abda-nl-post-privacy.* &&
        -d "${ABDA_POST_PRIVACY_ROOT:-}" ]]; then
    rm -rf -- "$ABDA_POST_PRIVACY_ROOT"
  fi
  return "$exit_code"
}

abda_post_privacy_usage() {
  cat <<'EOF'
Usage: post-privacy-operator-gate.sh PHASE

Phases, in required order:
  verify       Download and hash-check every pinned gate without running one
  deploy       Deploy only the cumulative accounting-integrity image
  audit        Run its read-only release and sanitized-log audit
  hostname     Verify the Cloudflare redirect and public DNS boundary
  rollback     Rehearse compatible rollback and automatic restoration
  promote      Promote 10 users to 100 and enable bounded outage fallback
  final-audit  Run the read-only audit against the promoted public limits

There is intentionally no run-all phase. Mutating gates retain their own exact
confirmations, prerequisite checks, and resume boundaries.
EOF
}

abda_post_privacy_gate_metadata() {
  local phase=$1
  case "$phase" in
    deploy)
      printf '%s\n' \
        'deploy/azure/gate20-rate-limit-retention-image.sh' \
        '782bfff583f9c3f9770c7e5af22bc47dea9f0b32e89d302776f2549f3669b4b3' \
        'bash' \
        'Changes only the existing web image and revision suffix.'
      ;;
    audit)
      printf '%s\n' \
        'deploy/azure/gate21-rate-limit-retention-audit.sh' \
        '88f291c01ef4c8e6184aaa0392e6552f38409662beb7e7a9c90a05b101d65bcf' \
        'bash' \
        'Read-only Azure, HTTPS, release, and count-only log checks.'
      ;;
    hostname)
      printf '%s\n' \
        'deploy/cloudflare/gate16_public_hostname_boundary.py' \
        'bb528ff37e21a0b4219e5ced7f3f1e5ffbd2ea2324f2cdcda1fdc6e010f94d7c' \
        'python3' \
        'Read-only HTTPS and DNS checks for the friendly public hostnames.'
      ;;
    rollback)
      printf '%s\n' \
        'deploy/azure/gate22-rate-limit-retention-rollback.sh' \
        'f1c78216e10eb4c2a2426795b2f40e04446430a2cc0c7255121d65bc7a93ab0e' \
        'bash' \
        'Changes only the web image twice and restores the cumulative image.'
      ;;
    promote)
      printf '%s\n' \
        'deploy/azure/gate23-rate-limit-retention-promotion.sh' \
        'e9489a5fe7d6203a36ccf42d264777baf6d856ff7a52af8415f0f9973f3a31cb' \
        'bash' \
        'Changes only three reviewed trial and fallback settings.'
      ;;
    final-audit)
      printf '%s\n' \
        'deploy/azure/gate21-rate-limit-retention-audit.sh' \
        '88f291c01ef4c8e6184aaa0392e6552f38409662beb7e7a9c90a05b101d65bcf' \
        'bash' \
        'Read-only audit of the promoted 100-user public boundary.'
      ;;
    *)
      return 1
      ;;
  esac
}

abda_post_privacy_download() {
  local phase=$1
  local metadata=''
  metadata="$(abda_post_privacy_gate_metadata "$phase")" || return 1
  local relative_path=''
  local expected_sha256=''
  local interpreter=''
  local boundary=''
  local fields=()
  mapfile -t fields <<<"$metadata"
  relative_path="${fields[0]}"
  expected_sha256="${fields[1]}"
  interpreter="${fields[2]}"
  boundary="${fields[3]}"
  local destination="$ABDA_POST_PRIVACY_ROOT/${relative_path##*/}"
  curl --fail --silent --show-error --location \
    --proto '=https' --tlsv1.2 \
    "https://raw.githubusercontent.com/Liu-Hy/ABDA-NL/$ABDA_POST_PRIVACY_SOURCE_COMMIT/$relative_path" \
    --output "$destination"
  printf '%s  %s\n' "$expected_sha256" "$destination" | \
    sha256sum --check --status
  printf '%s\n' "$destination" "$interpreter" "$boundary"
}

abda_post_privacy_main() {
  local phase="${1:-}"
  if [[ "$phase" == 'help' || "$phase" == '--help' || "$phase" == '-h' ]]; then
    abda_post_privacy_usage
    return 0
  fi
  if [[ -z "$phase" ]]; then
    abda_post_privacy_usage >&2
    return 2
  fi

  local command_name=''
  for command_name in curl sha256sum; do
    command -v "$command_name" >/dev/null 2>&1 || {
      printf 'Required command is unavailable: %s\n' "$command_name" >&2
      return 1
    }
  done
  ABDA_POST_PRIVACY_ROOT="$(mktemp -d /tmp/abda-nl-post-privacy.XXXXXX)"
  chmod 700 "$ABDA_POST_PRIVACY_ROOT"

  printf 'ABDA-NL post-privacy operator helper revision: %s\n' \
    "$ABDA_POST_PRIVACY_SCRIPT_REVISION"
  printf 'Pinned gate source commit: %s\n' "$ABDA_POST_PRIVACY_SOURCE_COMMIT"

  if [[ "$phase" == 'verify' ]]; then
    local gate=''
    for gate in deploy audit hostname rollback promote final-audit; do
      abda_post_privacy_download "$gate" >/dev/null
      printf 'verified: %s\n' "$gate"
    done
    printf 'result: ALL_POST_PRIVACY_OPERATOR_GATES_VERIFIED\n'
    return 0
  fi

  local metadata=''
  metadata="$(abda_post_privacy_gate_metadata "$phase")" || {
    printf 'Unknown phase: %s\n\n' "$phase" >&2
    abda_post_privacy_usage >&2
    return 2
  }
  local download_result=''
  download_result="$(abda_post_privacy_download "$phase")"
  local downloaded=()
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

trap abda_post_privacy_cleanup EXIT
abda_post_privacy_main "$@"
