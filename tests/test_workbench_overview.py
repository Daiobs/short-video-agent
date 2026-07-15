from __future__ import annotations

import hashlib
import json
import os
import socket
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import workbench as workbench_routes
from app.services import data_source_settings, runtime_settings, workbench_overview


def _create_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            status TEXT NOT NULL,
            progress INTEGER NOT NULL,
            message TEXT NOT NULL,
            result_json TEXT NOT NULL,
            error_code TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE case_artifacts (
            case_id TEXT PRIMARY KEY,
            aweme_id TEXT NOT NULL,
            local_video_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE local_video_items (
            local_video_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT NOT NULL
        );
        CREATE TABLE douyin_video_items (
            aweme_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT NOT NULL
        );
        """
    )
    connection.commit()
    connection.close()


def _runtime_paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    cases_dir = tmp_path / "cases"
    creator_state_dir = tmp_path / "creator_state"
    creator_clones_dir = tmp_path / "creator_clones"
    cases_dir.mkdir()
    creator_state_dir.mkdir()
    creator_clones_dir.mkdir()
    return cases_dir, creator_state_dir, creator_clones_dir


def _database_url(path: Path) -> str:
    return f"sqlite:///{path}"


def _patch_capabilities(monkeypatch) -> None:
    monkeypatch.setattr(
        workbench_overview,
        "douyin_source_health_payload",
        lambda: {
            "configured": False,
            "status": "not_configured",
            "label": "未配置",
            "last_checked_at": "",
            "status_message": "未配置",
        },
    )
    monkeypatch.setattr(
        workbench_overview,
        "llm_status_payload",
        lambda: {"configured": False, "provider": "disabled", "model": ""},
    )
    monkeypatch.setattr(
        workbench_overview,
        "local_tools_summary_payload",
        lambda: {"status": "ready", "ready_count": 2, "total_count": 2, "checks": []},
    )


def _build(tmp_path: Path, monkeypatch) -> dict:
    database_path = tmp_path / "overview.db"
    _create_database(database_path)
    cases_dir, creator_state_dir, creator_clones_dir = _runtime_paths(tmp_path)
    _patch_capabilities(monkeypatch)
    return workbench_overview.build_workbench_overview(
        database_url=_database_url(database_path),
        cases_dir=cases_dir,
        creator_state_dir=creator_state_dir,
        creator_clones_dir=creator_clones_dir,
    )


def test_workbench_overview_empty_state_has_stable_shape(tmp_path: Path, monkeypatch) -> None:
    payload = _build(tmp_path, monkeypatch)

    assert payload["running_tasks"] == []
    assert payload["stale_tasks"] == []
    assert payload["resumable_tasks"] == []
    assert payload["recent_cases"] == []
    assert payload["recent_creator_reports"] == []
    assert payload["recent_strategy_plans"] == []
    assert payload["recent_failures"] == []
    assert payload["source_errors"] == []
    assert payload["meta"]["partial"] is False
    assert payload["capabilities"]["running_task_count"] == 0
    assert payload["capabilities"]["stale_task_count"] == 0


def test_workbench_overview_normalizes_running_stale_and_failed_tasks_without_mutation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "overview.db"
    _create_database(database_path)
    cases_dir, creator_state_dir, creator_clones_dir = _runtime_paths(tmp_path)
    _patch_capabilities(monkeypatch)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    clone_id = f"clone_{'a' * 32}"
    case_id = f"case_{'b' * 32}"
    rows = [
        (
            "job_running",
            "profile-build-cases",
            "running",
            44,
            "正在富化证据",
            json.dumps({"set": {"set_id": clone_id}, "pipeline_summary": {"case_count": 2}}),
            "",
            now.isoformat(sep=" "),
            now.isoformat(sep=" "),
        ),
        (
            "job_stale",
            "creator-clone-distill",
            "running",
            63,
            "等待模型响应",
            json.dumps({"recovery_context": {"sample_set_id": clone_id}}),
            "",
            (now - timedelta(hours=2)).isoformat(sep=" "),
            (now - timedelta(hours=1)).isoformat(sep=" "),
        ),
        (
            "job_failed",
            "analyze-case",
            "failed",
            75,
            "模型请求失败",
            json.dumps({"recovery_context": {"case_id": case_id}}),
            "LLM_REQUEST_FAILED",
            now.isoformat(sep=" "),
            now.isoformat(sep=" "),
        ),
    ]
    connection = sqlite3.connect(database_path)
    connection.executemany("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    connection.commit()
    connection.close()

    first = workbench_overview.build_workbench_overview(
        database_url=_database_url(database_path),
        cases_dir=cases_dir,
        creator_state_dir=creator_state_dir,
        creator_clones_dir=creator_clones_dir,
    )
    second = workbench_overview.build_workbench_overview(
        database_url=_database_url(database_path),
        cases_dir=cases_dir,
        creator_state_dir=creator_state_dir,
        creator_clones_dir=creator_clones_dir,
    )

    running = first["running_tasks"][0]
    stale = first["stale_tasks"][0]
    failed = first["recent_failures"][0]
    required_fields = {
        "task_id",
        "task_type",
        "title",
        "status",
        "stage",
        "progress",
        "message",
        "created_at",
        "updated_at",
        "resume_target",
        "recoverable",
        "has_resource_target",
        "can_observe_by_job",
        "diagnostic_only",
        "recovery_hint",
    }
    assert required_fields <= running.keys()
    assert running["status"] == "running"
    assert running["resume_target"] == {
        "route": "profile",
        "stage": "enrich",
        "resource_id": clone_id,
        "job_id": "job_running",
        "task_type": "profile-build-cases",
        "mode": "observe",
        "open_url": "",
    }
    assert running["has_resource_target"] is True
    assert running["can_observe_by_job"] is True
    assert running["diagnostic_only"] is False
    assert stale["status"] == "stale"
    assert stale["resume_target"]["stage"] == "distill"
    assert stale["resume_target"]["mode"] == "observe"
    assert stale["recoverable"] is True
    assert "不会自动重试" in stale["recovery_hint"]
    assert failed["status"] == "failed"
    assert failed["error_code"] == "LLM_REQUEST_FAILED"
    assert failed["resume_target"]["open_url"] == f"/cases/{case_id}"
    assert failed["has_resource_target"] is True
    assert failed["can_observe_by_job"] is False
    assert failed["diagnostic_only"] is False
    assert "Case 素材包" in failed["available_results"]
    assert "模型配置" in failed["recovery_hint"]
    assert first["capabilities"]["running_task_count"] == 1
    assert first["capabilities"]["stale_task_count"] == 1
    assert second["running_tasks"] == first["running_tasks"]
    assert second["stale_tasks"] == first["stale_tasks"]

    connection = sqlite3.connect(database_path)
    persisted_status = connection.execute("SELECT status FROM jobs WHERE id = 'job_stale'").fetchone()[0]
    connection.close()
    assert persisted_status == "running"


def test_workbench_overview_marks_resource_less_old_jobs_as_diagnostic_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "overview.db"
    _create_database(database_path)
    cases_dir, creator_state_dir, creator_clones_dir = _runtime_paths(tmp_path)
    _patch_capabilities(monkeypatch)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = [
        (
            "job_failed_case",
            "analyze-case",
            "failed",
            75,
            "模型请求失败",
            "{}",
            "LLM_REQUEST_FAILED",
            now.isoformat(sep=" "),
            now.isoformat(sep=" "),
        ),
        (
            "job_failed_creator",
            "creator-clone-distill",
            "failed",
            45,
            "蒸馏失败",
            "{}",
            "LLM_REQUEST_FAILED",
            now.isoformat(sep=" "),
            now.isoformat(sep=" "),
        ),
        (
            "job_profile_scan",
            "profile-scan",
            "running",
            30,
            "正在扫描主页",
            "{}",
            "",
            now.isoformat(sep=" "),
            now.isoformat(sep=" "),
        ),
    ]
    connection = sqlite3.connect(database_path)
    connection.executemany("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    connection.commit()
    connection.close()

    payload = workbench_overview.build_workbench_overview(
        database_url=_database_url(database_path),
        cases_dir=cases_dir,
        creator_state_dir=creator_state_dir,
        creator_clones_dir=creator_clones_dir,
    )

    failures = {item["task_id"]: item for item in payload["recent_failures"]}
    for task_id in ("job_failed_case", "job_failed_creator"):
        task = failures[task_id]
        assert task["recoverable"] is False
        assert task["has_resource_target"] is False
        assert task["can_observe_by_job"] is False
        assert task["diagnostic_only"] is True
        assert task["resume_target"] == {
            "route": "",
            "stage": "",
            "resource_id": "",
            "job_id": "",
            "task_type": "",
            "mode": "manual",
            "open_url": "",
        }
        assert "只能查看错误码、进度和诊断信息" in task["recovery_hint"]

    running = payload["running_tasks"][0]
    assert running["task_id"] == "job_profile_scan"
    assert running["recoverable"] is True
    assert running["has_resource_target"] is False
    assert running["can_observe_by_job"] is True
    assert running["diagnostic_only"] is False
    assert running["resume_target"] == {
        "route": "profile",
        "stage": "import",
        "resource_id": "",
        "job_id": "job_profile_scan",
        "task_type": "profile-scan",
        "mode": "observe",
        "open_url": "",
    }
    assert "任务成功后将从安全 Job 结果恢复素材池" in running["recovery_hint"]


def test_workbench_overview_recovers_large_profile_job_without_loading_full_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "overview.db"
    _create_database(database_path)
    cases_dir, creator_state_dir, creator_clones_dir = _runtime_paths(tmp_path)
    _patch_capabilities(monkeypatch)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
    clone_id = f"clone_{'d' * 32}"
    large_result = json.dumps(
        {
            "set": {"set_id": clone_id, "selected_count": 150},
            "pipeline_summary": {"selected_count": 150, "case_count": 148},
            "padding": "x" * (workbench_overview.JOB_RESULT_MAX_BYTES + 1024),
        }
    )
    connection = sqlite3.connect(database_path)
    connection.execute(
        "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "job_large_profile",
            "profile-build-cases",
            "running",
            81,
            "正在处理大样本队列",
            large_result,
            "",
            now,
            now,
        ),
    )
    connection.commit()
    connection.close()

    payload = workbench_overview.build_workbench_overview(
        database_url=_database_url(database_path),
        cases_dir=cases_dir,
        creator_state_dir=creator_state_dir,
        creator_clones_dir=creator_clones_dir,
    )

    task = payload["running_tasks"][0]
    assert task["resume_target"]["resource_id"] == clone_id
    assert task["resume_target"]["stage"] == "enrich"
    assert "已选样本" in task["available_results"]
    assert "已完成素材包 148 条" in task["available_results"]
    assert "padding" not in json.dumps(payload)


def test_workbench_overview_api_returns_read_only_contract(monkeypatch) -> None:
    expected = {
        "running_tasks": [],
        "resumable_tasks": [],
        "recent_cases": [],
        "recent_creator_reports": [],
        "recent_strategy_plans": [],
        "recent_failures": [],
        "capabilities": {},
        "source_errors": [],
        "meta": {"partial": False},
    }
    monkeypatch.setattr(workbench_routes, "build_workbench_overview", lambda: expected)
    app = FastAPI()
    app.include_router(workbench_routes.router)

    response = TestClient(app).get("/api/workbench/overview")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"ok": True, **expected}


def test_workbench_job_api_returns_sanitized_recovery_context(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "overview.db"
    _create_database(database_path)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
    clone_id = f"clone_{'a' * 32}"
    case_id = f"case_{'b' * 32}"
    local_id = f"local_{'c' * 32}"
    raw_result = {
        "set": {"set_id": clone_id, "selected_count": 3},
        "recovery_context": {"sample_set_id": clone_id, "case_id": case_id},
        "items": [
            {
                "sample_id": "sample_safe",
                "aweme_id": "7654321098765432101",
                "case_id": case_id,
                "local_video_id": local_id,
                "title": "安全标题",
                "status": "completed",
                "source_url": "https://www.douyin.com/video/7654321098765432101",
                "signed_url": "https://v26-default.365yg.com/video.mp4?token=SECRET_SIGNED",
                "file_path": "/var/private/video.mp4",
                "request_headers": {"Authorization": "Bearer SECRET_HEADER"},
            }
        ],
        "pipeline_summary": {
            "selected_count": 3,
            "case_count": 1,
            "notes": [
                '"api_key": "SECRET_JSON" /var/private/cache https://secret.invalid',
                "队列已完成。",
            ],
        },
        "download": {
            "aweme_id": "7654321098765432101",
            "local_video_id": local_id,
            "file_path": "/var/private/video.mp4",
            "url": "https://v26-default.365yg.com/video.mp4?token=SECRET_SIGNED",
            "size_bytes": 1024,
        },
        "prompt": "SECRET_PROMPT",
        "api_key": "SECRET_API_KEY",
        "Authorization": "Basic SECRET_AUTH",
    }
    connection = sqlite3.connect(database_path)
    connection.execute(
        "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "job_safe_detail",
            "profile-build-cases",
            "running",
            76,
            '恢复队列，"cookie": "SECRET_COOKIE"',
            json.dumps(raw_result, ensure_ascii=False),
            "",
            now,
            now,
        ),
    )
    connection.commit()
    connection.close()
    monkeypatch.setattr(workbench_overview.settings, "database_url", _database_url(database_path))
    app = FastAPI()
    app.include_router(workbench_routes.router)

    response = TestClient(app).get("/api/workbench/jobs/job_safe_detail")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    job = response.json()["job"]
    assert job["id"] == "job_safe_detail"
    assert job["resume_target"]["resource_id"] == clone_id
    assert job["result_json"]["set"]["set_id"] == clone_id
    assert job["result_json"]["items"] == [
        {
            "sample_id": "sample_safe",
            "aweme_id": "7654321098765432101",
            "case_id": case_id,
            "local_video_id": local_id,
            "title": "安全标题",
            "status": "completed",
        }
    ]
    serialized = json.dumps(response.json(), ensure_ascii=False)
    for secret in (
        "SECRET_SIGNED",
        "SECRET_HEADER",
        "SECRET_JSON",
        "SECRET_PROMPT",
        "SECRET_API_KEY",
        "SECRET_AUTH",
        "SECRET_COOKIE",
        "/var/private",
        "365yg.com",
        "douyin.com",
        "secret.invalid",
    ):
        assert secret not in serialized
    for forbidden_key in ("source_url", "signed_url", "file_path", "request_headers", "prompt", "api_key", "Authorization"):
        assert f'"{forbidden_key}"' not in serialized


def test_workbench_job_api_returns_safe_not_found(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "overview.db"
    _create_database(database_path)
    monkeypatch.setattr(workbench_overview.settings, "database_url", _database_url(database_path))
    app = FastAPI()
    app.include_router(workbench_routes.router)

    missing = TestClient(app).get("/api/workbench/jobs/job_missing")
    invalid = TestClient(app).get("/api/workbench/jobs/not-a-job")

    assert missing.status_code == 404
    assert missing.json() == {"ok": False, "error_code": "JOB_NOT_FOUND", "message": "任务不存在。"}
    assert invalid.status_code == 404
    assert "detail" not in invalid.json()


def test_workbench_overview_degrades_one_failed_source_without_exception_details(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "overview.db"
    _create_database(database_path)
    cases_dir, creator_state_dir, creator_clones_dir = _runtime_paths(tmp_path)
    _patch_capabilities(monkeypatch)

    def fail_jobs(_database_url: str):
        raise OSError("SECRET_SENTINEL /var/private/project sk-secretvalue")

    monkeypatch.setattr(workbench_overview, "_collect_job_sections", fail_jobs)
    payload = workbench_overview.build_workbench_overview(
        database_url=_database_url(database_path),
        cases_dir=cases_dir,
        creator_state_dir=creator_state_dir,
        creator_clones_dir=creator_clones_dir,
    )
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["meta"]["partial"] is True
    assert [item["source"] for item in payload["source_errors"]] == ["jobs"]
    assert payload["recent_cases"] == []
    assert "SECRET_SENTINEL" not in serialized
    assert "/var/private" not in serialized
    assert "sk-secretvalue" not in serialized


def test_workbench_overview_handles_500_records_with_bounded_output(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "overview.db"
    _create_database(database_path)
    cases_dir, creator_state_dir, creator_clones_dir = _runtime_paths(tmp_path)
    _patch_capabilities(monkeypatch)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = []
    case_rows = []
    local_rows = []
    sessions: dict[str, dict] = {}
    for index in range(500):
        stamp = now.replace(microsecond=index).isoformat(sep=" ")
        rows.append(
            (
                f"job_{index:04d}",
                "profile-build-cases",
                "running",
                index % 100,
                f"处理中 {index}",
                "{}",
                "",
                stamp,
                stamp,
            )
        )
        case_id = f"case_{index:04d}"
        local_id = f"local_{index:04d}"
        case_rows.append((case_id, "", local_id, "success", stamp))
        local_rows.append((local_id, f"作品 {index}", "作者"))
        clone_id = f"clone_{index:04d}"
        sessions[clone_id] = {
            "session_id": clone_id,
            "project_id": clone_id,
            "state": "DONE",
            "updated_at": now.replace(microsecond=index).isoformat(),
        }
        clone_dir = creator_clones_dir / clone_id
        clone_dir.mkdir()
        (clone_dir / "samples.json").write_text(
            json.dumps(
                {
                    "title": f"创作者 {index}",
                    "sample_count": 20,
                    "selected_count": 5,
                    "samples": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (clone_dir / "creator_clone_result.json").write_text("{}", encoding="utf-8")
        (clone_dir / "creator_clone.html").write_text("<p>report</p>", encoding="utf-8")
    (creator_state_dir / "sessions.json").write_text(
        json.dumps({"sessions": sessions, "updated_at": now.isoformat()}),
        encoding="utf-8",
    )
    connection = sqlite3.connect(database_path)
    connection.executemany("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    connection.executemany("INSERT INTO case_artifacts VALUES (?, ?, ?, ?, ?)", case_rows)
    connection.executemany("INSERT INTO local_video_items VALUES (?, ?, ?)", local_rows)
    connection.commit()
    connection.close()

    json_read_count = 0
    original_read_json = workbench_overview._read_json_object

    def counted_read_json(path: Path, max_bytes: int):
        nonlocal json_read_count
        json_read_count += 1
        return original_read_json(path, max_bytes)

    monkeypatch.setattr(workbench_overview, "_read_json_object", counted_read_json)
    started = time.perf_counter()
    payload = workbench_overview.build_workbench_overview(
        database_url=_database_url(database_path),
        cases_dir=cases_dir,
        creator_state_dir=creator_state_dir,
        creator_clones_dir=creator_clones_dir,
    )
    elapsed = time.perf_counter() - started
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["capabilities"]["running_task_count"] == 500
    assert len(payload["running_tasks"]) == 5
    assert len(payload["recent_cases"]) == 5
    assert len(payload["recent_creator_reports"]) == 5
    assert payload["meta"]["truncated_sources"] == ["creator_runtime"]
    assert json_read_count <= 10
    assert len(serialized.encode("utf-8")) < 128 * 1024
    assert elapsed < 2.0


def test_workbench_overview_degrades_oversized_runtime_index_in_bounded_time(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "overview.db"
    _create_database(database_path)
    cases_dir, creator_state_dir, creator_clones_dir = _runtime_paths(tmp_path)
    _patch_capabilities(monkeypatch)
    (creator_state_dir / "sessions.json").write_bytes(
        b"{" + b"x" * workbench_overview.RUNTIME_INDEX_MAX_BYTES
    )

    started = time.perf_counter()
    payload = workbench_overview.build_workbench_overview(
        database_url=_database_url(database_path),
        cases_dir=cases_dir,
        creator_state_dir=creator_state_dir,
        creator_clones_dir=creator_clones_dir,
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0
    assert payload["meta"]["partial"] is True
    assert any(item["source"] == "creator_runtime" for item in payload["source_errors"])
    assert payload["recent_creator_reports"] == []


def test_workbench_overview_handles_missing_files_without_creating_outputs(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "overview.db"
    _create_database(database_path)
    cases_dir, creator_state_dir, creator_clones_dir = _runtime_paths(tmp_path)
    _patch_capabilities(monkeypatch)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
    connection = sqlite3.connect(database_path)
    connection.execute(
        "INSERT INTO case_artifacts VALUES (?, ?, ?, ?, ?)",
        ("case_missing", "", "local_missing", "success", now),
    )
    connection.execute("INSERT INTO local_video_items VALUES (?, ?, ?)", ("local_missing", "缺失素材", "作者"))
    connection.commit()
    connection.close()
    (creator_state_dir / "sessions.json").write_text(
        json.dumps(
            {
                "sessions": {
                    "clone_missing": {
                        "session_id": "clone_missing",
                        "project_id": "clone_missing",
                        "state": "SAMPLE_READY",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    before_files = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))

    payload = workbench_overview.build_workbench_overview(
        database_url=_database_url(database_path),
        cases_dir=cases_dir,
        creator_state_dir=creator_state_dir,
        creator_clones_dir=creator_clones_dir,
    )
    after_files = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))

    assert payload["recent_cases"][0]["status"] == "missing"
    assert payload["recent_creator_reports"] == []
    assert payload["resumable_tasks"][0]["task_id"] == "clone_missing"
    assert payload["resumable_tasks"][0]["report_status"] == "未生成"
    assert before_files == after_files


def test_workbench_overview_resumes_single_case_at_case_page(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "overview.db"
    _create_database(database_path)
    cases_dir, creator_state_dir, creator_clones_dir = _runtime_paths(tmp_path)
    _patch_capabilities(monkeypatch)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
    case_id = f"case_{'c' * 32}"
    connection = sqlite3.connect(database_path)
    connection.execute(
        "INSERT INTO case_artifacts VALUES (?, ?, ?, ?, ?)",
        (case_id, "", "local_resume", "success", now),
    )
    connection.execute("INSERT INTO local_video_items VALUES (?, ?, ?)", ("local_resume", "待拆解作品", "作者"))
    connection.commit()
    connection.close()
    case_dir = cases_dir / case_id
    case_dir.mkdir()
    (case_dir / "video.mp4").write_bytes(b"video")

    payload = workbench_overview.build_workbench_overview(
        database_url=_database_url(database_path),
        cases_dir=cases_dir,
        creator_state_dir=creator_state_dir,
        creator_clones_dir=creator_clones_dir,
    )

    task = payload["resumable_tasks"][0]
    assert task["status"] == "recoverable"
    assert task["resume_target"] == {
        "route": "single",
        "stage": "case",
        "resource_id": case_id,
        "job_id": "",
        "task_type": "single_work",
        "mode": "manual",
        "open_url": f"/cases/{case_id}",
    }
    assert task["available_results"] == ["Case 素材包", "关键帧与分析输入"]


def test_workbench_overview_maps_resumable_creator_and_marks_stale_strategy(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "overview.db"
    _create_database(database_path)
    cases_dir, creator_state_dir, creator_clones_dir = _runtime_paths(tmp_path)
    _patch_capabilities(monkeypatch)
    now = datetime.now(timezone.utc)
    sessions = {
        "clone_resume": {
            "session_id": "clone_resume",
            "project_id": "clone_resume",
            "state": "SAMPLE_SELECTED",
            "updated_at": now.isoformat(),
        },
        "clone_done": {
            "session_id": "clone_done",
            "project_id": "clone_done",
            "state": "DONE",
            "updated_at": now.replace(microsecond=1).isoformat(),
        },
    }
    (creator_state_dir / "sessions.json").write_text(json.dumps({"sessions": sessions}), encoding="utf-8")
    resume_dir = creator_clones_dir / "clone_resume"
    resume_dir.mkdir()
    (resume_dir / "samples.json").write_text(
        json.dumps(
            {
                "creator_name": "可继续创作者",
                "sample_count": 12,
                "selected_count": 4,
                "samples": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    done_dir = creator_clones_dir / "clone_done"
    done_dir.mkdir()
    (done_dir / "samples.json").write_text(
        json.dumps({"creator_name": "已完成创作者", "sample_count": 20, "selected_count": 8}, ensure_ascii=False),
        encoding="utf-8",
    )
    report_path = done_dir / "creator_clone_result.json"
    strategy_path = done_dir / "creator_strategy_plan.json"
    report_path.write_text("{}", encoding="utf-8")
    strategy_path.write_text("{}", encoding="utf-8")
    report_time = now.timestamp()
    os.utime(strategy_path, (report_time - 60, report_time - 60))
    os.utime(report_path, (report_time, report_time))

    payload = workbench_overview.build_workbench_overview(
        database_url=_database_url(database_path),
        cases_dir=cases_dir,
        creator_state_dir=creator_state_dir,
        creator_clones_dir=creator_clones_dir,
    )

    resumable = payload["resumable_tasks"][0]
    assert resumable["task_id"] == "clone_resume"
    assert resumable["current_step"] == "证据富化"
    assert resumable["sample_count"] == 12
    assert resumable["selected_count"] == 4
    assert resumable["status"] == "recoverable"
    assert resumable["resume_target"] == {
        "route": "profile",
        "stage": "enrich",
        "resource_id": "clone_resume",
        "job_id": "",
        "task_type": "creator_work",
        "mode": "manual",
        "open_url": "",
    }
    assert payload["recent_creator_reports"][0]["resource_id"] == "clone_done"
    assert payload["recent_creator_reports"][0]["resume_target"]["stage"] == "export"
    assert payload["recent_creator_reports"][0]["resume_target"]["mode"] == "result"
    assert payload["recent_strategy_plans"][0]["status"] == "stale"
    assert payload["recent_strategy_plans"][0]["resume_target"]["stage"] == "export"


def test_workbench_overview_recovers_sample_sets_missing_from_runtime_index(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "overview.db"
    _create_database(database_path)
    cases_dir, creator_state_dir, creator_clones_dir = _runtime_paths(tmp_path)
    _patch_capabilities(monkeypatch)
    pool_id = f"clone_{'1' * 32}"
    selected_id = f"clone_{'2' * 32}"
    report_id = f"clone_{'3' * 32}"
    for clone_id, payload in (
        (
            pool_id,
            {
                "set_id": pool_id,
                "creator_name": "仅素材池",
                "samples": [{"sample_id": "sample_pool"}],
                "selected_sample_ids": [],
            },
        ),
        (
            selected_id,
            {
                "set_id": selected_id,
                "creator_name": "已有选样",
                "samples": [{"sample_id": "sample_selected"}],
                "selected_sample_ids": ["sample_selected"],
            },
        ),
        (
            report_id,
            {
                "set_id": report_id,
                "creator_name": "已有报告",
                "samples": [{"sample_id": "sample_report"}],
                "selected_sample_ids": ["sample_report"],
            },
        ),
    ):
        clone_dir = creator_clones_dir / clone_id
        clone_dir.mkdir()
        (clone_dir / "samples.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    report_dir = creator_clones_dir / report_id
    (report_dir / "creator_clone_result.json").write_text("{}", encoding="utf-8")
    (report_dir / "creator_clone.html").write_text("<p>report</p>", encoding="utf-8")

    payload = workbench_overview.build_workbench_overview(
        database_url=_database_url(database_path),
        cases_dir=cases_dir,
        creator_state_dir=creator_state_dir,
        creator_clones_dir=creator_clones_dir,
    )

    tasks = {item["task_id"]: item for item in payload["resumable_tasks"]}
    assert tasks[pool_id]["resume_target"]["stage"] == "pool"
    assert tasks[pool_id]["workflow_state"] == "INGESTED"
    assert tasks[selected_id]["resume_target"]["stage"] == "select"
    assert tasks[selected_id]["workflow_state"] == "SAMPLE_READY"
    assert report_id not in tasks
    assert payload["recent_creator_reports"][0]["resource_id"] == report_id
    assert payload["source_errors"] == []


def test_orphan_sample_set_scan_reuses_short_lived_directory_index(tmp_path: Path, monkeypatch) -> None:
    creator_clones_dir = tmp_path / "creator_clones"
    creator_clones_dir.mkdir()
    clone_id = f"clone_{'4' * 32}"
    clone_dir = creator_clones_dir / clone_id
    clone_dir.mkdir()
    (clone_dir / "samples.json").write_text(
        json.dumps({"set_id": clone_id, "samples": [{"sample_id": "sample_1"}]}),
        encoding="utf-8",
    )
    workbench_overview._scan_sample_set_candidates.cache_clear()
    real_scandir = workbench_overview.os.scandir
    scan_count = 0

    def counted_scandir(path):
        nonlocal scan_count
        scan_count += 1
        return real_scandir(path)

    monkeypatch.setattr(workbench_overview.os, "scandir", counted_scandir)
    monkeypatch.setattr(workbench_overview.time, "monotonic", lambda: 100.0)

    first = workbench_overview._read_orphan_sample_sets(creator_clones_dir, set())
    second = workbench_overview._read_orphan_sample_sets(creator_clones_dir, set())

    assert first == second
    assert first[0][0]["project_id"] == clone_id
    assert scan_count == 1
    workbench_overview._scan_sample_set_candidates.cache_clear()


def test_workbench_overview_keeps_valid_creator_when_one_samples_file_is_malformed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "overview.db"
    _create_database(database_path)
    cases_dir, creator_state_dir, creator_clones_dir = _runtime_paths(tmp_path)
    _patch_capabilities(monkeypatch)
    now = datetime.now(timezone.utc)
    sessions = {
        "clone_bad": {
            "session_id": "clone_bad",
            "project_id": "clone_bad",
            "state": "SAMPLE_READY",
            "updated_at": now.isoformat(),
        },
        "clone_good": {
            "session_id": "clone_good",
            "project_id": "clone_good",
            "state": "SAMPLE_SELECTED",
            "updated_at": now.replace(microsecond=1).isoformat(),
        },
    }
    (creator_state_dir / "sessions.json").write_text(json.dumps({"sessions": sessions}), encoding="utf-8")
    bad_dir = creator_clones_dir / "clone_bad"
    bad_dir.mkdir()
    (bad_dir / "samples.json").write_text(
        json.dumps(
            {
                "creator_name": "损坏计数样本",
                "sample_count": {"unexpected": True},
                "selected_count": "unknown",
                "samples": {"not": "a list"},
                "selected_sample_ids": "not-a-list",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    good_dir = creator_clones_dir / "clone_good"
    good_dir.mkdir()
    (good_dir / "samples.json").write_text(
        json.dumps(
            {"creator_name": "合法创作者", "sample_count": 10, "selected_count": 3},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = workbench_overview.build_workbench_overview(
        database_url=_database_url(database_path),
        cases_dir=cases_dir,
        creator_state_dir=creator_state_dir,
        creator_clones_dir=creator_clones_dir,
    )

    assert not any(item["source"] == "creator_runtime" for item in payload["source_errors"])
    tasks = {item["task_id"]: item for item in payload["resumable_tasks"]}
    assert tasks["clone_good"]["sample_count"] == 10
    assert tasks["clone_good"]["selected_count"] == 3
    assert tasks["clone_bad"]["sample_count"] == 0
    assert tasks["clone_bad"]["selected_count"] == 0


def test_workbench_overview_maps_creator_runtime_states_to_exact_wizard_stages(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "overview.db"
    _create_database(database_path)
    cases_dir, creator_state_dir, creator_clones_dir = _runtime_paths(tmp_path)
    _patch_capabilities(monkeypatch)
    now = datetime.now(timezone.utc)
    expected = {
        "INGESTED": "pool",
        "SAMPLE_READY": "select",
        "SAMPLE_SELECTED": "enrich",
        "EVIDENCE_READY": "distill",
        "DISTILLING": "distill",
    }
    sessions = {}
    for index, (state, stage) in enumerate(expected.items()):
        clone_id = f"clone_{index:032x}"
        sessions[clone_id] = {
            "session_id": clone_id,
            "project_id": clone_id,
            "state": state,
            "updated_at": now.replace(microsecond=index).isoformat(),
        }
        clone_dir = creator_clones_dir / clone_id
        clone_dir.mkdir()
        (clone_dir / "samples.json").write_text(
            json.dumps(
                {
                    "creator_name": state,
                    "sample_count": 12,
                    "selected_count": 4 if stage in {"enrich", "distill"} else 0,
                }
            ),
            encoding="utf-8",
        )
    (creator_state_dir / "sessions.json").write_text(json.dumps({"sessions": sessions}), encoding="utf-8")

    payload = workbench_overview.build_workbench_overview(
        database_url=_database_url(database_path),
        cases_dir=cases_dir,
        creator_state_dir=creator_state_dir,
        creator_clones_dir=creator_clones_dir,
    )

    tasks = {item["title"]: item for item in payload["resumable_tasks"]}
    assert set(tasks) == set(expected)
    for state, stage in expected.items():
        task = tasks[state]
        assert task["status"] == "recoverable"
        assert task["resume_target"]["route"] == "profile"
        assert task["resume_target"]["stage"] == stage
        assert task["resume_target"]["mode"] == "manual"
        assert "不会自动执行" in task["recovery_hint"]


def test_workbench_overview_maps_creator_import_and_missing_done_report_to_boundary_stages(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "overview.db"
    _create_database(database_path)
    cases_dir, creator_state_dir, creator_clones_dir = _runtime_paths(tmp_path)
    _patch_capabilities(monkeypatch)
    now = datetime.now(timezone.utc)
    import_id = f"clone_{'e' * 32}"
    done_id = f"clone_{'f' * 32}"
    sessions = {
        import_id: {
            "session_id": import_id,
            "project_id": import_id,
            "state": "IMPORT",
            "updated_at": now.isoformat(),
        },
        done_id: {
            "session_id": done_id,
            "project_id": done_id,
            "state": "DONE",
            "updated_at": now.replace(microsecond=1).isoformat(),
        },
    }
    (creator_state_dir / "sessions.json").write_text(json.dumps({"sessions": sessions}), encoding="utf-8")
    for clone_id, name in ((import_id, "IMPORT"), (done_id, "DONE")):
        clone_dir = creator_clones_dir / clone_id
        clone_dir.mkdir()
        (clone_dir / "samples.json").write_text(
            json.dumps({"creator_name": name, "sample_count": 2, "selected_count": 1}),
            encoding="utf-8",
        )

    payload = workbench_overview.build_workbench_overview(
        database_url=_database_url(database_path),
        cases_dir=cases_dir,
        creator_state_dir=creator_state_dir,
        creator_clones_dir=creator_clones_dir,
    )

    tasks = {item["title"]: item for item in payload["resumable_tasks"]}
    assert tasks["IMPORT"]["resume_target"]["stage"] == "import"
    assert tasks["DONE"]["resume_target"]["stage"] == "export"
    assert tasks["DONE"]["report_status"] == "未生成"


def test_workbench_overview_is_read_only_and_does_not_call_network_or_llm(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "overview.db"
    _create_database(database_path)
    cases_dir, creator_state_dir, creator_clones_dir = _runtime_paths(tmp_path)
    _patch_capabilities(monkeypatch)
    before_hash = hashlib.sha256(database_path.read_bytes()).hexdigest()
    before_mtime = database_path.stat().st_mtime_ns
    before_tree = {
        str(path.relative_to(tmp_path)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    def forbid_connect(*_args, **_kwargs):
        raise AssertionError("overview attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", forbid_connect)
    payload = workbench_overview.build_workbench_overview(
        database_url=_database_url(database_path),
        cases_dir=cases_dir,
        creator_state_dir=creator_state_dir,
        creator_clones_dir=creator_clones_dir,
    )

    assert payload["source_errors"] == []
    assert hashlib.sha256(database_path.read_bytes()).hexdigest() == before_hash
    assert database_path.stat().st_mtime_ns == before_mtime
    after_tree = {
        str(path.relative_to(tmp_path)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after_tree == before_tree


def test_workbench_overview_redacts_sensitive_values(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "overview.db"
    _create_database(database_path)
    cases_dir, creator_state_dir, creator_clones_dir = _runtime_paths(tmp_path)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
    bearer_token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.real-signature"
    connection = sqlite3.connect(database_path)
    connection.execute(
        "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "job_secret",
            "profile-scan",
            "failed",
            10,
            "Cookie=sessionid=SECRET_COOKIE; sk-SECRETKEY123456 "
            "https://cdn.example/video.mp4?token=SECRET /var/private/video.mp4 "
            f"Authorization=Bearer {bearer_token}",
            json.dumps({"signed_url": "https://secret.invalid", "api_key": "SECRET_RESULT"}),
            "PROVIDER_FAILED",
            now,
            now,
        ),
    )
    connection.commit()
    connection.close()
    monkeypatch.setattr(
        workbench_overview,
        "douyin_source_health_payload",
        lambda: {
            "configured": True,
            "status": "success",
            "label": "自检成功",
            "masked_cookie": "SECRET_MASKED_COOKIE",
            "cookie_fingerprint": "SECRET_FINGERPRINT",
            "status_message": "ready",
        },
    )
    monkeypatch.setattr(
        workbench_overview,
        "llm_status_payload",
        lambda: {
            "configured": True,
            "provider": "openai_compatible",
            "model": "model",
            "api_key": "SECRET_API_KEY",
            "masked_api_key": "SECRET_MASKED_KEY",
            "api_base": "https://secret.invalid",
        },
    )
    monkeypatch.setattr(
        workbench_overview,
        "local_tools_summary_payload",
        lambda: {
            "status": "ready",
            "ready_count": 1,
            "total_count": 1,
            "checks": [{"id": "ffmpeg", "label": "ffmpeg", "status": "ready", "available": True, "path": "/secret/bin"}],
        },
    )

    payload = workbench_overview.build_workbench_overview(
        database_url=_database_url(database_path),
        cases_dir=cases_dir,
        creator_state_dir=creator_state_dir,
        creator_clones_dir=creator_clones_dir,
    )
    serialized = json.dumps(payload, ensure_ascii=False)

    for secret in (
        "SECRET_COOKIE",
        bearer_token,
        "SECRETKEY123456",
        "SECRET_RESULT",
        "SECRET_MASKED_COOKIE",
        "SECRET_FINGERPRINT",
        "SECRET_API_KEY",
        "SECRET_MASKED_KEY",
        "/var/private",
        "/secret/bin",
        "token=SECRET",
    ):
        assert secret not in serialized
    for forbidden_key in ("result_json", "masked_cookie", "cookie_fingerprint", "api_key", "masked_api_key", "api_base", "path"):
        assert f'"{forbidden_key}"' not in serialized


def test_douyin_health_tracks_cookie_self_test_without_exposing_fingerprint(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(runtime_settings, "LOCAL_SETTINGS_PATH", tmp_path / ".local_settings.json")
    cookie_a = "sessionid=COOKIE_A; sid_guard=1; uid_tt=1; uid_tt_ss=1; sid_tt=1; passport_csrf_token=1; passport_csrf_token_default=1; ttwid=1"
    cookie_b = cookie_a.replace("COOKIE_A", "COOKIE_B")
    monkeypatch.setattr(
        data_source_settings,
        "test_douyin_cookie_api",
        lambda **_kwargs: {"status": "ok", "message": "Cookie API 可用。"},
    )

    data_source_settings.update_douyin_settings_payload({"douyin_cookie": cookie_a})
    assert data_source_settings.douyin_source_health_payload()["status"] == "pending"
    data_source_settings.test_douyin_settings_payload({"profile_url": "https://www.douyin.com/user/MS4wTEST"})
    assert data_source_settings.douyin_source_health_payload()["status"] == "success"
    monkeypatch.setattr(
        data_source_settings,
        "test_douyin_cookie_api",
        lambda **_kwargs: {"status": "config_only", "message": "需要主页 URL。"},
    )
    data_source_settings.test_douyin_settings_payload({})
    assert data_source_settings.douyin_source_health_payload()["status"] == "success"
    data_source_settings.update_douyin_settings_payload({"user_agent": "Updated browser"})
    assert data_source_settings.douyin_source_health_payload()["status"] == "success"
    data_source_settings.update_douyin_settings_payload({"douyin_cookie": cookie_b})
    assert data_source_settings.douyin_source_health_payload()["status"] == "pending"
    data_source_settings.update_douyin_settings_payload({"clear_cookie": True})
    health = data_source_settings.douyin_source_health_payload()
    serialized = json.dumps(health, ensure_ascii=False)

    assert health["status"] == "not_configured"
    assert "COOKIE_A" not in serialized
    assert "COOKIE_B" not in serialized
    assert "cookie_fingerprint" not in serialized
