from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.creator_clone import CloneSample, CloneSampleSet
from app.services.creator_clone import save_sample_set
from app.services.creator_intelligence import (
    CreatorCloneStrategy,
    WorkflowAction,
    WorkflowEngine,
    WorkflowState,
    build_behavior_representation,
    project_from_clone_sample_set,
    project_from_clone_selection,
)

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
    assert project.profile.creator_id == "MS4wLjABAAAA_v2"
    assert project.profile.display_name == "测试创作者"
    assert project.profile.platform.value == "douyin"
    assert project.sample_count == 2
    assert project.selected_count == 1
    assert project.samples[0].metrics.engagement_score == 1340
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
    assert any("No ASR evidence" in item for item in behavior.constraints)


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
    assert engine.dispatch(WorkflowAction.INGEST).state == WorkflowState.INGESTED
    assert engine.dispatch(WorkflowAction.BUILD_SAMPLE_POOL).state == WorkflowState.SAMPLE_READY
    selected = engine.dispatch(WorkflowAction.SELECT_SAMPLES, {"selected_sample_ids": ["sample_ready"]})
    assert selected.state == WorkflowState.SAMPLE_SELECTED
    assert selected.selected_count == 1
    evidence = engine.dispatch(WorkflowAction.MARK_EVIDENCE_READY)
    assert evidence.state == WorkflowState.EVIDENCE_READY
    assert evidence.has_behavior_model is True
    assert engine.behavior_model is not None
    assert engine.dispatch(WorkflowAction.START_DISTILLATION).state == WorkflowState.DISTILLING
    done = engine.dispatch(
        WorkflowAction.COMPLETE_DISTILLATION,
        {"strategy_output": CreatorCloneStrategy(positioning="甜美 COS 视觉吸引").to_dict()},
    )
    assert done.state == WorkflowState.DONE
    assert done.has_strategy_output is True


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
    assert intelligence["workflow"]["state"] == WorkflowState.EVIDENCE_READY
    assert intelligence["workflow"]["selected_count"] == 1
    assert intelligence["behavior_model"]["project_id"] == sample_set.set_id
    assert intelligence["behavior_model"]["evidence_matrix"]["with_keyframes"] == 1
    shutil.rmtree(settings.creator_clones_dir / sample_set.set_id, ignore_errors=True)
