#!/usr/bin/env bash

# Live, content-safe MCP read and revocation acceptance for Codex and Claude Code.
# This gate never changes Azure configuration, creates a project, or calls an
# ABDA-NL model provider. The operator creates and later revokes one read-only
# token in the browser. Raw client transcripts remain private and are deleted.

ABDA_MCP_READ_SCRIPT_REVISION='5'
ABDA_MCP_READ_ROOT=''
ABDA_NL_MCP_TOKEN=''

abda_mcp_read_cleanup() {
  local exit_code=$?
  trap - ERR INT
  set +e
  unset ABDA_NL_MCP_TOKEN
  if [[ "${ABDA_MCP_READ_ROOT:-}" == /tmp/abda-nl-mcp-read.* &&
        -d "${ABDA_MCP_READ_ROOT:-}" ]]; then
    rm -rf -- "$ABDA_MCP_READ_ROOT"
  fi
  printf '\nMCP read client acceptance shell exit code: %s\n' "$exit_code"
}

abda_mcp_read_error() {
  local exit_code=$?
  trap - ERR
  printf '\nSTOP: MCP read client acceptance failed in section: %s\n' \
    "${ABDA_MCP_READ_SECTION:-unknown}" >&2
  printf '%s\n' \
    'No Azure configuration, project, or ABDA-NL model provider was changed.' \
    'The temporary client transcripts and token environment value will be removed.' \
    'Send the visible section name and shell exit code to Codex.' >&2
  exit "$exit_code"
}

abda_mcp_read_interrupt() {
  trap - ERR INT
  printf '\nSTOP: MCP read client acceptance was interrupted in section: %s\n' \
    "${ABDA_MCP_READ_SECTION:-unknown}" >&2
  exit 130
}

abda_mcp_read_fail() {
  printf 'STOP: %s\n' "$*" >&2
  return 1
}

abda_mcp_read_set_constants() {
  ABDA_PUBLIC_ORIGIN='https://demo.abda-nl.org'
  ABDA_MCP_URL='https://demo.abda-nl.org/mcp/'
  ABDA_MCP_TOOL='list_examples'
  ABDA_MCP_CLAUDE_TOOL='mcp__abda_nl__list_examples'
}

abda_mcp_read_write_output_schema() {
  local path=$1
  python3 - "$path" <<'PY'
import json
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
schema = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "success": {"type": "boolean"},
        "example_count": {"type": "integer", "minimum": 0},
    },
    "required": ["success", "example_count"],
}
path.write_text(json.dumps(schema, separators=(",", ":")), encoding="utf-8")
os.chmod(path, 0o600)
PY
}

abda_mcp_read_validate_token_format() {
  python3 - <<'PY'
import os
import re

token = os.environ.get("ABDA_NL_MCP_TOKEN", "")
if not 40 <= len(token) <= 128:
    raise SystemExit("STOP: the hidden value is not an ABDA-NL MCP token")
if not re.fullmatch(r"abda_mcp_[A-Za-z0-9_-]+", token):
    raise SystemExit("STOP: the hidden value is not an ABDA-NL MCP token")
PY
}

abda_mcp_read_write_curl_auth() {
  local path=$1
  python3 - "$path" <<'PY'
import os
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
token = os.environ.get("ABDA_NL_MCP_TOKEN", "")
if not re.fullmatch(r"abda_mcp_[A-Za-z0-9_-]{31,119}", token):
    raise SystemExit("STOP: refusing to create an invalid bearer header")
path.write_text(f'header = "Authorization: Bearer {token}"\n', encoding="utf-8")
path.chmod(0o600)
PY
}

abda_mcp_read_http_status() {
  local body_path=$1
  local auth_config=${2:-}
  local -a command=(
    curl --silent --show-error --max-time 20
    --output "$body_path" --write-out '%{http_code}'
    --request POST
    --header 'Content-Type: application/json'
    --header 'Accept: application/json, text/event-stream'
    --data '{}'
  )
  if [[ -n "$auth_config" ]]; then
    command+=(--config "$auth_config")
  fi
  command+=("$ABDA_MCP_URL")
  "${command[@]}"
}

abda_mcp_read_validate_codex_positive() {
  local path=$1
  local exit_code=$2
  python3 - "$path" "$exit_code" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
exit_code = int(sys.argv[2])
if exit_code != 0:
    raise SystemExit("STOP: Codex did not complete the read test")
try:
    events = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit("STOP: Codex did not produce valid JSONL") from exc
completed = [
    event.get("item")
    for event in events
    if event.get("type") == "item.completed"
    and isinstance(event.get("item"), dict)
]
forbidden = {"command_execution", "file_change", "web_search", "image_generation"}
if any(item.get("type") in forbidden for item in completed):
    raise SystemExit("STOP: Codex used a non-MCP tool")
calls = [item for item in completed if item.get("type") == "mcp_tool_call"]
if len(calls) != 1:
    raise SystemExit("STOP: Codex did not complete exactly one MCP tool call")
call = calls[0]
if call.get("server") != "abda_nl" or call.get("tool") != "list_examples":
    raise SystemExit("STOP: Codex called an unexpected MCP server or tool")
if call.get("status") != "completed" or call.get("error"):
    raise SystemExit("STOP: the Codex MCP read did not succeed")

def find_examples(value, depth=0):
    if depth > 8:
        return None
    if isinstance(value, dict):
        examples = value.get("examples")
        if isinstance(examples, list):
            return examples
        for child in value.values():
            found = find_examples(child, depth + 1)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_examples(child, depth + 1)
            if found is not None:
                return found
    return None

examples = find_examples(call.get("result"))
if not examples or not all(isinstance(item, dict) for item in examples):
    raise SystemExit("STOP: the Codex result lacks the public example list")
if not any(event.get("type") == "turn.completed" for event in events):
    raise SystemExit("STOP: the Codex turn did not complete")
PY
}

abda_mcp_read_validate_codex_revoked() {
  local path=$1
  local exit_code=$2
  python3 - "$path" "$exit_code" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
exit_code = int(sys.argv[2])
if exit_code != 0:
    raise SystemExit("STOP: Codex did not finish the revocation check")
try:
    events = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit("STOP: Codex did not produce valid revocation JSONL") from exc
if not any(event.get("type") == "turn.completed" for event in events):
    raise SystemExit("STOP: the Codex revocation turn did not complete")
completed = [
    event.get("item")
    for event in events
    if event.get("type") == "item.completed"
    and isinstance(event.get("item"), dict)
]
forbidden = {"command_execution", "file_change", "web_search", "image_generation"}
if any(item.get("type") in forbidden for item in completed):
    raise SystemExit("STOP: Codex used a non-MCP tool during revocation")
for item in completed:
    if item.get("type") != "mcp_tool_call":
        continue
    if item.get("server") != "abda_nl" or item.get("tool") != "list_examples":
        raise SystemExit("STOP: Codex called an unexpected MCP server or tool")
    if item.get("status") == "completed" and not item.get("error"):
        raise SystemExit("STOP: Codex accessed MCP after token revocation")
PY
}

abda_mcp_read_validate_claude_positive() {
  local path=$1
  local exit_code=$2
  python3 - "$path" "$exit_code" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
exit_code = int(sys.argv[2])
if exit_code != 0:
    raise SystemExit("STOP: Claude Code did not complete the read test")
try:
    events = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit("STOP: Claude Code did not produce valid JSONL") from exc

blocks = []
for event in events:
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        blocks.extend(item for item in content if isinstance(item, dict))
uses = [
    item
    for item in blocks
    if item.get("type") == "tool_use"
    and str(item.get("name") or "").startswith("mcp__")
]
if len(uses) != 1 or uses[0].get("name") != "mcp__abda_nl__list_examples":
    raise SystemExit("STOP: Claude Code did not call exactly one allowed MCP tool")
tool_id = uses[0].get("id")
results = [
    item
    for item in blocks
    if item.get("type") == "tool_result" and item.get("tool_use_id") == tool_id
]
if len(results) != 1 or results[0].get("is_error") is True:
    raise SystemExit("STOP: the Claude Code MCP read did not succeed")

def find_examples(value, depth=0):
    if depth > 10:
        return None
    if isinstance(value, str):
        try:
            return find_examples(json.loads(value), depth + 1)
        except json.JSONDecodeError:
            return None
    if isinstance(value, dict):
        examples = value.get("examples")
        if isinstance(examples, list):
            return examples
        for child in value.values():
            found = find_examples(child, depth + 1)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_examples(child, depth + 1)
            if found is not None:
                return found
    return None

examples = find_examples(results[0].get("content"))
if not examples or not all(isinstance(item, dict) for item in examples):
    raise SystemExit("STOP: the Claude Code result lacks the public example list")
finals = [event for event in events if event.get("type") == "result"]
if len(finals) != 1 or finals[0].get("is_error") is True:
    raise SystemExit("STOP: the Claude Code turn did not complete")
structured = finals[0].get("structured_output")
if not isinstance(structured, dict) or structured.get("success") is not True:
    raise SystemExit("STOP: Claude Code did not report a successful MCP read")
if structured.get("example_count") != len(examples):
    raise SystemExit("STOP: the Claude Code public example count is inconsistent")
PY
}

abda_mcp_read_validate_claude_revoked() {
  local path=$1
  local exit_code=$2
  python3 - "$path" "$exit_code" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
exit_code = int(sys.argv[2])
if exit_code != 0:
    raise SystemExit("STOP: Claude Code did not finish the revocation check")
try:
    events = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit("STOP: Claude Code did not produce valid revocation JSONL") from exc
blocks = []
for event in events:
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        blocks.extend(item for item in content if isinstance(item, dict))
uses = [
    item
    for item in blocks
    if item.get("type") == "tool_use"
    and str(item.get("name") or "").startswith("mcp__")
]
for item in uses:
    if item.get("name") != "mcp__abda_nl__list_examples":
        raise SystemExit("STOP: Claude Code called an unexpected MCP tool")
    tool_id = item.get("id")
    results = [
        result
        for result in blocks
        if result.get("type") == "tool_result"
        and result.get("tool_use_id") == tool_id
    ]
    if any(result.get("is_error") is not True for result in results):
        raise SystemExit("STOP: Claude Code accessed MCP after token revocation")
finals = [event for event in events if event.get("type") == "result"]
if len(finals) != 1 or finals[0].get("is_error") is True:
    raise SystemExit("STOP: the Claude Code revocation turn did not complete")
structured = finals[0].get("structured_output")
if not isinstance(structured, dict) or structured.get("success") is not False:
    raise SystemExit("STOP: Claude Code did not report the revoked access failure")
if structured.get("example_count") != 0:
    raise SystemExit("STOP: Claude Code reported examples after token revocation")
PY
}

abda_mcp_read_run_codex() {
  local phase=$1
  local output=$2
  local errors=$3
  local prompt
  if [[ "$phase" == 'active' ]]; then
    prompt='Use only the ABDA-NL MCP server. Call list_examples exactly once. Do not call shell or any other tool. Return success true and only the number of examples. Do not include example content, configuration, credentials, or other details.'
  else
    prompt='Try to call the ABDA-NL list_examples tool exactly once. The credential was revoked. Do not call shell or any other tool. Return success false and example_count zero when access is unavailable. Never include error details, configuration, credentials, or example content.'
  fi
  if timeout --kill-after=10s 180s codex exec \
      --ephemeral \
      --sandbox read-only \
      --ignore-user-config \
      --ignore-rules \
      --strict-config \
      --skip-git-repo-check \
      --color never \
      -C "$ABDA_MCP_READ_ROOT/client-work" \
      --json \
      --output-schema "$ABDA_MCP_READ_ROOT/output-schema.json" \
      -c 'shell_environment_policy.inherit="none"' \
      -c "mcp_servers.abda_nl.url=\"$ABDA_MCP_URL\"" \
      -c 'mcp_servers.abda_nl.bearer_token_env_var="ABDA_NL_MCP_TOKEN"' \
      -c 'mcp_servers.abda_nl.default_tools_approval_mode="writes"' \
      -c 'mcp_servers.abda_nl.enabled_tools=["list_examples"]' \
      -c 'mcp_servers.abda_nl.tool_timeout_sec=60' \
      "$prompt" >"$output" 2>"$errors"; then
    ABDA_CLIENT_EXIT=0
  else
    ABDA_CLIENT_EXIT=$?
  fi
}

abda_mcp_read_run_claude() {
  local phase=$1
  local output=$2
  local errors=$3
  local prompt
  local schema
  local mcp_config
  schema="$(<"$ABDA_MCP_READ_ROOT/output-schema.json")"
  mcp_config='{"mcpServers":{"abda_nl":{"type":"http","url":"https://demo.abda-nl.org/mcp/","headers":{"Authorization":"Bearer ${ABDA_NL_MCP_TOKEN}"}}}}'
  if [[ "$phase" == 'active' ]]; then
    prompt='Use only the ABDA-NL list_examples MCP tool, exactly once. Return success true and only the number of examples. Do not include example content, configuration, credentials, or other details.'
  else
    prompt='Try to use the ABDA-NL list_examples MCP tool exactly once. The credential was revoked. Return success false and example_count zero when access is unavailable. Never include error details, configuration, credentials, or example content.'
  fi
  if timeout --kill-after=10s 180s claude -p \
      --no-session-persistence \
      --strict-mcp-config \
      --setting-sources '' \
      --disable-slash-commands \
      --no-chrome \
      --tools "$ABDA_MCP_CLAUDE_TOOL" \
      --allowedTools "$ABDA_MCP_CLAUDE_TOOL" \
      --permission-mode dontAsk \
      --model haiku \
      --effort low \
      --max-budget-usd 0.50 \
      --output-format stream-json \
      --verbose \
      --json-schema "$schema" \
      --mcp-config "$mcp_config" \
      --system-prompt 'Follow the user instruction exactly. Never reveal credentials, configuration, tool payloads, or example content.' \
      "$prompt" >"$output" 2>"$errors"; then
    ABDA_CLIENT_EXIT=0
  else
    ABDA_CLIENT_EXIT=$?
  fi
}

abda_mcp_read_main() {
  set -Eeuo pipefail
  set +x
  umask 077
  unset HISTFILE
  trap abda_mcp_read_cleanup EXIT
  trap abda_mcp_read_error ERR
  trap abda_mcp_read_interrupt INT
  abda_mcp_read_set_constants

  printf 'ABDA-NL MCP read client acceptance script revision: %s\n' \
    "$ABDA_MCP_READ_SCRIPT_REVISION"
  printf '%s\n' \
    'This gate calls only the public list_examples MCP tool.' \
    'It runs two Codex turns and two Claude Code turns, including revocation checks.' \
    'It does not change Azure, create a project, or call an ABDA-NL model provider.' \
    'Raw client transcripts are never printed and are deleted on exit.'

  ABDA_MCP_READ_SECTION='client and HTTPS preflight'
  printf '\n[1/7] Verifying the local clients and public MCP authentication boundary...\n'
  for command in codex claude curl python3 timeout; do
    command -v "$command" >/dev/null || \
      abda_mcp_read_fail "required command is unavailable: $command"
  done
  ABDA_CODEX_VERSION="$(codex --version)"
  ABDA_CLAUDE_VERSION="$(claude --version)"
  [[ "$ABDA_CODEX_VERSION" =~ ^codex-cli[[:space:]][0-9] ]] || \
    abda_mcp_read_fail 'the Codex CLI version could not be identified'
  [[ "$ABDA_CLAUDE_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+ ]] || \
    abda_mcp_read_fail 'the Claude Code version could not be identified'
  ABDA_MCP_READ_ROOT="$(mktemp -d /tmp/abda-nl-mcp-read.XXXXXX)"
  curl --fail --silent --show-error --max-time 20 \
    "$ABDA_PUBLIC_ORIGIN/health/ready" \
    >"$ABDA_MCP_READ_ROOT/public-ready.json"
  mkdir -p "$ABDA_MCP_READ_ROOT/client-work"
  abda_mcp_read_write_output_schema "$ABDA_MCP_READ_ROOT/output-schema.json"
  ABDA_ANONYMOUS_STATUS="$(abda_mcp_read_http_status \
    "$ABDA_MCP_READ_ROOT/anonymous.body")"
  [[ "$ABDA_ANONYMOUS_STATUS" == '401' ]] || \
    abda_mcp_read_fail 'the public MCP endpoint accepted an anonymous request'
  printf 'codex_version: %s\n' "$ABDA_CODEX_VERSION"
  printf 'claude_version: %s\n' "$ABDA_CLAUDE_VERSION"
  printf 'anonymous_mcp_status: 401\n'

  ABDA_MCP_READ_SECTION='hidden read-only token validation'
  printf '\n[2/7] Loading one short-lived read-only MCP token...\n'
  printf '%s\n' \
    'In the browser, create one token with only projects:read selected.' \
    'Before copying it, inspect the Claude command and confirm that -- appears' \
    'between the header value and the abda-nl server name.' \
    'Paste only the token at the hidden prompt. Nothing will be displayed.'
  IFS= read -r -s -p 'ABDA-NL read-only MCP token: ' ABDA_NL_MCP_TOKEN
  printf '\n'
  export ABDA_NL_MCP_TOKEN
  abda_mcp_read_validate_token_format
  abda_mcp_read_write_curl_auth "$ABDA_MCP_READ_ROOT/curl-auth.conf"
  ABDA_ACTIVE_STATUS="$(abda_mcp_read_http_status \
    "$ABDA_MCP_READ_ROOT/active.body" \
    "$ABDA_MCP_READ_ROOT/curl-auth.conf")"
  [[ "$ABDA_ACTIVE_STATUS" == '400' ]] || \
    abda_mcp_read_fail 'the supplied MCP token is not active at the public endpoint'
  printf 'active_read_token_status: verified\n'

  ABDA_MCP_READ_SECTION='generated Claude command boundary confirmation'
  printf '\n[3/7] Recording the exact generated-command boundary confirmation...\n'
  printf '%s\n' \
    'In the browser-generated Claude command, confirm that the complete' \
    '--header value is followed by -- and then the abda-nl server name.'
  IFS= read -r -p \
    'Type CLAUDE_COMMAND_BOUNDARY_CONFIRMED to continue: ' \
    ABDA_COMMAND_CONFIRMATION
  [[ "$ABDA_COMMAND_CONFIRMATION" == 'CLAUDE_COMMAND_BOUNDARY_CONFIRMED' ]] || \
    abda_mcp_read_fail 'the generated Claude command boundary was not confirmed'
  unset ABDA_COMMAND_CONFIRMATION
  printf 'claude_command_argument_boundary: passed\n'
  printf 'real_token_stored_in_claude_config: false\n'

  ABDA_MCP_READ_SECTION='live Codex and Claude read acceptance'
  printf '\n[4/7] Running one public-example read through each real client...\n'
  abda_mcp_read_run_codex active \
    "$ABDA_MCP_READ_ROOT/codex-active.jsonl" \
    "$ABDA_MCP_READ_ROOT/codex-active.stderr"
  abda_mcp_read_validate_codex_positive \
    "$ABDA_MCP_READ_ROOT/codex-active.jsonl" "$ABDA_CLIENT_EXIT"
  printf 'codex_read: passed\n'
  abda_mcp_read_run_claude active \
    "$ABDA_MCP_READ_ROOT/claude-active.jsonl" \
    "$ABDA_MCP_READ_ROOT/claude-active.stderr"
  abda_mcp_read_validate_claude_positive \
    "$ABDA_MCP_READ_ROOT/claude-active.jsonl" "$ABDA_CLIENT_EXIT"
  printf 'claude_read: passed\n'

  ABDA_MCP_READ_SECTION='browser token revocation'
  printf '\n[5/7] Revoke the same token in the browser now...\n'
  printf '%s\n' \
    'Keep this shell open.' \
    'At demo.abda-nl.org, open Research workspace, then Codex and Claude.' \
    'Revoke the exact token used above. Do not create another token.' \
    'After the token disappears or shows revoked, return here.'
  IFS= read -r -p 'Type TOKEN_REVOKED to continue: ' ABDA_REVOCATION_CONFIRMATION
  [[ "$ABDA_REVOCATION_CONFIRMATION" == 'TOKEN_REVOKED' ]] || \
    abda_mcp_read_fail 'token revocation was not confirmed'
  unset ABDA_REVOCATION_CONFIRMATION
  ABDA_REVOKED_STATUS="$(abda_mcp_read_http_status \
    "$ABDA_MCP_READ_ROOT/revoked.body" \
    "$ABDA_MCP_READ_ROOT/curl-auth.conf")"
  [[ "$ABDA_REVOKED_STATUS" == '401' ]] || \
    abda_mcp_read_fail 'the revoked token is still accepted by the public endpoint'
  printf 'revoked_token_status: 401\n'

  ABDA_MCP_READ_SECTION='live Codex and Claude revocation acceptance'
  printf '\n[6/7] Proving both real clients can no longer access MCP...\n'
  abda_mcp_read_run_codex revoked \
    "$ABDA_MCP_READ_ROOT/codex-revoked.jsonl" \
    "$ABDA_MCP_READ_ROOT/codex-revoked.stderr"
  abda_mcp_read_validate_codex_revoked \
    "$ABDA_MCP_READ_ROOT/codex-revoked.jsonl" "$ABDA_CLIENT_EXIT"
  printf 'codex_revocation: passed\n'
  abda_mcp_read_run_claude revoked \
    "$ABDA_MCP_READ_ROOT/claude-revoked.jsonl" \
    "$ABDA_MCP_READ_ROOT/claude-revoked.stderr"
  abda_mcp_read_validate_claude_revoked \
    "$ABDA_MCP_READ_ROOT/claude-revoked.jsonl" "$ABDA_CLIENT_EXIT"
  printf 'claude_revocation: passed\n'
  unset ABDA_NL_MCP_TOKEN

  ABDA_MCP_READ_SECTION='content-free receipt'
  printf '\n[7/7] MCP read and revocation acceptance is complete.\n'
  printf '\nABDA-NL MCP read client acceptance status:\n'
  printf 'script_revision: %s\n' "$ABDA_MCP_READ_SCRIPT_REVISION"
  printf 'public_origin: %s\n' "$ABDA_PUBLIC_ORIGIN"
  printf 'codex_version: %s\n' "$ABDA_CODEX_VERSION"
  printf 'codex_read: passed\n'
  printf 'codex_revocation: passed\n'
  printf 'claude_version: %s\n' "$ABDA_CLAUDE_VERSION"
  printf 'claude_command_argument_boundary: passed\n'
  printf 'claude_read: passed\n'
  printf 'claude_revocation: passed\n'
  printf 'token_scope: projects:read\n'
  printf 'token_revoked: true\n'
  printf 'private_project_tools_enabled: false\n'
  printf 'abda_model_provider_called: false\n'
  printf 'raw_client_logs_printed: false\n'
  printf 'raw_client_logs_retained: false\n'
  printf 'result: LIVE_CODEX_AND_CLAUDE_MCP_READ_ACCEPTANCE_VERIFIED\n'
  printf '%s\n' \
    'Send this status and the shell exit code to Codex.'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  abda_mcp_read_main "$@"
fi
