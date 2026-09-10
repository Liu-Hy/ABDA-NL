"""Tests for safe local corpus extraction."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.llm import corpus
from app.llm.corpus import CorpusLoadError


def test_custom_scenario_context_never_reads_the_filesystem(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("custom scenario attempted a filesystem read")

    monkeypatch.setattr(corpus.Path, "is_file", forbidden)
    monkeypatch.setattr(corpus.Path, "read_text", forbidden)
    block = corpus.build_corpus_block(None, [], "Custom idea")
    assert "No external source documents" in block
    assert "Do not invent document citations" in block
    with pytest.raises(CorpusLoadError, match="cannot read local"):
        corpus.build_corpus_block(None, ["../../.env"], "Untrusted")


def test_pdf_extraction_fallback_rejects_invalid_pdf(tmp_path, monkeypatch):
    document = tmp_path / "paper.pdf"
    document.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(corpus.shutil, "which", lambda _name: None)

    with pytest.raises(CorpusLoadError, match="source PDF text could not be extracted"):
        corpus._read_corpus_file(document)


def test_pdf_extraction_falls_back_to_pypdf(monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(corpus.shutil, "which", lambda _name: None)
    document = next((Path(__file__).parents[1] / "examples" / "popov_v_hayashi" / "corpus").glob("*.pdf"))
    assert "Popov" in corpus._read_corpus_file(document)


def test_pdf_extraction_uses_the_resolved_executable(tmp_path, monkeypatch):
    document = tmp_path / "paper.pdf"
    document.write_bytes(b"%PDF-1.4\n")
    calls: list[tuple[list[str], dict]] = []
    monkeypatch.setattr(
        corpus.shutil,
        "which",
        lambda name: "/usr/bin/pdftotext" if name == "pdftotext" else None,
    )

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout="extracted text")

    monkeypatch.setattr(corpus.subprocess, "run", fake_run)

    assert corpus._read_corpus_file(document) == "extracted text"
    assert calls == [
        (
            ["/usr/bin/pdftotext", "-layout", str(document), "-"],
            {"check": True, "capture_output": True, "text": True},
        )
    ]
