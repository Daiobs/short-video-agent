"""PR29 compact report regressions. All report content here is synthetic."""
import json
from html.parser import HTMLParser

import pytest

from test_content_aware_frontend import renderer_setup, run_node


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag == "details":
            self.depth += 1

    def handle_endtag(self, tag):
        if tag == "details":
            self.depth -= 1

    def handle_data(self, data):
        if not self.depth:
            self.text.append(data)


def visible(html):
    parser = VisibleText()
    parser.feed(html)
    return " ".join(parser.text)


@pytest.mark.parametrize("focus", ["beauty_cos", "tutorial"])
def test_long_report_highlights_actions_and_complete_content(focus):
    report = {
        "summary": "SYNTHETIC positioning. " + "Long qualified account observation. " * 30,
        "analysis_focus": {"primary": focus, "source": "user"},
        "focused_analysis": [
            {"question": f"Finding {i}", "observation": f"Observation {i}.",
             "interpretation": "A hypothesis, not established causality.",
             "transfer": "Try one controlled change.", "evidence": ["sample_synthetic"],
             "uncertainty": f"Important qualification {i}"}
            for i in range(8)
        ],
        "next_actions": [f"Visible action {i}" for i in range(6)],
        "candidate_ideas": [{"title": f"Idea {i}", "production_requirements": ["Material " * 150],
                             "new_extension": f"Preserved extension {i}"} for i in range(5)],
        "transferable_formulas": [{"name": f"Formula {i}", "beat_structure": "Start → Demonstrate → Result",
                                   "risks": [f"Formula condition {i}"]} for i in range(5)],
    }
    result = run_node(renderer_setup() + f"const report={json.dumps(report)};\n" + """
const before = JSON.stringify(report);
const html = renderer.renderReportMarkup({result:report, viewModel:{summary:report.summary, headline:report.summary,
  value_upgrade:{observation:{bullets:[report.summary]}}}});
console.log(JSON.stringify({html, unchanged:before === JSON.stringify(report)}));
""")
    html = result["html"]
    text = visible(html)
    assert result["unchanged"]
    assert text.count("SYNTHETIC positioning") == 1
    assert "Finding 0" in text and "Finding 1" in text and "Finding 2" not in text
    assert "Visible action 0" in text and "Visible action 3" not in text
    assert html.index('data-report-section="actions"') < html.index('data-report-section="formulas"')
    for i in range(8):
        assert f"Important qualification {i}" in html
    for i in range(5):
        assert f"Preserved extension {i}" in html and f"Formula condition {i}" in html
    assert "Long qualified account observation. " * 29 in html


def test_rankings_merge_all_metrics_without_causal_preset_or_missing_zero_coercion():
    data = run_node(renderer_setup() + r"""
const sample = {sample_id:'sample_synthetic', title:'Synthetic <unsafe>', case_id:'case_synthetic'};
const html = renderer.renderReportMarkup({result:{
  performance_segments:{likes:[{...sample, metric:'like_count', metric_value:0, share_count:7}],
    comments:[{...sample, metric:'comment_count', metric_value:4, share_count:9}],
    collected:[{...sample, metric:'collect_count', metric_value:2, url:'javascript:alert(1)'}]},
}, viewModel:{value_upgrade:{sample_evidence:[{...sample, metric:'like_count', metric_value:0,
  reason:'高赞代表，通常支撑情绪/身份共鸣判断'}]}}});
console.log(JSON.stringify({html}));
""")
    html = data["html"]
    text = visible(html)
    assert html.count('class="report-sample-card"') == 1
    assert '<dt>点赞</dt><dd>0' in html
    assert '<dt>播放</dt><dd>未采集' in html
    assert '<dt>分享</dt><dd>7 / 9' in html
    assert "记录冲突" in text
    assert "通常支撑" not in text and "通常支撑" in html
    assert 'href="/cases/case_synthetic"' in html
    assert 'href="javascript:' not in html and "<unsafe>" not in html


def test_empty_new_fields_fall_back_and_local_advice_is_not_model_claim():
    data = run_node(renderer_setup() + r"""
const html = renderer.renderReportMarkup({result:{transferable_formulas:[], candidate_ideas:[],
  creator_clone_strategy:{templates:[{name:'Generic formula'}],
    idea_bank:[{title:'Historical idea'}]},
  report_provenance:{version:1,fields:{'creator_clone_strategy.templates':'fallback'}}},
  viewModel:{sections:{next_actions:['Legacy action']}}});
console.log(JSON.stringify({html}));
""")
    text = visible(data["html"])
    assert "Legacy action" in text and "Historical idea" in text
    assert "Generic formula" not in text and "Generic formula" in data["html"]
    assert "通用参考建议 · 本地预设" in data["html"]
    assert "来源未区分" in text


def test_actual_final_request_counts_distinct_samples_and_hides_excerpts():
    data = run_node(renderer_setup() + r"""
const row={sample_id:'sample_one',materials:[{kind:'asr',excerpt:'PRIVATE_EXCERPT'},
  {kind:'prior_analysis',secondhand:true}],image_orders:[1],truncated:true};
const manifest={version:1,source:'actual_request',attempt:2,final_attempt:true,degraded:true,
  structured_rows_found:true,samples:[row,row,{sample_id:'sample_two',materials:[{kind:'ocr'}],image_orders:[]}]};
const render=(request_evidence)=>renderer.renderReportMarkup({result:{request_evidence,
  performance_segments:{likes:[{sample_id:'sample_one',title:'Synthetic first'}]}}});
console.log(JSON.stringify({html:render(manifest),failed:render({...manifest,final_attempt:false}),
  model:render({...manifest,source:'model'}),old:render({})}));
""")
    html = data["html"]
    assert "本次提交 2 条样本；直接图片 1 张，覆盖 1 条样本；1 条未直接查看图片" in html
    assert "转录 1 条样本" in html and "已有分析（二手） 1 条样本" in html
    assert "1 条样本的输入短摘有截短" in html
    assert "PRIVATE_EXCERPT" not in html
    assert "Synthetic first" in html and "使用降级输入" in html
    for key in ["failed", "model", "old"]:
        assert "本次输入范围未完整记录" in data[key]
        assert "最终成功请求" not in data[key]


def test_backend_field_and_per_item_provenance_separate_local_defaults():
    data = run_node(renderer_setup() + r"""
const html=renderer.renderReportMarkup({result:{next_actions:['Model action'],
  report_provenance:{version:1,fields:{next_actions:'model'}}},viewModel:{
  sources:{'sections.formulas':['fallback','model']},sections:{formulas:['Local default','Model structure']}}});
console.log(JSON.stringify({html}));
""")
    text = visible(data["html"])
    assert "Model action" in text and "Model structure" in text
    assert "本轮模型分析" in text
    assert "Local default" not in text and "Local default" in data["html"]


def test_historical_object_thinking_patterns_have_visible_judgment_content():
    data = run_node(renderer_setup() + r"""
console.log(JSON.stringify({html:renderer.renderReportMarkup({result:{focused_analysis:[],
  thinking_patterns:{assumptions:['Synthetic audience assumption'],
    tension_sources:['Synthetic contrast'], detail_selection_rules:['Synthetic concrete choice']},
  next_actions:['Synthetic action remains early']}})}));
""")
    text = visible(data["html"])
    assert "Synthetic concrete choice" in data["html"]
    assert "Synthetic concrete choice" not in text
    for phrase in ["Synthetic audience assumption", "Synthetic contrast",
                   "Synthetic action remains early"]:
        assert phrase in text


@pytest.mark.parametrize("strategy", [None, {}, []])
def test_report_never_reads_global_strategy_for_core_or_evidence_details(strategy):
    data = run_node(renderer_setup() + f"const ownStrategy={json.dumps(strategy)};\n" + r"""
let helperCalls=0;
helpers.creatorStrategyFromResult=()=>{helperCalls++; return {positioning:'STALE GLOBAL POSITIONING',
  templates:[{name:'STALE GLOBAL TEMPLATE'}],idea_bank:[{title:'STALE GLOBAL IDEA'}]};};
const local=view.createRenderer(helpers);
const report={summary:'Current report',creator_clone_strategy:ownStrategy};
const before=JSON.stringify(report);
const html=local.renderReportMarkup({result:report});
const own=local.renderReportMarkup({result:{creator_clone_strategy:{positioning:'OWN POSITIONING',
  templates:[{name:'OWN TEMPLATE'}],idea_bank:[{title:'OWN IDEA'}]}}});
console.log(JSON.stringify({html,own,helperCalls,unchanged:before===JSON.stringify(report)}));
""")
    assert data["helperCalls"] == 0
    assert data["unchanged"]
    assert "STALE GLOBAL" not in data["html"] and "STALE GLOBAL" not in data["own"]
    assert all(text in data["own"] for text in ["OWN POSITIONING", "OWN TEMPLATE", "OWN IDEA"])


@pytest.mark.parametrize("claim", ["model", "fallback", "deterministic"])
def test_item_source_claims_cannot_override_unknown_or_backend_provenance(claim):
    data = run_node(renderer_setup() + f"const claim={json.dumps(claim)};\n" + r"""
const report={candidate_ideas:[{title:'Self claimed source',source:claim,provenance:claim}]};
const render=(fields)=>renderer.renderReportMarkup({result:{...report,
  ...(fields?{report_provenance:{version:1,fields}}:{})}});
console.log(JSON.stringify({unknown:render(),model:render({candidate_ideas:'model'}),
  fallback:render({candidate_ideas:'fallback'})}));
""")
    unknown = visible(data["unknown"])
    assert "Self claimed source" in unknown and "来源未区分" in unknown
    assert "本轮模型分析" not in unknown and "本地数据整理" not in unknown
    assert 'class="report-generic-advice"' not in data["unknown"]
    assert "本轮模型分析" in visible(data["model"])
    assert "Self claimed source" not in visible(data["fallback"])
    assert "Self claimed source" in data["fallback"]
    assert 'class="report-generic-advice"' in data["fallback"]


@pytest.mark.parametrize("text", ["长行动" * 100, "<unsafe>" + "X" * 400, "🎬" * 200])
def test_unpunctuated_long_actions_have_safe_prefix_and_lossless_remainder(text):
    from test_creator_report_reading import ReportHTML

    data = run_node(renderer_setup() + f"const action={json.dumps(text)};\n" + r"""
console.log(JSON.stringify({html:renderer.renderReportMarkup({result:{next_actions:[action]}})}));
""")
    report = ReportHTML(data["html"])
    action = next(node for node in report.root.walk() if node.attrs.get("class") == "report-action-card")
    prefix, remainder = text[:160], text[160:]
    assert prefix in action.text(core=True)
    disclosure = next(node for node in action.walk() if node.attrs.get("class") == "report-long-copy")
    assert remainder in disclosure.text()
    assert not any(node.tag in {"unsafe", "script", "img"} for node in report.root.walk())


def test_all_important_limits_remain_visible_beyond_first_two():
    from test_creator_report_reading import ReportHTML

    report = {"evidence_gaps": ["Ordinary gap one", "Ordinary gap two",
                                "Only two samples directly observed", "No causal validation " * 30],
              "report_quality": {"evidence_warnings": ["Speech remains unknown"]}}
    model = {"value_upgrade": {"low_confidence_reasons": ["Missing denominator, no interaction rate"]}}
    data = run_node(renderer_setup() + f"const result={json.dumps(report)},viewModel={json.dumps(model)};\n" + r"""
console.log(JSON.stringify({html:renderer.renderReportMarkup({result,viewModel})}));
""")
    limits = ReportHTML(data["html"]).regions(expected=["limits"])["limits"].text(core=True)
    for text in [*report["evidence_gaps"], "Speech remains unknown", "Missing denominator, no interaction rate"]:
        assert text in limits
    assert "查看其余限制" not in data["html"]


def test_two_findings_keep_actions_uncertainty_and_friendly_evidence_visible():
    from test_creator_report_reading import ReportHTML

    report = {
        "focused_analysis": [
            {"question": f"Tutorial judgment {i}", "observation": f"Show operation {i}",
             "transfer": f"Try one demonstration {i}", "interpretation": "Lengthy explanation " * 60,
             "evidence": ["sample_synthetic", "Additional textual support " * 40],
             "uncertainty": f"Critical uncertainty {i}: " + "not validated " * 20}
            for i in range(4)
        ],
        "performance_segments": {"likes": [{"sample_id": "sample_synthetic", "title": "Friendly tutorial sample"}]},
        "reference_manifest": {"version": 1, "scope": "actual_request", "samples": [
            {"sample_id": "sample_synthetic", "title": "Friendly tutorial sample", "open_url": ""}
        ], "entries": []},
        "next_actions": ["Record next tutorial now"],
    }
    data = run_node(renderer_setup() + f"const report={json.dumps(report)};\n" + r"""
console.log(JSON.stringify({html:renderer.renderReportMarkup({result:report})}));
""")
    root = ReportHTML(data["html"]).root
    findings = [node for node in root.walk() if node.attrs.get("class") == "report-finding-card"]
    assert len(findings) == 4
    assert not findings[0].inside("details") and not findings[1].inside("details")
    assert findings[2].inside("details") and findings[3].inside("details")
    for i, finding in enumerate(findings[:2]):
        core = finding.text(core=True)
        assert f"Show operation {i}" in core and f"Try one demonstration {i}" in core
        assert report["focused_analysis"][i]["uncertainty"] in core
        assert "Friendly tutorial sample" in core and "sample_synthetic" not in core
        assert "Lengthy explanation" not in core
        assert report["focused_analysis"][i]["interpretation"] in finding.text()
        assert report["focused_analysis"][i]["evidence"][1] in finding.text()
    assert "Record next tutorial now" in root.text(core=True)
