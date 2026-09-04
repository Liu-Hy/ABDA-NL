"""Isolated staging OpenRouter outage-drill acceptance."""

from __future__ import annotations

from dataclasses import replace
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.cli import outage_drill
from app.core.config import Settings
from app.db.models import (
    Base,
    EmergencyBudget,
    LLMUsageEvent,
    TrialGrant,
    TrialProgram,
    User,
)
from app.llm.client import LLMResponse
from app.llm.providers import LLMProviderError
from app.services.emergency_budget import get_emergency_balance
from app.services.trials import get_trial_balance


EMAIL = "outage-drill@example.edu"
ORIGIN = "https://demo.abda-nl.org"


@pytest.fixture
def drill_factory(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'drill.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        user = User(email=EMAIL, email_verified=True)
        session.add_all(
            [
                user,
                TrialProgram(
                    key="global",
                    enabled=True,
                    max_users=10,
                    grant_microusd=5_000_000,
                    budget_microusd=50_000_000,
                    activation_count=1,
                    allocated_microusd=5_000_000,
                ),
                EmergencyBudget(
                    key="openrouter",
                    enabled=False,
                    hard_limit_microusd=500_000_000,
                ),
            ]
        )
        session.flush()
        session.add(TrialGrant(user_id=user.id, granted_microusd=5_000_000))
        session.commit()
        factory.user_id = user.id
    yield factory
    engine.dispose()


class _SuccessfulOpenRouter:
    instances = []

    def __init__(self, **kwargs):
        self.model = kwargs["model"]
        self.provider = kwargs["provider"]
        self.billing_source = kwargs["billing_source"]
        self.route = kwargs["route"]
        self.closed = False
        self.instances.append(self)

    def close(self):
        self.closed = True

    def complete(self, **_kwargs):
        return LLMResponse(
            text=outage_drill._RESPONSE_MARKER,
            stop_reason="stop",
            usage={"input_tokens": 10, "output_tokens": 5},
            latency_ms=12,
            model=self.model,
            provider=self.provider,
            billing_source=self.billing_source,
            route=self.route,
            provider_cost_microusd=100,
        )


class _FailingOpenRouter(_SuccessfulOpenRouter):
    def complete(self, **_kwargs):
        raise LLMProviderError(
            "test provider rejection",
            provider="openrouter",
            status_code=400,
            retryable=False,
            outage_candidate=False,
        )


class _ReasoningOnlyOpenRouter(_SuccessfulOpenRouter):
    def complete(self, **_kwargs):
        response = super().complete(**_kwargs)
        response.text = ""
        response.stop_reason = "length"
        return response


def _install_runtime(monkeypatch, factory):
    _SuccessfulOpenRouter.instances.clear()
    settings = replace(
        Settings.from_environment(),
        environment="staging",
        public_base_url=ORIGIN,
        openrouter_failover_enabled=False,
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("ABDA_OUTAGE_DRILL_USER_EMAIL", EMAIL)
    monkeypatch.setattr(outage_drill, "get_settings", lambda: settings)
    monkeypatch.setattr(outage_drill, "database_is_ready", lambda: True)
    monkeypatch.setattr(outage_drill, "get_session_factory", lambda: factory)
    monkeypatch.setattr(
        "app.llm.routing.OpenAICompatibleClient",
        _SuccessfulOpenRouter,
    )


def test_outage_drill_is_dry_run_by_default(drill_factory, monkeypatch, capsys):
    _install_runtime(monkeypatch, drill_factory)
    assert outage_drill.main(["--expected-origin", ORIGIN]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["result"] == "DRY_RUN_READY"
    assert output["mutated"] is False
    assert EMAIL not in json.dumps(output)
    with drill_factory() as session:
        assert get_trial_balance(session, drill_factory.user_id).spent_microusd == 0
        assert get_emergency_balance(session).spent_microusd == 0
        assert get_emergency_balance(session).enabled is False


def test_outage_drill_requires_confirmation(drill_factory, monkeypatch, capsys):
    _install_runtime(monkeypatch, drill_factory)
    monkeypatch.delenv("ABDA_OUTAGE_DRILL_CONFIRMATION", raising=False)
    assert outage_drill.main(["--expected-origin", ORIGIN, "--execute"]) == 1
    assert "exact value" in capsys.readouterr().err
    with drill_factory() as session:
        assert get_emergency_balance(session).enabled is False


def test_outage_drill_reaches_fallback_and_reconciles_both_ledgers(
    drill_factory,
    monkeypatch,
    capsys,
):
    _install_runtime(monkeypatch, drill_factory)
    monkeypatch.setenv(
        "ABDA_OUTAGE_DRILL_CONFIRMATION",
        outage_drill._CONFIRMATION,
    )
    assert outage_drill.main(["--expected-origin", ORIGIN, "--execute"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["result"] == "OPENROUTER_OUTAGE_DRILL_PASSED"
    assert output["marker_verified"] is True
    assert output["audit"] == {
        "openrouter_enabled_restored": True,
        "openrouter_recorded_cost_microusd": 106,
        "openrouter_reserved_microusd": 0,
        "provider_attempt_count": 1,
        "settled_cost_microusd": 106,
        "trial_recorded_cost_microusd": 106,
        "trial_reserved_microusd": 0,
    }
    assert EMAIL not in json.dumps(output)
    with drill_factory() as session:
        assert get_trial_balance(session, drill_factory.user_id).spent_microusd == 106
        emergency = get_emergency_balance(session)
        assert emergency.enabled is False
        assert emergency.spent_microusd == 106
        event = session.scalar(
            select(LLMUsageEvent).where(LLMUsageEvent.request_id == output["request_id"])
        )
        assert event is not None
        assert event.route == outage_drill._FALLBACK_ROUTE
    assert len(_SuccessfulOpenRouter.instances) == 1
    assert _SuccessfulOpenRouter.instances[0].closed is True


def test_outage_drill_restores_disabled_budget_after_provider_failure(
    drill_factory,
    monkeypatch,
    capsys,
):
    _install_runtime(monkeypatch, drill_factory)
    monkeypatch.setattr("app.llm.routing.OpenAICompatibleClient", _FailingOpenRouter)
    monkeypatch.setenv(
        "ABDA_OUTAGE_DRILL_CONFIRMATION",
        outage_drill._CONFIRMATION,
    )
    assert outage_drill.main(["--expected-origin", ORIGIN, "--execute"]) == 1
    assert "provider request did not complete" in capsys.readouterr().err
    with drill_factory() as session:
        trial = get_trial_balance(session, drill_factory.user_id)
        emergency = get_emergency_balance(session)
        assert trial.spent_microusd == 0
        assert trial.reserved_microusd == 0
        assert emergency.enabled is False
        assert emergency.spent_microusd == 0
        assert emergency.reserved_microusd == 0
    assert len(_SuccessfulOpenRouter.instances) == 1
    assert _SuccessfulOpenRouter.instances[0].closed is True


def test_outage_drill_preserves_receipt_when_visible_marker_is_missing(
    drill_factory,
    monkeypatch,
    capsys,
):
    _install_runtime(monkeypatch, drill_factory)
    monkeypatch.setattr("app.llm.routing.OpenAICompatibleClient", _ReasoningOnlyOpenRouter)
    monkeypatch.setenv(
        "ABDA_OUTAGE_DRILL_CONFIRMATION",
        outage_drill._CONFIRMATION,
    )
    assert outage_drill.main(["--expected-origin", ORIGIN, "--execute"]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["result"] == "OPENROUTER_OUTAGE_DRILL_ACCOUNTING_PASSED_MARKER_MISSING"
    assert output["marker_verified"] is False
    assert output["audit"]["settled_cost_microusd"] == 106
    assert output["audit"]["openrouter_enabled_restored"] is True
    with drill_factory() as session:
        trial = get_trial_balance(session, drill_factory.user_id)
        emergency = get_emergency_balance(session)
        assert trial.spent_microusd == 106
        assert trial.reserved_microusd == 0
        assert emergency.enabled is False
        assert emergency.spent_microusd == 106
        assert emergency.reserved_microusd == 0


def test_outage_drill_refuses_wrong_origin_or_enabled_public_failover(
    drill_factory,
    monkeypatch,
    capsys,
):
    _install_runtime(monkeypatch, drill_factory)
    assert outage_drill.main(["--expected-origin", "https://wrong.example"]) == 1
    assert "expected origin" in capsys.readouterr().err

    settings = replace(
        Settings.from_environment(),
        environment="staging",
        public_base_url=ORIGIN,
        openrouter_failover_enabled=True,
    )
    monkeypatch.setattr(outage_drill, "get_settings", lambda: settings)
    assert outage_drill.main(["--expected-origin", ORIGIN]) == 1
    assert "must remain disabled" in capsys.readouterr().err
