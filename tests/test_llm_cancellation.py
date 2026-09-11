"""Cancellation stops paid work without losing accounting or HTTP errors."""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import anyio
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
import pytest

from app.api.llm_cancellation import run_cancellable_llm
from app.llm.client import (
    LLMRequestCancelledError,
    cancellable_request,
    invoke_before_deadline,
)
from app.llm.providers import LLMProviderError
from app.llm.routing import CircuitRegistry, FailoverClient, RetryingClient


def test_cancel_before_dispatch_never_calls_provider():
    cancelled = threading.Event()
    calls = []
    with cancellable_request(cancelled):
        cancelled.set()
        with pytest.raises(LLMRequestCancelledError) as caught:
            invoke_before_deadline(
                lambda: calls.append(True), deadline=None,
                provider="test", client=SimpleNamespace(),
            )
    assert calls == []
    assert not caught.value.billing_uncertain


def test_cancel_active_provider_closes_transport_and_blocks_retry_and_fallback():
    cancelled, started, closed = threading.Event(), threading.Event(), threading.Event()
    calls = []

    class Provider:
        provider, route = "test", "funded"
        request_dispatched = False

        def close(self):
            closed.set()

        def complete(self, **kwargs):
            def call():
                calls.append("funded")
                self.request_dispatched = True
                started.set()
                assert closed.wait(2)
                raise LLMProviderError("closed socket", provider="test", retryable=True,
                                       outage_candidate=True, billing_uncertain=True)
            return invoke_before_deadline(call, deadline=None, provider=self.provider, client=self)

    fallback = SimpleNamespace(complete=lambda **kw: calls.append("fallback"))
    circuit = CircuitRegistry()
    client = FailoverClient(RetryingClient(Provider(), attempts=2), fallback,
                            cooldown_seconds=15, circuits=circuit)

    def stop():
        assert started.wait(2)
        cancelled.set()

    stopper = threading.Thread(target=stop)
    stopper.start()
    try:
        with cancellable_request(cancelled), pytest.raises(LLMProviderError) as caught:
            client.complete()
        assert caught.value.error_type == "request_cancelled"
        assert caught.value.billing_uncertain
        assert not caught.value.retryable and not caught.value.outage_candidate
        assert calls == ["funded"]
        assert closed.is_set()
        assert circuit.primary_allowed("funded")
    finally:
        closed.set()
        stopper.join(timeout=2)


def test_cancellation_during_retry_delay_prevents_second_call(monkeypatch):
    cancelled = threading.Event()
    calls = []

    def call(**kwargs):
        calls.append(True)
        raise LLMProviderError("busy", provider="test", retryable=True, outage_candidate=True)

    monkeypatch.setattr("app.llm.routing.time.sleep", lambda delay: cancelled.set())
    with cancellable_request(cancelled), pytest.raises(LLMRequestCancelledError):
        RetryingClient(SimpleNamespace(complete=call, provider="test"), attempts=2).complete()
    assert calls == [True]


def _test_app(operation):
    app = FastAPI()

    @app.middleware("http")
    async def context(request, call_next):
        return await call_next(request)

    @app.post("/chat")
    async def chat(request: Request):
        await request.json()
        return await run_cancellable_llm(request, operation)

    return app


@pytest.mark.parametrize("status", [400, 401, 403, 429, 503])
def test_async_cancellation_wrapper_preserves_http_errors(status):
    def operation():
        raise HTTPException(status, detail={"code": "expected"})
    with TestClient(_test_app(operation)) as client:
        response = client.post("/chat", json={})
    assert response.status_code == status
    assert response.json() == {"detail": {"code": "expected"}}


def test_asgi_disconnect_reaches_provider_behind_http_middleware():
    started, closed = threading.Event(), threading.Event()
    errors = []

    def operation():
        def call():
            started.set()
            assert closed.wait(2)
            return "late response"
        try:
            return invoke_before_deadline(
                call, deadline=time.monotonic() + 3, provider="test",
                client=SimpleNamespace(close=closed.set, request_dispatched=True),
            )
        except LLMRequestCancelledError as exc:
            errors.append(exc)
            raise

    async def exercise():
        request_sent = False
        async def receive():
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": b"{}", "more_body": False}
            while not started.is_set():
                await anyio.sleep(0.01)
            return {"type": "http.disconnect"}

        async def send(message):
            pass

        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "POST", "scheme": "http", "path": "/chat", "raw_path": b"/chat",
            "query_string": b"", "headers": [(b"content-type", b"application/json")],
            "client": ("127.0.0.1", 12345), "server": ("test", 80),
        }
        with anyio.fail_after(3):
            await _test_app(operation)(scope, receive, send)

    try:
        anyio.run(exercise)
        assert started.is_set() and closed.is_set()
        assert len(errors) == 1 and errors[0].billing_uncertain
    finally:
        closed.set()
