"""Synthetic wiring checks only; no real creator data or external model calls."""
from __future__ import annotations

import json

import pytest

from app.config import settings
from app.errors import AppError, ErrorCode
from app.services import creator_clone as creator
from app.services.content_analysis import resolve_analysis_focus
from app.services.creator_intelligence.execution_pack import build_creator_execution_pack_prompt
from app.services.creator_intelligence.generator import generate_creator_strategy_plan
from app.services.creator_intelligence.report_quality import validate_creator_report_quality


@pytest.fixture(autouse=True)
def block_real_services(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Synthetic tests must not use external services")
    monkeypatch.setattr(creator, "get_llm_provider", forbidden)
    monkeypatch.setattr(creator, "scan_profile", forbidden)


def sample_pool(count=3):
    samples = [
        creator.CloneSample("synthetic_visual", title="COS 展示", content_category="beauty_cos", has_frames=True, asr_status="provider_missing"),
        creator.CloneSample("synthetic_tutorial", title="COS 妆容教程", content_category="tutorial"),
        creator.CloneSample("synthetic_knowledge", title="观点论证", content_category="knowledge"),
    ][:count]
    return creator.CloneSampleSet("synthetic_creator", title="Synthetic mixed creator", samples=samples)


def install_provider(monkeypatch, *, fail_first=False):
    calls = []

    class Provider:
        def analyze(self, prompt, image_paths):
            calls.append((prompt, image_paths))
            if fail_first and len(calls) == 1:
                raise AppError(ErrorCode.LLM_RESPONSE_INVALID)
            return {"summary": "Synthetic result, not a real analysis",
                "creator_positioning": {"what_the_creator_sells": "Synthetic structure"},
                "creator_clone_spec": {"taste": "Synthetic evidence"}, "focused_analysis": [
                {"observation": "Synthetic observation", "transfer": "Test a different composition",
                 "evidence": ["synthetic_visual", "not_selected"]}
            ]}

    monkeypatch.setattr(creator, "llm_is_configured", lambda: True)
    monkeypatch.setattr(creator, "get_llm_provider", lambda **kwargs: Provider())
    return calls


def save_case(sample, category="tutorial"):
    sample.case_id = "synthetic_case"
    case_dir = settings.cases_dir / sample.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    focus = resolve_analysis_focus({"title": sample.title}, {}, requested=category)
    (case_dir / "analysis_result.json").write_text(json.dumps({
        "summary": "Synthetic saved case", "analysis_focus": focus,
        "focused_analysis": [{"observation": "synthetic_saved_observation", "evidence": ["frame_001.jpg"]}],
    }), encoding="utf-8")
    (case_dir / "analysis_input.json").write_text(json.dumps({
        "analysis_direction": "beauty_cos", "content_category": "beauty_cos",
    }), encoding="utf-8")
    return focus


@pytest.mark.parametrize("mode", ["quick", "deep"])
@pytest.mark.parametrize("count", [1, 2, 3])
def test_actual_provider_normal_reduce_micro_wiring(monkeypatch, mode, count):
    pool = sample_pool(count)
    calls = install_provider(monkeypatch)
    response = creator.distill_creator_clone(pool, [sample.sample_id for sample in pool.samples], distill_mode=mode)
    assert len(calls) == 1
    prompt, images = calls[0]
    assert images == []
    assert "content_groups" in prompt and "focused_analysis" in prompt
    for sample in pool.samples:
        assert sample.sample_id in prompt
        assert creator.sample_analysis_focus(sample)["primary"] in prompt
    result = response["result"]
    assert result["focused_analysis"][0]["evidence"] == ["synthetic_visual"]
    assert result["focused_analysis"][0]["uncertainty"]
    assert sum(group["count"] for group in result["content_groups"]) == count
    saved = creator.load_creator_clone_result(pool.set_id)
    assert saved["analysis_focus"] == result["analysis_focus"]
    assert saved["focused_analysis"] == result["focused_analysis"]


def test_existing_compact_retry_retains_focus(monkeypatch):
    pool = sample_pool(1)
    calls = install_provider(monkeypatch, fail_first=True)
    creator.distill_creator_clone(pool, [pool.samples[0].sample_id])
    assert len(calls) == 2
    assert all("content_groups" in prompt and "focused_analysis" in prompt for prompt, _ in calls)


def test_lite_map_and_compaction_keep_saved_type_analysis():
    pool = sample_pool(2)
    sample = pool.samples[1]
    saved_focus = save_case(sample)
    pool.content_profile = "knowledge"
    summary = creator.sample_map_summary(sample)
    assert summary["analysis_focus"] == saved_focus
    assert summary["content_category"] == "tutorial"
    assert summary["focused_analysis"][0]["evidence"] == [sample.sample_id]
    for compact in (creator._micro_map_summary(summary), creator._map_summary_for_reduce(summary), creator._lite_sample_prompt_payload(sample)):
        assert compact["focused_analysis"][0]["observation"] == "synthetic_saved_observation"
        assert compact["analysis_focus"]["primary"] == "tutorial"
    lite = creator.build_lite_distill_prompt(pool, pool.samples)
    assert "synthetic_saved_observation" in lite
    assert "tutorial" in lite and "knowledge" in lite
    prompt = creator.build_sample_map_prompt(sample, summary)
    assert saved_focus["questions"][0] in prompt
    normalized = creator._normalize_llm_map_summary({"content_category": "beauty_cos", "focused_analysis": [
        {"observation": "Synthetic map", "evidence": [sample.sample_id, "not_selected"]}
    ]}, summary)
    assert normalized["content_category"] == "tutorial"
    assert normalized["focused_analysis"][0]["evidence"] == [sample.sample_id]


def test_group_counts_and_references_are_program_owned():
    pool = sample_pool()
    save_case(pool.samples[1])
    result = creator.normalize_creator_clone_result({
        "analysis_focus": {"primary": "commerce_seed"},
        "content_groups": [{"category": "tutorial", "count": 900, "sample_ids": ["not_selected"],
            "focused_analysis": [{"observation": "Synthetic group", "evidence": ["synthetic_tutorial", "synthetic_visual"]}]}],
        "creator_clone_strategy": {"hooks": [{"sample_id": "not_selected", "text": "Fabricated"}]},
        "performance_segments": {"highest_like_samples": [{"sample_id": "not_selected"}]},
    }, pool, pool.samples)
    groups = {group["category"]: group for group in result["content_groups"]}
    assert groups["tutorial"]["sample_ids"] == ["synthetic_tutorial"]
    assert groups["tutorial"]["count"] == groups["tutorial"]["analyzed_count"] == 1
    assert groups["tutorial"]["metadata_only_count"] == 0
    assert groups["knowledge"]["analyzed_count"] == 0
    assert groups["knowledge"]["metadata_only_count"] == 1
    assert groups["tutorial"]["focused_analysis"][0]["evidence"] == ["synthetic_tutorial"]
    assert "not_selected" not in json.dumps(result)
    assert result["warnings"]


def test_manual_account_focus_does_not_reclassify_samples():
    pool = sample_pool(2)
    pool.content_profile = "knowledge"
    focus = creator.creator_analysis_focus(pool, pool.samples)
    assert focus["primary"] == "knowledge" and focus["source"] == "user"
    assert creator.sample_analysis_focus(pool.samples[1])["primary"] == "tutorial"
    pool.content_profile = "auto"
    assert creator.creator_analysis_focus(pool, pool.samples)["source"] == "auto"
    assert creator.normalize_content_profile("tutorial") == "tutorial"
    assert creator.normalize_content_profile("teaching") == "tutorial"
    assert creator.normalize_content_profile("knowledge") == "knowledge"


def test_batch_and_final_reduce_calls_keep_type_data(monkeypatch):
    pool = sample_pool()
    save_case(pool.samples[1])
    calls = install_provider(monkeypatch)
    creator.batch_distill_creator_clone(pool, [s.sample_id for s in pool.samples], batch_size=2)
    assert len(calls) == 3  # Two existing batch requests and one final Reduce.
    assert all("content_groups" in prompt for prompt, _ in calls)
    assert "synthetic_saved_observation" in calls[0][0]
    assert "focused_analysis" in calls[-1][0]
    assert '"analyzed_count": 1' in calls[-1][0]


def test_old_and_new_reports_still_feed_strategy_and_execution():
    pool = sample_pool(1)
    pool.content_profile = "tutorial"
    for raw in ({"summary": "Synthetic legacy report"}, {"summary": "Synthetic new report", "focused_analysis": [
        {"observation": "Synthetic observation", "evidence": ["synthetic_visual"]}
    ]}):
        report = creator.normalize_creator_clone_result(raw, pool, pool.samples)
        plan = generate_creator_strategy_plan(report["creator_clone_strategy"], report["creator_report_view_model"],
            report["report_quality"], {}, report.get("evidence_gaps") or [], "tutorial")
        assert plan["source"]["content_profile"] == "tutorial"
        assert len(plan["next_topics"]) >= 5
        prompt = build_creator_execution_pack_prompt(sample_set=pool, report=report, strategy_plan=plan,
            selected_samples=pool.samples, selected_topic=plan["next_topics"][0], topic_index=0)
        assert "synthetic_visual" in prompt


@pytest.mark.parametrize("status", ["provider_missing", "failed", "no_speech", "pending"])
def test_missing_transcription_never_proves_silence(status):
    sample = creator.CloneSample("synthetic", asr_status=status, has_frames=True)
    evidence = creator._sample_evidence_status(sample)
    assert not evidence["can_infer_visual_rhythm"]
    assert "确认无可转写语音" not in json.dumps(evidence, ensure_ascii=False)


def test_llm_map_failure_does_not_drop_other_samples():
    pool = sample_pool(2)
    calls = []

    class Provider:
        def analyze(self, prompt, image_paths):
            calls.append((prompt, image_paths))
            if len(calls) == 1:
                raise AppError(ErrorCode.LLM_AUTH_FAILED)
            return {"one_line_summary": "Synthetic map", "focused_analysis": [
                {"observation": "Synthetic step", "evidence": ["synthetic_tutorial", "not_selected"]}
            ]}

    summaries = creator.build_llm_map_summaries(Provider(), pool.samples)
    assert len(calls) == len(summaries) == 2
    assert summaries[0]["map_error_code"] == ErrorCode.LLM_AUTH_FAILED
    assert summaries[1]["focused_analysis"][0]["evidence"] == ["synthetic_tutorial"]
    assert all(images == [] for _, images in calls)
    assert "步骤" in calls[1][0]


def test_local_batch_fallback_preserves_type_findings():
    pool = sample_pool()
    batch = {"result": {"focused_analysis": [{"observation": "Synthetic cross-type finding", "evidence": ["synthetic_visual"]}],
        "content_groups": [{"category": "tutorial", "focused_analysis": [
            {"observation": "Synthetic steps", "evidence": ["synthetic_tutorial"]}]}]}}
    report = creator.build_local_batch_distill_result(pool, pool.samples, [batch])
    assert report["focused_analysis"][0]["observation"] == "Synthetic cross-type finding"
    group = next(group for group in report["content_groups"] if group["category"] == "tutorial")
    assert group["focused_analysis"][0]["observation"] == "Synthetic steps"


def test_failed_reanalysis_preserves_previous_report(monkeypatch):
    pool = sample_pool(1)
    install_provider(monkeypatch)
    creator.distill_creator_clone(pool, ["synthetic_visual"])
    path = settings.creator_clones_dir / pool.set_id / "creator_clone_result.json"
    previous = path.read_bytes()

    class Failure:
        def analyze(self, *args):
            raise AppError(ErrorCode.LLM_AUTH_FAILED)

    monkeypatch.setattr(creator, "get_llm_provider", lambda **kwargs: Failure())
    with pytest.raises(AppError):
        creator.distill_creator_clone(pool, ["synthetic_visual"])
    assert path.read_bytes() == previous


def test_quality_does_not_require_spoken_script_for_visual_content():
    evidence = {"selected_count": 3, "evidence_ready_count": 3, "with_keyframes": 3, "with_asr": 0, "with_ocr": 0}
    quality = validate_creator_report_quality({}, evidence_summary=evidence,
        report_context={"analysis_focus": {"primary": "beauty_cos"}}).to_dict()
    assert not any("ASR/OCR" in warning for warning in quality["evidence_warnings"])
    assert quality["missing_fields"]


@pytest.mark.parametrize(("title", "category"), [
    ("COS 妆容教程第一步第二步", "tutorial"),
    ("摄影出片教程与成片证明", "photo_beauty"),
    ("核心观点与论证举例", "knowledge"),
    ("COS 角色反转与伏笔揭示", "plot_twist"),
])
def test_sample_expression_form_takes_priority_over_topic(title, category):
    focus = creator.sample_analysis_focus(creator.CloneSample("synthetic", title=title))
    assert focus["primary"] == category
    assert focus["source"] == "auto"


@pytest.mark.parametrize("report", [{}, {"path": "synthetic_report.json"}, {"summary": ""}])
def test_group_counts_ignore_empty_reports_and_unsubstantiated_partial_flags(report):
    sample = creator.CloneSample("synthetic_partial", understanding_level="partial", case_id="synthetic_partial_case")
    case_dir = settings.cases_dir / sample.case_id
    case_dir.mkdir(parents=True)
    (case_dir / "analysis_result.json").write_text(json.dumps(report), encoding="utf-8")
    group = creator.creator_content_groups([sample])[0]
    assert group["analyzed_count"] == 0
    assert group["metadata_only_count"] == group["missing_analysis_count"] == 1
    (case_dir / "analysis_result.json").write_text(json.dumps({"summary": "Synthetic valid summary"}), encoding="utf-8")
    assert creator.creator_content_groups([sample])[0]["analyzed_count"] == 1


@pytest.mark.parametrize("groups", [None, [None], [{"category": "unknown", "focused_analysis": None}]])
def test_review_is_safe_optional_and_cannot_override_focus(groups):
    pool = sample_pool(1)
    pool.content_profile = "tutorial"
    result = creator.normalize_creator_clone_result({
        "analysis_focus": {"primary": "beauty_cos"},
        "category_review": {"suggested_category": "knowledge", "reason": "https://example.test/private /Users/test/private", "extra": "discard"},
        "focused_analysis": [{"observation": "Synthetic observation", "evidence": ["not_selected"]}],
        "content_groups": groups,
    }, pool, pool.samples)
    assert result["analysis_focus"]["primary"] == "tutorial"
    assert result["analysis_focus"]["source"] == "user"
    assert result["category_review"]["suggested_category"] == "knowledge"
    assert "extra" not in result["category_review"]
    assert "https://" not in result["category_review"]["reason"]
    assert "/Users/" not in result["category_review"]["reason"]
    assert result["focused_analysis"][0]["evidence"] == []
    assert any("引用" in warning for warning in result["warnings"])


@pytest.mark.parametrize("path", ["compact", "lite"])
def test_legacy_case_summary_and_steps_reach_compact_provider(monkeypatch, path):
    pool = sample_pool(1)
    sample = pool.samples[0]
    sample.case_id = "synthetic_legacy_case"
    case_dir = settings.cases_dir / sample.case_id
    case_dir.mkdir(parents=True)
    (case_dir / "analysis_result.json").write_text(json.dumps({
        "summary": "SYNTHETIC_LEGACY_SUMMARY",
        "speech_analysis": {"script_structure": "SYNTHETIC_LEGACY_STEP_ONE_THEN_TWO"},
        "replication": {"copyable_points": ["SYNTHETIC_LEGACY_KEEP_STEP"]},
    }), encoding="utf-8")
    calls = install_provider(monkeypatch)
    if path == "compact":
        creator.distill_creator_clone(pool, [sample.sample_id], include_case_reports=False)
        payload = creator.sample_to_prompt_payload(sample, include_case_reports=False)
    else:
        prompt = creator.build_lite_distill_prompt(pool, pool.samples)
        creator.ExecutionLayer().analyze_json(creator.get_llm_provider(), prompt, [])
        payload = creator._lite_sample_prompt_payload(sample)
    assert len(calls) == 1
    prompt, images = calls[0]
    assert images == []
    assert "SYNTHETIC_LEGACY_SUMMARY" in prompt
    assert "SYNTHETIC_LEGACY_STEP_ONE_THEN_TWO" in prompt
    assert "SYNTHETIC_LEGACY_KEEP_STEP" in prompt
    assert "case_analysis_result" not in prompt
    assert payload["map_source"] == "analysis_result"
    assert payload["focused_analysis"] == []
    assert payload["legacy_analysis_summary"]["summary"] == "SYNTHETIC_LEGACY_SUMMARY"


def test_compact_legacy_summary_is_bounded_and_source_matches_payload():
    summary = {"map_source": "analysis_result", "one_line_summary": "X" * 2000,
        "speech": {"script_structure": "Y" * 2000}, "copyable_points": ["Z" * 1000] * 10}
    payload = creator._compact_sample_analysis_payload(summary)
    assert len(payload["legacy_analysis_summary"]["summary"]) <= 180
    assert len(payload["legacy_analysis_summary"]["script_structure"]) <= 180
    assert len(payload["legacy_analysis_summary"]["copyable_points"]) <= 2
    assert creator._compact_sample_analysis_payload({"map_source": "case_evidence"})["map_source"] == "metadata"
    assert creator._compact_sample_analysis_payload({"map_source": "analysis_result"})["map_source"] == "metadata"


def test_new_model_report_sanitizes_sensitive_leaves_and_keys_without_changing_refs():
    pool = sample_pool(1)
    sample = pool.samples[0]
    raw = {
        "summary": "Synthetic sk-syntheticsecret123 /Users/synthetic/private.txt https://example.test/video?signature=synthetic_signature",
        "creator_positioning": {"what_the_creator_sells": "Keep this legitimate description",
            "Cookie": "synthetic_cookie_value", "api_key": "synthetic_api_value"},
        "creator_clone_strategy": {"hooks": [{"sample_id": sample.sample_id,
            "text": "Synthetic bearer synthetic_bearer_secret", "authorization": "synthetic_auth_value"}]},
        "focused_analysis": [{"observation": "Synthetic safe observation", "evidence": [sample.sample_id]}],
        "nested": [{"apiKey": "synthetic_camel_key", "client_secret": "synthetic_client_secret",
            "safe": "Keep this nested description", "sample_ids": [sample.sample_id]}],
    }
    result = creator.normalize_creator_clone_result(raw, pool, pool.samples)
    creator._write_json(settings.creator_clones_dir / "synthetic_sanitized.json", result)
    serialized = (settings.creator_clones_dir / "synthetic_sanitized.json").read_text(encoding="utf-8")
    for secret in ("sk-syntheticsecret123", "/Users/synthetic/private.txt", "synthetic_signature",
                   "synthetic_cookie_value", "synthetic_api_value", "synthetic_bearer_secret",
                   "synthetic_auth_value", "synthetic_camel_key", "synthetic_client_secret"):
        assert secret not in serialized
    assert result["creator_positioning"]["what_the_creator_sells"] == "Keep this legitimate description"
    assert result["nested"] == [{"safe": "Keep this nested description", "sample_ids": [sample.sample_id]}]
    assert result["focused_analysis"][0]["evidence"] == [sample.sample_id]
    sanitized = creator._validated_creator_refs(raw, pool.samples, [])
    assert sanitized["creator_clone_strategy"]["hooks"][0]["sample_id"] == sample.sample_id
    assert "synthetic_cookie_value" in json.dumps(raw)  # No mutation of source data.
