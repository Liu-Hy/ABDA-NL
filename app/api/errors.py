"""Exception-to-response mapping for the HTTP API.

Maps domain exceptions raised by `app.scenario` modules to HTTP
responses shaped as `{"errors": [{"code", "path", "message"}, ...]}`.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.abda_bridge import ArgumentConstructionError
from app.api.models import ErrorDetail, ErrorResponse
from app.scenario.diff_ops import DiffOpError
from app.scenario.catalog import ScenarioNotFoundError
from app.scenario.loader import ScenarioValidationError
from app.scenario.save import (
    InvalidScenarioId,
    SaveVerificationFailed,
    ScenarioIdCollision,
)


log = logging.getLogger(__name__)


def _response(status_code: int, errors: list[ErrorDetail]) -> JSONResponse:
    payload = ErrorResponse(errors=errors).model_dump()
    return JSONResponse(status_code=status_code, content=payload)


async def _scenario_validation_handler(
    request: Request, exc: ScenarioValidationError
) -> JSONResponse:
    details = [
        ErrorDetail(code="scenario_invalid", path="<root>", message=msg)
        for msg in exc.errors
    ] or [ErrorDetail(code="scenario_invalid", path="<root>", message=str(exc))]
    return _response(400, details)


async def _diff_op_handler(request: Request, exc: DiffOpError) -> JSONResponse:
    return _response(
        400,
        [ErrorDetail(code="op_invalid", path="<root>", message=str(exc))],
    )


async def _argument_construction_handler(
    request: Request, exc: ArgumentConstructionError
) -> JSONResponse:
    return _response(
        400,
        [
            ErrorDetail(
                code="scenario_unbuildable",
                path="<root>",
                message=str(exc),
            )
        ],
    )


async def _scenario_not_found_handler(
    request: Request, exc: ScenarioNotFoundError
) -> JSONResponse:
    return _response(
        404,
        [ErrorDetail(code="scenario_not_found", path="<root>", message=str(exc))],
    )


async def _invalid_scenario_id_handler(
    request: Request, exc: InvalidScenarioId
) -> JSONResponse:
    return _response(
        400,
        [ErrorDetail(code="invalid_scenario_id", path="save_as_id", message=str(exc))],
    )


async def _scenario_id_collision_handler(
    request: Request, exc: ScenarioIdCollision
) -> JSONResponse:
    # 409 Conflict: signals that the client can retry with overwrite=true.
    return _response(
        409,
        [ErrorDetail(code="scenario_id_collision", path="save_as_id", message=str(exc))],
    )


async def _save_verification_failed_handler(
    request: Request, exc: SaveVerificationFailed
) -> JSONResponse:
    return _response(
        500,
        [ErrorDetail(code="save_verification_failed", path="<root>", message=str(exc))],
    )


async def _request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = [
        ErrorDetail(
            code="request_invalid",
            path="/".join(str(p) for p in err.get("loc", ())) or "<root>",
            message=err.get("msg", "invalid request"),
        )
        for err in exc.errors()
    ]
    return _response(422, details)


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    log.exception(
        "request_unhandled request_id=%s exception=%s",
        request_id,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "code": "internal_error",
                "message": "The request could not be completed.",
                "request_id": request_id,
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ScenarioValidationError, _scenario_validation_handler)
    app.add_exception_handler(DiffOpError, _diff_op_handler)
    app.add_exception_handler(ArgumentConstructionError, _argument_construction_handler)
    app.add_exception_handler(ScenarioNotFoundError, _scenario_not_found_handler)
    app.add_exception_handler(InvalidScenarioId, _invalid_scenario_id_handler)
    app.add_exception_handler(ScenarioIdCollision, _scenario_id_collision_handler)
    app.add_exception_handler(SaveVerificationFailed, _save_verification_failed_handler)
    app.add_exception_handler(RequestValidationError, _request_validation_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
