"""Pytest root configuration.

Adds the project root to `sys.path` so tests can import `app.*`
without an install step.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("ABDA_ENVIRONMENT", "test")
os.environ.setdefault("ABDA_AUTH_MODE", "dev")
os.environ.setdefault("ABDA_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ABDA_AUTO_CREATE_DB", "1")

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
