"""Synthetic equivalents of the real C's nested/stringified shapes, never private data."""
import json
from pathlib import Path

from test_content_aware_frontend import renderer_setup, run_node
from test_creator_report_reading import ReportHTML


def render_fixture():
    fixture = json.loads(Path("tests/fixtures/creator_reference_review_synthetic.json").read_text())
    result = run_node(renderer_setup() + f"const report={json.dumps(fixture)};" + """
const before=JSON.stringify(report);
const html=renderer.renderReportMarkup({result:report});
console.log(JSON.stringify({html,unchanged:before===JSON.stringify(report)}));
""")
    assert result["unchanged"]
    return ReportHTML(result["html"]), result["html"]


def test_nested_reference_rendering_uses_server_mapping_and_keeps_source_details():
    report, html = render_fixture()
    regions = report.regions()
    for region in ["patterns", "formulas", "actions"]:
        core = regions[region].text(core=True)
        assert "合成：蓝色造型对照" in core
        assert "sample_fixture" not in core
        assert "此条未单列支持依据" not in core
    core = report.root.text(core=True)
    assert "样本 2（名称未记录）" in core
    assert "未提供具体片段定位" in core
    assert "引用无法定位，需复核" in core
    assert "模型伪造标题不可使用" not in core
    assert "sample_fixture_onne" in html  # Original audit is retained.
    assert 'href="/cases/case_fixture_one"' in html
    assert 'href="javascript:' not in html
    assert 'href="/cases/sample_fixture_onne"' not in html
    assert html.count('class="report-sample-card"') == 5
    assert "high five" in core  # Do not globally replace quoted prose.
    assert "模型自评较高" in html and "不是事实准确率" in html
    assert "静态图不能确认整段视频固定机位" in core


def test_reference_manifest_is_authoritative_over_model_or_legacy_titles():
    result = run_node(renderer_setup() + """
const html=renderer.renderReportMarkup({result:{
 reference_manifest:{version:1,samples:[],entries:[]},
 focused_analysis:[{observation:'参照 sample_fake',evidence:[{sample_id:'sample_fake',title:'FAKE TITLE',case_id:'case_fake'}]}],
 transferable_formulas:[{name:'Formula',supporting_samples:[{sample_id:'sample_fake',title:'FAKE TITLE'}]}]
},viewModel:{value_upgrade:{sample_evidence:[{sample_id:'sample_fake',title:'STALE TITLE'}]}}});
console.log(JSON.stringify({html}));
""")
    report = ReportHTML(result["html"])
    core = report.root.text(core=True)
    assert "FAKE TITLE" not in core and "STALE TITLE" not in core
    assert "引用无法定位" in core
    assert 'href="/cases/case_fake"' not in result["html"]


def test_phone_action_anchor_precedes_direction_notes_and_does_not_change_route():
    report, html = render_fixture()
    assert html.index("data-report-action-jump") < html.index('class="analysis-focus"')
    assert html.index("data-report-action-jump") < html.index('data-report-section="patterns"')
    assert html.index('data-report-section="patterns"') < html.index('data-report-section="actions"')
    result = run_node("""
let listener, prevented=0, scrolled=0, focused=0;
const document={addEventListener:(event,fn)=>{if(event==='click')listener=fn;}};
""" + renderer_setup().replace("const context = {console};", "const context = {console,document};") + """
const target={scrollIntoView:()=>scrolled++,focus:()=>focused++};
listener({target:{closest:()=>({closest:()=>({querySelector:()=>target})})},preventDefault:()=>prevented++});
console.log(JSON.stringify({prevented,scrolled,focused}));
""")
    assert result == {"prevented": 1, "scrolled": 1, "focused": 1}
    css = Path("app/static/app.css").read_text()
    assert ".report-priority-action-link { display: none; }" in css
    assert "@media (max-width: 767px)" in css


def test_history_inventory_does_not_claim_actual_comment_input():
    result = run_node(renderer_setup() + """
const html=renderer.renderReportMarkup({result:{summary:'Historical',next_actions:['Existing action']},
 viewModel:{confidence_note:'STALE comments covered and high confidence',evidence_counts:{with_comments:5},
 value_upgrade:{diagnostics:{coverage_text:'评论库存5条'}}}});
console.log(JSON.stringify({html}));
""")
    core = ReportHTML(result["html"]).root.text(core=True)
    assert "本次输入范围未完整记录" in core
    assert "STALE comments" not in core
    assert "评论库存5条" in result["html"]


def test_original_expression_objects_win_over_lossy_vm_flattening():
    result = run_node(renderer_setup() + """
const pattern={pattern:'同一背景中的造型变化',evidence:['sample_example'],evidence_level:'high',
 note:'静态图不能确认完整运镜'};
const flattened='同一背景中的造型变化：证据：sample_example；证据等级：high';
const html=renderer.renderReportMarkup({result:{focused_analysis:[],thinking_patterns:{},
 expression_patterns:{visual_style:[pattern],shot_types:[{pattern:'全身和近景分工',evidence:['sample_example'],evidence_level:'high'}]},
 next_actions:['原话 high five 保留'],
 reference_manifest:{version:1,samples:[{sample_id:'sample_example',title:'服务端作品',case_id:'case_example',open_url:'/cases/case_example'}],entries:[]}
},viewModel:{sections:{repeatable_patterns:[flattened]}}});
console.log(JSON.stringify({html}));
""")
    report = ReportHTML(result["html"])
    core = report.regions(["positioning", "patterns", "actions", "limits"])["patterns"].text(core=True)
    assert "同一背景中的造型变化" in core and "全身和近景分工" in core
    assert "静态图不能确认完整运镜" in core
    assert "服务端作品" in core and "未提供具体片段定位" in core
    assert "sample_example" not in core and "high" not in core
    assert "证据等级：high" not in report.root.text(core=True)
    assert "原话 high five 保留" in report.root.text(core=True)
    assert "证据等级：high" in result["html"]  # Unchanged VM remains in raw details.
    assert 'href="/cases/case_example"' in result["html"]
