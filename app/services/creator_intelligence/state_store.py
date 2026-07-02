from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.creator_intelligence.models import (
    BehaviorRepresentation,
    CreatorProject,
    creator_project_from_dict,
    utc_now_iso,
)


def _safe_id(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(value or "").strip())
    return cleaned or "unknown"


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


@dataclass
class CreatorSession:
    session_id: str
    creator_id: str
    project_id: str
    project: CreatorProject
    workflow_state: dict[str, Any] = field(default_factory=dict)
    runtime_state: dict[str, Any] = field(default_factory=dict)
    behavior_model: dict[str, Any] = field(default_factory=dict)
    strategy_output: dict[str, Any] = field(default_factory=dict)
    actions: list[dict[str, Any]] = field(default_factory=list)
    sample_set_history: list[dict[str, Any]] = field(default_factory=list)
    distill_history: list[dict[str, Any]] = field(default_factory=list)
    creator_profile_evolution: list[dict[str, Any]] = field(default_factory=list)
    debug_trace: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "creator_id": self.creator_id,
            "project_id": self.project_id,
            "project": self.project.to_dict(),
            "workflow_state": dict(self.workflow_state),
            "runtime_state": dict(self.runtime_state),
            "behavior_model": dict(self.behavior_model),
            "strategy_output": dict(self.strategy_output),
            "actions": list(self.actions),
            "sample_set_history": list(self.sample_set_history),
            "distill_history": list(self.distill_history),
            "creator_profile_evolution": list(self.creator_profile_evolution),
            "debug_trace": list(self.debug_trace),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CreatorSession":
        payload = value if isinstance(value, dict) else {}
        project = creator_project_from_dict(payload.get("project") if isinstance(payload.get("project"), dict) else {})
        session_id = str(payload.get("session_id") or project.project_id)
        creator_id = str(payload.get("creator_id") or project.profile.creator_id)
        project_id = str(payload.get("project_id") or project.project_id)
        return cls(
            session_id=session_id,
            creator_id=creator_id,
            project_id=project_id,
            project=project,
            workflow_state=dict(payload.get("workflow_state") or {}),
            runtime_state=dict(payload.get("runtime_state") or {}),
            behavior_model=dict(payload.get("behavior_model") or {}),
            strategy_output=dict(payload.get("strategy_output") or {}),
            actions=list(payload.get("actions") or []),
            sample_set_history=list(payload.get("sample_set_history") or []),
            distill_history=list(payload.get("distill_history") or []),
            creator_profile_evolution=list(payload.get("creator_profile_evolution") or []),
            debug_trace=list(payload.get("debug_trace") or []),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or utc_now_iso()),
        )


class CreatorStateStore:
    """File-backed system of record for Creator Intelligence runtime state."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or settings.creator_state_dir)
        self.sessions_dir = self.root / "sessions"
        self.index_path = self.root / "sessions.json"

    def session_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{_safe_id(session_id)}.json"

    def load_session(self, session_id: str) -> CreatorSession | None:
        payload = _read_json(self.session_path(session_id))
        if not payload:
            return None
        return CreatorSession.from_dict(payload)

    def save_session(self, session: CreatorSession) -> CreatorSession:
        session.updated_at = utc_now_iso()
        _write_json_atomic(self.session_path(session.session_id), session.to_dict())
        self._update_index(session)
        return session

    def persist_workflow_state(
        self,
        session_id: str,
        project: CreatorProject,
        workflow_state: dict[str, Any],
        *,
        runtime_state: dict[str, Any] | None = None,
        behavior_model: BehaviorRepresentation | dict[str, Any] | None = None,
        strategy_output: dict[str, Any] | None = None,
        action: str | None = None,
        action_payload: dict[str, Any] | None = None,
        debug: dict[str, Any] | None = None,
    ) -> CreatorSession:
        existing = self.load_session(session_id)
        created_at = existing.created_at if existing else utc_now_iso()
        actions = list(existing.actions if existing else [])
        sample_set_history = list(existing.sample_set_history if existing else [])
        distill_history = list(existing.distill_history if existing else [])
        profile_evolution = list(existing.creator_profile_evolution if existing else [])
        debug_trace = list(existing.debug_trace if existing else [])

        now = utc_now_iso()
        if action:
            actions.append(
                {
                    "action": str(action),
                    "payload": dict(action_payload or {}),
                    "state_after": workflow_state.get("state"),
                    "created_at": now,
                }
            )
        project_snapshot = project.to_dict()
        sample_set_history.append(
            {
                "project_id": project.project_id,
                "sample_count": project.sample_count,
                "selected_sample_ids": list(project.selected_sample_ids),
                "snapshot": project_snapshot,
                "captured_at": now,
            }
        )
        if strategy_output:
            distill_history.append(
                {
                    "project_id": project.project_id,
                    "strategy_output": dict(strategy_output),
                    "captured_at": now,
                }
            )
        profile_evolution.append(
            {
                "creator_id": project.profile.creator_id,
                "profile": project.profile.to_dict(),
                "sample_count": project.sample_count,
                "selected_count": project.selected_count,
                "captured_at": now,
            }
        )
        if debug:
            debug_trace.append({"event": dict(debug), "captured_at": now})

        behavior_payload = behavior_model.to_dict() if isinstance(behavior_model, BehaviorRepresentation) else dict(behavior_model or {})
        session = CreatorSession(
            session_id=session_id,
            creator_id=project.profile.creator_id,
            project_id=project.project_id,
            project=project,
            workflow_state=dict(workflow_state),
            runtime_state=dict(runtime_state or (existing.runtime_state if existing else {})),
            behavior_model=behavior_payload,
            strategy_output=dict(strategy_output or (existing.strategy_output if existing else {})),
            actions=actions,
            sample_set_history=sample_set_history[-50:],
            distill_history=distill_history[-50:],
            creator_profile_evolution=profile_evolution[-100:],
            debug_trace=debug_trace[-200:],
            created_at=created_at,
            updated_at=now,
        )
        return self.save_session(session)

    def replay_actions(self, session_id: str) -> list[dict[str, Any]]:
        session = self.load_session(session_id)
        if not session:
            return []
        from app.services.creator_intelligence.runtime import CreatorRuntimeEngine
        from app.services.creator_intelligence.workflow import WorkflowAction

        engine = CreatorRuntimeEngine.from_project(session.project, store=self, session_id=session_id)
        snapshots: list[dict[str, Any]] = []
        for entry in session.actions:
            try:
                action = WorkflowAction(entry.get("action"))
                snapshot = engine.dispatch(
                    action,
                    entry.get("payload") if isinstance(entry.get("payload"), dict) else {},
                    persist=False,
                )
                snapshots.append(snapshot.to_dict())
            except Exception as error:
                snapshots.append(
                    {
                        "state": engine.state.workflow_dict().get("state"),
                        "error": type(error).__name__,
                        "message": str(error),
                        "action": entry.get("action"),
                    }
                )
                break
        return snapshots

    def _update_index(self, session: CreatorSession) -> None:
        index = _read_json(self.index_path)
        sessions = index.get("sessions") if isinstance(index.get("sessions"), dict) else {}
        sessions[session.session_id] = {
            "session_id": session.session_id,
            "creator_id": session.creator_id,
            "project_id": session.project_id,
            "state": session.workflow_state.get("state"),
            "updated_at": session.updated_at,
        }
        _write_json_atomic(self.index_path, {"sessions": sessions, "updated_at": utc_now_iso()})
