"""Low-cardinality in-process HTTP telemetry for platform scraping."""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class _Metric:
    count: int = 0
    duration_seconds: float = 0.0


class RequestMetrics:
    def __init__(self) -> None:
        self._started_at = time.monotonic()
        self._lock = threading.Lock()
        self._in_flight = 0
        self._requests: dict[tuple[str, str, int], _Metric] = defaultdict(_Metric)

    def begin(self) -> float:
        with self._lock:
            self._in_flight += 1
        return time.monotonic()

    def finish(self, method: str, route: str, status_code: int, started_at: float) -> None:
        duration = max(0.0, time.monotonic() - started_at)
        key = (method.upper(), route, int(status_code))
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
            metric = self._requests[key]
            metric.count += 1
            metric.duration_seconds += duration

    def abandon(self) -> None:
        """Release a request that stopped before producing a response."""
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')

    def render(self) -> str:
        with self._lock:
            in_flight = self._in_flight
            items = [
                (key, _Metric(value.count, value.duration_seconds))
                for key, value in self._requests.items()
            ]
            uptime = max(0.0, time.monotonic() - self._started_at)

        lines = [
            "# HELP abda_http_requests_in_flight Current HTTP requests in this process.",
            "# TYPE abda_http_requests_in_flight gauge",
            f"abda_http_requests_in_flight {in_flight}",
            "# HELP abda_process_uptime_seconds Process uptime in seconds.",
            "# TYPE abda_process_uptime_seconds gauge",
            f"abda_process_uptime_seconds {uptime:.6f}",
            "# HELP abda_http_requests_total Completed HTTP requests.",
            "# TYPE abda_http_requests_total counter",
        ]
        for (method, route, status_code), metric in sorted(items):
            labels = (
                f'method="{self._escape(method)}",'
                f'route="{self._escape(route)}",status="{status_code}"'
            )
            lines.append(f"abda_http_requests_total{{{labels}}} {metric.count}")
        lines.extend(
            [
                "# HELP abda_http_request_duration_seconds_sum "
                "Cumulative HTTP request duration.",
                "# TYPE abda_http_request_duration_seconds_sum counter",
            ]
        )
        for (method, route, status_code), metric in sorted(items):
            labels = (
                f'method="{self._escape(method)}",'
                f'route="{self._escape(route)}",status="{status_code}"'
            )
            lines.append(
                f"abda_http_request_duration_seconds_sum{{{labels}}} "
                f"{metric.duration_seconds:.6f}"
            )
        return "\n".join(lines) + "\n"


REQUEST_METRICS = RequestMetrics()
