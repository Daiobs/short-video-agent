from __future__ import annotations

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.errors import AppError
from app.routes.common import error_response
from app.services import data_source_settings
from app.services import llm_settings
from app.services.tool_preflight import preflight_status_payload


router = APIRouter(prefix="/api/settings", tags=["settings"])


class LLMSettingsUpdate(BaseModel):
    provider: str | None = None
    api_base: str | None = None
    api_key: str | None = None
    model: str | None = None
    timeout_seconds: float | None = None
    temperature: float | None = None
    reasoning_effort: str | None = None
    llm_max_keyframes: int | None = None
    max_keyframes: int | None = None
    max_output_tokens: int | None = None
    clear_api_key: bool = False


class DouyinSettingsUpdate(BaseModel):
    douyin_cookie: str | None = None
    cookie: str | None = None
    user_agent: str | None = None
    referer: str | None = None
    clear_cookie: bool = False


class DouyinSettingsTest(BaseModel):
    profile_url: str | None = None
    sec_user_id: str | None = None
    count: int | None = 5


def _payload_dict(payload: BaseModel) -> dict:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=True)
    return payload.dict(exclude_none=True)


@router.get("/llm")
def get_llm_settings():
    return {"ok": True, "llm": llm_settings.llm_status_payload()}


@router.put("/llm")
def update_llm_settings(payload: LLMSettingsUpdate):
    return {"ok": True, "llm": llm_settings.update_llm_settings_payload(_payload_dict(payload))}


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
def get_data_source_settings(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True, "data_sources": data_source_settings.data_source_status_payload()}


@router.put("/data-sources/douyin")
def update_douyin_data_source_settings(payload: DouyinSettingsUpdate, response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        return {
            "ok": True,
            "data_sources": data_source_settings.update_douyin_settings_payload(_payload_dict(payload)),
        }
    except AppError as error:
        return error_response(error)


@router.post("/data-sources/douyin/test")
def test_douyin_data_source_settings(payload: DouyinSettingsTest, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {
        "ok": True,
        "test": data_source_settings.test_douyin_settings_payload(_payload_dict(payload)),
    }
