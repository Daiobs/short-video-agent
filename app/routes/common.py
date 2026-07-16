from __future__ import annotations

from fastapi.responses import JSONResponse

from app.errors import AppError, error_message


def error_response(error: AppError, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"ok": False, **error.as_dict()},
        headers={"Cache-Control": "no-store"},
    )


def not_implemented_response() -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={
            "ok": False,
            "error_code": "NOT_IMPLEMENTED",
            "message": error_message("NOT_IMPLEMENTED"),
        },
    )
