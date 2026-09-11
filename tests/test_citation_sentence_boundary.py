import pytest

from app.llm.evidence import source_evidence


@pytest.mark.parametrize("quotes", [('"', '"'), ('“', '”')])
@pytest.mark.parametrize("mark", [".", "!", "?"])
def test_sentence_ending_inside_quote_does_not_take_later_citation(quotes, mark):
    opening, closing = quotes
    answer = (
        f'The summary is {opening}keep the window open{mark}{closing} '
        f'The note says {opening}The vent releases hot air.{closing} [note.txt]'
    )
    sources = {"note.txt": [(0, "The vent releases hot air.")]}
    evidence, issues = source_evidence(answer, sources)
    assert not issues
    assert [(item["source"], item["quote"]) for item in evidence] == [
        ("note.txt", "The vent releases hot air.")
    ]


@pytest.mark.parametrize("quotes", [('"', '"'), ('“', '”')])
@pytest.mark.parametrize("mark", [".", "!", "?"])
def test_sentence_ending_inside_quote_keeps_its_immediate_citation(quotes, mark):
    opening, closing = quotes
    sentence = f"The vent releases hot air{mark}"
    sources = {"note.txt": [(0, sentence)]}
    answer = f'The note says {opening}{sentence}{closing} [note.txt]'
    evidence, issues = source_evidence(answer, sources)
    assert not issues
    assert evidence[0]["quote"] == sentence
    assert source_evidence(answer.replace("hot", "cold"), sources)[1]


@pytest.mark.parametrize("quotes", [('"', '"'), ('“', '”')])
@pytest.mark.parametrize("connector", ["and", "or"])
def test_coordinated_quotations_share_citation_and_validate_each_member(quotes, connector):
    opening, closing = quotes
    answer = (
        f'The record says {opening}The permit had expired.{closing} {connector} '
        f'{opening}The gate was closed.{closing} [record.txt]'
    )
    sources = {"record.txt": [(0, "The permit had expired. The gate was closed.")]}
    evidence, issues = source_evidence(answer, sources)
    assert not issues
    assert [item["quote"] for item in evidence] == [
        "The permit had expired.", "The gate was closed.",
    ]
    assert source_evidence(answer.replace("expired", "remained valid"), sources)[1]
    assert source_evidence(answer.replace("closed", "open"), sources)[1]
