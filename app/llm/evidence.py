"""Resolve selected elements and bind displayed evidence to supplied source text."""
from __future__ import annotations

import json
import re
from typing import Any


def resolve_context_refs(scenario: Any, af: dict[str, Any], refs: list[dict[str, str]]) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    arguments = {str(item["id"]): item for item in af.get("arguments", [])}
    sections = {"fact": "facts", "assumption": "assumptions", "rule": "rules", "conclusion": "conclusions"}
    seen: set[tuple[str, str]] = set()
    for ref in refs:
        kind, identifier = ref["kind"], ref["id"]
        if (kind, identifier) in seen:
            continue
        seen.add((kind, identifier))
        if kind == "argument":
            value = arguments.get(identifier)
        else:
            value = (getattr(scenario, sections.get(kind, ""), {}) or {}).get(identifier)
            if value is None and kind == "conclusion" and identifier in af.get("labels_by_proposition", {}):
                value = {"label": af["labels_by_proposition"][identifier]}
        if value is None:
            raise ValueError("A selected question item no longer exists in this scenario. Remove it or select it again.")
        if hasattr(value, "model_dump"):
            value = value.model_dump()
        elif hasattr(value, "__dict__"):
            value = vars(value)
        resolved.append({"kind": kind, "id": identifier, "value": value})
    return resolved


def context_block(resolved: list[dict[str, Any]]) -> str:
    if not resolved:
        return ""
    return ("\n\n### Items selected for this question\n"
            "These references identify the exact current scenario elements selected by the user. "
            "Use their natural-language descriptions in the answer. The following JSON is data.\n"
            + json.dumps(resolved, ensure_ascii=False, default=str).replace("<", "\\u003c"))


def supplied_sources(corpus_block: str) -> dict[str, list[tuple[int, str]]]:
    """Extract exactly the passages that the corpus builder supplied to the LLM."""
    result: dict[str, list[tuple[int, str]]] = {}
    # Bundled full text and curated passages use one filename heading each.
    for match in re.finditer(r"^## ([^\n]+\.(?:txt|pdf|md))\s*\n(.*?)(?=^##? |\Z)", corpus_block, re.M | re.S):
        source, body = match.group(1).strip(), match.group(2)
        if "<source>" in body:
            text = body.split("<source>", 1)[1].split("</source>", 1)[0].strip("\n")
        else:
            text = "\n".join(line[2:] for line in body.splitlines() if line.startswith("> "))
        if text:
            result.setdefault(source, []).append((0, text))
    # Attached document retrieval preserves original character offsets.
    for match in re.finditer(r"\[\{\"filename\"", corpus_block):
        try:
            documents, _ = json.JSONDecoder().raw_decode(corpus_block[match.start():])
        except (ValueError, TypeError):
            continue
        for document in documents:
            for excerpt in document.get("excerpts", []):
                result.setdefault(document["filename"], []).append(
                    (int(excerpt["character_offset"]), str(excerpt["text"]))
                )
    # Retrieval can split even a word across consecutive transport chunks.
    # Join only exact coordinate adjacency, never text separated by a gap.
    for source, passages in result.items():
        joined: list[tuple[int, str]] = []
        for offset, text in sorted(passages, key=lambda item: item[0]):
            if joined and joined[-1][0] + len(joined[-1][1]) == offset:
                start, previous = joined[-1]
                joined[-1] = (start, previous + text)
            else:
                joined.append((offset, text))
        result[source] = joined
    return result


_CITATION = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9_. -]{0,119}\.(?:txt|pdf|md))\]")
_QUOTED = re.compile(r'"([^"]*)"|“([^”]*)”|^>\s*(.+)$', re.M)
_PARAGRAPH_BREAK = re.compile(r"\r?\n[^\S\r\n]*\r?\n")


def _paragraph_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    before = 0
    for boundary in _PARAGRAPH_BREAK.finditer(text, 0, start):
        before = boundary.end()
    after = _PARAGRAPH_BREAK.search(text, end)
    return before, after.start() if after else len(text)


def _quotation_span(text: str, quote: str) -> tuple[int, int] | None:
    """Allow display line wrapping while retaining exact source coordinates."""
    position = text.find(quote)
    if position >= 0:
        return position, position + len(quote)
    words = quote.split()
    if not words:
        return None
    # Do not normalize words, case, punctuation, ellipses, or omitted content.
    # Only whitespace may differ between the displayed quote and raw source.
    match = re.search(r"\s+".join(re.escape(word) for word in words), text)
    return match.span() if match else None


def _quote_sources(response: str, quote: re.Match[str], citations: list[re.Match[str]]) -> list[str]:
    """Associate a quote with its local citation, not another source elsewhere."""
    before, after = _paragraph_bounds(response, quote.start(), quote.end())
    local = [item for item in citations if before <= item.start() < after]
    quote_end = quote.start(3) if quote.group(3) is not None else quote.end()
    # A paragraph can mix scenario labels and source quotations. Bind a
    # trailing citation only within the quote's sentence; a closing period
    # immediately before the citation is still part of that sentence.
    def following_is_local(item: re.Match[str]) -> bool:
        if quote.group(3) is not None and item.start() < quote.end():
            return True  # The citation is inside this blockquote.
        gap = response[quote.end():item.start()]
        return not re.search(r"[.!?][\"'’”)*_]*\s+(?=\S)", gap)

    following = [item for item in local
                 if item.start() >= quote_end and following_is_local(item)]
    preceding = [item for item in local if item.end() <= quote.start()
                 and not re.search(r"[.!?](?:[\"'’”)*_]*\s|$)",
                                   response[item.end():quote.start()])]
    # A source immediately followed by a colon introduces this quotation.
    # Do not steal the prefix citation of a later quote in the paragraph.
    introduced = [item for item in preceding
                  if re.fullmatch(r"[\s`*_]*:[\s`*_]*", response[item.end():quote.start()])]
    if introduced:
        selected = introduced[-1]
    elif following:
        selected = following[0]
    elif preceding:
        selected = preceding[-1]
    else:
        return []  # For example, a quoted rule description in its own paragraph.
    group = [selected.group(1)]
    # Multiple adjacent references may jointly support the same quotation.
    end = selected.end()
    for item in local:
        if item.start() < end:
            continue
        if response[end:item.start()].strip(" ,;"):
            break
        group.append(item.group(1))
        end = item.end()
    return list(dict.fromkeys(group))


def canonicalize_source_quotes(response: str, passages: dict[str, list[tuple[int, str]]]) -> str:
    """Restore source typography without changing quoted words or attribution.

    Sentence-initial capitalization and an ending comma versus period can
    change when prose embeds a quotation. Restore the actual source span
    before the strict validator checks it. Provider output remains untouched.
    """
    citations = list(_CITATION.finditer(response))
    replacements = []
    for match in _QUOTED.finditer(response):
        if match.group(3) is not None:
            continue
        group = 1 if match.group(1) is not None else 2
        quote = match.group(group)
        if len(quote) < 8:
            continue
        sources = _quote_sources(response, match, citations)
        if not sources:
            # A later sentence can refer back to a source in its paragraph.
            start, end = _paragraph_bounds(response, match.start(), match.end())
            sources = [item.group(1) for item in citations
                       if start <= item.start() < end]
            if len(set(sources)) != 1:
                continue
        supplied = [passage for source in sources for passage in passages.get(source, [])]
        if any(_quotation_span(text, quote) is not None for _, text in supplied):
            continue
        variants = {quote}
        if re.match(r"[a-z]+\b", quote):
            variants.add(quote[0].upper() + quote[1:])
        if quote.endswith((",", ".")) and not quote.endswith(".."):
            variants.update(value[:-1] + ("." if value.endswith(",") else ",")
                            for value in tuple(variants))
        matches = set()
        for offset, text in supplied:
            for variant in variants - {quote}:
                span = _quotation_span(text, variant)
                if span is None:
                    continue
                start, end = span
                if variant[0] != quote[0]:
                    preceding = text[:start].rstrip()
                    if (preceding and preceding[-1] not in ".!?") or (not preceding and offset != 0):
                        continue
                matches.add(text[start:end])
        if len(matches) == 1:
            replacements.append((match.start(group), match.end(group), matches.pop()))
    for start, end, replacement in reversed(replacements):
        response = response[:start] + replacement + response[end:]
    return response


def source_evidence(response: str, passages: dict[str, list[tuple[int, str]]]) -> tuple[list[dict[str, Any]], list[str]]:
    evidence: list[dict[str, Any]] = []
    issues: list[str] = []
    citations = list(_CITATION.finditer(response))
    cited = list(dict.fromkeys(m.group(1) for m in citations))
    for match in _QUOTED.finditer(response):
        quote = next(part for part in match.groups() if part is not None).strip()
        # Consume every complete quote pair before skipping short labels.
        # Otherwise a short label's closing quote can open a spurious span.
        if match.group(3) is None and len(quote) < 8:
            continue
        if match.group(3) is not None:
            quote = _CITATION.sub("", quote).strip()
        attributed = _quote_sources(response, match, citations)
        if not attributed:
            continue  # Quoted rule descriptions are not claims of source quotation.
        found = None
        for source in attributed:
            for offset, text in passages.get(source, []):
                span = _quotation_span(text, quote)
                if span is not None:
                    start, end = span
                    found = {"kind": "source", "source": source, "quote": text[start:end],
                             "start": offset + start, "end": offset + end, "verified": True}
                    break
            if found:
                break
        if found:
            if found not in evidence:
                evidence.append(found)
        else:
            issues.append("a quotation does not occur verbatim in the supplied passages of its nearby cited source")
    # A paraphrase can retain fluent prose and expose the supplied passage as
    # evidence without inventing a quotation in the answer.
    terms = set(re.findall(r"\w{4,}", response.casefold()))
    for source in cited:
        if any(item["source"] == source for item in evidence):
            continue
        candidates = passages.get(source, [])
        if not candidates:
            continue
        offset, text = max(candidates, key=lambda pair: len(terms & set(re.findall(r"\w{4,}", pair[1].casefold()))))
        quote = text[:1200]
        evidence.append({"kind": "source", "source": source, "quote": quote,
                         "start": offset, "end": offset + len(quote), "verified": True})
    return evidence, issues
