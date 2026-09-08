"""Preview bounded document text without saving files or fetching URLs."""

from __future__ import annotations

import base64
import binascii
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading

from app.scenario.materials import MaterialError, MAX_SOURCE_BYTES, validate_sources

_PDF_SLOT = threading.BoundedSemaphore(1)


def preview_source(filename: str, data_base64: str) -> tuple[dict, list[str]]:
    if len(data_base64) > 1_333_336:
        raise MaterialError("Each document must be at most 1 MB.")
    try:
        raw = base64.b64decode(data_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise MaterialError("The uploaded document could not be decoded.") from exc
    if len(raw) > MAX_SOURCE_BYTES:
        raise MaterialError("Each document must be at most 1 MB.")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".txt", ".md", ".pdf"}:
        raise MaterialError("Upload UTF-8 text, Markdown, or a text-based PDF.")
    label = re.sub(r"[^A-Za-z0-9_. -]", "_", Path(filename).stem).strip(" ._")[:100]
    name = (label or "document") + suffix
    warnings = []
    if suffix != ".pdf":
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise MaterialError("Save the document as UTF-8 text before uploading.") from exc
    else:
        if os.name != "posix":
            raise MaterialError(
                "Safe PDF extraction is unavailable here. Upload or paste a text version."
            )
        if not _PDF_SLOT.acquire(blocking=False):
            raise MaterialError("Another PDF is being checked. Try again in a moment.")
        try:
            # This fixed child receives document bytes only, not the service's
            # provider keys, database URLs, or identity environment.
            process = subprocess.run(  # noqa: S603
                [
                    str(Path(sys.executable).absolute()),
                    "-I",
                    str(Path(__file__).with_name("pdf_worker.py")),
                ],
                input=raw,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=12,
                env={"LANG": "C.UTF-8", "PYTHONIOENCODING": "utf-8"},
            )
            if process.returncode != 0 or len(process.stdout) > 700_000:
                raise MaterialError(
                    "Could not safely extract this PDF. Use a text-based PDF of at most 40 pages, or paste relevant text. Scans and encrypted PDFs are not supported."
                )
            text = json.loads(process.stdout)["text"]
            warnings.append(
                "PDF text extraction may change layout or miss figures and tables. Check the extracted text; the original PDF is not stored."
            )
        except (subprocess.TimeoutExpired, OSError, ValueError, KeyError) as exc:
            if isinstance(exc, MaterialError):
                raise
            raise MaterialError(
                "PDF extraction could not finish safely. Upload or paste relevant text instead."
            ) from exc
        finally:
            _PDF_SLOT.release()
    item = {"filename": name, "text": text.strip()}
    validate_sources([item])
    if name != filename:
        warnings.append(f"The citation filename was normalized to {name}.")
    return item, warnings
