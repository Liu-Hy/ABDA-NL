#!/usr/bin/env python3
"""CI browser handler that records one local URL without opening a GUI."""

from __future__ import annotations

import os
from pathlib import Path
import sys


def main() -> int:
    destination = os.environ.get("ABDA_BROWSER_CAPTURE_PATH")
    if not destination or len(sys.argv) != 2:
        return 2
    target = Path(destination)
    target.write_text(sys.argv[1] + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
