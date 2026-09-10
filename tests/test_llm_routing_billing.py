"""Billing, retry, failover, and BYOK routing invariants."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.models import (
    Base,
    EmergencyBudget,
    EmergencyUsageReservation,
    LLMUsageEvent,
    TrialGrant,
    TrialProgram,
    UsageReservation,
    User,
    utc_now,
)
from app.llm.catalog import load_model_catalog
from app.llm.client import LLMRequestValidationError, LLMResponse, ToolCallResponse
from app.llm.providers import LLMProviderError
from app.llm.routing import (
    BYOKCredential,
    BYOKValidationError,
    CallContext,
    CircuitRegistry,
    FailoverClient,
    LLMRouter,
    LocalSpendCap,
    MeteredClient,
    PaidRunCapReached,
    RetryingClient,
)
from app.services.emergency_budget import (
    EmergencyBudgetExceededError,
    get_emergency_balance,
)
from app.services.llm_billing import (
    reconcile_stale_llm_reservations,
    release_llm_call,
    reserve_llm_call,
    settle_llm_call,
    usage_event,
)
from app.services.trials import get_trial_balance
from helpers.catalogs import admit_catalog_models


@pytest.fixture
def billing_factory(tmp_path):
    path = tmp_path / "billing.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        user = User(email="metered@example.edu", email_verified=True)
        session.add_all(
            [
                user,
                TrialProgram(
                    key="global",
                    enabled=True,
                    max_users=1,
                    grant_microusd=5_000_000,
                    budget_microusd=5_000_000,
                    activation_count=1,
                    allocated_microusd=5_000_000,
                ),
                EmergencyBudget(
                    key="openrouter",
                    enabled=True,
                    hard_limit_microusd=1_000_000,
                ),
            ]
        )
        session.flush()
        session.add(TrialGrant(user_id=user.id, granted_microusd=5_000_000))
        session.commit()
        factory.user_id = user.id
    yield factory
    engine.dispose()


def test_openrouter_budget_above_500_requires_explicit_ack(monkeypatch):
    monkeypatch.setenv("ABDA_OPENROUTER_BUDGET_MICROUSD", "500000001")
    monkeypatch.delenv("ABDA_OPENROUTER_BUDGET_ACK", raising=False)
    with pytest.raises(RuntimeError, match="requires ABDA_OPENROUTER_BUDGET_ACK"):
        Settings.from_environment()

    monkeypatch.setenv(
        "ABDA_OPENROUTER_BUDGET_ACK", "I_ACCEPT_UP_TO_1000_USD"
    )
    assert Settings.from_environment().openrouter_budget_microusd == 500_000_001


def test_openrouter_budget_cannot_exceed_1000(monkeypatch):
    monkeypatch.setenv("ABDA_OPENROUTER_BUDGET_MICROUSD", "1000000001")
    monkeypatch.setenv(
        "ABDA_OPENROUTER_BUDGET_ACK", "I_ACCEPT_UP_TO_1000_USD"
    )
    with pytest.raises(RuntimeError, match="cannot exceed"):
        Settings.from_environment()


def test_combined_reservation_is_atomic_when_emergency_budget_is_too_low(
    billing_factory,
):
    with billing_factory() as session:
        budget = session.get(EmergencyBudget, "openrouter")
        budget.hard_limit_microusd = 50
        session.commit()
        with pytest.raises(EmergencyBudgetExceededError):
            reserve_llm_call(
                session,
                amount_microusd=60,
                user_id=billing_factory.user_id,
                provider="openrouter",
                route="fallback",
                model="test-model",
                request_kind="chat",
                charge_trial=True,
                charge_emergency=True,
            )
        assert get_trial_balance(
            session, billing_factory.user_id
        ).reserved_microusd == 0
        assert get_emergency_balance(session).reserved_microusd == 0
        assert session.scalar(select(UsageReservation)) is None


def test_combined_settlement_updates_both_ledgers_and_audit_event(billing_factory):
    with billing_factory() as session:
        reservation = reserve_llm_call(
            session,
            amount_microusd=100,
            user_id=billing_factory.user_id,
            provider="openrouter",
            route="fallback",
            model="test-model",
            request_kind="propose",
            charge_trial=True,
            charge_emergency=True,
        )
        event = usage_event(
            request_id="request-1",
            user_id=billing_factory.user_id,
            provider="openrouter",
            route="fallback",
            model="test-model",
            billing_source="openrouter-emergency",
            request_kind="propose",
            status="succeeded",
            usage={"input_tokens": 10, "output_tokens": 5},
            cost_microusd=40,
            latency_ms=50,
        )
        settle_llm_call(session, reservation, actual_microusd=40, event=event)
        trial = get_trial_balance(session, billing_factory.user_id)
        emergency = get_emergency_balance(session)
        assert trial.spent_microusd == 40
        assert trial.reserved_microusd == 0
        assert emergency.spent_microusd == 40
        assert emergency.reserved_microusd == 0
        stored = session.scalar(select(LLMUsageEvent))
        assert stored.request_id == "request-1"
        assert stored.input_tokens == 10


def test_combined_release_restores_both_balances(billing_factory):
    with billing_factory() as session:
        reservation = reserve_llm_call(
            session,
            amount_microusd=100,
            user_id=billing_factory.user_id,
            provider="openrouter",
            route="fallback",
            model="test-model",
            request_kind="chat",
            charge_trial=True,
            charge_emergency=True,
        )
        release_llm_call(session, reservation)
        assert get_trial_balance(
            session, billing_factory.user_id
        ).available_microusd == 5_000_000
        assert get_emergency_balance(session).available_microusd == 1_000_000


def test_emergency_cap_is_exact_under_concurrency(billing_factory):
    with billing_factory() as session:
        budget = session.get(EmergencyBudget, "openrouter")
        budget.hard_limit_microusd = 100
        session.commit()

    def reserve(index: int) -> bool:
        with billing_factory() as session:
            try:
                reserve_llm_call(
                    session,
                    amount_microusd=10,
                    user_id=None,
                    provider="openrouter",
                    route="fallback",
                    model=f"model-{index}",
                    request_kind="chat",
                    charge_trial=False,
                    charge_emergency=True,
                )
                return True
            except EmergencyBudgetExceededError:
                return False

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(reserve, range(30)))
    assert sum(outcomes) == 10
    with billing_factory() as session:
        balance = get_emergency_balance(session)
        assert balance.reserved_microusd == 100
        assert balance.available_microusd == 0


def test_stale_reservations_are_charged_conservatively_after_worker_loss(
    billing_factory,
):
    with billing_factory() as session:
        reservation = reserve_llm_call(
            session,
            amount_microusd=100,
            user_id=billing_factory.user_id,
            provider="openrouter",
            route="fallback",
            model="test-model",
            request_kind="chat",
            charge_trial=True,
            charge_emergency=True,
        )
        trial = session.get(UsageReservation, reservation.trial_reservation_id)
        emergency = session.get(
            EmergencyUsageReservation, reservation.emergency_reservation_id
        )
        trial.expires_at = utc_now() - timedelta(minutes=1)
        emergency.expires_at = utc_now() - timedelta(minutes=1)
        session.commit()
        assert reconcile_stale_llm_reservations(session) == (1, 1)
        assert get_trial_balance(
            session, billing_factory.user_id
        ).spent_microusd == 100
        assert get_trial_balance(session, billing_factory.user_id).reserved_microusd == 0
        assert session.get(TrialProgram, "global").spent_microusd == 100
        assert get_emergency_balance(session).spent_microusd == 100
        assert get_emergency_balance(session).reserved_microusd == 0
        assert trial.status == "expired_charged"
        assert trial.actual_microusd == 100
        assert emergency.status == "expired_charged"
        assert emergency.actual_microusd == 100


class _SuccessfulClient:
    model = "deepseek-v4-flash"
    provider = "openrouter"
    billing_source = "openrouter-emergency"
    route = "fallback"

    def __init__(self):
        self.calls = 0

    def complete(self, **_kwargs):
        self.calls += 1
        return LLMResponse(
            text="answer",
            stop_reason="stop",
            usage={"input_tokens": 100, "output_tokens": 50},
            latency_ms=25,
            model=self.model,
            provider=self.provider,
            billing_source=self.billing_source,
            route=self.route,
        )

    def tool_call(self, **_kwargs):
        raise AssertionError("not used")


class _ClosableClient(_SuccessfulClient):
    def __init__(self):
        super().__init__()
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


class _WrongResponseTypeClient(_SuccessfulClient):
    def complete(self, **_kwargs):
        return ToolCallResponse(
            tool_name="unexpected",
            tool_input={},
            stop_reason="tool_use",
            usage={"input_tokens": 1, "output_tokens": 1},
            latency_ms=1,
            model=self.model,
            provider=self.provider,
            billing_source=self.billing_source,
            route=self.route,
        )

    def tool_call(self, **_kwargs):
        return LLMResponse(
            text="unexpected",
            stop_reason="stop",
            usage={"input_tokens": 1, "output_tokens": 1},
            latency_ms=1,
            model=self.model,
            provider=self.provider,
            billing_source=self.billing_source,
            route=self.route,
        )


class _FailingClient(_SuccessfulClient):
    def complete(self, **_kwargs):
        raise LLMProviderError(
            "temporary failure",
            provider=self.provider,
            status_code=503,
            retryable=True,
            outage_candidate=True,
        )


class _ProviderCostClient(_SuccessfulClient):
    def complete(self, **_kwargs):
        response = super().complete(**_kwargs)
        response.provider_cost_microusd = 100
        return response


class _NoBillingEvidenceClient(_SuccessfulClient):
    def complete(self, **_kwargs):
        return LLMResponse(
            text="answer without usage metadata",
            stop_reason="stop",
            usage={},
            latency_ms=25,
            model=self.model,
            provider=self.provider,
            billing_source=self.billing_source,
            route=self.route,
        )


class _ChargedFailingClient(_SuccessfulClient):
    def complete(self, **_kwargs):
        raise LLMProviderError(
            "temporary billed failure",
            provider=self.provider,
            status_code=429,
            retryable=True,
            outage_candidate=True,
            error_type="rate_limit_exceeded",
            usage={"input_tokens": 100, "output_tokens": 0},
            provider_cost_microusd=100,
        )


class _UsageOnlyFailingClient(_SuccessfulClient):
    def complete(self, **_kwargs):
        raise LLMProviderError(
            "temporary unbilled failure",
            provider=self.provider,
            status_code=503,
            retryable=True,
            outage_candidate=True,
            usage={"input_tokens": 100, "output_tokens": 0},
        )


class _AmbiguousFailingClient(_SuccessfulClient):
    def complete(self, **_kwargs):
        raise LLMProviderError(
            "response was lost after dispatch",
            provider=self.provider,
            retryable=True,
            outage_candidate=True,
            billing_uncertain=True,
        )


class _RawTransportFailingClient(_SuccessfulClient):
    def __init__(self, error_type):
        super().__init__()
        self.error_type = error_type

    def complete(self, **_kwargs):
        request = httpx.Request("POST", "https://provider.invalid/v1/messages")
        raise self.error_type("synthetic transport failure", request=request)


class _RawTransportThenSuccessClient(_SuccessfulClient):
    def complete(self, **kwargs):
        del kwargs
        self.calls += 1
        if self.calls == 1:
            request = httpx.Request(
                "POST", "https://provider.invalid/v1/messages"
            )
            raise httpx.ReadTimeout(
                "synthetic response timeout",
                request=request,
            )
        return LLMResponse(
            text="answer",
            stop_reason="stop",
            usage={"input_tokens": 100, "output_tokens": 50},
            latency_ms=25,
            model=self.model,
            provider=self.provider,
            billing_source=self.billing_source,
            route=self.route,
        )


def test_metered_client_settles_actual_cost_and_records_route(billing_factory):
    model = load_model_catalog().models["deepseek-v4-flash"]
    client = MeteredClient(
        _SuccessfulClient(),
        model_spec=model,
        context=CallContext(
            user_id=billing_factory.user_id,
            request_id="metered-success",
            request_kind="chat",
            charge_trial=True,
        ),
        charge_emergency=True,
        session_factory=billing_factory,
    )
    response = client.complete(
        system="system",
        messages=[{"role": "user", "content": "question"}],
        max_tokens=100,
    )
    assert response.cost_microusd == model.cost_microusd(response.usage)
    with billing_factory() as session:
        event = session.scalar(
            select(LLMUsageEvent).where(
                LLMUsageEvent.request_id == "metered-success"
            )
        )
        assert event.status == "succeeded"
        assert event.route == "fallback"
        assert get_trial_balance(session, billing_factory.user_id).spent_microusd > 0
        assert get_emergency_balance(session).spent_microusd > 0


def test_composite_client_close_reaches_each_physical_provider_once(
    billing_factory,
):
    model = load_model_catalog().models["deepseek-v4-flash"]
    primary_physical = _ClosableClient()
    fallback_physical = _ClosableClient()
    context = CallContext(
        user_id=None,
        request_id="close-composite",
        request_kind="test",
        charge_trial=False,
    )
    primary = RetryingClient(
        MeteredClient(
            primary_physical,
            model_spec=model,
            context=context,
            charge_emergency=False,
            session_factory=billing_factory,
        ),
        attempts=1,
    )
    fallback = RetryingClient(
        MeteredClient(
            fallback_physical,
            model_spec=model,
            context=context,
            charge_emergency=False,
            session_factory=billing_factory,
        ),
        attempts=1,
    )

    FailoverClient(primary, fallback, cooldown_seconds=60).close()

    assert primary_physical.close_calls == 1
    assert fallback_physical.close_calls == 1


def test_metered_client_rejects_wrong_response_types_without_asserts(
    billing_factory,
):
    model = load_model_catalog().models["deepseek-v4-flash"]
    client = MeteredClient(
        _WrongResponseTypeClient(),
        model_spec=model,
        context=CallContext(
            user_id=None,
            request_id="wrong-response-type",
            request_kind="test",
            charge_trial=False,
        ),
        charge_emergency=False,
        session_factory=billing_factory,
    )
    common = {
        "system": "system",
        "messages": [{"role": "user", "content": "question"}],
        "max_tokens": 10,
    }
    with pytest.raises(TypeError, match="complete returned"):
        client.complete(**common)
    with pytest.raises(TypeError, match="tool_call returned"):
        client.tool_call(tool={"name": "test", "input_schema": {}}, **common)


def test_local_spend_cap_blocks_before_call_and_releases_reservation(
    billing_factory,
):
    model = load_model_catalog().models["deepseek-v4-flash"]
    cap = LocalSpendCap(1)
    inner = _SuccessfulClient()
    client = MeteredClient(
        inner,
        model_spec=model,
        context=CallContext(
            user_id=None,
            request_id="capped-before-call",
            request_kind="eval-chat",
            charge_trial=False,
        ),
        charge_emergency=False,
        spend_cap=cap,
        session_factory=billing_factory,
    )
    with pytest.raises(PaidRunCapReached):
        client.complete(
            system="system",
            messages=[{"role": "user", "content": "question"}],
            max_tokens=100,
        )
    assert inner.calls == 0
    assert cap.spent_microusd == 0
    assert cap.reserved_microusd == 0
    assert cap.reached is True


def test_local_spend_cap_is_exact_under_concurrency():
    cap = LocalSpendCap(100)

    def reserve(_index):
        try:
            return cap.reserve(10)
        except PaidRunCapReached:
            return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        reservations = list(executor.map(reserve, range(30)))
    accepted = [reservation for reservation in reservations if reservation is not None]
    assert len(accepted) == 10
    assert cap.reserved_microusd == 100
    assert cap.spent_microusd == 0
    assert cap.reached is True

    for reservation in accepted:
        cap.release(reservation)
    assert cap.reserved_microusd == 0


def test_local_spend_cap_settles_provider_cost_and_credit_fee(billing_factory):
    model = load_model_catalog().models["deepseek-v4-flash"]
    cap = LocalSpendCap(1_000_000)
    client = MeteredClient(
        _ProviderCostClient(),
        model_spec=model,
        use_provider_reported_cost=True,
        billing_multiplier=Decimal("1.055"),
        context=CallContext(
            user_id=None,
            request_id="capped-settlement",
            request_kind="eval-chat",
            charge_trial=False,
        ),
        charge_emergency=False,
        spend_cap=cap,
        session_factory=billing_factory,
    )
    response = client.complete(
        system="system",
        messages=[{"role": "user", "content": "question"}],
        max_tokens=100,
    )
    assert response.cost_microusd == 106
    assert cap.spent_microusd == 106
    assert cap.reserved_microusd == 0


def test_metered_openrouter_cost_includes_credit_purchase_overhead(billing_factory):
    model = load_model_catalog().models["deepseek-v4-flash"]
    client = MeteredClient(
        _ProviderCostClient(),
        model_spec=model,
        use_provider_reported_cost=True,
        billing_multiplier=Decimal("1.055"),
        context=CallContext(
            user_id=billing_factory.user_id,
            request_id="metered-provider-cost",
            request_kind="chat",
            charge_trial=True,
        ),
        charge_emergency=True,
        session_factory=billing_factory,
    )
    response = client.complete(
        system="system",
        messages=[{"role": "user", "content": "question"}],
        max_tokens=100,
    )
    assert response.provider_cost_microusd == 100
    assert response.cost_microusd == 106
    with billing_factory() as session:
        event = session.scalar(
            select(LLMUsageEvent).where(
                LLMUsageEvent.request_id == "metered-provider-cost"
            )
        )
        assert event.cost_microusd == 106
        assert get_trial_balance(session, billing_factory.user_id).spent_microusd == 106
        assert get_emergency_balance(session).spent_microusd == 106


def test_metered_client_settles_a_provider_charged_failure(billing_factory):
    model = load_model_catalog().models["deepseek-v4-flash"]
    client = MeteredClient(
        _ChargedFailingClient(),
        model_spec=model,
        use_provider_reported_cost=True,
        billing_multiplier=Decimal("1.055"),
        context=CallContext(
            user_id=billing_factory.user_id,
            request_id="metered-charged-failure",
            request_kind="chat",
            charge_trial=True,
        ),
        charge_emergency=True,
        session_factory=billing_factory,
    )
    with pytest.raises(LLMProviderError):
        client.complete(
            system="system",
            messages=[{"role": "user", "content": "question"}],
            max_tokens=100,
        )
    with billing_factory() as session:
        event = session.scalar(
            select(LLMUsageEvent).where(
                LLMUsageEvent.request_id == "metered-charged-failure"
            )
        )
        assert event.status == "failed"
        assert event.error_type == "LLMProviderError:rate_limit_exceeded"
        assert event.cost_microusd == 106
        assert get_trial_balance(session, billing_factory.user_id).spent_microusd == 106
        assert get_emergency_balance(session).spent_microusd == 106


def test_metered_client_estimates_openrouter_failure_cost_from_reported_usage(
    billing_factory,
):
    model = load_model_catalog().models["deepseek-v4-flash"]
    client = MeteredClient(
        _UsageOnlyFailingClient(),
        model_spec=model,
        use_provider_reported_cost=True,
        billing_multiplier=Decimal("1.055"),
        context=CallContext(
            user_id=billing_factory.user_id,
            request_id="metered-unbilled-failure",
            request_kind="chat",
            charge_trial=True,
        ),
        charge_emergency=True,
        session_factory=billing_factory,
    )
    with pytest.raises(LLMProviderError):
        client.complete(
            system="system",
            messages=[{"role": "user", "content": "question"}],
            max_tokens=100,
        )
    with billing_factory() as session:
        event = session.scalar(
            select(LLMUsageEvent).where(
                LLMUsageEvent.request_id == "metered-unbilled-failure"
            )
        )
        assert event.cost_microusd == 10
        assert get_trial_balance(session, billing_factory.user_id).spent_microusd == 10
        assert get_emergency_balance(session).spent_microusd == 10


def test_metered_client_charges_full_reservation_when_billing_is_uncertain(
    billing_factory,
):
    model = load_model_catalog().models["deepseek-v4-flash"]
    client = MeteredClient(
        _AmbiguousFailingClient(),
        model_spec=model,
        use_provider_reported_cost=True,
        billing_multiplier=Decimal("1.055"),
        context=CallContext(
            user_id=billing_factory.user_id,
            request_id="metered-uncertain-failure",
            request_kind="chat",
            charge_trial=True,
        ),
        charge_emergency=True,
        session_factory=billing_factory,
    )
    with pytest.raises(LLMProviderError):
        client.complete(
            system="system",
            messages=[{"role": "user", "content": "question"}],
            max_tokens=100,
        )

    with billing_factory() as session:
        event = session.scalar(
            select(LLMUsageEvent).where(
                LLMUsageEvent.request_id == "metered-uncertain-failure"
            )
        )
        trial_reservation = session.scalar(
            select(UsageReservation).where(
                UsageReservation.request_kind == "chat"
            )
        )
        emergency_reservation = session.scalar(
            select(EmergencyUsageReservation).where(
                EmergencyUsageReservation.request_kind == "chat"
            )
        )
        assert event.error_type == "LLMProviderError:billing_uncertain"
        assert event.cost_microusd == trial_reservation.reserved_microusd
        assert trial_reservation.actual_microusd == trial_reservation.reserved_microusd
        assert emergency_reservation.actual_microusd == event.cost_microusd
        assert get_trial_balance(
            session, billing_factory.user_id
        ).spent_microusd == event.cost_microusd
        assert get_trial_balance(
            session, billing_factory.user_id
        ).reserved_microusd == 0
        assert get_emergency_balance(session).spent_microusd == event.cost_microusd
        assert get_emergency_balance(session).reserved_microusd == 0


@pytest.mark.parametrize(
    ("error_type", "expected_cost_kind"),
    [
        (httpx.ReadTimeout, "full_reservation"),
        (httpx.ConnectError, "released"),
    ],
)
def test_metered_client_classifies_raw_transport_before_retry_layer(
    billing_factory,
    error_type,
    expected_cost_kind,
):
    model = load_model_catalog().models["deepseek-v4-flash"]
    client = MeteredClient(
        _RawTransportFailingClient(error_type),
        model_spec=model,
        context=CallContext(
            user_id=billing_factory.user_id,
            request_id=f"metered-{error_type.__name__}",
            request_kind="chat",
            charge_trial=True,
        ),
        charge_emergency=True,
        session_factory=billing_factory,
    )

    with pytest.raises(error_type):
        client.complete(
            system="system",
            messages=[{"role": "user", "content": "question"}],
            max_tokens=100,
        )

    with billing_factory() as session:
        event = session.scalar(
            select(LLMUsageEvent).where(
                LLMUsageEvent.request_id == f"metered-{error_type.__name__}"
            )
        )
        trial_reservation = session.scalar(
            select(UsageReservation).where(
                UsageReservation.request_kind == "chat"
            )
        )
        assert event.status == "failed"
        assert get_trial_balance(
            session, billing_factory.user_id
        ).reserved_microusd == 0
        assert get_emergency_balance(session).reserved_microusd == 0
        if expected_cost_kind == "full_reservation":
            assert event.error_type == "ReadTimeout:billing_uncertain"
            assert event.cost_microusd == trial_reservation.reserved_microusd
            assert trial_reservation.actual_microusd == event.cost_microusd
        else:
            assert event.error_type == "ConnectError"
            assert event.cost_microusd == 0
            assert trial_reservation.status == "released"


def test_retrying_metered_client_reserves_each_physical_attempt(
    billing_factory,
    monkeypatch,
):
    monkeypatch.setattr("app.llm.routing.time.sleep", lambda _seconds: None)
    model = load_model_catalog().models["deepseek-v4-flash"]
    raw = _RawTransportThenSuccessClient()
    metered = MeteredClient(
        raw,
        model_spec=model,
        context=CallContext(
            user_id=billing_factory.user_id,
            request_id="metered-two-attempts",
            request_kind="chat",
            charge_trial=True,
        ),
        charge_emergency=True,
        session_factory=billing_factory,
    )
    response = RetryingClient(metered, attempts=2).complete(
        system="system",
        messages=[{"role": "user", "content": "question"}],
        max_tokens=100,
    )

    assert response.text == "answer"
    assert raw.calls == 2
    with billing_factory() as session:
        events = list(
            session.scalars(
                select(LLMUsageEvent)
                .where(LLMUsageEvent.request_id == "metered-two-attempts")
                .order_by(LLMUsageEvent.created_at, LLMUsageEvent.id)
            )
        )
        trial_reservations = list(
            session.scalars(
                select(UsageReservation).where(
                    UsageReservation.request_kind == "chat"
                )
            )
        )
        emergency_reservations = list(
            session.scalars(
                select(EmergencyUsageReservation).where(
                    EmergencyUsageReservation.request_kind == "chat"
                )
            )
        )
        assert [event.status for event in events] == ["failed", "succeeded"]
        assert events[0].error_type == "ReadTimeout:billing_uncertain"
        assert events[0].cost_microusd == trial_reservations[0].reserved_microusd
        assert len(trial_reservations) == 2
        assert len(emergency_reservations) == 2
        assert all(item.status == "settled" for item in trial_reservations)
        assert all(item.status == "settled" for item in emergency_reservations)
        assert get_trial_balance(
            session, billing_factory.user_id
        ).reserved_microusd == 0
        assert get_emergency_balance(session).reserved_microusd == 0


def test_metered_client_conservatively_charges_success_without_billing_evidence(
    billing_factory,
):
    model = load_model_catalog().models["deepseek-v4-flash"]
    client = MeteredClient(
        _NoBillingEvidenceClient(),
        model_spec=model,
        use_provider_reported_cost=True,
        billing_multiplier=Decimal("1.055"),
        context=CallContext(
            user_id=billing_factory.user_id,
            request_id="metered-uncertain-success",
            request_kind="chat",
            charge_trial=True,
        ),
        charge_emergency=True,
        session_factory=billing_factory,
    )

    response = client.complete(
        system="system",
        messages=[{"role": "user", "content": "question"}],
        max_tokens=100,
    )

    with billing_factory() as session:
        event = session.scalar(
            select(LLMUsageEvent).where(
                LLMUsageEvent.request_id == "metered-uncertain-success"
            )
        )
        trial_reservation = session.scalar(
            select(UsageReservation).where(
                UsageReservation.request_kind == "chat"
            )
        )
        emergency_reservation = session.scalar(
            select(EmergencyUsageReservation).where(
                EmergencyUsageReservation.request_kind == "chat"
            )
        )
        assert event.status == "succeeded"
        assert event.error_type == "billing_uncertain"
        assert response.cost_microusd == trial_reservation.reserved_microusd
        assert trial_reservation.actual_microusd == response.cost_microusd
        assert emergency_reservation.actual_microusd == response.cost_microusd
        assert get_trial_balance(
            session, billing_factory.user_id
        ).spent_microusd == response.cost_microusd
        assert get_emergency_balance(session).spent_microusd == response.cost_microusd


def test_metered_client_releases_reservation_on_provider_failure(billing_factory):
    model = load_model_catalog().models["deepseek-v4-flash"]
    client = MeteredClient(
        _FailingClient(),
        model_spec=model,
        context=CallContext(
            user_id=billing_factory.user_id,
            request_id="metered-failure",
            request_kind="chat",
            charge_trial=True,
        ),
        charge_emergency=True,
        session_factory=billing_factory,
    )
    with pytest.raises(LLMProviderError):
        client.complete(
            system="system",
            messages=[{"role": "user", "content": "question"}],
            max_tokens=100,
        )
    with billing_factory() as session:
        assert get_trial_balance(
            session, billing_factory.user_id
        ).reserved_microusd == 0
        assert get_emergency_balance(session).reserved_microusd == 0
        event = session.scalar(
            select(LLMUsageEvent).where(
                LLMUsageEvent.request_id == "metered-failure"
            )
        )
        assert event.status == "failed"
        assert event.error_type == "LLMProviderError"


class _SequenceClient:
    model = "model"
    provider = "provider"
    billing_source = "billing"
    route = "route"

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def complete(self, **_kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def tool_call(self, **kwargs):
        return self.complete(**kwargs)


def _response(text="ok"):
    return LLMResponse(
        text=text,
        stop_reason="stop",
        usage={},
        latency_ms=1,
        model="model",
        provider="provider",
        billing_source="billing",
        route="route",
    )


def _provider_error(status, *, retryable, outage):
    return LLMProviderError(
        "provider error",
        provider="provider",
        status_code=status,
        retryable=retryable,
        outage_candidate=outage,
    )


def test_retrying_client_retries_only_retryable_failures(monkeypatch):
    monkeypatch.setattr("app.llm.routing.time.sleep", lambda _seconds: None)
    inner = _SequenceClient(
        [_provider_error(503, retryable=True, outage=True), _response()]
    )
    result = RetryingClient(inner, attempts=3).complete()
    assert result.text == "ok"
    assert inner.calls == 2

    auth = _SequenceClient([_provider_error(401, retryable=False, outage=False)])
    with pytest.raises(LLMProviderError):
        RetryingClient(auth, attempts=3).complete()
    assert auth.calls == 1


def test_failover_opens_circuit_only_for_service_outage():
    primary = _SequenceClient([_provider_error(503, retryable=True, outage=True)])
    fallback = _SequenceClient([_response("fallback"), _response("fallback again")])
    circuits = CircuitRegistry()
    client = FailoverClient(
        primary,
        fallback,
        cooldown_seconds=60,
        circuits=circuits,
    )
    assert client.complete().text == "fallback"
    assert client.complete().text == "fallback again"
    assert primary.calls == 1

    invalid = _SequenceClient([_provider_error(400, retryable=False, outage=False)])
    unused = _SequenceClient([_response("must not run")])
    with pytest.raises(LLMProviderError):
        FailoverClient(
            invalid,
            unused,
            cooldown_seconds=60,
            circuits=CircuitRegistry(),
        ).complete()
    assert unused.calls == 0


def test_byok_credential_never_exposes_key_in_repr():
    credential = BYOKCredential(
        provider="openrouter", api_key="super-secret-value", model="claude-sonnet-5"
    )
    assert "super-secret-value" not in repr(credential)


@pytest.mark.parametrize(
    ("provider", "client_name"),
    [
        ("anthropic", "ClaudeClient"),
        ("openai", "OpenAIResponsesClient"),
        ("google", "GeminiClient"),
        ("openrouter", "OpenAICompatibleClient"),
    ],
)
def test_byok_default_uses_provider_request_model(
    monkeypatch,
    billing_factory,
    provider,
    client_name,
):
    from app.llm import routing as routing_module

    captured: list[dict[str, object]] = []

    class CapturedProviderClient:
        def __init__(self, **kwargs):
            captured.append(kwargs)
            self.model = kwargs["model"]
            self.provider = kwargs.get("provider", provider)
            self.billing_source = kwargs.get("billing_source", "byok")
            self.route = kwargs["route"]

    catalog = load_model_catalog()
    candidates = [catalog.routes[profile.primary_route].model for profile in catalog.profiles.values()
                  if provider == "openrouter" or catalog.model_for_route(
                      catalog.routes[profile.primary_route]).family == provider]
    previous_default = catalog.byok_defaults[provider].model
    model_id = previous_default if previous_default in candidates else candidates[0]
    catalog = admit_catalog_models(catalog, model_id)
    defaults = dict(catalog.byok_defaults)
    defaults[provider] = replace(
        defaults[provider], model=model_id, request_model="provider-specific-default"
    )
    catalog = replace(catalog, byok_defaults=defaults)
    monkeypatch.setattr(
        routing_module, client_name, CapturedProviderClient
    )

    router = LLMRouter(
        settings=Settings.from_environment(),
        catalog=catalog,
        session_factory=billing_factory,
    )
    router.byok(
        BYOKCredential(
            provider=provider,
            api_key="test-key",
            model=model_id,
        ),
        context=CallContext(
            user_id=billing_factory.user_id,
            request_id="request-model-translation",
            request_kind="chat",
            charge_trial=False,
        ),
    )

    assert len(captured) == 1
    expected_model = catalog.openrouter_models()[model_id] if provider == "openrouter" else "provider-specific-default"
    assert captured[0]["model"] == expected_model
    assert captured[0]["route"] == f"byok:{provider}:{model_id}"
    if provider == "openrouter":
        preferences = captured[0]["provider_preferences"]
        assert {key: preferences[key] for key in (
            "sort", "allow_fallbacks", "require_parameters", "data_collection", "zdr",
        )} == {
            "sort": "price",
            "allow_fallbacks": True,
            "require_parameters": True,
            "data_collection": "deny",
            "zdr": True,
        }
        assert preferences["max_price"] == {
            "prompt": float(catalog.models[model_id].input_usd_per_million),
            "completion": float(catalog.models[model_id].output_usd_per_million),
        }
    if provider == "anthropic":
        assert captured[0]["sdk_max_retries"] == 0


def test_funded_anthropic_uses_only_the_metered_retry_layer(
    monkeypatch,
    billing_factory,
):
    from app.llm import routing as routing_module

    monkeypatch.setenv("AZURE_ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("AZURE_ANTHROPIC_ENDPOINT", "https://example.services.ai.azure.com/anthropic")
    captured: list[dict[str, object]] = []

    class CapturedClaudeClient:
        def __init__(self, **kwargs):
            captured.append(kwargs)
            self.model = kwargs["model"]
            self.provider = "azure-foundry"
            self.billing_source = kwargs["billing_source"]
            self.route = kwargs["route"]

    monkeypatch.setattr(routing_module, "ClaudeClient", CapturedClaudeClient)
    settings = replace(
        Settings.from_environment(),
        openrouter_failover_enabled=False,
    )
    router = LLMRouter(
        settings=settings,
        session_factory=billing_factory,
    )
    router.funded(
        "balanced",
        context=CallContext(
            user_id=billing_factory.user_id,
            request_id="metered-anthropic-retry",
            request_kind="chat",
            charge_trial=True,
        ),
    )

    assert len(captured) == 1
    assert captured[0]["sdk_max_retries"] == 0


def test_byok_nondefault_direct_model_keeps_catalog_id(
    monkeypatch, billing_factory
):
    from app.llm import routing as routing_module

    captured: list[dict[str, object]] = []

    class CapturedOpenAIClient:
        def __init__(self, **kwargs):
            captured.append(kwargs)
            self.model = kwargs["model"]
            self.provider = kwargs["provider"]
            self.billing_source = kwargs["billing_source"]
            self.route = kwargs["route"]

    catalog = load_model_catalog()
    nondefault = next(
        catalog.routes[profile.primary_route].model for profile in catalog.profiles.values()
        if catalog.models[catalog.routes[profile.primary_route].model].family == "openai"
        and catalog.routes[profile.primary_route].model != catalog.byok_defaults["openai"].model
    )
    catalog = admit_catalog_models(catalog, nondefault)
    defaults = dict(catalog.byok_defaults)
    defaults["openai"] = replace(
        defaults["openai"], request_model="provider-specific-default"
    )
    catalog = replace(catalog, byok_defaults=defaults)
    monkeypatch.setattr(
        routing_module, "OpenAIResponsesClient", CapturedOpenAIClient
    )

    router = LLMRouter(
        settings=Settings.from_environment(),
        catalog=catalog,
        session_factory=billing_factory,
    )
    router.byok(
        BYOKCredential(
            provider="openai",
            api_key="test-key",
            model=nondefault,
        ),
        context=CallContext(
            user_id=billing_factory.user_id,
            request_id="request-nondefault-model",
            request_kind="chat",
            charge_trial=False,
        ),
    )

    assert len(captured) == 1
    assert captured[0]["model"] == nondefault
    assert captured[0]["route"] == f"byok:openai:{nondefault}"


def test_byok_rejects_mismatched_provider_model(monkeypatch, billing_factory):
    settings = Settings.from_environment()
    catalog = load_model_catalog()
    wrong_family_model = catalog.byok_defaults["openai"].model
    catalog = admit_catalog_models(catalog, wrong_family_model, catalog.byok_defaults["anthropic"].model)
    router = LLMRouter(settings=settings, catalog=catalog, session_factory=billing_factory)
    with pytest.raises(BYOKValidationError, match="does not match"):
        router.byok(
            BYOKCredential(
                provider="anthropic",
                api_key="test-key",
                model=wrong_family_model,
            ),
            context=CallContext(
                user_id=billing_factory.user_id,
                request_id="request",
                request_kind="chat",
                charge_trial=False,
            ),
        )


def test_openrouter_byok_rejects_models_without_a_zdr_tool_route(
    monkeypatch, billing_factory
):
    settings = Settings.from_environment()
    catalog = load_model_catalog()
    model_id = catalog.byok_defaults["openrouter"].model
    catalog = admit_catalog_models(catalog, model_id)
    # Simulate an operator removing a backup after qualification. Routing
    # still rejects the request before any provider client is constructed.
    catalog = replace(catalog, routes={key: route for key, route in catalog.routes.items()
                      if route.model != model_id or route.provider != "openrouter"})
    router = LLMRouter(settings=settings, catalog=catalog, session_factory=billing_factory)
    with pytest.raises(BYOKValidationError, match="unsupported OpenRouter model"):
        router.byok(
            BYOKCredential(
                provider="openrouter",
                api_key="test-key",
                model=model_id,
            ),
            context=CallContext(
                user_id=billing_factory.user_id,
                request_id="request",
                request_kind="chat",
                charge_trial=False,
            ),
        )


def test_funded_deadline_settles_uncertain_dispatch_on_request_thread(monkeypatch, billing_factory):
    import threading
    import time
    from app.llm import routing as routing_module

    released, finished = threading.Event(), threading.Event()
    worker_threads, ledger_threads = [], []
    caller_thread = threading.get_ident()

    class StalledProvider(_SuccessfulClient):
        def complete(self, **kwargs):
            worker_threads.append(threading.get_ident())
            self.calls += 1
            try:
                released.wait(2)
                return _response("late output")
            finally:
                finished.set()
        def close(self):
            released.set()

    original_settle = routing_module.settle_llm_call
    def settle(*args, **kwargs):
        ledger_threads.append(threading.get_ident())
        return original_settle(*args, **kwargs)
    monkeypatch.setattr(routing_module, "settle_llm_call", settle)
    raw, backup = StalledProvider(), _SequenceClient([_response("must not run")])
    deadline = time.monotonic() + .1
    metered = MeteredClient(raw, model_spec=load_model_catalog().models["claude-sonnet-4-6"],
        context=CallContext(billing_factory.user_id, "deadline-billed", "chat", True),
        charge_emergency=False, session_factory=billing_factory, deadline=deadline)
    client = FailoverClient(RetryingClient(metered, attempts=2, deadline=deadline), backup,
        cooldown_seconds=15, circuits=CircuitRegistry(), deadline=deadline)
    try:
        with pytest.raises(LLMProviderError) as caught:
            client.complete(system="system", messages=[{"role": "user", "content": "question"}], max_tokens=32)
        assert caught.value.error_type == "request_deadline"
        assert caught.value.billing_uncertain
        assert finished.wait(.5)
    finally:
        released.set()
    assert raw.calls == 1 and backup.calls == 0
    assert ledger_threads == [caller_thread] and worker_threads[0] != caller_thread
    with billing_factory() as session:
        reservation = session.scalar(select(UsageReservation).where(UsageReservation.user_id == billing_factory.user_id))
        event = session.scalar(select(LLMUsageEvent).where(LLMUsageEvent.request_id == "deadline-billed"))
        assert reservation.status == "settled"
        assert event.cost_microusd == reservation.reserved_microusd
        assert event.cost_microusd > 0 and "request_deadline" in event.error_type


def test_byok_slow_correction_uses_shared_deadline_without_funded_charges(monkeypatch, billing_factory):
    import threading
    import time
    from app.llm import routing as routing_module

    released = threading.Event()

    class UserProvider:
        def __init__(self, **kwargs):
            self.model = kwargs["model"]
            self.provider, self.billing_source, self.route = "openai", "byok", kwargs["route"]
            self.calls = 0
            self.request_dispatched = False

        def complete(self, **_kwargs):
            self.calls += 1
            self.request_dispatched = True
            if self.calls > 1:
                released.wait(1)
            return LLMResponse(text="answer", stop_reason="stop", usage={"input_tokens": 1, "output_tokens": 1},
                latency_ms=1, model=self.model, provider=self.provider,
                billing_source=self.billing_source, route=self.route)

        def close(self):
            released.set()

    monkeypatch.setattr(routing_module, "OpenAIResponsesClient", UserProvider)
    router = LLMRouter(settings=replace(Settings.from_environment(), llm_allow_byok=True), session_factory=billing_factory)
    client = router.byok(BYOKCredential("openai", "fake-user-key"),
        context=CallContext(billing_factory.user_id, "byok-shared-deadline", "propose", True))
    deadline = time.monotonic() + .15
    client.deadline = client.inner.deadline = client.inner.inner.request_deadline = deadline
    kwargs = {"system": "test", "messages": [], "max_tokens": 32}
    try:
        assert client.complete(**kwargs).text == "answer"
        with pytest.raises(LLMProviderError) as caught:
            client.complete(**kwargs)
        assert caught.value.error_type == "request_deadline"
        assert client.inner.inner.calls == 2
        assert time.monotonic() < deadline + .5
    finally:
        released.set()
    with billing_factory() as session:
        events = session.scalars(select(LLMUsageEvent).where(LLMUsageEvent.request_id == "byok-shared-deadline")).all()
        assert len(events) == 2 and all(event.billing_source == "byok" for event in events)
        assert events[1].status == "failed" and "request_deadline" in events[1].error_type
        assert session.get(TrialGrant, billing_factory.user_id).spent_microusd == 0
        assert session.get(EmergencyBudget, "openrouter").spent_microusd == 0
        assert not session.scalars(select(UsageReservation)).all()


def test_provider_timeout_still_retries_then_uses_backup_with_time_remaining(monkeypatch, billing_factory):
    import time
    monkeypatch.setattr("app.llm.routing.time.sleep", lambda _seconds: None)
    deadline = time.monotonic() + 10
    class TimeoutProvider(_SuccessfulClient):
        def complete(self, **_kwargs):
            self.calls += 1
            raise httpx.ReadTimeout("provider timeout", request=httpx.Request("POST", "https://provider.test/messages"))
    raw, backup = TimeoutProvider(), _SequenceClient([_response("same model backup")])
    metered = MeteredClient(raw, model_spec=load_model_catalog().models["claude-sonnet-4-6"],
        context=CallContext(billing_factory.user_id, "physical-timeout", "chat", True),
        charge_emergency=False, session_factory=billing_factory, deadline=deadline)
    client = FailoverClient(RetryingClient(metered, attempts=2, deadline=deadline), backup,
        cooldown_seconds=15, circuits=CircuitRegistry(), deadline=deadline)
    result = client.complete(system="system", messages=[{"role": "user", "content": "question"}], max_tokens=32)
    assert result.text == "same model backup" and raw.calls == 2 and backup.calls == 1
    with billing_factory() as session:
        events = session.scalars(select(LLMUsageEvent).where(LLMUsageEvent.request_id == "physical-timeout")).all()
        assert len(events) == 2 and all(event.cost_microusd > 0 for event in events)


def test_accounting_transport_failure_never_authorizes_a_paid_backup(monkeypatch, billing_factory):
    def unavailable(*_args, **_kwargs):
        raise httpx.ReadTimeout("accounting transport unavailable")
    monkeypatch.setattr("app.llm.routing.settle_llm_call", unavailable)
    backup = _SequenceClient([_response("must not run")])
    metered = MeteredClient(_SuccessfulClient(), model_spec=load_model_catalog().models["claude-sonnet-4-6"],
        context=CallContext(billing_factory.user_id, "accounting-unavailable", "chat", True),
        charge_emergency=False, session_factory=billing_factory)
    client = FailoverClient(RetryingClient(metered, attempts=2), backup,
        cooldown_seconds=15, circuits=CircuitRegistry())
    with pytest.raises(RuntimeError, match="accounting is unavailable"):
        client.complete(system="system", messages=[{"role": "user", "content": "question"}], max_tokens=32)
    assert backup.calls == 0


@pytest.mark.parametrize("max_tokens,content", [(32, "x" * 200_000), (0, "short"), (100_000, "short")])
def test_request_limits_are_safe_user_errors_before_reservation_or_fallback(billing_factory, max_tokens, content):
    from app.api.llm_access import HANDLED_LLM_ERRORS, llm_http_exception

    raw = _SuccessfulClient()
    metered = MeteredClient(raw, model_spec=load_model_catalog().models["gemini-3.8-flash"],
        context=CallContext(billing_factory.user_id, "long-context", "chat", True),
        charge_emergency=False, session_factory=billing_factory)
    backup = _SequenceClient([_response("must not run")])
    client = FailoverClient(RetryingClient(metered, attempts=2), backup,
        cooldown_seconds=15, circuits=CircuitRegistry(), primary_verified=True)
    with pytest.raises(LLMRequestValidationError) as caught:
        client.complete(system="system", messages=[{"role": "user", "content": content}], max_tokens=max_tokens)
    assert isinstance(caught.value, HANDLED_LLM_ERRORS)
    for byok in (True, False):
        response = llm_http_exception(caught.value, byok=byok)
        assert response.status_code == 400
        assert response.detail["code"] == "llm_request_too_large"
        assert "billing_uncertain" not in response.detail
    assert raw.calls == backup.calls == 0
    with billing_factory() as session:
        assert session.scalar(select(UsageReservation)) is None
        assert session.scalar(select(LLMUsageEvent)) is None


def test_exhausted_abda_credit_never_dispatches_or_uses_backup(billing_factory):
    from app.services.trials import InsufficientTrialCreditError

    with billing_factory() as session:
        grant = session.get(TrialGrant, billing_factory.user_id)
        grant.spent_microusd = grant.granted_microusd
        session.commit()
    raw, backup = _SuccessfulClient(), _SequenceClient([_response("must not run")])
    raw.provider, raw.billing_source, raw.route = "azure-foundry", "cloudbank", "primary"
    metered = MeteredClient(raw, model_spec=load_model_catalog().models["claude-sonnet-4-6"],
        context=CallContext(billing_factory.user_id, "user-credit-exhausted", "chat", True),
        charge_emergency=False, session_factory=billing_factory)
    client = FailoverClient(RetryingClient(metered, attempts=2), backup,
        cooldown_seconds=15, circuits=CircuitRegistry(), primary_verified=True)
    with pytest.raises(InsufficientTrialCreditError):
        client.complete(system="system", messages=[{"role": "user", "content": "question"}], max_tokens=32)
    assert raw.calls == 0 and backup.calls == 0
    with billing_factory() as session:
        assert session.scalar(select(UsageReservation)) is None
        assert session.scalar(select(LLMUsageEvent)) is None
