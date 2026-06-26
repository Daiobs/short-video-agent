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
            ("first_impression", "第一眼看到了什么", "写具体画面：人物/物体/文字/动作/场景，不要只写“好看”。"),
            ("stop_reason", "观众为什么会停下", "说明停留理由：反差、颜值、冲突、利益点、悬念或情绪命中。"),
            ("first_3s_notes", "0-3 秒逐帧笔记", "建议按 0s/1s/2s 写，每个时间点记录画面、字幕、动作或声音变化。"),
        ),
    },
    {
        "section_id": "structure",
        "title": "内容结构",
        "fields": (
            ("rhythm_notes", "画面/动作节奏", "记录镜头变化、动作强弱、剪辑速度，以及哪里开始变慢或变快。"),
            ("subtitle_notes", "字幕/标题/文案", "拆标题点击理由、字幕承担的信息、是否有评论引导或金句。"),
            ("audio_emotion_notes", "音乐/声音/情绪路径", "写清情绪从哪里开始、如何推进、结尾给什么感受。"),
        ),
    },
    {
        "section_id": "category",
        "title": "类型判断",
        "fields": (
            ("content_ratio_notes", "内容占比判断", "按当前类型估算：视觉/文案/情绪/教程/评论触发各占多少，为什么。"),
            ("reusable_points", "可借鉴点", "列 3-5 个可复用结构，不要只复制原视频台词或画面。"),
            ("risk_or_mismatch", "风险或不建议照搬", "写明尺度、版权、搬运、人设不匹配或平台风险，以及替代表达。"),
        ),
    },
    {
        "section_id": "remake",
        "title": "复刻方案",
        "fields": (
            ("remake_angle", "适合我账号的改编角度", "把原视频结构换成你的账号角色、人设、场景或受众需求。"),
            ("shot_script", "分镜/动作/字幕草案", "至少写一版可拍摄分镜：时间、画面、动作、字幕、节奏、目的。"),
            ("publish_package", "发布文案/标签/评论引导", "给标题、正文、标签或置顶评论，方便直接发布前复核。"),
        ),
    },
)


WORKSHEET_REVIEW_CHECKS = (
    {
        "id": "summary",
        "label": "一句话结论",
        "weight": 15,
        "fields": ("summary",),
        "action": "先写一句话：这条视频最值得学习的结构或爆点是什么。",
    },
    {
        "id": "hook",
        "label": "前 3 秒钩子",
        "weight": 20,
        "fields": ("hook.first_impression", "hook.stop_reason", "hook.first_3s_notes"),
        "action": "补齐第一眼、停留理由和 0-3 秒逐帧笔记。",
    },
    {
        "id": "structure",
        "label": "内容结构",
        "weight": 20,
        "fields": ("structure.rhythm_notes", "structure.subtitle_notes", "structure.audio_emotion_notes"),
        "minimum_fields": 2,
        "action": "至少补两项：画面节奏、字幕文案、音乐/情绪路径。",
    },
    {
        "id": "category_boundary",
        "label": "类型判断与边界",
        "weight": 20,
        "fields": ("category.content_ratio_notes", "category.reusable_points", "category.risk_or_mismatch"),
        "action": "补内容占比、可借鉴点，以及不建议照搬/风险替代表达。",
    },
    {
        "id": "remake",
        "label": "复刻落地",
        "weight": 20,
        "fields": ("remake.remake_angle", "remake.shot_script", "remake.publish_package"),
        "action": "补改编角度、分镜草案和发布文案/标签/评论引导。",
    },
    {
        "id": "specificity",
        "label": "具体程度",
        "weight": 5,
        "minimum_specific_fields": 5,
        "action": "把空泛描述改成带时间点、画面元素、用户心理或发布动作的具体笔记。",
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
        "review": {},
    }
    for section in WORKSHEET_SECTIONS:
        worksheet["sections"][section["section_id"]] = {
            "title": section["title"],
            "fields": {
                field_id: {
                    "label": label,
                    "hint": hint,
                    "value": "",
                }
                for field_id, label, hint in section["fields"]
            },
        }
    worksheet["review"] = worksheet_quality_review(worksheet)
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
            field["hint"] = _string_value(field.get("hint"))
    base["review"] = worksheet_quality_review(base)
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
    review = worksheet_quality_review(worksheet)
    lines.extend(
        [
            "### 工作表完成度",
            "",
            f"- 分数：{review['score']} / {review['max_score']}",
            f"- 等级：{review['label']}",
            f"- 结论：{review['summary']}",
            "",
        ]
    )
    if review["gaps"]:
        lines.extend(["#### 待补齐", ""])
        lines.extend(f"- {gap['label']}：{gap['action']}" for gap in review["gaps"])
        lines.append("")
    summary = worksheet.get("summary") or ""
    lines.extend(["### 总结", "", summary or "- ", ""])
    for section in worksheet.get("sections", {}).values():
        lines.extend([f"### {section.get('title', '')}", ""])
        for field in section.get("fields", {}).values():
            value = field.get("value") or "- "
            lines.extend([f"#### {field.get('label', '')}", "", value, ""])
    return "\n".join(lines).rstrip() + "\n"


def worksheet_quality_review(worksheet: dict) -> dict:
    checks = []
    for spec in WORKSHEET_REVIEW_CHECKS:
        if spec["id"] == "specificity":
            specific_count = sum(1 for value in _all_field_values(worksheet) if _is_specific_note(value))
            passed = specific_count >= spec["minimum_specific_fields"]
            message = f"已有 {specific_count} 个较具体字段。"
        else:
            values = [_worksheet_value(worksheet, field_path) for field_path in spec["fields"]]
            minimum = int(spec.get("minimum_fields") or len(values))
            filled_count = sum(1 for value in values if _has_text(value))
            passed = filled_count >= minimum
            message = f"已填写 {filled_count}/{len(values)} 项。"
        checks.append(
            {
                "id": spec["id"],
                "label": spec["label"],
                "weight": spec["weight"],
                "passed": passed,
                "message": message,
                "action": spec["action"],
            }
        )

    score = sum(check["weight"] for check in checks if check["passed"])
    gaps = [check for check in checks if not check["passed"]]
    if score >= 90 and not gaps:
        level = "complete"
        label = "人工拆解较完整"
        summary = "工作表已经覆盖钩子、结构、边界和复刻方案，可作为人工复盘稿。"
    elif score >= 70:
        level = "usable"
        label = "人工拆解可用"
        summary = "工作表主体可用，但仍建议补齐少量缺口。"
    elif score >= 40:
        level = "draft"
        label = "人工拆解草稿"
        summary = "已经有基础观察，但还不足以支撑复刻决策。"
    else:
        level = "empty"
        label = "待开始人工拆解"
        summary = "工作表信息较少，建议先从前 3 秒钩子开始补。"
    return {
        "score": score,
        "max_score": 100,
        "level": level,
        "label": label,
        "summary": summary,
        "checks": checks,
        "gaps": gaps,
        "next_actions": [gap["action"] for gap in gaps[:3]],
    }


def _worksheet_value(worksheet: dict, field_path: str) -> str:
    if field_path == "summary":
        return str(worksheet.get("summary") or "")
    section_id, field_id = field_path.split(".", 1)
    return str(
        (((worksheet.get("sections") or {}).get(section_id) or {}).get("fields") or {}).get(field_id, {}).get("value")
        or ""
    )


def _all_field_values(worksheet: dict) -> list[str]:
    values = [str(worksheet.get("summary") or "")]
    for section in (worksheet.get("sections") or {}).values():
        for field in (section.get("fields") or {}).values():
            values.append(str(field.get("value") or ""))
    return values


def _has_text(value: str) -> bool:
    return bool(str(value or "").strip())


def _is_specific_note(value: str) -> bool:
    text = str(value or "").strip()
    if len(text) >= 18:
        return True
    return any(marker in text for marker in ("0s", "1s", "2s", "3s", "前3秒", "标题", "字幕", "评论", "风险", "分镜"))
