from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from app.config import settings
from app.errors import AppError, ErrorCode
from app.models import CaseArtifact
from app.services.analysis_taxonomy import build_analysis_context
from app.services.llm_provider import BaseLLMProvider, get_llm_provider


ProgressCallback = Callable[[int, str], None]


def analyze_case_artifact(
    artifact: CaseArtifact,
    provider: BaseLLMProvider | None = None,
    progress: ProgressCallback | None = None,
) -> dict:
    def report(value: int, message: str) -> None:
        if progress:
            progress(value, message)

    try:
        report(5, "读取素材包")
        case_dir = Path(artifact.prompt_path).parent
        metadata = _read_json(Path(artifact.metadata_path))
        ffprobe = _read_json(Path(artifact.ffprobe_path))
        analysis_input = _read_json(Path(artifact.analysis_input_path))
        analysis_context = _analysis_context(analysis_input)

        report(20, "准备视觉素材")
        image_paths = _analysis_image_paths(artifact, analysis_input)
        if not image_paths:
            raise AppError(ErrorCode.AUTO_ANALYSIS_FAILED, "素材包缺少 contact sheet 或关键帧，无法自动拆解。")

        report(35, "调用大模型自动拆解")
        llm = provider or get_llm_provider()
        result = llm.analyze(_build_prompt(metadata, ffprobe, analysis_input, analysis_context), image_paths)

        report(75, "整理自动拆解结果")
        normalized = _normalize_result(result, metadata, ffprobe, analysis_input, analysis_context)
        report_text = render_analysis_report(normalized)

        result_path = case_dir / "analysis_result.json"
        report_path = case_dir / "analysis_report.md"
        result_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        report_path.write_text(report_text, encoding="utf-8")
        report(100, "自动拆解完成")
        return {
            "analysis_result_path": str(result_path),
            "analysis_report_path": str(report_path),
            "analysis_result": normalized,
            "analysis_report": report_text,
        }
    except AppError:
        raise
    except Exception as error:
        raise AppError(ErrorCode.AUTO_ANALYSIS_FAILED, str(error)[:500]) from error


def existing_auto_analysis(artifact: CaseArtifact) -> tuple[dict | None, str]:
    case_dir = Path(artifact.prompt_path).parent
    result_path = case_dir / "analysis_result.json"
    report_path = case_dir / "analysis_report.md"
    result = None
    report = ""
    if result_path.is_file():
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            result = None
    if report_path.is_file():
        report = report_path.read_text(encoding="utf-8")
    return result, report


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _analysis_context(analysis_input: dict) -> dict:
    context = analysis_input.get("analysis_context")
    if isinstance(context, dict) and context:
        return context
    return build_analysis_context(analysis_input.get("content_category") or "generic")


def _analysis_image_paths(artifact: CaseArtifact, analysis_input: dict) -> list[Path]:
    paths: list[Path] = []
    contact_sheet = Path(artifact.contact_sheet_path)
    if contact_sheet.is_file():
        paths.append(contact_sheet)
    keyframe_dir = Path(artifact.keyframes_dir)
    keyframe_files = sorted(keyframe_dir.glob("frame_*.jpg"))[: max(0, settings.llm_max_keyframes)]
    for path in keyframe_files:
        if path.is_file() and path not in paths:
            paths.append(path)
    if not paths:
        for item in (analysis_input.get("assets") or {}).get("keyframes") or []:
            path = settings.project_root / item.get("path", "")
            if path.is_file():
                paths.append(path)
    return paths


def _build_prompt(metadata: dict, ffprobe: dict, analysis_input: dict, analysis_context: dict) -> str:
    payload = {
        "metadata": metadata,
        "ffprobe": ffprobe,
        "analysis_input": {
            key: value
            for key, value in analysis_input.items()
            if key not in {"assets"}
        },
        "analysis_context": analysis_context,
    }
    return f"""请对这个短视频素材包做全自动爆款拆解。

你会收到 contact sheet 和若干关键帧。请结合视觉信息、标题、作者、互动数据、视频参数和内容类型进行判断。

要求：
1. 只输出合法 JSON，不要 Markdown，不要解释 JSON 之外的内容。
2. 如果点赞/评论/分享为 0 或缺失，请明确标记 engagement_data_quality 为 "missing"，不要编造数据。
3. 下载文件只用于视觉拆解；标题、作者、点赞、评论、分享、发布时间以 metadata / analysis_input 为准。
4. 不要复述素材路径；输出可直接展示给用户的分析结论。
5. 对可能涉及高风险尺度、搬运、侵权或不适合照搬的内容，要给出风险与替代表达。

请严格输出以下 JSON 结构：
{{
  "summary": "一句话总结这条视频为什么值得拆",
  "content_category": "内容类型 id",
  "content_category_label": "内容类型中文名",
  "confidence": 0.0,
  "engagement_data_quality": "ok|missing|partial",
  "hook_analysis": {{
    "first_impression": "",
    "why_stop_scrolling": "",
    "first_3_seconds": ["0s ...", "1s ...", "2s ..."],
    "optimization": ""
  }},
  "visual_analysis": {{
    "scene": "",
    "subject": "",
    "composition": "",
    "lighting_color": "",
    "movement_rhythm": "",
    "style_keywords": []
  }},
  "copywriting_analysis": {{
    "title_click_reason": "",
    "subtitle_or_text_role": "",
    "comment_trigger": "",
    "reusable_patterns": []
  }},
  "emotion_path": ["开头", "中段", "结尾"],
  "content_ratio": [
    {{"name": "维度", "percent": 0, "reason": ""}}
  ],
  "timeline": [
    {{"time_range": "0-1s", "visual": "", "purpose": ""}}
  ],
  "replication": {{
    "copyable_points": [],
    "avoid_copying": [],
    "remake_angle": "",
    "opening_3s": "",
    "shot_table": [
      {{"time": "", "visual": "", "action": "", "subtitle": "", "music_rhythm": "", "purpose": ""}}
    ]
  }},
  "publish_package": {{
    "titles": [],
    "caption": "",
    "hashtags": [],
    "pinned_comment": ""
  }},
  "risks": [],
  "next_actions": []
}}

素材包结构化信息：
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def _normalize_result(
    result: dict,
    metadata: dict,
    ffprobe: dict,
    analysis_input: dict,
    analysis_context: dict,
) -> dict:
    normalized = dict(result)
    normalized.setdefault("summary", "")
    normalized.setdefault("content_category", analysis_input.get("content_category") or analysis_context.get("category_id") or "generic")
    normalized.setdefault(
        "content_category_label",
        analysis_input.get("content_category_label") or analysis_context.get("label") or "通用短视频",
    )
    normalized.setdefault("confidence", 0)
    stats = analysis_input.get("stats") or {}
    if not any(int(stats.get(key) or 0) for key in ("like_count", "comment_count", "share_count")):
        normalized["engagement_data_quality"] = "missing"
    else:
        normalized.setdefault("engagement_data_quality", "ok")
    normalized.setdefault("hook_analysis", {})
    normalized.setdefault("visual_analysis", {})
    normalized.setdefault("copywriting_analysis", {})
    normalized.setdefault("emotion_path", [])
    normalized.setdefault("content_ratio", [])
    normalized.setdefault("timeline", [])
    normalized.setdefault("replication", {})
    normalized.setdefault("publish_package", {})
    normalized.setdefault("risks", [])
    normalized.setdefault("next_actions", [])
    normalized["source"] = {
        "title": metadata.get("title") or analysis_input.get("title") or "",
        "author": metadata.get("author") or analysis_input.get("author") or "",
        "source_url": metadata.get("source_url") or analysis_input.get("source_url") or "",
        "duration": (analysis_input.get("video") or {}).get("duration") or ffprobe.get("duration") or 0,
        "resolution": f"{(analysis_input.get('video') or {}).get('width') or ffprobe.get('width') or 0}x{(analysis_input.get('video') or {}).get('height') or ffprobe.get('height') or 0}",
    }
    return normalized


def render_analysis_report(result: dict) -> str:
    lines = [
        "# AI 自动拆解报告",
        "",
        f"## 一句话总结\n\n{result.get('summary') or '-'}",
        "",
        "## 基础判断",
        "",
        f"- 内容类型：{result.get('content_category_label') or result.get('content_category') or ''}",
        f"- 置信度：{result.get('confidence', 0)}",
        f"- 互动数据质量：{result.get('engagement_data_quality', '')}",
        "",
    ]
    hook = result.get("hook_analysis") or {}
    lines.extend(
        [
            "## 前 3 秒钩子",
            "",
            f"- 第一眼：{hook.get('first_impression', '')}",
            f"- 停留理由：{hook.get('why_stop_scrolling', '')}",
            f"- 优化建议：{hook.get('optimization', '')}",
            "",
        ]
    )
    first_3s = hook.get("first_3_seconds") or []
    if first_3s:
        lines.extend(["### 逐秒观察", ""])
        lines.extend(f"- {item}" for item in first_3s)
        lines.append("")

    for title, key in (
        ("视觉拆解", "visual_analysis"),
        ("文案拆解", "copywriting_analysis"),
        ("复刻方案", "replication"),
        ("发布包", "publish_package"),
    ):
        lines.extend([f"## {title}", ""])
        value = result.get(key) or {}
        if isinstance(value, dict):
            for item_key, item_value in value.items():
                lines.append(f"- {item_key}：{_format_value(item_value)}")
        else:
            lines.append(_format_value(value))
        lines.append("")

    for title, key in (
        ("情绪路径", "emotion_path"),
        ("内容占比", "content_ratio"),
        ("时间线", "timeline"),
        ("风险", "risks"),
        ("下一步动作", "next_actions"),
    ):
        lines.extend([f"## {title}", ""])
        values = result.get(key) or []
        if isinstance(values, list):
            lines.extend(f"- {_format_value(item)}" for item in values)
        else:
            lines.append(_format_value(values))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _format_value(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)
