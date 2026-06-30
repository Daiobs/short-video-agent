from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.errors import AppError, ErrorCode
from app.routes.common import error_response
from app.services.local_chrome import (
    chrome_helper_diagnostics,
    clear_local_chrome_profile,
    consume_local_scan_token,
    is_loopback_client,
    issue_local_scan_token,
    launch_local_chrome_debug,
    load_capture_audit,
    local_helper_security_contract,
    open_douyin_profile_in_local_chrome,
    scan_douyin_profile_from_local_chrome,
    validate_local_scan_token,
)


router = APIRouter(prefix="/api/local-helper", tags=["local-helper"])


class ChromeScanRequest(BaseModel):
    profile_url: str = ""
    token: str = ""
    page_confirmed: bool = False
    max_items: int = 100
    scroll_rounds: int = 6
    sample_set_id: str = ""


class ChromeOpenProfileRequest(BaseModel):
    profile_url: str = ""
    token: str = ""
    page_confirmed: bool = False


class ChromeLaunchRequest(BaseModel):
    profile_url: str = ""
    token: str = ""
    page_confirmed: bool = False


class ChromeClearProfileRequest(BaseModel):
    token: str = ""
    page_confirmed: bool = False


def _require_loopback(request: Request) -> None:
    if not is_loopback_client(request.client.host if request.client else ""):
        raise AppError(ErrorCode.LOCAL_HELPER_FORBIDDEN)


def _consume_confirmed_token(token: str, page_confirmed: bool) -> None:
    validate_local_scan_token(token)
    if not page_confirmed:
        raise AppError(ErrorCode.LOCAL_HELPER_CONFIRMATION_REQUIRED)
    consume_local_scan_token(token)


@router.get("/chrome/status")
def chrome_helper_status(request: Request):
    try:
        _require_loopback(request)
        diagnostics = chrome_helper_diagnostics()
        return {
            "ok": True,
            "enabled": True,
            "scope": "local_only",
            "security_contract": local_helper_security_contract(),
            **diagnostics,
            "security": [
                "只允许本机 127.0.0.1 / localhost 调用。",
                "不读取 Cookie，不返回 Cookie，不写 Cookie 日志。",
                "状态检查只返回匿名标签页数量和就绪状态，不返回标签页标题、URL 或作品数据。",
                "真正读取当前 Chrome 页面 DOM 中可见作品列表，必须走一次性 token + 页面确认后的本机 Chrome 辅助入口。",
                "每次启动 Chrome、打开主页、扫描或清理辅助 profile 都必须先申请一次性 token，并由页面按钮触发确认。",
            ],
        }
    except AppError as error:
        return error_response(error, status_code=403)


@router.post("/chrome/scan-token")
def chrome_scan_token(request: Request):
    try:
        _require_loopback(request)
        return {
            "ok": True,
            "token": issue_local_scan_token(),
            "expires_in_seconds": 120,
            "security_contract": local_helper_security_contract(),
        }
    except AppError as error:
        return error_response(error, status_code=403)


@router.post("/chrome/scan-profile")
def chrome_scan_profile(payload: ChromeScanRequest, request: Request):
    try:
        _require_loopback(request)
        _consume_confirmed_token(payload.token, payload.page_confirmed)
        sample_set = scan_douyin_profile_from_local_chrome(
            payload.profile_url,
            max_items=payload.max_items,
            scroll_rounds=payload.scroll_rounds,
            merge_sample_set_id=payload.sample_set_id,
            authorization_context={
                "page_confirmed": True,
                "one_time_token_consumed": True,
                "trigger": "profile_page_plugin_assisted_scan",
            },
        )
        return {
            "ok": True,
            "set": sample_set.to_dict(),
            "capture_audit": load_capture_audit(sample_set.set_id),
            "security_contract": local_helper_security_contract(),
        }
    except AppError as error:
        status_code = 403 if error.code == ErrorCode.LOCAL_HELPER_FORBIDDEN else 400
        return error_response(error, status_code=status_code)


@router.post("/chrome/open-profile")
def chrome_open_profile(payload: ChromeOpenProfileRequest, request: Request):
    try:
        _require_loopback(request)
        _consume_confirmed_token(payload.token, payload.page_confirmed)
        tab = open_douyin_profile_in_local_chrome(payload.profile_url)
        return {
            "ok": True,
            "tab": tab,
            "security_contract": local_helper_security_contract(),
        }
    except AppError as error:
        status_code = 403 if error.code == ErrorCode.LOCAL_HELPER_FORBIDDEN else 400
        return error_response(error, status_code=status_code)


@router.post("/chrome/launch")
def chrome_launch(payload: ChromeLaunchRequest, request: Request):
    try:
        _require_loopback(request)
        _consume_confirmed_token(payload.token, payload.page_confirmed)
        launch = launch_local_chrome_debug(payload.profile_url)
        return {
            "ok": True,
            "launch": launch,
            "security_contract": local_helper_security_contract(),
        }
    except AppError as error:
        status_code = 403 if error.code == ErrorCode.LOCAL_HELPER_FORBIDDEN else 400
        return error_response(error, status_code=status_code)


@router.post("/chrome/clear-profile")
def chrome_clear_profile(payload: ChromeClearProfileRequest, request: Request):
    try:
        _require_loopback(request)
        _consume_confirmed_token(payload.token, payload.page_confirmed)
        cleanup = clear_local_chrome_profile()
        return {
            "ok": True,
            "cleanup": cleanup,
            "security_contract": local_helper_security_contract(),
        }
    except AppError as error:
        status_code = 403 if error.code == ErrorCode.LOCAL_HELPER_FORBIDDEN else 400
        return error_response(error, status_code=status_code)
