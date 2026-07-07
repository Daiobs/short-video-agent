from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


BEAUTY_PROFILES = {"beauty_cos", "photo_beauty"}
LOW_QUALITY_THRESHOLD = 70


@dataclass(frozen=True)
class CreatorStrategyPlan:
    next_topics: tuple[dict[str, Any], ...] = ()
    script_templates: tuple[dict[str, Any], ...] = ()
    shot_templates: tuple[dict[str, Any], ...] = ()
    title_cover_suggestions: tuple[dict[str, Any], ...] = ()
    pre_publish_checklist: tuple[str, ...] = ()
    low_confidence_notes: tuple[str, ...] = ()
    source: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "next_topics": [dict(item) for item in self.next_topics],
            "script_templates": [dict(item) for item in self.script_templates],
            "shot_templates": [dict(item) for item in self.shot_templates],
            "title_cover_suggestions": [dict(item) for item in self.title_cover_suggestions],
            "pre_publish_checklist": list(self.pre_publish_checklist),
            "low_confidence_notes": list(self.low_confidence_notes),
            "source": dict(self.source),
        }


def generate_creator_strategy_plan(
    creator_clone_strategy: dict,
    report_view_model: dict,
    report_quality: dict,
    diagnostics: dict,
    evidence_gaps: list[str],
    content_profile: str,
    selected_sample_evidence_summary: dict | None = None,
) -> dict:
    """Build an executable next-content plan from an existing distillation report.

    This is deliberately deterministic. It does not re-analyze videos, re-run
    enrichment, or call an LLM; it turns the already-distilled creator rules into
    a production plan that can be rendered and tested.
    """

    strategy = creator_clone_strategy if isinstance(creator_clone_strategy, dict) else {}
    report = report_view_model if isinstance(report_view_model, dict) else {}
    quality = report_quality if isinstance(report_quality, dict) else {}
    diag = diagnostics if isinstance(diagnostics, dict) else {}
    gaps = _string_list(evidence_gaps)
    profile = _normalize_profile(content_profile)
    sample_summary = selected_sample_evidence_summary if isinstance(selected_sample_evidence_summary, dict) else {}
    low_confidence_notes = _low_confidence_notes(quality, diag, gaps, sample_summary, has_view_model=bool(report))
    needs_review = bool(low_confidence_notes)

    topics = _build_next_topics(profile, strategy, report, needs_review)
    script_templates = _build_script_templates(profile, strategy, report, needs_review)
    shot_templates = _build_shot_templates(profile, strategy, report, needs_review)
    title_cover = _build_title_cover_suggestions(profile, strategy, report, needs_review)
    checklist = _build_pre_publish_checklist(profile, strategy, report, needs_review)

    plan = CreatorStrategyPlan(
        next_topics=tuple(topics[:8]),
        script_templates=tuple(script_templates[:6]),
        shot_templates=tuple(shot_templates[:6]),
        title_cover_suggestions=tuple(title_cover[:8]),
        pre_publish_checklist=tuple(checklist[:8]),
        low_confidence_notes=tuple(low_confidence_notes),
        source={
            "content_profile": profile,
            "report_quality_score": _quality_score(quality),
            "diagnostics": diag,
            "evidence_gaps": gaps,
            "sample_evidence_summary": sample_summary,
        },
    )
    return validate_creator_strategy_plan(plan.to_dict())


def validate_creator_strategy_plan(value: dict) -> dict:
    payload = value if isinstance(value, dict) else {}
    plan = {
        "next_topics": _dict_list(payload.get("next_topics")),
        "script_templates": _dict_list(payload.get("script_templates")),
        "shot_templates": _dict_list(payload.get("shot_templates")),
        "title_cover_suggestions": _dict_list(payload.get("title_cover_suggestions")),
        "pre_publish_checklist": _string_list(payload.get("pre_publish_checklist")),
        "low_confidence_notes": _string_list(payload.get("low_confidence_notes")),
    }
    if len(plan["next_topics"]) < 5:
        raise ValueError("next_topics must contain at least 5 items")
    if len(plan["script_templates"]) < 3:
        raise ValueError("script_templates must contain at least 3 items")
    if len(plan["shot_templates"]) < 3:
        raise ValueError("shot_templates must contain at least 3 items")
    if len(plan["title_cover_suggestions"]) < 5:
        raise ValueError("title_cover_suggestions must contain at least 5 items")
    if len(plan["pre_publish_checklist"]) < 5:
        raise ValueError("pre_publish_checklist must contain at least 5 items")
    plan["source"] = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    return plan


def _normalize_profile(value: str) -> str:
    profile = str(value or "").strip()
    if profile in BEAUTY_PROFILES or profile in {"knowledge", "emotional_copy", "story_twist", "commerce_seed"}:
        return profile
    return "general"


def _quality_score(report_quality: dict) -> int:
    score = report_quality.get("quality_score", report_quality.get("score", 0))
    try:
        return int(float(score or 0))
    except (TypeError, ValueError):
        return 0


def _low_confidence_notes(
    report_quality: dict,
    diagnostics: dict,
    evidence_gaps: list[str],
    sample_summary: dict,
    *,
    has_view_model: bool,
) -> list[str]:
    notes: list[str] = []
    score = _quality_score(report_quality)
    has_score = "quality_score" in report_quality or "score" in report_quality
    if not has_score:
        notes.append("报告缺少质量评分，本次创作方案需要人工复核。")
    if has_score and score < LOW_QUALITY_THRESHOLD:
        notes.append(f"报告质量分 {score}/100，下一批方案需要人工复核。")
    if not diagnostics:
        notes.append("报告缺少生成诊断，无法确认是否为完整大模型蒸馏结果。")
    if not has_view_model:
        notes.append("报告缺少结构化 view model，方案基于压缩策略字段生成。")
    if diagnostics.get("is_fallback"):
        notes.append(str(diagnostics.get("fallback_reason") or "当前报告来自降级或兜底结果，不能当作完整账号规律。"))
    source_label = str(diagnostics.get("source_label") or "")
    if "Prompt-only" in source_label or "待分析" in source_label:
        notes.append("当前报告没有可用大模型完整蒸馏结果，只能生成基础方向。")
    for label in _string_list(diagnostics.get("missing_evidence_labels")):
        notes.append(f"缺少{label}证据，相关建议需要人工复核。")
    for gap in evidence_gaps[:4]:
        notes.append(gap)
    counts = sample_summary.get("understanding") if isinstance(sample_summary.get("understanding"), dict) else {}
    metadata_only = int(counts.get("metadata_only") or 0)
    selected = int(sample_summary.get("selected_count") or 0)
    if selected and metadata_only >= max(1, selected // 2):
        notes.append("半数以上样本仅有元数据，标题、画面和互动结论应低置信处理。")
    return _unique_strings(notes, limit=8)


def _build_next_topics(profile: str, strategy: dict, report: dict, needs_review: bool) -> list[dict[str, Any]]:
    seed_ideas = _dict_or_text_items(strategy.get("idea_bank")) + _dict_or_text_items(_section(report, "next_ideas"))
    formulas = _dict_or_text_items(strategy.get("templates")) + _dict_or_text_items(_section(report, "formulas"))
    defaults = _profile_topic_defaults(profile)
    rows = seed_ideas + defaults
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows[:8], start=1):
        title = row.get("title") or row.get("name") or row.get("text") or row.get("value") or f"下一批选题 {index}"
        formula = row.get("formula_used") or (
            _item_title(formulas[(index - 1) % len(formulas)]) if formulas else _profile_formula_name(profile)
        )
        result.append(
            {
                "title": title,
                "angle": row.get("angle") or _profile_topic_angle(profile),
                "why": row.get("why") or row.get("reason") or "延续已蒸馏出的高互动规律，并替换具体人物、场景或主题。",
                "formula_used": formula,
                "expected_metric": row.get("expected_metric") or _profile_expected_metric(profile),
                "production_notes": row.get("production_requirements") or _profile_production_note(profile),
                "requires_review": needs_review,
            }
        )
    return _ensure_count(result, 5, lambda idx: _fallback_topic(profile, idx, needs_review))


def _build_script_templates(profile: str, strategy: dict, report: dict, needs_review: bool) -> list[dict[str, Any]]:
    strategy_items = _dict_or_text_items(strategy.get("content_strategy")) + _dict_or_text_items(strategy.get("templates"))
    defaults = _profile_script_defaults(profile)
    rows = strategy_items + defaults
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows[:5], start=1):
        name = row.get("name") or row.get("title") or row.get("text") or f"脚本结构 {index}"
        result.append(
            {
                "name": name,
                "best_for": row.get("best_for") or _profile_script_best_for(profile),
                "beats": row.get("beat_structure") if isinstance(row.get("beat_structure"), list) else _profile_script_beats(profile),
                "caption_voice": row.get("caption_voice") or _profile_caption_voice(profile),
                "evidence_basis": row.get("sample_id") or row.get("evidence") or "来自 creator_clone_strategy / report_view_model",
                "requires_review": needs_review,
            }
        )
    return _ensure_count(result, 3, lambda idx: _fallback_script(profile, idx, needs_review))


def _build_shot_templates(profile: str, strategy: dict, report: dict, needs_review: bool) -> list[dict[str, Any]]:
    visual_rules = _text_items(strategy.get("visual_rules")) + _text_items(_section(report, "repeatable_patterns"))
    result: list[dict[str, Any]] = []
    defaults = _profile_shot_defaults(profile)
    for index, row in enumerate(defaults[:5], start=1):
        item = dict(row)
        item["name"] = item.get("name") or f"镜头模板 {index}"
        item["evidence_basis"] = visual_rules[(index - 1) % len(visual_rules)] if visual_rules else "来自视觉/表达规律"
        item["requires_review"] = needs_review
        result.append(item)
    return _ensure_count(result, 3, lambda idx: _fallback_shot(profile, idx, needs_review))


def _build_title_cover_suggestions(profile: str, strategy: dict, report: dict, needs_review: bool) -> list[dict[str, Any]]:
    hooks = _text_items(strategy.get("hooks")) + _text_items(_section(report, "traffic_sources", "hooks"))
    defaults = _profile_title_cover_defaults(profile)
    result: list[dict[str, Any]] = []
    for index, row in enumerate(defaults[:8], start=1):
        item = dict(row)
        item["hook_basis"] = hooks[(index - 1) % len(hooks)] if hooks else item.get("hook_basis") or "来自报告流量来源"
        item["requires_review"] = needs_review
        result.append(item)
    return _ensure_count(result, 5, lambda idx: _fallback_title_cover(profile, idx, needs_review))


def _build_pre_publish_checklist(profile: str, strategy: dict, report: dict, needs_review: bool) -> list[str]:
    checks = _text_items(strategy.get("validation_rules")) + _text_items(_section(report, "checklist"))
    checks.extend(_profile_checklist_defaults(profile))
    if needs_review:
        checks.append("低置信建议必须先人工复核样本证据，不要直接发布。")
    return _unique_strings(checks, limit=8)[:8]


def _section(report: dict, *keys: str) -> Any:
    current: Any = report.get("sections") if isinstance(report.get("sections"), dict) else {}
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, dict):
        text = value.get("text") or value.get("title") or value.get("name") or value.get("value")
        return [str(text).strip()] if text else []
    if isinstance(value, (list, tuple)):
        rows: list[str] = []
        for item in value:
            rows.extend(_string_list(item))
        return [item for item in rows if item]
    return [str(value).strip()] if str(value).strip() else []


def _dict_or_text_items(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, str):
        return [{"text": value}]
    if isinstance(value, (list, tuple)):
        rows: list[dict[str, Any]] = []
        for item in value:
            rows.extend(_dict_or_text_items(item))
        return rows
    return [{"text": str(value)}]


def _text_items(value: Any) -> list[str]:
    return _unique_strings(_string_list(value), limit=12)


def _item_title(item: dict[str, Any]) -> str:
    return str(item.get("name") or item.get("title") or item.get("text") or item.get("formula") or "可复刻公式").strip()


def _unique_strings(values: list[str], limit: int = 8) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _ensure_count(rows: list[dict[str, Any]], count: int, factory) -> list[dict[str, Any]]:
    result = list(rows)
    index = 1
    while len(result) < count:
        result.append(factory(index))
        index += 1
    return result


def _profile_topic_defaults(profile: str) -> list[dict[str, Any]]:
    if profile in BEAUTY_PROFILES:
        return [
            {"title": "同一妆造三种人物状态测试", "angle": "甜美 / 冷感 / 反差各拍一版", "expected_metric": "停留和点赞"},
            {"title": "首帧眼神抓停留系列", "angle": "0-1 秒直接给脸、眼神和姿态", "expected_metric": "完播和点赞"},
            {"title": "低成本场景出片反差", "angle": "普通环境到成片效果的视觉反差", "expected_metric": "收藏和分享"},
            {"title": "热门角色妆造安全改编", "angle": "保留角色识别点，替换动作和标题", "expected_metric": "圈层互动"},
            {"title": "同一动作不同镜头距离", "angle": "近景、中景、俯拍三版 A/B 测试", "expected_metric": "停留差异"},
        ]
    if profile == "knowledge":
        return [
            {"title": "一个常见误区的三步纠正", "angle": "问题 -> 原因 -> 操作步骤", "expected_metric": "收藏"},
            {"title": "新手最容易忽略的检查清单", "angle": "列出可保存的步骤", "expected_metric": "收藏和分享"},
            {"title": "同一问题的错误示范和正确示范", "angle": "对比带来理解", "expected_metric": "完播"},
            {"title": "一分钟讲清一个高频问题", "angle": "承诺明确、步骤短", "expected_metric": "完播和收藏"},
            {"title": "评论区问题集中回答", "angle": "用用户原问题做开头", "expected_metric": "评论"},
        ]
    if profile == "emotional_copy":
        return [
            {"title": "被低估的人如何翻盘", "angle": "身份代入 -> 冲突 -> 情绪落点", "expected_metric": "点赞和转发"},
            {"title": "越沉默的人越有力量", "angle": "反差人设和情绪补偿", "expected_metric": "点赞"},
            {"title": "关系里真正清醒的瞬间", "angle": "冲突句 -> 自我确认", "expected_metric": "评论"},
            {"title": "低谷期不要做的三件事", "angle": "痛点清单 -> 希望落点", "expected_metric": "收藏"},
            {"title": "给正在硬撑的人一句话", "angle": "直接代入目标人群", "expected_metric": "转发"},
        ]
    return [
        {"title": "复刻最高互动样本的开头承诺", "angle": "保留结构，替换主题", "expected_metric": "点赞"},
        {"title": "把高评样本改成互动问题", "angle": "制造评论入口", "expected_metric": "评论"},
        {"title": "把高分享样本改成转发理由", "angle": "让观众愿意发给别人", "expected_metric": "分享"},
        {"title": "把高收藏样本改成清单模板", "angle": "增加复看价值", "expected_metric": "收藏"},
        {"title": "弱样本反向改写测试", "angle": "避开低效表达", "expected_metric": "完播"},
    ]


def _profile_script_defaults(profile: str) -> list[dict[str, Any]]:
    if profile in BEAUTY_PROFILES:
        return [
            {"name": "首帧视觉抓停留", "beat_structure": _profile_script_beats(profile), "best_for": "美拍 / COS / 出片类短视频"},
            {"name": "妆造亮点递进", "beat_structure": ["首帧给完整状态", "第二拍展示妆造细节", "第三拍切动作变化", "结尾用标题话题承接评论"]},
            {"name": "成片反差证明", "beat_structure": ["普通场景一闪而过", "给最好看的成片", "补一个拍摄动作", "结尾提示下一组主题"]},
        ]
    if profile == "knowledge":
        return [
            {"name": "问题-原因-步骤", "beat_structure": ["开头抛问题", "指出错误原因", "给 3 个步骤", "结尾提醒保存"]},
            {"name": "误区纠正", "beat_structure": ["说出常见错误", "展示后果", "给正确做法", "评论区收集问题"]},
            {"name": "清单教学", "beat_structure": ["承诺结果", "列清单", "逐条解释", "结尾给保存理由"]},
        ]
    if profile == "emotional_copy":
        return [
            {"name": "身份代入-冲突-落点", "beat_structure": ["点名人群", "抛出冲突句", "解释内在力量", "给情绪落点"]},
            {"name": "反差强者叙事", "beat_structure": ["外显柔弱", "内在克制", "价值判断", "结尾共鸣"]},
            {"name": "低谷翻盘", "beat_structure": ["承认处境", "给反差定义", "提炼金句", "评论区承接"]},
        ]
    return [
        {"name": "高互动样本复刻", "beat_structure": ["复制开头承诺", "替换具体素材", "保留互动钩子", "验证指标"]},
        {"name": "评论触发结构", "beat_structure": ["提出争议/问题", "给一个例子", "留出表达空间", "评论区引导"]},
        {"name": "收藏清单结构", "beat_structure": ["承诺可复用", "列步骤", "给注意点", "提醒收藏"]},
    ]


def _profile_script_beats(profile: str) -> list[str]:
    if profile in BEAUTY_PROFILES:
        return ["0-1 秒给人物脸/眼神/姿态", "2-4 秒展示妆造、服装或道具亮点", "中段给动作变化或镜头距离变化", "结尾用标题话题引导评论或收藏"]
    if profile == "knowledge":
        return ["提出具体问题", "解释为什么", "给出步骤", "提醒保存/评论提问"]
    if profile == "emotional_copy":
        return ["身份代入", "情绪冲突", "价值判断", "金句落点"]
    return ["开头承诺", "主体证明", "转折/亮点", "互动收口"]


def _profile_shot_defaults(profile: str) -> list[dict[str, Any]]:
    if profile in BEAUTY_PROFILES:
        return [
            {"name": "近景首帧抓停留", "first_frame": "人物脸、眼神、姿态直接占屏", "action": "微转头、抬眼或手势变化", "camera": "近景或半身，轻微俯拍/平拍", "light_scene": "统一服化色调，背景干净", "title_topic": "把人物状态写成点击理由", "validation_metric": "停留率 / 点赞", "risk_boundary": "避免只靠暴露或低俗暗示"},
            {"name": "妆造细节推进", "first_frame": "先给完整造型", "action": "手部、发饰、道具逐步进入画面", "camera": "近景到中景", "light_scene": "突出妆造颜色和材质", "title_topic": "强调角色/氛围/出片承诺", "validation_metric": "收藏 / 评论点名", "risk_boundary": "不要照搬原角色动作"},
            {"name": "成片反差证明", "first_frame": "最好看的成片先出现", "action": "切一个拍摄过程动作", "camera": "成片近景 + 过程侧拍", "light_scene": "普通场景与成片光线形成反差", "title_topic": "低成本也能出片", "validation_metric": "收藏 / 分享", "risk_boundary": "不要过度夸大器材效果"},
        ]
    return [
        {"name": "信息首帧", "first_frame": "问题或核心结论直接出现", "action": "主体进入画面或字幕出现", "camera": "稳定中近景", "light_scene": "信息清晰", "title_topic": "明确承诺", "validation_metric": "完播 / 收藏", "risk_boundary": "不要标题党过度"},
        {"name": "证明镜头", "first_frame": "结果或冲突先出现", "action": "展示证据或例子", "camera": "跟随信息推进", "light_scene": "突出主体", "title_topic": "结果导向", "validation_metric": "评论 / 分享", "risk_boundary": "不要伪造证据"},
        {"name": "结尾互动", "first_frame": "结论回收", "action": "抛出选择题或评论问题", "camera": "回到主体", "light_scene": "保持一致", "title_topic": "参与理由", "validation_metric": "评论", "risk_boundary": "不要诱导无意义互动"},
    ]


def _profile_title_cover_defaults(profile: str) -> list[dict[str, Any]]:
    if profile in BEAUTY_PROFILES:
        return [
            {"title": "这一眼真的很适合当封面", "cover_frame": "人物眼神最完整的一帧", "promise": "第一眼颜值/氛围", "hook_type": "视觉抓停留"},
            {"title": "同一套妆造，哪个状态更出片？", "cover_frame": "三状态并列或最好状态", "promise": "选择参与", "hook_type": "评论互动"},
            {"title": "普通场景也能拍成这样", "cover_frame": "成片反差最大的一帧", "promise": "低门槛出片", "hook_type": "收藏"},
            {"title": "这组更偏甜还是冷？", "cover_frame": "表情最有差异的一帧", "promise": "人设判断", "hook_type": "评论"},
            {"title": "这套造型的氛围感拉满", "cover_frame": "服化和背景最统一的一帧", "promise": "妆造/氛围", "hook_type": "点赞"},
        ]
    if profile == "knowledge":
        return [
            {"title": "新手最容易错的 3 个点", "cover_frame": "错误/正确对比", "promise": "避坑", "hook_type": "收藏"},
            {"title": "一分钟讲清这个问题", "cover_frame": "核心问题大字", "promise": "省时间", "hook_type": "完播"},
            {"title": "照着这 4 步做就够了", "cover_frame": "步骤清单", "promise": "可操作", "hook_type": "收藏"},
            {"title": "为什么你总是做不好？", "cover_frame": "问题场景", "promise": "原因解释", "hook_type": "评论"},
            {"title": "先收藏，迟早用得上", "cover_frame": "结果展示", "promise": "复看价值", "hook_type": "收藏"},
        ]
    return [
        {"title": "这条为什么能起量？", "cover_frame": "最强情绪/信息帧", "promise": "规律拆解", "hook_type": "完播"},
        {"title": "下一条可以直接复刻这个结构", "cover_frame": "结构最清楚的一帧", "promise": "可复用", "hook_type": "收藏"},
        {"title": "评论区会吵起来的点在这里", "cover_frame": "冲突点", "promise": "参与", "hook_type": "评论"},
        {"title": "高赞样本的共同点", "cover_frame": "代表样本", "promise": "规律", "hook_type": "点赞"},
        {"title": "别照搬，保留这个动作就够了", "cover_frame": "关键动作", "promise": "安全改编", "hook_type": "收藏"},
    ]


def _profile_checklist_defaults(profile: str) -> list[str]:
    if profile in BEAUTY_PROFILES:
        return [
            "0-1 秒是否直接给出人物脸、眼神、姿态或服化亮点。",
            "妆造、服装、发型、道具和背景是否服务同一种人设。",
            "镜头距离、俯仰角和光线是否强化颜值或氛围。",
            "动作变化是否足够让观众继续看，而不是静态摆拍。",
            "标题和话题是否把人物气质转化为可点击理由。",
            "复刻时是否避开低俗化、过度擦边或直接照搬原作品。",
        ]
    if profile == "knowledge":
        return [
            "开头是否提出一个具体问题。",
            "是否在前 3 秒给出明确学习承诺。",
            "步骤是否足够短，适合收藏复看。",
            "是否有例子或对比证明。",
            "标题/封面是否突出问题、承诺和保存理由。",
        ]
    if profile == "emotional_copy":
        return [
            "开头是否点名具体身份或处境。",
            "是否有情绪冲突，而不是泛泛鸡汤。",
            "中段是否给观众自我投射空间。",
            "结尾是否有金句或情绪落点。",
            "是否避免过度油腻、说教或直接复制文案。",
        ]
    return [
        "是否保留最高互动样本的开头承诺。",
        "是否替换成自己的素材、角色或场景。",
        "是否明确希望验证点赞、评论、分享还是收藏。",
        "是否避免照搬低置信结论。",
        "发布后是否记录 T+3/T+7 数据用于校准。",
    ]


def _profile_formula_name(profile: str) -> str:
    if profile in BEAUTY_PROFILES:
        return "首帧视觉 + 人设动作 + 标题话题"
    if profile == "knowledge":
        return "问题承诺 + 步骤证明 + 保存理由"
    if profile == "emotional_copy":
        return "身份代入 + 情绪冲突 + 金句落点"
    return "高互动样本结构复刻"


def _profile_topic_angle(profile: str) -> str:
    if profile in BEAUTY_PROFILES:
        return "围绕人物状态、妆造、镜头和标题话题做 A/B 测试"
    if profile == "knowledge":
        return "把高频问题拆成可保存步骤"
    if profile == "emotional_copy":
        return "用身份代入和情绪冲突形成共鸣"
    return "复刻高互动结构，替换具体内容"


def _profile_expected_metric(profile: str) -> str:
    if profile in BEAUTY_PROFILES:
        return "停留 / 点赞 / 评论"
    if profile == "knowledge":
        return "收藏 / 完播"
    if profile == "emotional_copy":
        return "点赞 / 转发 / 评论"
    return "按选题目标验证"


def _profile_production_note(profile: str) -> str:
    if profile in BEAUTY_PROFILES:
        return "先定封面首帧，再拍 3 个动作版本，标题用人物气质或出片承诺。"
    if profile == "knowledge":
        return "准备一个问题、一个例子和一张步骤清单。"
    if profile == "emotional_copy":
        return "先写身份代入句，再写冲突句和结尾落点。"
    return "保留结构，替换素材，记录验证指标。"


def _profile_script_best_for(profile: str) -> str:
    if profile in BEAUTY_PROFILES:
        return "视觉吸引、COS、美拍、出片类内容"
    if profile == "knowledge":
        return "教学、知识、步骤类内容"
    if profile == "emotional_copy":
        return "情绪文案、鸡汤、共鸣类内容"
    return "通用短视频内容"


def _profile_caption_voice(profile: str) -> str:
    if profile in BEAUTY_PROFILES:
        return "短句、角色气质、出片承诺，少解释。"
    if profile == "knowledge":
        return "明确、步骤化、有保存理由。"
    if profile == "emotional_copy":
        return "代入感强、克制、不空喊。"
    return "贴近已验证样本语气。"


def _fallback_topic(profile: str, index: int, needs_review: bool) -> dict[str, Any]:
    return {
        "title": f"{_profile_formula_name(profile)}测试 {index}",
        "angle": _profile_topic_angle(profile),
        "why": "补足最小数量的可执行选题，具体内容需结合账号素材再定。",
        "formula_used": _profile_formula_name(profile),
        "expected_metric": _profile_expected_metric(profile),
        "production_notes": _profile_production_note(profile),
        "requires_review": True,
    }


def _fallback_script(profile: str, index: int, needs_review: bool) -> dict[str, Any]:
    return {
        "name": f"{_profile_formula_name(profile)}脚本 {index}",
        "best_for": _profile_script_best_for(profile),
        "beats": _profile_script_beats(profile),
        "caption_voice": _profile_caption_voice(profile),
        "evidence_basis": "fallback",
        "requires_review": True,
    }


def _fallback_shot(profile: str, index: int, needs_review: bool) -> dict[str, Any]:
    item = _profile_shot_defaults(profile)[0]
    return {**item, "name": f"{item['name']} {index}", "requires_review": True}


def _fallback_title_cover(profile: str, index: int, needs_review: bool) -> dict[str, Any]:
    item = _profile_title_cover_defaults(profile)[0]
    return {**item, "title": f"{item['title']} {index}", "requires_review": True}
