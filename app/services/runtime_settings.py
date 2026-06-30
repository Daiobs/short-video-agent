from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

from app.config import settings


LOCAL_SETTINGS_PATH = settings.project_root / ".local_settings.json"
_LOCK = Lock()


def load_local_settings() -> dict[str, Any]:
    if not LOCAL_SETTINGS_PATH.is_file():
        return {}
    try:
        payload = json.loads(LOCAL_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_local_settings(payload: dict[str, Any]) -> None:
    with _LOCK:
        LOCAL_SETTINGS_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def update_local_section(section: str, values: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        payload = load_local_settings()
        current = payload.get(section)
        if not isinstance(current, dict):
            current = {}
        current.update(values)
        payload[section] = current
        LOCAL_SETTINGS_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return payload


def _local_value(section: str, key: str, fallback):
    payload = load_local_settings()
    section_payload = payload.get(section)
    if isinstance(section_payload, dict) and key in section_payload:
        return section_payload.get(key)
    return fallback


def _safe_float(value, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def effective_llm_settings() -> dict[str, Any]:
    return {
        "provider": str(_local_value("llm", "provider", settings.llm_provider) or "").strip().lower(),
        "api_base": str(_local_value("llm", "api_base", settings.llm_api_base) or "").rstrip("/"),
        "api_key": str(_local_value("llm", "api_key", settings.llm_api_key) or ""),
        "model": str(_local_value("llm", "model", settings.llm_model) or "").strip(),
        "timeout_seconds": _safe_float(_local_value("llm", "timeout_seconds", settings.llm_timeout_seconds), settings.llm_timeout_seconds),
        "temperature": _safe_float(_local_value("llm", "temperature", settings.llm_temperature), settings.llm_temperature),
        "max_keyframes": _safe_int(_local_value("llm", "max_keyframes", settings.llm_max_keyframes), settings.llm_max_keyframes),
        "max_output_tokens": _safe_int(_local_value("llm", "max_output_tokens", settings.llm_max_output_tokens), settings.llm_max_output_tokens),
        "image_max_width": _safe_int(_local_value("llm", "image_max_width", settings.llm_image_max_width), settings.llm_image_max_width),
        "image_jpeg_quality": _safe_int(_local_value("llm", "image_jpeg_quality", settings.llm_image_jpeg_quality), settings.llm_image_jpeg_quality),
    }


def update_llm_runtime_settings(values: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "provider",
        "api_base",
        "api_key",
        "model",
        "timeout_seconds",
        "temperature",
        "max_keyframes",
        "max_output_tokens",
    }
    cleaned = {key: value for key, value in values.items() if key in allowed}
    if "provider" in cleaned:
        cleaned["provider"] = str(cleaned["provider"] or "disabled").strip().lower()
    if "api_base" in cleaned:
        cleaned["api_base"] = str(cleaned["api_base"] or "").strip().rstrip("/")
    if "api_key" in cleaned:
        cleaned["api_key"] = str(cleaned["api_key"] or "").strip()
    if "model" in cleaned:
        cleaned["model"] = str(cleaned["model"] or "").strip()
    for key in ("timeout_seconds", "temperature"):
        if key in cleaned:
            cleaned[key] = float(cleaned[key] or 0)
    for key in ("max_keyframes", "max_output_tokens"):
        if key in cleaned:
            cleaned[key] = int(cleaned[key] or 0)
    update_local_section("llm", cleaned)
    return effective_llm_settings()


def effective_douyin_settings() -> dict[str, str]:
    return {
        "cookie": str(_local_value("douyin", "cookie", settings.douyin_cookie) or ""),
        "user_agent": str(_local_value("douyin", "user_agent", settings.douyin_user_agent) or "").strip(),
        "referer": str(_local_value("douyin", "referer", settings.douyin_referer) or "https://www.douyin.com/").strip(),
    }


def update_douyin_runtime_settings(values: dict[str, Any]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for source_key, target_key in (
        ("cookie", "cookie"),
        ("douyin_cookie", "cookie"),
        ("user_agent", "user_agent"),
        ("referer", "referer"),
    ):
        if source_key in values:
            cleaned[target_key] = str(values.get(source_key) or "").strip()
    update_local_section("douyin", cleaned)
    return effective_douyin_settings()
