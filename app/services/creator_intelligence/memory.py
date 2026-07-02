from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.creator_intelligence.models import BehaviorRepresentation, CreatorProject, utc_now_iso
from app.services.creator_intelligence.state_store import CreatorSession, _safe_id


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


class CreatorMemoryGraph:
    """Persistent creator memory graph for cross-session learning."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or settings.creator_state_dir) / "memory"

    def memory_path(self, creator_id: str) -> Path:
        return self.root / f"{_safe_id(creator_id)}.json"

    def load(self, creator_id: str) -> dict[str, Any]:
        payload = _read_json(self.memory_path(creator_id))
        if payload:
            return payload
        return {
            "creator_id": creator_id,
            "sample_sets": [],
            "distill_results": [],
            "behavior_patterns": {},
            "hook_patterns": {},
            "structure_patterns": {},
            "anti_patterns": {},
            "evolution": [],
            "updated_at": "",
        }

    def save(self, creator_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        payload["creator_id"] = creator_id
        payload["updated_at"] = utc_now_iso()
        _write_json_atomic(self.memory_path(creator_id), payload)
        return payload

    def record_project(
        self,
        project: CreatorProject,
        *,
        behavior_model: BehaviorRepresentation | dict[str, Any] | None = None,
        strategy_output: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        creator_id = project.profile.creator_id
        memory = self.load(creator_id)
        now = utc_now_iso()
        memory.setdefault("sample_sets", []).append(
            {
                "session_id": session_id or project.project_id,
                "project_id": project.project_id,
                "title": project.title,
                "sample_count": project.sample_count,
                "selected_sample_ids": list(project.selected_sample_ids),
                "captured_at": now,
            }
        )
        behavior_payload = behavior_model.to_dict() if isinstance(behavior_model, BehaviorRepresentation) else dict(behavior_model or {})
        if behavior_payload:
            self._accumulate_patterns(memory, behavior_payload)
        if strategy_output:
            memory.setdefault("distill_results", []).append(
                {
                    "session_id": session_id or project.project_id,
                    "project_id": project.project_id,
                    "strategy_output": dict(strategy_output),
                    "captured_at": now,
                }
            )
            self._accumulate_strategy(memory, strategy_output)
        memory.setdefault("evolution", []).append(self._evolution_point(project, behavior_payload, strategy_output, now))
        return self.save(creator_id, memory)

    def record_session(self, session: CreatorSession) -> dict[str, Any]:
        return self.record_project(
            session.project,
            behavior_model=session.behavior_model,
            strategy_output=session.strategy_output,
            session_id=session.session_id,
        )

    def creator_evolution(self, creator_id: str) -> dict[str, Any]:
        memory = self.load(creator_id)
        sample_sets = memory.get("sample_sets") if isinstance(memory.get("sample_sets"), list) else []
        distills = memory.get("distill_results") if isinstance(memory.get("distill_results"), list) else []
        return {
            "creator_id": creator_id,
            "sample_set_count": len(sample_sets),
            "distill_count": len(distills),
            "latest": (memory.get("evolution") or [])[-1] if memory.get("evolution") else {},
            "reusable_patterns": self.reusable_patterns(creator_id),
            "updated_at": memory.get("updated_at") or "",
        }

    def reusable_patterns(self, creator_id: str, limit: int = 10) -> dict[str, list[str]]:
        memory = self.load(creator_id)
        return {
            key: _top_pattern_keys(memory.get(key), limit)
            for key in ("behavior_patterns", "hook_patterns", "structure_patterns", "anti_patterns")
        }

    def distillation_prompt_context(self, creator_id: str, limit: int = 6) -> dict[str, Any]:
        evolution = self.creator_evolution(creator_id)
        patterns = self.reusable_patterns(creator_id, limit=limit)
        return {
            "creator_id": creator_id,
            "historical_sample_set_count": evolution["sample_set_count"],
            "historical_distill_count": evolution["distill_count"],
            "reusable_patterns": patterns,
        }

    def _accumulate_patterns(self, memory: dict[str, Any], behavior_payload: dict[str, Any]) -> None:
        for source_key, memory_key in (
            ("behavior_patterns", "behavior_patterns"),
            ("hook_patterns", "hook_patterns"),
            ("structure_patterns", "structure_patterns"),
            ("content_structures", "structure_patterns"),
            ("risk_patterns", "anti_patterns"),
            ("anti_patterns", "anti_patterns"),
        ):
            values = _flatten_signal_values(behavior_payload.get(source_key))
            _counter_add(memory, memory_key, values)

    def _accumulate_strategy(self, memory: dict[str, Any], strategy_output: dict[str, Any]) -> None:
        strategy = strategy_output.get("creator_clone_strategy") if isinstance(strategy_output.get("creator_clone_strategy"), dict) else strategy_output
        if not isinstance(strategy, dict):
            return
        _counter_add(memory, "hook_patterns", _flatten_signal_values(strategy.get("hooks")))
        _counter_add(memory, "structure_patterns", _flatten_signal_values(strategy.get("templates") or strategy.get("content_strategy")))
        _counter_add(memory, "anti_patterns", _flatten_signal_values(strategy.get("anti_patterns")))
        _counter_add(memory, "behavior_patterns", _flatten_signal_values(strategy.get("positioning")))

    def _evolution_point(
        self,
        project: CreatorProject,
        behavior_payload: dict[str, Any],
        strategy_output: dict[str, Any] | None,
        captured_at: str,
    ) -> dict[str, Any]:
        return {
            "project_id": project.project_id,
            "sample_count": project.sample_count,
            "selected_count": project.selected_count,
            "evidence_depth": (behavior_payload.get("behavior_patterns") or {}).get("evidence_depth") or "",
            "has_strategy": bool(strategy_output),
            "captured_at": captured_at,
        }


def _flatten_signal_values(value) -> list[str]:
    result: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            result.extend(_flatten_signal_values(item))
    elif isinstance(value, list) or isinstance(value, tuple):
        for item in value:
            result.extend(_flatten_signal_values(item))
    elif value not in (None, "", [], {}):
        text = str(value).strip()
        if text:
            result.append(text[:160])
    return result


def _counter_add(memory: dict[str, Any], key: str, values: list[str]) -> None:
    counter = Counter(memory.get(key) if isinstance(memory.get(key), dict) else {})
    for value in values:
        counter[value] += 1
    memory[key] = dict(counter.most_common(100))


def _top_pattern_keys(value, limit: int) -> list[str]:
    if not isinstance(value, dict):
        return []
    return [key for key, _count in Counter(value).most_common(limit)]
