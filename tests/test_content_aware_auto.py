"""Synthetic inputs only: provider wiring, not real model quality validation."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.errors import AppError, ErrorCode
from app.models import CaseArtifact
from app.services import auto_analyzer as auto


class RecordingProvider:
    def __init__(self, failures=0, result=None):
        self.failures = failures
        self.calls = []
        self.result = result

    def analyze(self, prompt, image_paths):
        self.calls.append((prompt, list(image_paths)))
        if len(self.calls) <= self.failures:
            raise AppError(ErrorCode.LLM_GATEWAY_TIMEOUT, "synthetic timeout")
        if self.result is not None:
            return deepcopy(self.result)
        return {
            "summary": "合成示例：先说明具体问题，再按操作顺序解释结果，便于复用表达结构。",
            "content_category": "beauty_cos",
            "category_review": {"suggested_category": "beauty_cos", "reason": "合成复核建议"},
            "focused_analysis": [{
                "question": "哪些表达结构可迁移？",
                "observation": "标题承诺展示操作结果。",
                "interpretation": "结果承诺提供理解后续步骤的线索。",
                "transfer": "先列结果，再逐项演示必要步骤。",
                "evidence": ["metadata", "frame_missing.jpg"],
                "uncertainty": "仅为合成测试，不是模型质量证据。",
            }],
            "speech_analysis": {"has_speech": False},
        }


@pytest.fixture
def case(tmp_path, monkeypatch):
    frames = tmp_path / "keyframes"
    frames.mkdir()
    (frames / "frame_001.jpg").write_bytes(b"synthetic")
    (tmp_path / "contact_sheet.jpg").write_bytes(b"synthetic")
    (tmp_path / "metadata.json").write_text('{}')
    (tmp_path / "ffprobe.json").write_text('{"duration": 10}')
    artifact = CaseArtifact(
        case_id="synthetic-content-aware", prompt_path=str(tmp_path / "prompt.md"),
        metadata_path=str(tmp_path / "metadata.json"), ffprobe_path=str(tmp_path / "ffprobe.json"),
        analysis_input_path=str(tmp_path / "analysis_input.json"),
        contact_sheet_path=str(tmp_path / "contact_sheet.jpg"), keyframes_dir=str(frames),
    )
    data = {"title": "合成COS妆容教程", "analysis_direction": "auto",
            "analysis_focus": ["legacy base focus"], "video": {"duration": 10},
            "analysis_enrichment": {"asr": {"status": "not_configured"}}}
    monkeypatch.setattr(auto, "refresh_analysis_input_enrichment", lambda _: deepcopy(data))
    monkeypatch.setattr(auto, "_manual_review_payload", lambda *args: {})
    monkeypatch.setattr(auto, "get_llm_provider", lambda: pytest.fail("Real provider forbidden"))
    return artifact, data


@pytest.mark.parametrize("mode,failures,images", [
    ("deep", 0, [2]), ("deep", 1, [2, 1]), ("deep", 2, [2, 1, 0]),
    ("fast", 0, [1]), ("fast", 1, [1, 0]),
])
def test_actual_provider_paths(case, mode, failures, images):
    artifact, data = case
    provider = RecordingProvider(failures)
    saved = auto.analyze_case_artifact(artifact, provider, mode=mode)["analysis_result"]
    assert [len(paths) for _, paths in provider.calls] == images
    for prompt, paths in provider.calls:
        assert "具体问题与结果承诺" in prompt
        manifest = json.loads(prompt.split("本次输入证据：", 1)[1].splitlines()[0])
        assert manifest["images"] == [path.name for path in paths]
        assert manifest["visual_available"] == bool(paths)
        assert str(Path(artifact.prompt_path).parent) not in prompt
        assert '"percent"' not in prompt
    assert saved["analysis_focus"]["primary"] == "tutorial"
    assert saved["analysis_focus"]["source"] == "auto"
    assert saved["category_review"]["suggested_category"] == "beauty_cos"
    assert saved["focused_analysis"][0]["evidence"] == ["metadata"]
    assert "无法定位" in saved["focused_analysis"][0]["uncertainty"]
    assert saved["speech_analysis"]["has_speech"] is None
    assert saved["content_ratio"] == []
    assert saved["request_evidence"]["images"] == [p.name for p in provider.calls[-1][1]]
    if images[-1] == 0:
        assert saved["evidence_summary"]["visual_evidence"] == []
    data["analysis_direction"] = "knowledge"
    loaded, report = auto.existing_auto_analysis(artifact)
    assert loaded == saved
    assert "本次分析重点" in report


@pytest.mark.parametrize("title,category,needle", [
    ("COS造型展示", "beauty_cos", "妆造"),
    ("COS妆容教程", "tutorial", "步骤"),
    ("摄影出片教程", "photo_beauty", "成片承诺"),
    ("知识观点举例", "knowledge", "论据"),
    ("情绪文案", "motivational", "措辞"),
    ("角色反转剧情", "plot_twist", "信息差"),
])
def test_type_questions_reach_provider(case, title, category, needle):
    artifact, data = case
    data.update(title=title, analysis_direction=category)
    provider = RecordingProvider()
    saved = auto.analyze_case_artifact(artifact, provider)["analysis_result"]
    assert saved["analysis_focus"]["primary"] == category
    assert saved["analysis_focus"]["source"] == "user"
    assert needle in provider.calls[0][0]
    assert len(provider.calls) == 1


def test_fast_manifest_uses_truncated_payload(case, monkeypatch):
    artifact, data = case
    data["analysis_enrichment"] = {
        "asr": {"status": "success", "full_text": "a" * 800 + "OMITTED_ASR",
                "segments": [{"text": "OMITTED_SEGMENT", "start": 8}]},
        "ocr": {"status": "success", "frame_text": "b" * 300 + "OMITTED_OCR"},
    }
    observed = []
    original = auto.request_evidence
    def capture(payload, paths):
        observed.append(deepcopy(payload))
        return original(payload, paths)
    monkeypatch.setattr(auto, "request_evidence", capture)
    provider = RecordingProvider()
    saved = auto.analyze_case_artifact(artifact, provider, mode="fast")["analysis_result"]
    prompt = provider.calls[0][0]
    assert "OMITTED_" not in prompt
    submitted = observed[-1]["analysis_enrichment"]
    assert "segments" not in submitted["asr"]
    assert len(submitted["asr"]["full_text"]) == 603
    assert len(submitted["ocr"]["frame_text"]) == 203
    assert saved["request_evidence"]["asr"]["submitted"] is True


@pytest.mark.parametrize("status", ["failed", "success", "no_speech", "not_configured"])
def test_empty_asr_never_means_no_speech(case, status):
    artifact, data = case
    data["analysis_enrichment"]["asr"]["status"] = status
    result = auto.analyze_case_artifact(artifact, RecordingProvider())["analysis_result"]
    assert result["speech_analysis"]["has_speech"] is None
    assert result["request_evidence"]["asr"]["submitted"] is False


@pytest.mark.parametrize("failure", ["timeout", "empty"])
def test_failed_reanalysis_preserves_report(case, failure):
    artifact, _ = case
    directory = Path(artifact.prompt_path).parent
    (directory / "analysis_result.json").write_text('{"summary":"old"}')
    (directory / "analysis_report.md").write_text("old report")
    provider = RecordingProvider(10) if failure == "timeout" else RecordingProvider(result={})
    with pytest.raises(AppError):
        auto.analyze_case_artifact(artifact, provider)
    assert (directory / "analysis_result.json").read_text() == '{"summary":"old"}'
    assert (directory / "analysis_report.md").read_text() == "old report"


def test_versioned_quality_keeps_safety_and_nonempty_checks(case):
    artifact, _ = case
    result = auto.analyze_case_artifact(artifact, RecordingProvider())["analysis_result"]
    checks = {item["id"]: item for item in result["quality_review"]["checks"]}
    assert "content_ratio_balance" not in checks
    assert checks["category_alignment"]["passed"]
    assert checks["visual"]["passed"]
    assert checks["visual"]["weight"] == 0
    assert "time_bounds" in checks and "adaptation_boundary" in checks
    result["focused_analysis"] = []
    result["summary"] = ""
    failed = {item["id"]: item for item in auto._analysis_quality_review(result)["checks"]}
    assert not failed["summary"]["passed"]
    assert not failed["category_alignment"]["passed"]
    result.pop("analysis_focus")
    legacy = {item["id"]: item for item in auto._analysis_quality_review(result)["checks"]}
    assert "content_ratio_balance" in legacy


def test_prompts_redact_sensitive_metadata(case):
    artifact, data = case
    data["notes"] = "https://media.test/video?signature=secret /Users/private/video.mp4"
    data["api_key"] = "test-sensitive-value"
    provider = RecordingProvider()
    auto.analyze_case_artifact(artifact, provider)
    assert "signature=secret" not in provider.calls[0][0]
    assert "/Users/private" not in provider.calls[0][0]
    assert "test-sensitive-value" not in provider.calls[0][0]


def test_single_frame_fallback_and_manual_review(case, monkeypatch):
    artifact, data = case
    Path(artifact.contact_sheet_path).unlink()
    data["analysis_direction"] = "knowledge"
    monkeypatch.setattr(auto, "_manual_review_payload", lambda *args: {
        "summary": "合成复核：补充论据与例子", "quality_acceptance": {"verdict": "needs_fix"},
    })
    provider = RecordingProvider(1)
    saved = auto.analyze_case_artifact(artifact, provider)["analysis_result"]
    assert [len(paths) for _, paths in provider.calls] == [1, 0]
    assert saved["analysis_focus"]["primary"] == "knowledge"
    for prompt, paths in provider.calls:
        assert "合成复核：补充论据与例子" in prompt
        assert "论据" in prompt
        manifest = json.loads(prompt.split("本次输入证据：", 1)[1].splitlines()[0])
        assert manifest["images"] == [path.name for path in paths]


def test_legacy_direction_and_return_to_auto(case):
    artifact, data = case
    data.pop("analysis_direction")
    data["content_category"] = "beauty_cos"
    saved = auto.analyze_case_artifact(artifact, RecordingProvider())["analysis_result"]
    assert saved["analysis_focus"]["source"] == "legacy"
    data["analysis_direction"] = "auto"
    saved = auto.analyze_case_artifact(artifact, RecordingProvider())["analysis_result"]
    assert saved["analysis_focus"]["source"] == "auto"
    assert saved["analysis_focus"]["primary"] == "tutorial"


def test_new_model_string_evidence_shape_is_tolerated(case):
    artifact, _ = case
    result = RecordingProvider().analyze("", [])
    result["evidence_summary"] = "synthetic nonstandard model shape"
    saved = auto.analyze_case_artifact(artifact, RecordingProvider(result=result))["analysis_result"]
    assert saved["request_evidence"]["visual_available"]
    assert isinstance(saved["evidence_summary"], dict)


@pytest.mark.parametrize("stats,expected", [
    ({"like_count": 0, "comment_count": 0, "share_count": 0}, "ok"),
    ({"like_count": 0, "comment_count": None, "share_count": 0}, "partial"),
    ({"like_count": None}, "missing"), ({}, "missing"),
])
@pytest.mark.parametrize("mode,failures", [("deep", 0), ("fast", 1), ("deep", 2)])
def test_metric_zero_and_missing_contract(case, stats, expected, mode, failures):
    artifact, data = case
    data["stats"] = stats
    provider = RecordingProvider(failures)
    saved = auto.analyze_case_artifact(artifact, provider, mode=mode)["analysis_result"]
    assert saved["engagement_data_quality"] == expected
    for prompt, _ in provider.calls:
        assert "为 0 或缺失" not in prompt
    if "like_count" in stats:
        assert f'"like_count": {json.dumps(stats["like_count"])}' in provider.calls[-1][0]
    elif mode == "fast" or failures:
        assert '"like_count": null' in provider.calls[-1][0]


def test_one_focused_row_does_not_pass_independent_modules(case):
    artifact, data = case
    data["analysis_direction"] = "beauty_cos"
    saved = auto.analyze_case_artifact(artifact, RecordingProvider())["analysis_result"]
    checks = {item["id"]: item for item in saved["quality_review"]["checks"]}
    assert checks["category_alignment"]["passed"]
    for key in ("hook", "visual", "replication", "model_confidence"):
        assert not checks[key]["passed"], key
    assert checks["copy_speech_text"]["weight"] == 0
    assert checks["audience"]["weight"] == 0
    assert saved["quality_review"]["score"] < 50


@pytest.mark.parametrize("confidence,valid", [(0, True), (0.2, True), (1, True),
    (-0.1, False), (1.1, False), (None, False), (True, False), ("nan", False), ("inf", False)])
def test_confidence_validation_precedes_normalization(case, confidence, valid):
    artifact, _ = case
    raw = RecordingProvider().analyze("", [])
    raw["confidence"] = confidence
    saved = auto.analyze_case_artifact(artifact, RecordingProvider(result=raw))["analysis_result"]
    check = next(item for item in saved["quality_review"]["checks"] if item["id"] == "model_confidence")
    assert check["passed"] is valid


def test_unsubmitted_visual_and_speech_claims_still_diagnosed(case):
    artifact, _ = case
    raw = RecordingProvider().analyze("", [])
    raw.update(visual_analysis={"subject": "人物穿着红色衣服", "composition": "人物位于画面正中"},
               speech_analysis={"has_speech": True, "opening_line": "原片口播第一句"})
    saved = auto.analyze_case_artifact(artifact, RecordingProvider(2, raw))["analysis_result"]
    check = next(item for item in saved["quality_review"]["checks"] if item["id"] == "submitted_claim_support")
    assert not check["passed"]
    assert any("visual_analysis" in detail for detail in check["details"])
    assert any("speech_analysis" in detail for detail in check["details"])


@pytest.mark.parametrize("model_source", [False, True])
def test_saved_new_reports_redact_model_and_metadata(case, model_source):
    artifact, _ = case
    metadata = {
        "title": "合成标题 sk-SYNTHETIC_KEY_123456",
        "author": "Cookie: SYNTHETIC_COOKIE_123456",
        "source_url": "https://cdn.example.test/video.mp4?signature=SYNTHETIC_SIGNATURE",
    }
    Path(artifact.metadata_path).write_text(json.dumps(metadata), encoding="utf-8")
    raw = RecordingProvider().analyze("", [])
    raw.update({
        "summary": "合成结果 /Users/private/SYNTHETIC_LOCAL_FILE.mp4 sk-SYNTHETIC_MODEL_KEY_123456",
        "visual_analysis": {"subject": "Authorization: Bearer SYNTHETIC_AUTH_TOKEN"},
        "replication": {"copyable_points": ["https://cdn.test/a?token=SYNTHETIC_MEDIA_TOKEN"]},
        "publish_package": {"caption": "api_key=SYNTHETIC_CAPTION_KEY", "password": "SYNTHETIC_PASSWORD"},
        "api_key": "SYNTHETIC_NESTED_KEY",
        "extra": [{"Cookie": "SYNTHETIC_NESTED_COOKIE", "notes": "Bearer SYNTHETIC_BEARER_TOKEN"}],
    })
    if model_source:
        raw["source"] = {"title": "api_key=SYNTHETIC_SOURCE_KEY",
                         "source_url": "https://cdn.test/v?signature=SYNTHETIC_MODEL_SIGNATURE",
                         "credentials": "SYNTHETIC_CREDENTIALS"}
    response = auto.analyze_case_artifact(artifact, RecordingProvider(result=raw))
    disk_json = Path(response["analysis_result_path"]).read_text()
    disk_markdown = Path(response["analysis_report_path"]).read_text()
    for text in (disk_json, disk_markdown, json.dumps(response, ensure_ascii=False)):
        assert "SYNTHETIC_" not in text
        assert "/Users/private" not in text
        assert "https://cdn" not in text
    assert json.loads(disk_json) == response["analysis_result"]
    assert disk_markdown == response["analysis_report"]
    assert json.loads(Path(artifact.metadata_path).read_text()) == metadata
    assert Path(artifact.contact_sheet_path).read_bytes() == b"synthetic"


def test_new_report_url_redaction_does_not_rewrite_source_metadata(case):
    artifact, _ = case
    url = "https://www.douyin.com/video/1234567890"
    Path(artifact.metadata_path).write_text(json.dumps({"source_url": url}))
    saved = auto.analyze_case_artifact(artifact, RecordingProvider())["analysis_result"]
    assert saved["source"]["source_url"] == "[链接已省略]"
    assert json.loads(Path(artifact.metadata_path).read_text())["source_url"] == url
