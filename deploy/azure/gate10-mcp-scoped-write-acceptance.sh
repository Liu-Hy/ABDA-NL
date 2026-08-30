#!/usr/bin/env bash

# Live, bounded MCP scope, write, version, proposal, cleanup, and revocation
# acceptance. The operator supplies two disposable tokens through hidden prompts.
# One temporary project is created from a bundled public example and must be
# removed in the browser before the gate can pass.

ABDA_MCP_SCOPED_SCRIPT_REVISION='3'
ABDA_MCP_SCOPED_ROOT=''
ABDA_MCP_READ_TOKEN=''
ABDA_MCP_WRITE_TOKEN=''

abda_mcp_scoped_cleanup() {
  local exit_code=$?
  trap - ERR INT
  set +e
  unset ABDA_MCP_READ_TOKEN
  unset ABDA_MCP_WRITE_TOKEN
  if [[ "${ABDA_MCP_SCOPED_ROOT:-}" == /tmp/abda-nl-mcp-scoped.* &&
        -d "${ABDA_MCP_SCOPED_ROOT:-}" ]]; then
    rm -rf -- "$ABDA_MCP_SCOPED_ROOT"
  fi
  printf '\nMCP scoped-write acceptance shell exit code: %s\n' "$exit_code"
}

abda_mcp_scoped_error() {
  local exit_code=$?
  trap - ERR
  printf '\nSTOP: MCP scoped-write acceptance failed in section: %s\n' \
    "${ABDA_MCP_SCOPED_SECTION:-unknown}" >&2
  if [[ -f "${ABDA_MCP_SCOPED_ROOT:-}/project-created" ]]; then
    printf '%s\n' \
      'A disposable project may remain. In Research workspace, delete the newest' \
      'project named MCP scoped acceptance, delete me.' >&2
  fi
  printf '%s\n' \
    'Revoke both disposable acceptance tokens in Research workspace.' \
    'No Azure configuration was changed. No proposal was applied.' \
    'Temporary state and token environment values will now be removed.' \
    'Send only the visible section name and shell exit code to Codex.' >&2
  exit "$exit_code"
}

abda_mcp_scoped_interrupt() {
  trap - ERR INT
  printf '\nSTOP: MCP scoped-write acceptance was interrupted in section: %s\n' \
    "${ABDA_MCP_SCOPED_SECTION:-unknown}" >&2
  exit 130
}

abda_mcp_scoped_fail() {
  printf 'STOP: %s\n' "$*" >&2
  return 1
}

abda_mcp_scoped_set_constants() {
  ABDA_PUBLIC_ORIGIN='https://demo.abda-nl.org'
  ABDA_MCP_SCOPED_URL='https://demo.abda-nl.org/mcp/'
  ABDA_MCP_SCOPED_PROJECT_NAME='MCP scoped acceptance, delete me'
  export ABDA_MCP_SCOPED_URL
  export ABDA_MCP_SCOPED_PROJECT_NAME
}

abda_mcp_scoped_validate_tokens() {
  python3 - <<'PY'
import os
import re

pattern = re.compile(r"abda_mcp_[A-Za-z0-9_-]{31,119}")
read_token = os.environ.get("ABDA_MCP_READ_TOKEN", "")
write_token = os.environ.get("ABDA_MCP_WRITE_TOKEN", "")
if not pattern.fullmatch(read_token):
    raise SystemExit("STOP: the first hidden value is not an ABDA-NL MCP token")
if not pattern.fullmatch(write_token):
    raise SystemExit("STOP: the second hidden value is not an ABDA-NL MCP token")
if read_token == write_token:
    raise SystemExit("STOP: the read-only and full-scope tokens must be different")
PY
}

abda_mcp_scoped_runner() {
  local phase=$1
  local state_path=$2
  python3 - "$phase" "$state_path" <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


phase = sys.argv[1]
state_path = Path(sys.argv[2])
url = os.environ.get("ABDA_MCP_SCOPED_URL", "")
project_name = os.environ.get("ABDA_MCP_SCOPED_PROJECT_NAME", "")
read_token = os.environ.get("ABDA_MCP_READ_TOKEN", "")
write_token = os.environ.get("ABDA_MCP_WRITE_TOKEN", "")

if not url or not project_name:
    raise SystemExit("STOP: the MCP acceptance constants are missing")


class GateFailure(RuntimeError):
    pass


def fail(message: str) -> None:
    raise GateFailure(message)


def request(
    token: str | None,
    method: str,
    params: dict[str, Any] | None,
    request_id: int,
    *,
    timeout: int = 30,
) -> tuple[int, dict[str, Any] | None]:
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
    }
    if params is not None:
        payload["params"] = params
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": "2025-11-25",
        "User-Agent": "ABDA-NL-scoped-write-acceptance/1",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    wire = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    http_request = Request(url, data=wire, headers=headers, method="POST")
    try:
        with urlopen(http_request, timeout=timeout) as response:
            status = response.status
            body = response.read(2_000_000)
    except HTTPError as exc:
        status = exc.code
        body = exc.read(2_000_000)
    except (URLError, TimeoutError, socket.timeout) as exc:
        raise GateFailure("the public MCP endpoint did not respond in time") from exc
    if not body:
        return status, None
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateFailure("the MCP endpoint returned a non-JSON response") from exc
    if not isinstance(value, dict):
        raise GateFailure("the MCP endpoint returned an invalid JSON envelope")
    return status, value


def initialize(token: str | None, request_id: int) -> tuple[int, dict[str, Any] | None]:
    return request(
        token,
        "initialize",
        {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {
                "name": "abda-nl-scoped-write-acceptance",
                "version": "1",
            },
        },
        request_id,
    )


def call_tool(
    token: str,
    name: str,
    arguments: dict[str, Any] | None,
    request_id: int,
    *,
    timeout: int = 30,
) -> dict[str, Any]:
    status, envelope = request(
        token,
        "tools/call",
        {"name": name, "arguments": arguments or {}},
        request_id,
        timeout=timeout,
    )
    if status != 200 or not envelope:
        fail(f"the {name} MCP request did not return HTTP 200")
    if envelope.get("jsonrpc") != "2.0" or envelope.get("id") != request_id:
        fail(f"the {name} MCP response envelope changed")
    result = envelope.get("result")
    if not isinstance(result, dict):
        fail(f"the {name} MCP response has no result")
    return result


def tool_error(result: dict[str, Any]) -> str:
    if result.get("isError") is not True:
        return ""
    content = result.get("content")
    if not isinstance(content, list):
        return ""
    pieces = []
    for item in content:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            pieces.append(item["text"])
    return "\n".join(pieces)


def structured(result: dict[str, Any], name: str) -> dict[str, Any]:
    if result.get("isError") is True:
        fail(f"the {name} MCP tool returned a sanitized error")
    value = result.get("structuredContent")
    if not isinstance(value, dict):
        fail(f"the {name} MCP tool returned no structured content")
    return value


def project_ids(token: str, request_id: int) -> list[str]:
    body = structured(call_tool(token, "list_projects", {}, request_id), "list_projects")
    projects = body.get("projects")
    if not isinstance(projects, list):
        fail("the private project listing changed shape")
    identifiers = []
    for item in projects:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            fail("the private project listing contains an invalid record")
        identifiers.append(item["id"])
    return identifiers


def load_state() -> dict[str, Any]:
    try:
        value = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateFailure("the private acceptance state is unavailable") from exc
    if not isinstance(value, dict):
        fail("the private acceptance state changed shape")
    return value


def save_state(value: dict[str, Any]) -> None:
    state_path.write_text(
        json.dumps(value, separators=(",", ":")),
        encoding="utf-8",
    )
    state_path.chmod(0o600)


def require_active_initialize(token: str, request_id: int, label: str) -> None:
    status, envelope = initialize(token, request_id)
    if status != 200 or not envelope:
        fail(f"the {label} token is not active")
    result = envelope.get("result")
    if not isinstance(result, dict):
        fail(f"the {label} token received no initialization result")
    server_info = result.get("serverInfo")
    if not isinstance(server_info, dict) or server_info.get("name") != "abda-nl":
        fail("the public MCP server identity changed")


def run_preflight() -> None:
    anonymous_status, _ = initialize(None, 1)
    if anonymous_status != 401:
        fail("the public MCP endpoint accepted an anonymous client")
    require_active_initialize(read_token, 2, "read-only")
    require_active_initialize(write_token, 3, "full-scope")

    before_read = project_ids(read_token, 4)
    denied = call_tool(
        read_token,
        "create_project",
        {
            "name": "MCP scope denial probe",
            "source_scenario_id": "__abda_missing_scope_probe__",
        },
        5,
    )
    denied_text = tool_error(denied)
    if "projects:write" not in denied_text:
        fail("the read-only token was not rejected at the write-scope boundary")
    after_read = project_ids(read_token, 6)
    if before_read != after_read:
        fail("the read-only write probe changed the private project list")
    before_write = project_ids(write_token, 7)
    if before_read != before_write:
        fail("the two acceptance tokens do not belong to the same account")
    save_state({"before_project_ids": before_write})
    print("anonymous_authentication: rejected")
    print("read_only_write_scope: rejected_without_mutation")
    print("token_account_match: passed")


def run_mutation() -> None:
    state = load_state()
    before_ids = state.get("before_project_ids")
    if not isinstance(before_ids, list) or not all(
        isinstance(item, str) for item in before_ids
    ):
        fail("the preflight project inventory is invalid")

    created_result = call_tool(
        write_token,
        "create_project",
        {
            "name": project_name,
            "description": "Temporary live MCP acceptance project.",
            "source_scenario_id": "fire_prevention",
        },
        10,
    )
    (state_path.parent / "project-created").touch(mode=0o600)
    created = structured(created_result, "create_project")
    project_id = created.get("id")
    if not isinstance(project_id, str) or not project_id or project_id in before_ids:
        fail("the disposable project identifier is invalid")
    if created.get("version") != 1 or created.get("name") != project_name:
        fail("the disposable project did not start at the expected version")
    state.update({"project_id": project_id, "accepted_version": 1})
    save_state(state)

    loaded = structured(
        call_tool(
            write_token,
            "get_project",
            {"project_id": project_id},
            11,
        ),
        "get_project",
    )
    if loaded.get("version") != 1 or loaded.get("id") != project_id:
        fail("the newly created project could not be read consistently")
    read_loaded = structured(
        call_tool(
            read_token,
            "get_project",
            {"project_id": project_id},
            111,
        ),
        "get_project",
    )
    if read_loaded.get("version") != 1 or read_loaded.get("id") != project_id:
        fail("the read-only and full-scope tokens do not belong to one account")

    accepted_description = "Updated through live MCP scoped acceptance."
    updated = structured(
        call_tool(
            write_token,
            "update_project_metadata",
            {
                "project_id": project_id,
                "expected_version": 1,
                "description": accepted_description,
            },
            12,
        ),
        "update_project_metadata",
    )
    if updated.get("version") != 2 or updated.get("description") != accepted_description:
        fail("the versioned metadata update did not produce version 2")

    stale = call_tool(
        write_token,
        "update_project_metadata",
        {
            "project_id": project_id,
            "expected_version": 1,
            "name": "MCP stale update must not apply",
        },
        13,
    )
    if "changed since it was loaded" not in tool_error(stale):
        fail("the stale metadata update was not rejected as a version conflict")

    before_proposal = structured(
        call_tool(
            write_token,
            "get_project",
            {"project_id": project_id},
            14,
        ),
        "get_project",
    )
    if (
        before_proposal.get("version") != 2
        or before_proposal.get("name") != project_name
        or before_proposal.get("description") != accepted_description
    ):
        fail("the rejected stale update changed the accepted project")

    proposal = structured(
        call_tool(
            write_token,
            "propose_project_edit",
            {
                "project_id": project_id,
                "task": "add-fact",
                "instruction": (
                    "Add a fact that a calibrated temporary air-quality monitor "
                    "is operating in the downwind community."
                ),
            },
            15,
            timeout=180,
        ),
        "propose_project_edit",
    )
    operation = proposal.get("op")
    if (
        proposal.get("project_id") != project_id
        or proposal.get("expected_version") != 2
        or not isinstance(operation, dict)
        or operation.get("op") != "add-fact"
    ):
        fail("the model proposal did not return the expected bounded operation")
    if proposal.get("billing_source") != "cloudbank":
        fail("the live proposal did not use the funded CloudBank route")
    cost = proposal.get("cost_microusd")
    if not isinstance(cost, int) or cost <= 0:
        fail("the live proposal did not record a positive settled cost")

    after_proposal = structured(
        call_tool(
            write_token,
            "get_project",
            {"project_id": project_id},
            16,
        ),
        "get_project",
    )
    if after_proposal != before_proposal:
        fail("the proposal changed the project before explicit application")
    state["accepted_version"] = 2
    save_state(state)
    print("scoped_project_create_and_read: passed")
    print("token_account_match: passed")
    print("optimistic_metadata_update: passed")
    print("stale_version_rejection: passed")
    print("funded_cloudbank_route: passed")
    print("funded_proposal_cost_recorded: passed")
    print("proposal_did_not_apply: passed")


def run_deleted() -> None:
    state = load_state()
    project_id = state.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        fail("the disposable project identifier is missing")
    missing = call_tool(
        write_token,
        "get_project",
        {"project_id": project_id},
        20,
    )
    if "project not found" not in tool_error(missing).lower():
        fail("the disposable project is still accessible")
    if project_id in project_ids(write_token, 21):
        fail("the disposable project remains in the active project list")
    print("disposable_project_removed: passed")


def run_revoked() -> None:
    for request_id, label, token in (
        (30, "read-only", read_token),
        (31, "full-scope", write_token),
    ):
        status, _ = initialize(token, request_id)
        if status != 401:
            fail(f"the revoked {label} token still authenticates")
    print("read_only_token_revocation: passed")
    print("full_scope_token_revocation: passed")


try:
    if phase == "preflight":
        run_preflight()
    elif phase == "mutation":
        run_mutation()
    elif phase == "deleted":
        run_deleted()
    elif phase == "revoked":
        run_revoked()
    else:
        fail("the scoped-write runner phase is invalid")
except GateFailure as exc:
    print(f"STOP: {exc}", file=sys.stderr)
    raise SystemExit(1) from None
PY
}

abda_mcp_scoped_main() {
  abda_mcp_scoped_set_constants
  printf 'ABDA-NL MCP scoped-write acceptance script revision: %s\n' \
    "$ABDA_MCP_SCOPED_SCRIPT_REVISION"
  printf '%s\n' \
    'This gate uses one read-only token and one temporary full-scope token.' \
    'It creates one disposable private project and makes one funded proposal.' \
    'The proposal is inspected but never applied. No Azure setting is changed.' \
    'Raw MCP payloads, project identifiers, email addresses, and tokens are not printed.'

  ABDA_MCP_SCOPED_SECTION='public endpoint and token input'
  printf '\n[1/7] Verifying the public endpoint and loading two disposable tokens...\n'
  curl --fail --silent --show-error --max-time 20 \
    "$ABDA_PUBLIC_ORIGIN/health/ready" \
    >"$ABDA_MCP_SCOPED_ROOT/public-ready.json"
  printf '%s\n' \
    'Create one 30-day token named MCP scope read acceptance.' \
    'Keep only Read examples and private projects checked.' \
    'Paste it only at the hidden prompt. Nothing will be displayed.'
  IFS= read -r -s -p 'Read-only MCP token: ' ABDA_MCP_READ_TOKEN
  printf '\n'
  printf '%s\n' \
    'Keep this shell open. In the browser, create a separate 30-day token named' \
    'MCP scoped write acceptance with all three permissions checked.' \
    'Paste that new token only at the next hidden prompt.'
  IFS= read -r -s -p 'Full-scope MCP token: ' ABDA_MCP_WRITE_TOKEN
  printf '\n'
  export ABDA_MCP_READ_TOKEN
  export ABDA_MCP_WRITE_TOKEN
  abda_mcp_scoped_validate_tokens

  ABDA_MCP_SCOPED_SECTION='authentication and independent scope enforcement'
  printf '\n[2/7] Proving authentication and independent read/write scopes...\n'
  abda_mcp_scoped_runner preflight "$ABDA_MCP_SCOPED_ROOT/state.json"

  ABDA_MCP_SCOPED_SECTION='bounded project write and model proposal'
  printf '\n[3/7] Running the bounded write, version, and non-applying proposal checks...\n'
  printf 'This step can take up to three minutes because it makes one funded proposal.\n'
  abda_mcp_scoped_runner mutation "$ABDA_MCP_SCOPED_ROOT/state.json"

  ABDA_MCP_SCOPED_SECTION='browser project cleanup'
  printf '\n[4/7] Waiting for exact browser cleanup of the disposable project...\n'
  printf '%s\n' \
    'At demo.abda-nl.org, open Research workspace, then Projects.' \
    'Refresh the list and delete the newest project named:' \
    '  MCP scoped acceptance, delete me' \
    'Do not delete another project.'
  IFS= read -r -p 'Type PROJECT_DELETED after deletion: ' ABDA_CONFIRMATION
  [[ "$ABDA_CONFIRMATION" == 'PROJECT_DELETED' ]] || \
    abda_mcp_scoped_fail 'project deletion was not confirmed'

  ABDA_MCP_SCOPED_SECTION='project deletion verification'
  printf '\n[5/7] Proving the disposable project is no longer accessible...\n'
  abda_mcp_scoped_runner deleted "$ABDA_MCP_SCOPED_ROOT/state.json"

  ABDA_MCP_SCOPED_SECTION='browser token revocation'
  printf '\n[6/7] Waiting for revocation of both disposable tokens...\n'
  printf '%s\n' \
    'In Research workspace, Codex and Claude, revoke both acceptance tokens:' \
    '  MCP scope read acceptance' \
    '  MCP scoped write acceptance'
  IFS= read -r -p 'Type TOKENS_REVOKED after both are revoked: ' ABDA_CONFIRMATION
  [[ "$ABDA_CONFIRMATION" == 'TOKENS_REVOKED' ]] || \
    abda_mcp_scoped_fail 'both token revocations were not confirmed'
  abda_mcp_scoped_runner revoked "$ABDA_MCP_SCOPED_ROOT/state.json"
  unset ABDA_MCP_READ_TOKEN
  unset ABDA_MCP_WRITE_TOKEN

  ABDA_MCP_SCOPED_SECTION='content-free receipt'
  printf '\n[7/7] MCP scoped-write acceptance is complete.\n'
  printf '\nABDA-NL MCP scoped-write acceptance status:\n'
  printf 'script_revision: %s\n' "$ABDA_MCP_SCOPED_SCRIPT_REVISION"
  printf 'public_origin: %s\n' "$ABDA_PUBLIC_ORIGIN"
  printf 'anonymous_authentication: rejected\n'
  printf 'read_only_write_scope: rejected_without_mutation\n'
  printf 'scoped_project_write: passed\n'
  printf 'stale_version_rejected: passed\n'
  printf 'proposal_did_not_apply: passed\n'
  printf 'funded_cloudbank_route: passed\n'
  printf 'funded_proposal_cost_recorded: passed\n'
  printf 'disposable_project_removed: passed\n'
  printf 'all_acceptance_tokens_revoked: passed\n'
  printf 'azure_configuration_changed: false\n'
  printf 'result: LIVE_MCP_SCOPED_WRITE_ACCEPTANCE_VERIFIED\n'
  printf 'Send this status and the shell exit code to Codex.\n'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  set -Eeuo pipefail
  set +x
  umask 077
  trap abda_mcp_scoped_cleanup EXIT
  trap abda_mcp_scoped_error ERR
  trap abda_mcp_scoped_interrupt INT
  ABDA_MCP_SCOPED_ROOT="$(mktemp -d /tmp/abda-nl-mcp-scoped.XXXXXX)"
  chmod 700 "$ABDA_MCP_SCOPED_ROOT"
  abda_mcp_scoped_main
fi
