from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.errors import AppError, ErrorCode


JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class BaseLLMProvider:
    def analyze(self, prompt: str, image_paths: list[Path]) -> dict:
        raise NotImplementedError


class OpenAICompatibleProvider(BaseLLMProvider):
    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        temperature: float | None = None,
    ) -> None:
        self.api_base = (api_base or settings.llm_api_base).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.llm_api_key
        self.model = model or settings.llm_model
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.llm_timeout_seconds
        self.temperature = temperature if temperature is not None else settings.llm_temperature

    def analyze(self, prompt: str, image_paths: list[Path]) -> dict:
        if not self.api_key or not self.model:
            raise AppError(ErrorCode.LLM_NOT_CONFIGURED)

        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for path in image_paths:
            if path.is_file():
                content.append({"type": "image_url", "image_url": {"url": _image_data_url(path)}})

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是短视频内容策略分析师。只输出合法 JSON，不要输出 Markdown。",
                },
                {
                    "role": "user",
                    "content": content,
                },
            ],
            "temperature": self.temperature,
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                response = client.post(
                    f"{self.api_base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            if response.status_code >= 400:
                raise AppError(ErrorCode.LLM_REQUEST_FAILED, f"大模型 API 返回 HTTP {response.status_code}。")
            data = response.json()
            text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
            return parse_json_text(text)
        except AppError:
            raise
        except httpx.TimeoutException as error:
            raise AppError(ErrorCode.LLM_REQUEST_FAILED, "大模型 API 请求超时。") from error
        except Exception as error:
            raise AppError(ErrorCode.LLM_REQUEST_FAILED, str(error)[:500]) from error


def get_llm_provider() -> BaseLLMProvider:
    if settings.llm_provider in {"", "disabled", "none", "off"}:
        raise AppError(ErrorCode.LLM_NOT_CONFIGURED)
    if settings.llm_provider in {"openai", "openai_compatible", "compatible"}:
        return OpenAICompatibleProvider()
    raise AppError(ErrorCode.LLM_NOT_CONFIGURED, f"不支持的 LLM_PROVIDER：{settings.llm_provider}")


def parse_json_text(text: str) -> dict:
    candidate = (text or "").strip()
    match = JSON_FENCE_RE.search(candidate)
    if match:
        candidate = match.group(1).strip()
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise AppError(ErrorCode.LLM_RESPONSE_INVALID) from error
    if not isinstance(data, dict):
        raise AppError(ErrorCode.LLM_RESPONSE_INVALID)
    return data


def _image_data_url(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"
