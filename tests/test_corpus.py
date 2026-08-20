"""Tests for safe local corpus extraction."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.llm import corpus
from app.llm.corpus import CorpusLoadError


def test_pdf_extraction_requires_a_resolved_executable(tmp_path, monkeypatch):
    document = tmp_path / "paper.pdf"
    document.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(corpus.shutil, "which", lambda _name: None)

    with pytest.raises(CorpusLoadError, match="pdftotext not found"):
        corpus._read_corpus_file(document)


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
