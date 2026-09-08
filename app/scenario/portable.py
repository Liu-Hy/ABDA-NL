"""Self-contained scenario exchange: all stored meanings and full corpus text."""

from copy import deepcopy
from functools import lru_cache
import json
import re
import threading

from app.scenario import catalog
from app.scenario.materials import MaterialError, validate_sources

_BUNDLED_EXPORT_LOCK = threading.Lock()


@lru_cache(maxsize=32)
def _bundled_texts(root: str, scenario_id: str) -> tuple[tuple[str, str], ...]:
    """Read only the trusted catalog's manifest, never user-specified paths."""
    from pypdf import PdfReader

    scenario = catalog.load_bundled_scenario(scenario_id)
    directory = catalog.bundled_scenario_directory(scenario_id)
    documents = []
    for filename in scenario.corpus:
        path = (directory / "corpus" / filename).resolve()
        if not path.is_relative_to((directory / "corpus").resolve()) or not path.is_file():
            raise MaterialError("A bundled reference is unavailable. Export was not created.")
        if path.stat().st_size > 5_000_000:
            raise MaterialError("A bundled reference exceeds the export limit.")
        if path.suffix.lower() == ".pdf":
            reader = PdfReader(path)
            if len(reader.pages) > 100:
                raise MaterialError("A bundled PDF exceeds the export page limit.")
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
            # PDF layout control characters are represented as text whitespace.
            text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "\n", text)
        else:
            text = path.read_text(encoding="utf-8")
        documents.append((filename, text))
    summary = directory / "corpus_summary.yaml"
    if summary.is_file():
        documents.append(("ABDA-curated-context.txt", summary.read_text(encoding="utf-8")))
    return tuple(documents)


def portable_scenario(raw: dict, source_id: str | None) -> dict:
    result = deepcopy(raw)
    references = list(raw.get("corpus") or [])
    documents = []
    if references:
        if not source_id:
            raise MaterialError("Reference content is missing. Attach the documents before exporting.")
        original = catalog.load_bundled_scenario(source_id)
        if references != original.corpus:
            raise MaterialError("The bundled reference list does not match its source scenario.")
        with _BUNDLED_EXPORT_LOCK:
            texts = _bundled_texts(str(catalog.EXAMPLES_ROOT), source_id)
        documents = [{"filename": name, "text": text} for name, text in texts]
    documents += deepcopy(raw.get("sources") or [])
    validate_sources(documents)
    result["corpus"] = []
    if documents:
        result["sources"] = documents
    else:
        result.pop("sources", None)
    return result


def export_scenario(raw: dict, source_id: str | None) -> dict:
    envelope = {
        "format": "abda-nl-scenario", "version": 3,
        "source_scenario_id": None,
        "scenario": portable_scenario(raw, source_id),
    }
    # Match the browser's compact UTF-8 serialization. Never silently truncate.
    if len(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > 996_000:
        raise MaterialError("The complete scenario exceeds the 1 MB portable file limit. Reduce reference text before saving.")
    return envelope
