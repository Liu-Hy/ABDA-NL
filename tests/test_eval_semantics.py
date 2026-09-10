"""Application evals need reproducible evidence, semantic checks, and full coverage."""
from __future__ import annotations

from copy import deepcopy

import pytest

from app.evals.evidence import RecordingClient, apply_semantic_reviews, coverage_matrix, digest
from app.evals.llm_eval import DEFAULT_SUITE, _chat_semantic_checks, _check_proposal, _concept_checks, _scenario_for_case, load_suite
from app.llm.client import LLMResponse
from app.llm.evidence import resolve_context_refs


def _case(identifier):
    suite, _ = load_suite(DEFAULT_SUITE)
    return deepcopy(next(case for case in suite["cases"] if case["id"] == identifier))


def test_every_feature_has_all_case_types_and_all_six_examples_are_used():
    suite, _ = load_suite(DEFAULT_SUITE)
    assert len(suite["cases"]) >= 40
    for feature in suite["required_features"]:
        cases = [case for case in suite["cases"] if feature in case["features"]]
        assert {case["case_type"] for case in cases} == set(suite["required_case_types"])
    assert set(suite["required_scenarios"]).issubset({case["scenario_id"] for case in suite["cases"]})
    assert any(case.get("split") == "regression" for case in suite["cases"])
    for case in suite["cases"]:
        scenario, bundle, _, _ = _scenario_for_case(case)
        resolve_context_refs(scenario, bundle["af"], case.get("context_refs", []))


def test_real_filename_does_not_make_invented_quotation_pass():
    case = _case("fire-corpus-quote")
    scenario, bundle, _, directory = _scenario_for_case(case)
    result = _chat_semantic_checks(case, 'The permit is withheld: "all prescribed burns are automatically illegal everywhere" [epa_pm25_standards.txt].', scenario, bundle, directory)
    assert result["exact_quote_epa_pm25_standards.txt"] is False
    assert result["all_substantial_quotes_grounded"] is False


def test_quote_check_accepts_actual_passage_and_requires_local_citation():
    case = _case("fire-corpus-quote")
    scenario, bundle, _, directory = _scenario_for_case(case)
    quote = '"exceedance days are off-limits regardless."'
    correct = _chat_semantic_checks(case, quote + " [epa_pm25_standards.txt]", scenario, bundle, directory)
    assert all(correct.values())
    missing = _chat_semantic_checks(case, quote, scenario, bundle, directory)
    assert missing["exact_quote_epa_pm25_standards.txt"] is False


def test_swapped_labels_do_not_pass_just_because_expected_words_occur():
    case = _case("fried-chicken-v1-airfryer-off")
    scenario, bundle, _, directory = _scenario_for_case(case)
    wrong = _chat_semantic_checks(case, "Crispiness is undecided and ordering to-go is rejected.", scenario, bundle, directory)
    assert wrong == {"label_0_crispy": False, "label_1_order_to_go": False}
    correct = _chat_semantic_checks(case, "Crispiness is rejected and ordering to-go is undecided.", scenario, bundle, directory)
    assert all(correct.values())


def test_label_check_accepts_present_tense_without_accepting_negated_or_swapped_claims():
    case = _case("custom-scenario-renamed-meanings")
    scenario, bundle, _, directory = _scenario_for_case(case)
    observed = "The scenario accepts the conclusion that the greenhouse should be ventilated."
    assert _chat_semantic_checks(case, observed, scenario, bundle, directory)["label_0_ventilate"]
    for false_claim in (
        "The scenario does not accept the conclusion that the greenhouse should be ventilated.",
        "The scenario doesn't accept the conclusion that the greenhouse should be ventilated.",
        "The ventilation conclusion is not currently accepted.",
        "The scenario rejects the conclusion that the greenhouse should be ventilated.",
    ):
        assert not _chat_semantic_checks(case, false_claim, scenario, bundle, directory)["label_0_ventilate"]
    changed = _case("fried-chicken-v1-airfryer-off")
    scenario, bundle, _, directory = _scenario_for_case(changed)
    accepted = "The scenario rejects crispiness. Ordering to-go is undecided."
    assert all(_chat_semantic_checks(changed, accepted, scenario, bundle, directory).values())
    negated = "The scenario does not reject crispiness. Ordering to-go is undecided."
    assert not _chat_semantic_checks(changed, negated, scenario, bundle, directory)["label_0_crispy"]


def test_single_selected_item_accepts_a_direct_pronoun_answer():
    case = _case("fried-chicken-v1-item-question")
    scenario, bundle, _, directory = _scenario_for_case(case)
    explanation = " The active air-fryer assumption supports crispiness and undercuts the soggy inference."
    for opening in ("It's accepted.", "It’s accepted.", "It is currently accepted."):
        assert _chat_semantic_checks(case, opening + explanation, scenario, bundle, directory)["label_0_crispy"]
    for opening in ("It's rejected.", "It is undecided.", "It's not accepted.", "It isn't rejected.", "Perhaps it's accepted."):
        assert not _chat_semantic_checks(case, opening + explanation, scenario, bundle, directory)["label_0_crispy"]
    contradiction = "It's accepted. Crispiness is rejected."
    assert not _chat_semantic_checks(case, contradiction, scenario, bundle, directory)["label_0_crispy"]


@pytest.mark.parametrize("references", [
    [],
    [{"kind": "conclusion", "id": "order_to_go"}],
    [{"kind": "rule", "id": "airfryer_makes_crispy"}],
    [{"kind": "conclusion", "id": "crispy"}, {"kind": "conclusion", "id": "order_to_go"}],
])
def test_direct_pronoun_does_not_guess_an_unselected_or_ambiguous_label(references):
    case = _case("fried-chicken-v1-item-question")
    case["context_refs"] = references
    scenario, bundle, _, directory = _scenario_for_case(case)
    assert not _chat_semantic_checks(case, "It's accepted. The air fryer supports crispiness.", scenario, bundle, directory)["label_0_crispy"]


def test_unattached_handbook_wording_passes_without_licensing_invented_sources():
    case = _case("missing-reference-does-not-license-a-quote")
    scenario, bundle, _, directory = _scenario_for_case(case)
    actual = (
        "No handbook is attached, so no external quotation or handbook-based justification can be provided. "
        "The scenario establishes that ventilation is accepted because the window is open."
    )
    assert _concept_checks(actual, case["required_concepts"])[0]
    assert all(_chat_semantic_checks(case, actual, scenario, bundle, directory).values())
    invented = actual + ' The handbook states "all windows must remain open" [handbook.pdf].'
    assert _chat_semantic_checks(case, invented, scenario, bundle, directory)["no_invented_source"] is False
    assert not _concept_checks("The scenario handbook justifies the rule.", case["required_concepts"])[0]


@pytest.mark.parametrize(("case_id", "payload", "unsupported_source"), [
    ("propose-fire-monitor-fact", "fact", "community airshed letter; school-district monitoring station"),
    ("propose-medical-alternative-assumption", "assumption", "wikipedia_ppi.txt; H2RAs as alternative acid suppression"),
])
def test_stipulated_premise_cannot_borrow_unrelated_document_provenance(case_id, payload, unsupported_source):
    expected = _case(case_id)["expected"]
    operation = {"op": expected["op"], payload: {"source": unsupported_source}}
    assert _check_proposal(operation, expected)["source_origin"] is False
    operation[payload]["source"] = "user-provided scenario premise"
    assert _check_proposal(operation, expected)["source_origin"] is True
    operation[payload].pop("source")
    assert _check_proposal(operation, expected)["source_origin"] is True


def test_recording_client_keeps_rejected_drafts_and_request_parameters():
    class Client:
        def complete(self, **kwargs):
            return LLMResponse(text="a draft to inspect", stop_reason="end_turn", usage={"input_tokens": 10, "output_tokens": 3}, latency_ms=1, model="test")

    recorder = RecordingClient(Client())
    recorder.complete(system="shared prompt", messages=[{"role": "user", "content": "question"}], max_tokens=99, cache=True)
    assert recorder.calls[0]["request"]["max_tokens"] == 99
    assert recorder.calls[0]["response"]["text"] == "a draft to inspect"
    assert recorder.calls[0]["response_sha256"] == digest(recorder.calls[0]["response"])


def test_recording_client_preserves_safe_truncation_evidence_without_transport_or_reasoning_text():
    class ParseFailure(RuntimeError):
        diagnostics = {
            "finish_reason": "length", "requested_max_tokens": 2048,
            "actual_model": "FW-GLM-5.3", "visible_content": "incomplete visible answer",
            "reasoning_tokens": 2010, "reasoning_content": "private reasoning text",
            "endpoint": "https://private.example", "headers": {"Authorization": "private-key"},
            "usage": {"input_tokens": 12000, "output_tokens": 2048, "api_key": "private-key"},
            "tool_calls": [{"function": {"name": "propose_add_fact", "arguments": '{"fact":',
                                          "headers": {"Authorization": "private-key"}},
                            "request_url": "https://private.example"}],
        }

    class Client:
        def tool_call(self, **kwargs):
            raise ParseFailure("Do not save raw exception strings: private-key")

    recorder = RecordingClient(Client())
    with pytest.raises(ParseFailure):
        recorder.tool_call(system="synthetic prompt", messages=[], tool={"name": "propose_add_fact"}, max_tokens=2048)
    entry = recorder.calls[0]
    diagnostics = entry["error_diagnostics"]
    assert diagnostics["finish_reason"] == "length"
    assert diagnostics["reasoning_tokens"] == 2010
    assert diagnostics["tool_calls"] == [{"function": {"name": "propose_add_fact", "arguments": '{"fact":'}}]
    assert diagnostics["usage"] == {"input_tokens": 12000, "output_tokens": 2048}
    assert entry["diagnostics_sha256"] == digest(diagnostics)
    assert "private-key" not in str(entry)
    assert "private.example" not in str(entry)
    assert "private reasoning text" not in str(entry)
    assert "finished_at" in entry

    ParseFailure.diagnostics["tool_calls"][0]["function"]["arguments"] = ["not an object"]
    with pytest.raises(ParseFailure):
        recorder.tool_call(system="synthetic prompt", messages=[], tool={"name": "propose_add_fact"}, max_tokens=2048)
    assert recorder.calls[1]["error_diagnostics"]["tool_calls"][0]["function"]["arguments"] == ["not an object"]


def _small_report():
    cases = [{"id": kind, "kind": "chat", "features": ["grounded_chat"], "case_type": kind} for kind in ("routine", "ambiguous", "adversarial", "edge")]
    suite = {"cases": cases, "required_features": ["grounded_chat"], "required_case_types": [case["case_type"] for case in cases]}
    results = [{"case_id": case["id"], "kind": "chat", "route_id": "funded", "repetition": 1, "passed": True, "error": None, "evidence_sha256": "a" * 64} for case in cases]
    return {"suite_definition": suite, "results": results, "routes": ["funded"], "repetitions": 1, "implementation_unchanged": True, "automated_gate_passed": True}


def test_model_feature_cell_is_incomplete_until_every_case_type_and_repeat_runs():
    report = _small_report()
    matrix = coverage_matrix(report["suite_definition"], report["results"][:-1], report["routes"], repetitions=1)
    assert matrix["funded"]["grounded_chat"]["complete"] is False
    assert matrix["funded"]["grounded_chat"]["case_types_missing"] == ["edge"]
    matrix = coverage_matrix(report["suite_definition"], report["results"], report["routes"], repetitions=2)
    assert matrix["funded"]["grounded_chat"]["complete"] is False


def test_automated_pass_is_not_answer_inspection_or_application_acceptance():
    report = _small_report()
    matrix = coverage_matrix(report["suite_definition"], report["results"], report["routes"], repetitions=1)
    cell = matrix["funded"]["grounded_chat"]
    assert cell["complete"] and cell["automated_pass"]
    assert not cell["answers_reviewed"] and not cell["accepted"]


def test_reviews_are_bound_to_exact_evidence_and_all_semantic_criteria():
    report = _small_report()
    annotations = {
        f"funded:{result['case_id']}:1": {
            "response_sha256": result["evidence_sha256"],
            "grounding": True, "semantic_fidelity": True, "usefulness": True, "presentation": True,
            "notes": "Checked the claimed label, quoted source, requested meaning, and displayed wording against this case's state.",
        }
        for result in report["results"]
    }
    reviews = {"reviewer": "independent-evaluation-agent", "results": annotations}
    bad = deepcopy(reviews)
    bad["results"]["funded:routine:1"]["response_sha256"] = "changed"
    with pytest.raises(ValueError, match="does not match"):
        apply_semantic_reviews(deepcopy(report), bad)
    accepted = apply_semantic_reviews(deepcopy(report), reviews)
    assert accepted["application_accepted"] is True
    changed_code = deepcopy(report)
    changed_code["implementation_unchanged"] = False
    assert apply_semantic_reviews(changed_code, reviews)["application_accepted"] is False
    rejected = deepcopy(reviews)
    rejected["results"]["funded:edge:1"]["semantic_fidelity"] = False
    assert apply_semantic_reviews(deepcopy(report), rejected)["application_accepted"] is False
