"""Disposable PDF text extraction process. No server credentials are inherited."""

from __future__ import annotations

import io
import json
import logging
import resource
import sys


def main() -> int:
    # Delta's Python maps about 230 MiB before imports, mostly shared libraries.
    # Bound virtual address space without assuming it equals resident memory.
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (6, 6))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    logging.disable(logging.CRITICAL)
    from pypdf import PdfReader

    try:
        raw = sys.stdin.buffer.read(1_000_001)
        if len(raw) > 1_000_000 or not raw.startswith(b"%PDF-"):
            return 2
        reader = PdfReader(io.BytesIO(raw), strict=True)
        if reader.is_encrypted or len(reader.pages) > 40:
            return 2
        parts, size = [], 0
        for index, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or "").replace("\x00", "").replace("\f", "\n")
            size += len(text)
            if size > 99_000:
                return 2
            if text.strip():
                parts.append(f"[Page {index}]\n{text.strip()}")
        result = "\n\n".join(parts)
        if not result.strip():
            return 2
        sys.stdout.write(json.dumps({"text": result, "pages": len(reader.pages)}))
        return 0
    except Exception:
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
