from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.errors import AppError, ErrorCode
from app.services.creator_clone import (
    creator_intelligence_payload_for_sample_set,
    load_sample_set,
    normalize_sample_set_selected_ids,
    update_sample_set_selection,
)
from app.services.creator_intelligence.adapters import project_from_clone_sample_set
from app.services.creator_intelligence.memory import CreatorMemoryGraph
from app.services.creator_intelligence.workflow import WorkflowAction, WorkflowEngine


def _persist_engine(engine: WorkflowEngine, action: WorkflowAction, payload: dict[str, Any] | None = None) -> None:
    session = engine.persist_state(
        engine.project.project_id,
        action=action,
        action_payload=payload or {},
        debug={"source": "dispatch_creator_workflow"},
    )
    CreatorMemoryGraph().record_session(session)


@dataclass(frozen=True)
class CreatorWorkflowDispatchResult:
    sample_set: Any
    creator_intelligence: dict[str, Any]

    @property
    def workflow(self) -> dict[str, Any]:
        workflow = self.creator_intelligence.get("workflow")
        return workflow if isinstance(workflow, dict) else {}

    @property
    def behavior_model(self) -> dict[str, Any] | None:
        behavior = self.creator_intelligence.get("behavior_model")
        return behavior if isinstance(behavior, dict) else None

    @property
    def strategy_output(self) -> dict[str, Any] | None:
        strategy = self.creator_intelligence.get("strategy_output")
        return strategy if isinstance(strategy, dict) else None


def dispatch_creator_workflow(
    set_id: str,
    action: WorkflowAction | str,
    *,
    selected_sample_ids: list[str] | None = None,
    strategy_output: dict[str, Any] | None = None,
) -> CreatorWorkflowDispatchResult:
    workflow_action = WorkflowAction(action)
    sample_set = load_sample_set(set_id)
    engine = WorkflowEngine.from_project(project_from_clone_sample_set(sample_set))

    if workflow_action == WorkflowAction.SELECT_SAMPLES:
        selected = normalize_sample_set_selected_ids(sample_set, selected_sample_ids or [])
        engine.dispatch(workflow_action, {"selected_sample_ids": selected})
        sample_set = update_sample_set_selection(set_id, selected)
        persisted_engine = WorkflowEngine.from_project(project_from_clone_sample_set(sample_set))
        _persist_engine(persisted_engine, workflow_action, {"selected_sample_ids": selected})
        return CreatorWorkflowDispatchResult(
            sample_set=sample_set,
            creator_intelligence=creator_intelligence_payload_for_sample_set(sample_set),
        )

    if workflow_action == WorkflowAction.MARK_EVIDENCE_READY:
        workflow = engine.dispatch(workflow_action).to_dict()
        intelligence = creator_intelligence_payload_for_sample_set(sample_set)
        intelligence["workflow"] = workflow
        if engine.behavior_model:
            intelligence["behavior_model"] = engine.behavior_model.to_dict()
        _persist_engine(engine, workflow_action)
        return CreatorWorkflowDispatchResult(sample_set=sample_set, creator_intelligence=intelligence)

    if workflow_action == WorkflowAction.START_DISTILLATION:
        if engine.state.value == "SAMPLE_SELECTED":
            engine.dispatch(WorkflowAction.MARK_EVIDENCE_READY)
        workflow = engine.dispatch(workflow_action).to_dict()
        intelligence = creator_intelligence_payload_for_sample_set(sample_set)
        intelligence["workflow"] = workflow
        if engine.behavior_model:
            intelligence["behavior_model"] = engine.behavior_model.to_dict()
        _persist_engine(engine, workflow_action)
        return CreatorWorkflowDispatchResult(sample_set=sample_set, creator_intelligence=intelligence)

    if workflow_action == WorkflowAction.COMPLETE_DISTILLATION:
        if engine.state.value == "SAMPLE_SELECTED":
            engine.dispatch(WorkflowAction.MARK_EVIDENCE_READY)
        if engine.state.value != "DISTILLING":
            engine.dispatch(WorkflowAction.START_DISTILLATION)
        workflow = engine.dispatch(workflow_action, {"strategy_output": strategy_output or {}}).to_dict()
        intelligence = creator_intelligence_payload_for_sample_set(sample_set, strategy_output or {})
        intelligence["workflow"] = workflow
        if engine.behavior_model:
            intelligence["behavior_model"] = engine.behavior_model.to_dict()
        _persist_engine(engine, workflow_action, {"strategy_output": strategy_output or {}})
        return CreatorWorkflowDispatchResult(sample_set=sample_set, creator_intelligence=intelligence)

    raise AppError(
        ErrorCode.PROFILE_SCAN_FAILED,
        f"当前 workflow action 暂不支持持久化：{workflow_action.value}。",
    )
