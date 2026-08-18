from __future__ import annotations

import ipaddress
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import parse_qsl, urlsplit
from uuid import uuid4

from app.config import settings
from app.errors import AppError, ErrorCode
from app.services.creator_intelligence.execution_pack import load_creator_execution_pack
from app.services.creator_intelligence.execution_record import load_creator_execution_record


OUTCOME_TIMELINE_VERSION = "1.0"
OUTCOME_TIMELINE_FILENAME = "creator_outcome_snapshots.json"
OUTCOME_TIMELINE_MAX_JSON_BYTES = 512 * 1024
OUTCOME_MAX_SNAPSHOTS = 64
OUTCOME_PLATFORMS = frozenset({"douyin", "xhs", "bili", "other"})
OUTCOME_METRIC_FIELDS = ("views", "likes", "comments", "shares", "collects")
OUTCOME_INTERACTION_FIELDS = ("likes", "comments", "shares", "collects")
OUTCOME_SNAPSHOT_SOURCE = "manual"
_OUTCOME_LOCK = Lock()
_SENSITIVE_QUERY_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "cookie",
        "expires",
        "odin_tt",
        "passport_csrf_token",
        "sessionid",
        "sig",
        "sign",
        "signature",
        "sid_tt",
        "token",
        "ttwid",
        "uid_tt",
        "wssecret",
        "wstime",
        "x-amz-credential",
        "x-amz-security-token",
        "x-amz-signature",
        "xsec_token",
    }
)
_SIGNED_MEDIA_HOST_SUFFIXES = ("365yg.com", "douyinvod.com")


@dataclass(frozen=True)
class CreatorOutcomeSnapshotV1:
    snapshot_id: str
    captured_at: str
    source: str
    metrics: dict[str, int | None]
    derived: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "captured_at": self.captured_at,
            "source": self.source,
            "metrics": dict(self.metrics),
            "derived": {
                **self.derived,
                "delta_from_previous": dict(self.derived.get("delta_from_previous") or {}),
            },
        }


@dataclass(frozen=True)
class CreatorOutcomeTimelineV1:
    version: str
    project_id: str
    execution_record_created_at: str
    execution_pack_generated_at: str
    execution_pack_topic_index: int
    selected_topic: str
    expected_metric: str
    publication: dict[str, Any]
    snapshots: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]
    summary: dict[str, Any]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        latest_derived = self.summary.get("latest_derived") or {}
        return {
            "version": self.version,
            "project_id": self.project_id,
            "execution_record_created_at": self.execution_record_created_at,
            "execution_pack_generated_at": self.execution_pack_generated_at,
            "execution_pack_topic_index": self.execution_pack_topic_index,
            "selected_topic": self.selected_topic,
            "expected_metric": self.expected_metric,
            "publication": dict(self.publication),
            "snapshots": [dict(snapshot) for snapshot in self.snapshots],
            "warnings": list(self.warnings),
            "summary": {
                **self.summary,
                "latest_metrics": dict(self.summary.get("latest_metrics") or {}),
                "latest_derived": (
                    {
                        **latest_derived,
                        "delta_from_previous": dict(latest_derived.get("delta_from_previous") or {}),
                    }
                    if latest_derived
                    else {}
                ),
            },
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def upsert_creator_outcome_timeline(project_id: str, publication: dict[str, Any]) -> dict[str, Any]:
    project_id = _validated_project_id(project_id, ErrorCode.EXECUTION_RECORD_NOT_READY)
    normalized_publication = normalize_outcome_publication(publication)
    path = creator_outcome_timeline_path(project_id)
    with _OUTCOME_LOCK:
        if path.is_file():
            current = _load_outcome_file(path, project_id)
            updated = validate_creator_outcome_timeline(
                {
                    **current,
                    "publication": normalized_publication,
                    "updated_at": _now_iso(),
                },
                expected_project_id=project_id,
            )
            _write_json_atomic(path, updated)
            return updated

        execution_record = load_creator_execution_record(project_id)
        production_status = execution_record.get("production_status")
        publishing_status = production_status.get("publishing") if isinstance(production_status, dict) else None
        if publishing_status != "completed":
            raise AppError(ErrorCode.EXECUTION_NOT_PUBLISHED)

        expected_metric, warnings = _expected_metric_for_record(project_id, execution_record)
        now = _now_iso()
        outcome = validate_creator_outcome_timeline(
            {
                "version": OUTCOME_TIMELINE_VERSION,
                "project_id": project_id,
                "execution_record_created_at": execution_record.get("created_at"),
                "execution_pack_generated_at": execution_record.get("execution_pack_generated_at"),
                "execution_pack_topic_index": execution_record.get("execution_pack_topic_index"),
                "selected_topic": execution_record.get("selected_topic"),
                "expected_metric": expected_metric,
                "publication": normalized_publication,
                "snapshots": [],
                "warnings": warnings,
                "created_at": now,
                "updated_at": now,
            },
            expected_project_id=project_id,
        )
        _write_json_atomic(path, outcome)
        return outcome


def load_creator_outcome_timeline(project_id: str) -> dict[str, Any]:
    project_id = _validated_project_id(project_id, ErrorCode.OUTCOME_NOT_READY)
    return _load_outcome_file(creator_outcome_timeline_path(project_id), project_id)


def append_creator_outcome_snapshot(
    project_id: str,
    metrics: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    project_id = _validated_project_id(project_id, ErrorCode.OUTCOME_NOT_READY)
    path = creator_outcome_timeline_path(project_id)
    normalized_metrics = normalize_outcome_metrics(metrics)
    with _OUTCOME_LOCK:
        current = _load_outcome_file(path, project_id)
        if len(current["snapshots"]) >= OUTCOME_MAX_SNAPSHOTS:
            raise AppError(ErrorCode.OUTCOME_SNAPSHOT_LIMIT_REACHED)
        snapshot = {
            "snapshot_id": f"snapshot_{uuid4().hex}",
            "captured_at": _now_iso(),
            "source": OUTCOME_SNAPSHOT_SOURCE,
            "metrics": normalized_metrics,
            "derived": {},
        }
        updated = validate_creator_outcome_timeline(
            {
                **current,
                "snapshots": [*current["snapshots"], snapshot],
                "updated_at": _now_iso(),
            },
            expected_project_id=project_id,
        )
        _write_json_atomic(path, updated)
        created = next(
            item for item in updated["snapshots"] if item["snapshot_id"] == snapshot["snapshot_id"]
        )
        return created, updated


def update_creator_outcome_snapshot(
    project_id: str,
    snapshot_id: str,
    metric_changes: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    project_id = _validated_project_id(project_id, ErrorCode.OUTCOME_NOT_READY)
    snapshot_id = _validated_snapshot_id(snapshot_id)
    normalized_changes = normalize_outcome_metric_changes(metric_changes)
    path = creator_outcome_timeline_path(project_id)
    with _OUTCOME_LOCK:
        current = _load_outcome_file(path, project_id)
        found = False
        snapshots: list[dict[str, Any]] = []
        for item in current["snapshots"]:
            if item["snapshot_id"] != snapshot_id:
                snapshots.append(item)
                continue
            found = True
            snapshots.append(
                {
                    **item,
                    "metrics": {**item["metrics"], **normalized_changes},
                }
            )
        if not found:
            raise AppError(ErrorCode.OUTCOME_SNAPSHOT_NOT_FOUND)
        updated = validate_creator_outcome_timeline(
            {
                **current,
                "snapshots": snapshots,
                "updated_at": _now_iso(),
            },
            expected_project_id=project_id,
        )
        _write_json_atomic(path, updated)
        corrected = next(item for item in updated["snapshots"] if item["snapshot_id"] == snapshot_id)
        return corrected, updated


def creator_outcome_timeline_path(project_id: str) -> Path:
    project_id = _validated_project_id(project_id, ErrorCode.OUTCOME_NOT_READY)
    return settings.creator_clones_dir / project_id / OUTCOME_TIMELINE_FILENAME


def validate_creator_outcome_timeline(
    value: dict[str, Any] | None,
    *,
    expected_project_id: str = "",
) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    if not payload:
        raise ValueError("outcome timeline must be a JSON object")
    version = str(payload.get("version") or "")
    if version != OUTCOME_TIMELINE_VERSION:
        raise ValueError(f"version must be {OUTCOME_TIMELINE_VERSION}")
    project_id = _safe_id(payload.get("project_id"))
    if expected_project_id and project_id != expected_project_id:
        raise ValueError("project_id does not match the requested project")
    record_created_at = normalize_outcome_timestamp(
        payload.get("execution_record_created_at"),
        "execution_record_created_at",
    )
    pack_generated_at = normalize_outcome_timestamp(
        payload.get("execution_pack_generated_at"),
        "execution_pack_generated_at",
    )
    topic_index = _strict_integer(payload.get("execution_pack_topic_index"), "execution_pack_topic_index")
    if topic_index < 0:
        raise ValueError("execution_pack_topic_index must be non-negative")
    selected_topic = _safe_required_text(payload.get("selected_topic"), "selected_topic", 240)
    expected_metric = _safe_text(payload.get("expected_metric"), 240)
    publication = normalize_outcome_publication(payload.get("publication"))

    raw_snapshots = payload.get("snapshots")
    if not isinstance(raw_snapshots, list):
        raise ValueError("snapshots must be an array")
    if len(raw_snapshots) > OUTCOME_MAX_SNAPSHOTS:
        raise ValueError(f"snapshots must not exceed {OUTCOME_MAX_SNAPSHOTS}")
    snapshots = [_normalize_snapshot(item) for item in raw_snapshots]
    if len({item["snapshot_id"] for item in snapshots}) != len(snapshots):
        raise ValueError("snapshot_id values must be unique")
    snapshots.sort(key=lambda item: datetime.fromisoformat(item["captured_at"]))
    normalized_snapshots: list[dict[str, Any]] = []
    previous_metrics: dict[str, int | None] | None = None
    for item in snapshots:
        normalized = CreatorOutcomeSnapshotV1(
            snapshot_id=item["snapshot_id"],
            captured_at=item["captured_at"],
            source=OUTCOME_SNAPSHOT_SOURCE,
            metrics=item["metrics"],
            derived=_derive_outcome_metrics(item["metrics"], previous_metrics),
        ).to_dict()
        normalized_snapshots.append(normalized)
        previous_metrics = item["metrics"]

    raw_warnings = payload.get("warnings")
    if not isinstance(raw_warnings, list):
        raise ValueError("warnings must be an array")
    warnings: list[str] = []
    for warning in raw_warnings[:10]:
        normalized_warning = _safe_text(warning, 240)
        if normalized_warning and normalized_warning not in warnings:
            warnings.append(normalized_warning)
    created_at = normalize_outcome_timestamp(payload.get("created_at"), "created_at")
    updated_at = normalize_outcome_timestamp(payload.get("updated_at"), "updated_at")
    summary = _outcome_summary(normalized_snapshots, expected_metric)
    return CreatorOutcomeTimelineV1(
        version=version,
        project_id=project_id,
        execution_record_created_at=record_created_at,
        execution_pack_generated_at=pack_generated_at,
        execution_pack_topic_index=topic_index,
        selected_topic=selected_topic,
        expected_metric=expected_metric,
        publication=publication,
        snapshots=tuple(normalized_snapshots),
        warnings=tuple(warnings),
        summary=summary,
        created_at=created_at,
        updated_at=updated_at,
    ).to_dict()


def validate_creator_outcome_snapshot(
    value: dict[str, Any] | None,
    *,
    previous_metrics: dict[str, int | None] | None = None,
) -> dict[str, Any]:
    item = _normalize_snapshot(value)
    return CreatorOutcomeSnapshotV1(
        snapshot_id=item["snapshot_id"],
        captured_at=item["captured_at"],
        source=OUTCOME_SNAPSHOT_SOURCE,
        metrics=item["metrics"],
        derived=_derive_outcome_metrics(item["metrics"], previous_metrics),
    ).to_dict()


def normalize_outcome_publication(value: dict[str, Any] | None) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    platform = str(payload.get("platform") or "douyin")
    if platform not in OUTCOME_PLATFORMS:
        raise ValueError("publication.platform contains an unsupported value")
    item_id = _safe_text(payload.get("platform_item_id"), 160)
    published_url = normalize_outcome_publication_url(payload.get("published_url"))
    published_at = normalize_optional_outcome_timestamp(payload.get("published_at"), "publication.published_at")
    return {
        "platform": platform,
        "platform_item_id": item_id,
        "published_url": published_url,
        "published_at": published_at,
    }


def normalize_outcome_publication_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) > 2048:
        raise ValueError("publication.published_url exceeds 2048 characters")
    if "\\" in raw or any(ord(character) < 32 for character in raw):
        raise ValueError("publication.published_url contains unsupported characters")
    parsed = urlsplit(raw)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("publication.published_url must be an HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("publication.published_url must not include credentials")
    try:
        parsed.port
    except ValueError as error:
        raise ValueError("publication.published_url contains an invalid port") from error
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local")):
        raise ValueError("publication.published_url must use a public host")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("publication.published_url must use a public host")
    if any(host == suffix or host.endswith(f".{suffix}") for suffix in _SIGNED_MEDIA_HOST_SUFFIXES):
        raise ValueError("publication.published_url must not be a signed media URL")
    for key, _item in parse_qsl(parsed.query, keep_blank_values=True):
        if key.strip().lower() in _SENSITIVE_QUERY_KEYS:
            raise ValueError("publication.published_url must not include credential or signature parameters")
    if re.search(
        r"(?i)(?:\bbearer\b|\bsk-[A-Za-z0-9_-]{8,}|\b(?:authorization|cookie|api[_ -]?key|login[_ -]?state)\b\s*[:=])",
        raw,
    ):
        raise ValueError("publication.published_url must not include credentials")
    return raw


def normalize_optional_outcome_timestamp(value: Any, field_name: str) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return normalize_outcome_timestamp(value, field_name)


def normalize_outcome_timestamp(value: Any, field_name: str) -> str:
    raw = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.isoformat()


def normalize_outcome_metrics(value: dict[str, Any] | None) -> dict[str, int | None]:
    payload = value if isinstance(value, dict) else {}
    return {field: _metric_value(payload.get(field), f"metrics.{field}") for field in OUTCOME_METRIC_FIELDS}


def normalize_outcome_metric_changes(value: dict[str, Any] | None) -> dict[str, int | None]:
    payload = value if isinstance(value, dict) else {}
    return {
        field: _metric_value(payload[field], f"metrics.{field}")
        for field in OUTCOME_METRIC_FIELDS
        if field in payload
    }


def _normalize_snapshot(value: dict[str, Any] | None) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    snapshot_id = _safe_snapshot_id(payload.get("snapshot_id"))
    captured_at = normalize_outcome_timestamp(payload.get("captured_at"), "snapshot.captured_at")
    if payload.get("source") != OUTCOME_SNAPSHOT_SOURCE:
        raise ValueError(f"snapshot.source must be {OUTCOME_SNAPSHOT_SOURCE}")
    return {
        "snapshot_id": snapshot_id,
        "captured_at": captured_at,
        "source": OUTCOME_SNAPSHOT_SOURCE,
        "metrics": normalize_outcome_metrics(payload.get("metrics")),
    }


def _derive_outcome_metrics(
    metrics: dict[str, int | None],
    previous_metrics: dict[str, int | None] | None,
) -> dict[str, Any]:
    known_interactions = [metrics[field] for field in OUTCOME_INTERACTION_FIELDS if metrics[field] is not None]
    views = metrics["views"]

    def rate(field: str) -> float | None:
        value = metrics[field]
        return value / views if views is not None and views > 0 and value is not None else None

    delta = {
        field: (
            metrics[field] - previous_metrics[field]
            if previous_metrics is not None
            and metrics[field] is not None
            and previous_metrics[field] is not None
            else None
        )
        for field in OUTCOME_METRIC_FIELDS
    }
    return {
        "known_interactions": sum(known_interactions),
        "known_interaction_metric_count": len(known_interactions),
        "engagement_rate": (
            sum(known_interactions) / views
            if views is not None and views > 0 and len(known_interactions) == len(OUTCOME_INTERACTION_FIELDS)
            else None
        ),
        "like_rate": rate("likes"),
        "comment_rate": rate("comments"),
        "share_rate": rate("shares"),
        "collect_rate": rate("collects"),
        "delta_from_previous": delta,
    }


def _outcome_summary(snapshots: list[dict[str, Any]], expected_metric: str) -> dict[str, Any]:
    latest = snapshots[-1] if snapshots else None
    return {
        "snapshot_count": len(snapshots),
        "latest_snapshot_id": latest.get("snapshot_id") if latest else "",
        "latest_captured_at": latest.get("captured_at") if latest else None,
        "latest_metrics": dict(latest.get("metrics") or {}) if latest else {},
        "latest_derived": dict(latest.get("derived") or {}) if latest else {},
        "expected_metric": expected_metric,
    }


def _expected_metric_for_record(project_id: str, record: dict[str, Any]) -> tuple[str, list[str]]:
    try:
        execution_pack = load_creator_execution_pack(project_id)
    except AppError:
        return "", ["execution_pack_unavailable_for_expected_metric"]
    pack_matches = (
        execution_pack.get("generated_at") == record.get("execution_pack_generated_at")
        and execution_pack.get("topic_index") == record.get("execution_pack_topic_index")
    )
    if not pack_matches:
        return "", ["execution_pack_changed_since_record"]
    topic = execution_pack.get("topic") if isinstance(execution_pack.get("topic"), dict) else {}
    return _safe_text(topic.get("expected_metric"), 240), []


def _load_outcome_file(path: Path, project_id: str) -> dict[str, Any]:
    if not path.is_file():
        raise AppError(ErrorCode.OUTCOME_NOT_READY)
    try:
        if path.stat().st_size > OUTCOME_TIMELINE_MAX_JSON_BYTES:
            raise AppError(ErrorCode.OUTCOME_NOT_READY)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return validate_creator_outcome_timeline(payload, expected_project_id=project_id)
    except AppError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise AppError(ErrorCode.OUTCOME_NOT_READY) from error


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    serialized = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(serialized) > OUTCOME_TIMELINE_MAX_JSON_BYTES:
        raise AppError(ErrorCode.OUTCOME_STORAGE_LIMIT_REACHED)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(serialized)
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


def _validated_snapshot_id(value: Any) -> str:
    try:
        return _safe_snapshot_id(value)
    except ValueError as error:
        raise AppError(ErrorCode.OUTCOME_SNAPSHOT_NOT_FOUND) from error


def _safe_snapshot_id(value: Any) -> str:
    candidate = str(value or "")
    if not re.fullmatch(r"snapshot_[0-9a-f]{32}", candidate):
        raise ValueError("snapshot_id contains unsupported characters")
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
        r"(?i)\b(?:authorization|cookie|api[_ -]?key|login[_ -]?state|sessionid|sid_tt|uid_tt|ttwid|odin_tt|passport_csrf_token)\b\s*[:=]?\s*[^\s,;，。]*",
        "[redacted]",
        text,
    )
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _metric_value(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    number = _strict_integer(value, field_name)
    if number < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return number


def _strict_integer(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
