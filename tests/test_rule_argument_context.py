"""Keep configured rules distinct from the arguments that determine chat results."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.llm.chat_service import _format_labels, build_state_block, build_system_prompt
from app.llm.edit_service import build_proposer_system_prompt, build_reviewer_system_prompt
from app.scenario.catalog import EXAMPLES_ROOT, load_bundled_scenario
from app.scenario.serialize import scenario_to_dict
from app.scenario.state import compute_state_bundle


def _summary(scenario, af):
    return _format_labels(scenario, af, include_rule_argument_status=True)


def _line(block, rule_id):
    return next(line for line in block.splitlines() if line.startswith(f"    - {rule_id} ("))


def test_popov_keeps_rejected_exclusivity_separate_from_accepted_causes():
    scenario = load_bundled_scenario("popov_v_hayashi")
    af = compute_state_bundle(scenario)["af"]
    text = _summary(scenario, af)
    arguments = {a["id"]: a for a in af["arguments"]}
    exclusive = next(a for a in arguments.values() if a["top_rule"] == "strict_poss_exclusive")
    exclusive_line = _line(text, "strict_poss_exclusive")
    assert "strict, configured enabled" in exclusive_line
    assert f"{exclusive['id']} rejected" in exclusive_line
    possession = [a for a in arguments.values() if a["conclusion"] == "popov_has_poss"]
    assert len(possession) == 2
    actual_causes = set()
    for argument in possession:
        causes = [edge["from"] for edge in af["attacks"]
                  if edge["to"] == argument["id"] and arguments[edge["from"]]["label"] == "in"]
        assert len(causes) == 1 and exclusive["id"] not in causes
        actual_causes.add(arguments[causes[0]]["top_rule"])
        assert f"{argument['id']} rejected (accepted defeaters: {causes[0]})" in _line(text, "bb1a")
    assert actual_causes == {"cs3", "cs5"}


def test_inactive_cogent_is_visible_without_becoming_a_current_cause():
    scenario = load_bundled_scenario("medical_ppi")
    scenario.assumptions["ppi_is_panto"].active = True
    af = compute_state_bundle(scenario)["af"]
    text = _summary(scenario, af)
    line = _line(text, "ppi_blocks_cyp2c19")
    cause = next(a for a in af["arguments"] if a["top_rule"] == "panto_spares")
    cardiac = next(a for a in af["arguments"] if a["conclusion"] == "cardiac_risk")
    assert f"{cardiac['id']} rejected (accepted defeaters: {cause['id']})" in line
    assert f"panto_spares [{cause['id']} accepted]" in line
    assert "cogent [no current argument]" in line
    assert "declared undercutters:" in line
    assert not scenario.assumptions["cogent_applies"].active


def test_equal_fire_arguments_stay_undecided_without_collapsing_derivations():
    scenario = load_bundled_scenario("fire_prevention")
    af = compute_state_bundle(scenario)["af"]
    text = _summary(scenario, af)
    decisions = [a for a in af["arguments"] if a["conclusion"].lstrip("-") == "conduct_burn"]
    assert len(decisions) == 4
    for argument in decisions:
        line = _line(text, argument["top_rule"])
        assert f"{argument['id']} undecided" in line
        assert "accepted defeaters:" not in line


def test_same_rule_preserves_accepted_and_rejected_sibling_arguments():
    rule = SimpleNamespace(type="defeasible", active=True, block=1, premises=["input"], conclusion="claim")
    scenario = SimpleNamespace(rules={"renamed_rule": rule}, conclusions={"claim": SimpleNamespace(description="the result")})
    af = {
        "labels_by_proposition": {"claim": "accepted"},
        "arguments": [
            {"id": "left", "top_rule": "renamed_rule", "conclusion": "claim", "label": "in"},
            {"id": "right", "top_rule": "renamed_rule", "conclusion": "claim", "label": "out"},
            {"id": "objection", "top_rule": "other", "conclusion": "-input", "label": "in"},
        ],
        "attacks": [{"from": "objection", "to": "right", "type": "rebut"}],
    }
    line = _line(_summary(scenario, af), "renamed_rule")
    assert "left accepted; right rejected (accepted defeaters: objection)" in line


@pytest.mark.parametrize("active", [True, False])
def test_uninstantiated_rule_stays_visible_with_its_configuration(active):
    rule = SimpleNamespace(type="defeasible", active=active, block=1, premises=["pending"], conclusion="claim")
    scenario = SimpleNamespace(rules={"hypothetical": rule}, conclusions={"claim": SimpleNamespace(description="the result")})
    af = {"arguments": [], "attacks": [], "labels_by_proposition": {"claim": "absent"}}
    line = _line(_summary(scenario, af), "hypothetical")
    assert f"configured {'enabled' if active else 'disabled'}" in line
    assert "pending -> claim; current arguments: no current argument" in line


@pytest.mark.parametrize("premise_kind", ["facts", "assumptions"])
def test_premise_backed_conclusion_does_not_claim_absent_support(premise_kind):
    premise = SimpleNamespace(description="the sensor is ready", active=True)
    scenario = SimpleNamespace(rules={}, conclusions={"sensor": premise}, **{premise_kind: {"sensor": premise}})
    af = {"arguments": [{"id": "sensor_arg", "top_rule": "sensor", "conclusion": "sensor", "label": "in"}],
          "attacks": [], "labels_by_proposition": {"sensor": "accepted"}}
    text = _summary(scenario, af)
    assert "`sensor` (accepted)" in text
    assert "(no rule directly concludes this claim)" in text
    assert "absence of support" not in text
    # The old edit-agent format remains byte-compatible during this chat fix.
    assert "label comes from absence of support" in _format_labels(scenario, af)


def test_only_chat_builder_enables_current_rule_argument_status():
    scenario = load_bundled_scenario("popov_v_hayashi")
    af = compute_state_bundle(scenario)["af"]
    legacy = _format_labels(scenario, af)
    default_state = build_state_block(scenario, af, [])
    assert default_state.startswith(legacy)
    directory = EXAMPLES_ROOT / "popov_v_hayashi"
    chat = build_system_prompt(scenario, af, [], scenario_dir=directory)
    proposer = build_proposer_system_prompt(scenario, af, [], scenario_dir=directory)
    reviewer = build_reviewer_system_prompt(
        scenario, af, [], scenario_dir=directory, user_instruction="Add this hypothetical bridge.",
        proposed_edit={"op": "add-rule", "id": "new_bridge", "rule": {
            "type": "defeasible", "premises": ["popov_preposs_interest"], "conclusion": "popov_legit_claim",
        }},
    )
    assert "### Key conclusions and current arguments" in chat
    assert legacy not in chat
    for text in (proposer, reviewer):
        assert legacy in text
        assert "### Key conclusions and current arguments" not in text


def test_context_formatting_does_not_mutate_rules_labels_or_edges():
    scenario = load_bundled_scenario("medical_ppi")
    scenario.assumptions["ppi_is_panto"].active = True
    af = compute_state_bundle(scenario)["af"]
    before_scenario, before_af = scenario_to_dict(scenario), deepcopy(af)
    text = _summary(scenario, af)
    assert _summary(scenario, af) == text
    assert scenario_to_dict(scenario) == before_scenario
    assert af == before_af
