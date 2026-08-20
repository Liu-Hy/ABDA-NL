"""Process lock used to serialize SQLite billing changes in local mode."""
from __future__ import annotations

import threading


BILLING_LOCK = threading.RLock()
