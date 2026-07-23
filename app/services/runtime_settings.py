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


def replace_local_section(section: str, values: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        payload = load_local_settings()
        payload[section] = dict(values)
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
        "final_reduce_timeout_seconds": _safe_float(
            _local_value("llm", "final_reduce_timeout_seconds", settings.llm_final_reduce_timeout_seconds),
            settings.llm_final_reduce_timeout_seconds,
        ),
        "temperature": _safe_float(_local_value("llm", "temperature", settings.llm_temperature), settings.llm_temperature),
        "max_keyframes": _safe_int(_local_value("llm", "max_keyframes", settings.llm_max_keyframes), settings.llm_max_keyframes),
        "max_output_tokens": _safe_int(_local_value("llm", "max_output_tokens", settings.llm_max_output_tokens), settings.llm_max_output_tokens),
        "final_reduce_max_output_tokens": _safe_int(
            _local_value("llm", "final_reduce_max_output_tokens", settings.llm_final_reduce_max_output_tokens),
            settings.llm_final_reduce_max_output_tokens,
        ),
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
        "final_reduce_timeout_seconds",
        "temperature",
        "max_keyframes",
        "max_output_tokens",
        "final_reduce_max_output_tokens",
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
    for key in ("timeout_seconds", "final_reduce_timeout_seconds", "temperature"):
        if key in cleaned:
            cleaned[key] = float(cleaned[key] or 0)
    for key in ("max_keyframes", "max_output_tokens", "final_reduce_max_output_tokens"):
        if key in cleaned:
            cleaned[key] = int(cleaned[key] or 0)
    update_local_section("llm", cleaned)
    return effective_llm_settings()


def effective_douyin_settings() -> dict[str, Any]:
    # Imported lazily so the secure credential service can reuse the local
    # settings metadata helpers without creating an import cycle.
    from app.errors import AppError
    from app.services.local_login_state import (
        extension_douyin_credentials,
        manual_douyin_credentials,
        store_manual_douyin_credentials,
    )

    payload = load_local_settings()
    legacy_douyin = payload.get("douyin")
    legacy_douyin = legacy_douyin if isinstance(legacy_douyin, dict) else {}
    legacy_cookie = str(legacy_douyin.get("cookie") or "")
    if legacy_cookie:
        try:
            if not manual_douyin_credentials().get("cookie"):
                store_manual_douyin_credentials(
                    {
                        "cookie": legacy_cookie,
                        "user_agent": str(legacy_douyin.get("user_agent") or settings.douyin_user_agent or ""),
                        "referer": str(
                            legacy_douyin.get("referer")
                            or settings.douyin_referer
                            or "https://www.douyin.com/"
                        ),
                    }
                )
            else:
                manual = manual_douyin_credentials()
                replace_local_section(
                    "douyin",
                    {
                        "configured": True,
                        "source": "manual_secure",
                        "credential_fingerprint": _credential_fingerprint(str(manual.get("cookie") or "")),
                        "updated_at": str(manual.get("updated_at") or ""),
                    },
                )
        except AppError:
            # Preserve read compatibility if the secure credential file cannot
            # be migrated yet; never delete the only remaining credential.
            return {
                "cookie": legacy_cookie,
                "user_agent": str(legacy_douyin.get("user_agent") or settings.douyin_user_agent or "").strip(),
                "referer": str(
                    legacy_douyin.get("referer")
                    or settings.douyin_referer
                    or "https://www.douyin.com/"
                ).strip(),
                "source": "manual_legacy",
                "last_synced_at": "",
                "pair_count": 0,
                "login_key_count": 0,
                "extension_version": "",
            }

    extension = extension_douyin_credentials()
    if extension.get("cookie"):
        return {
            **extension,
            "source": "chrome_extension",
        }

    manual = manual_douyin_credentials()
    manual_cookie = str(manual.get("cookie") or "")
    if manual_cookie:
        return {
            **manual,
            "source": "manual_local",
        }

    environment_cookie = str(settings.douyin_cookie or "")
    return {
        "cookie": environment_cookie,
        "user_agent": str(settings.douyin_user_agent or "").strip(),
        "referer": str(settings.douyin_referer or "https://www.douyin.com/").strip(),
        "source": "environment" if environment_cookie else "",
        "last_synced_at": "",
        "pair_count": 0,
        "login_key_count": 0,
        "extension_version": "",
    }


def update_douyin_runtime_settings(values: dict[str, Any]) -> dict[str, Any]:
    from app.services.local_login_state import store_manual_douyin_credentials

    cleaned: dict[str, str] = {}
    for source_key, target_key in (
        ("cookie", "cookie"),
        ("douyin_cookie", "cookie"),
        ("user_agent", "user_agent"),
        ("referer", "referer"),
    ):
        if source_key in values:
            cleaned[target_key] = str(values.get(source_key) or "").strip()
    store_manual_douyin_credentials(cleaned)
    return effective_douyin_settings()


def _credential_fingerprint(value: str) -> str:
    import hashlib

    return hashlib.sha256((value or "").encode("utf-8")).hexdigest() if value else ""
