from __future__ import annotations

import copy
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier, Thread
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.errors import AppError, ErrorCode
from app.main import app
from app.models import Job
from app.services.creator_intelligence.execution_pack import execution_pack_path
from app.services.creator_intelligence.execution_pack import generate_creator_execution_pack
from app.services.creator_intelligence.execution_record import (
    execution_record_path,
    start_creator_execution_record,
    update_creator_execution_record,
)
from app.services.creator_intelligence.iteration_history import (
    get_creator_iteration_artifact,
    list_creator_iterations,
    start_next_creator_iteration,
)
from app.services.creator_intelligence.iteration_storage import (
    ITERATION_INDEX_FILENAME,
    ITERATION_INDEX_MAX_BYTES,
    LEGACY_ITERATION_ID,
    creator_iteration_index_path,
    resolve_current_iteration_context,
    resolve_iteration_context,
    validate_creator_iteration_index,
    write_creator_iteration_index,
)
from app.services.creator_intelligence.outcome_snapshot import (
    append_creator_outcome_snapshot,
    creator_outcome_timeline_path,
    update_creator_outcome_snapshot,
    upsert_creator_outcome_timeline,
)
from app.services.creator_intelligence import execution_record as execution_record_service
from app.services.creator_intelligence import iteration_storage as iteration_storage_service
from app.services.creator_intelligence import outcome_snapshot as outcome_snapshot_service
from tests.test_creator_execution_pack import (
    FakeProvider,
    _execution_payload,
    _write_upstream,
)


client = TestClient(app)
PROJECT_ID = "clone_iteration_test"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ref(
    sequence: int,
    *,
    current: bool = False,
    legacy: bool = False,
    state: str | None = None,
) -> dict[str, Any]:
    active = current if state is None else state == "active"
    return {
        "iteration_id": LEGACY_ITERATION_ID if legacy else f"iteration_{sequence:032x}",
        "sequence": sequence,
        "storage_mode": "legacy_root" if legacy else "iteration_dir",
        "state": "active" if active else "closed",
        "created_at": f"2026-08-{min(sequence, 28):02d}T00:00:00+00:00",
        "closed_at": "" if active else f"2026-08-{min(sequence, 28):02d}T01:00:00+00:00",
        "close_reason": "" if active else "execution_completed",
        "close_note": "",
    }


def _index(refs: list[dict[str, Any]], current_id: str = "") -> dict[str, Any]:
    return {
        "version": "1.0",
        "project_id": PROJECT_ID,
        "current_iteration_id": current_id,
        "iterations": refs,
        "created_at": "2026-08-01T00:00:00+00:00",
        "updated_at": "2026-08-20T00:00:00+00:00",
    }


def _project_dir() -> Path:
    path = settings.creator_clones_dir / PROJECT_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _record(*, status: str = "draft", project_id: str = PROJECT_ID) -> dict[str, Any]:
    return {
        "version": "1.0",
        "project_id": project_id,
        "execution_pack_generated_at": "2026-08-09T10:00:00+00:00",
        "execution_pack_topic_index": 2,
        "selected_topic": "同一妆造三种人物状态测试",
        "status": status,
        "production_status": {
            "shooting": "completed" if status in {"completed", "archived"} else "pending",
            "editing": "completed" if status in {"completed", "archived"} else "pending",
            "publishing": "completed" if status in {"completed", "archived"} else "pending",
        },
        "feedback": {
            "was_used": status in {"completed", "archived"},
            "difficulty": "",
            "quality_rating": None,
            "result_rating": None,
            "notes": "",
        },
        "created_at": "2026-08-09T10:01:00+00:00",
        "updated_at": "2026-08-09T10:02:00+00:00",
    }


def _outcome(*, views: int | None = 0) -> dict[str, Any]:
    return {
        "version": "1.0",
        "project_id": PROJECT_ID,
        "execution_record_created_at": "2026-08-09T10:01:00+00:00",
        "execution_pack_generated_at": "2026-08-09T10:00:00+00:00",
        "execution_pack_topic_index": 2,
        "selected_topic": "同一妆造三种人物状态测试",
        "expected_metric": "播放与互动",
        "publication": {
            "platform": "douyin",
            "platform_item_id": "7654321098765432100",
            "published_url": "https://www.douyin.com/video/7654321098765432100",
            "published_at": "2026-08-10T09:30:00+08:00",
        },
        "snapshots": [
            {
                "snapshot_id": f"snapshot_{'a' * 32}",
                "captured_at": "2026-08-10T02:10:00+00:00",
                "source": "manual",
                "metrics": {
                    "views": views,
                    "likes": 0,
                    "comments": None,
                    "shares": 0,
                    "collects": None,
                },
                "derived": {},
            }
        ],
        "warnings": [],
        "created_at": "2026-08-10T02:00:00+00:00",
        "updated_at": "2026-08-10T02:10:00+00:00",
    }


def test_index_schema_accepts_empty_closed_and_active_shapes() -> None:
    assert validate_creator_iteration_index(_index([]), expected_project_id=PROJECT_ID)["iterations"] == []
    active = _ref(1, current=True)
    assert validate_creator_iteration_index(
        _index([active], active["iteration_id"]), expected_project_id=PROJECT_ID
    )["current_iteration_id"] == active["iteration_id"]
    closed = _ref(1)
    active = _ref(2, current=True)
    validated = validate_creator_iteration_index(
        _index([closed, active], active["iteration_id"]), expected_project_id=PROJECT_ID
    )
    assert [item["sequence"] for item in validated["iterations"]] == [1, 2]


@pytest.mark.parametrize(
    "mutator",
    [
        lambda refs, payload: refs.append(copy.deepcopy(refs[0])),
        lambda refs, payload: refs[1].update(sequence=refs[0]["sequence"]),
        lambda refs, payload: refs[0].update(state="active", closed_at="", close_reason=""),
        lambda refs, payload: payload.update(current_iteration_id="iteration_ffffffffffffffffffffffffffffffff"),
        lambda refs, payload: refs[0].update(iteration_id="../escape"),
        lambda refs, payload: refs[0].update(storage_mode="legacy_root"),
        lambda refs, payload: refs[0].update(created_at="2026-08-01T00:00:00"),
        lambda refs, payload: refs[1].update(close_note="active note"),
    ],
)
def test_index_schema_rejects_invalid_invariants(mutator) -> None:
    refs = [_ref(1), _ref(2, current=True)]
    payload = _index(refs, refs[1]["iteration_id"])
    mutator(refs, payload)
    with pytest.raises(ValueError):
        validate_creator_iteration_index(payload, expected_project_id=PROJECT_ID)


def test_index_rejects_more_than_128_iterations() -> None:
    refs = [_ref(index) for index in range(1, 129)]
    refs[-1] = _ref(128, current=True)
    refs.append(_ref(129, current=True))
    with pytest.raises(ValueError):
        validate_creator_iteration_index(
            _index(refs, refs[-1]["iteration_id"]), expected_project_id=PROJECT_ID
        )


def test_oversize_and_corrupt_index_fail_closed_without_rewrite() -> None:
    path = _project_dir() / ITERATION_INDEX_FILENAME
    path.write_bytes(b"{" + b"x" * ITERATION_INDEX_MAX_BYTES)
    before = path.read_bytes()
    with pytest.raises(AppError) as captured:
        list_creator_iterations(PROJECT_ID)
    assert captured.value.code == ErrorCode.ITERATION_INDEX_INVALID
    assert path.read_bytes() == before

    path.write_text("{broken", encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(AppError) as captured:
        execution_pack_path(PROJECT_ID)
    assert captured.value.code == ErrorCode.ITERATION_INDEX_INVALID
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "filename",
    [
        "creator_execution_pack.json",
        "creator_execution_record.json",
        "creator_outcome_snapshots.json",
    ],
)
def test_virtual_legacy_is_read_only_for_each_root_artifact(filename: str) -> None:
    root = _project_dir()
    (root / filename).write_text("{}", encoding="utf-8")
    index_path = root / ITERATION_INDEX_FILENAME

    result = list_creator_iterations(PROJECT_ID)

    assert result["current_iteration_id"] == LEGACY_ITERATION_ID
    assert result["iterations"][0]["storage_mode"] == "legacy_root"
    assert not index_path.exists()


def test_no_assets_returns_empty_without_filesystem_mutation() -> None:
    project_dir = settings.creator_clones_dir / PROJECT_ID
    response = client.get(f"/api/creator-intelligence/projects/{PROJECT_ID}/iterations")

    assert response.status_code == 200
    assert response.json()["iterations"] == []
    assert response.json()["current_iteration_id"] == ""
    assert not project_dir.exists()


def test_materialize_legacy_preserves_root_bytes_and_does_not_create_legacy_directory() -> None:
    root = _project_dir()
    paths = {
        "creator_execution_pack.json": root / "creator_execution_pack.json",
        "creator_execution_record.json": root / "creator_execution_record.json",
        "creator_outcome_snapshots.json": root / "creator_outcome_snapshots.json",
    }
    paths["creator_execution_pack.json"].write_text('{"generated_at":"2026-08-01T00:00:00+00:00"}', encoding="utf-8")
    _write_json(paths["creator_execution_record.json"], _record(status="completed"))
    paths["creator_outcome_snapshots.json"].write_text('{"created_at":"2026-08-03T00:00:00+00:00"}', encoding="utf-8")
    before = {name: path.read_bytes() for name, path in paths.items()}

    result = start_next_creator_iteration(PROJECT_ID)
    index = json.loads((root / ITERATION_INDEX_FILENAME).read_text(encoding="utf-8"))

    assert index["iterations"][0]["iteration_id"] == LEGACY_ITERATION_ID
    assert index["iterations"][0]["state"] == "closed"
    assert index["iterations"][0]["storage_mode"] == "legacy_root"
    assert index["iterations"][0]["close_reason"] == "execution_completed"
    assert index["iterations"][1]["state"] == "active"
    assert result["current_iteration"]["sequence"] == 2
    assert {name: path.read_bytes() for name, path in paths.items()} == before
    assert not (root / "iterations" / LEGACY_ITERATION_ID).exists()


def test_current_resolver_routes_all_artifacts_to_the_same_iteration() -> None:
    assert execution_pack_path(PROJECT_ID).parent == settings.creator_clones_dir / PROJECT_ID
    assert execution_record_path(PROJECT_ID).parent == settings.creator_clones_dir / PROJECT_ID
    assert creator_outcome_timeline_path(PROJECT_ID).parent == settings.creator_clones_dir / PROJECT_ID

    legacy = _ref(1, current=True, legacy=True)
    write_creator_iteration_index(PROJECT_ID, _index([legacy], legacy["iteration_id"]))
    assert execution_pack_path(PROJECT_ID).parent == settings.creator_clones_dir / PROJECT_ID

    current = _ref(2, current=True)
    legacy = _ref(1, legacy=True)
    write_creator_iteration_index(PROJECT_ID, _index([legacy, current], current["iteration_id"]))
    expected = settings.creator_clones_dir / PROJECT_ID / "iterations" / current["iteration_id"]
    assert execution_pack_path(PROJECT_ID).parent == expected
    assert execution_record_path(PROJECT_ID).parent == expected
    assert creator_outcome_timeline_path(PROJECT_ID).parent == expected


@pytest.mark.parametrize(
    ("record_status", "close_current", "close_reason", "allowed", "expected_reason"),
    [
        ("draft", False, "", False, ""),
        ("in_progress", False, "", False, ""),
        ("draft", True, "", False, ""),
        ("draft", True, "cancelled", True, "cancelled"),
        ("completed", False, "", True, "execution_completed"),
        ("archived", False, "", True, "execution_archived"),
    ],
)
def test_start_next_close_policy(
    record_status: str,
    close_current: bool,
    close_reason: str,
    allowed: bool,
    expected_reason: str,
) -> None:
    _write_json(_project_dir() / "creator_execution_record.json", _record(status=record_status))
    if not allowed:
        before = (_project_dir() / "creator_execution_record.json").read_bytes()
        with pytest.raises(AppError) as captured:
            start_next_creator_iteration(
                PROJECT_ID,
                close_current=close_current,
                close_reason=close_reason,
            )
        assert captured.value.code == ErrorCode.CURRENT_ITERATION_ACTIVE
        assert not creator_iteration_index_path(PROJECT_ID).exists()
        assert (_project_dir() / "creator_execution_record.json").read_bytes() == before
        return

    result = start_next_creator_iteration(
        PROJECT_ID,
        close_current=close_current,
        close_reason=close_reason,
    )
    assert result["previous_iteration"]["close_reason"] == expected_reason


def test_repeated_start_next_creates_at_most_one_new_iteration() -> None:
    _write_json(_project_dir() / "creator_execution_record.json", _record(status="completed"))
    first = start_next_creator_iteration(PROJECT_ID)

    with pytest.raises(AppError) as captured:
        start_next_creator_iteration(PROJECT_ID)

    assert captured.value.code == ErrorCode.CURRENT_ITERATION_ACTIVE
    persisted = json.loads(creator_iteration_index_path(PROJECT_ID).read_text(encoding="utf-8"))
    assert len(persisted["iterations"]) == 2
    assert len({item["sequence"] for item in persisted["iterations"]}) == 2
    assert sum(item["state"] == "active" for item in persisted["iterations"]) == 1
    assert persisted["current_iteration_id"] == first["current_iteration"]["iteration_id"]


def test_concurrent_start_next_creates_only_one_iteration() -> None:
    _write_json(_project_dir() / "creator_execution_record.json", _record(status="completed"))
    barrier = Barrier(2)
    results: list[str] = []

    def run() -> None:
        barrier.wait()
        try:
            start_next_creator_iteration(PROJECT_ID)
            results.append("success")
        except AppError as error:
            results.append(error.code)

    threads = [Thread(target=run), Thread(target=run)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == sorted(["success", ErrorCode.CURRENT_ITERATION_ACTIVE])


def test_iteration_limit_rejects_without_changing_index() -> None:
    refs = [_ref(index) for index in range(1, 128)]
    refs.append(_ref(128, current=True))
    write_creator_iteration_index(PROJECT_ID, _index(refs, refs[-1]["iteration_id"]))
    path = creator_iteration_index_path(PROJECT_ID)
    before = path.read_bytes()

    with pytest.raises(AppError) as captured:
        start_next_creator_iteration(PROJECT_ID, close_current=True, close_reason="other")

    assert captured.value.code == ErrorCode.ITERATION_LIMIT_REACHED
    assert path.read_bytes() == before


def test_history_partial_artifacts_and_missing_vs_zero_are_preserved() -> None:
    current = _ref(1, current=True)
    write_creator_iteration_index(PROJECT_ID, _index([current], current["iteration_id"]))
    context = resolve_current_iteration_context(PROJECT_ID)
    _write_json(context.base_dir / "creator_execution_record.json", _record(status="completed"))
    _write_json(context.base_dir / "creator_outcome_snapshots.json", _outcome(views=0))

    result = list_creator_iterations(PROJECT_ID)["iterations"][0]

    assert result["execution_pack_status"] == "missing"
    assert result["execution_record_status"] == "completed"
    assert result["outcome_status"] == "ready"
    assert result["latest_metrics"]["views"] == 0
    assert result["latest_metrics"]["comments"] is None


def test_history_artifact_endpoint_is_standalone_and_read_only() -> None:
    closed = _ref(1)
    current = _ref(2, current=True)
    write_creator_iteration_index(PROJECT_ID, _index([closed, current], current["iteration_id"]))
    historical = resolve_iteration_context(PROJECT_ID, closed["iteration_id"])
    _write_json(historical.base_dir / "creator_execution_record.json", _record(status="completed"))
    before = (historical.base_dir / "creator_execution_record.json").read_bytes()

    response = client.get(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/iterations/"
        f"{closed['iteration_id']}/artifacts/execution-record"
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["artifact"]["status"] == "completed"
    assert (historical.base_dir / "creator_execution_record.json").read_bytes() == before
    assert client.patch(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/iterations/"
        f"{closed['iteration_id']}/artifacts/execution-record"
    ).status_code == 405


def test_invalid_or_missing_history_artifact_does_not_break_list() -> None:
    current = _ref(1, current=True)
    write_creator_iteration_index(PROJECT_ID, _index([current], current["iteration_id"]))
    context = resolve_current_iteration_context(PROJECT_ID)
    path = context.base_dir / "creator_outcome_snapshots.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken", encoding="utf-8")

    response = client.get(f"/api/creator-intelligence/projects/{PROJECT_ID}/iterations")
    artifact = client.get(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/iterations/"
        f"{current['iteration_id']}/artifacts/outcome"
    )

    assert response.status_code == 200
    assert response.json()["iterations"][0]["outcome_status"] == "invalid"
    assert artifact.status_code == 400
    assert artifact.json()["error_code"] == ErrorCode.ITERATION_ARTIFACT_INVALID


def test_start_next_and_read_apis_create_no_jobs() -> None:
    _write_json(_project_dir() / "creator_execution_record.json", _record(status="completed"))
    with SessionLocal() as session:
        before = session.query(Job).count()

    result = start_next_creator_iteration(PROJECT_ID)
    client.get(f"/api/creator-intelligence/projects/{PROJECT_ID}/iterations")
    client.get(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/iterations/"
        f"{result['current_iteration']['iteration_id']}"
    )

    with SessionLocal() as session:
        assert session.query(Job).count() == before


def test_close_note_is_bounded_and_redacts_sensitive_values() -> None:
    _write_json(_project_dir() / "creator_execution_record.json", _record(status="draft"))
    result = start_next_creator_iteration(
        PROJECT_ID,
        close_current=True,
        close_reason="other",
        close_note=(
            "Cookie=sessionid-secret; ttwid=browser-secret "
            "Authorization=Bearer-secret sk-1234567890abcdef "
            "https://example.com/video?token=secret "
            "/Users/example/private.json normal note"
        ),
    )
    persisted = json.loads(creator_iteration_index_path(PROJECT_ID).read_text(encoding="utf-8"))
    note = persisted["iterations"][0]["close_note"]
    assert "sessionid-secret" not in note
    assert "browser-secret" not in note
    assert "Bearer-secret" not in note
    assert "sk-1234567890abcdef" not in note
    assert "example.com" not in note
    assert "/Users/" not in note
    assert "normal note" in note
    assert result["current_iteration"]["state"] == "active"


def test_unregistered_iteration_and_symlink_are_rejected() -> None:
    current = _ref(1, current=True)
    write_creator_iteration_index(PROJECT_ID, _index([current], current["iteration_id"]))
    with pytest.raises(AppError) as captured:
        resolve_iteration_context(PROJECT_ID, "iteration_ffffffffffffffffffffffffffffffff")
    assert captured.value.code == ErrorCode.ITERATION_NOT_FOUND

    context = resolve_current_iteration_context(PROJECT_ID)
    context.base_dir.mkdir(parents=True, exist_ok=True)
    target = _project_dir() / "target.json"
    target.write_text("{}", encoding="utf-8")
    artifact = context.base_dir / "creator_execution_record.json"
    artifact.symlink_to(target)
    with pytest.raises(AppError) as captured:
        get_creator_iteration_artifact(PROJECT_ID, current["iteration_id"], "execution-record")
    assert captured.value.code == ErrorCode.ITERATION_ARTIFACT_INVALID


def test_execution_pack_long_operation_refuses_cross_iteration_write() -> None:
    sample_set, output_dir = _write_upstream()

    class SwitchingProvider(FakeProvider):
        def analyze(self, prompt: str, image_paths: list[Path]) -> Any:
            start_next_creator_iteration(sample_set.set_id)
            return super().analyze(prompt, image_paths)

    with pytest.raises(AppError) as captured:
        generate_creator_execution_pack(
            sample_set.set_id,
            0,
            provider=SwitchingProvider([_execution_payload()]),
        )

    assert captured.value.code == ErrorCode.ITERATION_CONTEXT_CHANGED
    assert not (output_dir / "creator_execution_pack.json").exists()
    index = json.loads((output_dir / ITERATION_INDEX_FILENAME).read_text(encoding="utf-8"))
    current = next(item for item in index["iterations"] if item["state"] == "active")
    assert not (
        output_dir / "iterations" / current["iteration_id"] / "creator_execution_pack.json"
    ).exists()


@pytest.mark.parametrize(
    "operation",
    ["record_start", "record_patch", "outcome_put", "outcome_post", "outcome_patch"],
)
def test_current_artifact_writes_refuse_cross_iteration_switch(monkeypatch, operation: str) -> None:
    sample_set, output_dir = _write_upstream()
    project_id = sample_set.set_id
    generate_creator_execution_pack(project_id, 0, provider=FakeProvider([_execution_payload()]))
    publication = {
        "platform": "douyin",
        "platform_item_id": "7654321098765432100",
        "published_url": "https://www.douyin.com/video/7654321098765432100",
        "published_at": "2026-08-10T09:30:00+08:00",
    }
    metrics = {"views": 100, "likes": 10, "comments": 1, "shares": 0, "collects": None}
    snapshot_id = ""

    if operation != "record_start":
        start_creator_execution_record(project_id)
    if operation.startswith("outcome"):
        update_creator_execution_record(
            project_id,
            {"production_status": {"shooting": "completed", "editing": "completed", "publishing": "completed"}},
        )
    if operation in {"outcome_post", "outcome_patch"}:
        upsert_creator_outcome_timeline(project_id, publication)
    if operation == "outcome_patch":
        snapshot, _timeline = append_creator_outcome_snapshot(project_id, metrics)
        snapshot_id = snapshot["snapshot_id"]

    filename = {
        "record_start": "creator_execution_record.json",
        "record_patch": "creator_execution_record.json",
        "outcome_put": "creator_outcome_snapshots.json",
        "outcome_post": "creator_outcome_snapshots.json",
        "outcome_patch": "creator_outcome_snapshots.json",
    }[operation]
    historical_path = output_dir / filename
    historical_before = historical_path.read_bytes() if historical_path.exists() else None
    target_module = execution_record_service if operation.startswith("record") else outcome_snapshot_service
    original_lock = target_module.iteration_write_lock
    switched = False

    @contextmanager
    def switching_lock():
        nonlocal switched
        if not switched:
            switched = True
            start_next_creator_iteration(
                project_id,
                close_current=True,
                close_reason="superseded",
            )
        with original_lock():
            yield

    monkeypatch.setattr(target_module, "iteration_write_lock", switching_lock)
    operations = {
        "record_start": lambda: start_creator_execution_record(project_id),
        "record_patch": lambda: update_creator_execution_record(
            project_id,
            {"feedback": {"notes": "must not cross iterations"}},
        ),
        "outcome_put": lambda: upsert_creator_outcome_timeline(project_id, publication),
        "outcome_post": lambda: append_creator_outcome_snapshot(project_id, metrics),
        "outcome_patch": lambda: update_creator_outcome_snapshot(project_id, snapshot_id, {"views": 200}),
    }

    with pytest.raises(AppError) as captured:
        operations[operation]()

    assert captured.value.code == ErrorCode.ITERATION_CONTEXT_CHANGED
    assert switched is True
    if historical_before is None:
        assert not historical_path.exists()
    else:
        assert historical_path.read_bytes() == historical_before
    current = resolve_current_iteration_context(project_id)
    assert current.storage_mode == "iteration_dir"
    assert not (current.base_dir / filename).exists()


def test_corrupt_index_blocks_every_current_artifact_write() -> None:
    sample_set, output_dir = _write_upstream()
    project_id = sample_set.set_id
    index_path = output_dir / ITERATION_INDEX_FILENAME
    index_path.write_text("{broken", encoding="utf-8")
    before = index_path.read_bytes()
    provider = FakeProvider([_execution_payload()])
    operations = [
        lambda: generate_creator_execution_pack(project_id, 0, provider=provider),
        lambda: start_creator_execution_record(project_id),
        lambda: update_creator_execution_record(project_id, {"status": "in_progress"}),
        lambda: upsert_creator_outcome_timeline(project_id, {"platform": "douyin"}),
        lambda: append_creator_outcome_snapshot(project_id, {"views": 0}),
        lambda: update_creator_outcome_snapshot(project_id, f"snapshot_{'a' * 32}", {"views": 0}),
    ]

    for operation in operations:
        with pytest.raises(AppError) as captured:
            operation()
        assert captured.value.code == ErrorCode.ITERATION_INDEX_INVALID
        assert index_path.read_bytes() == before


def test_index_atomic_write_failure_preserves_original_and_cleans_tmp(monkeypatch) -> None:
    active = _ref(1, current=True)
    original = write_creator_iteration_index(PROJECT_ID, _index([active], active["iteration_id"]))
    path = creator_iteration_index_path(PROJECT_ID)
    before = path.read_bytes()
    replacement = {**original, "updated_at": "2026-08-21T00:00:00+00:00"}

    def fail_replace(_source, _destination) -> None:
        raise OSError("synthetic replace failure")

    monkeypatch.setattr(iteration_storage_service.os, "replace", fail_replace)
    with pytest.raises(AppError) as captured:
        write_creator_iteration_index(PROJECT_ID, replacement)

    assert captured.value.code == ErrorCode.ITERATION_INDEX_INVALID
    assert path.read_bytes() == before
    assert list(path.parent.glob(f".{path.name}.*.tmp")) == []


def test_legacy_and_new_iteration_complete_flow_remain_independent() -> None:
    sample_set, output_dir = _write_upstream()
    project_id = sample_set.set_id
    publication = {
        "platform": "douyin",
        "platform_item_id": "7654321098765432100",
        "published_url": "https://www.douyin.com/video/7654321098765432100",
        "published_at": "2026-08-10T09:30:00+08:00",
    }
    metrics = {"views": 100, "likes": 10, "comments": 1, "shares": 0, "collects": None}

    generate_creator_execution_pack(project_id, 0, provider=FakeProvider([_execution_payload()]))
    start_creator_execution_record(project_id)
    update_creator_execution_record(
        project_id,
        {"production_status": {"shooting": "completed", "editing": "completed", "publishing": "completed"}},
    )
    upsert_creator_outcome_timeline(project_id, publication)
    append_creator_outcome_snapshot(project_id, metrics)
    legacy_paths = {
        filename: output_dir / filename
        for filename in (
            "creator_execution_pack.json",
            "creator_execution_record.json",
            "creator_outcome_snapshots.json",
        )
    }
    legacy_before = {name: path.read_bytes() for name, path in legacy_paths.items()}

    started = start_next_creator_iteration(project_id)
    new_id = started["current_iteration"]["iteration_id"]
    new_dir = output_dir / "iterations" / new_id
    assert not new_dir.exists()

    generate_creator_execution_pack(project_id, 0, provider=FakeProvider([_execution_payload()]))
    start_creator_execution_record(project_id)
    update_creator_execution_record(
        project_id,
        {"production_status": {"shooting": "completed", "editing": "completed", "publishing": "completed"}},
    )
    upsert_creator_outcome_timeline(project_id, publication)
    append_creator_outcome_snapshot(project_id, {**metrics, "views": 0})

    assert all((new_dir / filename).is_file() for filename in legacy_paths)
    assert {name: path.read_bytes() for name, path in legacy_paths.items()} == legacy_before
    history = list_creator_iterations(project_id)
    assert len(history["iterations"]) == 2
    assert get_creator_iteration_artifact(project_id, LEGACY_ITERATION_ID, "execution-record")["status"] == "completed"
    assert get_creator_iteration_artifact(project_id, new_id, "outcome")["snapshots"][-1]["metrics"]["views"] == 0


def test_historical_pack_validation_does_not_rebind_current_strategy() -> None:
    sample_set, output_dir = _write_upstream()
    project_id = sample_set.set_id
    generated = generate_creator_execution_pack(
        project_id,
        0,
        provider=FakeProvider([_execution_payload()]),
    )
    start_creator_execution_record(project_id)
    update_creator_execution_record(project_id, {"status": "completed"})
    start_next_creator_iteration(project_id)
    (output_dir / "creator_strategy_plan.json").write_text(
        json.dumps({"next_topics": []}),
        encoding="utf-8",
    )

    historical = get_creator_iteration_artifact(project_id, LEGACY_ITERATION_ID, "execution-pack")

    assert historical["generated_at"] == generated["generated_at"]
    assert historical["topic"]["title"] == generated["topic"]["title"]
