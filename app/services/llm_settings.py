from __future__ import annotations

import math

from app.config import settings
from app.errors import AppError, ErrorCode
from app.services.llm_provider import BaseLLMProvider, get_llm_provider
from app.services.runtime_settings import effective_llm_settings, update_llm_runtime_settings


SUPPORTED_PROVIDERS = {
    "openai",
    "openai_compatible",
    "compatible",
    "openai_responses",
    "responses",
    "anthropic",
    "anthropic_compatible",
    "claude",
}
DISABLED_PROVIDERS = {"", "disabled", "none", "off"}
LLM_TIMING_LIMITS = {
    "timeout_seconds": (5.0, 300.0, "普通 LLM 请求上限"),
    "creator_distill_request_timeout_seconds": (30.0, 300.0, "Creator 单请求上限"),
    "quick_distill_budget_seconds": (60.0, 600.0, "Quick 总预算"),
    "deep_distill_budget_seconds": (120.0, 1200.0, "Deep 总预算"),
    "batch_job_budget_seconds": (180.0, 1800.0, "Batch 总预算"),
    "final_reduce_timeout_seconds": (30.0, 900.0, "Final Reduce 请求上限"),
    "final_reduce_min_reserve_seconds": (30.0, 600.0, "Final Reduce 预留"),
    "compact_retry_min_remaining_seconds": (10.0, 300.0, "Compact Retry 最低剩余"),
}


def mask_api_key(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:3]}****{value[-4:]}"


def llm_is_configured() -> bool:
    effective = effective_llm_settings()
    return (
        effective["provider"] not in DISABLED_PROVIDERS
        and effective["provider"] in SUPPORTED_PROVIDERS
        and bool(effective["api_base"])
        and bool(effective["api_key"])
        and bool(effective["model"])
    )


def llm_status_payload() -> dict:
    effective = effective_llm_settings()
    has_api_key = bool(effective["api_key"])
    provider_supported = effective["provider"] in SUPPORTED_PROVIDERS
    configured = llm_is_configured()
    if configured:
        status_message = "AI 自动拆解已启用，可以测试连接或在 case 页面重新分析。"
    elif effective["provider"] in DISABLED_PROVIDERS:
        status_message = "AI 自动拆解未启用：请在设置弹窗中配置 Provider、API Key 和 Model。"
    elif not provider_supported:
        status_message = f"AI 自动拆解未启用：暂不支持 LLM_PROVIDER={effective['provider']}。"
    elif not has_api_key:
        status_message = "AI 自动拆解未启用：缺少 LLM_API_KEY。"
    elif not effective["model"]:
        status_message = "AI 自动拆解未启用：缺少 LLM_MODEL。"
    else:
        status_message = "AI 自动拆解未启用：请检查 LLM_API_BASE、LLM_API_KEY 和 LLM_MODEL。"

    return {
        "provider": effective["provider"],
        "api_base": effective["api_base"],
        "model": effective["model"],
        "configured": configured,
        "has_api_key": has_api_key,
        "masked_api_key": mask_api_key(effective["api_key"]),
        "llm_max_keyframes": effective["max_keyframes"],
        "temperature": effective["temperature"],
        "timeout_seconds": effective["timeout_seconds"],
        "creator_distill_request_timeout_seconds": effective["creator_distill_request_timeout_seconds"],
        "final_reduce_timeout_seconds": effective["final_reduce_timeout_seconds"],
        "quick_distill_budget_seconds": effective["quick_distill_budget_seconds"],
        "deep_distill_budget_seconds": effective["deep_distill_budget_seconds"],
        "batch_job_budget_seconds": effective["batch_job_budget_seconds"],
        "final_reduce_min_reserve_seconds": effective["final_reduce_min_reserve_seconds"],
        "compact_retry_min_remaining_seconds": effective["compact_retry_min_remaining_seconds"],
        "max_output_tokens": effective["max_output_tokens"],
        "final_reduce_max_output_tokens": effective["final_reduce_max_output_tokens"],
        "status_message": status_message,
    }


def validate_llm_timing_settings(values: dict) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for key, (minimum, maximum, label) in LLM_TIMING_LIMITS.items():
        try:
            value = float(values.get(key))
        except (TypeError, ValueError) as error:
            raise AppError(ErrorCode.LLM_SETTINGS_INVALID, f"{label}必须是有效数字。") from error
        if not math.isfinite(value):
            raise AppError(ErrorCode.LLM_SETTINGS_INVALID, f"{label}必须是有限数字。")
        if value < minimum or value > maximum:
            raise AppError(
                ErrorCode.LLM_SETTINGS_INVALID,
                f"{label}必须在 {minimum:g}–{maximum:g} 秒之间。",
            )
        normalized[key] = value

    creator_timeout = normalized["creator_distill_request_timeout_seconds"]
    quick_budget = normalized["quick_distill_budget_seconds"]
    deep_budget = normalized["deep_distill_budget_seconds"]
    retry_minimum = normalized["compact_retry_min_remaining_seconds"]
    batch_budget = normalized["batch_job_budget_seconds"]
    final_timeout = normalized["final_reduce_timeout_seconds"]
    final_reserve = normalized["final_reduce_min_reserve_seconds"]
    if quick_budget < creator_timeout:
        raise AppError(ErrorCode.LLM_SETTINGS_INVALID, "Quick 总预算不能小于 Creator 单请求上限。")
    if deep_budget < creator_timeout:
        raise AppError(ErrorCode.LLM_SETTINGS_INVALID, "Deep 总预算不能小于 Creator 单请求上限。")
    if retry_minimum >= quick_budget:
        raise AppError(ErrorCode.LLM_SETTINGS_INVALID, "Compact Retry 最低剩余必须小于 Quick 总预算。")
    if retry_minimum >= deep_budget:
        raise AppError(ErrorCode.LLM_SETTINGS_INVALID, "Compact Retry 最低剩余必须小于 Deep 总预算。")
    if final_reserve >= batch_budget:
        raise AppError(ErrorCode.LLM_SETTINGS_INVALID, "Final Reduce 预留必须小于 Batch 总预算。")
    if final_timeout > batch_budget:
        raise AppError(ErrorCode.LLM_SETTINGS_INVALID, "Final Reduce 请求上限不能大于 Batch 总预算。")
    return normalized


def update_llm_settings_payload(payload: dict) -> dict:
    current = effective_llm_settings()
    values = {
        "provider": payload.get("provider", current["provider"]),
        "api_base": payload.get("api_base", current["api_base"]),
        "model": payload.get("model", current["model"]),
        "timeout_seconds": payload.get("timeout_seconds", current["timeout_seconds"]),
        "creator_distill_request_timeout_seconds": payload.get(
            "creator_distill_request_timeout_seconds",
            current["creator_distill_request_timeout_seconds"],
        ),
        "final_reduce_timeout_seconds": payload.get("final_reduce_timeout_seconds", current["final_reduce_timeout_seconds"]),
        "quick_distill_budget_seconds": payload.get(
            "quick_distill_budget_seconds",
            current["quick_distill_budget_seconds"],
        ),
        "deep_distill_budget_seconds": payload.get(
            "deep_distill_budget_seconds",
            current["deep_distill_budget_seconds"],
        ),
        "batch_job_budget_seconds": payload.get(
            "batch_job_budget_seconds",
            current["batch_job_budget_seconds"],
        ),
        "final_reduce_min_reserve_seconds": payload.get(
            "final_reduce_min_reserve_seconds",
            current["final_reduce_min_reserve_seconds"],
        ),
        "compact_retry_min_remaining_seconds": payload.get(
            "compact_retry_min_remaining_seconds",
            current["compact_retry_min_remaining_seconds"],
        ),
        "temperature": payload.get("temperature", current["temperature"]),
        "max_keyframes": payload.get("llm_max_keyframes", payload.get("max_keyframes", current["max_keyframes"])),
        "max_output_tokens": payload.get("max_output_tokens", current["max_output_tokens"]),
        "final_reduce_max_output_tokens": payload.get("final_reduce_max_output_tokens", current["final_reduce_max_output_tokens"]),
    }
    values.update(validate_llm_timing_settings(values))
    if payload.get("clear_api_key"):
        values["api_key"] = ""
    elif str(payload.get("api_key") or "").strip():
        values["api_key"] = str(payload.get("api_key") or "").strip()
    update_llm_runtime_settings(values)
    return llm_status_payload()


def test_llm_connection(provider: BaseLLMProvider | None = None) -> dict:
    if not llm_is_configured():
        raise AppError(ErrorCode.LLM_NOT_CONFIGURED)

    llm = provider or get_llm_provider()
    result = llm.analyze(
        '这是一次连接测试。请只返回合法 JSON：{"ok": true, "message": "pong"}',
        [],
    )
    if result.get("ok") is not True:
        raise AppError(ErrorCode.LLM_RESPONSE_INVALID, "模型没有返回预期的 JSON：{\"ok\": true, ...}。")
    return {
        "ok": True,
        "message": str(result.get("message") or "pong"),
        "provider": effective_llm_settings()["provider"],
        "model": effective_llm_settings()["model"],
    }
