from __future__ import annotations

import json
from urllib.parse import urlparse

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from app.errors import AppError, ErrorCode
from app.routes.common import error_response
from app.services.local_chrome import is_loopback_client
from app.services.local_login_state import (
    MAX_REQUEST_BODY_BYTES,
    clear_douyin_login_state,
    complete_pairing,
    login_state_status_payload,
    require_allowed_extension_origin,
    start_pairing,
    sync_douyin_login_state,
    verify_signed_request,
)


router = APIRouter(prefix="/api/local-login-state", tags=["local-login-state"])


class PairCompletePayload(BaseModel):
    pairing_code: str = Field(min_length=8, max_length=32)
    extension_version: str = Field(min_length=5, max_length=64)
    schema_version: int


def _require_loopback(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    if not is_loopback_client(client_host):
        raise AppError(ErrorCode.LOCAL_HELPER_FORBIDDEN)


def _require_pair_start_origin(request: Request) -> None:
    origin = str(request.headers.get("origin") or "").strip()
    if not origin:
        return
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not is_loopback_client(parsed.hostname):
        raise AppError(ErrorCode.LOCAL_HELPER_FORBIDDEN)


def _require_extension(request: Request) -> str:
    return require_allowed_extension_origin(str(request.headers.get("origin") or ""))


def _error_status(error: AppError) -> int:
    if error.code == ErrorCode.LOCAL_LOGIN_STATE_PAYLOAD_TOO_LARGE:
        return 413
    if error.code in {
        ErrorCode.LOCAL_LOGIN_STATE_AUTH_FAILED,
        ErrorCode.LOCAL_LOGIN_STATE_NOT_PAIRED,
        ErrorCode.LOCAL_LOGIN_STATE_TIMESTAMP_INVALID,
    }:
        return 401
    if error.code == ErrorCode.LOCAL_LOGIN_STATE_REPLAY:
        return 409
    if error.code in {
        ErrorCode.LOCAL_HELPER_FORBIDDEN,
        ErrorCode.LOCAL_LOGIN_STATE_EXTENSION_FORBIDDEN,
    }:
        return 403
    if error.code == ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED:
        return 500
    return 400


def _safe_error(error: AppError):
    response = error_response(error, _error_status(error))
    response.headers["Cache-Control"] = "no-store"
    return response


async def _bounded_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length", "")
    try:
        if content_length and int(content_length) > MAX_REQUEST_BODY_BYTES:
            raise AppError(ErrorCode.LOCAL_LOGIN_STATE_PAYLOAD_TOO_LARGE)
    except ValueError as error:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID) from error
    body = await request.body()
    if len(body) > MAX_REQUEST_BODY_BYTES:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_PAYLOAD_TOO_LARGE)
    return body


def _json_object(raw_body: bytes) -> dict:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID) from error
    if not isinstance(payload, dict):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID)
    return payload


@router.post("/pair/start")
def start_local_login_state_pair(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        _require_loopback(request)
        _require_pair_start_origin(request)
        return {"ok": True, "pairing": start_pairing()}
    except AppError as error:
        return _safe_error(error)


@router.post("/pair/complete")
def complete_local_login_state_pair(
    payload: PairCompletePayload,
    request: Request,
    response: Response,
):
    response.headers["Cache-Control"] = "no-store"
    try:
        _require_loopback(request)
        extension_id = _require_extension(request)
        pairing = complete_pairing(
            payload.pairing_code,
            payload.extension_version,
            payload.schema_version,
            extension_id,
        )
        return {"ok": True, "pairing": pairing}
    except AppError as error:
        return _safe_error(error)


@router.get("/status")
def get_local_login_state_status(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        _require_loopback(request)
        origin = str(request.headers.get("origin") or "")
        if origin.lower().startswith("chrome-extension://"):
            _require_extension(request)
        return {"ok": True, "login_state": login_state_status_payload()}
    except AppError as error:
        return _safe_error(error)


@router.post("/douyin/sync")
async def sync_local_douyin_login_state(request: Request):
    try:
        _require_loopback(request)
        extension_id = _require_extension(request)
        raw_body = await _bounded_body(request)
        verified = verify_signed_request(request.headers, raw_body, extension_id)
        state = sync_douyin_login_state(_json_object(raw_body), verified)
        return Response(
            content=json.dumps({"ok": True, "login_state": state}, ensure_ascii=False),
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
        )
    except AppError as error:
        return _safe_error(error)


@router.delete("/douyin")
async def delete_local_douyin_login_state(request: Request):
    try:
        _require_loopback(request)
        extension_id = _require_extension(request)
        raw_body = await _bounded_body(request)
        verified = verify_signed_request(request.headers, raw_body, extension_id)
        state = clear_douyin_login_state(verified)
        return Response(
            content=json.dumps({"ok": True, "login_state": state}, ensure_ascii=False),
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
        )
    except AppError as error:
        return _safe_error(error)
