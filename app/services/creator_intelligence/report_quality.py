from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.creator_intelligence.models import CreatorCloneStrategy, validate_creator_clone_schema


REPORT_QUALITY_FIELDS = tuple(CreatorCloneStrategy.empty_schema().keys())
_LIST_FIELDS = {"content_strategy", "hooks", "templates", "anti_patterns", "idea_bank", "validation_rules"}


@dataclass(frozen=True)
class ReportQualityValidation:
    ok: bool
    score: int
    missing_fields: tuple[str, ...] = ()
    weak_fields: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    evidence_warnings: tuple[str, ...] = ()
    field_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "score": self.score,
            "missing_fields": list(self.missing_fields),
            "weak_fields": list(self.weak_fields),
            "warnings": list(self.warnings),
            "evidence_warnings": list(self.evidence_warnings),
            "field_counts": dict(self.field_counts),
        }


def _meaningful_count(value: Any) -> int:
    if isinstance(value, str):
        return 1 if value.strip() else 0
    if isinstance(value, list):
        return sum(1 for item in value if _meaningful_count(item))
    if isinstance(value, dict):
        return 1 if any(_meaningful_count(item) for item in value.values()) else 0
    return 1 if value not in (None, "", [], {}) else 0


def _evidence_warnings(evidence_summary: dict[str, Any] | None) -> tuple[str, ...]:
    evidence = evidence_summary if isinstance(evidence_summary, dict) else {}
    if not evidence:
        return ()
    selected_count = int(evidence.get("selected_count") or 0)
    evidence_ready_count = int(evidence.get("evidence_ready_count") or 0)
    with_keyframes = int(evidence.get("with_keyframes") or 0)
    with_asr = int(evidence.get("with_asr") or 0)
    with_ocr = int(evidence.get("with_ocr") or 0)
    warnings: list[str] = []
    if selected_count and evidence_ready_count < selected_count:
        warnings.append(f"证据不足：{selected_count - evidence_ready_count}/{selected_count} 条样本尚未达到可蒸馏证据。")
    if selected_count and with_keyframes == 0:
        warnings.append("证据不足：当前样本没有关键帧，视觉规律置信度会降低。")
    if selected_count >= 3 and with_asr == 0 and with_ocr == 0:
        warnings.append("证据不足：当前缺少 ASR/OCR 文本，表达结构和字幕规律置信度会降低。")
    return tuple(warnings)


def validate_creator_report_quality(
    strategy_output: dict[str, Any] | None,
    *,
    evidence_summary: dict[str, Any] | None = None,
) -> ReportQualityValidation:
    """Lightweight schema and evidence readiness validator for creator reports."""

    normalized = validate_creator_clone_schema(strategy_output if isinstance(strategy_output, dict) else {})
    missing: list[str] = []
    weak: list[str] = []
    field_counts: dict[str, int] = {}
    for field_name in REPORT_QUALITY_FIELDS:
        count = _meaningful_count(normalized.get(field_name))
        field_counts[field_name] = count
        if count <= 0:
            missing.append(field_name)
        elif field_name in _LIST_FIELDS and count < 2:
            weak.append(field_name)

    warnings: list[str] = []
    if missing:
        warnings.append("报告结构不完整：" + "、".join(missing))
    if weak:
        warnings.append("报告字段偏弱：" + "、".join(weak))
    evidence = _evidence_warnings(evidence_summary)
    score = max(0, 100 - len(missing) * 12 - len(weak) * 5 - len(evidence) * 8)
    return ReportQualityValidation(
        ok=not missing and score >= 70,
        score=score,
        missing_fields=tuple(missing),
        weak_fields=tuple(weak),
        warnings=tuple(warnings),
        evidence_warnings=evidence,
        field_counts=field_counts,
    )
