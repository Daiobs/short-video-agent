from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.errors import AppError, ErrorCode
from app.services.creator_intelligence.iteration_storage import (
    ITERATION_MAX_COUNT,
    LEGACY_ITERATION_ID,
    IterationStorageContext,
    infer_legacy_created_at,
    iteration_artifact_path,
    iteration_write_lock,
    legacy_artifacts_exist,
    read_creator_iteration_index,
    resolve_iteration_context,
    sanitize_close_note,
    validate_project_id,
    virtual_iteration_index,
    write_creator_iteration_index,
)


ARTIFACT_NAME_TO_FILENAME = {
    "execution-pack": "creator_execution_pack.json",
    "execution-record": "creator_execution_record.json",
    "outcome": "creator_outcome_snapshots.json",
}
ARTIFACT_MAX_BYTES = {
    "execution-pack": 512 * 1024,
    "execution-record": 256 * 1024,
    "outcome": 512 * 1024,
}
EXPLICIT_CLOSE_REASONS = frozenset({"cancelled", "superseded", "not_published", "other"})


def list_creator_iterations(project_id: str) -> dict[str, Any]:
    project_id = validate_project_id(project_id)
    index = virtual_iteration_index(project_id)
    summaries = [
        summarize_iteration(project_id, ref, current_iteration_id=index["current_iteration_id"])
        for ref in index["iterations"]
    ]
    current_summary = next((item for item in summaries if item["is_current"]), None)
    return {
        "version": index["version"],
        "project_id": project_id,
        "current_iteration_id": index["current_iteration_id"],
        "iterations": summaries,
        "current_policy": _current_policy(current_summary),
        "virtual": bool(index.get("virtual", False)),
    }


def get_creator_iteration(project_id: str, iteration_id: str) -> dict[str, Any]:
    project_id = validate_project_id(project_id)
    context = resolve_iteration_context(project_id, iteration_id)
    index = virtual_iteration_index(project_id)
    ref = next(
        item for item in index["iterations"] if item["iteration_id"] == context.iteration_id
    )
    summary = summarize_iteration(project_id, ref, current_iteration_id=index["current_iteration_id"])
    return {
        "project_id": project_id,
        "iteration": deepcopy(ref),
        "summary": summary,
        "artifact_availability": {
            "execution_pack": summary["execution_pack_status"],
            "execution_record": summary["execution_record_artifact_status"],
            "outcome": summary["outcome_status"],
        },
    }


def get_creator_iteration_artifact(
    project_id: str,
    iteration_id: str,
    artifact_name: str,
) -> dict[str, Any]:
    if artifact_name not in ARTIFACT_NAME_TO_FILENAME:
        raise AppError(ErrorCode.ITERATION_ARTIFACT_NOT_READY)
    context = resolve_iteration_context(project_id, iteration_id)
    status, payload = _artifact_state(context, artifact_name)
    if status == "missing":
        raise AppError(ErrorCode.ITERATION_ARTIFACT_NOT_READY)
    if status != "ready" or payload is None:
        raise AppError(ErrorCode.ITERATION_ARTIFACT_INVALID)
    return payload


def start_next_creator_iteration(
    project_id: str,
    *,
    close_current: bool = False,
    close_reason: str = "",
    close_note: str = "",
) -> dict[str, Any]:
    project_id = validate_project_id(project_id)
    close_reason = str(close_reason or "").strip()
    try:
        close_note = sanitize_close_note(close_note)
    except ValueError as error:
        raise AppError(ErrorCode.CURRENT_ITERATION_ACTIVE, str(error)[:180]) from error

    with iteration_write_lock():
        persisted = read_creator_iteration_index(project_id)
        if persisted is None:
            iterations: list[dict[str, Any]] = []
            created_at = _now_iso()
            if legacy_artifacts_exist(project_id):
                legacy_created_at, inferred = infer_legacy_created_at(project_id)
                iterations.append(
                    {
                        "iteration_id": LEGACY_ITERATION_ID,
                        "sequence": 1,
                        "storage_mode": "legacy_root",
                        "state": "active",
                        "created_at": legacy_created_at,
                        "closed_at": "",
                        "close_reason": "",
                        "close_note": "",
                        "legacy_created_at_inferred": inferred,
                    }
                )
                current_iteration_id = LEGACY_ITERATION_ID
                created_at = legacy_created_at
            else:
                current_iteration_id = ""
        else:
            iterations = deepcopy(persisted["iterations"])
            current_iteration_id = persisted["current_iteration_id"]
            created_at = persisted["created_at"]

        if len(iterations) >= ITERATION_MAX_COUNT:
            raise AppError(ErrorCode.ITERATION_LIMIT_REACHED)

        previous_ref = next(
            (item for item in iterations if item["iteration_id"] == current_iteration_id),
            None,
        )
        if previous_ref is not None:
            previous_context = _context_for_ref(project_id, previous_ref)
            natural_reason = _natural_close_reason(previous_context)
            if not natural_reason:
                if not close_current or close_reason not in EXPLICIT_CLOSE_REASONS:
                    raise AppError(ErrorCode.CURRENT_ITERATION_ACTIVE)
                applied_reason = close_reason
            else:
                applied_reason = natural_reason
            previous_ref.update(
                {
                    "state": "closed",
                    "closed_at": _now_iso(),
                    "close_reason": applied_reason,
                    "close_note": close_note,
                }
            )

        next_sequence = max((item["sequence"] for item in iterations), default=0) + 1
        new_iteration_id = f"iteration_{uuid4().hex}"
        new_ref = {
            "iteration_id": new_iteration_id,
            "sequence": next_sequence,
            "storage_mode": "iteration_dir",
            "state": "active",
            "created_at": _now_iso(),
            "closed_at": "",
            "close_reason": "",
            "close_note": "",
            "legacy_created_at_inferred": False,
        }
        iterations.append(new_ref)
        now = _now_iso()
        updated_index = write_creator_iteration_index(
            project_id,
            {
                "version": "1.0",
                "project_id": project_id,
                "current_iteration_id": new_iteration_id,
                "iterations": iterations,
                "created_at": created_at or now,
                "updated_at": now,
            },
        )

    previous_summary = (
        summarize_iteration(project_id, previous_ref, current_iteration_id=new_iteration_id)
        if previous_ref is not None
        else None
    )
    new_summary = summarize_iteration(project_id, new_ref, current_iteration_id=new_iteration_id)
    return {
        "index": updated_index,
        "previous_iteration": previous_summary,
        "current_iteration": new_summary,
    }


def summarize_iteration(
    project_id: str,
    ref: dict[str, Any],
    *,
    current_iteration_id: str,
) -> dict[str, Any]:
    context = _context_for_ref(project_id, ref)
    pack_status, pack = _artifact_state(context, "execution-pack")
    record_status, record = _artifact_state(context, "execution-record")
    outcome_status, outcome = _artifact_state(context, "outcome")

    selected_topic = ""
    for source in (record, pack, outcome):
        if not isinstance(source, dict):
            continue
        topic = source.get("selected_topic")
        if not topic and isinstance(source.get("topic"), dict):
            topic = source["topic"].get("title")
        if topic:
            selected_topic = str(topic)[:240]
            break

    snapshots = outcome.get("snapshots") if isinstance(outcome, dict) else []
    snapshots = snapshots if isinstance(snapshots, list) else []
    latest = snapshots[-1] if snapshots else {}
    latest_metrics = latest.get("metrics") if isinstance(latest, dict) else {}
    latest_metrics = latest_metrics if isinstance(latest_metrics, dict) else {}
    metrics = {
        name: latest_metrics.get(name) if name in latest_metrics else None
        for name in ("views", "likes", "comments", "shares", "collects")
    }
    production = record.get("production_status") if isinstance(record, dict) else {}
    production = production if isinstance(production, dict) else {}

    return {
        "iteration_id": ref["iteration_id"],
        "sequence": ref["sequence"],
        "label": f"第 {ref['sequence']} 轮",
        "storage_mode": ref["storage_mode"],
        "state": ref["state"],
        "is_current": ref["iteration_id"] == current_iteration_id,
        "created_at": ref["created_at"],
        "closed_at": ref["closed_at"],
        "close_reason": ref["close_reason"],
        "selected_topic": selected_topic,
        "execution_pack_status": pack_status,
        "execution_record_artifact_status": record_status,
        "execution_record_status": (
            str(record.get("status") or "") if record_status == "ready" and isinstance(record, dict) else record_status
        ),
        "production_status": dict(production),
        "outcome_status": outcome_status,
        "snapshot_count": len(snapshots) if outcome_status == "ready" else 0,
        "latest_metrics": metrics,
        "latest_captured_at": str(latest.get("captured_at") or "") if isinstance(latest, dict) else "",
        "legacy_created_at_inferred": bool(ref.get("legacy_created_at_inferred", False)),
    }


def _current_policy(current_summary: dict[str, Any] | None) -> dict[str, Any]:
    if current_summary is None:
        return {
            "can_start_next": True,
            "requires_explicit_close": False,
            "natural_close_reason": "",
            "blocking_reason": "",
        }
    record_status = current_summary.get("execution_record_status")
    natural_reason = {
        "completed": "execution_completed",
        "archived": "execution_archived",
    }.get(record_status, "")
    if natural_reason:
        return {
            "can_start_next": True,
            "requires_explicit_close": False,
            "natural_close_reason": natural_reason,
            "blocking_reason": "",
        }
    return {
        "can_start_next": False,
        "requires_explicit_close": True,
        "natural_close_reason": "",
        "blocking_reason": "当前轮次尚未完成，请明确结束原因后开始下一轮。",
    }


def _natural_close_reason(context: IterationStorageContext) -> str:
    status, record = _artifact_state(context, "execution-record")
    if status != "ready" or not isinstance(record, dict):
        return ""
    return {
        "completed": "execution_completed",
        "archived": "execution_archived",
    }.get(str(record.get("status") or ""), "")


def _context_for_ref(
    project_id: str,
    ref: dict[str, Any],
) -> IterationStorageContext:
    # The resolver is authoritative and also enforces that iteration_dir values
    # are registered in the index. Virtual legacy is its only no-index exception.
    return resolve_iteration_context(project_id, ref["iteration_id"])


def _artifact_state(
    context: IterationStorageContext,
    artifact_name: str,
) -> tuple[str, dict[str, Any] | None]:
    filename = ARTIFACT_NAME_TO_FILENAME[artifact_name]
    try:
        path = iteration_artifact_path(context, filename)
    except AppError:
        return "invalid", None
    if not path.exists():
        return "missing", None
    if path.is_symlink() or not path.is_file():
        return "invalid", None
    try:
        if path.stat().st_size > ARTIFACT_MAX_BYTES[artifact_name]:
            return "invalid", None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return "invalid", None
        return "ready", _validate_standalone_artifact(
            artifact_name,
            payload,
            project_id=context.project_id,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, AppError):
        return "invalid", None


def _validate_standalone_artifact(
    artifact_name: str,
    payload: dict[str, Any],
    *,
    project_id: str,
) -> dict[str, Any]:
    if artifact_name == "execution-pack":
        from app.services.creator_intelligence.execution_pack import validate_creator_execution_pack

        validated = validate_creator_execution_pack(payload)
        if validated.get("project_id") != project_id:
            raise ValueError("project_id mismatch")
        return validated
    if artifact_name == "execution-record":
        from app.services.creator_intelligence.execution_record import validate_creator_execution_record

        return validate_creator_execution_record(payload, expected_project_id=project_id)
    if artifact_name == "outcome":
        from app.services.creator_intelligence.outcome_snapshot import validate_creator_outcome_timeline

        return validate_creator_outcome_timeline(payload, expected_project_id=project_id)
    raise ValueError("unsupported artifact")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
