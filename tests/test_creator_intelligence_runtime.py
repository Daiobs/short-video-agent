from __future__ import annotations

from pathlib import Path

import pytest

from app.errors import AppError, ErrorCode
from app.services.creator_intelligence import (
    CreatorCloneStrategy,
    CreatorMemoryGraph,
    CreatorProfile,
    CreatorProject,
    CreatorSample,
    CreatorStateStore,
    Evidence,
    EvidenceLevel,
    LLMExecutionEngine,
    MediaKind,
    Platform,
    SampleMetrics,
    WorkflowAction,
    WorkflowEngine,
    WorkflowState,
    build_behavior_representation,
)


def runtime_project() -> CreatorProject:
    return CreatorProject(
        project_id="runtime_project",
        title="Runtime 测试创作者",
        profile=CreatorProfile(
            creator_id="creator_runtime",
            display_name="Runtime Creator",
            platform=Platform.DOUYIN,
            content_direction="美拍 COS",
        ),
        samples=(
            CreatorSample(
                sample_id="sample_a",
                source=Platform.DOUYIN,
                platform_item_id="7650000000000000001",
                title="粉色近景回头杀",
                media_kind=MediaKind.VIDEO,
                metrics=SampleMetrics(like_count=1000, comment_count=20, share_count=30),
                evidence=Evidence(level=EvidenceLevel.PARTIAL, has_video=True, has_frames=True, has_ocr=True),
            ),
            CreatorSample(
                sample_id="sample_b",
                source=Platform.DOUYIN,
                platform_item_id="7650000000000000002",
                title="甜妹眼神互动",
                media_kind=MediaKind.VIDEO,
                metrics=SampleMetrics(like_count=800, comment_count=12, share_count=10),
                evidence=Evidence(level=EvidenceLevel.PARTIAL, has_video=True, has_frames=True),
            ),
        ),
        selected_sample_ids=("sample_a", "sample_b"),
    )


def test_creator_state_store_restores_workflow_state(tmp_path: Path) -> None:
    store = CreatorStateStore(root=tmp_path)
    project = runtime_project()
    strategy = CreatorCloneStrategy(positioning="甜美 COS 近景视觉").to_dict()
    engine = WorkflowEngine.from_project(project)

    engine.dispatch(WorkflowAction.START_DISTILLATION)
    engine.persist_state("session_restore", store, action=WorkflowAction.START_DISTILLATION)
    engine.dispatch(WorkflowAction.COMPLETE_DISTILLATION, {"strategy_output": strategy})
    engine.persist_state("session_restore", store, action=WorkflowAction.COMPLETE_DISTILLATION, action_payload={"strategy_output": strategy})

    restored = WorkflowEngine.restore_state("session_restore", store)

    assert restored.state == WorkflowState.DONE
    assert restored.strategy_output == strategy
    assert restored.project.project_id == project.project_id
    assert restored.get_state().has_strategy_output is True


def test_workflow_replay_actions_reconstructs_distillation_path(tmp_path: Path) -> None:
    store = CreatorStateStore(root=tmp_path)
    project = runtime_project()
    strategy = CreatorCloneStrategy(positioning="甜美 COS 近景视觉").to_dict()
    engine = WorkflowEngine.from_project(project)

    engine.dispatch(WorkflowAction.START_DISTILLATION)
    engine.persist_state("session_replay", store, action=WorkflowAction.START_DISTILLATION)
    engine.dispatch(WorkflowAction.COMPLETE_DISTILLATION, {"strategy_output": strategy})
    engine.persist_state("session_replay", store, action=WorkflowAction.COMPLETE_DISTILLATION, action_payload={"strategy_output": strategy})

    replayed = WorkflowEngine.replay_actions("session_replay", store)

    assert [item["state"] for item in replayed] == [WorkflowState.DISTILLING, WorkflowState.DONE]


class FlakySchemaProvider:
    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, prompt: str, image_paths: list[Path]) -> dict:
        self.calls += 1
        if self.calls == 1:
            return {"summary": "缺少 creator_clone_strategy"}
        return {
            "summary": "已修复",
            "creator_clone_strategy": {
                "positioning": "甜美 COS 近景视觉",
                "content_strategy": "近景人设先行",
                "hooks": ["第一眼给脸和眼神"],
                "templates": ["近景三拍公式"],
                "anti_patterns": None,
                "idea_bank": [{"title": "粉色妆造回头杀"}],
                "validation_rules": ["0-1 秒是否有人物亮点"],
            },
        }


def test_llm_execution_engine_retries_and_validates_creator_clone_schema() -> None:
    provider = FlakySchemaProvider()
    result = LLMExecutionEngine(provider).execute_creator_clone("prompt", [])

    assert provider.calls == 2
    assert result.attempts == 2
    assert result.repaired is True
    assert result.strategy == {
        "positioning": "甜美 COS 近景视觉",
        "content_strategy": ["近景人设先行"],
        "hooks": ["第一眼给脸和眼神"],
        "templates": [{"text": "近景三拍公式"}],
        "anti_patterns": [],
        "idea_bank": [{"title": "粉色妆造回头杀"}],
        "validation_rules": ["0-1 秒是否有人物亮点"],
    }
    assert result.to_dict()["creator_clone_strategy"] == result.strategy


class AlwaysInvalidProvider:
    def analyze(self, prompt: str, image_paths: list[Path]) -> dict:
        return {"summary": "still invalid"}


def test_llm_execution_engine_fails_after_retry_budget() -> None:
    with pytest.raises(AppError) as error:
        LLMExecutionEngine(AlwaysInvalidProvider(), max_retries=2).execute_creator_clone("prompt", [])

    assert error.value.code == ErrorCode.LLM_RESPONSE_INVALID


def test_creator_memory_graph_persists_patterns_and_evolution(tmp_path: Path) -> None:
    project = runtime_project()
    behavior = build_behavior_representation(project)
    strategy = CreatorCloneStrategy(
        positioning="甜美 COS 近景视觉",
        hooks=("第一眼给脸",),
        templates=({"name": "近景三拍公式"},),
        anti_patterns=("不要照搬擦边表达",),
    ).to_dict()
    graph = CreatorMemoryGraph(root=tmp_path)

    graph.record_project(project, behavior_model=behavior, strategy_output=strategy, session_id="session_memory")
    reloaded = CreatorMemoryGraph(root=tmp_path)
    evolution = reloaded.creator_evolution(project.profile.creator_id)

    assert evolution["sample_set_count"] == 1
    assert evolution["distill_count"] == 1
    assert "第一眼给脸" in evolution["reusable_patterns"]["hook_patterns"]
    assert "不要照搬擦边表达" in evolution["reusable_patterns"]["anti_patterns"]
    assert reloaded.distillation_prompt_context(project.profile.creator_id)["historical_distill_count"] == 1


def test_cognition_outputs_runtime_evolution_signals() -> None:
    behavior = build_behavior_representation(runtime_project()).to_dict()

    assert behavior["behavior_patterns"]["dominant_media"] == "video"
    assert behavior["hook_patterns"]["hook_evidence"] == "frames_or_text"
    assert behavior["structure_patterns"]["media_mix"] == {"video": 2}
    assert behavior["anti_patterns"]["low_confidence"] is False
    assert behavior["evolution_signals"]["creator_id"] == "creator_runtime"
    assert behavior["evolution_signals"]["selected_count"] == 2


def test_pipeline_debug_trace_is_persisted_with_workflow_state(tmp_path: Path) -> None:
    store = CreatorStateStore(root=tmp_path)
    engine = WorkflowEngine.from_project(runtime_project())

    engine.dispatch(WorkflowAction.START_DISTILLATION)
    session = engine.persist_state(
        "session_trace",
        store,
        action=WorkflowAction.START_DISTILLATION,
        debug={"job_id": "job_1", "stage": "distill"},
    )

    loaded = store.load_session("session_trace")
    assert loaded is not None
    assert loaded.workflow_state["state"] == WorkflowState.DISTILLING
    assert loaded.debug_trace[-1]["event"] == {"job_id": "job_1", "stage": "distill"}
    assert session.debug_trace[-1]["event"]["stage"] == "distill"
