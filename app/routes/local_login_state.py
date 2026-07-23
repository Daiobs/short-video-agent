from __future__ import annotations

import json
from urllib.parse import urlparse

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.errors import AppError, ErrorCode
from app.routes.common import error_response
from app.services.local_chrome import is_loopback_client
from app.services.local_login_state import (
    MAX_REQUEST_BODY_BYTES,
    clear_douyin_login_state,
    complete_pairing,
    login_state_status_payload,
    start_pairing,
    sync_douyin_login_state,
    verify_signed_request,
)


router = APIRouter(prefix="/api/local-login-state", tags=["local-login-state"])


class PairCompletePayload(BaseModel):
    pairing_code: str
    extension_version: str
    schema_version: int


def _require_loopback(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    if not is_loopback_client(client_host):
        raise AppError(ErrorCode.LOCAL_HELPER_FORBIDDEN)


def _require_pair_start_origin(request: Request) -> None:
    origin = (request.headers.get("origin") or "").strip()
    if not origin:
        return
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not is_loopback_client(parsed.hostname):
        raise AppError(ErrorCode.LOCAL_HELPER_FORBIDDEN)


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
    if error.code == ErrorCode.LOCAL_HELPER_FORBIDDEN:
        return 403
    return 400


async def _bounded_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length", "")
    try:
        if content_length and int(content_length) > MAX_REQUEST_BODY_BYTES:
            raise AppError(ErrorCode.LOCAL_LOGIN_STATE_PAYLOAD_TOO_LARGE)
    except ValueError as exc:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID) from exc
    body = await request.body()
    if len(body) > MAX_REQUEST_BODY_BYTES:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_PAYLOAD_TOO_LARGE)
    return body


def _json_object(raw_body: bytes) -> dict:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID) from exc
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
        return error_response(error, _error_status(error))


@router.post("/pair/complete")
def complete_local_login_state_pair(payload: PairCompletePayload, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        _require_loopback(request)
        pairing = complete_pairing(
            payload.pairing_code,
            payload.extension_version,
            payload.schema_version,
        )
        # shared_key is intentionally returned only once, on successful pairing.
        return {"ok": True, "pairing": pairing}
    except AppError as error:
        return error_response(error, _error_status(error))


@router.get("/status")
def get_local_login_state_status(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        _require_loopback(request)
        return {"ok": True, "login_state": login_state_status_payload()}
    except AppError as error:
        return error_response(error, _error_status(error))


@router.post("/douyin/sync")
async def sync_local_douyin_login_state(request: Request):
    try:
        _require_loopback(request)
        raw_body = await _bounded_body(request)
        credentials = verify_signed_request(request.headers, raw_body)
        payload = _json_object(raw_body)
        state = sync_douyin_login_state(payload, credentials)
        return Response(
            content=json.dumps({"ok": True, "login_state": state}, ensure_ascii=False),
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
        )
    except AppError as error:
        return error_response(error, _error_status(error))


@router.delete("/douyin")
async def delete_local_douyin_login_state(request: Request):
    try:
        _require_loopback(request)
        raw_body = await _bounded_body(request)
        credentials = verify_signed_request(request.headers, raw_body)
        state = clear_douyin_login_state(credentials)
        return Response(
            content=json.dumps({"ok": True, "login_state": state}, ensure_ascii=False),
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
        )
    except AppError as error:
        return error_response(error, _error_status(error))
