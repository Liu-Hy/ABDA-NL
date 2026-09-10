"""A failed advisory call must preserve the paid proposal and its full liability."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, LLMUsageEvent
from app.evals.evidence import RecordingClient
from app.llm.catalog import load_model_catalog
from app.llm.client import (
    LLMAccountingUnavailableError, LLMRequestDeadlineError,
    LLMResponseValidationError, ToolCallResponse,
)
from app.llm.edit_service import run_propose
from app.llm.evidence import source_evidence
from app.llm.providers import LLMProviderError
from app.llm.routing import CallContext, LocalSpendCap, MeteredClient
from app.scenario.loader import scenario_from_dict


@pytest.fixture
def scenario():
    return scenario_from_dict({
        "title": "Advisory review", "facts": {"smoke": {"description": "Smoke is present"}},
        "assumptions": {}, "rules": {},
        "conclusions": {"alarm": {"description": "Raise the alarm"}}, "corpus": [],
    })


class Provider:
    model = "claude-sonnet-5"
    provider = "azure-foundry"
    billing_source = "cloudbank"
    route = "synthetic-review-degradation"

    def __init__(self, reviewer):
        self.reviewer = reviewer

    def tool_call(self, **kwargs):
        if kwargs["tool"]["name"] == "review_edit":
            if isinstance(self.reviewer, Exception):
                raise self.reviewer
            payload = self.reviewer
        else:
            payload = {"id": "smoke_alarm", "rule": {"type": "defeasible",
                "premises": ["smoke"], "conclusion": "alarm", "source": "user instruction"}}
        return ToolCallResponse(
            tool_name=kwargs["tool"]["name"], tool_input=deepcopy(payload),
            stop_reason="tool_use", usage={"input_tokens": 11, "output_tokens": 7},
            latency_ms=3, model=self.model, provider=self.provider,
            billing_source=self.billing_source, route=self.route,
            resolved_model_version="claude-sonnet-5-provider-version",
        )


@pytest.mark.parametrize("failure", [
    LLMProviderError("private timeout", provider="azure-foundry", billing_uncertain=True),
    LLMProviderError("private provider error", provider="azure-foundry", status_code=503,
                     usage={"input_tokens": 9, "output_tokens": 2}),
    LLMRequestDeadlineError(provider="azure-foundry"),
    LLMResponseValidationError("private malformed output", usage={"input_tokens": 9}),
    {"issues": "not a list"},
    {"issues": [{"severity": {}, "message": "invalid severity"}]},
    {"issues": [{"severity": "warning", "message": ""}]},
])
def test_failed_review_keeps_proposal_and_every_settled_cost(tmp_path, scenario, failure, caplog):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'usage.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    provider = Provider(failure)
    client = MeteredClient(
        provider, model_spec=load_model_catalog().models[provider.model],
        context=CallContext(None, "test-review", "propose", False),
        charge_emergency=False, spend_cap=LocalSpendCap(1_000_000), session_factory=factory,
    )
    # Cumulative counters from a previous use must not be charged again.
    client.settled_cost_microusd = 123
    client = RecordingClient(client)
    result = run_propose(scenario, {}, [], task="add-rule",
        instruction="Raise an alarm when smoke is present.", scenario_dir=None, client=client)
    assert result.op["rule"]["conclusion"] == "alarm"
    assert not result.reviewed and result.proposer_attempts == 1
    assert any("review was unavailable" in issue.message for issue in result.review_issues)
    with factory() as session:
        events = list(session.scalars(select(LLMUsageEvent)))
    assert len(events) == 2
    assert result.cost_microusd == sum(event.cost_microusd for event in events)
    assert result.cost_microusd == client.settled_cost_microusd - 123
    assert result.billing_uncertain == (client.settled_billing_uncertain_count > 0)
    assert result.resolved_model_version == "claude-sonnet-5-provider-version"
    assert "private" not in caplog.text
    engine.dispose()


@pytest.mark.parametrize("error", [
    ValueError("unexpected internal detail"), LLMAccountingUnavailableError("private ledger detail"),
])
def test_programming_or_accounting_errors_do_not_become_review_success(monkeypatch, scenario, error):
    def fail(*_args, **_kwargs):
        raise error

    monkeypatch.setattr("app.llm.edit_service.run_review", fail)
    with pytest.raises(type(error)):
        run_propose(scenario, {}, [], task="add-rule", instruction="Raise the alarm.",
                    scenario_dir=None, client=Provider({"issues": []}))


def test_source_integrity_does_not_label_context_as_an_answer_quotation():
    sources = {"memo.txt": [(17, "Smoke was observed near the east entrance.")]}
    context, issues = source_evidence("There was smoke [memo.txt].", sources)
    quotation, quote_issues = source_evidence(
        'The memo says "Smoke was observed near the east entrance." [memo.txt].', sources,
    )
    assert not issues and not quote_issues
    assert context[0]["evidence_role"] == "context"
    assert quotation[0]["evidence_role"] == "quotation"
    for item in (context[0], quotation[0]):
        assert item["verified"] is True
        assert item["start"] == 17
        assert item["end"] - item["start"] == len(item["quote"])


@pytest.mark.parametrize("endpoint,payload", [
    ("/chat", {"messages": [{"role": "user", "content": "Why?"}]}),
    ("/propose", {"task": "add-rule", "instruction": "Add a supporting rule."}),
])
def test_unexpected_value_error_is_private_at_http_boundary(monkeypatch, endpoint, payload):
    from fastapi.testclient import TestClient
    from app.api import main as api

    class Broken:
        def complete(self, **_kwargs):
            raise ValueError("private provider key or database diagnostic")

        tool_call = complete

    monkeypatch.setattr(api, "ENABLE_LLM", True)
    monkeypatch.setattr(api, "_request_llm_client", lambda *_args, **_kwargs: Broken())
    with TestClient(api.app, raise_server_exceptions=False) as client:
        response = client.post(endpoint, json={"scenario_id": "popov_v_hayashi", **payload})
    assert response.status_code == 500
    assert "private provider" not in response.text


@pytest.mark.parametrize("boundary", ["http", "mcp"])
@pytest.mark.parametrize("missing_usage", [False, True])
def test_exhausted_proposal_reports_real_settled_uncertainty(
    tmp_path, monkeypatch, scenario, boundary, missing_usage,
):
    from fastapi.testclient import TestClient
    from app.api import main as api
    from app.mcp import server as mcp
    from app.llm.edit_service import MAX_PROPOSER_ATTEMPTS

    class InvalidProposal(Provider):
        def tool_call(self, **kwargs):
            response = super().tool_call(**kwargs)
            response.tool_input["id"] = "invalid" * 100
            if missing_usage:
                response.usage = {}
            return response

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'exhausted.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    provider = InvalidProposal({"issues": []})
    client = MeteredClient(
        provider, model_spec=load_model_catalog().models[provider.model],
        context=CallContext(None, "test-exhausted", "propose", False),
        charge_emergency=False, spend_cap=LocalSpendCap(1_000_000), session_factory=factory,
    )
    try:
        if boundary == "http":
            monkeypatch.setattr(api, "ENABLE_LLM", True)
            monkeypatch.setattr(api, "_load_baseline", lambda _id: scenario)
            monkeypatch.setattr(api, "_request_llm_client", lambda *_args, **_kwargs: client)
            with TestClient(api.app) as http:
                response = http.post("/propose", json={
                    "scenario_id": "popov_v_hayashi", "task": "add-rule",
                    "instruction": "Raise an alarm when smoke is present.",
                })
            assert response.status_code == 422
            detail = response.json()["detail"]
            assert detail["code"] == "proposer_retry_exhausted"
            assert detail["billing_uncertain"] is missing_usage
        else:
            project = SimpleNamespace(id="test-project", source_scenario_id=None)
            monkeypatch.setattr(mcp, "_load_project_for_llm", lambda _id: (
                None, project, scenario, {"af": {}},
            ))
            monkeypatch.setattr(mcp, "_select_mcp_llm_client", lambda **_kwargs: client)
            with pytest.raises(mcp.MCPToolUserError) as captured:
                mcp.propose_project_edit(
                    "test-project", "add-rule", "Raise an alarm when smoke is present.",
                    SimpleNamespace(request_id="test-exhausted"),
                )
            assert "No valid edit was produced" in str(captured.value)
            assert ("conservatively charged" in str(captured.value)) is missing_usage
        with factory() as session:
            events = list(session.scalars(select(LLMUsageEvent)))
        assert len(events) == MAX_PROPOSER_ATTEMPTS
        assert client.settled_cost_microusd == sum(event.cost_microusd for event in events) > 0
        assert client.settled_billing_uncertain_count == (
            MAX_PROPOSER_ATTEMPTS if missing_usage else 0
        )
    finally:
        engine.dispose()
