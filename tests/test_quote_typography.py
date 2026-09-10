"""Restore harmless display typography while retaining strict source checks."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.llm.chat_service import run_turn
from app.llm.client import LLMResponse
from app.llm.evidence import canonicalize_source_quotes, source_evidence, supplied_sources


@pytest.mark.parametrize("quote,expected", [
    ("The permit had expired,", "The permit had expired."),
    ("the permit had expired.", "The permit had expired."),
    ("the permit had expired,", "The permit had expired."),
])
@pytest.mark.parametrize("opening,closing", [('"', '"'), ('“', '”')])
def test_restores_only_source_typography_and_keeps_raw_evidence(quote, expected, opening, closing):
    source = "Preface. The permit had expired. The gate was closed."
    passages = {"record.txt": [(9, source)]}
    answer = f"The record says {opening}{quote}{closing} [record.txt]"
    fixed = canonicalize_source_quotes(answer, passages)
    assert fixed == f"The record says {opening}{expected}{closing} [record.txt]"
    evidence, issues = source_evidence(fixed, passages)
    assert not issues and len(evidence) == 1
    item = evidence[0]
    assert item["quote"] == source[item["start"] - 9:item["end"] - 9] == expected
    # Standalone verification remains strict; only the displayed text is corrected.
    assert source_evidence(answer, passages)[1]
    assert canonicalize_source_quotes(fixed, passages) == fixed


@pytest.mark.parametrize("quote", [
    "The permit had not expired.",
    "The Permit had expired.",
    "The permit had expired!",
    "The permit had expired?",
    "The permit, had expired.",
    "The permit had... expired.",
    "The permit had expi[red].",
    "The permit expired in 2027.",
])
def test_word_case_polarity_numbers_and_interior_punctuation_cannot_be_repaired(quote):
    passages = {"record.txt": [(0, "The permit had expired. The permit expired in 2026.")]}
    answer = f'"{quote}" [record.txt]'
    assert canonicalize_source_quotes(answer, passages) == answer
    assert source_evidence(answer, passages)[1]


def test_wrong_source_cannot_borrow_another_paragraph_citation():
    sources = {"first.txt": [(0, "The permit was valid.")],
               "second.txt": [(0, "The permit had expired.")]}
    answer = ('The first says "the permit had expired," [first.txt] '
              'The second disagrees. [second.txt]')
    assert canonicalize_source_quotes(answer, sources) == answer
    assert source_evidence(answer, sources)[1]


def test_paragraph_fallback_requires_one_unambiguous_source():
    sources = {"first.txt": [(0, "The permit was valid.")],
               "second.txt": [(0, "The permit had expired.")]}
    answer = ('[first.txt] is the morning record. It states "the permit had expired,". '
              'The afternoon record disagrees [second.txt].')
    assert canonicalize_source_quotes(answer, sources) == answer


def test_excerpt_start_is_not_necessarily_a_sentence_boundary():
    answer = '"polish workers arrived," [record.txt]'
    sources = {"record.txt": [(5000, "Polish workers arrived.")]}
    assert canonicalize_source_quotes(answer, sources) == answer


def test_paragraph_reference_can_restore_typography_without_crossing_paragraphs():
    passages = {"record.txt": [(0, "The permit had expired. This is a categorical constraint, not a balancing test.")]}
    answer = ('[record.txt] says the permit expired. The source calls this '
              '"a categorical constraint, not a balancing test," and allows rescheduling.')
    assert canonicalize_source_quotes(answer, passages) == answer.replace('test,"', 'test."')
    separate = answer.replace('expired. The source', 'expired.\n\nThe source')
    assert canonicalize_source_quotes(separate, passages) == separate


def test_capitalization_requires_a_sentence_boundary_and_unambiguous_source_span():
    answer = '"the permit had expired," [record.txt]'
    interior = {"record.txt": [(0, "The heading The permit had expired. is incomplete.")]}
    assert canonicalize_source_quotes(answer, interior) == answer
    ambiguous = {"record.txt": [(0, "The permit had expired. The permit had expired, before arrival.")]}
    assert canonicalize_source_quotes(answer, ambiguous) == answer


def test_source_line_wrapping_is_restored_with_typography():
    passages = {"record.txt": [(0, "The permit\n  had expired.")]}
    answer = '"the permit had expired," [record.txt]'
    fixed = canonicalize_source_quotes(answer, passages)
    assert fixed == '"The permit\n  had expired." [record.txt]'
    evidence, issues = source_evidence(fixed, passages)
    assert not issues and evidence[0]["start"] == 0


def test_adjacent_retrieval_chunks_preserve_words_and_exact_source_coordinates():
    source = "The permit had expired."
    # Retrieval order can differ from source order; offsets are authoritative.
    block = json.dumps([{"filename": "record.txt", "excerpts": [
        {"character_offset": 18, "text": "pired."},
        {"character_offset": 1, "text": "The permit had ex"},
    ]}])
    passages = supplied_sources(block)
    assert passages == {"record.txt": [(1, source)]}
    evidence, issues = source_evidence(f'"{source}" [record.txt]', passages)
    assert not issues and evidence[0]["start"] == 1
    assert evidence[0]["end"] == 1 + len(source)


@pytest.mark.parametrize("offset", [17, 19])
def test_retrieval_overlap_or_gap_cannot_invent_contiguous_source_text(offset):
    block = json.dumps([{"filename": "record.txt", "excerpts": [
        {"character_offset": 1, "text": "The permit had ex"},
        {"character_offset": offset, "text": "pired."},
    ]}])
    passages = supplied_sources(block)
    assert len(passages["record.txt"]) == 2
    assert source_evidence('"The permit had expired." [record.txt]', passages)[1]


def test_adjacent_offsets_from_different_sources_are_never_joined():
    block = json.dumps([
        {"filename": "first.txt", "excerpts": [{"character_offset": 1, "text": "The permit had ex"}]},
        {"filename": "second.txt", "excerpts": [{"character_offset": 18, "text": "pired."}]},
    ])
    passages = supplied_sources(block)
    assert source_evidence('"The permit had expired." [first.txt] [second.txt]', passages)[1]


def test_actual_chat_uses_exact_source_without_an_extra_call_or_provider_mutation():
    source = "The permit had expired."
    scenario = SimpleNamespace(
        name="Permit", description="A supplied inspection record.",
        facts={}, assumptions={}, rules={}, propositions={}, conclusions={}, corpus=[],
        sources=[{"filename": "record.txt", "text": source}],
    )
    raw = LLMResponse(text='The record says "the permit had expired," [record.txt]',
                      stop_reason="stop", usage={"input_tokens": 10, "output_tokens": 5},
                      latency_ms=12, model="fixture", cost_microusd=23)
    calls = []

    def complete(**kwargs):
        calls.append(kwargs)
        return raw

    result = run_turn(scenario, {"arguments": [], "attacks": [], "labels_by_proposition": {}}, [],
                      [{"role": "user", "content": "What does the record say?"}],
                      scenario_dir=None, client=SimpleNamespace(complete=complete))
    assert result.text == 'The record says "The permit had expired." [record.txt]'
    assert len(calls) == 1 and not result.retried and not result.validator_flags
    assert result.evidence[0]["quote"] == source
    assert raw.text == 'The record says "the permit had expired," [record.txt]'
    assert result.cost_microusd == 23 and result.usage == raw.usage
