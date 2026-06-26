from __future__ import annotations

from app.config import settings
from app.errors import AppError, ErrorCode
from app.services.llm_provider import BaseLLMProvider, get_llm_provider


SUPPORTED_PROVIDERS = {"openai", "openai_compatible", "compatible", "openai_responses", "responses"}
DISABLED_PROVIDERS = {"", "disabled", "none", "off"}


def mask_api_key(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:3]}****{value[-4:]}"


def llm_is_configured() -> bool:
    return (
        settings.llm_provider not in DISABLED_PROVIDERS
        and settings.llm_provider in SUPPORTED_PROVIDERS
        and bool(settings.llm_api_base)
        and bool(settings.llm_api_key)
        and bool(settings.llm_model)
    )


def llm_status_payload() -> dict:
    has_api_key = bool(settings.llm_api_key)
    provider_supported = settings.llm_provider in SUPPORTED_PROVIDERS
    configured = llm_is_configured()
    if configured:
        status_message = "AI 自动拆解已启用，可以测试连接或在 case 页面重新分析。"
    elif settings.llm_provider in DISABLED_PROVIDERS:
        status_message = "AI 自动拆解未启用：请在 .env 中配置 LLM_PROVIDER、LLM_API_KEY 和 LLM_MODEL。"
    elif not provider_supported:
        status_message = f"AI 自动拆解未启用：暂不支持 LLM_PROVIDER={settings.llm_provider}。"
    elif not has_api_key:
        status_message = "AI 自动拆解未启用：缺少 LLM_API_KEY。"
    elif not settings.llm_model:
        status_message = "AI 自动拆解未启用：缺少 LLM_MODEL。"
    else:
        status_message = "AI 自动拆解未启用：请检查 LLM_API_BASE、LLM_API_KEY 和 LLM_MODEL。"

    return {
        "provider": settings.llm_provider,
        "api_base": settings.llm_api_base,
        "model": settings.llm_model,
        "configured": configured,
        "has_api_key": has_api_key,
        "masked_api_key": mask_api_key(settings.llm_api_key),
        "llm_max_keyframes": settings.llm_max_keyframes,
        "temperature": settings.llm_temperature,
        "status_message": status_message,
    }


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
        "provider": settings.llm_provider,
        "model": settings.llm_model,
    }
