"""Preserve valid edit semantics while reporting malformed fields precisely."""
from copy import deepcopy

import pytest

from app.llm.edit_schemas import diff_op_from_tool_input
from app.llm.edit_validator import validate_op
from app.scenario.catalog import load_bundled_scenario
from app.scenario.diff_ops import DiffOpError, apply
from app.scenario.state import compute_state_bundle


def test_explicit_active_strict_rule_has_the_same_engine_meaning_as_omission():
    baseline = load_bundled_scenario("fried_chicken_v2")
    baseline = apply(baseline, [{"op": "toggle-assumption", "id": "have_airfryer"}])
    operation = {
        "op": "add-rule", "id": "soggy_prevents_togo",
        "rule": {"type": "strict", "premises": ["-crispy"],
                 "conclusion": "-order_to_go", "category": "ordering", "block": 1},
    }
    explicit = deepcopy(operation)
    explicit["rule"]["active"] = True
    implicit_result, explicit_result = apply(baseline, [operation]), apply(baseline, [explicit])
    assert implicit_result.rules == explicit_result.rules
    assert explicit_result.rules[operation["id"]].active is True
    assert compute_state_bundle(implicit_result) == compute_state_bundle(explicit_result)
    assert not any(issue.severity == "blocking" for issue in validate_op(explicit, baseline))


@pytest.mark.parametrize("active", [False, None, "true", 1])
def test_invalid_strict_activation_is_not_coerced_and_feedback_names_the_field(active):
    baseline = load_bundled_scenario("fried_chicken_v2")
    operation = {
        "op": "add-rule", "id": "strict_check",
        "rule": {"type": "strict", "premises": ["-crispy"],
                 "conclusion": "-order_to_go", "active": active},
    }
    with pytest.raises(DiffOpError, match="/rule/active"):
        apply(baseline, [operation])
    messages = [issue.message for issue in validate_op(operation, baseline)]
    assert any("/rule/active" in message for message in messages)
    assert all("sibling" not in message for message in messages)


def test_only_optional_null_text_is_omitted_without_changing_the_provider_payload():
    payload = {
        "id": "added_rule", "rule": {
            "type": "defeasible", "premises": ["want_chicken"], "conclusion": "order_to_go",
            "negated_description": None, "source": None, "category": None,
        },
    }
    original = deepcopy(payload)
    operation = diff_op_from_tool_input("add-rule", payload)
    assert payload == original
    assert operation["rule"] == {
        "type": "defeasible", "premises": ["want_chicken"], "conclusion": "order_to_go",
    }
    baseline = load_bundled_scenario("fried_chicken_v2")
    assert "added_rule" in apply(baseline, [operation]).rules


@pytest.mark.parametrize("field,value", [
    ("type", None), ("premises", None), ("conclusion", None),
    ("active", None), ("block", None), ("unknown", None), ("source", False),
])
def test_optional_null_compatibility_does_not_hide_other_invalid_values(field, value):
    payload = {
        "id": "invalid_rule", "rule": {
            "type": "defeasible", "premises": ["want_chicken"], "conclusion": "order_to_go",
            field: value,
        },
    }
    operation = diff_op_from_tool_input("add-rule", payload)
    assert field in operation["rule"] and operation["rule"][field] is value
    with pytest.raises(DiffOpError):
        apply(load_bundled_scenario("fried_chicken_v2"), [operation])


def test_null_metadata_on_a_replacement_rule_requires_explicit_correction():
    baseline = load_bundled_scenario("fried_chicken_v2")
    original = baseline.rules["box_softens"]
    payload = {
        "id": original.id, "rule": {
            "type": original.type, "premises": original.premises,
            "conclusion": original.conclusion, "source": None,
        },
    }
    operation = diff_op_from_tool_input("modify-rule", payload)
    assert "source" in operation["rule"] and operation["rule"]["source"] is None
    with pytest.raises(DiffOpError, match="/rule/source"):
        apply(baseline, [operation])
    assert baseline.rules[original.id] == original
