from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from sqlalchemy.engine import make_url

from app.config import settings
from app.services.data_source_settings import douyin_source_health_payload
from app.services.llm_settings import llm_status_payload
from app.services.tool_preflight import local_tools_summary_payload


OVERVIEW_LIMIT = 5
CASE_QUERY_LIMIT = 30
RUNTIME_INDEX_MAX_BYTES = 4 * 1024 * 1024
RUNTIME_CANDIDATE_LIMIT = 50
SAMPLE_SET_MAX_BYTES = 2 * 1024 * 1024
SQLITE_PROGRESS_CALLBACK_STEPS = 1_000
SQLITE_PROGRESS_CALLBACK_LIMIT = 5_000
RUNNING_FRESH_SECONDS = 24 * 60 * 60

SAFE_RESOURCE_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
HTTP_URL = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:\\[^\s,;]+|(?<![:\w])/(?!/)[^\s,;]+)")
SECRET_VALUE = re.compile(
    r"(?i)(?:authorization|api[_ -]?key|cookie|access[_ -]?token|refresh[_ -]?token)\s*[:=]\s*[^\s,;]+"
)
AUTHORIZATION_VALUE = re.compile(
    r"(?i)\bauthorization\s*[:=]\s*(?:(?:bearer|basic|token)\s+)?[^\s,;]+"
)
BEARER_VALUE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
OPENAI_STYLE_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b", re.IGNORECASE)

JOB_META = {
    "build-case": ("生成素材包", "单作品", "single"),
    "resolve-qualities": ("解析清晰度", "单作品", "single"),
    "download": ("下载作品", "单作品", "single"),
    "download-and-build-case": ("下载并生成素材包", "单作品", "single"),
    "download-build-analyze-case": ("下载、素材包与拆解", "单作品", "single"),
    "analyze-case": ("单作品 AI 拆解", "单作品", "single"),
    "enrich-case": ("素材富化", "单作品", "single"),
    "asr-case": ("语音识别", "单作品", "single"),
    "ocr-case": ("画面文字识别", "单作品", "single"),
    "profile-scan": ("扫描创作者素材", "创作者", "profile"),
    "profile-build-cases": ("富化创作者样本", "创作者", "profile"),
    "creator-clone-distill": ("创作者蒸馏", "创作者", "profile"),
    "creator-clone-batch-distill": ("分批创作者蒸馏", "创作者", "profile"),
}

WORKFLOW_STAGE_META = {
    "IMPORT": ("导入素材", "import"),
    "INGESTED": ("构建素材池", "pool"),
    "SAMPLE_READY": ("选择代表样本", "select"),
    "SAMPLE_SELECTED": ("证据富化", "enrich"),
    "EVIDENCE_READY": ("大模型蒸馏", "distill"),
    "DISTILLING": ("大模型蒸馏", "distill"),
    "DONE": ("查看蒸馏报告", "export"),
}


class WorkbenchSourceError(RuntimeError):
    pass


def _safe_public_text(value: Any, max_length: int = 240) -> str:
    text = str(value or "").replace("\x00", " ").strip()
    text = AUTHORIZATION_VALUE.sub("[授权信息已隐藏]", text)
    text = BEARER_VALUE.sub("[授权信息已隐藏]", text)
    text = SECRET_VALUE.sub("[敏感配置已隐藏]", text)
    text = OPENAI_STYLE_KEY.sub("[API Key 已隐藏]", text)
    text = HTTP_URL.sub("[外部链接]", text)
    text = ABSOLUTE_PATH.sub("[本地路径]", text)
    text = " ".join(text.split())
    return text[:max_length]


def _safe_resource_id(value: Any) -> str:
    candidate = str(value or "").strip()
    return candidate if SAFE_RESOURCE_ID.fullmatch(candidate) else ""


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


def _sqlite_database_path(database_url: str) -> Path:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise WorkbenchSourceError("任务控制台只读取本机 SQLite 状态。")
    database_path = Path(url.database).expanduser().resolve()
    if not database_path.is_file():
        raise WorkbenchSourceError("本机任务数据库尚未创建。")
    return database_path


def _readonly_connection(database_url: str) -> sqlite3.Connection:
    database_path = _sqlite_database_path(database_url)
    uri = f"file:{quote(str(database_path), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=0.25)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA busy_timeout=250")
    callback_count = 0

    def progress_guard() -> int:
        nonlocal callback_count
        callback_count += 1
        return int(callback_count > SQLITE_PROGRESS_CALLBACK_LIMIT)

    connection.set_progress_handler(progress_guard, SQLITE_PROGRESS_CALLBACK_STEPS)
    return connection


def _job_payload(row: sqlite3.Row) -> dict[str, Any]:
    job_type = str(row["type"] or "")
    stage, task_group, route = JOB_META.get(job_type, ("后台任务", "系统", "workbench"))
    return {
        "task_id": _safe_resource_id(row["id"]),
        "task_type": _safe_public_text(job_type, 64),
        "task_group": task_group,
        "title": stage,
        "status": str(row["status"] or ""),
        "stage": stage,
        "progress": max(0, min(100, int(row["progress"] or 0))),
        "message": _safe_public_text(row["message"] or "任务状态已更新。"),
        "error_code": _safe_public_text(row["error_code"], 80),
        "created_at": _iso_datetime(row["created_at"]),
        "updated_at": _iso_datetime(row["updated_at"]),
        "target": {"route": route},
    }


def _collect_job_sections(database_url: str) -> tuple[list[dict], list[dict], int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=RUNNING_FRESH_SECONDS)).replace(tzinfo=None).isoformat(sep=" ")
    with _readonly_connection(database_url) as connection:
        running_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE status IN ('pending', 'running') AND updated_at >= ?",
                (cutoff,),
            ).fetchone()[0]
            or 0
        )
        running_rows = connection.execute(
            """
            SELECT id, type, status, progress, message, error_code, created_at, updated_at
            FROM jobs
            WHERE status IN ('pending', 'running') AND updated_at >= ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (cutoff, OVERVIEW_LIMIT),
        ).fetchall()
        failure_rows = connection.execute(
            """
            SELECT id, type, status, progress, message, error_code, created_at, updated_at
            FROM jobs
            WHERE status = 'failed'
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (OVERVIEW_LIMIT,),
        ).fetchall()
    return (
        [_job_payload(row) for row in running_rows],
        [_job_payload(row) for row in failure_rows],
        running_count,
    )


def _case_directory(cases_dir: Path, case_id: str) -> Path | None:
    safe_id = _safe_resource_id(case_id)
    if not safe_id:
        return None
    root = cases_dir.resolve()
    raw_candidate = root / safe_id
    if raw_candidate.is_symlink():
        return None
    candidate = raw_candidate.resolve()
    if candidate.parent != root:
        return None
    return candidate


def _collect_case_sections(database_url: str, cases_dir: Path) -> tuple[list[dict], list[dict]]:
    with _readonly_connection(database_url) as connection:
        rows = connection.execute(
            """
            SELECT
                c.case_id,
                c.status,
                c.created_at,
                COALESCE(NULLIF(l.title, ''), NULLIF(d.title, ''), '') AS title,
                COALESCE(NULLIF(l.author, ''), NULLIF(d.author, ''), '') AS author
            FROM case_artifacts AS c
            LEFT JOIN local_video_items AS l ON l.local_video_id = c.local_video_id
            LEFT JOIN douyin_video_items AS d ON d.aweme_id = c.aweme_id
            ORDER BY c.created_at DESC
            LIMIT ?
            """,
            (CASE_QUERY_LIMIT,),
        ).fetchall()

    recent_cases: list[dict] = []
    resumable: list[dict] = []
    for row in rows:
        case_id = _safe_resource_id(row["case_id"])
        if not case_id:
            continue
        case_dir = _case_directory(cases_dir, case_id)
        has_video = bool(case_dir and (case_dir / "video.mp4").is_file())
        has_analysis = bool(
            case_dir
            and ((case_dir / "analysis_result.json").is_file() or (case_dir / "analysis_report.md").is_file())
        )
        title = _safe_public_text(row["title"], 120) or _safe_public_text(row["author"], 120) or "未命名单作品"
        created_at = _iso_datetime(row["created_at"])
        status = str(row["status"] or "unknown")
        display_status = status if has_video else "missing"
        item = {
            "resource_id": case_id,
            "title": title,
            "type": "单作品 Case",
            "status": display_status,
            "updated_at": created_at,
            "open_url": f"/cases/{case_id}",
        }
        if len(recent_cases) < OVERVIEW_LIMIT:
            recent_cases.append(item)
        if has_video and not has_analysis and len(resumable) < OVERVIEW_LIMIT:
            resumable.append(
                {
                    "task_id": case_id,
                    "task_type": "single_work",
                    "title": title,
                    "status": "resumable",
                    "current_step": "素材包已生成，等待拆解",
                    "sample_count": 1,
                    "selected_count": 1,
                    "report_status": "未生成",
                    "updated_at": created_at,
                    "open_url": f"/cases/{case_id}",
                    "target": {"route": "single", "resource_id": case_id},
                }
            )
    return recent_cases, resumable


def _read_json_object(path: Path, max_bytes: int) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        if path.stat().st_size > max_bytes:
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_runtime_index(creator_state_dir: Path) -> tuple[list[dict[str, Any]], bool]:
    index_path = creator_state_dir.resolve() / "sessions.json"
    if not index_path.is_file():
        return [], False
    if index_path.is_symlink() or index_path.stat().st_size > RUNTIME_INDEX_MAX_BYTES:
        raise WorkbenchSourceError("Creator Runtime 索引不可安全读取。")
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkbenchSourceError("Creator Runtime 索引损坏。") from error
    sessions = payload.get("sessions") if isinstance(payload, dict) else {}
    if not isinstance(sessions, dict):
        raise WorkbenchSourceError("Creator Runtime 索引结构无效。")
    rows = [value for value in sessions.values() if isinstance(value, dict)]
    rows.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    truncated = len(rows) > RUNTIME_CANDIDATE_LIMIT
    return rows[:RUNTIME_CANDIDATE_LIMIT], truncated


def _safe_clone_directory(creator_clones_dir: Path, resource_id: str) -> Path | None:
    safe_id = _safe_resource_id(resource_id)
    if not safe_id:
        return None
    root = creator_clones_dir.resolve()
    raw_candidate = root / safe_id
    if raw_candidate.is_symlink():
        return None
    candidate = raw_candidate.resolve()
    if candidate.parent != root:
        return None
    return candidate


def _sample_set_summary(clone_dir: Path | None, resource_id: str) -> dict[str, Any]:
    payload = _read_json_object(clone_dir / "samples.json", SAMPLE_SET_MAX_BYTES) if clone_dir else {}
    title = _safe_public_text(payload.get("creator_name"), 120) or _safe_public_text(payload.get("title"), 120)
    samples = payload.get("samples")
    selected_ids = payload.get("selected_sample_ids")

    def safe_count(value: Any, fallback: int = 0) -> int:
        if isinstance(value, bool):
            return fallback
        try:
            count = int(value)
        except (TypeError, ValueError, OverflowError):
            return fallback
        return max(0, min(count, 1_000_000))

    return {
        "title": title or f"创作者任务 {resource_id[-6:]}",
        "sample_count": safe_count(
            payload.get("sample_count"),
            len(samples) if isinstance(samples, list) else 0,
        ),
        "selected_count": safe_count(
            payload.get("selected_count"),
            len(selected_ids) if isinstance(selected_ids, list) else 0,
        ),
    }


def _collect_creator_sections(
    creator_state_dir: Path,
    creator_clones_dir: Path,
) -> tuple[list[dict], list[dict], list[dict], bool]:
    index_rows, truncated = _read_runtime_index(creator_state_dir)
    resumable: list[dict] = []
    report_candidates: list[tuple[float, str, Path]] = []
    strategy_candidates: list[tuple[float, str, Path, str]] = []

    for entry in index_rows:
        resource_id = _safe_resource_id(entry.get("project_id") or entry.get("session_id"))
        if not resource_id:
            continue
        clone_dir = _safe_clone_directory(creator_clones_dir, resource_id)
        if not clone_dir:
            continue
        report_path = clone_dir / "creator_clone_result.json"
        strategy_path = clone_dir / "creator_strategy_plan.json"
        report_exists = report_path.is_file() and not report_path.is_symlink()
        report_mtime = report_path.stat().st_mtime if report_exists else 0.0
        strategy_exists = strategy_path.is_file() and not strategy_path.is_symlink()
        strategy_mtime = strategy_path.stat().st_mtime if strategy_exists else 0.0
        summary: dict[str, Any] | None = None

        if report_exists:
            report_candidates.append((report_mtime, resource_id, clone_dir))

        if strategy_exists and report_exists:
            strategy_candidates.append(
                (
                    strategy_mtime,
                    resource_id,
                    clone_dir,
                    "ready" if strategy_mtime >= report_mtime else "stale",
                )
            )

        state = str(entry.get("state") or "IMPORT").upper()
        if state == "DONE" and report_exists:
            continue
        if len(resumable) >= OVERVIEW_LIMIT:
            continue
        summary = summary or _sample_set_summary(clone_dir, resource_id)
        if state == "IMPORT" and summary["sample_count"] <= 0:
            continue
        step_label, stage = WORKFLOW_STAGE_META.get(state, ("继续创作者拆解", "import"))
        resumable.append(
            {
                "task_id": resource_id,
                "task_type": "creator_work",
                "title": summary["title"],
                "status": "resumable",
                "workflow_state": state,
                "current_step": step_label,
                "sample_count": summary["sample_count"],
                "selected_count": summary["selected_count"],
                "report_status": "已生成" if report_exists else "未生成",
                "updated_at": _iso_datetime(entry.get("updated_at")),
                "target": {"route": "profile", "resource_id": resource_id, "stage": stage},
            }
        )

    reports: list[dict] = []
    for report_mtime, resource_id, clone_dir in sorted(report_candidates, key=lambda pair: pair[0], reverse=True)[:OVERVIEW_LIMIT]:
        summary = _sample_set_summary(clone_dir, resource_id)
        open_url = ""
        if (clone_dir / "creator_clone.html").is_file() and not (clone_dir / "creator_clone.html").is_symlink():
            open_url = f"/api/creator-clone/sets/{resource_id}/files/creator_clone.html"
        elif (clone_dir / "creator_clone.md").is_file() and not (clone_dir / "creator_clone.md").is_symlink():
            open_url = f"/api/creator-clone/sets/{resource_id}/files/creator_clone.md"
        reports.append(
            {
                "resource_id": resource_id,
                "title": summary["title"],
                "type": "创作者蒸馏报告",
                "status": "ready",
                "updated_at": datetime.fromtimestamp(report_mtime, timezone.utc).isoformat(),
                "open_url": open_url,
                "target": {"route": "profile", "resource_id": resource_id, "stage": "export"},
            }
        )

    strategies: list[dict] = []
    for strategy_mtime, resource_id, clone_dir, status in sorted(
        strategy_candidates,
        key=lambda pair: pair[0],
        reverse=True,
    )[:OVERVIEW_LIMIT]:
        summary = _sample_set_summary(clone_dir, resource_id)
        strategies.append(
            {
                "resource_id": resource_id,
                "title": summary["title"],
                "type": "Creator Strategy Plan",
                "status": status,
                "updated_at": datetime.fromtimestamp(strategy_mtime, timezone.utc).isoformat(),
                "target": {"route": "profile", "resource_id": resource_id, "stage": "export"},
            }
        )
    return resumable, reports, strategies, truncated


def _source_error(source: str, message: str) -> dict[str, str]:
    return {
        "source": source,
        "error_code": "WORKBENCH_SOURCE_UNAVAILABLE",
        "message": _safe_public_text(message or "该数据源暂时不可用。"),
    }


def _unknown_capability(label: str) -> dict[str, Any]:
    return {"status": "unknown", "label": label, "configured": False}


def build_workbench_overview(
    *,
    database_url: str | None = None,
    cases_dir: Path | None = None,
    creator_state_dir: Path | None = None,
    creator_clones_dir: Path | None = None,
) -> dict[str, Any]:
    database_url = database_url or settings.database_url
    cases_dir = Path(cases_dir or settings.cases_dir)
    creator_state_dir = Path(creator_state_dir or settings.creator_state_dir)
    creator_clones_dir = Path(creator_clones_dir or settings.creator_clones_dir)

    running_tasks: list[dict] = []
    recent_failures: list[dict] = []
    recent_cases: list[dict] = []
    single_resumable: list[dict] = []
    creator_resumable: list[dict] = []
    recent_creator_reports: list[dict] = []
    recent_strategy_plans: list[dict] = []
    running_task_count = 0
    source_errors: list[dict] = []
    truncated_sources: list[str] = []

    try:
        running_tasks, recent_failures, running_task_count = _collect_job_sections(database_url)
    except Exception:
        source_errors.append(_source_error("jobs", "任务状态暂时不可用。"))

    try:
        recent_cases, single_resumable = _collect_case_sections(database_url, cases_dir)
    except Exception:
        source_errors.append(_source_error("cases", "Case 索引暂时不可用。"))

    try:
        creator_resumable, recent_creator_reports, recent_strategy_plans, creator_truncated = _collect_creator_sections(
            creator_state_dir,
            creator_clones_dir,
        )
        if creator_truncated:
            truncated_sources.append("creator_runtime")
    except Exception:
        source_errors.append(_source_error("creator_runtime", "创作者任务与报告索引暂时不可用。"))

    capabilities: dict[str, Any] = {
        "douyin_source": _unknown_capability("抖音数据源待确认"),
        "llm": _unknown_capability("LLM 状态待确认"),
        "preflight": {"status": "unknown", "ready_count": 0, "total_count": 0},
        "running_task_count": running_task_count,
    }
    try:
        douyin_source = douyin_source_health_payload()
        capabilities["douyin_source"] = {
            "configured": bool(douyin_source.get("configured")),
            "status": _safe_public_text(douyin_source.get("status"), 40),
            "label": _safe_public_text(douyin_source.get("label"), 80),
            "last_checked_at": _iso_datetime(douyin_source.get("last_checked_at")),
            "status_message": _safe_public_text(douyin_source.get("status_message"), 180),
        }
    except Exception:
        source_errors.append(_source_error("douyin_source", "抖音数据源状态暂时不可用。"))
    try:
        llm = llm_status_payload()
        capabilities["llm"] = {
            "configured": bool(llm.get("configured")),
            "status": "configured" if llm.get("configured") else "not_configured",
            "label": "已配置" if llm.get("configured") else "未配置",
            "provider": _safe_public_text(llm.get("provider"), 40),
            "model": _safe_public_text(llm.get("model"), 80),
        }
    except Exception:
        source_errors.append(_source_error("llm", "LLM 配置状态暂时不可用。"))
    try:
        preflight = local_tools_summary_payload()
        public_checks = [
            {
                "id": _safe_public_text(item.get("id"), 40),
                "label": _safe_public_text(item.get("label"), 80),
                "status": _safe_public_text(item.get("status"), 40),
                "available": bool(item.get("available")),
            }
            for item in preflight.get("checks", [])
            if isinstance(item, dict)
        ]
        capabilities["preflight"] = {
            "status": _safe_public_text(preflight.get("status"), 40),
            "ready_count": max(0, int(preflight.get("ready_count") or 0)),
            "total_count": max(0, int(preflight.get("total_count") or 0)),
            "checks": public_checks,
        }
    except Exception:
        source_errors.append(_source_error("preflight", "本地工具状态暂时不可用。"))

    resumable_tasks = sorted(
        [*single_resumable, *creator_resumable],
        key=lambda item: str(item.get("updated_at") or ""),
        reverse=True,
    )[:OVERVIEW_LIMIT]
    return {
        "running_tasks": running_tasks,
        "resumable_tasks": resumable_tasks,
        "recent_cases": recent_cases,
        "recent_creator_reports": recent_creator_reports,
        "recent_strategy_plans": recent_strategy_plans,
        "recent_failures": recent_failures,
        "capabilities": capabilities,
        "source_errors": source_errors,
        "meta": {
            "partial": bool(source_errors or truncated_sources),
            "truncated_sources": truncated_sources,
            "limit_per_section": OVERVIEW_LIMIT,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
