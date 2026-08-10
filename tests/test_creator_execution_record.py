from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.errors import AppError, ErrorCode
from app.main import app
from app.models import Job
from app.services.creator_intelligence import execution_record as record_module
from app.services.creator_intelligence.execution_record import (
    EXECUTION_RECORD_FILENAME,
    execution_record_path,
    load_creator_execution_record,
    start_creator_execution_record,
    update_creator_execution_record,
    validate_creator_execution_record,
)


client = TestClient(app)
PROJECT_ID = "clone_execution_record_test"


def _execution_pack(
    *,
    generated_at: str = "2026-08-09T10:00:00+00:00",
    topic_index: int = 2,
    title: str = "同一妆造三种人物状态测试",
) -> dict[str, Any]:
    return {
        "version": "1.0",
        "project_id": PROJECT_ID,
        "generated_at": generated_at,
        "topic_index": topic_index,
        "topic": {"title": title},
    }


def _valid_record() -> dict[str, Any]:
    return {
        "version": "1.0",
        "project_id": PROJECT_ID,
        "execution_pack_generated_at": "2026-08-09T10:00:00+00:00",
        "execution_pack_topic_index": 2,
        "selected_topic": "同一妆造三种人物状态测试",
        "status": "draft",
        "production_status": {
            "shooting": "pending",
            "editing": "pending",
            "publishing": "pending",
        },
        "feedback": {
            "was_used": False,
            "difficulty": "",
            "quality_rating": None,
            "result_rating": None,
            "notes": "",
        },
        "created_at": "2026-08-09T10:01:00+00:00",
        "updated_at": "2026-08-09T10:01:00+00:00",
    }


def _install_pack(monkeypatch, pack: dict[str, Any] | None = None, calls: list[str] | None = None) -> None:
    payload = copy.deepcopy(pack or _execution_pack())

    def load_pack(project_id: str) -> dict[str, Any]:
        if calls is not None:
            calls.append(project_id)
        return copy.deepcopy(payload)

    monkeypatch.setattr(record_module, "load_creator_execution_pack", load_pack)


def _start(monkeypatch, pack: dict[str, Any] | None = None) -> dict[str, Any]:
    _install_pack(monkeypatch, pack)
    return start_creator_execution_record(PROJECT_ID)


def test_execution_record_schema_accepts_valid_record() -> None:
    record = validate_creator_execution_record(_valid_record(), expected_project_id=PROJECT_ID)

    assert record["version"] == "1.0"
    assert record["status"] == "draft"
    assert record["production_status"] == {
        "shooting": "pending",
        "editing": "pending",
        "publishing": "pending",
    }


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("status",), "blocked"),
        (("production_status", "shooting"), "failed"),
        (("production_status", "editing"), "waiting"),
        (("production_status", "publishing"), "queued"),
        (("feedback", "difficulty"), "extreme"),
    ],
)
def test_execution_record_schema_rejects_invalid_enums(path: tuple[str, ...], value: str) -> None:
    payload = _valid_record()
    target: dict[str, Any] = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValueError):
        validate_creator_execution_record(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quality_rating", 0),
        ("quality_rating", 6),
        ("result_rating", 0),
        ("result_rating", 6),
    ],
)
def test_execution_record_schema_rejects_out_of_range_ratings(field: str, value: int) -> None:
    payload = _valid_record()
    payload["feedback"][field] = value

    with pytest.raises(ValueError):
        validate_creator_execution_record(payload)


def test_execution_record_schema_rejects_notes_over_1000_characters() -> None:
    payload = _valid_record()
    payload["feedback"]["notes"] = "x" * 1001

    with pytest.raises(ValueError):
        validate_creator_execution_record(payload)


def test_start_requires_an_existing_execution_pack(monkeypatch) -> None:
    def missing_pack(_project_id: str):
        raise AppError(ErrorCode.EXECUTION_PACK_NOT_READY)

    monkeypatch.setattr(record_module, "load_creator_execution_pack", missing_pack)

    response = client.post(f"/api/creator-intelligence/projects/{PROJECT_ID}/execution-record/start")

    assert response.status_code == 400
    assert response.json()["error_code"] == ErrorCode.EXECUTION_PACK_NOT_READY
    assert not execution_record_path(PROJECT_ID).exists()


def test_get_missing_record_uses_not_ready_contract() -> None:
    response = client.get(f"/api/creator-intelligence/projects/{PROJECT_ID}/execution-record")

    assert response.status_code == 400
    assert response.json()["error_code"] == ErrorCode.EXECUTION_RECORD_NOT_READY


def test_start_is_idempotent_and_uses_server_owned_pack_fields(monkeypatch) -> None:
    calls: list[str] = []
    _install_pack(monkeypatch, calls=calls)

    first = client.post(f"/api/creator-intelligence/projects/{PROJECT_ID}/execution-record/start")
    second = client.post(f"/api/creator-intelligence/projects/{PROJECT_ID}/execution-record/start")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.headers["cache-control"] == "no-store"
    assert first.json() == second.json()
    assert calls == [PROJECT_ID]
    record = first.json()["execution_record"]
    assert record["project_id"] == PROJECT_ID
    assert record["execution_pack_generated_at"] == "2026-08-09T10:00:00+00:00"
    assert record["execution_pack_topic_index"] == 2
    assert record["selected_topic"] == "同一妆造三种人物状态测试"
    assert record["status"] == "draft"
    assert record["feedback"]["was_used"] is False
    assert datetime.fromisoformat(record["created_at"]).tzinfo is not None
    assert datetime.fromisoformat(record["updated_at"]).tzinfo is not None
    assert execution_record_path(PROJECT_ID).is_file()


def test_patch_single_stage_preserves_other_stages_and_advances_status(monkeypatch) -> None:
    _start(monkeypatch)

    response = client.patch(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/execution-record",
        json={"production_status": {"shooting": "completed"}},
    )

    assert response.status_code == 200
    record = response.json()["execution_record"]
    assert record["production_status"] == {
        "shooting": "completed",
        "editing": "pending",
        "publishing": "pending",
    }
    assert record["status"] == "in_progress"
    assert record["feedback"]["was_used"] is True


def test_feedback_partial_update_preserves_production_state(monkeypatch) -> None:
    _start(monkeypatch)
    update_creator_execution_record(PROJECT_ID, {"production_status": {"shooting": "completed"}})

    response = client.patch(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/execution-record",
        json={"feedback": {"difficulty": "normal", "quality_rating": 4, "notes": "拍摄顺利"}},
    )

    assert response.status_code == 200
    record = response.json()["execution_record"]
    assert record["production_status"]["shooting"] == "completed"
    assert record["production_status"]["editing"] == "pending"
    assert record["status"] == "in_progress"
    assert record["feedback"]["difficulty"] == "normal"
    assert record["feedback"]["quality_rating"] == 4
    assert record["feedback"]["result_rating"] is None


def test_client_cannot_overwrite_server_owned_fields(monkeypatch) -> None:
    original = _start(monkeypatch)

    response = client.patch(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/execution-record",
        json={
            "project_id": "clone_attacker",
            "execution_pack_generated_at": "2030-01-01T00:00:00+00:00",
            "execution_pack_topic_index": 99,
            "selected_topic": "伪造选题",
            "created_at": "2030-01-01T00:00:00+00:00",
            "feedback": {"notes": "只更新备注"},
        },
    )

    assert response.status_code == 200
    record = response.json()["execution_record"]
    for field in (
        "project_id",
        "execution_pack_generated_at",
        "execution_pack_topic_index",
        "selected_topic",
        "created_at",
    ):
        assert record[field] == original[field]
    assert record["feedback"]["notes"] == "只更新备注"


def test_status_progresses_to_completed_and_feedback_keeps_it_completed(monkeypatch) -> None:
    _start(monkeypatch)
    for stage in ("shooting", "editing", "publishing"):
        record = update_creator_execution_record(PROJECT_ID, {"production_status": {stage: "completed"}})

    assert record["status"] == "completed"
    updated = update_creator_execution_record(PROJECT_ID, {"feedback": {"result_rating": 5}})
    assert updated["status"] == "completed"
    assert updated["feedback"]["result_rating"] == 5


def test_archived_status_is_preserved_when_feedback_changes(monkeypatch) -> None:
    _start(monkeypatch)
    archived = update_creator_execution_record(PROJECT_ID, {"status": "archived"})
    assert archived["status"] == "archived"

    updated = update_creator_execution_record(PROJECT_ID, {"feedback": {"difficulty": "hard"}})

    assert updated["status"] == "archived"
    assert updated["feedback"]["difficulty"] == "hard"


def test_record_binding_does_not_follow_a_regenerated_execution_pack(monkeypatch) -> None:
    original = _start(monkeypatch, _execution_pack(generated_at="2026-08-09T10:00:00+00:00", title="选题 A"))
    _install_pack(monkeypatch, _execution_pack(generated_at="2030-01-01T00:00:00+00:00", title="选题 B"))

    loaded = load_creator_execution_record(PROJECT_ID)

    assert loaded["execution_pack_generated_at"] == original["execution_pack_generated_at"]
    assert loaded["execution_pack_topic_index"] == original["execution_pack_topic_index"]
    assert loaded["selected_topic"] == "选题 A"


def test_record_persistence_is_atomic_and_does_not_modify_upstream_files(monkeypatch) -> None:
    output_dir = settings.creator_clones_dir / PROJECT_ID
    output_dir.mkdir(parents=True, exist_ok=True)
    upstream_names = (
        "creator_execution_pack.json",
        "creator_strategy_plan.json",
        "creator_clone_result.json",
        "samples.json",
    )
    for name in upstream_names:
        (output_dir / name).write_bytes(f"unchanged:{name}".encode())
    before = {name: (output_dir / name).read_bytes() for name in upstream_names}
    _install_pack(monkeypatch)

    start_creator_execution_record(PROJECT_ID)
    update_creator_execution_record(PROJECT_ID, {"production_status": {"shooting": "skipped"}})

    assert execution_record_path(PROJECT_ID).is_file()
    assert {name: (output_dir / name).read_bytes() for name in upstream_names} == before
    assert not list(output_dir.glob(f".{EXECUTION_RECORD_FILENAME}.*.tmp"))


def test_feedback_notes_are_redacted_in_api_and_persisted_file(monkeypatch) -> None:
    _start(monkeypatch)
    notes = (
        "Cookie=sessionid=secret Authorization: Bearer top-secret "
        "API_KEY=hidden sk-1234567890abcdef "
        "/Users/test/private/video.mp4 https://cdn.example.test/video?token=signed"
    )

    response = client.patch(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/execution-record",
        json={"feedback": {"notes": notes}},
    )

    assert response.status_code == 200
    serialized = json.dumps(response.json(), ensure_ascii=False).lower()
    file_text = execution_record_path(PROJECT_ID).read_text(encoding="utf-8").lower()
    for value in (serialized, file_text):
        assert "sessionid=secret" not in value
        assert "bearer top-secret" not in value
        assert "api_key=hidden" not in value
        assert "sk-1234567890abcdef" not in value
        assert "/users/test" not in value
        assert "cdn.example.test" not in value
    assert "[redacted" in file_text


def test_record_apis_do_not_create_jobs_or_call_upstream_services(monkeypatch) -> None:
    _install_pack(monkeypatch)
    with SessionLocal() as session:
        jobs_before = session.query(Job).count()

    forbidden_calls: list[str] = []

    def forbidden(*_args, **_kwargs):
        forbidden_calls.append("called")
        raise AssertionError("Execution Record must not invoke upstream work")

    monkeypatch.setattr("app.services.profile_scan.scan_profile", forbidden)
    monkeypatch.setattr("app.services.downloader.download_candidate", forbidden)
    monkeypatch.setattr("app.services.asr.run_case_asr", forbidden)
    monkeypatch.setattr("app.services.ocr.run_case_ocr", forbidden)
    monkeypatch.setattr("app.services.creator_clone.distill_creator_clone", forbidden)

    start_response = client.post(f"/api/creator-intelligence/projects/{PROJECT_ID}/execution-record/start")
    patch_response = client.patch(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/execution-record",
        json={"production_status": {"shooting": "completed"}},
    )
    get_response = client.get(f"/api/creator-intelligence/projects/{PROJECT_ID}/execution-record")

    assert start_response.status_code == patch_response.status_code == get_response.status_code == 200
    assert forbidden_calls == []
    with SessionLocal() as session:
        assert session.query(Job).count() == jobs_before


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "failed"},
        {"production_status": {"shooting": "blocked"}},
        {"feedback": {"difficulty": "impossible"}},
        {"feedback": {"quality_rating": 0}},
        {"feedback": {"result_rating": 6}},
        {"feedback": {"notes": "x" * 1001}},
    ],
)
def test_patch_api_rejects_invalid_contract_values(monkeypatch, payload: dict[str, Any]) -> None:
    _start(monkeypatch)

    response = client.patch(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/execution-record",
        json=payload,
    )

    assert response.status_code == 422


def test_project_id_alias_cannot_open_another_execution_record(monkeypatch) -> None:
    _start(monkeypatch)

    response = client.get(f"/api/creator-intelligence/projects/{PROJECT_ID}../execution-record")

    assert response.status_code == 400
    assert response.json()["error_code"] == ErrorCode.EXECUTION_RECORD_NOT_READY
