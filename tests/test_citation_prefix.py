import pytest

from app.llm.evidence import canonicalize_source_quotes, source_evidence


PASSAGES = {
    'morning.txt': [(0, 'At 09:00 the greenhouse window was open.')],
    'afternoon.txt': [(0, 'At 15:00 the greenhouse window was closed.')],
}


@pytest.mark.parametrize('quotes', [('"', '"'), ('“', '”')])
@pytest.mark.parametrize('wrapper', ['', '`', '**'])
def test_explicit_prefix_citations_stay_with_their_own_quotes(quotes, wrapper):
    opening, closing = quotes
    response = (
        f'From {wrapper}[morning.txt]{wrapper}: '
        f'{opening}At 09:00 the greenhouse window was open.{closing} '
        f'From {wrapper}[afternoon.txt]{wrapper}: '
        f'{opening}At 15:00 the greenhouse window was closed.{closing}'
    )
    evidence, issues = source_evidence(response, PASSAGES)
    assert not issues
    assert [(item['source'], item['quote']) for item in evidence] == [
        (name, passages[0][1]) for name, passages in PASSAGES.items()
    ]
    assert canonicalize_source_quotes(response, PASSAGES) == response


@pytest.mark.parametrize('response', [
    'From [afternoon.txt]: "At 09:00 the greenhouse window was open." '
    'From [morning.txt]: "At 15:00 the greenhouse window was closed."',
    'From [afternoon.txt]: "At 09:00 the greenhouse window was open." [morning.txt]',
    '"At 09:00 the greenhouse window was open." [afternoon.txt] '
    '"At 15:00 the greenhouse window was closed." [morning.txt]',
    'From [morning.txt]: "At 09:00 the greenhouse window was closed."',
])
def test_another_source_cannot_rescue_a_wrong_explicit_citation(response):
    assert source_evidence(response, PASSAGES)[1]
    assert canonicalize_source_quotes(response, PASSAGES) == response


def test_trailing_citations_continue_to_resolve():
    response = (
        '"At 09:00 the greenhouse window was open." [morning.txt] '
        '"At 15:00 the greenhouse window was closed." [afternoon.txt]'
    )
    assert not source_evidence(response, PASSAGES)[1]


@pytest.mark.parametrize('separator', ['\n\n', '\n \n', '\n\t\n', '\r\n\r\n', '\r\n \r\n', '\r\n\t\r\n'])
@pytest.mark.parametrize('earlier, trailing, accepted', [
    ('morning.txt', 'afternoon.txt', False),
    ('afternoon.txt', 'morning.txt', True),
])
def test_prefix_in_another_paragraph_cannot_override_local_citation(separator, earlier, trailing, accepted):
    response = (
        f'From [{earlier}]:{separator}'
        f'"At 09:00 the greenhouse window was open." [{trailing}]'
    )
    evidence, issues = source_evidence(response, PASSAGES)
    assert (not issues) is accepted
    if accepted:
        assert any(item['source'] == 'morning.txt' and item['start'] == 0 for item in evidence)


@pytest.mark.parametrize('separator', ['\n\n', '\n \n', '\n\t\n', '\r\n\r\n', '\r\n \r\n', '\r\n\t\r\n'])
def test_typography_fallback_does_not_cross_a_blank_paragraph(separator):
    response = f'From [morning.txt]:{separator}"at 09:00 the greenhouse window was open,"'
    assert canonicalize_source_quotes(response, PASSAGES) == response


@pytest.mark.parametrize('newline', ['\n', '\r\n'])
def test_prefix_can_introduce_a_quote_on_the_next_line(newline):
    response = f'From [morning.txt]:{newline}"At 09:00 the greenhouse window was open."'
    assert not source_evidence(response, PASSAGES)[1]
