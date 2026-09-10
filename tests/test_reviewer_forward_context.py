"""The reviewer must see validated forward references already in the preview."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from app.llm.client import ToolCallResponse
from app.llm.edit_service import run_propose
from app.scenario.catalog import load_bundled_scenario
from app.scenario.diff_ops import apply as apply_ops
from app.scenario.serialize import scenario_to_dict
from app.scenario.state import compute_state_bundle


def test_reviewer_sees_the_same_forward_reference_as_preview_and_apply():
    scenario = load_bundled_scenario("fried_chicken_v2")
    before = scenario_to_dict(scenario)
    payload = {
        "id": "dinein_if_open",
        "rule": {"type": "defeasible", "premises": ["restaurant_open"],
                 "conclusion": "-order_to_go"},
        "new_premise_notes": [{"id": "restaurant_open",
                               "description": "the restaurant is open for dine-in service"}],
    }

    class Client:
        def __init__(self):
            self.reviewed_operation = None
            self.calls = 0

        def tool_call(self, **kwargs):
            self.calls += 1
            name = kwargs["tool"]["name"]
            if name == "review_edit":
                body = kwargs["system"].split("<proposed_edit>\n", 1)[1].split("\n</proposed_edit>", 1)[0]
                self.reviewed_operation = json.loads(body)
                assert self.reviewed_operation["new_premise_notes"] == payload["new_premise_notes"]
                result = {"issues": []}
            else:
                result = deepcopy(payload)
            return ToolCallResponse(tool_name=name, tool_input=result, stop_reason="tool_use",
                                    usage={}, latency_ms=1, model="fixture")

    client = Client()
    result = run_propose(scenario, compute_state_bundle(scenario)["af"], [], task="add-rule",
                         instruction="If the restaurant is open for dine-in, prefer dining in.",
                         scenario_dir=Path(__file__).resolve().parents[1] / "examples" / "fried_chicken_v2",
                         client=client)
    assert client.calls == 2 and result.reviewed
    assert client.reviewed_operation == result.op
    assert scenario_to_dict(scenario) == before
    applied = apply_ops(scenario, [result.op])
    assert applied.propositions["restaurant_open"].description == payload["new_premise_notes"][0]["description"]
    assert len(result.review_issues) == 1
    assert "the restaurant is open for dine-in service" in result.review_issues[0].message
