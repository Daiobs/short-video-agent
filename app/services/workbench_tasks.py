from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


TASK_STATUSES = frozenset({"pending", "running", "success", "failed", "recoverable", "stale"})
RESUME_ROUTES = frozenset({"single", "profile"})
RESUME_MODES = frozenset({"observe", "manual", "result"})


@dataclass(frozen=True)
class WorkbenchResumeTarget:
    route: str = ""
    stage: str = ""
    resource_id: str = ""
    job_id: str = ""
    task_type: str = ""
    mode: str = "manual"
    open_url: str = ""

    def to_dict(self) -> dict[str, str]:
        route = self.route if self.route in RESUME_ROUTES else ""
        mode = self.mode if self.mode in RESUME_MODES else "manual"
        return {
            "route": route,
            "stage": self.stage,
            "resource_id": self.resource_id,
            "job_id": self.job_id,
            "task_type": self.task_type,
            "mode": mode,
            "open_url": self.open_url,
        }


@dataclass(frozen=True)
class WorkbenchTask:
    task_id: str
    task_type: str
    title: str
    status: str
    stage: str
    progress: int
    message: str
    created_at: str
    updated_at: str
    resume_target: WorkbenchResumeTarget = field(default_factory=WorkbenchResumeTarget)
    recoverable: bool = False
    has_resource_target: bool = False
    can_observe_by_job: bool = False
    diagnostic_only: bool = True
    recovery_hint: str = ""
    task_group: str = "系统"
    error_code: str = ""
    last_completed_stage: str = ""
    available_results: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        status = self.status if self.status in TASK_STATUSES else "failed"
        target = self.resume_target.to_dict()
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "task_group": self.task_group,
            "title": self.title,
            "status": status,
            "stage": self.stage,
            "progress": max(0, min(100, int(self.progress))),
            "message": self.message,
            "error_code": self.error_code,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "resume_target": target,
            "target": target,
            "recoverable": bool(self.recoverable),
            "has_resource_target": bool(self.has_resource_target),
            "can_observe_by_job": bool(self.can_observe_by_job),
            "diagnostic_only": bool(self.diagnostic_only),
            "recovery_hint": self.recovery_hint,
            "last_completed_stage": self.last_completed_stage,
            "available_results": list(self.available_results),
        }
