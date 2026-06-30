from __future__ import annotations

from app.config import settings
from app.services.runtime_settings import effective_douyin_settings, update_douyin_runtime_settings


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
    }


def update_douyin_settings_payload(payload: dict) -> dict:
    values = {
        "user_agent": payload.get("user_agent", effective_douyin_settings()["user_agent"]),
        "referer": payload.get("referer", effective_douyin_settings()["referer"]),
    }
    if payload.get("clear_cookie"):
        values["cookie"] = ""
    elif str(payload.get("douyin_cookie") or payload.get("cookie") or "").strip():
        values["cookie"] = str(payload.get("douyin_cookie") or payload.get("cookie") or "").strip()
    update_douyin_runtime_settings(values)
    return data_source_status_payload()
