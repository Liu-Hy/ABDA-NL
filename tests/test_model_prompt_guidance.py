"""Keep observed prompt corrections scoped through actual routing wrappers."""
from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import pytest

from app.llm.catalog import load_model_catalog
from app.llm.chat_service import build_system_prompt, run_turn
from app.llm.client import LLMResponse
from app.llm.prompts import model_prompt_guidance
from app.llm.routing import FailoverClient, RetryingClient
from app.scenario.catalog import load_bundled_scenario
from app.scenario.state import compute_state_bundle

SCENARIO_DIR = Path(__file__).resolve().parents[1] / "examples" / "fire_prevention"


class CapturingClient:
    def __init__(self, model: str):
        self.model_spec = load_model_catalog().models[model]
        self.model = "deployment-name"
        self.requests: list[dict] = []

    def complete(self, **kwargs):
        self.requests.append(kwargs)
        return LLMResponse(
            text="Conducting the burn is undecided.", stop_reason="end_turn",
            usage={"input_tokens": 1, "output_tokens": 1},
            latency_ms=1, model=self.model,
        )


@pytest.mark.parametrize("model", [
    "gpt-5.6-sol", "gemini-3.1-pro-preview",
    "gemini-3.8-flash", "deepseek-v4-flash-0731", "glm-5.3", "kimi-k3",
])
def test_unaffected_model_receives_byte_identical_chat_prompt(model):
    scenario = load_bundled_scenario("fire_prevention")
    af = compute_state_bundle(scenario)["af"]
    client = CapturingClient(model)
    question = "Why is the burn decision undecided?"
    run_turn(scenario, af, [], [{"role": "user", "content": question}],
             scenario_dir=SCENARIO_DIR, client=RetryingClient(client, attempts=2))
    assert client.requests[0]["system"] == build_system_prompt(
        scenario, af, [], scenario_dir=SCENARIO_DIR, query=question,
    )


@pytest.mark.parametrize("model", ["claude-sonnet-5", "claude-opus-5", "gpt-5.6-terra"])
def test_guidance_uses_catalog_identity_for_funded_and_byok_clients(model):
    client = CapturingClient(model)
    byok = RetryingClient(client, attempts=2)
    funded = FailoverClient(byok, None, cooldown_seconds=0)
    recorded = SimpleNamespace(inner=funded, model="deployment-name")
    expected = model_prompt_guidance(client, "chat")
    assert expected
    assert model_prompt_guidance(byok, "chat") == expected
    assert model_prompt_guidance(recorded, "chat") == expected
    assert model_prompt_guidance(recorded, "propose") == ""
    assert model_prompt_guidance(recorded, "review") == ""
    scenario = load_bundled_scenario("fire_prevention")
    af = compute_state_bundle(scenario)["af"]
    run_turn(scenario, af, [], [{"role": "user", "content": "Explain."}],
             scenario_dir=SCENARIO_DIR, client=funded)
    assert client.requests[0]["system"] == build_system_prompt(
        scenario, af, [], scenario_dir=SCENARIO_DIR, query="Explain.",
    ) + expected


def test_temporarily_unavailable_primary_keeps_same_model_guidance():
    backup = CapturingClient("claude-opus-5")
    primary = SimpleNamespace(model="claude-opus-5")
    funded = FailoverClient(primary, backup, cooldown_seconds=0)
    assert model_prompt_guidance(funded, "chat") == model_prompt_guidance(backup, "chat")


def test_unknown_client_and_cyclic_wrapper_do_not_acquire_guidance():
    wrapper = SimpleNamespace(model="custom-model")
    wrapper.inner = wrapper
    assert model_prompt_guidance(wrapper, "chat") == ""
    assert model_prompt_guidance(object(), "chat") == ""
