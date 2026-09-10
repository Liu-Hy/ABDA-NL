"""Browser mode reduces curator authority without impersonation or credit changes."""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi import Response
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.main import app
from app.core.config import Settings, get_settings, reset_settings_cache
from app.db.models import (
    CreditEligibilityMarker,
    LLMUsageEvent,
    NamedCreditEntitlement,
    TrialGrant,
    TrialProgram,
    UsageReservation,
    User,
)
from app.db.session import get_session_factory, reset_database_caches
from app.services.admin_view import admin_view_cookie_name, set_admin_view_cookie
from app.services.credit_policy import NAMED_CREDIT_EMAILS

CURATOR = "curator@example.org"
OTHER_CURATOR = "second-curator@example.org"
AUTHOR = "author@example.org"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ABDA_DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'view-mode.db'}")
    monkeypatch.setenv("ABDA_SCENARIO_ADMIN_EMAILS", f"{CURATOR},{OTHER_CURATOR}")
    monkeypatch.setenv("ABDA_COMMUNITY_CATALOG_ENABLED", "true")
    monkeypatch.setenv("ABDA_TRIAL_ENABLED", "true")
    monkeypatch.setenv("ABDA_ABUSE_PROTECTION_ENABLED", "false")
    reset_database_caches()
    reset_settings_cache()
    with TestClient(app) as result:
        yield result
    app.dependency_overrides.pop(get_settings, None)
    reset_database_caches()
    reset_settings_cache()


def login(client, email=CURATOR):
    response = client.post("/api/auth/dev/login", json={"email": email})
    assert response.status_code == 200, response.text
    return response.json()


def set_mode(client, normal):
    return client.post("/api/auth/view-mode", json={"normal_user_view": normal})


def project(client):
    response = client.post(
        "/api/projects", json={"name": "View mode example", "source_scenario_id": "popov_v_hayashi"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def submit(client, saved, *, publish=False):
    return client.post("/api/scenario-submissions", json={
        "project_id": saved["id"], "expected_version": saved["version"],
        "public_consent": True, "publish": publish,
    })


def review(client, item, action):
    return client.post(f"/api/scenario-submissions/{item['id']}/review", json={
        "expected_version": item["version"], "action": action, "note": "Review test reason",
    })


def credit_snapshot():
    with get_session_factory()() as session:
        return {
            model.__tablename__: list(session.execute(select(model.__table__).order_by(*model.__table__.primary_key)))
            for model in (
                TrialGrant, TrialProgram, NamedCreditEntitlement,
                CreditEligibilityMarker, UsageReservation, LLMUsageEvent,
            )
        }


def test_curator_demotes_every_admin_path_and_keeps_own_workspace_and_credit(client):
    login(client, AUTHOR)
    others = submit(client, project(client)).json()
    signed_in = login(client)
    assert signed_in["scenario_admin"] and signed_in["can_switch_admin_view"]
    assert not signed_in["normal_user_view"]
    published = submit(client, project(client), publish=True).json()
    pending = submit(client, project(client)).json()
    draft = project(client)
    draft_before = client.get(f"/api/projects/{draft['id']}").json()
    quota = client.get("/api/trial").json()
    credit = credit_snapshot()

    switched = set_mode(client, True)
    assert switched.status_code == 200, switched.text
    assert switched.json() == {**signed_in, "scenario_admin": False, "normal_user_view": True}
    assert client.get("/api/auth/session").json() == switched.json()
    assert client.get(f"/api/projects/{draft['id']}").json() == draft_before
    assert client.get("/api/trial").json() == quota
    assert client.get("/api/scenario-submissions?queue=true").status_code == 403
    assert client.get(f"/api/scenario-submissions/{others['id']}").status_code == 404
    assert review(client, others, "approve").status_code == 404
    # These service methods reload the real administrator account. A temporary
    # change only to the HTTP dependency's User would fail these checks.
    assert submit(client, draft, publish=True).status_code == 403
    assert review(client, pending, "approve").status_code == 403
    assert review(client, pending, "reject").status_code == 403
    assert review(client, published, "unpublish").status_code == 403
    normal_submission = submit(client, draft)
    assert normal_submission.status_code == 201, normal_submission.text
    assert normal_submission.json()["status"] == "pending"
    assert review(client, normal_submission.json(), "withdraw").status_code == 200
    assert client.put(f"/api/projects/{draft['id']}", json={
        "expected_version": draft["version"], "name": "An ordinary user edit",
    }).status_code == 200

    restored = set_mode(client, False)
    assert restored.status_code == 200, restored.text
    assert restored.json() == signed_in
    assert client.get("/api/scenario-submissions?queue=true").status_code == 200
    assert client.get(f"/api/scenario-submissions/{others['id']}").status_code == 200
    assert review(client, others, "approve").status_code == 200
    assert review(client, pending, "approve").status_code == 200
    assert credit_snapshot() == credit


@pytest.mark.parametrize("email", NAMED_CREDIT_EMAILS)
def test_named_administrators_lose_curator_rights_only_in_normal_view(client, email):
    signed_in = login(client, email)
    assert signed_in["can_switch_admin_view"]
    assert signed_in["scenario_admin"]
    saved = project(client)
    pending = submit(client, project(client)).json()
    published = submit(client, project(client), publish=True)
    assert published.status_code == 201, published.text
    assert published.json()["status"] == "published"
    assert client.get("/api/scenario-submissions?queue=true").status_code == 200
    quota = client.get("/api/trial").json()
    assert quota["granted_microusd"] == 50_000_000
    credit = credit_snapshot()
    response = set_mode(client, True)
    assert response.status_code == 200, response.text
    assert response.json() == {**signed_in, "normal_user_view": True, "scenario_admin": False}
    assert client.get("/api/scenario-submissions?queue=true").status_code == 403
    assert submit(client, saved, publish=True).status_code == 403
    assert review(client, pending, "approve").status_code == 403
    assert review(client, pending, "reject").status_code == 403
    assert review(client, published.json(), "unpublish").status_code == 403
    assert client.get(f"/api/projects/{saved['id']}").status_code == 200
    assert client.get("/api/trial").json() == quota
    restored = set_mode(client, False)
    assert restored.status_code == 200, restored.text
    assert restored.json() == signed_in
    assert client.get("/api/scenario-submissions?queue=true").status_code == 200
    assert submit(client, saved, publish=True).json()["status"] == "published"
    assert review(client, pending, "approve").status_code == 200
    assert review(client, published.json(), "unpublish").status_code == 200
    assert credit_snapshot() == credit


def test_ordinary_accounts_cannot_enable_or_restore_admin_view(client):
    assert set_mode(client, True).status_code == 401
    for email in (AUTHOR, "hl57+alias@illinois.edu", "hl57@illinois.edu.example.org"):
        signed_in = login(client, email)
        assert not signed_in["can_switch_admin_view"]
        assert not signed_in["normal_user_view"]
        assert not signed_in["scenario_admin"]
        for normal in (True, False):
            response = set_mode(client, normal)
            assert response.status_code == 403
            assert response.json()["detail"]["code"] == "admin_view_unavailable"
        assert client.get("/api/scenario-submissions?queue=true").status_code == 403


def test_arbitrary_fifty_dollar_grant_never_confers_administrator_rights(client):
    user = login(client, AUTHOR)["user"]
    client.post("/api/trial/activate")
    with get_session_factory()() as session:
        grant = session.get(TrialGrant, user["id"])
        program = session.get(TrialProgram, grant.program_key)
        program.allocated_microusd += 50_000_000 - grant.granted_microusd
        grant.granted_microusd = 50_000_000
        session.commit()
    credit = credit_snapshot()
    state = client.get("/api/auth/session").json()
    assert not state["scenario_admin"] and not state["can_switch_admin_view"]
    assert client.get("/api/trial").json()["granted_microusd"] == 50_000_000
    assert set_mode(client, True).status_code == 403
    assert set_mode(client, False).status_code == 403
    assert client.get("/api/scenario-submissions?queue=true").status_code == 403
    assert submit(client, project(client), publish=True).status_code == 403
    assert credit_snapshot() == credit


@pytest.mark.parametrize("extra", [None, "", "CURATOR@EXAMPLE.ORG, hl57@illinois.edu,curator@example.org"])
def test_admin_settings_keep_exact_named_identities_and_normalized_extras(monkeypatch, extra):
    if extra is None:
        monkeypatch.delenv("ABDA_SCENARIO_ADMIN_EMAILS", raising=False)
    else:
        monkeypatch.setenv("ABDA_SCENARIO_ADMIN_EMAILS", extra)
    settings = Settings.from_environment()
    expected = set(NAMED_CREDIT_EMAILS) | ({CURATOR} if extra else set())
    assert set(settings.scenario_admin_emails) == expected
    assert len(settings.scenario_admin_emails) == len(expected)
    assert "hl57+alias@illinois.edu" not in settings.scenario_admin_emails
    assert "other@illinois.edu" not in settings.scenario_admin_emails
    assert Settings.__dataclass_fields__["scenario_admin_emails"].default == NAMED_CREDIT_EMAILS


@pytest.mark.parametrize("field,value,status", [
    ("email_verified", False, 403),
    ("status", "deletion_pending", 401),
])
def test_demoted_account_cannot_restore_after_verification_or_status_revocation(client, field, value, status):
    user = login(client)["user"]
    assert set_mode(client, True).status_code == 200
    with get_session_factory()() as session:
        persisted = session.get(User, user["id"])
        setattr(persisted, field, value)
        session.commit()
    response = set_mode(client, False)
    assert response.status_code == status
    assert set_mode(client, True).status_code == status
    state = client.get("/api/auth/session").json()
    assert not state["can_switch_admin_view"]
    assert not state["scenario_admin"]


def test_demoted_configured_curator_cannot_restore_revoked_base_role(client):
    login(client)
    pending = submit(client, project(client)).json()
    assert set_mode(client, True).status_code == 200
    settings = replace(get_settings(), scenario_admin_emails=NAMED_CREDIT_EMAILS)
    app.dependency_overrides[get_settings] = lambda: settings
    response = set_mode(client, False)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "admin_view_unavailable"
    state = client.get("/api/auth/session").json()
    assert not state["can_switch_admin_view"] and not state["scenario_admin"]
    assert client.get("/api/scenario-submissions?queue=true").status_code == 403
    assert review(client, pending, "approve").status_code == 403
    client.cookies.delete(admin_view_cookie_name(settings))
    assert not client.get("/api/auth/session").json()["scenario_admin"]


@pytest.mark.parametrize("payload", [
    {}, {"normal_user_view": "false"}, {"normal_user_view": 1},
    {"normal_user_view": None}, {"normal_user_view": False, "scenario_admin": True},
])
def test_view_mode_payload_cannot_coerce_or_set_authority(client, payload):
    login(client)
    assert client.post("/api/auth/view-mode", json=payload).status_code == 422
    assert not client.get("/api/auth/session").json()["normal_user_view"]


def test_view_mode_requires_same_origin_and_uses_account_rate_limit(client):
    login(client)
    settings = replace(get_settings(), abuse_protection_enabled=True, mutation_requests_per_minute=1)
    app.dependency_overrides[get_settings] = lambda: settings
    denied = client.post("/api/auth/view-mode", json={"normal_user_view": True},
                         headers={"Origin": "https://other.example"})
    assert denied.status_code == 403
    assert not client.get("/api/auth/session").json()["normal_user_view"]
    allowed = client.post("/api/auth/view-mode", json={"normal_user_view": True},
                          headers={"Origin": "http://testserver"})
    assert allowed.status_code == 200, allowed.text
    denied = set_mode(client, False)
    assert denied.status_code == 429
    assert "Retry-After" in denied.headers
    assert client.get("/api/auth/session").json()["normal_user_view"]


def test_mode_cookie_is_user_bound_and_cannot_escalate_other_accounts(client):
    login(client)
    assert set_mode(client, True).status_code == 200
    name = admin_view_cookie_name(get_settings())
    cookie = client.cookies.get(name)
    login(client, OTHER_CURATOR)
    client.cookies.set(name, cookie, domain="testserver.local", path="/")
    state = client.get("/api/auth/session").json()
    assert state["scenario_admin"]
    assert not state["normal_user_view"]
    login(client, AUTHOR)
    for value in (cookie, cookie + "tampered", '{"scenario_admin":true}'):
        client.cookies.set(name, value, domain="testserver.local", path="/")
        state = client.get("/api/auth/session").json()
        assert not state["scenario_admin"]
        assert not state["can_switch_admin_view"]
        assert set_mode(client, False).status_code == 403
        assert client.get("/api/scenario-submissions?queue=true").status_code == 403


def test_mode_survives_late_ordinary_responses_and_isolated_browser_login(client):
    login(client)
    name = admin_view_cookie_name(get_settings())
    old_admin_response = client.get("/api/auth/session")
    switched = set_mode(client, True)
    header = next(value for value in switched.headers.get_list("set-cookie") if value.startswith(name + "="))
    assert "HttpOnly" in header and "SameSite=lax" in header and "Path=/" in header
    assert "Max-Age" not in header and "expires=" not in header.lower() and "Domain=" not in header
    assert name not in old_admin_response.cookies
    client.cookies.update(old_admin_response.cookies)
    old_normal_response = client.get("/api/auth/session")
    assert old_normal_response.json()["normal_user_view"]
    assert name not in old_normal_response.cookies

    # Another browser has the same real account but its own view preference.
    other_browser = TestClient(app)
    try:
        assert login(other_browser)["scenario_admin"]
        assert other_browser.get("/api/scenario-submissions?queue=true").status_code == 200
        assert client.get("/api/scenario-submissions?queue=true").status_code == 403
    finally:
        other_browser.close()

    assert set_mode(client, False).status_code == 200
    client.cookies.update(old_normal_response.cookies)
    assert client.get("/api/auth/session").json()["scenario_admin"]
    assert not client.get("/api/auth/session").json()["normal_user_view"]


@pytest.mark.parametrize("logout_path", ["/api/auth/logout", "/auth/logout"])
def test_logout_and_new_login_reset_browser_mode(client, logout_path):
    login(client)
    assert set_mode(client, True).status_code == 200
    name = admin_view_cookie_name(get_settings())
    response = client.post(logout_path, follow_redirects=False)
    assert response.status_code in (200, 303)
    assert name not in client.cookies
    assert not client.get("/api/auth/session").json()["authenticated"]
    assert login(client)["scenario_admin"]
    assert set_mode(client, True).status_code == 200
    assert login(client)["scenario_admin"]
    assert name not in client.cookies


@pytest.mark.parametrize("valid_issuer", [True, False])
def test_oidc_callback_resets_mode_for_success_and_rejected_login(client, monkeypatch, valid_issuer):
    from app.api import account_routes

    login(client)
    assert set_mode(client, True).status_code == 200
    name = admin_view_cookie_name(get_settings())
    issuer = "urn:abda-nl:local-development"
    settings = replace(get_settings(), auth_mode="oidc", oidc_issuer=issuer)
    app.dependency_overrides[get_settings] = lambda: settings

    class OIDCClient:
        async def authorize_access_token(self, request):
            return {"userinfo": {
                "iss": issuer if valid_issuer else "https://wrong-issuer.example",
                "sub": f"email:{CURATOR}", "email": CURATOR, "email_verified": True,
            }}

    class Registry:
        def create_client(self, name):
            return OIDCClient()

    monkeypatch.setattr(account_routes, "_oauth_registry", lambda: Registry())
    response = client.get("/auth/callback", follow_redirects=False)
    assert response.status_code == 303
    assert name not in client.cookies
    state = client.get("/api/auth/session").json()
    assert state["authenticated"] is valid_issuer
    assert state["scenario_admin"] is valid_issuer
    assert not state["normal_user_view"]


def test_hosted_mode_cookie_preserves_host_only_secure_scope():
    settings = replace(get_settings(), cookie_secure=True, session_cookie="__Host-abda_session")
    response = Response()
    set_admin_view_cookie(response, User(id="verified-admin"), settings)
    header = response.headers["set-cookie"]
    assert header.startswith("__Host-abda_session_view_mode=")
    assert "HttpOnly" in header and "Secure" in header and "Path=/" in header
    assert "Domain=" not in header
