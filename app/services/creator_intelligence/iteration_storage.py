from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterator

from app.config import settings
from app.errors import AppError, ErrorCode


ITERATION_INDEX_VERSION = "1.0"
ITERATION_INDEX_FILENAME = "creator_iterations.json"
ITERATION_INDEX_MAX_BYTES = 256 * 1024
ITERATION_MAX_COUNT = 128
LEGACY_ITERATION_ID = "iteration_legacy_001"
ITERATION_DIRECTORY_NAME = "iterations"
ITERATION_ARTIFACT_FILENAMES = frozenset(
    {
        "creator_execution_pack.json",
        "creator_execution_record.json",
        "creator_outcome_snapshots.json",
    }
)
ITERATION_STORAGE_MODES = frozenset({"legacy_root", "iteration_dir"})
ITERATION_STATES = frozenset({"active", "closed"})
ITERATION_CLOSE_REASONS = frozenset(
    {
        "",
        "execution_completed",
        "execution_archived",
        "cancelled",
        "superseded",
        "not_published",
        "other",
    }
)

_PROJECT_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,120}")
_ITERATION_ID_RE = re.compile(r"iteration_[0-9a-f]{32}")
_SENSITIVE_TEXT_RE = re.compile(
    r"(?i)\b(cookie|authorization|api[_ -]?key|sessionid|sid_guard|sid_tt|ttwid|uid_tt|odin_tt|token)\b"
    r"\s*[:=]\s*(?:bearer\s+)?[^\s,;]+"
)
_BEARER_TEXT_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_OPENAI_KEY_RE = re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{8,}")
_URL_TEXT_RE = re.compile(r"(?i)https?://[^\s,;，。]+")
_ABSOLUTE_PATH_RE = re.compile(
    r"(?<!\w)(?:/(?:Users|home|private|var|tmp|Volumes)/[^\s,;，。]+|[A-Za-z]:\\Users\\[^\s,;，。]+)"
)
_CONTROL_TEXT_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ITERATION_LOCK = RLock()


@dataclass(frozen=True)
class IterationStorageContext:
    project_id: str
    iteration_id: str
    sequence: int
    storage_mode: str
    base_dir: Path
    is_legacy: bool
    is_current: bool
    index_updated_at: str


def validate_project_id(value: Any) -> str:
    candidate = str(value or "").strip()
    if not _PROJECT_ID_RE.fullmatch(candidate):
        raise AppError(ErrorCode.ITERATION_INDEX_INVALID)
    return candidate


def validate_iteration_id(value: Any, *, allow_legacy: bool = True) -> str:
    candidate = str(value or "").strip()
    if allow_legacy and candidate == LEGACY_ITERATION_ID:
        return candidate
    if not _ITERATION_ID_RE.fullmatch(candidate):
        raise AppError(ErrorCode.ITERATION_NOT_FOUND)
    return candidate


def creator_project_path(project_id: str) -> Path:
    project_id = validate_project_id(project_id)
    root = Path(settings.creator_clones_dir)
    _reject_symlink(root, allow_missing=True)
    project_dir = root / project_id
    _reject_symlink(project_dir, allow_missing=True)
    if project_dir.exists() and not project_dir.is_dir():
        raise AppError(ErrorCode.ITERATION_INDEX_INVALID)
    return project_dir


def creator_iteration_index_path(project_id: str) -> Path:
    return creator_project_path(project_id) / ITERATION_INDEX_FILENAME


def validate_creator_iteration_index(
    value: dict[str, Any] | None,
    *,
    expected_project_id: str,
) -> dict[str, Any]:
    project_id = validate_project_id(expected_project_id)
    payload = value if isinstance(value, dict) else {}
    if str(payload.get("version") or "") != ITERATION_INDEX_VERSION:
        raise ValueError(f"version must be {ITERATION_INDEX_VERSION}")
    if str(payload.get("project_id") or "") != project_id:
        raise ValueError("project_id does not match the requested project")

    raw_iterations = payload.get("iterations")
    if not isinstance(raw_iterations, list):
        raise ValueError("iterations must be a list")
    if len(raw_iterations) > ITERATION_MAX_COUNT:
        raise ValueError("iteration limit exceeded")

    iterations = [_validate_iteration_ref(item) for item in raw_iterations]
    ids = [item["iteration_id"] for item in iterations]
    sequences = [item["sequence"] for item in iterations]
    if len(ids) != len(set(ids)):
        raise ValueError("iteration_id must be unique")
    if len(sequences) != len(set(sequences)):
        raise ValueError("sequence must be unique")
    if sequences != sorted(sequences):
        raise ValueError("iterations must be ordered by sequence")

    current_iteration_id = str(payload.get("current_iteration_id") or "")
    active = [item for item in iterations if item["state"] == "active"]
    if len(active) > 1:
        raise ValueError("only one active iteration is allowed")
    if current_iteration_id:
        current = next((item for item in iterations if item["iteration_id"] == current_iteration_id), None)
        if current is None:
            raise ValueError("current_iteration_id must reference an iteration")
        if current["state"] != "active" or len(active) != 1:
            raise ValueError("current_iteration_id must reference the only active iteration")
    elif active:
        raise ValueError("an active iteration requires current_iteration_id")
    for item in iterations:
        if item["iteration_id"] != current_iteration_id and item["state"] != "closed":
            raise ValueError("all non-current iterations must be closed")

    created_at = _timezone_aware_timestamp(payload.get("created_at"), "created_at")
    updated_at = _timezone_aware_timestamp(payload.get("updated_at"), "updated_at")
    return {
        "version": ITERATION_INDEX_VERSION,
        "project_id": project_id,
        "current_iteration_id": current_iteration_id,
        "iterations": iterations,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def read_creator_iteration_index(project_id: str) -> dict[str, Any] | None:
    project_id = validate_project_id(project_id)
    path = creator_iteration_index_path(project_id)
    if not path.exists():
        return None
    _require_regular_file(path)
    try:
        if path.stat().st_size > ITERATION_INDEX_MAX_BYTES:
            raise AppError(ErrorCode.ITERATION_INDEX_INVALID)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return validate_creator_iteration_index(payload, expected_project_id=project_id)
    except AppError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise AppError(ErrorCode.ITERATION_INDEX_INVALID) from error


def virtual_iteration_index(project_id: str) -> dict[str, Any]:
    project_id = validate_project_id(project_id)
    persisted = read_creator_iteration_index(project_id)
    if persisted is not None:
        return persisted
    if not legacy_artifacts_exist(project_id):
        return {
            "version": ITERATION_INDEX_VERSION,
            "project_id": project_id,
            "current_iteration_id": "",
            "iterations": [],
            "created_at": "",
            "updated_at": "",
            "virtual": True,
        }
    created_at, inferred = infer_legacy_created_at(project_id)
    return {
        "version": ITERATION_INDEX_VERSION,
        "project_id": project_id,
        "current_iteration_id": LEGACY_ITERATION_ID,
        "iterations": [
            {
                "iteration_id": LEGACY_ITERATION_ID,
                "sequence": 1,
                "storage_mode": "legacy_root",
                "state": "active",
                "created_at": created_at,
                "closed_at": "",
                "close_reason": "",
                "close_note": "",
                "legacy_created_at_inferred": inferred,
            }
        ],
        "created_at": created_at,
        "updated_at": "",
        "virtual": True,
    }


def legacy_artifacts_exist(project_id: str) -> bool:
    project_dir = creator_project_path(project_id)
    found = False
    for filename in ITERATION_ARTIFACT_FILENAMES:
        path = project_dir / filename
        if path.is_symlink():
            raise AppError(ErrorCode.ITERATION_INDEX_INVALID)
        if path.exists():
            if not path.is_file():
                raise AppError(ErrorCode.ITERATION_INDEX_INVALID)
            found = True
    return found


def infer_legacy_created_at(project_id: str) -> tuple[str, bool]:
    project_dir = creator_project_path(project_id)
    timestamps: list[datetime] = []
    timestamp_fields = {
        "creator_execution_pack.json": ("generated_at",),
        "creator_execution_record.json": ("created_at",),
        "creator_outcome_snapshots.json": ("created_at",),
    }
    for filename, fields in timestamp_fields.items():
        path = project_dir / filename
        if not path.exists() or path.is_symlink() or not path.is_file():
            continue
        try:
            if path.stat().st_size > 512 * 1024:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        for field in fields:
            parsed = _parse_timestamp(payload.get(field))
            if parsed is not None:
                timestamps.append(parsed)
    if timestamps:
        return min(timestamps).astimezone(timezone.utc).isoformat(), False
    return _now_iso(), True


def resolve_current_iteration_context(project_id: str) -> IterationStorageContext:
    project_id = validate_project_id(project_id)
    index = read_creator_iteration_index(project_id)
    project_dir = creator_project_path(project_id)
    if index is None:
        revision = "virtual-legacy" if legacy_artifacts_exist(project_id) else "virtual-empty"
        return IterationStorageContext(
            project_id=project_id,
            iteration_id=LEGACY_ITERATION_ID,
            sequence=1,
            storage_mode="legacy_root",
            base_dir=project_dir,
            is_legacy=True,
            is_current=True,
            index_updated_at=revision,
        )
    current_id = index["current_iteration_id"]
    if not current_id:
        raise AppError(ErrorCode.ITERATION_INDEX_INVALID, "迭代索引没有可写的当前轮次。")
    ref = next(item for item in index["iterations"] if item["iteration_id"] == current_id)
    return _context_from_ref(project_id, ref, current_id=current_id, revision=index["updated_at"])


def resolve_iteration_context(project_id: str, iteration_id: str) -> IterationStorageContext:
    project_id = validate_project_id(project_id)
    iteration_id = validate_iteration_id(iteration_id)
    index = read_creator_iteration_index(project_id)
    if index is None:
        if iteration_id != LEGACY_ITERATION_ID or not legacy_artifacts_exist(project_id):
            raise AppError(ErrorCode.ITERATION_NOT_FOUND)
        return IterationStorageContext(
            project_id=project_id,
            iteration_id=LEGACY_ITERATION_ID,
            sequence=1,
            storage_mode="legacy_root",
            base_dir=creator_project_path(project_id),
            is_legacy=True,
            is_current=True,
            index_updated_at="virtual-legacy",
        )
    ref = next((item for item in index["iterations"] if item["iteration_id"] == iteration_id), None)
    if ref is None:
        raise AppError(ErrorCode.ITERATION_NOT_FOUND)
    return _context_from_ref(
        project_id,
        ref,
        current_id=index["current_iteration_id"],
        revision=index["updated_at"],
    )


def iteration_artifact_path(context: IterationStorageContext, filename: str) -> Path:
    if filename not in ITERATION_ARTIFACT_FILENAMES:
        raise AppError(ErrorCode.ITERATION_ARTIFACT_INVALID)
    _reject_symlink(context.base_dir, allow_missing=True)
    if context.base_dir.exists() and not context.base_dir.is_dir():
        raise AppError(ErrorCode.ITERATION_INDEX_INVALID)
    path = context.base_dir / filename
    if path.is_symlink():
        raise AppError(ErrorCode.ITERATION_ARTIFACT_INVALID)
    return path


def assert_iteration_context_current(context: IterationStorageContext) -> None:
    try:
        current = resolve_current_iteration_context(context.project_id)
    except AppError as error:
        if error.code == ErrorCode.ITERATION_INDEX_INVALID:
            raise
        raise AppError(ErrorCode.ITERATION_CONTEXT_CHANGED) from error
    identity = (
        context.iteration_id,
        context.sequence,
        context.storage_mode,
        context.index_updated_at,
    )
    current_identity = (
        current.iteration_id,
        current.sequence,
        current.storage_mode,
        current.index_updated_at,
    )
    if identity != current_identity:
        raise AppError(ErrorCode.ITERATION_CONTEXT_CHANGED)


@contextmanager
def iteration_write_lock() -> Iterator[None]:
    with _ITERATION_LOCK:
        yield


def write_creator_iteration_index(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    project_id = validate_project_id(project_id)
    try:
        validated = validate_creator_iteration_index(payload, expected_project_id=project_id)
    except ValueError as error:
        raise AppError(ErrorCode.ITERATION_INDEX_INVALID) from error
    encoded = (json.dumps(validated, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(encoded) > ITERATION_INDEX_MAX_BYTES:
        raise AppError(ErrorCode.ITERATION_INDEX_INVALID)

    path = creator_iteration_index_path(project_id)
    project_dir = path.parent
    _reject_symlink(project_dir, allow_missing=True)
    project_dir.mkdir(parents=True, exist_ok=True)
    _reject_symlink(project_dir)
    if not project_dir.is_dir():
        raise AppError(ErrorCode.ITERATION_INDEX_INVALID)
    if path.is_symlink():
        raise AppError(ErrorCode.ITERATION_INDEX_INVALID)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=project_dir,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.replace(temporary_path, path)
        _fsync_directory(project_dir)
    except OSError as error:
        raise AppError(ErrorCode.ITERATION_INDEX_INVALID) from error
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)
    return validated


def new_index_payload(project_id: str, iterations: list[dict[str, Any]], current_iteration_id: str) -> dict[str, Any]:
    now = _now_iso()
    return {
        "version": ITERATION_INDEX_VERSION,
        "project_id": validate_project_id(project_id),
        "current_iteration_id": current_iteration_id,
        "iterations": iterations,
        "created_at": now,
        "updated_at": now,
    }


def _context_from_ref(
    project_id: str,
    ref: dict[str, Any],
    *,
    current_id: str,
    revision: str,
) -> IterationStorageContext:
    project_dir = creator_project_path(project_id)
    storage_mode = ref["storage_mode"]
    if storage_mode == "legacy_root":
        base_dir = project_dir
    else:
        iterations_dir = project_dir / ITERATION_DIRECTORY_NAME
        _reject_symlink(iterations_dir, allow_missing=True)
        if iterations_dir.exists() and not iterations_dir.is_dir():
            raise AppError(ErrorCode.ITERATION_INDEX_INVALID)
        base_dir = iterations_dir / ref["iteration_id"]
        _reject_symlink(base_dir, allow_missing=True)
        if base_dir.exists() and not base_dir.is_dir():
            raise AppError(ErrorCode.ITERATION_INDEX_INVALID)
    return IterationStorageContext(
        project_id=project_id,
        iteration_id=ref["iteration_id"],
        sequence=ref["sequence"],
        storage_mode=storage_mode,
        base_dir=base_dir,
        is_legacy=storage_mode == "legacy_root",
        is_current=ref["iteration_id"] == current_id,
        index_updated_at=revision,
    )


def _validate_iteration_ref(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("iteration ref must be an object")
    iteration_id = str(value.get("iteration_id") or "")
    storage_mode = str(value.get("storage_mode") or "")
    if storage_mode not in ITERATION_STORAGE_MODES:
        raise ValueError("unsupported storage_mode")
    if storage_mode == "legacy_root":
        if iteration_id != LEGACY_ITERATION_ID:
            raise ValueError("legacy_root requires the fixed legacy iteration ID")
    elif not _ITERATION_ID_RE.fullmatch(iteration_id):
        raise ValueError("iteration_dir requires a safe iteration ID")

    sequence = value.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence <= 0:
        raise ValueError("sequence must be a positive integer")
    state = str(value.get("state") or "")
    if state not in ITERATION_STATES:
        raise ValueError("unsupported state")
    created_at = _timezone_aware_timestamp(value.get("created_at"), "created_at")
    closed_at_raw = str(value.get("closed_at") or "")
    close_reason = str(value.get("close_reason") or "")
    if close_reason not in ITERATION_CLOSE_REASONS:
        raise ValueError("unsupported close_reason")
    if state == "active":
        if closed_at_raw or close_reason or value.get("close_note"):
            raise ValueError("active iteration cannot be closed")
        closed_at = ""
    else:
        closed_at = _timezone_aware_timestamp(closed_at_raw, "closed_at")
        if not close_reason:
            raise ValueError("closed iteration requires close_reason")
    close_note = sanitize_close_note(value.get("close_note"))
    return {
        "iteration_id": iteration_id,
        "sequence": sequence,
        "storage_mode": storage_mode,
        "state": state,
        "created_at": created_at,
        "closed_at": closed_at,
        "close_reason": close_reason,
        "close_note": close_note,
        "legacy_created_at_inferred": bool(value.get("legacy_created_at_inferred", False)),
    }


def sanitize_close_note(value: Any) -> str:
    raw = str(value or "")
    if len(raw) > 500:
        raise ValueError("close_note must not exceed 500 characters")
    cleaned = _CONTROL_TEXT_RE.sub(" ", raw)
    cleaned = _SENSITIVE_TEXT_RE.sub("[redacted]", cleaned)
    cleaned = _BEARER_TEXT_RE.sub("[redacted]", cleaned)
    cleaned = _OPENAI_KEY_RE.sub("[redacted]", cleaned)
    cleaned = _URL_TEXT_RE.sub("[redacted-url]", cleaned)
    cleaned = _ABSOLUTE_PATH_RE.sub("[redacted-path]", cleaned)
    return " ".join(cleaned.split())[:500]


def _timezone_aware_timestamp(value: Any, field_name: str) -> str:
    parsed = _parse_timestamp(value)
    if parsed is None:
        raise ValueError(f"{field_name} must be a timezone-aware ISO-8601 timestamp")
    return parsed.isoformat()


def _parse_timestamp(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reject_symlink(path: Path, *, allow_missing: bool = False) -> None:
    if path.is_symlink():
        raise AppError(ErrorCode.ITERATION_INDEX_INVALID)
    if not allow_missing and not path.exists():
        raise AppError(ErrorCode.ITERATION_INDEX_INVALID)


def _require_regular_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise AppError(ErrorCode.ITERATION_INDEX_INVALID)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)
