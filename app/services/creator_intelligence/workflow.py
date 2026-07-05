from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from app.services.creator_intelligence.models import CreatorProject

DIRECT_DISTILL_LIMIT = 20


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
class WorkflowIntent:
    """Pure Control -> Execution protocol.

    The workflow engine only declares the next intended action. It never
    extracts evidence, builds behavior models, calls LLMs, or renders UI copy.
    """

    action: str
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_action(cls, action: WorkflowAction | str, payload: dict[str, Any] | None = None) -> "WorkflowIntent":
        value = action.value if isinstance(action, WorkflowAction) else str(action)
        return cls(action=value, payload=dict(payload or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class WorkflowSnapshot:
    project_id: str
    state: WorkflowState = WorkflowState.IMPORT
    sample_count: int = 0
    selected_count: int = 0
    evidence_ready_count: int = 0
    has_behavior_model: bool = False
    has_strategy_output: bool = False
    allowed_actions: tuple[str, ...] = ()
    next_intent: WorkflowIntent | None = None
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
            "allowed_actions": list(self.allowed_actions),
            "next_intent": self.next_intent.to_dict() if self.next_intent else None,
            "message": self.message,
            "updated_at": self.updated_at,
        }


@dataclass
class WorkflowEngine:
    """Creator Intelligence Control Plane.

    This engine is intentionally side-effect free. It validates transitions and
    exposes intent; the runtime/execution layer performs all computation.
    """

    project: CreatorProject
    state: WorkflowState = WorkflowState.IMPORT
    has_behavior_model: bool = False
    has_strategy_output: bool = False
    message: str = ""

    @classmethod
    def from_project(
        cls,
        project: CreatorProject,
        strategy_output: dict[str, Any] | None = None,
        *,
        behavior_model: dict[str, Any] | None = None,
    ) -> "WorkflowEngine":
        engine = cls(
            project=project,
            has_behavior_model=bool(behavior_model),
            has_strategy_output=bool(strategy_output),
        )
        engine.state = engine.infer_state()
        if engine.has_strategy_output:
            engine.message = "Creator strategy output ready."
        return engine

    @classmethod
    def restore_state(cls, session_id: str, store=None) -> "WorkflowEngine":
        store = store or _default_state_store()
        session = store.load_session(session_id)
        if not session:
            raise ValueError(f"Creator session not found: {session_id}")
        engine = cls.from_project(
            session.project,
            strategy_output=session.strategy_output or None,
            behavior_model=session.behavior_model or None,
        )
        saved_state = session.workflow_state.get("state")
        if saved_state:
            engine.state = WorkflowState(saved_state)
        engine.has_behavior_model = bool(session.workflow_state.get("has_behavior_model") or session.behavior_model)
        engine.has_strategy_output = bool(session.workflow_state.get("has_strategy_output") or session.strategy_output)
        engine.message = str(session.workflow_state.get("message") or engine.message)
        return engine

    @classmethod
    def replay_actions(cls, session_id: str, store=None) -> list[dict[str, Any]]:
        store = store or _default_state_store()
        return store.replay_actions(session_id)

    def persist_state(
        self,
        session_id: str,
        store=None,
        *,
        action: WorkflowAction | str | None = None,
        action_payload: dict[str, Any] | None = None,
        runtime_state: dict[str, Any] | None = None,
        behavior_model: dict[str, Any] | None = None,
        strategy_output: dict[str, Any] | None = None,
        debug: dict[str, Any] | None = None,
    ):
        store = store or _default_state_store()
        return store.persist_workflow_state(
            session_id,
            self.project,
            self.get_state().to_dict(),
            runtime_state=runtime_state or {},
            behavior_model=behavior_model or {},
            strategy_output=strategy_output or {},
            action=str(action.value if isinstance(action, WorkflowAction) else action or ""),
            action_payload=action_payload or {},
            debug=debug or {},
        )

    def get_state(self) -> WorkflowSnapshot:
        selected = self.project.selected_samples
        evidence_ready_count = sum(1 for sample in selected if sample.evidence.ready_for_distillation)
        sample_count = len(self.project.samples)
        selected_count = len(selected)
        return WorkflowSnapshot(
            project_id=self.project.project_id,
            state=self.state,
            sample_count=sample_count,
            selected_count=selected_count,
            evidence_ready_count=evidence_ready_count,
            has_behavior_model=self.has_behavior_model,
            has_strategy_output=self.has_strategy_output,
            allowed_actions=self.allowed_actions(),
            next_intent=self.next_intent(
                sample_count=sample_count,
                selected_count=selected_count,
                evidence_ready_count=evidence_ready_count,
            ),
            message=self.message,
        )

    def allowed_actions(self) -> tuple[str, ...]:
        actions: set[WorkflowAction] = {WorkflowAction.RESET}
        if self.state == WorkflowState.IMPORT:
            actions.add(WorkflowAction.INGEST)
            if self.project.samples:
                actions.add(WorkflowAction.BUILD_SAMPLE_POOL)
        elif self.state == WorkflowState.INGESTED:
            actions.add(WorkflowAction.BUILD_SAMPLE_POOL)
        elif self.state == WorkflowState.SAMPLE_READY:
            actions.add(WorkflowAction.SELECT_SAMPLES)
        elif self.state == WorkflowState.SAMPLE_SELECTED:
            actions.update({WorkflowAction.SELECT_SAMPLES, WorkflowAction.MARK_EVIDENCE_READY})
            if self.project.selected_samples and not self._selected_has_pending_evidence():
                actions.add(WorkflowAction.START_DISTILLATION)
        elif self.state == WorkflowState.EVIDENCE_READY:
            actions.update({WorkflowAction.SELECT_SAMPLES, WorkflowAction.START_DISTILLATION})
        elif self.state == WorkflowState.DISTILLING:
            actions.add(WorkflowAction.COMPLETE_DISTILLATION)
        elif self.state == WorkflowState.DONE:
            actions.add(WorkflowAction.SELECT_SAMPLES)
            if self.project.selected_samples:
                actions.update({WorkflowAction.MARK_EVIDENCE_READY, WorkflowAction.START_DISTILLATION})
        return tuple(action.value for action in sorted(actions, key=lambda item: item.value))

    def next_intent(
        self,
        *,
        sample_count: int | None = None,
        selected_count: int | None = None,
        evidence_ready_count: int | None = None,
    ) -> WorkflowIntent | None:
        sample_count = self.project.sample_count if sample_count is None else sample_count
        selected_count = self.project.selected_count if selected_count is None else selected_count
        evidence_ready_count = 0 if evidence_ready_count is None else evidence_ready_count
        if self.state == WorkflowState.IMPORT:
            return WorkflowIntent.from_action(WorkflowAction.INGEST)
        if self.state == WorkflowState.INGESTED:
            return WorkflowIntent.from_action(WorkflowAction.BUILD_SAMPLE_POOL)
        if self.state == WorkflowState.SAMPLE_READY:
            return WorkflowIntent.from_action(WorkflowAction.SELECT_SAMPLES, {"sample_count": sample_count})
        if self.state == WorkflowState.SAMPLE_SELECTED:
            pending = max(0, selected_count - evidence_ready_count)
            if pending:
                return WorkflowIntent.from_action(WorkflowAction.MARK_EVIDENCE_READY, {"pending_count": pending})
            return WorkflowIntent.from_action(self._distill_intent_action(selected_count), self._distill_intent_payload(selected_count))
        if self.state == WorkflowState.EVIDENCE_READY:
            if not selected_count:
                return WorkflowIntent.from_action(WorkflowAction.SELECT_SAMPLES)
            return WorkflowIntent.from_action(self._distill_intent_action(selected_count), self._distill_intent_payload(selected_count))
        if self.state == WorkflowState.DISTILLING:
            return WorkflowIntent.from_action(WorkflowAction.COMPLETE_DISTILLATION)
        return None

    def dispatch(self, action: WorkflowAction | str, payload: dict[str, Any] | None = None) -> WorkflowSnapshot:
        action = WorkflowAction(action)
        payload = payload or {}
        if action == WorkflowAction.RESET:
            self.state = WorkflowState.IMPORT
            self.has_behavior_model = False
            self.has_strategy_output = False
            self.message = "Workflow reset."
            return self.get_state()
        self._transition(action, payload)
        return self.get_state()

    def infer_state(self) -> WorkflowState:
        if self.has_strategy_output:
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
            self._require(
                {WorkflowState.SAMPLE_READY, WorkflowState.SAMPLE_SELECTED, WorkflowState.EVIDENCE_READY, WorkflowState.DONE},
                action,
            )
            selected_ids = tuple(str(item) for item in (payload.get("selected_sample_ids") or []) if str(item))
            if not selected_ids:
                raise ValueError("SELECT_SAMPLES requires selected_sample_ids.")
            available_ids = {sample.sample_id for sample in self.project.samples}
            if not any(sample_id in available_ids for sample_id in selected_ids):
                raise ValueError("SELECT_SAMPLES did not match any project samples.")
            self.project = replace(self.project, selected_sample_ids=selected_ids, updated_at=_now())
            self.state = WorkflowState.SAMPLE_SELECTED
            self.has_behavior_model = False
            self.has_strategy_output = False
            self.message = "Samples selected."
            return
        if action == WorkflowAction.MARK_EVIDENCE_READY:
            self._require({WorkflowState.SAMPLE_SELECTED, WorkflowState.EVIDENCE_READY, WorkflowState.DISTILLING, WorkflowState.DONE}, action)
            if not self.project.selected_samples:
                raise ValueError("Cannot mark evidence ready without selected samples.")
            self.has_behavior_model = bool(payload.get("has_behavior_model") or self.has_behavior_model)
            self.has_strategy_output = False
            self.state = WorkflowState.EVIDENCE_READY
            self.message = "Evidence ready."
            return
        if action == WorkflowAction.START_DISTILLATION:
            self._require({WorkflowState.EVIDENCE_READY, WorkflowState.DISTILLING, WorkflowState.DONE}, action)
            if not self.project.selected_samples:
                raise ValueError("Cannot start distillation without selected samples.")
            self.has_strategy_output = False
            self.state = WorkflowState.DISTILLING
            self.message = "Distillation started."
            return
        if action == WorkflowAction.COMPLETE_DISTILLATION:
            self._require({WorkflowState.DISTILLING}, action)
            if not payload.get("has_strategy_output") and not isinstance(payload.get("strategy_output"), dict):
                raise ValueError("COMPLETE_DISTILLATION requires strategy output metadata.")
            self.has_strategy_output = True
            self.state = WorkflowState.DONE
            self.message = "Creator strategy output ready."
            return
        raise ValueError(f"Unsupported workflow action: {action}")

    def _require(self, states: set[WorkflowState], action: WorkflowAction) -> None:
        if self.state not in states:
            allowed = ", ".join(state.value for state in sorted(states, key=lambda item: item.value))
            raise ValueError(f"Cannot dispatch {action.value} from {self.state.value}; allowed states: {allowed}.")

    def _selected_has_pending_evidence(self) -> bool:
        return any(not sample.evidence.ready_for_distillation for sample in self.project.selected_samples)

    def _distill_intent_action(self, selected_count: int) -> WorkflowAction:
        # The workflow action remains START_DISTILLATION; execution chooses
        # direct vs batch from payload without changing state-machine topology.
        _ = selected_count
        return WorkflowAction.START_DISTILLATION

    def _distill_intent_payload(self, selected_count: int) -> dict[str, Any]:
        return {
            "selected_count": int(selected_count or 0),
            "mode": "batch" if int(selected_count or 0) > DIRECT_DISTILL_LIMIT else "direct",
        }


def _default_state_store():
    from app.services.creator_intelligence.state_store import CreatorStateStore

    return CreatorStateStore()
