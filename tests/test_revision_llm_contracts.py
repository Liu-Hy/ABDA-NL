"""Behavioral checks for funded routing, selected context, and exact evidence."""
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest

from app.llm.catalog import load_model_catalog, _validate_catalog
from app.llm.corpus import build_corpus_block
from app.llm.evidence import resolve_context_refs, source_evidence, supplied_sources
from app.llm.providers import LLMProviderError, VertexGeminiClient
from app.llm.routing import CircuitRegistry, FailoverClient, RetryingClient


class Provider:
    model = "same-model"
    provider = "azure-foundry"
    billing_source = "cloudbank"
    route = "test-deployment"

    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = 0

    def complete(self, **_kwargs):
        self.calls += 1
        result = next(self.outcomes)
        if isinstance(result, Exception):
            raise result
        return result


def failure(status=503):
    return LLMProviderError("provider unavailable", provider="azure-foundry",
                            status_code=status, retryable=status == 503,
                            outage_candidate=status == 503)


def test_funded_retry_recovers_without_spending_on_backup(monkeypatch):
    monkeypatch.setattr("app.llm.routing.time.sleep", lambda _seconds: None)
    primary = Provider([failure(), "recovered"])
    backup = Provider(["backup"])
    client = FailoverClient(RetryingClient(primary, attempts=2), backup,
                            cooldown_seconds=15, circuits=CircuitRegistry())
    assert client.complete() == "recovered"
    assert primary.calls == 2 and backup.calls == 0


def test_funded_two_failures_then_one_same_model_backup(monkeypatch):
    monkeypatch.setattr("app.llm.routing.time.sleep", lambda _seconds: None)
    primary = Provider([failure(), failure()])
    backup = Provider(["backup"])
    client = FailoverClient(RetryingClient(primary, attempts=2), backup,
                            cooldown_seconds=15, circuits=CircuitRegistry())
    assert client.complete() == "backup"
    assert primary.calls == 2 and backup.calls == 1


@pytest.mark.parametrize("status", [401, 403, 404])
def test_only_verified_provider_faults_can_use_backup(status):
    for verified in (False, True):
        primary, backup = Provider([failure(status)]), Provider(["backup"])
        client = FailoverClient(primary, backup, cooldown_seconds=15,
                                circuits=CircuitRegistry(), primary_verified=verified)
        if verified:
            assert client.complete() == "backup"
        else:
            with pytest.raises(LLMProviderError):
                client.complete()
        assert backup.calls == int(verified)


def test_accounting_failure_never_authorizes_backup():
    primary, backup = Provider([RuntimeError("accounting unavailable")]), Provider(["backup"])
    client = FailoverClient(primary, backup, cooldown_seconds=15, circuits=CircuitRegistry())
    with pytest.raises(RuntimeError):
        client.complete()
    assert backup.calls == 0


def test_recovery_allows_only_one_probe(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("app.llm.routing.time.monotonic", lambda: now[0])
    registry = CircuitRegistry()
    registry.open("deployment", 15)
    assert not registry.primary_allowed("deployment")
    now[0] = 116
    assert registry.primary_allowed("deployment")
    assert not registry.primary_allowed("deployment")
    registry.close("deployment")
    assert registry.primary_allowed("deployment")


def test_catalog_rejects_cross_model_fallback():
    catalog = load_model_catalog()
    profiles = dict(catalog.profiles)
    profiles["balanced"] = replace(profiles["balanced"], fallback_route="openrouter-gpt-5.6-sol")
    with pytest.raises(RuntimeError, match="same model"):
        _validate_catalog(replace(catalog, profiles=profiles))


def test_removed_low_tiers_are_not_selectable():
    catalog = load_model_catalog()
    removed = {"claude-haiku-4-5", "gpt-5.6-luna", "gemini-3.5-flash-lite"}
    assert catalog.public_model_ids().isdisjoint(removed)
    assert all(catalog.routes[p.primary_route].model not in removed for p in catalog.profiles.values())


def test_vertex_uses_project_scoped_oauth_and_counts_thinking():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "An answer."}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 100, "cachedContentTokenCount": 20,
                              "candidatesTokenCount": 30, "thoughtsTokenCount": 40},
        })

    client = VertexGeminiClient(model="gemini-3.8-flash",
        model_spec=load_model_catalog().models["gemini-3.8-flash"], project="funded-project",
        token_provider=lambda: "injected-test-token", transport=httpx.MockTransport(handler))
    try:
        answer = client.complete(system="system", messages=[{"role": "user", "content": "question"}], max_tokens=128)
    finally:
        client.close()
    assert answer.provider == "gcp-vertex" and answer.billing_source == "cloudbank"
    assert answer.usage["input_tokens"] == 80 and answer.usage["output_tokens"] == 70
    assert requests[0].url.host == "aiplatform.googleapis.com"
    assert "/projects/funded-project/locations/global/publishers/google/" in requests[0].url.path
    assert requests[0].headers["authorization"] == "Bearer injected-test-token"
    assert requests[0].headers["x-goog-user-project"] == "funded-project"
    assert "x-goog-api-key" not in requests[0].headers


def test_selected_context_preserves_distinct_rule_and_argument_identity():
    scenario = SimpleNamespace(rules={"r1": {"description": "Same description"},
                                      "r2": {"description": "Same description"}})
    af = {"arguments": [{"id": "a1", "top_rule": "r1"}, {"id": "a2", "top_rule": "r2"}]}
    result = resolve_context_refs(scenario, af, [{"kind": "rule", "id": "r2"},
                                                {"kind": "argument", "id": "a1"}])
    assert result[0]["id"] == "r2" and result[1]["value"]["top_rule"] == "r1"
    with pytest.raises(ValueError, match="no longer exists"):
        resolve_context_refs(scenario, af, [{"kind": "rule", "id": "deleted"}])


def test_evidence_uses_exact_attached_source_spans_and_rejects_invention():
    source = "Context. The witness did not see possession. The record is incomplete."
    block = build_corpus_block(None, [], "Example", query="witness possession",
        sources=[{"filename": "record.txt", "text": source}], verified_spans=True)
    passages = supplied_sources(block)
    evidence, issues = source_evidence('The record says "The witness did not see possession." [record.txt]', passages)
    assert issues == [] and evidence
    assert evidence[0]["quote"] == source[evidence[0]["start"]:evidence[0]["end"]]
    assert source_evidence('The record says "The witness clearly saw possession." [record.txt]', passages)[1]


def test_paraphrase_has_inspectable_evidence_without_claiming_verbatim_prose():
    evidence, issues = source_evidence("Possession remains uncertain. [record.txt]",
                                      {"record.txt": [(12, "The witness did not see possession.")]})
    assert not issues and evidence[0]["start"] == 12 and evidence[0]["verified"]


def test_exact_quote_in_another_document_does_not_validate_wrong_attribution():
    sources = {"first.txt": [(0, "The permit was valid.")],
               "second.txt": [(0, "The permit had expired.")]}
    _, issues = source_evidence(
        'The first record says "The permit had expired." [first.txt] '
        'The other record disagrees. [second.txt]', sources)
    assert issues
    evidence, issues = source_evidence(
        'One says "The permit was valid." [first.txt] '
        'The other says "The permit had expired." [second.txt]', sources)
    assert not issues
    assert {(item["source"], item["quote"]) for item in evidence} == {
        ("first.txt", "The permit was valid."), ("second.txt", "The permit had expired.")}


def test_rule_description_in_separate_paragraph_is_not_a_source_quote():
    _, issues = source_evidence(
        'The rule means "a permit is needed to burn".\n\n'
        'The source discusses the permit. [record.txt]',
        {"record.txt": [(0, "The permit had expired.")]})
    assert not issues


@pytest.mark.parametrize("answer", [
    '[record.txt] states: "The permit had expired."',
    '> The permit had expired. [record.txt]',
])
def test_leading_and_blockquote_citations_keep_exact_source_binding(answer):
    evidence, issues = source_evidence(answer, {"record.txt": [(10, "The permit had expired.")]})
    assert not issues and evidence[0]["quote"] == "The permit had expired."
    assert source_evidence(answer, {"record.txt": [(0, "The permit was valid.")]})[1]


def test_quotation_line_wrapping_preserves_raw_source_offsets():
    source = "Preface. The permit\n  had expired. End."
    evidence, issues = source_evidence(
        'The record says "The permit had expired." [record.txt]',
        {"record.txt": [(0, source)]})
    assert not issues
    item = evidence[0]
    assert item["quote"] == source[item["start"]:item["end"]] == "The permit\n  had expired."
    for invented in ("The permit had expired!", "The permit had not expired.", "The Permit had expired."):
        assert source_evidence(f'"{invented}" [record.txt]', {"record.txt": [(0, source)]})[1]


def test_multiline_answer_quote_is_checked_against_the_cited_source():
    evidence, issues = source_evidence('"The permit\nhad expired." [record.txt]',
                                      {"record.txt": [(3, "The permit had expired.")]})
    assert not issues and evidence[0]["start"] == 3
    assert source_evidence('"The permit\nhad expired." [record.txt]',
                           {"record.txt": [(0, "The permit was valid.")]})[1]
