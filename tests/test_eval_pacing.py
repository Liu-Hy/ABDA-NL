"""Operational pacing cannot reset spending or permit deadline overrun."""
from __future__ import annotations

import multiprocessing
from pathlib import Path

import pytest

from app.evals.budget import PersistentSpendCap
from app.evals.evidence import RecordingClient
from app.evals.pacing import DeploymentRate, EvaluationPacer, parse_rate_limits
from app.llm.client import LLMRequestDeadlineError, LLMResponse, remaining_request_seconds


def test_deployment_schedule_survives_new_runs_and_keeps_budget_unchanged(monkeypatch, tmp_path):
    clock = [1000.0]
    monkeypatch.setattr("app.evals.pacing.time.time", lambda: clock[0])
    monkeypatch.setattr("app.evals.pacing.time.sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    path = tmp_path / "shared.sqlite3"
    rate = DeploymentRate(60, 60000)
    first = EvaluationPacer(budget=PersistentSpendCap(path=path), deployment="azure:model", rate=rate, physical_attempts=2)
    request = {"system": "synthetic", "messages": [], "max_tokens": 100}
    one = first.before_call(request)
    second_budget = PersistentSpendCap(path=path)
    restarted = EvaluationPacer(budget=second_budget, deployment="azure:model", rate=rate, physical_attempts=2)
    two = restarted.before_call(request)
    assert one["wait_ms"] == 0
    assert two["wait_ms"] >= 2500
    assert two["physical_attempts_allowed"] == 2
    independent = EvaluationPacer(budget=second_budget, deployment="azure:other", rate=rate, physical_attempts=2)
    assert independent.before_call(request)["wait_ms"] == 0
    assert second_budget.snapshot()["spent_microusd"] == 0
    assert second_budget.snapshot()["reserved_microusd"] == 0


def test_recording_client_waits_before_provider_dispatch_and_records_pacing():
    events = []

    class Pacer:
        def before_call(self, request):
            assert request["max_tokens"] == 100
            events.append("pace")
            return {"wait_ms": 2500}

    class Client:
        def complete(self, **kwargs):
            events.append("dispatch")
            return LLMResponse(text="answer", stop_reason="stop", usage={}, latency_ms=10, model="synthetic")

    recorder = RecordingClient(Client(), pacer=Pacer())
    recorder.complete(system="synthetic", messages=[], max_tokens=100)
    assert events == ["pace", "dispatch"]
    assert recorder.calls[0]["pacing"]["wait_ms"] == 2500
    assert "provider_invoked_at" in recorder.calls[0]


def test_one_case_deadline_extends_only_by_recorded_pacing_not_by_another_model_call(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("app.evals.evidence.time.monotonic", lambda: clock[0])

    class Pacer:
        def before_call(self, request):
            clock[0] += 10
            return {"wait_ms": 10000}

    class Raw:
        request_deadline = None

        def complete(self, **kwargs):
            remaining_request_seconds(self.request_deadline, provider="synthetic")
            clock[0] += 7
            return LLMResponse(text="answer", stop_reason="stop", usage={}, latency_ms=7000, model="synthetic")

    class Wrapper:
        deadline = None

        def __init__(self, inner):
            self.inner = inner

        def complete(self, **kwargs):
            remaining_request_seconds(self.deadline, provider="synthetic")
            return self.inner.complete(**kwargs)

    raw = Raw()
    wrapper = Wrapper(Wrapper(raw))
    recorder = RecordingClient(wrapper, pacer=Pacer(), request_timeout_seconds=180)
    recorder.complete(system="synthetic", messages=[], max_tokens=100)
    recorder.complete(system="synthetic", messages=[], max_tokens=100)
    assert raw.request_deadline == wrapper.deadline == wrapper.inner.deadline == 300
    assert recorder.pacing_seconds == 20
    assert sum(call["pacing"]["elapsed_seconds"] for call in recorder.calls) == 20
    clock[0] = 301
    with pytest.raises(LLMRequestDeadlineError):
        recorder.complete(system="synthetic", messages=[], max_tokens=100)


def _pace_in_process(path, barrier, results):
    budget = PersistentSpendCap(path=Path(path))
    pacer = EvaluationPacer(budget=budget, deployment="shared:model", rate=DeploymentRate(60, 60000), physical_attempts=1)
    barrier.wait(timeout=20)
    receipt = pacer.before_call({"system": "synthetic", "messages": [], "max_tokens": 100})
    results.put(receipt["scheduled_at_unix"])


def test_separate_workers_share_deployment_schedule(tmp_path):
    path = tmp_path / "shared.sqlite3"
    PersistentSpendCap(path=path)
    context = multiprocessing.get_context("spawn")
    barrier, results = context.Barrier(2), context.Queue()
    processes = [context.Process(target=_pace_in_process, args=(str(path), barrier, results)) for _ in range(2)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0
    times = sorted(results.get(timeout=2) for _ in processes)
    assert times[1] - times[0] >= 1.24


@pytest.mark.parametrize("values", [["broken"], ["model:0:100"], ["model:10:0"], ["model:1:100", "model:2:200"]])
def test_ambiguous_or_nonpositive_pacing_limits_are_rejected(values):
    with pytest.raises(ValueError):
        parse_rate_limits(values)
