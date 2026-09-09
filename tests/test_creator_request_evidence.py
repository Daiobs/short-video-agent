import json
from types import SimpleNamespace

import pytest
from PIL import Image

from app.services import creator_request_evidence as evidence


def make_sample(root, index=0, category="general"):
    case = root / f"case_{index}"
    case.mkdir(parents=True)
    Image.new("RGB", (32, 24), "red").save(case / "contact_sheet.jpg")
    return SimpleNamespace(sample_id=f"sample_{index}", case_id=case.name,
                           content_category=category)


def select(root, samples, limit=2, supported=True):
    return evidence.select_creator_request_images(
        samples, case_root=root, llm_max_keyframes=limit, supports_images=supported)


@pytest.mark.parametrize("limit,count", [(0, 0), (-1, 0), (2, 2), (6, 6), (99, 6)])
def test_existing_limit_and_six_cap(tmp_path, limit, count):
    samples = [make_sample(tmp_path, index) for index in range(8)]
    result = select(tmp_path, samples, limit)
    assert len(result["image_paths"]) == count
    assert [row["image_order"] for row in result["image_bindings"]] == list(range(1, count + 1))
    assert [row["sample_id"] for row in result["image_bindings"]] == [s.sample_id for s in samples[:count]]
    assert "untrusted" in result["prompt_note"]
    assert str(tmp_path) not in result["prompt_note"]


def test_two_of_five_is_read_only_and_explicit(tmp_path):
    samples = [make_sample(tmp_path, index) for index in range(5)]
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = select(tmp_path, samples)
    assert [row["reason"] for row in result["coverage"]] == [
        "direct_image_selected", "direct_image_selected", *["request_image_limit"] * 3]
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_only_selected_visual_and_unknown_samples(tmp_path):
    make_sample(tmp_path, 99)
    samples = [make_sample(tmp_path, i, category) for i, category in enumerate([
        "knowledge", "tutorial", "beauty_cos", "unknown"])]
    result = select(tmp_path, samples)
    assert [b["sample_id"] for b in result["image_bindings"]] == ["sample_2", "sample_3"]
    assert not select(tmp_path, samples, supported=False)["image_paths"]


@pytest.mark.parametrize("mode,visual,expected", [
    ("multi_image", {"composition": "Subject at the left edge"}, 0),
    ("text_only", {"composition": "Subject at the left edge"}, 1),
    ("contact_sheet_only", {}, 1),
    ("contact_sheet_only", {"subject": "{}", "composition": "null"}, 1),
    ("contact_sheet_only", {"subject": "文本降级，需复核画面"}, 1),
])
def test_valid_prior_visual_not_merely_report_presence(tmp_path, mode, visual, expected):
    sample = make_sample(tmp_path)
    (tmp_path / sample.case_id / "analysis_result.json").write_text(json.dumps({
        "summary": "Saved report", "visual_analysis": visual,
        "evidence_summary": {"visual_input_mode": mode}}))
    assert len(select(tmp_path, [sample])["image_paths"]) == expected


@pytest.mark.parametrize("restriction", ["file_link", "directory_link", "root_link", "ancestor_link",
                                          "traversal", "absolute", "corrupt", "oversize", "directory"])
def test_restricted_paths_are_not_submitted(tmp_path, monkeypatch, restriction):
    root = tmp_path / "cases"
    sample = make_sample(root)
    sheet = root / sample.case_id / "contact_sheet.jpg"
    if restriction == "file_link":
        target = tmp_path / "outside.jpg"
        sheet.rename(target)
        sheet.symlink_to(target)
    elif restriction == "directory_link":
        target = tmp_path / "outside"
        sheet.parent.rename(target)
        (root / sample.case_id).symlink_to(target, target_is_directory=True)
    elif restriction == "root_link":
        alias = tmp_path / "alias"
        alias.symlink_to(root, target_is_directory=True)
        root = alias
    elif restriction == "ancestor_link":
        alias = tmp_path / "alias"
        alias.symlink_to(tmp_path, target_is_directory=True)
        root = alias / "cases"
    elif restriction == "traversal":
        sample.case_id = "../cases/case_0"
    elif restriction == "absolute":
        sample.case_id = str(sheet.parent)
    elif restriction == "corrupt":
        sheet.write_text("not an image")
    elif restriction == "oversize":
        monkeypatch.setattr(evidence, "MAX_IMAGE_BYTES", 10)
    elif restriction == "directory":
        sheet.unlink()
        sheet.mkdir()
    assert select(root, [sample])["image_paths"] == []


def test_duplicate_and_oversized_pixel_input(tmp_path, monkeypatch):
    sample = make_sample(tmp_path)
    other = SimpleNamespace(sample_id="sample_other", case_id=sample.case_id, content_category="")
    assert len(select(tmp_path, [sample, sample, other])["image_paths"]) == 1
    monkeypatch.setattr(evidence, "MAX_IMAGE_PIXELS", 10)
    assert select(tmp_path, [sample])["image_paths"] == []


@pytest.mark.parametrize("report_kind", ["symlink", "oversize", "invalid", "non_object"])
def test_untrusted_prior_report_cannot_suppress_images(tmp_path, monkeypatch, report_kind):
    sample = make_sample(tmp_path)
    report = tmp_path / sample.case_id / "analysis_result.json"
    valid = json.dumps({"visual_analysis": {"subject": "Hands fold paper"},
                        "evidence_summary": {"visual_input_mode": "multi_image"}})
    if report_kind == "symlink":
        outside = tmp_path / "other_report.json"
        outside.write_text(valid)
        report.symlink_to(outside)
    elif report_kind == "oversize":
        report.write_text(valid)
        monkeypatch.setattr(evidence, "MAX_REPORT_BYTES", 10)
    else:
        report.write_text("{" if report_kind == "invalid" else "[]")
    assert len(select(tmp_path, [sample])["image_paths"]) == 1


def test_unreadable_image_and_no_contact_sheet_do_not_extract(tmp_path, monkeypatch):
    sample = make_sample(tmp_path)

    def denied(*args, **kwargs):
        raise PermissionError("synthetic read restriction")

    monkeypatch.setattr(evidence.Image, "open", denied)
    assert not select(tmp_path, [sample])["image_paths"]
    sheet = tmp_path / sample.case_id / "contact_sheet.jpg"
    sheet.rename(sheet.with_name("frame_001.jpg"))
    assert not select(tmp_path, [sample])["image_paths"]
    assert not sheet.exists()


def test_actual_semantics_sources_and_final_attempt():
    rows = [{"sample_id": f"sample_{i}", "title": "Example", "evidence_excerpts": {
        "asr": {"text": "First, fold the paper", "source": "enrichment.asr", "truncated": True},
        "ocr": {"text": "Fold twice", "source": "enrichment.ocr"},
        "comments": {"status": "success", "total_comments": 40, "top_needs": []},
        "prior_analysis": {"text": "The frame centers the hands", "source": "analysis_result"},
    }} for i in range(5)]
    result = evidence.summarize_creator_request("Analyze:\n" + json.dumps(rows),
        image_bindings=[{"sample_id": "sample_0", "image_order": 1}],
        attempt=2, final_attempt=True, degraded=True)
    assert result["attempt"] == 2 and result["final_attempt"] and result["degraded"]
    assert len(result["samples"]) == 5
    for row in result["samples"]:
        assert {m["kind"] for m in row["materials"]} == {"asr", "ocr", "prior_analysis"}
        assert row["truncated"]
        assert row["materials"][0]["source"] == "enrichment.asr"
        assert row["materials"][0]["chars"] == len("First, fold the paper")
        assert "First, fold the paper" not in json.dumps(result)
    assert result["samples"][0]["image_orders"] == [1]
    assert not result["samples"][1]["image_orders"]


def test_retry_does_not_inherit_prepared_or_failed_images():
    prompt = json.dumps([{"id": "sample_0", "title": "Example", "evidence": {
        "has_asr": True, "has_comments": True, "has_frames": True}}])
    first = evidence.summarize_creator_request(prompt, attempt=1, image_bindings=[
        {"sample_id": "sample_0", "image_order": 1}])
    final = evidence.summarize_creator_request(prompt, attempt=2, degraded=True, final_attempt=True)
    assert first["samples"][0]["image_orders"] == [1]
    assert not final["samples"][0]["image_orders"]
    assert not final["samples"][0]["materials"]


def test_summary_contains_only_metadata_not_private_material_text():
    text = "Opening /opt/private/secret.txt password=hunter2 sk-abcdefgh1234 https://private.example " + "x" * 400
    prompt = json.dumps([{"sample_id": "sample_0", "title": "private title", "evidence_excerpts": {
        "asr": {"text": text, "source": "/opt/private/report"}}}])
    result = evidence.summarize_creator_request(prompt, attempt=1)
    serialized = json.dumps(result)
    for forbidden in ("hunter2", "sk-abcdefgh", "/opt/private", "private.example", "private title"):
        assert forbidden not in serialized
    material = result["samples"][0]["materials"][0]
    assert material["source"] == "unknown"
    assert material["chars"] == len(text)
    assert set(material) == {"kind", "field", "source", "chars", "secondhand", "truncated"}
    assert "Opening" not in serialized


@pytest.mark.parametrize("text", ["{}", "[]", "null", "  ", '""', '[{}, [], null, "  "]',
                                  '{"text": "{}"}', '{"status": "success", "count": 3}'])
def test_serialized_empty_values_are_not_materials(text):
    row = {"sample_id": "sample_0", "evidence_excerpts": {
        kind: {"text": text, "source": "analysis_result"}
        for kind in ("asr", "ocr", "comments", "prior_analysis")}}
    result = evidence.summarize_creator_request(json.dumps([row]), attempt=1)
    assert result["samples"][0]["materials"] == []


def test_serialized_semantic_text_and_numeric_subtitles_remain_evidence():
    row = {"sample_id": "sample_0", "evidence_excerpts": {
        "asr": {"text": '{"text": "Fold paper"}', "source": "enrichment.asr"},
        "ocr": {"text": "123", "source": "enrichment.ocr"}}}
    result = evidence.summarize_creator_request(json.dumps([row]), attempt=1)
    assert [material["chars"] for material in result["samples"][0]["materials"]] == [10, 3]


@pytest.mark.parametrize("location", ["row", "evidence", "material"])
def test_context_truncated_is_recorded(location):
    row = {"sample_id": "sample_0", "evidence_excerpts": {
        "asr": {"text": "Opening", "source": "enrichment.asr"}}}
    target = {"row": row, "evidence": row["evidence_excerpts"],
              "material": row["evidence_excerpts"]["asr"]}[location]
    target["context_truncated"] = True
    result = evidence.summarize_creator_request(json.dumps([row]), attempt=1)
    assert result["samples"][0]["truncated"]
    assert result["samples"][0]["materials"][0]["truncated"] == (location == "material")


@pytest.mark.parametrize("map_source,count", [("", 0), ("metadata", 0), ("llm_map", 0),
                                               ("analysis_result", 1)])
def test_default_visual_fields_are_not_prior_analysis_without_trace(map_source, count):
    row = {"sample_id": "sample_0", "title": "Example", "map_source": map_source,
           "visual": {"subject": "Default subject"}}
    result = evidence.summarize_creator_request(json.dumps([row]), attempt=1)
    assert len(result["samples"][0]["materials"]) == count


@pytest.mark.parametrize("source,count", [("analysis_result", 1), ("map.analysis", 1),
    ("analysis_result.focused_analysis", 1), ("map.focused_analysis", 1),
    ("analysis_report.md", 1), ("analysis_result+analysis_report.md", 1),
    ("metadata", 0), ("private_secret", 0), ("enrichment.asr", 0), ("", 0)])
def test_prior_analysis_requires_known_analysis_provenance(source, count):
    row = {"sample_id": "sample_0", "evidence_excerpts": {
        "prior_analysis": {"text": "Centered framing", "source": source}}}
    result = evidence.summarize_creator_request(json.dumps([row]), attempt=1)
    assert len(result["samples"][0]["materials"]) == count


def test_final_reduce_eight_batches_bind_shared_summaries_without_inheriting_images():
    batches = [{"batch_id": f"batch_{i:03d}", "status": "success",
                "sample_ids": [f"sample_{i}_{j}" for j in range(20)],
                "summary": "The group demonstrates folding before explaining it",
                "creator_positioning": {"audience_promise": "Repeatable paper craft"},
                "focused_analysis": [{"observation": "Hands stay centered", "evidence": [f"sample_{i}_0"]}],
                "image_bindings": [{"sample_id": f"sample_{i}_0", "image_order": 1}]}
               for i in range(8)]
    segments = {"highest_like_samples": [{"sample_id": "sample_0_0", "title": "Private title",
                                          "metric": "like_count", "value": 100}],
                "highest_comment_samples": [{"sample_id": "metadata_only", "title": "Another title",
                                             "metric": "comment_count", "value": 0}]}
    prompt = "Batches:\n" + json.dumps(batches) + "\nPerformance:\n" + json.dumps(segments)
    result = evidence.summarize_creator_request(prompt, attempt=2, final_attempt=True)
    assert len(result["samples"]) == 161
    assert all(not row["image_orders"] for row in result["samples"])
    for row in result["samples"][:-1]:
        assert len(row["materials"]) == 1
        material = row["materials"][0]
        assert material["source"] == "batch_report" and material["kind"] == "prior_analysis"
        assert material["scope"] == "shared_batch" and material["secondhand"]
        assert material["chars"] > len(batches[0]["summary"])
    assert result["samples"][-1]["materials"] == []
    assert "paper craft" not in json.dumps(result)


@pytest.mark.parametrize("status,source", [("failed", "batch_failure"),
    ("prompt_only", "unknown"), ("fallback", "unknown"), ("", "unknown")])
def test_failed_or_unknown_batch_is_not_model_analysis(status, source):
    batch = {"batch_id": "batch_001", "status": status, "sample_ids": ["sample_0"],
             "summary": "Local fallback summary", "source": "batch_result", "secondhand": True}
    result = evidence.summarize_creator_request(json.dumps([batch]), attempt=1)
    material = result["samples"][0]["materials"][0]
    assert material["source"] == source and material["kind"] == "batch_context"
    assert not material["secondhand"]


def test_batch_refs_bounded_validated_and_empty_summaries_not_evidence():
    batch = {"batch_id": "batch_001", "status": "success",
             "sample_ids": [None, {}, "/tmp/private", "sample_0", "sample_0"] +
                           [f"sample_{i}" for i in range(1, 22)],
             "summary": "Bounded input", "context_truncated": True}
    result = evidence.summarize_creator_request(json.dumps([batch]), attempt=1)
    assert len(result["samples"]) == 20
    assert all(row["truncated"] and row["materials"][0]["sample_bindings_truncated"]
               for row in result["samples"])
    batch["summary"] = "{}"
    batch["focused_analysis"] = [{"evidence": ["sample_0"]}]
    result = evidence.summarize_creator_request(json.dumps([batch]), attempt=1)
    assert all(not row["materials"] for row in result["samples"])


def test_nonstructured_prompt_is_unknown_and_note_not_evidence(tmp_path):
    note = select(tmp_path, [make_sample(tmp_path)])["prompt_note"]
    result = evidence.summarize_creator_request("has_asr=true\n" + note, attempt=1)
    assert result["samples"] == []
    assert not result["structured_rows_found"]
