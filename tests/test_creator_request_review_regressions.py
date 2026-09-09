import json

import pytest
from PIL import Image

from app.config import settings
from app.services import creator_clone as creator
from app.services.creator_request_evidence import summarize_creator_request


@pytest.mark.parametrize("provider", ["compatible", "responses", "claude", "openai_responses"])
def test_provider_aliases_prepare_existing_images_under_effective_limit(provider):
    samples = []
    for index in range(3):
        sample = creator.CloneSample(f"sample_{index}", case_id=f"case_{index}")
        directory = settings.cases_dir / sample.case_id
        directory.mkdir(parents=True)
        Image.new("RGB", (24, 24), "red").save(directory / "contact_sheet.jpg")
        samples.append(sample)
    _, visual = creator._prepare_creator_request("Synthetic prompt", samples, {
        "provider": provider, "max_keyframes": 2})
    assert len(visual["image_paths"]) == 2
    assert [binding["sample_id"] for binding in visual["image_bindings"]] == ["sample_0", "sample_1"]


@pytest.mark.parametrize("with_json", [False, True])
def test_markdown_source_survives_actual_prompt_to_public_manifest(with_json):
    sample = creator.CloneSample("sample_review", case_id="case_review")
    directory = settings.cases_dir / sample.case_id
    directory.mkdir(parents=True)
    report = "Saved observation: the ruler remains beside the object."
    (directory / "analysis_report.md").write_text(report)
    if with_json:
        (directory / "analysis_result.json").write_text(json.dumps({
            "summary": "The object is measured before folding."}))
    pool = creator.CloneSampleSet("review_pool", samples=[sample])
    prompt = creator.build_micro_reduce_distill_prompt(pool, pool.samples, [creator.sample_map_summary(sample)])
    manifest = summarize_creator_request(prompt, attempt=1, final_attempt=True)
    material = next(item for row in manifest["samples"] for item in row["materials"]
                    if item["field"] == "evidence_excerpts.prior_analysis")
    assert material["source"] == ("analysis_result+analysis_report.md" if with_json else "analysis_report.md")
    assert material["secondhand"] and material["chars"] > 0
    assert report not in json.dumps(manifest)


@pytest.mark.parametrize("length,truncated", [(259, False), (260, False), (261, True), (1000, True)])
@pytest.mark.parametrize("status,source", [("success", "batch_report"), ("failed", "batch_failure")])
def test_final_batch_summary_preclipping_survives_to_manifest(length, truncated, status, source):
    sample = creator.CloneSample("sample_review")
    pool = creator.CloneSampleSet("review_pool", samples=[sample])
    batches = [{"batch_id": "batch_001", "sample_ids": [sample.sample_id],
                "status": status, "result": {"summary": "x" * length}}]
    prompt = creator.build_final_creator_clone_reduce_prompt(pool, pool.samples, batches)
    submitted = json.loads(prompt.split("批次摘要：", 1)[1])
    assert len(submitted[0]["summary"]) == min(length, 260)
    assert submitted[0]["context_truncated"] is truncated
    manifest = summarize_creator_request(prompt, attempt=1, final_attempt=True)
    entry = next(row for row in manifest["samples"] if row["sample_id"] == sample.sample_id)
    material = next(item for item in entry["materials"] if item.get("batch_id") == "batch_001")
    assert material["source"] == source
    assert material["truncated"] is truncated
    assert entry["truncated"] is truncated
    assert entry["image_orders"] == []


def test_later_batch_budget_truncation_is_still_recorded():
    rows = [{"batch_id": "batch_001", "sample_ids": ["sample_review"], "status": "success",
             "summary": "x" * 10000, "context_truncated": False}]
    clipped = creator._bounded_batch_prompt_rows(rows)
    assert clipped[0]["context_truncated"] is True
    assert len(clipped[0]["summary"]) < 10000
