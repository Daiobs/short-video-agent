from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from app.services.creator_intelligence.cognition import build_behavior_representation
from app.services.creator_intelligence.models import BehaviorRepresentation, CreatorProject


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowState(StrEnum):
    IMPORT = "IMPORT"
    INGESTED = "INGESTED"
    SAMPLE_READY = "SAMPLE_READY"
    SAMPLE_SELECTED = "SAMPLE_SELECTED"
    EVIDENCE_READY = "EVIDENCE_READY"
    DISTILLING = "DISTILLING"
    DONE = "DONE"


class WorkflowAction(StrEnum):
    INGEST = "INGEST"
    BUILD_SAMPLE_POOL = "BUILD_SAMPLE_POOL"
    SELECT_SAMPLES = "SELECT_SAMPLES"
    MARK_EVIDENCE_READY = "MARK_EVIDENCE_READY"
    START_DISTILLATION = "START_DISTILLATION"
    COMPLETE_DISTILLATION = "COMPLETE_DISTILLATION"
    RESET = "RESET"


@dataclass(frozen=True)
class WorkflowSnapshot:
    project_id: str
    state: WorkflowState = WorkflowState.IMPORT
    sample_count: int = 0
    selected_count: int = 0
    evidence_ready_count: int = 0
    has_behavior_model: bool = False
    has_strategy_output: bool = False
    message: str = ""
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "state": self.state.value,
            "sample_count": self.sample_count,
            "selected_count": self.selected_count,
            "evidence_ready_count": self.evidence_ready_count,
            "has_behavior_model": self.has_behavior_model,
            "has_strategy_output": self.has_strategy_output,
            "message": self.message,
            "updated_at": self.updated_at,
        }


@dataclass
class WorkflowEngine:
    project: CreatorProject
    state: WorkflowState = WorkflowState.IMPORT
    behavior_model: BehaviorRepresentation | None = None
    strategy_output: dict[str, Any] | None = None
    message: str = ""

    @classmethod
    def from_project(cls, project: CreatorProject) -> "WorkflowEngine":
        engine = cls(project=project)
        engine.state = engine.infer_state()
        return engine

    def get_state(self) -> WorkflowSnapshot:
        selected = self.project.selected_samples
        evidence_ready_count = sum(1 for sample in selected if sample.evidence.ready_for_distillation)
        return WorkflowSnapshot(
            project_id=self.project.project_id,
            state=self.state,
            sample_count=len(self.project.samples),
            selected_count=len(selected),
            evidence_ready_count=evidence_ready_count,
            has_behavior_model=self.behavior_model is not None,
            has_strategy_output=bool(self.strategy_output),
            message=self.message,
        )

    def dispatch(self, action: WorkflowAction | str, payload: dict[str, Any] | None = None) -> WorkflowSnapshot:
        action = WorkflowAction(action)
        payload = payload or {}
        if action == WorkflowAction.RESET:
            self.state = WorkflowState.IMPORT
            self.behavior_model = None
            self.strategy_output = None
            self.message = "Workflow reset."
            return self.get_state()
        self._transition(action, payload)
        return self.get_state()

    def infer_state(self) -> WorkflowState:
        if self.strategy_output:
            return WorkflowState.DONE
        selected = self.project.selected_samples
        if selected and all(sample.evidence.ready_for_distillation for sample in selected):
            return WorkflowState.EVIDENCE_READY
        if selected:
            return WorkflowState.SAMPLE_SELECTED
        if self.project.samples:
            return WorkflowState.SAMPLE_READY
        return WorkflowState.IMPORT

    def _transition(self, action: WorkflowAction, payload: dict[str, Any]) -> None:
        if action == WorkflowAction.INGEST:
            self._require({WorkflowState.IMPORT, WorkflowState.INGESTED}, action)
            self.state = WorkflowState.INGESTED
            self.message = "Input ingested."
            return
        if action == WorkflowAction.BUILD_SAMPLE_POOL:
            self._require({WorkflowState.IMPORT, WorkflowState.INGESTED, WorkflowState.SAMPLE_READY}, action)
            if not self.project.samples:
                raise ValueError("Cannot mark sample pool ready without samples.")
            self.state = WorkflowState.SAMPLE_READY
            self.message = "Sample pool ready."
            return
        if action == WorkflowAction.SELECT_SAMPLES:
            self._require({WorkflowState.SAMPLE_READY, WorkflowState.SAMPLE_SELECTED, WorkflowState.EVIDENCE_READY}, action)
            selected_ids = tuple(str(item) for item in (payload.get("selected_sample_ids") or []) if str(item))
            if not selected_ids:
                raise ValueError("SELECT_SAMPLES requires selected_sample_ids.")
            available_ids = {sample.sample_id for sample in self.project.samples}
            if not any(sample_id in available_ids for sample_id in selected_ids):
                raise ValueError("SELECT_SAMPLES did not match any project samples.")
            self.project = replace(self.project, selected_sample_ids=selected_ids, updated_at=_now())
            self.state = WorkflowState.SAMPLE_SELECTED
            self.behavior_model = None
            self.message = "Samples selected."
            return
        if action == WorkflowAction.MARK_EVIDENCE_READY:
            self._require({WorkflowState.SAMPLE_SELECTED, WorkflowState.EVIDENCE_READY}, action)
            selected = self.project.selected_samples
            if not selected:
                raise ValueError("Cannot mark evidence ready without selected samples.")
            self.behavior_model = build_behavior_representation(self.project)
            self.state = WorkflowState.EVIDENCE_READY
            self.message = "Evidence model ready."
            return
        if action == WorkflowAction.START_DISTILLATION:
            self._require({WorkflowState.EVIDENCE_READY, WorkflowState.DISTILLING}, action)
            self.behavior_model = self.behavior_model or build_behavior_representation(self.project)
            self.state = WorkflowState.DISTILLING
            self.message = "Distillation started."
            return
        if action == WorkflowAction.COMPLETE_DISTILLATION:
            self._require({WorkflowState.DISTILLING}, action)
            strategy = payload.get("strategy_output")
            if not isinstance(strategy, dict):
                raise ValueError("COMPLETE_DISTILLATION requires strategy_output.")
            self.strategy_output = strategy
            self.state = WorkflowState.DONE
            self.message = "Creator strategy output ready."
            return
        raise ValueError(f"Unsupported workflow action: {action}")

    def _require(self, states: set[WorkflowState], action: WorkflowAction) -> None:
        if self.state not in states:
            allowed = ", ".join(state.value for state in sorted(states, key=lambda item: item.value))
            raise ValueError(f"Cannot dispatch {action.value} from {self.state.value}; allowed states: {allowed}.")
