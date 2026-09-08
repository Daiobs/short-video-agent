"""PR29 comment evidence: isolated synthetic inputs, no external calls."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.services import auto_analyzer as auto
from app.services.content_analysis import request_evidence
from tests.test_content_aware_auto import RecordingProvider, case


@pytest.mark.parametrize("mode,failures", [("deep", 0), ("deep", 1), ("deep", 2), ("fast", 0), ("fast", 1)])
def test_submitted_comments_survive_actual_paths_and_reload(case, mode, failures):
    artifact, data = case
    data["analysis_enrichment"]["comments"] = {
        "status": "success", "total_comments": 2,
        "top_comments": [{"text": "合成评论：希望展示机位。", "likes": 0}],
        "top_needs": ["查看拍摄步骤"],
    }
    provider = RecordingProvider(failures, result={
        "summary": "合成评论反映提问，不证明转化。",
        "comment_insights": {"audience_needs": ["想知道机位"], "comment_triggers": ["提问拍摄方法"]},
        "evidence_summary": {"comment_evidence": [{"claim": "评论提问", "evidence": "合成评论：希望展示机位。"}]},
        "focused_analysis": [{"observation": "部分评论询问机位。", "transfer": "补充机位示意。",
                              "evidence": ["comments", "not_submitted", "frame_001.jpg"]}],
    })
    saved = auto.analyze_case_artifact(artifact, provider, mode=mode)["analysis_result"]
    assert len(provider.calls) == failures + 1
    for prompt, images in provider.calls:
        manifest = json.loads(prompt.split("本次输入证据：", 1)[1].splitlines()[0])
        assert manifest["comments"]["submitted"] is True
        assert manifest["comments"]["source"] == ("comment_summary" if mode == "fast" else "analysis_enrichment.comments")
        assert "评论引用 ID 为 comments" in prompt
        assert "合成评论：希望展示机位。" in prompt
        assert manifest["images"] == [p.name for p in images]
    row = saved["focused_analysis"][0]
    assert saved["evidence_summary"]["comment_evidence"]
    assert saved["enrichment_usage"]["comments_used"]
    assert saved["enrichment_coverage"]["items"]["comments"]["verdict"] == "used"
    assert "comments" in row["evidence"]
    assert "not_submitted" not in row["evidence"]
    assert "无法定位" in row["uncertainty"]
    if not provider.calls[-1][1]:
        assert row["evidence"] == ["comments"]
    loaded, _ = auto.existing_auto_analysis(artifact)
    assert loaded["focused_analysis"] == saved["focused_analysis"]
    assert loaded["request_evidence"] == saved["request_evidence"]


@pytest.mark.parametrize("comments", [None, {}, "", "  ", "{}", '"{}"', "[]", "null",
    {"status": "success", "total_comments": 42}, {"top_comments": [{"text": " "}]},
    {"top_comments": [], "top_needs": ["{}"]}, {"notes": "人工备注不是评论"}])
@pytest.mark.parametrize("fast", [False, True])
def test_empty_or_status_only_comments_do_not_register(comments, fast):
    data = {"analysis_enrichment": {"comments": comments}}
    payload = auto._fast_prompt_payload({}, {}, data, {}) if fast else data
    manifest = request_evidence(payload, [])
    assert not manifest["comments"]["submitted"]
    assert "comments" not in manifest["valid_refs"]


def test_fast_manifest_only_uses_cleaned_truncated_content(case, monkeypatch):
    artifact, data = case
    data["analysis_enrichment"]["comments"] = {
        "top_comments": [{"text": "合成有效评论" * 150 + "NOT_SUBMITTED_TAIL"}],
    }
    received = []
    original = auto.request_evidence
    def capture(payload, images):
        received.append(deepcopy(payload))
        return original(payload, images)
    monkeypatch.setattr(auto, "request_evidence", capture)
    provider = RecordingProvider()
    auto.analyze_case_artifact(artifact, provider, mode="fast")
    assert len(received[-1]["comment_summary"]) == 603
    assert "comments" not in received[-1]["analysis_enrichment"]
    assert "NOT_SUBMITTED_TAIL" not in provider.calls[-1][0]
    # Existing source data cannot backfill an empty final fast payload.
    payload = {"analysis_enrichment": data["analysis_enrichment"], "comment_summary": ""}
    assert not request_evidence(payload, [])["comments"]["submitted"]


def test_unsubmitted_comment_reference_rejected_without_regressing_other_sources(case):
    artifact, data = case
    data["analysis_enrichment"].update(asr={"full_text": "合成转录"}, ocr={"frame_text": "合成文字"})
    manifest = request_evidence(data, [Path("frame_001.jpg")])
    assert manifest["valid_refs"] == ["frame_001.jpg", "asr", "ocr", "metadata"]
    provider = RecordingProvider(result={"summary": "合成结论", "focused_analysis": [
        {"observation": "待核实", "evidence": ["comments", "metadata"]}]})
    saved = auto.analyze_case_artifact(artifact, provider)["analysis_result"]
    assert saved["focused_analysis"][0]["evidence"] == ["metadata"]
    assert "无法定位" in saved["focused_analysis"][0]["uncertainty"]


@pytest.mark.parametrize("mode", ["deep", "fast"])
@pytest.mark.parametrize("comments", ["{}", '"{}"', "  ", {"status": "success", "total_comments": 5},
    {"summary": "[捂脸] 希望展示机位", "total_comments": 1}])
def test_comment_shapes_through_normalization(case, mode, comments):
    artifact, data = case
    data["analysis_enrichment"]["comments"] = comments
    valid = isinstance(comments, dict) and "summary" in comments
    provider = RecordingProvider(result={"summary": "合成摘要",
        "comment_insights": {"audience_needs": ["希望看到机位"]} if valid else {},
        "focused_analysis": [{"observation": "合成观察", "evidence": ["comments"]}]})
    saved = auto.analyze_case_artifact(artifact, provider, mode=mode)["analysis_result"]
    assert saved["request_evidence"]["comments"]["submitted"] is valid
    assert saved["focused_analysis"][0]["evidence"] == (["comments"] if valid else [])
    if valid:
        assert "[捂脸] 希望展示机位" in provider.calls[0][0]
        assert saved["enrichment_coverage"]["items"]["comments"]["verdict"] == "used"
