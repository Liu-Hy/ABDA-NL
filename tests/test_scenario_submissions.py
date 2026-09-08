"""Public curation must not expose private projects or grant broader account access."""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.main import app
from app.core.config import get_settings, reset_settings_cache
from app.db.models import ScenarioSubmission, User
from app.db.session import get_session_factory, reset_database_caches
from app.services.privacy_requests import (
    export_privacy_account,
    prepare_privacy_deletion,
    delete_privacy_account,
)
from app.services.scenario_submissions import is_scenario_admin

ADMIN = "curator@example.org"
AUTHOR = "author@example.org"
PICNIC = {
    "title": "Outdoor picnic",
    "description": "A public teaching example.",
    "sources": [{"filename": "public-note.txt", "text": "A source the author has approved for public sharing."}],
    "facts": {"sunny": {"description": "It is sunny"}},
    "conclusions": {"outside": {"description": "Hold the picnic outside"}},
    "rules": {"r1": {"type": "defeasible", "premises": ["sunny"], "conclusion": "outside"}},
}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ABDA_DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'curation.db'}")
    monkeypatch.setenv("ABDA_SCENARIO_ADMIN_EMAILS", ADMIN)
    monkeypatch.setenv("ABDA_COMMUNITY_CATALOG_ENABLED", "true")
    reset_database_caches()
    reset_settings_cache()
    with TestClient(app) as result:
        yield result
    reset_database_caches()
    reset_settings_cache()


def login(client, email=AUTHOR):
    response = client.post("/api/auth/dev/login", json={"email": email})
    assert response.status_code == 200, response.text
    return response.json()


def project(client):
    response = client.post(
        "/api/projects/import",
        json={
            "name": "Picnic for everyone",
            "description": "Private note must never publish",
            "scenario": PICNIC,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def submit(client, saved, **options):
    return client.post(
        "/api/scenario-submissions",
        json={
            "project_id": saved["id"],
            "expected_version": saved["version"],
            "public_consent": True,
            **options,
        },
    )


def decide(client, item, action, **options):
    return client.post(
        f"/api/scenario-submissions/{item['id']}/review",
        json={
            "expected_version": item["version"],
            "action": action,
            **options,
        },
    )


def assert_admin(client):
    assert login(client, ADMIN)["scenario_admin"]
    assert client.get("/api/auth/session").json()["scenario_admin"]


def test_owner_approval_snapshot_public_copy_and_unpublish(client):
    assert not login(client)["scenario_admin"]
    saved = project(client)
    result = submit(client, saved)
    assert result.status_code == 201, result.text
    item = result.json()
    assert item["status"] == "pending"
    assert submit(client, saved).json()["id"] == item["id"]
    assert not any(
        x["category"] == "community" for x in client.get("/scenarios").json()["scenarios"]
    )
    assert len(client.get("/api/scenario-submissions").json()["submissions"]) == 1
    assert client.get("/api/scenario-submissions?queue=true").status_code == 403
    assert decide(client, item, "approve").status_code == 403
    login(client, "other@example.org")
    assert client.get(f"/api/scenario-submissions/{item['id']}").status_code == 404
    assert submit(client, saved).status_code == 404
    assert_admin(client)
    assert client.get(f"/api/projects/{saved['id']}").status_code == 404
    snapshot = client.get(f"/api/scenario-submissions/{item['id']}").json()
    assert snapshot["scenario"]["title"] == saved["name"]
    assert "Private note" not in str(snapshot)
    published = decide(client, item, "approve")
    assert published.status_code == 200, published.text
    public_id = published.json()["public_scenario_id"]
    client.post("/api/auth/logout")
    body = client.get(f"/scenarios/{public_id}").json()
    assert body["af"]["labels_by_proposition"]["outside"] == "accepted"
    changed = client.post(
        "/state", json={"scenario_id": public_id, "diff_ops": [{"op": "toggle-rule", "id": "r1"}]}
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["af"]["labels_by_proposition"]["outside"] != "accepted"
    assert AUTHOR not in str(body) and saved["id"] not in str(body)
    login(client)
    renamed = client.put(
        f"/api/projects/{saved['id']}", json={"expected_version": 1, "name": "Private revision"}
    )
    assert renamed.status_code == 200, renamed.text
    assert client.get(f"/scenarios/{public_id}").json() == body
    copy = client.post(
        "/api/projects", json={"name": "My public copy", "source_scenario_id": public_id}
    )
    assert copy.status_code == 201, copy.text
    assert copy.json()["source_scenario_id"] is None
    assert_admin(client)
    removed = decide(client, published.json(), "unpublish", note="Needs clarification")
    assert removed.status_code == 200, removed.text
    assert client.get(f"/scenarios/{public_id}").status_code == 404
    assert client.post("/state", json={"scenario_id": public_id}).status_code == 404


def test_direct_publish_requires_admin_consent_and_version(client):
    assert client.get("/api/scenario-submissions").status_code == 401
    login(client)
    saved = project(client)
    assert submit(client, saved, publish=True).status_code == 403
    assert submit(client, saved, public_consent=False).status_code == 422
    assert submit(client, saved, expected_version=3).status_code == 409
    assert (
        client.post(
            "/api/scenario-submissions",
            json={
                "project_id": saved["id"],
                "expected_version": 1,
                "public_consent": True,
            },
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    assert_admin(client)
    result = submit(client, project(client), publish=True)
    assert result.status_code == 201, result.text
    assert result.json()["status"] == "published"
    assert len(client.get("/scenarios").json()["scenarios"]) == 7


def test_withdraw_reject_and_stale_review(client):
    login(client)
    saved = project(client)
    item = submit(client, saved).json()
    assert decide(client, item, "withdraw").json()["status"] == "withdrawn"
    assert submit(client, saved).json()["status"] == "withdrawn"
    revised = client.put(
        f"/api/projects/{saved['id']}", json={"expected_version": 1, "name": "New snapshot"}
    ).json()
    item = submit(client, revised).json()
    assert_admin(client)
    assert decide(client, item, "reject").status_code == 400
    assert decide(client, item, "approve", expected_version=7).status_code == 409
    declined = decide(client, item, "reject", note="Please clarify the assumptions")
    assert declined.status_code == 200, declined.text
    assert decide(client, item, "approve").status_code in {403, 409}
    login(client)
    rows = client.get("/api/scenario-submissions").json()["submissions"]
    assert rows[0]["review_note"] == "Please clarify the assumptions"


def test_admin_allowlist_exact_verified_active_and_not_client_writable(client):
    settings = get_settings()
    user = User(email=ADMIN, email_verified=True, status="active")
    assert is_scenario_admin(user, settings)
    user.email_verified = False
    assert not is_scenario_admin(user, settings)
    user.email_verified = True
    user.status = "deletion_pending"
    assert not is_scenario_admin(user, settings)
    user.status = "active"
    user.email = "curator+other@example.org"
    assert not is_scenario_admin(user, settings)
    assert not is_scenario_admin(user, replace(settings, scenario_admin_emails=()))
    assert (
        client.post(
            "/api/auth/dev/login", json={"email": AUTHOR, "scenario_admin": True}
        ).status_code
        == 422
    )
    assert ADMIN not in client.get("/config").text


def test_privacy_export_suspend_delete_include_snapshots(client):
    assert_admin(client)
    public_id = submit(client, project(client), publish=True).json()["public_scenario_id"]
    with get_session_factory()() as session:
        exported = export_privacy_account(session, ADMIN)
        assert len(exported["scenario_submissions"]) == 1
        assert 'A source the author has approved' in str(exported['scenario_submissions'])
        prepare_privacy_deletion(session, ADMIN, request_reference="curation-test")
    assert client.get(f"/scenarios/{public_id}").status_code == 404
    with get_session_factory()() as session:
        receipt = delete_privacy_account(session, ADMIN, request_reference="curation-test")
        assert receipt.deleted_scenario_submission_count == 1
        assert session.scalar(select(ScenarioSubmission)) is None


def test_pending_limit_does_not_prevent_withdrawal(client):
    login(client)
    items = [submit(client, project(client)).json() for _ in range(5)]
    extra = project(client)
    assert submit(client, extra).status_code == 429
    assert decide(client, items[0], "withdraw").status_code == 200
    assert submit(client, extra).status_code == 201


@pytest.mark.parametrize("consent", [False, None, 1, "true"])
def test_consent_cannot_be_coerced(client, consent):
    login(client)
    assert submit(client, project(client), public_consent=consent).status_code == 422


def test_public_bundled_copy_preserves_corpus_and_mcp_access(client):
    assert_admin(client)
    saved = client.post(
        "/api/projects",
        json={
            "name": "Community fire example",
            "source_scenario_id": "fire_prevention",
        },
    ).json()
    item = submit(client, saved, publish=True).json()
    public_id = item["public_scenario_id"]
    copied = client.post(
        "/api/projects",
        json={
            "name": "A private copy",
            "source_scenario_id": public_id,
        },
    )
    assert copied.status_code == 201, copied.text
    assert copied.json()["source_scenario_id"] == "fire_prevention"
    assert copied.json()["scenario"]["corpus"] == saved["scenario"]["corpus"]
    token = client.post(
        "/api/mcp/tokens",
        json={"name": "Curation test", "scopes": ["projects:read", "projects:write"]},
    ).json()["token"]

    def call(name, arguments=None):
        response = client.post(
            "/mcp/",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-11-25",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()["result"]
        assert not result.get("isError"), result
        return result["structuredContent"]

    assert any(row["id"] == public_id for row in call("list_examples")["examples"])
    assert call("get_example", {"scenario_id": public_id})["id"] == public_id
    assert (
        call("create_project", {"name": "Agent copy", "source_scenario_id": public_id})[
            "source_scenario_id"
        ]
        == "fire_prevention"
    )
    assert decide(client, item, "unpublish", note="Test cleanup").status_code == 200
    assert not any(row["id"] == public_id for row in call("list_examples")["examples"])


def test_published_example_ai_uses_its_real_corpus_boundary(client, monkeypatch):
    from app.api import main
    from app.api.models import ChatResponse

    assert_admin(client)
    public_id = submit(client, project(client), publish=True).json()["public_scenario_id"]
    monkeypatch.setattr(main, "ENABLE_LLM", True)
    calls = []

    def fake_chat(*args, **kwargs):
        assert kwargs["scenario_dir"] is None
        assert kwargs["scenario"].title == "Picnic for everyone"
        calls.append(kwargs["context_kind"])
        return ChatResponse(
            message="The sunny forecast supports an outdoor picnic.",
            stop_reason="end_turn",
            model="test",
            provider="test",
            billing_source="test",
            route="test",
            cost_microusd=0,
            request_id="curation-chat-test",
            usage={},
            latency_ms=0,
        )

    monkeypatch.setattr(main, "_run_chat_request", fake_chat)
    result = client.post(
        "/chat",
        json={
            "scenario_id": public_id,
            "messages": [{"role": "user", "content": "Why outside?"}],
        },
    )
    assert result.status_code == 200, result.text
    assert calls == ["example"]


def test_disabled_catalog(client, monkeypatch):
    monkeypatch.setenv("ABDA_COMMUNITY_CATALOG_ENABLED", "false")
    reset_settings_cache()
    login(client)
    assert client.get("/api/auth/session").json()["community_catalog_enabled"] is False
    assert client.get("/api/scenario-submissions").status_code == 503
    assert len(client.get("/scenarios").json()["scenarios"]) == 6
