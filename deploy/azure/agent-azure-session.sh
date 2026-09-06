#!/usr/bin/env bash

# Operator-initiated Azure login for agent-driven ABDA-NL development.
# This helper never deploys, modifies, or deletes an Azure resource.
# It does not narrow the Azure RBAC permissions of the signed-in user.

set -Eeuo pipefail
set +x
umask 077

ABDA_AZURE_ROOT="${ABDA_AZURE_ROOT:-${HOME}/.local/share/abda-azure}"
ABDA_AZURE_CLI="$ABDA_AZURE_ROOT/cli/bin/az"
ABDA_AZURE_PYTHON="$ABDA_AZURE_ROOT/cli/bin/python"
ABDA_AZURE_SUBSCRIPTION='00e62f6e-2174-40b2-b428-8ebfd7c2ac54'
ABDA_AZURE_TENANT='040f05eb-33ab-462f-af54-fb4bedb055ae'
ABDA_AZURE_USER='hliu2@cloudbank.org'

if [[ ! -d "$ABDA_AZURE_ROOT" || -L "$ABDA_AZURE_ROOT" ||
      ! -O "$ABDA_AZURE_ROOT" || ! -x "$ABDA_AZURE_CLI" ||
      ! -x "$ABDA_AZURE_PYTHON" ]]; then
  printf 'STOP: the private ABDA Azure CLI installation is unavailable.\n' >&2
  exit 1
fi

export AZURE_CONFIG_DIR="$ABDA_AZURE_ROOT/config"
if [[ -L "$AZURE_CONFIG_DIR" ||
      ( -e "$AZURE_CONFIG_DIR" && ! -O "$AZURE_CONFIG_DIR" ) ]]; then
  printf 'STOP: the dedicated Azure session directory is not private.\n' >&2
  exit 1
fi
mkdir -p "$AZURE_CONFIG_DIR"
chmod 700 "$ABDA_AZURE_ROOT" "$AZURE_CONFIG_DIR"
export AZURE_CORE_COLLECT_TELEMETRY=false
export AZURE_LOGGING_ENABLE_LOG_FILE=false
export AZURE_CORE_LOGIN_EXPERIENCE_V2=off
export AZURE_EXTENSION_USE_DYNAMIC_INSTALL=no

abda_session_status() {
  timeout 30s "$ABDA_AZURE_CLI" account show --only-show-errors \
    --query '{subscription:id,tenant:tenantId,user:user.name,state:state}' \
    --output json |
    "$ABDA_AZURE_PYTHON" -c '
import json
import sys

try:
    account = json.load(sys.stdin)
except (ValueError, TypeError):
    raise SystemExit("azure_session: unavailable; run the login command")
subscription, tenant, user = sys.argv[1:]
if not isinstance(account, dict) or (
    account.get("subscription") != subscription
    or account.get("tenant") != tenant
    or str(account.get("user", "")).lower() != user
    or account.get("state") != "Enabled"
):
    raise SystemExit("STOP: the Azure identity or subscription is not the approved ABDA account")
print("azure_identity: verified")
print("azure_subscription: verified")
print("credentials_printed: false")
print("azure_resources_changed: false")
print("result: ABDA_AGENT_AZURE_SESSION_READY")
' "$ABDA_AZURE_SUBSCRIPTION" "$ABDA_AZURE_TENANT" "$ABDA_AZURE_USER"
}

case "${1:-}" in
  login)
    printf '%s\n' \
      'This signs the private Delta CLI into your existing Azure account.' \
      'It grants no new Azure role and changes no cloud resource.' \
      'Its session has your existing account permissions, not a new resource-group-only role.' \
      'The Linux token cache is private to this Unix account, outside the repository.' \
      'Open the Microsoft sign-in page shown below on your own computer.' \
      'Enter the displayed device code there and sign in as hliu2@cloudbank.org.' \
      'Complete MFA in the browser. Do not send passwords, MFA codes, or tokens to Codex.'
    "$ABDA_AZURE_CLI" login --tenant "$ABDA_AZURE_TENANT" \
      --use-device-code --output none
    "$ABDA_AZURE_CLI" account set --subscription "$ABDA_AZURE_SUBSCRIPTION" \
      --only-show-errors
    abda_session_status
    ;;
  status)
    abda_session_status
    ;;
  logout)
    "$ABDA_AZURE_CLI" logout --only-show-errors
    printf '%s\n' \
      'result: ABDA_AGENT_AZURE_SESSION_LOGGED_OUT' \
      'Only the dedicated local Azure CLI session was signed out.'
    ;;
  *)
    printf 'Usage: bash agent-azure-session.sh {login|status|logout}\n' >&2
    exit 2
    ;;
esac
