from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone


WORKSHEET_VERSION = 1


FIELD_LIMIT = 4000


WORKSHEET_SECTIONS = (
    {
        "section_id": "hook",
        "title": "前 3 秒钩子",
        "fields": (
            ("first_impression", "第一眼看到了什么"),
            ("stop_reason", "观众为什么会停下"),
            ("first_3s_notes", "0-3 秒逐帧笔记"),
        ),
    },
    {
        "section_id": "structure",
        "title": "内容结构",
        "fields": (
            ("rhythm_notes", "画面/动作节奏"),
            ("subtitle_notes", "字幕/标题/文案"),
            ("audio_emotion_notes", "音乐/声音/情绪路径"),
        ),
    },
    {
        "section_id": "category",
        "title": "类型判断",
        "fields": (
            ("content_ratio_notes", "内容占比判断"),
            ("reusable_points", "可借鉴点"),
            ("risk_or_mismatch", "风险或不建议照搬"),
        ),
    },
    {
        "section_id": "remake",
        "title": "复刻方案",
        "fields": (
            ("remake_angle", "适合我账号的改编角度"),
            ("shot_script", "分镜/动作/字幕草案"),
            ("publish_package", "发布文案/标签/评论引导"),
        ),
    },
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _string_value(value) -> str:
    if value is None:
        return ""
    return str(value)[:FIELD_LIMIT]


def build_default_worksheet(case_id: str, analysis_input: dict) -> dict:
    context = analysis_input.get("analysis_context") or {}
    worksheet = {
        "version": WORKSHEET_VERSION,
        "case_id": case_id,
        "content_category": analysis_input.get("content_category") or context.get("category_id") or "generic",
        "content_category_label": analysis_input.get("content_category_label") or context.get("label") or "通用短视频",
        "status": "draft",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "summary": "",
        "sections": {},
    }
    for section in WORKSHEET_SECTIONS:
        worksheet["sections"][section["section_id"]] = {
            "title": section["title"],
            "fields": {
                field_id: {
                    "label": label,
                    "value": "",
                }
                for field_id, label in section["fields"]
            },
        }
    return worksheet


def normalize_worksheet(case_id: str, analysis_input: dict, payload: dict | None, existing: dict | None = None) -> dict:
    base = build_default_worksheet(case_id, analysis_input)
    if existing:
        base = _merge_worksheet(base, existing)
    if payload:
        base = _merge_worksheet(base, payload)

    context = analysis_input.get("analysis_context") or {}
    base["version"] = WORKSHEET_VERSION
    base["case_id"] = case_id
    base["content_category"] = analysis_input.get("content_category") or context.get("category_id") or base["content_category"]
    base["content_category_label"] = (
        analysis_input.get("content_category_label") or context.get("label") or base["content_category_label"]
    )
    base["summary"] = _string_value(base.get("summary"))
    base["status"] = _string_value(base.get("status") or "draft")[:32]
    base["updated_at"] = _now_iso()
    if not base.get("created_at"):
        base["created_at"] = base["updated_at"]

    for section in base["sections"].values():
        for field in section.get("fields", {}).values():
            field["value"] = _string_value(field.get("value"))
    return base


def _merge_worksheet(base: dict, incoming: dict) -> dict:
    merged = deepcopy(base)
    for key in ("status", "summary", "created_at", "updated_at"):
        if key in incoming:
            merged[key] = incoming[key]
    for section_id, section in (incoming.get("sections") or {}).items():
        if section_id not in merged["sections"]:
            continue
        incoming_fields = section.get("fields") or {}
        for field_id, field in incoming_fields.items():
            if field_id in merged["sections"][section_id]["fields"]:
                merged["sections"][section_id]["fields"][field_id]["value"] = field.get("value", "")
    return merged


def render_analysis_brief(metadata: dict, ffprobe: dict, analysis_input: dict, worksheet: dict) -> str:
    stats = analysis_input.get("stats") or {}
    video = analysis_input.get("video") or {}
    context = analysis_input.get("analysis_context") or {}
    lines = [
        "# 短视频案例分析工作表",
        "",
        "## 基础信息",
        "",
        f"- 标题：{metadata.get('title') or analysis_input.get('title') or ''}",
        f"- 作者：{metadata.get('author') or analysis_input.get('author') or ''}",
        f"- 来源：{metadata.get('source_url') or analysis_input.get('source_url') or ''}",
        f"- 内容类型：{worksheet.get('content_category_label') or analysis_input.get('content_category_label') or ''}",
        f"- 点赞：{stats.get('like_count', 0)}",
        f"- 评论：{stats.get('comment_count', 0)}",
        f"- 分享：{stats.get('share_count', 0)}",
        f"- 互动分：{stats.get('engagement_score', 0)}",
        f"- 时长：{video.get('duration') or ffprobe.get('duration') or 0}",
        f"- 分辨率：{video.get('width') or ffprobe.get('width') or 0}x{video.get('height') or ffprobe.get('height') or 0}",
        "",
        "## 类型拆解框架",
        "",
    ]
    for title, items in (
        ("分析镜头", context.get("analysis_lens") or analysis_input.get("analysis_lens") or []),
        ("关键问题", context.get("key_questions") or analysis_input.get("key_questions") or []),
        ("内容占比", context.get("content_ratio") or analysis_input.get("content_ratio") or []),
    ):
        lines.extend([f"### {title}", ""])
        lines.extend(f"- {item}" for item in items)
        lines.append("")

    lines.extend(["## 我的拆解", ""])
    summary = worksheet.get("summary") or ""
    lines.extend(["### 总结", "", summary or "- ", ""])
    for section in worksheet.get("sections", {}).values():
        lines.extend([f"### {section.get('title', '')}", ""])
        for field in section.get("fields", {}).values():
            value = field.get("value") or "- "
            lines.extend([f"#### {field.get('label', '')}", "", value, ""])
    return "\n".join(lines).rstrip() + "\n"
