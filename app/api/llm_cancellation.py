"""Stop provider work when the originating HTTP connection is closed."""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TypeVar

import anyio
from starlette.requests import Request

from app.api.llm_access import llm_http_exception
from app.llm.client import LLMRequestCancelledError, cancellable_request


_Result = TypeVar("_Result")


async def run_cancellable_llm(request: Request, operation: Callable[[], _Result]) -> _Result:
    """Watch the same connection on the replica doing the work.

    FastAPI has consumed the validated JSON body before calling this helper.
    Await receive instead of polling is_disconnected: cancellation-based polls
    can miss disconnect messages behind Starlette's HTTP middleware.
    Keep the worker alive until its reservations have been settled.
    """
    cancelled = threading.Event()

    async def watch_disconnect() -> None:
        while True:
            message = await request.receive()
            if message["type"] == "http.disconnect":
                cancelled.set()
                return

    def run() -> _Result:
        with cancellable_request(cancelled):
            return operation()

    error: BaseException | None = None
    result: _Result
    async with anyio.create_task_group() as group:
        group.start_soon(watch_disconnect)
        try:
            result = await anyio.to_thread.run_sync(run)
        except BaseException as exc:
            # Raise outside the task group, preserving FastAPI's typed HTTP
            # errors instead of wrapping them in an ExceptionGroup.
            error = exc
        finally:
            cancelled.set()
            group.cancel_scope.cancel()
    if isinstance(error, LLMRequestCancelledError):
        raise llm_http_exception(error, byok=False)
    if error is not None:
        raise error
    return result
