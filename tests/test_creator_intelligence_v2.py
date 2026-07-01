from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.creator_clone import CloneSample, CloneSampleSet
from app.services.creator_clone import normalize_creator_clone_result, save_sample_set, validate_creator_clone_schema
from app.services.creator_intelligence import (
    CreatorCloneStrategy,
    CreatorSample,
    WorkflowAction,
    WorkflowEngine,
    WorkflowState,
    build_behavior_representation,
    project_from_clone_sample_set,
    project_from_clone_selection,
    samples_from_browser_dom,
    samples_from_case_import,
    samples_from_cookie_api,
    samples_from_json_csv,
    samples_from_manual_links,
)
from app.services.creator_intelligence.dispatch import dispatch_creator_workflow

client = TestClient(app)


def sample_set_for_v2() -> CloneSampleSet:
    return CloneSampleSet(
        set_id="clone_v2_test",
        title="v2 测试素材池",
        creator_name="测试创作者",
        source_platform="douyin",
        profile_metadata={
            "sec_user_id": "MS4wLjABAAAA_v2",
            "profile_url": "https://www.douyin.com/user/MS4wLjABAAAA_v2",
            "bio": "甜美 COS 账号",
        },
        selected_sample_ids=["sample_ready"],
        samples=[
            CloneSample(
                sample_id="sample_ready",
                aweme_id="7650000000000000001",
                title="高赞 COS 视频",
                source_type="douyin",
                media_type="video",
                like_count=1000,
                comment_count=20,
                share_count=30,
                collect_count=40,
                understanding_level="partial",
                has_video=True,
                has_frames=True,
                has_ocr=True,
                case_id="case_ready",
                selected=True,
            ),
            CloneSample(
                sample_id="sample_meta",
                aweme_id="7650000000000000002",
                title="仅元数据样本",
                source_type="douyin",
                media_type="image",
                like_count=10,
                comment_count=1,
                share_count=0,
                understanding_level="metadata_only",
            ),
        ],
    )


def test_clone_sample_set_adapts_to_creator_project() -> None:
    project = project_from_clone_sample_set(sample_set_for_v2())

    assert project.project_id == "clone_v2_test"
    assert project.to_dict()["id"] == "clone_v2_test"
    assert project.profile.creator_id == "MS4wLjABAAAA_v2"
    assert project.profile.to_dict()["id"] == "MS4wLjABAAAA_v2"
    assert project.profile.to_dict()["name"] == "测试创作者"
    assert project.profile.to_dict()["source"] == "douyin"
    assert "metadata" in project.profile.to_dict()
    assert project.profile.display_name == "测试创作者"
    assert project.profile.platform.value == "douyin"
    assert project.sample_count == 2
    assert project.selected_count == 1
    assert project.samples[0].metrics.engagement_score == 1340
    assert project.samples[0].to_dict()["source_type"] == "douyin"
    assert project.samples[0].to_dict()["aweme_id"] == "7650000000000000001"
    assert project.samples[0].to_dict()["media_type"] == "video"
    assert project.samples[0].to_dict()["evidence_level"] == "partial"
    assert project.samples[0].evidence.ready_for_distillation is True
    assert project.samples[1].evidence.level.value == "metadata_only"


def test_behavior_representation_is_cognitive_middle_layer() -> None:
    project = project_from_clone_sample_set(sample_set_for_v2())
    behavior = build_behavior_representation(project)

    assert behavior.project_id == project.project_id
    assert behavior.sample_count == 2
    assert behavior.selected_count == 1
    assert behavior.evidence_matrix["selected_count"] == 1
    assert behavior.evidence_matrix["with_keyframes"] == 1
    assert behavior.evidence_matrix["with_ocr_text"] == 1
    assert behavior.performance_segments["highest_like_samples"][0]["title"] == "高赞 COS 视频"
    assert behavior.media_mix == {"video": 1}
    assert behavior.behavior_patterns["dominant_media"] == "video"
    assert behavior.content_structures["media_mix"] == {"video": 1}
    assert behavior.hook_patterns["hook_evidence"] == "frames_or_text"
    assert behavior.risk_patterns["low_confidence"] is False
    assert any("No ASR evidence" in item for item in behavior.constraints)


def test_adapter_sources_output_unified_samples() -> None:
    rows = [
        {
            "sample_id": "sample_one",
            "source_type": "douyin",
            "aweme_id": "765",
            "media_type": "video",
            "title": "统一入口",
            "like_count": 10,
            "has_frames": True,
            "understanding_level": "partial",
        }
    ]

    for adapter in (
        samples_from_manual_links,
        samples_from_browser_dom,
        samples_from_json_csv,
        samples_from_case_import,
        samples_from_cookie_api,
    ):
        samples = adapter(rows)
        assert isinstance(samples[0], CreatorSample)
        assert samples[0].sample_id == "sample_one"
        assert samples[0].source.value == "douyin"
        assert samples[0].media_kind.value == "video"
        assert samples[0].evidence.level.value == "partial"


def test_selection_adapter_keeps_behavior_model_scoped_to_selected_samples() -> None:
    sample_set = sample_set_for_v2()
    project = project_from_clone_selection(sample_set, [sample_set.samples[0]])
    behavior = build_behavior_representation(project)

    assert project.sample_count == 1
    assert project.selected_count == 1
    assert behavior.media_mix == {"video": 1}
    assert behavior.performance_segments["highest_like_samples"][0]["sample_id"] == "sample_ready"


def test_workflow_engine_controls_creator_distillation_state() -> None:
    project = project_from_clone_sample_set(sample_set_for_v2())
    engine = WorkflowEngine(project=project)

    assert engine.get_state().state == WorkflowState.IMPORT
    assert engine.get_state().to_dict()["ui"]["stage"] == "import"
    assert engine.get_state().to_dict()["next_action"]["state"] == "IMPORT_READY"
    assert engine.get_state().to_dict()["next_action"]["command"] == "import_input"
    assert engine.dispatch(WorkflowAction.INGEST).state == WorkflowState.INGESTED
    ready = engine.dispatch(WorkflowAction.BUILD_SAMPLE_POOL)
    assert ready.state == WorkflowState.SAMPLE_READY
    assert ready.to_dict()["next_action"]["command"] == "select_recommended_samples"
    selected = engine.dispatch(WorkflowAction.SELECT_SAMPLES, {"selected_sample_ids": ["sample_ready"]})
    assert selected.state == WorkflowState.SAMPLE_SELECTED
    assert selected.selected_count == 1
    assert selected.to_dict()["ui"]["stage"] == "enrich"
    assert selected.to_dict()["next_action"]["state"] == "DISTILL_READY"
    assert selected.to_dict()["next_action"]["command"] == "start_distillation"
    evidence = engine.dispatch(WorkflowAction.MARK_EVIDENCE_READY)
    assert evidence.state == WorkflowState.EVIDENCE_READY
    assert evidence.has_behavior_model is True
    assert evidence.to_dict()["ui"]["stage"] == "distill"
    assert evidence.to_dict()["next_action"]["state"] == "DISTILL_READY"
    assert evidence.to_dict()["next_action"]["command"] == "start_distillation"
    assert engine.behavior_model is not None
    distilling = engine.dispatch(WorkflowAction.START_DISTILLATION)
    assert distilling.state == WorkflowState.DISTILLING
    assert distilling.to_dict()["next_action"]["command"] == "wait"
    done = engine.dispatch(
        WorkflowAction.COMPLETE_DISTILLATION,
        {"strategy_output": CreatorCloneStrategy(positioning="甜美 COS 视觉吸引").to_dict()},
    )
    assert done.state == WorkflowState.DONE
    assert done.has_strategy_output is True
    assert done.to_dict()["ui"]["stage"] == "export"
    assert done.to_dict()["next_action"]["command"] == "export_report"


def test_workflow_engine_restores_done_state_from_strategy_output() -> None:
    project = project_from_clone_sample_set(sample_set_for_v2())
    strategy = CreatorCloneStrategy(positioning="甜美 COS 视觉吸引").to_dict()

    engine = WorkflowEngine.from_project(project, strategy_output=strategy)

    snapshot = engine.get_state().to_dict()
    assert snapshot["state"] == WorkflowState.DONE
    assert snapshot["has_strategy_output"] is True
    assert snapshot["next_action"]["command"] == "export_report"


def test_workflow_engine_rejects_ui_driven_state_skips() -> None:
    project = project_from_clone_sample_set(sample_set_for_v2())
    engine = WorkflowEngine(project=project)

    with pytest.raises(ValueError, match="Cannot dispatch START_DISTILLATION"):
        engine.dispatch(WorkflowAction.START_DISTILLATION)

    engine.dispatch(WorkflowAction.INGEST)
    with pytest.raises(ValueError, match="Cannot mark sample pool ready"):
        empty_project = project.__class__(project_id="empty_project")
        WorkflowEngine(project=empty_project, state=WorkflowState.INGESTED).dispatch(WorkflowAction.BUILD_SAMPLE_POOL)


def test_creator_clone_set_endpoint_exposes_creator_intelligence_state() -> None:
    sample_set = sample_set_for_v2()
    shutil.rmtree(settings.creator_clones_dir / sample_set.set_id, ignore_errors=True)
    save_sample_set(sample_set)

    response = client.get(f"/api/creator-clone/sets/{sample_set.set_id}")

    assert response.status_code == 200
    payload = response.json()
    intelligence = payload["creator_intelligence"]
    assert intelligence["project"]["project_id"] == sample_set.set_id
    assert intelligence["workflow"]["state"] == WorkflowState.EVIDENCE_READY
    assert intelligence["workflow"]["selected_count"] == 1
    assert intelligence["behavior_model"]["project_id"] == sample_set.set_id
    assert intelligence["behavior_model"]["evidence_matrix"]["with_keyframes"] == 1
    shutil.rmtree(settings.creator_clones_dir / sample_set.set_id, ignore_errors=True)


def test_creator_clone_set_endpoint_restores_done_state_from_strategy_output() -> None:
    sample_set = sample_set_for_v2()
    output_dir = settings.creator_clones_dir / sample_set.set_id
    shutil.rmtree(output_dir, ignore_errors=True)
    save_sample_set(sample_set)
    output_dir.mkdir(parents=True, exist_ok=True)
    strategy = CreatorCloneStrategy(positioning="甜美 COS 视觉吸引", hooks=("第一眼给脸",)).to_dict()
    (output_dir / "creator_clone_result.json").write_text(
        json.dumps({"summary": "完成", "creator_clone_strategy": strategy}, ensure_ascii=False),
        encoding="utf-8",
    )

    response = client.get(f"/api/creator-clone/sets/{sample_set.set_id}")

    assert response.status_code == 200
    intelligence = response.json()["creator_intelligence"]
    assert intelligence["project"]["project_id"] == sample_set.set_id
    assert intelligence["workflow"]["state"] == WorkflowState.DONE
    assert intelligence["workflow"]["has_strategy_output"] is True
    assert intelligence["strategy_output"] == strategy
    shutil.rmtree(output_dir, ignore_errors=True)


def test_creator_clone_workflow_dispatch_selects_samples_and_persists_state() -> None:
    sample_set = sample_set_for_v2()
    sample_set.selected_sample_ids = []
    for sample in sample_set.samples:
        sample.selected = False
    shutil.rmtree(settings.creator_clones_dir / sample_set.set_id, ignore_errors=True)
    save_sample_set(sample_set)

    response = client.post(
        f"/api/creator-clone/sets/{sample_set.set_id}/workflow",
        json={"action": WorkflowAction.SELECT_SAMPLES.value, "selected_sample_ids": ["7650000000000000001"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["set"]["selected_sample_ids"] == ["sample_ready"]
    assert payload["creator_intelligence"]["workflow"]["state"] == WorkflowState.EVIDENCE_READY
    assert payload["creator_intelligence"]["workflow"]["selected_count"] == 1
    assert payload["creator_intelligence"]["behavior_model"]["selected_count"] == 1

    reloaded = client.get(f"/api/creator-clone/sets/{sample_set.set_id}").json()
    assert reloaded["set"]["selected_sample_ids"] == ["sample_ready"]
    shutil.rmtree(settings.creator_clones_dir / sample_set.set_id, ignore_errors=True)


def test_shared_creator_workflow_dispatch_service_selects_samples() -> None:
    sample_set = sample_set_for_v2()
    sample_set.selected_sample_ids = []
    for sample in sample_set.samples:
        sample.selected = False
    shutil.rmtree(settings.creator_clones_dir / sample_set.set_id, ignore_errors=True)
    save_sample_set(sample_set)

    result = dispatch_creator_workflow(
        sample_set.set_id,
        WorkflowAction.SELECT_SAMPLES,
        selected_sample_ids=["7650000000000000001"],
    )

    assert result.sample_set.selected_sample_ids == ["sample_ready"]
    assert result.workflow["state"] == WorkflowState.EVIDENCE_READY
    assert result.behavior_model["selected_count"] == 1
    reloaded = client.get(f"/api/creator-intelligence/projects/{sample_set.set_id}").json()
    assert reloaded["project"]["selected_sample_ids"] == ["sample_ready"]
    shutil.rmtree(settings.creator_clones_dir / sample_set.set_id, ignore_errors=True)


def test_creator_clone_workflow_dispatch_rejects_unknown_sample_ids() -> None:
    sample_set = sample_set_for_v2()
    sample_set.selected_sample_ids = []
    for sample in sample_set.samples:
        sample.selected = False
    shutil.rmtree(settings.creator_clones_dir / sample_set.set_id, ignore_errors=True)
    save_sample_set(sample_set)

    response = client.post(
        f"/api/creator-clone/sets/{sample_set.set_id}/workflow",
        json={"action": WorkflowAction.SELECT_SAMPLES.value, "selected_sample_ids": ["missing_sample"]},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "AWEME_ID_NOT_FOUND"
    reloaded = client.get(f"/api/creator-clone/sets/{sample_set.set_id}").json()
    assert reloaded["set"]["selected_sample_ids"] == []
    shutil.rmtree(settings.creator_clones_dir / sample_set.set_id, ignore_errors=True)


def test_creator_clone_legacy_workflow_endpoint_advances_distillation_state() -> None:
    sample_set = sample_set_for_v2()
    shutil.rmtree(settings.creator_clones_dir / sample_set.set_id, ignore_errors=True)
    save_sample_set(sample_set)

    response = client.post(
        f"/api/creator-clone/sets/{sample_set.set_id}/workflow",
        json={"action": WorkflowAction.START_DISTILLATION.value},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["set"]["set_id"] == sample_set.set_id
    assert payload["creator_intelligence"]["workflow"]["state"] == WorkflowState.DISTILLING
    assert payload["creator_intelligence"]["workflow"]["has_behavior_model"] is True
    assert payload["creator_intelligence"]["behavior_model"]["selected_count"] == 1
    shutil.rmtree(settings.creator_clones_dir / sample_set.set_id, ignore_errors=True)


def test_creator_intelligence_project_api_exposes_v2_contract() -> None:
    sample_set = sample_set_for_v2()
    shutil.rmtree(settings.creator_clones_dir / sample_set.set_id, ignore_errors=True)
    save_sample_set(sample_set)

    response = client.get(f"/api/creator-intelligence/projects/{sample_set.set_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["project"]["project_id"] == sample_set.set_id
    assert payload["project"]["profile"]["display_name"] == "测试创作者"
    assert payload["workflow"]["state"] == WorkflowState.EVIDENCE_READY
    assert payload["behavior_model"]["project_id"] == sample_set.set_id
    assert "set" not in payload
    shutil.rmtree(settings.creator_clones_dir / sample_set.set_id, ignore_errors=True)


def test_cookie_runtime_settings_do_not_change_creator_workflow(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.services.runtime_settings.LOCAL_SETTINGS_PATH", tmp_path / "local_settings.json")
    sample_set = sample_set_for_v2()
    shutil.rmtree(settings.creator_clones_dir / sample_set.set_id, ignore_errors=True)
    save_sample_set(sample_set)

    before = client.get(f"/api/creator-intelligence/projects/{sample_set.set_id}").json()["workflow"]
    response = client.put(
        "/api/settings/data-sources/douyin",
        json={
            "douyin_cookie": "Cookie: sessionid=workflow-secret; sid_guard=guard; uid_tt=uid; sid_tt=sid",
            "user_agent": "Workflow Test UA",
            "referer": "https://www.douyin.com/",
        },
    )
    after = client.get(f"/api/creator-intelligence/projects/{sample_set.set_id}").json()["workflow"]

    assert response.status_code == 200
    assert response.json()["data_sources"]["has_cookie"] is True
    assert "workflow-secret" not in json.dumps(response.json(), ensure_ascii=False)
    assert before["state"] == after["state"] == WorkflowState.EVIDENCE_READY
    assert before["next_action"] == after["next_action"]
    shutil.rmtree(settings.creator_clones_dir / sample_set.set_id, ignore_errors=True)


def test_creator_intelligence_workflow_api_dispatches_selection() -> None:
    sample_set = sample_set_for_v2()
    sample_set.selected_sample_ids = []
    for sample in sample_set.samples:
        sample.selected = False
    shutil.rmtree(settings.creator_clones_dir / sample_set.set_id, ignore_errors=True)
    save_sample_set(sample_set)

    response = client.post(
        f"/api/creator-intelligence/projects/{sample_set.set_id}/workflow",
        json={"action": WorkflowAction.SELECT_SAMPLES.value, "selected_sample_ids": ["sample_ready"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project"]["selected_sample_ids"] == ["sample_ready"]
    assert payload["workflow"]["state"] == WorkflowState.EVIDENCE_READY
    assert payload["behavior_model"]["selected_count"] == 1

    reloaded = client.get(f"/api/creator-intelligence/projects/{sample_set.set_id}").json()
    assert reloaded["project"]["selected_sample_ids"] == ["sample_ready"]
    shutil.rmtree(settings.creator_clones_dir / sample_set.set_id, ignore_errors=True)


def test_creator_intelligence_workflow_api_advances_evidence_and_distillation_state() -> None:
    sample_set = sample_set_for_v2()
    shutil.rmtree(settings.creator_clones_dir / sample_set.set_id, ignore_errors=True)
    save_sample_set(sample_set)

    evidence_response = client.post(
        f"/api/creator-intelligence/projects/{sample_set.set_id}/workflow",
        json={"action": WorkflowAction.MARK_EVIDENCE_READY.value},
    )

    assert evidence_response.status_code == 200
    evidence_payload = evidence_response.json()
    assert evidence_payload["workflow"]["state"] == WorkflowState.EVIDENCE_READY
    assert evidence_payload["workflow"]["has_behavior_model"] is True
    assert evidence_payload["behavior_model"]["selected_count"] == 1

    distill_response = client.post(
        f"/api/creator-intelligence/projects/{sample_set.set_id}/workflow",
        json={"action": WorkflowAction.START_DISTILLATION.value},
    )

    assert distill_response.status_code == 200
    distill_payload = distill_response.json()
    assert distill_payload["workflow"]["state"] == WorkflowState.DISTILLING
    assert distill_payload["workflow"]["has_behavior_model"] is True
    assert distill_payload["behavior_model"]["selected_count"] == 1
    shutil.rmtree(settings.creator_clones_dir / sample_set.set_id, ignore_errors=True)


def test_creator_clone_result_exposes_structured_strategy_contract() -> None:
    sample_set = sample_set_for_v2()
    raw = {
        "summary": "视觉吸引账号规律。",
        "creator_positioning": {
            "what_the_creator_sells": "甜美 COS 视觉吸引",
            "audience_promise": "快速看到妆造和人物状态",
            "hidden_genre": "美拍氛围",
        },
        "topic_buckets": [{"name": "近景妆造", "why_it_works": "第一眼抓停留"}],
        "expression_patterns": {"opening_hooks": ["0-1 秒直接给脸和眼神"]},
        "transferable_formulas": [{"name": "近景眼神钩子", "beat_structure": ["脸", "动作", "标题"]}],
        "creator_clone_spec": {
            "anti_patterns": ["不要照搬擦边表达"],
            "self_check_rubric": ["第一眼是否有人物亮点"],
        },
        "candidate_ideas": [{"title": "粉色妆造回头杀", "formula_used": "近景眼神钩子"}],
    }

    normalized = normalize_creator_clone_result(raw, sample_set, [sample_set.samples[0]])
    strategy = normalized["creator_clone_strategy"]

    assert strategy == {
        "positioning": "甜美 COS 视觉吸引；快速看到妆造和人物状态；美拍氛围",
        "content_strategy": ["近景妆造", "近景眼神钩子"],
        "hooks": ["0-1 秒直接给脸和眼神"],
        "templates": [{"name": "近景眼神钩子", "beat_structure": ["脸", "动作", "标题"]}],
        "anti_patterns": ["不要照搬擦边表达"],
        "idea_bank": [{"title": "粉色妆造回头杀", "formula_used": "近景眼神钩子"}],
        "validation_rules": ["第一眼是否有人物亮点"],
    }


def test_creator_clone_schema_validation_is_deterministic() -> None:
    validated = validate_creator_clone_schema(
        {
            "positioning": "稳定审美",
            "content_strategy": "近景视觉",
            "hooks": ["第一眼给脸"],
            "templates": ["三拍公式"],
            "anti_patterns": None,
            "idea_bank": [{"title": "粉色回头杀"}, "日常眼神杀"],
            "validation_rules": ["是否有第一眼吸引"],
            "extra": "ignored",
        }
    )

    assert set(validated) == set(CreatorCloneStrategy.empty_schema())
    assert validated["content_strategy"] == ["近景视觉"]
    assert validated["templates"] == [{"text": "三拍公式"}]
    assert validated["anti_patterns"] == []
    assert validated["idea_bank"] == [{"title": "粉色回头杀"}, {"text": "日常眼神杀"}]


def test_creator_intelligence_v2_doc_tracks_completion_evidence() -> None:
    doc = Path("docs/creator-intelligence-v2.md").read_text(encoding="utf-8")

    assert "## Current Completion Evidence" in doc
    assert "Workflow Engine As Single State Contract" in doc
    assert "Unified Creator Project Model" in doc
    assert "Cognitive Modeling Layer" in doc
    assert "Structured Generation Contract" in doc
    assert "State-Driven Frontend Wizard" in doc
    assert "Async Job Contract Alignment" in doc
    assert "Compatibility Boundary" in doc
    assert "dispatch_creator_workflow" in doc
    assert "profile-build-cases" in doc
    assert "prompt-only recovery" in doc
    assert "Retire remaining legacy frontend names" in doc
