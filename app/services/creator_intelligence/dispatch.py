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
from app.services.creator_intelligence.workflow import WorkflowAction, WorkflowEngine


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
) -> CreatorWorkflowDispatchResult:
    workflow_action = WorkflowAction(action)
    sample_set = load_sample_set(set_id)
    engine = WorkflowEngine.from_project(project_from_clone_sample_set(sample_set))

    if workflow_action == WorkflowAction.SELECT_SAMPLES:
        selected = normalize_sample_set_selected_ids(sample_set, selected_sample_ids or [])
        engine.dispatch(workflow_action, {"selected_sample_ids": selected})
        sample_set = update_sample_set_selection(set_id, selected)
        return CreatorWorkflowDispatchResult(
            sample_set=sample_set,
            creator_intelligence=creator_intelligence_payload_for_sample_set(sample_set),
        )

    if workflow_action in {WorkflowAction.MARK_EVIDENCE_READY, WorkflowAction.START_DISTILLATION}:
        workflow = engine.dispatch(workflow_action).to_dict()
        intelligence = creator_intelligence_payload_for_sample_set(sample_set)
        intelligence["workflow"] = workflow
        if engine.behavior_model:
            intelligence["behavior_model"] = engine.behavior_model.to_dict()
        return CreatorWorkflowDispatchResult(sample_set=sample_set, creator_intelligence=intelligence)

    raise AppError(
        ErrorCode.PROFILE_SCAN_FAILED,
        f"当前 workflow action 暂不支持持久化：{workflow_action.value}。",
    )
