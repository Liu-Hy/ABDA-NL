"""Integration and invariant tests for accounts, projects, sharing, and trial credit."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.account_routes import _safe_logout_hint, _safe_next
from app.api.main import app
from app.core.config import get_settings
from app.db.models import Base, Identity, ShareLink, TrialProgram, User
from app.llm.client import LLMResponse, ToolCallResponse
from app.services.accounts import IdentityError, normalize_email, upsert_verified_identity
from app.services.trials import (
    InsufficientTrialCreditError,
    TrialUnavailableError,
    activate_trial,
    get_trial_balance,
    release_trial_credit,
    reserve_trial_credit,
    settle_trial_credit,
)
from app.scenario.catalog import ScenarioNotFoundError, bundled_scenario_directory


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _login(client: TestClient, email: str) -> dict:
    response = client.post(
        "/api/auth/dev/login",
        json={"email": email, "display_name": "Project Researcher"},
    )
    assert response.status_code == 200
    return response.json()["user"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "/"),
        ("/", "/"),
        ("/workspace", "/workspace"),
        ("/workspace?tab=projects", "/workspace"),
        ("/#share=private-token", "/"),
        ("//attacker.example/path", "/"),
        ("/\\attacker.example/path", "/"),
        ("https://attacker.example/path", "/"),
        ("/safe\r\nLocation: https://attacker.example", "/"),
    ],
)
def test_oidc_return_path_stays_same_origin_and_drops_secrets(
    value: str | None,
    expected: str,
):
    assert _safe_next(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("auth0-session-id", "auth0-session-id"),
        ("unsafe\r\nheader", None),
        ("x" * 513, None),
        (123, None),
    ],
)
def test_oidc_logout_hint_is_bounded_and_header_safe(value, expected):
    assert _safe_logout_hint(value) == expected


def test_browser_logout_clears_local_and_oidc_sessions(monkeypatch):
    from app.api import account_routes

    class FakeOIDCClient:
        async def load_server_metadata(self):
            return {"end_session_endpoint": "https://login.example/oidc/logout"}

    class FakeOIDCRegistry:
        def create_client(self, _name):
            return FakeOIDCClient()

    class FakeRequest:
        def __init__(self):
            self.session = {
                "user_id": "user-id",
                "oidc_sid": "auth0-session-id",
            }
            self.base_url = "https://internal.example/"

    monkeypatch.setattr(
        account_routes,
        "_oauth_registry",
        lambda: FakeOIDCRegistry(),
    )
    settings = replace(
        get_settings(),
        environment="staging",
        auth_mode="oidc",
        public_base_url="https://demo.example",
        oidc_client_id="client-id",
    )
    request = FakeRequest()

    response = asyncio.run(
        account_routes.browser_logout(request=request, settings=settings)
    )

    location = urlsplit(response.headers["location"])
    query = parse_qs(location.query)
    assert response.status_code == 303
    assert request.session == {}
    assert location.scheme == "https"
    assert location.netloc == "login.example"
    assert location.path == "/oidc/logout"
    assert query == {
        "client_id": ["client-id"],
        "logout_hint": ["auth0-session-id"],
        "post_logout_redirect_uri": ["https://demo.example/"],
    }


def test_api_logout_returns_validated_oidc_destination(monkeypatch):
    from app.api import account_routes

    class FakeOIDCClient:
        async def load_server_metadata(self):
            return {"end_session_endpoint": "https://login.example/oidc/logout"}

    class FakeOIDCRegistry:
        def create_client(self, _name):
            return FakeOIDCClient()

    class FakeRequest:
        def __init__(self):
            self.session = {
                "user_id": "user-id",
                "oidc_sid": "auth0-session-id",
            }
            self.base_url = "https://internal.example/"

    monkeypatch.setattr(
        account_routes,
        "_oauth_registry",
        lambda: FakeOIDCRegistry(),
    )
    settings = replace(
        get_settings(),
        environment="staging",
        auth_mode="oidc",
        public_base_url="https://demo.example",
        oidc_client_id="client-id",
    )
    request = FakeRequest()

    response = asyncio.run(account_routes.logout(request=request, settings=settings))

    location = urlsplit(response.logout_url)
    query = parse_qs(location.query)
    assert request.session == {}
    assert location.scheme == "https"
    assert location.netloc == "login.example"
    assert location.path == "/oidc/logout"
    assert query == {
        "client_id": ["client-id"],
        "logout_hint": ["auth0-session-id"],
        "post_logout_redirect_uri": ["https://demo.example/"],
    }


def test_browser_logout_falls_back_to_local_home_when_discovery_fails(
    monkeypatch,
):
    from app.api import account_routes

    class FailingOIDCClient:
        async def load_server_metadata(self):
            raise RuntimeError("provider unavailable")

    class FakeOIDCRegistry:
        def create_client(self, _name):
            return FailingOIDCClient()

    class FakeRequest:
        def __init__(self):
            self.session = {"user_id": "user-id"}
            self.base_url = "https://internal.example/"

    monkeypatch.setattr(
        account_routes,
        "_oauth_registry",
        lambda: FakeOIDCRegistry(),
    )
    settings = replace(
        get_settings(),
        environment="staging",
        auth_mode="oidc",
        public_base_url="https://demo.example",
        oidc_client_id="client-id",
    )
    request = FakeRequest()

    response = asyncio.run(
        account_routes.browser_logout(request=request, settings=settings)
    )

    assert response.status_code == 303
    assert response.headers["location"] == "https://demo.example/"
    assert request.session == {}


class _ProjectLLM:
    def __init__(self) -> None:
        self.complete_systems: list[str] = []
        self.tool_systems: list[str] = []

    def complete(self, *, system, messages, max_tokens, cache=True):
        self.complete_systems.append(str(system))
        return LLMResponse(
            text="The saved project state is reflected in this answer.",
            stop_reason="end_turn",
            usage={"input_tokens": 10, "output_tokens": 8},
            latency_ms=5,
            model="test-model",
        )

    def tool_call(self, *, system, messages, tool, max_tokens, cache=True):
        self.tool_systems.append(str(system))
        return ToolCallResponse(
            tool_name="propose_add_fact",
            tool_input={
                "id": "field_check_complete",
                "fact": {"description": "the field check is complete"},
            },
            stop_reason="tool_use",
            usage={"input_tokens": 12, "output_tokens": 7},
            latency_ms=6,
            model="test-model",
        )


def test_anonymous_browsing_but_projects_require_login(client: TestClient):
    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert logout.json() == {"logout_url": "http://testserver/"}
    assert client.get("/scenarios/popov_v_hayashi").status_code == 200
    session = client.get("/api/auth/session")
    assert session.json()["authenticated"] is False
    denied = client.get("/api/projects")
    assert denied.status_code == 401
    assert denied.json()["detail"]["code"] == "authentication_required"


def test_development_login_sets_server_session(client: TestClient):
    user = _login(client, "Researcher@example.edu")
    assert user["email"] == "researcher@example.edu"
    assert user["email_verified"] is True
    cookie = client.cookies.get("abda_session")
    assert cookie
    session = client.get("/api/auth/session").json()
    assert session["authenticated"] is True
    assert session["user"]["id"] == user["id"]


def test_browser_logout_route_clears_development_session(client: TestClient):
    _login(client, "browser-logout@example.edu")
    response = client.post("/auth/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "http://testserver/"
    assert client.get("/api/auth/session").json()["authenticated"] is False


def test_private_project_lifecycle_and_optimistic_versioning(client: TestClient):
    _login(client, "owner@example.edu")
    created = client.post(
        "/api/projects",
        json={
            "name": "My Popov analysis",
            "description": "Conference exploration",
            "source_scenario_id": "popov_v_hayashi",
            "diff_ops": [],
        },
    )
    assert created.status_code == 201
    assert created.headers["etag"] == '"1"'
    project = created.json()
    project_id = project["id"]
    assert project["version"] == 1
    assert project["af"]["labels_by_proposition"]

    listing = client.get("/api/projects").json()["projects"]
    assert any(item["id"] == project_id for item in listing)

    updated = client.put(
        f"/api/projects/{project_id}",
        json={"expected_version": 1, "name": "Refined Popov analysis"},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.headers["etag"] == '"2"'

    stale = client.put(
        f"/api/projects/{project_id}",
        json={"expected_version": 1, "name": "Stale edit"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "project_version_conflict"

    _login(client, "other@example.edu")
    assert client.get(f"/api/projects/{project_id}").status_code == 404

    _login(client, "owner@example.edu")
    archived = client.delete(f"/api/projects/{project_id}?expected_version=2")
    assert archived.status_code == 204
    assert client.get(f"/api/projects/{project_id}").status_code == 404


def test_empty_project_update_is_rejected_without_advancing_version(
    client: TestClient,
):
    _login(client, "empty-project-update@example.edu")
    created = client.post(
        "/api/projects",
        json={
            "name": "Stable project version",
            "source_scenario_id": "fire_prevention",
            "diff_ops": [],
        },
    )
    assert created.status_code == 201
    project = created.json()

    rejected = client.put(
        f"/api/projects/{project['id']}",
        json={"expected_version": project["version"]},
    )

    assert rejected.status_code == 422
    reopened = client.get(f"/api/projects/{project['id']}")
    assert reopened.status_code == 200
    assert reopened.json()["version"] == 1


def test_project_detail_and_working_state_share_one_compute_limit(
    client: TestClient,
):
    _login(client, "project-read-limit@example.edu")
    created = client.post(
        "/api/projects",
        json={
            "name": "Bounded project reads",
            "source_scenario_id": "fire_prevention",
            "diff_ops": [],
        },
    ).json()
    limited = replace(
        get_settings(),
        abuse_protection_enabled=True,
        anonymous_requests_per_minute=2,
    )
    app.dependency_overrides[get_settings] = lambda: limited
    try:
        detail = client.get(f"/api/projects/{created['id']}")
        working = client.post(
            f"/api/projects/{created['id']}/state",
            json={"expected_version": created["version"], "diff_ops": []},
        )
        rejected = client.get(f"/api/projects/{created['id']}")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert detail.status_code == 200
    assert working.status_code == 200
    assert rejected.status_code == 429
    assert rejected.json()["detail"]["code"] == "rate_limit_exceeded"


def test_reopened_project_uses_saved_state_as_its_working_baseline(client: TestClient):
    _login(client, "project-context@example.edu")
    created = client.post(
        "/api/projects",
        json={
            "name": "Saved treatment history",
            "source_scenario_id": "fire_prevention",
            "diff_ops": [{"op": "toggle-assumption", "id": "recent_burn"}],
        },
    )
    assert created.status_code == 201
    project = created.json()
    assert project["scenario"]["assumptions"]["recent_burn"]["active"] is True

    unchanged = client.post(
        f"/api/projects/{project['id']}/state",
        json={"expected_version": 1, "diff_ops": []},
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["scenario"]["assumptions"]["recent_burn"]["active"] is True

    toggled = client.post(
        f"/api/projects/{project['id']}/state",
        json={
            "expected_version": 1,
            "diff_ops": [{"op": "toggle-assumption", "id": "recent_burn"}],
        },
    )
    assert toggled.status_code == 200
    assert toggled.json()["scenario"]["assumptions"]["recent_burn"]["active"] is False

    stale = client.post(
        f"/api/projects/{project['id']}/state",
        json={"expected_version": 2, "diff_ops": []},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "project_version_conflict"

    _login(client, "project-context-other@example.edu")
    hidden = client.post(
        f"/api/projects/{project['id']}/state",
        json={"expected_version": 1, "diff_ops": []},
    )
    assert hidden.status_code == 404


def test_project_corpus_cannot_escape_its_bundled_source(client: TestClient):
    with pytest.raises(ScenarioNotFoundError):
        bundled_scenario_directory("../private")

    _login(client, "corpus-boundary@example.edu")
    created = client.post(
        "/api/projects",
        json={
            "name": "Corpus boundary",
            "source_scenario_id": "fire_prevention",
            "diff_ops": [],
        },
    ).json()
    changed = dict(created["scenario"])
    changed["corpus"] = ["../../.env"]
    rejected = client.put(
        f"/api/projects/{created['id']}",
        json={"expected_version": 1, "scenario": changed},
    )
    assert rejected.status_code == 400
    assert "immutable source" in rejected.json()["detail"]["message"]


def _too_complex_project_scenario() -> dict:
    return {
        "title": "Too many ground arguments",
        "facts": {
            f"fact_{index}": {"description": f"fact {index}"}
            for index in range(251)
        },
        "conclusions": {},
        "rules": {},
    }


def test_too_complex_project_import_does_not_persist(client: TestClient):
    _login(client, "complex-import@example.edu")

    rejected = client.post(
        "/api/projects/import",
        json={
            "name": "Rejected complex import",
            "scenario": _too_complex_project_scenario(),
        },
    )

    assert rejected.status_code == 422
    assert rejected.json()["errors"][0]["code"] == "scenario_too_complex"
    assert client.get("/api/projects").json()["projects"] == []


def test_too_complex_project_update_preserves_saved_version(client: TestClient):
    _login(client, "complex-update@example.edu")
    created = client.post(
        "/api/projects/import",
        json={
            "name": "Safe custom project",
            "scenario": {
                "title": "Safe custom scenario",
                "facts": {"fact": {"description": "a safe fact"}},
                "conclusions": {},
                "rules": {},
            },
        },
    )
    assert created.status_code == 201
    project = created.json()

    rejected = client.put(
        f"/api/projects/{project['id']}",
        json={
            "expected_version": project["version"],
            "scenario": _too_complex_project_scenario(),
        },
    )

    assert rejected.status_code == 422
    assert rejected.json()["errors"][0]["code"] == "scenario_too_complex"
    reopened = client.get(f"/api/projects/{project['id']}")
    assert reopened.status_code == 200
    assert reopened.json()["version"] == project["version"]
    assert reopened.json()["scenario"] == project["scenario"]


def test_reopened_project_chat_and_propose_use_saved_state(
    client: TestClient, monkeypatch
):
    from app.api import main as main_module

    _login(client, "project-llm-context@example.edu")
    project = client.post(
        "/api/projects",
        json={
            "name": "LLM project context",
            "source_scenario_id": "fire_prevention",
            "diff_ops": [{"op": "toggle-assumption", "id": "recent_burn"}],
        },
    ).json()
    fake = _ProjectLLM()
    monkeypatch.setattr(main_module, "ENABLE_LLM", True)
    monkeypatch.setattr(main_module, "_llm_client", fake)

    chat = client.post(
        f"/api/projects/{project['id']}/chat",
        json={
            "expected_version": 1,
            "diff_ops": [],
            "messages": [{"role": "user", "content": "What is the saved state?"}],
        },
    )
    assert chat.status_code == 200, chat.text
    assert "`recent_burn` (ACTIVE)" in fake.complete_systems[0]

    proposed = client.post(
        f"/api/projects/{project['id']}/propose",
        json={
            "expected_version": 1,
            "diff_ops": [],
            "task": "add-fact",
            "instruction": "Add a fact that the field check is complete.",
        },
    )
    assert proposed.status_code == 200, proposed.text
    assert proposed.json()["op"]["id"] == "field_check_complete"
    assert "`recent_burn` (ACTIVE)" in fake.tool_systems[0]


def test_share_token_is_returned_once_hashed_and_revocable(client: TestClient):
    user = _login(client, "sharing@example.edu")
    created = client.post(
        "/api/projects",
        json={
            "name": "Shared analysis",
            "source_scenario_id": "fire_prevention",
            "diff_ops": [],
        },
    ).json()
    project_id = created["id"]
    shared = client.post(f"/api/projects/{project_id}/shares", json={})
    assert shared.status_code == 201
    share = shared.json()
    assert "/#share=" in share["url"]
    token = share["url"].split("/#share=", 1)[1]

    from app.db.session import get_session_factory

    with get_session_factory()() as database:
        link = database.scalar(select(ShareLink).where(ShareLink.id == share["id"]))
        assert link is not None
        assert link.token_hash != token
        assert len(link.token_hash) == 64
        assert database.get(User, user["id"]) is not None

    client.post("/api/auth/logout")
    resolved = client.post("/api/shares/resolve", json={"token": token})
    assert resolved.status_code == 200
    shared_project = resolved.json()
    assert shared_project["id"] == project_id
    assert shared_project["source_scenario_id"] == "fire_prevention"

    _login(client, "shared-copy@example.edu")
    imported = client.post(
        "/api/projects/import",
        json={
            "name": "Private shared copy",
            "source_scenario_id": shared_project["source_scenario_id"],
            "scenario": shared_project["scenario"],
        },
    )
    assert imported.status_code == 201
    assert imported.json()["scenario"] == shared_project["scenario"]

    _login(client, "sharing@example.edu")
    revoked = client.delete(f"/api/projects/{project_id}/shares/{share['id']}")
    assert revoked.status_code == 204
    client.post("/api/auth/logout")
    assert client.post("/api/shares/resolve", json={"token": token}).status_code == 404


def test_trial_api_is_explicit_and_idempotent(client: TestClient):
    _login(client, "trial-api@example.edu")
    assert client.get("/api/trial").json()["active"] is False
    first = client.post("/api/trial/activate")
    second = client.post("/api/trial/activate")
    assert first.status_code == 200
    assert first.json()["granted_microusd"] == 5_000_000
    assert second.json() == first.json()


@pytest.fixture
def accounting_factory(tmp_path):
    database_path = tmp_path / "accounting.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(
            TrialProgram(
                key="global",
                enabled=True,
                max_users=3,
                grant_microusd=5_000_000,
                budget_microusd=15_000_000,
            )
        )
        session.commit()
    yield factory
    engine.dispose()


def _new_user(session: Session, index: int) -> User:
    user = User(email=f"trial-{index}@example.edu", email_verified=True)
    session.add(user)
    session.commit()
    return user


def test_verified_email_does_not_silently_link_two_oidc_identities(accounting_factory):
    with accounting_factory() as session:
        upsert_verified_identity(
            session,
            issuer="https://issuer-one.example",
            subject="subject-one",
            email="linked@example.edu",
            email_verified=True,
        )
        with pytest.raises(IdentityError, match="different sign-in identity"):
            upsert_verified_identity(
                session,
                issuer="https://issuer-two.example",
                subject="subject-two",
                email="LINKED@example.edu",
                email_verified=True,
            )


def test_oidc_identity_requires_verification_and_tracks_verified_email_change(
    accounting_factory,
):
    with accounting_factory() as session:
        with pytest.raises(IdentityError, match="verify the email"):
            upsert_verified_identity(
                session,
                issuer="https://issuer.example",
                subject="unverified-subject",
                email="pending@example.edu",
                email_verified=False,
            )

        user = upsert_verified_identity(
            session,
            issuer="https://issuer.example",
            subject="stable-subject",
            email="old-address@example.edu",
            email_verified=True,
        )
        updated = upsert_verified_identity(
            session,
            issuer="https://issuer.example",
            subject="stable-subject",
            email="new-address@example.edu",
            email_verified=True,
        )
        assert updated.id == user.id
        assert updated.email == "new-address@example.edu"


def test_concurrent_first_login_resolves_to_one_identity(accounting_factory):
    def login(_index: int) -> str:
        with accounting_factory() as session:
            return upsert_verified_identity(
                session,
                issuer="https://concurrent-issuer.example",
                subject="concurrent-subject",
                email="concurrent-login@example.edu",
                email_verified=True,
            ).id

    with ThreadPoolExecutor(max_workers=8) as executor:
        user_ids = list(executor.map(login, range(12)))

    assert len(set(user_ids)) == 1
    with accounting_factory() as session:
        assert session.scalar(
            select(func.count(User.id)).where(
                User.email == "concurrent-login@example.edu"
            )
        ) == 1
        assert session.scalar(
            select(func.count(Identity.id)).where(
                Identity.issuer == "https://concurrent-issuer.example",
                Identity.subject == "concurrent-subject",
            )
        ) == 1


@pytest.mark.parametrize(
    "claims",
    [
        {
            "sub": "missing-issuer",
            "email": "missing-issuer@example.edu",
            "email_verified": True,
        },
        {
            "iss": "https://different-issuer.example/",
            "sub": "mismatched-issuer",
            "email": "mismatched-issuer@example.edu",
            "email_verified": True,
        },
    ],
)
def test_oidc_callback_requires_exact_configured_issuer(
    monkeypatch, accounting_factory, claims
):
    from app.api import account_routes

    class FakeOIDCClient:
        async def authorize_access_token(self, _request):
            return {"userinfo": claims}

    class FakeOIDCRegistry:
        def create_client(self, _name):
            return FakeOIDCClient()

    class FakeRequest:
        def __init__(self):
            self.session = {"post_login_path": "/"}

    monkeypatch.setattr(
        account_routes,
        "_oauth_registry",
        lambda: FakeOIDCRegistry(),
    )
    settings = replace(
        get_settings(),
        auth_mode="oidc",
        oidc_issuer="https://expected-issuer.example",
    )
    request = FakeRequest()
    with accounting_factory() as session:
        response = asyncio.run(
            account_routes.oidc_callback(
                request=request,
                session=session,
                settings=settings,
            )
        )
        assert session.scalar(
            select(User).where(User.email == claims["email"])
        ) is None

    assert response.status_code == 303
    assert response.headers["location"] == "/?auth_error=identity_claims_invalid"
    assert request.session == {}


def test_oidc_callback_accepts_exact_issuer_and_boolean_verification(
    monkeypatch, accounting_factory
):
    from app.api import account_routes

    claims = {
        "iss": "https://expected-issuer.example/",
        "sub": "valid-oidc-subject",
        "email": "valid-oidc-callback@example.edu",
        "email_verified": True,
        "name": "Verified Researcher",
        "sid": "auth0-session-id",
    }

    class FakeOIDCClient:
        async def authorize_access_token(self, _request):
            return {"userinfo": claims}

    class FakeOIDCRegistry:
        def create_client(self, _name):
            return FakeOIDCClient()

    class FakeRequest:
        def __init__(self):
            self.session = {"post_login_path": "/workspace"}

    monkeypatch.setattr(
        account_routes,
        "_oauth_registry",
        lambda: FakeOIDCRegistry(),
    )
    settings = replace(
        get_settings(),
        auth_mode="oidc",
        oidc_issuer="https://expected-issuer.example",
    )
    request = FakeRequest()
    with accounting_factory() as session:
        response = asyncio.run(
            account_routes.oidc_callback(
                request=request,
                session=session,
                settings=settings,
            )
        )
        user = session.scalar(
            select(User).where(User.email == claims["email"])
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/workspace"
    assert user is not None
    assert request.session == {
        "user_id": user.id,
        "oidc_sid": "auth0-session-id",
    }


def test_identity_email_is_syntax_checked_and_normalized():
    assert normalize_email(" Researcher@EXAMPLE.EDU ") == "researcher@example.edu"
    with pytest.raises(IdentityError) as error:
        normalize_email("not-an-email")
    assert error.value.code == "identity_claims_invalid"


def test_trial_activation_cap_is_exact_under_concurrency(accounting_factory):
    with accounting_factory() as session:
        user_ids = [_new_user(session, index + 100).id for index in range(12)]

    def claim(user_id: str) -> bool:
        with accounting_factory() as session:
            user = session.get(User, user_id)
            try:
                activate_trial(session, user)
                return True
            except TrialUnavailableError:
                return False

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(claim, user_ids))

    assert sum(results) == 3
    with accounting_factory() as session:
        program = session.get(TrialProgram, "global")
        assert program.activation_count == 3
        assert program.allocated_microusd == 15_000_000


def test_same_user_concurrent_trial_claim_is_idempotent(accounting_factory):
    with accounting_factory() as session:
        user_id = _new_user(session, 555).id

    def claim(_index: int) -> int:
        with accounting_factory() as session:
            user = session.get(User, user_id)
            return activate_trial(session, user).granted_microusd

    with ThreadPoolExecutor(max_workers=6) as executor:
        grants = list(executor.map(claim, range(12)))

    assert grants == [5_000_000] * 12
    with accounting_factory() as session:
        program = session.get(TrialProgram, "global")
        assert program.activation_count == 1
        assert program.allocated_microusd == 5_000_000


def test_trial_reservation_settlement_and_release(accounting_factory):
    with accounting_factory() as session:
        user = _new_user(session, 999)
        activate_trial(session, user)
        reservation = reserve_trial_credit(
            session,
            user.id,
            amount_microusd=4_000_000,
            provider="cloudbank",
            model="test-model",
            request_kind="chat",
        )
        assert get_trial_balance(session, user.id).available_microusd == 1_000_000
        settled = settle_trial_credit(
            session, reservation.id, actual_microusd=2_000_000
        )
        assert settled.spent_microusd == 2_000_000
        assert settled.available_microusd == 3_000_000

        pending = reserve_trial_credit(
            session,
            user.id,
            amount_microusd=3_000_000,
            provider="cloudbank",
            model="test-model",
            request_kind="propose",
        )
        with pytest.raises(InsufficientTrialCreditError):
            reserve_trial_credit(
                session,
                user.id,
                amount_microusd=1,
                provider="cloudbank",
                model="test-model",
                request_kind="chat",
            )
        released = release_trial_credit(session, pending.id)
        assert released.available_microusd == 3_000_000
