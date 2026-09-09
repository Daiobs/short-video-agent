"""Synthetic report-reading contracts; no real samples or model-quality claims."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

import pytest

from test_content_aware_frontend import renderer_setup, run_node


REGIONS = {
    "positioning": "账号定位与本轮结论",
    "patterns": "核心规律与可复用结构",
    "samples": "代表样本对比",
    "actions": "下一条怎么做",
    "limits": "证据与限制",
}


@dataclass
class Element:
    tag: str
    attrs: dict = field(default_factory=dict)
    parent: Element | None = None
    children: list = field(default_factory=list)

    def text(self, *, core: bool = False) -> str:
        if core and self.tag == "details":
            return ""
        return " ".join(
            child.text(core=core) if isinstance(child, Element) else child
            for child in self.children
        )

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Element):
                yield from child.walk()

    def inside(self, tag: str) -> bool:
        ancestor = self.parent
        while ancestor is not None:
            if ancestor.tag == tag:
                return True
            ancestor = ancestor.parent
        return False


class ReportHTML(HTMLParser):
    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
                 "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, html: str):
        super().__init__(convert_charrefs=True)
        self.root = Element("root")
        self.current = self.root
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = Element(tag, dict(attrs), self.current)
        self.current.children.append(node)
        if tag not in self.VOID_TAGS:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent is not None:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)

    def regions(self, expected=None) -> dict[str, Element]:
        nodes = [node for node in self.root.walk() if "data-report-section" in node.attrs]
        assert [node.attrs["data-report-section"] for node in nodes] == (
            list(REGIONS) if expected is None else expected
        )
        for node in nodes:
            assert not node.inside("details"), node.attrs
            # The shared renderPublicCard stub emits its title as plain text.
            assert REGIONS[node.attrs["data-report-section"]] in node.text(core=True)
        return {node.attrs["data-report-section"]: node for node in nodes}


def render_report(**payload) -> ReportHTML:
    result = run_node(renderer_setup() + "\nconst payload = " + json.dumps(payload) + r""";
const before = JSON.stringify(payload);
const html = renderer.renderReportMarkup(payload);
console.log(JSON.stringify({html, unchanged: before === JSON.stringify(payload)}));
""")
    assert result["unchanged"], "Rendering must not mutate saved report inputs"
    return ReportHTML(result["html"])


def legacy_view_model() -> dict:
    return {
        "headline": "合成定位：给新手解释操作",
        "summary": "合成本轮结论：先呈现结果",
        "sections": {
            "core_judgment": {"bullets": ["合成观察：固定机位展示"]},
            "traffic_sources": {"hooks": ["合成解释：减少理解步骤"]},
            "repeatable_patterns": ["合成共性：结果与过程对照"],
            "formulas": ["合成旧公式：结果、过程、复核"],
            "next_actions": ["合成旧行动：录制两个不同开头"],
            "next_ideas": ["合成旧选题：桌面整理前后对比"],
        },
        "value_upgrade": {
            "sample_evidence": [{"sample_id": "synthetic_known_1", "title": "合成样本：收纳演示",
                                 "metric_label": "点赞", "metric_value": 0}],
            "evidence_gaps": ["合成限制：尚无连续动作证据"],
        },
    }


@pytest.mark.parametrize("focus", [None, {"primary": "tutorial", "section_order": ["visual_analysis"]}])
def test_legacy_view_model_keeps_five_readable_regions_with_or_without_focus(focus):
    report = render_report(result={"analysis_focus": focus} if focus else {},
                           viewModel=legacy_view_model())
    regions = report.regions()
    assert "合成定位：给新手解释操作" in regions["positioning"].text(core=True)
    assert "合成本轮结论：先呈现结果" in regions["positioning"].text(core=True)
    assert "合成旧公式：结果、过程、复核" in regions["patterns"].text(core=True)
    assert "合成样本：收纳演示" in regions["samples"].text(core=True)
    assert "合成旧行动：录制两个不同开头" in regions["actions"].text(core=True)
    assert "合成旧选题：桌面整理前后对比" in regions["actions"].text(core=True)
    assert "合成限制：尚无连续动作证据" in regions["limits"].text(core=True)


@pytest.mark.parametrize("with_focus", [False, True])
def test_structured_findings_groups_formulas_and_candidates_share_reading_order(with_focus):
    result = {
        "summary": "合成结论：操作对照值得复核",
        "focused_analysis": [{"question": "合成问题：为何保留对照？",
                              "observation": "合成观察：保留操作前后画面",
                              "interpretation": "合成解释：便于检查差异",
                              "transfer": "合成迁移：同机位重拍",
                              "evidence": ["synthetic_known_1"],
                              "uncertainty": "合成边界：不能确认因果"}],
        "content_groups": [{"category": "tutorial", "label": "合成教程组", "count": 2,
                            "analyzed_count": 1, "metadata_only_count": 1,
                            "sample_ids": ["synthetic_known_1"],
                            "patterns": ["合成组规律：固定角度对照"]}],
        "transferable_formulas": [{"name": "合成公式：对照结构",
                                   "when_to_use": "合成适用：能展示差异时",
                                   "beat_structure": ["合成拍法：首帧展示整理结果", "合成拍法：补录操作过程"],
                                   "risks": ["合成风险：不能照搬具体素材"],
                                   "evidence": ["synthetic_known_1", "sample_synthetic_unresolved_9"]}],
        "candidate_ideas": [{"title": "合成选题：抽屉分类演示", "formula_used": "合成公式：对照结构",
                             "why_worth_trying": "合成动机：验证操作是否易懂",
                             "production_requirements": ["合成准备：同机位拍摄两版"],
                             "evidence": ["synthetic_known_1"]}],
        "next_actions": ["合成行动：比较两版开头的留存"],
        "evidence_gaps": ["合成缺口：尚未验证留存变化"],
    }
    if with_focus:
        result["analysis_focus"] = {"primary": "tutorial", "section_order": ["visual_analysis"]}
    report = render_report(result=result, viewModel=legacy_view_model())
    regions = report.regions()
    assert "合成组规律：固定角度对照" in regions["patterns"].text()
    assert "仅元数据：1" in regions["patterns"].text()
    for text in ["合成观察：保留操作前后画面",
                 "合成公式：对照结构", "合成拍法：首帧展示整理结果", "合成适用：能展示差异时"]:
        assert text in regions["patterns"].text(core=True)
    for text in ["合成选题：抽屉分类演示", "合成准备：同机位拍摄两版", "合成行动：比较两版开头的留存"]:
        assert text in regions["actions"].text(core=True)
    assert "合成缺口：尚未验证留存变化" in regions["limits"].text(core=True)
    assert "合成样本：收纳演示" in regions["patterns"].text(core=True)
    assert "合成样本：收纳演示" in regions["actions"].text(core=True)
    core = report.root.text(core=True)
    assert "synthetic_known_1" not in core
    assert "sample_synthetic_unresolved_9" not in core
    assert "样本名称未记录" in core
    assert any("sample_synthetic_unresolved_9" in node.text() for node in report.root.walk() if node.tag == "details")


@pytest.mark.parametrize("empty", [[], [{}], "", None])
def test_empty_new_fields_fall_back_to_usable_old_sections(empty):
    model = legacy_view_model()
    model["value_upgrade"].update({"observation": {"bullets": empty},
                                   "explanation": {"bullets": empty},
                                   "execution": {"bullets": empty, "next_content_suggestions": empty}})
    report = render_report(result={"focused_analysis": empty, "content_groups": empty,
                                   "transferable_formulas": empty, "candidate_ideas": empty,
                                   "next_actions": empty, "evidence_gaps": empty}, viewModel=model)
    regions = report.regions()
    core = report.root.text(core=True)
    assert "合成观察：固定机位展示" in core
    assert "合成解释：减少理解步骤" in core
    assert "合成旧公式：结果、过程、复核" in regions["patterns"].text(core=True)
    assert "合成旧行动：录制两个不同开头" in regions["actions"].text(core=True)
    assert "合成旧选题：桌面整理前后对比" in regions["actions"].text(core=True)
    assert "合成限制：尚无连续动作证据" in regions["limits"].text(core=True)


def test_saved_text_is_escaped_in_every_reading_region():
    marker = '<img src=x onerror="synthetic()"> & <script>synthetic()</script>'
    model = legacy_view_model()
    model["headline"] = marker
    model["value_upgrade"]["sample_evidence"][0]["title"] = marker
    report = render_report(result={"summary": marker, "transferable_formulas": [{"name": marker}],
                                   "candidate_ideas": [{"title": marker}], "evidence_gaps": [marker]},
                           viewModel=model)
    regions = report.regions()
    for node in regions.values():
        assert marker in node.text(core=True)
    for node in report.root.walk():
        assert node.tag not in {"script", "img", "iframe"}
        assert not any(name.startswith("on") for name in node.attrs)


@pytest.mark.parametrize("metric", [None, "absent", 0])
def test_sample_metric_missing_is_not_rendered_as_zero(metric):
    model = legacy_view_model()
    sample = model["value_upgrade"]["sample_evidence"][0]
    if metric == "absent":
        sample.pop("metric_value")
    else:
        sample["metric_value"] = metric
    report = render_report(viewModel=model)
    text = report.regions()["samples"].text(core=True)
    if metric == 0:
        assert re.search(r"点赞\s*[:：]?\s*0(?!\d)", text)
        assert "未采集" not in text
    else:
        assert "未采集" in text
        assert not re.search(r"点赞\s*[:：]?\s*0(?!\d)", text)


def test_structural_quality_score_is_not_evidence_confidence():
    model = legacy_view_model()
    model["value_upgrade"].update({
        "quality": {"quality_score": 96},
        "diagnostics": {"quality_score": 96, "quality_label": "高可信", "source_label": "合成历史报告"},
    })
    report = render_report(viewModel=model)
    limits = report.regions()["limits"].text(core=True)
    assert "96" in report.regions()["limits"].text()
    assert "结构" in report.regions()["limits"].text()
    assert "高可信" not in report.root.text(core=True)
    assert "合成限制：尚无连续动作证据" in limits


@pytest.mark.parametrize("archived_count", [0, 3])
def test_archived_inventory_does_not_claim_actual_model_input(archived_count):
    overview = {"sample_count": 3, "selected_count": 3,
                "understanding_counts": {"full": 3, "partial": 0, "metadata_only": 0}}
    model = legacy_view_model()
    model["evidence_counts"] = {"sample_count": 3, "selected_count": 3,
                                "with_video": archived_count, "with_keyframes": archived_count,
                                "with_asr": archived_count, "with_ocr": archived_count,
                                "with_comments": archived_count}
    report = render_report(result={"summary": "合成历史报告，无请求输入清单"},
                           overview=overview, viewModel=model)
    regions = report.regions()
    limits = regions["limits"].text(core=True)
    assert "本次输入范围未完整记录" in limits
    assert "二手材料" in limits
    assert "归档" in report.root.text()
    assert not re.search(r"本次(?:仅|只)(?:有|使用|输入|读取|看)?标题", report.root.text(core=True))
    assert "本次已读取" not in report.root.text(core=True)


def test_sparse_historical_report_omits_empty_regions_without_inventing_content():
    report = render_report(result={"summary": "合成历史记录：只保留本轮结论"})
    regions = report.regions(expected=["positioning", "limits"])
    assert "合成历史记录：只保留本轮结论" in regions["positioning"].text(core=True)
    assert "本次输入范围未完整记录" in regions["limits"].text(core=True)


@pytest.mark.parametrize("source", ["request_evidence", "evidence_summary"])
def test_creator_unverified_public_manifest_does_not_claim_actual_input(source):
    manifest = {"visual_available": True, "asr": {"submitted": True},
                "ocr": {"submitted": False}, "comments": {"submitted": False},
                "valid_refs": ["synthetic_known_1"]}
    result = {source: manifest if source == "request_evidence" else {"submitted_evidence": manifest}}
    report = render_report(result=result, viewModel=legacy_view_model())
    limits = report.regions()["limits"].text(core=True)
    assert "二手材料" in limits
    assert "本次输入范围未完整记录" in limits
    assert "记录了直接图片输入" not in limits
    assert "ASR 转录文本：已提交" not in limits


def test_existing_secondary_summary_is_retained_without_claiming_title_only_input():
    summary = "合成既有单条分析摘要：固定机位记录整理前后的对照"
    report = render_report(result={"summary": summary})
    regions = report.regions(expected=["positioning", "limits"])
    assert summary in regions["positioning"].text(core=True)
    limits = regions["limits"].text(core=True)
    assert "本次输入范围未完整记录" in limits
    assert "二手材料" in limits
    assert "不等于本次直接查看原视频" in limits
    assert not re.search(r"本次(?:仅|只)(?:有|使用|输入|读取|看)?标题", report.root.text(core=True))


@pytest.mark.parametrize("item, expected", [
    ({"title": "合成标题", "idea": "合成具体方案"}, ["合成标题", "合成具体方案"]),
    ({"title": "合成方案", "sample_id": "sample_unknown", "opening": "先给成品", "beat_structure": ["再给步骤"], "production_requirements": ["一套工具"]}, ["合成方案", "先给成品", "再给步骤", "一套工具"]),
    ({"title": "合成依据", "evidence": [{"text": "已有摘要记录对照", "frame": "synthetic_frame"}]}, ["已有摘要记录对照"]),
    ({"title": "合成依据", "evidence": [{"sample_id": "sample_unknown", "text": "已有文本说明", "frame": "synthetic_frame"}]}, ["已有文本说明"]),
])
def test_reading_aliases_and_reference_objects_preserve_business_content(item, expected):
    report = render_report(result={"candidate_ideas": [item]}, viewModel=legacy_view_model())
    core = report.regions()["actions"].text(core=True)
    for text in expected:
        assert text in core
    assert "sample_unknown" not in core
    if "evidence" in item:
        assert "synthetic_frame" in report.root.text()


def test_empty_group_and_positioning_only_strategy_do_not_create_empty_patterns():
    report = render_report(result={"content_groups": [{}], "creator_strategy": {"positioning": "已有定位"}})
    regions = report.regions(expected=["positioning", "limits"])
    assert "已有定位" in regions["positioning"].text(core=True)
    assert "补充策略与模板" not in report.root.text()
    assert "样本类型" not in report.root.text()


def test_empty_new_members_fall_back_to_existing_members():
    report = render_report(result={"content_groups": [{"label": "合成分组", "sample_ids": [], "members": ["sample_known"]}]}, viewModel=legacy_view_model())
    assert "sample_known" in report.regions()["patterns"].text()
    assert "按样本类型归纳" in report.root.text()


@pytest.mark.parametrize("group, expected", [
    ({"label": "合成分组", "sample_count": 3}, "样本 3"),
    ({"label": "合成分组", "uncertainty": "合成限制不能丢失"}, "合成限制不能丢失"),
    ({"label": "合成分组", "metadata_only_count": 0}, "仅元数据：0"),
])
def test_partial_group_keeps_all_existing_statistics_and_limits(group, expected):
    report = render_report(result={"content_groups": [group]}, viewModel=legacy_view_model())
    assert expected in report.regions()["patterns"].text()


def render_job_phase(phase: dict, *, status: str = "running") -> ReportHTML:
    source = Path("app/static/app.js").read_text()
    block = source[source.index("function renderJobPhase(job)"):
                   source.index("function renderJobStatus(job,")]
    result = run_node(renderer_setup() + r"""
const hidden = new Set(['hidden']);
context.jobPhase = {innerHTML: '', classList: {
  add(name) {hidden.add(name);}, remove(name) {hidden.delete(name);}
}};
context.formatNumber = String;
context.normalizeItems = list;
context.formatReportValue = String;
context.isMeaningfulReportText = view.hasContent;
context.escapeHtml = view.renderValue;
""" + f"vm.runInNewContext({json.dumps(block)}, context);\n"
        + "const job = " + json.dumps({"status": status, "result_json": {"distill_phase": phase}})
        + r""";
const before = JSON.stringify(job);
context.renderJobPhase(job);
console.log(JSON.stringify({html: context.jobPhase.innerHTML,
  hidden: hidden.has('hidden'), unchanged: before === JSON.stringify(job)}));
""")
    assert result["unchanged"]
    assert not result["hidden"]
    return ReportHTML(result["html"])


@pytest.mark.parametrize("completed", [False, True])
def test_job_phase_batch_ordinal_and_budget_visibility_follow_lifecycle(completed):
    phase = {"current_phase": "complete" if completed else "batch_reduce",
             "status": "complete" if completed else "running",
             "phase_index": 3 if completed else 2, "batch_count": 1 if completed else 3,
             "total_budget_seconds": 900, "elapsed_seconds": 120, "remaining_seconds": 780,
             "timeout_seconds": 300}
    report = render_job_phase(phase, status="success" if completed else "running")
    text = report.root.text()
    chips = [node for node in report.root.walk()
             if "job-phase-chips" in node.attrs.get("class", "").split()]
    assert len(chips) == 1
    assert "总预算 900 秒" in chips[0].text()
    assert "本次请求最多等待 300 秒" in chips[0].text()
    if completed:
        assert "计划批次 1" in text
        assert not re.search(r"3\s*/\s*1", text)
        details = [node for node in report.root.walk() if node.tag == "details"
                   and any(child.tag == "summary" and child.text() == "运行详情"
                           for child in node.children if isinstance(child, Element))]
        assert len(details) == 1
        assert "open" not in details[0].attrs
        assert any(node is chips[0] for node in details[0].walk())
        assert "总预算" not in report.root.text(core=True)
    else:
        assert re.search(r"批次\s*2\s*/\s*3", text)
        assert not chips[0].inside("details")
        assert "总预算 900 秒" in report.root.text(core=True)


@pytest.mark.parametrize("index", [None, -1, 0, 4, 1.5, "2"])
def test_invalid_batch_phase_index_is_unknown_not_clamped(index):
    phase = {"current_phase": "batch_reduce", "status": "running", "batch_count": 3}
    if index is not None:
        phase["phase_index"] = index
    report = render_job_phase(phase)
    text = report.root.text(core=True)
    assert "批次序号未记录" in text
    assert "共 3 批" in text
    assert not re.search(r"批次\s*\d+\s*/\s*3", text)
