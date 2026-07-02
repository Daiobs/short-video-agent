from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.errors import AppError, ErrorCode
from app.services.creator_intelligence.execution import ExecutionLayer
from app.services.creator_intelligence.memory import CreatorMemoryGraph
from app.services.creator_intelligence.models import (
    BehaviorRepresentation,
    CreatorProject,
    behavior_representation_from_dict,
    utc_now_iso,
)
from app.services.creator_intelligence.state_store import CreatorStateStore
from app.services.creator_intelligence.workflow import (
    DIRECT_DISTILL_LIMIT,
    WorkflowAction,
    WorkflowEngine,
    WorkflowSnapshot,
    WorkflowState,
)


def _snapshot_dict(snapshot: WorkflowSnapshot | dict[str, Any]) -> dict[str, Any]:
    return snapshot.to_dict() if hasattr(snapshot, "to_dict") else dict(snapshot or {})


@dataclass(frozen=True)
class CreatorRuntimeState:
    """Unified state contract rendered by the UI and persisted by the runtime."""

    project: CreatorProject
    workflow: WorkflowSnapshot | dict[str, Any]
    behavior_model: BehaviorRepresentation | dict[str, Any] | None = None
    strategy_output: dict[str, Any] = field(default_factory=dict)
    job_state: dict[str, Any] | None = None
    source: str = "runtime"
    updated_at: str = field(default_factory=utc_now_iso)

    def workflow_dict(self) -> dict[str, Any]:
        return _snapshot_dict(self.workflow)

    def behavior_dict(self) -> dict[str, Any] | None:
        if self.behavior_model is None:
            return None
        if hasattr(self.behavior_model, "to_dict"):
            return self.behavior_model.to_dict()
        return dict(self.behavior_model or {})

    def current_step(self) -> dict[str, Any]:
        workflow = self.workflow_dict()
        ui = workflow.get("ui") if isinstance(workflow.get("ui"), dict) else {}
        return {
            "state": workflow.get("state") or WorkflowState.IMPORT.value,
            "stage": ui.get("stage") or "import",
            "index": int(ui.get("step_index") or 0),
            "label": ui.get("step_label") or "当前步骤：导入素材",
            "progress_percent": int(ui.get("progress_percent") or 0),
        }

    def primary_action(self) -> dict[str, Any]:
        workflow = self.workflow_dict()
        ui = workflow.get("ui") if isinstance(workflow.get("ui"), dict) else {}
        action = ui.get("next_action") if isinstance(ui.get("next_action"), dict) else {}
        if not action:
            action = workflow.get("next_action") if isinstance(workflow.get("next_action"), dict) else {}
        return {
            "state": action.get("state") or "",
            "command": action.get("command") or "wait",
            "label": action.get("label") or "等待状态更新",
            "summary": action.get("summary") or workflow.get("message") or "",
            "disabled": bool(action.get("disabled")),
        }

    def state_summary(self) -> dict[str, Any]:
        workflow = self.workflow_dict()
        behavior = self.behavior_dict() or {}
        evidence = behavior.get("evidence_matrix") if isinstance(behavior.get("evidence_matrix"), dict) else {}
        selected_count = int(workflow.get("selected_count") or self.project.selected_count or 0)
        sample_count = int(workflow.get("sample_count") or self.project.sample_count or 0)
        evidence_ready_count = int(workflow.get("evidence_ready_count") or 0)
        return {
            "workflow_state": workflow.get("state") or WorkflowState.IMPORT.value,
            "sample_count": sample_count,
            "selected_count": selected_count,
            "evidence_ready_count": evidence_ready_count,
            "has_behavior_model": bool(workflow.get("has_behavior_model") or behavior),
            "has_strategy_output": bool(workflow.get("has_strategy_output") or self.strategy_output),
            "message": workflow.get("message") or "",
            "evidence_matrix": evidence,
            "job": dict(self.job_state or {}),
        }

    def advanced_panel(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow_dict(),
            "behavior_model": self.behavior_dict(),
            "strategy_output": dict(self.strategy_output or {}),
            "job_state": dict(self.job_state or {}),
        }

    def to_dict(self) -> dict[str, Any]:
        workflow = self.workflow_dict()
        return {
            "project": self.project.to_dict(),
            "workflow": workflow,
            "behavior_model": self.behavior_dict(),
            "strategy_output": dict(self.strategy_output or {}),
            "job_state": dict(self.job_state or {}),
            "current_step": self.current_step(),
            "primary_action": self.primary_action(),
            "state_summary": self.state_summary(),
            "advanced_panel": self.advanced_panel(),
            "state": workflow.get("state") or WorkflowState.IMPORT.value,
            "sample_count": workflow.get("sample_count") or self.project.sample_count,
            "selected_count": workflow.get("selected_count") or self.project.selected_count,
            "evidence_ready_count": workflow.get("evidence_ready_count") or 0,
            "has_behavior_model": bool(workflow.get("has_behavior_model") or self.behavior_dict()),
            "has_strategy_output": bool(workflow.get("has_strategy_output") or self.strategy_output),
            "message": workflow.get("message") or "",
            "source": self.source,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class CreatorRuntimeDispatchResult:
    sample_set: Any | None
    state: CreatorRuntimeState

    @property
    def creator_intelligence(self) -> dict[str, Any]:
        payload = self.state.to_dict()
        # Compatibility aliases for existing routes and UI while runtime_state is
        # adopted as the canonical renderer contract.
        payload["runtime_state"] = self.state.to_dict()
        return payload

    @property
    def workflow(self) -> dict[str, Any]:
        return self.state.workflow_dict()

    @property
    def behavior_model(self) -> dict[str, Any] | None:
        return self.state.behavior_dict()

    @property
    def strategy_output(self) -> dict[str, Any]:
        return dict(self.state.strategy_output or {})


class CreatorRuntimeEngine:
    """Creator Intelligence runtime control center.

    The engine is the only supported state transition entry point for Creator
    Intelligence. Legacy workflow/dispatch helpers delegate here so the runtime
    state is the single source consumed by routes, jobs, and the UI renderer.
    """

    def __init__(
        self,
        project: CreatorProject,
        *,
        strategy_output: dict[str, Any] | None = None,
        behavior_model: BehaviorRepresentation | dict[str, Any] | None = None,
        store: CreatorStateStore | None = None,
        session_id: str | None = None,
        execution_layer: ExecutionLayer | None = None,
        job_state: dict[str, Any] | None = None,
    ) -> None:
        self.execution_layer = execution_layer or ExecutionLayer()
        self.store = store or CreatorStateStore()
        self.session_id = session_id or project.project_id
        self.job_state = dict(job_state or {})
        self.workflow_engine = WorkflowEngine.from_project(project, strategy_output=strategy_output or None)
        if behavior_model is not None:
            self.workflow_engine.behavior_model = (
                behavior_model
                if isinstance(behavior_model, BehaviorRepresentation)
                else behavior_representation_from_dict(behavior_model)
            )

    @classmethod
    def from_project(
        cls,
        project: CreatorProject,
        *,
        strategy_output: dict[str, Any] | None = None,
        behavior_model: BehaviorRepresentation | dict[str, Any] | None = None,
        store: CreatorStateStore | None = None,
        session_id: str | None = None,
        job_state: dict[str, Any] | None = None,
    ) -> "CreatorRuntimeEngine":
        return cls(
            project,
            strategy_output=strategy_output,
            behavior_model=behavior_model,
            store=store,
            session_id=session_id,
            job_state=job_state,
        )

    @classmethod
    def from_sample_set(
        cls,
        sample_set: Any,
        *,
        strategy_output: dict[str, Any] | None = None,
        store: CreatorStateStore | None = None,
        job_state: dict[str, Any] | None = None,
    ) -> "CreatorRuntimeEngine":
        execution = ExecutionLayer()
        if strategy_output is None:
            from app.services.creator_clone import load_creator_strategy_output

            strategy_output = load_creator_strategy_output(sample_set.set_id)
        return cls(
            execution.normalize_sample_set(sample_set),
            strategy_output=strategy_output or None,
            store=store,
            session_id=str(sample_set.set_id),
            execution_layer=execution,
            job_state=job_state,
        )

    @classmethod
    def restore_state(cls, session_id: str, store: CreatorStateStore | None = None) -> "CreatorRuntimeEngine":
        store = store or CreatorStateStore()
        session = store.load_session(session_id)
        if not session:
            raise ValueError(f"Creator session not found: {session_id}")
        engine = cls.from_project(
            session.project,
            strategy_output=session.strategy_output or None,
            behavior_model=session.behavior_model or None,
            store=store,
            session_id=session_id,
        )
        saved_state = session.workflow_state.get("state")
        if saved_state:
            engine.workflow_engine.state = WorkflowState(saved_state)
        engine.workflow_engine.message = str(session.workflow_state.get("message") or engine.workflow_engine.message)
        return engine

    @classmethod
    def replay_actions(cls, session_id: str, store: CreatorStateStore | None = None) -> list[dict[str, Any]]:
        store = store or CreatorStateStore()
        session = store.load_session(session_id)
        if not session:
            return []
        engine = cls.from_project(session.project, store=store, session_id=session_id)
        snapshots: list[dict[str, Any]] = []
        for entry in session.actions:
            try:
                snapshot = engine.dispatch(
                    entry.get("action"),
                    entry.get("payload") if isinstance(entry.get("payload"), dict) else {},
                    persist=False,
                )
                snapshots.append(snapshot.to_dict())
            except Exception as error:
                snapshots.append(
                    {
                        "state": engine.workflow_engine.state.value,
                        "error": type(error).__name__,
                        "message": str(error),
                        "action": entry.get("action"),
                    }
                )
                break
        return snapshots

    @property
    def project(self) -> CreatorProject:
        return self.workflow_engine.project

    @property
    def state(self) -> CreatorRuntimeState:
        if self.workflow_engine.behavior_model is None and self.workflow_engine.project.selected_samples:
            self.workflow_engine.behavior_model = self.execution_layer.extract_behavior_model(self.workflow_engine.project)
        return CreatorRuntimeState(
            project=self.workflow_engine.project,
            workflow=self.workflow_engine.get_state(),
            behavior_model=self.workflow_engine.behavior_model,
            strategy_output=dict(self.workflow_engine.strategy_output or {}),
            job_state=self.job_state,
        )

    def dispatch(
        self,
        action: WorkflowAction | str,
        payload: dict[str, Any] | None = None,
        *,
        persist: bool = False,
        debug: dict[str, Any] | None = None,
    ) -> CreatorRuntimeState:
        workflow_action = WorkflowAction(action)
        payload = dict(payload or {})
        if workflow_action == WorkflowAction.MARK_EVIDENCE_READY:
            self.workflow_engine.behavior_model = self.execution_layer.extract_behavior_model(self.workflow_engine.project)
        self.workflow_engine.dispatch(workflow_action, payload)
        if workflow_action == WorkflowAction.MARK_EVIDENCE_READY and not self.workflow_engine.behavior_model:
            self.workflow_engine.behavior_model = self.execution_layer.extract_behavior_model(self.workflow_engine.project)
        if persist:
            self.persist(workflow_action, payload, debug=debug)
        return self.state

    def persist(
        self,
        action: WorkflowAction | str | None = None,
        action_payload: dict[str, Any] | None = None,
        *,
        debug: dict[str, Any] | None = None,
    ):
        workflow_action = WorkflowAction(action) if action else None
        session = self.workflow_engine.persist_state(
            self.session_id,
            self.store,
            action=workflow_action,
            action_payload=action_payload or {},
            runtime_state=self.state.to_dict(),
            debug={
                "source": "CreatorRuntimeEngine",
                **dict(debug or {}),
            },
        )
        CreatorMemoryGraph().record_session(session)
        return session

    def to_payload(self) -> dict[str, Any]:
        return self.state.to_dict()

    @classmethod
    def dispatch_sample_set(
        cls,
        set_id: str,
        action: WorkflowAction | str,
        *,
        selected_sample_ids: list[str] | None = None,
        strategy_output: dict[str, Any] | None = None,
    ) -> CreatorRuntimeDispatchResult:
        from app.services.creator_clone import (
            load_sample_set,
            normalize_sample_set_selected_ids,
            update_sample_set_selection,
        )

        workflow_action = WorkflowAction(action)
        sample_set = load_sample_set(set_id)
        engine = cls.from_sample_set(sample_set, strategy_output=strategy_output)

        if workflow_action == WorkflowAction.SELECT_SAMPLES:
            selected = normalize_sample_set_selected_ids(sample_set, selected_sample_ids or [])
            engine.dispatch(workflow_action, {"selected_sample_ids": selected})
            sample_set = update_sample_set_selection(set_id, selected)
            engine = cls.from_sample_set(sample_set, strategy_output=strategy_output)
            engine.persist(workflow_action, {"selected_sample_ids": selected}, debug={"source": "dispatch_sample_set"})
            return CreatorRuntimeDispatchResult(sample_set=sample_set, state=engine.state)

        if workflow_action == WorkflowAction.MARK_EVIDENCE_READY:
            engine.dispatch(workflow_action)
            engine.persist(workflow_action, debug={"source": "dispatch_sample_set"})
            return CreatorRuntimeDispatchResult(sample_set=sample_set, state=engine.state)

        if workflow_action == WorkflowAction.START_DISTILLATION:
            if engine.workflow_engine.state == WorkflowState.SAMPLE_SELECTED:
                engine.dispatch(WorkflowAction.MARK_EVIDENCE_READY, persist=True, debug={"source": "dispatch_sample_set"})
            engine.dispatch(workflow_action)
            engine.persist(workflow_action, debug={"source": "dispatch_sample_set"})
            return CreatorRuntimeDispatchResult(sample_set=sample_set, state=engine.state)

        if workflow_action == WorkflowAction.COMPLETE_DISTILLATION:
            if engine.workflow_engine.state == WorkflowState.DONE:
                if strategy_output:
                    engine.workflow_engine.strategy_output = dict(strategy_output or {})
                engine.persist(
                    workflow_action,
                    {"strategy_output": strategy_output or engine.workflow_engine.strategy_output or {}},
                    debug={"source": "dispatch_sample_set", "idempotent": True},
                )
                return CreatorRuntimeDispatchResult(sample_set=sample_set, state=engine.state)
            if engine.workflow_engine.state == WorkflowState.SAMPLE_SELECTED:
                engine.dispatch(WorkflowAction.MARK_EVIDENCE_READY, persist=True, debug={"source": "dispatch_sample_set"})
            if engine.workflow_engine.state != WorkflowState.DISTILLING:
                engine.dispatch(WorkflowAction.START_DISTILLATION, persist=True, debug={"source": "dispatch_sample_set"})
            engine.dispatch(workflow_action, {"strategy_output": strategy_output or {}})
            engine.persist(
                workflow_action,
                {"strategy_output": strategy_output or {}},
                debug={"source": "dispatch_sample_set"},
            )
            return CreatorRuntimeDispatchResult(sample_set=sample_set, state=engine.state)

        raise AppError(
            ErrorCode.PROFILE_SCAN_FAILED,
            f"当前 runtime action 暂不支持持久化：{workflow_action.value}。",
        )


def runtime_action_command_for_selected_count(selected_count: int) -> str:
    return "start_batch_distillation" if int(selected_count or 0) > DIRECT_DISTILL_LIMIT else "start_distillation"
