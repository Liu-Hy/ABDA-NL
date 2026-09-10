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
    return result


_CITATION = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9_. -]{0,119}\.(?:txt|pdf|md))\]")
_QUOTED = re.compile(r'"([^"]{8,})"|“([^”]{8,})”|^>\s*(.+)$', re.M)


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
    boundary = response.rfind("\n\n", 0, quote.start())
    before = boundary + 2 if boundary >= 0 else 0
    after = response.find("\n\n", quote.end())
    if after < 0:
        after = len(response)
    local = [item for item in citations if before <= item.start() < after]
    quote_end = quote.start(3) if quote.group(3) is not None else quote.end()
    following = [item for item in local if item.start() >= quote_end]
    preceding = [item for item in local if item.end() <= quote.start()]
    if following:
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


def source_evidence(response: str, passages: dict[str, list[tuple[int, str]]]) -> tuple[list[dict[str, Any]], list[str]]:
    evidence: list[dict[str, Any]] = []
    issues: list[str] = []
    citations = list(_CITATION.finditer(response))
    cited = list(dict.fromkeys(m.group(1) for m in citations))
    for match in _QUOTED.finditer(response):
        quote = next(part for part in match.groups() if part is not None).strip()
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
