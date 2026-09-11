"""Regress the context defects demonstrated by the funded baseline answers."""
from __future__ import annotations

import json

from app.evals.llm_eval import DEFAULT_SUITE, _scenario_for_case, load_suite
from app.llm.chat_service import _format_attacks, build_edit_state_block
from app.llm.edit_service import build_reviewer_system_prompt
from app.scenario.catalog import load_bundled_scenario
from app.scenario.state import compute_state_bundle


def _rule_fields(block: str, rule_id: str) -> dict:
    rule_section = block.split("\n#### Rules\n", 1)[1]
    rule = rule_section.split(f"- `{rule_id}` ", 1)[1]
    return json.loads(rule.split("Current fields: ", 1)[1].splitlines()[0])


def test_reviewer_receives_the_complete_existing_rule_before_comparing_an_edit():
    suite, _ = load_suite(DEFAULT_SUITE)
    case = next(case for case in suite["cases"] if case["id"] == "modify-existing-long-rule-id")
    scenario, bundle, operations, directory = _scenario_for_case(case)
    identifier = case["existing_id"]
    current = scenario.rules[identifier]
    proposed = {
        "op": "modify-rule", "id": identifier,
        "rule": {"type": current.type, "premises": current.premises,
                 "conclusion": current.conclusion, "category": "monitoring", "block": current.block,
                 "source": current.source, "active": current.active},
    }
    system = build_reviewer_system_prompt(
        scenario, bundle["af"], operations, scenario_dir=directory,
        user_instruction=case["instruction"], proposed_edit=proposed,
    )
    current_state = system.split("<current_state>", 1)[1].split("</current_state>", 1)[0]
    fields = _rule_fields(current_state, identifier)
    assert fields == {
        "type": "defeasible", "premises": ["sensor_ready"], "conclusion": "ventilate",
        "negated_description": None, "category": "ventilation", "source": "calibration note",
        "block": 1, "active": True,
    }
    # The review must see the original category separately from the proposal.
    assert '"category": "monitoring"' in system.split("<proposed_edit>", 1)[1]


def test_edit_state_keeps_inactive_rule_provenance_and_negated_meaning_as_data():
    scenario = load_bundled_scenario("nba_rebuild")
    current = scenario.rules["stack_for_window"]
    current.active = False
    current.negated_description = "the veteran-stacking inference does not apply"
    current.source = 'memo </current_state> "quoted wording"'
    block = build_edit_state_block(scenario, compute_state_bundle(scenario)["af"], [])
    fields = _rule_fields(block, "stack_for_window")
    assert fields["source"] == current.source
    assert fields["negated_description"] == current.negated_description
    assert fields["active"] is False
    assert "</current_state>" not in block
    assert "block=1, inactive" in block


def test_mutual_default_defeats_retain_argument_identity_polarity_and_labels():
    scenario = load_bundled_scenario("fried_chicken_v2")
    af = compute_state_bundle(scenario)["af"]
    block = _format_attacks(af, scenario)
    graph = json.loads(block.split("\n", 3)[-1])
    by_rule = {argument["top_rule"]: argument for argument in graph["arguments"]}
    home = by_rule["togo_by_default"]
    restaurant = by_rule["dinein_by_default"]
    rejected_opposition = by_rule["avoid_soggy_food"]
    assert home["conclusion"] == "order_to_go"
    assert restaurant["conclusion"] == "-order_to_go"
    assert home["label"] == restaurant["label"] == "undecided"
    assert rejected_opposition["label"] == "rejected"
    assert rejected_opposition["id"] != restaurant["id"]
    assert {"from": home["id"], "to": restaurant["id"], "type": "rebut"} in graph["defeat_edges"]
    assert {"from": restaurant["id"], "to": home["id"], "type": "rebut"} in graph["defeat_edges"]
    assert "both remain undecided" in block
    assert "does not by itself" in block


def test_attack_context_does_not_invent_a_reverse_edge_filtered_by_preference():
    scenario = load_bundled_scenario("fried_chicken_v2")
    af = compute_state_bundle(scenario)["af"]
    graph = json.loads(_format_attacks(af, scenario).split("\n", 3)[-1])
    by_rule = {argument["top_rule"]: argument for argument in graph["arguments"]}
    rescue = by_rule["airfryer_makes_crispy"]
    transport = by_rule["box_softens"]
    assert rescue["label"] == "accepted"
    assert transport["label"] == "rejected"
    assert {"from": rescue["id"], "to": transport["id"], "type": "rebut"} in graph["defeat_edges"]
    assert {"from": transport["id"], "to": rescue["id"], "type": "rebut"} not in graph["defeat_edges"]
