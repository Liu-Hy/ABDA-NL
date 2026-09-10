"""The funded evaluation must fail closed across retries and process restarts."""
from __future__ import annotations

import multiprocessing
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.models import Base, LLMUsageEvent
from app.evals.budget import EvaluationBudgetError, MAX_CLOUDBANK_EVALUATION_MICROUSD, PersistentSpendCap
from app.evals.funded import funded_environment
from app.evals.isolation import EvaluationIsolationError, assert_no_openrouter_credentials, check_funded_request, funded_network_only
from app.evals.llm_eval import EvaluationConfigurationError, run_evaluation
from app.llm.catalog import load_model_catalog
from app.llm.client import LLMResponse
from app.llm.providers import LLMProviderError
from app.llm.routing import CallContext, LLMRouter, MeteredClient, PaidRunCapReached, RetryingClient


def _reserve_in_process(path: str, result_queue) -> None:
    ledger = PersistentSpendCap(path=Path(path))
    try:
        ledger.reserve(70_000_000)
    except PaidRunCapReached:
        result_queue.put("blocked")
    else:
        result_queue.put("reserved")


def test_shared_budget_serializes_separate_processes(tmp_path):
    path = tmp_path / "shared.sqlite3"
    PersistentSpendCap(path=path)
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    processes = [context.Process(target=_reserve_in_process, args=(str(path), queue)) for _ in range(2)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0
    assert sorted(queue.get(timeout=2) for _ in processes) == ["blocked", "reserved"]
    assert PersistentSpendCap(path=path).reserved_microusd == 70_000_000


def test_new_runs_and_resumes_do_not_reset_spend_or_orphan_reservations(tmp_path):
    path = tmp_path / "budget.sqlite3"
    first = PersistentSpendCap(path=path, run_id="baseline")
    first.settle(first.reserve(60_000_000), 55_000_000)
    orphan = first.reserve(40_000_000)
    later = PersistentSpendCap(path=path, run_id="tuning", phase="tuning")
    assert later.snapshot()["remaining_microusd"] == 5_000_000
    with pytest.raises(PaidRunCapReached):
        later.reserve(5_000_001)
    restored = PersistentSpendCap(path=path, run_id="baseline")
    restored.settle(orphan, 30_000_000)
    assert later.spent_microusd == 85_000_000
    assert later.reserved_microusd == 0


def test_per_run_cap_cannot_raise_lifetime_authorization(tmp_path):
    path = tmp_path / "budget.sqlite3"
    with pytest.raises(ValueError, match="authorized"):
        PersistentSpendCap(path=path, run_limit_microusd=MAX_CLOUDBANK_EVALUATION_MICROUSD + 1)
    cap = PersistentSpendCap(path=path, run_limit_microusd=1000)
    cap.settle(cap.reserve(900), 800)
    with pytest.raises(PaidRunCapReached):
        cap.reserve(201)
    assert PersistentSpendCap(path=path).snapshot()["remaining_microusd"] == MAX_CLOUDBANK_EVALUATION_MICROUSD - 800


def test_resume_cannot_change_original_run_limits(tmp_path):
    path = tmp_path / "budget.sqlite3"
    PersistentSpendCap(path=path, run_id="one", run_limit_microusd=1000)
    with pytest.raises(EvaluationBudgetError, match="resumed"):
        PersistentSpendCap(path=path, run_id="one", run_limit_microusd=2000)


def test_reservation_cannot_be_released_twice_or_by_another_run(tmp_path):
    path = tmp_path / "budget.sqlite3"
    first, second = PersistentSpendCap(path=path), PersistentSpendCap(path=path)
    reservation = first.reserve(100)
    with pytest.raises(EvaluationBudgetError, match="pending"):
        second.release(reservation)
    first.release(reservation)
    with pytest.raises(EvaluationBudgetError, match="pending"):
        first.release(reservation)


def test_charge_larger_than_bound_persistently_blocks_future_dispatch(tmp_path):
    path = tmp_path / "budget.sqlite3"
    cap = PersistentSpendCap(path=path)
    reservation = cap.reserve(10)
    with pytest.raises(EvaluationBudgetError, match="exceeded"):
        cap.settle(reservation, 11)
    restarted = PersistentSpendCap(path=path)
    assert restarted.spent_microusd == 11
    assert restarted.reached
    with pytest.raises(EvaluationBudgetError, match="blocked"):
        restarted.reserve(1)


def test_upward_correction_is_idempotent_and_reduces_both_remaining_allowances(tmp_path):
    path = tmp_path / "budget.sqlite3"
    cap = PersistentSpendCap(path=path, run_id="smoke", run_limit_microusd=1000)
    cap.settle(cap.reserve(600), 500)
    adjustment = {
        "adjustment_id": "verified-cache-price-correction", "amount_microusd": 200,
        "reason": "Verified cached-write price was higher than the original receipt.",
        "evidence_sha256": "a" * 64,
    }
    cap.adjust_upward(**adjustment)
    cap.adjust_upward(**adjustment)
    restarted = PersistentSpendCap(path=path, run_id="smoke", run_limit_microusd=1000)
    snapshot = restarted.snapshot()
    assert snapshot["spent_microusd"] == snapshot["run_spent_microusd"] == 700
    assert snapshot["remaining_microusd"] == MAX_CLOUDBANK_EVALUATION_MICROUSD - 700
    assert snapshot["accounting_adjustments_microusd"] == 200
    assert snapshot["physical_attempts_reserved"] == 1
    with pytest.raises(PaidRunCapReached):
        restarted.reserve(301)
    with pytest.raises(EvaluationBudgetError, match="cannot be changed"):
        restarted.adjust_upward(**{**adjustment, "amount_microusd": 201})
    assert restarted.snapshot()["accounting_adjustments_microusd"] == 200


def test_known_correction_can_be_recorded_during_pause_but_never_creates_allowance(tmp_path):
    cap = PersistentSpendCap(path=tmp_path / "budget.sqlite3", run_limit_microusd=100)
    with cap._transaction() as connection:
        connection.execute("UPDATE evaluation_budget SET blocked_reason = 'operator pause'")
    adjustment = {
        "adjustment_id": "paused-correction", "amount_microusd": 1,
        "reason": "Additional verified billing is recorded while dispatch remains paused.",
        "evidence_sha256": "b" * 64,
    }
    cap.adjust_upward(**adjustment)
    assert cap.snapshot()["blocked_reason"] == "operator pause"
    with pytest.raises(EvaluationBudgetError, match="blocked"):
        cap.reserve(1)
    for invalid in (0, -1, True):
        with pytest.raises(ValueError, match="positive"):
            cap.adjust_upward(**{**adjustment, "amount_microusd": invalid})
    cap.adjust_upward(**{**adjustment, "adjustment_id": "ceiling-correction", "amount_microusd": 100})
    assert cap.spent_microusd == 101
    assert "exceed" in cap.snapshot()["blocked_reason"]


def test_existing_network_filesystem_lock_is_not_expired_or_deleted(tmp_path):
    path = tmp_path / "budget.sqlite3"
    PersistentSpendCap(path=path)
    lock = path.with_name(path.name + ".lock")
    lock.mkdir()
    (lock / "owner.json").write_text('{"pid": 1, "created_at": "2000-01-01"}')
    with pytest.raises(EvaluationBudgetError, match="occupied"):
        PersistentSpendCap(path=path, mutex_timeout_seconds=0.01)
    assert lock.is_dir()


@pytest.fixture
def usage_factory(tmp_path):
    engine = create_engine("sqlite+pysqlite:///" + str(tmp_path / "usage.sqlite3"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()


def test_each_retry_is_reserved_and_uncertain_attempt_is_charged(tmp_path, usage_factory, monkeypatch):
    model = next(model for model in load_model_catalog().models.values() if model.family == "anthropic")
    cap = PersistentSpendCap(path=tmp_path / "budget.sqlite3")

    class Provider:
        provider, route, billing_source = "azure-foundry", "eval-test", "cloudbank"
        calls = 0

        def complete(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise LLMProviderError("timeout", provider=self.provider, retryable=True, billing_uncertain=True)
            return LLMResponse(text="ok", stop_reason="end_turn", usage={"input_tokens": 2, "output_tokens": 1}, latency_ms=1, model=model.id, provider=self.provider, route=self.route, billing_source=self.billing_source)

    provider = Provider()
    monkeypatch.setattr("app.llm.routing.time.sleep", lambda _: None)
    client = RetryingClient(MeteredClient(provider, model_spec=model, context=CallContext(user_id=None, request_id="retry-test", request_kind="eval-chat", charge_trial=False), charge_emergency=False, spend_cap=cap, session_factory=usage_factory), attempts=2)
    client.complete(system="test", messages=[{"role": "user", "content": "test"}], max_tokens=10)
    snapshot = cap.snapshot()
    assert provider.calls == 2
    assert snapshot["physical_attempts_reserved"] == 2
    assert snapshot["spent_microusd"] > model.pricing.cost_microusd({"input_tokens": 2, "output_tokens": 1})
    assert snapshot["reserved_microusd"] == 0
    with usage_factory() as session:
        assert session.query(LLMUsageEvent).count() == 2


def test_exhausted_shared_budget_stops_before_provider_dispatch(tmp_path, usage_factory):
    model = next(iter(load_model_catalog().models.values()))
    cap = PersistentSpendCap(path=tmp_path / "budget.sqlite3", run_limit_microusd=1)

    class Provider:
        calls = 0

        def complete(self, **kwargs):
            self.calls += 1
            raise AssertionError("dispatch must not happen")

    provider = Provider()
    client = MeteredClient(provider, model_spec=model, context=CallContext(user_id=None, request_id="blocked", request_kind="eval-chat", charge_trial=False), charge_emergency=False, spend_cap=cap, session_factory=usage_factory)
    with pytest.raises(PaidRunCapReached):
        client.complete(system="test", messages=[], max_tokens=100)
    assert provider.calls == 0


def test_evaluation_rejects_openrouter_even_with_legacy_permission_flag(tmp_path):
    router = LLMRouter(settings=get_settings())
    route = next(route.id for route in router.catalog.routes.values() if route.provider == "openrouter")
    for permission in (True, False):
        with pytest.raises(EvaluationConfigurationError, match="OpenRouter|CloudBank"):
            run_evaluation({"cases": [{"id": "no-call", "kind": "chat"}]}, suite_hash="unused", route_ids=[route], router=router, repetitions=1, smoke=False, case_ids=set(), allow_emergency_spend=permission, paid_run_cap_microusd=1000, spend_cap=PersistentSpendCap(path=tmp_path / "budget.sqlite3"))


def test_funded_launcher_excludes_direct_and_backup_credentials():
    values = funded_environment({"AZURE_OPENAI_API_KEY": "funded", "OPENROUTER_API_KEY": "backup", "ANTHROPIC_API_KEY": "direct", "GOOGLE_CLOUD_PROJECT": "project", "ABDA_DATABASE_URL": "production"})
    assert values == {"AZURE_OPENAI_API_KEY": "funded", "GOOGLE_CLOUD_PROJECT": "project"}


def test_evaluator_refuses_process_with_backup_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-test-key")
    with pytest.raises(EvaluationIsolationError, match="without OpenRouter"):
        assert_no_openrouter_credentials()


@pytest.mark.parametrize("url", ["https://openrouter.ai/api/v1/chat/completions", "https://api.openai.com/v1/responses", "https://api.anthropic.com/v1/messages", "https://generativelanguage.googleapis.com/v1beta/models/test:generateContent", "http://unit.services.ai.azure.com/anthropic/v1/messages", "https://unit.services.ai.azure.com.attacker.invalid/v1"])
def test_generation_egress_rejects_nonfunded_destinations(url):
    with pytest.raises(EvaluationIsolationError):
        check_funded_request("POST", url)


def test_egress_checks_redirect_targets_before_sending():
    calls = []

    def transport(request):
        calls.append(str(request.url))
        return httpx.Response(307, headers={"location": "https://openrouter.ai/api/v1/chat/completions"})

    with funded_network_only(), httpx.Client(transport=httpx.MockTransport(transport), follow_redirects=True) as client:
        with pytest.raises(EvaluationIsolationError):
            client.post("https://unit.services.ai.azure.com/anthropic/v1/messages", json={})
    assert calls == ["https://unit.services.ai.azure.com/anthropic/v1/messages"]


def test_public_catalog_get_and_funded_auth_are_allowed():
    check_funded_request("GET", "https://openrouter.ai/api/v1/models")
    check_funded_request("POST", "https://oauth2.googleapis.com/token")
    check_funded_request("POST", "https://us-central1-aiplatform.googleapis.com/v1/projects/p/locations/us-central1/publishers/google/models/m:generateContent")
