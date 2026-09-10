"""Deterministic tests for the versioned model evaluation harness."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.evals.budget import PersistentSpendCap
from app.evals.llm_eval import (
    _check_proposal,
    _read_checkpoint,
    evaluate_chat,
    evaluate_case,
    evaluate_propose,
    evaluate_review,
    load_suite,
    main,
    run_evaluation,
    summarize_route,
)
from app.llm.catalog import load_model_catalog
from app.llm.client import LLMResponse, ToolCallResponse
from app.llm.routing import (
    CallContext,
    LLMRouteConfigurationError,
    LLMRouter,
    PaidRunCapReached,
)


SUITE_PATH = Path(__file__).resolve().parents[1] / "evals" / "llm_suite.yaml"


class _FakeClient:
    def __init__(self, *, completions=None, tools=None):
        self.completions = list(completions or [])
        self.tools = list(tools or [])
        self.closed = False

    def complete(self, **_kwargs):
        return self.completions.pop(0)

    def tool_call(self, **_kwargs):
        return self.tools.pop(0)

    def close(self):
        self.closed = True


def _response(text: str) -> LLMResponse:
    return LLMResponse(
        text=text,
        stop_reason="end_turn",
        usage={"input_tokens": 100, "output_tokens": 20},
        latency_ms=10,
        model="eval-model",
        provider="eval-provider",
        billing_source="eval",
        route="eval-route",
        cost_microusd=50,
    )


def _tool(name: str, payload: dict) -> ToolCallResponse:
    return ToolCallResponse(
        tool_name=name,
        tool_input=payload,
        stop_reason="tool_use",
        usage={"input_tokens": 100, "output_tokens": 20},
        latency_ms=10,
        model="eval-model",
        provider="eval-provider",
        billing_source="eval",
        route="eval-route",
        cost_microusd=50,
    )


def _case(case_id: str) -> dict:
    suite, _ = load_suite(SUITE_PATH)
    return next(case for case in suite["cases"] if case["id"] == case_id)


def test_suite_is_versioned_and_hashable():
    suite, digest = load_suite(SUITE_PATH)
    assert suite["version"] == 7
    assert suite["default_repetitions"] == 3
    assert suite["gates"]["min_case_pass_rate"] == 1.0
    assert len(suite["cases"]) >= 16
    assert len(digest) == 64


def test_route_listing_exposes_only_public_selector_fields(capsys, monkeypatch):
    monkeypatch.setattr("app.cli.serve._load_environment", lambda: None)
    assert main(["--list-routes"]) == 0
    lines = capsys.readouterr().out.splitlines()
    catalog = load_model_catalog()
    assert len(lines) == len(catalog.routes)
    assert all(len(line.split("\t")) == 3 for line in lines)
    assert {line.split("\t", 1)[0] for line in lines} == set(catalog.routes)


def test_chat_case_requires_grounding_and_expected_concepts():
    client = _FakeClient(
        completions=[
            _response(
                "Neither Popov nor Hayashi has a clearly stronger claim. "
                "The baseline remains balanced and undecided."
            )
        ]
    )
    result = evaluate_chat(_case("popov-baseline-decision"), client)
    assert result["passed"] is True
    assert result["grounded"] is True
    assert result["missing_concepts"] == []


def test_medical_chat_rubric_accepts_reject_as_rejected_morphology():
    client = _FakeClient(
        completions=[
            _response(
                "Pantoprazole undercuts the CYP2C19 interaction argument, so the "
                "engine will reject the cardiac concern and accept continuing PPI "
                "therapy."
            )
        ]
    )
    result = evaluate_chat(_case("medical-pantoprazole-toggle"), client)
    assert result["concepts_passed"] is True
    assert result["missing_concepts"] == []


def test_proposal_case_checks_semantic_rule_fields():
    client = _FakeClient(
        tools=[
            _tool(
                "propose_add_rule",
                {
                    "id": "preposs_support",
                    "rule": {
                        "type": "defeasible",
                        "premises": ["popov_preposs_interest"],
                        "conclusion": "popov_legit_claim",
                        "category": "legitimacy",
                        "block": 1,
                    },
                },
            ),
            _tool("review_edit", {"issues": []}),
        ]
    )
    result = evaluate_propose(_case("propose-popov-support-rule"), client)
    assert result["passed"] is True
    assert all(result["checks"].values())


def test_proposal_case_checks_narrow_rule_fields_and_forward_notes():
    narrow = _check_proposal(
        {
            "op": "modify-rule",
            "id": "r_stack",
            "rule": {
                "type": "defeasible",
                "premises": ["has_firsts"],
                "conclusion": "stack_vets",
                "category": "strategy",
            },
        },
        {
            "op": "modify-rule",
            "id": "r_stack",
            "rule_fields": {
                "premises": ["has_firsts"],
                "category": "strategy",
            },
        },
    )
    assert all(narrow.values())

    notes = _check_proposal(
        {
            "op": "add-rule",
            "id": "open_dinein",
            "rule": {
                "type": "defeasible",
                "premises": ["restaurant_open"],
                "conclusion": "-order_to_go",
            },
            "new_premise_notes": [
                {
                    "id": "restaurant_open",
                    "description": "the restaurant is open for dine-in service",
                }
            ],
        },
        {"conclusion": "-order_to_go", "new_premise_notes_min": 1},
    )
    assert all(notes.values())


def test_review_case_detects_reversed_semantics():
    client = _FakeClient(
        tools=[
            _tool(
                "review_edit",
                {
                    "issues": [
                        {
                            "severity": "blocker",
                            "message": "The conclusion reverses the requested effect.",
                        }
                    ]
                },
            )
        ]
    )
    result = evaluate_review(_case("review-reversed-smoke-rule"), client)
    assert result["passed"] is True
    assert result["issues"][0]["severity"] == "blocker"


def test_route_summary_applies_quality_latency_and_cost_gates():
    results = [
        {
            "case_id": "chat-case",
            "kind": "chat",
            "passed": True,
            "error": None,
            "wall_time_ms": 100,
            "audit": {"cost_microusd": 10, "provider_calls": 1},
        },
        {
            "case_id": "propose-case",
            "kind": "propose",
            "passed": True,
            "error": None,
            "wall_time_ms": 200,
            "audit": {"cost_microusd": 20, "provider_calls": 2},
        },
        {
            "case_id": "review-case",
            "kind": "review",
            "passed": True,
            "error": None,
            "wall_time_ms": 150,
            "audit": {"cost_microusd": 15, "provider_calls": 1},
        },
    ]
    gates = {
        "min_overall_pass_rate": 1,
        "min_chat_pass_rate": 1,
        "min_propose_pass_rate": 1,
        "min_review_pass_rate": 1,
        "min_case_pass_rate": 1,
        "max_error_count": 0,
        "max_p95_latency_ms": 500,
        "max_average_cost_microusd": 100,
    }
    summary = summarize_route("test-route", results, gates)
    assert summary["gate_passed"] is True
    assert summary["provider_calls"] == 4
    assert summary["total_cost_microusd"] == 45
    assert summary["minimum_case_pass_rate"] == 1
    assert summary["failed_case_ids"] == []


def test_route_summary_rejects_an_unstable_case_hidden_by_aggregate_rate():
    results = []
    for repetition, passed in enumerate((True, True, False), 1):
        results.append(
            {
                "case_id": "critical-case",
                "kind": "chat",
                "repetition": repetition,
                "passed": passed,
                "error": None,
                "wall_time_ms": 100,
                "audit": {"cost_microusd": 10, "provider_calls": 1},
            }
        )
    results.extend(
        {
            "case_id": f"stable-case-{index}",
            "kind": "chat",
            "repetition": 1,
            "passed": True,
            "error": None,
            "wall_time_ms": 100,
            "audit": {"cost_microusd": 10, "provider_calls": 1},
        }
        for index in range(20)
    )
    summary = summarize_route(
        "test-route",
        results,
        {
            "min_overall_pass_rate": 0.95,
            "min_chat_pass_rate": 0.95,
            "min_case_pass_rate": 1,
            "max_error_count": 0,
        },
    )
    assert summary["overall_pass_rate"] > 0.95
    assert summary["minimum_case_pass_rate"] == pytest.approx(2 / 3)
    assert summary["failed_case_ids"] == ["critical-case"]
    assert summary["gate_passed"] is False


def test_route_summary_does_not_fail_unselected_case_kinds():
    results = [
        {
            "case_id": "propose-only",
            "kind": "propose",
            "passed": True,
            "error": None,
            "wall_time_ms": 100,
            "audit": {"cost_microusd": 10, "provider_calls": 1},
        }
    ]
    summary = summarize_route(
        "test-route",
        results,
        {
            "min_overall_pass_rate": 1,
            "min_chat_pass_rate": 1,
            "min_propose_pass_rate": 1,
            "min_review_pass_rate": 1,
            "min_case_pass_rate": 1,
            "max_error_count": 0,
        },
    )
    assert summary["gate_checks"]["chat_pass_rate"] is True
    assert summary["gate_checks"]["review_pass_rate"] is True
    assert summary["gate_passed"] is True


def test_latency_gate_excludes_recorded_pacing_but_keeps_wall_time():
    result = {"case_id": "paced", "kind": "chat", "passed": True, "error": None,
              "wall_time_ms": 65000, "application_time_ms": 5000, "pacing_time_ms": 60000,
              "audit": {"cost_microusd": 10, "provider_calls": 1}}
    summary = summarize_route("funded", [result], {"max_p95_latency_ms": 10000})
    assert summary["p95_wall_time_ms"] == 65000
    assert summary["p95_application_time_ms"] == 5000
    assert summary["pacing_time_ms"] == 60000
    assert summary["gate_checks"]["p95_application_time_ms"]


def test_evaluate_case_closes_its_route_client(monkeypatch):
    client = _FakeClient(
        completions=[
            _response(
                "Neither Popov nor Hayashi has a clearly stronger claim. "
                "The baseline remains balanced and undecided."
            )
        ]
    )

    class Router:
        def evaluation_route(self, *_args, **_kwargs):
            return client

    monkeypatch.setattr(
        "app.evals.llm_eval._audit_totals",
        lambda _router, _request_id: {"provider_calls": 1},
    )
    result = evaluate_case(
        _case("popov-baseline-decision"),
        router=Router(),
        route_id="test-route",
        repetition=1,
        allow_emergency_spend=False,
    )

    assert result["passed"] is True
    assert client.closed is True


def test_openrouter_evaluation_requires_explicit_paid_permission():
    router = LLMRouter(settings=get_settings())
    with pytest.raises(LLMRouteConfigurationError, match="explicit"):
        router.evaluation_route(
            "openrouter-claude-sonnet-5",
            context=CallContext(
                user_id=None,
                request_id="eval-test",
                request_kind="eval-chat",
                charge_trial=False,
            ),
        )


def test_evaluation_paid_cap_reserves_each_call_and_stops_remaining_cases(
    monkeypatch, tmp_path,
):
    router = LLMRouter(settings=get_settings())
    calls = 0

    def fake_evaluate_case(
        case,
        *,
        router,
        route_id,
        repetition,
        allow_emergency_spend,
        spend_cap,
        pacer=None,
    ):
        nonlocal calls
        del router, allow_emergency_spend
        calls += 1
        try:
            reservation = spend_cap.reserve(6)
        except PaidRunCapReached as exc:
            return {
                "case_id": case["id"],
                "kind": case["kind"],
                "route_id": route_id,
                "repetition": repetition,
                "request_id": "capped",
                "passed": False,
                "error": {"type": type(exc).__name__, "message": str(exc)},
                "audit": {"cost_microusd": 0, "provider_calls": 0},
                "wall_time_ms": 0,
            }
        spend_cap.settle(reservation, 5)
        return {
            "case_id": case["id"],
            "kind": case["kind"],
            "route_id": route_id,
            "repetition": repetition,
            "request_id": "paid",
            "passed": True,
            "error": None,
            "audit": {"cost_microusd": 5, "provider_calls": 1},
            "wall_time_ms": 1,
        }

    monkeypatch.setattr("app.evals.llm_eval.evaluate_case", fake_evaluate_case)
    report = run_evaluation(
        {
            "name": "cap-test",
            "version": 1,
            "cases": [
                {
                    "id": "paid-case",
                    "kind": "chat",
                    "scenario_id": "popov-hayashi",
                }
            ],
            "gates": {},
        },
        suite_hash="a" * 64,
        route_ids=[next(route.id for route in router.catalog.routes.values() if route.provider == "azure-foundry")],
        router=router,
        repetitions=3,
        smoke=False,
        case_ids=set(),
        allow_emergency_spend=False,
        paid_run_cap_microusd=10,
        spend_cap=PersistentSpendCap(path=tmp_path / "budget.sqlite3", run_limit_microusd=10),
    )
    assert calls == 2
    assert report["paid_spend_microusd"] == 5
    assert report["results"][0]["passed"] is True
    assert report["results"][1]["error"]["type"] == "PaidRunCapReached"
    assert report["results"][2]["skipped"] is True


def test_checkpoint_preserves_partial_tail_and_recovers_complete_results(tmp_path):
    path = tmp_path / "partial.checkpoint.jsonl"
    path.write_bytes(b'{"run_id":"original","metadata":{}}\n{"result":{"case_id":"done"}}\n{"result":{"case_id":"interrupted')
    header, results = _read_checkpoint(path)
    assert header["run_id"] == "original"
    assert results == [{"case_id": "done"}]
    assert path.read_bytes().endswith(b'"done"}}\n')
    tails = list(tmp_path.glob("*.partial-*"))
    assert len(tails) == 1
    assert tails[0].read_bytes() == b'{"result":{"case_id":"interrupted'


def test_smoke_sub_budget_is_shared_by_both_funded_models(monkeypatch, tmp_path):
    router = LLMRouter(settings=get_settings())
    cap = PersistentSpendCap(path=tmp_path / "budget.sqlite3", run_limit_microusd=5_000_000)
    dispatches = []

    def fake_evaluate_case(case, *, route_id, repetition, spend_cap, **kwargs):
        result = {
            "case_id": case["id"], "kind": case["kind"], "route_id": route_id,
            "repetition": repetition, "wall_time_ms": 1,
        }
        try:
            reservation = spend_cap.reserve(3_000_000)
        except PaidRunCapReached:
            return {**result, "passed": False, "error": {"type": "PaidRunCapReached"}, "audit": {"provider_calls": 0, "cost_microusd": 0}}
        dispatches.append(route_id)
        spend_cap.settle(reservation, 2_500_000)
        return {**result, "passed": True, "error": None, "audit": {"provider_calls": 1, "cost_microusd": 2_500_000}}

    monkeypatch.setattr("app.evals.llm_eval.evaluate_case", fake_evaluate_case)
    report = run_evaluation(
        {"cases": [{"id": "shared-smoke", "kind": "chat"}]}, suite_hash="synthetic",
        route_ids=["cloudbank-gpt-5.6-terra", "cloudbank-gpt-5.6-sol"], router=router,
        repetitions=1, smoke=False, case_ids=set(), allow_emergency_spend=False,
        paid_run_cap_microusd=5_000_000, spend_cap=cap,
    )
    assert dispatches == ["cloudbank-gpt-5.6-terra"]
    assert report["paid_spend_microusd"] == 2_500_000
    assert report["results"][1]["audit"]["provider_calls"] == 0


@pytest.mark.parametrize("stop_mode", ["runtime", "operator"])
def test_case_boundary_stop_settles_current_case_and_resumes_only_remaining_cases(monkeypatch, tmp_path, stop_mode):
    router = LLMRouter(settings=get_settings())
    cap = PersistentSpendCap(path=tmp_path / "budget.sqlite3", run_limit_microusd=100)
    checkpoint = tmp_path / "run.checkpoint.jsonl"
    stop_file = tmp_path / "route.stop"
    clock = [0.0]
    dispatched = []
    monkeypatch.setattr("app.evals.llm_eval.time.time", lambda: clock[0])

    def fake_case(case, *, route_id, repetition, spend_cap, **kwargs):
        dispatched.append(case["id"])
        spend_cap.settle(spend_cap.reserve(20), 5)
        clock[0] += 20
        if stop_mode == "operator" and case["id"] == "first":
            stop_file.write_text("pause this model after inspected failures\n")
        return {"case_id": case["id"], "kind": "chat", "route_id": route_id,
                "repetition": repetition, "passed": True, "error": None,
                "audit": {"cost_microusd": 5, "provider_calls": 1}, "wall_time_ms": 1}

    monkeypatch.setattr("app.evals.llm_eval.evaluate_case", fake_case)
    kwargs = dict(
        suite_hash="synthetic", route_ids=["cloudbank-gpt-5.6-terra"], router=router,
        repetitions=1, smoke=False, case_ids=set(), allow_emergency_spend=False,
        paid_run_cap_microusd=100, spend_cap=cap, checkpoint_path=checkpoint,
        stop_file=stop_file,
    )
    suite = {"cases": [{"id": "first", "kind": "chat"}, {"id": "second", "kind": "chat"}]}
    first = run_evaluation(suite, **kwargs, stop_after_unix=190 if stop_mode == "runtime" else None)
    assert dispatched == ["first"]
    assert first["stopped_reason"]
    assert first["remaining_observations"] == 1
    assert not first["automated_gate_passed"]
    assert cap.snapshot()["reserved_microusd"] == 0
    assert cap.snapshot()["spent_microusd"] == 5
    if stop_file.exists():
        stop_file.rename(tmp_path / "preserved-stop-receipt.txt")
    resumed = run_evaluation(suite, **kwargs, resume=True, stop_after_unix=1000)
    assert dispatched == ["first", "second"]
    assert resumed["run_id"] == first["run_id"]
    assert resumed["remaining_observations"] == 0
    assert resumed["automated_gate_passed"]
    assert cap.snapshot()["spent_microusd"] == 10
    assert len(_read_checkpoint(checkpoint)[1]) == 2
