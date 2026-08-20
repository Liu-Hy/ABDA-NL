"""API access gates, profile exposure, BYOK secrecy, and safe failures."""
from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.api.llm_access import (
    LLMAccessError,
    build_llm_config,
    llm_http_exception,
    select_request_llm_client,
)
from app.api.models import BYOKRequest, LLMRequestOptions
from app.core.config import get_settings
from app.db.models import User
from app.db.models import LLMUsageEvent
from app.db.session import get_session_factory
from app.llm.catalog import load_model_catalog
from app.llm.client import LLMResponse
from app.llm.providers import LLMProviderError
from app.llm.routing import LLMRouteConfigurationError, LLMRouter
from app.services.trials import InsufficientTrialCreditError


class _StubRouter:
    def __init__(self):
        self.catalog = load_model_catalog()
        self.funded_calls = []
        self.byok_calls = []
        self.funded_client = object()
        self.byok_client = object()

    def funded(self, profile_id, *, context):
        self.funded_calls.append((profile_id, context))
        return self.funded_client

    def byok(self, credential, *, context):
        self.byok_calls.append((credential, context))
        return self.byok_client


def _verified_user() -> User:
    return User(
        id="user-verified",
        email="verified@example.edu",
        email_verified=True,
        status="active",
    )


def _public_settings():
    return replace(get_settings(), llm_require_auth=True)


def test_public_config_exposes_only_quality_gated_profile():
    config = build_llm_config(llm_enabled=True, settings=_public_settings())
    assert [profile.id for profile in config.profiles] == ["balanced"]
    assert config.default_profile == "balanced"
    assert config.byok_enabled is True
    assert config.byok_keys_stored is False


def test_development_config_also_hides_unvalidated_funded_profiles():
    config = build_llm_config(llm_enabled=True, settings=get_settings())
    assert [profile.id for profile in config.profiles] == ["balanced"]


def test_byok_request_representation_and_json_hide_secret():
    request = BYOKRequest(
        provider="openai",
        api_key="sk-user-secret-that-must-not-appear",
        model="gpt-5.6-terra",
    )
    assert "sk-user-secret" not in repr(request)
    assert "sk-user-secret" not in request.model_dump_json()


def test_public_funded_route_requires_authenticated_verified_user():
    router = _StubRouter()
    with pytest.raises(LLMAccessError) as anonymous:
        select_request_llm_client(
            None,
            user=None,
            request_id="request-1",
            request_kind="chat",
            legacy_factory=lambda: object(),
            settings=_public_settings(),
            router=router,
        )
    assert anonymous.value.status_code == 401

    unverified = User(
        id="user-unverified",
        email="unverified@example.edu",
        email_verified=False,
        status="active",
    )
    with pytest.raises(LLMAccessError) as pending:
        select_request_llm_client(
            None,
            user=unverified,
            request_id="request-2",
            request_kind="chat",
            legacy_factory=lambda: object(),
            settings=_public_settings(),
            router=router,
        )
    assert pending.value.status_code == 403
    assert not router.funded_calls


def test_public_funded_route_charges_trial_and_propagates_context():
    router = _StubRouter()
    result = select_request_llm_client(
        LLMRequestOptions(profile="balanced"),
        user=_verified_user(),
        request_id="request-funded",
        request_kind="propose",
        legacy_factory=lambda: object(),
        settings=_public_settings(),
        router=router,
    )
    assert result is router.funded_client
    profile, context = router.funded_calls[0]
    assert profile == "balanced"
    assert context.user_id == "user-verified"
    assert context.request_id == "request-funded"
    assert context.request_kind == "propose"
    assert context.charge_trial is True


def test_funded_route_rejects_profile_that_has_not_passed_eval_gate():
    router = _StubRouter()
    with pytest.raises(LLMAccessError) as error:
        select_request_llm_client(
            LLMRequestOptions(profile="economy"),
            user=_verified_user(),
            request_id="request-economy",
            request_kind="chat",
            legacy_factory=lambda: object(),
            settings=get_settings(),
            router=router,
        )
    assert error.value.code == "model_profile_not_ready"
    assert not router.funded_calls


def test_byok_route_bypasses_trial_and_passes_secret_only_to_router():
    router = _StubRouter()
    options = LLMRequestOptions(
        byok=BYOKRequest(
            provider="openai",
            api_key="sk-session-only-secret",
            model="gpt-5.6-terra",
        )
    )
    result = select_request_llm_client(
        options,
        user=_verified_user(),
        request_id="request-byok",
        request_kind="chat",
        legacy_factory=lambda: object(),
        settings=_public_settings(),
        router=router,
    )
    assert result is router.byok_client
    credential, context = router.byok_calls[0]
    assert credential.api_key == "sk-session-only-secret"
    assert "sk-session-only-secret" not in repr(credential)
    assert context.charge_trial is False
    assert not router.funded_calls


def test_local_ollama_path_preserves_legacy_client(monkeypatch):
    monkeypatch.setenv("ABDA_LLM_BACKEND", "ollama")
    legacy = object()
    router = _StubRouter()
    result = select_request_llm_client(
        None,
        user=None,
        request_id="request-local",
        request_kind="chat",
        legacy_factory=lambda: legacy,
        settings=replace(get_settings(), llm_require_auth=False),
        router=router,
    )
    assert result is legacy
    assert not router.funded_calls
    assert not router.byok_calls


def test_http_error_mapping_never_exposes_provider_or_key_details():
    rejected = llm_http_exception(
        LLMProviderError(
            "provider body contained sk-user-secret",
            provider="openai",
            status_code=401,
            retryable=False,
            outage_candidate=False,
        ),
        byok=True,
    )
    assert rejected.status_code == 400
    assert rejected.detail["code"] == "byok_credentials_rejected"
    assert "sk-user-secret" not in str(rejected.detail)

    rate_limited = llm_http_exception(
        LLMProviderError(
            "provider body contained sk-user-secret",
            provider="openai",
            status_code=429,
            retryable=True,
            outage_candidate=True,
        ),
        byok=True,
    )
    assert rate_limited.status_code == 429
    assert rate_limited.detail["code"] == "byok_provider_rate_limited"
    assert rate_limited.headers == {"Retry-After": "30"}
    assert "sk-user-secret" not in str(rate_limited.detail)

    unavailable = llm_http_exception(
        LLMProviderError(
            "provider body contained sk-user-secret",
            provider="google",
            status_code=503,
            retryable=True,
            outage_candidate=True,
        ),
        byok=True,
    )
    assert unavailable.status_code == 503
    assert unavailable.detail["code"] == "byok_provider_unavailable"
    assert unavailable.headers == {"Retry-After": "30"}
    assert "sk-user-secret" not in str(unavailable.detail)

    route = llm_http_exception(
        LLMRouteConfigurationError("internal endpoint and account details"),
        byok=False,
    )
    assert route.status_code == 503
    assert "endpoint" not in str(route.detail)

    trial = llm_http_exception(
        InsufficientTrialCreditError("claim trial credit before using funded models"),
        byok=False,
    )
    assert trial.status_code == 402
    assert trial.detail["code"] == "trial_credit_required"


def test_public_chat_endpoint_enforces_access_before_client_creation(monkeypatch):
    from app.api import llm_access
    from app.api import main as main_module

    monkeypatch.setattr(llm_access, "get_settings", _public_settings)
    monkeypatch.setattr(main_module, "ENABLE_LLM", True)
    monkeypatch.setattr(main_module, "_llm_client", object())

    with TestClient(main_module.app) as client:
        response = client.post(
            "/chat",
            json={
                "scenario_id": "popov_v_hayashi",
                "diff_ops": [],
                "messages": [{"role": "user", "content": "Explain the result."}],
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"
    assert response.headers["x-request-id"]


def test_invalid_llm_options_do_not_echo_byok_secret(monkeypatch):
    from app.api import main as main_module

    monkeypatch.setattr(main_module, "ENABLE_LLM", True)
    secret = "sk-invalid-options-secret"
    with TestClient(main_module.app) as client:
        response = client.post(
            "/chat",
            json={
                "scenario_id": "popov_v_hayashi",
                "messages": [{"role": "user", "content": "Explain."}],
                "llm": {
                    "profile": "balanced",
                    "byok": {
                        "provider": "openai",
                        "api_key": secret,
                    },
                },
            },
        )
    assert response.status_code == 422
    assert secret not in response.text


class _CannedPhysicalClient:
    def __init__(
        self,
        *,
        model: str,
        provider: str,
        billing_source: str,
        route: str,
    ) -> None:
        self.model = model
        self.provider = provider
        self.billing_source = billing_source
        self.route = route

    def complete(self, **_kwargs):
        return LLMResponse(
            text="The scenario remains balanced between the two parties.",
            stop_reason="end_turn",
            usage={"input_tokens": 100, "output_tokens": 20},
            latency_ms=12,
            model=self.model,
            provider=self.provider,
            billing_source=self.billing_source,
            route=self.route,
        )


def _install_request_router(monkeypatch, router: LLMRouter, settings) -> None:
    from app.api import main as main_module

    def choose(options, *, user, request_id, request_kind):
        return select_request_llm_client(
            options,
            user=user,
            request_id=request_id,
            request_kind=request_kind,
            legacy_factory=lambda: object(),
            settings=settings,
            router=router,
        )

    monkeypatch.setattr(main_module, "ENABLE_LLM", True)
    monkeypatch.setattr(main_module, "_request_llm_client", choose)


def _login_and_claim_trial(client: TestClient, email: str) -> dict:
    login = client.post(
        "/api/auth/dev/login",
        json={"email": email, "display_name": "LLM integration test"},
    )
    assert login.status_code == 200
    claimed = client.post("/api/trial/activate")
    assert claimed.status_code == 200
    return login.json()["user"]


def test_funded_api_call_deducts_exact_metered_trial_cost(monkeypatch):
    from app.api import main as main_module

    settings = replace(
        get_settings(),
        llm_require_auth=True,
        llm_retry_attempts=1,
        openrouter_failover_enabled=False,
    )
    router = LLMRouter(settings=settings, session_factory=get_session_factory())

    def raw_route(route, *, user_id):
        assert user_id
        spec = router.catalog.model_for_route(route)
        return (
            _CannedPhysicalClient(
                model=spec.id,
                provider=route.provider,
                billing_source=route.billing_source,
                route=route.id,
            ),
            spec,
        )

    monkeypatch.setattr(router, "_raw_route", raw_route)
    _install_request_router(monkeypatch, router, settings)

    with TestClient(main_module.app) as client:
        client.post("/api/auth/logout")
        user = _login_and_claim_trial(client, "funded-api-routing@example.edu")
        response = client.post(
            "/chat",
            json={
                "scenario_id": "popov_v_hayashi",
                "messages": [{"role": "user", "content": "Explain the balance."}],
                "llm": {"profile": "balanced"},
            },
        )
        balance = client.get("/api/trial").json()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["billing_source"] == "cloudbank"
    assert body["route"] == "cloudbank-claude-sonnet-4-6"
    assert body["cost_microusd"] > 0
    assert balance["spent_microusd"] == body["cost_microusd"]
    assert balance["reserved_microusd"] == 0

    with get_session_factory()() as session:
        events = session.query(LLMUsageEvent).filter_by(
            request_id=body["request_id"], user_id=user["id"]
        ).all()
    assert len(events) == 1
    assert events[0].status == "succeeded"
    assert events[0].cost_microusd == body["cost_microusd"]


def test_funded_api_call_without_claimed_trial_returns_402(monkeypatch):
    from app.api import main as main_module

    settings = replace(
        get_settings(),
        llm_require_auth=True,
        llm_retry_attempts=1,
        openrouter_failover_enabled=False,
    )
    router = LLMRouter(settings=settings, session_factory=get_session_factory())

    def raw_route(route, *, user_id):
        spec = router.catalog.model_for_route(route)
        return (
            _CannedPhysicalClient(
                model=spec.id,
                provider=route.provider,
                billing_source=route.billing_source,
                route=route.id,
            ),
            spec,
        )

    monkeypatch.setattr(router, "_raw_route", raw_route)
    _install_request_router(monkeypatch, router, settings)

    with TestClient(main_module.app) as client:
        client.post("/api/auth/logout")
        login = client.post(
            "/api/auth/dev/login",
            json={"email": "no-trial-routing@example.edu"},
        )
        assert login.status_code == 200
        response = client.post(
            "/chat",
            json={
                "scenario_id": "popov_v_hayashi",
                "messages": [{"role": "user", "content": "Explain the balance."}],
                "llm": {"profile": "balanced"},
            },
        )

    assert response.status_code == 402
    assert response.json()["detail"]["code"] == "trial_credit_required"
    assert "claim trial credit" in response.json()["detail"]["message"]


def test_byok_api_call_is_audited_without_trial_deduction(monkeypatch):
    from app.api import main as main_module
    from app.llm import routing as routing_module

    seen_keys = []

    class FakeDirectOpenAI(_CannedPhysicalClient):
        def __init__(self, **kwargs):
            seen_keys.append(kwargs["api_key"])
            super().__init__(
                model=kwargs["model"],
                provider=kwargs["provider"],
                billing_source=kwargs["billing_source"],
                route=kwargs["route"],
            )

    monkeypatch.setattr(routing_module, "OpenAIResponsesClient", FakeDirectOpenAI)
    settings = replace(
        get_settings(),
        llm_require_auth=True,
        llm_retry_attempts=1,
        openrouter_failover_enabled=False,
    )
    router = LLMRouter(settings=settings, session_factory=get_session_factory())
    _install_request_router(monkeypatch, router, settings)
    secret = "sk-session-only-integration-secret"

    with TestClient(main_module.app) as client:
        client.post("/api/auth/logout")
        login = client.post(
            "/api/auth/dev/login",
            json={"email": "byok-api-routing@example.edu"},
        )
        assert login.status_code == 200
        user = login.json()["user"]
        before = client.get("/api/trial").json()
        response = client.post(
            "/chat",
            json={
                "scenario_id": "popov_v_hayashi",
                "messages": [{"role": "user", "content": "Explain the balance."}],
                "llm": {
                    "byok": {
                        "provider": "openai",
                        "api_key": secret,
                        "model": "gpt-5.6-terra",
                    }
                },
            },
        )
        after = client.get("/api/trial").json()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["billing_source"] == "byok"
    assert body["route"] == "byok:openai:gpt-5.6-terra"
    assert before == after
    assert after["active"] is False
    assert seen_keys == [secret]
    assert secret not in response.text

    with get_session_factory()() as session:
        events = session.query(LLMUsageEvent).filter_by(
            request_id=body["request_id"], user_id=user["id"]
        ).all()
    assert len(events) == 1
    event = events[0]
    assert event.billing_source == "byok"
    assert secret not in " ".join(
        value or ""
        for value in (event.provider, event.route, event.model, event.error_type)
    )
