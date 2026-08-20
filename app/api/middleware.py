"""Small ASGI middleware components used by the public service."""
from __future__ import annotations

import logging

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


log = logging.getLogger(__name__)


class _RequestBodyTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    """Reject oversized fixed-length and streamed HTTP request bodies."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content={
                "detail": {
                    "code": "request_too_large",
                    "message": (
                        f"Request body exceeds the {self.max_bytes}-byte service limit."
                    ),
                }
            },
            headers={"Cache-Control": "no-store"},
        )
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_length = headers.get(b"content-length")
        if raw_length is not None:
            try:
                content_length = int(raw_length)
            except ValueError:
                response = JSONResponse(
                    status_code=400,
                    content={
                        "detail": {
                            "code": "content_length_invalid",
                            "message": "Content-Length must be a nonnegative integer.",
                        }
                    },
                    headers={"Cache-Control": "no-store"},
                )
                await response(scope, receive, send)
                return
            if content_length < 0:
                response = JSONResponse(
                    status_code=400,
                    content={
                        "detail": {
                            "code": "content_length_invalid",
                            "message": "Content-Length must be a nonnegative integer.",
                        }
                    },
                    headers={"Cache-Control": "no-store"},
                )
                await response(scope, receive, send)
                return
            if content_length > self.max_bytes:
                await self._reject(scope, receive, send)
                return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _RequestBodyTooLarge
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _RequestBodyTooLarge:
            if response_started:
                log.error("request body limit exceeded after response start")
                raise
            await self._reject(scope, receive, send)
