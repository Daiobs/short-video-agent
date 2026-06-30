from __future__ import annotations

from fastapi import APIRouter

from app.errors import AppError
from app.routes.common import error_response
from app.services import data_source_settings
from app.services import llm_settings
from app.services.tool_preflight import preflight_status_payload


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/llm")
def get_llm_settings():
    return {"ok": True, "llm": llm_settings.llm_status_payload()}


@router.post("/llm/test")
def test_llm_settings():
    try:
        return {"ok": True, "test": llm_settings.test_llm_connection()}
    except AppError as error:
        return error_response(error)


@router.get("/preflight")
def get_preflight_settings():
    return {"ok": True, "preflight": preflight_status_payload()}


@router.get("/data-sources")
def get_data_source_settings():
    return {"ok": True, "data_sources": data_source_settings.data_source_status_payload()}
