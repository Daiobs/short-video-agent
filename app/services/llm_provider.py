from __future__ import annotations

import base64
import json
import logging
import re
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageOps

from app.config import settings
from app.errors import AppError, ErrorCode
from app.services.llm_budget import DistillDeadline
from app.services.runtime_settings import effective_llm_settings


JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
logger = logging.getLogger("uvicorn.error")


class BaseLLMProvider:
    _diagnostics: dict[str, Any] = {}

    def analyze(self, prompt: str, image_paths: list[Path]) -> dict:
        raise NotImplementedError

    def public_diagnostics(self) -> dict[str, Any]:
        return _safe_llm_diagnostics(getattr(self, "_diagnostics", {}))


class OpenAICompatibleProvider(BaseLLMProvider):
    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        deadline: DistillDeadline | None = None,
    ) -> None:
        effective = effective_llm_settings()
        self.api_base = (api_base or effective["api_base"]).rstrip("/")
        self.api_key = api_key if api_key is not None else effective["api_key"]
        self.model = model or effective["model"]
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else effective["timeout_seconds"]
        self.temperature = temperature if temperature is not None else effective["temperature"]
        self.max_output_tokens = (
            max_output_tokens if max_output_tokens is not None else effective["max_output_tokens"]
        )
        self.deadline = deadline
        self._diagnostics = _new_llm_diagnostics("openai_compatible")

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
        if self.max_output_tokens:
            payload["max_tokens"] = self.max_output_tokens
        endpoint = f"{self.api_base}/chat/completions"
        started_at = time.monotonic()
        image_bytes = _image_bytes(image_paths)
        self._diagnostics = _new_llm_diagnostics("openai_compatible")
        logger.info(
            "llm_request_start provider=openai_compatible model=%s endpoint=%s prompt_chars=%s image_count=%s image_bytes=%s timeout=%s",
            self.model,
            endpoint,
            len(prompt),
            len([path for path in image_paths if path.is_file()]),
            image_bytes,
            self.timeout_seconds,
        )
        try:
            first_timeout = _provider_request_timeout(
                self.timeout_seconds,
                self.deadline,
                phase="chat_completions",
                attempt_index=1,
                provider="openai_compatible",
            )
            self._diagnostics.update({"http_attempt_index": 1, "http_attempt_count": 1})
            with httpx.Client(timeout=first_timeout, trust_env=False) as client:
                response = client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            if _response_format_may_be_unsupported(response):
                fallback_timeout = _provider_request_timeout(
                    self.timeout_seconds,
                    self.deadline,
                    minimum_seconds=5.0,
                    phase="response_format_fallback",
                    attempt_index=2,
                    provider="openai_compatible",
                )
                payload.pop("response_format", None)
                self._diagnostics.update(
                    {
                        "http_attempt_index": 2,
                        "http_attempt_count": 2,
                        "response_format_fallback_used": True,
                    }
                )
                with httpx.Client(timeout=fallback_timeout, trust_env=False) as fallback_client:
                    response = fallback_client.post(
                        endpoint,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
            if response.status_code >= 400:
                logger.warning(
                    "llm_request_failed provider=openai_compatible model=%s status=%s duration_ms=%s prompt_chars=%s image_count=%s image_bytes=%s",
                    self.model,
                    response.status_code,
                    _duration_ms(started_at),
                    len(prompt),
                    len([path for path in image_paths if path.is_file()]),
                    image_bytes,
                )
                raise _classify_llm_http_error(
                    response,
                    provider="openai_compatible",
                    phase="response_format_fallback" if self._diagnostics["response_format_fallback_used"] else "chat_completions",
                    attempt_index=int(self._diagnostics["http_attempt_index"]),
                    diagnostics=self._diagnostics,
                )
            data = _response_json(response, "openai_compatible", diagnostics=self._diagnostics)
            try:
                result = parse_json_text(_chat_completion_output_text(data))
            except AppError as error:
                raise AppError(
                    ErrorCode.LLM_RESPONSE_INVALID,
                    details={
                        **self.public_diagnostics(),
                        "retryable": True,
                        "phase": "parse_response",
                        "attempt_index": int(self._diagnostics["http_attempt_index"]),
                    },
                ) from error
            logger.info(
                "llm_request_success provider=openai_compatible model=%s duration_ms=%s prompt_chars=%s image_count=%s image_bytes=%s",
                self.model,
                _duration_ms(started_at),
                len(prompt),
                len([path for path in image_paths if path.is_file()]),
                image_bytes,
            )
            return result
        except AppError:
            raise
        except httpx.TimeoutException as error:
            logger.warning(
                "llm_request_timeout provider=openai_compatible model=%s duration_ms=%s prompt_chars=%s image_count=%s image_bytes=%s timeout=%s",
                self.model,
                _duration_ms(started_at),
                len(prompt),
                len([path for path in image_paths if path.is_file()]),
                image_bytes,
                self.timeout_seconds,
            )
            raise AppError(
                ErrorCode.LLM_GATEWAY_TIMEOUT,
                details={
                    **self.public_diagnostics(),
                    "retryable": True,
                    "phase": "response_format_fallback"
                    if self._diagnostics.get("response_format_fallback_used")
                    else "chat_completions",
                    "attempt_index": int(self._diagnostics.get("http_attempt_index") or 1),
                },
            ) from error
        except httpx.RequestError as error:
            logger.warning(
                "llm_request_transport_error provider=openai_compatible model=%s error_type=%s duration_ms=%s",
                self.model,
                type(error).__name__,
                _duration_ms(started_at),
            )
            raise AppError(
                ErrorCode.LLM_UPSTREAM_UNAVAILABLE,
                details={
                    **self.public_diagnostics(),
                    "retryable": True,
                    "phase": "transport",
                    "attempt_index": int(self._diagnostics.get("http_attempt_index") or 1),
                },
            ) from error
        except Exception as error:
            logger.warning(
                "llm_request_error provider=openai_compatible model=%s error_type=%s duration_ms=%s prompt_chars=%s image_count=%s image_bytes=%s",
                self.model,
                type(error).__name__,
                _duration_ms(started_at),
                len(prompt),
                len([path for path in image_paths if path.is_file()]),
                image_bytes,
            )
            raise AppError(
                ErrorCode.LLM_REQUEST_FAILED,
                details={
                    **self.public_diagnostics(),
                    "retryable": False,
                    "phase": "client",
                    "attempt_index": int(self._diagnostics.get("http_attempt_index") or 1),
                },
            ) from error


class OpenAIResponsesProvider(BaseLLMProvider):
    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        deadline: DistillDeadline | None = None,
    ) -> None:
        effective = effective_llm_settings()
        self.api_base = (api_base or effective["api_base"]).rstrip("/")
        self.api_key = api_key if api_key is not None else effective["api_key"]
        self.model = model or effective["model"]
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else effective["timeout_seconds"]
        self.temperature = temperature if temperature is not None else effective["temperature"]
        self.max_output_tokens = (
            max_output_tokens if max_output_tokens is not None else effective["max_output_tokens"]
        )
        self.deadline = deadline
        self._diagnostics = _new_llm_diagnostics("openai_responses")

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
        if self.max_output_tokens:
            payload["max_output_tokens"] = self.max_output_tokens
        endpoint = f"{self.api_base}/responses"
        started_at = time.monotonic()
        image_bytes = _image_bytes(image_paths)
        self._diagnostics = _new_llm_diagnostics("openai_responses")
        logger.info(
            "llm_request_start provider=openai_responses model=%s endpoint=%s prompt_chars=%s image_count=%s image_bytes=%s timeout=%s",
            self.model,
            endpoint,
            len(prompt),
            len([path for path in image_paths if path.is_file()]),
            image_bytes,
            self.timeout_seconds,
        )
        try:
            request_timeout = _provider_request_timeout(
                self.timeout_seconds,
                self.deadline,
                phase="responses",
                attempt_index=1,
                provider="openai_responses",
            )
            self._diagnostics.update({"http_attempt_index": 1, "http_attempt_count": 1})
            with httpx.Client(timeout=request_timeout, trust_env=False) as client:
                response = client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            if response.status_code >= 400:
                logger.warning(
                    "llm_request_failed provider=openai_responses model=%s status=%s duration_ms=%s",
                    self.model,
                    response.status_code,
                    _duration_ms(started_at),
                )
                raise _classify_llm_http_error(
                    response,
                    provider="openai_responses",
                    phase="responses",
                    attempt_index=1,
                    diagnostics=self._diagnostics,
                )
            data = _response_json(response, "openai_responses", diagnostics=self._diagnostics)
            output_text = _responses_output_text(data)
            try:
                result = parse_json_text(output_text)
            except AppError as error:
                raise AppError(
                    ErrorCode.LLM_RESPONSE_INVALID,
                    details={
                        **self.public_diagnostics(),
                        "retryable": True,
                        "phase": "parse_response",
                        "attempt_index": 1,
                    },
                ) from error
            logger.info(
                "llm_request_success provider=openai_responses model=%s duration_ms=%s prompt_chars=%s image_count=%s image_bytes=%s",
                self.model,
                _duration_ms(started_at),
                len(prompt),
                len([path for path in image_paths if path.is_file()]),
                image_bytes,
            )
            return result
        except AppError:
            raise
        except httpx.TimeoutException as error:
            logger.warning(
                "llm_request_timeout provider=openai_responses model=%s duration_ms=%s timeout=%s",
                self.model,
                _duration_ms(started_at),
                self.timeout_seconds,
            )
            raise AppError(
                ErrorCode.LLM_GATEWAY_TIMEOUT,
                details={
                    **self.public_diagnostics(),
                    "retryable": True,
                    "phase": "responses",
                    "attempt_index": 1,
                },
            ) from error
        except httpx.RequestError as error:
            logger.warning(
                "llm_request_transport_error provider=openai_responses model=%s error_type=%s duration_ms=%s",
                self.model,
                type(error).__name__,
                _duration_ms(started_at),
            )
            raise AppError(
                ErrorCode.LLM_UPSTREAM_UNAVAILABLE,
                details={
                    **self.public_diagnostics(),
                    "retryable": True,
                    "phase": "transport",
                    "attempt_index": 1,
                },
            ) from error
        except Exception as error:
            logger.warning(
                "llm_request_error provider=openai_responses model=%s error_type=%s duration_ms=%s",
                self.model,
                type(error).__name__,
                _duration_ms(started_at),
            )
            raise AppError(
                ErrorCode.LLM_REQUEST_FAILED,
                details={
                    **self.public_diagnostics(),
                    "retryable": False,
                    "phase": "client",
                    "attempt_index": 1,
                },
            ) from error


class AnthropicCompatibleProvider(BaseLLMProvider):
    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        deadline: DistillDeadline | None = None,
    ) -> None:
        effective = effective_llm_settings()
        self.api_base = (api_base or effective["api_base"]).rstrip("/")
        self.api_key = api_key if api_key is not None else effective["api_key"]
        self.model = model or effective["model"]
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else effective["timeout_seconds"]
        self.temperature = temperature if temperature is not None else effective["temperature"]
        self.max_output_tokens = (
            max_output_tokens if max_output_tokens is not None else effective["max_output_tokens"]
        )
        self.deadline = deadline
        self._diagnostics = _new_llm_diagnostics("anthropic_compatible")

    def analyze(self, prompt: str, image_paths: list[Path]) -> dict:
        if not self.api_key or not self.model:
            raise AppError(ErrorCode.LLM_NOT_CONFIGURED)

        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for path in image_paths:
            if path.is_file():
                content.append(_anthropic_image_payload(path))

        payload = {
            "model": self.model,
            "max_tokens": self.max_output_tokens or 1200,
            "temperature": self.temperature,
            "system": "你是短视频内容策略分析师。只输出合法 JSON，不要输出 Markdown。",
            "messages": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
        }
        self._diagnostics = _new_llm_diagnostics("anthropic_compatible")
        try:
            request_timeout = _provider_request_timeout(
                self.timeout_seconds,
                self.deadline,
                phase="messages",
                attempt_index=1,
                provider="anthropic_compatible",
            )
            self._diagnostics.update({"http_attempt_index": 1, "http_attempt_count": 1})
            with httpx.Client(timeout=request_timeout, trust_env=False) as client:
                response = client.post(
                    _anthropic_messages_url(self.api_base),
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            if response.status_code >= 400:
                raise _classify_llm_http_error(
                    response,
                    provider="anthropic_compatible",
                    phase="messages",
                    attempt_index=1,
                    diagnostics=self._diagnostics,
                )
            data = _response_json(response, "anthropic_compatible", diagnostics=self._diagnostics)
            try:
                return parse_json_text(_anthropic_output_text(data))
            except AppError as error:
                raise AppError(
                    ErrorCode.LLM_RESPONSE_INVALID,
                    details={
                        **self.public_diagnostics(),
                        "retryable": True,
                        "phase": "parse_response",
                        "attempt_index": 1,
                    },
                ) from error
        except AppError:
            raise
        except httpx.TimeoutException as error:
            raise AppError(
                ErrorCode.LLM_GATEWAY_TIMEOUT,
                details={
                    **self.public_diagnostics(),
                    "retryable": True,
                    "phase": "messages",
                    "attempt_index": 1,
                },
            ) from error
        except httpx.RequestError as error:
            raise AppError(
                ErrorCode.LLM_UPSTREAM_UNAVAILABLE,
                details={
                    **self.public_diagnostics(),
                    "retryable": True,
                    "phase": "transport",
                    "attempt_index": 1,
                },
            ) from error
        except Exception as error:
            raise AppError(
                ErrorCode.LLM_REQUEST_FAILED,
                details={
                    **self.public_diagnostics(),
                    "retryable": False,
                    "phase": "client",
                    "attempt_index": 1,
                },
            ) from error


def get_llm_provider(
    *,
    timeout_seconds: float | None = None,
    max_output_tokens: int | None = None,
    deadline: DistillDeadline | None = None,
) -> BaseLLMProvider:
    effective = effective_llm_settings()
    provider = effective["provider"]
    provider_timeout = timeout_seconds if timeout_seconds is not None else effective["timeout_seconds"]
    provider_max_tokens = (
        max_output_tokens if max_output_tokens is not None else effective["max_output_tokens"]
    )
    common = {
        "timeout_seconds": provider_timeout,
        "max_output_tokens": provider_max_tokens,
        "deadline": deadline,
    }
    if provider in {"", "disabled", "none", "off"}:
        raise AppError(ErrorCode.LLM_NOT_CONFIGURED)
    if provider in {"openai", "openai_compatible", "compatible"}:
        return OpenAICompatibleProvider(**common)
    if provider in {"openai_responses", "responses"}:
        return OpenAIResponsesProvider(**common)
    if provider in {"anthropic", "anthropic_compatible", "claude"}:
        return AnthropicCompatibleProvider(**common)
    raise AppError(ErrorCode.LLM_NOT_CONFIGURED, f"不支持的 LLM_PROVIDER：{provider}")


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
    mime, image_bytes = _optimized_image_payload(path)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _anthropic_image_payload(path: Path) -> dict:
    media_type, image_bytes = _optimized_image_payload(path)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": encoded,
        },
    }


def _optimized_image_payload(path: Path) -> tuple[str, bytes]:
    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            effective = effective_llm_settings()
            max_width = max(320, int(effective["image_max_width"] or 1280))
            if image.width > max_width:
                ratio = max_width / image.width
                image = image.resize((max_width, max(1, int(image.height * ratio))), Image.Resampling.LANCZOS)
            output = BytesIO()
            quality = min(95, max(40, int(effective["image_jpeg_quality"] or 72)))
            image.save(output, format="JPEG", quality=quality, optimize=True)
            return "image/jpeg", output.getvalue()
    except Exception:
        suffix = path.suffix.lower()
        mime = "image/png" if suffix == ".png" else "image/jpeg"
        return mime, path.read_bytes()


def _anthropic_messages_url(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/messages"
    return f"{base}/v1/messages"


def _duration_ms(started_at: float) -> int:
    return int((time.monotonic() - started_at) * 1000)


def _image_bytes(image_paths: list[Path]) -> int:
    total = 0
    for path in image_paths:
        if path.is_file():
            total += path.stat().st_size
    return total


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
    unsupported_markers = (
        "not support",
        "unsupported",
        "unknown parameter",
        "unrecognized",
        "not permitted",
        "extra inputs",
        "不支持",
    )
    return (
        response.status_code in {400, 422}
        and "response_format" in body
        and any(marker in body for marker in unsupported_markers)
    )


def _response_json(response: httpx.Response, provider: str, *, diagnostics: dict | None = None) -> dict:
    try:
        data = response.json()
    except ValueError as error:
        raise AppError(
            ErrorCode.LLM_RESPONSE_INVALID,
            details={
                **_safe_llm_diagnostics(diagnostics or {}),
                "provider": provider,
                "retryable": True,
                "phase": "parse_response",
                "attempt_index": int((diagnostics or {}).get("http_attempt_index") or 1),
            },
        ) from error
    if not isinstance(data, dict):
        raise AppError(
            ErrorCode.LLM_RESPONSE_INVALID,
            details={
                **_safe_llm_diagnostics(diagnostics or {}),
                "provider": provider,
                "retryable": True,
                "phase": "parse_response",
                "attempt_index": int((diagnostics or {}).get("http_attempt_index") or 1),
            },
        )
    return data


def _new_llm_diagnostics(provider: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "http_attempt_index": 0,
        "http_attempt_count": 0,
        "response_format_fallback_used": False,
    }


def _safe_llm_diagnostics(value: dict[str, Any] | None) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        "provider": str(source.get("provider") or "")[:80],
        "http_attempt_index": max(0, int(source.get("http_attempt_index") or 0)),
        "http_attempt_count": max(0, int(source.get("http_attempt_count") or 0)),
        "response_format_fallback_used": bool(source.get("response_format_fallback_used")),
    }


def _provider_request_timeout(
    configured_timeout_seconds: float,
    deadline: DistillDeadline | None,
    *,
    minimum_seconds: float = 0.1,
    phase: str,
    attempt_index: int,
    provider: str,
) -> float:
    configured = max(0.1, float(configured_timeout_seconds))
    if deadline is None:
        return configured
    return deadline.request_timeout(
        configured,
        minimum_seconds=minimum_seconds,
        phase=phase,
        attempt_index=attempt_index,
        provider=provider,
    )


def _classify_llm_http_error(
    response: httpx.Response,
    *,
    provider: str,
    phase: str,
    attempt_index: int,
    diagnostics: dict | None = None,
) -> AppError:
    status_code = int(response.status_code)
    try:
        body = str(response.text or "").lower()
    except Exception:
        body = ""
    quota_markers = (
        "insufficient_quota",
        "quota exceeded",
        "billing",
        "credit balance",
        "余额不足",
        "额度不足",
        "配额不足",
    )
    if any(marker in body for marker in quota_markers):
        code = ErrorCode.LLM_QUOTA_EXCEEDED
        retryable = False
    elif status_code in {401, 403}:
        code = ErrorCode.LLM_AUTH_FAILED
        retryable = False
    elif status_code == 429:
        code = ErrorCode.LLM_RATE_LIMITED
        retryable = False
    elif status_code in {408, 504}:
        code = ErrorCode.LLM_GATEWAY_TIMEOUT
        retryable = True
    elif status_code in {502, 503} or status_code >= 500:
        code = ErrorCode.LLM_UPSTREAM_UNAVAILABLE
        retryable = True
    else:
        code = ErrorCode.LLM_REQUEST_FAILED
        retryable = False
    return AppError(
        code,
        details={
            **_safe_llm_diagnostics(diagnostics or {}),
            "status_code": status_code,
            "provider": provider,
            "retryable": retryable,
            "phase": phase,
            "attempt_index": attempt_index,
        },
    )


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


def _anthropic_output_text(data: dict) -> str:
    chunks: list[str] = []
    for item in data.get("content") or []:
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str):
                chunks.append(text)
        elif isinstance(item, str):
            chunks.append(item)
    return "\n".join(chunks).strip()
