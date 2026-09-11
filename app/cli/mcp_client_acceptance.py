"""Run a bounded subscribed-client MCP editing workflow and verify its evidence."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit
from uuid import uuid4

import httpx


TOOLS = ("list_examples", "get_example", "create_project", "get_project", "apply_project_ops")
EDIT = {"op": "toggle-assumption", "id": "permit_window_open"}


class AcceptanceError(RuntimeError):
    pass


def _endpoint(value: str) -> str:
    parsed = urlsplit(value)
    local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise AcceptanceError("provide an MCP endpoint without credentials or query parameters")
    if parsed.scheme != "https" and not (local and parsed.scheme == "http"):
        raise AcceptanceError("the MCP endpoint must use HTTPS, or HTTP on loopback")
    return value


class ProtocolClient:
    def __init__(self, endpoint: str, token: str):
        self.endpoint, self.token, self.sequence = endpoint, token, 0

    def request(self, method: str, params: dict) -> tuple[int, dict]:
        self.sequence += 1
        response = httpx.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-11-25",
            },
            json={"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": params},
            timeout=30, follow_redirects=False,
        )
        try:
            return response.status_code, response.json()
        except ValueError as exc:
            raise AcceptanceError("the MCP endpoint returned an invalid response") from exc

    def initialize(self) -> tuple[int, dict]:
        return self.request("initialize", {
            "protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "abda-subscription-acceptance", "version": "1"},
        })

    def tool(self, name: str, arguments: dict, *, error: str | None = None) -> dict:
        status, envelope = self.request("tools/call", {"name": name, "arguments": arguments})
        result = envelope.get("result", {})
        if status != 200 or not isinstance(result, dict):
            raise AcceptanceError(f"the {name} protocol request failed")
        if error:
            messages = " ".join(item.get("text", "") for item in result.get("content", []))
            if not result.get("isError") or error.lower() not in messages.lower():
                raise AcceptanceError(f"the {name} rejection boundary failed")
            return {}
        if result.get("isError") or not isinstance(result.get("structuredContent"), dict):
            raise AcceptanceError(f"the {name} tool did not return a successful structured result")
        return result["structuredContent"]


def _client_environment() -> dict[str, str]:
    # Keep existing client subscription auth, but never inherit provider keys,
    # external model gateways or alternate cloud-provider switches.
    environment = dict(os.environ)
    for key in tuple(environment):
        if key.startswith(("OPENAI_", "ANTHROPIC_", "AZURE_", "OPENROUTER_", "GOOGLE_", "GCP_")):
            environment.pop(key)
        if key.startswith(("CLAUDE_CODE_USE_", "AWS_")):
            environment.pop(key)
        if key.endswith("_API_KEY"):
            environment.pop(key, None)
    return environment


def require_subscription_auth(client: str, environment: dict[str, str]) -> None:
    command = ["codex", "login", "status"] if client == "codex" else ["claude", "auth", "status", "--json"]
    # Both command variants are fixed argv lists; no shell is used.
    result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=20)  # noqa: S603
    if result.returncode:
        raise AcceptanceError("the selected client needs an existing subscription login")
    if client == "codex":
        subscribed = "logged in using chatgpt" in (result.stdout + result.stderr).lower()
    else:
        status = json.loads(result.stdout)
        subscribed = status.get("loggedIn") is True and status.get("authMethod") == "claude.ai"
        subscribed = subscribed and status.get("subscriptionType") in {"pro", "max", "team", "enterprise"}
    if not subscribed:
        raise AcceptanceError("client acceptance requires subscription authentication, not an API key")


def client_command(client: str, endpoint: str, token_env: str, workdir: Path) -> list[str]:
    if client == "codex":
        return [
            "codex", "exec", "--ephemeral", "--sandbox", "read-only",
            "--ignore-user-config", "--ignore-rules", "--strict-config",
            "--skip-git-repo-check", "--color", "never", "--json", "-C", str(workdir),
            "--model", "gpt-5.6-sol",
            "-c", 'shell_environment_policy.inherit="none"',
            "-c", 'mcp_servers.abda_nl.default_tools_approval_mode="approve"',
            "-c", f"mcp_servers.abda_nl.url={json.dumps(endpoint)}",
            "-c", f"mcp_servers.abda_nl.bearer_token_env_var={json.dumps(token_env)}",
            "-c", f"mcp_servers.abda_nl.enabled_tools={json.dumps(list(TOOLS))}",
            "-c", "mcp_servers.abda_nl.tool_timeout_sec=60",
        ]
    names = ",".join(f"mcp__abda_nl__{tool}" for tool in TOOLS)
    config = {"mcpServers": {"abda_nl": {
        "type": "http", "url": endpoint,
        "headers": {"Authorization": "Bearer ${" + token_env + "}"},
    }}}
    return [
        "claude", "-p", "--no-session-persistence", "--strict-mcp-config",
        "--setting-sources", "", "--disable-slash-commands", "--no-chrome",
        "--tools", names, "--allowedTools", names, "--permission-mode", "dontAsk",
        "--model", "sonnet", "--effort", "low", "--max-budget-usd", "1.00",
        "--output-format", "stream-json", "--verbose", "--mcp-config", json.dumps(config),
        "--system-prompt", "Follow the bounded MCP acceptance task. Use only its named tools. Never reveal credentials.",
    ]


def transcript_calls(client: str, transcript: str) -> list[dict]:
    events = [json.loads(line) for line in transcript.splitlines() if line.strip()]
    calls = []
    if client == "codex":
        if not any(item.get("type") == "turn.completed" for item in events):
            raise AcceptanceError("Codex did not complete its turn")
        for event in events:
            if event.get("type") != "item.completed":
                continue
            item = event.get("item", {})
            if item.get("type") in {"command_execution", "file_change", "web_search", "image_generation"}:
                raise AcceptanceError("the client used a non-MCP tool")
            if item.get("type") != "mcp_tool_call":
                continue
            if item.get("server") != "abda_nl" or item.get("status") != "completed" or item.get("error"):
                raise AcceptanceError("a client MCP call failed or used another server")
            if not item.get("result") or _contains_tool_error(item["result"]):
                raise AcceptanceError("a client MCP call returned no successful result")
            arguments = item.get("arguments", {})
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            calls.append({"name": item.get("tool"), "arguments": arguments})
    else:
        finals = [item for item in events if item.get("type") == "result"]
        if len(finals) != 1 or finals[0].get("is_error"):
            raise AcceptanceError("Claude Code did not complete its turn")
        failed_tools = set()
        returned_tools = set()
        for event in events:
            for item in event.get("message", {}).get("content", []) if isinstance(event.get("message"), dict) else []:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "tool_result":
                    returned_tools.add(item.get("tool_use_id"))
                    if item.get("is_error") or _contains_tool_error(item.get("content")):
                        failed_tools.add(item.get("tool_use_id"))
                if item.get("type") == "tool_use":
                    name = item.get("name", "")
                    if not name.startswith("mcp__abda_nl__"):
                        raise AcceptanceError("the client used a non-MCP tool")
                    calls.append({"name": name.removeprefix("mcp__abda_nl__"),
                                  "arguments": item.get("input", {}), "id": item.get("id")})
        if any(call.get("id") in failed_tools or call.get("id") not in returned_tools for call in calls):
            raise AcceptanceError("a client MCP tool returned an error")
    if any(call["name"] not in TOOLS for call in calls):
        raise AcceptanceError("the client called a tool outside this acceptance task")
    return calls


def _contains_tool_error(value, depth: int = 0) -> bool:
    if depth > 10:
        return False
    if isinstance(value, str):
        try:
            return _contains_tool_error(json.loads(value), depth + 1)
        except ValueError:
            return False
    if isinstance(value, dict):
        return value.get("isError") is True or any(
            _contains_tool_error(child, depth + 1) for child in value.values()
        )
    if isinstance(value, list):
        return any(_contains_tool_error(child, depth + 1) for child in value)
    return False


def client_failure_message(client: str, transcript: str) -> str:
    """Report known client-auth failures without echoing arbitrary model output."""
    if client == "claude-code":
        for line in transcript.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict) or event.get("type") != "result" or not event.get("is_error"):
                continue
            message = event.get("result")
            if isinstance(message, str) and "another Claude Code process is refreshing" in message:
                return (
                    "Claude Code could not refresh its subscription login; retry after its "
                    "concurrent credential refresh finishes, then check the private cleanup receipt"
                )
    return "the subscribed client exited unsuccessfully; check its subscription login and the private cleanup receipt"


def verify_client_workflow(calls: list[dict], project: dict, name: str) -> None:
    creations = [call for call in calls if call["name"] == "create_project"]
    edits = [call for call in calls if call["name"] == "apply_project_ops"]
    if len(creations) != 1 or len(edits) != 1:
        raise AcceptanceError("the client must create one project and apply one edit")
    creation, edit = creations[0]["arguments"], edits[0]["arguments"]
    if creation.get("name") != name or creation.get("source_scenario_id") != "fire_prevention" or creation.get("diff_ops"):
        raise AcceptanceError("the client created a project outside the accepted task")
    if edit != {"project_id": project["id"], "expected_version": 1, "diff_ops": [EDIT]}:
        raise AcceptanceError("the client did not apply the single authorized edit")
    reads = [index for index, call in enumerate(calls) if call["name"] == "get_project"]
    edit_index = calls.index(edits[0])
    if not any(index < edit_index for index in reads) or not any(index > edit_index for index in reads):
        raise AcceptanceError("the client did not read before editing and verify afterward")
    if any(calls[index]["arguments"].get("project_id") != project["id"] for index in reads):
        raise AcceptanceError("the client accessed another private project")
    if not {"list_examples", "get_example"}.issubset({call["name"] for call in calls}):
        raise AcceptanceError("the client did not discover and inspect the public example")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=["codex", "claude-code"], required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--token-env", default="ABDA_NL_MCP_TOKEN")
    parser.add_argument("--receipt", type=Path, required=True, help="private JSON receipt, including cleanup project id")
    parser.add_argument("--verify-revoked", action="store_true")
    args = parser.parse_args(argv)
    try:
        endpoint = _endpoint(args.endpoint)
        token = os.environ.get(args.token_env, "")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.token_env) or not re.fullmatch(r"abda_mcp_[A-Za-z0-9_-]{31,119}", token):
            raise AcceptanceError("provide a personal MCP token through the named environment variable")
        protocol = ProtocolClient(endpoint, token)
        if args.verify_revoked:
            if any(protocol.initialize()[0] != 401 for _ in range(2)):
                raise AcceptanceError("the revoked credential still authenticates")
            print("MCP_REPEATED_REVOCATION_VERIFIED")
            return 0
        status, initialized = protocol.initialize()
        if status != 200:
            raise AcceptanceError("the personal MCP credential did not authenticate")
        environment = _client_environment()
        require_subscription_auth(args.client, environment)
        # This must fail at the scope check, before project lookup or model use.
        protocol.tool("ask_project", {"project_id": "scope-probe", "question": "scope probe"}, error="llm:use")
        baseline = protocol.tool("get_example", {"scenario_id": "fire_prevention"})
        name = f"MCP subscription acceptance {args.client} {uuid4().hex[:8]}"
        executable = "codex" if args.client == "codex" else "claude"
        # The argparse client choice selects one of two fixed executable names.
        version = subprocess.run([executable, "--version"], capture_output=True, text=True, check=True, timeout=20).stdout.strip()  # noqa: S603
        receipt = {"client": args.client, "client_version": version,
                   "server_info": initialized.get("result", {}).get("serverInfo"),
                   "project_name": name, "status": "client_pending",
                   "cleanup_required": True, "abda_llm_scope": False}
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(args.receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(receipt, stream, indent=2)
        prompt = (
            "Use only the ABDA-NL MCP tools for this authorized disposable acceptance task. "
            "Perform these six tool calls in order, waiting for each result before the next call: "
            "1. list_examples. 2. get_example with scenario_id fire_prevention. "
            f"3. create_project named {name!r} from fire_prevention with no initial diff operations. "
            "4. get_project for the new project's id, to obtain its current version and burn_permitted outcome. "
            "5. apply_project_ops for that id and the version from step 4, with exactly one operation: "
            "{\"op\":\"toggle-assumption\",\"id\":\"permit_window_open\"}. I authorize that one edit "
            "in the new project, from active to inactive. "
            "6. get_project for the same id again, to verify the saved assumption is inactive and "
            "compare burn_permitted with step 4. Both explicit get_project calls are required, even "
            "when create_project or apply_project_ops already returns a project snapshot. "
            "Do not access another "
            "private project, create another project, invoke server LLM tools, or use any shell "
            "or file tools. Return only whether the workflow succeeded."
        )
        environment[args.token_env] = token
        with tempfile.TemporaryDirectory(prefix="abda-mcp-client-") as directory:
            # Validated configuration and prompt remain argv items, never shell text.
            completed = subprocess.run(  # noqa: S603
                [*client_command(args.client, endpoint, args.token_env, Path(directory)), prompt],
                capture_output=True, text=True, cwd=directory, env=environment,
                check=False, timeout=240,
            )
        if completed.returncode:
            receipt.update(status="client_failed")
            args.receipt.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
            raise AcceptanceError(client_failure_message(args.client, completed.stdout))
        calls = transcript_calls(args.client, completed.stdout)
        projects = protocol.tool("list_projects", {})["projects"]
        matches = [item for item in projects if item.get("name") == name]
        if len(matches) != 1:
            raise AcceptanceError("the disposable project could not be uniquely located")
        project = protocol.tool("get_project", {"project_id": matches[0]["id"], "include_argument_graph": True})
        receipt.update(project_id=project["id"], project_version=project["version"],
                       status="verification_pending")
        # Retain only the bounded cleanup receipt; raw client transcripts and
        # token values are never written to reports or printed on failure.
        args.receipt.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        verify_client_workflow(calls, project, name)
        if project["version"] != 2 or project["scenario"]["assumptions"]["permit_window_open"]["active"]:
            raise AcceptanceError("the project did not preserve the authorized edit")
        if project["af_summary"]["labels_by_proposition"]["burn_permitted"] == baseline["af_summary"]["labels_by_proposition"]["burn_permitted"]:
            raise AcceptanceError("the expected formal outcome did not change")
        protocol.tool("apply_project_ops", {"project_id": project["id"], "expected_version": 1, "diff_ops": [EDIT]}, error="changed since it was loaded")
        protocol.tool("apply_project_ops", {"project_id": project["id"], "expected_version": 2,
                      "diff_ops": [{"op": "toggle-assumption", "id": "missing_acceptance_assumption"}]}, error="missing_acceptance_assumption")
        readback = protocol.tool("get_project", {"project_id": project["id"], "include_argument_graph": True})
        if readback != project:
            raise AcceptanceError("a rejected edit changed the project")
        receipt.update(status="passed", tool_calls=len(calls), stale_version_rejected=True,
                       invalid_operation_rejected=True, cleanup_required=True)
        args.receipt.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(f"MCP_SUBSCRIPTION_WORKFLOW_VERIFIED client={args.client} server_llm_calls=0")
        return 0
    except AcceptanceError as exc:
        print(f"MCP acceptance stopped: {exc}")
    except Exception:
        print("MCP acceptance failed; inspect the private cleanup receipt if one was created.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
