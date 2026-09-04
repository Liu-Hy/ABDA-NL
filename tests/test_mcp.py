"""Credential invariants and authenticated MCP protocol integration tests."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.api.account_routes as account_routes
import app.mcp.server as mcp_module
from app.api.main import app
from app.core.config import get_settings
from app.db.models import Base, MCPAccessToken, User
from app.db.session import get_session_factory
from app.services.mcp_tokens import (
    MCPTokenLimitError,
    authenticate_mcp_token,
    create_mcp_token,
    revoke_mcp_token,
)


PEPPER = "test-only-mcp-token-pepper-32-characters"


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _login(client: TestClient, email: str) -> dict:
    response = client.post("/api/auth/dev/login", json={"email": email})
    assert response.status_code == 200
    return response.json()["user"]


def _create_token(
    client: TestClient,
    *,
    name: str,
    scopes: list[str] | None = None,
) -> dict:
    payload = {"name": name}
    if scopes is not None:
        payload["scopes"] = scopes
    response = client.post(
        "/api/mcp/tokens",
        headers={"Origin": "http://testserver"},
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _mcp_headers(token: str, *, protocol: bool = True) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if protocol:
        headers["MCP-Protocol-Version"] = "2025-11-25"
    return headers


def _initialize(client: TestClient, token: str):
    return client.post(
        "/mcp/",
        headers=_mcp_headers(token, protocol=False),
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "abda-test", "version": "1.0"},
            },
        },
    )


def _mcp_request(
    client: TestClient,
    token: str,
    method: str,
    params: dict | None = None,
    *,
    request_id: int = 2,
):
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    return client.post(
        "/mcp/",
        headers=_mcp_headers(token),
        json=payload,
    )


def _call_tool(
    client: TestClient,
    token: str,
    name: str,
    arguments: dict | None = None,
    *,
    request_id: int = 3,
) -> dict:
    response = _mcp_request(
        client,
        token,
        "tools/call",
        {"name": name, "arguments": arguments or {}},
        request_id=request_id,
    )
    assert response.status_code == 200, response.text
    assert response.json()["jsonrpc"] == "2.0"
    return response.json()["result"]


@pytest.fixture
def token_factory(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'tokens.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        user = User(email="token-service@example.edu", email_verified=True)
        session.add(user)
        session.commit()
        user_id = user.id
    yield factory, user_id
    engine.dispose()


def test_token_service_hashes_expires_revokes_and_limits_active_tokens(token_factory):
    factory, user_id = token_factory
    start = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
    with factory() as session:
        user = session.get(User, user_id)
        record, raw_token = create_mcp_token(
            session,
            user,
            name="Research laptop",
            scopes=["projects:read"],
            expires_in_days=90,
            pepper=PEPPER,
            now=start,
        )
        assert raw_token.startswith("abda_mcp_")
        assert record.token_hash != raw_token
        assert raw_token not in repr(record.__dict__)
        assert len(record.token_hash) == 64

        principal = authenticate_mcp_token(
            session, raw_token, pepper=PEPPER, now=start + timedelta(minutes=1)
        )
        assert principal is not None
        assert principal.user_id == user_id
        assert principal.scopes == ("projects:read",)
        first_use = record.last_used_at
        authenticate_mcp_token(
            session, raw_token, pepper=PEPPER, now=start + timedelta(minutes=30)
        )
        assert record.last_used_at == first_use
        authenticate_mcp_token(
            session, raw_token, pepper=PEPPER, now=start + timedelta(hours=2)
        )
        assert record.last_used_at != first_use

        assert (
            authenticate_mcp_token(
                session,
                raw_token,
                pepper=PEPPER,
                now=start + timedelta(days=91),
            )
            is None
        )
        revoke_mcp_token(session, user, record.id, now=start + timedelta(days=1))
        assert (
            authenticate_mcp_token(
                session,
                raw_token,
                pepper=PEPPER,
                now=start + timedelta(days=2),
            )
            is None
        )

        for index in range(10):
            create_mcp_token(
                session,
                user,
                name=f"Active {index}",
                pepper=PEPPER,
                now=start,
            )
        with pytest.raises(MCPTokenLimitError):
            create_mcp_token(
                session,
                user,
                name="One too many",
                pepper=PEPPER,
                now=start,
            )


def test_token_management_requires_login_checks_origin_and_discloses_once(client: TestClient):
    client.post("/api/auth/logout")
    assert client.get("/api/mcp/tokens").status_code == 401
    _login(client, "mcp-management@example.edu")

    rejected = client.post(
        "/api/mcp/tokens",
        headers={"Origin": "https://attacker.example"},
        json={"name": "Rejected"},
    )
    assert rejected.status_code == 403
    assert rejected.json()["detail"]["code"] == "cross_origin_request"

    created_response = client.post(
        "/api/mcp/tokens",
        headers={"Origin": "http://testserver"},
        json={"name": "Codex", "scopes": ["projects:read"]},
    )
    assert created_response.status_code == 201
    assert created_response.headers["cache-control"] == "no-store"
    created = created_response.json()
    raw_token = created["token"]
    assert created["mcp_url"] == "http://testserver/mcp/"
    assert raw_token not in created["codex_config"]
    assert raw_token not in created["claude_command"]
    assert "bearer_token_env_var" in created["codex_config"]
    assert 'default_tools_approval_mode = "writes"' in created["codex_config"]
    assert "tool_timeout_sec = 180" in created["codex_config"]
    assert created["claude_command"] == (
        "claude mcp add --transport http --scope user --header "
        "'Authorization: Bearer ${ABDA_NL_MCP_TOKEN}' -- "
        'abda-nl "http://testserver/mcp/"'
    )

    listing_text = client.get("/api/mcp/tokens").text
    assert raw_token not in listing_text
    assert created["token_prefix"] in listing_text
    with get_session_factory()() as session:
        record = session.scalar(
            select(MCPAccessToken).where(MCPAccessToken.id == created["id"])
        )
        assert record is not None
        assert record.token_hash != raw_token
        assert raw_token not in repr(record.__dict__)


def test_token_revocation_is_never_rate_limited(
    client: TestClient,
    monkeypatch,
) -> None:
    _login(client, "mcp-independent-revocation@example.edu")
    created = _create_token(client, name="Revocation boundary")

    def reject_rate_limit_call(*_args, **_kwargs) -> None:
        raise AssertionError("credential revocation must not invoke a rate limiter")

    monkeypatch.setattr(account_routes, "enforce_rate_limit", reject_rate_limit_call)
    revoked = client.delete(
        f"/api/mcp/tokens/{created['id']}",
        headers={"Origin": "http://testserver"},
    )

    assert revoked.status_code == 204


def test_mcp_wire_authentication_discovery_and_read_tools(client: TestClient):
    _login(client, "mcp-reader@example.edu")
    project = client.post(
        "/api/projects",
        json={
            "name": "Reader project",
            "source_scenario_id": "fire_prevention",
            "diff_ops": [],
        },
    ).json()
    token = _create_token(
        client,
        name="Read tools",
        scopes=["projects:read"],
    )["token"]

    unauthorized = client.post(
        "/mcp/",
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert unauthorized.status_code == 401
    assert unauthorized.headers["www-authenticate"].startswith("Bearer ")

    initialized = _initialize(client, token)
    assert initialized.status_code == 200
    assert "expected_version" in initialized.json()["result"]["instructions"]

    listing = _mcp_request(client, token, "tools/list", {})
    assert listing.status_code == 200
    tools = {item["name"]: item for item in listing.json()["result"]["tools"]}
    assert set(tools) == {
        "list_examples",
        "get_example",
        "list_projects",
        "get_project",
        "create_project",
        "apply_project_ops",
        "update_project_metadata",
        "ask_project",
        "propose_project_edit",
    }
    assert tools["get_project"]["annotations"]["readOnlyHint"] is True
    assert tools["apply_project_ops"]["annotations"]["destructiveHint"] is True
    assert tools["ask_project"]["inputSchema"]["properties"]["profile"][
        "const"
    ] == "balanced"
    assert tools["propose_project_edit"]["inputSchema"]["properties"]["profile"][
        "const"
    ] == "balanced"
    assert "api_key" not in listing.text.lower()

    projects = _call_tool(client, token, "list_projects")["structuredContent"]
    assert any(item["id"] == project["id"] for item in projects["projects"])
    loaded = _call_tool(
        client,
        token,
        "get_project",
        {"project_id": project["id"]},
    )["structuredContent"]
    assert loaded["version"] == 1
    assert loaded["af_summary"]["labels_by_proposition"]
    assert "af" not in loaded


def test_mcp_read_tools_share_one_authenticated_rate_limit(
    client: TestClient,
    monkeypatch,
) -> None:
    _login(client, "mcp-rate-limited-reader@example.edu")
    project = client.post(
        "/api/projects",
        json={
            "name": "Rate-limited reader project",
            "source_scenario_id": "fire_prevention",
            "diff_ops": [],
        },
    ).json()
    token = _create_token(
        client,
        name="Rate-limited reads",
        scopes=["projects:read"],
    )["token"]

    settings = replace(
        get_settings(),
        abuse_protection_enabled=True,
        anonymous_requests_per_minute=4,
    )
    monkeypatch.setattr(mcp_module, "get_settings", lambda: settings)

    assert _call_tool(client, token, "list_examples")["isError"] is False
    assert (
        _call_tool(
            client,
            token,
            "get_example",
            {"scenario_id": "fire_prevention"},
        )["isError"]
        is False
    )
    assert _call_tool(client, token, "list_projects")["isError"] is False
    assert (
        _call_tool(
            client,
            token,
            "get_project",
            {"project_id": project["id"]},
        )["isError"]
        is False
    )

    rejected = _call_tool(client, token, "list_examples")
    assert rejected["isError"] is True
    assert "Too many requests" in rejected["content"][0]["text"]


def test_mcp_scopes_optimistic_writes_and_cross_user_isolation(client: TestClient):
    _login(client, "mcp-writer@example.edu")
    read_token = _create_token(
        client,
        name="Read only",
        scopes=["projects:read"],
    )["token"]
    denied = _call_tool(
        client,
        read_token,
        "create_project",
        {"name": "Denied", "source_scenario_id": "fire_prevention"},
    )
    assert denied["isError"] is True
    assert "projects:write" in denied["content"][0]["text"]

    write_token_record = _create_token(
        client,
        name="Writer",
        scopes=["projects:read", "projects:write"],
    )
    write_token = write_token_record["token"]
    created = _call_tool(
        client,
        write_token,
        "create_project",
        {"name": "MCP project", "source_scenario_id": "fire_prevention"},
    )["structuredContent"]
    assert created["version"] == 1

    updated = _call_tool(
        client,
        write_token,
        "update_project_metadata",
        {
            "project_id": created["id"],
            "expected_version": 1,
            "description": "Updated through MCP",
        },
    )["structuredContent"]
    assert updated["version"] == 2
    stale = _call_tool(
        client,
        write_token,
        "update_project_metadata",
        {
            "project_id": created["id"],
            "expected_version": 1,
            "name": "Stale overwrite",
        },
    )
    assert stale["isError"] is True
    assert "changed since it was loaded" in stale["content"][0]["text"]

    _login(client, "mcp-other-user@example.edu")
    other_token_record = _create_token(client, name="Other user")
    isolated = _call_tool(
        client,
        other_token_record["token"],
        "get_project",
        {"project_id": created["id"]},
    )
    assert isolated["isError"] is True
    assert "project not found" in isolated["content"][0]["text"]

    revoked = client.delete(
        f"/api/mcp/tokens/{other_token_record['id']}",
        headers={"Origin": "http://testserver"},
    )
    assert revoked.status_code == 204
    after_revoke = _initialize(client, other_token_record["token"])
    assert after_revoke.status_code == 401


def test_mcp_proposal_is_metered_and_never_applied_implicitly(
    client: TestClient, monkeypatch
):
    user = _login(client, "mcp-llm@example.edu")
    project = client.post(
        "/api/projects",
        json={
            "name": "LLM project",
            "source_scenario_id": "fire_prevention",
            "diff_ops": [],
        },
    ).json()
    token = _create_token(
        client,
        name="LLM proposal",
        scopes=["projects:read", "projects:write", "llm:use"],
    )["token"]
    captured = {}

    class ClosableClient:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    selected_client = ClosableClient()

    def fake_select(options, *, user, request_id, request_kind, legacy_factory):
        captured["profile"] = options.profile
        captured["user_id"] = user.id
        captured["request_id"] = request_id
        captured["request_kind"] = request_kind
        return selected_client

    def fake_propose(*args, **kwargs):
        return SimpleNamespace(
            op={
                "op": "add-fact",
                "id": "smoke_visible",
                "fact": {"description": "Smoke is visible"},
            },
            reviewed=False,
            review_issues=[],
            proposer_attempts=1,
            model="test-model",
            provider="test-provider",
            billing_source="trial",
            route="test-route",
            cost_microusd=42,
            usage={"input_tokens": 10, "output_tokens": 5},
            latency_ms=12,
        )

    monkeypatch.setattr(mcp_module, "_llm_enabled", lambda: True)
    monkeypatch.setattr(mcp_module, "select_request_llm_client", fake_select)
    monkeypatch.setattr(mcp_module, "run_propose", fake_propose)

    proposed = _call_tool(
        client,
        token,
        "propose_project_edit",
        {
            "project_id": project["id"],
            "task": "add-fact",
            "instruction": "Add visible smoke as a fact.",
        },
    )["structuredContent"]
    assert proposed["op"]["id"] == "smoke_visible"
    assert proposed["expected_version"] == 1
    assert proposed["cost_microusd"] == 42
    assert captured["profile"] == "balanced"
    assert captured["user_id"] == user["id"]
    assert captured["request_kind"] == "mcp-propose"
    assert selected_client.closed is True

    unchanged = client.get(f"/api/projects/{project['id']}").json()
    assert unchanged["version"] == 1
    assert "smoke_visible" not in unchanged["scenario"]["facts"]
