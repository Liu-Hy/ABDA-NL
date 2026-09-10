"""Logical response costs include every committed physical provider attempt."""
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Base, EmergencyBudget, LLMUsageEvent, TrialGrant, TrialProgram, UsageReservation, User,
)
from app.llm.catalog import load_model_catalog
from app.llm.client import LLMResponse, ToolCallResponse
from app.llm.providers import LLMProviderError
from app.llm.routing import (
    CallContext, CircuitRegistry, FailoverClient, MeteredClient, RetryingClient,
    _UnavailableVerifiedRoute,
)


class RawProvider:
    def __init__(self, model, outcomes, *, backup=False):
        self.model = model
        self.provider = 'openrouter' if backup else 'azure-foundry'
        self.billing_source = 'openrouter-emergency' if backup else 'cloudbank'
        self.route = 'cost-backup' if backup else 'cost-primary'
        self.outcomes = iter(outcomes)
        self.calls = []

    def _response(self, method, kwargs):
        self.calls.append((method, kwargs.get('tool', {}).get('name')))
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        common = dict(stop_reason='stop', usage={'input_tokens': 2, 'output_tokens': 1},
                      latency_ms=1, model=self.model, provider=self.provider,
                      billing_source=self.billing_source, route=self.route,
                      cost_microusd=outcome, provider_cost_microusd=outcome)
        if method == 'tool_call':
            return ToolCallResponse(tool_name=kwargs['tool']['name'], tool_input={}, **common)
        return LLMResponse(text='injected answer', **common)

    def complete(self, **kwargs):
        return self._response('complete', kwargs)

    def tool_call(self, **kwargs):
        return self._response('tool_call', kwargs)


def outage(cost=7, *, uncertain=False, provider='azure-foundry'):
    return LLMProviderError('injected provider failure', provider=provider, status_code=503,
                            retryable=True, outage_candidate=True,
                            provider_cost_microusd=None if uncertain else cost,
                            billing_uncertain=uncertain)


@pytest.fixture
def billed_clients(tmp_path, monkeypatch):
    monkeypatch.setattr('app.llm.routing.time.sleep', lambda _seconds: None)
    engine = create_engine(f'sqlite+pysqlite:///{tmp_path / "costs.db"}')
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    catalog = load_model_catalog()
    route = catalog.routes[next(iter(catalog.public_profiles())).primary_route]
    model = catalog.models[route.model]
    with factory() as session:
        user = User(email='cost-metadata@example.edu', email_verified=True)
        session.add_all([user,
            TrialProgram(key='global', enabled=True, max_users=1, grant_microusd=5_000_000,
                         budget_microusd=5_000_000, activation_count=1, allocated_microusd=5_000_000),
            EmergencyBudget(key='openrouter', enabled=True, hard_limit_microusd=5_000_000)])
        session.flush()
        session.add(TrialGrant(user_id=user.id, granted_microusd=5_000_000))
        session.commit()
        user_id = user.id

    def make(primary_outcomes, backup_outcomes=()):
        primary_raw = RawProvider(model.id, primary_outcomes)
        backup_raw = RawProvider(model.id, backup_outcomes, backup=True)
        context = CallContext(user_id, 'cost-request', 'propose', True)
        primary = MeteredClient(primary_raw, model_spec=model, use_provider_reported_cost=True,
                                context=context, charge_emergency=False, session_factory=factory)
        backup = MeteredClient(backup_raw, model_spec=model, use_provider_reported_cost=True,
                               context=context, charge_emergency=True, session_factory=factory)
        circuits = CircuitRegistry()
        client = FailoverClient(RetryingClient(primary, attempts=2), backup,
                                cooldown_seconds=60, circuits=circuits)
        return SimpleNamespace(client=client, primary=primary, backup=backup,
                               primary_raw=primary_raw, backup_raw=backup_raw,
                               factory=factory, user_id=user_id, route=route, circuits=circuits)

    yield make
    engine.dispose()


def invoke(client, method='complete', tool_name='propose_add_rule'):
    kwargs = dict(system='injected request', messages=[{'role': 'user', 'content': 'test'}],
                  max_tokens=128)
    if method == 'tool_call':
        kwargs['tool'] = {'name': tool_name, 'input_schema': {'type': 'object'}}
    return getattr(client, method)(**kwargs)


def ledger(harness):
    with harness.factory() as session:
        events = session.scalars(select(LLMUsageEvent).order_by(LLMUsageEvent.created_at)).all()
        costs = [event.cost_microusd for event in events]
        grant = session.get(TrialGrant, harness.user_id)
        emergency = session.get(EmergencyBudget, 'openrouter')
        assert grant.spent_microusd == sum(costs)
        assert session.get(TrialProgram, 'global').spent_microusd == sum(costs)
        assert emergency.spent_microusd == sum(event.cost_microusd for event in events
                                              if event.provider == 'openrouter')
        assert grant.reserved_microusd == emergency.reserved_microusd == 0
        assert all(row.status in {'settled', 'released'}
                   for row in session.scalars(select(UsageReservation)).all())
        return costs


@pytest.mark.parametrize('method', ['complete', 'tool_call'])
@pytest.mark.parametrize('uncertain', [False, True])
def test_retry_response_includes_known_or_conservative_failure_cost(billed_clients, method, uncertain):
    h = billed_clients([outage(uncertain=uncertain), 11])
    response = invoke(h.client, method)
    costs = ledger(h)
    assert len(costs) == 2 and costs[0] > 0 and costs[1] == 11
    if not uncertain:
        assert costs[0] == 7
    assert response.cost_microusd == sum(costs) == h.client.settled_cost_microusd
    assert response.provider_cost_microusd == 11
    assert len(h.primary_raw.calls) == 2 and h.backup_raw.calls == []


def test_fallback_and_consecutive_proposal_review_report_only_each_call_delta(billed_clients):
    h = billed_clients([outage(), outage()], [11, 13])
    proposal = invoke(h.client, 'tool_call', 'propose_add_rule')
    review = invoke(h.client, 'tool_call', 'review_edit')
    assert proposal.cost_microusd == 25
    assert review.cost_microusd == 13
    assert h.primary.settled_cost_microusd == 14 and h.backup.settled_cost_microusd == 24
    assert proposal.cost_microusd + review.cost_microusd == sum(ledger(h)) == 38
    assert h.client.settled_cost_microusd == 38
    assert len(h.primary_raw.calls) == 2
    assert h.backup_raw.calls == [('tool_call', 'propose_add_rule'), ('tool_call', 'review_edit')]


def test_primary_consecutive_proposal_review_does_not_double_count_retry(billed_clients):
    h = billed_clients([outage(), 11, 13])
    proposal = invoke(h.client, 'tool_call', 'propose_add_rule')
    review = invoke(h.client, 'tool_call', 'review_edit')
    assert proposal.cost_microusd == 18 and review.cost_microusd == 13
    assert proposal.cost_microusd + review.cost_microusd == sum(ledger(h)) == 31
    assert h.client.settled_cost_microusd == 31 and h.backup_raw.calls == []


def test_open_circuit_reports_only_new_backup_cost(billed_clients):
    h = billed_clients([], [11])
    h.circuits.open(h.primary.route, 60)
    response = invoke(h.client)
    assert response.cost_microusd == sum(ledger(h)) == 11
    assert h.primary_raw.calls == []


@pytest.mark.parametrize('verified', [False, True])
def test_configuration_placeholder_never_invents_a_primary_charge(billed_clients, verified):
    h = billed_clients([], [11])
    client = FailoverClient(_UnavailableVerifiedRoute(h.route), h.backup,
                            cooldown_seconds=60, circuits=h.circuits, primary_verified=verified)
    if verified:
        response = invoke(client)
        assert response.cost_microusd == sum(ledger(h)) == 11
        assert client.settled_cost_microusd == 11
    else:
        with pytest.raises(LLMProviderError, match='configuration is unavailable'):
            invoke(client)
        assert ledger(h) == [] and h.backup_raw.calls == []
        assert client.settled_cost_microusd == 0
    assert h.primary_raw.calls == []


def test_failed_request_cost_is_not_reused_by_later_success(billed_clients):
    h = billed_clients([outage(), outage()], [outage(3, provider='openrouter'), 5])
    with pytest.raises(LLMProviderError):
        invoke(h.client)
    assert h.client.settled_cost_microusd == sum(ledger(h)) == 17
    response = invoke(h.client)
    assert response.cost_microusd == 5
    assert h.client.settled_cost_microusd == sum(ledger(h)) == 22


@pytest.mark.parametrize('provider_failed', [False, True])
def test_failed_settlement_does_not_report_committed_cost_or_authorize_backup(
    billed_clients, monkeypatch, provider_failed,
):
    h = billed_clients([outage() if provider_failed else 11], [13])

    def fail(*_args, **_kwargs):
        raise RuntimeError('injected database outage')

    monkeypatch.setattr('app.llm.routing.settle_llm_call', fail)
    with pytest.raises(RuntimeError, match='accounting is unavailable'):
        invoke(h.client)
    assert h.client.settled_cost_microusd == 0 and h.backup_raw.calls == []
    with h.factory() as session:
        assert session.scalar(select(LLMUsageEvent)) is None
        grant = session.get(TrialGrant, h.user_id)
        assert grant.spent_microusd == 0 and grant.reserved_microusd > 0


def test_unmetered_response_cost_metadata_remains_unchanged():
    raw = RawProvider('injected-model', [11])
    client = FailoverClient(RetryingClient(raw, attempts=1), None,
                            cooldown_seconds=60, circuits=CircuitRegistry())
    response = invoke(client)
    assert response.cost_microusd == 11
    assert client.settled_cost_microusd is None


def test_mixed_unmetered_chain_does_not_replace_response_cost_with_partial_totals(billed_clients):
    h = billed_clients([], [])
    raw = RawProvider(h.primary.model, [11])
    client = FailoverClient(raw, h.backup, cooldown_seconds=60, circuits=h.circuits)
    response = invoke(client)
    assert response.cost_microusd == 11
    assert client.settled_cost_microusd is None
    assert ledger(h) == [] and h.backup_raw.calls == []
