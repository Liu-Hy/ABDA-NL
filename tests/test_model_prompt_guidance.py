"""Keep observed prompt corrections scoped through actual routing wrappers."""
from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import pytest

from app.llm.catalog import load_model_catalog
from app.llm.chat_service import build_system_prompt, run_turn
from app.llm.client import LLMResponse, ToolCallResponse
from app.llm.edit_service import (
    build_proposer_system_prompt, build_reviewer_system_prompt, run_propose,
)
from app.llm.prompts import model_prompt_guidance, model_prompt_templates
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

    def tool_call(self, **kwargs):
        self.requests.append(kwargs)
        name = kwargs["tool"]["name"]
        payload = {"issues": []} if name == "review_edit" else {
            "id": "fuel_support", "rule": {
                "type": "defeasible", "premises": ["heavy_fuels"], "conclusion": "conduct_burn",
            },
        }
        return ToolCallResponse(
            tool_name=name, tool_input=payload, stop_reason="tool_use",
            usage={"input_tokens": 1, "output_tokens": 1}, latency_ms=1, model=self.model,
        )


@pytest.mark.parametrize("model", [
    "gpt-5.6-sol", "gemini-3.1-pro-preview",
    "gemini-3.8-flash", "glm-5.3", "kimi-k3",
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


@pytest.mark.parametrize("model", [
    "claude-sonnet-5", "claude-opus-5", "gpt-5.6-terra", "deepseek-v4-flash-0731",
])
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
        include_accepted_defeaters="chat_accepted_defeaters" in model_prompt_templates(client, "chat"),
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


@pytest.mark.parametrize("model,proposer_changed,reviewer_changed", [
    ("claude-sonnet-5", True, True),
    ("deepseek-v4-flash-0731", True, True),
    ("glm-5.3", True, False),
    ("kimi-k3", True, False),
    ("claude-opus-5", False, False),
    ("gpt-5.6-terra", False, False),
    ("gpt-5.6-sol", False, False),
    ("gemini-3.1-pro-preview", False, False),
    ("gemini-3.8-flash", False, False),
])
def test_actual_edit_pipeline_keeps_guidance_scoped_to_observed_model_and_feature(
    model, proposer_changed, reviewer_changed,
):
    scenario = load_bundled_scenario("fire_prevention")
    af = compute_state_bundle(scenario)["af"]
    client = CapturingClient(model)
    wrapped = FailoverClient(RetryingClient(client, attempts=2), None, cooldown_seconds=0)
    instruction = "Add a rule that heavy fuels support conducting a burn."
    result = run_propose(
        scenario, af, [], task="add-rule", instruction=instruction,
        scenario_dir=SCENARIO_DIR, client=wrapped,
    )
    assert result.reviewed and len(client.requests) == 2
    bases = (
        build_proposer_system_prompt(scenario, af, [], scenario_dir=SCENARIO_DIR, query=instruction),
        build_reviewer_system_prompt(
            scenario, af, [], scenario_dir=SCENARIO_DIR,
            user_instruction=instruction, proposed_edit=result.op,
        ),
    )
    for request, base, feature, changed in zip(
        client.requests, bases, ("proposer", "reviewer"), (proposer_changed, reviewer_changed),
        strict=True,
    ):
        guidance = model_prompt_guidance(wrapped, feature)
        assert bool(guidance) is changed
        assert request["system"] == base + guidance
