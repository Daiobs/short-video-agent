import copy
import json
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import creator_clone as creator
from app.services.creator_report_details import LIMIT_NOTE, MAX_DETAIL_BYTES, detail_markdown, report_detail_items


def render(result):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    return subprocess.run([node, "tests/creator_report_details_runner.cjs"], input=json.dumps(result),
                          capture_output=True, text=True, check=True).stdout


def full_result():
    return {
        "summary": "合成测试：核心摘要保持不变。", "creator_positioning": {"what_the_creator_sells": "合成定位"},
        "next_actions": ["合成测试的已有执行建议"],
        "transferable_formulas": [{"name": "合成完整方法", "when_to_use": "限定条件",
            "beat_structure": ["详细步骤。" * 400, "FORMULA_STEP_END"], "risks": ["RISK_END"],
            "metric": "share_count", "metric_value": 0, "sample_id": "sample_test",
            "extension": {"detail": "EXTENSION_END"}}],
        "candidate_ideas": [{"title": "合成选题", "production_requirements": ["制作内容。" * 200, "IDEA_END"],
            "formula_used": "合成完整方法", "low_confidence": True}, "仅名称选题"],
        "creator_clone_strategy": {"positioning": "合成定位", "templates": [{"text": "简写名称"}], "idea_bank": [{"text": "简写选题"}]},
    }


def test_formal_save_reload_mount_and_exports_preserve_details(monkeypatch):
    raw = full_result()
    sample_set = creator.CloneSampleSet(set_id="clone_details_test", title="合成数据",
        samples=[creator.CloneSample(sample_id="sample_test", title="测试素材")])
    monkeypatch.setattr(creator, "llm_is_configured", lambda: True)

    class Provider:
        def analyze(self, *args, **kwargs):
            return copy.deepcopy(raw)

    monkeypatch.setattr(creator, "get_llm_provider", lambda **kwargs: Provider())
    payload = creator.distill_creator_clone(sample_set, ["sample_test"])
    saved = payload["result"]
    with TestClient(app) as client:
        response = client.get("/api/creator-clone/sets/clone_details_test")
    assert response.status_code == 200
    loaded = response.json()["result"]
    assert loaded["transferable_formulas"] == raw["transferable_formulas"]
    assert loaded["candidate_ideas"] == raw["candidate_ideas"]
    assert loaded["summary"] == raw["summary"]
    markup = render(loaded)
    markdown = creator.render_creator_clone_markdown(loaded)
    exported = creator.render_creator_clone_html_report(markdown)
    for sentinel in ("FORMULA_STEP_END", "RISK_END", "IDEA_END", "EXTENSION_END", "sample_test"):
        assert sentinel in markup and sentinel in markdown and sentinel in exported
    assert "没有返回独立公式" not in markup
    assert "[object Object]" not in markup and "True" not in markup
    assert "<dt>低置信标记</dt><dd><span>是</span>" in markup
    assert "<details class=\"creator-content-detail\"><summary>合成完整方法</summary>" in markup
    assert "open" not in markup.split('class="creator-content-detail"', 1)[1].split(">", 1)[0]
    for _ in range(2):
        again = creator.normalize_creator_clone_result(loaded, sample_set, sample_set.samples)
        assert again["transferable_formulas"] == raw["transferable_formulas"]
        assert again["candidate_ideas"] == raw["candidate_ideas"]
        loaded = again
    assert saved["creator_clone_strategy"] == loaded["creator_clone_strategy"]


@pytest.mark.parametrize("value", ["仅名称", {"name": "仅名称"}, [{"text": "仅名称"}], []])
def test_history_and_same_report_fallback(value):
    result = {"transferable_formulas": value, "creator_clone_strategy": {"templates": [{"text": "同报告旧名称"}]}}
    markup = render(result)
    assert "UNRELATED_REPORT" not in markup
    assert "没有返回独立公式" not in markup
    expected = "仅名称" if value else "同报告旧名称"
    assert expected in markup and expected in detail_markdown(result, "transferable_formulas")
    assert "<summary>" + expected not in markup  # No invented details for names.


def test_empty_saved_summary_and_no_cross_report_details():
    result = {"transferable_formulas": {}, "candidate_ideas": [], "creator_report_view_model": {"sections": {"formulas": ["历史截断摘要…"]}}}
    markup = render(result)
    assert "历史截断摘要…" in markup and "完整原文未记录" in markup
    assert "当前保存记录未提供完整内容" in markup
    assert "UNRELATED_REPORT" not in markup and "UNRELATED_IDEA" not in markup


def test_detail_safety_and_limits():
    result = full_result()
    result["transferable_formulas"][0]["extension"] = {"<script>bad()</script>": '<img src=x onerror="bad()">'}
    markup = render(result)
    exported = creator.render_creator_clone_html_report(creator.render_creator_clone_markdown(result))
    assert "<img src=x" not in markup + exported
    assert "&lt;img" in markup and "&lt;img" in exported
    result["transferable_formulas"] = [{"name": "大内容", "beat_structure": "x" * MAX_DETAIL_BYTES}]
    assert report_detail_items(result, "transferable_formulas")["notice"] == LIMIT_NOTE
    assert LIMIT_NOTE in render(result)
    result["transferable_formulas"] = [{"nested": {"n": {"n": {"n": {"n": {"n": {"n": {"n": {"n": "deep"}}}}}}}}}]
    assert report_detail_items(result, "transferable_formulas")["notice"] == LIMIT_NOTE
