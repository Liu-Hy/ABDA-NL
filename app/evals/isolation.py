"""Fail-closed network and credential isolation for funded evaluations."""
from __future__ import annotations

import os
import re
from contextlib import contextmanager
from typing import Iterator
from urllib.parse import urlsplit
from unittest.mock import patch

import httpx


class EvaluationIsolationError(RuntimeError):
    pass


def assert_no_openrouter_credentials() -> None:
    if any(
        value and "OPENROUTER" in name.upper()
        and any(marker in name.upper() for marker in ("KEY", "TOKEN", "SECRET"))
        for name, value in os.environ.items()
    ):
        raise EvaluationIsolationError(
            "evaluation requires a process without OpenRouter credentials; use the funded evaluation launcher"
        )


def check_funded_request(method: str, url: str) -> None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    azure = any(host.endswith(suffix) for suffix in (".openai.azure.com", ".services.ai.azure.com"))
    gcp = host == "aiplatform.googleapis.com" or bool(re.fullmatch(r"[a-z0-9-]+-aiplatform\.googleapis\.com", host))
    google_auth = host == "oauth2.googleapis.com" and parsed.path == "/token"
    catalog_read = (
        host == "openrouter.ai" and method.upper() == "GET"
        and parsed.path.rstrip("/") == "/api/v1/models"
    )
    if parsed.scheme != "https" or not (azure or gcp or google_auth or catalog_read):
        raise EvaluationIsolationError("evaluation outbound request is outside the funded-provider allowlist")


@contextmanager
def funded_network_only() -> Iterator[None]:
    """Guard the HTTP transports used by the Anthropic, Azure, and Google SDKs.

    Check on send, including redirects, rather than only on construction of a
    route. The application route check and absence of backup keys are additional
    independent protections. Mocked transports can still exercise contracts.
    """
    assert_no_openrouter_credentials()
    sync_send = httpx.Client._send_single_request
    async_send = httpx.AsyncClient._send_single_request

    def guarded_send(client, request, *args, **kwargs):
        check_funded_request(request.method, str(request.url))
        return sync_send(client, request, *args, **kwargs)

    async def guarded_async_send(client, request, *args, **kwargs):
        check_funded_request(request.method, str(request.url))
        return await async_send(client, request, *args, **kwargs)

    try:
        import requests
    except ImportError:
        requests = None

    with patch.object(httpx.Client, "_send_single_request", guarded_send), patch.object(
        httpx.AsyncClient, "_send_single_request", guarded_async_send
    ):
        if requests is None:
            yield
        else:
            requests_send = requests.Session.send

            def guarded_requests_send(session, request, *args, **kwargs):
                check_funded_request(request.method, request.url)
                return requests_send(session, request, *args, **kwargs)

            with patch.object(requests.Session, "send", guarded_requests_send):
                yield
