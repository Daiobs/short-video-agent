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
    WorkflowIntent,
    WorkflowSnapshot,
    WorkflowState,
)


def _snapshot_dict(snapshot: WorkflowSnapshot | dict[str, Any]) -> dict[str, Any]:
    return snapshot.to_dict() if hasattr(snapshot, "to_dict") else dict(snapshot or {})


_RUNTIME_STEP_META = {
    WorkflowState.IMPORT.value: ("import", 0, "当前步骤：导入素材"),
    WorkflowState.INGESTED.value: ("pool", 1, "当前步骤：构建素材池"),
    WorkflowState.SAMPLE_READY.value: ("select", 2, "当前步骤：选择 N 条样本"),
    WorkflowState.SAMPLE_SELECTED.value: ("enrich", 3, "当前步骤：富化证据"),
    WorkflowState.EVIDENCE_READY.value: ("distill", 4, "当前步骤：大模型蒸馏"),
    WorkflowState.DISTILLING.value: ("distill", 4, "当前步骤：大模型蒸馏"),
    WorkflowState.DONE.value: ("export", 5, "当前步骤：可视化输出"),
}


def _runtime_next_action(workflow: dict[str, Any]) -> dict[str, Any]:
    state = str(workflow.get("state") or WorkflowState.IMPORT.value)
    intent = workflow.get("next_intent") if isinstance(workflow.get("next_intent"), dict) else {}
    intent_action = str(intent.get("action") or "")
    intent_payload = intent.get("payload") if isinstance(intent.get("payload"), dict) else {}
    sample_count = int(workflow.get("sample_count") or 0)
    selected_count = int(workflow.get("selected_count") or 0)
    evidence_ready_count = int(workflow.get("evidence_ready_count") or 0)
    if state == WorkflowState.IMPORT.value:
        return {
            "state": "IMPORT_READY",
            "command": "import_input",
            "label": "下一步：开始导入素材",
            "summary": "输入主页 URL、作品链接、aweme_id 或分享文案后，点击主按钮开始。",
            "disabled": False,
        }
    if state == WorkflowState.INGESTED.value:
        return {
            "state": "POOL_READY",
            "command": "select_recommended_samples",
            "label": "下一步：构建素材池",
            "summary": "已接收输入，准备构建素材池。",
            "disabled": False,
        }
    if state == WorkflowState.SAMPLE_READY.value:
        return {
            "state": "RECOMMENDED_READY",
            "command": "select_recommended_samples",
            "label": "下一步：使用推荐样本继续",
            "summary": f"已导入 {sample_count} 条素材，请选择代表样本继续。",
            "disabled": False,
        }
    if state == WorkflowState.SAMPLE_SELECTED.value:
        if not selected_count:
            return {
                "state": "SELECT_EMPTY",
                "command": "select_samples",
                "label": "请先选择样本",
                "summary": "在素材列表中勾选代表样本，或使用快捷入口。",
                "disabled": True,
            }
        pending = max(0, selected_count - evidence_ready_count)
        if intent_action == WorkflowAction.MARK_EVIDENCE_READY.value or pending:
            return {
                "state": "ENRICH_READY",
                "command": "build_evidence",
                "label": "下一步：开始富化证据",
                "summary": f"已选择 {selected_count} 条样本，其中 {pending} 条仍需补齐证据。",
                "disabled": False,
            }
        return {
            "state": "DISTILL_READY",
            "command": runtime_action_command_for_selected_count(selected_count),
            "label": "下一步：进入大模型蒸馏",
            "summary": f"已选择 {selected_count} 条样本，当前证据可进入蒸馏。",
            "disabled": False,
        }
    if state == WorkflowState.EVIDENCE_READY.value:
        if not selected_count:
            return {
                "state": "DISTILL_BLOCKED",
                "command": "select_samples",
                "label": "返回选择样本",
                "summary": "还没有可蒸馏样本。请先选择代表样本。",
                "disabled": False,
            }
        return {
            "state": "BATCH_DISTILL_READY" if intent_payload.get("mode") == "batch" else "DISTILL_READY",
            "command": runtime_action_command_for_selected_count(selected_count),
            "label": "下一步：开始分批蒸馏" if selected_count > DIRECT_DISTILL_LIMIT else "下一步：开始大模型蒸馏",
            "summary": (
                f"已选择 {selected_count} 条样本，超过单次蒸馏上限，将按批次蒸馏后汇总。"
                if selected_count > DIRECT_DISTILL_LIMIT
                else f"已选择 {selected_count} 条样本，当前证据可进入蒸馏。"
            ),
            "disabled": False,
        }
    if state == WorkflowState.DISTILLING.value:
        return {
            "state": "DISTILLING",
            "command": "wait",
            "label": "正在大模型蒸馏",
            "summary": "当前任务由 Execution Layer 执行，完成后会展示创作者蒸馏报告。",
            "disabled": True,
        }
    if state == WorkflowState.DONE.value:
        return {
            "state": "EXPORT_READY",
            "command": "export_report",
            "label": "下一步：查看报告",
            "summary": "创作者蒸馏报告已生成，可打开网页报告或复制规则继续使用。",
            "disabled": False,
        }
    return {
        "state": "IMPORT_READY",
        "command": "import_input",
        "label": "下一步：开始导入素材",
        "summary": "等待输入。",
        "disabled": False,
    }


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
        state = str(workflow.get("state") or WorkflowState.IMPORT.value)
        stage, index, label = _RUNTIME_STEP_META.get(state, _RUNTIME_STEP_META[WorkflowState.IMPORT.value])
        return {
            "state": state,
            "stage": stage,
            "index": index,
            "label": label,
            "progress_percent": int((index / 5) * 100),
        }

    def primary_action(self) -> dict[str, Any]:
        workflow = self.workflow_dict()
        return _runtime_next_action(workflow)

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
        self.behavior_model = (
            behavior_model
            if isinstance(behavior_model, BehaviorRepresentation)
            else behavior_representation_from_dict(behavior_model)
        )
        self.strategy_output = dict(strategy_output or {})
        self.workflow_engine = WorkflowEngine.from_project(
            project,
            strategy_output=self.strategy_output or None,
            behavior_model=self.behavior_model.to_dict() if self.behavior_model else None,
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
        engine.workflow_engine.has_behavior_model = bool(session.workflow_state.get("has_behavior_model") or engine.behavior_model)
        engine.workflow_engine.has_strategy_output = bool(session.workflow_state.get("has_strategy_output") or engine.strategy_output)
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
        return CreatorRuntimeState(
            project=self.workflow_engine.project,
            workflow=self.workflow_engine.get_state(),
            behavior_model=self.behavior_model,
            strategy_output=dict(self.strategy_output or {}),
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
        intent = WorkflowIntent.from_action(workflow_action, payload)
        if (
            self.workflow_engine.state == WorkflowState.DONE
            and workflow_action in {WorkflowAction.MARK_EVIDENCE_READY, WorkflowAction.START_DISTILLATION}
        ):
            self.strategy_output = {}
            self.workflow_engine.has_strategy_output = False
        if workflow_action == WorkflowAction.MARK_EVIDENCE_READY:
            self.behavior_model = self.execution_layer.extract_behavior_model(
                self.workflow_engine.project,
                intent=intent,
            )
            payload["has_behavior_model"] = True
        if workflow_action == WorkflowAction.START_DISTILLATION and self.behavior_model is None:
            self.behavior_model = self.execution_layer.extract_behavior_model(
                self.workflow_engine.project,
                intent=intent,
            )
            self.workflow_engine.has_behavior_model = True
        if workflow_action == WorkflowAction.COMPLETE_DISTILLATION:
            self.strategy_output = dict(payload.get("strategy_output") or self.strategy_output or {})
            payload["has_strategy_output"] = bool(self.strategy_output)
        self.workflow_engine.dispatch(workflow_action, payload)
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
            behavior_model=self.behavior_model,
            strategy_output=self.strategy_output,
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
            engine = cls.from_sample_set(sample_set, strategy_output={})
            if engine.workflow_engine.state == WorkflowState.EVIDENCE_READY and engine.behavior_model is None:
                engine.behavior_model = engine.execution_layer.extract_behavior_model(
                    engine.project,
                    intent=WorkflowIntent.from_action(WorkflowAction.MARK_EVIDENCE_READY),
                )
                engine.workflow_engine.has_behavior_model = True
            engine.persist(workflow_action, {"selected_sample_ids": selected}, debug={"source": "dispatch_sample_set"})
            return CreatorRuntimeDispatchResult(sample_set=sample_set, state=engine.state)

        if workflow_action == WorkflowAction.MARK_EVIDENCE_READY:
            engine.dispatch(workflow_action)
            engine.persist(workflow_action, debug={"source": "dispatch_sample_set"})
            return CreatorRuntimeDispatchResult(sample_set=sample_set, state=engine.state)

        if workflow_action == WorkflowAction.START_DISTILLATION:
            if engine.workflow_engine.state == WorkflowState.DONE:
                engine.strategy_output = {}
                engine.workflow_engine.has_strategy_output = False
                engine.dispatch(WorkflowAction.MARK_EVIDENCE_READY, persist=True, debug={"source": "dispatch_sample_set"})
            if engine.workflow_engine.state == WorkflowState.SAMPLE_SELECTED:
                engine.dispatch(WorkflowAction.MARK_EVIDENCE_READY, persist=True, debug={"source": "dispatch_sample_set"})
            engine.dispatch(workflow_action)
            engine.persist(workflow_action, debug={"source": "dispatch_sample_set"})
            return CreatorRuntimeDispatchResult(sample_set=sample_set, state=engine.state)

        if workflow_action == WorkflowAction.COMPLETE_DISTILLATION:
            if engine.workflow_engine.state == WorkflowState.DONE:
                if strategy_output:
                    engine.strategy_output = dict(strategy_output or {})
                    engine.workflow_engine.has_strategy_output = True
                engine.persist(
                    workflow_action,
                    {"strategy_output": strategy_output or engine.strategy_output or {}},
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
