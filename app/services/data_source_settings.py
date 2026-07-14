from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.config import settings
from app.services.profile_scan import inspect_douyin_cookie, test_douyin_cookie_api
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
            "status_message": "未配置 Douyin Cookie；仍可使用手动链接或本机 Chrome 辅助。",
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
        message = "最近一次 Cookie Web API 自检失败，可改用手动链接或本机 Chrome 辅助。"
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
    if not cleaned:
        return ""
    if len(cleaned) <= 10:
        return "****"
    return f"{cleaned[:4]}****{cleaned[-4:]}"


def data_source_status_payload() -> dict:
    effective = effective_douyin_settings()
    has_cookie = bool((effective["cookie"] or "").strip())
    has_user_agent = bool((effective["user_agent"] or "").strip())
    referer = effective["referer"] or "https://www.douyin.com/"
    sources = [
        {
            "id": "manual_links",
            "label": "多作品链接粘贴",
            "role": "main",
            "enabled": True,
            "status": "ready",
            "message": "稳定主路径：不依赖 Cookie、不绕风控，适合上线默认入口。",
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
            "label": "Cookie Web API 增强",
            "role": "enhancement",
            "enabled": has_cookie,
            "status": "configured" if has_cookie else "not_configured",
            "message": "只用于提高 Web API 成功率；失败会回退到手动链接或浏览器辅助。",
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
        "configured": has_cookie,
        "provider": "cookie_api",
        "has_cookie": has_cookie,
        "masked_cookie": mask_cookie(effective["cookie"]),
        "cookie_diagnostics": inspect_douyin_cookie(effective["cookie"]),
        "user_agent_configured": has_user_agent,
        "user_agent": effective["user_agent"],
        "referer": referer,
        "profile_scan_provider": settings.profile_scan_provider,
        "sources": sources,
        "status_message": (
            "已配置 Cookie API 增强层；它只会作为可选加速/补全尝试，失败后仍回到主流程。"
            if has_cookie
            else "未配置 Cookie API；当前默认使用手动链接和浏览器辅助采集，不影响主流程。"
        ),
        "safety_notes": [
            "Cookie 不会返回给前端，不会写入 case、prompt 或日志。",
            "Cookie 不是默认依赖，也不用于绕验证码或风控。",
            "公开扫描失败时，请使用多作品链接粘贴或浏览器辅助采集。",
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
        values["cookie"] = normalize_cookie_input(str(payload.get("douyin_cookie") or payload.get("cookie") or ""))
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
