from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.errors import AppError, ErrorCode
from app.models import CaseArtifact
from app.routes.common import error_response
from app.services.llm_settings import llm_status_payload
from app.services.analysis_taxonomy import (
    BASE_ANALYSIS_FOCUS,
    build_analysis_context,
    build_prompt,
    explain_content_category,
    infer_content_category,
    list_analysis_profiles,
)
from app.services.analysis_worksheet import (
    build_default_worksheet,
    normalize_worksheet,
    render_analysis_brief,
    worksheet_quality_review,
)
from app.services.asr import run_case_asr
from app.services.auto_analyzer import existing_auto_analysis, manual_review_context_for_case
from app.services.case_builder import build_case_from_local_video
from app.services.enrichment import (
    build_enrichment_archive,
    create_metrics_snapshot,
    enrichment_payload,
    import_comments,
    refresh_analysis_input_enrichment,
)
from app.services.ocr import run_case_ocr


router = APIRouter(prefix="/api/cases", tags=["cases"])


class BuildCaseRequest(BaseModel):
    local_video_id: str


class UpdateAnalysisCategoryRequest(BaseModel):
    category_id: str


class UpdateWorksheetRequest(BaseModel):
    worksheet: dict


class UpdateQualityAcceptanceRequest(BaseModel):
    acceptance: dict


class ImportCommentsRequest(BaseModel):
    text: str = ""
    comments: list[dict] = Field(default_factory=list)
    source: str = "manual"
    permission_note: str = "user provided comments"


class MetricSnapshotRequest(BaseModel):
    capture_method: str = "case_metadata"
    permission_note: str = "local personal analysis"


ARTIFACT_DESCRIPTIONS = {
    "video.mp4": "下载或导入后的本地视频副本，用于抽帧和视觉复盘。",
    "metadata.json": "标题、作者、来源链接、互动数据和导入备注等基础信息。",
    "qualities.json": "视频清晰度候选记录；本地上传模式会标记为 local。",
    "ffprobe.json": "ffprobe 读取到的视频参数，包括时长、分辨率、编码、码率和文件大小。",
    "contact_sheet.jpg": "关键帧总览图，用于快速查看视频节奏和画面变化。",
    "keyframes/": "按时间抽取的关键帧图片，适合交给多模态模型做视觉拆解。",
    "analysis_input.json": "交给大模型的结构化输入，聚合元数据、视频参数、关键帧路径、分析重点和富化摘要。",
    "prompt.md": "可复制给 ChatGPT / Claude / Gemini 的人工分析 Prompt。",
    "worksheet.json": "用户手动拆解工作表，保存人工观察和二次判断。",
    "quality_acceptance.json": "人工质量验收表，用于记录真实样例下 AI 拆解是否可信、哪里需要调规则。",
    "quality_calibration_record.json": "单条作品校准样本，汇总 AI 自检、人工验收、准备度、顶部诊断快照和下一步修正建议。",
    "rerun_plan.json": "下一轮拆解任务单，汇总当前诊断、人工反馈、缺失证据、重跑约束和推荐动作。",
    "rerun_plan.md": "下一轮拆解任务单的 Markdown 版本，适合人工复盘或复制给外部大模型。",
    "analysis_brief.md": "人工工作表生成的简洁 Markdown 摘要。",
    "analysis_result.json": "大模型返回的结构化拆解结果。",
    "analysis_report.md": "大模型拆解结果渲染后的可读 Markdown 报告。",
    "enrichment/manifest.json": "富化层总清单，记录 ASR、OCR、评论、指标和索引状态。",
    "enrichment/comments/comment_summary.json": "评论导入后的高频词、需求和评论区钩子摘要。",
    "enrichment/metrics/snapshots.jsonl": "点赞、评论、分享等指标快照，便于后续观察增长变化。",
    "enrichment/indexes/case_index.json": "给检索、批处理和后续 Agent 使用的结构化索引。",
}


QUALITY_ACCEPTANCE_CHECK_LABELS = {
    "summary_matches_video": "总结是否符合视频",
    "evidence_is_sufficient": "证据是否足够",
    "copyable_points_are_useful": "可复刻点是否有用",
    "shot_table_is_actionable": "分镜表是否可执行",
    "publish_package_is_usable": "发布包是否可用",
}

QUALITY_ACCEPTANCE_VERDICT_LABELS = {
    "pending": "待验收",
    "pass": "通过，可作为样例",
    "needs_fix": "需要修正",
    "reject": "不通过",
}

QUALITY_ACCEPTANCE_BLOCKING_STATUSES = {"needs_fix", "reject"}


def _case_or_error(db: Session, case_id: str) -> CaseArtifact:
    artifact = db.get(CaseArtifact, case_id)
    if not artifact:
        raise AppError(ErrorCode.CASE_BUILD_FAILED, "素材包不存在。")
    return artifact


def _read_json_file(path: str) -> dict:
    file_path = Path(path)
    if not file_path.is_file():
        raise AppError(ErrorCode.CASE_BUILD_FAILED, f"素材包文件缺失：{file_path.name}")
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise AppError(ErrorCode.CASE_BUILD_FAILED, f"素材包 JSON 无法读取：{file_path.name}") from error


def _read_text_file(path: str) -> str:
    file_path = Path(path)
    if not file_path.is_file():
        raise AppError(ErrorCode.CASE_BUILD_FAILED, f"素材包文件缺失：{file_path.name}")
    return file_path.read_text(encoding="utf-8")


def _write_json_file(path: str, payload: dict | list) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _case_dir(artifact: CaseArtifact) -> Path:
    return Path(artifact.prompt_path).parent


def _worksheet_path(artifact: CaseArtifact) -> Path:
    return _case_dir(artifact) / "worksheet.json"


def _analysis_brief_path(artifact: CaseArtifact) -> Path:
    return _case_dir(artifact) / "analysis_brief.md"


def _quality_acceptance_path(artifact: CaseArtifact) -> Path:
    return _case_dir(artifact) / "quality_acceptance.json"


def _quality_calibration_record_path(artifact: CaseArtifact) -> Path:
    return _case_dir(artifact) / "quality_calibration_record.json"


def _rerun_plan_path(artifact: CaseArtifact) -> Path:
    return _case_dir(artifact) / "rerun_plan.json"


def _rerun_plan_markdown_path(artifact: CaseArtifact) -> Path:
    return _case_dir(artifact) / "rerun_plan.md"


def _quality_calibration_index_path() -> Path:
    return settings.calibration_dir / "quality_calibration_index.json"


def _analysis_result_path(artifact: CaseArtifact) -> Path:
    return _case_dir(artifact) / "analysis_result.json"


def _analysis_report_path(artifact: CaseArtifact) -> Path:
    return _case_dir(artifact) / "analysis_report.md"


def _infer_case_category(metadata: dict, analysis_input: dict) -> str:
    existing = (
        analysis_input.get("content_category")
        or metadata.get("content_category")
        or analysis_input.get("analysis_context", {}).get("category_id")
    )
    if existing:
        return str(existing)
    return infer_content_category(
        " ".join(
            [
                str(metadata.get("title") or ""),
                str(metadata.get("notes") or ""),
                str(metadata.get("author") or ""),
                str(metadata.get("source_url") or ""),
            ]
        )
    )


def _category_source_text(metadata: dict, analysis_input: dict) -> str:
    return " ".join(
        [
            str(metadata.get("title") or analysis_input.get("title") or ""),
            str(metadata.get("notes") or ""),
            str(metadata.get("author") or analysis_input.get("author") or ""),
            str(metadata.get("source_url") or analysis_input.get("source_url") or ""),
        ]
    )


def _apply_analysis_context(
    metadata: dict,
    analysis_input: dict,
    category_id: str,
    *,
    category_guess: dict | None = None,
) -> tuple[dict, dict]:
    analysis_context = build_analysis_context(category_id)
    guess = category_guess if isinstance(category_guess, dict) else analysis_input.get("content_category_guess")
    if not isinstance(guess, dict) or guess.get("category_id") != analysis_context["category_id"]:
        guess = explain_content_category(_category_source_text(metadata, analysis_input))
        if guess.get("category_id") != analysis_context["category_id"]:
            guess = {
                "category_id": analysis_context["category_id"],
                "label": analysis_context["label"],
                "description": analysis_context["description"],
                "confidence": "manual",
                "matched_keywords": [],
                "reason": "用户已手动切换分析类型，系统按当前模板展示和生成 Prompt。",
                "source": "manual_override",
            }
    metadata["content_category"] = analysis_context["category_id"]
    metadata["content_category_label"] = analysis_context["label"]
    metadata["content_category_guess"] = guess
    analysis_input["content_category"] = analysis_context["category_id"]
    analysis_input["content_category_label"] = analysis_context["label"]
    analysis_input["content_category_guess"] = guess
    analysis_input["analysis_context"] = analysis_context
    analysis_input["analysis_lens"] = analysis_context["analysis_lens"]
    analysis_input["key_questions"] = analysis_context["key_questions"]
    analysis_input["content_ratio"] = analysis_context["content_ratio"]
    analysis_input.setdefault("analysis_focus", list(BASE_ANALYSIS_FOCUS))
    return metadata, analysis_input


def _load_case_parts(artifact: CaseArtifact) -> tuple[dict, dict, dict, str]:
    metadata = _read_json_file(artifact.metadata_path)
    ffprobe = _read_json_file(artifact.ffprobe_path)
    analysis_input = refresh_analysis_input_enrichment(artifact)
    category_id = _infer_case_category(metadata, analysis_input)
    metadata, analysis_input = _apply_analysis_context(metadata, analysis_input, category_id)
    _write_json_file(artifact.metadata_path, metadata)
    _write_json_file(artifact.analysis_input_path, analysis_input)
    prompt = _read_text_file(artifact.prompt_path)
    if "## 2. 本类型优先分析镜头" not in prompt:
        prompt = build_prompt(metadata, ffprobe, analysis_input["analysis_context"])
    return metadata, ffprobe, analysis_input, prompt


def _load_or_create_worksheet(artifact: CaseArtifact, metadata: dict, ffprobe: dict, analysis_input: dict) -> tuple[dict, str]:
    worksheet_file = _worksheet_path(artifact)
    existing = None
    if worksheet_file.is_file():
        existing = json.loads(worksheet_file.read_text(encoding="utf-8"))
    worksheet = normalize_worksheet(artifact.case_id, analysis_input, None, existing=existing)
    brief = render_analysis_brief(metadata, ffprobe, analysis_input, worksheet)
    _write_json_file(str(worksheet_file), worksheet)
    _analysis_brief_path(artifact).write_text(brief, encoding="utf-8")
    return worksheet, brief


def _update_case_category(artifact: CaseArtifact, category_id: str) -> None:
    metadata = _read_json_file(artifact.metadata_path)
    ffprobe = _read_json_file(artifact.ffprobe_path)
    analysis_input = _read_json_file(artifact.analysis_input_path)
    metadata, analysis_input = _apply_analysis_context(metadata, analysis_input, category_id)
    _write_json_file(artifact.metadata_path, metadata)
    _write_json_file(artifact.analysis_input_path, analysis_input)
    Path(artifact.prompt_path).write_text(
        build_prompt(metadata, ffprobe, analysis_input["analysis_context"]),
        encoding="utf-8",
    )
    _load_or_create_worksheet(artifact, metadata, ffprobe, analysis_input)


def _update_case_worksheet(artifact: CaseArtifact, payload: dict) -> None:
    metadata, ffprobe, analysis_input, _prompt = _load_case_parts(artifact)
    existing = None
    worksheet_file = _worksheet_path(artifact)
    if worksheet_file.is_file():
        existing = json.loads(worksheet_file.read_text(encoding="utf-8"))
    worksheet = normalize_worksheet(artifact.case_id, analysis_input, payload, existing=existing)
    _write_json_file(str(worksheet_file), worksheet)
    _analysis_brief_path(artifact).write_text(
        render_analysis_brief(metadata, ffprobe, analysis_input, worksheet),
        encoding="utf-8",
    )


def _default_quality_acceptance(artifact: CaseArtifact, analysis_result: dict | None) -> dict:
    quality = (analysis_result or {}).get("quality_review") or {}
    return {
        "case_id": artifact.case_id,
        "verdict": "pending",
        "score": "",
        "reviewer": "",
        "summary": "",
        "checks": {
            "summary_matches_video": "",
            "evidence_is_sufficient": "",
            "copyable_points_are_useful": "",
            "shot_table_is_actionable": "",
            "publish_package_is_usable": "",
        },
        "notes": "",
        "next_actions": "",
        "quality_snapshot": {
            "score": quality.get("score", 0),
            "level": quality.get("level", ""),
            "label": quality.get("label", ""),
            "gap_ids": [gap.get("id", "") for gap in quality.get("gaps") or [] if isinstance(gap, dict)],
        },
    }


def _normalize_quality_acceptance(
    artifact: CaseArtifact,
    payload: dict | None,
    analysis_result: dict | None,
    existing: dict | None = None,
) -> dict:
    base = _default_quality_acceptance(artifact, analysis_result)
    source = existing if isinstance(existing, dict) else {}
    incoming = payload if isinstance(payload, dict) else {}
    merged = {**base, **source, **incoming}
    checks = {**base["checks"], **(source.get("checks") if isinstance(source.get("checks"), dict) else {})}
    checks.update(incoming.get("checks") if isinstance(incoming.get("checks"), dict) else {})
    merged["checks"] = {
        key: str(checks.get(key) or "").strip()
        for key in base["checks"]
    }
    verdict = str(merged.get("verdict") or "pending").strip()
    merged["verdict"] = verdict if verdict in {"pending", "pass", "needs_fix", "reject"} else "pending"
    merged["score"] = str(merged.get("score") or "").strip()
    merged["reviewer"] = str(merged.get("reviewer") or "").strip()
    merged["summary"] = str(merged.get("summary") or "").strip()
    merged["notes"] = str(merged.get("notes") or "").strip()
    merged["next_actions"] = str(merged.get("next_actions") or "").strip()
    merged["case_id"] = artifact.case_id
    merged["quality_snapshot"] = base["quality_snapshot"]
    return merged


def _load_or_create_quality_acceptance(artifact: CaseArtifact, analysis_result: dict | None) -> dict:
    file_path = _quality_acceptance_path(artifact)
    existing = None
    if file_path.is_file():
        existing = json.loads(file_path.read_text(encoding="utf-8"))
    acceptance = _normalize_quality_acceptance(artifact, None, analysis_result, existing=existing)
    _write_json_file(str(file_path), acceptance)
    return acceptance


def _update_quality_acceptance(artifact: CaseArtifact, payload: dict, analysis_result: dict | None) -> None:
    file_path = _quality_acceptance_path(artifact)
    existing = None
    if file_path.is_file():
        existing = json.loads(file_path.read_text(encoding="utf-8"))
    acceptance = _normalize_quality_acceptance(artifact, payload, analysis_result, existing=existing)
    _write_json_file(str(file_path), acceptance)


def _append_unique_action(
    actions: list[dict],
    label: str,
    description: str,
    target: str = "",
    mode: str = "focus",
) -> None:
    normalized = (label.strip(), description.strip(), target.strip(), _normalize_action_mode(mode))
    if not normalized[0] and not normalized[1]:
        return
    for action in actions:
        if _same_action_slot(action, normalized):
            return
    actions.append(
        {"label": normalized[0], "description": normalized[1], "target": normalized[2], "mode": normalized[3]}
    )


def _prepend_unique_action(
    actions: list[dict],
    label: str,
    description: str,
    target: str = "",
    mode: str = "focus",
) -> None:
    normalized = (label.strip(), description.strip(), target.strip(), _normalize_action_mode(mode))
    if not normalized[0] and not normalized[1]:
        return
    actions[:] = [
        action
        for action in actions
        if not _same_action_slot(action, normalized)
    ]
    actions.insert(
        0,
        {"label": normalized[0], "description": normalized[1], "target": normalized[2], "mode": normalized[3]},
    )


def _normalize_action_mode(mode: str) -> str:
    return "click" if str(mode or "").strip() == "click" else "focus"


def _same_action_slot(action: dict, normalized: tuple[str, str, str, str]) -> bool:
    label = action.get("label", "").strip()
    description = action.get("description", "").strip()
    target = action.get("target", "").strip()
    if normalized[2]:
        return (label, target) == (normalized[0], normalized[2])
    return (label, description, target) == normalized[:3]


def _quality_acceptance_blockers(quality_acceptance: dict) -> list[dict]:
    checks = quality_acceptance.get("checks") if isinstance(quality_acceptance.get("checks"), dict) else {}
    blockers = []
    for key, value in checks.items():
        status = str(value or "").strip()
        if status not in QUALITY_ACCEPTANCE_BLOCKING_STATUSES:
            continue
        label = QUALITY_ACCEPTANCE_CHECK_LABELS.get(key, key)
        blockers.append(
            {
                "id": key,
                "label": label,
                "status": status,
                "message": f"{label}被人工标记为「{QUALITY_ACCEPTANCE_VERDICT_LABELS.get(status, status)}」。",
            }
        )
    return blockers


def _quality_calibration_payload(
    analysis_result: dict | None,
    quality_acceptance: dict,
    analysis_readiness: dict,
    worksheet_review: dict,
    rerun_strategy: dict | None = None,
) -> dict:
    quality = (analysis_result or {}).get("quality_review") or {}
    quality_gaps = quality.get("gaps") if isinstance(quality.get("gaps"), list) else []
    readiness_gaps = analysis_readiness.get("critical_gaps") if isinstance(analysis_readiness.get("critical_gaps"), list) else []
    acceptance_blockers = _quality_acceptance_blockers(quality_acceptance)
    verdict = str(quality_acceptance.get("verdict") or "pending").strip()
    has_ai_report = bool(analysis_result)
    has_acceptance_feedback = bool(
        verdict not in {"", "pending"}
        or str(quality_acceptance.get("score") or "").strip()
        or str(quality_acceptance.get("summary") or "").strip()
        or acceptance_blockers
        or str(quality_acceptance.get("notes") or "").strip()
        or str(quality_acceptance.get("next_actions") or "").strip()
    )

    actions: list[dict] = []
    if not has_ai_report:
        status = "needs_ai_analysis"
        label = "等待 AI 拆解"
        summary = "素材包已生成，但还没有 AI 自动拆解报告。先运行 AI，再做人工验收。"
        _append_unique_action(actions, "开始 AI 拆解", "生成第一版 AI 拆解报告。", "#run-auto-analysis-button")
    elif verdict == "pass" and not quality_gaps:
        status = "accepted"
        label = "人工验收通过"
        summary = "AI 拆解已通过人工验收，可以作为样例沉淀。"
        _append_unique_action(actions, "沉淀样例", "保留这份 case 作为后续 prompt 与质量闸门的正样本。", "")
    elif verdict in {"needs_fix", "reject"} or acceptance_blockers:
        status = "needs_rerun"
        label = "需要按人工反馈重跑"
        summary = quality_acceptance.get("summary") or "人工验收指出拆解仍有问题，建议补证据或调整后重新 AI 拆解。"
        if quality_acceptance.get("next_actions"):
            _append_unique_action(actions, "执行人工下一步", str(quality_acceptance.get("next_actions")), "")
        _append_unique_action(actions, "重新 AI 拆解", "重新分析时会带入人工质量验收反馈。", "#run-auto-analysis-button")
    elif verdict == "pending":
        status = "awaiting_review"
        label = "等待人工验收"
        summary = "AI 拆解已生成，建议先做人工质量验收，确认结论、证据、分镜和发布包是否可信。"
        _append_unique_action(actions, "填写质量验收", "记录这份 AI 拆解是否符合你的真实判断。", "#quality-acceptance-verdict")
    else:
        status = "calibrating"
        label = "校准中"
        summary = "已有部分校准信息，建议继续补充人工验收或重新 AI 拆解。"
        _append_unique_action(actions, "继续校准", "补全人工质量验收后再重新分析。", "#quality-acceptance-verdict")

    for blocker in acceptance_blockers:
        _append_unique_action(actions, blocker["label"], blocker["message"], "#quality-acceptance-verdict")

    for gap in quality_gaps[:3]:
        if not isinstance(gap, dict):
            continue
        _append_unique_action(
            actions,
            gap.get("label") or gap.get("id") or "AI 质量缺口",
            gap.get("action") or gap.get("message") or "根据 AI 自检补齐缺口。",
            "#auto-analysis-summary",
        )

    for gap in readiness_gaps[:3]:
        if not isinstance(gap, dict):
            continue
        _append_unique_action(
            actions,
            gap.get("action_label") or gap.get("label") or "补齐素材",
            gap.get("action") or gap.get("message") or "补齐拆解所需素材。",
            gap.get("action_target") or "#readiness-summary",
        )

    payload = {
        "status": status,
        "label": label,
        "summary": summary,
        "ai_quality": {
            "has_report": has_ai_report,
            "score": quality.get("score", 0),
            "max_score": quality.get("max_score", 100),
            "level": quality.get("level", ""),
            "label": quality.get("label", ""),
            "summary": quality.get("summary", ""),
            "gap_count": len(quality_gaps),
            "gaps": quality_gaps[:8],
        },
        "human_acceptance": {
            "has_feedback": has_acceptance_feedback,
            "verdict": verdict or "pending",
            "verdict_label": QUALITY_ACCEPTANCE_VERDICT_LABELS.get(verdict, "待验收"),
            "score": str(quality_acceptance.get("score") or "").strip(),
            "summary": str(quality_acceptance.get("summary") or "").strip(),
            "blocker_count": len(acceptance_blockers),
            "blockers": acceptance_blockers,
        },
        "readiness": {
            "score": analysis_readiness.get("score", 0),
            "label": analysis_readiness.get("label", ""),
            "critical_gap_count": len(readiness_gaps),
            "critical_gaps": readiness_gaps[:8],
        },
        "worksheet": {
            "score": worksheet_review.get("score", 0),
            "label": worksheet_review.get("label", ""),
            "level": worksheet_review.get("level", ""),
        },
        "next_actions": actions[:8],
    }
    payload["recommendations"] = _quality_calibration_recommendations(
        _quality_calibration_insights(
            [
                {
                    "title": "current case",
                    "quality_calibration": payload,
                    "quality_acceptance": quality_acceptance,
                    "rerun_strategy": rerun_strategy if isinstance(rerun_strategy, dict) else {},
                }
            ]
        )
    )
    return payload


def _case_diagnosis_payload(
    analysis_result: dict | None,
    analysis_readiness: dict,
    quality_calibration: dict,
) -> dict:
    quality = (analysis_result or {}).get("quality_review") or {}
    enrichment_coverage = (analysis_result or {}).get("enrichment_coverage") or {}
    coverage_items = enrichment_coverage.get("items") if isinstance(enrichment_coverage.get("items"), dict) else {}
    coverage_summary = (
        enrichment_coverage.get("summary") if isinstance(enrichment_coverage.get("summary"), dict) else {}
    )
    quality_gaps = quality.get("gaps") if isinstance(quality.get("gaps"), list) else []
    readiness_gaps = (
        analysis_readiness.get("critical_gaps") if isinstance(analysis_readiness.get("critical_gaps"), list) else []
    )
    calibration_status = str(quality_calibration.get("status") or "")
    quality_score = int(quality.get("score") or 0)
    readiness_score = int(analysis_readiness.get("score") or 0)
    coverage_blocking_count = int(coverage_summary.get("blocking_count") or 0)
    human_acceptance = quality_calibration.get("human_acceptance") or {}

    blockers: list[dict] = []
    actions: list[dict] = []

    for key, item in coverage_items.items():
        if not isinstance(item, dict) or item.get("verdict") not in {
            "available_not_used",
            "evidence_without_insight",
            "insight_without_evidence",
            "empty_result",
        }:
            continue
        _append_unique_diagnosis_item(
            blockers,
            "enrichment",
            item.get("label") or key,
            item.get("message") or "富化证据和拆解结论没有对齐。",
            "#auto-analysis-summary",
        )
        if item.get("action"):
            _append_unique_action(actions, item.get("label") or "处理富化证据", item.get("action"), "#auto-analysis-summary")

    for gap in quality_gaps[:4]:
        if not isinstance(gap, dict):
            continue
        _append_unique_diagnosis_item(
            blockers,
            "ai_quality",
            gap.get("label") or gap.get("id") or "AI 质量缺口",
            gap.get("message") or gap.get("action") or "AI 自检发现拆解质量缺口。",
            "#auto-analysis-summary",
        )

    for gap in readiness_gaps[:4]:
        if not isinstance(gap, dict):
            continue
        _append_unique_diagnosis_item(
            blockers,
            "readiness",
            gap.get("label") or gap.get("id") or "准备度缺口",
            gap.get("message") or gap.get("action") or "拆解输入仍有缺口。",
            gap.get("action_target") or "#readiness-summary",
        )

    for blocker in (human_acceptance.get("blockers") or [])[:4]:
        if not isinstance(blocker, dict):
            continue
        _append_unique_diagnosis_item(
            blockers,
            "human_acceptance",
            blocker.get("label") or blocker.get("id") or "人工验收阻塞项",
            blocker.get("message") or blocker.get("status") or "人工验收指出需要修正。",
            "#quality-acceptance-verdict",
        )

    for action in quality_calibration.get("next_actions") or []:
        if not isinstance(action, dict):
            continue
        _append_unique_action(
            actions,
            action.get("label") or "下一步",
            action.get("description") or "",
            action.get("target") or "",
        )

    if not analysis_result:
        status = "needs_ai_analysis"
        label = "尚未生成拆解报告"
        summary = "素材包已经生成，但还没有 AI 自动拆解。先生成第一版报告，再进入人工验收和质量校准。"
    elif calibration_status == "needs_rerun":
        status = "needs_rerun"
        label = "需要按人工反馈重跑"
        summary = quality_calibration.get("summary") or "人工验收指出拆解仍有问题，建议带着反馈重新 AI 拆解。"
    elif coverage_blocking_count:
        status = "enrichment_mismatch"
        label = "富化证据没有对齐"
        summary = "ASR、OCR 或评论已有可用信息，但报告没有正确消费，或输出了缺少证据的洞察。"
    elif readiness_gaps and readiness_score < 85:
        status = "needs_context"
        label = "拆解证据还不完整"
        summary = "基础报告可以阅读，但部分素材证据还没补齐，建议先处理关键准备度缺口。"
    elif quality_score >= 85 and calibration_status == "accepted":
        status = "accepted"
        label = "可作为正样本沉淀"
        summary = "AI 自检和人工验收都比较稳定，可以保存为校准样本。"
    elif quality_score >= 70:
        status = "reviewable"
        label = "可进入人工复核"
        summary = "AI 报告已有可用结构，建议用人工质量验收确认总结、证据、分镜和发布包是否可信。"
    else:
        status = "needs_review"
        label = "需要补齐后再用"
        summary = "拆解报告还有关键质量缺口，不建议直接作为复刻依据。"

    if not analysis_result:
        _prepend_unique_action(
            actions,
            "开始 AI 拆解",
            "生成第一版 AI 自动拆解报告。",
            "#run-auto-analysis-button",
            mode="click",
        )
    elif status == "needs_rerun":
        _prepend_unique_action(
            actions,
            "保存反馈并重跑",
            "保存当前人工验收反馈，并立即带入反馈重新 AI 拆解。",
            "#save-quality-acceptance-and-rerun-button",
            mode="click",
        )
    elif status == "accepted":
        _prepend_unique_action(
            actions,
            "保存校准样本",
            "把这条通过验收的 case 沉淀为正向校准样本。",
            "#save-quality-calibration-record-button",
            mode="click",
        )
    elif status == "enrichment_mismatch":
        _prepend_unique_action(
            actions,
            "处理证据后重跑",
            "先处理富化证据使用阻塞，再重新 AI 拆解。",
            "#run-auto-analysis-button",
        )
    elif status in {"reviewable", "needs_review"}:
        _prepend_unique_action(
            actions,
            "填写质量验收",
            "先用人工质量验收确认总结、证据、分镜和发布包是否可信。",
            "#quality-acceptance-verdict",
        )

    if not actions:
        _append_unique_action(actions, "继续人工复核", "查看质量缺口和素材证据，决定是否保存为校准样本。", "#quality-calibration-summary")

    return {
        "status": status,
        "label": label,
        "summary": summary,
        "score": {
            "quality": quality_score,
            "readiness": readiness_score,
            "enrichment_blocking": coverage_blocking_count,
            "human_blocking": int(human_acceptance.get("blocker_count") or 0),
        },
        "blockers": blockers[:8],
        "primary_actions": actions[:4],
    }


def _evidence_status_is_ready(status: str) -> bool:
    return str(status or "").strip() in {"success", "no_speech", "no_text"}


def _split_rerun_evidence(required_evidence: list[dict]) -> tuple[list[dict], list[dict]]:
    ready: list[dict] = []
    missing: list[dict] = []
    for item in required_evidence:
        if not isinstance(item, dict):
            continue
        target = ready if _evidence_status_is_ready(str(item.get("status") or "")) else missing
        target.append(item)
    return ready, missing


def _dedupe_plan_actions(*groups: list[dict]) -> list[dict]:
    actions: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for group in groups:
        for item in group or []:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or item.get("action_label") or item.get("id") or "").strip()
            description = str(item.get("description") or item.get("action") or item.get("message") or "").strip()
            target = str(item.get("target") or item.get("action_target") or "").strip()
            if not label and not description:
                continue
            key = (label, description, target)
            if key in seen:
                continue
            seen.add(key)
            actions.append(
                {
                    "label": label,
                    "description": description,
                    "target": target,
                    "mode": str(item.get("mode") or item.get("action_mode") or "").strip(),
                }
            )
    return actions


def _rerun_plan_execution_gate(
    plan_status: str,
    analysis_result: dict | None,
    missing_evidence: list[dict],
    readiness_gaps: list[dict],
    recommended_actions: list[dict],
    quality_calibration: dict,
) -> dict:
    blocking_reasons: list[str] = []
    for item in missing_evidence:
        label = str(item.get("label") or item.get("id") or "必需证据").strip()
        instruction = str(item.get("instruction") or "").strip()
        blocking_reasons.append(f"缺少{label}：{instruction}" if instruction else f"缺少{label}")
    for gap in readiness_gaps:
        if not isinstance(gap, dict) or gap.get("id") in {"comments", "speech_asr", "screen_ocr"}:
            continue
        label = str(gap.get("label") or gap.get("id") or "准备度缺口").strip()
        message = str(gap.get("message") or gap.get("action") or "").strip()
        blocking_reasons.append(f"{label}：{message}" if message else label)
    next_action = recommended_actions[0] if recommended_actions else {}
    if missing_evidence:
        mode = "collect_evidence_first"
        can_rerun_now = False
    elif not analysis_result:
        mode = "run_first_analysis"
        can_rerun_now = True
    elif plan_status == "accepted" or quality_calibration.get("status") == "accepted":
        mode = "archive_positive_case"
        can_rerun_now = False
    elif plan_status == "needs_rerun":
        mode = "rerun_with_feedback"
        can_rerun_now = True
    else:
        mode = "review_or_calibrate"
        can_rerun_now = False
    return {
        "mode": mode,
        "can_rerun_now": can_rerun_now,
        "blocking_reasons": blocking_reasons[:8],
        "next_best_action": next_action,
        "message": (
            "先补齐缺失证据，再带着人工反馈重跑。"
            if missing_evidence
            else "可以进入下一步。"
            if can_rerun_now
            else "当前不建议直接重跑，先按任务单复核或沉淀。"
        ),
    }


def _markdown_escape_line(value) -> str:
    return " ".join(str(value or "").split())


def _markdown_bullets(items: list, empty_text: str = "暂无") -> list[str]:
    if not items:
        return [f"- {empty_text}"]
    lines: list[str] = []
    for item in items:
        if isinstance(item, dict):
            label = _markdown_escape_line(item.get("label") or item.get("id") or item.get("action_label") or "项目")
            detail = _markdown_escape_line(
                item.get("description")
                or item.get("instruction")
                or item.get("action")
                or item.get("message")
                or item.get("status")
                or ""
            )
            target = _markdown_escape_line(item.get("target") or item.get("action_target") or "")
            suffix = f" -> {target}" if target else ""
            lines.append(f"- {label}{f'：{detail}' if detail else ''}{suffix}")
        else:
            lines.append(f"- {_markdown_escape_line(item)}")
    return lines


def _render_rerun_plan_markdown(plan: dict) -> str:
    gate = plan.get("execution_gate") if isinstance(plan.get("execution_gate"), dict) else {}
    diagnosis = plan.get("diagnosis") if isinstance(plan.get("diagnosis"), dict) else {}
    quality = plan.get("quality_snapshot") if isinstance(plan.get("quality_snapshot"), dict) else {}
    strategy = plan.get("rerun_strategy") if isinstance(plan.get("rerun_strategy"), dict) else {}
    compliance = plan.get("rerun_compliance") if isinstance(plan.get("rerun_compliance"), dict) else {}
    evidence = plan.get("evidence_plan") if isinstance(plan.get("evidence_plan"), dict) else {}
    files = plan.get("files") if isinstance(plan.get("files"), dict) else {}
    lines = [
        "# 下一轮拆解任务单",
        "",
        f"- Case ID：{_markdown_escape_line(plan.get('case_id'))}",
        f"- 标题：{_markdown_escape_line(plan.get('title'))}",
        f"- 作者：{_markdown_escape_line(plan.get('author'))}",
        f"- 来源：{_markdown_escape_line(plan.get('source_url'))}",
        f"- 内容类型：{_markdown_escape_line(plan.get('content_category_label'))}",
        f"- 任务状态：{_markdown_escape_line(plan.get('status'))}",
        f"- 生成时间：{_markdown_escape_line(plan.get('generated_at'))}",
        "",
        "## 1. 执行闸门",
        "",
        f"- 当前模式：{_markdown_escape_line(gate.get('mode'))}",
        f"- 是否建议立即重跑：{'是' if gate.get('can_rerun_now') else '否'}",
        f"- 说明：{_markdown_escape_line(gate.get('message'))}",
        "",
        "### 阻塞原因",
        "",
        *_markdown_bullets(gate.get("blocking_reasons") or [], "无阻塞原因"),
        "",
        "### 下一步首选动作",
        "",
        *_markdown_bullets([gate.get("next_best_action")] if gate.get("next_best_action") else [], "暂无动作"),
        "",
        "## 2. 当前诊断",
        "",
        f"- 状态：{_markdown_escape_line(diagnosis.get('label') or diagnosis.get('status'))}",
        f"- 结论：{_markdown_escape_line(diagnosis.get('summary'))}",
        f"- 分数：{_markdown_escape_line(diagnosis.get('score'))}",
        "",
        "## 3. 质量快照",
        "",
        f"- 准备度：{_markdown_escape_line(quality.get('readiness_score'))} / 100，{_markdown_escape_line(quality.get('readiness_label'))}",
        f"- 校准状态：{_markdown_escape_line(quality.get('calibration_label') or quality.get('calibration_status'))}",
        f"- 人工结论：{_markdown_escape_line((quality.get('human_acceptance') or {}).get('verdict'))}",
        f"- 人工意见：{_markdown_escape_line((quality.get('human_acceptance') or {}).get('summary'))}",
        f"- 人工备注：{_markdown_escape_line((quality.get('human_acceptance') or {}).get('notes'))}",
        f"- 人工下一步：{_markdown_escape_line((quality.get('human_acceptance') or {}).get('next_actions'))}",
        "",
        "## 4. 重跑硬约束",
        "",
        f"- 是否启用：{'是' if strategy.get('active') else '否'}",
        f"- 优先级：{_markdown_escape_line(strategy.get('priority'))}",
        f"- 摘要：{_markdown_escape_line(strategy.get('summary'))}",
        "",
        "## 5. 重跑合规检查",
        "",
        f"- 是否启用：{'是' if compliance.get('active') else '否'}",
        f"- 状态：{_markdown_escape_line(compliance.get('status'))}",
        f"- 合规分：{_markdown_escape_line(compliance.get('score', 100))} / 100",
        f"- 结论：{_markdown_escape_line(compliance.get('summary'))}",
        "",
        "### 未通过约束",
        "",
        *_markdown_bullets(
            [item for item in compliance.get("checks") or [] if isinstance(item, dict) and not item.get("passed")],
            "暂无未通过约束",
        ),
        "",
        "### 全部约束",
        "",
        *_markdown_bullets(compliance.get("checks") or [], "暂无约束"),
        "",
        "## 6. 重跑约束明细",
        "",
        "### 修正目标",
        "",
        *_markdown_bullets(strategy.get("fix_targets") or [], "暂无修正目标"),
        "",
        "### 禁止重复",
        "",
        *_markdown_bullets(strategy.get("do_not_repeat") or [], "暂无禁止项"),
        "",
        "### 输出要求",
        "",
        *_markdown_bullets(strategy.get("output_requirements") or [], "暂无额外要求"),
        "",
        "## 7. 证据计划",
        "",
        "### 缺失证据",
        "",
        *_markdown_bullets(evidence.get("missing_evidence") or [], "暂无缺失证据"),
        "",
        "### 已就绪证据",
        "",
        *_markdown_bullets(evidence.get("ready_evidence") or [], "暂无已就绪证据"),
        "",
        "### 关键准备度缺口",
        "",
        *_markdown_bullets(evidence.get("critical_readiness_gaps") or [], "暂无关键缺口"),
        "",
        "## 8. 推荐动作",
        "",
        *_markdown_bullets(plan.get("recommended_actions") or [], "暂无推荐动作"),
        "",
        "## 9. 相关文件",
        "",
    ]
    for label, path in files.items():
        lines.append(f"- {label}：{path}")
    lines.append("")
    return "\n".join(lines)


def _build_rerun_plan(
    artifact: CaseArtifact,
    metadata: dict,
    analysis_input: dict,
    analysis_result: dict | None,
    quality_acceptance: dict,
    analysis_readiness: dict,
    quality_calibration: dict,
    case_diagnosis: dict,
    rerun_strategy: dict,
) -> dict:
    required_evidence = (
        rerun_strategy.get("required_evidence")
        if isinstance(rerun_strategy.get("required_evidence"), list)
        else []
    )
    ready_evidence, missing_evidence = _split_rerun_evidence(required_evidence)
    readiness_gaps = (
        analysis_readiness.get("critical_gaps")
        if isinstance(analysis_readiness.get("critical_gaps"), list)
        else []
    )
    plan_status = "needs_rerun" if rerun_strategy.get("active") else str(case_diagnosis.get("status") or "reviewable")
    if missing_evidence:
        plan_status = "missing_required_evidence"
    elif not analysis_result:
        plan_status = "needs_ai_analysis"
    elif quality_calibration.get("status") == "accepted":
        plan_status = "accepted"
    if missing_evidence:
        action_groups = [
            missing_evidence,
            readiness_gaps,
            quality_calibration.get("recommendations") or [],
            quality_calibration.get("next_actions") or [],
            case_diagnosis.get("primary_actions") or [],
        ]
    elif not analysis_result:
        action_groups = [
            case_diagnosis.get("primary_actions") or [],
            quality_calibration.get("next_actions") or [],
            readiness_gaps,
            quality_calibration.get("recommendations") or [],
        ]
    else:
        action_groups = [
            quality_calibration.get("recommendations") or [],
            quality_calibration.get("next_actions") or [],
            case_diagnosis.get("primary_actions") or [],
            readiness_gaps,
        ]
    recommended_actions = _dedupe_plan_actions(*action_groups)[:12]
    execution_gate = _rerun_plan_execution_gate(
        plan_status,
        analysis_result,
        missing_evidence,
        readiness_gaps,
        recommended_actions,
        quality_calibration,
    )
    rerun_compliance = (
        analysis_result.get("rerun_compliance")
        if isinstance(analysis_result, dict) and isinstance(analysis_result.get("rerun_compliance"), dict)
        else {}
    )

    plan = {
        "schema_version": 1,
        "case_id": artifact.case_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": plan_status,
        "title": metadata.get("title") or analysis_input.get("title") or "",
        "author": metadata.get("author") or analysis_input.get("author") or "",
        "source_url": metadata.get("source_url") or analysis_input.get("source_url") or "",
        "content_category": analysis_input.get("content_category") or metadata.get("content_category") or "generic",
        "content_category_label": (
            analysis_input.get("content_category_label")
            or metadata.get("content_category_label")
            or "通用短视频"
        ),
        "diagnosis": {
            "status": case_diagnosis.get("status", ""),
            "label": case_diagnosis.get("label", ""),
            "summary": case_diagnosis.get("summary", ""),
            "score": case_diagnosis.get("score", {}),
            "blockers": case_diagnosis.get("blockers", []),
            "primary_actions": case_diagnosis.get("primary_actions", []),
        },
        "quality_snapshot": {
            "readiness_score": analysis_readiness.get("score", 0),
            "readiness_label": analysis_readiness.get("label", ""),
            "calibration_status": quality_calibration.get("status", ""),
            "calibration_label": quality_calibration.get("label", ""),
            "ai_quality": (quality_calibration.get("ai_quality") or {}),
            "human_acceptance": {
                "verdict": quality_acceptance.get("verdict", "pending"),
                "score": quality_acceptance.get("score", ""),
                "summary": quality_acceptance.get("summary", ""),
                "notes": quality_acceptance.get("notes", ""),
                "next_actions": quality_acceptance.get("next_actions", ""),
            },
        },
        "rerun_strategy": {
            "active": bool(rerun_strategy.get("active")),
            "priority": rerun_strategy.get("priority", "normal"),
            "summary": rerun_strategy.get("summary", ""),
            "evidence_summary": rerun_strategy.get("evidence_summary", {}),
            "fix_targets": rerun_strategy.get("fix_targets", []),
            "do_not_repeat": rerun_strategy.get("do_not_repeat", []),
            "required_evidence": required_evidence,
            "output_requirements": rerun_strategy.get("output_requirements", []),
        },
        "rerun_compliance": {
            "active": bool(rerun_compliance.get("active")),
            "status": rerun_compliance.get("status", "not_available" if analysis_result else "not_analyzed"),
            "score": rerun_compliance.get("score", 100 if not analysis_result else 0),
            "summary": rerun_compliance.get(
                "summary",
                "尚未生成 AI 报告，暂无重跑合规检查。" if not analysis_result else "当前报告缺少重跑合规检查。",
            ),
            "blocking_count": int(rerun_compliance.get("blocking_count") or 0),
            "checks": rerun_compliance.get("checks", []),
        },
        "evidence_plan": {
            "ready_evidence": ready_evidence,
            "missing_evidence": missing_evidence,
            "critical_readiness_gaps": readiness_gaps,
        },
        "execution_gate": execution_gate,
        "recommended_actions": recommended_actions,
        "files": {
            "analysis_input": artifact.analysis_input_path,
            "prompt": artifact.prompt_path,
            "analysis_result": str(_analysis_result_path(artifact)),
            "analysis_report": str(_analysis_report_path(artifact)),
            "quality_acceptance": str(_quality_acceptance_path(artifact)),
            "quality_calibration_record": str(_quality_calibration_record_path(artifact)),
            "rerun_plan": str(_rerun_plan_path(artifact)),
            "rerun_plan_markdown": str(_rerun_plan_markdown_path(artifact)),
        },
    }
    _write_json_file(str(_rerun_plan_path(artifact)), plan)
    _rerun_plan_markdown_path(artifact).write_text(_render_rerun_plan_markdown(plan), encoding="utf-8")
    return plan


def _append_unique_diagnosis_item(items: list[dict], source: str, label: str, message: str, target: str) -> None:
    key = (source, label, message, target)
    for item in items:
        if (item.get("source"), item.get("label"), item.get("message"), item.get("target")) == key:
            return
    items.append(
        {
            "source": source,
            "label": label,
            "message": message,
            "target": target,
        }
    )


def _quality_calibration_record_payload(
    artifact: CaseArtifact,
    metadata: dict,
    ffprobe: dict,
    analysis_input: dict,
    analysis_result: dict | None,
    quality_acceptance: dict,
    worksheet_review: dict,
    analysis_readiness: dict,
    quality_calibration: dict,
    case_diagnosis: dict,
    rerun_strategy: dict,
) -> dict:
    stats = analysis_input.get("stats") or {}
    video = analysis_input.get("video") or {}
    return {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "case_id": artifact.case_id,
        "aweme_id": metadata.get("aweme_id") or analysis_input.get("aweme_id") or artifact.aweme_id or "",
        "local_video_id": artifact.local_video_id,
        "title": metadata.get("title") or analysis_input.get("title") or "",
        "author": metadata.get("author") or analysis_input.get("author") or "",
        "source_url": metadata.get("source_url") or analysis_input.get("source_url") or "",
        "content_category": analysis_input.get("content_category") or metadata.get("content_category") or "generic",
        "content_category_label": (
            analysis_input.get("content_category_label")
            or metadata.get("content_category_label")
            or "通用短视频"
        ),
        "stats": {
            "like_count": int(stats.get("like_count") or metadata.get("like_count") or 0),
            "comment_count": int(stats.get("comment_count") or metadata.get("comment_count") or 0),
            "share_count": int(stats.get("share_count") or metadata.get("share_count") or 0),
            "engagement_score": int(stats.get("engagement_score") or metadata.get("engagement_score") or 0),
        },
        "video": {
            "duration": video.get("duration") or ffprobe.get("duration") or 0,
            "width": video.get("width") or ffprobe.get("width") or 0,
            "height": video.get("height") or ffprobe.get("height") or 0,
            "fps": video.get("fps") or ffprobe.get("fps") or 0,
            "bitrate": video.get("bitrate") or ffprobe.get("bitrate") or 0,
            "file_size": video.get("file_size") or ffprobe.get("file_size") or 0,
        },
        "analysis_summary": (analysis_result or {}).get("summary", ""),
        "rerun_compliance": (analysis_result or {}).get("rerun_compliance", {}),
        "quality_calibration": quality_calibration,
        "case_diagnosis": case_diagnosis,
        "rerun_strategy": rerun_strategy,
        "recommendations": quality_calibration.get("recommendations", []),
        "quality_acceptance": {
            "verdict": quality_acceptance.get("verdict", "pending"),
            "score": str(quality_acceptance.get("score") or "").strip(),
            "summary": str(quality_acceptance.get("summary") or "").strip(),
            "checks": quality_acceptance.get("checks", {}),
            "notes": str(quality_acceptance.get("notes") or "").strip(),
            "next_actions": str(quality_acceptance.get("next_actions") or "").strip(),
        },
        "worksheet_review": {
            "score": worksheet_review.get("score", 0),
            "level": worksheet_review.get("level", ""),
            "label": worksheet_review.get("label", ""),
        },
        "case_files": {
            "quality_calibration_record": str(_quality_calibration_record_path(artifact)),
            "quality_acceptance": str(_quality_acceptance_path(artifact)),
            "analysis_result": str(_analysis_result_path(artifact)),
            "analysis_report": str(_analysis_report_path(artifact)),
        },
    }


def _write_quality_calibration_index(record: dict) -> Path:
    settings.calibration_dir.mkdir(parents=True, exist_ok=True)
    index_path = _quality_calibration_index_path()
    index = {"schema_version": 1, "updated_at": "", "records": []}
    if index_path.is_file():
        try:
            loaded = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                index.update(loaded)
        except json.JSONDecodeError:
            index = {"schema_version": 1, "updated_at": "", "records": []}
    records = index.get("records") if isinstance(index.get("records"), list) else []
    records = [
        item
        for item in records
        if isinstance(item, dict) and item.get("case_id") != record.get("case_id")
    ]
    records.append(record)
    records.sort(key=lambda item: str(item.get("recorded_at") or ""), reverse=True)
    index["schema_version"] = 1
    index["updated_at"] = datetime.now(timezone.utc).isoformat()
    index["records"] = records
    _write_json_file(str(index_path), index)
    return index_path


def _load_quality_calibration_index() -> dict:
    index_path = _quality_calibration_index_path()
    if not index_path.is_file():
        return {"schema_version": 1, "updated_at": "", "records": []}
    try:
        loaded = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"schema_version": 1, "updated_at": "", "records": []}
    if not isinstance(loaded, dict):
        return {"schema_version": 1, "updated_at": "", "records": []}
    records = loaded.get("records") if isinstance(loaded.get("records"), list) else []
    return {
        "schema_version": loaded.get("schema_version", 1),
        "updated_at": loaded.get("updated_at", ""),
        "records": [record for record in records if isinstance(record, dict)],
    }


def _rerun_evidence_completion_counts(required_evidence: list[dict]) -> dict:
    missing_statuses = {"missing", "provider_missing", "pending", "disabled", "not_configured"}
    ready_statuses = {"success", "no_speech", "no_text"}
    total = 0
    ready = 0
    missing = 0
    for item in required_evidence:
        if not isinstance(item, dict):
            continue
        total += 1
        status = str(item.get("status") or "").strip()
        if status in missing_statuses or status not in ready_statuses:
            missing += 1
        else:
            ready += 1
    return {"total": total, "ready": ready, "missing": missing}


def _quality_calibration_summary(records: list[dict]) -> dict:
    by_status: dict[str, int] = {}
    by_diagnosis_status: dict[str, int] = {}
    by_verdict: dict[str, int] = {}
    by_category: dict[str, int] = {}
    evidence_completion = {
        "with_required_evidence": 0,
        "complete_records": 0,
        "missing_records": 0,
        "ready_items": 0,
        "missing_items": 0,
        "total_items": 0,
    }
    for record in records:
        calibration = record.get("quality_calibration") if isinstance(record.get("quality_calibration"), dict) else {}
        diagnosis = record.get("case_diagnosis") if isinstance(record.get("case_diagnosis"), dict) else {}
        acceptance = record.get("quality_acceptance") if isinstance(record.get("quality_acceptance"), dict) else {}
        rerun_strategy = record.get("rerun_strategy") if isinstance(record.get("rerun_strategy"), dict) else {}
        status = str(calibration.get("status") or "unknown")
        diagnosis_status = str(diagnosis.get("status") or "unknown")
        verdict = str(acceptance.get("verdict") or "pending")
        category = str(record.get("content_category_label") or record.get("content_category") or "未分类")
        by_status[status] = by_status.get(status, 0) + 1
        by_diagnosis_status[diagnosis_status] = by_diagnosis_status.get(diagnosis_status, 0) + 1
        by_verdict[verdict] = by_verdict.get(verdict, 0) + 1
        by_category[category] = by_category.get(category, 0) + 1
        required_evidence = (
            rerun_strategy.get("required_evidence")
            if isinstance(rerun_strategy.get("required_evidence"), list)
            else []
        )
        evidence_summary = (
            rerun_strategy.get("evidence_summary")
            if isinstance(rerun_strategy.get("evidence_summary"), dict)
            else {}
        )
        if required_evidence:
            evidence_completion["with_required_evidence"] += 1
            total_items = int(evidence_summary.get("total") or len(required_evidence))
            ready_items = int(evidence_summary.get("ready") or 0)
            missing_items = int(evidence_summary.get("missing") or 0)
            if not evidence_summary:
                fallback = _rerun_evidence_completion_counts(required_evidence)
                total_items = int(fallback.get("total") or 0)
                ready_items = int(fallback.get("ready") or 0)
                missing_items = int(fallback.get("missing") or 0)
            evidence_completion["total_items"] += total_items
            evidence_completion["ready_items"] += ready_items
            evidence_completion["missing_items"] += missing_items
            if missing_items:
                evidence_completion["missing_records"] += 1
            else:
                evidence_completion["complete_records"] += 1
    return {
        "total": len(records),
        "by_status": by_status,
        "by_diagnosis_status": by_diagnosis_status,
        "by_verdict": by_verdict,
        "by_category": by_category,
        "evidence_completion": evidence_completion,
    }


def _increment_issue(counter: dict[str, dict], key: str, label: str, source: str, example: str = "") -> None:
    key = str(key or label or "").strip()
    label = str(label or key or "").strip()
    if not key and not label:
        return
    item = counter.setdefault(
        key or label,
        {
            "id": key or label,
            "label": label or key,
            "source": source,
            "count": 0,
            "examples": [],
        },
    )
    item["count"] += 1
    if example and len(item["examples"]) < 3:
        item["examples"].append(example)


def _top_issues(counter: dict[str, dict], limit: int = 8) -> list[dict]:
    return sorted(counter.values(), key=lambda item: (-int(item.get("count") or 0), str(item.get("label") or "")))[:limit]


def _quality_calibration_insights(records: list[dict]) -> dict:
    ai_gaps: dict[str, dict] = {}
    human_blockers: dict[str, dict] = {}
    diagnosis_blockers: dict[str, dict] = {}
    diagnosis_actions: dict[str, dict] = {}
    rerun_evidence_gaps: dict[str, dict] = {}
    rerun_compliance_failures: dict[str, dict] = {}
    next_actions: dict[str, dict] = {}
    readiness_gaps: dict[str, dict] = {}
    for record in records:
        title = str(record.get("title") or record.get("case_id") or "")
        calibration = record.get("quality_calibration") if isinstance(record.get("quality_calibration"), dict) else {}
        diagnosis = record.get("case_diagnosis") if isinstance(record.get("case_diagnosis"), dict) else {}
        rerun_strategy = record.get("rerun_strategy") if isinstance(record.get("rerun_strategy"), dict) else {}
        rerun_compliance = (
            record.get("rerun_compliance") if isinstance(record.get("rerun_compliance"), dict) else {}
        )
        ai_quality = calibration.get("ai_quality") if isinstance(calibration.get("ai_quality"), dict) else {}
        human_acceptance = calibration.get("human_acceptance") if isinstance(calibration.get("human_acceptance"), dict) else {}
        readiness = calibration.get("readiness") if isinstance(calibration.get("readiness"), dict) else {}
        for gap in ai_quality.get("gaps") or []:
            if not isinstance(gap, dict):
                continue
            _increment_issue(
                ai_gaps,
                str(gap.get("id") or gap.get("label") or ""),
                str(gap.get("label") or gap.get("id") or ""),
                "ai_quality",
                title,
            )
        for blocker in human_acceptance.get("blockers") or []:
            if not isinstance(blocker, dict):
                continue
            _increment_issue(
                human_blockers,
                str(blocker.get("id") or blocker.get("label") or ""),
                str(blocker.get("label") or blocker.get("id") or ""),
                "human_acceptance",
                title,
            )
        for gap in readiness.get("critical_gaps") or []:
            if not isinstance(gap, dict):
                continue
            _increment_issue(
                readiness_gaps,
                str(gap.get("id") or gap.get("label") or ""),
                str(gap.get("label") or gap.get("id") or ""),
                "readiness",
                title,
            )
        for blocker in diagnosis.get("blockers") or []:
            if not isinstance(blocker, dict):
                continue
            _increment_issue(
                diagnosis_blockers,
                str(blocker.get("source") or blocker.get("label") or ""),
                str(blocker.get("label") or blocker.get("source") or ""),
                "case_diagnosis",
                title,
            )
        for action in diagnosis.get("primary_actions") or []:
            if not isinstance(action, dict):
                continue
            label = str(action.get("label") or action.get("description") or "").strip()
            _increment_issue(
                diagnosis_actions,
                label,
                label,
                "diagnosis_action",
                title,
            )
        for evidence in rerun_strategy.get("required_evidence") or []:
            if not isinstance(evidence, dict):
                continue
            if str(evidence.get("status") or "") not in {"missing", "provider_missing", "pending", "disabled", "not_configured"}:
                continue
            _increment_issue(
                rerun_evidence_gaps,
                str(evidence.get("id") or evidence.get("label") or ""),
                str(evidence.get("label") or evidence.get("id") or ""),
                "rerun_strategy",
                title,
            )
        for check in rerun_compliance.get("checks") or []:
            if not isinstance(check, dict) or check.get("passed") is not False:
                continue
            _increment_issue(
                rerun_compliance_failures,
                str(check.get("id") or check.get("label") or ""),
                str(check.get("label") or check.get("id") or ""),
                "rerun_compliance",
                title,
            )
        for action in calibration.get("next_actions") or []:
            if not isinstance(action, dict):
                continue
            label = str(action.get("label") or action.get("description") or "").strip()
            _increment_issue(
                next_actions,
                label,
                label,
                "next_action",
                title,
            )
    return {
        "top_ai_gaps": _top_issues(ai_gaps),
        "top_human_blockers": _top_issues(human_blockers),
        "top_diagnosis_blockers": _top_issues(diagnosis_blockers),
        "top_readiness_gaps": _top_issues(readiness_gaps),
        "top_diagnosis_actions": _top_issues(diagnosis_actions),
        "top_rerun_evidence_gaps": _top_issues(rerun_evidence_gaps),
        "top_rerun_compliance_failures": _top_issues(rerun_compliance_failures),
        "top_next_actions": _top_issues(next_actions),
    }


def _issue_id_set(*groups: list[dict]) -> set[str]:
    values = set()
    for group in groups:
        for item in group or []:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "").strip()
            label = str(item.get("label") or "").strip()
            if item_id:
                values.add(item_id)
            if label:
                values.add(label)
    return values


def _add_recommendation(
    recommendations: list[dict],
    recommendation_id: str,
    label: str,
    priority: int,
    reason: str,
    action: str,
    source_issue_ids: list[str],
    action_label: str = "",
    action_target: str = "",
    action_mode: str = "focus",
) -> None:
    if any(item.get("id") == recommendation_id for item in recommendations):
        return
    recommendations.append(
        {
            "id": recommendation_id,
            "label": label,
            "priority": priority,
            "reason": reason,
            "action": action,
            "source_issue_ids": source_issue_ids,
            "action_label": action_label,
            "action_target": action_target,
            "action_mode": _normalize_action_mode(action_mode),
        }
    )


def _quality_calibration_recommendations(insights: dict) -> list[dict]:
    ai_gaps = insights.get("top_ai_gaps") if isinstance(insights.get("top_ai_gaps"), list) else []
    human_blockers = (
        insights.get("top_human_blockers") if isinstance(insights.get("top_human_blockers"), list) else []
    )
    readiness_gaps = (
        insights.get("top_readiness_gaps") if isinstance(insights.get("top_readiness_gaps"), list) else []
    )
    rerun_evidence_gaps = (
        insights.get("top_rerun_evidence_gaps")
        if isinstance(insights.get("top_rerun_evidence_gaps"), list)
        else []
    )
    rerun_compliance_failures = (
        insights.get("top_rerun_compliance_failures")
        if isinstance(insights.get("top_rerun_compliance_failures"), list)
        else []
    )
    issue_ids = _issue_id_set(ai_gaps, human_blockers, readiness_gaps, rerun_evidence_gaps, rerun_compliance_failures)
    recommendations: list[dict] = []

    if any(str(issue_id).startswith("required_evidence:") for issue_id in issue_ids):
        _add_recommendation(
            recommendations,
            "enforce_rerun_required_evidence",
            "先兑现重跑必需证据",
            92,
            "校准样本显示 AI 重跑后仍未正确使用或说明必需证据。",
            "重跑后必须检查 rerun_compliance：必需证据已就绪就进入对应模块，仍缺失就写入 evidence_gaps、risks 和 next_actions。",
            ["required_evidence"],
            "查看合规",
            "#auto-analysis-summary",
        )
    if any(str(issue_id).startswith("fix_target:") for issue_id in issue_ids):
        _add_recommendation(
            recommendations,
            "enforce_rerun_fix_targets",
            "逐项回应人工修正目标",
            91,
            "校准样本显示 AI 没有真正回应人工验收指出的问题。",
            "每次带反馈重跑后，逐项核对 rerun_compliance.checks；未通过的 fix_target 必须改写对应模块，而不是只重新生成泛化报告。",
            ["fix_target"],
            "填写验收",
            "#quality-acceptance-verdict",
        )
    if {"evidence_is_sufficient", "evidence_gaps", "claim_traceability"} & issue_ids:
        _add_recommendation(
            recommendations,
            "tighten_evidence_gate",
            "收紧证据闸门",
            90,
            "样本反复出现证据不足或结论无法追溯。",
            "要求 summary、可复刻点和分镜都必须引用视觉、ASR、OCR、评论或人工工作表证据；证据不足时降级为待复核。",
            ["evidence_is_sufficient", "evidence_gaps", "claim_traceability"],
            "重新拆解",
            "#run-auto-analysis-button",
            "click",
        )
    if {"enrichment_usage"} & issue_ids:
        _add_recommendation(
            recommendations,
            "enforce_enrichment_coverage",
            "核对富化证据是否真正使用",
            88,
            "样本显示 ASR、OCR 或评论可用，但报告没有形成对应拆解，或输出了缺少证据的洞察。",
            "重跑前先查看 enrichment_coverage：可用未使用、有证据无洞察、有洞察无证据都必须进入质量缺口和人工复核。",
            ["enrichment_usage"],
            "重新拆解",
            "#run-auto-analysis-button",
            "click",
        )
    if {"shot_table_is_actionable", "shot_table_traceability", "replication"} & issue_ids:
        _add_recommendation(
            recommendations,
            "tighten_shot_table_gate",
            "收紧分镜表闸门",
            85,
            "人工验收或 AI 自检指出分镜不可执行、凭空扩展或缺少来源。",
            "分镜表每一行必须包含时间、画面/动作/字幕/目的中的至少两项，并能追溯到关键帧、timeline 或人工备注。",
            ["shot_table_is_actionable", "shot_table_traceability", "replication"],
            "填写验收",
            "#quality-acceptance-verdict",
        )
    if {"time_bounds"} & issue_ids:
        _add_recommendation(
            recommendations,
            "enforce_source_time_bounds",
            "锁定原片时间边界",
            84,
            "样本中的前 3 秒、时间线或分镜表出现超出原视频时长的时间点。",
            "AI 拆解必须以 ffprobe/analysis_input.video.duration 为硬边界；超出原片时长的创意扩展只能放入 risks 或 next_actions，不能写进原片 timeline 或 shot_table。",
            ["time_bounds"],
            "重新拆解",
            "#run-auto-analysis-button",
            "click",
        )
    if {"content_ratio_balance", "structure_depth"} & issue_ids:
        _add_recommendation(
            recommendations,
            "tighten_content_ratio_gate",
            "校准内容占比结构",
            82,
            "样本中的内容占比缺少完整结构、比例总和不接近 100%，或比例缺少依据。",
            "content_ratio 应输出 2-5 个结构段，每项包含 name、percent、reason，percent 总和约 100%；无法量化时应写入 risks 或 next_actions 等待人工复核。",
            ["content_ratio_balance", "structure_depth"],
            "重新拆解",
            "#run-auto-analysis-button",
            "click",
        )
    if {"category_alignment"} & issue_ids:
        _add_recommendation(
            recommendations,
            "enforce_category_specific_lens",
            "收紧内容类型拆解",
            81,
            "样本的内容占比或拆解维度没有贴合当前内容类型，容易把教程、美拍、鸡汤等都写成通用模板。",
            "每次拆解必须先确认 content_category，再让 content_ratio 至少覆盖两个该类型核心维度；类型不确定时先人工切换分类后重跑。",
            ["category_alignment"],
            "调整类型",
            "#analysis-category-select",
            "focus",
        )
    if {"engagement_data", "metrics"} & issue_ids:
        _add_recommendation(
            recommendations,
            "complete_engagement_metrics",
            "先补互动指标边界",
            81,
            "样本缺少点赞、评论或分享数据，AI 只能判断内容结构，不能判断真实爆款强度。",
            "先补作品链接返回的互动数据，或记录 metrics/snapshots.jsonl 指标快照；没有指标时报告必须把爆款强度判断降级为待复核。",
            ["engagement_data", "metrics"],
            "记录指标",
            "#metric-snapshot-button",
            "click",
        )
    if {"copyable_points_are_useful", "copyable_traceability"} & issue_ids:
        _add_recommendation(
            recommendations,
            "tighten_copyable_points_gate",
            "收紧可复刻点闸门",
            80,
            "样本中的可复刻点不够具体，或无法说明来自哪个证据。",
            "可复刻点必须写成可执行动作，并附来源：钩子、视觉、文案、口播、OCR、评论或人工验收。",
            ["copyable_points_are_useful", "copyable_traceability"],
            "填写验收",
            "#quality-acceptance-verdict",
        )
    if {"publish_package_is_usable", "publishing"} & issue_ids:
        _add_recommendation(
            recommendations,
            "tighten_publish_package_gate",
            "收紧发布包闸门",
            75,
            "发布标题、文案、标签或置顶评论不可直接使用。",
            "发布包不能只有标题，必须同时提供 caption、hashtags 或 pinned_comment，并说明适合复刻的理由。",
            ["publish_package_is_usable", "publishing"],
            "填写验收",
            "#quality-acceptance-verdict",
        )
    if {"speech_asr", "asr"} & issue_ids:
        _add_recommendation(
            recommendations,
            "complete_asr_before_rerun",
            "先补 ASR 再重跑",
            70,
            "准备度或重跑策略显示口播/语音信息不足。",
            "有口播的视频先运行 ASR，生成 transcript.json/txt/srt 后再重新 AI 拆解。",
            ["speech_asr", "asr"],
            "运行 ASR",
            "#asr-placeholder-button",
            "click",
        )
    if {"screen_ocr", "ocr"} & issue_ids:
        _add_recommendation(
            recommendations,
            "complete_ocr_before_rerun",
            "先补 OCR 再重跑",
            70,
            "准备度或重跑策略显示封面字、字幕或画面文字不足。",
            "有字幕、封面字或教程画面的视频先运行 OCR，把画面文字补进 analysis_enrichment。",
            ["screen_ocr", "ocr"],
            "运行 OCR",
            "#ocr-placeholder-button",
            "click",
        )
    if {"comments", "audience"} & issue_ids:
        _add_recommendation(
            recommendations,
            "import_comments_before_rerun",
            "先导入评论再重跑",
            68,
            "样本缺少评论证据，难以判断用户需求和互动钩子。",
            "至少导入高赞评论和典型评论，再让 AI 判断观众需求、评论触发和可复刻互动设计。",
            ["comments", "audience"],
            "导入评论",
            "#comments-import-text",
        )
    if {"summary_matches_video", "summary"} & issue_ids:
        _add_recommendation(
            recommendations,
            "tighten_summary_gate",
            "收紧总结闸门",
            65,
            "人工验收指出总结不贴合视频，或 AI 自检发现总结泛化。",
            "summary 必须包含具体画面/文本/评论证据，不允许只写“值得学习”“适合复刻”等泛化判断。",
            ["summary_matches_video", "summary"],
            "填写验收",
            "#quality-acceptance-verdict",
        )

    return sorted(
        recommendations,
        key=lambda item: (-int(item.get("priority") or 0), str(item.get("label") or "")),
    )


def _markdown_issue_list(items: list[dict], empty_text: str = "暂无") -> list[str]:
    if not items:
        return [f"- {empty_text}"]
    lines = []
    for item in items:
        label = item.get("label") or item.get("id") or "未命名问题"
        item_id = str(item.get("id") or "").strip()
        source = str(item.get("source") or "").strip()
        count = item.get("count", 0)
        meta = []
        if item_id and item_id != label:
            meta.append(f"id: {item_id}")
        if source:
            meta.append(f"source: {source}")
        meta_text = f"（{'，'.join(meta)}）" if meta else ""
        lines.append(f"- {label}{meta_text}：{count} 次")
        examples = item.get("examples") if isinstance(item.get("examples"), list) else []
        if examples:
            lines.append(f"  - 示例：{' / '.join(str(example) for example in examples[:3])}")
    return lines


def _format_rerun_evidence_summary(items: list[dict]) -> str:
    if not items:
        return "无证据要求"
    parts = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("id") or "证据").strip()
        status = str(item.get("status") or "pending").strip()
        meta = []
        if item.get("char_count") not in {None, ""}:
            meta.append(f"文本 {item.get('char_count')} 字")
        if item.get("segment_count") not in {None, ""}:
            meta.append(f"ASR {item.get('segment_count')} 段")
        if item.get("count") not in {None, ""}:
            meta.append(f"评论 {item.get('count')} 条")
        sources = item.get("sources") if isinstance(item.get("sources"), list) else []
        if sources:
            meta.append(f"来源 {'/'.join(str(source) for source in sources)}")
        excerpt = str(item.get("excerpt") or "").strip()
        detail = f"{label}:{status}"
        if meta:
            detail += f"（{'，'.join(meta)}）"
        if excerpt:
            detail += f"「{excerpt}」"
        parts.append(detail)
    return "；".join(parts) or "无证据要求"


def _format_rerun_evidence_completion(rerun_strategy: dict) -> str:
    summary = rerun_strategy.get("evidence_summary") if isinstance(rerun_strategy.get("evidence_summary"), dict) else {}
    total = int(summary.get("total") or 0)
    if not total:
        return "暂无必须核对的证据"
    return f"已就绪 {int(summary.get('ready') or 0)} / 缺失 {int(summary.get('missing') or 0)} / 总计 {total}"


def _format_summary_evidence_completion(summary: dict) -> str:
    evidence = (
        summary.get("evidence_completion")
        if isinstance(summary.get("evidence_completion"), dict)
        else {}
    )
    if not int(evidence.get("with_required_evidence") or 0):
        return "暂无重跑证据样本"
    return (
        f"样本 {int(evidence.get('with_required_evidence') or 0)}，"
        f"已齐 {int(evidence.get('complete_records') or 0)}，"
        f"仍缺 {int(evidence.get('missing_records') or 0)}，"
        f"证据项 {int(evidence.get('ready_items') or 0)}/{int(evidence.get('total_items') or 0)}"
    )


def _render_quality_calibration_report(
    records: list[dict],
    summary: dict,
    insights: dict,
    recommendations: list[dict],
    filters: dict,
    updated_at: str = "",
) -> str:
    lines = [
        "# 单条作品拆解质量校准报告",
        "",
        f"- 生成时间：{datetime.now(timezone.utc).isoformat()}",
        f"- 索引更新时间：{updated_at or '无'}",
        f"- 当前样本数：{summary.get('total', 0)}",
        f"- 筛选条件：status={filters.get('status') or '全部'}，diagnosis_status={filters.get('diagnosis_status') or '全部'}，verdict={filters.get('verdict') or '全部'}，category={filters.get('category') or '全部'}，search={filters.get('search') or '无'}",
        "",
        "## 1. 分布概览",
        "",
        f"- 校准状态：{summary.get('by_status') or {}}",
        f"- 诊断状态：{summary.get('by_diagnosis_status') or {}}",
        f"- 人工结论：{summary.get('by_verdict') or {}}",
        f"- 内容类型：{summary.get('by_category') or {}}",
        f"- 证据完成度：{_format_summary_evidence_completion(summary)}",
        "",
        "## 2. 常见质量问题",
        "",
        "### AI 自检缺口",
        "",
        *_markdown_issue_list(insights.get("top_ai_gaps") or []),
        "",
        "### 人工阻塞项",
        "",
        *_markdown_issue_list(insights.get("top_human_blockers") or []),
        "",
        "### 顶部诊断阻塞",
        "",
        *_markdown_issue_list(insights.get("top_diagnosis_blockers") or []),
        "",
        "### 准备度缺口",
        "",
        *_markdown_issue_list(insights.get("top_readiness_gaps") or []),
        "",
        "### 重跑仍缺证据",
        "",
        *_markdown_issue_list(insights.get("top_rerun_evidence_gaps") or []),
        "",
        "### 重跑合规失败",
        "",
        *_markdown_issue_list(insights.get("top_rerun_compliance_failures") or []),
        "",
        "### 下一步动作",
        "",
        *_markdown_issue_list(insights.get("top_next_actions") or []),
        "",
        "### 诊断推荐动作",
        "",
        *_markdown_issue_list(insights.get("top_diagnosis_actions") or []),
        "",
        "## 3. 规则改进建议",
        "",
    ]
    if recommendations:
        for item in recommendations:
            source_ids = item.get("source_issue_ids") if isinstance(item.get("source_issue_ids"), list) else []
            action_label = str(item.get("action_label") or "").strip()
            action_target = str(item.get("action_target") or "").strip()
            lines.extend(
                [
                    f"- P{item.get('priority', 0)} · {item.get('label', '')}",
                    f"  - 原因：{item.get('reason', '')}",
                    f"  - 动作：{item.get('action', '')}",
                ]
            )
            if source_ids:
                lines.append(f"  - 触发项：{' / '.join(str(source_id) for source_id in source_ids)}")
            if action_label or action_target:
                lines.append(f"  - 页面动作：{action_label or '查看'} -> {action_target or '无'}")
    else:
        lines.append("- 暂无明确规则改进建议。")
    lines.extend(
        [
            "",
            "## 4. 重点样本",
            "",
        ]
    )
    if not records:
        lines.append("- 暂无样本。")
    for record in records[:20]:
        calibration = record.get("quality_calibration") if isinstance(record.get("quality_calibration"), dict) else {}
        diagnosis = record.get("case_diagnosis") if isinstance(record.get("case_diagnosis"), dict) else {}
        rerun_strategy = record.get("rerun_strategy") if isinstance(record.get("rerun_strategy"), dict) else {}
        rerun_compliance = (
            record.get("rerun_compliance") if isinstance(record.get("rerun_compliance"), dict) else {}
        )
        ai_quality = calibration.get("ai_quality") if isinstance(calibration.get("ai_quality"), dict) else {}
        acceptance = record.get("quality_acceptance") if isinstance(record.get("quality_acceptance"), dict) else {}
        actions = calibration.get("next_actions") if isinstance(calibration.get("next_actions"), list) else []
        action_text = "；".join(
            str(action.get("description") or action.get("label") or "")
            for action in actions[:3]
            if isinstance(action, dict)
        )
        lines.extend(
            [
                f"### {record.get('title') or record.get('case_id') or '未命名样本'}",
                "",
                f"- case_id：{record.get('case_id', '')}",
                f"- 内容类型：{record.get('content_category_label') or record.get('content_category') or ''}",
                f"- 校准状态：{calibration.get('label') or calibration.get('status') or ''}",
                f"- 诊断状态：{diagnosis.get('label') or diagnosis.get('status') or ''}",
                f"- AI 分数：{ai_quality.get('score', 0)} / {ai_quality.get('max_score', 100)}",
                f"- 人工结论：{acceptance.get('verdict', 'pending')}，人工评分：{acceptance.get('score', '')}",
                f"- 人工意见：{acceptance.get('summary') or '暂无'}",
                f"- 下一步：{action_text or '暂无'}",
                f"- 证据完成度：{_format_rerun_evidence_completion(rerun_strategy)}",
                f"- 重跑合规：{rerun_compliance.get('status', 'not_required')}，阻塞 {int(rerun_compliance.get('blocking_count') or 0)} 项",
                f"- 重跑证据：{_format_rerun_evidence_summary(rerun_strategy.get('required_evidence') or [])}",
                "",
            ]
        )
    lines.extend(
        [
            "## 5. 使用建议",
            "",
            "- 优先处理出现次数最多的人工阻塞项，这通常代表 AI 输出最不符合真实判断的部分。",
            "- 如果准备度缺口集中在 ASR/OCR/评论，先补富化数据，再重跑 AI 拆解。",
            "- 如果 AI 自检缺口集中在分镜、复刻点或发布包，优先收紧 prompt 和质量闸门。",
            "- 通过样本可作为正样本沉淀；需要重跑样本可作为反例用于调规则。",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _filter_quality_calibration_records(
    records: list[dict],
    status: str = "",
    diagnosis_status: str = "",
    verdict: str = "",
    category: str = "",
    search: str = "",
) -> list[dict]:
    status = status.strip()
    diagnosis_status = diagnosis_status.strip()
    verdict = verdict.strip()
    category = category.strip().lower()
    search = search.strip().lower()
    filtered = []
    for record in records:
        calibration = record.get("quality_calibration") if isinstance(record.get("quality_calibration"), dict) else {}
        diagnosis = record.get("case_diagnosis") if isinstance(record.get("case_diagnosis"), dict) else {}
        acceptance = record.get("quality_acceptance") if isinstance(record.get("quality_acceptance"), dict) else {}
        record_status = str(calibration.get("status") or "")
        record_diagnosis_status = str(diagnosis.get("status") or "")
        record_verdict = str(acceptance.get("verdict") or "")
        record_category = str(record.get("content_category") or "").lower()
        record_category_label = str(record.get("content_category_label") or "").lower()
        haystack = " ".join(
            [
                str(record.get("case_id") or ""),
                str(record.get("aweme_id") or ""),
                str(record.get("title") or ""),
                str(record.get("author") or ""),
                str(record.get("source_url") or ""),
                str(record.get("analysis_summary") or ""),
                str(acceptance.get("summary") or ""),
            ]
        ).lower()
        if status and record_status != status:
            continue
        if diagnosis_status and record_diagnosis_status != diagnosis_status:
            continue
        if verdict and record_verdict != verdict:
            continue
        if category and category not in {record_category, record_category_label}:
            continue
        if search and search not in haystack:
            continue
        filtered.append(record)
    return filtered


def _save_quality_calibration_record(artifact: CaseArtifact) -> dict:
    metadata, ffprobe, analysis_input, _prompt = _load_case_parts(artifact)
    worksheet, _analysis_brief = _load_or_create_worksheet(artifact, metadata, ffprobe, analysis_input)
    worksheet_review = worksheet_quality_review(worksheet)
    analysis_result, _analysis_report = existing_auto_analysis(artifact)
    quality_acceptance = _load_or_create_quality_acceptance(artifact, analysis_result)
    keyframes_dir = Path(artifact.keyframes_dir)
    keyframe_files = []
    if keyframes_dir.is_dir():
        keyframe_files = sorted(path.name for path in keyframes_dir.glob("frame_*.jpg") if path.is_file())
    enrichment = enrichment_payload(artifact)
    analysis_readiness = _analysis_readiness_payload(
        artifact,
        keyframe_files,
        analysis_input,
        enrichment,
        analysis_result,
        worksheet_review,
    )
    manual_review_context = manual_review_context_for_case(artifact)
    rerun_strategy = (
        manual_review_context.get("rerun_strategy")
        if isinstance(manual_review_context.get("rerun_strategy"), dict)
        else {}
    )
    quality_calibration = _quality_calibration_payload(
        analysis_result,
        quality_acceptance,
        analysis_readiness,
        worksheet_review,
        rerun_strategy,
    )
    case_diagnosis = _case_diagnosis_payload(
        analysis_result,
        analysis_readiness,
        quality_calibration,
    )
    record = _quality_calibration_record_payload(
        artifact,
        metadata,
        ffprobe,
        analysis_input,
        analysis_result,
        quality_acceptance,
        worksheet_review,
        analysis_readiness,
        quality_calibration,
        case_diagnosis,
        rerun_strategy,
    )
    record_path = _quality_calibration_record_path(artifact)
    _write_json_file(str(record_path), record)
    index_path = _write_quality_calibration_index(record)
    return {"record": record, "record_path": str(record_path), "index_path": str(index_path)}


def _file_ready(path: str) -> bool:
    return bool(path) and Path(path).is_file()


def _positive_status(status: str) -> bool:
    return status in {"success", "no_speech", "no_text"}


def _asr_readiness_message(status: str, full_text: str) -> str:
    if full_text:
        return "ASR 已提供口播文本。"
    if status == "no_speech":
        return "ASR 已检测，未发现可转写语音；可按画面、音乐和动作拆解。"
    if status == "success":
        return "ASR 已完成，但转写文本为空，请复核音频。"
    return "尚未检测口播；有口播的视频建议运行 ASR。"


def _ocr_readiness_message(status: str, text: str) -> str:
    if text:
        return "OCR 已提供封面字、字幕或画面文字。"
    if status == "no_text":
        return "OCR 已检测，未发现封面字、字幕或画面文字；可按视觉动作和构图拆解。"
    if status == "success":
        return "OCR 已完成，但识别文本为空，请复核关键帧。"
    return "尚未检测画面文字；有字幕、封面字或教学文字的视频建议运行 OCR。"


def _analysis_readiness_payload(
    artifact: CaseArtifact,
    keyframe_files: list[str],
    analysis_input: dict,
    enrichment: dict,
    analysis_result: dict | None,
    worksheet_review: dict | None = None,
) -> dict:
    manifest = enrichment.get("manifest") or {}
    statuses = manifest.get("statuses") or {}
    analysis_enrichment = analysis_input.get("analysis_enrichment") or {}
    asr = analysis_enrichment.get("asr") or {}
    ocr = analysis_enrichment.get("ocr") or {}
    comments = analysis_enrichment.get("comments") or {}
    metrics = analysis_enrichment.get("metrics") or {}
    asr_status = str(asr.get("status") or statuses.get("asr") or "pending")
    ocr_status = str(ocr.get("status") or statuses.get("ocr") or "pending")
    ocr_text = " / ".join(
        item
        for item in (ocr.get("frame_text", ""), ocr.get("subtitle_text", ""), ocr.get("cover_text", ""))
        if item
    )
    worksheet_review = worksheet_review or {}
    worksheet_score = int(worksheet_review.get("score") or 0)
    worksheet_ready = worksheet_score >= 70
    analysis_output_ready = bool(analysis_result) or worksheet_ready
    if analysis_result:
        analysis_output_status = "ai_report"
        analysis_output_message = "AI 自动拆解报告已生成。"
        analysis_output_action = "可继续人工复核工作表，或重新 AI 自动拆解。"
        analysis_output_label = "重新 AI 拆解"
        analysis_output_target = "#run-auto-analysis-button"
    elif worksheet_ready:
        analysis_output_status = "manual_worksheet"
        analysis_output_message = f"人工工作表已达到「{worksheet_review.get('label') or '可用'}」，可作为当前拆解产出。"
        analysis_output_action = "如需更完整报告，可配置 LLM 后运行 AI 自动拆解。"
        analysis_output_label = "开始 AI 拆解"
        analysis_output_target = "#run-auto-analysis-button"
    else:
        analysis_output_status = worksheet_review.get("level") or "pending"
        analysis_output_message = "尚未生成 AI 报告，人工工作表也未达到可用完成度。"
        analysis_output_action = "先完善人工工作表，或配置 LLM 后运行自动拆解。"
        analysis_output_label = "完善工作表"
        analysis_output_target = "#worksheet-summary"

    checks = [
        {
            "id": "base_package",
            "label": "基础素材包",
            "weight": 30,
            "ready": all(
                [
                    _file_ready(artifact.video_path),
                    _file_ready(artifact.metadata_path),
                    _file_ready(artifact.ffprobe_path),
                    _file_ready(artifact.contact_sheet_path),
                    _file_ready(artifact.analysis_input_path),
                    _file_ready(artifact.prompt_path),
                    bool(keyframe_files),
                ]
            ),
            "status": "success" if keyframe_files else "missing",
            "message": "视频、元数据、关键帧和 Prompt 已生成。",
            "action": "如果缺失，请重新生成素材包。",
            "action_label": "返回首页重新生成",
            "action_target": "/",
        },
        {
            "id": "analysis_lens",
            "label": "内容类型镜头",
            "weight": 10,
            "ready": bool(analysis_input.get("analysis_context")),
            "status": analysis_input.get("content_category") or "generic",
            "message": f"当前按「{analysis_input.get('content_category_label') or '通用短视频'}」拆解。",
            "action": "如果判断不准，请在页面切换内容类型。",
            "action_label": "切换内容类型",
            "action_target": "#analysis-category-select",
        },
        {
            "id": "speech_asr",
            "label": "语音/口播",
            "weight": 15,
            "ready": _positive_status(asr_status),
            "status": asr_status,
            "message": _asr_readiness_message(asr_status, str(asr.get("full_text") or "")),
            "action": "有口播的视频建议运行 ASR；无口播可接受 no_speech。",
            "action_label": "运行 ASR",
            "action_target": "#asr-placeholder-button",
        },
        {
            "id": "screen_ocr",
            "label": "画面文字/OCR",
            "weight": 15,
            "ready": _positive_status(ocr_status),
            "status": ocr_status,
            "message": _ocr_readiness_message(ocr_status, ocr_text),
            "action": "字幕、封面字或教学类视频建议运行 OCR。",
            "action_label": "运行 OCR",
            "action_target": "#ocr-placeholder-button",
        },
        {
            "id": "comments",
            "label": "评论反馈",
            "weight": 15,
            "ready": comments.get("status") == "success" and int(comments.get("total_comments") or 0) > 0,
            "status": comments.get("status") or statuses.get("comments") or "pending",
            "message": f"已导入 {int(comments.get('total_comments') or 0)} 条评论。",
            "action": "导入高赞评论或典型评论，可判断用户真实需求和互动钩子。",
            "action_label": "导入评论",
            "action_target": "#comments-import-text",
        },
        {
            "id": "metrics",
            "label": "指标快照",
            "weight": 5,
            "ready": metrics.get("status") == "success" or statuses.get("metrics") == "success",
            "status": metrics.get("status") or statuses.get("metrics") or "pending",
            "message": f"已有 {int(metrics.get('snapshot_count') or 0)} 次指标快照。",
            "action": "记录指标快照，后续可比较增长曲线。",
            "action_label": "记录快照",
            "action_target": "#metric-snapshot-button",
        },
        {
            "id": "analysis_output",
            "label": "拆解产出",
            "weight": 10,
            "ready": analysis_output_ready,
            "status": analysis_output_status,
            "message": analysis_output_message,
            "action": analysis_output_action,
            "action_label": analysis_output_label,
            "action_target": analysis_output_target,
        },
    ]

    score = sum(check["weight"] for check in checks if check["ready"])
    required_gaps = [check for check in checks if not check["ready"] and check["id"] in {"base_package", "analysis_lens"}]
    improvement_gaps = [check for check in checks if not check["ready"] and check["id"] not in {"base_package", "analysis_lens"}]
    critical_gap_ids = {"base_package", "analysis_lens", "speech_asr", "screen_ocr", "comments", "analysis_output"}
    critical_gaps = [check for check in checks if not check["ready"] and check["id"] in critical_gap_ids]
    if score >= 85 and not critical_gaps:
        level = "high"
        label = "拆解资料完整"
        summary = "这条素材已经具备比较完整的视觉、语音、评论和拆解产出。"
    elif score >= 65:
        level = "ready"
        label = "可开始分析"
        summary = "基础素材已经足够进入拆解，补齐富化数据会让结论更准。"
    elif score >= 40:
        level = "basic"
        label = "基础素材可用"
        summary = "可以先做人工观察或复制 prompt，但自动拆解会缺少上下文。"
    else:
        level = "low"
        label = "需要补齐基础数据"
        summary = "素材包信息不足，建议先重新生成或检查基础文件。"

    next_gaps = [] if level == "high" else required_gaps + improvement_gaps[:3]
    next_actions = [gap["action"] for gap in next_gaps]
    next_action_items = [
        {
            "label": gap.get("action_label", ""),
            "target": gap.get("action_target", ""),
            "description": gap.get("action", ""),
        }
        for gap in next_gaps
        if gap.get("action_target")
    ]
    return {
        "score": score,
        "max_score": 100,
        "level": level,
        "label": label,
        "summary": summary,
        "checks": checks,
        "critical_gaps": critical_gaps,
        "required_gaps": required_gaps,
        "improvement_gaps": improvement_gaps,
        "next_actions": next_actions,
        "next_action_items": next_action_items,
    }


def _primary_workflow_payload(artifact: CaseArtifact, analysis_result: dict | None, llm_settings: dict) -> dict:
    required_paths = {
        "video": artifact.video_path,
        "metadata": artifact.metadata_path,
        "ffprobe": artifact.ffprobe_path,
        "analysis_input": artifact.analysis_input_path,
        "prompt": artifact.prompt_path,
        "contact_sheet": artifact.contact_sheet_path,
        "keyframes_dir": artifact.keyframes_dir,
    }
    missing = [
        label
        for label, value in required_paths.items()
        if not value or not Path(value).exists()
    ]
    artifact_ready = not missing
    llm_configured = bool(llm_settings.get("configured"))
    if not artifact_ready:
        analysis_status = "artifact_incomplete"
        ai_status_label = "素材包未完整"
        next_action = "rebuild_case"
        next_action_label = "重新生成素材包"
        next_action_target = "/"
    elif analysis_result:
        analysis_status = "completed"
        ai_status_label = "AI 报告已生成"
        next_action = "view_report"
        next_action_label = "查看 AI 报告"
        next_action_target = "#auto-analysis-report"
    elif not llm_configured:
        analysis_status = "not_configured"
        ai_status_label = "AI 未配置"
        next_action = "copy_prompt"
        next_action_label = "复制 Prompt 手动分析"
        next_action_target = "#prompt-text"
    else:
        analysis_status = "not_analyzed"
        ai_status_label = "等待 AI 拆解"
        next_action = "run_ai_analysis"
        next_action_label = "开始 AI 自动拆解"
        next_action_target = "#run-auto-analysis-button"
    return {
        "artifact_ready": artifact_ready,
        "artifact_status_label": "素材包已生成" if artifact_ready else "素材包文件缺失",
        "missing_artifacts": missing,
        "llm_configured": llm_configured,
        "analysis_status": analysis_status,
        "ai_status_label": ai_status_label,
        "next_action": next_action,
        "next_action_label": next_action_label,
        "next_action_target": next_action_target,
    }


def _case_payload(artifact: CaseArtifact) -> dict:
    case_id = artifact.case_id
    metadata, ffprobe, analysis_input, prompt = _load_case_parts(artifact)
    worksheet, analysis_brief = _load_or_create_worksheet(artifact, metadata, ffprobe, analysis_input)
    analysis_result, analysis_report = existing_auto_analysis(artifact)
    quality_acceptance = _load_or_create_quality_acceptance(artifact, analysis_result)
    keyframes_dir = Path(artifact.keyframes_dir)
    keyframe_files = []
    if keyframes_dir.is_dir():
        keyframe_files = sorted(path.name for path in keyframes_dir.glob("frame_*.jpg") if path.is_file())
    enrichment = enrichment_payload(artifact)
    worksheet_review = worksheet_quality_review(worksheet)
    analysis_readiness = _analysis_readiness_payload(
        artifact,
        keyframe_files,
        analysis_input,
        enrichment,
        analysis_result,
        worksheet_review,
    )
    manual_review_context = manual_review_context_for_case(artifact)
    rerun_strategy = (
        manual_review_context.get("rerun_strategy")
        if isinstance(manual_review_context.get("rerun_strategy"), dict)
        else {}
    )
    quality_calibration = _quality_calibration_payload(
        analysis_result,
        quality_acceptance,
        analysis_readiness,
        worksheet_review,
        rerun_strategy,
    )
    case_diagnosis = _case_diagnosis_payload(
        analysis_result,
        analysis_readiness,
        quality_calibration,
    )
    llm_settings = llm_status_payload()
    primary_workflow = _primary_workflow_payload(artifact, analysis_result, llm_settings)
    rerun_plan = _build_rerun_plan(
        artifact,
        metadata,
        analysis_input,
        analysis_result,
        quality_acceptance,
        analysis_readiness,
        quality_calibration,
        case_diagnosis,
        rerun_strategy,
    )
    return {
        "case_id": case_id,
        "local_video_id": artifact.local_video_id,
        "status": artifact.status,
        "paths": {
            "video": artifact.video_path,
            "metadata": artifact.metadata_path,
            "qualities": artifact.qualities_path,
            "ffprobe": artifact.ffprobe_path,
            "analysis_input": artifact.analysis_input_path,
            "prompt": artifact.prompt_path,
            "worksheet": str(_worksheet_path(artifact)),
            "quality_acceptance": str(_quality_acceptance_path(artifact)),
            "quality_calibration_record": str(_quality_calibration_record_path(artifact)),
            "rerun_plan": str(_rerun_plan_path(artifact)),
            "rerun_plan_markdown": str(_rerun_plan_markdown_path(artifact)),
            "analysis_brief": str(_analysis_brief_path(artifact)),
            "analysis_result": str(_analysis_result_path(artifact)),
            "analysis_report": str(_analysis_report_path(artifact)),
            "contact_sheet": artifact.contact_sheet_path,
            "keyframes_dir": artifact.keyframes_dir,
        },
        "artifact_urls": {
            "contact_sheet": f"/api/cases/{case_id}/contact-sheet",
            "analysis_input": f"/api/cases/{case_id}/analysis-input",
            "rerun_plan": f"/api/cases/{case_id}/rerun-plan",
            "rerun_plan_markdown": f"/api/cases/{case_id}/rerun-plan.md",
            "keyframes": [
                {
                    "filename": filename,
                    "url": f"/api/cases/{case_id}/keyframes/{filename}",
                }
                for filename in keyframe_files
            ],
        },
        "artifact_descriptions": ARTIFACT_DESCRIPTIONS,
        "llm_settings": llm_settings,
        "primary_workflow": primary_workflow,
        "analysis_profiles": list_analysis_profiles(),
        "metadata": metadata,
        "qualities": _read_json_file(artifact.qualities_path),
        "ffprobe": ffprobe,
        "analysis_input": analysis_input,
        "worksheet": worksheet,
        "worksheet_review": worksheet_review,
        "quality_acceptance": quality_acceptance,
        "analysis_brief": analysis_brief,
        "analysis_result": analysis_result,
        "analysis_report": analysis_report,
        "manual_review_context": manual_review_context,
        "rerun_plan": rerun_plan,
        "prompt": prompt,
        "enrichment": enrichment,
        "analysis_readiness": analysis_readiness,
        "quality_calibration": quality_calibration,
        "case_diagnosis": case_diagnosis,
    }


@router.post("/build")
def build_case_sync(payload: BuildCaseRequest, db: Session = Depends(get_db)):
    try:
        artifact = build_case_from_local_video(db, payload.local_video_id)
        return {
            "ok": True,
            "case": {
                "case_id": artifact.case_id,
                "local_video_id": artifact.local_video_id,
                "video_path": artifact.video_path,
                "metadata_path": artifact.metadata_path,
                "analysis_input_path": artifact.analysis_input_path,
                "prompt_path": artifact.prompt_path,
                "contact_sheet_path": artifact.contact_sheet_path,
                "keyframes_dir": artifact.keyframes_dir,
                "status": artifact.status,
            },
        }
    except AppError as error:
        return error_response(error)


@router.get("/quality-calibration/records")
def list_quality_calibration_records(
    status: str = Query(default=""),
    diagnosis_status: str = Query(default=""),
    verdict: str = Query(default=""),
    category: str = Query(default=""),
    search: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
):
    index = _load_quality_calibration_index()
    records = index["records"]
    filtered = _filter_quality_calibration_records(
        records,
        status=status,
        diagnosis_status=diagnosis_status,
        verdict=verdict,
        category=category,
        search=search,
    )
    insights = _quality_calibration_insights(records)
    filtered_insights = _quality_calibration_insights(filtered)
    return {
        "ok": True,
        "updated_at": index.get("updated_at", ""),
        "summary": _quality_calibration_summary(records),
        "filtered_summary": _quality_calibration_summary(filtered),
        "insights": insights,
        "filtered_insights": filtered_insights,
        "recommendations": _quality_calibration_recommendations(insights),
        "filtered_recommendations": _quality_calibration_recommendations(filtered_insights),
        "filters": {
            "status": status,
            "diagnosis_status": diagnosis_status,
            "verdict": verdict,
            "category": category,
            "search": search,
            "limit": limit,
        },
        "records": filtered[:limit],
    }


@router.get("/quality-calibration/report")
def get_quality_calibration_report(
    status: str = Query(default=""),
    diagnosis_status: str = Query(default=""),
    verdict: str = Query(default=""),
    category: str = Query(default=""),
    search: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
):
    index = _load_quality_calibration_index()
    records = index["records"]
    filtered = _filter_quality_calibration_records(
        records,
        status=status,
        diagnosis_status=diagnosis_status,
        verdict=verdict,
        category=category,
        search=search,
    )[:limit]
    filters = {
        "status": status,
        "diagnosis_status": diagnosis_status,
        "verdict": verdict,
        "category": category,
        "search": search,
        "limit": limit,
    }
    summary = _quality_calibration_summary(filtered)
    insights = _quality_calibration_insights(filtered)
    recommendations = _quality_calibration_recommendations(insights)
    return {
        "ok": True,
        "updated_at": index.get("updated_at", ""),
        "filters": filters,
        "summary": summary,
        "insights": insights,
        "recommendations": recommendations,
        "report_markdown": _render_quality_calibration_report(
            filtered,
            summary,
            insights,
            recommendations,
            filters,
            updated_at=index.get("updated_at", ""),
        ),
    }


@router.get("/{case_id}")
def get_case(case_id: str, db: Session = Depends(get_db)):
    try:
        artifact = _case_or_error(db, case_id)
        return {"ok": True, "case": _case_payload(artifact)}
    except AppError as error:
        return error_response(error)


@router.get("/{case_id}/enrichment")
def get_case_enrichment(case_id: str, db: Session = Depends(get_db)):
    try:
        artifact = _case_or_error(db, case_id)
        return {"ok": True, "enrichment": enrichment_payload(artifact)}
    except AppError as error:
        return error_response(error)


@router.post("/{case_id}/archive/enrich")
def enrich_case_archive(case_id: str, db: Session = Depends(get_db)):
    try:
        artifact = _case_or_error(db, case_id)
        result = build_enrichment_archive(artifact)
        return {"ok": True, "enrichment": result}
    except AppError as error:
        return error_response(error)


@router.post("/{case_id}/comments/import")
def import_case_comments(
    case_id: str,
    payload: ImportCommentsRequest,
    db: Session = Depends(get_db),
):
    try:
        artifact = _case_or_error(db, case_id)
        result = import_comments(
            artifact,
            text=payload.text,
            comments=payload.comments,
            source=payload.source,
            permission_note=payload.permission_note,
        )
        return {"ok": True, "comments": result, "enrichment": enrichment_payload(artifact)}
    except AppError as error:
        return error_response(error)


@router.post("/{case_id}/metrics/snapshot")
def create_case_metric_snapshot(
    case_id: str,
    payload: MetricSnapshotRequest,
    db: Session = Depends(get_db),
):
    try:
        artifact = _case_or_error(db, case_id)
        snapshot = create_metrics_snapshot(
            artifact,
            capture_method=payload.capture_method,
            permission_note=payload.permission_note,
        )
        return {"ok": True, "snapshot": snapshot, "enrichment": enrichment_payload(artifact)}
    except AppError as error:
        return error_response(error)


@router.post("/{case_id}/asr")
def run_case_asr_placeholder(case_id: str, db: Session = Depends(get_db)):
    try:
        artifact = _case_or_error(db, case_id)
        result = run_case_asr(artifact)
        return {"ok": True, "asr": result, "enrichment": enrichment_payload(artifact)}
    except AppError as error:
        status_code = 501 if error.code == ErrorCode.ASR_PROVIDER_NOT_CONFIGURED else 400
        return error_response(error, status_code=status_code)


@router.post("/{case_id}/ocr")
def run_case_ocr_placeholder(case_id: str, db: Session = Depends(get_db)):
    try:
        artifact = _case_or_error(db, case_id)
        result = run_case_ocr(artifact)
        return {"ok": True, "ocr": result, "enrichment": enrichment_payload(artifact)}
    except AppError as error:
        status_code = 501 if error.code == ErrorCode.OCR_PROVIDER_NOT_CONFIGURED else 400
        return error_response(error, status_code=status_code)


@router.post("/{case_id}/analysis-category")
def update_case_analysis_category(
    case_id: str,
    payload: UpdateAnalysisCategoryRequest,
    db: Session = Depends(get_db),
):
    try:
        artifact = _case_or_error(db, case_id)
        _update_case_category(artifact, payload.category_id)
        return {"ok": True, "case": _case_payload(artifact)}
    except AppError as error:
        return error_response(error)


@router.post("/{case_id}/worksheet")
def update_case_worksheet(
    case_id: str,
    payload: UpdateWorksheetRequest,
    db: Session = Depends(get_db),
):
    try:
        artifact = _case_or_error(db, case_id)
        _update_case_worksheet(artifact, payload.worksheet)
        return {"ok": True, "case": _case_payload(artifact)}
    except AppError as error:
        return error_response(error)


@router.post("/{case_id}/quality-acceptance")
def update_case_quality_acceptance(
    case_id: str,
    payload: UpdateQualityAcceptanceRequest,
    db: Session = Depends(get_db),
):
    try:
        artifact = _case_or_error(db, case_id)
        analysis_result, _analysis_report = existing_auto_analysis(artifact)
        _update_quality_acceptance(artifact, payload.acceptance, analysis_result)
        return {"ok": True, "case": _case_payload(artifact)}
    except AppError as error:
        return error_response(error)


@router.post("/{case_id}/quality-calibration/record")
def save_case_quality_calibration_record(case_id: str, db: Session = Depends(get_db)):
    try:
        artifact = _case_or_error(db, case_id)
        result = _save_quality_calibration_record(artifact)
        return {"ok": True, **result, "case": _case_payload(artifact)}
    except AppError as error:
        return error_response(error)


@router.get("/{case_id}/contact-sheet")
def get_case_contact_sheet(case_id: str, db: Session = Depends(get_db)):
    try:
        artifact = _case_or_error(db, case_id)
        path = Path(artifact.contact_sheet_path)
        if not path.is_file():
            raise AppError(ErrorCode.CASE_BUILD_FAILED, "关键帧总览图不存在。")
        return FileResponse(path, media_type="image/jpeg")
    except AppError as error:
        return error_response(error)


@router.get("/{case_id}/analysis-input")
def get_case_analysis_input(case_id: str, db: Session = Depends(get_db)):
    try:
        artifact = _case_or_error(db, case_id)
        refresh_analysis_input_enrichment(artifact)
        path = Path(artifact.analysis_input_path)
        if not path.is_file():
            raise AppError(ErrorCode.CASE_BUILD_FAILED, "analysis_input.json 不存在。")
        return FileResponse(path, media_type="application/json", filename="analysis_input.json")
    except AppError as error:
        return error_response(error)


@router.get("/{case_id}/rerun-plan")
def get_case_rerun_plan(case_id: str, db: Session = Depends(get_db)):
    try:
        artifact = _case_or_error(db, case_id)
        _case_payload(artifact)
        path = _rerun_plan_path(artifact)
        if not path.is_file():
            raise AppError(ErrorCode.CASE_BUILD_FAILED, "rerun_plan.json 不存在。")
        return FileResponse(path, media_type="application/json", filename="rerun_plan.json")
    except AppError as error:
        return error_response(error)


@router.get("/{case_id}/rerun-plan.md")
def get_case_rerun_plan_markdown(case_id: str, db: Session = Depends(get_db)):
    try:
        artifact = _case_or_error(db, case_id)
        _case_payload(artifact)
        path = _rerun_plan_markdown_path(artifact)
        if not path.is_file():
            raise AppError(ErrorCode.CASE_BUILD_FAILED, "rerun_plan.md 不存在。")
        return FileResponse(path, media_type="text/markdown", filename="rerun_plan.md")
    except AppError as error:
        return error_response(error)


@router.get("/{case_id}/keyframes/{filename}")
def get_case_keyframe(case_id: str, filename: str, db: Session = Depends(get_db)):
    try:
        if "/" in filename or "\\" in filename or not filename.startswith("frame_") or not filename.endswith(".jpg"):
            raise AppError(ErrorCode.CASE_BUILD_FAILED, "关键帧文件名无效。")
        artifact = _case_or_error(db, case_id)
        path = Path(artifact.keyframes_dir) / filename
        if not path.is_file():
            raise AppError(ErrorCode.CASE_BUILD_FAILED, "关键帧不存在。")
        return FileResponse(path, media_type="image/jpeg")
    except AppError as error:
        return error_response(error)
