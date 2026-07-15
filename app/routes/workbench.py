from __future__ import annotations

import logging

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from app.services.workbench_overview import (
    build_workbench_job_detail,
    build_workbench_overview,
)


router = APIRouter(prefix="/api/workbench", tags=["workbench"])
logger = logging.getLogger(__name__)


@router.get("/overview")
def get_workbench_overview(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True, **build_workbench_overview()}


@router.get("/jobs/{job_id}")
def get_workbench_job(job_id: str):
    try:
        job = build_workbench_job_detail(job_id)
    except Exception as error:
        logger.warning(
            "workbench_job_read_failed",
            extra={"error_type": type(error).__name__},
        )
        return JSONResponse(
            status_code=503,
            headers={"Cache-Control": "no-store"},
            content={
                "ok": False,
                "error_code": "WORKBENCH_SOURCE_UNAVAILABLE",
                "message": "任务状态暂时不可用。",
            },
        )
    if job is None:
        return JSONResponse(
            status_code=404,
            headers={"Cache-Control": "no-store"},
            content={"ok": False, "error_code": "JOB_NOT_FOUND", "message": "任务不存在。"},
        )
    return JSONResponse(
        headers={"Cache-Control": "no-store"},
        content={"ok": True, "job": job},
    )
