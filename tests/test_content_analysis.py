"""Synthetic examples only; these are wiring tests, not model quality evidence."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import CaseArtifact, Job
from app.services.analysis_taxonomy import build_analysis_context, build_prompt
from app.services.content_analysis import (
    creator_category, focus_prompt, normalize_focused_analysis,
    request_evidence, resolve_analysis_focus,
)


SYNTHETIC_CASES = [
    ("COS 角色近景展示", "", "beauty_cos"),
    ("COS 妆容教程", "第一步铺底色，第二步画眼线，最后对比结果", "tutorial"),
    ("摄影出片教程", "调整机位，展示成片与拍摄过程", "photo_beauty"),
    ("知识观点", "核心论点是理解成本，举例说明，再给出论证", "knowledge"),
    ("低谷成长情绪文案", "先描述委屈，再转折为自己的选择", "motivational"),
    ("COS角色反转剧情", "冲突之后揭示误会，回收伏笔", "plot_twist"),
    ("未知素材", "", "generic"),
]


@pytest.mark.parametrize("title,transcript,expected", SYNTHETIC_CASES)
def test_synthetic_expression_direction(title, transcript, expected):
    pack = {"analysis_direction": "auto", "analysis_enrichment": {
        "asr": {"status": "success" if transcript else "not_configured", "full_text": transcript}}}
    focus = resolve_analysis_focus({"title": title}, pack)
    assert focus["primary"] == expected
    assert focus["source"] == "auto"
    if "COS" in title and expected != "beauty_cos":
        assert "beauty_cos" in focus["auxiliary"]
    for compact in (False, True):
        prompt = focus_prompt(focus, request_evidence(pack, [Path("frame_0000.jpg")]), compact)
        assert expected in prompt
        assert focus["questions"][0] in prompt
        assert "45%" not in prompt


@pytest.mark.parametrize("status,text,state", [
    ("not_configured", "", "not_run"), ("pending", "", "not_run"),
    ("failed", "", "failed"), ("success", "", "empty_text"),
    ("no_speech", "", "empty_text"), ("success", "第一步", "valid_text"),
])
def test_asr_state_does_not_imply_no_speech(status, text, state):
    evidence = request_evidence({"analysis_enrichment": {"asr": {"status": status, "full_text": text}}}, [])
    assert evidence["asr"]["text_state"] == state
    assert evidence["asr"]["submitted"] == bool(text)
    assert evidence["visual_available"] is False
    assert "no_speech" not in evidence or evidence["no_speech"] is not True


def test_user_direction_legacy_and_auto_are_distinct():
    metadata = {"title": "COS 妆容教程"}
    assert resolve_analysis_focus(metadata, {"content_category": "beauty_cos"})["source"] == "legacy"
    manual = resolve_analysis_focus(metadata, {"analysis_direction": "beauty_cos"})
    assert (manual["primary"], manual["source"]) == ("beauty_cos", "user")
    auto = resolve_analysis_focus(metadata, {"content_category": "beauty_cos", "analysis_direction": "auto"})
    assert (auto["primary"], auto["source"]) == ("tutorial", "auto")
    assert resolve_analysis_focus(metadata, {"analysis_direction": "invalid"})["primary"] == "generic"
    assert creator_category("tutorial") != creator_category("knowledge")
    assert creator_category("photo_beauty") == "photo_beauty"
    assert creator_category("motivational") == "emotional_copy"


@pytest.mark.parametrize("status,expected", [("not_configured", "not_run"), ("failed", "failed"), ("success", "empty_text")])
def test_blank_ocr_never_supplies_a_valid_reference(status, expected):
    pack = {"analysis_enrichment": {"ocr": {"status": status, "frame_text": "", "subtitle_text": "  ", "cover_text": ""}}}
    evidence = request_evidence(pack, [])
    assert evidence["ocr"]["submitted"] is False
    assert evidence["ocr"]["text_state"] == expected
    assert "ocr" not in evidence["valid_refs"]
    rows = normalize_focused_analysis([{"observation": "合成文字声明", "evidence": ["ocr"]}], evidence["valid_refs"])
    assert rows[0]["evidence"] == []
    assert "已移除" in rows[0]["uncertainty"]
    assert "仅根据元数据" in resolve_analysis_focus({"title": "合成展示"}, pack)["reason"]


def test_focused_refs_filter_unselected_material_and_preserve_uncertainty():
    normalized = normalize_focused_analysis([{
        "observation": "合成示例：人物近景", "transfer": "尝试固定机位",
        "evidence": ["frame_0000.jpg", "sample_unselected"],
    }], ["frame_0000.jpg"])
    assert normalized[0]["evidence"] == ["frame_0000.jpg"]
    assert "已移除" in normalized[0]["uncertainty"]


def test_export_prompt_has_no_preset_ratio_or_sensitive_metadata():
    context = build_analysis_context("tutorial")
    assert context["content_ratio"] == []
    assert context["attention_priorities"]
    prompt = build_prompt({"title": "合成教程", "like_count": None,
        "source_url": "https://cdn.invalid/a?signature=secret", "notes": "Cookie: secret"}, {"duration": 4}, context)
    assert "合成教程" in prompt and "步骤" in prompt
    assert "signature=secret" not in prompt and "Cookie: secret" not in prompt
    assert "45%" not in prompt and "各占多少" not in prompt


def test_category_api_only_changes_direction_and_keeps_prior_report(monkeypatch):
    root = settings.cases_dir / "case_synthetic_focus"
    root.mkdir(parents=True)
    payloads = {"metadata.json": {"title": "COS 妆容教程"},
        "ffprobe.json": {"duration": 4, "width": 100, "height": 100},
        "analysis_input.json": {"case_id": root.name, "title": "COS 妆容教程", "analysis_direction": "auto", "assets": {}, "video": {"duration": 4}},
        "qualities.json": [], "analysis_result.json": {"summary": "合成旧报告", "analysis_focus": {"primary": "beauty_cos", "label": "美拍", "version": 1}}}
    for name, data in payloads.items():
        (root / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (root / "prompt.md").write_text("合成 Prompt", encoding="utf-8")
    (root / "analysis_report.md").write_text("合成旧报告", encoding="utf-8")
    artifact = CaseArtifact(case_id=root.name, **{key: str(root / filename) for key, filename in {
        "metadata_path": "metadata.json", "ffprobe_path": "ffprobe.json", "analysis_input_path": "analysis_input.json",
        "qualities_path": "qualities.json", "prompt_path": "prompt.md", "video_path": "video.mp4",
        "contact_sheet_path": "contact_sheet.jpg", "keyframes_dir": "keyframes"}.items()})
    with SessionLocal() as db:
        db.add(artifact)
        db.commit()
    original_report = (root / "analysis_report.md").read_bytes()
    # This operation must not schedule jobs, call providers or rebuild the case.
    from app.routes import cases
    monkeypatch.setattr(cases, "existing_auto_analysis", lambda artifact: (payloads["analysis_result.json"], "合成旧报告"))
    client = TestClient(app)
    for requested, effective, source in (("knowledge", "knowledge", "user"), ("auto", "tutorial", "auto")):
        response = client.post(f"/api/cases/{root.name}/analysis-category", json={"category_id": requested})
        assert response.status_code == 200, response.text
        result = response.json()["case"]
        assert result["analysis_input"]["analysis_focus"]["primary"] == effective
        assert result["analysis_input"]["analysis_focus"]["source"] == source
        persisted = json.loads((root / "analysis_input.json").read_text())
        assert persisted["analysis_direction"] == requested
    assert (root / "analysis_report.md").read_bytes() == original_report
    assert json.loads((root / "analysis_result.json").read_text())["analysis_focus"]["primary"] == "beauty_cos"
    with SessionLocal() as db:
        assert db.query(Job).count() == 0
