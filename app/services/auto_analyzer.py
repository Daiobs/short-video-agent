from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from app.config import settings
from app.errors import AppError, ErrorCode
from app.models import CaseArtifact
from app.services.analysis_taxonomy import build_analysis_context
from app.services.enrichment import refresh_analysis_input_enrichment
from app.services.llm_provider import BaseLLMProvider, get_llm_provider


ProgressCallback = Callable[[int, str], None]
SHOT_TIME_RE = re.compile(r"(?P<time>\d+(?:\.\d+)?\s*(?:-|~|到)\s*\d+(?:\.\d+)?\s*s?|\d+(?:\.\d+)?\s*s)")
FIRST_SECONDS_TIME_RE = re.compile(
    r"(?:第\s*)?\d+(?:\.\d+)?\s*(?:s|秒)|"
    r"\d+(?:\.\d+)?\s*(?:-|~|到)\s*\d+(?:\.\d+)?\s*(?:s|秒)?",
    re.IGNORECASE,
)
EMOTION_PHASE_RE = re.compile(r"(开头|前段|中段|中间|结尾|后段|收尾|\d+(?:\.\d+)?\s*(?:s|秒))")
CONTENT_RATIO_RE = re.compile(
    r"(?P<name>[^,，;；、\n\r%]{1,48}?)\s*(?:[:：]?\s*(?:约|大约|大概|占比|占|比例|为|是)?\s*)"
    r"(?P<percent>\d+(?:\.\d+)?)\s*%"
)
PLACEHOLDER_TEXTS = {
    "-",
    "--",
    "n/a",
    "na",
    "none",
    "null",
    "todo",
    "待补充",
    "待填写",
    "待完善",
    "待定",
    "暂无",
    "无",
    "没有",
    "不清楚",
    "未知",
    "未提供",
    "无法判断",
    "需要补充",
}
PLACEHOLDER_PATTERNS = (
    "待补充",
    "待填写",
    "待完善",
    "暂无",
    "不清楚",
    "未提供",
    "无法判断",
    "需要补充",
)
GENERIC_VISUAL_TEXTS = {
    "室内",
    "室外",
    "人物",
    "主体",
    "画面",
    "场景",
    "测试场景",
    "室内布景",
    "人物主体",
    "主体出现",
    "字幕出现",
    "动作变化",
    "节奏变化",
    "动作节奏清楚",
    "紧凑",
    "清楚",
    "停留",
    "抓注意力",
    "文本推断",
}
GENERIC_HOOK_TEXTS = GENERIC_VISUAL_TEXTS | {
    "展示结果",
    "信息出现",
    "开头吸引",
    "制造停留",
    "有停留理由",
    "第一眼强",
    "抓住注意力",
}
GENERIC_VISUAL_PATTERNS = (
    "泛泛",
    "待复核",
    "不确定",
    "无法确认",
)
GENERIC_SHOT_TEXTS = GENERIC_VISUAL_TEXTS | {
    "看镜头",
    "动作",
    "展示",
    "互动",
    "拍摄",
    "复刻分镜草案",
}
GENERIC_PUBLISH_TEXTS = {
    "测试标题",
    "测试文案",
    "保存这套结构",
    "保留结构换成自己的表达",
    "短视频拆解",
    "内容复盘",
    "标题",
    "正文",
    "标签",
    "置顶评论",
}
GENERIC_COPY_TEXTS = {
    "标题有点击理由",
    "标题有承诺",
    "开头金句",
    "封面承诺",
    "字幕作用",
    "口播开头",
    "标题给出明确收益",
}
GENERIC_AUDIENCE_TEXTS = {
    "求同款",
    "接好运",
    "引导求同款",
    "求教程",
    "评论互动",
}
GENERIC_BOUNDARY_TEXTS = {
    "不要照搬",
    "不要照搬原文",
    "不要照搬原动作",
    "注意版权",
    "注意风险",
}
GENERIC_SUMMARY_TEXTS = {
    "可用",
    "自动拆解结果",
    "富化拆解结果",
    "旧版拆解",
    "旧报告",
    "完整拆解",
    "测试",
}
GENERIC_SUMMARY_PATTERNS = (
    "表现不错",
    "值得学习",
    "可以参考",
    "适合复刻",
    "比较完整",
    "内容完整",
    "质量较高",
    "效果不错",
)
GENERIC_EVIDENCE_TEXTS = {
    "关键帧",
    "视觉",
    "口播",
    "开头金句",
    "字幕",
    "封面承诺",
    "评论",
    "求同款",
    "求教程",
    "证据",
}
GENERIC_COPYABLE_POINT_TEXTS = {
    "爆款结构",
    "爆款节奏",
    "内容结构",
    "视频结构",
    "可以复刻",
    "适合复刻",
    "复刻结构",
    "通用模板",
}
COPYABLE_TRACE_STOP_TERMS = {
    "可以",
    "适合",
    "复刻",
    "结构",
    "视频",
    "内容",
    "这个",
    "那个",
    "方式",
    "模板",
}
SHOT_TRACE_EXTRA_TERMS = (
    "角色",
    "正面",
    "入镜",
    "结果",
    "承诺",
    "步骤",
    "教程",
    "引导",
    "鼓点",
    "黑屏",
    "闪白",
    "拔剑",
    "反转",
)
TRACEABLE_CLAIM_KEYWORDS = {
    "visual": (
        "画面",
        "视觉",
        "近景",
        "远景",
        "镜头",
        "动作",
        "构图",
        "主体",
        "人物",
        "脸",
        "姿态",
        "状态",
        "服化",
        "妆造",
        "道具",
        "光线",
        "节奏",
        "停留",
    ),
    "asr": (
        "口播",
        "旁白",
        "声音",
        "台词",
        "金句",
        "说出",
        "说了",
        "念出",
        "语音",
        "开场",
    ),
    "ocr": (
        "字幕",
        "封面字",
        "画面文字",
        "屏幕文字",
        "大字",
        "文字承诺",
    ),
    "comment": (
        "评论",
        "评论区",
        "求同款",
        "求教程",
        "教程",
        "用户需求",
        "观众需求",
        "互动需求",
    ),
}
TRACEABLE_SOURCE_LABELS = {
    "visual": "视觉证据",
    "asr": "ASR 证据",
    "ocr": "OCR 证据",
    "comment": "评论证据",
}
EVIDENCE_FIELD_LABELS = {
    "visual_evidence": "视觉证据",
    "asr_evidence": "ASR 证据",
    "ocr_evidence": "OCR 证据",
    "comment_evidence": "评论证据",
}
SPECIFIC_VISUAL_TERMS = (
    "近景",
    "远景",
    "中景",
    "特写",
    "居中",
    "构图",
    "景别",
    "镜头",
    "推进",
    "切换",
    "转场",
    "抬手",
    "转身",
    "动作",
    "姿态",
    "字幕",
    "封面字",
    "服化",
    "妆造",
    "道具",
    "光线",
    "色彩",
    "背景",
    "场景变化",
)
QUALITY_GAP_CATEGORY_LABELS = {
    "summary": "结论",
    "hook": "钩子",
    "visual": "画面",
    "copy_speech_text": "文案/声音",
    "audience": "评论",
    "evidence": "证据",
    "claim_traceability": "结论证据",
    "visual_input": "视觉输入",
    "evidence_gaps": "证据缺口",
    "evidence_confidence": "证据置信度",
    "model_confidence": "模型置信度",
    "engagement_data": "互动数据",
    "structure_depth": "结构",
    "content_ratio_balance": "内容占比",
    "category_alignment": "类型适配",
    "adaptation_boundary": "改编边界",
    "replication": "复刻",
    "copyable_traceability": "复刻来源",
    "shot_table_traceability": "分镜来源",
    "time_bounds": "时间边界",
    "publishing": "发布",
    "enrichment_usage": "富化证据",
}
CATEGORY_RATIO_KEYWORDS = {
    "beauty_cos": {
        "视觉吸引": ("视觉", "第一眼", "颜值", "吸引", "镜头", "氛围"),
        "人物人设": ("人设", "角色", "人物", "气质", "甜美", "cos"),
        "动作节奏": ("动作", "姿态", "节奏", "舞蹈", "转身"),
        "标题话题": ("标题", "话题", "点击", "标签"),
        "互动引导": ("互动", "评论", "引导", "关注"),
    },
    "motivational": {
        "情绪痛点": ("情绪", "痛点", "低谷", "焦虑", "共鸣"),
        "金句文案": ("金句", "文案", "台词", "表达", "句子"),
        "音乐氛围": ("音乐", "氛围", "声音", "bgm"),
        "画面承托": ("画面", "视觉", "场景", "承托"),
        "评论触发": ("评论", "触发", "代入", "互动"),
    },
    "tutorial": {
        "痛点承诺": ("痛点", "问题", "需求", "承诺", "解决"),
        "步骤清晰": ("步骤", "教程", "教学", "方法", "操作"),
        "结果证明": ("结果", "对比", "证明", "效果"),
        "字幕信息": ("字幕", "画面文字", "信息提示"),
        "收藏理由": ("收藏", "保存", "转发", "复看"),
    },
    "plot_twist": {
        "冲突建立": ("冲突", "矛盾", "人物关系", "目标"),
        "悬念推进": ("悬念", "信息差", "推进", "铺垫"),
        "反转强度": ("反转", "转折", "结尾", "爽点", "笑点"),
        "表演表达": ("表演", "台词", "动作", "情绪"),
        "互动争议": ("争议", "讨论", "评论", "互动"),
    },
    "product_seed": {
        "痛点场景": ("痛点", "场景", "需求", "问题"),
        "卖点证明": ("卖点", "证明", "效果", "功能"),
        "细节特写": ("细节", "特写", "展示", "开箱"),
        "信任建立": ("信任", "测评", "体验", "背书"),
        "转化引导": ("转化", "下单", "链接", "私信", "购买"),
    },
    "knowledge": {
        "观点钩子": ("观点", "钩子", "反常识", "争议"),
        "论证结构": ("论证", "结构", "逻辑", "推理"),
        "例子类比": ("例子", "案例", "类比", "场景"),
        "字幕承载": ("字幕", "信息", "文字", "理解"),
        "讨论引导": ("讨论", "评论", "争议", "互动"),
    },
    "edge_visual": {
        "视觉吸引": ("视觉", "第一眼", "吸引", "身材", "镜头"),
        "尺度风险": ("尺度", "风险", "审核", "低质", "标签"),
        "人设匹配": ("人设", "角色", "气质", "定位"),
        "可替代表达": ("替代", "安全", "高级", "妆造", "剧情"),
        "评论质量": ("评论", "质量", "互动", "低质量"),
    },
}
CATEGORY_ALIGNMENT_REQUIRED_MATCHES = 2
EMOTION_STAGE_KEYWORDS = {
    "opening": ("开头", "开场", "前3秒", "前三秒", "0s", "0-", "第一秒", "第一眼"),
    "middle": ("中段", "中间", "承接", "维持", "推进", "展开", "中部"),
    "ending": ("结尾", "收尾", "最后", "尾段", "互动", "转化", "评论", "关注", "记忆点"),
}
EMOTION_STAGE_LABELS = {
    "opening": "开头",
    "middle": "中段",
    "ending": "结尾",
}


def analyze_case_artifact(
    artifact: CaseArtifact,
    provider: BaseLLMProvider | None = None,
    progress: ProgressCallback | None = None,
    mode: str = "deep",
) -> dict:
    def report(value: int, message: str) -> None:
        if progress:
            progress(value, message)

    try:
        report(5, "读取素材包")
        case_dir = Path(artifact.prompt_path).parent
        metadata = _read_json(Path(artifact.metadata_path))
        ffprobe = _read_json(Path(artifact.ffprobe_path))
        analysis_input = refresh_analysis_input_enrichment(artifact)
        analysis_context = _analysis_context(analysis_input)
        manual_review = _manual_review_payload(case_dir, analysis_input)

        report(20, "准备视觉素材")
        image_paths = _analysis_image_paths(artifact, analysis_input)
        if not image_paths:
            raise AppError(ErrorCode.AUTO_ANALYSIS_FAILED, "素材包缺少 contact sheet 或关键帧，无法自动拆解。")

        report(35, "调用大模型自动拆解")
        llm = provider or get_llm_provider()
        if mode == "fast":
            result, visual_input_mode = _run_fast_analysis(
                llm,
                artifact,
                metadata,
                ffprobe,
                analysis_input,
                analysis_context,
                manual_review,
                image_paths,
                report,
            )
        else:
            prompt = _build_prompt(metadata, ffprobe, analysis_input, analysis_context, manual_review)
            visual_input_mode = _visual_input_mode(artifact, image_paths)
            try:
                result = llm.analyze(prompt, image_paths)
            except AppError as error:
                if not _should_degrade_llm_error(error) or len(image_paths) <= 1:
                    if _should_degrade_llm_error(error) and image_paths:
                        report(55, "视觉输入调用失败，降级为文本拆解")
                        visual_input_mode = "text_only"
                        result = llm.analyze(
                            _compact_text_prompt(metadata, ffprobe, analysis_input, analysis_context, manual_review),
                            [],
                        )
                    else:
                        raise
                else:
                    report(45, "首次调用失败，使用轻量视觉输入重试")
                    light_image_paths = image_paths[:1]
                    visual_input_mode = _visual_input_mode(artifact, light_image_paths)
                    light_prompt = (
                        f"{prompt}\n\n"
                        "注意：首次多图请求失败，本次只使用 contact_sheet.jpg 进行轻量重试。"
                        "请基于关键帧总览图和结构化信息完成拆解。"
                    )
                    try:
                        result = llm.analyze(light_prompt, light_image_paths)
                    except AppError as retry_error:
                        if not _should_degrade_llm_error(retry_error):
                            raise
                        report(55, "轻量视觉输入仍失败，降级为文本拆解")
                        visual_input_mode = "text_only"
                        result = llm.analyze(
                            _compact_text_prompt(metadata, ffprobe, analysis_input, analysis_context, manual_review),
                            [],
                        )

        report(75, "整理自动拆解结果")
        normalized = _normalize_result(
            result,
            metadata,
            ffprobe,
            analysis_input,
            analysis_context,
            visual_input_mode,
            manual_review,
        )
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
    if result:
        result = _ensure_analysis_quality_fields(artifact, result)
    if report_path.is_file():
        report = report_path.read_text(encoding="utf-8")
    return result, report


def manual_review_context_for_case(artifact: CaseArtifact) -> dict:
    case_dir = Path(artifact.prompt_path).parent
    analysis_input = refresh_analysis_input_enrichment(artifact)
    return _normalize_manual_review_context(_manual_review_payload(case_dir, analysis_input))


def _ensure_analysis_quality_fields(artifact: CaseArtifact, result: dict) -> dict:
    normalized = dict(result)
    before = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    analysis_input = refresh_analysis_input_enrichment(artifact)
    metadata = _read_optional_json(Path(artifact.metadata_path))
    ffprobe = _read_optional_json(Path(artifact.ffprobe_path))
    case_dir = Path(artifact.prompt_path).parent
    manual_review = _manual_review_payload(case_dir, analysis_input)
    normalized.setdefault("summary", "")
    normalized.setdefault("hook_analysis", {})
    normalized.setdefault("visual_analysis", {})
    normalized.setdefault("copywriting_analysis", {})
    normalized.setdefault("speech_analysis", {})
    normalized.setdefault("screen_text_analysis", {})
    normalized.setdefault("comment_insights", {})
    normalized.setdefault("emotion_path", [])
    normalized.setdefault("content_ratio", [])
    normalized.setdefault("timeline", [])
    normalized.setdefault("replication", {})
    normalized.setdefault("publish_package", {})
    normalized.setdefault("enrichment_usage", _default_enrichment_usage(analysis_input))
    normalized.setdefault("risks", [])
    normalized.setdefault("next_actions", [])
    normalized["confidence"] = _normalize_model_confidence(normalized.get("confidence"))
    _normalize_structured_fields(normalized)
    existing_evidence = normalized.get("evidence_summary")
    current_visual_mode = _visual_input_mode(artifact, _analysis_image_paths(artifact, analysis_input))
    normalized["evidence_summary"] = _normalize_evidence_summary(
        existing_evidence,
        analysis_input,
        _conservative_visual_input_mode(
            existing_evidence.get("visual_input_mode") if isinstance(existing_evidence, dict) else "",
            current_visual_mode,
        ),
    )
    normalized["enrichment_usage"] = _normalize_enrichment_usage(
        normalized.get("enrichment_usage"),
        analysis_input,
        normalized["evidence_summary"],
    )
    normalized["manual_review_context"] = _normalize_manual_review_context(manual_review)
    _align_detection_flags_with_evidence(normalized)
    _annotate_unbacked_enrichment_insights(normalized)
    _annotate_unused_available_enrichment(normalized)
    normalized["enrichment_coverage"] = _build_enrichment_coverage(normalized, analysis_input)
    normalized["rerun_compliance"] = _build_rerun_compliance(normalized)
    normalized["source"] = _normalize_source_payload(normalized.get("source"), metadata, ffprobe, analysis_input)
    normalized["quality_review"] = _analysis_quality_review(normalized)
    after = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    if after != before:
        case_dir = Path(artifact.prompt_path).parent
        result_path = case_dir / "analysis_result.json"
        report_path = case_dir / "analysis_report.md"
        result_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        report_path.write_text(render_analysis_report(normalized), encoding="utf-8")
    return normalized


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _manual_review_payload(case_dir: Path, analysis_input: dict | None = None) -> dict:
    worksheet = _read_optional_json(case_dir / "worksheet.json")
    compact = _compact_worksheet(worksheet)
    quality_acceptance = _compact_quality_acceptance(_read_optional_json(case_dir / "quality_acceptance.json"))
    has_notes = bool(
        compact.get("summary")
        or compact.get("sections")
        or quality_acceptance.get("has_feedback")
    )
    return {
        "has_manual_notes": has_notes,
        "worksheet": compact,
        "quality_acceptance": quality_acceptance,
        "rerun_strategy": _build_rerun_strategy(compact, quality_acceptance, analysis_input or {}),
        "analysis_brief": _read_optional_text(case_dir / "analysis_brief.md", 6000) if has_notes else "",
    }


def _read_optional_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _read_optional_text(path: Path, limit: int) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _compact_worksheet(worksheet: dict) -> dict:
    if not isinstance(worksheet, dict) or not worksheet:
        return {}
    sections = []
    for section_id, section in (worksheet.get("sections") or {}).items():
        fields = []
        for field_id, field in (section.get("fields") or {}).items():
            value = str((field or {}).get("value") or "").strip()
            if not value:
                continue
            fields.append(
                {
                    "field_id": field_id,
                    "label": (field or {}).get("label") or field_id,
                    "value": _truncate(value, 1200),
                }
            )
        if fields:
            sections.append(
                {
                    "section_id": section_id,
                    "title": section.get("title") or section_id,
                    "fields": fields,
                }
            )
    review = worksheet.get("review") if isinstance(worksheet.get("review"), dict) else {}
    return {
        "content_category": worksheet.get("content_category", ""),
        "content_category_label": worksheet.get("content_category_label", ""),
        "summary": _truncate(worksheet.get("summary", ""), 1200),
        "review": {
            "score": review.get("score", 0),
            "level": review.get("level", ""),
            "label": review.get("label", ""),
            "gaps": [
                {"id": gap.get("id", ""), "label": gap.get("label", ""), "action": gap.get("action", "")}
                for gap in (review.get("gaps") or [])[:6]
                if isinstance(gap, dict)
            ],
        },
        "sections": sections,
    }


def _compact_quality_acceptance(acceptance: dict) -> dict:
    if not isinstance(acceptance, dict) or not acceptance:
        return {}
    checks = []
    check_labels = {
        "summary_matches_video": "总结是否符合视频",
        "evidence_is_sufficient": "证据是否足够",
        "copyable_points_are_useful": "可复刻点是否有用",
        "shot_table_is_actionable": "分镜表是否可执行",
        "publish_package_is_usable": "发布包是否可用",
    }
    raw_checks = acceptance.get("checks") if isinstance(acceptance.get("checks"), dict) else {}
    for key, value in raw_checks.items():
        status = str(value or "").strip()
        if not status:
            continue
        checks.append(
            {
                "id": key,
                "label": check_labels.get(key, key),
                "status": status,
            }
        )
    snapshot = acceptance.get("quality_snapshot") if isinstance(acceptance.get("quality_snapshot"), dict) else {}
    verdict = str(acceptance.get("verdict") or "pending").strip()
    summary = _truncate(acceptance.get("summary", ""), 1200)
    notes = _truncate(acceptance.get("notes", ""), 1600)
    next_actions = _truncate(acceptance.get("next_actions", ""), 1200)
    score = str(acceptance.get("score") or "").strip()
    has_feedback = bool(
        verdict not in {"", "pending"}
        or score
        or summary
        or checks
        or notes
        or next_actions
    )
    return {
        "has_feedback": has_feedback,
        "verdict": verdict or "pending",
        "score": score,
        "summary": summary,
        "checks": checks,
        "notes": notes,
        "next_actions": next_actions,
        "quality_snapshot": {
            "score": snapshot.get("score", 0),
            "level": snapshot.get("level", ""),
            "label": snapshot.get("label", ""),
            "gap_ids": [
                str(item or "").strip()
                for item in (snapshot.get("gap_ids") or [])[:12]
                if str(item or "").strip()
            ],
        },
    }


RERUN_CHECK_INSTRUCTIONS = {
    "summary_matches_video": {
        "instruction": "重写 summary 和 hook_analysis，必须贴合实际画面、标题、ASR/OCR/评论证据。",
        "do_not_repeat": "不要继续输出和视频不相符的泛化总结。",
        "output": "summary 必须包含至少一个具体视觉、文字、口播或评论证据。",
    },
    "evidence_is_sufficient": {
        "instruction": "补齐 evidence_summary，并让每个关键结论都能追溯到视觉、ASR、OCR、评论或人工观察。",
        "do_not_repeat": "不要把没有证据的判断写成确定结论。",
        "output": "证据不足的判断必须放入 inferred_points 或 evidence_gaps。",
    },
    "copyable_points_are_useful": {
        "instruction": "把可复刻点改成可执行动作，并说明对应证据来源。",
        "do_not_repeat": "不要输出“爆款结构”“适合复刻”这类无来源泛化点。",
        "output": "replication.copyable_points 每条都要具体、可拍、可追溯。",
    },
    "shot_table_is_actionable": {
        "instruction": "重写分镜表，只保留基于原视频时间线、关键帧、OCR/ASR 或人工反馈的动作。",
        "do_not_repeat": "不要凭空新增原视频没有的镜头、动作、转场或字幕。",
        "output": "replication.shot_table 每行必须包含 time，且画面/动作/字幕/节奏/目的至少两项可执行。",
    },
    "publish_package_is_usable": {
        "instruction": "重写发布包，让标题、正文、标签和置顶评论能直接用于复盘或改编。",
        "do_not_repeat": "不要只给标题或空泛发布建议。",
        "output": "publish_package 至少包含 titles、caption，并尽量补 hashtags 或 pinned_comment。",
    },
}


def _build_rerun_strategy(worksheet: dict, quality_acceptance: dict, analysis_input: dict) -> dict:
    fix_targets: list[dict] = []
    do_not_repeat: list[str] = []
    required_evidence: list[dict] = []
    output_requirements: list[str] = []
    verdict = str(quality_acceptance.get("verdict") or "pending").strip()
    has_feedback = bool(quality_acceptance.get("has_feedback"))
    worksheet_has_notes = bool(worksheet.get("summary") or worksheet.get("sections"))

    for check in quality_acceptance.get("checks") or []:
        if not isinstance(check, dict):
            continue
        status = str(check.get("status") or "").strip()
        if status not in {"needs_fix", "reject"}:
            continue
        check_id = str(check.get("id") or "").strip()
        label = str(check.get("label") or check_id).strip()
        rule = RERUN_CHECK_INSTRUCTIONS.get(check_id, {})
        fix_targets.append(
            {
                "id": check_id,
                "label": label,
                "source": "quality_acceptance",
                "status": status,
                "instruction": rule.get("instruction") or f"修正人工验收指出的问题：{label}",
            }
        )
        if rule.get("do_not_repeat"):
            _append_unique_text(do_not_repeat, rule["do_not_repeat"])
        if rule.get("output"):
            _append_unique_text(output_requirements, rule["output"])

    if worksheet_has_notes:
        for gap in (worksheet.get("review") or {}).get("gaps") or []:
            if not isinstance(gap, dict):
                continue
            label = str(gap.get("label") or gap.get("id") or "").strip()
            action = str(gap.get("action") or "").strip()
            if not label and not action:
                continue
            fix_targets.append(
                {
                    "id": str(gap.get("id") or label).strip(),
                    "label": label or "人工工作表缺口",
                    "source": "worksheet_review",
                    "status": "needs_context",
                    "instruction": action or "参考人工工作表缺口补齐拆解。",
                }
            )

    if quality_acceptance.get("summary"):
        fix_targets.append(
            {
                "id": "human_summary",
                "label": "人工验收意见",
                "source": "quality_acceptance",
                "status": verdict,
                "instruction": f"优先回应人工验收意见：{quality_acceptance.get('summary')}",
            }
        )
    if quality_acceptance.get("notes"):
        fix_targets.append(
            {
                "id": "human_notes",
                "label": "人工详细备注",
                "source": "quality_acceptance",
                "status": "needs_fix",
                "instruction": f"逐条处理人工备注：{quality_acceptance.get('notes')}",
            }
        )
    if quality_acceptance.get("next_actions"):
        fix_targets.append(
            {
                "id": "human_next_actions",
                "label": "人工下一步",
                "source": "quality_acceptance",
                "status": "needs_fix",
                "instruction": f"执行人工下一步要求：{quality_acceptance.get('next_actions')}",
            }
        )

    enrichment = analysis_input.get("analysis_enrichment") if isinstance(analysis_input, dict) else {}
    enrichment = enrichment if isinstance(enrichment, dict) else {}
    asr = enrichment.get("asr") if isinstance(enrichment.get("asr"), dict) else {}
    ocr = enrichment.get("ocr") if isinstance(enrichment.get("ocr"), dict) else {}
    comments = enrichment.get("comments") if isinstance(enrichment.get("comments"), dict) else {}

    asr_text = str(asr.get("full_text") or "").strip()
    if asr_text:
        required_evidence.append(
            {
                "id": "asr",
                "label": "ASR 转写",
                "status": asr.get("status") or "success",
                "char_count": len(asr_text),
                "segment_count": int(asr.get("segment_count") or 0),
                "excerpt": _evidence_excerpt(asr_text),
                "instruction": "必须用 ASR 转写修正 speech_analysis、脚本结构、金句和情绪路径。",
            }
        )
    elif _strategy_needs_text(quality_acceptance, ("口播", "ASR", "语音", "脚本")):
        required_evidence.append(
            {
                "id": "asr",
                "label": "ASR 转写",
                "status": _missing_evidence_status(asr.get("status")),
                "instruction": "本次仍缺 ASR；不要编造口播内容，把口播相关判断放入 evidence_gaps。",
                "action_label": "运行 ASR",
                "target": "#asr-placeholder-button",
                "mode": "click",
            }
        )

    ocr_text = " ".join(
        str(ocr.get(key) or "").strip()
        for key in ("frame_text", "subtitle_text", "cover_text")
        if str(ocr.get(key) or "").strip()
    )
    if ocr_text:
        required_evidence.append(
            {
                "id": "ocr",
                "label": "OCR 文字",
                "status": ocr.get("status") or "success",
                "char_count": len(ocr_text),
                "sources": _ocr_evidence_sources(ocr),
                "excerpt": _evidence_excerpt(ocr_text),
                "instruction": "必须用 OCR 文字修正 screen_text_analysis、标题承诺、字幕结构和文案节奏。",
            }
        )
    elif _strategy_needs_text(quality_acceptance, ("OCR", "字幕", "封面字", "画面文字")):
        required_evidence.append(
            {
                "id": "ocr",
                "label": "OCR 文字",
                "status": _missing_evidence_status(ocr.get("status")),
                "instruction": "本次仍缺 OCR；不要编造字幕/封面字，把画面文字判断放入 evidence_gaps。",
                "action_label": "运行 OCR",
                "target": "#ocr-placeholder-button",
                "mode": "click",
            }
        )

    if int(comments.get("total_comments") or 0) > 0:
        required_evidence.append(
            {
                "id": "comments",
                "label": "评论摘要",
                "status": comments.get("status") or "success",
                "count": int(comments.get("total_comments") or 0),
                "instruction": "必须用评论摘要修正 comment_insights、用户需求、互动钩子和发布包。",
            }
        )
    elif _strategy_needs_text(quality_acceptance, ("评论", "用户", "互动", "高赞")):
        required_evidence.append(
            {
                "id": "comments",
                "label": "评论摘要",
                "status": _missing_evidence_status(comments.get("status")),
                "instruction": "本次仍缺评论；不要编造用户反馈，把评论相关判断放入 evidence_gaps。",
                "action_label": "导入评论",
                "target": "#comments-import-text",
                "mode": "focus",
            }
        )

    if fix_targets:
        _append_unique_text(
            output_requirements,
            "next_actions 必须说明本次重跑后仍缺什么，以及下一步应该补哪类证据或改哪类输出。",
        )

    active = bool(has_feedback or fix_targets or required_evidence)
    evidence_summary = _rerun_evidence_summary(required_evidence)
    return {
        "active": active,
        "priority": _rerun_priority(verdict, fix_targets),
        "summary": _rerun_strategy_summary(verdict, fix_targets, required_evidence),
        "evidence_summary": evidence_summary,
        "fix_targets": fix_targets[:12],
        "do_not_repeat": do_not_repeat[:10],
        "required_evidence": required_evidence[:8],
        "output_requirements": output_requirements[:10],
    }


def _rerun_evidence_summary(required_evidence: list[dict]) -> dict:
    missing_statuses = {"missing", "provider_missing", "pending", "disabled", "not_configured"}
    ready_statuses = {"success", "no_speech", "no_text"}
    total = 0
    ready = 0
    missing = 0
    missing_ids = []
    ready_ids = []
    for item in required_evidence:
        if not isinstance(item, dict):
            continue
        total += 1
        item_id = str(item.get("id") or item.get("label") or "").strip()
        status = str(item.get("status") or "").strip()
        if status in missing_statuses or status not in ready_statuses:
            missing += 1
            if item_id:
                missing_ids.append(item_id)
        else:
            ready += 1
            if item_id:
                ready_ids.append(item_id)
    return {
        "total": total,
        "ready": ready,
        "missing": missing,
        "ready_ids": ready_ids,
        "missing_ids": missing_ids,
        "complete": total > 0 and missing == 0,
    }


def _evidence_excerpt(value: str, limit: int = 80) -> str:
    return _truncate(" ".join(str(value or "").split()), limit)


def _ocr_evidence_sources(ocr: dict) -> list[str]:
    sources = []
    labels = {
        "cover_text": "cover",
        "subtitle_text": "subtitle",
        "frame_text": "frame",
    }
    for key, label in labels.items():
        if str(ocr.get(key) or "").strip():
            sources.append(label)
    return sources


def _strategy_needs_text(quality_acceptance: dict, needles: tuple[str, ...]) -> bool:
    text = " ".join(
        str(value or "")
        for value in (
            quality_acceptance.get("summary"),
            quality_acceptance.get("notes"),
            quality_acceptance.get("next_actions"),
            json.dumps(quality_acceptance.get("checks") or [], ensure_ascii=False),
        )
    )
    return any(needle.lower() in text.lower() for needle in needles)


def _missing_evidence_status(status: str | None) -> str:
    value = str(status or "").strip()
    if not value or value in {"pending", "disabled", "not_configured"}:
        return "missing"
    return value


def _rerun_priority(verdict: str, fix_targets: list[dict]) -> str:
    if verdict == "reject":
        return "blocker"
    if verdict == "needs_fix" or fix_targets:
        return "high"
    return "normal"


def _rerun_strategy_summary(verdict: str, fix_targets: list[dict], required_evidence: list[dict]) -> str:
    if not fix_targets and not required_evidence:
        return "暂无明确重跑策略。"
    pieces = []
    if verdict in {"needs_fix", "reject"}:
        pieces.append("按人工验收反馈修正")
    if fix_targets:
        pieces.append(f"优先处理 {len(fix_targets)} 个修正目标")
    if required_evidence:
        pieces.append(f"核对 {len(required_evidence)} 类证据")
    return "，".join(pieces) + "。"


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


def _visual_input_mode(artifact: CaseArtifact, image_paths: list[Path]) -> str:
    if not image_paths:
        return "text_only"
    contact_sheet = Path(artifact.contact_sheet_path)
    if len(image_paths) == 1 and image_paths[0] == contact_sheet:
        return "contact_sheet_only"
    return "multi_image"


def _conservative_visual_input_mode(existing_mode: str, current_mode: str) -> str:
    rank = {"text_only": 0, "contact_sheet_only": 1, "multi_image": 2}
    if existing_mode not in rank:
        return current_mode if current_mode in rank else "text_only"
    if current_mode not in rank:
        return existing_mode
    return existing_mode if rank[existing_mode] <= rank[current_mode] else current_mode


def _run_fast_analysis(
    llm: BaseLLMProvider,
    artifact: CaseArtifact,
    metadata: dict,
    ffprobe: dict,
    analysis_input: dict,
    analysis_context: dict,
    manual_review: dict | None,
    image_paths: list[Path],
    report: Callable[[int, str], None],
) -> tuple[dict, str]:
    contact_sheet = Path(artifact.contact_sheet_path)
    light_image_paths = [contact_sheet] if contact_sheet.is_file() else image_paths[:1]
    if light_image_paths:
        report(35, "调用大模型快速视觉拆解")
        visual_input_mode = _visual_input_mode(artifact, light_image_paths)
        try:
            return (
                llm.analyze(
                    _build_fast_prompt(metadata, ffprobe, analysis_input, analysis_context, manual_review),
                    light_image_paths,
                ),
                visual_input_mode,
            )
        except AppError as error:
            if not _should_degrade_llm_error(error):
                raise
            report(55, "快速视觉失败，改用文本拆解")

    report(60, "调用大模型快速文本拆解")
    return (
        llm.analyze(_fast_text_prompt(metadata, ffprobe, analysis_input, analysis_context, manual_review), []),
        "text_only",
    )


def _build_fast_prompt(
    metadata: dict,
    ffprobe: dict,
    analysis_input: dict,
    analysis_context: dict,
    manual_review: dict | None = None,
) -> str:
    return f"""你是短视频内容策略分析师。请看 contact_sheet.jpg，并快速输出一个简短 JSON。

目标：给用户一个能直接看的短视频拆解报告，不要写后台诊断。总字数控制在 800-1200 字。

要求：
1. 只输出合法 JSON，不要 Markdown。
2. 每个数组最多 4 条，每条尽量不超过 45 个字。
3. summary 写 2-3 句，说明这条视频靠什么吸引、适合学习什么。
4. 重点判断：第一眼吸引、画面/人物气质、动作节奏、可复刻点、风险边界。
4. 看不到的内容不要编造。
5. 面向短视频创作者，不要输出“质量门槛、证据覆盖、后台素材包”等工程说明。

输出 JSON 结构：
{{
  "summary": "",
  "content_category": "{analysis_input.get('content_category') or analysis_context.get('category_id') or 'generic'}",
  "content_category_label": "{analysis_input.get('content_category_label') or analysis_context.get('label') or '通用短视频'}",
  "confidence": 0.0,
  "engagement_data_quality": "ok|missing|partial",
  "hook_analysis": {{"first_impression": "", "why_stop_scrolling": "", "first_3_seconds": [], "optimization": ""}},
  "visual_analysis": {{"subject": "", "composition": "", "lighting_color": "", "movement_rhythm": "", "style_keywords": []}},
  "replication": {{"copyable_points": [], "avoid_copying": [], "remake_angle": "", "opening_3s": ""}},
  "publish_package": {{"titles": [], "caption": "", "hashtags": []}},
  "evidence_summary": {{"visual_input_mode": "contact_sheet_only", "visual_evidence": [], "inferred_points": [], "evidence_gaps": []}},
  "risks": [],
  "next_actions": []
}}

输入信息：
{json.dumps(_fast_prompt_payload(metadata, ffprobe, analysis_input, analysis_context, manual_review), ensure_ascii=False, indent=2)}
"""


def _fast_text_prompt(
    metadata: dict,
    ffprobe: dict,
    analysis_input: dict,
    analysis_context: dict,
    manual_review: dict | None = None,
) -> str:
    return f"""请做短视频快速文本拆解。本次视觉图片调用失败，只能基于标题、互动数据、视频参数和内容类型输出保守结论。

只输出合法 JSON，不要 Markdown。总字数控制在 600-900 字。数组最多 4 条。
面向短视频创作者，不要输出后台诊断说明；视觉判断必须标记为需要复核。

输出字段：
{{
  "summary": "",
  "content_category": "{analysis_input.get('content_category') or analysis_context.get('category_id') or 'generic'}",
  "content_category_label": "{analysis_input.get('content_category_label') or analysis_context.get('label') or '通用短视频'}",
  "confidence": 0.35,
  "engagement_data_quality": "ok|missing|partial",
  "hook_analysis": {{"first_impression": "文本降级推断，需要复核画面", "why_stop_scrolling": "", "first_3_seconds": [], "optimization": ""}},
  "visual_analysis": {{"subject": "文本降级，需复核画面", "composition": "", "lighting_color": "", "movement_rhythm": "", "style_keywords": []}},
  "replication": {{"copyable_points": [], "avoid_copying": ["不要照搬原视频画面和文案"], "remake_angle": "", "opening_3s": ""}},
  "publish_package": {{"titles": [], "caption": "", "hashtags": []}},
  "evidence_summary": {{"visual_input_mode": "text_only", "visual_evidence": [], "inferred_points": ["视觉相关结论需要人工复核"], "evidence_gaps": ["缺少可用视觉输入"]}},
  "risks": ["文本降级拆解不能替代画面判断"],
  "next_actions": []
}}

输入信息：
{json.dumps(_fast_prompt_payload(metadata, ffprobe, analysis_input, analysis_context, manual_review), ensure_ascii=False, indent=2)}
"""


def _fast_prompt_payload(
    metadata: dict,
    ffprobe: dict,
    analysis_input: dict,
    analysis_context: dict,
    manual_review: dict | None = None,
) -> dict:
    stats = analysis_input.get("stats") or {}
    video = analysis_input.get("video") or {}
    enrichment = analysis_input.get("analysis_enrichment") or {}
    return {
        "title": metadata.get("title") or analysis_input.get("title") or "",
        "author": metadata.get("author") or analysis_input.get("author") or "",
        "source_url": metadata.get("source_url") or analysis_input.get("source_url") or "",
        "stats": {
            "like_count": stats.get("like_count", 0),
            "comment_count": stats.get("comment_count", 0),
            "share_count": stats.get("share_count", 0),
            "engagement_score": stats.get("engagement_score", 0),
        },
        "video": {
            "duration": video.get("duration") or ffprobe.get("duration") or 0,
            "width": video.get("width") or ffprobe.get("width") or 0,
            "height": video.get("height") or ffprobe.get("height") or 0,
            "file_size": video.get("file_size") or ffprobe.get("file_size") or 0,
        },
        "content_category": analysis_input.get("content_category") or analysis_context.get("category_id") or "generic",
        "content_category_label": (
            analysis_input.get("content_category_label") or analysis_context.get("label") or "通用短视频"
        ),
        "category_description": analysis_context.get("description", ""),
        "asr_text": _truncate_text(((enrichment.get("asr") or {}).get("full_text") or ""), 600),
        "ocr_text": _truncate_text(json.dumps(enrichment.get("ocr") or {}, ensure_ascii=False), 600),
        "comment_summary": _truncate_text(json.dumps(enrichment.get("comments") or {}, ensure_ascii=False), 600),
        "manual_notes": _truncate_text(json.dumps(manual_review or {}, ensure_ascii=False), 600),
    }


def _truncate_text(value: str, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else f"{text[:limit]}..."


def _build_prompt(
    metadata: dict,
    ffprobe: dict,
    analysis_input: dict,
    analysis_context: dict,
    manual_review: dict | None = None,
) -> str:
    payload = {
        "metadata": metadata,
        "ffprobe": ffprobe,
        "analysis_input": {
            key: value
            for key, value in analysis_input.items()
            if key not in {"assets"}
        },
        "analysis_context": analysis_context,
        "manual_review": manual_review or {},
    }
    enrichment = analysis_input.get("analysis_enrichment") or {}
    return f"""请对这个短视频素材包做全自动爆款拆解。

你会收到 contact sheet 和若干关键帧。请结合视觉信息、标题、作者、互动数据、视频参数、内容类型，以及素材包中已富化的 ASR/OCR/评论数据进行判断。

要求：
1. 只输出合法 JSON，不要 Markdown，不要解释 JSON 之外的内容。
2. 如果点赞/评论/分享为 0 或缺失，请明确标记 engagement_data_quality 为 "missing"，不要编造数据；此时只能判断内容结构，不能判断真实爆款强度，并要在 risks 或 next_actions 中说明需要补指标快照。
3. 下载文件只用于视觉拆解；标题、作者、点赞、评论、分享、发布时间以 metadata / analysis_input 为准。
4. 不要复述素材路径；输出可直接展示给用户的分析结论。
5. 对可能涉及高风险尺度、搬运、侵权或不适合照搬的内容，要给出风险与替代表达。
6. 如果 analysis_enrichment 中存在 ASR 转写、OCR 文字或评论摘要，必须用于判断钩子、文案结构、情绪路径和复刻方案；如果缺失，要在 enrichment_usage 里说明缺失，不要编造。
7. 每个关键结论要尽量标注证据来源。视觉判断来自 contact sheet/keyframes；口播判断来自 ASR；画面文字判断来自 OCR；用户需求判断来自评论摘要。证据不足的结论必须放入 inferred_points 或 evidence_gaps。
8. 输出必须满足质量门槛：confidence 建议 >= 0.6；first_3_seconds 至少写两个具体时间点，并说明真实画面/字幕/动作变化，不要只写“主体出现/字幕出现/节奏变化”；visual_analysis 至少覆盖场景/主体/构图/运动节奏中的两类；emotion_path 至少两段；content_ratio 要用 2-5 项覆盖完整结构，每项有 percent 和 reason，percent 总和约 100%；shot_table 至少一行包含 time 且画面/动作/字幕/节奏/目的中至少两项；publish_package 不能只有标题，还要有 caption、hashtags 或 pinned_comment；replication.avoid_copying 或 risks 必须说明不要照搬和替代表达。
9. replication.copyable_points 每一条都必须能追溯到 hook_analysis、visual_analysis、copywriting_analysis、speech_analysis、screen_text_analysis、comment_insights 或 evidence_summary；不要输出“爆款结构”“适合复刻”这类无来源泛化点。replication.shot_table 每一行都必须基于 timeline、evidence_summary、opening_3s 或 copyable_points；不要凭空新增原视频没有的镜头、动作、转场或字幕。若属于创意扩展，请移入 risks / next_actions，并说明需要人工确认。
10. timeline、hook_analysis.first_3_seconds 和 replication.shot_table 的时间点必须落在 ffprobe/analysis_input 给出的视频时长内；first_3_seconds 只能描述 0-3s；不要给 10 秒视频编出 15-20s 的原片分镜。
11. 如果 manual_review 中存在人工工作表内容，请把它作为用户观察和校对意见使用；不要用它替代真实视觉/ASR/OCR/评论证据。若人工笔记与模型观察冲突，请在 evidence_gaps、risks 或 next_actions 中标记需要人工复核。
12. 如果 manual_review.quality_acceptance 中存在人工质量验收反馈，必须优先修正其中 verdict=needs_fix/reject、checks=needs_fix/reject、notes 或 next_actions 指出的缺口；不能重复输出用户已经指出为错误或不可执行的分镜、复刻点和发布包。
13. 如果 manual_review.rerun_strategy.active=true，它就是本次重跑的硬约束：fix_targets 必须逐项回应，do_not_repeat 必须避免，required_evidence 必须进入对应分析模块；如果证据仍缺失，必须写进 evidence_gaps 和 next_actions，不要编造。

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
  "speech_analysis": {{
    "has_speech": true,
    "opening_line": "",
    "spoken_hook": "",
    "script_structure": "",
    "quotable_lines": []
  }},
  "screen_text_analysis": {{
    "cover_text_role": "",
    "subtitle_text_role": "",
    "screen_text_patterns": [],
    "text_visual_conflicts": []
  }},
  "comment_insights": {{
    "audience_needs": [],
    "comment_triggers": [],
    "high_frequency_words": [],
    "replicable_interaction_design": ""
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
  "enrichment_usage": {{
    "asr_used": false,
    "ocr_used": false,
    "comments_used": false,
    "notes": []
  }},
  "evidence_summary": {{
    "visual_input_mode": "multi_image|contact_sheet_only|text_only",
    "visual_evidence": [
      {{"claim": "画面/节奏结论", "evidence": "来自哪张图或哪个时间段", "confidence": "high|medium|low"}}
    ],
    "asr_evidence": [
      {{"claim": "口播/脚本结论", "evidence": "ASR 原文或时间段", "confidence": "high|medium|low"}}
    ],
    "ocr_evidence": [
      {{"claim": "字幕/封面字结论", "evidence": "OCR 识别文字", "confidence": "high|medium|low"}}
    ],
    "comment_evidence": [
      {{"claim": "用户需求/互动结论", "evidence": "评论高频词或典型评论", "confidence": "high|medium|low"}}
    ],
    "inferred_points": ["证据不足但合理推断的点"],
    "evidence_gaps": ["缺少哪些素材会影响判断"]
  }},
  "risks": [],
  "next_actions": []
}}

素材包结构化信息：
{json.dumps(payload, ensure_ascii=False, indent=2)}

可用富化信息概览：
{json.dumps(enrichment, ensure_ascii=False, indent=2)}

人工工作表、质量验收与人工摘要：
{json.dumps(manual_review or {}, ensure_ascii=False, indent=2)}
"""


def _compact_text_prompt(
    metadata: dict,
    ffprobe: dict,
    analysis_input: dict,
    analysis_context: dict,
    manual_review: dict | None = None,
) -> str:
    stats = analysis_input.get("stats") or {}
    video = analysis_input.get("video") or {}
    payload = {
        "title": metadata.get("title") or analysis_input.get("title") or "",
        "author": metadata.get("author") or analysis_input.get("author") or "",
        "source_url": metadata.get("source_url") or analysis_input.get("source_url") or "",
        "stats": {
            "like_count": stats.get("like_count", 0),
            "comment_count": stats.get("comment_count", 0),
            "share_count": stats.get("share_count", 0),
            "engagement_score": stats.get("engagement_score", 0),
        },
        "video": {
            "duration": video.get("duration") or ffprobe.get("duration") or 0,
            "width": video.get("width") or ffprobe.get("width") or 0,
            "height": video.get("height") or ffprobe.get("height") or 0,
            "file_size": video.get("file_size") or ffprobe.get("file_size") or 0,
        },
        "content_category": analysis_input.get("content_category") or analysis_context.get("category_id") or "generic",
        "content_category_label": (
            analysis_input.get("content_category_label") or analysis_context.get("label") or "通用短视频"
        ),
        "analysis_lens": (analysis_context.get("analysis_lens") or analysis_input.get("analysis_lens") or [])[:5],
        "key_questions": (analysis_context.get("key_questions") or analysis_input.get("key_questions") or [])[:5],
        "analysis_enrichment": analysis_input.get("analysis_enrichment") or {},
        "manual_review": manual_review or {},
    }
    return f"""请做一次短视频案例的文本降级拆解。

本次视觉图片输入调用失败，你没有成功读取 contact_sheet.jpg 或 keyframes。
请只基于以下标题、互动数据、视频参数和分析方向输出结论，并在 summary 或 risks 中明确说明视觉判断需要人工复核。
即使是文本降级拆解，也要尽量满足质量门槛：confidence 不要虚高；first_3_seconds、visual_analysis、timeline 和 shot_table 中凡是涉及画面的内容都必须标记为推断或需要复核；publish_package 不能只有标题，还要给 caption、hashtags 或 pinned_comment；replication.avoid_copying 或 risks 必须说明不要照搬和替代表达。replication.copyable_points 必须来自标题、互动数据、富化文本或人工工作表；shot_table 不得凭空新增画面镜头，只能写“文本降级推断/需要人工复核”的保守分镜。
如果 manual_review 中有人工工作表内容，请把它作为用户观察和校对意见使用；但所有画面结论仍需标记为文本降级推断或需要复核。
如果 manual_review.quality_acceptance 中有人工质量验收反馈，请优先修正用户指出的 needs_fix/reject 检查项、备注和下一步处理，不要重复输出已经被人工判定为不可执行的内容。
如果 manual_review.rerun_strategy.active=true，请按 rerun_strategy.fix_targets / do_not_repeat / required_evidence 修正输出；文本降级时缺失的证据也必须写入 evidence_gaps。

只输出合法 JSON，不要 Markdown。JSON 字段：
{{
  "summary": "",
  "content_category": "",
  "content_category_label": "",
  "confidence": 0.0,
  "engagement_data_quality": "ok|missing|partial",
  "hook_analysis": {{"first_impression": "", "why_stop_scrolling": "", "first_3_seconds": [], "optimization": ""}},
  "visual_analysis": {{"scene": "", "subject": "", "composition": "", "lighting_color": "", "movement_rhythm": "", "style_keywords": []}},
  "copywriting_analysis": {{"title_click_reason": "", "subtitle_or_text_role": "", "comment_trigger": "", "reusable_patterns": []}},
  "speech_analysis": {{"has_speech": false, "opening_line": "", "spoken_hook": "", "script_structure": "", "quotable_lines": []}},
  "screen_text_analysis": {{"cover_text_role": "", "subtitle_text_role": "", "screen_text_patterns": [], "text_visual_conflicts": []}},
  "comment_insights": {{"audience_needs": [], "comment_triggers": [], "high_frequency_words": [], "replicable_interaction_design": ""}},
  "emotion_path": [],
  "content_ratio": [],
  "timeline": [],
  "replication": {{"copyable_points": [], "avoid_copying": [], "remake_angle": "", "opening_3s": "", "shot_table": []}},
  "publish_package": {{"titles": [], "caption": "", "hashtags": [], "pinned_comment": ""}},
  "enrichment_usage": {{"asr_used": false, "ocr_used": false, "comments_used": false, "notes": []}},
  "evidence_summary": {{
    "visual_input_mode": "text_only",
    "visual_evidence": [],
    "asr_evidence": [],
    "ocr_evidence": [],
    "comment_evidence": [],
    "inferred_points": ["本次没有成功读取视觉图片，视觉拆解需要人工复核"],
    "evidence_gaps": ["缺少可用视觉输入"]
  }},
  "risks": [],
  "next_actions": []
}}

输入：
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def _should_degrade_llm_error(error: AppError) -> bool:
    return error.code in {ErrorCode.LLM_REQUEST_FAILED, ErrorCode.LLM_RESPONSE_INVALID}


def _normalize_result(
    result: dict,
    metadata: dict,
    ffprobe: dict,
    analysis_input: dict,
    analysis_context: dict,
    visual_input_mode: str,
    manual_review: dict | None = None,
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
    normalized["confidence"] = _normalize_model_confidence(normalized.get("confidence"))
    normalized.setdefault("hook_analysis", {})
    normalized.setdefault("visual_analysis", {})
    normalized.setdefault("copywriting_analysis", {})
    normalized.setdefault("speech_analysis", {})
    normalized.setdefault("screen_text_analysis", {})
    normalized.setdefault("comment_insights", {})
    normalized.setdefault("emotion_path", [])
    normalized.setdefault("content_ratio", [])
    normalized.setdefault("timeline", [])
    normalized.setdefault("replication", {})
    normalized.setdefault("publish_package", {})
    normalized.setdefault("enrichment_usage", _default_enrichment_usage(analysis_input))
    _normalize_structured_fields(normalized)
    normalized["manual_review_context"] = _normalize_manual_review_context(manual_review)
    normalized["evidence_summary"] = _normalize_evidence_summary(
        normalized.get("evidence_summary"),
        analysis_input,
        visual_input_mode,
    )
    normalized["enrichment_usage"] = _normalize_enrichment_usage(
        normalized.get("enrichment_usage"),
        analysis_input,
        normalized["evidence_summary"],
    )
    normalized.setdefault("risks", [])
    normalized.setdefault("next_actions", [])
    _align_detection_flags_with_evidence(normalized)
    _annotate_unbacked_enrichment_insights(normalized)
    _annotate_unused_available_enrichment(normalized)
    normalized["enrichment_coverage"] = _build_enrichment_coverage(normalized, analysis_input)
    normalized["rerun_compliance"] = _build_rerun_compliance(normalized)
    normalized["source"] = _normalize_source_payload(normalized.get("source"), metadata, ffprobe, analysis_input)
    normalized["rerun_compliance"] = _build_rerun_compliance(normalized)
    normalized["quality_review"] = _analysis_quality_review(normalized)
    return normalized


def _normalize_source_payload(source, metadata: dict, ffprobe: dict, analysis_input: dict) -> dict:
    existing = source if isinstance(source, dict) else {}
    video = analysis_input.get("video") if isinstance(analysis_input.get("video"), dict) else {}
    width = video.get("width") or ffprobe.get("width") or 0
    height = video.get("height") or ffprobe.get("height") or 0
    return {
        **existing,
        "title": existing.get("title") or metadata.get("title") or analysis_input.get("title") or "",
        "author": existing.get("author") or metadata.get("author") or analysis_input.get("author") or "",
        "source_url": existing.get("source_url") or metadata.get("source_url") or analysis_input.get("source_url") or "",
        "duration": existing.get("duration") or video.get("duration") or ffprobe.get("duration") or 0,
        "resolution": existing.get("resolution") or f"{width}x{height}",
    }


def _normalize_structured_fields(result: dict) -> None:
    _coerce_object_field(result, "hook_analysis", "first_impression")
    _coerce_object_field(result, "visual_analysis", "scene")
    _coerce_object_field(result, "copywriting_analysis", "title_click_reason")
    _coerce_object_field(result, "speech_analysis", "script_structure")
    _coerce_object_field(result, "screen_text_analysis", "subtitle_text_role")
    _coerce_object_field(result, "comment_insights", "replicable_interaction_design")
    _coerce_object_field(result, "replication", "remake_angle")
    _coerce_object_field(result, "publish_package", "caption")
    _coerce_object_field(result, "enrichment_usage", "notes")

    result["emotion_path"] = _coerce_list(result.get("emotion_path"))
    result["content_ratio"] = _coerce_content_ratio(result.get("content_ratio"))
    result["timeline"] = _coerce_list(result.get("timeline"))
    result["risks"] = _coerce_list(result.get("risks"))
    result["next_actions"] = _coerce_list(result.get("next_actions"))

    hook = result["hook_analysis"]
    hook["first_3_seconds"] = _coerce_list(hook.get("first_3_seconds"))

    visual = result["visual_analysis"]
    visual["style_keywords"] = _coerce_list(visual.get("style_keywords"))

    copywriting = result["copywriting_analysis"]
    copywriting["reusable_patterns"] = _coerce_list(copywriting.get("reusable_patterns"))

    speech = result["speech_analysis"]
    speech["quotable_lines"] = _coerce_list(speech.get("quotable_lines"))

    screen_text = result["screen_text_analysis"]
    screen_text["screen_text_patterns"] = _coerce_list(screen_text.get("screen_text_patterns"))
    screen_text["text_visual_conflicts"] = _coerce_list(screen_text.get("text_visual_conflicts"))

    comments = result["comment_insights"]
    comments["audience_needs"] = _coerce_list(comments.get("audience_needs"))
    comments["comment_triggers"] = _coerce_list(comments.get("comment_triggers"))
    comments["high_frequency_words"] = _coerce_list(comments.get("high_frequency_words"))

    replication = result["replication"]
    replication["copyable_points"] = _coerce_list(replication.get("copyable_points"))
    replication["avoid_copying"] = _coerce_list(replication.get("avoid_copying"))
    replication["shot_table"] = _coerce_shot_table(replication.get("shot_table"))

    publish = result["publish_package"]
    publish["titles"] = _coerce_list(publish.get("titles"))
    publish["hashtags"] = _coerce_list(publish.get("hashtags"))

    enrichment_usage = result["enrichment_usage"]
    enrichment_usage["notes"] = _coerce_list(enrichment_usage.get("notes"))


def _coerce_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if _has_meaningful_item(item)]
    if isinstance(value, tuple):
        return [item for item in value if _has_meaningful_item(item)]
    if isinstance(value, str):
        return [item for item in _split_note_lines(value) if _has_text(item)]
    return [value]


def _coerce_content_ratio(value) -> list:
    if value is None:
        return []
    if isinstance(value, tuple):
        raw_items = list(value)
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = [value]

    items = []
    for item in raw_items:
        if isinstance(item, dict):
            normalized = dict(item)
            name = normalized.get("name") or normalized.get("dimension") or normalized.get("label") or ""
            reason = normalized.get("reason") or normalized.get("basis") or normalized.get("why") or ""
            percent = _normalize_ratio_percent(_content_ratio_percent_value(normalized))
            if _has_text(name):
                normalized["name"] = str(name).strip()
            if _has_text(reason):
                normalized["reason"] = str(reason).strip()
            if percent is not None:
                normalized["percent"] = percent
            if _has_meaningful_item(normalized):
                items.append(normalized)
            continue
        if isinstance(item, str):
            parsed = _parse_content_ratio_text(item)
            if parsed:
                items.extend(parsed)
            else:
                items.extend([part for part in _split_note_lines(item) if _has_text(part)])
            continue
        if _has_meaningful_item(item):
            items.append(item)
    return items


def _content_ratio_percent_value(item: dict):
    for key in ("percent", "percentage", "ratio"):
        if item.get(key) is not None:
            return item.get(key)
    return None


def _parse_content_ratio_text(value: str) -> list[dict]:
    text = str(value or "").strip()
    if not text:
        return []
    parsed = []
    for match in CONTENT_RATIO_RE.finditer(text):
        name = _clean_content_ratio_name(match.group("name"))
        percent = _normalize_ratio_percent(match.group("percent"))
        if not name or percent is None:
            continue
        parsed.append({"name": name, "percent": percent, "reason": ""})
    return parsed


def _clean_content_ratio_name(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = text.strip(" -•、\t，,；;：:。.!！?？")
    text = re.sub(r"(约|大约|大概|占比|占|比例|为|是)$", "", text).strip()
    return text


def _normalize_ratio_percent(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if 0 < number <= 1:
            number *= 100
    elif isinstance(value, str):
        text = value.strip()
        match = re.search(r"\d+(?:\.\d+)?", text)
        if not match:
            return None
        number = float(match.group(0))
        if "%" not in text and 0 < number <= 1:
            number *= 100
    else:
        return None
    if number <= 0:
        return None
    rounded = round(number, 2)
    return int(rounded) if rounded.is_integer() else rounded


def _coerce_object_field(result: dict, key: str, fallback_field: str) -> None:
    value = result.get(key)
    if isinstance(value, dict):
        return
    if isinstance(value, str) and value.strip():
        if fallback_field == "notes":
            result[key] = {fallback_field: _coerce_list(value)}
        else:
            result[key] = {fallback_field: value.strip()}
        return
    result[key] = {}


def _coerce_shot_table(value) -> list[dict]:
    rows = []
    if isinstance(value, list):
        raw_rows = value
    elif isinstance(value, dict):
        raw_rows = [value]
    elif isinstance(value, str):
        raw_rows = _split_note_lines(value)
    else:
        raw_rows = []

    for row in raw_rows:
        if isinstance(row, dict):
            rows.append(dict(row))
        elif isinstance(row, str) and row.strip():
            rows.append(_shot_row_from_text(row))
    return rows


def _shot_row_from_text(value: str) -> dict:
    text = value.strip()
    match = SHOT_TIME_RE.search(text)
    time_value = match.group("time").replace(" ", "") if match else ""
    detail = text
    if match:
        detail = (text[: match.start()] + text[match.end() :]).strip(" ：:-—，,")
    return {
        "time": time_value,
        "visual": detail,
        "action": "",
        "subtitle": "",
        "music_rhythm": "",
        "purpose": "复刻分镜草案",
    }


def _split_note_lines(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    parts = re.split(r"[\n\r]+|[；;]+", text)
    return [part.strip(" -•、\t") for part in parts if part.strip(" -•、\t")]


def _normalize_manual_review_context(manual_review: dict | None) -> dict:
    payload = manual_review if isinstance(manual_review, dict) else {}
    worksheet = payload.get("worksheet") if isinstance(payload.get("worksheet"), dict) else {}
    review = worksheet.get("review") if isinstance(worksheet.get("review"), dict) else {}
    quality_acceptance = (
        payload.get("quality_acceptance")
        if isinstance(payload.get("quality_acceptance"), dict)
        else {}
    )
    rerun_strategy = payload.get("rerun_strategy") if isinstance(payload.get("rerun_strategy"), dict) else {}
    rerun_evidence = rerun_strategy.get("required_evidence") if isinstance(rerun_strategy.get("required_evidence"), list) else []
    rerun_evidence_summary = (
        rerun_strategy.get("evidence_summary")
        if isinstance(rerun_strategy.get("evidence_summary"), dict)
        else _rerun_evidence_summary(rerun_evidence)
    )
    sections = []
    for section in worksheet.get("sections") or []:
        if not isinstance(section, dict):
            continue
        fields = [
            {
                "label": field.get("label") or field.get("field_id") or "",
                "has_value": bool(str(field.get("value") or "").strip()),
            }
            for field in section.get("fields") or []
            if isinstance(field, dict)
        ]
        if fields:
            sections.append(
                {
                    "title": section.get("title") or section.get("section_id") or "",
                    "filled_fields": [field["label"] for field in fields if field["has_value"]],
                }
            )
    return {
        "used": bool(payload.get("has_manual_notes")),
        "summary": worksheet.get("summary", ""),
        "worksheet_score": review.get("score", 0),
        "worksheet_level": review.get("level", ""),
        "worksheet_label": review.get("label", ""),
        "sections": sections,
        "quality_acceptance": {
            "used": bool(quality_acceptance.get("has_feedback")),
            "verdict": quality_acceptance.get("verdict", "pending"),
            "score": quality_acceptance.get("score", ""),
            "summary": quality_acceptance.get("summary", ""),
            "checks": quality_acceptance.get("checks", []),
            "notes": quality_acceptance.get("notes", ""),
            "next_actions": quality_acceptance.get("next_actions", ""),
            "quality_snapshot": quality_acceptance.get("quality_snapshot", {}),
        },
        "rerun_strategy": {
            "active": bool(rerun_strategy.get("active")),
            "priority": rerun_strategy.get("priority", "normal"),
            "summary": rerun_strategy.get("summary", ""),
            "evidence_summary": rerun_evidence_summary,
            "fix_targets": rerun_strategy.get("fix_targets", []),
            "do_not_repeat": rerun_strategy.get("do_not_repeat", []),
            "required_evidence": rerun_evidence,
            "output_requirements": rerun_strategy.get("output_requirements", []),
        },
    }


def _build_rerun_compliance(result: dict) -> dict:
    manual_context = result.get("manual_review_context") if isinstance(result.get("manual_review_context"), dict) else {}
    strategy = (
        manual_context.get("rerun_strategy")
        if isinstance(manual_context.get("rerun_strategy"), dict)
        else {}
    )
    if not strategy.get("active"):
        return {
            "active": False,
            "status": "not_required",
            "score": 100,
            "summary": "当前没有启用带反馈重跑策略。",
            "checks": [],
            "blocking_count": 0,
        }

    checks: list[dict] = []
    for item in strategy.get("required_evidence") or []:
        if isinstance(item, dict):
            checks.append(_rerun_required_evidence_compliance(result, item))
    for item in strategy.get("fix_targets") or []:
        if isinstance(item, dict):
            checks.append(_rerun_fix_target_compliance(result, item))
    if strategy.get("output_requirements"):
        checks.append(_rerun_output_requirements_compliance(result, strategy.get("output_requirements") or []))

    blocking = [check for check in checks if not check.get("passed")]
    score = int(round((sum(1 for check in checks if check.get("passed")) / len(checks)) * 100)) if checks else 100
    status = "passed" if not blocking else "needs_attention"
    return {
        "active": True,
        "status": status,
        "score": score,
        "summary": (
            "本次输出已回应重跑策略。"
            if status == "passed"
            else f"本次输出仍有 {len(blocking)} 个重跑约束没有满足。"
        ),
        "checks": checks,
        "blocking_count": len(blocking),
    }


def _rerun_required_evidence_compliance(result: dict, item: dict) -> dict:
    evidence_id = str(item.get("id") or "").strip()
    label = str(item.get("label") or evidence_id or "必需证据").strip()
    status = str(item.get("status") or "").strip()
    ready_statuses = {"success", "no_speech", "no_text"}
    missing_statuses = {"missing", "provider_missing", "pending", "disabled", "not_configured", "failed", ""}
    if status in ready_statuses:
        passed, message, action = _ready_rerun_evidence_used(result, evidence_id, status, label)
    elif status in missing_statuses or status not in ready_statuses:
        passed = _missing_rerun_evidence_acknowledged(result, evidence_id, label)
        message = (
            f"已把缺失的{label}写入证据缺口或下一步。"
            if passed
            else f"重跑策略要求说明缺失的{label}，但报告没有明确标记这个缺口。"
        )
        action = f"在 evidence_gaps、risks 或 next_actions 中明确写出{label}缺失，并避免编造相关结论。"
    else:
        passed = False
        message = f"{label}状态无法识别。"
        action = f"复核{label}状态后重跑。"
    return {
        "id": f"required_evidence:{evidence_id or label}",
        "label": f"必需证据：{label}",
        "source": "required_evidence",
        "passed": passed,
        "message": message,
        "action": action,
        "evidence_id": evidence_id,
        "status": status,
    }


def _ready_rerun_evidence_used(result: dict, evidence_id: str, status: str, label: str) -> tuple[bool, str, str]:
    evidence = result.get("evidence_summary") if isinstance(result.get("evidence_summary"), dict) else {}
    usage = result.get("enrichment_usage") if isinstance(result.get("enrichment_usage"), dict) else {}
    checks = {
        "asr": (
            _has_items(evidence.get("asr_evidence")),
            bool(usage.get("asr_used")) or status == "no_speech",
            _has_insight_content(result.get("speech_analysis")) or status == "no_speech",
            "ASR 转写已就绪，但报告没有把它写入 ASR 证据、使用标记或口播拆解。",
            "基于 ASR 转写补齐 speech_analysis，并在 evidence_summary.asr_evidence 中列出依据。",
        ),
        "ocr": (
            _has_items(evidence.get("ocr_evidence")),
            bool(usage.get("ocr_used")) or status == "no_text",
            _has_insight_content(result.get("screen_text_analysis")) or status == "no_text",
            "OCR 文字已就绪，但报告没有把它写入 OCR 证据、使用标记或画面文字拆解。",
            "基于 OCR 结果补齐 screen_text_analysis，并在 evidence_summary.ocr_evidence 中列出依据。",
        ),
        "comments": (
            _has_items(evidence.get("comment_evidence")),
            bool(usage.get("comments_used")),
            _has_insight_content(result.get("comment_insights")),
            "评论摘要已就绪，但报告没有把它写入评论证据、使用标记或评论洞察。",
            "基于评论摘要补齐 comment_insights，并在 evidence_summary.comment_evidence 中列出依据。",
        ),
    }
    evidence_ready, usage_ready, insight_ready, fail_message, action = checks.get(
        evidence_id,
        (
            _has_usable_evidence_summary(evidence),
            True,
            True,
            f"{label}已就绪，但报告没有形成可追溯证据。",
            f"把{label}写入 evidence_summary，并关联到对应分析模块。",
        ),
    )
    passed = bool(evidence_ready and usage_ready and insight_ready)
    message = f"{label}已进入证据链和对应拆解模块。" if passed else fail_message
    return passed, message, action


def _missing_rerun_evidence_acknowledged(result: dict, evidence_id: str, label: str) -> bool:
    terms = {
        "asr": ("ASR", "口播", "语音", "转写"),
        "ocr": ("OCR", "字幕", "封面字", "画面文字"),
        "comments": ("评论", "用户反馈", "受众", "互动"),
    }.get(evidence_id, (label, evidence_id))
    return _result_mentions_any(
        result,
        terms,
        fields=("evidence_gaps", "risks", "next_actions"),
    )


def _rerun_fix_target_compliance(result: dict, item: dict) -> dict:
    target_id = str(item.get("id") or "").strip()
    label = str(item.get("label") or target_id or "修正目标").strip()
    evidence = result.get("evidence_summary") if isinstance(result.get("evidence_summary"), dict) else {}
    replication = result.get("replication") if isinstance(result.get("replication"), dict) else {}
    publish = result.get("publish_package") if isinstance(result.get("publish_package"), dict) else {}
    if target_id == "summary_matches_video":
        passed = _has_usable_summary(result.get("summary")) and _has_traceable_core_claims(result, evidence)
        message = "总结已具备可追溯依据。" if passed else "人工要求修正总结可信度，但总结仍不够具体或缺少证据对应。"
        action = "把总结改成基于视觉/ASR/OCR/评论证据的具体判断。"
    elif target_id == "evidence_is_sufficient":
        passed = _has_usable_evidence_summary(evidence) and not _has_items(evidence.get("evidence_gaps"))
        message = "证据链已补齐。" if passed else "人工要求补足证据，但报告仍有证据缺口或证据链不足。"
        action = "补齐视觉、ASR、OCR 或评论证据；无法补齐时要明确保留为 evidence_gaps。"
    elif target_id == "copyable_points_are_useful":
        passed = _has_items(replication.get("copyable_points")) and _has_traceable_copyable_points(result, evidence)
        message = "可复刻点已有来源依据。" if passed else "可复刻点仍不够可追溯或不够具体。"
        action = "为每条可复刻点补对应证据，删掉无法追溯的泛化建议。"
    elif target_id == "shot_table_is_actionable":
        passed = _has_usable_shot_table(replication.get("shot_table")) and _has_traceable_shot_table(result, evidence)
        message = "分镜表可执行且能对应原视频证据。" if passed else "人工要求修正分镜表，但分镜仍不可执行或缺少来源对应。"
        action = "补齐有时间、画面、动作、字幕/节奏和目的的分镜，并确保来自原视频时间线或证据。"
    elif target_id == "publish_package_is_usable":
        passed = _has_usable_publish_package(publish)
        message = "发布包具备标题和落地文案/标签/评论。" if passed else "发布包仍不够可直接落地。"
        action = "补齐标题候选、发布文案、标签或置顶评论。"
    else:
        passed = _result_mentions_any(result, (label, target_id), fields=("summary", "risks", "next_actions"))
        message = f"报告已回应修正目标：{label}。" if passed else f"报告没有明确回应修正目标：{label}。"
        action = f"在 summary、risks 或 next_actions 中明确回应：{label}。"
    return {
        "id": f"fix_target:{target_id or label}",
        "label": f"修正目标：{label}",
        "source": "fix_targets",
        "passed": passed,
        "message": message,
        "action": action,
        "target_id": target_id,
    }


def _rerun_output_requirements_compliance(result: dict, requirements: list) -> dict:
    passed = _has_items(result.get("next_actions"))
    return {
        "id": "output_requirements:next_actions",
        "label": "输出要求：下一步说明",
        "source": "output_requirements",
        "passed": passed,
        "message": "报告包含下一步动作。" if passed else "重跑策略要求说明仍缺什么和下一步，但报告没有 next_actions。",
        "action": "补齐 next_actions，说明仍缺什么、下一步补哪类证据或改哪类输出。",
        "requirements": requirements,
    }


def _result_mentions_any(result: dict, terms: tuple[str, ...] | list[str], fields: tuple[str, ...]) -> bool:
    if not terms:
        return False
    haystack_parts = []
    evidence = result.get("evidence_summary") if isinstance(result.get("evidence_summary"), dict) else {}
    for field in fields:
        if field in {"evidence_gaps", "inferred_points"}:
            haystack_parts.append(json.dumps(evidence.get(field) or [], ensure_ascii=False))
        else:
            haystack_parts.append(json.dumps(result.get(field) or "", ensure_ascii=False))
    haystack = " ".join(haystack_parts)
    return any(str(term or "").strip() and str(term).strip() in haystack for term in terms)


def _analysis_quality_review(result: dict) -> dict:
    hook = result.get("hook_analysis") or {}
    visual = result.get("visual_analysis") or {}
    copywriting = result.get("copywriting_analysis") or {}
    speech = result.get("speech_analysis") or {}
    screen_text = result.get("screen_text_analysis") or {}
    comments = result.get("comment_insights") or {}
    evidence = result.get("evidence_summary") or {}
    enrichment_coverage = result.get("enrichment_coverage") or _fallback_enrichment_coverage(result)
    coverage_summary = enrichment_coverage.get("summary") or {}
    rerun_compliance = result.get("rerun_compliance") if isinstance(result.get("rerun_compliance"), dict) else {}
    visual_input_mode = str(evidence.get("visual_input_mode") or "")
    has_visual_input = visual_input_mode in {"multi_image", "contact_sheet_only"}
    asr_checked_no_speech = _evidence_mentions(evidence.get("asr_evidence"), "未检测到可转写语音")
    ocr_checked_no_text = _evidence_mentions(evidence.get("ocr_evidence"), "未检测到封面字")
    checked_visual_only = asr_checked_no_speech and ocr_checked_no_text
    has_comment_evidence = _has_items(evidence.get("comment_evidence"))
    evidence_gap_issues = _evidence_gap_issues(evidence)
    replication = result.get("replication") or {}
    publish = result.get("publish_package") or {}
    time_bound_issues = _time_bound_issues(result)
    content_ratio_issues = _content_ratio_balance_issues(result.get("content_ratio"))
    category_alignment_issues = _content_category_alignment_issues(result)
    emotion_path_issues = _emotion_path_issues(result.get("emotion_path"))
    engagement_data_issues = _engagement_data_quality_issues(result)
    audience_issues = _audience_quality_issues(evidence, comments)
    claim_traceability_issues = _core_claim_traceability_issues(result, evidence)
    evidence_confidence_issues = _low_confidence_evidence_issues(evidence)
    summary_issues = _summary_quality_issues(result.get("summary"))
    hook_issues = _hook_quality_issues(hook)
    copyable_issues = _copyable_point_quality_issues(result, evidence)
    shot_table_issues = _shot_table_quality_issues(result, evidence)
    publish_issues = _publish_package_quality_issues(publish)
    visual_issues = _visual_analysis_quality_issues(visual, result.get("timeline"))

    checks = [
        {
            "id": "summary",
            "label": "一句话总结",
            "weight": 10,
            "passed": not summary_issues,
            "message": "是否给出可直接理解的视频价值判断。",
            "action": "补一句清晰总结：这条视频为什么值得学、核心爆点是什么。",
            "details": summary_issues[:8],
        },
        {
            "id": "hook",
            "label": "前 3 秒钩子",
            "weight": 15,
            "passed": not hook_issues,
            "message": "是否拆出第一眼、停留理由，以及至少两条 0-3 秒观察。",
            "action": "重跑或手动补齐 0-3 秒逐秒观察，至少写出两个时间点的画面/文字/动作变化。",
            "details": hook_issues[:8],
        },
        {
            "id": "visual",
            "label": "视觉节奏",
            "weight": 15,
            "passed": not visual_issues,
            "message": "是否至少覆盖场景/主体/构图/运动节奏中的两类信息，并给出关键时间线。",
            "action": "补充画面主体、景别变化、动作节奏和关键时间线；避免只写“室内”“人物”等泛泛描述。",
            "details": visual_issues[:8],
        },
        {
            "id": "copy_speech_text",
            "label": "文案/口播/字幕",
            "weight": 15,
            "passed": any(
                [
                    _has_usable_copy_text(copywriting.get("title_click_reason")),
                    _has_usable_copy_text(copywriting.get("subtitle_or_text_role")),
                    _has_usable_copy_text(speech.get("opening_line")),
                    _has_usable_copy_text(screen_text.get("cover_text_role")),
                    _has_usable_copy_text(screen_text.get("subtitle_text_role")),
                ]
            )
            or checked_visual_only,
            "message": "是否覆盖标题、字幕、口播、画面文字，或确认这条内容主要依赖纯视觉表达。",
            "action": "补齐标题点击理由、字幕作用、口播开头或封面字作用；若是纯视觉作品，请先完成 ASR/OCR 空内容检测。",
        },
        {
            "id": "audience",
            "label": "受众与评论反馈",
            "weight": 10,
            "passed": has_comment_evidence
            and (
                _has_usable_audience_items(comments.get("audience_needs"))
                or _has_usable_audience_items(comments.get("comment_triggers"))
                or _has_usable_audience_text(comments.get("replicable_interaction_design"))
            ),
            "message": "是否说明观众为什么互动、评论区暴露了什么需求。",
            "action": "导入评论后重跑，或把这部分标记为基于内容结构的推断。",
            "details": audience_issues[:8],
        },
        {
            "id": "evidence",
            "label": "证据与推断边界",
            "weight": 15,
            "passed": bool(evidence)
            and _has_usable_evidence_summary(evidence),
            "message": "是否标明结论来自画面、ASR、OCR、评论，还是推断。",
            "action": "补齐 ASR/OCR/评论或要求模型明确列出证据来源和证据缺口。",
        },
        {
            "id": "enrichment_usage",
            "label": "富化证据使用",
            "weight": 0,
            "passed": int(coverage_summary.get("blocking_count") or 0) == 0,
            "message": "ASR、OCR、评论可用时，报告是否真正用于对应拆解模块，而不是只列在素材里。",
            "action": "优先处理富化证据覆盖里的阻塞项：可用未使用、输出洞察但无证据、或 provider 成功却内容为空。",
        },
        {
            "id": "rerun_compliance",
            "label": "重跑策略兑现",
            "weight": 0,
            "passed": not rerun_compliance.get("active") or rerun_compliance.get("status") == "passed",
            "message": "带反馈重跑时，是否真正回应人工修正目标、必需证据和输出要求。",
            "action": "按 rerun_compliance 中未通过的检查项修正报告；缺证据时先补证据，不要编造结论。",
        },
        {
            "id": "claim_traceability",
            "label": "结论证据对应",
            "weight": 0,
            "passed": not claim_traceability_issues,
            "message": "总结里的视觉、口播、字幕或评论判断是否能在对应证据里找到依据。",
            "action": "把总结中的核心判断分别补上视觉/ASR/OCR/评论证据；没有证据的判断应移入推断点。",
            "details": claim_traceability_issues[:8],
        },
        {
            "id": "visual_input",
            "label": "视觉输入",
            "weight": 0,
            "passed": has_visual_input,
            "message": "是否真实读取 contact sheet 或关键帧，而不是只靠文本字段推断画面。",
            "action": "重新生成 contact_sheet/keyframes 并使用支持图片输入的模型重跑拆解。",
        },
        {
            "id": "evidence_gaps",
            "label": "证据缺口",
            "weight": 0,
            "passed": not evidence_gap_issues,
            "message": "是否还存在会影响结论可信度的证据缺口。",
            "action": "优先补齐证据缺口，或在复刻方案里明确哪些判断需要人工复核。",
            "details": evidence_gap_issues[:8],
        },
        {
            "id": "evidence_confidence",
            "label": "证据置信度",
            "weight": 0,
            "passed": not evidence_confidence_issues,
            "message": "关键证据是否避免使用 low 置信度依据支撑核心结论。",
            "action": "补充更可靠的视觉/ASR/OCR/评论证据，或把低置信结论移入推断点并标记需要人工复核。",
            "details": evidence_confidence_issues[:8],
        },
        {
            "id": "model_confidence",
            "label": "模型整体置信度",
            "weight": 0,
            "passed": _has_usable_model_confidence(result.get("confidence")),
            "message": "模型是否对整份拆解给出足够置信度。",
            "action": "如果 confidence 偏低或缺失，请补齐素材证据后重跑，或把报告作为草稿人工复核。",
        },
        {
            "id": "engagement_data",
            "label": "互动数据边界",
            "weight": 0,
            "passed": not engagement_data_issues,
            "message": "点赞、评论、分享是否足以支撑真实爆款强度判断。",
            "action": "补齐作品链接互动数据或指标快照；缺失时只能判断内容结构，不能下真实爆款强度结论。",
            "details": engagement_data_issues[:8],
        },
        {
            "id": "structure_depth",
            "label": "结构与情绪路径",
            "weight": 0,
            "passed": not emotion_path_issues
            and _has_usable_content_ratio(result.get("content_ratio")),
            "message": "是否说明情绪推进，并给出可解释的内容占比。",
            "action": "补齐开头/中段/结尾的情绪路径，以及带原因的内容占比，避免只输出单点结论。",
            "details": emotion_path_issues[:8],
        },
        {
            "id": "content_ratio_balance",
            "label": "内容占比自洽",
            "weight": 0,
            "passed": not content_ratio_issues,
            "message": "内容占比是否覆盖完整结构，总和是否接近 100%，并说明每个比例的依据。",
            "action": "把 content_ratio 改成 2-5 个结构段，percent 总和约 100%，每项写清 reason。",
            "details": content_ratio_issues[:8],
        },
        {
            "id": "category_alignment",
            "label": "内容类型适配",
            "weight": 0,
            "passed": not category_alignment_issues,
            "message": "拆解维度是否贴合当前内容类型，而不是套用通用钩子/主体/互动模板。",
            "action": "按当前内容类型重写 content_ratio、analysis_lens 和复刻重点，至少覆盖两个类型核心维度。",
            "details": category_alignment_issues[:8],
        },
        {
            "id": "adaptation_boundary",
            "label": "改编边界",
            "weight": 0,
            "passed": _has_usable_boundary_items(replication.get("avoid_copying"))
            or _has_usable_boundary_items(result.get("risks")),
            "message": "是否说明哪些地方不要照搬，或给出风险与替代表达。",
            "action": "补齐不要照搬的元素、潜在尺度/版权/搬运风险，以及更适合自己账号的替代表达。",
        },
        {
            "id": "replication",
            "label": "复刻可执行性",
            "weight": 15,
            "passed": _has_text(replication.get("remake_angle"))
            and _has_text(replication.get("opening_3s"))
            and _has_items(replication.get("copyable_points"))
            and _has_usable_shot_table(replication.get("shot_table")),
            "message": "是否给出复刻角度、前三秒改编、可借鉴点和分镜表。",
            "action": "补齐可复刻脚本，尤其是 opening_3s，以及包含时间、画面、动作/字幕/节奏/目的的可拍摄分镜表。",
        },
        {
            "id": "shot_table_traceability",
            "label": "分镜表来源对应",
            "weight": 0,
            "passed": not shot_table_issues,
            "message": "分镜表里的画面、动作、字幕或节奏是否能对应到原视频时间线、证据或已验证的复刻点。",
            "action": "把分镜表改写为基于原视频时间线和证据的拍摄步骤；凭空新增的镜头应标记为创意扩展或移出复刻表。",
            "details": shot_table_issues[:8],
        },
        {
            "id": "time_bounds",
            "label": "时间边界",
            "weight": 0,
            "passed": not time_bound_issues,
            "message": "前 3 秒、时间线和分镜表里的时间点是否落在原视频时长范围内。",
            "action": "把越界时间点改回原视频实际范围；超出原片时长的创意扩展请移入 risks 或 next_actions。",
            "details": time_bound_issues[:8],
        },
        {
            "id": "copyable_traceability",
            "label": "可复刻点可追溯",
            "weight": 0,
            "passed": not copyable_issues,
            "message": "可借鉴点是否能在钩子、画面、口播、字幕、评论或证据链中找到来源。",
            "action": "为每条可借鉴点补充对应依据；无法追溯的点应删掉、改写，或移入推断点。",
            "details": copyable_issues[:8],
        },
        {
            "id": "publishing",
            "label": "发布落地",
            "weight": 5,
            "passed": not publish_issues,
            "message": "是否给出标题，并配套发布文案、标签或置顶评论中的至少一类。",
            "action": "补齐标题候选，并至少补一项发布文案、标签或置顶评论，方便直接落地发布。",
            "details": publish_issues[:8],
        },
    ]
    score = sum(check["weight"] for check in checks if check["passed"])
    gaps = [check for check in checks if not check["passed"]]
    has_visual_input_gap = any(gap["id"] == "visual_input" for gap in gaps)
    if score >= 85 and not gaps:
        level = "strong"
        label = "拆解质量较完整"
        summary = "报告覆盖了钩子、视觉、文案、证据和复刻方案，可直接进入人工筛选与改编。"
    elif has_visual_input_gap and score >= 50:
        level = "needs_review"
        label = "缺少视觉输入"
        summary = "报告缺少真实关键帧或 contact sheet 视觉输入，画面节奏和复刻判断必须人工复核。"
    elif score >= 70:
        level = "usable"
        label = "可用但建议复核"
        summary = "报告主体可用，但仍有少量模块需要人工复核或补数据。"
    elif score >= 50:
        level = "needs_review"
        label = "需要补充后再用"
        summary = "报告有基础结论，但缺少关键拆解模块，建议补齐后重跑。"
    else:
        level = "weak"
        label = "拆解质量不足"
        summary = "报告缺少多项核心内容，不建议直接作为复刻依据。"
    return {
        "score": score,
        "max_score": 100,
        "level": level,
        "label": label,
        "summary": summary,
        "checks": checks,
        "gaps": gaps,
        "next_actions": [gap["action"] for gap in gaps[:4]],
    }


def _normalize_evidence_summary(existing: dict | None, analysis_input: dict, visual_input_mode: str) -> dict:
    defaults = _default_evidence_summary(analysis_input, visual_input_mode)
    payload = existing if isinstance(existing, dict) else {}
    normalized = {"visual_input_mode": visual_input_mode}
    visual_values = _coerce_evidence_items(payload.get("visual_evidence"), "视觉证据")
    payload_visual_mode = str(payload.get("visual_input_mode") or visual_input_mode)
    can_preserve_visual_values = visual_input_mode == "multi_image" or (
        visual_input_mode == "contact_sheet_only" and payload_visual_mode != "multi_image"
    )
    if can_preserve_visual_values and visual_values:
        normalized["visual_evidence"] = visual_values
    else:
        normalized["visual_evidence"] = list(defaults.get("visual_evidence", []))
    for key, label in (
        ("asr_evidence", "ASR 证据"),
        ("ocr_evidence", "OCR 证据"),
        ("comment_evidence", "评论证据"),
    ):
        values = _coerce_evidence_items(payload.get(key), label)
        normalized[key] = (
            values if values and _evidence_source_available(key, analysis_input) else list(defaults.get(key, []))
        )
    inferred_values = _coerce_list(payload.get("inferred_points"))
    normalized["inferred_points"] = inferred_values if inferred_values else list(defaults.get("inferred_points", []))
    normalized["evidence_gaps"] = _coerce_list(payload.get("evidence_gaps"))
    for gap in defaults.get("evidence_gaps", []):
        if gap not in normalized["evidence_gaps"]:
            normalized["evidence_gaps"].append(gap)
    return normalized


def _evidence_source_available(key: str, analysis_input: dict) -> bool:
    enrichment = analysis_input.get("analysis_enrichment") or {}
    if key == "asr_evidence":
        asr = enrichment.get("asr") or {}
        return _has_text(asr.get("full_text"))
    if key == "ocr_evidence":
        ocr = enrichment.get("ocr") or {}
        return any(_has_text(ocr.get(field)) for field in ("cover_text", "subtitle_text", "frame_text"))
    if key == "comment_evidence":
        comments = enrichment.get("comments") or {}
        return any(_has_items(comments.get(field)) for field in ("top_needs", "high_frequency_words", "comment_hooks"))
    return True


def _coerce_evidence_items(value, default_claim: str) -> list[dict]:
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else [value]
    items = []
    for item in raw_items:
        if isinstance(item, dict):
            raw_evidence = str(item.get("evidence") or item.get("text") or item.get("value") or "").strip()
            raw_claim = str(item.get("claim") or "").strip()
            evidence = raw_evidence if _has_text(raw_evidence) else ""
            claim = raw_claim if _has_text(raw_claim) else default_claim
            confidence = str(item.get("confidence") or "medium").strip().lower()
            if confidence not in {"high", "medium", "low"}:
                confidence = "medium"
            if evidence:
                normalized = dict(item)
                normalized["claim"] = claim
                normalized["evidence"] = evidence
                normalized["confidence"] = confidence
                items.append(normalized)
        elif isinstance(item, str) and _has_text(item):
            items.append({"claim": default_claim, "evidence": item.strip(), "confidence": "medium"})
    return items


def _default_evidence_summary(analysis_input: dict, visual_input_mode: str) -> dict:
    enrichment = analysis_input.get("analysis_enrichment") or {}
    asr = enrichment.get("asr") or {}
    ocr = enrichment.get("ocr") or {}
    comments = enrichment.get("comments") or {}
    assets = analysis_input.get("assets") or {}
    keyframes = assets.get("keyframes") or []
    visual_evidence = []
    evidence_gaps = []
    inferred_points = []
    if visual_input_mode == "text_only":
        inferred_points.append("本次降级为文本拆解，视觉相关结论需要人工复核。")
        evidence_gaps.append("缺少可用视觉输入。")
    elif visual_input_mode == "contact_sheet_only":
        visual_evidence.append(
            {
                "claim": "整体画面节奏和关键帧变化",
                "evidence": "模型收到 contact_sheet.jpg，但未使用逐张关键帧。",
                "confidence": "medium",
            }
        )
        evidence_gaps.append("只使用 contact_sheet，细节动作和字幕位置可能需要人工复核。")
    elif keyframes:
        visual_evidence.append(
            {
                "claim": "画面主体、节奏和分镜判断",
                "evidence": f"模型收到 contact_sheet.jpg 和 {len(keyframes)} 张关键帧。",
                "confidence": "high",
            }
        )
    else:
        evidence_gaps.append("关键帧列表为空，视觉拆解依据不足。")

    asr_status = asr.get("status") or ""
    asr_text = str(asr.get("full_text") or "").strip()
    asr_evidence = []
    if _has_text(asr_text):
        asr_evidence.append(
            {
                "claim": "口播/脚本结构判断",
                "evidence": _truncate(asr_text, 160),
                "confidence": "high",
            }
        )
    elif asr_status == "no_speech":
        asr_evidence.append(
            {
                "claim": "口播/脚本结构判断",
                "evidence": "ASR 已完成，未检测到可转写语音；本条更适合按画面、音乐和文字信息拆解。",
                "confidence": "high",
            }
        )
    elif asr_status == "success":
        evidence_gaps.append("ASR 已完成但转写文本为空或无效，请复核音频。")
    else:
        evidence_gaps.append("未提供 ASR 转写，口播和声音节奏判断可能不完整。")

    ocr_status = ocr.get("status") or ""
    ocr_text = " / ".join(
        item
        for item in (ocr.get("cover_text", ""), ocr.get("subtitle_text", ""), ocr.get("frame_text", ""))
        if _has_text(item)
    )
    ocr_evidence = []
    if ocr_text:
        ocr_evidence.append(
            {
                "claim": "封面字、字幕和画面文字判断",
                "evidence": _truncate(ocr_text, 180),
                "confidence": "high",
            }
        )
    elif ocr_status == "no_text":
        ocr_evidence.append(
            {
                "claim": "封面字、字幕和画面文字判断",
                "evidence": "OCR 已完成，未检测到封面字、字幕或画面文字；本条更适合按视觉动作和构图拆解。",
                "confidence": "high",
            }
        )
    elif ocr_status == "success":
        evidence_gaps.append("OCR 已完成但识别文本为空或无效，请复核关键帧。")
    else:
        evidence_gaps.append("未提供 OCR 文字，封面字和字幕结构需要人工复核。")

    comment_evidence = []
    if int(comments.get("total_comments") or 0):
        comment_bits = []
        top_needs = _coerce_list(comments.get("top_needs"))
        high_frequency_words = _coerce_list(comments.get("high_frequency_words"))
        comment_hooks = _coerce_list(comments.get("comment_hooks"))
        if top_needs:
            comment_bits.append("需求：" + "、".join(str(item) for item in top_needs))
        if high_frequency_words:
            comment_bits.append("高频词：" + "、".join(str(item) for item in high_frequency_words))
        if comment_hooks:
            comment_bits.append("互动钩子：" + "、".join(str(item) for item in comment_hooks))
        if comment_bits:
            comment_evidence.append(
                {
                    "claim": "评论区需求和互动触发判断",
                    "evidence": _truncate("；".join(comment_bits), 180),
                    "confidence": "high",
                }
            )
        else:
            evidence_gaps.append("评论已导入，但评论摘要为空，用户需求判断需要人工复核。")
    else:
        evidence_gaps.append("未导入评论，用户需求和评论触发点只能作为推断。")

    return {
        "visual_input_mode": visual_input_mode,
        "visual_evidence": visual_evidence,
        "asr_evidence": asr_evidence,
        "ocr_evidence": ocr_evidence,
        "comment_evidence": comment_evidence,
        "inferred_points": inferred_points,
        "evidence_gaps": evidence_gaps,
    }


def _default_enrichment_usage(analysis_input: dict) -> dict:
    enrichment = analysis_input.get("analysis_enrichment") or {}
    asr = enrichment.get("asr") or {}
    ocr = enrichment.get("ocr") or {}
    comments = enrichment.get("comments") or {}
    comment_summary_used = any(
        _has_items(comments.get(key)) for key in ("top_needs", "high_frequency_words", "comment_hooks")
    )
    notes = []
    if str(asr.get("status") or "") == "no_speech":
        notes.append("ASR 已检测，未发现可转写语音；本条按画面、音乐和动作拆解。")
    elif str(asr.get("status") or "") == "success" and not _has_text(asr.get("full_text")):
        notes.append("ASR 已完成但转写为空，请复核音频或重新运行。")
    elif not _has_text(asr.get("full_text")):
        notes.append("未提供 ASR 转写，口播和声音节奏判断可能不完整。")
    if str(ocr.get("status") or "") == "no_text":
        notes.append("OCR 已检测，未发现封面字、字幕或画面文字；本条按视觉动作和构图拆解。")
    elif str(ocr.get("status") or "") == "success" and not any(
        _has_text(ocr.get(key)) for key in ("frame_text", "subtitle_text", "cover_text")
    ):
        notes.append("OCR 已完成但识别文本为空，请复核关键帧或重新运行。")
    elif not any(_has_text(ocr.get(key)) for key in ("frame_text", "subtitle_text", "cover_text")):
        notes.append("未提供 OCR 文字，封面字和字幕结构需要人工复核。")
    if int(comments.get("total_comments") or 0) and not comment_summary_used:
        notes.append("评论已导入，但评论摘要为空，未作为有效用户需求证据。")
    ocr_used = any(_has_text(ocr.get(key)) for key in ("frame_text", "subtitle_text", "cover_text"))
    return {
        "asr_used": _has_text(asr.get("full_text")),
        "ocr_used": ocr_used,
        "comments_used": comment_summary_used,
        "notes": notes,
    }


def _normalize_enrichment_usage(value, analysis_input: dict, evidence_summary: dict) -> dict:
    defaults = _default_enrichment_usage(analysis_input)
    payload = value if isinstance(value, dict) else {}
    notes = _merge_text_lists(_coerce_list(payload.get("notes")), defaults.get("notes", []))
    return {
        "asr_used": bool(defaults.get("asr_used")) and _has_items(evidence_summary.get("asr_evidence")),
        "ocr_used": bool(defaults.get("ocr_used")) and _has_items(evidence_summary.get("ocr_evidence")),
        "comments_used": bool(defaults.get("comments_used")) and _has_items(evidence_summary.get("comment_evidence")),
        "notes": notes,
    }


def _build_enrichment_coverage(result: dict, analysis_input: dict) -> dict:
    enrichment = analysis_input.get("analysis_enrichment") or {}
    evidence = result.get("evidence_summary") or {}
    usage = result.get("enrichment_usage") or {}
    items = {
        "asr": _coverage_item(
            label="语音 / ASR",
            status=str((enrichment.get("asr") or {}).get("status") or "pending"),
            signal_available=_has_text((enrichment.get("asr") or {}).get("full_text")),
            checked_empty=str((enrichment.get("asr") or {}).get("status") or "") == "no_speech",
            used=bool(usage.get("asr_used")),
            insight_ready=_has_insight_content(result.get("speech_analysis")),
            evidence_count=len(evidence.get("asr_evidence") or []),
            missing_message="尚未提供 ASR 转写；口播、声音节奏和台词判断只能作为推断。",
            checked_empty_message="ASR 已检测为无可转写语音；按画面、音乐和动作拆解即可。",
            available_message="ASR 转写已可用，并被用于口播/声音拆解。",
            available_not_used_message="ASR 转写已可用，但报告没有把它作为有效口播证据使用。",
            evidence_without_insight_message="ASR 证据已列出，但口播/声音拆解字段没有形成可用结论。",
            insight_without_evidence_message="报告输出了口播/声音洞察，但缺少 ASR 转写证据支撑。",
            empty_result_message="ASR 标记为成功，但转写文本为空；请确认是否应标记为 no_speech。",
            action="运行或修正 ASR 后重跑，让 opening_line、spoken_hook、script_structure 有真实文本依据。",
        ),
        "ocr": _coverage_item(
            label="画面文字 / OCR",
            status=str((enrichment.get("ocr") or {}).get("status") or "pending"),
            signal_available=any(
                _has_text((enrichment.get("ocr") or {}).get(key))
                for key in ("frame_text", "subtitle_text", "cover_text")
            ),
            checked_empty=str((enrichment.get("ocr") or {}).get("status") or "") == "no_text",
            used=bool(usage.get("ocr_used")),
            insight_ready=_has_insight_content(result.get("screen_text_analysis")),
            evidence_count=len(evidence.get("ocr_evidence") or []),
            missing_message="尚未提供 OCR 文字；封面字、字幕和屏幕文字判断需要人工复核。",
            checked_empty_message="OCR 已检测为无封面字、字幕或画面文字；按视觉动作和构图拆解即可。",
            available_message="OCR 文字已可用，并被用于封面字/字幕/画面文字拆解。",
            available_not_used_message="OCR 文字已可用，但报告没有把它作为有效画面文字证据使用。",
            evidence_without_insight_message="OCR 证据已列出，但画面文字/OCR 拆解字段没有形成可用结论。",
            insight_without_evidence_message="报告输出了画面文字/字幕洞察，但缺少 OCR 证据支撑。",
            empty_result_message="OCR 标记为成功，但识别文本为空；请确认是否应标记为 no_text。",
            action="运行或修正 OCR 后重跑，让 cover_text_role、subtitle_text_role、screen_text_patterns 有真实文字依据。",
        ),
        "comments": _coverage_item(
            label="评论反馈",
            status=str((enrichment.get("comments") or {}).get("status") or "pending"),
            signal_available=any(
                _has_items((enrichment.get("comments") or {}).get(key))
                for key in ("top_needs", "high_frequency_words", "comment_hooks", "top_comments")
            ),
            checked_empty=False,
            used=bool(usage.get("comments_used")),
            insight_ready=_has_insight_content(result.get("comment_insights")),
            evidence_count=len(evidence.get("comment_evidence") or []),
            missing_message="尚未导入可用评论摘要；用户需求和互动触发点只能作为推断。",
            checked_empty_message="评论区样本为空；可以先按内容结构推断，但不要当成真实用户反馈。",
            available_message="评论摘要已可用，并被用于用户需求/互动触发拆解。",
            available_not_used_message="评论摘要已可用，但报告没有把它作为有效用户反馈证据使用。",
            evidence_without_insight_message="评论证据已列出，但评论反馈洞察字段没有形成可用结论。",
            insight_without_evidence_message="报告输出了评论/受众洞察，但缺少评论摘要证据支撑。",
            empty_result_message="已导入评论但摘要为空；请重新导入更有代表性的高赞或典型评论。",
            action="导入高赞/典型评论后重跑，让 audience_needs、comment_triggers、replicable_interaction_design 有真实评论依据。",
            empty_result=bool(int((enrichment.get("comments") or {}).get("total_comments") or 0))
            and not any(
                _has_items((enrichment.get("comments") or {}).get(key))
                for key in ("top_needs", "high_frequency_words", "comment_hooks", "top_comments")
            ),
        ),
    }
    blocking = [item for item in items.values() if item["verdict"] in _coverage_blocking_verdicts()]
    return {
        "items": items,
        "summary": {
            "used_count": sum(1 for item in items.values() if item["verdict"] == "used"),
            "checked_empty_count": sum(1 for item in items.values() if item["verdict"] == "checked_empty"),
            "blocking_count": len(blocking),
            "blocking_labels": [item["label"] for item in blocking],
        },
    }


def _coverage_item(
    *,
    label: str,
    status: str,
    signal_available: bool,
    checked_empty: bool,
    used: bool,
    insight_ready: bool,
    evidence_count: int,
    missing_message: str,
    checked_empty_message: str,
    available_message: str,
    available_not_used_message: str,
    evidence_without_insight_message: str,
    insight_without_evidence_message: str,
    empty_result_message: str,
    action: str,
    empty_result: bool = False,
) -> dict:
    if checked_empty and insight_ready:
        verdict = "insight_without_evidence"
        message = insight_without_evidence_message
    elif checked_empty:
        verdict = "checked_empty"
        message = checked_empty_message
    elif empty_result or (status == "success" and not signal_available and not used):
        verdict = "empty_result"
        message = empty_result_message
    elif signal_available and used and insight_ready:
        verdict = "used"
        message = available_message
    elif signal_available and used and not insight_ready:
        verdict = "evidence_without_insight"
        message = evidence_without_insight_message
    elif signal_available and not used:
        verdict = "available_not_used"
        message = available_not_used_message
    elif not signal_available and insight_ready:
        verdict = "insight_without_evidence"
        message = insight_without_evidence_message
    elif status == "provider_missing":
        verdict = "provider_missing"
        message = missing_message
    else:
        verdict = "missing"
        message = missing_message
    return {
        "label": label,
        "status": status,
        "available": bool(signal_available),
        "used": bool(used),
        "insight_ready": bool(insight_ready),
        "evidence_count": int(evidence_count or 0),
        "verdict": verdict,
        "message": message,
        "action": "" if verdict in {"used", "checked_empty", "missing", "provider_missing"} else action,
    }


def _coverage_blocking_verdicts() -> set[str]:
    return {
        "available_not_used",
        "evidence_without_insight",
        "insight_without_evidence",
        "empty_result",
    }


def _fallback_enrichment_coverage(result: dict) -> dict:
    evidence = result.get("evidence_summary") or {}
    usage = result.get("enrichment_usage") or {}
    items = {
        "asr": {
            "label": "语音 / ASR",
            "status": "unknown",
            "available": bool(usage.get("asr_used")),
            "used": bool(usage.get("asr_used")),
            "insight_ready": _has_insight_content(result.get("speech_analysis")),
            "evidence_count": len(evidence.get("asr_evidence") or []),
            "verdict": "used" if usage.get("asr_used") or _has_items(evidence.get("asr_evidence")) else "missing",
            "message": "基于旧报告字段推断富化使用状态。",
            "action": "",
        },
        "ocr": {
            "label": "画面文字 / OCR",
            "status": "unknown",
            "available": bool(usage.get("ocr_used")),
            "used": bool(usage.get("ocr_used")),
            "insight_ready": _has_insight_content(result.get("screen_text_analysis")),
            "evidence_count": len(evidence.get("ocr_evidence") or []),
            "verdict": "used" if usage.get("ocr_used") or _has_items(evidence.get("ocr_evidence")) else "missing",
            "message": "基于旧报告字段推断富化使用状态。",
            "action": "",
        },
        "comments": {
            "label": "评论反馈",
            "status": "unknown",
            "available": bool(usage.get("comments_used")),
            "used": bool(usage.get("comments_used")),
            "insight_ready": _has_insight_content(result.get("comment_insights")),
            "evidence_count": len(evidence.get("comment_evidence") or []),
            "verdict": (
                "used" if usage.get("comments_used") or _has_items(evidence.get("comment_evidence")) else "missing"
            ),
            "message": "基于旧报告字段推断富化使用状态。",
            "action": "",
        },
    }
    blocking = [item for item in items.values() if item["verdict"] in _coverage_blocking_verdicts()]
    return {
        "items": items,
        "summary": {
            "used_count": sum(1 for item in items.values() if item["verdict"] == "used"),
            "checked_empty_count": 0,
            "blocking_count": len(blocking),
            "blocking_labels": [item["label"] for item in blocking],
        },
    }


def _align_detection_flags_with_evidence(result: dict) -> None:
    evidence = result.get("evidence_summary") or {}
    usage = result.get("enrichment_usage") or {}
    speech = result.get("speech_analysis") if isinstance(result.get("speech_analysis"), dict) else {}
    screen_text = result.get("screen_text_analysis") if isinstance(result.get("screen_text_analysis"), dict) else {}
    inferred_points = evidence.setdefault("inferred_points", [])
    evidence_gaps = evidence.setdefault("evidence_gaps", [])
    risks = result.setdefault("risks", [])
    next_actions = result.setdefault("next_actions", [])

    asr_no_speech = _evidence_mentions(evidence.get("asr_evidence"), "未检测到可转写语音")
    if speech:
        if asr_no_speech and speech.get("has_speech") is True:
            text = "ASR 已确认无可转写语音，但报告声称有口播，需要人工复核。"
            speech["has_speech"] = False
            _append_quality_note(inferred_points, evidence_gaps, risks, next_actions, text, "复核音频或清空口播洞察后重跑。")
        elif usage.get("asr_used") is True and speech.get("has_speech") is False:
            text = "ASR 存在转写文本，但报告标记为无口播，需要人工复核。"
            speech["has_speech"] = True
            _append_quality_note(inferred_points, evidence_gaps, risks, next_actions, text, "复核 ASR 转写和口播拆解字段。")
        elif usage.get("asr_used") is True and "has_speech" not in speech:
            speech["has_speech"] = True
        elif asr_no_speech and "has_speech" not in speech:
            speech["has_speech"] = False

    ocr_no_text = _evidence_mentions(evidence.get("ocr_evidence"), "未检测到封面字")
    if screen_text:
        if ocr_no_text and screen_text.get("has_text") is True:
            text = "OCR 已确认无封面字、字幕或画面文字，但报告声称有画面文字，需要人工复核。"
            screen_text["has_text"] = False
            _append_quality_note(inferred_points, evidence_gaps, risks, next_actions, text, "复核关键帧或清空画面文字洞察后重跑。")
        elif usage.get("ocr_used") is True and screen_text.get("has_text") is False:
            text = "OCR 存在识别文本，但报告标记为无画面文字，需要人工复核。"
            screen_text["has_text"] = True
            _append_quality_note(inferred_points, evidence_gaps, risks, next_actions, text, "复核 OCR 结果和画面文字拆解字段。")
        elif usage.get("ocr_used") is True and "has_text" not in screen_text:
            screen_text["has_text"] = True
        elif ocr_no_text and "has_text" not in screen_text:
            screen_text["has_text"] = False


def _append_quality_note(
    inferred_points: list,
    evidence_gaps: list,
    risks: list,
    next_actions: list,
    text: str,
    action: str,
) -> None:
    _append_unique_text(inferred_points, text)
    _append_unique_text(evidence_gaps, text)
    _append_unique_text(risks, text)
    _append_unique_text(next_actions, action)


def _annotate_unbacked_enrichment_insights(result: dict) -> None:
    evidence = result.get("evidence_summary") or {}
    usage = result.get("enrichment_usage") or {}
    checks = (
        (
            "speech_analysis",
            "asr_used",
            "口播/声音洞察缺少 ASR 转写证据，只能作为画面和结构推断。",
            "补充 ASR 转写后重跑，或在人工工作表中确认口播内容。",
        ),
        (
            "screen_text_analysis",
            "ocr_used",
            "画面文字/字幕洞察缺少 OCR 证据，只能作为视觉推断。",
            "补充 OCR 识别后重跑，或人工核对封面字、字幕和画面文字。",
        ),
        (
            "comment_insights",
            "comments_used",
            "评论反馈洞察缺少评论摘要证据，只能作为内容结构推断。",
            "导入高赞/典型评论后重跑，或把受众判断标记为人工推断。",
        ),
    )
    inferred_points = evidence.setdefault("inferred_points", [])
    evidence_gaps = evidence.setdefault("evidence_gaps", [])
    risks = result.setdefault("risks", [])
    next_actions = result.setdefault("next_actions", [])
    for insight_key, usage_key, risk_text, action_text in checks:
        if _has_insight_content(result.get(insight_key)) and usage.get(usage_key) is not True:
            _append_unique_text(inferred_points, risk_text)
            _append_unique_text(evidence_gaps, risk_text)
            _append_unique_text(risks, risk_text)
            _append_unique_text(next_actions, action_text)


def _annotate_unused_available_enrichment(result: dict) -> None:
    evidence = result.get("evidence_summary") or {}
    usage = result.get("enrichment_usage") or {}
    checks = (
        (
            "speech_analysis",
            "asr_used",
            "ASR 转写已可用，但报告没有形成有效的口播/声音拆解。",
            "基于 ASR 转写补充 opening_line、spoken_hook 或 script_structure 后重跑。",
        ),
        (
            "screen_text_analysis",
            "ocr_used",
            "OCR 文字已可用，但报告没有形成有效的封面字/字幕拆解。",
            "基于 OCR 结果补充 cover_text_role、subtitle_text_role 或 screen_text_patterns 后重跑。",
        ),
        (
            "comment_insights",
            "comments_used",
            "评论摘要已可用，但报告没有形成有效的用户需求/互动触发拆解。",
            "基于评论摘要补充 audience_needs、comment_triggers 或 replicable_interaction_design 后重跑。",
        ),
    )
    evidence_gaps = evidence.setdefault("evidence_gaps", [])
    risks = result.setdefault("risks", [])
    next_actions = result.setdefault("next_actions", [])
    for insight_key, usage_key, gap_text, action_text in checks:
        if usage.get(usage_key) is True and not _has_insight_content(result.get(insight_key)):
            _append_unique_text(evidence_gaps, gap_text)
            _append_unique_text(risks, gap_text)
            _append_unique_text(next_actions, action_text)


def _append_unique_text(values: list, text: str) -> None:
    if not _has_text(text) or text in values:
        return
    values.append(text)


def _merge_text_lists(*values) -> list[str]:
    merged = []
    seen = set()
    for value in values:
        for item in _coerce_list(value):
            text = str(item).strip()
            if not _has_text(text) or text in seen:
                continue
            seen.add(text)
            merged.append(text)
    return merged


def _has_insight_content(value) -> bool:
    if isinstance(value, str):
        return _has_text(value)
    if isinstance(value, list):
        return any(_has_insight_content(item) for item in value)
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"has_speech", "has_text"} and isinstance(item, bool):
                continue
            if _has_insight_content(item):
                return True
        return False
    if isinstance(value, bool) or value is None:
        return False
    return True


def _has_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not _is_placeholder_text(value)


def _has_items(value) -> bool:
    if not isinstance(value, list):
        return False
    return any(_has_meaningful_item(item) for item in value)


def _has_meaningful_item(item) -> bool:
    if item in (None, [], {}):
        return False
    if isinstance(item, str):
        return _has_text(item)
    if isinstance(item, dict):
        return any(_has_meaningful_item(value) for value in item.values())
    if isinstance(item, list):
        return any(_has_meaningful_item(value) for value in item)
    return True


def _is_placeholder_text(value: str) -> bool:
    text = re.sub(r"\s+", "", str(value or "")).strip().lower()
    if not text:
        return True
    stripped = text.strip("。.!！?？：:，,；;（）()[]【】{}")
    if stripped in PLACEHOLDER_TEXTS:
        return True
    return any(pattern in stripped for pattern in PLACEHOLDER_PATTERNS) and len(stripped) <= 16


def _has_usable_summary(value) -> bool:
    return not _summary_quality_issues(value)


def _summary_quality_issues(value) -> list[dict]:
    raw = "" if value is None else str(value)
    compact = re.sub(r"\s+", "", raw).strip("。.!！?？：:，,；;（）()[]【】{}")
    if not raw.strip():
        return [
            {
                "id": "summary_missing",
                "label": "缺少总结",
                "location": "summary",
                "message": "缺少一句话总结，用户无法快速判断这条视频为什么值得拆。",
            }
        ]
    if _is_placeholder_text(raw) or compact in GENERIC_SUMMARY_TEXTS:
        return [
            {
                "id": "summary_placeholder",
                "label": "总结是占位文本",
                "location": "summary",
                "message": "summary 是占位或测试文本，不能作为拆解结论。",
            }
        ]
    compact = re.sub(r"\s+", "", str(value)).strip("。.!！?？：:，,；;（）()[]【】{}")
    if len(compact) <= 24 and any(pattern in compact for pattern in GENERIC_SUMMARY_PATTERNS):
        return [
            {
                "id": "summary_too_generic",
                "label": "总结太泛",
                "location": "summary",
                "message": "summary 只写了“值得学习/适合复刻”等泛化判断，没有说明具体爆点。",
            }
        ]
    if len(compact) < 8:
        return [
            {
                "id": "summary_too_short",
                "label": "总结过短",
                "location": "summary",
                "message": "summary 过短，无法说明核心爆点或复刻价值。",
            }
        ]
    return []


def _has_usable_evidence_summary(evidence: dict) -> bool:
    if not isinstance(evidence, dict):
        return False
    return any(
        any(_has_usable_evidence_item(item) for item in evidence.get(key) or [])
        for key in ("visual_evidence", "asr_evidence", "ocr_evidence", "comment_evidence")
    )


def _has_usable_evidence_item(item) -> bool:
    if isinstance(item, dict):
        claim = item.get("claim")
        evidence = item.get("evidence")
        return _has_usable_evidence_text(claim) and _has_usable_evidence_text(evidence)
    return _has_usable_evidence_text(item)


def _has_usable_evidence_text(value) -> bool:
    if not _has_text(value):
        return False
    compact = re.sub(r"\s+", "", str(value)).strip("。.!！?？：:，,；;（）()[]【】{}")
    if compact in GENERIC_EVIDENCE_TEXTS:
        return False
    return len(compact) >= 6


def _evidence_gap_issues(evidence: dict) -> list[dict]:
    if not isinstance(evidence, dict):
        return []
    gaps = evidence.get("evidence_gaps")
    if not isinstance(gaps, list):
        return []
    issues = []
    for index, gap in enumerate(gaps):
        if not _has_text(gap) or _is_placeholder_text(str(gap)):
            continue
        issues.append(
            {
                "id": "evidence_gap_item",
                "label": "证据缺口",
                "location": f"evidence_summary.evidence_gaps[{index}]",
                "message": str(gap),
            }
        )
    return issues


def _has_traceable_core_claims(result: dict, evidence: dict) -> bool:
    if not isinstance(result, dict) or not isinstance(evidence, dict):
        return False
    checked_text = " ".join(
        str(value)
        for value in (
            result.get("summary"),
            (result.get("hook_analysis") or {}).get("why_stop_scrolling"),
            (result.get("replication") or {}).get("remake_angle"),
        )
        if _has_text(value)
    )
    if not checked_text:
        return False
    required_sources = _traceable_sources_required_by_text(checked_text)
    if not required_sources:
        return True
    return all(_has_usable_evidence_for_source(evidence, source) for source in required_sources)


def _core_claim_traceability_issues(result: dict, evidence: dict) -> list[dict]:
    if not isinstance(result, dict) or not isinstance(evidence, dict):
        return [
            {
                "id": "core_claim_context_invalid",
                "label": "结论上下文无效",
                "location": "summary",
                "message": "缺少 result 或 evidence_summary，无法校验核心结论证据来源。",
            }
        ]
    fields = {
        "summary": result.get("summary"),
        "hook_analysis.why_stop_scrolling": (result.get("hook_analysis") or {}).get("why_stop_scrolling"),
        "replication.remake_angle": (result.get("replication") or {}).get("remake_angle"),
    }
    checked_text = " ".join(str(value) for value in fields.values() if _has_text(value))
    if not checked_text:
        return [
            {
                "id": "core_claim_missing",
                "label": "缺少核心结论",
                "location": "summary",
                "message": "summary、why_stop_scrolling 和 remake_angle 都缺少可校验的核心结论。",
            }
        ]
    required_sources = _traceable_sources_required_by_text(checked_text)
    issues = []
    for source in sorted(required_sources):
        if _has_usable_evidence_for_source(evidence, source):
            continue
        source_fields = [
            location for location, value in fields.items() if _text_requires_source(str(value or ""), source)
        ]
        issues.append(
            {
                "id": f"core_claim_missing_{source}_evidence",
                "label": f"缺少{TRACEABLE_SOURCE_LABELS.get(source, source)}",
                "location": ", ".join(source_fields) or "summary",
                "message": (
                    f"核心结论提到了{TRACEABLE_SOURCE_LABELS.get(source, source)}相关判断，"
                    f"但 evidence_summary 中没有可用的{TRACEABLE_SOURCE_LABELS.get(source, source)}。"
                ),
            }
        )
    return issues


def _traceable_sources_required_by_text(value: str) -> set[str]:
    compact = re.sub(r"\s+", "", str(value or ""))
    return {
        source
        for source, keywords in TRACEABLE_CLAIM_KEYWORDS.items()
        if any(keyword in compact for keyword in keywords)
    }


def _text_requires_source(value: str, source: str) -> bool:
    compact = re.sub(r"\s+", "", str(value or ""))
    keywords = TRACEABLE_CLAIM_KEYWORDS.get(source, ())
    return any(keyword in compact for keyword in keywords)


def _has_usable_evidence_for_source(evidence: dict, source: str) -> bool:
    key = {
        "visual": "visual_evidence",
        "asr": "asr_evidence",
        "ocr": "ocr_evidence",
        "comment": "comment_evidence",
    }.get(source)
    if not key:
        return False
    return any(_has_usable_evidence_item(item) for item in evidence.get(key) or [])


def _has_traceable_copyable_points(result: dict, evidence: dict) -> bool:
    if not isinstance(result, dict) or not isinstance(evidence, dict):
        return False
    replication = result.get("replication") or {}
    points = _coerce_list(replication.get("copyable_points"))
    if not points:
        return False
    context = _copyable_trace_context(result, evidence)
    return all(_is_traceable_copyable_point(point, evidence, context) for point in points)


def _copyable_point_quality_issues(result: dict, evidence: dict) -> list[dict]:
    if not isinstance(result, dict) or not isinstance(evidence, dict):
        return [
            {
                "id": "copyable_context_invalid",
                "label": "可复刻点上下文无效",
                "location": "replication.copyable_points",
                "message": "缺少 result 或 evidence_summary，无法校验可复刻点来源。",
            }
        ]
    replication = result.get("replication") or {}
    points = _coerce_list(replication.get("copyable_points"))
    if not points:
        return [
            {
                "id": "copyable_points_missing",
                "label": "缺少可复刻点",
                "location": "replication.copyable_points",
                "message": "没有输出可复刻点，无法落到脚本或分镜。",
            }
        ]
    context = _copyable_trace_context(result, evidence)
    compact_context = re.sub(r"\s+", "", context)
    issues = []
    for index, point in enumerate(points):
        text = _copyable_point_text(point)
        location = f"replication.copyable_points[{index}]"
        if not _has_usable_copyable_point_text(text):
            issues.append(
                {
                    "id": "copyable_point_too_generic",
                    "label": "可复刻点太泛",
                    "location": location,
                    "message": f"「{_truncate(text, 40)}」不够具体，不能直接指导拍摄或改编。",
                }
            )
            continue
        required_sources = _traceable_sources_required_by_text(text)
        missing_sources = [
            source for source in sorted(required_sources) if not _has_usable_evidence_for_source(evidence, source)
        ]
        if missing_sources:
            issues.append(
                {
                    "id": "copyable_point_missing_evidence",
                    "label": "可复刻点缺少证据",
                    "location": location,
                    "message": f"「{_truncate(text, 40)}」需要 {', '.join(missing_sources)} 证据支撑，但证据链不足。",
                }
            )
            continue
        terms = _copyable_trace_terms(text)
        if not terms:
            if not required_sources:
                issues.append(
                    {
                        "id": "copyable_point_no_trace_terms",
                        "label": "可复刻点缺少可追溯关键词",
                        "location": location,
                        "message": f"「{_truncate(text, 40)}」没有能和钩子、画面、口播、字幕或评论对应的关键词。",
                    }
                )
            continue
        matched_terms = [term for term in terms if term in compact_context]
        if not matched_terms:
            issues.append(
                {
                    "id": "copyable_point_untraceable",
                    "label": "可复刻点找不到来源",
                    "location": location,
                    "message": f"「{_truncate(text, 40)}」没有在钩子、画面、口播、字幕、评论或证据链中找到对应来源。",
                }
            )
    return issues


def _has_traceable_shot_table(result: dict, evidence: dict) -> bool:
    if not isinstance(result, dict) or not isinstance(evidence, dict):
        return False
    replication = result.get("replication") or {}
    rows = replication.get("shot_table")
    if not isinstance(rows, list) or not rows:
        return False
    context = _shot_table_trace_context(result, evidence)
    return all(_is_traceable_shot_row(row, context) for row in rows if isinstance(row, dict))


def _shot_table_quality_issues(result: dict, evidence: dict) -> list[dict]:
    if not isinstance(result, dict) or not isinstance(evidence, dict):
        return [
            {
                "id": "shot_table_context_invalid",
                "label": "分镜表上下文无效",
                "location": "replication.shot_table",
                "message": "缺少 result 或 evidence_summary，无法校验分镜表来源。",
            }
        ]
    replication = result.get("replication") or {}
    rows = replication.get("shot_table")
    if not isinstance(rows, list) or not rows:
        return [
            {
                "id": "shot_table_missing",
                "label": "缺少分镜表",
                "location": "replication.shot_table",
                "message": "没有输出分镜表，无法落到拍摄步骤。",
            }
        ]
    context = _shot_table_trace_context(result, evidence)
    compact_context = re.sub(r"\s+", "", context)
    issues = []
    for index, row in enumerate(rows):
        location = f"replication.shot_table[{index}]"
        if not isinstance(row, dict):
            issues.append(
                {
                    "id": "shot_row_invalid",
                    "label": "分镜行格式无效",
                    "location": location,
                    "message": "分镜行不是对象结构，无法校验 time、visual、action、subtitle 等字段。",
                }
            )
            continue
        if not _has_time_marker(row.get("time")):
            issues.append(
                {
                    "id": "shot_row_missing_time",
                    "label": "分镜行缺少时间",
                    "location": f"{location}.time",
                    "message": "分镜行缺少可识别的时间范围，无法对应原片时间线。",
                }
            )
            continue
        row_text = " ".join(
            str(row.get(key) or "")
            for key in ("visual", "action", "subtitle", "music_rhythm", "purpose")
            if _has_text(row.get(key))
        )
        if not _has_text(row_text):
            issues.append(
                {
                    "id": "shot_row_missing_detail",
                    "label": "分镜行缺少细节",
                    "location": location,
                    "message": "分镜行没有画面、动作、字幕、节奏或目的细节，无法判断是否来自原视频。",
                }
            )
            continue
        terms = _shot_trace_terms(row_text)
        if not terms:
            issues.append(
                {
                    "id": "shot_row_no_trace_terms",
                    "label": "分镜行缺少可追溯关键词",
                    "location": location,
                    "message": f"「{_truncate(row_text, 60)}」没有能和原片证据对应的关键词。",
                }
            )
            continue
        matched_terms = {term for term in terms if term in compact_context}
        if len(matched_terms) < 2:
            issues.append(
                {
                    "id": "shot_row_untraceable",
                    "label": "分镜行找不到来源",
                    "location": location,
                    "message": f"「{_truncate(row_text, 60)}」没有在时间线、证据链或可复刻点中找到足够来源。",
                }
            )
    return issues


def _is_traceable_shot_row(row: dict, context: str) -> bool:
    if not isinstance(row, dict) or not _has_time_marker(row.get("time")):
        return False
    row_text = " ".join(
        str(row.get(key) or "")
        for key in ("visual", "action", "subtitle", "music_rhythm", "purpose")
        if _has_text(row.get(key))
    )
    if not _has_text(row_text):
        return False
    terms = _shot_trace_terms(row_text)
    if not terms:
        return False
    compact_context = re.sub(r"\s+", "", context)
    matched_terms = {term for term in terms if term in compact_context}
    return len(matched_terms) >= 2


def _is_traceable_copyable_point(point, evidence: dict, context: str) -> bool:
    text = _copyable_point_text(point)
    if not _has_usable_copyable_point_text(text):
        return False
    required_sources = _traceable_sources_required_by_text(text)
    if required_sources and not all(_has_usable_evidence_for_source(evidence, source) for source in required_sources):
        return False
    terms = _copyable_trace_terms(text)
    if not terms:
        return bool(required_sources)
    compact_context = re.sub(r"\s+", "", context)
    return any(term in compact_context for term in terms)


def _copyable_point_text(point) -> str:
    if isinstance(point, dict):
        return " ".join(str(value) for value in point.values() if _has_meaningful_item(value))
    if isinstance(point, list):
        return " ".join(_copyable_point_text(item) for item in point)
    return str(point or "")


def _has_usable_copyable_point_text(value) -> bool:
    if not _has_text(value):
        return False
    compact = re.sub(r"\s+", "", str(value)).strip("。.!！?？：:，,；;（）()[]【】{}")
    if compact in GENERIC_COPYABLE_POINT_TEXTS:
        return False
    return len(compact) >= 4


def _copyable_trace_terms(value: str) -> list[str]:
    compact = re.sub(r"\s+", "", str(value or ""))
    terms: list[str] = []
    for keywords in TRACEABLE_CLAIM_KEYWORDS.values():
        terms.extend(keyword for keyword in keywords if keyword in compact)
    for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", compact):
        if token not in COPYABLE_TRACE_STOP_TERMS and token not in terms:
            terms.append(token)
    return terms


def _shot_trace_terms(value: str) -> list[str]:
    compact = re.sub(r"\s+", "", str(value or ""))
    terms: list[str] = []
    keyword_groups = [
        SPECIFIC_VISUAL_TERMS,
        SHOT_TRACE_EXTRA_TERMS,
        *(TRACEABLE_CLAIM_KEYWORDS.values()),
    ]
    for keywords in keyword_groups:
        for keyword in keywords:
            if keyword in compact and keyword not in terms:
                terms.append(keyword)
    return terms


def _copyable_trace_context(result: dict, evidence: dict) -> str:
    replication = result.get("replication") or {}
    trace_payload = {
        "summary": result.get("summary"),
        "hook_analysis": result.get("hook_analysis"),
        "visual_analysis": result.get("visual_analysis"),
        "copywriting_analysis": result.get("copywriting_analysis"),
        "speech_analysis": result.get("speech_analysis"),
        "screen_text_analysis": result.get("screen_text_analysis"),
        "comment_insights": result.get("comment_insights"),
        "timeline": result.get("timeline"),
        "emotion_path": result.get("emotion_path"),
        "content_ratio": result.get("content_ratio"),
        "evidence_summary": evidence,
        "replication": {
            "remake_angle": replication.get("remake_angle"),
            "opening_3s": replication.get("opening_3s"),
            "shot_table": replication.get("shot_table"),
        },
    }
    return " ".join(_iter_text_values(trace_payload))


def _shot_table_trace_context(result: dict, evidence: dict) -> str:
    replication = result.get("replication") or {}
    trace_payload = {
        "summary": result.get("summary"),
        "hook_analysis": result.get("hook_analysis"),
        "visual_analysis": result.get("visual_analysis"),
        "copywriting_analysis": result.get("copywriting_analysis"),
        "speech_analysis": result.get("speech_analysis"),
        "screen_text_analysis": result.get("screen_text_analysis"),
        "comment_insights": result.get("comment_insights"),
        "timeline": result.get("timeline"),
        "emotion_path": result.get("emotion_path"),
        "content_ratio": result.get("content_ratio"),
        "evidence_summary": evidence,
        "replication": {
            "copyable_points": replication.get("copyable_points"),
            "remake_angle": replication.get("remake_angle"),
            "opening_3s": replication.get("opening_3s"),
        },
    }
    return " ".join(_iter_text_values(trace_payload))


def _iter_text_values(value):
    if isinstance(value, str):
        if _has_text(value):
            yield value
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_text_values(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_text_values(item)


def _visual_analysis_quality_issues(visual: dict, timeline) -> list[dict]:
    issues = []
    visual = visual if isinstance(visual, dict) else {}
    field_labels = {
        "scene": "场景",
        "subject": "主体",
        "composition": "构图",
        "movement_rhythm": "运动节奏",
    }
    usable_fields = [key for key in field_labels if _has_specific_visual_text(visual.get(key))]
    if len(usable_fields) < 2:
        weak_fields = [
            f"{field_labels[key]}={str(visual.get(key) or '缺失').strip() or '缺失'}"
            for key in field_labels
            if key not in usable_fields
        ]
        issues.append(
            {
                "id": "visual_fields_too_shallow",
                "label": "视觉字段不足",
                "location": "visual_analysis",
                "message": "视觉分析至少需要场景、主体、构图、运动节奏中的两项具体描述；待补："
                + "；".join(weak_fields[:4])
                + "。",
            }
        )
    if not _has_usable_timeline(timeline):
        issues.append(
            {
                "id": "visual_timeline_missing",
                "label": "关键时间线不足",
                "location": "timeline",
                "message": "缺少带时间点且包含具体画面、动作、字幕或目的的关键时间线。",
            }
        )
    return issues


def _has_specific_visual_text(value) -> bool:
    if not _has_text(value):
        return False
    compact = re.sub(r"\s+", "", str(value)).strip("。.!！?？：:，,；;（）()[]【】{}")
    if compact in GENERIC_VISUAL_TEXTS:
        return False
    if any(pattern in compact for pattern in GENERIC_VISUAL_PATTERNS) and len(compact) <= 16:
        return False
    if any(term in compact for term in SPECIFIC_VISUAL_TERMS):
        return True
    return len(compact) >= 6


def _has_usable_shot_detail(value) -> bool:
    if not _has_text(value):
        return False
    compact = re.sub(r"\s+", "", str(value)).strip("。.!！?？：:，,；;（）()[]【】{}")
    if compact in GENERIC_SHOT_TEXTS:
        return False
    if any(pattern in compact for pattern in GENERIC_VISUAL_PATTERNS) and len(compact) <= 16:
        return False
    if any(term in compact for term in SPECIFIC_VISUAL_TERMS):
        return True
    return len(compact) >= 6


def _has_rich_shot_detail(value) -> bool:
    if not _has_usable_shot_detail(value):
        return False
    compact = re.sub(r"\s+", "", str(value)).strip("。.!！?？：:，,；;（）()[]【】{}")
    term_count = sum(1 for term in SPECIFIC_VISUAL_TERMS if term in compact)
    return term_count >= 2 and len(compact) >= 10


def _has_usable_timeline(value) -> bool:
    if not isinstance(value, list):
        return False
    return any(_has_usable_timeline_item(item) for item in value)


def _has_usable_timeline_item(item) -> bool:
    if isinstance(item, dict):
        time_value = _first_available_value(item, ("time", "time_range", "range", "timestamp", "start", "segment"))
        if not _has_text(time_value) and not isinstance(time_value, (int, float)):
            return False
        if not (_has_time_marker(time_value) or isinstance(time_value, (int, float))):
            return False
        detail_values = [
            item.get(key)
            for key in ("visual", "action", "subtitle", "text", "description", "purpose", "music_rhythm")
        ]
        return any(_has_specific_visual_text(value) for value in detail_values)
    if not _has_text(item) or not _has_time_marker(item):
        return False
    detail = SHOT_TIME_RE.sub("", str(item)).strip(" -•、\t，,；;：:。.!！?？")
    return _has_specific_visual_text(detail)


def _has_publish_items(value) -> bool:
    if not isinstance(value, list):
        return False
    return any(_has_publish_text(item) for item in value)


def _has_publish_text(value) -> bool:
    if not _has_text(value):
        return False
    compact = re.sub(r"\s+", "", str(value)).strip("。.!！?？：:，,；;（）()[]【】{}#")
    if compact in GENERIC_PUBLISH_TEXTS:
        return False
    return len(compact) >= 6


def _has_usable_copy_text(value) -> bool:
    if not _has_text(value):
        return False
    compact = re.sub(r"\s+", "", str(value)).strip("。.!！?？：:，,；;（）()[]【】{}")
    if compact in GENERIC_COPY_TEXTS:
        return False
    return len(compact) >= 6


def _has_usable_audience_items(value) -> bool:
    if not isinstance(value, list):
        return False
    return any(_has_usable_audience_text(item) for item in value)


def _has_usable_audience_text(value) -> bool:
    if not _has_text(value):
        return False
    compact = re.sub(r"\s+", "", str(value)).strip("。.!！?？：:，,；;（）()[]【】{}")
    if compact in GENERIC_AUDIENCE_TEXTS:
        return False
    return len(compact) >= 6


def _audience_quality_issues(evidence: dict, comments: dict) -> list[dict]:
    issues = []
    has_comment_evidence = _has_items(evidence.get("comment_evidence")) if isinstance(evidence, dict) else False
    has_comment_insight = _has_insight_content(comments)
    has_usable_insight = (
        _has_usable_audience_items(comments.get("audience_needs"))
        or _has_usable_audience_items(comments.get("comment_triggers"))
        or _has_usable_audience_text(comments.get("replicable_interaction_design"))
    )
    if not has_comment_evidence:
        issues.append(
            {
                "id": "audience_comment_evidence_missing",
                "label": "缺少评论证据",
                "location": "evidence_summary.comment_evidence",
                "message": "没有评论证据时，用户需求和评论触发只能作为内容结构推断。",
            }
        )
    if has_comment_insight and not has_comment_evidence:
        issues.append(
            {
                "id": "audience_insight_without_evidence",
                "label": "评论洞察无证据",
                "location": "comment_insights",
                "message": "报告写了评论/受众洞察，但没有对应 comment_evidence 支撑。",
            }
        )
    if has_comment_evidence and not has_usable_insight:
        issues.append(
            {
                "id": "audience_insight_too_generic",
                "label": "评论洞察太泛",
                "location": "comment_insights",
                "message": "已有评论证据，但 audience_needs、comment_triggers 或互动设计仍过于泛化。",
            }
        )
    return issues


def _has_usable_boundary_items(value) -> bool:
    if not isinstance(value, list):
        return False
    return any(_has_usable_boundary_text(item) for item in value)


def _has_usable_boundary_text(value) -> bool:
    if not _has_text(value):
        return False
    compact = re.sub(r"\s+", "", str(value)).strip("。.!！?？：:，,；;（）()[]【】{}")
    if compact in GENERIC_BOUNDARY_TEXTS:
        return False
    has_boundary_keyword = any(keyword in compact for keyword in ("不要照搬", "替换", "保留自己", "版权", "尺度", "风险"))
    return has_boundary_keyword and len(compact) >= 10


def _has_usable_shot_table(value) -> bool:
    if not isinstance(value, list):
        return False
    detail_keys = ("visual", "action", "subtitle", "music_rhythm", "purpose")
    for row in value:
        if not isinstance(row, dict) or not _has_time_marker(row.get("time")):
            continue
        usable_details = [row.get(key) for key in detail_keys if _has_usable_shot_detail(row.get(key))]
        if any(_has_rich_shot_detail(detail) for detail in usable_details):
            return True
        detail_count = len(usable_details)
        if detail_count >= 2:
            return True
    return False


def _has_useful_first_3_seconds(value) -> bool:
    if not isinstance(value, list):
        return False
    observations = [item for item in value if _has_timed_first_3s_observation(item)]
    return len(observations) >= 2


def _hook_quality_issues(hook: dict) -> list[dict]:
    hook = hook if isinstance(hook, dict) else {}
    issues = []
    if not _has_text(hook.get("first_impression")) or _is_placeholder_text(str(hook.get("first_impression") or "")):
        issues.append(
            {
                "id": "hook_first_impression_missing",
                "label": "缺少第一眼判断",
                "location": "hook_analysis.first_impression",
                "message": "缺少可用的第一眼观察，无法判断用户第一秒为什么停留。",
            }
        )
    if not _has_text(hook.get("why_stop_scrolling")) or _is_placeholder_text(str(hook.get("why_stop_scrolling") or "")):
        issues.append(
            {
                "id": "hook_stop_reason_missing",
                "label": "缺少停留理由",
                "location": "hook_analysis.why_stop_scrolling",
                "message": "缺少可用的停留理由，无法判断钩子来自视觉、文案、动作还是情绪。",
            }
        )
    observations = hook.get("first_3_seconds")
    if not isinstance(observations, list) or not observations:
        issues.append(
            {
                "id": "hook_first_3_seconds_missing",
                "label": "缺少前三秒观察",
                "location": "hook_analysis.first_3_seconds",
                "message": "缺少 0-3 秒逐秒观察。",
            }
        )
        return issues
    usable_count = 0
    observation_issues = []
    for index, item in enumerate(observations):
        issue = _first_3s_observation_issue(item, index)
        if issue:
            observation_issues.append(issue)
        else:
            usable_count += 1
    if usable_count < 2:
        issues.append(
            {
                "id": "hook_first_3_seconds_too_few",
                "label": "前三秒观察不足",
                "location": "hook_analysis.first_3_seconds",
                "message": f"前三秒至少需要 2 条带时间点且具体的观察；当前可用 {usable_count} 条。",
            }
        )
        issues.extend(observation_issues[:4])
    return issues


def _first_3s_observation_issue(item, index: int) -> dict | None:
    location = f"hook_analysis.first_3_seconds[{index}]"
    if isinstance(item, dict):
        time_value = _first_available_value(item, ("time", "timestamp", "time_range", "start", "second", "seconds"))
        has_time = _has_time_marker(time_value) or isinstance(time_value, (int, float))
        detail = _first_available_value(
            item,
            ("visual", "observation", "description", "action", "subtitle", "text", "event", "change", "purpose"),
        )
        if not _has_text(detail):
            detail = " ".join(
                str(value)
                for key, value in item.items()
                if key not in {"time", "timestamp", "time_range", "start", "second", "seconds"}
                and _has_text(value)
            )
    else:
        has_time = _has_time_marker(item)
        detail = FIRST_SECONDS_TIME_RE.sub("", str(item or "")).strip(" -•、\t，,；;：:。.!！?？")
    if not has_time:
        return {
            "id": "hook_observation_missing_time",
            "label": "观察缺少时间点",
            "location": location,
            "message": f"「{_truncate(str(item), 50)}」缺少 0s/1s/2s 等时间点。",
        }
    if not _has_specific_hook_detail(detail):
        return {
            "id": "hook_observation_too_generic",
            "label": "观察太泛",
            "location": location,
            "message": f"「{_truncate(str(item), 50)}」缺少具体画面、字幕、动作或口播变化。",
        }
    return None


def _has_useful_emotion_path(value) -> bool:
    if not isinstance(value, list):
        return False
    return not _emotion_path_issues(value)


def _emotion_path_issues(value) -> list[dict]:
    if not isinstance(value, list) or not value:
        return [
            {
                "id": "emotion_path_missing",
                "label": "缺少情绪路径",
                "location": "emotion_path",
                "message": "情绪路径为空，无法判断开头、中段、结尾如何推进。",
            }
        ]
    usable_items = [item for item in value if _has_emotion_phase(item)]
    if len(usable_items) < 3:
        return [
            {
                "id": "emotion_path_too_short",
                "label": "情绪路径过短",
                "location": "emotion_path",
                "message": "情绪路径至少需要覆盖开头、中段、结尾三段。",
            }
        ]
    covered = {_emotion_stage_id(item) for item in usable_items}
    covered.discard("")
    missing = [stage for stage in ("opening", "middle", "ending") if stage not in covered]
    if not missing:
        return []
    return [
        {
            "id": "emotion_path_missing_stage",
            "label": "情绪阶段缺失",
            "location": "emotion_path",
            "message": "情绪路径缺少：" + "、".join(EMOTION_STAGE_LABELS[stage] for stage in missing) + "。",
        }
    ]


def _has_usable_content_ratio(value) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        if isinstance(item, dict):
            if _has_text(item.get("name")) and (
                _positive_number(item.get("percent")) or _text_has_ratio_number(item.get("reason"))
            ):
                return True
        elif _text_has_ratio_number(item):
            return True
    return False


def _content_ratio_balance_issues(value) -> list[dict]:
    if not isinstance(value, list) or not value:
        return []
    ratio_items = []
    missing_reason = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("label") or item.get("dimension") or f"第 {index + 1} 项").strip()
        percent = _normalize_ratio_percent(_content_ratio_percent_value(item))
        if percent is not None:
            ratio_items.append({"index": index, "name": name, "percent": percent})
        if percent is not None and not _has_text(item.get("reason")):
            missing_reason.append({"index": index, "name": name})

    issues = []
    if ratio_items and len(ratio_items) < 2:
        issues.append(
            {
                "id": "content_ratio_too_few_items",
                "label": "占比项过少",
                "location": "content_ratio",
                "message": "内容占比只有 1 个比例项，无法说明完整结构。",
            }
        )
    if len(ratio_items) >= 2:
        total = round(sum(float(item["percent"]) for item in ratio_items), 2)
        if total < 90 or total > 110:
            issues.append(
                {
                    "id": "content_ratio_total",
                    "label": "占比总和不自洽",
                    "location": "content_ratio",
                    "total": total,
                    "limit": "90-110",
                    "message": f"内容占比总和为 {total:g}%，应接近 100%。",
                }
            )
    for item in missing_reason[:3]:
        issues.append(
            {
                "id": "content_ratio_missing_reason",
                "label": "占比缺少依据",
                "location": f"content_ratio[{item['index']}].reason",
                "message": f"{item['name']} 有比例但缺少 reason，无法判断依据。",
            }
        )
    return issues


def _content_category_alignment_issues(result: dict) -> list[dict]:
    category_id = str(result.get("content_category") or "").strip() or "generic"
    if category_id == "generic":
        return []
    expected_dimensions = CATEGORY_RATIO_KEYWORDS.get(category_id)
    if not expected_dimensions:
        return []
    ratio_text = _content_ratio_search_text(result.get("content_ratio"))
    if not ratio_text:
        return []
    matched = [
        label
        for label, keywords in expected_dimensions.items()
        if _text_matches_any_keyword(ratio_text, keywords)
    ]
    required = min(CATEGORY_ALIGNMENT_REQUIRED_MATCHES, len(expected_dimensions))
    if len(matched) >= required:
        return []
    context = build_analysis_context(category_id)
    missing = [label for label in expected_dimensions if label not in matched]
    return [
        {
            "id": "category_ratio_mismatch",
            "label": "内容占比未贴合类型",
            "location": "content_ratio",
            "message": (
                f"当前内容类型是「{context.get('label', category_id)}」，"
                f"内容占比至少应覆盖 {required} 个类型维度；"
                f"已覆盖 {len(matched)} 个。建议补：{'、'.join(missing[:3])}。"
            ),
        }
    ]


def _content_ratio_search_text(value) -> str:
    if not isinstance(value, list):
        return ""
    chunks = []
    for item in value:
        if isinstance(item, dict):
            chunks.extend(
                str(item.get(key) or "")
                for key in ("name", "label", "dimension", "reason", "description")
            )
        elif _has_text(item):
            chunks.append(str(item))
    return re.sub(r"\s+", "", " ".join(chunks)).lower()


def _text_matches_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    return any(str(keyword or "").strip().lower() in text for keyword in keywords if str(keyword or "").strip())


def _engagement_data_quality_issues(result: dict) -> list[dict]:
    quality = str(result.get("engagement_data_quality") or "").strip().lower()
    if not quality or quality == "ok":
        return []
    if quality not in {"missing", "partial"}:
        return []
    label = "互动数据缺失" if quality == "missing" else "互动数据不完整"
    message = (
        "点赞、评论、分享均为空或缺失，不能判断真实爆款强度。"
        if quality == "missing"
        else "点赞、评论或分享数据不完整，爆款强度判断需要降级。"
    )
    return [
        {
            "id": f"engagement_data_{quality}",
            "label": label,
            "location": "engagement_data_quality",
            "message": message,
        }
    ]


def _has_usable_publish_package(value) -> bool:
    if not isinstance(value, dict):
        return False
    has_title = _has_publish_items(value.get("titles"))
    has_support = (
        _has_publish_text(value.get("caption"))
        or _has_publish_items(value.get("hashtags"))
        or _has_publish_text(value.get("pinned_comment"))
    )
    return has_title and has_support


def _publish_package_quality_issues(value) -> list[dict]:
    if not isinstance(value, dict):
        return [
            {
                "id": "publish_package_invalid",
                "label": "发布包格式无效",
                "location": "publish_package",
                "message": "发布包不是对象结构，无法读取标题、正文、标签或置顶评论。",
            }
        ]
    issues = []
    titles = value.get("titles")
    if not _has_publish_items(titles):
        issues.append(_publish_field_issue("titles", titles, "缺少可用标题", "标题候选为空或过于泛化，不能直接用于发布。"))
    caption = value.get("caption")
    hashtags = value.get("hashtags")
    pinned_comment = value.get("pinned_comment")
    support_checks = {
        "caption": _has_publish_text(caption),
        "hashtags": _has_publish_items(hashtags),
        "pinned_comment": _has_publish_text(pinned_comment),
    }
    if not any(support_checks.values()):
        support_values = {
            "caption": caption,
            "hashtags": hashtags,
            "pinned_comment": pinned_comment,
        }
        generic_support = [
            _publish_field_issue(field, support_values[field], "发布支撑太泛", f"{field} 已填写但过于泛化，不能直接落地。")
            for field in ("caption", "hashtags", "pinned_comment")
            if _publish_field_has_any_text(support_values[field])
        ]
        if generic_support:
            issues.extend(generic_support)
        else:
            issues.append(
                {
                    "id": "publish_support_missing",
                    "label": "缺少发布支撑",
                    "location": "publish_package",
                    "message": "发布包只有标题，缺少 caption、hashtags 或 pinned_comment。",
                }
            )
    return issues


def _publish_field_issue(field: str, value, label: str, message: str) -> dict:
    suffix = "too_generic" if _publish_field_has_any_text(value) else "missing"
    return {
        "id": f"publish_{field}_{suffix}",
        "label": label,
        "location": f"publish_package.{field}",
        "message": message,
    }


def _publish_field_has_any_text(value) -> bool:
    if isinstance(value, list):
        return any(_has_text(item) for item in value)
    return _has_text(value)


def _time_bound_issues(result: dict) -> list[dict]:
    duration = _result_duration_seconds(result)
    if duration <= 0:
        return []
    issues: list[dict] = []
    hook = result.get("hook_analysis") if isinstance(result.get("hook_analysis"), dict) else {}
    for index, item in enumerate(hook.get("first_3_seconds") or []):
        max_time = _max_time_seconds_from_value(item)
        if max_time is None:
            continue
        limit = min(3.5, duration + 0.5)
        if max_time > limit:
            issues.append(
                {
                    "id": "hook_first_3_seconds",
                    "label": "前 3 秒观察越界",
                    "location": f"hook_analysis.first_3_seconds[{index}]",
                    "time": max_time,
                    "limit": limit,
                    "message": f"前 3 秒观察写到了 {max_time:g}s，超过允许范围 {limit:g}s。",
                }
            )

    for index, item in enumerate(result.get("timeline") or []):
        max_time = _max_time_seconds_from_timeline_item(item)
        if max_time is not None and max_time > duration + 0.75:
            issues.append(
                {
                    "id": "timeline_out_of_bounds",
                    "label": "时间线越界",
                    "location": f"timeline[{index}]",
                    "time": max_time,
                    "limit": duration,
                    "message": f"时间线写到了 {max_time:g}s，但视频时长约 {duration:g}s。",
                }
            )

    replication = result.get("replication") if isinstance(result.get("replication"), dict) else {}
    for index, row in enumerate(replication.get("shot_table") or []):
        if not isinstance(row, dict):
            continue
        max_time = _max_time_seconds_from_value(row.get("time"))
        if max_time is not None and max_time > duration + 0.75:
            issues.append(
                {
                    "id": "shot_table_out_of_bounds",
                    "label": "分镜表越界",
                    "location": f"replication.shot_table[{index}].time",
                    "time": max_time,
                    "limit": duration,
                    "message": f"分镜表写到了 {max_time:g}s，但视频时长约 {duration:g}s。",
                }
            )
    return issues


def _result_duration_seconds(result: dict) -> float:
    source = result.get("source") if isinstance(result.get("source"), dict) else {}
    for value in (
        source.get("duration"),
        source.get("duration_seconds"),
        result.get("duration"),
        result.get("video_duration"),
    ):
        number = _float_or_zero(value)
        if number > 0:
            return number
    return 0.0


def _max_time_seconds_from_timeline_item(item) -> float | None:
    if isinstance(item, dict):
        time_value = _first_available_value(item, ("time", "time_range", "range", "timestamp", "start", "segment"))
        return _max_time_seconds_from_value(time_value)
    return _max_time_seconds_from_value(item)


def _max_time_seconds_from_value(value) -> float | None:
    numbers = _time_seconds_from_value(value)
    if not numbers:
        return None
    return max(numbers)


def _time_seconds_from_value(value) -> list[float]:
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        return [float(value)] if value >= 0 else []
    if not isinstance(value, str):
        return []
    text = value.strip()
    if not text or not _has_time_marker(text):
        return []
    return [float(match.group(0)) for match in re.finditer(r"\d+(?:\.\d+)?", text)]


def _float_or_zero(value) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        match = re.search(r"\d+(?:\.\d+)?", str(value))
        return float(match.group(0)) if match else 0.0


def _has_low_confidence_evidence(evidence: dict) -> bool:
    return bool(_low_confidence_evidence_issues(evidence))


def _low_confidence_evidence_issues(evidence: dict) -> list[dict]:
    if not isinstance(evidence, dict):
        return []
    issues = []
    for key in ("visual_evidence", "asr_evidence", "ocr_evidence", "comment_evidence"):
        values = evidence.get(key)
        if not isinstance(values, list):
            continue
        for index, item in enumerate(values):
            if not isinstance(item, dict) or str(item.get("confidence") or "").lower() != "low":
                continue
            label = EVIDENCE_FIELD_LABELS.get(key, key)
            claim = str(item.get("claim") or "").strip()
            evidence_text = str(item.get("evidence") or "").strip()
            summary = "；".join(part for part in (claim, evidence_text) if part)
            issues.append(
                {
                    "id": f"low_confidence_{key}",
                    "label": f"低置信{label}",
                    "location": f"evidence_summary.{key}[{index}]",
                    "message": f"{label}置信度为 low：{_truncate(summary, 80) if summary else '未提供证据摘要'}。",
                }
            )
    return issues


def _has_usable_model_confidence(value) -> bool:
    return _normalize_model_confidence(value) >= 0.6


def _normalize_model_confidence(value) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return 0.0
        qualitative = {
            "high": 0.85,
            "medium": 0.65,
            "low": 0.35,
            "高": 0.85,
            "较高": 0.8,
            "中": 0.65,
            "中等": 0.65,
            "低": 0.35,
            "较低": 0.3,
        }
        compact = text.replace("置信度", "").replace("：", "").replace(":", "").strip()
        if compact in qualitative:
            return qualitative[compact]
        match = re.search(r"\d+(?:\.\d+)?", compact)
        if not match:
            return 0.0
        number = float(match.group(0))
        if "%" in compact:
            number = number / 100
    else:
        return 0.0
    if number > 1:
        number = number / 100
    if number < 0:
        return 0.0
    if number > 1:
        return 1.0
    return round(number, 4)


def _positive_number(value) -> bool:
    try:
        if isinstance(value, str):
            value = value.strip().rstrip("%")
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _text_has_ratio_number(value) -> bool:
    if not _has_text(value):
        return False
    return bool(re.search(r"\d+(?:\.\d+)?\s*%", str(value)))


def _has_timed_first_3s_observation(item) -> bool:
    if isinstance(item, dict):
        time_value = _first_available_value(item, ("time", "timestamp", "time_range", "start", "second", "seconds"))
        has_time = _has_time_marker(time_value) or isinstance(time_value, (int, float))
        detail = _first_available_value(
            item,
            ("visual", "observation", "description", "action", "subtitle", "text", "event", "change", "purpose"),
        )
        if not _has_text(detail):
            detail = " ".join(
                str(value)
                for key, value in item.items()
                if key not in {"time", "timestamp", "time_range", "start", "second", "seconds"}
                and _has_text(value)
            )
        return bool(has_time and _has_specific_hook_detail(detail))
    if not _has_text(item) or not _has_time_marker(item):
        return False
    detail = FIRST_SECONDS_TIME_RE.sub("", str(item)).strip(" -•、\t，,；;：:。.!！?？")
    return _has_specific_hook_detail(detail)


def _has_specific_hook_detail(value) -> bool:
    if not _has_text(value):
        return False
    compact = re.sub(r"\s+", "", str(value)).strip("。.!！?？：:，,；;（）()[]【】{}")
    if compact in GENERIC_HOOK_TEXTS:
        return False
    if any(pattern in compact for pattern in PLACEHOLDER_PATTERNS):
        return False
    if any(term in compact for term in SPECIFIC_VISUAL_TERMS):
        return True
    if any(term in compact for terms in TRACEABLE_CLAIM_KEYWORDS.values() for term in terms):
        return True
    return len(compact) >= 8


def _has_emotion_phase(item) -> bool:
    if isinstance(item, dict):
        phase = _first_available_value(item, ("phase", "stage", "time", "time_range", "segment"))
        detail = _first_available_value(item, ("emotion", "change", "description", "purpose", "text", "reason"))
        if not _has_text(detail):
            detail = " ".join(
                str(value)
                for key, value in item.items()
                if key not in {"phase", "stage", "time", "time_range", "segment"} and _has_text(value)
            )
        return (_has_text(phase) or _has_time_marker(phase)) and _has_text(detail)
    if not _has_text(item):
        return False
    text = str(item)
    if not EMOTION_PHASE_RE.search(text):
        return False
    detail = EMOTION_PHASE_RE.sub("", text).strip(" -•、\t，,；;：:。.!！?？")
    return _has_text(detail)


def _emotion_stage_id(item) -> str:
    if isinstance(item, dict):
        stage_text = " ".join(
            str(value)
            for value in (
                _first_available_value(item, ("phase", "stage", "time", "time_range", "segment")),
                _first_available_value(item, ("emotion", "change", "description", "purpose", "text", "reason")),
            )
            if _has_text(value)
        )
    else:
        stage_text = str(item or "")
    compact = re.sub(r"\s+", "", stage_text).lower()
    for stage, keywords in EMOTION_STAGE_KEYWORDS.items():
        if any(str(keyword).lower() in compact for keyword in keywords):
            return stage
    return ""


def _has_time_marker(value) -> bool:
    if isinstance(value, (int, float)):
        return True
    if not isinstance(value, str):
        return False
    return bool(FIRST_SECONDS_TIME_RE.search(value))


def _first_available_value(item: dict, keys: tuple[str, ...]):
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _evidence_mentions(value, phrase: str) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        if isinstance(item, dict):
            fields = (item.get("claim"), item.get("evidence"))
        else:
            fields = (item,)
        if any(phrase in str(field or "") for field in fields):
            return True
    return False


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
    evidence = result.get("evidence_summary") or {}
    lines.extend(["## 证据与推断边界", ""])
    lines.append(f"- 视觉输入模式：{evidence.get('visual_input_mode', '')}")
    for title, key in (
        ("视觉证据", "visual_evidence"),
        ("ASR 证据", "asr_evidence"),
        ("OCR 证据", "ocr_evidence"),
        ("评论证据", "comment_evidence"),
        ("推断点", "inferred_points"),
        ("证据缺口", "evidence_gaps"),
    ):
        values = evidence.get(key) or []
        if values:
            lines.append(f"- {title}：{_format_value(values)}")
    lines.append("")

    coverage = result.get("enrichment_coverage") or _fallback_enrichment_coverage(result)
    lines.extend(["## 富化证据使用核对", ""])
    coverage_summary = coverage.get("summary") or {}
    lines.append(f"- 已使用：{coverage_summary.get('used_count', 0)} 项")
    lines.append(f"- 已检测为空：{coverage_summary.get('checked_empty_count', 0)} 项")
    lines.append(f"- 阻塞项：{coverage_summary.get('blocking_count', 0)} 项")
    for key in ("asr", "ocr", "comments"):
        item = (coverage.get("items") or {}).get(key) or {}
        if not item:
            continue
        lines.append(
            f"- {item.get('label', key)}：{item.get('verdict', '')}，"
            f"状态={item.get('status', '')}，证据={item.get('evidence_count', 0)}，"
            f"洞察={'是' if item.get('insight_ready') else '否'}"
        )
        if item.get("message"):
            lines.append(f"  - 说明：{item.get('message')}")
        if item.get("action"):
            lines.append(f"  - 建议：{item.get('action')}")
    lines.append("")

    quality = result.get("quality_review") or {}
    lines.extend(["## 拆解质量自检", ""])
    lines.append(f"- 质量分：{quality.get('score', 0)} / {quality.get('max_score', 100)}")
    lines.append(f"- 等级：{quality.get('label', '')}")
    lines.append(f"- 结论：{quality.get('summary', '')}")
    gaps = quality.get("gaps") or []
    if gaps:
        lines.append(f"- 待补齐：{_format_value([gap.get('label', '') for gap in gaps])}")
    actions = quality.get("next_actions") or []
    if actions:
        lines.append(f"- 建议动作：{_format_value(actions)}")
    lines.append("")

    rerun_compliance = result.get("rerun_compliance") or {}
    lines.extend(["## 重跑合规检查", ""])
    lines.append(f"- 是否启用：{'是' if rerun_compliance.get('active') else '否'}")
    lines.append(f"- 状态：{rerun_compliance.get('status', '')}")
    lines.append(f"- 合规分：{rerun_compliance.get('score', 100)} / 100")
    lines.append(f"- 结论：{rerun_compliance.get('summary', '')}")
    for check in rerun_compliance.get("checks") or []:
        status = "通过" if check.get("passed") else "待修"
        lines.append(f"- {status} · {check.get('label') or check.get('id') or ''}")
        if check.get("message"):
            lines.append(f"  - 说明：{check.get('message')}")
        if not check.get("passed") and check.get("action"):
            lines.append(f"  - 建议：{check.get('action')}")
    lines.append("")
    lines.extend(["### 优先质量缺口", ""])
    if gaps:
        for gap in gaps:
            gap_id = str(gap.get("id") or "")
            lines.append(
                f"- [{_quality_gap_category_label(gap_id)}] {gap.get('label') or gap_id or '待处理'}"
            )
            if gap.get("message"):
                lines.append(f"  - 问题：{gap.get('message')}")
            if gap.get("action"):
                lines.append(f"  - 建议：{gap.get('action')}")
            for detail in _format_quality_gap_details(gap.get("details")):
                lines.append(f"  - 细节：{detail}")
    else:
        lines.append("- 暂无阻塞缺口。")
    lines.append("")
    checks = quality.get("checks") or []
    if checks:
        lines.extend(["### 模块检查明细", ""])
        for check in checks:
            status = "通过" if check.get("passed") else "待补"
            check_id = str(check.get("id") or "")
            lines.append(
                f"- {status} · [{_quality_gap_category_label(check_id)}] {check.get('label') or check_id}"
            )
            if not check.get("passed") and check.get("action"):
                lines.append(f"  - 建议：{check.get('action')}")
        lines.append("")

    manual_context = result.get("manual_review_context") or {}
    lines.extend(["## 人工工作表上下文", ""])
    lines.append(f"- 是否使用人工笔记：{'是' if manual_context.get('used') else '否'}")
    lines.append(f"- 工作表完成度：{manual_context.get('worksheet_score', 0)} / 100")
    lines.append(f"- 工作表等级：{manual_context.get('worksheet_label') or manual_context.get('worksheet_level') or ''}")
    if manual_context.get("summary"):
        lines.append(f"- 人工总结：{manual_context.get('summary')}")
    sections = manual_context.get("sections") or []
    if sections:
        lines.append(f"- 已填写模块：{_format_value(sections)}")
    lines.append("")

    acceptance_context = manual_context.get("quality_acceptance") or {}
    lines.extend(["## 人工质量验收反馈", ""])
    lines.append(f"- 是否有验收反馈：{'是' if acceptance_context.get('used') else '否'}")
    if acceptance_context.get("used"):
        lines.append(f"- 验收结论：{acceptance_context.get('verdict', '')}")
        if acceptance_context.get("score"):
            lines.append(f"- 人工评分：{acceptance_context.get('score')}")
        snapshot = acceptance_context.get("quality_snapshot") or {}
        if snapshot:
            lines.append(
                f"- 验收时 AI 自评分：{snapshot.get('score', 0)} / "
                f"{snapshot.get('label') or snapshot.get('level') or ''}"
            )
        if acceptance_context.get("summary"):
            lines.append(f"- 验收意见：{acceptance_context.get('summary')}")
        checks = acceptance_context.get("checks") or []
        if checks:
            lines.append(f"- 检查项：{_format_value(checks)}")
        if acceptance_context.get("notes"):
            lines.append(f"- 详细备注：{acceptance_context.get('notes')}")
        if acceptance_context.get("next_actions"):
            lines.append(f"- 下一步：{acceptance_context.get('next_actions')}")
    lines.append("")

    rerun_strategy = manual_context.get("rerun_strategy") or {}
    lines.extend(["## 重跑修正策略", ""])
    lines.append(f"- 是否启用：{'是' if rerun_strategy.get('active') else '否'}")
    if rerun_strategy.get("active"):
        lines.append(f"- 优先级：{rerun_strategy.get('priority', '')}")
        lines.append(f"- 策略摘要：{rerun_strategy.get('summary', '')}")
        if rerun_strategy.get("fix_targets"):
            lines.append(f"- 修正目标：{_format_value(rerun_strategy.get('fix_targets'))}")
        if rerun_strategy.get("do_not_repeat"):
            lines.append(f"- 禁止重复：{_format_value(rerun_strategy.get('do_not_repeat'))}")
        if rerun_strategy.get("required_evidence"):
            lines.append(f"- 必须核对证据：{_format_value(rerun_strategy.get('required_evidence'))}")
        if rerun_strategy.get("output_requirements"):
            lines.append(f"- 输出要求：{_format_value(rerun_strategy.get('output_requirements'))}")
    lines.append("")

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
        ("语音/口播拆解", "speech_analysis"),
        ("画面文字/OCR 拆解", "screen_text_analysis"),
        ("评论反馈洞察", "comment_insights"),
        ("复刻方案", "replication"),
        ("发布包", "publish_package"),
        ("富化数据使用情况", "enrichment_usage"),
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


def _quality_gap_category_label(gap_id: str) -> str:
    return QUALITY_GAP_CATEGORY_LABELS.get(gap_id, "待处理")


def _format_quality_gap_details(details) -> list[str]:
    if not isinstance(details, list):
        return []
    values = []
    for item in details[:8]:
        if not isinstance(item, dict):
            if _has_text(item):
                values.append(str(item))
            continue
        parts = []
        label = str(item.get("label") or item.get("id") or "").strip()
        location = str(item.get("location") or "").strip()
        message = str(item.get("message") or "").strip()
        if label:
            parts.append(label)
        if location:
            parts.append(location)
        if item.get("time") not in {None, ""} and item.get("limit") not in {None, ""}:
            parts.append(f"{item.get('time')}s / 上限 {item.get('limit')}s")
        if item.get("total") not in {None, ""} and item.get("limit") not in {None, ""}:
            parts.append(f"{item.get('total')}% / 目标 {item.get('limit')}%")
        if message:
            parts.append(message)
        if parts:
            values.append("；".join(parts))
    return values


def _format_value(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _truncate(value: str, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."
