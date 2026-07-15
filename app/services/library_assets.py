from __future__ import annotations

import json
import os
import re
import sqlite3
import time as monotonic_time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import quote

from sqlalchemy.engine import make_url

from app.config import settings
from app.services.workbench_tasks import WorkbenchResumeTarget


ASSET_TYPES = ("case", "creator_report", "strategy_plan")
ASSET_STATUSES = ("ready", "incomplete", "missing", "stale")
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
MAX_CASE_ROWS = 2_000
MAX_CREATOR_DIRECTORIES = 2_000
MAX_CREATOR_SCAN_ENTRIES = 10_000
MAX_RUNTIME_ENTRIES = 2_000
MAX_RUNTIME_INDEX_BYTES = 4 * 1024 * 1024
MAX_SAMPLE_SET_BYTES = 1024 * 1024
MAX_RESULT_BYTES = 2 * 1024 * 1024
MAX_STRATEGY_BYTES = 1024 * 1024
MAX_PRESENTATION_BYTES = 8 * 1024 * 1024
CASE_METADATA_BUDGET_BYTES = 24 * 1024 * 1024
CREATOR_METADATA_BUDGET_BYTES = 64 * 1024 * 1024
SQLITE_PROGRESS_CALLBACK_STEPS = 1_000
SQLITE_PROGRESS_CALLBACK_LIMIT = 20_000
LIBRARY_CACHE_SECONDS = 30
LIBRARY_CACHE_MAX_ENTRIES = 8

SAFE_ASSET_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
SAFE_CASE_ID = re.compile(r"^case_[A-Za-z0-9_-]{1,94}$")
SAFE_CREATOR_ID = re.compile(r"^clone_[A-Za-z0-9_-]{1,94}$")
HTTP_URL = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:\\[^\s,;]+|(?<![:\w])/(?!/)[^\s,;]+)")
SECRET_VALUE = re.compile(
    r"(?i)(?:authorization|api[_ -]?key|cookie|access[_ -]?token|refresh[_ -]?token)\s*[:=]\s*[^\s,;]+"
)
AUTHORIZATION_VALUE = re.compile(
    r"(?i)\bauthorization\s*[:=]\s*(?:bearer\s+)?[^\s,;]+"
)
QUOTED_SECRET_VALUE = re.compile(
    r'''(?ix)
    ["']?(?:authorization|api[_ -]?key|cookie|access[_ -]?token|refresh[_ -]?token)["']?
    \s*[:=]\s*
    (?:"[^"]*"|'[^']*'|[^\s,;}\]]+)
    '''
)
BEARER_VALUE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
OPENAI_STYLE_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b", re.IGNORECASE)

CASE_FILES = (
    "video.mp4",
    "metadata.json",
    "qualities.json",
    "ffprobe.json",
    "analysis_input.json",
    "prompt.md",
    "contact_sheet.jpg",
    "analysis_result.json",
    "analysis_report.md",
    "worksheet.json",
    "analysis_brief.md",
)
CASE_ENRICHMENT_FILES = (
    "enrichment/manifest.json",
    "enrichment/asr/transcript.json",
    "enrichment/ocr/frame_ocr.json",
    "enrichment/ocr/subtitle_ocr.json",
    "enrichment/ocr/cover_ocr.json",
    "enrichment/comments/comment_summary.json",
    "enrichment/metrics/snapshots.jsonl",
)
CASE_AVAILABLE_DIRECTORIES = ("keyframes/", "enrichment/")
CASE_CORE_FILES = frozenset(
    {
        "video.mp4",
        "metadata.json",
        "ffprobe.json",
        "analysis_input.json",
        "prompt.md",
    }
)
CREATOR_FILES = (
    "samples.json",
    "creator_clone_result.json",
    "creator_clone.html",
    "creator_clone.md",
    "distill_prompt.md",
)
PLATFORMS = frozenset({"douyin", "xhs", "bili", "local", "manual", "unknown"})


@dataclass(frozen=True)
class LibraryAsset:
    asset_id: str
    asset_type: str
    title: str
    creator_name: str = ""
    platform: str = "unknown"
    status: str = "incomplete"
    created_at: str = ""
    updated_at: str = ""
    quality_score: float | int | None = None
    confidence: str = ""
    sample_count: int = 0
    selected_count: int = 0
    open_url: str = ""
    resume_target: WorkbenchResumeTarget = field(default_factory=WorkbenchResumeTarget)
    available_files: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        asset_id = self.asset_id if SAFE_ASSET_ID.fullmatch(self.asset_id) else ""
        asset_type = self.asset_type if self.asset_type in ASSET_TYPES else "case"
        status = self.status if self.status in ASSET_STATUSES else "incomplete"
        target = self.resume_target
        resume_target = WorkbenchResumeTarget(
            route=target.route,
            stage=_safe_public_text(target.stage, 40),
            resource_id=target.resource_id if SAFE_ASSET_ID.fullmatch(target.resource_id) else "",
            job_id="",
            task_type=_safe_public_text(target.task_type, 40),
            mode=target.mode,
            open_url=_safe_internal_url(target.open_url),
        ).to_dict()
        return {
            "asset_id": asset_id,
            "asset_type": asset_type,
            "title": _safe_public_text(self.title, 180) or "未命名资产",
            "creator_name": _safe_public_text(self.creator_name, 120),
            "platform": _safe_platform(self.platform),
            "status": status,
            "created_at": _iso_datetime(self.created_at),
            "updated_at": _iso_datetime(self.updated_at),
            "quality_score": _safe_score(self.quality_score),
            "confidence": _safe_public_text(self.confidence, 40),
            "sample_count": _safe_count(self.sample_count),
            "selected_count": _safe_count(self.selected_count),
            "open_url": _safe_internal_url(self.open_url),
            "resume_target": resume_target,
            "available_files": [
                value
                for value in self.available_files
                if value in CASE_FILES
                or value in CASE_ENRICHMENT_FILES
                or value in CASE_AVAILABLE_DIRECTORIES
                or value in CREATOR_FILES
                or value == "creator_strategy_plan.json"
            ],
        }


@dataclass
class _Diagnostics:
    errors: dict[str, str] = field(default_factory=dict)
    truncated_sources: set[str] = field(default_factory=set)

    def add_error(self, source: str, message: str) -> None:
        self.errors.setdefault(source, message)

    def truncate(self, source: str) -> None:
        self.truncated_sources.add(source)


@dataclass(frozen=True)
class _LibraryIndexSnapshot:
    assets: tuple[LibraryAsset, ...]
    errors: tuple[tuple[str, str], ...]
    truncated_sources: tuple[str, ...]


_LIBRARY_CACHE: dict[tuple[Any, ...], tuple[float, _LibraryIndexSnapshot]] = {}
_LIBRARY_CACHE_LOCK = Lock()


@dataclass
class _BoundedReader:
    remaining_bytes: int
    diagnostics: _Diagnostics

    def json_object(self, path: Path, *, max_bytes: int, source: str) -> tuple[dict[str, Any], str]:
        if path.is_symlink():
            self.diagnostics.add_error(source, "部分符号链接元数据已被安全拒绝。")
            return {}, "symlink"
        try:
            stat = path.stat()
        except FileNotFoundError:
            return {}, "missing"
        except OSError:
            self.diagnostics.add_error(source, "部分元数据暂时不可读取。")
            return {}, "unreadable"
        if not path.is_file():
            return {}, "missing"
        if stat.st_size > max_bytes:
            self.diagnostics.truncate(source)
            return {}, "oversized"
        if stat.st_size > self.remaining_bytes:
            self.diagnostics.truncate(source)
            return {}, "budget_exhausted"
        self.remaining_bytes -= stat.st_size
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            self.diagnostics.add_error(source, "部分 JSON 元数据损坏，其他资产仍可浏览。")
            return {}, "invalid"
        if not isinstance(payload, dict):
            self.diagnostics.add_error(source, "部分 JSON 元数据结构无效，其他资产仍可浏览。")
            return {}, "invalid"
        return payload, "ok"


def _safe_public_text(value: Any, max_length: int = 240) -> str:
    text = str(value or "").replace("\x00", " ").strip()
    text = AUTHORIZATION_VALUE.sub("[授权信息已隐藏]", text)
    text = QUOTED_SECRET_VALUE.sub("[敏感配置已隐藏]", text)
    text = SECRET_VALUE.sub("[敏感配置已隐藏]", text)
    text = BEARER_VALUE.sub("[授权信息已隐藏]", text)
    text = OPENAI_STYLE_KEY.sub("[API Key 已隐藏]", text)
    text = HTTP_URL.sub("[外部链接]", text)
    text = ABSOLUTE_PATH.sub("[本地路径]", text)
    return " ".join(text.split())[:max_length]


def _safe_platform(value: Any) -> str:
    candidate = str(value or "unknown").strip().lower()
    return candidate if candidate in PLATFORMS else "unknown"


def _safe_count(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, min(int(value or 0), 1_000_000))
    except (TypeError, ValueError, OverflowError):
        return 0


def _safe_score(value: Any) -> float | int | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        score = max(0.0, min(float(value), 100.0))
    except (TypeError, ValueError, OverflowError):
        return None
    return int(score) if score.is_integer() else round(score, 2)


def _iso_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        current = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return ""
        try:
            current = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat()


def _mtime_iso(path: Path) -> str:
    if path.is_symlink():
        return ""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    except (FileNotFoundError, OSError):
        return ""


def _newest_datetime(*values: Any) -> str:
    normalized = [_iso_datetime(value) for value in values]
    return max((value for value in normalized if value), default="")


def _safe_internal_url(value: Any) -> str:
    candidate = str(value or "").strip()
    if re.fullmatch(r"/cases/case_[A-Za-z0-9_-]{1,94}", candidate):
        return candidate
    if re.fullmatch(
        r"/api/creator-clone/sets/clone_[A-Za-z0-9_-]{1,94}/files/creator_clone\.(?:html|md)",
        candidate,
    ):
        return candidate
    return ""


def _sqlite_database_path(database_url: str) -> Path:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise RuntimeError("library requires a local SQLite source")
    raw_path = Path(url.database).expanduser()
    if raw_path.is_symlink():
        raise RuntimeError("library database symlinks are not allowed")
    path = raw_path.resolve()
    if not path.is_file():
        raise RuntimeError("library database is unavailable")
    return path


def _path_fingerprint(path: Path) -> tuple[int, int]:
    try:
        stat = path.lstat()
    except OSError:
        return (-1, -1)
    return (stat.st_mtime_ns, stat.st_size)


def _database_fingerprint(database_url: str) -> tuple[int, int]:
    try:
        return _path_fingerprint(_sqlite_database_path(database_url))
    except Exception:
        return (-1, -1)


def _readonly_connection(database_url: str) -> sqlite3.Connection:
    path = _sqlite_database_path(database_url)
    connection = sqlite3.connect(f"file:{quote(str(path), safe='/')}?mode=ro", uri=True, timeout=0.5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA busy_timeout=500")
    callback_count = 0

    def progress_guard() -> int:
        nonlocal callback_count
        callback_count += 1
        return int(callback_count > SQLITE_PROGRESS_CALLBACK_LIMIT)

    connection.set_progress_handler(progress_guard, SQLITE_PROGRESS_CALLBACK_STEPS)
    return connection


def _safe_root(root: Path, diagnostics: _Diagnostics, source: str) -> Path | None:
    if root.is_symlink():
        diagnostics.add_error(source, "资产根目录为符号链接，已安全拒绝。")
        return None
    try:
        resolved = root.resolve()
    except OSError:
        diagnostics.add_error(source, "资产根目录暂时不可读取。")
        return None
    if not resolved.exists():
        return None
    if not resolved.is_dir():
        diagnostics.add_error(source, "资产根目录结构无效。")
        return None
    return resolved


def _safe_child_directory(root: Path, resource_id: str, diagnostics: _Diagnostics, source: str) -> Path | None:
    raw = root / resource_id
    if raw.is_symlink():
        diagnostics.add_error(source, "部分符号链接资产已被安全拒绝。")
        return None
    try:
        resolved = raw.resolve()
    except OSError:
        diagnostics.add_error(source, "部分资产目录暂时不可读取。")
        return None
    if resolved.parent != root:
        diagnostics.add_error(source, "部分越界资产目录已被安全拒绝。")
        return None
    return resolved


def _safe_file_exists(path: Path, diagnostics: _Diagnostics, source: str) -> bool:
    if path.is_symlink():
        diagnostics.add_error(source, "部分符号链接产物已被安全拒绝。")
        return False
    try:
        return path.is_file()
    except OSError:
        diagnostics.add_error(source, "部分产物状态暂时不可读取。")
        return False


def _safe_bounded_file_exists(
    path: Path,
    diagnostics: _Diagnostics,
    source: str,
    *,
    max_bytes: int,
) -> bool:
    if not _safe_file_exists(path, diagnostics, source):
        return False
    try:
        if path.stat().st_size > max_bytes:
            diagnostics.truncate(source)
            return False
    except OSError:
        diagnostics.add_error(source, "部分产物状态暂时不可读取。")
        return False
    return True


def _safe_directory_exists(path: Path, diagnostics: _Diagnostics, source: str) -> bool:
    if path.is_symlink():
        diagnostics.add_error(source, "部分符号链接产物目录已被安全拒绝。")
        return False
    try:
        return path.is_dir()
    except OSError:
        diagnostics.add_error(source, "部分产物目录状态暂时不可读取。")
        return False


def _case_quality(payload: dict[str, Any]) -> tuple[float | int | None, str]:
    review = payload.get("quality_review") if isinstance(payload.get("quality_review"), dict) else {}
    overview = payload.get("sample_overview") if isinstance(payload.get("sample_overview"), dict) else {}
    score = review.get("quality_score", review.get("score"))
    confidence = overview.get("confidence") or payload.get("confidence") or review.get("confidence")
    return _safe_score(score), _safe_public_text(confidence, 40)


def _creator_quality(payload: dict[str, Any]) -> tuple[float | int | None, str]:
    review = payload.get("report_quality") if isinstance(payload.get("report_quality"), dict) else {}
    overview = payload.get("sample_overview") if isinstance(payload.get("sample_overview"), dict) else {}
    score = review.get("quality_score", review.get("score"))
    confidence = overview.get("confidence") or review.get("confidence") or payload.get("confidence")
    return _safe_score(score), _safe_public_text(confidence, 40)


def _collect_case_assets(
    database_url: str,
    cases_dir: Path,
    diagnostics: _Diagnostics,
) -> list[LibraryAsset]:
    root = _safe_root(cases_dir, diagnostics, "cases")
    reader = _BoundedReader(CASE_METADATA_BUDGET_BYTES, diagnostics)
    with _readonly_connection(database_url) as connection:
        rows = connection.execute(
            """
            SELECT
                c.case_id,
                c.aweme_id,
                c.local_video_id,
                c.status,
                c.created_at,
                COALESCE(NULLIF(d.title, ''), NULLIF(l.title, ''), '') AS title,
                COALESCE(NULLIF(d.author, ''), NULLIF(l.author, ''), '') AS author
            FROM case_artifacts AS c
            LEFT JOIN douyin_video_items AS d ON d.aweme_id = c.aweme_id
            LEFT JOIN local_video_items AS l ON l.local_video_id = c.local_video_id
            ORDER BY c.created_at DESC
            LIMIT ?
            """,
            (MAX_CASE_ROWS + 1,),
        ).fetchall()
    if len(rows) > MAX_CASE_ROWS:
        diagnostics.truncate("cases")
        rows = rows[:MAX_CASE_ROWS]

    assets: list[LibraryAsset] = []
    for row in rows:
        case_id = str(row["case_id"] or "").strip()
        if not SAFE_CASE_ID.fullmatch(case_id):
            diagnostics.add_error("cases", "部分非法 Case 标识已被安全跳过。")
            continue
        case_dir = _safe_child_directory(root, case_id, diagnostics, "cases") if root else None
        available: list[str] = []
        mtimes: list[str] = []
        if case_dir and _safe_directory_exists(case_dir, diagnostics, "cases"):
            for relative_name in CASE_FILES:
                path = case_dir / relative_name
                if _safe_file_exists(path, diagnostics, "cases"):
                    available.append(relative_name)
                    mtimes.append(_mtime_iso(path))
            if _safe_directory_exists(case_dir / "keyframes", diagnostics, "cases"):
                available.append("keyframes/")
                mtimes.append(_mtime_iso(case_dir / "keyframes"))
            enrichment_dir = case_dir / "enrichment"
            if _safe_directory_exists(enrichment_dir, diagnostics, "cases"):
                available.append("enrichment/")
                mtimes.append(_mtime_iso(enrichment_dir))
                for relative_name in CASE_ENRICHMENT_FILES:
                    path = case_dir / relative_name
                    if _safe_file_exists(path, diagnostics, "cases"):
                        available.append(relative_name)
                        mtimes.append(_mtime_iso(path))
        available_set = set(available)
        if not case_dir or not _safe_directory_exists(case_dir, diagnostics, "cases") or not {"video.mp4", "metadata.json"} <= available_set:
            status = "missing"
        elif not CASE_CORE_FILES <= available_set or str(row["status"] or "").lower() not in {"success", "ready"}:
            status = "incomplete"
        else:
            status = "ready"

        quality_score = None
        confidence = ""
        if case_dir and "analysis_result.json" in available_set:
            analysis_result, _state = reader.json_object(
                case_dir / "analysis_result.json",
                max_bytes=MAX_RESULT_BYTES,
                source="cases",
            )
            quality_score, confidence = _case_quality(analysis_result)
        created_at = _iso_datetime(row["created_at"])
        updated_at = _newest_datetime(created_at, *mtimes)
        platform = "douyin" if str(row["aweme_id"] or "") else "local"
        open_url = f"/cases/{case_id}"
        assets.append(
            LibraryAsset(
                asset_id=case_id,
                asset_type="case",
                title=_safe_public_text(row["title"], 180) or f"单作品 {case_id[-6:]}",
                creator_name=_safe_public_text(row["author"], 120),
                platform=platform,
                status=status,
                created_at=created_at,
                updated_at=updated_at,
                quality_score=quality_score,
                confidence=confidence,
                open_url=open_url,
                resume_target=WorkbenchResumeTarget(
                    route="single",
                    stage="case",
                    resource_id=case_id,
                    task_type="case_asset",
                    mode="result",
                    open_url=open_url,
                ),
                available_files=tuple(available),
            )
        )
    return assets


def _runtime_entries(
    creator_state_dir: Path,
    diagnostics: _Diagnostics,
) -> dict[str, dict[str, str]]:
    root = _safe_root(creator_state_dir, diagnostics, "creator_runtime")
    if not root:
        return {}
    reader = _BoundedReader(MAX_RUNTIME_INDEX_BYTES, diagnostics)
    payload, state = reader.json_object(
        root / "sessions.json",
        max_bytes=MAX_RUNTIME_INDEX_BYTES,
        source="creator_runtime",
    )
    if state != "ok":
        return {}
    raw_sessions = payload.get("sessions")
    if isinstance(raw_sessions, dict):
        values = list(raw_sessions.values())
    elif isinstance(raw_sessions, list):
        values = raw_sessions
    else:
        diagnostics.add_error("creator_runtime", "Creator Runtime 索引结构无效。")
        return {}
    values.sort(key=lambda item: str(item.get("updated_at") or "") if isinstance(item, dict) else "", reverse=True)
    if len(values) > MAX_RUNTIME_ENTRIES:
        diagnostics.truncate("creator_runtime")
        values = values[:MAX_RUNTIME_ENTRIES]
    result: dict[str, dict[str, str]] = {}
    for item in values:
        if not isinstance(item, dict):
            continue
        resource_id = str(item.get("project_id") or item.get("session_id") or "").strip()
        if not SAFE_CREATOR_ID.fullmatch(resource_id):
            continue
        result[resource_id] = {
            "state": _safe_public_text(item.get("state"), 40).upper(),
            "updated_at": _iso_datetime(item.get("updated_at")),
        }
    return result


def _creator_directories(
    creator_clones_dir: Path,
    diagnostics: _Diagnostics,
) -> tuple[Path | None, dict[str, str]]:
    root = _safe_root(creator_clones_dir, diagnostics, "creator_assets")
    if not root:
        return None, {}
    candidates: list[tuple[float, str]] = []
    try:
        iterator = os.scandir(root)
    except OSError:
        diagnostics.add_error("creator_assets", "Creator 资产目录暂时不可读取。")
        return root, {}
    with iterator:
        for index, entry in enumerate(iterator):
            if index >= MAX_CREATOR_SCAN_ENTRIES:
                diagnostics.truncate("creator_assets")
                break
            try:
                if entry.is_symlink():
                    diagnostics.add_error("creator_assets", "部分符号链接 Creator 资产已被安全拒绝。")
                    continue
                if not entry.is_dir(follow_symlinks=False):
                    continue
                resource_id = str(entry.name or "")
                if not SAFE_CREATOR_ID.fullmatch(resource_id):
                    diagnostics.add_error("creator_assets", "部分非法 Creator 标识已被安全跳过。")
                    continue
                candidates.append((entry.stat(follow_symlinks=False).st_mtime, resource_id))
            except OSError:
                diagnostics.add_error("creator_assets", "部分 Creator 资产状态暂时不可读取。")
    candidates.sort(reverse=True)
    if len(candidates) > MAX_CREATOR_DIRECTORIES:
        diagnostics.truncate("creator_assets")
        candidates = candidates[:MAX_CREATOR_DIRECTORIES]
    return root, {
        resource_id: datetime.fromtimestamp(mtime, timezone.utc).isoformat()
        for mtime, resource_id in candidates
    }


def _creator_asset_id(resource_id: str, suffix: str) -> str:
    candidate = f"{resource_id}_{suffix}"
    return candidate if SAFE_ASSET_ID.fullmatch(candidate) else ""


def _creator_summary(payload: dict[str, Any], resource_id: str) -> dict[str, Any]:
    samples = payload.get("samples") if isinstance(payload.get("samples"), list) else []
    selected = payload.get("selected_sample_ids") if isinstance(payload.get("selected_sample_ids"), list) else []
    return {
        "title": _safe_public_text(payload.get("title"), 180) or f"创作者资产 {resource_id[-6:]}",
        "creator_name": _safe_public_text(payload.get("creator_name"), 120),
        "platform": _safe_platform(payload.get("source_platform")),
        "sample_count": _safe_count(payload.get("sample_count") or len(samples)),
        "selected_count": _safe_count(payload.get("selected_count") or len(selected)),
        "created_at": _iso_datetime(payload.get("created_at")),
    }


def _collect_creator_assets(
    creator_state_dir: Path,
    creator_clones_dir: Path,
    diagnostics: _Diagnostics,
) -> list[LibraryAsset]:
    runtime = _runtime_entries(creator_state_dir, diagnostics)
    root, directories = _creator_directories(creator_clones_dir, diagnostics)
    reader = _BoundedReader(CREATOR_METADATA_BUDGET_BYTES, diagnostics)
    directory_ids = sorted(
        directories,
        key=lambda resource_id: directories.get(resource_id, ""),
        reverse=True,
    )
    runtime_only_done_ids = sorted(
        (
            resource_id
            for resource_id, entry in runtime.items()
            if resource_id not in directories and str(entry.get("state") or "").upper() == "DONE"
        ),
        key=lambda resource_id: runtime[resource_id].get("updated_at", ""),
        reverse=True,
    )
    ordered_ids = [*directory_ids, *runtime_only_done_ids]

    assets: list[LibraryAsset] = []
    for resource_id in ordered_ids:
        clone_dir = _safe_child_directory(root, resource_id, diagnostics, "creator_assets") if root and resource_id in directories else None
        directory_ready = bool(clone_dir and _safe_directory_exists(clone_dir, diagnostics, "creator_assets"))
        samples_payload: dict[str, Any] = {}
        samples_state = "missing"
        if directory_ready:
            samples_payload, samples_state = reader.json_object(
                clone_dir / "samples.json",
                max_bytes=MAX_SAMPLE_SET_BYTES,
                source="creator_assets",
            )
        creator_context_restorable = directory_ready and samples_state == "ok"
        summary = _creator_summary(samples_payload, resource_id)
        runtime_entry = runtime.get(resource_id, {})
        runtime_state = str(runtime_entry.get("state") or "").upper()
        report_available: list[str] = []
        report_mtimes: list[str] = []
        report_core_mtimes: list[str] = []
        if directory_ready:
            for filename in CREATOR_FILES:
                path = clone_dir / filename
                max_bytes = MAX_PRESENTATION_BYTES if filename.endswith((".html", ".md")) else MAX_RESULT_BYTES
                if _safe_bounded_file_exists(
                    path,
                    diagnostics,
                    "creator_assets",
                    max_bytes=max_bytes,
                ):
                    report_available.append(filename)
                    file_mtime = _mtime_iso(path)
                    report_mtimes.append(file_mtime)
                    if filename in {"creator_clone_result.json", "creator_clone.html", "creator_clone.md"}:
                        report_core_mtimes.append(file_mtime)
        report_files = set(report_available)
        has_result = "creator_clone_result.json" in report_files
        has_presentation = bool({"creator_clone.html", "creator_clone.md"} & report_files)
        report_expected = runtime_state == "DONE"
        report_exists = bool(report_files & {"creator_clone_result.json", "creator_clone.html", "creator_clone.md"})

        result_payload: dict[str, Any] = {}
        result_state = "missing"
        if directory_ready and has_result:
            result_payload, result_state = reader.json_object(
                clone_dir / "creator_clone_result.json",
                max_bytes=MAX_RESULT_BYTES,
                source="creator_assets",
            )
        quality_score, confidence = _creator_quality(result_payload)
        report_updated_at = _newest_datetime(runtime_entry.get("updated_at"), *report_mtimes)
        report_created_at = summary["created_at"] or directories.get(resource_id, "")

        if report_exists or report_expected:
            if not report_exists:
                report_status = "missing"
            elif has_result and has_presentation and result_state == "ok" and samples_state == "ok":
                report_status = "ready"
            else:
                report_status = "incomplete"
            open_url = ""
            if "creator_clone.html" in report_files:
                open_url = f"/api/creator-clone/sets/{resource_id}/files/creator_clone.html"
            elif "creator_clone.md" in report_files:
                open_url = f"/api/creator-clone/sets/{resource_id}/files/creator_clone.md"
            assets.append(
                LibraryAsset(
                    asset_id=_creator_asset_id(resource_id, "report"),
                    asset_type="creator_report",
                    title=summary["title"],
                    creator_name=summary["creator_name"],
                    platform=summary["platform"],
                    status=report_status,
                    created_at=report_created_at,
                    updated_at=report_updated_at,
                    quality_score=quality_score,
                    confidence=confidence,
                    sample_count=summary["sample_count"],
                    selected_count=summary["selected_count"],
                    open_url=open_url,
                    resume_target=(
                        WorkbenchResumeTarget(
                            route="profile",
                            stage="export",
                            resource_id=resource_id,
                            task_type="creator_report",
                            mode="result",
                            open_url=open_url,
                        )
                        if creator_context_restorable
                        else WorkbenchResumeTarget()
                    ),
                    available_files=tuple(report_available),
                )
            )

        strategy_path = clone_dir / "creator_strategy_plan.json" if directory_ready else None
        has_strategy = bool(strategy_path and _safe_file_exists(strategy_path, diagnostics, "creator_assets"))
        if not has_strategy:
            continue
        strategy_payload, strategy_state = reader.json_object(
            strategy_path,
            max_bytes=MAX_STRATEGY_BYTES,
            source="creator_assets",
        )
        strategy_mtime = _mtime_iso(strategy_path)
        source_payload = strategy_payload.get("source") if isinstance(strategy_payload.get("source"), dict) else {}
        strategy_score = _safe_score(source_payload.get("report_quality_score"))
        low_confidence_notes = strategy_payload.get("low_confidence_notes")
        strategy_confidence = "low" if isinstance(low_confidence_notes, list) and low_confidence_notes else confidence
        if strategy_state != "ok" or not has_result:
            strategy_status = "incomplete"
        elif result_state != "ok":
            strategy_status = "incomplete"
        elif report_core_mtimes and strategy_mtime and strategy_mtime < max(report_core_mtimes):
            strategy_status = "stale"
        else:
            strategy_status = "ready"
        strategy_files = ["creator_strategy_plan.json"]
        if has_result:
            strategy_files.append("creator_clone_result.json")
        assets.append(
            LibraryAsset(
                asset_id=_creator_asset_id(resource_id, "strategy"),
                asset_type="strategy_plan",
                title=summary["title"],
                creator_name=summary["creator_name"],
                platform=summary["platform"],
                status=strategy_status,
                created_at=report_created_at,
                updated_at=strategy_mtime,
                quality_score=strategy_score if strategy_score is not None else quality_score,
                confidence=strategy_confidence,
                sample_count=summary["sample_count"],
                selected_count=summary["selected_count"],
                resume_target=(
                    WorkbenchResumeTarget(
                        route="profile",
                        stage="export",
                        resource_id=resource_id,
                        task_type="creator_strategy",
                        mode="result",
                    )
                    if creator_context_restorable
                    else WorkbenchResumeTarget()
                ),
                available_files=tuple(strategy_files),
            )
        )
    return assets


def _asset_matches_date(asset: dict[str, Any], date_from: date | None, date_to: date | None) -> bool:
    if date_from is None and date_to is None:
        return True
    raw = asset.get("updated_at") or asset.get("created_at")
    try:
        current = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return False
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    lower = datetime.combine(date_from, time.min, tzinfo=timezone.utc) if date_from else None
    upper = datetime.combine(date_to, time.max, tzinfo=timezone.utc) if date_to else None
    return not ((lower and current < lower) or (upper and current > upper))


def _build_library_index(
    database_url: str,
    cases_dir_value: str,
    creator_state_dir_value: str,
    creator_clones_dir_value: str,
) -> _LibraryIndexSnapshot:
    diagnostics = _Diagnostics()
    assets: list[LibraryAsset] = []
    try:
        assets.extend(
            _collect_case_assets(
                database_url,
                Path(cases_dir_value),
                diagnostics,
            )
        )
    except Exception:
        diagnostics.add_error("cases", "Case 索引暂时不可用，其他资产仍可浏览。")
    try:
        assets.extend(
            _collect_creator_assets(
                Path(creator_state_dir_value),
                Path(creator_clones_dir_value),
                diagnostics,
            )
        )
    except Exception:
        diagnostics.add_error("creator_assets", "Creator 资产索引暂时不可用，Case 仍可浏览。")
    return _LibraryIndexSnapshot(
        assets=tuple(assets),
        errors=tuple(sorted(diagnostics.errors.items())),
        truncated_sources=tuple(sorted(diagnostics.truncated_sources)),
    )


def build_library_assets(
    *,
    asset_type: str = "",
    status: str = "",
    query: str = "",
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    database_url: str | None = None,
    cases_dir: Path | None = None,
    creator_state_dir: Path | None = None,
    creator_clones_dir: Path | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    database_url_value = database_url or settings.database_url
    cases_path = Path(cases_dir or settings.cases_dir)
    creator_state_path = Path(creator_state_dir or settings.creator_state_dir)
    creator_clones_path = Path(creator_clones_dir or settings.creator_clones_dir)
    cache_key = (
        database_url_value,
        str(cases_path),
        str(creator_state_path),
        str(creator_clones_path),
        _database_fingerprint(database_url_value),
        _path_fingerprint(cases_path),
        _path_fingerprint(creator_state_path / "sessions.json"),
        _path_fingerprint(creator_clones_path),
    )
    now = monotonic_time.monotonic()
    with _LIBRARY_CACHE_LOCK:
        cached_entry = _LIBRARY_CACHE.get(cache_key)
    if not refresh and cached_entry and now - cached_entry[0] < LIBRARY_CACHE_SECONDS:
        snapshot = cached_entry[1]
    else:
        snapshot = _build_library_index(
            database_url_value,
            str(cases_path),
            str(creator_state_path),
            str(creator_clones_path),
        )
        with _LIBRARY_CACHE_LOCK:
            if refresh:
                _LIBRARY_CACHE.clear()
            _LIBRARY_CACHE[cache_key] = (monotonic_time.monotonic(), snapshot)
            if len(_LIBRARY_CACHE) > LIBRARY_CACHE_MAX_ENTRIES:
                oldest_key = min(_LIBRARY_CACHE, key=lambda key: _LIBRARY_CACHE[key][0])
                _LIBRARY_CACHE.pop(oldest_key, None)

    items = [asset.to_dict() for asset in snapshot.assets if SAFE_ASSET_ID.fullmatch(asset.asset_id)]
    items.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
    facets = {
        "types": dict(Counter(item["asset_type"] for item in items)),
        "statuses": dict(Counter(item["status"] for item in items)),
    }
    normalized_query = _safe_public_text(query, 120).casefold()
    filtered = [
        item
        for item in items
        if (not asset_type or item["asset_type"] == asset_type)
        and (not status or item["status"] == status)
        and (
            not normalized_query
            or normalized_query in item["title"].casefold()
            or normalized_query in item["creator_name"].casefold()
            or normalized_query in item["asset_id"].casefold()
        )
        and _asset_matches_date(item, date_from, date_to)
    ]
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
    total = len(filtered)
    start = (safe_page - 1) * safe_page_size
    page_items = filtered[start:start + safe_page_size]
    source_errors = [
        {
            "source": source,
            "error_code": "LIBRARY_SOURCE_UNAVAILABLE",
            "message": _safe_public_text(message, 180),
        }
        for source, message in snapshot.errors
    ]
    truncated_sources = list(snapshot.truncated_sources)
    return {
        "items": page_items,
        "pagination": {
            "page": safe_page,
            "page_size": safe_page_size,
            "total": total,
            "has_next": start + safe_page_size < total,
        },
        "facets": facets,
        "source_errors": source_errors,
        "meta": {
            "partial": bool(source_errors or truncated_sources),
            "truncated_sources": truncated_sources,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "limits": {
                "max_page_size": MAX_PAGE_SIZE,
                "max_case_rows": MAX_CASE_ROWS,
                "max_creator_directories": MAX_CREATOR_DIRECTORIES,
            },
        },
    }
