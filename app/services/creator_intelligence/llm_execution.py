from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.errors import AppError, ErrorCode, is_retryable_llm_error
from app.services.llm_budget import DistillDeadline
from app.services.creator_intelligence.models import validate_creator_clone_schema


SCHEMA_REPAIR_INSTRUCTION = """

上一次输出没有严格符合 CreatorCloneSchema。请只返回 JSON object，且必须包含：
{
  "creator_clone_strategy": {
    "positioning": "",
    "content_strategy": [],
    "hooks": [],
    "templates": [],
    "anti_patterns": [],
    "idea_bank": [],
    "validation_rules": []
  }
}
不要输出 Markdown，不要解释。
"""


@dataclass
class LLMExecutionResult:
    result: dict[str, Any]
    strategy: dict[str, Any]
    attempts: int
    repaired: bool = False
    errors: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.result)
        payload["creator_clone_strategy"] = dict(self.strategy)
        payload["_llm_execution"] = {
            "attempts": self.attempts,
            "repaired": self.repaired,
            "errors": list(self.errors),
        }
        return payload


@dataclass
class StructuredLLMExecutionResult:
    payload: dict[str, Any]
    attempts: int
    repaired: bool = False
    errors: list[dict[str, str]] = field(default_factory=list)


class LLMExecutionEngine:
    """System-level LLM executor for deterministic CreatorCloneSchema output."""

    def __init__(
        self,
        provider,
        *,
        max_retries: int = 3,
        deadline: DistillDeadline | None = None,
    ) -> None:
        self.provider = provider
        self.max_retries = max(1, min(int(max_retries or 3), 3))
        self.deadline = deadline

    def execute_creator_clone(self, prompt: str, image_paths: list[Path] | None = None) -> LLMExecutionResult:
        errors: list[dict[str, str]] = []
        repaired = False
        current_prompt = prompt
        for attempt in range(1, self.max_retries + 1):
            if self.deadline is not None:
                self.deadline.require_remaining(
                    0.1,
                    phase="execution",
                    attempt_index=attempt,
                    provider=str(getattr(self.provider, "public_diagnostics", lambda: {})().get("provider") or ""),
                )
            try:
                raw = self.provider.analyze(current_prompt, list(image_paths or []))
                payload = self._repair_raw_payload(raw)
                strategy = self._extract_strategy(payload)
                if not _strategy_has_signal(strategy):
                    raise AppError(ErrorCode.LLM_RESPONSE_INVALID, "CreatorCloneSchema 内容为空。")
                payload["creator_clone_strategy"] = strategy
                return LLMExecutionResult(
                    result=payload,
                    strategy=strategy,
                    attempts=attempt,
                    repaired=repaired or payload is not raw,
                    errors=errors,
                )
            except AppError as error:
                errors.append({"error_code": error.code, "message": error.message})
                if not is_retryable_llm_error(error.code) or attempt >= self.max_retries:
                    raise
                if self.deadline is not None:
                    self.deadline.require_remaining(
                        5.0,
                        phase="execution_retry",
                        attempt_index=attempt + 1,
                    )
                current_prompt = prompt + SCHEMA_REPAIR_INSTRUCTION
                repaired = True
        raise AppError(ErrorCode.LLM_RESPONSE_INVALID)

    def execute_structured(
        self,
        prompt: str,
        *,
        validator: Callable[[dict[str, Any]], dict[str, Any]],
        repair_instruction: str,
        retry_min_remaining_seconds: float,
        image_paths: list[Path] | None = None,
    ) -> StructuredLLMExecutionResult:
        """Run one bounded structured-generation path through the shared provider.

        The first provider call is the main logical request. The existing LLM
        error classification permits at most one compact schema/upstream retry
        when ``max_retries=2``; authentication, quota, and rate-limit failures
        remain terminal.
        """

        errors: list[dict[str, str]] = []
        current_prompt = prompt
        for attempt in range(1, self.max_retries + 1):
            if self.deadline is not None:
                self.deadline.require_remaining(
                    0.1,
                    phase="structured_execution",
                    attempt_index=attempt,
                    provider=str(getattr(self.provider, "public_diagnostics", lambda: {})().get("provider") or ""),
                )
            try:
                raw = self.provider.analyze(current_prompt, list(image_paths or []))
                payload = self._repair_raw_payload(raw)
                try:
                    normalized = validator(payload)
                except ValueError as error:
                    raise AppError(ErrorCode.LLM_RESPONSE_INVALID, str(error)[:240]) from error
                if not isinstance(normalized, dict) or not normalized:
                    raise AppError(ErrorCode.LLM_RESPONSE_INVALID, "结构化输出内容为空。")
                return StructuredLLMExecutionResult(
                    payload=normalized,
                    attempts=attempt,
                    repaired=attempt > 1 or not isinstance(raw, dict),
                    errors=errors,
                )
            except AppError as error:
                errors.append({"error_code": error.code, "message": error.message})
                if not is_retryable_llm_error(error.code) or attempt >= self.max_retries:
                    raise
                if self.deadline is not None:
                    self.deadline.require_remaining(
                        retry_min_remaining_seconds,
                        phase="structured_execution_retry",
                        attempt_index=attempt + 1,
                    )
                current_prompt = prompt + repair_instruction
        raise AppError(ErrorCode.LLM_RESPONSE_INVALID)

    def _extract_strategy(self, payload: dict[str, Any]) -> dict[str, Any]:
        explicit = payload.get("creator_clone_strategy") if isinstance(payload.get("creator_clone_strategy"), dict) else None
        if explicit is not None:
            return validate_creator_clone_schema(explicit)
        root_payload = {key: payload.get(key) for key in validate_creator_clone_schema({}) if key in payload}
        if root_payload:
            return validate_creator_clone_schema(root_payload)
        legacy_payload = _strategy_from_legacy_payload(payload)
        if legacy_payload:
            return validate_creator_clone_schema(legacy_payload)
        return validate_creator_clone_schema({})

    def _repair_raw_payload(self, raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return dict(raw)
        if isinstance(raw, str):
            parsed = _parse_json_object(raw)
            if parsed:
                return parsed
        raise AppError(ErrorCode.LLM_RESPONSE_INVALID, "大模型没有返回 JSON object。")


def _parse_json_object(text: str) -> dict[str, Any]:
    source = str(text or "").strip()
    if not source:
        return {}
    candidates = [source]
    first = source.find("{")
    last = source.rfind("}")
    if first >= 0 and last > first:
        candidates.append(source[first : last + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _strategy_has_signal(strategy: dict[str, Any]) -> bool:
    if str(strategy.get("positioning") or "").strip():
        return True
    for key in ("content_strategy", "hooks", "templates", "anti_patterns", "idea_bank", "validation_rules"):
        value = strategy.get(key)
        if isinstance(value, list) and value:
            return True
    return False


def _strategy_from_legacy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    creator_positioning = payload.get("creator_positioning") if isinstance(payload.get("creator_positioning"), dict) else {}
    expression = payload.get("expression_patterns") if isinstance(payload.get("expression_patterns"), dict) else {}
    thinking = payload.get("thinking_patterns") if isinstance(payload.get("thinking_patterns"), dict) else {}
    spec = payload.get("creator_clone_spec") if isinstance(payload.get("creator_clone_spec"), dict) else {}
    positioning = "；".join(
        item
        for item in (
            creator_positioning.get("what_the_creator_sells"),
            creator_positioning.get("audience_promise"),
            creator_positioning.get("hidden_genre"),
        )
        if str(item or "").strip()
    )
    result = {
        "positioning": positioning,
        "content_strategy": _unique_text_values(
            [
                payload.get("topic_buckets"),
                payload.get("transferable_formulas"),
                spec.get("topic_selection_rules"),
                spec.get("structure_rules"),
                spec.get("expression_rules"),
                spec.get("visual_rules"),
                spec.get("taste"),
            ],
            limit=12,
        ),
        "hooks": _unique_text_values([expression.get("opening_hooks"), thinking.get("tension_sources")], limit=10),
        "templates": _normalize_dict_items(payload.get("transferable_formulas"), fallback_key="template", limit=8),
        "anti_patterns": _unique_text_values([spec.get("anti_patterns")], limit=10),
        "idea_bank": _normalize_dict_items(payload.get("candidate_ideas"), fallback_key="idea", limit=10),
        "validation_rules": _unique_text_values([spec.get("self_check_rubric")], limit=10),
    }
    if not _strategy_has_signal(validate_creator_clone_schema(result)):
        return {}
    return result


def _unique_text_values(values, *, limit: int = 10) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    def add(item) -> None:
        if isinstance(item, dict):
            text = item.get("name") or item.get("title") or item.get("formula") or item.get("summary") or item.get("description")
            if text:
                add(text)
            return
        if isinstance(item, list) or isinstance(item, tuple):
            for child in item:
                add(child)
            return
        text = str(item or "").strip()
        if text and text not in seen:
            result.append(text[:160])
            seen.add(text)

    add(values)
    return result[:limit]


def _normalize_dict_items(value, *, fallback_key: str, limit: int) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else [value]
    normalized: list[dict[str, Any]] = []
    for item in rows:
        if isinstance(item, dict):
            cleaned = {key: val for key, val in item.items() if val not in ("", [], {}, None)}
            if cleaned:
                normalized.append(cleaned)
        else:
            text = str(item or "").strip()
            if text:
                normalized.append({fallback_key: text[:160]})
        if len(normalized) >= limit:
            break
    return normalized
