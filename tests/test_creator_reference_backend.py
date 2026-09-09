import copy
import json

import pytest

from app.services import creator_clone as creator
from app.services.creator_references import resolve_creator_references, request_input_summary
from tests.creator_reference_backend_fixture import backend_fixture


def test_c_shaped_references_aliases_and_invalid_support_are_idempotent():
    raw, pool, samples = backend_fixture()
    cleaned, manifest, warnings = resolve_creator_references(raw, samples)
    assert cleaned["expression_patterns"]["subtitle_voice"][0]["evidence"] == [samples[0].sample_id]
    row = next(x for x in manifest["entries"] if x["path"] == "expression_patterns.subtitle_voice[0].evidence")
    assert row["status"] == "partial" and row["invalid_refs"] == ["sample_demo_typo"]
    assert cleaned["expression_patterns"]["shot_types"][0]["evidence"] == [samples[1].sample_id]
    assert cleaned["expression_patterns"]["visual_style"][0]["evidence"] == [samples[0].sample_id]
    assert cleaned["transferable_formulas"][0]["supporting_samples"][0]["title"] == samples[0].title
    assert resolve_creator_references(json.loads(json.dumps(cleaned)), samples) == (cleaned, manifest, warnings)
    assert "sample_demo_typo" in raw["expression_patterns"]["subtitle_voice"][0]["evidence"]


def test_selected_and_submitted_intersection_and_unrelated_numbers():
    raw, pool, samples = backend_fixture()
    raw["request_evidence"]["samples"] = raw["request_evidence"]["samples"][:2]
    raw["candidate_ideas"][0]["id"] = "creative-idea-13"
    raw["next_actions"] = ["Use 1234567890123456789 as dialogue; see sample_demo_unknown for an unlocated reference."]
    result, manifest, warnings = resolve_creator_references(raw, samples)
    assert result["candidate_ideas"][0]["evidence"] == []
    assert result["candidate_ideas"][0]["id"] == "creative-idea-13"
    assert result["next_actions"] == raw["next_actions"]
    assert any(x["path"] == "next_actions[0]" and x["invalid_refs"] == ["sample_demo_unknown"] for x in manifest["entries"])
    assert len(manifest["samples"]) == 2
    assert warnings


def test_conflicting_identity_and_invalid_formula_leave_idea_not_false_support():
    raw, pool, samples = backend_fixture()
    raw["transferable_formulas"][0]["supporting_samples"][0]["case_id"] = samples[1].case_id
    result, _, warnings = resolve_creator_references(raw, samples)
    assert result["transferable_formulas"][0]["supporting_samples"] == []
    assert result["transferable_formulas"][0]["beat_structure"] == ["Reveal", "Contrast"]
    assert warnings


def test_source_counts_do_not_use_complete_inventory_and_reload_does_not_write():
    raw, pool, samples = backend_fixture()
    normalized = creator.normalize_creator_clone_result(raw, pool, samples)
    repeated = creator.normalize_creator_clone_result(json.loads(json.dumps(normalized)), pool, samples)
    assert repeated["reference_manifest"] == normalized["reference_manifest"]
    assert repeated["warnings"] == normalized["warnings"]
    view = normalized["creator_report_view_model"]
    assert view["evidence_counts"]["with_comments"] == 5
    assert view["request_input"]["comments"] == 0
    assert view["request_input"]["image_count"] == 2
    assert view["request_input"]["ocr"] == 5
    assert view["request_input"]["asr"] == 2
    assert "高" not in view["confidence_note"]
    creator.save_sample_set(pool)
    path = creator.creator_clone_dir(pool.set_id) / "creator_clone_result.json"
    normalized["creator_report_view_model"]["confidence_note"] = "评论均已覆盖；高可信"
    path.write_text(json.dumps(normalized))
    before = path.read_bytes()
    loaded = creator.load_creator_clone_result(pool.set_id)
    assert "评论均已覆盖" not in loaded["creator_report_view_model"]["confidence_note"]
    assert path.read_bytes() == before
    assert creator.load_creator_clone_result(pool.set_id) == loaded


@pytest.mark.parametrize("evidence", [None, {}, {"version": 1, "source": "inventory", "samples": []}])
def test_historical_unknown_does_not_claim_input_coverage(evidence):
    raw, pool, samples = backend_fixture()
    raw["request_evidence"] = evidence
    adapted = creator.adapt_creator_report_sources(raw, pool, samples)
    assert not adapted["creator_report_view_model"]["request_input"]["known"]
    assert "未完整记录" in adapted["creator_report_view_model"]["confidence_note"]
    assert adapted["creator_report_view_model"]["evidence_counts"]["with_comments"] == 5


def test_nested_contract_locations_and_group_refs_remain_canonical():
    raw, pool, samples = backend_fixture()
    raw["creator_clone_strategy"] = {"templates": [{"title": "Template", "references": [samples[1].case_id, "sample_demo_typ0"]}]}
    normalized = creator.normalize_creator_clone_result(raw, pool, samples)
    entries = normalized["reference_manifest"]["entries"]
    assert any(e["path"] == "creator_clone_strategy.templates[0].references" and e["valid_sample_ids"] == [samples[1].sample_id] for e in entries)
    assert normalized["focused_analysis"][0]["evidence"] == [samples[0].sample_id]
    assert len(normalized["warnings"]) == len(set(normalized["warnings"]))


@pytest.mark.parametrize("shape", ["sample_demo_0", {"case_id": "case_demo_0"},
                                  '{"aweme_id":"7000000000000000000"}',
                                  '["sample_demo_0","sample_demo_typo"]'])
def test_scalar_nested_and_json_encoded_citations_are_idempotent(shape):
    raw, pool, samples = backend_fixture()
    raw["expression_patterns"]["subtitle_voice"][0]["evidence"] = shape
    cleaned, manifest, warnings = resolve_creator_references(raw, samples)
    row = next(e for e in manifest["entries"] if e["path"] == "expression_patterns.subtitle_voice[0].evidence")
    assert row["valid_sample_ids"] == [samples[0].sample_id]
    assert resolve_creator_references(json.loads(json.dumps(cleaned)), samples) == (cleaned, manifest, warnings)


def test_historical_scope_is_only_identity_not_submission_and_exports_use_request():
    raw, pool, samples = backend_fixture()
    raw.pop("request_evidence")
    cleaned, manifest, _ = resolve_creator_references(raw, samples)
    assert manifest["scope"] == "historical_unknown"
    assert manifest["identity_scope"] == "selected_only"
    assert "未完整记录" in creator.render_creator_clone_markdown(cleaned)
    raw, _, _ = backend_fixture()
    raw["creator_report_view_model"] = {"confidence_note": "评论均已覆盖，高可信"}
    markdown = creator.render_creator_clone_markdown(raw)
    assert "有效评论 0 条" in markdown
    assert "评论均已覆盖" not in markdown


def test_routes_read_and_exports_share_adapter_without_rewriting_existing_files():
    from fastapi.testclient import TestClient
    from app.main import app

    raw, pool, samples = backend_fixture()
    creator.save_sample_set(pool)
    directory = creator.creator_clone_dir(pool.set_id)
    raw["creator_report_view_model"] = {"confidence_note": "评论均已覆盖，高可信"}
    (directory / "creator_clone_result.json").write_text(json.dumps(raw))
    (directory / "creator_clone.md").write_text("Archived Markdown; do not rewrite")
    (directory / "creator_clone.html").write_text("Archived HTML; do not rewrite")
    before = {name: (directory / name).read_bytes() for name in (
        "samples.json", "creator_clone_result.json", "creator_clone.md", "creator_clone.html")}
    client = TestClient(app)
    response = client.get(f"/api/creator-clone/sets/{pool.set_id}")
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["creator_report_view_model"]["request_input"]["comments"] == 0
    assert result["expression_patterns"]["subtitle_voice"][0]["evidence"] == [samples[0].sample_id]
    for filename in ("creator_clone_result.json", "creator_clone.md", "creator_clone.html"):
        exported = client.get(f"/api/creator-clone/sets/{pool.set_id}/files/{filename}")
        assert exported.status_code == 200
        assert "评论均已覆盖" not in exported.text
        assert filename in exported.headers["content-disposition"]
        if filename.endswith(".json"):
            assert exported.json()["reference_manifest"] == result["reference_manifest"]
        else:
            assert "有效评论 0 条" in exported.text
    assert before == {name: (directory / name).read_bytes() for name in before}


def test_html_missing_keeps_existing_lazy_creation_and_missing_markdown_stays_404():
    from fastapi.testclient import TestClient
    from app.main import app

    raw, pool, samples = backend_fixture()
    creator.save_sample_set(pool)
    directory = creator.creator_clone_dir(pool.set_id)
    path = directory / "creator_clone_result.json"
    path.write_text(json.dumps(raw))
    before = path.read_bytes()
    client = TestClient(app)
    assert client.get(f"/api/creator-clone/sets/{pool.set_id}/files/creator_clone.md").status_code == 404
    response = client.get(f"/api/creator-clone/sets/{pool.set_id}/files/creator_clone.html")
    assert response.status_code == 200
    assert (directory / "creator_clone.html").is_file()
    assert "有效评论 0 条" in response.text
    assert path.read_bytes() == before
