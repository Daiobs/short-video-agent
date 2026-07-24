from __future__ import annotations

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
REASONING_EFFORTS = {"auto", "low", "medium", "high", "xhigh"}
PROVIDER_OPTIONS = (
    {
        "value": "openai",
        "label": "OpenAI · Responses API",
        "default_api_base": "https://api.openai.com/v1",
    },
    {
        "value": "openai_compatible",
        "label": "OpenAI-compatible · Chat Completions",
        "default_api_base": "",
    },
    {
        "value": "openai_responses",
        "label": "OpenAI-compatible · Responses API",
        "default_api_base": "",
    },
    {
        "value": "anthropic_compatible",
        "label": "Anthropic-compatible · Messages API",
        "default_api_base": "",
    },
)
MODEL_SUGGESTIONS = (
    {"value": "gpt-5.6-sol", "label": "GPT-5.6 Sol"},
    {"value": "gpt-5.6-terra", "label": "GPT-5.6 Terra"},
    {"value": "gpt-5.6-luna", "label": "GPT-5.6 Luna"},
)


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
        "reasoning_effort": effective["reasoning_effort"]
        if effective["reasoning_effort"] in REASONING_EFFORTS
        else "auto",
        "timeout_seconds": effective["timeout_seconds"],
        "final_reduce_timeout_seconds": effective["final_reduce_timeout_seconds"],
        "max_output_tokens": effective["max_output_tokens"],
        "final_reduce_max_output_tokens": effective["final_reduce_max_output_tokens"],
        "provider_options": list(PROVIDER_OPTIONS),
        "model_suggestions": list(MODEL_SUGGESTIONS),
        "reasoning_effort_options": [
            {"value": "auto", "label": "自动（由模型或网关决定）"},
            {"value": "low", "label": "低"},
            {"value": "medium", "label": "中"},
            {"value": "high", "label": "高"},
            {"value": "xhigh", "label": "XHigh"},
        ],
        "status_message": status_message,
    }


def update_llm_settings_payload(payload: dict) -> dict:
    current = effective_llm_settings()
    values = {
        "provider": payload.get("provider", current["provider"]),
        "api_base": payload.get("api_base", current["api_base"]),
        "model": payload.get("model", current["model"]),
        "timeout_seconds": payload.get("timeout_seconds", current["timeout_seconds"]),
        "final_reduce_timeout_seconds": payload.get("final_reduce_timeout_seconds", current["final_reduce_timeout_seconds"]),
        "temperature": payload.get("temperature", current["temperature"]),
        "reasoning_effort": payload.get("reasoning_effort", current["reasoning_effort"]),
        "max_keyframes": payload.get("llm_max_keyframes", payload.get("max_keyframes", current["max_keyframes"])),
        "max_output_tokens": payload.get("max_output_tokens", current["max_output_tokens"]),
        "final_reduce_max_output_tokens": payload.get("final_reduce_max_output_tokens", current["final_reduce_max_output_tokens"]),
    }
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
