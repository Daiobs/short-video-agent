from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.errors import AppError, ErrorCode
from app.services.creator_clone import CloneSample, CloneSampleSet, creator_clone_dir, load_sample_set
from app.services.creator_intelligence.generator import validate_creator_strategy_plan
from app.services.creator_intelligence.llm_execution import LLMExecutionEngine
from app.services.llm_budget import DistillDeadline
from app.services.llm_provider import BaseLLMProvider, get_llm_provider


EXECUTION_PACK_VERSION = "1.0"
EXECUTION_PACK_FILENAME = "creator_execution_pack.json"
EXECUTION_PACK_TIMEOUT_SECONDS = 180
EXECUTION_PACK_MAX_ATTEMPTS = 2
EXECUTION_PACK_MAX_JSON_BYTES = 8 * 1024 * 1024
ALLOWED_CONFIDENCE = {"high", "medium", "low"}
ALLOWED_EVIDENCE_TYPES = {"sample", "creator_rule", "strategy_plan"}
CREATOR_RULE_FIELDS = {
    "positioning",
    "content_strategy",
    "hooks",
    "templates",
    "anti_patterns",
    "idea_bank",
    "validation_rules",
}
STRATEGY_PLAN_FIELDS = {
    "next_topics",
    "script_templates",
    "shot_templates",
    "title_cover_suggestions",
    "pre_publish_checklist",
    "low_confidence_notes",
}


@dataclass(frozen=True)
class ExecutionPackValidationContext:
    project_id: str
    topic_index: int
    topic: dict[str, Any]
    valid_samples: dict[str, str] = field(default_factory=dict)
    creator_rule_catalog: dict[str, tuple[str, ...]] = field(default_factory=dict)
    strategy_plan_catalog: dict[str, tuple[str, ...]] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    generated_at: str = ""
    confidence_cap: str = ""


@dataclass(frozen=True)
class CreatorExecutionPackV1:
    version: str
    project_id: str
    topic_index: int
    generated_at: str
    topic: dict[str, Any]
    creative_basis: dict[str, Any]
    hook: dict[str, Any]
    script: dict[str, Any]
    shot_plan: tuple[dict[str, Any], ...]
    cover: dict[str, Any]
    titles: tuple[dict[str, Any], ...]
    publish_copy: str
    hashtags: tuple[str, ...]
    editing_notes: dict[str, Any]
    production_checklist: tuple[str, ...]
    evidence_refs: tuple[dict[str, Any], ...]
    confidence: str
    warnings: tuple[str, ...]
    source: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "project_id": self.project_id,
            "topic_index": self.topic_index,
            "generated_at": self.generated_at,
            "topic": dict(self.topic),
            "creative_basis": dict(self.creative_basis),
            "hook": dict(self.hook),
            "script": dict(self.script),
            "shot_plan": [dict(item) for item in self.shot_plan],
            "cover": dict(self.cover),
            "titles": [dict(item) for item in self.titles],
            "publish_copy": self.publish_copy,
            "hashtags": list(self.hashtags),
            "editing_notes": dict(self.editing_notes),
            "production_checklist": list(self.production_checklist),
            "evidence_refs": [dict(item) for item in self.evidence_refs],
            "confidence": self.confidence,
            "warnings": list(self.warnings),
            "source": dict(self.source),
        }


def generate_creator_execution_pack(
    project_id: str,
    topic_index: int,
    *,
    provider: BaseLLMProvider | None = None,
) -> dict[str, Any]:
    project_id = _validated_project_id(project_id, ErrorCode.CREATOR_REPORT_NOT_READY)
    sample_set, report, strategy_plan = _load_generation_inputs(project_id)
    topics = strategy_plan["next_topics"]
    if not isinstance(topic_index, int) or isinstance(topic_index, bool) or topic_index < 0 or topic_index >= len(topics):
        raise AppError(ErrorCode.EXECUTION_TOPIC_INVALID)

    selected_samples = _selected_samples(sample_set)
    selected_topic = _selected_topic(topics[topic_index], report)
    generated_at = datetime.now(timezone.utc).isoformat()
    base_source, context_warnings, confidence_cap = _generation_context(
        sample_set,
        selected_samples,
        report,
        strategy_plan,
        topic_index,
    )
    context = ExecutionPackValidationContext(
        project_id=sample_set.set_id,
        topic_index=topic_index,
        topic=selected_topic,
        valid_samples={
            sample.sample_id: _safe_text(sample.title or "代表样本", 180)
            for sample in selected_samples[:8]
        },
        creator_rule_catalog=_catalog_for(report.get("creator_clone_strategy"), CREATOR_RULE_FIELDS),
        strategy_plan_catalog=_catalog_for(strategy_plan, STRATEGY_PLAN_FIELDS),
        source=base_source,
        warnings=tuple(context_warnings),
        generated_at=generated_at,
        confidence_cap=confidence_cap,
    )
    prompt = build_creator_execution_pack_prompt(
        sample_set=sample_set,
        report=report,
        strategy_plan=strategy_plan,
        selected_samples=selected_samples,
        selected_topic=selected_topic,
        topic_index=topic_index,
    )
    deadline = DistillDeadline.start(EXECUTION_PACK_TIMEOUT_SECONDS)
    llm = provider or get_llm_provider(
        timeout_seconds=EXECUTION_PACK_TIMEOUT_SECONDS,
        deadline=deadline,
    )
    result = LLMExecutionEngine(
        llm,
        max_retries=EXECUTION_PACK_MAX_ATTEMPTS,
        deadline=deadline,
    ).execute_structured(
        prompt,
        validator=lambda payload: validate_creator_execution_pack(payload, context=context),
        repair_instruction=_execution_pack_repair_instruction(selected_topic),
    )

    final_source = {
        **base_source,
        "llm_attempts": result.attempts,
        "llm_repaired": result.repaired,
    }
    final_context = replace(context, source=final_source)
    try:
        pack = validate_creator_execution_pack(result.payload, context=final_context)
    except ValueError as error:
        raise AppError(ErrorCode.LLM_RESPONSE_INVALID, str(error)[:240]) from error
    _write_json_atomic(execution_pack_path(project_id), pack)
    return pack


def load_creator_execution_pack(project_id: str) -> dict[str, Any]:
    project_id = _validated_project_id(project_id, ErrorCode.EXECUTION_PACK_NOT_READY)
    sample_set = load_sample_set(project_id)
    path = execution_pack_path(project_id)
    if not path.is_file():
        raise AppError(ErrorCode.EXECUTION_PACK_NOT_READY)
    payload = _read_json_object(path, ErrorCode.EXECUTION_PACK_NOT_READY)
    report = _read_json_optional(creator_clone_dir(project_id) / "creator_clone_result.json")
    strategy_plan = _read_json_optional(creator_clone_dir(project_id) / "creator_strategy_plan.json")
    try:
        topic_index = _integer(payload.get("topic_index"), fallback=-1)
        topics = strategy_plan.get("next_topics") if isinstance(strategy_plan.get("next_topics"), list) else []
        expected_topic = _selected_topic(topics[topic_index], report) if 0 <= topic_index < len(topics) else payload.get("topic")
        context = ExecutionPackValidationContext(
            project_id=sample_set.set_id,
            topic_index=topic_index,
            topic=expected_topic if isinstance(expected_topic, dict) else {},
            valid_samples={
                sample.sample_id: _safe_text(sample.title or "代表样本", 180)
                for sample in _selected_samples(sample_set)[:8]
            },
            creator_rule_catalog=_catalog_for(report.get("creator_clone_strategy"), CREATOR_RULE_FIELDS),
            strategy_plan_catalog=_catalog_for(strategy_plan, STRATEGY_PLAN_FIELDS),
            source=payload.get("source") if isinstance(payload.get("source"), dict) else {},
            generated_at=str(payload.get("generated_at") or ""),
        )
        return validate_creator_execution_pack(payload, context=context)
    except ValueError as error:
        raise AppError(ErrorCode.EXECUTION_PACK_NOT_READY) from error


def execution_pack_path(project_id: str) -> Path:
    return creator_clone_dir(project_id) / EXECUTION_PACK_FILENAME


def validate_creator_execution_pack(
    value: dict[str, Any] | None,
    *,
    context: ExecutionPackValidationContext | None = None,
) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    if not payload:
        raise ValueError("execution pack must be a JSON object")

    version = str(payload.get("version") or EXECUTION_PACK_VERSION)
    if version != EXECUTION_PACK_VERSION:
        raise ValueError(f"version must be {EXECUTION_PACK_VERSION}")
    project_id = _safe_id(context.project_id if context else payload.get("project_id"))
    topic_index = context.topic_index if context else _integer(payload.get("topic_index"), fallback=-1)
    if topic_index < 0:
        raise ValueError("topic_index must be a non-negative integer")
    generated_at = str(context.generated_at if context and context.generated_at else payload.get("generated_at") or "")
    _validate_timestamp(generated_at)

    raw_topic = _required_dict(payload, "topic")
    topic = _normalize_topic(raw_topic, expected=context.topic if context else None)
    creative_basis, invalid_basis_refs = _normalize_creative_basis(
        _required_dict(payload, "creative_basis"),
        context=context,
    )
    hook = _normalize_hook(_required_dict(payload, "hook"))
    script = _normalize_script(_required_dict(payload, "script"))
    shot_plan = _normalize_shot_plan(_required_list(payload, "shot_plan"))
    cover = _normalize_cover(_required_dict(payload, "cover"))
    titles = _normalize_titles(_required_list(payload, "titles"))
    publish_copy = _required_text(payload, "publish_copy", 1200)
    hashtags = _normalize_string_list(_required_list(payload, "hashtags"), minimum=5, maximum=10, limit=80)
    editing_notes = _normalize_editing_notes(_required_dict(payload, "editing_notes"))
    production_checklist = _normalize_string_list(
        _required_list(payload, "production_checklist"),
        minimum=5,
        maximum=12,
        limit=240,
    )
    evidence_refs, invalid_evidence_refs = _normalize_evidence_refs(
        _required_list(payload, "evidence_refs"),
        context=context,
    )
    confidence = _normalize_confidence(payload.get("confidence"), cap=context.confidence_cap if context else "")
    warnings = _normalize_string_list(_required_list(payload, "warnings"), minimum=0, maximum=10, limit=260)
    warnings.extend(context.warnings if context else ())
    if invalid_basis_refs:
        warnings.append(f"已移除 {invalid_basis_refs} 条无法匹配代表样本的创作依据。")
    if invalid_evidence_refs:
        warnings.append(f"已移除 {invalid_evidence_refs} 条无法验证的证据引用。")
    warnings = _unique_text(warnings, limit=10)
    source = _normalize_source(context.source if context else _required_dict(payload, "source"))

    return CreatorExecutionPackV1(
        version=version,
        project_id=project_id,
        topic_index=topic_index,
        generated_at=generated_at,
        topic=topic,
        creative_basis=creative_basis,
        hook=hook,
        script=script,
        shot_plan=tuple(shot_plan),
        cover=cover,
        titles=tuple(titles),
        publish_copy=publish_copy,
        hashtags=tuple(hashtags),
        editing_notes=editing_notes,
        production_checklist=tuple(production_checklist),
        evidence_refs=tuple(evidence_refs),
        confidence=confidence,
        warnings=tuple(warnings),
        source=source,
    ).to_dict()


def build_creator_execution_pack_prompt(
    *,
    sample_set: CloneSampleSet,
    report: dict[str, Any],
    strategy_plan: dict[str, Any],
    selected_samples: list[CloneSample],
    selected_topic: dict[str, Any],
    topic_index: int,
) -> str:
    evidence = [
        {
            "sample_id": sample.sample_id,
            "title": _safe_text(sample.title or "代表样本", 180),
            "metrics": {
                "like_count": int(sample.like_count or 0),
                "comment_count": int(sample.comment_count or 0),
                "share_count": int(sample.share_count or 0),
                "collect_count": int(sample.collect_count or 0),
            },
            "understanding_level": sample.understanding_level,
            "evidence": {
                "has_frames": bool(sample.has_frames),
                "has_asr": bool(sample.has_asr),
                "has_ocr": bool(sample.has_ocr),
                "has_comments": bool(sample.has_comments),
                "enrichment_status": sample.enrichment_status,
            },
        }
        for sample in selected_samples[:8]
    ]
    inputs = {
        "project_id": sample_set.set_id,
        "creator_name": sample_set.creator_name,
        "content_profile": sample_set.content_profile,
        "topic_index": topic_index,
        "selected_topic": selected_topic,
        "creator_clone_strategy": report.get("creator_clone_strategy") or {},
        "creator_report_view_model": report.get("creator_report_view_model") or {},
        "report_quality": report.get("report_quality") or {},
        "strategy_plan": strategy_plan,
        "representative_evidence": evidence,
        "allowed_sample_ids": [item["sample_id"] for item in evidence],
    }
    schema = _execution_pack_schema_example(selected_topic, sample_set.set_id, topic_index)
    return f"""
你正在执行 Creator Execution Pack v1 的 Create 阶段。

边界：
- 你不是重新分析账号，不能重新推断账号事实。
- 你只能依据给定 Creator Report、Strategy Plan 和代表样本摘要。
- 用户已经主动选择 selected_topic；必须保持其标题、角度、受众、目标和预期指标，不得偷换主题。
- 不得发明 sample_id、互动指标、账号事实或证据。sample 引用只能使用 allowed_sample_ids。
- 迁移创作规律，不要复制原博主的原文、标题、脚本或具体人物素材。
- 输出是一份可直接修改后拍摄的 production-ready brief，不是抽象模板。
- 只返回一个 JSON object，不要 Markdown，不要解释。

约束：
- hook 必须是可直接执行的 0-3 秒视觉和文案方案。
- script 必须针对当前选题，包含 opening、1-8 个 beats、ending、cta、caption_or_voice_over。
- shot_plan 必须有 4-10 个实际镜头。
- titles 必须有 3-5 个真实候选；hashtags 必须有 5-10 个。
- production_checklist 至少 5 项。
- evidence_refs 最多 8 条；creator_rule / strategy_plan 的 value 应尽量逐字引用输入中的规则。
- source 字段留空对象，服务端会写入安全来源元数据。

必须符合此结构：
{json.dumps(schema, ensure_ascii=False, indent=2)}

只读输入：
{json.dumps(_sanitize_prompt_value(inputs), ensure_ascii=False, indent=2)}
""".strip()


def _execution_pack_repair_instruction(selected_topic: dict[str, Any]) -> str:
    return f"""

上一次输出没有严格符合 CreatorExecutionPackV1。请进行一次紧凑修复：
- 只返回 JSON object；补齐缺失字段，不要输出 Markdown。
- selected topic 必须保持为：{json.dumps(selected_topic, ensure_ascii=False)}
- shot_plan 4-10 项，titles 3-5 项，hashtags 5-10 项，production_checklist 至少 5 项。
- 不得发明 sample_id；没有把握的内容写入 warnings 并降低 confidence。
"""


def _execution_pack_schema_example(topic: dict[str, Any], project_id: str, topic_index: int) -> dict[str, Any]:
    return {
        "version": EXECUTION_PACK_VERSION,
        "project_id": project_id,
        "topic_index": topic_index,
        "generated_at": "由服务端写入",
        "topic": topic,
        "creative_basis": {
            "summary": "为什么值得拍",
            "creator_rules": ["逐字引用一条创作者规律"],
            "hook_patterns": ["逐字引用一个 hook pattern"],
            "formulas": ["逐字引用一个公式或模板"],
            "representative_samples": [{"sample_id": "只使用 allowed_sample_ids", "reason": "参考原因"}],
        },
        "hook": {
            "visual": "第一帧具体画面",
            "spoken_or_caption": "0-3 秒具体台词或字幕",
            "purpose": "钩子目的",
            "duration_hint": "0-3s",
        },
        "script": {
            "opening": "具体开场",
            "beats": [{"order": 1, "purpose": "推进目的", "script": "具体内容", "duration_hint": "3-6s"}],
            "ending": "具体结尾",
            "cta": "具体互动引导",
            "caption_or_voice_over": "完整字幕或旁白方向",
        },
        "shot_plan": [
            {
                "order": index,
                "duration_hint": f"{index - 1}-{index + 1}s",
                "shot_type": "近景",
                "subject_action": "具体动作",
                "camera": "机位与运动",
                "composition": "构图",
                "lighting_or_scene": "光线或场景",
                "purpose": "镜头目的",
            }
            for index in range(1, 5)
        ],
        "cover": {"visual": "封面画面", "composition": "主体位置", "headline": "封面文字", "reason": "选择依据"},
        "titles": [
            {"direction": "curiosity", "text": "真实标题候选 A"},
            {"direction": "result", "text": "真实标题候选 B"},
            {"direction": "contrast", "text": "真实标题候选 C"},
        ],
        "publish_copy": "适合短视频平台的发布正文",
        "hashtags": ["#话题1", "#话题2", "#话题3", "#话题4", "#话题5"],
        "editing_notes": {
            "pace": "节奏",
            "cuts": "剪切点",
            "subtitle": "字幕",
            "music_or_sound_direction": "音乐或声音方向",
            "transition_notes": "转场",
        },
        "production_checklist": [f"发布前检查 {index}" for index in range(1, 6)],
        "evidence_refs": [
            {"type": "strategy_plan", "field": "next_topics", "value": topic["title"], "reason": "用户主动选择的选题"}
        ],
        "confidence": "high | medium | low",
        "warnings": [],
        "source": {},
    }


def _load_generation_inputs(project_id: str) -> tuple[CloneSampleSet, dict[str, Any], dict[str, Any]]:
    sample_set = load_sample_set(project_id)
    output_dir = creator_clone_dir(project_id)
    report_path = output_dir / "creator_clone_result.json"
    strategy_path = output_dir / "creator_strategy_plan.json"
    if not report_path.is_file():
        raise AppError(ErrorCode.CREATOR_REPORT_NOT_READY)
    report = _read_json_object(report_path, ErrorCode.CREATOR_REPORT_NOT_READY)
    if not isinstance(report.get("creator_clone_strategy"), dict) or not report.get("creator_clone_strategy"):
        raise AppError(ErrorCode.CREATOR_REPORT_NOT_READY)
    if not strategy_path.is_file():
        raise AppError(ErrorCode.STRATEGY_PLAN_NOT_READY)
    strategy_raw = _read_json_object(strategy_path, ErrorCode.STRATEGY_PLAN_NOT_READY)
    try:
        strategy_plan = validate_creator_strategy_plan(strategy_raw)
    except (TypeError, ValueError) as error:
        raise AppError(ErrorCode.STRATEGY_PLAN_NOT_READY) from error
    return sample_set, report, strategy_plan


def _selected_samples(sample_set: CloneSampleSet) -> list[CloneSample]:
    selected_ids = set(sample_set.selected_sample_ids or [])
    selected = [sample for sample in sample_set.samples if sample.sample_id in selected_ids or sample.selected]
    return selected or list(sample_set.samples)


def _selected_topic(value: Any, report: dict[str, Any]) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    positioning = report.get("creator_positioning") if isinstance(report.get("creator_positioning"), dict) else {}
    return {
        "title": _required_text(payload, "title", 180),
        "angle": _safe_text(payload.get("angle") or payload.get("why") or "延续已验证的创作规律", 260),
        "audience": _safe_text(payload.get("audience") or positioning.get("audience_promise") or "现有目标受众", 220),
        "goal": _safe_text(payload.get("goal") or payload.get("why") or "验证该选题的停留与互动表现", 260),
        "expected_metric": _safe_text(payload.get("expected_metric") or "停留与互动", 120),
    }


def _generation_context(
    sample_set: CloneSampleSet,
    selected_samples: list[CloneSample],
    report: dict[str, Any],
    strategy_plan: dict[str, Any],
    topic_index: int,
) -> tuple[dict[str, Any], list[str], str]:
    quality = report.get("report_quality") if isinstance(report.get("report_quality"), dict) else {}
    score = _integer(quality.get("quality_score", quality.get("score")), fallback=0)
    ready_count = sum(1 for sample in selected_samples if _sample_evidence_ready(sample))
    failed_count = sum(1 for sample in selected_samples if sample.enrichment_status == "failed")
    low_confidence_notes = [
        _safe_text(item, 260)
        for item in strategy_plan.get("low_confidence_notes") or []
        if _safe_text(item, 260)
    ]
    warnings = list(low_confidence_notes[:5])
    confidence_cap = ""
    if score < 70 or low_confidence_notes:
        warnings.append(f"报告质量 {score}/100，本条执行方案建议人工复核。")
        confidence_cap = "low"
    elif failed_count or ready_count < len(selected_samples):
        confidence_cap = "medium"
    if failed_count:
        warnings.append(f"{failed_count} 条代表样本富化失败；执行方案继续生成，但相关视觉建议需要人工确认。")
    if ready_count < len(selected_samples):
        warnings.append(f"代表样本证据完整度为 {ready_count}/{len(selected_samples)}，未完整样本按低置信处理。")
    source = {
        "creator_report": "creator_clone_result.json",
        "strategy_plan": "creator_strategy_plan.json",
        "report_quality_score": score,
        "selected_count": len(selected_samples),
        "evidence_ready_count": ready_count,
        "failed_evidence_count": failed_count,
        "selected_topic_index": topic_index,
        "generation_mode": "llm",
        "llm_attempts": 0,
        "llm_repaired": False,
    }
    return source, _unique_text(warnings, limit=8), confidence_cap


def _sample_evidence_ready(sample: CloneSample) -> bool:
    if sample.enrichment_status == "failed":
        return False
    return sample.understanding_level in {"full", "partial"} or any(
        (sample.has_frames, sample.has_asr, sample.has_ocr, sample.has_comments)
    )


def _normalize_topic(value: dict[str, Any], *, expected: dict[str, Any] | None) -> dict[str, Any]:
    topic = {
        "title": _required_text(value, "title", 180),
        "angle": _required_text(value, "angle", 260),
        "audience": _required_text(value, "audience", 220),
        "goal": _required_text(value, "goal", 260),
        "expected_metric": _required_text(value, "expected_metric", 120),
    }
    if expected:
        normalized_expected = {
            key: _required_text(expected, key, 260 if key in {"angle", "goal"} else 220)
            for key in ("title", "angle", "audience", "goal", "expected_metric")
        }
        if topic["title"] != normalized_expected["title"]:
            raise ValueError("topic title must match the user-selected Strategy Plan topic")
        return normalized_expected
    return topic


def _normalize_creative_basis(
    value: dict[str, Any],
    *,
    context: ExecutionPackValidationContext | None,
) -> tuple[dict[str, Any], int]:
    summary = _required_text(value, "summary", 600)
    creator_rules, invalid_rules = _verified_basis_values(
        _required_list(value, "creator_rules"),
        catalogs=(context.creator_rule_catalog.values() if context else None),
    )
    hook_patterns, invalid_hooks = _verified_basis_values(
        _required_list(value, "hook_patterns"),
        catalogs=((context.creator_rule_catalog.get("hooks") or ()) if context else None),
    )
    formulas, invalid_formulas = _verified_basis_values(
        _required_list(value, "formulas"),
        catalogs=(
            (
                context.creator_rule_catalog.get("templates", ()),
                context.creator_rule_catalog.get("content_strategy", ()),
                context.strategy_plan_catalog.get("script_templates", ()),
                context.strategy_plan_catalog.get("shot_templates", ()),
            )
            if context
            else None
        ),
    )
    representative_rows = _required_list(value, "representative_samples")
    representative_samples: list[dict[str, Any]] = []
    invalid = invalid_rules + invalid_hooks + invalid_formulas
    valid_samples = context.valid_samples if context else {}
    for item in representative_rows[:8]:
        if not isinstance(item, dict):
            invalid += 1
            continue
        sample_id = _safe_id(item.get("sample_id"), allow_empty=True)
        if valid_samples and sample_id not in valid_samples:
            invalid += 1
            continue
        if not sample_id:
            invalid += 1
            continue
        representative_samples.append(
            {
                "sample_id": sample_id,
                "title": valid_samples.get(sample_id, _safe_text(item.get("title") or "代表样本", 180)),
                "reason": _required_text(item, "reason", 260),
            }
        )
    if not any((creator_rules, hook_patterns, formulas, representative_samples)):
        raise ValueError("creative_basis must contain at least one verifiable basis")
    return {
        "summary": summary,
        "creator_rules": creator_rules,
        "hook_patterns": hook_patterns,
        "formulas": formulas,
        "representative_samples": representative_samples[:6],
    }, invalid


def _verified_basis_values(
    value: list[Any],
    *,
    catalogs: Any | None,
) -> tuple[list[str], int]:
    rows = _normalize_string_list(value, minimum=0, maximum=6, limit=260)
    if catalogs is None:
        return rows, 0
    flattened = tuple(
        item
        for catalog in catalogs
        for item in (catalog if isinstance(catalog, (list, tuple)) else (catalog,))
        if item
    )
    if not flattened:
        return [], len(rows)
    verified = [item for item in rows if _catalog_contains(flattened, item)]
    return verified, len(rows) - len(verified)


def _normalize_hook(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "visual": _required_text(value, "visual", 360),
        "spoken_or_caption": _required_text(value, "spoken_or_caption", 360),
        "purpose": _required_text(value, "purpose", 260),
        "duration_hint": _required_text(value, "duration_hint", 60),
    }


def _normalize_script(value: dict[str, Any]) -> dict[str, Any]:
    beats = _required_list(value, "beats")
    if not 1 <= len(beats) <= 8:
        raise ValueError("script beats must contain 1-8 items")
    normalized_beats: list[dict[str, Any]] = []
    for index, item in enumerate(beats, start=1):
        if not isinstance(item, dict):
            raise ValueError("script beat must be an object")
        normalized_beats.append(
            {
                "order": index,
                "purpose": _required_text(item, "purpose", 220),
                "script": _required_text(item, "script", 800),
                "duration_hint": _required_text(item, "duration_hint", 60),
            }
        )
    return {
        "opening": _required_text(value, "opening", 600),
        "beats": normalized_beats,
        "ending": _required_text(value, "ending", 600),
        "cta": _required_text(value, "cta", 360),
        "caption_or_voice_over": _required_text(value, "caption_or_voice_over", 1600),
    }


def _normalize_shot_plan(value: list[Any]) -> list[dict[str, Any]]:
    if len(value) < 4:
        raise ValueError("shot_plan must contain at least 4 shots")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value[:10], start=1):
        if not isinstance(item, dict):
            raise ValueError("shot_plan item must be an object")
        result.append(
            {
                "order": index,
                "duration_hint": _required_text(item, "duration_hint", 60),
                "shot_type": _required_text(item, "shot_type", 100),
                "subject_action": _required_text(item, "subject_action", 360),
                "camera": _required_text(item, "camera", 260),
                "composition": _required_text(item, "composition", 260),
                "lighting_or_scene": _required_text(item, "lighting_or_scene", 260),
                "purpose": _required_text(item, "purpose", 260),
            }
        )
    return result


def _normalize_cover(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "visual": _required_text(value, "visual", 360),
        "composition": _required_text(value, "composition", 260),
        "headline": _required_text(value, "headline", 120),
        "reason": _required_text(value, "reason", 360),
    }


def _normalize_titles(value: list[Any]) -> list[dict[str, Any]]:
    if len(value) < 3:
        raise ValueError("titles must contain at least 3 candidates")
    result: list[dict[str, Any]] = []
    for item in value[:5]:
        if not isinstance(item, dict):
            raise ValueError("title candidate must be an object")
        text = _required_text(item, "text", 180)
        if _is_placeholder_title(text):
            raise ValueError("title candidate must be publishable, not a placeholder")
        result.append(
            {
                "direction": _required_text(item, "direction", 80),
                "text": text,
            }
        )
    return result


def _is_placeholder_title(value: str) -> bool:
    normalized = re.sub(r"[\s_\-：:]", "", value).casefold()
    return bool(
        re.fullmatch(
            r"(?:(?:真实|示例))?标题(?:候选)?(?:[0-9a-z一二三四五]*)",
            normalized,
        )
    )


def _normalize_editing_notes(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "pace": _required_text(value, "pace", 300),
        "cuts": _required_text(value, "cuts", 300),
        "subtitle": _required_text(value, "subtitle", 300),
        "music_or_sound_direction": _required_text(value, "music_or_sound_direction", 300),
        "transition_notes": _required_text(value, "transition_notes", 300),
    }


def _normalize_evidence_refs(
    rows: list[Any],
    *,
    context: ExecutionPackValidationContext | None,
) -> tuple[list[dict[str, Any]], int]:
    result: list[dict[str, Any]] = []
    invalid = 0
    if context:
        result.append(
            {
                "type": "strategy_plan",
                "field": "next_topics",
                "value": context.topic.get("title") or "",
                "reason": "用户主动选择的 Strategy Plan 选题。",
            }
        )
    for item in rows:
        if not isinstance(item, dict):
            invalid += 1
            continue
        evidence_type = str(item.get("type") or "").strip()
        if evidence_type not in ALLOWED_EVIDENCE_TYPES:
            invalid += 1
            continue
        reason = _safe_text(item.get("reason"), 260)
        if not reason:
            invalid += 1
            continue
        if evidence_type == "sample":
            sample_id = _safe_id(item.get("sample_id"), allow_empty=True)
            if not sample_id or (context and sample_id not in context.valid_samples):
                invalid += 1
                continue
            result.append(
                {
                    "type": "sample",
                    "sample_id": sample_id,
                    "title": context.valid_samples.get(sample_id, _safe_text(item.get("title") or "代表样本", 180)) if context else _safe_text(item.get("title") or "代表样本", 180),
                    "reason": reason,
                }
            )
            continue
        field_name = _safe_text(item.get("field"), 100).split("[", 1)[0]
        value = _safe_text(item.get("value"), 360)
        catalog = context.creator_rule_catalog if context and evidence_type == "creator_rule" else context.strategy_plan_catalog if context else {}
        allowed_fields = CREATOR_RULE_FIELDS if evidence_type == "creator_rule" else STRATEGY_PLAN_FIELDS
        if not field_name or field_name not in allowed_fields or not value:
            invalid += 1
            continue
        if context and not _catalog_contains(catalog.get(field_name, ()), value):
            invalid += 1
            continue
        result.append(
            {
                "type": evidence_type,
                "field": field_name,
                "value": value,
                "reason": reason,
            }
        )
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in result:
        key = (item["type"], str(item.get("sample_id") or item.get("field") or ""), str(item.get("value") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    if not deduped:
        raise ValueError("execution pack must retain at least one verified evidence reference")
    return deduped[:8], invalid


def _normalize_confidence(value: Any, *, cap: str = "") -> str:
    confidence = str(value or "").strip().lower()
    if confidence not in ALLOWED_CONFIDENCE:
        raise ValueError("confidence must be high, medium, or low")
    if cap == "low":
        return "low"
    if cap == "medium" and confidence == "high":
        return "medium"
    return confidence


def _normalize_source(value: dict[str, Any]) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    return {
        "creator_report": "creator_clone_result.json",
        "strategy_plan": "creator_strategy_plan.json",
        "report_quality_score": max(0, min(100, _integer(payload.get("report_quality_score"), fallback=0))),
        "selected_count": max(0, _integer(payload.get("selected_count"), fallback=0)),
        "evidence_ready_count": max(0, _integer(payload.get("evidence_ready_count"), fallback=0)),
        "failed_evidence_count": max(0, _integer(payload.get("failed_evidence_count"), fallback=0)),
        "selected_topic_index": max(0, _integer(payload.get("selected_topic_index"), fallback=0)),
        "generation_mode": "llm",
        "llm_attempts": max(0, min(EXECUTION_PACK_MAX_ATTEMPTS, _integer(payload.get("llm_attempts"), fallback=0))),
        "llm_repaired": bool(payload.get("llm_repaired")),
    }


def _catalog_for(value: Any, fields: set[str]) -> dict[str, tuple[str, ...]]:
    payload = value if isinstance(value, dict) else {}
    return {
        field_name: tuple(_unique_text(_flatten_text(payload.get(field_name)), limit=24))
        for field_name in fields
    }


def _catalog_contains(candidates: tuple[str, ...], value: str) -> bool:
    needle = re.sub(r"\s+", " ", value).strip().casefold()
    return any(re.sub(r"\s+", " ", item).strip().casefold() == needle for item in candidates)


def _flatten_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [_safe_text(value, 360)] if _safe_text(value, 360) else []
    if isinstance(value, dict):
        preferred = value.get("title") or value.get("name") or value.get("text") or value.get("value") or value.get("formula") or value.get("summary")
        rows = [_safe_text(preferred, 360)] if preferred else []
        for child in value.values():
            rows.extend(_flatten_text(child))
        return [item for item in rows if item]
    if isinstance(value, (list, tuple)):
        rows: list[str] = []
        for item in value:
            rows.extend(_flatten_text(item))
        return rows
    text = _safe_text(value, 360)
    return [text] if text else []


def _sanitize_prompt_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return "[truncated]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in list(value.items())[:60]:
            normalized_key = str(key).lower()
            if any(token in normalized_key for token in ("cookie", "authorization", "api_key", "token", "source_url", "cover_url", "file_path", "local_path", "signed_url")):
                continue
            result[str(key)[:80]] = _sanitize_prompt_value(child, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [_sanitize_prompt_value(item, depth=depth + 1) for item in list(value)[:40]]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    return _safe_text(value, 1600)


def _safe_text(value: Any, limit: int) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", str(value or ""))
    text = re.sub(r"https?://[^\s)\]}>]+", "[redacted-url]", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<!\w)/(?:Users|home|private|var|tmp|Volumes)/[^\s,;，。]+", "[redacted-path]", text)
    text = re.sub(r"[A-Za-z]:\\(?:Users|Documents and Settings)\\[^\s,;，。]+", "[redacted-path]", text)
    text = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+", "[redacted]", text)
    text = re.sub(r"(?i)\bsk-[A-Za-z0-9_-]{8,}", "[redacted]", text)
    text = re.sub(r"(?i)\b(?:authorization|cookie|api[_ -]?key)\b\s*[:=]?\s*[^\s,;，。]*", "[redacted]", text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _safe_id(value: Any, *, allow_empty: bool = False) -> str:
    candidate = str(value or "").strip()
    if not candidate and allow_empty:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", candidate):
        raise ValueError("identifier contains unsupported characters")
    return candidate


def _validated_project_id(value: Any, error_code: str) -> str:
    original = str(value or "")
    try:
        candidate = _safe_id(original)
    except ValueError as error:
        raise AppError(error_code) from error
    if candidate != original:
        raise AppError(error_code)
    return candidate


def _required_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _required_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _required_text(payload: dict[str, Any], key: str, limit: int) -> str:
    value = _safe_text(payload.get(key), limit)
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _normalize_string_list(
    value: list[Any],
    *,
    minimum: int,
    maximum: int,
    limit: int,
) -> list[str]:
    rows = _unique_text((_safe_text(item, limit) for item in value), limit=maximum)
    if len(rows) < minimum:
        raise ValueError(f"list must contain at least {minimum} items")
    return rows[:maximum]


def _unique_text(values: Any, *, limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in values or []:
        text = _safe_text(item, 360)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _integer(value: Any, *, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _validate_timestamp(value: str) -> None:
    if not value:
        raise ValueError("generated_at is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("generated_at must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise ValueError("generated_at must include a timezone")


def _read_json_object(path: Path, error_code: str) -> dict[str, Any]:
    try:
        if path.stat().st_size > EXECUTION_PACK_MAX_JSON_BYTES:
            raise AppError(error_code)
        value = json.loads(path.read_text(encoding="utf-8"))
    except AppError:
        raise
    except (OSError, json.JSONDecodeError) as error:
        raise AppError(error_code) from error
    if not isinstance(value, dict):
        raise AppError(error_code)
    return value


def _read_json_optional(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return _read_json_object(path, ErrorCode.EXECUTION_PACK_NOT_READY)
    except AppError:
        return {}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)
