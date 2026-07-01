from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from app.services.creator_intelligence.cognition import build_behavior_representation
from app.services.creator_intelligence.models import BehaviorRepresentation, CreatorProject

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
class WorkflowSnapshot:
    project_id: str
    state: WorkflowState = WorkflowState.IMPORT
    sample_count: int = 0
    selected_count: int = 0
    evidence_ready_count: int = 0
    has_behavior_model: bool = False
    has_strategy_output: bool = False
    message: str = ""
    ui: dict[str, Any] = field(default_factory=dict)
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
            "ui": dict(self.ui),
            "next_action": dict(self.ui.get("next_action") or {}),
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
        sample_count = len(self.project.samples)
        selected_count = len(selected)
        return WorkflowSnapshot(
            project_id=self.project.project_id,
            state=self.state,
            sample_count=sample_count,
            selected_count=selected_count,
            evidence_ready_count=evidence_ready_count,
            has_behavior_model=self.behavior_model is not None,
            has_strategy_output=bool(self.strategy_output),
            message=self.message,
            ui=self.ui_state(sample_count=sample_count, selected_count=selected_count, evidence_ready_count=evidence_ready_count),
        )

    def ui_state(self, *, sample_count: int, selected_count: int, evidence_ready_count: int) -> dict[str, Any]:
        step = {
            WorkflowState.IMPORT: ("import", 0, "当前步骤：导入素材"),
            WorkflowState.INGESTED: ("pool", 1, "当前步骤：构建素材池"),
            WorkflowState.SAMPLE_READY: ("select", 2, "当前步骤：选择 N 条样本"),
            WorkflowState.SAMPLE_SELECTED: ("enrich", 3, "当前步骤：富化证据"),
            WorkflowState.EVIDENCE_READY: ("distill", 4, "当前步骤：大模型蒸馏"),
            WorkflowState.DISTILLING: ("distill", 4, "当前步骤：大模型蒸馏"),
            WorkflowState.DONE: ("export", 5, "当前步骤：可视化输出"),
        }[self.state]
        action_state, label, summary, disabled = self._next_action_for_state(
            sample_count=sample_count,
            selected_count=selected_count,
            evidence_ready_count=evidence_ready_count,
        )
        return {
            "stage": step[0],
            "step_index": step[1],
            "step_label": step[2],
            "progress_percent": int((step[1] / 5) * 100),
            "next_action": {
                "state": action_state,
                "label": label,
                "summary": summary,
                "disabled": disabled,
            },
        }

    def _next_action_for_state(self, *, sample_count: int, selected_count: int, evidence_ready_count: int) -> tuple[str, str, str, bool]:
        if self.state == WorkflowState.IMPORT:
            return ("IMPORT_READY", "下一步：开始导入素材", "输入主页 URL、作品链接、aweme_id 或分享文案后，点击主按钮开始。", False)
        if self.state == WorkflowState.INGESTED:
            return ("POOL_READY", "下一步：构建素材池", f"已接收输入，准备构建素材池。", False)
        if self.state == WorkflowState.SAMPLE_READY:
            return ("RECOMMENDED_READY", "下一步：使用推荐样本继续", f"已导入 {sample_count} 条素材，请选择代表样本继续。", False)
        if self.state == WorkflowState.SAMPLE_SELECTED:
            if not selected_count:
                return ("SELECT_EMPTY", "请先选择样本", "在素材列表中勾选代表样本，或使用快捷入口。", True)
            pending = max(0, selected_count - evidence_ready_count)
            if pending:
                return ("ENRICH_READY", "下一步：开始富化证据", f"已选择 {selected_count} 条样本，其中 {pending} 条仍需补齐证据。", False)
            return ("DISTILL_READY", "下一步：进入大模型蒸馏", f"已选择 {selected_count} 条样本，当前证据可进入蒸馏。", False)
        if self.state == WorkflowState.EVIDENCE_READY:
            if not selected_count:
                return ("DISTILL_BLOCKED", "返回选择样本", "还没有可蒸馏样本。请先选择代表样本。", False)
            if selected_count > DIRECT_DISTILL_LIMIT:
                return ("BATCH_DISTILL_READY", "下一步：开始分批蒸馏", f"已选择 {selected_count} 条样本，超过单次蒸馏上限，将按批次蒸馏后汇总。", False)
            return ("DISTILL_READY", "下一步：开始大模型蒸馏", f"已选择 {selected_count} 条样本，当前证据可进入蒸馏。", False)
        if self.state == WorkflowState.DISTILLING:
            return ("DISTILLING", "正在大模型蒸馏", "当前任务由 Workflow Engine 接管，完成后会展示创作者蒸馏报告。", True)
        if self.state == WorkflowState.DONE:
            return ("EXPORT_READY", "下一步：下载报告", "创作者蒸馏报告已生成，可下载报告或复制规则继续使用。", False)
        return ("IMPORT_READY", "下一步：开始导入素材", "等待输入。", False)

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
