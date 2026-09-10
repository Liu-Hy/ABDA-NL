"""Replay malformed provider envelopes through real validation and billing."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, LLMUsageEvent
from app.llm.catalog import load_model_catalog
from app.llm.client import ToolCallResponse
from app.llm.edit_schemas import diff_op_from_tool_input, notes_from_tool_input
from app.llm.edit_service import ProposerRetryExhausted, run_propose
from app.llm.edit_validator import validate_op
from app.llm.routing import CallContext, CircuitRegistry, FailoverClient, LocalSpendCap, MeteredClient
from app.scenario.diff_ops import apply as apply_ops
from app.scenario.loader import load_scenario, scenario_from_dict
from app.scenario.serialize import scenario_to_dict
from app.scenario.state import compute_state_bundle


_FACT = {
    "category": "ventilation", "description": "outdoor air is safe for greenhouse ventilation",
    "source": "user instruction",
}
# Exact envelope shape observed in Sonnet's pending-reference failure.
_NESTED_ID = {"fact": {"id": "outdoor_safe", **_FACT}}
_VALID_FACT = {"id": "outdoor_safe", "fact": _FACT}
_USAGE = {"input_tokens": 11, "output_tokens": 7,
          "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}


@pytest.fixture
def greenhouse():
    return scenario_from_dict({
        "title": "Envelope replay", "facts": {"sensor_ready": {"description": "sensor is calibrated"}},
        "assumptions": {"window_open": {"description": "window is open", "active": True, "block": 1}},
        "propositions": {"outdoor_safe": {"description": _FACT["description"]}},
        "conclusions": {"ventilate": {"description": "ventilate the greenhouse"}},
        "rules": {"open_vent": {"type": "defeasible", "premises": ["window_open", "outdoor_safe"],
                                "conclusion": "ventilate", "block": 1}},
        "corpus": [],
    })


class RecordedProvider:
    model = "claude-sonnet-5"
    provider = "azure-foundry"
    billing_source = "cloudbank"
    route = "synthetic-envelope"

    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.calls = []

    def tool_call(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        name = kwargs["tool"]["name"]
        payload = {"issues": []} if name == "review_edit" else next(self.payloads)
        return ToolCallResponse(
            tool_name=name, tool_input=deepcopy(payload), stop_reason="tool_use",
            usage=dict(_USAGE), latency_ms=3, model=self.model, provider=self.provider,
            billing_source=self.billing_source, route=self.route,
        )


class UnusedFallback:
    calls = 0

    def tool_call(self, **_kwargs):
        self.calls += 1
        raise AssertionError("an application validation failure must not use OpenRouter")


@pytest.fixture
def billed_provider(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'billing.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def build(payloads):
        raw = RecordedProvider(payloads)
        cap = LocalSpendCap(1_000_000)
        metered = MeteredClient(
            raw, model_spec=load_model_catalog().models[raw.model],
            context=CallContext(user_id=None, request_id="envelope-test", request_kind="propose", charge_trial=False),
            charge_emergency=False, spend_cap=cap, session_factory=factory,
        )
        fallback = UnusedFallback()
        client = FailoverClient(metered, fallback, cooldown_seconds=60,
                                circuits=CircuitRegistry(), primary_verified=True)
        return client, raw, fallback, cap, factory

    yield build
    engine.dispose()


def _propose(scenario, client, *, task="add-fact"):
    return run_propose(
        scenario, compute_state_bundle(scenario)["af"], [], task=task,
        instruction="Add the outdoor-safe fact using the existing outdoor_safe identifier.",
        scenario_dir=None, client=client,
    )


def _assert_billed(factory, cap, count):
    expected = load_model_catalog().models[RecordedProvider.model].cost_microusd(_USAGE) * count
    with factory() as session:
        events = list(session.scalars(select(LLMUsageEvent)))
        assert len(events) == count
        assert all(event.provider == "azure-foundry" and event.status == "succeeded" for event in events)
        assert sum(event.input_tokens for event in events) == _USAGE["input_tokens"] * count
        assert sum(event.output_tokens for event in events) == _USAGE["output_tokens"] * count
        assert sum(event.cost_microusd for event in events) == expected
    assert cap.spent_microusd == expected
    assert cap.reserved_microusd == 0
    return expected


def test_observed_nested_id_retries_and_only_valid_result_can_be_applied(greenhouse, billed_provider):
    before = scenario_to_dict(greenhouse)
    client, raw, fallback, cap, factory = billed_provider([_NESTED_ID, _VALID_FACT])
    result = _propose(greenhouse, client)
    assert result.proposer_attempts == 2
    assert result.op == {"op": "add-fact", **_VALID_FACT}
    assert result.usage == {key: value * 2 for key, value in _USAGE.items()}
    assert result.cost_microusd == _assert_billed(factory, cap, 2)
    assert "failed deterministic validation" in raw.calls[1]["messages"][0]["content"]
    assert "Additional properties" in raw.calls[1]["messages"][0]["content"]
    assert scenario_to_dict(greenhouse) == before
    assert "outdoor_safe" not in greenhouse.facts
    applied = apply_ops(greenhouse, [result.op])
    assert "outdoor_safe" in applied.facts
    assert compute_state_bundle(applied)["af"]["labels_by_proposition"]["ventilate"] == "accepted"
    assert fallback.calls == 0


def test_nested_id_exhaustion_stops_after_three_charged_attempts(greenhouse, billed_provider):
    before = scenario_to_dict(greenhouse)
    client, raw, fallback, cap, factory = billed_provider([_NESTED_ID] * 3)
    with pytest.raises(ProposerRetryExhausted) as caught:
        _propose(greenhouse, client)
    assert caught.value.attempts == 3
    assert caught.value.last_issues
    assert len(raw.calls) == 3
    _assert_billed(factory, cap, 3)
    assert scenario_to_dict(greenhouse) == before
    assert fallback.calls == 0


def test_observed_rule_id_and_premise_collision_retries_then_materializes(billed_provider):
    scenario_dir = Path(__file__).resolve().parents[1] / "examples/fried_chicken_v2"
    scenario = load_scenario(scenario_dir / "scenario.yaml")
    original = scenario_to_dict(scenario)
    # Exact Opus payload from the stopped qualification run.
    collided = {
        "id": "dinein_open",
        "new_premise_notes": [{"id": "dinein_open", "description":
                               "the restaurant is open for dine-in service at the time of the meal"}],
        "rule": {
            "active": True, "block": 1, "category": "ordering", "conclusion": "-order_to_go",
            "negated_description": "the open-dining-room-to-dine-in inference does not apply here",
            "premises": ["dinein_open"], "source": "user instruction", "type": "defeasible",
        },
    }
    corrected = deepcopy(collided)
    corrected["id"] = "dinein_if_open"
    client, raw, fallback, cap, factory = billed_provider([collided, corrected])
    result = run_propose(
        scenario, compute_state_bundle(scenario)["af"], [], task="add-rule",
        instruction="Add a defeasible rule saying that if the restaurant is open for dine-in, "
                    "then dining in is preferred instead of ordering to-go.",
        scenario_dir=scenario_dir, client=client,
    )
    assert result.proposer_attempts == 2
    assert result.op["id"] == "dinein_if_open"
    assert result.op["rule"]["premises"] == ["dinein_open"]
    assert "Choose a distinct rule id" in raw.calls[1]["messages"][0]["content"]
    assert result.usage == {key: value * 3 for key, value in _USAGE.items()}
    assert result.cost_microusd == _assert_billed(factory, cap, 3)
    assert scenario_to_dict(scenario) == original
    assert fallback.calls == 0

    pending = apply_ops(scenario, [result.op])
    assert "dinein_open" in pending.propositions
    fact = {"op": "add-fact", "id": "dinein_open", "fact": {
        "description": "the restaurant is open for dine-in service at the time of the meal",
        "source": "user instruction",
    }}
    assert validate_op(fact, pending) == []
    materialized = apply_ops(pending, [fact])
    assert "dinein_open" in materialized.facts
    assert "dinein_open" not in materialized.propositions
    assert "dinein_if_open" in materialized.rules
    assert compute_state_bundle(materialized)["af"]["labels_by_proposition"]["dinein_open"] == "accepted"


@pytest.mark.parametrize("literal", ["dinein_open", "-dinein_open"])
def test_new_rule_id_cannot_reserve_its_own_pending_premise(greenhouse, literal):
    op = {"op": "add-rule", "id": "dinein_open", "rule": {
        "type": "defeasible", "premises": [literal], "conclusion": "ventilate",
    }}
    issues = validate_op(op, greenhouse)
    assert [(issue.code, issue.severity) for issue in issues] == [
        ("premise_rule_id_collision", "blocking")
    ]


@pytest.mark.parametrize("premise,conclusion", [
    ("-open_vent", "ventilate"), ("window_open", "-open_vent"),
])
def test_existing_rule_name_undercut_references_stay_valid(greenhouse, premise, conclusion):
    op = {"op": "add-rule", "id": "review_vent", "rule": {
        "type": "defeasible", "premises": [premise], "conclusion": conclusion,
    }}
    assert validate_op(op, greenhouse) == []


def test_existing_rule_reference_on_modify_keeps_established_semantics(greenhouse):
    op = {"op": "modify-rule", "id": "open_vent", "rule": {
        "type": "defeasible", "premises": ["-open_vent"], "conclusion": "ventilate",
    }}
    assert validate_op(op, greenhouse) == []


@pytest.mark.parametrize("task,payload", [
    ("add-rule", "rule"), ("modify-rule", "rule"),
    ("add-fact", "fact"), ("add-assumption", "assumption"),
])
def test_missing_payload_reaches_structural_validation(greenhouse, task, payload):
    candidate = diff_op_from_tool_input(task, {"id": "fresh"})
    assert candidate[payload] is None
    assert [issue.code for issue in validate_op(candidate, greenhouse)] == ["missing_payload"]


@pytest.mark.parametrize("malformed", [None, False, 0, "", "notes", {}])
def test_invalid_notes_container_is_not_silently_dropped(malformed):
    with pytest.raises(ValueError, match="must be an array"):
        notes_from_tool_input("add-rule", {"new_premise_notes": malformed})


def test_malformed_notes_use_the_same_bounded_correction_loop(greenhouse, billed_provider):
    rule = {"id": "new_vent", "rule": {"type": "defeasible", "premises": ["sensor_ready"],
                                       "conclusion": "ventilate", "block": 1}}
    client, raw, fallback, cap, factory = billed_provider([
        {**rule, "new_premise_notes": 42}, {**rule, "new_premise_notes": []},
    ])
    before = scenario_to_dict(greenhouse)
    result = _propose(greenhouse, client, task="add-rule")
    assert result.proposer_attempts == 2
    assert "new_premise_notes must be an array" in raw.calls[1]["messages"][0]["content"]
    assert result.op == {"op": "add-rule", **rule}
    assert result.cost_microusd == _assert_billed(factory, cap, 3)
    assert result.usage == {key: value * 3 for key, value in _USAGE.items()}
    assert scenario_to_dict(greenhouse) == before
    assert fallback.calls == 0
