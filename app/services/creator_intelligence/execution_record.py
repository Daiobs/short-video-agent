from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from app.config import settings
from app.errors import AppError, ErrorCode
from app.services.creator_intelligence.execution_pack import load_creator_execution_pack


EXECUTION_RECORD_VERSION = "1.0"
EXECUTION_RECORD_FILENAME = "creator_execution_record.json"
EXECUTION_RECORD_MAX_JSON_BYTES = 256 * 1024
EXECUTION_RECORD_STATUSES = frozenset({"draft", "in_progress", "completed", "archived"})
PRODUCTION_STATUSES = frozenset({"pending", "completed", "skipped"})
PRODUCTION_STAGES = ("shooting", "editing", "publishing")
DIFFICULTY_VALUES = frozenset({"", "easy", "normal", "hard"})
_RECORD_LOCK = Lock()


@dataclass(frozen=True)
class CreatorExecutionRecordV1:
    version: str
    project_id: str
    execution_pack_generated_at: str
    execution_pack_topic_index: int
    selected_topic: str
    status: str
    production_status: dict[str, str]
    feedback: dict[str, Any]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "project_id": self.project_id,
            "execution_pack_generated_at": self.execution_pack_generated_at,
            "execution_pack_topic_index": self.execution_pack_topic_index,
            "selected_topic": self.selected_topic,
            "status": self.status,
            "production_status": dict(self.production_status),
            "feedback": dict(self.feedback),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def start_creator_execution_record(project_id: str) -> dict[str, Any]:
    project_id = _validated_project_id(project_id, ErrorCode.EXECUTION_PACK_NOT_READY)
    path = execution_record_path(project_id)
    with _RECORD_LOCK:
        if path.is_file():
            return _load_record_file(path, project_id)

        execution_pack = load_creator_execution_pack(project_id)
        topic = execution_pack.get("topic") if isinstance(execution_pack.get("topic"), dict) else {}
        now = _now_iso()
        record = CreatorExecutionRecordV1(
            version=EXECUTION_RECORD_VERSION,
            project_id=project_id,
            execution_pack_generated_at=str(execution_pack.get("generated_at") or ""),
            execution_pack_topic_index=_strict_integer(execution_pack.get("topic_index"), "execution_pack_topic_index"),
            selected_topic=_safe_required_text(topic.get("title"), "selected_topic", 240),
            status="draft",
            production_status={stage: "pending" for stage in PRODUCTION_STAGES},
            feedback={
                "was_used": False,
                "difficulty": "",
                "quality_rating": None,
                "result_rating": None,
                "notes": "",
            },
            created_at=now,
            updated_at=now,
        )
        payload = validate_creator_execution_record(record.to_dict(), expected_project_id=project_id)
        _write_json_atomic(path, payload)
        return payload


def load_creator_execution_record(project_id: str) -> dict[str, Any]:
    project_id = _validated_project_id(project_id, ErrorCode.EXECUTION_RECORD_NOT_READY)
    path = execution_record_path(project_id)
    if not path.is_file():
        raise AppError(ErrorCode.EXECUTION_RECORD_NOT_READY)
    return _load_record_file(path, project_id)


def update_creator_execution_record(project_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    project_id = _validated_project_id(project_id, ErrorCode.EXECUTION_RECORD_NOT_READY)
    path = execution_record_path(project_id)
    with _RECORD_LOCK:
        current = _load_record_file(path, project_id)
        status = current["status"]
        production_status = dict(current["production_status"])
        feedback = dict(current["feedback"])

        requested_status = changes.get("status") if isinstance(changes, dict) else None
        if requested_status is not None:
            status = _enum_value(requested_status, EXECUTION_RECORD_STATUSES, "status")

        production_progressed = False
        production_changes = changes.get("production_status") if isinstance(changes, dict) else None
        if isinstance(production_changes, dict):
            for stage in PRODUCTION_STAGES:
                if stage not in production_changes or production_changes[stage] is None:
                    continue
                next_value = _enum_value(production_changes[stage], PRODUCTION_STATUSES, stage)
                if next_value != production_status[stage] and next_value in {"completed", "skipped"}:
                    production_progressed = True
                production_status[stage] = next_value

        feedback_changes = changes.get("feedback") if isinstance(changes, dict) else None
        if isinstance(feedback_changes, dict):
            if "was_used" in feedback_changes and feedback_changes["was_used"] is not None:
                if not isinstance(feedback_changes["was_used"], bool):
                    raise ValueError("feedback.was_used must be a boolean")
                feedback["was_used"] = feedback_changes["was_used"]
            if "difficulty" in feedback_changes:
                difficulty = "" if feedback_changes["difficulty"] is None else feedback_changes["difficulty"]
                feedback["difficulty"] = _enum_value(difficulty, DIFFICULTY_VALUES, "feedback.difficulty")
            if "quality_rating" in feedback_changes:
                feedback["quality_rating"] = _rating(feedback_changes["quality_rating"], "feedback.quality_rating")
            if "result_rating" in feedback_changes:
                feedback["result_rating"] = _rating(feedback_changes["result_rating"], "feedback.result_rating")
            if "notes" in feedback_changes:
                notes = "" if feedback_changes["notes"] is None else str(feedback_changes["notes"])
                if len(notes) > 1000:
                    raise ValueError("feedback.notes must not exceed 1000 characters")
                feedback["notes"] = _safe_text(notes, 1000)

        if production_progressed:
            feedback["was_used"] = True

        if status != "archived":
            stage_values = tuple(production_status[stage] for stage in PRODUCTION_STAGES)
            if all(value in {"completed", "skipped"} for value in stage_values):
                status = "completed"
            elif status == "draft" and any(value in {"completed", "skipped"} for value in stage_values):
                status = "in_progress"

        updated = {
            **current,
            "status": status,
            "production_status": production_status,
            "feedback": feedback,
            "updated_at": _now_iso(),
        }
        payload = validate_creator_execution_record(updated, expected_project_id=project_id)
        _write_json_atomic(path, payload)
        return payload


def execution_record_path(project_id: str) -> Path:
    project_id = _validated_project_id(project_id, ErrorCode.EXECUTION_RECORD_NOT_READY)
    return settings.creator_clones_dir / project_id / EXECUTION_RECORD_FILENAME


def validate_creator_execution_record(
    value: dict[str, Any] | None,
    *,
    expected_project_id: str = "",
) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    if not payload:
        raise ValueError("execution record must be a JSON object")

    version = str(payload.get("version") or "")
    if version != EXECUTION_RECORD_VERSION:
        raise ValueError(f"version must be {EXECUTION_RECORD_VERSION}")
    project_id = _safe_id(payload.get("project_id"))
    if expected_project_id and project_id != expected_project_id:
        raise ValueError("project_id does not match the requested project")
    pack_generated_at = _timezone_aware_timestamp(
        payload.get("execution_pack_generated_at"),
        "execution_pack_generated_at",
    )
    topic_index = _strict_integer(payload.get("execution_pack_topic_index"), "execution_pack_topic_index")
    if topic_index < 0:
        raise ValueError("execution_pack_topic_index must be non-negative")
    selected_topic = _safe_required_text(payload.get("selected_topic"), "selected_topic", 240)
    status = _enum_value(payload.get("status"), EXECUTION_RECORD_STATUSES, "status")

    raw_production = payload.get("production_status")
    if not isinstance(raw_production, dict):
        raise ValueError("production_status must be an object")
    production_status = {
        stage: _enum_value(raw_production.get(stage), PRODUCTION_STATUSES, f"production_status.{stage}")
        for stage in PRODUCTION_STAGES
    }

    raw_feedback = payload.get("feedback")
    if not isinstance(raw_feedback, dict):
        raise ValueError("feedback must be an object")
    was_used = raw_feedback.get("was_used")
    if not isinstance(was_used, bool):
        raise ValueError("feedback.was_used must be a boolean")
    difficulty = _enum_value(raw_feedback.get("difficulty", ""), DIFFICULTY_VALUES, "feedback.difficulty")
    raw_notes = raw_feedback.get("notes", "")
    if not isinstance(raw_notes, str):
        raise ValueError("feedback.notes must be a string")
    if len(raw_notes) > 1000:
        raise ValueError("feedback.notes must not exceed 1000 characters")
    feedback = {
        "was_used": was_used,
        "difficulty": difficulty,
        "quality_rating": _rating(raw_feedback.get("quality_rating"), "feedback.quality_rating"),
        "result_rating": _rating(raw_feedback.get("result_rating"), "feedback.result_rating"),
        "notes": _safe_text(raw_notes, 1000),
    }

    created_at = _timezone_aware_timestamp(payload.get("created_at"), "created_at")
    updated_at = _timezone_aware_timestamp(payload.get("updated_at"), "updated_at")
    return CreatorExecutionRecordV1(
        version=version,
        project_id=project_id,
        execution_pack_generated_at=pack_generated_at,
        execution_pack_topic_index=topic_index,
        selected_topic=selected_topic,
        status=status,
        production_status=production_status,
        feedback=feedback,
        created_at=created_at,
        updated_at=updated_at,
    ).to_dict()


def _load_record_file(path: Path, project_id: str) -> dict[str, Any]:
    if not path.is_file():
        raise AppError(ErrorCode.EXECUTION_RECORD_NOT_READY)
    try:
        if path.stat().st_size > EXECUTION_RECORD_MAX_JSON_BYTES:
            raise AppError(ErrorCode.EXECUTION_RECORD_NOT_READY)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return validate_creator_execution_record(payload, expected_project_id=project_id)
    except AppError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise AppError(ErrorCode.EXECUTION_RECORD_NOT_READY) from error


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


def _validated_project_id(value: Any, error_code: str) -> str:
    original = str(value or "")
    try:
        candidate = _safe_id(original)
    except ValueError as error:
        raise AppError(error_code) from error
    if candidate != original:
        raise AppError(error_code)
    return candidate


def _safe_id(value: Any) -> str:
    candidate = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", candidate):
        raise ValueError("identifier contains unsupported characters")
    return candidate


def _safe_required_text(value: Any, field_name: str, limit: int) -> str:
    raw = str(value or "")
    if not raw.strip():
        raise ValueError(f"{field_name} is required")
    if len(raw) > limit:
        raise ValueError(f"{field_name} exceeds {limit} characters")
    text = _safe_text(raw, limit)
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _safe_text(value: Any, limit: int) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", str(value or ""))
    text = re.sub(r"https?://[^\s)\]}>]+", "[redacted-url]", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<!\w)/(?:Users|home|private|var|tmp|Volumes)/[^\s,;，。]+", "[redacted-path]", text)
    text = re.sub(r"[A-Za-z]:\\(?:Users|Documents and Settings)\\[^\s,;，。]+", "[redacted-path]", text)
    text = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+", "[redacted]", text)
    text = re.sub(r"(?i)\bsk-[A-Za-z0-9_-]{8,}", "[redacted]", text)
    text = re.sub(
        r"(?i)\b(?:authorization|cookie|api[_ -]?key|sessionid|sid_tt|uid_tt|ttwid|odin_tt|passport_csrf_token)\b\s*[:=]?\s*[^\s,;，。]*",
        "[redacted]",
        text,
    )
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _strict_integer(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _rating(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    rating = _strict_integer(value, field_name)
    if rating < 1 or rating > 5:
        raise ValueError(f"{field_name} must be between 1 and 5")
    return rating


def _enum_value(value: Any, allowed: frozenset[str], field_name: str) -> str:
    candidate = str(value or "")
    if candidate not in allowed:
        raise ValueError(f"{field_name} contains an unsupported value")
    return candidate


def _timezone_aware_timestamp(value: Any, field_name: str) -> str:
    raw = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.isoformat()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
