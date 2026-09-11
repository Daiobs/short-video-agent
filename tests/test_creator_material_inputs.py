import json
from types import SimpleNamespace

from PIL import Image

from app.services.creator_material_inputs import (
    MAX_JSON_BYTES, clean_material_text, collect_materials,
    read_material_json, safe_case_dir, select_images,
)


def save(case, relative, value):
    path = case / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def setup_case(tmp_path):
    root = tmp_path.resolve() / "cases"
    case = root / "case_1"
    case.mkdir(parents=True)
    return root, case, SimpleNamespace(sample_id="sample_1", case_id="case_1")


def test_materials_original_distinct_secondhand_and_bounded(tmp_path):
    root, case, sample = setup_case(tmp_path)
    save(case, "enrichment/asr/transcript.json", {"full_text": "speech " * 300, "segments": [{"text": "opening", "start": 0, "end": 2}]})
    for kind in ("cover", "subtitle", "frame"):
        save(case, f"enrichment/ocr/{kind}_ocr.json", {"full_text": kind})
    save(case, "enrichment/comments/comment_summary.json", {"status": "success", "total_comments": 900, "notes": "DO_NOT_SEND", "top_comments": [{"text": "audience question", "user": "DO_NOT_SEND"}]})
    save(case, "analysis_result.json", {"summary": "observed scene", "limitations": ["missing audio"], "replication": {"remake_angle": "DO_NOT_SEND"}, "next_actions": ["DO_NOT_SEND"], "visual_analysis": {"scene": "api_key=SECRETVALUE"}})
    result = collect_materials(sample, root)
    assert result["version"] == 1 and result["sample_id"] == "sample_1"
    sources = result["sources"]
    assert sources["asr"]["segments"][0]["start"] == 0
    assert sources["ocr"]["cover_text"] == "cover"
    assert sources["ocr"]["frame_text"] == "frame"
    assert sources["existing_analysis"]["secondhand"] is True
    assert sources["existing_analysis"]["limits"] == "missing audio"
    encoded = json.dumps(result)
    assert "DO_NOT_SEND" not in encoded and "SECRETVALUE" not in encoded
    compact = collect_materials(sample, root, compact=True)["sources"]["asr"]
    assert len(compact["excerpt"]) + sum(len(x["text"]) for x in compact["segments"]) <= 400


def test_safe_readers_reject_traversal_symlinks_oversize_depth(tmp_path):
    root, case, _ = setup_case(tmp_path)
    assert safe_case_dir("../case_1", root) is None
    outside = save(root, "outside.json", {"text": "private"})
    (case / "link.json").symlink_to(outside)
    assert read_material_json(case, "link.json") == {}
    assert read_material_json(case, "../outside.json") == {}
    assert read_material_json(case, outside) == {}
    (root / "alias").symlink_to(case, target_is_directory=True)
    assert safe_case_dir("alias", root) is None
    (case / "big.json").write_bytes(b" " * (MAX_JSON_BYTES + 1))
    assert read_material_json(case, "big.json") == {}
    nested = {}
    for _ in range(30):
        nested = {"child": nested}
    save(case, "deep.json", nested)
    assert read_material_json(case, "deep.json") == {}
    (case / "bad.json").write_text("[", encoding="utf-8")
    assert read_material_json(case, "bad.json") == {}


def test_jsonl_semantics_and_fallback_excluded(tmp_path):
    root, case, sample = setup_case(tmp_path)
    path = case / "enrichment/comments/comments_clean.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"text": "real reaction", "notes": "NO"}) + "\n", encoding="utf-8")
    save(case, "analysis_result.json", {"is_fallback": True, "summary": "fabricated"})
    sources = collect_materials(sample, root)["sources"]
    assert sources["comments"]["excerpt"] == "real reaction"
    assert sources["existing_analysis"]["status"] == "missing"
    assert "fabricated" not in json.dumps(sources)
    assert clean_material_text("Bearer abcdefgh sk-abcdefgh123 https://example.test/token", 200).count("redacted") == 3


def test_images_fallback_limits_and_no_paths_in_diagnostics(tmp_path):
    root, case, sample = setup_case(tmp_path)
    (case / "contact_sheet.jpg").write_bytes(b"invalid")
    frames = case / "keyframes"
    frames.mkdir()
    Image.new("RGB", (20, 20)).save(frames / "frame_001.jpg")
    paths, diagnostics = select_images([sample] * 8, root, SimpleNamespace())
    assert len(paths) == 6
    assert diagnostics[0]["kind"] == "keyframe"
    assert diagnostics[5]["index"] == 6
    assert diagnostics[6]["status"] == "limit_reached"
    assert str(root) not in json.dumps(diagnostics)
    Image.new("RGB", (20, 20)).save(case / "contact_sheet.jpg")
    paths, diagnostics = select_images([sample] * 3, root, SimpleNamespace(max_keyframes=1))
    assert len(paths) == 1 and diagnostics[0]["kind"] == "contact_sheet"
    assert select_images([sample], root, SimpleNamespace(supports_images=False))[0] == []
    assert select_images([sample], root, SimpleNamespace(max_keyframes=0))[0] == []


def test_image_symlink_and_pixel_byte_limits(tmp_path, monkeypatch):
    import app.services.creator_material_inputs as module
    root, case, sample = setup_case(tmp_path)
    outside = root / "outside.jpg"
    Image.new("RGB", (20, 20)).save(outside)
    (case / "contact_sheet.jpg").symlink_to(outside)
    assert select_images([sample], root, SimpleNamespace())[0] == []
    (case / "contact_sheet.jpg").unlink()
    Image.new("RGB", (20, 20)).save(case / "contact_sheet.jpg")
    monkeypatch.setattr(module, "MAX_IMAGE_PIXELS", 10)
    assert select_images([sample], root, SimpleNamespace())[0] == []
    monkeypatch.setattr(module, "MAX_IMAGE_PIXELS", 1000)
    monkeypatch.setattr(module, "MAX_IMAGE_BYTES", 10)
    assert select_images([sample], root, SimpleNamespace())[0] == []


def test_embedded_fallback_and_saved_statuses(tmp_path):
    root, case, sample = setup_case(tmp_path)
    save(case, "analysis_input.json", {"analysis_enrichment": {
        "asr": {"full_text": "embedded speech", "segments": [{"text": "speech", "start": 1}]},
        "ocr": {"cover_text": "embedded cover", "frame_text": "embedded frame"},
        "comments": {"top_needs": ["embedded need"]},
    }})
    save(case, "enrichment/asr/status.json", {"status": "failed"})
    save(case, "enrichment/comments/comment_summary.json", {"top_comments": [{"text": "{}"}], "top_needs": ["[]", " "]})
    save(case, "analysis_result.json", {"summary": "observed", "risks": ["limited evidence"]})
    sources = collect_materials(sample, root)["sources"]
    assert sources["asr"]["source"] == "analysis_input_enrichment_asr"
    assert sources["asr"]["status"] == "failed"
    assert sources["ocr"]["frame_text"] == "embedded frame"
    assert sources["comments"]["excerpt"] == "embedded need"
    assert sources["comments"]["source"].endswith("derived")
    assert sources["existing_analysis"]["limits"] == "limited evidence"
    save(case, "analysis_input.json", {})
    save(case, "enrichment/asr/status.json", {"status": "no_speech"})
    sources = collect_materials(sample, root)["sources"]
    assert sources["asr"]["status"] == "no_speech"
    assert sources["comments"]["status"] == "missing"
