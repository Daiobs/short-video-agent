from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

from sqlalchemy.engine import make_url

from app.config import settings
from app.services.data_source_settings import douyin_source_health_payload
from app.services.llm_settings import llm_status_payload
from app.services.tool_preflight import local_tools_summary_payload
from app.services.workbench_tasks import WorkbenchResumeTarget, WorkbenchTask


OVERVIEW_LIMIT = 5
CASE_QUERY_LIMIT = 30
RUNTIME_INDEX_MAX_BYTES = 4 * 1024 * 1024
RUNTIME_CANDIDATE_LIMIT = 50
ORPHAN_SAMPLE_SCAN_LIMIT = 5_000
ORPHAN_SAMPLE_CANDIDATE_LIMIT = 50
ORPHAN_SAMPLE_CACHE_SECONDS = 5
SAMPLE_SET_MAX_BYTES = 2 * 1024 * 1024
SQLITE_PROGRESS_CALLBACK_STEPS = 1_000
SQLITE_PROGRESS_CALLBACK_LIMIT = 5_000
TASK_STALE_SECONDS = 30 * 60
JOB_RESULT_MAX_BYTES = 2 * 1024 * 1024
JOB_CONTEXT_MAX_BYTES = 8 * 1024 * 1024

SAFE_RESOURCE_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
CLONE_RESOURCE_ID = re.compile(r"^clone_[a-f0-9]{32}$", re.IGNORECASE)
HTTP_URL = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:\\[^\s,;]+|(?<![:\w])/(?!/)[^\s,;]+)")
SECRET_VALUE = re.compile(
    r"(?i)(?:authorization|api[_ -]?key|cookie|access[_ -]?token|refresh[_ -]?token)\s*[:=]\s*[^\s,;]+"
)
QUOTED_SECRET_VALUE = re.compile(
    r'''(?ix)
    ["']?(?:authorization|api[_ -]?key|cookie|access[_ -]?token|refresh[_ -]?token)["']?
    \s*[:=]\s*
    (?:"[^"]*"|'[^']*'|[^\s,;}\]]+)
    '''
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

JOB_TARGET_STAGE = {
    "build-case": "processing",
    "resolve-qualities": "import",
    "download": "processing",
    "download-and-build-case": "processing",
    "download-build-analyze-case": "processing",
    "analyze-case": "case",
    "enrich-case": "case",
    "asr-case": "case",
    "ocr-case": "case",
    "profile-scan": "import",
    "profile-build-cases": "enrich",
    "creator-clone-distill": "distill",
    "creator-clone-batch-distill": "distill",
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

WORKFLOW_STAGE_PROGRESS = {
    "IMPORT": 0,
    "INGESTED": 20,
    "SAMPLE_READY": 35,
    "SAMPLE_SELECTED": 50,
    "EVIDENCE_READY": 70,
    "DISTILLING": 85,
    "DONE": 100,
}


class WorkbenchSourceError(RuntimeError):
    pass


def _safe_public_text(value: Any, max_length: int = 240) -> str:
    text = str(value or "").replace("\x00", " ").strip()
    text = AUTHORIZATION_VALUE.sub("[授权信息已隐藏]", text)
    text = QUOTED_SECRET_VALUE.sub("[敏感配置已隐藏]", text)
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


def _bounded_json_object(value: Any, max_bytes: int) -> dict[str, Any]:
    if not isinstance(value, str) or len(value.encode("utf-8")) > max_bytes:
        return {}
    try:
        payload = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _bounded_job_result(value: Any) -> dict[str, Any]:
    return _bounded_json_object(value, JOB_RESULT_MAX_BYTES)


def _nested_dict(value: Any, key: str) -> dict[str, Any]:
    nested = value.get(key) if isinstance(value, dict) else None
    return nested if isinstance(nested, dict) else {}


def _safe_count(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, min(int(value or 0), 1_000_000))
    except (TypeError, ValueError, OverflowError):
        return 0


def _first_safe_id(*values: Any, prefix: str = "") -> str:
    for value in values:
        candidate = _safe_resource_id(value)
        if candidate and (not prefix or candidate.startswith(prefix)):
            return candidate
    return ""


def _job_result_hints(row: sqlite3.Row) -> dict[str, Any]:
    try:
        raw = row["result_hints_json"]
    except (IndexError, KeyError):
        return {}
    if not isinstance(raw, str) or len(raw) > 4096:
        return {}
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(values, list) or len(values) < 17:
        return {}
    return {
        "set_id": _first_safe_id(values[0], values[1], values[2], prefix="clone_"),
        "case_id": _first_safe_id(values[3], values[4], values[5], prefix="case_"),
        "aweme_id": _first_safe_id(values[6], values[7], values[8]),
        "local_video_id": _first_safe_id(values[9], values[10], values[11], prefix="local_"),
        "selected_count": max(_safe_count(values[12]), _safe_count(values[13]), _safe_count(values[14])),
        "case_count": max(_safe_count(values[15]), _safe_count(values[16])),
    }


def _job_result_context(result: dict[str, Any], hints: dict[str, Any] | None = None) -> dict[str, str]:
    hints = hints or {}
    recovery = _nested_dict(result, "recovery_context")
    case = _nested_dict(result, "case")
    download = _nested_dict(result, "download")
    sample_set = _nested_dict(result, "set")
    intelligence = _nested_dict(result, "creator_intelligence")
    project = _nested_dict(intelligence, "project")
    case_id = _first_safe_id(
        result.get("case_id"),
        case.get("case_id"),
        recovery.get("case_id"),
        hints.get("case_id"),
        prefix="case_",
    )
    set_id = _first_safe_id(
        sample_set.get("set_id"),
        recovery.get("sample_set_id"),
        project.get("project_id"),
        hints.get("set_id"),
        prefix="clone_",
    )
    aweme_id = _first_safe_id(
        result.get("aweme_id"),
        download.get("aweme_id"),
        recovery.get("aweme_id"),
        hints.get("aweme_id"),
    )
    local_video_id = _first_safe_id(
        result.get("local_video_id"),
        download.get("local_video_id"),
        recovery.get("local_video_id"),
        hints.get("local_video_id"),
        prefix="local_",
    )
    return {
        "case_id": case_id,
        "set_id": set_id,
        "aweme_id": aweme_id,
        "local_video_id": local_video_id,
    }


def _job_available_results(
    job_type: str,
    result: dict[str, Any],
    context: dict[str, str],
    hints: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    hints = hints or {}
    available: list[str] = []
    pipeline = _nested_dict(result, "pipeline_summary")
    if context["set_id"]:
        available.append("素材池")
        selected_count = max(
            _safe_count(result.get("selected_count") or len(result.get("selected_sample_ids") or [])),
            _safe_count(hints.get("selected_count")),
        )
        if selected_count:
            available.append("已选样本")
    case_count = max(
        _safe_count(pipeline.get("case_count") or result.get("completed_count")),
        _safe_count(hints.get("case_count")),
    )
    if case_count:
        available.append(f"已完成素材包 {case_count} 条")
    if context["case_id"]:
        available.append("Case 素材包")
    if context["local_video_id"] or isinstance(result.get("download"), dict):
        available.append("已下载视频")
    if isinstance(result.get("analysis_result"), dict) or isinstance(_nested_dict(result, "analysis").get("analysis_result"), dict):
        available.append("单作品分析结果")
    if isinstance(result.get("result"), dict) and result.get("result"):
        available.append("创作者蒸馏结果")
    if result.get("prompt") or result.get("recovery") == "prompt_only":
        available.append("蒸馏 Prompt")
    if job_type == "profile-scan" and isinstance(result.get("items"), list) and result.get("items"):
        available.append("主页扫描结果")
    return tuple(dict.fromkeys(available))


def _last_completed_stage(progress: int, available_results: tuple[str, ...]) -> str:
    priorities = (
        "创作者蒸馏结果",
        "单作品分析结果",
        "蒸馏 Prompt",
        "已完成素材包",
        "Case 素材包",
        "已下载视频",
        "已选样本",
        "素材池",
        "主页扫描结果",
    )
    for prefix in priorities:
        matched = next((item for item in available_results if item.startswith(prefix)), "")
        if matched:
            return matched
    return f"任务已执行至 {progress}%" if progress else "尚未产生可复用结果"


def _job_recovery_hint(
    job_type: str,
    error_code: str,
    status: str,
    *,
    has_resource_target: bool,
    can_observe_by_job: bool,
) -> str:
    if not has_resource_target and not can_observe_by_job:
        return (
            "旧任务缺少可恢复的业务资源标识，只能查看错误码、进度和诊断信息；"
            "系统不会自动重试或重建上下文。"
        )
    if can_observe_by_job and not has_resource_target and job_type == "profile-scan":
        return "可只读观察主页扫描状态；任务成功后将从安全 Job 结果恢复素材池。"
    if can_observe_by_job and not has_resource_target:
        return (
            "可只读观察任务状态；仅当任务结果包含安全业务资源标识时才恢复上下文。"
            "系统不会自动重试或重建资源。"
        )
    if status == "stale":
        return (
            "任务较长时间没有更新。可只读查看当前状态；如已有业务资源，可重新打开对应步骤核对。"
            "系统不会自动重试，也不会把该任务自动改成失败。"
        )
    code = error_code.upper()
    if code.startswith("LLM_") or code == "AUTO_ANALYSIS_FAILED":
        return "已有素材包、素材池或证据仍会保留。请检查模型配置后，进入拆解/蒸馏步骤手动重新执行。"
    if job_type == "profile-build-cases" or code.startswith("PROFILE_BUILD"):
        return "素材池和已经完成的素材包仍会保留。进入证据富化查看失败项后手动重跑，已完成素材会优先复用。"
    if code.startswith(("ASR_", "OCR_", "ENRICHMENT_")):
        return "Case 素材包仍可使用。进入 Case 检查本地依赖，然后只手动重跑失败的富化步骤。"
    if code.startswith(("DOWNLOAD", "QUALITY", "PROVIDER", "URL_")):
        return "进入原任务页面重新解析或下载；如已有 Case 或下载结果，可继续使用，系统不会自动重复下载。"
    if code.startswith(("PROFILE_SCAN", "DOUYIN_", "COOKIE_")):
        return "返回创作者导入步骤，检查数据源状态，或改用作品链接、JSON / CSV、已有 Case 等已授权入口。"
    if code.startswith(("CASE_BUILD", "FFMPEG", "FFPROBE", "KEYFRAME")):
        return "检查本地媒体工具后回到单作品页面手动生成素材包；已有下载文件不会被自动删除。"
    if status == "failed" and has_resource_target:
        return "重新打开对应页面，核对已保留结果后由你决定是否手动执行当前步骤。"
    return "查看错误说明和已有结果；该任务没有可自动执行的恢复动作。"


def _job_payload(row: sqlite3.Row, *, status_override: str = "") -> dict[str, Any]:
    job_type = str(row["type"] or "")
    stage, task_group, route = JOB_META.get(job_type, ("后台任务", "系统", ""))
    raw_status = str(row["status"] or "")
    status = status_override or raw_status
    progress = max(0, min(100, int(row["progress"] or 0)))
    result = _bounded_job_result(row["result_json"])
    hints = _job_result_hints(row)
    context = _job_result_context(result, hints)
    task_id = _first_safe_id(row["id"], prefix="job_")
    error_code = _safe_public_text(row["error_code"], 80)
    target_stage = JOB_TARGET_STAGE.get(job_type, "")
    resource_id = context["set_id"] if route == "profile" else (context["case_id"] or context["aweme_id"] or context["local_video_id"])
    open_url = f"/cases/{context['case_id']}" if context["case_id"] else ""
    has_resource_target = route in {"single", "profile"} and bool(resource_id or open_url)
    can_observe_by_job = (
        route in {"single", "profile"}
        and status in {"pending", "running", "stale"}
        and bool(task_id)
    )
    diagnostic_only = not (has_resource_target or can_observe_by_job)
    recoverable = not diagnostic_only
    mode = "observe" if can_observe_by_job else "manual"
    target = (
        WorkbenchResumeTarget(
            route=route,
            stage=target_stage,
            resource_id=resource_id,
            job_id=task_id,
            task_type=_safe_public_text(job_type, 64),
            mode=mode,
            open_url=open_url,
        )
        if recoverable
        else WorkbenchResumeTarget()
    )
    available_results = _job_available_results(job_type, result, context, hints)
    task = WorkbenchTask(
        task_id=task_id,
        task_type=_safe_public_text(job_type, 64),
        task_group=task_group,
        title=stage,
        status=status,
        stage=stage,
        progress=progress,
        message=_safe_public_text(row["message"] or "任务状态已更新。"),
        error_code=error_code,
        created_at=_iso_datetime(row["created_at"]),
        updated_at=_iso_datetime(row["updated_at"]),
        resume_target=target,
        recoverable=recoverable,
        has_resource_target=has_resource_target,
        can_observe_by_job=can_observe_by_job,
        diagnostic_only=diagnostic_only,
        recovery_hint=_job_recovery_hint(
            job_type,
            error_code,
            status,
            has_resource_target=has_resource_target,
            can_observe_by_job=can_observe_by_job,
        ),
        last_completed_stage=_last_completed_stage(progress, available_results),
        available_results=available_results,
    )
    return task.to_dict()


SAFE_RESULT_COUNT_KEYS = (
    "selected_count",
    "sample_count",
    "completed_count",
    "failed_count",
    "skipped_count",
    "reference_only_count",
    "downloadable_count",
    "case_count",
    "downloaded_count",
    "reused_case_count",
    "enriched_count",
    "asr_success_count",
    "ocr_success_count",
    "asr_provider_missing_count",
    "ocr_provider_missing_count",
    "ready_for_distill_count",
    "total_count",
    "pending_count",
)


def _safe_job_item(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    item = {
        "sample_id": _safe_resource_id(value.get("sample_id")),
        "aweme_id": _safe_resource_id(value.get("aweme_id")),
        "case_id": _first_safe_id(value.get("case_id"), prefix="case_"),
        "local_video_id": _first_safe_id(value.get("local_video_id"), prefix="local_"),
        "title": _safe_public_text(value.get("title"), 160),
        "author": _safe_public_text(value.get("author"), 100),
        "media_type": _safe_public_text(value.get("media_type"), 32),
        "status": _safe_public_text(value.get("status"), 32),
        "error_code": _safe_public_text(value.get("error_code"), 80),
        "message": _safe_public_text(value.get("message"), 240),
        "enrichment_status": _safe_public_text(value.get("enrichment_status"), 32),
        "asr_status": _safe_public_text(value.get("asr_status"), 32),
        "ocr_status": _safe_public_text(value.get("ocr_status"), 32),
        "analysis_status": _safe_public_text(value.get("analysis_status"), 32),
        "like_count": _safe_count(value.get("like_count")),
        "comment_count": _safe_count(value.get("comment_count")),
        "share_count": _safe_count(value.get("share_count")),
        "collect_count": _safe_count(value.get("collect_count")),
        "engagement_score": _safe_count(value.get("engagement_score")),
    }
    return {key: item_value for key, item_value in item.items() if item_value not in {"", 0}}


def _safe_pipeline_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    summary = {key: _safe_count(value.get(key)) for key in SAFE_RESULT_COUNT_KEYS if key in value}
    for key in ("notes", "next_actions"):
        items = value.get(key)
        if isinstance(items, list):
            summary[key] = [
                text
                for item in items[:10]
                for text in [_safe_public_text(item, 240)]
                if text
            ]
    return summary


def _safe_job_result(result: dict[str, Any], hints: dict[str, Any]) -> dict[str, Any]:
    context = _job_result_context(result, hints)
    safe_result: dict[str, Any] = {
        key: value
        for key, value in context.items()
        if value
    }
    if any(context.values()):
        safe_result["recovery_context"] = {
            "sample_set_id": context["set_id"],
            "case_id": context["case_id"],
            "aweme_id": context["aweme_id"],
            "local_video_id": context["local_video_id"],
        }
        safe_result["recovery_context"] = {
            key: value for key, value in safe_result["recovery_context"].items() if value
        }
    if context["set_id"]:
        safe_result["set"] = {
            "set_id": context["set_id"],
            "selected_count": max(
                _safe_count(_nested_dict(result, "set").get("selected_count")),
                _safe_count(result.get("selected_count")),
                _safe_count(hints.get("selected_count")),
            ),
            "sample_count": max(
                _safe_count(_nested_dict(result, "set").get("sample_count")),
                _safe_count(result.get("sample_count")),
            ),
        }
    for key in SAFE_RESULT_COUNT_KEYS:
        if key in result:
            safe_result[key] = _safe_count(result.get(key))
    pipeline = _safe_pipeline_summary(result.get("pipeline_summary"))
    if pipeline:
        safe_result["pipeline_summary"] = pipeline
    items = result.get("items")
    if isinstance(items, list):
        safe_result["items"] = [safe for item in items[:150] for safe in [_safe_job_item(item)] if safe]
    warnings = result.get("warnings")
    if isinstance(warnings, list):
        safe_result["warnings"] = [
            text for item in warnings[:10] for text in [_safe_public_text(item, 240)] if text
        ]
    if "sort_by" in result:
        safe_result["sort_by"] = _safe_public_text(result.get("sort_by"), 40)
    if "analysis_status" in result:
        safe_result["analysis_status"] = _safe_public_text(result.get("analysis_status"), 40)
    analysis_error = result.get("analysis_error")
    if isinstance(analysis_error, dict):
        safe_result["analysis_error"] = {
            "error_code": _safe_public_text(analysis_error.get("error_code"), 80),
            "message": _safe_public_text(analysis_error.get("message"), 240),
        }
    if context["case_id"]:
        safe_result["case"] = {"case_id": context["case_id"]}
    if context["aweme_id"] or context["local_video_id"]:
        safe_result["download"] = {
            key: value
            for key, value in {
                "aweme_id": context["aweme_id"],
                "local_video_id": context["local_video_id"],
                "size_bytes": _safe_count(_nested_dict(result, "download").get("size_bytes")),
            }.items()
            if value
        }
    return safe_result


def build_workbench_job_detail(job_id: str, *, database_url: str | None = None) -> dict[str, Any] | None:
    safe_job_id = _first_safe_id(job_id, prefix="job_")
    if not safe_job_id:
        return None
    database_url = database_url or settings.database_url
    with _readonly_connection(database_url) as connection:
        row = connection.execute(
            f"""
            SELECT id, type, status, progress, message, error_code, created_at, updated_at,
                   CASE
                       WHEN length(CAST(result_json AS BLOB)) <= {JOB_CONTEXT_MAX_BYTES} THEN result_json
                       ELSE '{{}}'
                   END AS result_json,
                   CASE
                       WHEN length(CAST(result_json AS BLOB)) <= {JOB_CONTEXT_MAX_BYTES} AND json_valid(result_json)
                       THEN json_extract(
                           result_json,
                           '$.set.set_id',
                           '$.recovery_context.sample_set_id',
                           '$.creator_intelligence.project.project_id',
                           '$.case_id',
                           '$.case.case_id',
                           '$.recovery_context.case_id',
                           '$.aweme_id',
                           '$.download.aweme_id',
                           '$.recovery_context.aweme_id',
                           '$.local_video_id',
                           '$.download.local_video_id',
                           '$.recovery_context.local_video_id',
                           '$.selected_count',
                           '$.set.selected_count',
                           '$.pipeline_summary.selected_count',
                           '$.pipeline_summary.case_count',
                           '$.completed_count'
                       )
                       ELSE '[]'
                   END AS result_hints_json
            FROM jobs
            WHERE id = ?
            LIMIT 1
            """,
            (safe_job_id,),
        ).fetchone()
    if row is None:
        return None
    raw_status = str(row["status"] or "")
    updated_at = _iso_datetime(row["updated_at"])
    status_override = ""
    if raw_status in {"pending", "running"}:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=TASK_STALE_SECONDS)
        parsed_updated_at = datetime.fromisoformat(updated_at) if updated_at else None
        if parsed_updated_at and parsed_updated_at < cutoff:
            status_override = "stale"
    task = _job_payload(row, status_override=status_override)
    result = _bounded_json_object(row["result_json"], JOB_CONTEXT_MAX_BYTES)
    hints = _job_result_hints(row)
    return {
        **task,
        "id": task["task_id"],
        "type": task["task_type"],
        "result_json": _safe_job_result(result, hints),
    }


def _collect_job_sections(database_url: str) -> tuple[list[dict], list[dict], list[dict], int, int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=TASK_STALE_SECONDS)).replace(tzinfo=None).isoformat(sep=" ")
    with _readonly_connection(database_url) as connection:
        def read_rows(where_sql: str, parameters: tuple[Any, ...]) -> list[sqlite3.Row]:
            return connection.execute(
                f"""
                WITH selected_jobs AS (
                    SELECT id, type, status, progress, message, error_code, created_at, updated_at, result_json
                    FROM jobs
                    WHERE {where_sql}
                    ORDER BY updated_at DESC
                    LIMIT ?
                )
                SELECT id, type, status, progress, message, error_code, created_at, updated_at,
                       CASE
                           WHEN length(result_json) <= {JOB_RESULT_MAX_BYTES} THEN result_json
                           ELSE '{{}}'
                       END AS result_json,
                       CASE
                           WHEN length(result_json) <= {JOB_CONTEXT_MAX_BYTES} AND json_valid(result_json)
                           THEN json_extract(
                               result_json,
                               '$.set.set_id',
                               '$.recovery_context.sample_set_id',
                               '$.creator_intelligence.project.project_id',
                               '$.case_id',
                               '$.case.case_id',
                               '$.recovery_context.case_id',
                               '$.aweme_id',
                               '$.download.aweme_id',
                               '$.recovery_context.aweme_id',
                               '$.local_video_id',
                               '$.download.local_video_id',
                               '$.recovery_context.local_video_id',
                               '$.selected_count',
                               '$.set.selected_count',
                               '$.pipeline_summary.selected_count',
                               '$.pipeline_summary.case_count',
                               '$.completed_count'
                           )
                           ELSE '[]'
                       END AS result_hints_json
                FROM selected_jobs
                """,
                (*parameters, OVERVIEW_LIMIT),
            ).fetchall()

        running_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE status IN ('pending', 'running') AND updated_at >= ?",
                (cutoff,),
            ).fetchone()[0]
            or 0
        )
        stale_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE status IN ('pending', 'running') AND updated_at < ?",
                (cutoff,),
            ).fetchone()[0]
            or 0
        )
        running_rows = read_rows("status IN ('pending', 'running') AND updated_at >= ?", (cutoff,))
        stale_rows = read_rows("status IN ('pending', 'running') AND updated_at < ?", (cutoff,))
        failure_rows = read_rows("status = 'failed'", ())
    return (
        [_job_payload(row) for row in running_rows],
        [_job_payload(row, status_override="stale") for row in stale_rows],
        [_job_payload(row) for row in failure_rows],
        running_count,
        stale_count,
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
            task = WorkbenchTask(
                task_id=case_id,
                task_type="single_work",
                task_group="单作品",
                title=title,
                status="recoverable",
                stage="素材包已生成，等待拆解",
                progress=70,
                message="视频、关键帧和分析输入已保留，可继续打开 Case 完成拆解。",
                created_at=created_at,
                updated_at=created_at,
                resume_target=WorkbenchResumeTarget(
                    route="single",
                    stage="case",
                    resource_id=case_id,
                    task_type="single_work",
                    mode="manual",
                    open_url=f"/cases/{case_id}",
                ),
                recoverable=True,
                has_resource_target=True,
                diagnostic_only=False,
                recovery_hint="打开 Case 后可查看已有素材包，并由你决定是否启动 AI 拆解。",
                last_completed_stage="Case 素材包",
                available_results=("Case 素材包", "关键帧与分析输入"),
            ).to_dict()
            task.update(
                {
                    "current_step": task["stage"],
                    "sample_count": 1,
                    "selected_count": 1,
                    "report_status": "未生成",
                    "open_url": f"/cases/{case_id}",
                }
            )
            resumable.append(task)
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


def _read_runtime_index(creator_state_dir: Path) -> tuple[list[dict[str, Any]], bool, set[str]]:
    index_path = creator_state_dir.resolve() / "sessions.json"
    if not index_path.is_file():
        return [], False, set()
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
    known_ids = {
        resource_id
        for item in rows
        for resource_id in [_safe_resource_id(item.get("project_id") or item.get("session_id"))]
        if resource_id
    }
    return rows[:RUNTIME_CANDIDATE_LIMIT], truncated, known_ids


@lru_cache(maxsize=8)
def _scan_sample_set_candidates(
    root_value: str,
    root_mtime_ns: int,
    refresh_bucket: int,
) -> tuple[tuple[tuple[float, str], ...], bool]:
    del root_mtime_ns, refresh_bucket
    root = Path(root_value)
    candidates: list[tuple[float, str]] = []
    scanned_count = 0
    truncated = False
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                scanned_count += 1
                if scanned_count > ORPHAN_SAMPLE_SCAN_LIMIT:
                    truncated = True
                    break
                resource_id = _safe_resource_id(entry.name)
                if (
                    not resource_id
                    or not CLONE_RESOURCE_ID.fullmatch(resource_id)
                    or not entry.is_dir(follow_symlinks=False)
                ):
                    continue
                samples_path = Path(entry.path) / "samples.json"
                if samples_path.is_symlink() or not samples_path.is_file():
                    continue
                try:
                    stat = samples_path.stat()
                except OSError:
                    continue
                candidates.append((stat.st_mtime, resource_id))
    except OSError as error:
        raise WorkbenchSourceError("Creator 素材池索引不可读取。") from error
    candidates.sort(key=lambda item: item[0], reverse=True)
    return tuple(candidates), truncated


def _read_orphan_sample_sets(
    creator_clones_dir: Path,
    known_runtime_ids: set[str],
) -> tuple[list[dict[str, Any]], bool]:
    root = creator_clones_dir.resolve()
    if not root.is_dir():
        return [], False
    try:
        root_mtime_ns = root.stat().st_mtime_ns
    except OSError as error:
        raise WorkbenchSourceError("Creator 素材池索引不可读取。") from error
    refresh_bucket = int(time.monotonic() // ORPHAN_SAMPLE_CACHE_SECONDS)
    candidates, scan_truncated = _scan_sample_set_candidates(str(root), root_mtime_ns, refresh_bucket)
    orphan_candidates = [item for item in candidates if item[1] not in known_runtime_ids]
    truncated = scan_truncated or len(orphan_candidates) > ORPHAN_SAMPLE_CANDIDATE_LIMIT
    return [
        {
            "project_id": resource_id,
            "session_id": resource_id,
            "state": "",
            "updated_at": datetime.fromtimestamp(mtime, timezone.utc).isoformat(),
            "orphan_sample_set": True,
        }
        for mtime, resource_id in orphan_candidates[:ORPHAN_SAMPLE_CANDIDATE_LIMIT]
    ], truncated


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
) -> tuple[list[dict], list[dict], list[dict], tuple[str, ...]]:
    index_rows, runtime_truncated, known_runtime_ids = _read_runtime_index(creator_state_dir)
    orphan_rows, orphan_truncated = _read_orphan_sample_sets(creator_clones_dir, known_runtime_ids)
    index_rows = [*index_rows, *orphan_rows]
    index_rows.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
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

        if entry.get("orphan_sample_set"):
            summary = summary or _sample_set_summary(clone_dir, resource_id)
            state = "DONE" if report_exists else ("SAMPLE_READY" if summary["selected_count"] else "INGESTED")
        else:
            state = str(entry.get("state") or "IMPORT").upper()
        if state == "DONE" and report_exists:
            continue
        if len(resumable) >= OVERVIEW_LIMIT:
            continue
        summary = summary or _sample_set_summary(clone_dir, resource_id)
        if state == "IMPORT" and summary["sample_count"] <= 0:
            continue
        step_label, stage = WORKFLOW_STAGE_META.get(state, ("继续创作者拆解", "import"))
        updated_at = _iso_datetime(entry.get("updated_at"))
        available_results = ["素材池"]
        if summary["selected_count"]:
            available_results.append("已选样本")
        task = WorkbenchTask(
            task_id=resource_id,
            task_type="creator_work",
            task_group="创作者",
            title=summary["title"],
            status="recoverable",
            stage=step_label,
            progress=WORKFLOW_STAGE_PROGRESS.get(state, 0),
            message=f"素材 {summary['sample_count']} 条，已选 {summary['selected_count']} 条。",
            created_at=updated_at,
            updated_at=updated_at,
            resume_target=WorkbenchResumeTarget(
                route="profile",
                stage=stage,
                resource_id=resource_id,
                task_type="creator_work",
                mode="manual",
            ),
            recoverable=True,
            has_resource_target=True,
            diagnostic_only=False,
            recovery_hint=f"恢复素材池后将直接打开“{step_label}”，不会自动执行该步骤。",
            last_completed_stage=available_results[-1],
            available_results=tuple(available_results),
        ).to_dict()
        task.update(
            {
                "workflow_state": state,
                "current_step": step_label,
                "sample_count": summary["sample_count"],
                "selected_count": summary["selected_count"],
                "report_status": "已生成" if report_exists else "未生成",
            }
        )
        resumable.append(task)

    reports: list[dict] = []
    for report_mtime, resource_id, clone_dir in sorted(report_candidates, key=lambda pair: pair[0], reverse=True)[:OVERVIEW_LIMIT]:
        summary = _sample_set_summary(clone_dir, resource_id)
        open_url = ""
        if (clone_dir / "creator_clone.html").is_file() and not (clone_dir / "creator_clone.html").is_symlink():
            open_url = f"/api/creator-clone/sets/{resource_id}/files/creator_clone.html"
        elif (clone_dir / "creator_clone.md").is_file() and not (clone_dir / "creator_clone.md").is_symlink():
            open_url = f"/api/creator-clone/sets/{resource_id}/files/creator_clone.md"
        resume_target = WorkbenchResumeTarget(
            route="profile",
            resource_id=resource_id,
            stage="export",
            task_type="creator_report",
            mode="result",
            open_url=open_url,
        ).to_dict()
        reports.append(
            {
                "resource_id": resource_id,
                "title": summary["title"],
                "type": "创作者蒸馏报告",
                "status": "ready",
                "updated_at": datetime.fromtimestamp(report_mtime, timezone.utc).isoformat(),
                "open_url": open_url,
                "resume_target": resume_target,
                "target": resume_target,
            }
        )

    strategies: list[dict] = []
    for strategy_mtime, resource_id, clone_dir, status in sorted(
        strategy_candidates,
        key=lambda pair: pair[0],
        reverse=True,
    )[:OVERVIEW_LIMIT]:
        summary = _sample_set_summary(clone_dir, resource_id)
        resume_target = WorkbenchResumeTarget(
            route="profile",
            resource_id=resource_id,
            stage="export",
            task_type="creator_strategy",
            mode="result",
        ).to_dict()
        strategies.append(
            {
                "resource_id": resource_id,
                "title": summary["title"],
                "type": "Creator Strategy Plan",
                "status": status,
                "updated_at": datetime.fromtimestamp(strategy_mtime, timezone.utc).isoformat(),
                "resume_target": resume_target,
                "target": resume_target,
            }
        )
    truncated_sources: list[str] = []
    if runtime_truncated:
        truncated_sources.append("creator_runtime")
    if orphan_truncated:
        truncated_sources.append("creator_sample_sets")
    return resumable, reports, strategies, tuple(truncated_sources)


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
    stale_tasks: list[dict] = []
    recent_failures: list[dict] = []
    recent_cases: list[dict] = []
    single_resumable: list[dict] = []
    creator_resumable: list[dict] = []
    recent_creator_reports: list[dict] = []
    recent_strategy_plans: list[dict] = []
    running_task_count = 0
    stale_task_count = 0
    source_errors: list[dict] = []
    truncated_sources: list[str] = []

    try:
        running_tasks, stale_tasks, recent_failures, running_task_count, stale_task_count = _collect_job_sections(
            database_url
        )
    except Exception:
        source_errors.append(_source_error("jobs", "任务状态暂时不可用。"))

    try:
        recent_cases, single_resumable = _collect_case_sections(database_url, cases_dir)
    except Exception:
        source_errors.append(_source_error("cases", "Case 索引暂时不可用。"))

    try:
        creator_resumable, recent_creator_reports, recent_strategy_plans, creator_truncated_sources = _collect_creator_sections(
            creator_state_dir,
            creator_clones_dir,
        )
        truncated_sources.extend(creator_truncated_sources)
    except Exception:
        source_errors.append(_source_error("creator_runtime", "创作者任务与报告索引暂时不可用。"))

    capabilities: dict[str, Any] = {
        "douyin_source": _unknown_capability("抖音数据源待确认"),
        "llm": _unknown_capability("LLM 状态待确认"),
        "preflight": {"status": "unknown", "ready_count": 0, "total_count": 0},
        "running_task_count": running_task_count,
        "stale_task_count": stale_task_count,
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

    active_resource_ids = {
        resource_id
        for item in [*running_tasks, *stale_tasks]
        if isinstance(item, dict)
        for resource_id in [str((item.get("resume_target") or {}).get("resource_id") or "")]
        if resource_id
    }
    resumable_tasks = sorted(
        [
            item
            for item in [*single_resumable, *creator_resumable]
            if str((item.get("resume_target") or {}).get("resource_id") or "") not in active_resource_ids
        ],
        key=lambda item: str(item.get("updated_at") or ""),
        reverse=True,
    )[:OVERVIEW_LIMIT]
    return {
        "running_tasks": running_tasks,
        "stale_tasks": stale_tasks,
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
            "task_stale_after_seconds": TASK_STALE_SECONDS,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
