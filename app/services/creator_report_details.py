"""Read same-report details without using the short presentation summaries."""

import json
import math


# Match the asset library's existing maximum result JSON size. Do not remove
# request compression limits: they serve a different purpose.
MAX_DETAIL_BYTES = 2 * 1024 * 1024
MAX_DETAIL_DEPTH = 8
MAX_DETAIL_NODES = 10000
LIMIT_NOTE = "完整详情超过安全读取范围，未展开；原始保存记录未修改。"
EMPTY_NOTE = "当前保存记录未提供完整内容。"
TITLE_KEYS = ("name", "title", "formula", "template", "idea", "text", "summary")
LABELS = {
    "when_to_use": "适用条件", "description": "说明", "beat_structure": "步骤",
    "beats": "步骤", "structure": "结构", "formula_used": "相关方法",
    "production_requirements": "制作要点", "why_worth_trying": "值得尝试的理由",
    "reason": "理由", "expected_metric_strength": "预期指标方向",
    "likely_strength": "预期优势", "risks": "风险与限制", "uncertainty": "尚不能确认",
    "evidence": "依据", "sample_id": "样本引用", "metric": "指标",
    "metric_value": "指标数值", "evidence_level": "证据等级", "low_confidence": "低置信标记",
    "input_material_needed": "所需素材", "opening_3s": "开头", "action": "具体动作",
}


def has_detail(value):
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list)):
        return any(has_detail(v) for v in (value.values() if isinstance(value, dict) else value))
    return isinstance(value, (bool, int, float)) and (not isinstance(value, float) or math.isfinite(value))


def report_detail_items(result, kind):
    strategy = result.get("creator_clone_strategy") or {}
    strategy = strategy if isinstance(strategy, dict) else {}
    view = result.get("creator_report_view_model") or {}
    view = view if isinstance(view, dict) else {}
    sections = view.get("sections") or {}
    sections = sections if isinstance(sections, dict) else {}
    legacy = "templates" if kind == "transferable_formulas" else "idea_bank"
    short = "formulas" if kind == "transferable_formulas" else "next_ideas"
    source, value = "", []
    try:
        nodes = 0

        def validate(item, depth=0):
            nonlocal nodes
            nodes += 1
            if depth > MAX_DETAIL_DEPTH or nodes > MAX_DETAIL_NODES:
                raise ValueError("detail limit")
            if isinstance(item, dict):
                for key, child in item.items():
                    if not isinstance(key, str):
                        raise ValueError("invalid key")
                    validate(child, depth + 1)
            elif isinstance(item, list):
                for child in item:
                    validate(child, depth + 1)
            elif not isinstance(item, (str, int, float, bool, type(None))):
                raise ValueError("invalid value")
        for name, candidate in ((kind, result.get(kind)), (legacy, strategy.get(legacy)),
                                (legacy, result.get(legacy)), ("saved_summary", sections.get(short))):
            nodes = 0
            validate(candidate)
            if has_detail(candidate):
                source, value = name, candidate
                break
        if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_DETAIL_BYTES:
            return {"source": source, "items": [], "notice": LIMIT_NOTE}
    except (ValueError, TypeError, RecursionError):
        return {"source": source, "items": [], "notice": LIMIT_NOTE}
    rows = value if isinstance(value, list) else [value]
    rows = [item for item in rows if isinstance(item, (str, dict, list)) and has_detail(item)]
    notice = "仅有同报告的已保存展示摘要，可能包含兼容建议；完整原文未记录。" if source == "saved_summary" else ""
    return {"source": source, "items": rows, "notice": notice}


def detail_title(item, index):
    if isinstance(item, str):
        return item, None
    if isinstance(item, dict):
        for key in TITLE_KEYS:
            if isinstance(item.get(key), str) and item[key].strip():
                return item[key], key
    return f"已保存内容 {index + 1}", None


def detail_markdown(result, kind):
    payload = report_detail_items(result, kind)
    lines = [payload["notice"]] if payload["notice"] else []

    def emit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if has_detail(child):
                    lines.extend(["", f"{LABELS.get(key, key)}："])
                    emit(child)
        elif isinstance(value, list):
            for child in value:
                emit(child)
        elif has_detail(value):
            lines.append("是" if value is True else "否" if value is False else str(value))
    for index, item in enumerate(payload["items"]):
        title, key = detail_title(item, index)
        lines.extend(["", f"### {title}", ""])
        if isinstance(item, dict):
            emit({k: v for k, v in item.items() if k != key})
        elif isinstance(item, list):
            emit(item)
    return "\n".join(lines) if payload["items"] or lines else EMPTY_NOTE
