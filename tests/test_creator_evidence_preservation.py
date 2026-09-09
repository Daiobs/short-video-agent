"""Synthetic backend evidence tests; every provider invocation is a mock."""
from __future__ import annotations

import json

import pytest

from app.config import settings
from app.services import creator_clone as creator
from tests.test_content_aware_creator import install_provider


def evidence_pool(count=3, *, long=False):
    samples = []
    for index in range(count):
        sample = creator.CloneSample(
            f"evidence_{index:03}", title=f"Synthetic steps {index}",
            case_id=f"synthetic_evidence_{index:03}", content_category="tutorial",
            like_count=index, has_asr=True, has_ocr=True, has_comments=True,
            analysis_status="success", understanding_level="partial",
        )
        directory = settings.cases_dir / sample.case_id
        directory.mkdir(parents=True, exist_ok=True)
        tail = (' descriptive step "quoted" \\ next step\n' * 400) if long else ""
        (directory / "analysis_input.json").write_text(json.dumps({
            "analysis_direction": "tutorial", "analysis_enrichment": {
                "asr": {"status": "success", "full_text": f"ASR_{index:03} first demonstrate the tool.{tail}"},
                "ocr": {"status": "success", "frame_text": f"OCR_{index:03} Step two: turn clockwise.{tail}"},
                "comments": {"status": "success", "total_comments": 1,
                             "top_comments": [{"text": f"COMMENT_{index:03} Which tool size works?{tail}", "likes": 0}]},
            },
        }), encoding="utf-8")
        (directory / "analysis_result.json").write_text(json.dumps({
            "summary": f"ANALYSIS_{index:03} shows a tool demonstration.",
            "visual_analysis": {"composition": f"VISUAL_{index:03} hands fill the frame beside a ruler.{tail}"},
            "focused_analysis": [{"observation": f"FOCUS_{index:03} result precedes numbered steps.{tail}",
                                  "interpretation": "The comparison may make the change easier to inspect.",
                                  "transfer": "Test a before and after comparison.", "evidence": ["frame_001.jpg"]}],
        }), encoding="utf-8")
        samples.append(sample)
    return creator.CloneSampleSet("synthetic_evidence_pool", title="Synthetic tutorial", samples=samples)


def assert_evidence(prompt, indices):
    for index in indices:
        assert f"evidence_{index:03}" in prompt
        for prefix in ("ASR", "OCR", "COMMENT", "VISUAL", "FOCUS"):
            assert f"{prefix}_{index:03}" in prompt, (prefix, index)
    assert '"secondhand":' in prompt
    assert '"source":' in prompt


@pytest.mark.parametrize("path", ["normal", "compact", "lite", "reduce", "micro"])
@pytest.mark.parametrize("count", [3, 6, 20])
def test_captured_provider_prompt_keeps_every_source_for_every_sample(monkeypatch, path, count):
    pool = evidence_pool(count, long=True)
    summaries = creator.build_sample_map_summaries(pool.samples)
    builders = {
        "normal": lambda: creator.build_distill_prompt(pool, pool.samples),
        "compact": lambda: creator.build_distill_prompt(pool, pool.samples, include_case_reports=False),
        "lite": lambda: creator.build_lite_distill_prompt(pool, pool.samples),
        "reduce": lambda: creator.build_reduce_distill_prompt(pool, pool.samples, summaries),
        "micro": lambda: creator.build_micro_reduce_distill_prompt(pool, pool.samples, summaries),
    }
    calls = install_provider(monkeypatch)
    creator.ExecutionLayer().analyze_json(creator.get_llm_provider(), builders[path](), [])
    prompt, images = calls[0]
    assert images == []
    assert_evidence(prompt, range(count))
    assert len(prompt) < 70000
    label = {"normal": "选中样本：", "compact": "选中样本：", "lite": "样本：", "reduce": "Map 摘要：", "micro": "样本摘要："}[path]
    rows = json.loads(prompt.rsplit(label, 1)[1])
    assert len(rows) == count
    assert len(json.dumps(rows, ensure_ascii=False)) <= 36000
    for row in rows:
        excerpts = row["evidence_excerpts"]
        assert len(excerpts) == 5
        assert all(item["text"] and item["truncated"] for item in excerpts.values())
        assert excerpts["prior_analysis"]["secondhand"] is True


@pytest.mark.parametrize("mode", ["quick", "deep"])
@pytest.mark.parametrize("retry", [False, True])
def test_real_orchestration_mock_provider_preserves_retry_evidence(monkeypatch, mode, retry):
    pool = evidence_pool()
    calls = install_provider(monkeypatch, fail_first=retry)
    creator.distill_creator_clone(pool, [sample.sample_id for sample in pool.samples], distill_mode=mode)
    assert len(calls) == (2 if retry else 1)
    for prompt, _ in calls:
        assert_evidence(prompt, range(3))


def test_150_sample_job_uses_bounded_batches_and_all_final_bindings(monkeypatch):
    pool = evidence_pool(150)
    calls = install_provider(monkeypatch)
    creator.batch_distill_creator_clone(pool, [sample.sample_id for sample in pool.samples], batch_size=20)
    assert len(calls) == 9
    for index, (prompt, _) in enumerate(calls[:-1]):
        assert_evidence(prompt, range(index * 20, min(150, (index + 1) * 20)))
        assert len(prompt) < 70000
    final_prompt = calls[-1][0]
    batches = json.loads(final_prompt.split("批次摘要：", 1)[1])
    assert [ref for batch in batches for ref in batch["sample_ids"]] == [sample.sample_id for sample in pool.samples]
    assert all(batch["source"] == "batch_result" and batch["secondhand"] for batch in batches)
    assert "ASR_000" not in final_prompt  # Batch summaries, not a claim of raw resubmission.
    assert len(final_prompt) < 70000


@pytest.mark.parametrize("value", [None, {}, [], "", "  ", "{}", "[]", "null", '"{}"', True,
                                       {"status": "success", "total_comments": 5}])
def test_semantically_empty_evidence_is_not_submitted(value):
    assert not creator._evidence_text(value)
    assert not creator._summary_evidence_excerpts({"evidence": {
        "asr_excerpt": value, "ocr_excerpt": value, "comment_summary": value,
    }})


def test_twenty_rows_escape_bounds_sanitization_and_fairness():
    text = 'A "quoted"\\\n\x00 observation. ' * 2000
    entries = {key: {"text": text, "source": "/private/cookie-file", "cookie": "SECRET"}
               for key in ("asr", "ocr", "comments", "prior_analysis", "focused_analysis")}
    rows = creator._bounded_evidence_rows([
        {"sample_id": f"sample_{index:03}", "title": text, "evidence_excerpts": entries,
         "private_path": "/private/cookie-file", "authorization": "SECRET"}
        for index in range(20)
    ])
    serialized = json.dumps(rows, ensure_ascii=False)
    assert len(serialized) <= 36000
    assert "SECRET" not in serialized and "/private/" not in serialized
    lengths = [len(json.dumps(row["evidence_excerpts"], ensure_ascii=False)) for row in rows]
    assert len(set(lengths)) == 1
    assert all(len(item["text"]) >= 16 for row in rows for item in row["evidence_excerpts"].values())
    with pytest.raises(ValueError, match="minimum text"):
        creator._bound_evidence_excerpts(entries, budget=100)
    with pytest.raises(ValueError, match="partitioned"):
        creator._bounded_evidence_rows(rows * 8)


def test_model_deterministic_fallback_and_unknown_origins_are_distinct():
    pool = creator.CloneSampleSet("synthetic_origins", samples=[creator.CloneSample("s", title="Sample", like_count=0)])
    raw = {"summary": "Concrete observation", "candidate_ideas": [{"title": "Test ruler comparison", "why_worth_trying": "Show scale"}],
           "transferable_formulas": [{"name": "Ruler comparison", "when_to_use": "Small objects", "risks": "Scale must match"}]}
    legacy = creator.normalize_creator_clone_result(raw, pool, pool.samples)
    assert creator._report_field_origin(legacy, "summary") == "unknown"
    raw["report_provenance"] = creator.creator_report_model_provenance(raw)
    result = creator.normalize_creator_clone_result(raw, pool, pool.samples)
    assert result["report_provenance"]["fields"]["performance_segments"] == "deterministic"
    assert creator._report_field_origin(result, "summary") == "model"
    view = result["creator_report_view_model"]
    assert "fallback" in view["sources"]["sections.formulas"]
    assert view["value_upgrade"]["sources"]["execution"] == "fallback"
    assert result["transferable_formulas"][0]["risks"] == "Scale must match"
    assert result["candidate_ideas"][0]["title"] == "Test ruler comparison"


def test_saved_semantics_used_when_embedded_asr_and_comments_are_status_only():
    pool = evidence_pool(1)
    directory = settings.cases_dir / pool.samples[0].case_id
    (directory / "analysis_input.json").write_text(json.dumps({"analysis_enrichment": {
        "asr": {"status": "success", "full_text": "{}"}, "comments": {"status": "success", "total_comments": 8},
    }}), encoding="utf-8")
    asr = directory / "enrichment" / "asr"
    comments = directory / "enrichment" / "comments"
    asr.mkdir(parents=True)
    comments.mkdir(parents=True)
    (asr / "transcript.json").write_text(json.dumps({"full_text": "Saved spoken step"}), encoding="utf-8")
    (comments / "comment_summary.json").write_text(json.dumps({"top_comments": [{"text": "Saved actual question?"}]}), encoding="utf-8")
    excerpts = creator.sample_map_summary(pool.samples[0])["evidence_excerpts"]
    assert excerpts["asr"]["text"] == "Saved spoken step"
    assert excerpts["asr"]["source"] == "enrichment.asr"
    assert excerpts["comments"]["text"] == "Saved actual question?"


def test_transcript_aliases_and_exact_duplicate_ocr_are_not_repeated():
    assert creator._evidence_text({"full_text": "A spoken step", "text": "A spoken step",
                                   "segments": [{"text": "A spoken step"}]}) == "A spoken step"
    assert creator._evidence_text({"full_text": "{}", "text": "A fallback step",
                                   "segments": [{"text": "A fallback step"}]}) == "A fallback step"
    assert creator._evidence_text({"cover_text": "Turn clockwise", "subtitle_text": "Turn  clockwise",
                                   "frame_text": "Stop when aligned"}) == "Turn clockwise\nStop when aligned"
    assert creator._evidence_text({"segments": [{"text": "First step"}, {"text": "Second step"}]}) == "First step\nSecond step"


@pytest.mark.parametrize("provenance", [None, [], "bad", {"fields": []},
    {"fields": {"summary": [], "candidate_ideas": {"origin": "model"}, "performance_segments": "model"}}])
def test_malformed_provenance_cannot_crash_or_claim_model_origin(provenance):
    pool = creator.CloneSampleSet("synthetic_provenance", samples=[])
    result = creator.normalize_creator_clone_result({"summary": "Saved content", "report_provenance": provenance}, pool, [])
    assert creator._report_field_origin(result, "summary") == "unknown"
    assert result["report_provenance"]["fields"]["performance_segments"] == "deterministic"
    assert creator._report_list_origins(result, ["Unmapped historical text"], ("summary",), 100) == ["unknown"]


def test_normalized_model_templates_keep_source_and_generic_additions_stay_separate():
    pool = creator.CloneSampleSet("synthetic_template_sources", samples=[])
    raw = {"summary": "A result-first demonstration", "transferable_formulas": [{
        "name": "Result then ruler", "when_to_use": "Only when scale is comparable",
        "beat_structure": "Show finished piece, then measure", "risks": "Do not compare different magnifications",
    }]}
    raw["report_provenance"] = creator.creator_report_model_provenance(raw)
    result = creator.normalize_creator_clone_result(raw, pool, [])
    assert creator._report_field_origin(result, "creator_clone_strategy.templates") == "model"
    assert result["creator_report_view_model"]["sources"]["sections.formulas"][0] == "model"
    assert result["creator_report_view_model"]["sources"]["sections.formulas"][-1] == "fallback"


def test_final_reduce_structured_conditions_and_all_ids_survive_long_batches():
    pool = creator.CloneSampleSet("synthetic_final", samples=[creator.CloneSample(f"sample_{index:03}") for index in range(150)])
    batches = [{"batch_id": f"batch_{start}", "status": "success",
                "sample_ids": [sample.sample_id for sample in pool.samples[start:start + 20]],
                "result": {"summary": "A ruler comparison is a testable hypothesis. " * 500,
                           "transferable_formulas": [{"name": "Compare scale", "when_to_use": "Matched magnification only",
                                                       "risks": "Do not imply equal size"}]}}
               for start in range(0, 150, 20)]
    prompt = creator.build_final_creator_clone_reduce_prompt(pool, pool.samples, batches)
    submitted = json.loads(prompt.split("批次摘要：", 1)[1])
    assert [ref for row in submitted for ref in row["sample_ids"]] == [sample.sample_id for sample in pool.samples]
    assert all(isinstance(row["transferable_formulas"][0], dict) for row in submitted)
    assert all(row["transferable_formulas"][0]["when_to_use"] == "Matched magnification only" for row in submitted)
    assert len(json.dumps(submitted, ensure_ascii=False)) <= 48000


def test_final_reduce_supports_150_single_sample_batches_without_losing_bindings():
    batches = [{"batch_id": f"batch_{index}", "sample_ids": [f"sample_{index:03}"],
                "status": "success", "source": "batch_result", "secondhand": True,
                "summary": "Concrete result before steps. " * 100,
                "focused_analysis": [{"observation": "Ruler beside object", "interpretation": "Scale may be clearer"}]*5}
               for index in range(150)]
    submitted = creator._bounded_batch_prompt_rows(batches)
    assert [row["sample_ids"] for row in submitted] == [row["sample_ids"] for row in batches]
    assert all(row["summary"] for row in submitted)
    assert len(json.dumps(submitted, ensure_ascii=False)) <= 48000


@pytest.mark.parametrize("with_json", [False, True])
def test_saved_markdown_report_is_bounded_secondhand_even_without_json(with_json):
    pool = evidence_pool(1)
    directory = settings.cases_dir / pool.samples[0].case_id
    if not with_json:
        (directory / "analysis_result.json").unlink()
    (directory / "analysis_report.md").write_text("已有 Case 报告：先展示结果，再用尺说明比例。", encoding="utf-8")
    summary = creator.sample_map_summary(pool.samples[0])
    prior = summary["evidence_excerpts"]["prior_analysis"]
    assert "已有 Case 报告" in prior["text"]
    assert prior["secondhand"] is True
    assert prior["source"] == ("analysis_result+analysis_report.md" if with_json else "analysis_report.md")
    assert "已有 Case 报告" in creator.build_distill_prompt(pool, pool.samples)
    (directory / "analysis_report.md").write_text("已有 Case 报告的具体观察。" * 3000, encoding="utf-8")
    bounded = creator.sample_map_summary(pool.samples[0])["evidence_excerpts"]
    assert len(json.dumps(bounded, ensure_ascii=False)) <= 1800
    assert bounded["prior_analysis"]["truncated"] is True
