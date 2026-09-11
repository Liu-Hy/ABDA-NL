"""Behavioral contracts for the September 10 scenario reconstruction.

These expectations are authored from the proposal's decision tables before
updating the scenario files or their generated label snapshots.
"""
from itertools import product

import pytest

from app.scenario.catalog import load_bundled_scenario
from app.scenario.diff_ops import apply
from app.scenario.state import compute_state_bundle


def _toggle(identifier):
    return {"op": "toggle-assumption", "id": identifier}


def _prefer(winner, loser, scenario_id):
    baseline = load_bundled_scenario(scenario_id)
    block = max(baseline.rules[winner].block, baseline.rules[loser].block) + 1
    return {"op": "set-block", "target": "rule", "id": winner, "block": block}


def _state(scenario_id, toggles=(), preference=None, blocks=()):
    baseline = load_bundled_scenario(scenario_id)
    ops = [_toggle(identifier) for identifier in toggles]
    if preference:
        ops.append(_prefer(*preference, scenario_id))
    ops.extend({"op": "set-block", "target": "rule", "id": key, "block": value}
               for key, value in blocks)
    return compute_state_bundle(apply(baseline, ops))["af"]


@pytest.mark.parametrize("toggles,preference,expected", [
    ((), None, ("accepted", "accepted", "undecided", "undecided", "accepted", "accepted")),
    (("cogent_decisive",), None, ("accepted", "rejected", "accepted", "rejected", "accepted", "accepted")),
    (("pantoprazole_contraindicated",), None, ("accepted", "accepted", "undecided", "rejected", "accepted", "accepted")),
    ((), ("avoid_interaction", "keep_current"), ("accepted", "accepted", "rejected", "accepted", "accepted", "accepted")),
    ((), ("keep_current", "avoid_interaction"), ("accepted", "accepted", "accepted", "rejected", "accepted", "accepted")),
    (("pantoprazole_contraindicated",), ("avoid_interaction", "keep_current"), ("accepted", "accepted", "rejected", "rejected", "accepted", "accepted")),
])
def test_ppi_decision_table(toggles, preference, expected):
    labels = _state("medical_ppi", toggles, preference)["labels_by_proposition"]
    columns = ("continue_acid_suppression", "cardiac_interaction", "keep_omeprazole",
               "switch_to_pantoprazole", "reassess_dose", "escalate")
    assert tuple(labels[column] for column in columns) == expected
    assert labels["be_indication"] == labels["fracture_risk"] == "accepted"


@pytest.mark.parametrize("toggles,preference,blocks,expected", [
    ((), None, (), ("undecided", "accepted", "accepted", "undecided")),
    (("forecast_exceedance",), None, (), ("undecided", "accepted", "rejected", "rejected")),
    (("recent_burn",), None, (), ("undecided", "rejected", "accepted", "undecided")),
    (("permit_window_open",), None, (), ("undecided", "accepted", "absent", "absent")),
    ((), ("treat_for_ecology", "no_treatment_for_smoke"), (), ("accepted", "accepted", "accepted", "accepted")),
    ((), ("treat_for_culture", "no_treatment_for_smoke"), (), ("accepted", "accepted", "accepted", "accepted")),
    ((), ("no_treatment_for_smoke", "treat_for_ecology"), (), ("rejected", "accepted", "accepted", "rejected")),
    (("recent_burn",), ("treat_for_ecology", "no_treatment_for_smoke"), (), ("undecided", "rejected", "accepted", "undecided")),
    (("forecast_exceedance",), ("treat_for_ecology", "no_treatment_for_smoke"), (), ("accepted", "accepted", "rejected", "rejected")),
    (("permit_window_open",), ("treat_for_ecology", "no_treatment_for_smoke"), (), ("accepted", "accepted", "absent", "absent")),
    (("forecast_exceedance",), None, (("treat_for_ecology", 4),), ("accepted", "accepted", "rejected", "rejected")),
])
def test_burn_decision_table(toggles, preference, blocks, expected):
    labels = _state("fire_prevention", toggles, preference, blocks)["labels_by_proposition"]
    columns = ("treat_unit", "eco_benefit", "burn_permitted", "burn_today")
    assert tuple(labels[column] for column in columns) == expected
    assert labels["elevated_risk"] == labels["good_fire"] == labels["smoke_harm"] == "accepted"


def test_recent_burn_teaching_sequence_preserves_independent_cultural_support():
    original = load_bundled_scenario("fire_prevention")
    preferred = apply(original, [
        _prefer("treat_for_ecology", "no_treatment_for_smoke", "fire_prevention"),
    ])
    assert compute_state_bundle(preferred)["af"]["labels_by_proposition"]["treat_unit"] == "accepted"
    changed = apply(preferred, [_toggle("recent_burn")])
    labels = compute_state_bundle(changed)["af"]["labels_by_proposition"]
    assert labels["eco_benefit"] == "rejected"
    assert labels["good_fire"] == "accepted"
    assert labels["treat_unit"] == labels["burn_today"] == "undecided"
    assert original.rules["treat_for_ecology"].block == 1
    assert original.assumptions["recent_burn"].active is False


@pytest.mark.parametrize("toggles,preference,expected", [
    ((), None, ("rejected", "rejected", "accepted")),
    (("expansion_pending",), None, ("undecided", "rejected", "undecided")),
    (("expansion_pending",), ("tank_for_scarcity", "no_tank_for_development"), ("accepted", "rejected", "rejected")),
    (("expansion_pending",), ("no_tank_for_development", "tank_for_scarcity"), ("rejected", "rejected", "accepted")),
    (("deal_fits_under_apron",), None, ("rejected", "rejected", "accepted")),
    (("deal_fits_under_apron",), ("stack_for_window", "preserve_flexibility"), ("rejected", "accepted", "accepted")),
    ((), ("stack_for_window", "preserve_flexibility"), ("rejected", "rejected", "accepted")),
    ((), ("tank_for_odds", "no_tank_for_development"), ("rejected", "rejected", "accepted")),
])
def test_nba_decision_table(toggles, preference, expected):
    labels = _state("nba_rebuild", toggles, preference)["labels_by_proposition"]
    assert tuple(labels[column] for column in ("tank", "stack_vets", "compete")) == expected
    assert labels["classic_fit"] == "rejected"
    assert labels["high_pick_valuable"] == labels["dev_first"] == "accepted"
    assert labels["talent_dilution"] == ("accepted" if "expansion_pending" in toggles else "absent")


@pytest.mark.parametrize("cogent,contraindicated,preferred", tuple(product(
    (False, True), (False, True), (None, "keep_current", "avoid_interaction"),
)))
def test_ppi_combined_changes_preserve_acid_suppression(cogent, contraindicated, preferred):
    toggles = [name for name, active in (("cogent_decisive", cogent),
               ("pantoprazole_contraindicated", contraindicated)) if active]
    blocks = ((preferred, 3),) if preferred else ()
    labels = _state("medical_ppi", toggles, blocks=blocks)["labels_by_proposition"]
    assert labels["continue_acid_suppression"] == labels["reassess_dose"] == "accepted"
    assert not (labels["keep_omeprazole"] == labels["switch_to_pantoprazole"] == "accepted")
    if cogent:
        assert labels["cardiac_interaction"] == "rejected"
        assert labels["keep_omeprazole"] == "accepted"
    if contraindicated:
        assert labels["switch_to_pantoprazole"] == "rejected"


@pytest.mark.parametrize("permit,exceedance,recent,preferred", tuple(product(
    (False, True), (False, True), (False, True),
    (None, "treat_for_ecology", "treat_for_culture", "no_treatment_for_smoke"),
)))
def test_burn_day_always_needs_permission(permit, exceedance, recent, preferred):
    toggles = [name for name, changed in (("permit_window_open", not permit),
               ("forecast_exceedance", exceedance), ("recent_burn", recent)) if changed]
    blocks = ((preferred, 4),) if preferred else ()
    af = _state("fire_prevention", toggles, blocks=blocks)
    labels = af["labels_by_proposition"]
    if not permit:
        assert labels["burn_today"] == "absent"
        assert not any(arg["conclusion"] == "burn_today" for arg in af["arguments"])
    if exceedance:
        assert labels["burn_permitted"] == "rejected"
        assert labels["burn_today"] != "accepted"
    if labels["burn_today"] == "accepted":
        assert labels["burn_permitted"] == labels["treat_unit"] == "accepted"
    if recent:
        assert labels["eco_benefit"] == "rejected"
        assert labels["good_fire"] == "accepted"


@pytest.mark.parametrize("deal,expansion,preferred", tuple(product(
    (False, True), (False, True),
    (None, "tank_for_scarcity", "tank_for_odds", "no_tank_for_development", "stack_for_window"),
)))
def test_nba_exclusivity_and_deal_applicability_survive_preferences(deal, expansion, preferred):
    toggles = [name for name, active in (("deal_fits_under_apron", deal),
               ("expansion_pending", expansion)) if active]
    blocks = ((preferred, 5),) if preferred else ()
    af = _state("nba_rebuild", toggles, blocks=blocks)
    labels = af["labels_by_proposition"]
    assert not (labels["tank"] == labels["compete"] == "accepted")
    assert labels["high_pick_valuable"] == "accepted"
    if not deal:
        assert labels["stack_vets"] == "rejected"
        assert not any(arg["conclusion"] == "stack_vets" for arg in af["arguments"])
    if not expansion:
        assert labels["tank"] == "rejected"


@pytest.mark.parametrize("scenario_id,arguments,attacks", [
    ("medical_ppi", 15, 9), ("fire_prevention", 17, 6), ("nba_rebuild", 19, 15),
])
def test_baseline_argument_and_attack_counts(scenario_id, arguments, attacks):
    af = _state(scenario_id)
    assert len(af["arguments"]) == arguments
    assert len(af["attacks"]) == attacks
