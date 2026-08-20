"""Run the versioned ABDA model suite against isolated provider routes."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

import yaml
from sqlalchemy import select

from app.core.config import get_settings, reset_settings_cache
from app.db.models import LLMUsageEvent
from app.db.session import initialize_database
from app.llm.catalog import load_model_catalog, reset_model_catalog_cache
from app.llm.chat_service import run_turn
from app.llm.edit_service import ProposerRetryExhausted, run_propose, run_review
from app.llm.routing import CallContext, LLMRouter, LocalSpendCap
from app.scenario.catalog import EXAMPLES_ROOT, load_bundled_scenario
from app.scenario.diff_ops import apply as apply_ops
from app.scenario.state import compute_state_bundle


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUITE = REPOSITORY_ROOT / "evals" / "llm_suite.yaml"
DEFAULT_PAID_RUN_CAP_MICROUSD = 1_000_000


class EvaluationConfigurationError(RuntimeError):
    pass


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvaluationConfigurationError(f"{name} must be a mapping")
    return value


def load_suite(path: Path) -> tuple[dict[str, Any], str]:
    data = path.read_bytes()
    parsed = yaml.safe_load(data)
    suite = _mapping(parsed, "evaluation suite")
    if int(suite.get("version", 0)) < 1:
        raise EvaluationConfigurationError("evaluation suite version must be positive")
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise EvaluationConfigurationError("evaluation suite must contain cases")
    seen: set[str] = set()
    for index, raw_case in enumerate(cases):
        case = _mapping(raw_case, f"cases[{index}]")
        case_id = str(case.get("id") or "")
        if not case_id or case_id in seen:
            raise EvaluationConfigurationError("evaluation case ids must be unique")
        seen.add(case_id)
        if case.get("kind") not in {"chat", "propose", "review"}:
            raise EvaluationConfigurationError(
                f"case {case_id!r} has an unsupported kind"
            )
        if not isinstance(case.get("scenario_id"), str):
            raise EvaluationConfigurationError(
                f"case {case_id!r} must identify a scenario"
            )
    return suite, hashlib.sha256(data).hexdigest()


def _scenario_for_case(case: dict[str, Any]):
    scenario_id = str(case["scenario_id"])
    baseline = load_bundled_scenario(scenario_id)
    operations = case.get("diff_ops") or []
    if not isinstance(operations, list):
        raise EvaluationConfigurationError(
            f"case {case['id']!r} diff_ops must be a list"
        )
    scenario = apply_ops(baseline, operations)
    bundle = compute_state_bundle(scenario)
    return scenario, bundle, operations, EXAMPLES_ROOT / scenario_id


def _concept_checks(
    text: str, groups: list[Any]
) -> tuple[bool, list[list[str]]]:
    normalized = text.casefold()
    missing: list[list[str]] = []
    for raw_group in groups:
        if not isinstance(raw_group, list) or not raw_group:
            raise EvaluationConfigurationError(
                "required concept groups must be nonempty lists"
            )
        group = [str(term) for term in raw_group]
        if not any(term.casefold() in normalized for term in group):
            missing.append(group)
    return not missing, missing


def evaluate_chat(case: dict[str, Any], client) -> dict[str, Any]:
    scenario, bundle, operations, scenario_dir = _scenario_for_case(case)
    result = run_turn(
        scenario,
        bundle["af"],
        operations,
        [{"role": "user", "content": str(case["question"])}],
        scenario_dir=scenario_dir,
        client=client,
    )
    concepts_passed, missing = _concept_checks(
        result.text, list(case.get("required_concepts") or [])
    )
    grounded = not result.validator_flags and result.stop_reason != "grounding_rejected"
    return {
        "passed": grounded and concepts_passed,
        "grounded": grounded,
        "concepts_passed": concepts_passed,
        "missing_concepts": missing,
        "text": result.text,
        "retried": result.retried,
        "validator_flags": result.validator_flags,
        "result_latency_ms": result.latency_ms,
        "result_cost_microusd": result.cost_microusd,
        "model": result.model,
        "provider": result.provider,
        "route": result.route,
        "billing_source": result.billing_source,
    }


def _description_for_op(operation: dict[str, Any]) -> str:
    for key in ("fact", "assumption", "rule"):
        payload = operation.get(key)
        if isinstance(payload, dict):
            return str(payload.get("description") or "")
    return ""


def _check_proposal(operation: dict[str, Any], expected: dict[str, Any]) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    if "op" in expected:
        checks["op"] = operation.get("op") == expected["op"]
    if "id" in expected:
        checks["id"] = operation.get("id") == expected["id"]
    rule = operation.get("rule")
    if "premises_include" in expected:
        premises = set(rule.get("premises") or []) if isinstance(rule, dict) else set()
        checks["premises_include"] = set(expected["premises_include"]).issubset(premises)
    if "conclusion" in expected:
        conclusion = rule.get("conclusion") if isinstance(rule, dict) else None
        checks["conclusion"] = conclusion == expected["conclusion"]
    if "rule_fields" in expected:
        expected_fields = _mapping(expected["rule_fields"], "expected rule_fields")
        checks["rule_fields"] = isinstance(rule, dict) and all(
            rule.get(field) == value for field, value in expected_fields.items()
        )
    if "new_premise_notes_min" in expected:
        notes = operation.get("new_premise_notes") or []
        checks["new_premise_notes_min"] = (
            isinstance(notes, list)
            and len(notes) >= int(expected["new_premise_notes_min"])
        )
    if "description_contains_any" in expected:
        description = _description_for_op(operation).casefold()
        checks["description_contains_any"] = any(
            str(term).casefold() in description
            for term in expected["description_contains_any"]
        )
    return checks


def evaluate_propose(case: dict[str, Any], client) -> dict[str, Any]:
    scenario, bundle, operations, scenario_dir = _scenario_for_case(case)
    result = run_propose(
        scenario,
        bundle["af"],
        operations,
        task=str(case["task"]),
        instruction=str(case["instruction"]),
        existing_id=case.get("existing_id"),
        scenario_dir=scenario_dir,
        client=client,
    )
    expected = _mapping(case.get("expected") or {}, f"case {case['id']} expected")
    checks = _check_proposal(result.op, expected)
    return {
        "passed": bool(checks) and all(checks.values()),
        "checks": checks,
        "operation": result.op,
        "proposer_attempts": result.proposer_attempts,
        "reviewed": result.reviewed,
        "review_issues": [issue.to_dict() for issue in result.review_issues],
        "result_latency_ms": result.latency_ms,
        "result_cost_microusd": result.cost_microusd,
        "model": result.model,
        "provider": result.provider,
        "route": result.route,
        "billing_source": result.billing_source,
    }


def evaluate_review(case: dict[str, Any], client) -> dict[str, Any]:
    scenario, bundle, operations, scenario_dir = _scenario_for_case(case)
    proposed_edit = _mapping(
        case.get("proposed_edit"), f"case {case['id']} proposed_edit"
    )
    result = run_review(
        scenario,
        bundle["af"],
        operations,
        user_instruction=str(case["instruction"]),
        proposed_edit=proposed_edit,
        scenario_dir=scenario_dir,
        client=client,
    )
    expected = _mapping(case.get("expected") or {}, f"case {case['id']} expected")
    min_issues = int(expected.get("min_issues", 0))
    max_issues = int(expected.get("max_issues", 2**31 - 1))
    allowed = {str(value) for value in expected.get("severities_any") or []}
    count_passed = min_issues <= len(result.issues) <= max_issues
    severity_passed = not allowed or any(issue.severity in allowed for issue in result.issues)
    return {
        "passed": count_passed and severity_passed,
        "count_passed": count_passed,
        "severity_passed": severity_passed,
        "issues": [issue.to_dict() for issue in result.issues],
        "result_latency_ms": result.latency_ms,
        "result_cost_microusd": result.cost_microusd,
        "model": result.model,
        "provider": result.provider,
        "route": result.route,
        "billing_source": result.billing_source,
    }


def _audit_totals(router: LLMRouter, request_id: str) -> dict[str, Any]:
    with router.session_factory() as session:
        events = list(
            session.scalars(
                select(LLMUsageEvent)
                .where(LLMUsageEvent.request_id == request_id)
                .order_by(LLMUsageEvent.created_at, LLMUsageEvent.id)
            )
        )
    return {
        "provider_calls": len(events),
        "successful_provider_calls": sum(event.status == "succeeded" for event in events),
        "failed_provider_calls": sum(event.status == "failed" for event in events),
        "cost_microusd": sum(event.cost_microusd for event in events),
        "latency_ms": sum(event.latency_ms for event in events),
        "input_tokens": sum(event.input_tokens for event in events),
        "output_tokens": sum(event.output_tokens for event in events),
        "cache_read_input_tokens": sum(
            event.cache_read_input_tokens for event in events
        ),
        "cache_creation_input_tokens": sum(
            event.cache_creation_input_tokens for event in events
        ),
        "routes": sorted({event.route for event in events}),
        "models": sorted({event.model for event in events}),
    }


def evaluate_case(
    case: dict[str, Any],
    *,
    router: LLMRouter,
    route_id: str,
    repetition: int,
    allow_emergency_spend: bool,
    spend_cap: LocalSpendCap | None = None,
) -> dict[str, Any]:
    request_id = "eval-" + uuid4().hex
    started = datetime.now(timezone.utc)
    payload: dict[str, Any]
    error: dict[str, str] | None = None
    try:
        client = router.evaluation_route(
            route_id,
            context=CallContext(
                user_id=None,
                request_id=request_id,
                request_kind=f"eval-{case['kind']}",
                charge_trial=False,
            ),
            allow_emergency_spend=allow_emergency_spend,
            spend_cap=spend_cap,
        )
        if case["kind"] == "chat":
            payload = evaluate_chat(case, client)
        elif case["kind"] == "propose":
            payload = evaluate_propose(case, client)
        else:
            payload = evaluate_review(case, client)
    except ProposerRetryExhausted as exc:
        payload = {
            "passed": False,
            "proposer_attempts": exc.attempts,
            "validator_issues": [issue.to_dict() for issue in exc.last_issues],
        }
        error = {"type": type(exc).__name__, "message": str(exc)}
    except Exception as exc:  # noqa: BLE001
        payload = {"passed": False}
        error = {"type": type(exc).__name__, "message": str(exc)[:500]}

    audit = _audit_totals(router, request_id)
    finished = datetime.now(timezone.utc)
    return {
        "case_id": case["id"],
        "kind": case["kind"],
        "route_id": route_id,
        "repetition": repetition,
        "request_id": request_id,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "wall_time_ms": int((finished - started).total_seconds() * 1000),
        "error": error,
        "audit": audit,
        **payload,
    }


def _rate(results: list[dict[str, Any]]) -> float:
    if not results:
        return 0.0
    return sum(bool(result.get("passed")) for result in results) / len(results)


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


def summarize_route(
    route_id: str,
    results: list[dict[str, Any]],
    gates: dict[str, Any],
) -> dict[str, Any]:
    by_kind = {
        kind: [result for result in results if result["kind"] == kind]
        for kind in ("chat", "propose", "review")
    }
    by_case: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        by_case.setdefault(str(result["case_id"]), []).append(result)
    case_pass_rates = {
        case_id: _rate(case_results)
        for case_id, case_results in sorted(by_case.items())
    }
    minimum_case_pass_rate = min(case_pass_rates.values(), default=0.0)
    total_cost = sum(result["audit"]["cost_microusd"] for result in results)
    average_cost = total_cost / len(results) if results else 0.0
    p95_latency = _p95([int(result["wall_time_ms"]) for result in results])
    error_count = sum(result.get("error") is not None for result in results)
    metrics = {
        "route_id": route_id,
        "case_count": len(results),
        "passed_count": sum(bool(result.get("passed")) for result in results),
        "overall_pass_rate": _rate(results),
        "chat_pass_rate": _rate(by_kind["chat"]),
        "propose_pass_rate": _rate(by_kind["propose"]),
        "review_pass_rate": _rate(by_kind["review"]),
        "case_pass_rates": case_pass_rates,
        "minimum_case_pass_rate": minimum_case_pass_rate,
        "failed_case_ids": [
            case_id
            for case_id, pass_rate in case_pass_rates.items()
            if pass_rate < float(gates.get("min_case_pass_rate", 0))
        ],
        "error_count": error_count,
        "total_cost_microusd": total_cost,
        "average_cost_microusd": average_cost,
        "p95_wall_time_ms": p95_latency,
        "provider_calls": sum(
            result["audit"]["provider_calls"] for result in results
        ),
    }
    comparisons = {
        "overall_pass_rate": metrics["overall_pass_rate"]
        >= float(gates.get("min_overall_pass_rate", 0)),
        "chat_pass_rate": not by_kind["chat"]
        or metrics["chat_pass_rate"] >= float(gates.get("min_chat_pass_rate", 0)),
        "propose_pass_rate": not by_kind["propose"]
        or metrics["propose_pass_rate"]
        >= float(gates.get("min_propose_pass_rate", 0)),
        "review_pass_rate": not by_kind["review"]
        or metrics["review_pass_rate"]
        >= float(gates.get("min_review_pass_rate", 0)),
        "minimum_case_pass_rate": minimum_case_pass_rate
        >= float(gates.get("min_case_pass_rate", 0)),
        "error_count": error_count <= int(gates.get("max_error_count", 0)),
        "p95_wall_time_ms": p95_latency
        <= int(gates.get("max_p95_latency_ms", 2**31 - 1)),
        "average_cost_microusd": average_cost
        <= float(gates.get("max_average_cost_microusd", 2**63 - 1)),
    }
    return {**metrics, "gate_checks": comparisons, "gate_passed": all(comparisons.values())}


def _selected_cases(
    suite: dict[str, Any], *, smoke: bool, case_ids: set[str]
) -> list[dict[str, Any]]:
    cases = [dict(case) for case in suite["cases"]]
    if smoke:
        cases = [case for case in cases if case.get("smoke") is True]
    if case_ids:
        known = {str(case["id"]) for case in cases}
        missing = sorted(case_ids - known)
        if missing:
            raise EvaluationConfigurationError(
                "unknown or filtered evaluation cases: " + ", ".join(missing)
            )
        cases = [case for case in cases if case["id"] in case_ids]
    if not cases:
        raise EvaluationConfigurationError("no evaluation cases were selected")
    return cases


def run_evaluation(
    suite: dict[str, Any],
    *,
    suite_hash: str,
    route_ids: list[str],
    router: LLMRouter,
    repetitions: int,
    smoke: bool,
    case_ids: set[str],
    allow_emergency_spend: bool,
    paid_run_cap_microusd: int,
) -> dict[str, Any]:
    cases = _selected_cases(suite, smoke=smoke, case_ids=case_ids)
    gates = _mapping(suite.get("gates") or {}, "gates")
    catalog = router.catalog
    unknown_routes = sorted(set(route_ids) - set(catalog.routes))
    if unknown_routes:
        raise EvaluationConfigurationError(
            "unknown routes: " + ", ".join(unknown_routes)
        )

    results: list[dict[str, Any]] = []
    spend_cap = LocalSpendCap(paid_run_cap_microusd)
    for route_id in route_ids:
        route = catalog.routes[route_id]
        paid = route.billing_source == "openrouter-emergency"
        for repetition in range(1, repetitions + 1):
            for case in cases:
                if paid and spend_cap.reached:
                    results.append(
                        {
                            "case_id": case["id"],
                            "kind": case["kind"],
                            "route_id": route_id,
                            "repetition": repetition,
                            "request_id": None,
                            "passed": False,
                            "skipped": True,
                            "error": {
                                "type": "PaidRunCapReached",
                                "message": "the evaluation paid-route cap was reached",
                            },
                            "audit": {
                                "provider_calls": 0,
                                "cost_microusd": 0,
                            },
                            "wall_time_ms": 0,
                        }
                    )
                    continue
                result = evaluate_case(
                    case,
                    router=router,
                    route_id=route_id,
                    repetition=repetition,
                    allow_emergency_spend=allow_emergency_spend,
                    spend_cap=spend_cap if paid else None,
                )
                results.append(result)

    paid_spend = spend_cap.spent_microusd

    summaries = {
        route_id: summarize_route(
            route_id,
            [result for result in results if result["route_id"] == route_id],
            gates,
        )
        for route_id in route_ids
    }
    return {
        "schema_version": 2,
        "usage_contract": "exclusive-input-cache-v1",
        "run_id": uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "suite_name": suite.get("name"),
        "suite_version": suite.get("version"),
        "suite_sha256": suite_hash,
        "catalog_version": catalog.version,
        "catalog_updated": catalog.updated,
        "routes": route_ids,
        "repetitions": repetitions,
        "smoke": smoke,
        "allow_emergency_spend": allow_emergency_spend,
        "paid_run_cap_microusd": paid_run_cap_microusd,
        "paid_spend_microusd": paid_spend,
        "gates": gates,
        "summaries": summaries,
        "results": results,
        "gate_passed": all(summary["gate_passed"] for summary in summaries.values()),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate ABDA prompts against isolated model routes"
    )
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--route", action="append", dest="routes")
    parser.add_argument("--case", action="append", dest="cases", default=[])
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--list-routes", action="store_true")
    parser.add_argument("--allow-openrouter-spend", action="store_true")
    parser.add_argument(
        "--paid-run-cap-microusd",
        type=int,
        default=DEFAULT_PAID_RUN_CAP_MICROUSD,
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-fail-on-gate", action="store_true")
    return parser


def _default_output() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return REPOSITORY_ROOT / "artifacts" / "evals" / f"{stamp}.json"


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    from app.cli.serve import _load_environment

    _load_environment()
    reset_settings_cache()
    reset_model_catalog_cache()
    catalog = load_model_catalog()
    if args.list_routes:
        for route in catalog.routes.values():
            print(
                f"{route.id}\t{route.provider}\t{route.model}\t{route.billing_source}"
            )
        return 0
    if not args.routes:
        print("At least one --route is required.", file=sys.stderr)
        return 2
    if args.repetitions is not None and args.repetitions < 1:
        print("--repetitions must be positive.", file=sys.stderr)
        return 2
    if args.paid_run_cap_microusd < 1:
        print("--paid-run-cap-microusd must be positive.", file=sys.stderr)
        return 2

    try:
        suite, suite_hash = load_suite(args.suite.resolve())
        repetitions = args.repetitions or int(suite.get("default_repetitions", 1))
        initialize_database()
        router = LLMRouter(settings=get_settings(), catalog=catalog)
        report = run_evaluation(
            suite,
            suite_hash=suite_hash,
            route_ids=list(dict.fromkeys(args.routes)),
            router=router,
            repetitions=repetitions,
            smoke=args.smoke,
            case_ids=set(args.cases),
            allow_emergency_spend=args.allow_openrouter_spend,
            paid_run_cap_microusd=args.paid_run_cap_microusd,
        )
    except (EvaluationConfigurationError, RuntimeError, OSError) as exc:
        print(f"Evaluation could not start: {exc}", file=sys.stderr)
        return 2

    output = (args.output or _default_output()).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "gate_passed": report["gate_passed"],
        "paid_spend_microusd": report["paid_spend_microusd"],
        "output": str(output),
        "summaries": report["summaries"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if report["gate_passed"] or args.no_fail_on_gate:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
