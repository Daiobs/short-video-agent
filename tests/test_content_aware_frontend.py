"""Synthetic UI fixtures only; these are not real model-quality evidence."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


NODE_BINARY = next((str(path) for path in [
    shutil.which("node"),
    Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node",
] if path and Path(path).is_file()), None)


def run_node(script: str) -> dict:
    if NODE_BINARY is None:
        pytest.skip("Node.js is unavailable")
    completed = subprocess.run([NODE_BINARY, "-e", script], check=True, capture_output=True, text=True, timeout=15)
    return json.loads(completed.stdout)


def renderer_setup() -> str:
    source = Path("app/static/modules/creator-report-view.js").read_text()
    return "const vm = require('vm'); const context = {console}; context.window = context;\n" + f"vm.runInNewContext({json.dumps(source)}, context);\n" + r"""
const view = context.CreatorReportView;
const list = (v) => Array.isArray(v) ? v : v == null ? [] : [v];
const helpers = {
  compactReportList: (...items) => items.flatMap(list),
  creatorStrategyFromResult: (r) => r.creator_strategy || {},
  formatNumber: String, normalizeItems: list,
  publicValueHasContent: view.hasContent, qualityLabelFromScore: String,
  renderCompactPerformanceSegments: () => '', renderCreatorCloneEvidenceOverview: () => '',
  renderFormulaCards: view.renderValue, renderPublicCard: (title, body) => `<article>${title}${body}</article>`,
  renderPublicFields: view.renderValue, renderPublicList: view.renderValue,
  renderTopicBuckets: view.renderValue, cleanPublicReportText: String,
};
const renderer = view.createRenderer(helpers);
const synthetic = {
  summary: '合成示例/非真实模型产物',
  analysis_focus: {version: 1, primary: 'tutorial', label: '步骤教程', source: 'user',
    reason: '<标题与步骤>', initial_category: 'beauty_cos', auxiliary: ['beauty_cos'],
    section_order: ['script_structure', 'visual_analysis', 'replication']},
  focused_analysis: [{question: '合成：如何演示步骤？', observation: '<可见操作>',
    interpretation: '降低理解成本', transfer: '先结果后步骤', evidence: ['synthetic_sample_1'],
    uncertainty: '静态帧不能确认连续动作'}],
};
"""


@pytest.mark.parametrize("primary", ["tutorial", "knowledge"])
def test_case_focus_uses_saved_report_order_and_omits_empty_sections(primary: str) -> None:
    source = Path("app/static/case_detail.js").read_text()
    start = source.index("function renderPublicAnalysisHero")
    end = source.index("function renderAutoAnalysis(data)", start)
    script = renderer_setup() + f"vm.runInNewContext({json.dumps(source[start:end])}, context); synthetic.analysis_focus.primary = {json.dumps(primary)};\n" + r"""
context.escapeHtml = view.renderValue;
context.renderPublicCard = helpers.renderPublicCard;
context.renderPublicFields = helpers.renderPublicFields;
context.renderPublicList = helpers.renderPublicList;
context.analysisCategorySelect = {value: 'beauty_cos'};
const report = {...synthetic, script_structure: '合成旧顶层结构', visual_analysis: {subject: '合成人物'},
  risks: ['合成边界'], speech_analysis: {script_structure: '合成嵌套步骤'}, publish_package: {titles: []}};
const snapshot = JSON.stringify(report);
const html = context.renderPublicAnalysisCards(report);
const withSpeech = context.renderPublicAnalysisCards({...report, speech_analysis: {...report.speech_analysis, opening_line: '合成开头一句'}});
const fallback = context.renderPublicAnalysisCards({...report, speech_analysis: {script_structure: ''}});
const empty = context.renderPublicAnalysisCards({...report, script_structure: [], speech_analysis: {script_structure: ''}});
context.analysisCategorySelect.value = 'auto';
const unchanged = html === context.renderPublicAnalysisCards(report);
const legacy = context.renderPublicAnalysisCards({summary: '合成旧报告', visual_analysis: {subject: '旧主体'}});
console.log(JSON.stringify({html, unchanged, legacy, withSpeech, fallback, empty,
  unmutated: snapshot === JSON.stringify(report), hero: context.renderPublicAnalysisHero(report)}));
"""
    result = run_node(script)
    html = result["html"]
    assert result["unchanged"]
    assert result["unmutated"]
    assert html.count("合成嵌套步骤") == 1
    assert "合成旧顶层结构" not in html
    assert html.index("合成嵌套步骤") < html.index('data-analysis-section="visual_analysis"')
    assert result["withSpeech"].count("合成嵌套步骤") == 1
    assert "合成开头一句" in result["withSpeech"]
    assert result["fallback"].index("合成旧顶层结构") < result["fallback"].index('class="analysis-auxiliary"')
    assert 'data-analysis-section="script_structure"' not in result["empty"]
    assert html.index('data-analysis-section="script_structure"') < html.index('data-analysis-section="visual_analysis"')
    assert html.index("合成：如何演示步骤") < html.index('class="analysis-auxiliary"')
    assert "<summary>辅助分析</summary>" in html and "合成边界" in html
    assert 'data-analysis-section="speech_analysis"' not in html
    assert 'data-analysis-section="publish_package"' not in html
    assert "&lt;可见操作&gt;" in html and "<可见操作>" not in html
    assert all(text in html for text in ["用户指定", "判断依据", "支持证据", "尚不能确认"])
    assert "步骤教程" in result["hero"]
    assert "旧主体" in result["legacy"]


def test_creator_mixed_groups_show_actual_counts_and_report_focus() -> None:
    result = run_node(renderer_setup() + r"""
const report = {...synthetic,
  thinking_patterns: {assumptions: ['合成论证']}, expression_patterns: {visual_style: ['合成构图']},
  content_groups: [
    {category: 'beauty_cos', label: '视觉展示', count: 1, analyzed_count: 1, metadata_only_count: 0,
      sample_ids: ['synthetic_sample_1'], focused_analysis: synthetic.focused_analysis},
    {category: 'tutorial', label: '教程', count: 1, analyzed_count: 0, metadata_only_count: 1,
      sample_ids: ['synthetic_metadata_2']},
  ],
};
const html = renderer.renderReportMarkup({result: report, templateLabel: '实时选择不应覆盖报告'});
const blank = renderer.renderReportMarkup({result: {analysis_focus: synthetic.analysis_focus, focused_analysis: [{}]}});
const legacy = renderer.renderReportMarkup({result: {summary: '合成旧报告'}, templateLabel: '旧模板'});
console.log(JSON.stringify({html, blank, legacy}));
""")
    html = result["html"]
    assert "实时选择不应覆盖报告" not in html
    assert "本次分析重点：步骤教程" in html
    # Creator chapters keep the user reading order; type ordering stays inside chapters.
    assert html.index('data-report-section="positioning"') < html.index('data-report-section="patterns"')
    assert "合成论证" in html and "合成构图" in html
    assert "仅元数据：1，不视为已验证的内容规律" in html
    assert "已有分析：0" in html and "synthetic_metadata_2" in html
    assert "合成示例/非真实模型产物" in html
    assert "类型重点分析" not in result["blank"]
    assert "暂无观察结论" not in result["blank"]
    assert "旧模板" in result["legacy"] and "合成旧报告" in result["legacy"]


def test_case_direction_save_is_single_metadata_request_and_auto_survives_reload() -> None:
    source = Path("app/static/case_detail.js").read_text()
    controls = source[source.index("function findProfile"):source.index("function buildAnalysisHints")]
    handler = source[source.index('updateCategoryButton.addEventListener("click"'):source.index('saveWorksheetButton.addEventListener("click"')]
    result = run_node(renderer_setup() + r"""
let save;
const requests = [];
const loadedCase = {analysis_profiles: [{category_id:'tutorial', label:'教程'}]};
const analysisCategorySelect = {value: 'auto', innerHTML: ''};
const categoryDescription = {};
const categoryStatus = {classList: {remove() {}}};
const updateCategoryButton = {addEventListener(name, fn) {save = fn;}};
const escapeHtml = view.renderValue;
const caseId = 'synthetic_case';
let rendered;
function renderCase(data) { rendered = data; }
async function fetch(url, options) {
  requests.push({url, ...options});
  return {ok:true, json:async () => ({case:{analysis_result:synthetic}})};
}
""" + controls + handler + r"""
renderCategoryControls({analysis_direction:'auto', content_category:'tutorial'});
const options = analysisCategorySelect.innerHTML;
(async () => {await save(); console.log(JSON.stringify({requests, options, status:categoryStatus.textContent,
  reportPreserved:rendered.analysis_result === synthetic}));})();
""")
    assert '<option value="auto" selected>' in result["options"]
    assert len(result["requests"]) == 1
    request = result["requests"][0]
    assert request["url"] == "/api/cases/synthetic_case/analysis-category"
    assert json.loads(request["body"]) == {"category_id": "auto"}
    assert result["reportPreserved"]
    assert "现有报告仍按上次方向生成" in result["status"]


def test_creator_select_change_only_sets_notice_and_keeps_auto_option() -> None:
    import re

    template = Path("app/templates/index.html").read_text()
    select = re.search(r'<select id="profile-content-profile".*?</select>', template, re.S).group()
    source = Path("app/static/app.js").read_text()
    start = source.index("const profileContentProfile =")
    handler = source[start:source.index("const profileDistillMode =", start)]
    result = run_node(r"""
const vm = require('vm');
const notice = {};
const listeners = {};
const requests = [];
const control = {value:'tutorial', addEventListener(type, callback) {listeners[type] = callback;}};
let showStatus = true;
const document = {getElementById(id) {
  return id === 'profile-content-profile' ? control : showStatus ? notice : null;
}};
const context = {document, fetch(...args) {requests.push(args);}};
""" + f"vm.runInNewContext({json.dumps(handler)}, context);\n" + r"""
listeners.change();
const manualNotice = notice.textContent;
control.value = 'auto';
listeners.change();
showStatus = false;
listeners.change();
console.log(JSON.stringify({manualNotice, autoNotice:notice.textContent, requests, selected:control.value}));
""")
    assert "现有报告仍按上次方向生成" in result["manualNotice"]
    assert "下次主动蒸馏时使用所选方向" in result["autoNotice"]
    assert result["requests"] == []
    assert result["selected"] == "auto"
    assert '<option value="auto">' in select
    assert '<option value="tutorial">' in select
    assert "onchange=" not in select


def test_focus_helpers_handle_legacy_unknown_fields_and_missing_vs_zero() -> None:
    result = run_node(renderer_setup() + r"""
console.log(JSON.stringify({
  empty: view.renderFocusedAnalysis([{}, {question:'没有结论'}]),
  zero: view.renderValue({missing:null, count:0}),
  legacy: view.renderFocus({analysis_focus:{primary:'unknown', source:'legacy'}}),
  sections: view.renderSections({section_order:['unknown']}, [{key:'visual_analysis',label:'画面',value:'合成观察'}]),
}));
""")
    assert result["empty"] == ""
    assert "missing" not in result["zero"] and "0" in result["zero"]
    assert "来源未记录" in result["legacy"]
    assert "辅助分析" in result["sections"] and "合成观察" in result["sections"]


def test_creator_render_failure_preserves_last_usable_report() -> None:
    result = run_node(renderer_setup() + r"""
const container = {innerHTML:renderer.renderReportMarkup({result:synthetic})};
renderer.showFailure(container, '合成重新分析失败 <error>');
console.log(JSON.stringify({html:container.innerHTML, preserved:renderer.hasReport(container)}));
""")
    assert result["preserved"]
    assert "合成：如何演示步骤" in result["html"]
    assert "&lt;error&gt;" in result["html"]
    assert "上次可用报告已保留" in result["html"]


def test_case_metadata_missing_counts_do_not_become_zero() -> None:
    source = Path("app/static/case_detail.js").read_text()
    start = source.index("  renderDefinitionList(caseMeta, [", source.index("function renderCase(data)"))
    block = source[start:source.index("  renderDefinitionList(primaryCaseMeta", start)]
    number = source[source.index("function formatNumber("):source.index("function formatSeconds(")]
    result = run_node(number + r"""
const caseMeta = {}, metadata = {}, analysisInput = {}, video = {}, ffprobe = {};
const loadedCase = {case_id: 'synthetic_metadata_case', paths: {}};
const formatSeconds = String, formatBytes = String;
let rows;
function renderDefinitionList(target, value) { rows = Object.fromEntries(value); }
function render(stats) {
""" + block + r"""
return rows;
}
console.log(JSON.stringify({
  missing: render({like_count:null, share_count:null}),
  zero: render({like_count:0, comment_count:0, share_count:0, engagement_score:0}),
  positive: render({like_count:1234}), globalNull: formatNumber(null),
}));
""")
    for label in ["点赞", "评论", "分享", "互动分"]:
        assert result["missing"][label] == "未采集"
        assert result["zero"][label] == "0"
    assert result["positive"]["点赞"] == "1,234"
    assert result["globalNull"] == "0"


def test_focus_direction_labels_map_known_ids_and_escape_unknown_values() -> None:
    result = run_node(renderer_setup() + r"""
const report = {analysis_focus: {primary:'tutorial', source:'auto', initial_category:'beauty_cos',
  auxiliary:['photo_beauty', 'knowledge', 'emotional_copy', 'plot_twist', 'commerce_seed', '<synthetic_unknown>']}};
const before = JSON.stringify(report);
console.log(JSON.stringify({html:view.renderFocus(report), unchanged:before === JSON.stringify(report)}));
""")
    html = result["html"]
    assert "本次分析重点：步骤教程" in html
    assert "自动初判：美拍 / COS / 颜值" in html
    assert all(label in html for label in ["摄影美拍 / 出片教程", "知识 / 观点", "情绪文案", "剧情 / 反转", "种草 / 带货"])
    assert "beauty_cos" not in html and "emotional_copy" not in html
    assert "&lt;synthetic_unknown&gt;" in html
    assert result["unchanged"]


def test_category_review_is_optional_advice_not_report_direction() -> None:
    source = Path("app/static/case_detail.js").read_text()
    block = source[source.index("function renderPublicAnalysisHero"):source.index("function renderAutoAnalysis(data)")]
    result = run_node(renderer_setup() + f"vm.runInNewContext({json.dumps(block)}, context);\n" + r"""
context.escapeHtml = view.renderValue;
context.renderPublicCard = helpers.renderPublicCard;
context.renderPublicFields = helpers.renderPublicFields;
context.renderPublicList = helpers.renderPublicList;
const report = {...synthetic, category_review:{suggested_category:'beauty_cos', reason:'合成复核 <证据不足>'},
  speech_analysis:{script_structure:'合成教程结构'}, visual_analysis:{subject:'合成主体'}};
const before = JSON.stringify(report);
const caseHtml = context.renderPublicAnalysisCards(report);
const creatorHtml = renderer.renderReportMarkup({result:report});
const legacy = {summary:'合成旧报告', category_review:report.category_review};
console.log(JSON.stringify({caseHtml, creatorHtml,
  legacyCase:context.renderPublicAnalysisCards(legacy), legacyCreator:renderer.renderReportMarkup({result:legacy}),
  empty:view.renderFocus({category_review:{}}), unchanged:before === JSON.stringify(report)}));
""")
    for key in ["caseHtml", "creatorHtml", "legacyCase", "legacyCreator"]:
        html = result[key]
        assert "模型复核建议（未自动切换）" in html
        assert "建议方向：美拍 / COS / 颜值" in html
        assert "合成复核 &lt;证据不足&gt;" in html
    assert "本次分析重点：步骤教程" in result["caseHtml"]
    assert result["caseHtml"].index('data-analysis-section="script_structure"') < result["caseHtml"].index('data-analysis-section="visual_analysis"')
    assert result["empty"] == ""
    assert result["unchanged"]
