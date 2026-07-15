from __future__ import annotations

import logging
from datetime import date
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.services.library_assets import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    build_library_assets,
)


router = APIRouter(prefix="/api/library", tags=["library"])
logger = logging.getLogger(__name__)


@router.get("/assets")
def get_library_assets(
    asset_type: Literal["case", "creator_report", "strategy_plan"] | None = Query(None, alias="type"),
    status: Literal["ready", "incomplete", "missing", "stale"] | None = None,
    query: str = Query("", max_length=120),
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(1, ge=1, le=100_000),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    refresh: bool = False,
):
    if date_from and date_to and date_from > date_to:
        return JSONResponse(
            status_code=400,
            headers={"Cache-Control": "no-store"},
            content={
                "ok": False,
                "error_code": "LIBRARY_DATE_RANGE_INVALID",
                "message": "开始日期不能晚于结束日期。",
            },
        )
    try:
        payload = build_library_assets(
            asset_type=asset_type or "",
            status=status or "",
            query=query,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
            refresh=refresh,
        )
    except Exception as error:
        logger.warning(
            "library_assets_read_failed",
            extra={"error_type": type(error).__name__},
        )
        return JSONResponse(
            status_code=503,
            headers={"Cache-Control": "no-store"},
            content={
                "ok": False,
                "error_code": "LIBRARY_SOURCE_UNAVAILABLE",
                "message": "资产索引暂时不可用，请稍后重试。",
            },
        )
    return JSONResponse(
        headers={"Cache-Control": "no-store"},
        content={"ok": True, **payload},
    )
