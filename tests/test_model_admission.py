"""Admission failures stay unavailable across public LLM entry points."""
from dataclasses import replace

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from app.api import llm_access
from app.api.models import BYOKRequest, LLMRequestOptions
from app.core.config import get_settings
from app.db.models import User
from app.llm import routing
from app.llm.catalog import load_model_catalog
from app.mcp import server as mcp_module


PUBLIC_MODELS = {
    "claude-sonnet-5", "claude-opus-5", "gpt-5.6-terra", "gpt-5.6-sol",
    "gemini-3.8-flash", "gemini-3.1-pro-preview",
}
WITHHELD_MODELS = {
    "glm-5-3": "glm-5.3",
    "deepseek-v4-flash-0731": "deepseek-v4-flash-0731",
    "kimi-k3": "kimi-k3",
}


def _user():
    return User(id="admission-test", email="admission@example.edu",
                email_verified=True, status="active")


def _settings():
    return replace(get_settings(), llm_require_auth=True, llm_allow_byok=True,
                   llm_allow_legacy_development=False)


def _forbid_dispatch(*_args, **_kwargs):
    pytest.fail("an unqualified model must be rejected before provider construction")


def test_six_qualified_models_share_quota_and_byok_pool():
    catalog = load_model_catalog()
    config = llm_access.build_llm_config(llm_enabled=True, settings=_settings())
    funded = {catalog.routes[catalog.profiles[p.id].primary_route].model
              for p in config.profiles}
    byok = {model.id for provider in config.byok_providers for model in provider.models}
    assert catalog.public_model_ids() == funded == byok == PUBLIC_MODELS
    for profile_id, model_id in WITHHELD_MODELS.items():
        assert profile_id not in {profile.id for profile in config.profiles}
        profile = catalog.profiles[profile_id]
        assert not profile.public_ready
        route = catalog.routes[profile.primary_route]
        assert route.model == model_id and not route.funded_feature_qualified
        assert route.metadata_confirmed and route.configuration_confirmed
        assert route.live_inference_verified
        assert catalog.routes[profile.fallback_route].model == model_id


@pytest.mark.parametrize("profile_id", WITHHELD_MODELS)
@pytest.mark.parametrize("request_kind", ["chat", "propose"])
def test_http_selection_rejects_withheld_models_without_provider_or_charge(
    profile_id, request_kind, monkeypatch,
):
    router = routing.LLMRouter(settings=_settings())
    monkeypatch.setattr(router, "funded", _forbid_dispatch)
    with pytest.raises(llm_access.LLMAccessError) as caught:
        llm_access.select_request_llm_client(
            LLMRequestOptions(profile=profile_id), user=_user(),
            request_id="withheld-funded", request_kind=request_kind,
            legacy_factory=_forbid_dispatch, settings=_settings(), router=router,
        )
    response = llm_access.llm_http_exception(caught.value, byok=False)
    assert response.status_code == 400
    assert response.detail["code"] == "model_profile_not_ready"


@pytest.mark.parametrize("model_id", WITHHELD_MODELS.values())
def test_http_byok_selection_rejects_withheld_models_without_provider_or_charge(model_id, monkeypatch):
    router = routing.LLMRouter(settings=_settings())
    monkeypatch.setattr(routing, "OpenAICompatibleClient", _forbid_dispatch)
    monkeypatch.setattr(router, "_metered_retrying", _forbid_dispatch)
    with pytest.raises(routing.BYOKValidationError) as caught:
        llm_access.select_request_llm_client(
            LLMRequestOptions(byok=BYOKRequest(
                provider="openrouter", api_key="synthetic-test-key", model=model_id,
            )), user=_user(), request_id="withheld-byok", request_kind="chat",
            legacy_factory=_forbid_dispatch, settings=_settings(), router=router,
        )
    response = llm_access.llm_http_exception(caught.value, byok=True)
    assert response.status_code == 400
    assert response.detail["code"] == "byok_configuration_invalid"


@pytest.mark.parametrize("profile_id", WITHHELD_MODELS)
@pytest.mark.parametrize("tool_name,arguments", [
    ("ask_project", {"project_id": "unused", "question": "Explain this result."}),
    ("propose_project_edit", {
        "project_id": "unused", "task": "modify-rule", "existing_id": "r_stack",
        "instruction": "Change only the category to strategy.",
    }),
])
def test_mcp_tool_schema_rejects_withheld_selection(profile_id, tool_name, arguments, monkeypatch):
    monkeypatch.setattr(mcp_module, "_load_project_for_llm", _forbid_dispatch)
    runtime = mcp_module.create_mcp_runtime()

    async def check():
        tools = {tool.name: tool for tool in await runtime.server.list_tools()}
        schema = tools[tool_name].input_schema["properties"]["profile"]
        selected = next(item for item in schema["anyOf"] if item["type"] == "string")
        profiles = selected.get("enum", [selected.get("const")])
        assert set(profiles) == {profile.id for profile in load_model_catalog().public_profiles()}
        assert profile_id not in profiles
        with pytest.raises(ToolError, match="profile") as caught:
            await runtime.server.call_tool(tool_name, {**arguments, "profile": profile_id})
        assert "literal_error" in str(caught.value)

    anyio.run(check)


@pytest.mark.parametrize("profile_id", WITHHELD_MODELS)
@pytest.mark.parametrize("request_kind", ["mcp-chat", "mcp-propose"])
def test_mcp_runtime_rejects_withheld_models_with_stale_tool_schema(profile_id, request_kind, monkeypatch):
    settings = _settings()
    router = routing.LLMRouter(settings=settings)
    monkeypatch.setattr(router, "funded", _forbid_dispatch)
    monkeypatch.setattr(llm_access, "LLMRouter", lambda **_kwargs: router)
    monkeypatch.setattr(mcp_module, "get_settings", lambda: settings)
    monkeypatch.setattr(mcp_module, "_llm_enabled", lambda: True)
    with pytest.raises(llm_access.LLMAccessError) as caught:
        mcp_module._select_mcp_llm_client(
            user=_user(), profile=profile_id, request_id="withheld-mcp",
            request_kind=request_kind,
        )
    assert caught.value.code == "model_profile_not_ready"


@pytest.mark.parametrize("profile_id", WITHHELD_MODELS)
def test_withheld_models_remain_available_to_internal_funded_evaluation(profile_id, monkeypatch):
    router = routing.LLMRouter(settings=_settings())
    route_id = router.catalog.profiles[profile_id].primary_route
    context = routing.CallContext(None, "internal-eval", "evaluation", False)
    selected = []
    client = object()

    def build(route, **kwargs):
        selected.append((route, kwargs))
        return client

    monkeypatch.setattr(router, "_metered_retrying", build)
    assert router.evaluation_route(route_id, context=context) is client
    assert len(selected) == 1
    route, kwargs = selected[0]
    assert route.id == route_id and route.billing_source == "cloudbank"
    assert not route.funded_feature_qualified
    assert kwargs["context"] is context
