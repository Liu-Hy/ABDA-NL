"""Duplicate advisories must preserve distinctions in formal rule behavior."""
from __future__ import annotations

from copy import deepcopy

import pytest

from app.llm.client import ToolCallResponse
from app.llm.edit_service import run_review
from app.scenario.diff_ops import apply as apply_ops
from app.scenario.loader import scenario_from_dict
from app.scenario.serialize import scenario_to_dict
from app.scenario.state import compute_state_bundle


class SilentReviewer:
    def tool_call(self, **kwargs):
        assert kwargs["tool"]["name"] == "review_edit"
        return ToolCallResponse(
            tool_name="review_edit", tool_input={"issues": []},
            stop_reason="tool_use", usage={}, latency_ms=1, model="synthetic-reviewer",
        )


def _scenario():
    return scenario_from_dict({
        "title": "Rule duplicate semantics",
        "facts": {"p": {"description": "the premise holds"}},
        "conclusions": {"q": {"description": "the conclusion holds"}},
        "rules": {
            "support": {"type": "defeasible", "premises": ["p"],
                        "conclusion": "q", "block": 2, "active": True},
            "oppose": {"type": "defeasible", "premises": ["p"],
                       "conclusion": "-q", "block": 2, "active": True},
        },
    })


def _review(scenario, rule, *, op="add-rule", rule_id="new_support"):
    return run_review(
        scenario, compute_state_bundle(scenario)["af"], [],
        user_instruction="Use the requested rule type, strength and activity.",
        proposed_edit={"op": op, "id": rule_id, "rule": rule},
        scenario_dir=None, client=SilentReviewer(),
    )


@pytest.mark.parametrize("change,expected_label", [
    ({"type": "strict"}, "accepted"),
    ({"block": 3}, "accepted"),
    ({"block": 1}, "undecided"),
    ({"active": False}, "undecided"),
])
def test_formally_different_rule_is_not_reported_as_duplicate(change, expected_label):
    scenario = _scenario()
    original = scenario_to_dict(scenario)
    proposed = deepcopy(original["rules"]["support"])
    proposed.update(change)
    if proposed["type"] == "strict":
        proposed.pop("active")
    result = _review(scenario, proposed)
    assert result.issues == []
    assert scenario_to_dict(scenario) == original
    applied = apply_ops(scenario, [{"op": "add-rule", "id": "new_support", "rule": proposed}])
    assert compute_state_bundle(applied)["af"]["labels_by_proposition"]["q"] == expected_label


def test_omitted_strength_uses_default_instead_of_existing_rule_strength():
    scenario = _scenario()
    proposed = {"type": "defeasible", "premises": ["p"], "conclusion": "q"}
    assert _review(scenario, proposed).issues == []


def test_inactive_existing_rule_is_not_duplicate_of_requested_active_rule():
    scenario = _scenario()
    scenario.rules["support"].active = False
    proposed = {"type": "defeasible", "premises": ["p"], "conclusion": "q", "block": 2}
    assert compute_state_bundle(scenario)["af"]["labels_by_proposition"]["q"] == "rejected"
    assert _review(scenario, proposed).issues == []
    applied = apply_ops(scenario, [{"op": "add-rule", "id": "new_support", "rule": proposed}])
    assert compute_state_bundle(applied)["af"]["labels_by_proposition"]["q"] == "undecided"


@pytest.mark.parametrize("defaults_omitted", [False, True])
def test_actual_duplicate_still_gets_one_advisory(defaults_omitted):
    scenario = _scenario()
    scenario.rules["support"].block = 1
    proposed = {"type": "defeasible", "premises": ["p"], "conclusion": "q"}
    if not defaults_omitted:
        proposed.update(block=1, active=True)
    result = _review(scenario, proposed)
    assert len(result.issues) == 1
    assert result.issues[0].severity == "note"
    assert "duplicates an existing rule" in result.issues[0].message


def test_modifying_only_metadata_does_not_duplicate_itself():
    scenario = _scenario()
    proposed = scenario_to_dict(scenario)["rules"]["support"] | {"source": "revised source"}
    assert _review(scenario, proposed, op="modify-rule", rule_id="support").issues == []
