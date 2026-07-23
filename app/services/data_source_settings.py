from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.config import settings
from app.errors import AppError, ErrorCode
from app.services.profile_scan import (
    inspect_douyin_cookie,
    public_cookie_diagnostics,
    test_douyin_cookie_api,
)
from app.services.runtime_settings import (
    effective_douyin_settings,
    load_local_settings,
    update_douyin_runtime_settings,
    update_local_section,
)


DOUYIN_HEALTH_SECTION = "douyin_health"


def _cookie_fingerprint(value: str) -> str:
    cleaned = (value or "").strip()
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest() if cleaned else ""


def _store_douyin_health(status: str, message: str = "", *, checked: bool = False) -> None:
    effective = effective_douyin_settings()
    update_local_section(
        DOUYIN_HEALTH_SECTION,
        {
            "status": status,
            "message": str(message or "")[:240],
            "cookie_fingerprint": _cookie_fingerprint(effective["cookie"]),
            "checked_at": datetime.now(timezone.utc).isoformat() if checked else "",
        },
    )


def douyin_source_health_payload() -> dict:
    """Return the last known source state without performing a platform request."""

    effective = effective_douyin_settings()
    cookie = (effective["cookie"] or "").strip()
    if not cookie:
        return {
            "configured": False,
            "status": "not_configured",
            "label": "未配置",
            "last_checked_at": "",
            "status_message": "未配置 Douyin Cookie；仍可使用作品链接、JSON/CSV 或已有 Case。",
        }
    diagnostics = inspect_douyin_cookie(cookie)
    if not diagnostics.get("format_valid"):
        return {
            "configured": False,
            "status": "invalid",
            "label": "格式无效",
            "last_checked_at": "",
            "status_message": "已保存的 Douyin Cookie 格式无效；远端请求不会执行。",
        }
    if not diagnostics.get("login_state_sufficient"):
        return {
            "configured": False,
            "status": "login_required",
            "label": "登录态不足",
            "last_checked_at": "",
            "status_message": "已保存的 Douyin Cookie 缺少必要登录态字段；远端请求不会执行。",
        }

    payload = load_local_settings()
    health = payload.get(DOUYIN_HEALTH_SECTION)
    health = health if isinstance(health, dict) else {}
    same_cookie = health.get("cookie_fingerprint") == _cookie_fingerprint(cookie)
    status = str(health.get("status") or "pending") if same_cookie else "pending"
    if status == "success":
        label = "自检成功"
        message = "最近一次 Cookie Web API 自检成功。"
    elif status == "failed":
        label = "自检失败"
        message = "最近一次 Cookie Web API 自检失败，可改用作品链接、JSON/CSV 或已有 Case。"
    else:
        status = "pending"
        label = "已配置待自检"
        message = "已配置 Douyin Cookie，尚未完成当前 Cookie 的 API 自检。"
    return {
        "configured": True,
        "status": status,
        "label": label,
        "last_checked_at": str(health.get("checked_at") or "") if same_cookie else "",
        "status_message": message,
    }


def mask_cookie(value: str) -> str:
    cleaned = (value or "").strip()
    return "********" if cleaned else ""


def data_source_status_payload() -> dict:
    effective = effective_douyin_settings()
    credential_source = str(effective.get("source") or "")
    has_cookie = bool((effective["cookie"] or "").strip())
    cookie_diagnostics = inspect_douyin_cookie(effective["cookie"])
    cookie_ready = bool(cookie_diagnostics.get("looks_complete"))
    has_user_agent = bool((effective["user_agent"] or "").strip())
    referer = effective["referer"] or "https://www.douyin.com/"
    sources = [
        {
            "id": "manual_links",
            "label": "多作品链接粘贴",
            "role": "fallback",
            "enabled": True,
            "status": "ready",
            "message": "安全兜底：不依赖 Cookie、不绕风控。",
        },
        {
            "id": "browser_dom",
            "label": "浏览器辅助采集",
            "role": "assisted",
            "enabled": True,
            "status": "optional",
            "message": "只读取本机 Chrome 当前页面可见作品，不读取 Cookie 或登录 token。",
        },
        {
            "id": "cookie_api",
            "label": "个人账号 Cookie Web API",
            "role": "main",
            "enabled": cookie_ready,
            "status": "configured" if cookie_ready else "invalid" if has_cookie else "not_configured",
            "message": (
                "主页作品扫描正式主路径；当前优先使用 Chrome 扩展主动同步的本机登录状态。"
                if credential_source == "chrome_extension"
                else "主页作品扫描正式主路径；仅使用用户主动配置的本机 Cookie。"
            ),
        },
        {
            "id": "external_api",
            "label": "外部授权数据源",
            "role": "reserved",
            "enabled": bool(settings.profile_scan_api_base),
            "status": "reserved",
            "message": "预留接口，不作为当前默认路径。",
        },
    ]
    return {
        "configured": cookie_ready,
        "source": credential_source,
        "provider": "cookie_api",
        "has_cookie": has_cookie,
        "masked_cookie": mask_cookie(effective["cookie"]),
        "cookie_diagnostics": public_cookie_diagnostics(cookie_diagnostics),
        "pair_count": int(effective.get("pair_count") or cookie_diagnostics.get("pair_count") or 0),
        "login_key_count": int(
            effective.get("login_key_count") or cookie_diagnostics.get("login_key_count") or 0
        ),
        "last_synced_at": str(effective.get("last_synced_at") or ""),
        "extension_version": str(effective.get("extension_version") or ""),
        "user_agent_configured": has_user_agent,
        "user_agent": effective["user_agent"],
        "referer": referer,
        "profile_scan_provider": settings.profile_scan_provider,
        "sources": sources,
        "status_message": (
            "Chrome 扩展登录状态已同步，并作为主页扫描主路径。"
            if cookie_ready and credential_source == "chrome_extension"
            else "个人账号 Cookie Web API 已配置并作为主页扫描主路径。"
            if cookie_ready
            else "已保存 Cookie，但登录态字段不足；远端自检不会发起请求。"
            if has_cookie
            else "未配置个人账号 Cookie；请使用作品链接、JSON/CSV 或已有 Case 作为安全兜底。"
        ),
        "safety_notes": [
            "扩展同步或手工输入的 Cookie 仅保存在用户目录的 0600 凭据文件，不进入数据库、Job、Case、Prompt、报告、日志或扩展存储。",
            "扩展仅在用户点击后读取 Douyin Cookie，不读取其他域名、localStorage 或 Network。",
            "Cookie 主路径失败时，请人工更新 Cookie，或使用作品链接、JSON/CSV、已有 Case。",
        ],
        "health": douyin_source_health_payload(),
    }


def normalize_cookie_input(value: str) -> str:
    cleaned = (value or "").strip()
    if cleaned.lower().startswith("cookie:"):
        cleaned = cleaned.split(":", 1)[1].strip()
    return cleaned


def update_douyin_settings_payload(payload: dict) -> dict:
    previous_cookie_fingerprint = _cookie_fingerprint(effective_douyin_settings()["cookie"])
    values = {
        "user_agent": payload.get("user_agent", effective_douyin_settings()["user_agent"]),
        "referer": payload.get("referer", effective_douyin_settings()["referer"]),
    }
    if payload.get("clear_cookie"):
        values["cookie"] = ""
    elif str(payload.get("douyin_cookie") or payload.get("cookie") or "").strip():
        candidate = normalize_cookie_input(str(payload.get("douyin_cookie") or payload.get("cookie") or ""))
        diagnostics = inspect_douyin_cookie(candidate)
        if not diagnostics.get("format_valid"):
            raise AppError(ErrorCode.DOUYIN_COOKIE_INVALID)
        if not diagnostics.get("login_state_sufficient"):
            raise AppError(ErrorCode.DOUYIN_LOGIN_REQUIRED)
        values["cookie"] = candidate
    update_douyin_runtime_settings(values)
    current_cookie = effective_douyin_settings()["cookie"]
    if _cookie_fingerprint(current_cookie) != previous_cookie_fingerprint:
        _store_douyin_health("pending" if current_cookie.strip() else "not_configured")
    return data_source_status_payload()


def test_douyin_settings_payload(payload: dict) -> dict:
    profile_url = str(payload.get("profile_url") or "").strip()
    sec_user_id = str(payload.get("sec_user_id") or "").strip()
    if profile_url.startswith("MS4w") and not sec_user_id:
        sec_user_id = profile_url
        profile_url = ""
    result = test_douyin_cookie_api(
        profile_url=profile_url,
        sec_user_id=sec_user_id,
        count=int(payload.get("count") or 5),
    )
    result_status = str(result.get("status") or "")
    if result_status == "ok":
        _store_douyin_health("success", str(result.get("message") or ""), checked=True)
    elif result_status == "not_configured":
        _store_douyin_health("not_configured", str(result.get("message") or ""), checked=False)
    elif result_status in {"config_only", "invalid_target"}:
        # The target was not testable, so retain the last Cookie health result.
        pass
    else:
        _store_douyin_health("failed", str(result.get("message") or ""), checked=True)
    return result
