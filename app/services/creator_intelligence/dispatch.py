from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.creator_intelligence.runtime import CreatorRuntimeEngine
from app.services.creator_intelligence.workflow import WorkflowAction


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
    result = CreatorRuntimeEngine.dispatch_sample_set(
        set_id,
        workflow_action,
        selected_sample_ids=selected_sample_ids,
        strategy_output=strategy_output,
    )
    return CreatorWorkflowDispatchResult(
        sample_set=result.sample_set,
        creator_intelligence=result.creator_intelligence,
    )
