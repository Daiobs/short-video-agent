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
            "response_format": {"type": "json_object"},
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
                if response.status_code >= 400 and _response_format_may_be_unsupported(response):
                    payload.pop("response_format", None)
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
            return parse_json_text(_chat_completion_output_text(data))
        except AppError:
            raise
        except httpx.TimeoutException as error:
            raise AppError(ErrorCode.LLM_REQUEST_FAILED, "大模型 API 请求超时。") from error
        except Exception as error:
            raise AppError(ErrorCode.LLM_REQUEST_FAILED, str(error)[:500]) from error


class OpenAIResponsesProvider(BaseLLMProvider):
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

        content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        for path in image_paths:
            if path.is_file():
                content.append({"type": "input_image", "image_url": _image_data_url(path)})

        payload = {
            "model": self.model,
            "instructions": "你是短视频内容策略分析师。只输出合法 JSON，不要输出 Markdown。",
            "input": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
            "temperature": self.temperature,
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                response = client.post(
                    f"{self.api_base}/responses",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            if response.status_code >= 400:
                raise AppError(ErrorCode.LLM_REQUEST_FAILED, f"大模型 API 返回 HTTP {response.status_code}。")
            return parse_json_text(_responses_output_text(response.json()))
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
    if settings.llm_provider in {"openai_responses", "responses"}:
        return OpenAIResponsesProvider()
    raise AppError(ErrorCode.LLM_NOT_CONFIGURED, f"不支持的 LLM_PROVIDER：{settings.llm_provider}")


def parse_json_text(text: str) -> dict:
    candidate = (text or "").strip()
    match = JSON_FENCE_RE.search(candidate)
    if match:
        candidate = match.group(1).strip()
    data = _parse_json_object(candidate)
    if data is None:
        extracted = _extract_json_object(candidate)
        data = _parse_json_object(extracted) if extracted else None
    if data is None:
        raise AppError(ErrorCode.LLM_RESPONSE_INVALID)
    return data


def _parse_json_object(candidate: str) -> dict | None:
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        raise AppError(ErrorCode.LLM_RESPONSE_INVALID)
    return data


def _extract_json_object(text: str) -> str:
    for start, char in enumerate(text or ""):
        if char != "{":
            continue
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            current = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    in_string = False
                continue
            if current == '"':
                in_string = True
            elif current == "{":
                depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
    return ""


def _image_data_url(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _chat_completion_output_text(data: dict) -> str:
    message = ((data.get("choices") or [{}])[0].get("message") or {})
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    chunks.append(text)
            elif isinstance(item, str):
                chunks.append(item)
        return "\n".join(chunks).strip()
    for key in ("reasoning_content", "output_text", "text"):
        value = message.get(key)
        if isinstance(value, str):
            return value.strip()
    return ""


def _response_format_may_be_unsupported(response: httpx.Response) -> bool:
    try:
        body = response.text.lower()
    except Exception:
        return False
    return response.status_code in {400, 422} and "response_format" in body


def _responses_output_text(data: dict) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"].strip()
    chunks: list[str] = []
    for item in data.get("output") or []:
        for content in item.get("content") or []:
            text = content.get("text")
            if isinstance(text, str) and content.get("type") in {None, "output_text", "text"}:
                chunks.append(text)
    return "\n".join(chunks).strip()
