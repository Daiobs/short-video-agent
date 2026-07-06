from __future__ import annotations

from pathlib import Path

import pytest

from app.errors import AppError, ErrorCode
from app.services.creator_intelligence import (
    CreatorCloneStrategy,
    CreatorMemoryGraph,
    CreatorProfile,
    CreatorProject,
    CreatorRuntimeEngine,
    CreatorRuntimeState,
    CreatorSample,
    CreatorStateStore,
    Evidence,
    EvidenceLevel,
    ExecutionLayer,
    LLMExecutionEngine,
    MediaKind,
    Platform,
    SampleMetrics,
    WorkflowAction,
    WorkflowEngine,
    WorkflowState,
    build_behavior_representation,
)
from app.services.creator_intelligence.report_quality import validate_creator_report_quality


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
    assert not hasattr(restored, "strategy_output")
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


def test_runtime_engine_is_unique_state_source_and_persists_runtime_state(tmp_path: Path) -> None:
    store = CreatorStateStore(root=tmp_path)
    engine = CreatorRuntimeEngine.from_project(runtime_project(), store=store, session_id="runtime_unique")

    state = engine.dispatch(WorkflowAction.START_DISTILLATION, persist=True, debug={"job_id": "job_runtime"})

    assert isinstance(state, CreatorRuntimeState)
    assert state.workflow_dict()["state"] == WorkflowState.DISTILLING
    assert state.current_step()["stage"] == "distill"
    assert state.primary_action()["command"] == "wait"
    loaded = store.load_session("runtime_unique")
    assert loaded is not None
    assert loaded.runtime_state["current_step"]["stage"] == "distill"
    assert loaded.runtime_state["primary_action"]["command"] == "wait"


def test_runtime_engine_restores_and_replays_pipeline(tmp_path: Path) -> None:
    store = CreatorStateStore(root=tmp_path)
    strategy = CreatorCloneStrategy(positioning="甜美 COS 近景视觉").to_dict()
    engine = CreatorRuntimeEngine.from_project(runtime_project(), store=store, session_id="runtime_replay")

    engine.dispatch(WorkflowAction.START_DISTILLATION, persist=True)
    engine.dispatch(WorkflowAction.COMPLETE_DISTILLATION, {"strategy_output": strategy}, persist=True)

    restored = CreatorRuntimeEngine.restore_state("runtime_replay", store)
    replayed = CreatorRuntimeEngine.replay_actions("runtime_replay", store)

    assert restored.state.workflow_dict()["state"] == WorkflowState.DONE
    assert restored.state.strategy_output == strategy
    assert [item["state"] for item in replayed] == [WorkflowState.DISTILLING, WorkflowState.DONE]
    assert replayed[-1]["primary_action"]["command"] == "export_report"


def test_execution_layer_outputs_stable_behavior_and_schema() -> None:
    layer = ExecutionLayer()
    behavior = layer.extract_behavior_model(runtime_project()).to_dict()
    strategy = layer.validate_strategy_output(
        {
            "positioning": "甜美 COS 近景视觉",
            "content_strategy": "近景人设先行",
            "hooks": ["第一眼给脸和眼神"],
            "templates": ["近景三拍公式"],
            "anti_patterns": None,
            "idea_bank": [{"title": "粉色妆造回头杀"}],
            "validation_rules": ["第一秒是否有人物亮点"],
        }
    )

    assert behavior["project_id"] == "runtime_project"
    assert behavior["selected_count"] == 2
    assert behavior["evidence_matrix"]["with_keyframes"] == 2
    assert strategy == {
        "positioning": "甜美 COS 近景视觉",
        "content_strategy": ["近景人设先行"],
        "hooks": ["第一眼给脸和眼神"],
        "templates": [{"text": "近景三拍公式"}],
        "anti_patterns": [],
        "idea_bank": [{"title": "粉色妆造回头杀"}],
        "validation_rules": ["第一秒是否有人物亮点"],
    }


def test_ui_renderer_no_longer_contains_legacy_wizard_state_calculation() -> None:
    script = Path("app/static/app.js").read_text(encoding="utf-8")

    assert "function getWizardStep" not in script
    assert "function getCreatorCloneWizardState" not in script
    assert "function getCreatorCloneStage" not in script
    assert "function workflowNextCommand" not in script
    assert "wizardStateFromWorkflowState" not in script
    assert "currentCreatorRuntimeState" in script
    assert "function creatorRuntimeCurrentStep" in script
    assert "function creatorRuntimePrimaryAction" in script
    assert "runtime_state" in script


def test_frontend_primary_button_uses_current_view_action_without_losing_runtime_progress() -> None:
    script = Path("app/static/app.js").read_text(encoding="utf-8")
    view_start = script.index("function creatorCloneViewMetaForStage")
    view_end = script.index("function creatorCloneStageMeta", view_start)
    view_meta_body = script[view_start:view_end]
    start = script.index("function creatorCloneStageMeta")
    end = script.index("function creatorCloneStateMeta", start)
    stage_meta_body = script[start:end]

    assert "return creatorCloneViewMetaForStage(stage);" in stage_meta_body
    assert "creatorRuntimeMetaFromState()" in view_meta_body
    assert 'normalizedStage === "export"' in view_meta_body
    assert 'command: "show_select"' in view_meta_body
    assert 'command: "build_evidence"' in view_meta_body
    assert 'command: "show_distill"' in view_meta_body
    assert 'command: "export_report"' in view_meta_body
    assert "selectedCreatorSampleViewItems" in view_meta_body
    assert "hasPendingEnrichment" in view_meta_body
    assert "CREATOR_CLONE_MAX_DISTILL_SAMPLES" not in view_meta_body


def test_report_quality_validator_flags_empty_and_weak_reports() -> None:
    empty = validate_creator_report_quality({}, evidence_summary={"selected_count": 3, "evidence_ready_count": 0, "with_keyframes": 0}).to_dict()
    weak = validate_creator_report_quality(
        {
            "positioning": "甜美 COS 近景视觉",
            "content_strategy": ["近景人设先行"],
            "hooks": ["第一眼给脸"],
            "templates": [],
            "anti_patterns": [],
            "idea_bank": [],
            "validation_rules": ["第一秒必须有人物亮点"],
        },
        evidence_summary={"selected_count": 3, "evidence_ready_count": 1, "with_keyframes": 1, "with_asr": 0, "with_ocr": 0},
    ).to_dict()

    assert empty["ok"] is False
    assert set(empty["missing_fields"]) == {
        "positioning",
        "content_strategy",
        "hooks",
        "templates",
        "anti_patterns",
        "idea_bank",
        "validation_rules",
    }
    assert empty["evidence_warnings"]
    assert weak["ok"] is False
    assert "templates" in weak["missing_fields"]
    assert "content_strategy" in weak["weak_fields"]
    assert weak["evidence_warnings"]


def test_report_quality_validator_scores_empty_template_and_strong_reports() -> None:
    empty = validate_creator_report_quality(
        {},
        evidence_summary={"selected_count": 3, "evidence_ready_count": 0, "with_keyframes": 0},
    ).to_dict()
    template_like = validate_creator_report_quality(
        {
            "positioning": "账号定位稳定",
            "content_strategy": ["持续输出垂直内容"],
            "hooks": ["用强钩子开头"],
            "templates": [{"name": "通用模板", "beat_structure": ["开头", "中段", "结尾"]}],
            "anti_patterns": ["避免跑题"],
            "idea_bank": [{"title": "新选题"}],
            "validation_rules": ["检查内容是否垂直"],
        },
        evidence_summary={"selected_count": 3, "evidence_ready_count": 3, "with_keyframes": 3, "with_asr": 1, "with_ocr": 1},
    ).to_dict()
    strong = validate_creator_report_quality(
        {
            "positioning": "粉色少御 COS 近景视觉，用首帧人物眼神和妆造承诺抓停留。",
            "content_strategy": [
                {
                    "text": "保留高赞样本的 0-1 秒近景给脸，再替换成新服装和新背景测试。",
                    "sample_id": "sample_a",
                    "title": "粉色近景回头杀",
                    "metric": "like_count",
                    "metric_value": 120000,
                    "evidence_level": "partial",
                },
                "标题写人物气质 + 场景承诺，封面首帧直接展示眼神和姿态，脚本文案用一句反差描述承接动作。",
            ],
            "hooks": ["开头 1 秒给人物脸、眼神、手势动作，标题补充反差。"],
            "templates": [
                {
                    "name": "近景眼神钩子",
                    "when_to_use": "新妆造或新角色上线时使用",
                    "beat_structure": ["首帧给脸", "手势动作", "标题承诺", "评论验证"],
                    "sample_id": "sample_a",
                    "title": "粉色近景回头杀",
                    "metric": "like_count",
                    "evidence_level": "partial",
                },
                {
                    "name": "服化反差钩子",
                    "beat_structure": ["封面展示服装", "镜头拉近", "动作变化", "话题标签"],
                },
            ],
            "anti_patterns": ["不要只复制擦边姿势，要保留安全人设和妆造统一。"],
            "idea_bank": [
                {
                    "title": "新粉色妆造回头杀",
                    "formula_used": "近景眼神钩子",
                    "why_worth_trying": "复用高赞首帧吸引",
                    "production_requirements": "准备近景镜头、封面图、标题 A/B 测试。",
                },
                {"title": "冷感服装三动作测试", "production_requirements": "同场景拍 3 个动作并比较评论。"},
            ],
            "validation_rules": ["发布前检查首帧人物是否清晰，标题是否有点击理由，脚本文案是否承接动作，封面是否能单独成立。"],
        },
        evidence_summary={"selected_count": 3, "evidence_ready_count": 3, "with_keyframes": 3, "with_asr": 1, "with_ocr": 1},
    ).to_dict()

    assert empty["ok"] is False
    assert empty["quality_score"] < template_like["quality_score"] < strong["quality_score"]
    assert template_like["missing_evidence"]
    assert template_like["checks"]["has_sample_evidence"] is False
    assert strong["ok"] is True
    assert strong["missing_evidence"] == []
    assert strong["checks"]["has_action_verbs"] is True
    assert strong["checks"]["has_sample_evidence"] is True
    assert strong["checks"]["has_executable_ideas"] is True
    assert strong["checks"]["has_shooting_advice"] is True
    assert strong["checks"]["has_title_advice"] is True
