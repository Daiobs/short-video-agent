from __future__ import annotations

from fastapi import APIRouter, Response

from app.services.workbench_overview import build_workbench_overview


router = APIRouter(prefix="/api/workbench", tags=["workbench"])


@router.get("/overview")
def get_workbench_overview(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True, **build_workbench_overview()}
