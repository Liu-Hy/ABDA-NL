"""Content-free diagnostics for unexpected application exceptions."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExceptionDiagnostic:
    """Bounded exception metadata that cannot contain an exception message."""

    kind: str
    location: str


def exception_diagnostic(exc: BaseException) -> ExceptionDiagnostic:
    """Return the exception class and final internal traceback location only."""
    traceback = exc.__traceback__
    if traceback is None:
        return ExceptionDiagnostic(kind=type(exc).__name__, location="unknown")
    while traceback.tb_next is not None:
        traceback = traceback.tb_next
    code = traceback.tb_frame.f_code
    location = f"{Path(code.co_filename).name}:{code.co_name}:{traceback.tb_lineno}"
    return ExceptionDiagnostic(kind=type(exc).__name__, location=location)
