"""Ground explanations in accepted incoming attackers, with original edges intact."""
from __future__ import annotations

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from app.llm.chat_service import _format_attacks
from app.llm.prompts import model_prompt_templates
from app.scenario.catalog import load_bundled_scenario
from app.scenario.state import compute_state_bundle


def _graph(af, scenario, *, enriched=True):
    text = _format_attacks(af, scenario, include_accepted_defeaters=enriched)
    return json.loads(text.split("\n", 3)[-1])


def test_rejected_strict_attacker_is_not_the_cause_of_possession_rejection():
    scenario = load_bundled_scenario("popov_v_hayashi")
    af = compute_state_bundle(scenario)["af"]
    before = deepcopy(af)
    graph = _graph(af, scenario)
    arguments = {argument["id"]: argument for argument in graph["arguments"]}
    possession = [a for a in arguments.values() if a["conclusion"] == "popov_has_poss"]
    exclusive = next(a for a in arguments.values() if a["top_rule"] == "strict_poss_exclusive")
    assert exclusive["label"] == "rejected"
    assert len(possession) == 2
    causes = set()
    for argument in possession:
        assert argument["label"] == "rejected"
        assert exclusive["id"] not in argument["accepted_defeaters"]
        assert len(argument["accepted_defeaters"]) == 1
        cause = arguments[argument["accepted_defeaters"][0]]
        assert cause["label"] == "accepted"
        causes.add(cause["top_rule"])
    assert causes == {"cs3", "cs5"}
    assert {arguments[value]["top_rule"] for value in exclusive["accepted_defeaters"]} == {"r5"}
    assert af == before
    assert graph["defeat_edges"] == _graph(af, scenario, enriched=False)["defeat_edges"]


def test_fire_premise_and_postponement_stay_accepted_while_decision_is_undecided():
    scenario = load_bundled_scenario("fire_prevention")
    af = compute_state_bundle(scenario)["af"]
    graph = _graph(af, scenario)
    arguments = graph["arguments"]
    decisions = [a for a in arguments if a["conclusion"].lstrip("-") == "conduct_burn"]
    assert len(decisions) == 4
    assert all(a["label"] == "undecided" and a["accepted_defeaters"] == [] for a in decisions)
    smoke = next(a for a in arguments if a["top_rule"] == "r_airshed")
    postponed = next(a for a in arguments if a["top_rule"] == "r_postpone_smoke")
    assert smoke["label"] == postponed["label"] == "accepted"
    assert smoke["accepted_defeaters"] == postponed["accepted_defeaters"] == []
    opposition = next(a for a in decisions if a["top_rule"] == "r_airshed_con")
    support = [a for a in decisions if a["conclusion"] == "conduct_burn"]
    for argument in support:
        assert {"from": argument["id"], "to": opposition["id"], "type": "rebut"} in graph["defeat_edges"]
        assert {"from": opposition["id"], "to": argument["id"], "type": "rebut"} in graph["defeat_edges"]


def test_preference_filtered_reverse_edge_is_not_an_accepted_defeater():
    scenario = load_bundled_scenario("fried_chicken_v2")
    af = compute_state_bundle(scenario)["af"]
    graph = _graph(af, scenario)
    by_rule = {a["top_rule"]: a for a in graph["arguments"]}
    crispy = by_rule["airfryer_makes_crispy"]
    soggy = by_rule["box_softens"]
    assert crispy["label"] == "accepted" and crispy["accepted_defeaters"] == []
    assert soggy["label"] == "rejected" and soggy["accepted_defeaters"] == [crispy["id"]]
    assert {"from": soggy["id"], "to": crispy["id"], "type": "rebut"} not in graph["defeat_edges"]
    home, restaurant = by_rule["togo_by_default"], by_rule["dinein_by_default"]
    assert home["label"] == restaurant["label"] == "undecided"
    assert home["accepted_defeaters"] == restaurant["accepted_defeaters"] == []
    assert {"from": home["id"], "to": restaurant["id"], "type": "rebut"} in graph["defeat_edges"]
    assert {"from": restaurant["id"], "to": home["id"], "type": "rebut"} in graph["defeat_edges"]


def test_intermediate_premise_uses_full_engine_edges_not_the_filtered_view():
    # This small signed AF separates the key-claim view from an included
    # intermediate argument. Its local defeat edge is absent from that view.
    scenario = SimpleNamespace(conclusions={"claim": object()})
    af = {
        "arguments": [
            {"id": "claim_arg", "conclusion": "claim", "top_rule": "derive_claim",
             "label": "out", "premises": ["premise_arg"], "sub_arguments": ["premise_arg"]},
            {"id": "premise_arg", "conclusion": "premise", "top_rule": "derive_premise",
             "label": "out", "premises": [], "sub_arguments": []},
            {"id": "accepted_objection", "conclusion": "-derive_premise", "top_rule": "objection",
             "label": "in", "premises": [], "sub_arguments": []},
        ],
        "attacks": [
            {"from": "accepted_objection", "to": "premise_arg", "type": "undercut"},
            {"from": "accepted_objection", "to": "claim_arg", "type": "undercut"},
        ],
    }
    graph = _graph(af, scenario)
    arguments = {argument["id"]: argument for argument in graph["arguments"]}
    assert arguments["claim_arg"]["accepted_defeaters"] == ["accepted_objection"]
    assert arguments["premise_arg"]["accepted_defeaters"] == ["accepted_objection"]
    assert {"from": "accepted_objection", "to": "premise_arg", "type": "undercut"} not in graph["defeat_edges"]
    assert graph["defeat_edges"] == _graph(af, scenario, enriched=False)["defeat_edges"]


def test_added_intermediate_defeater_keeps_its_supporting_premise_closure():
    scenario = SimpleNamespace(conclusions={"claim": object()})
    af = {
        "arguments": [
            {"id": "claim_arg", "conclusion": "claim", "label": "out",
             "premises": ["intermediate"], "sub_arguments": ["intermediate"]},
            {"id": "intermediate", "conclusion": "support", "label": "out",
             "premises": [], "sub_arguments": []},
            {"id": "objection", "conclusion": "-support", "label": "in",
             "premises": ["objection_support"], "sub_arguments": ["objection_support"]},
            {"id": "objection_support", "conclusion": "observation", "label": "in",
             "premises": ["recorded_fact"], "sub_arguments": ["recorded_fact"]},
            {"id": "recorded_fact", "conclusion": "record", "label": "in",
             "premises": [], "sub_arguments": []},
        ],
        "attacks": [{"from": "objection", "to": "intermediate", "type": "rebut"}],
    }
    plain = _graph(af, scenario, enriched=False)
    assert {a["id"] for a in plain["arguments"]} == {"claim_arg", "intermediate"}
    enriched = _graph(af, scenario)
    arguments = {a["id"]: a for a in enriched["arguments"]}
    assert arguments["intermediate"]["accepted_defeaters"] == ["objection"]
    assert arguments["objection"]["premise_arguments"] == ["objection_support"]
    assert arguments["objection_support"]["premise_arguments"] == ["recorded_fact"]
    assert set(arguments) == {"claim_arg", "intermediate", "objection", "objection_support", "recorded_fact"}
    assert all(set(a["premise_arguments"]) <= set(arguments) for a in arguments.values())
    assert enriched["defeat_edges"] == plain["defeat_edges"]


@pytest.mark.parametrize("model,features", [
    ("claude-sonnet-5", {"chat", "proposer", "reviewer"}),
    ("deepseek-v4-flash-0731", {"chat", "proposer", "reviewer"}),
    ("glm-5.3", {"chat", "proposer"}),
    ("kimi-k3", {"proposer"}),
    ("gpt-5.6-sol", set()),
    ("gemini-3.8-flash", set()),
])
def test_template_selection_is_the_single_scope_for_observed_model_features(model, features):
    client = SimpleNamespace(model_spec=SimpleNamespace(id=model))
    for feature in ("chat", "proposer", "reviewer"):
        templates = model_prompt_templates(client, feature)
        assert bool(templates) is (feature in features)
    if model == "deepseek-v4-flash-0731":
        assert model_prompt_templates(client, "proposer") == ("proposer_deepseek_provenance",)
        assert model_prompt_templates(client, "reviewer") == ("reviewer_deepseek_polarity",)
