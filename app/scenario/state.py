"""Compile an authored scenario into the API state bundle."""
from __future__ import annotations

from typing import Any

from app.abda_bridge import ArgumentationGraph, build_arguments, build_attacks
from app.scenario.loader import scenario_to_rule_collection
from app.scenario.serialize import scenario_to_dict, serialize_af


def compute_state_bundle(scenario) -> dict[str, Any]:
    rules = scenario_to_rule_collection(scenario)
    arguments = build_arguments(rules.get_all_rules())
    attacks = build_attacks(arguments)
    graph = ArgumentationGraph(arguments, attacks)
    labelling = graph.get_grounded_labelling()
    return {
        "scenario": scenario_to_dict(scenario),
        "af": serialize_af(scenario, arguments, attacks, labelling),
    }
