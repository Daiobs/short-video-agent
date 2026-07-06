from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.creator_intelligence.models import CreatorCloneStrategy, validate_creator_clone_schema


REPORT_QUALITY_FIELDS = tuple(CreatorCloneStrategy.empty_schema().keys())
_LIST_FIELDS = {"content_strategy", "hooks", "templates", "anti_patterns", "idea_bank", "validation_rules"}
_ACTION_VERBS = (
    "拍",
    "写",
    "剪",
    "测",
    "验证",
    "复核",
    "选择",
    "保留",
    "替换",
    "增加",
    "减少",
    "使用",
    "展示",
    "放大",
    "强化",
    "引导",
    "发布",
    "对比",
    "设计",
    "开头",
    "封面",
    "标题",
    "脚本",
    "镜头",
    "动作",
)
_LANDING_KEYWORDS = {
    "shooting": ("拍", "镜头", "画面", "动作", "构图", "光线", "妆造", "服装", "场景"),
    "script": ("脚本", "文案", "字幕", "口播", "段落", "金句", "台词"),
    "title": ("标题", "话题", "标签", "点击理由"),
    "cover": ("封面", "首帧", "第一眼", "视觉", "人物", "姿态"),
}
_EVIDENCE_KEYS = {
    "sample_id",
    "title",
    "metric",
    "metric_value",
    "evidence_level",
    "understanding_level",
    "case_id",
    "aweme_id",
}


@dataclass(frozen=True)
class ReportQualityValidation:
    ok: bool
    score: int
    missing_fields: tuple[str, ...] = ()
    weak_fields: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    evidence_warnings: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    field_counts: dict[str, int] = field(default_factory=dict)
    checks: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "score": self.score,
            "quality_score": self.score,
            "missing_fields": list(self.missing_fields),
            "weak_fields": list(self.weak_fields),
            "warnings": list(self.warnings),
            "evidence_warnings": list(self.evidence_warnings),
            "missing_evidence": list(self.missing_evidence),
            "field_counts": dict(self.field_counts),
            "checks": dict(self.checks),
        }


def _meaningful_count(value: Any) -> int:
    if isinstance(value, str):
        return 1 if value.strip() else 0
    if isinstance(value, list):
        return sum(1 for item in value if _meaningful_count(item))
    if isinstance(value, dict):
        return 1 if any(_meaningful_count(item) for item in value.values()) else 0
    return 1 if value not in (None, "", [], {}) else 0


def _flatten_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list) or isinstance(value, tuple):
        rows: list[str] = []
        for item in value:
            rows.extend(_flatten_text(item))
        return rows
    if isinstance(value, dict):
        rows = []
        for item in value.values():
            rows.extend(_flatten_text(item))
        return rows
    if value not in (None, "", [], {}):
        return [str(value)]
    return []


def _flatten_dicts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        rows = [value]
        for item in value.values():
            rows.extend(_flatten_dicts(item))
        return rows
    if isinstance(value, list) or isinstance(value, tuple):
        rows: list[dict[str, Any]] = []
        for item in value:
            rows.extend(_flatten_dicts(item))
        return rows
    return []


def _all_text(strategy_output: dict[str, Any], report_context: dict[str, Any] | None) -> str:
    rows = _flatten_text(strategy_output)
    if isinstance(report_context, dict):
        for key in ("next_actions", "candidate_ideas", "transferable_formulas", "creator_report_view_model"):
            rows.extend(_flatten_text(report_context.get(key)))
    return "\n".join(rows)


def _has_actionable_language(text: str) -> bool:
    return any(verb in text for verb in _ACTION_VERBS)


def _has_sample_evidence(strategy_output: dict[str, Any], report_context: dict[str, Any] | None) -> bool:
    rows = _flatten_dicts(strategy_output)
    if isinstance(report_context, dict):
        rows.extend(_flatten_dicts(report_context.get("creator_report_view_model")))
        rows.extend(_flatten_dicts(report_context.get("performance_segments")))
    identity_keys = ("sample_id", "case_id", "aweme_id")
    evidence_keys = ("metric", "metric_value", "evidence_level", "understanding_level")
    return any(
        any(row.get(key) not in (None, "", [], {}) for key in identity_keys)
        or (
            row.get("title") not in (None, "", [], {})
            and any(row.get(key) not in (None, "", [], {}) for key in evidence_keys)
        )
        for row in rows
    )


def _has_executable_ideas(strategy_output: dict[str, Any], report_context: dict[str, Any] | None) -> bool:
    idea_rows = []
    if isinstance(strategy_output, dict):
        idea_rows.extend(_flatten_dicts(strategy_output.get("idea_bank")))
        idea_rows.extend(_flatten_text(strategy_output.get("idea_bank")))
    if isinstance(report_context, dict):
        idea_rows.extend(_flatten_dicts(report_context.get("candidate_ideas")))
        idea_rows.extend(_flatten_text(report_context.get("candidate_ideas")))
        view_model = report_context.get("creator_report_view_model")
        if isinstance(view_model, dict):
            idea_rows.extend(_flatten_text((view_model.get("sections") or {}).get("next_ideas")))
    for item in idea_rows:
        if isinstance(item, dict):
            text = " ".join(_flatten_text(item))
            if (item.get("title") or item.get("idea")) and _has_actionable_language(text):
                return True
        elif _has_actionable_language(str(item)):
            return True
    return False


def _landing_dimensions(text: str) -> dict[str, bool]:
    return {
        key: any(keyword in text for keyword in keywords)
        for key, keywords in _LANDING_KEYWORDS.items()
    }


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
    report_context: dict[str, Any] | None = None,
) -> ReportQualityValidation:
    """Validate report structure, evidence binding, and execution value."""

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
    text = _all_text(normalized, report_context)
    has_actions = _has_actionable_language(text)
    has_sample_evidence = _has_sample_evidence(normalized, report_context)
    has_executable_ideas = _has_executable_ideas(normalized, report_context)
    dimensions = _landing_dimensions(text)
    has_landing_advice = any(dimensions.values())
    missing_evidence: list[str] = []
    if not has_sample_evidence:
        missing_evidence.append("核心策略缺少 sample_id/title/metric/evidence_level 等样本证据绑定。")
    if not has_executable_ideas:
        missing_evidence.append("缺少可直接执行的下一条选题。")
    if not has_actions:
        missing_evidence.append("报告缺少明确动作词，容易停留在抽象描述。")
    missing_dimensions = [name for name, ok in dimensions.items() if not ok]
    if missing_dimensions:
        labels = {"shooting": "拍摄", "script": "脚本/文案", "title": "标题/话题", "cover": "封面/首帧"}
        missing_evidence.append("缺少落地建议维度：" + "、".join(labels[name] for name in missing_dimensions))
    if missing_evidence:
        warnings.append("报告可执行性不足：" + "；".join(missing_evidence[:3]))
    score = max(0, 100 - len(missing) * 12 - len(weak) * 5 - len(evidence) * 8 - len(missing_evidence) * 7)
    checks = {
        "has_action_verbs": has_actions,
        "has_sample_evidence": has_sample_evidence,
        "has_executable_ideas": has_executable_ideas,
        "has_landing_advice": has_landing_advice,
        **{f"has_{key}_advice": value for key, value in dimensions.items()},
    }
    return ReportQualityValidation(
        ok=not missing and score >= 70 and not missing_evidence,
        score=score,
        missing_fields=tuple(missing),
        weak_fields=tuple(weak),
        warnings=tuple(warnings),
        evidence_warnings=evidence,
        missing_evidence=tuple(missing_evidence),
        field_counts=field_counts,
        checks=checks,
    )
