from __future__ import annotations

import copy
import json
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.errors import AppError, ErrorCode
from app.main import app
from app.models import Job
from app.services.creator_intelligence import outcome_snapshot as outcome_module
from app.services.creator_intelligence.outcome_snapshot import (
    OUTCOME_MAX_SNAPSHOTS,
    OUTCOME_TIMELINE_FILENAME,
    append_creator_outcome_snapshot,
    creator_outcome_timeline_path,
    load_creator_outcome_timeline,
    update_creator_outcome_snapshot,
    upsert_creator_outcome_timeline,
    validate_creator_outcome_snapshot,
    validate_creator_outcome_timeline,
)


client = TestClient(app)
PROJECT_ID = "clone_outcome_test"


def _record(*, publishing: str = "completed") -> dict[str, Any]:
    return {
        "version": "1.0",
        "project_id": PROJECT_ID,
        "execution_pack_generated_at": "2026-08-10T01:00:00+00:00",
        "execution_pack_topic_index": 3,
        "selected_topic": "同一妆造三种状态",
        "status": "in_progress",
        "production_status": {
            "shooting": "completed",
            "editing": "completed",
            "publishing": publishing,
        },
        "feedback": {
            "was_used": True,
            "difficulty": "normal",
            "quality_rating": 4,
            "result_rating": None,
            "notes": "",
        },
        "created_at": "2026-08-10T01:05:00+00:00",
        "updated_at": "2026-08-10T01:08:00+00:00",
    }


def _pack(
    *,
    generated_at: str = "2026-08-10T01:00:00+00:00",
    topic_index: int = 3,
    title: str = "同一妆造三种状态",
    expected_metric: str = "停留与评论",
) -> dict[str, Any]:
    return {
        "version": "1.0",
        "project_id": PROJECT_ID,
        "generated_at": generated_at,
        "topic_index": topic_index,
        "topic": {"title": title, "expected_metric": expected_metric},
    }


def _publication(**overrides: Any) -> dict[str, Any]:
    return {
        "platform": "douyin",
        "platform_item_id": "7654321098765432100",
        "published_url": "https://www.douyin.com/video/7654321098765432100",
        "published_at": "2026-08-10T09:30:00+08:00",
        **overrides,
    }


def _snapshot(
    suffix: str,
    *,
    captured_at: str,
    metrics: dict[str, int | None],
) -> dict[str, Any]:
    return {
        "snapshot_id": f"snapshot_{suffix * 32}",
        "captured_at": captured_at,
        "source": "manual",
        "metrics": metrics,
        "derived": {"client_value": "ignored"},
    }


def _valid_timeline(*, snapshots: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "version": "1.0",
        "project_id": PROJECT_ID,
        "execution_record_created_at": "2026-08-10T01:05:00+00:00",
        "execution_pack_generated_at": "2026-08-10T01:00:00+00:00",
        "execution_pack_topic_index": 3,
        "selected_topic": "同一妆造三种状态",
        "expected_metric": "停留与评论",
        "publication": _publication(),
        "snapshots": snapshots or [],
        "warnings": [],
        "created_at": "2026-08-10T02:00:00+00:00",
        "updated_at": "2026-08-10T02:00:00+00:00",
    }


def _install_sources(
    monkeypatch,
    *,
    record: dict[str, Any] | None = None,
    pack: dict[str, Any] | None = None,
) -> None:
    record_payload = copy.deepcopy(record or _record())
    pack_payload = copy.deepcopy(pack or _pack())
    monkeypatch.setattr(
        outcome_module,
        "load_creator_execution_record",
        lambda _project_id: copy.deepcopy(record_payload),
    )
    monkeypatch.setattr(
        outcome_module,
        "load_creator_execution_pack",
        lambda _project_id: copy.deepcopy(pack_payload),
    )


def _create(monkeypatch, **publication_overrides: Any) -> dict[str, Any]:
    _install_sources(monkeypatch)
    return upsert_creator_outcome_timeline(PROJECT_ID, _publication(**publication_overrides))


def test_timeline_and_snapshot_schemas_accept_valid_payloads() -> None:
    snapshot = _snapshot(
        "a",
        captured_at="2026-08-10T02:10:00+00:00",
        metrics={"views": 100, "likes": 10, "comments": 1, "shares": 0, "collects": None},
    )

    validated_snapshot = validate_creator_outcome_snapshot(snapshot)
    timeline = validate_creator_outcome_timeline(_valid_timeline(snapshots=[snapshot]))

    assert validated_snapshot["source"] == "manual"
    assert validated_snapshot["derived"]["share_rate"] == 0
    assert validated_snapshot["derived"]["collect_rate"] is None
    assert timeline["version"] == "1.0"
    assert timeline["summary"]["snapshot_count"] == 1
    assert timeline["summary"]["latest_snapshot_id"] == snapshot["snapshot_id"]


@pytest.mark.parametrize("field", ["views", "likes", "comments", "shares", "collects"])
@pytest.mark.parametrize("value", [-1, 1.5, "1", True])
def test_schema_rejects_invalid_metric_types_and_values(field: str, value: Any) -> None:
    metrics: dict[str, Any] = {name: None for name in outcome_module.OUTCOME_METRIC_FIELDS}
    metrics[field] = value
    snapshot = _snapshot("b", captured_at="2026-08-10T02:10:00+00:00", metrics=metrics)

    with pytest.raises(ValueError):
        validate_creator_outcome_snapshot(snapshot)


@pytest.mark.parametrize(
    "published_url",
    [
        "http://www.douyin.com/video/1",
        "javascript:alert(1)",
        "data:text/plain,hello",
        "file:///tmp/video.mp4",
        "https://user:pass@example.com/video/1",
        "https://localhost/video/1",
        "https://127.0.0.1/video/1",
        "https://v26-default.365yg.com/video/1?token=signed",
        "https://example.com/video/1?signature=secret",
    ],
)
def test_publication_url_rejects_non_public_or_sensitive_urls(published_url: str) -> None:
    payload = _valid_timeline()
    payload["publication"]["published_url"] = published_url

    with pytest.raises(ValueError):
        validate_creator_outcome_timeline(payload)


def test_publication_rejects_naive_timestamp() -> None:
    payload = _valid_timeline()
    payload["publication"]["published_at"] = "2026-08-10T09:30:00"

    with pytest.raises(ValueError):
        validate_creator_outcome_timeline(payload)


def test_missing_and_explicit_zero_remain_distinct_in_api_and_file(monkeypatch) -> None:
    _create(monkeypatch)

    missing = client.post(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/outcome/snapshots",
        json={"views": 100, "likes": 10, "comments": 1, "shares": None, "collects": 2},
    )
    zero = client.post(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/outcome/snapshots",
        json={"views": 120, "likes": 12, "comments": 1, "shares": 0, "collects": 2},
    )
    loaded = client.get(f"/api/creator-intelligence/projects/{PROJECT_ID}/outcome")
    persisted = json.loads(creator_outcome_timeline_path(PROJECT_ID).read_text(encoding="utf-8"))

    assert missing.status_code == zero.status_code == loaded.status_code == 200
    assert missing.json()["snapshot"]["metrics"]["shares"] is None
    assert zero.json()["snapshot"]["metrics"]["shares"] == 0
    assert loaded.json()["outcome"]["snapshots"][0]["metrics"]["shares"] is None
    assert loaded.json()["outcome"]["snapshots"][1]["metrics"]["shares"] == 0
    assert persisted["snapshots"][0]["metrics"]["shares"] is None
    assert persisted["snapshots"][1]["metrics"]["shares"] == 0


def test_derived_rates_require_known_values_and_positive_views() -> None:
    complete = validate_creator_outcome_snapshot(
        _snapshot(
            "c",
            captured_at="2026-08-10T02:10:00+00:00",
            metrics={"views": 1000, "likes": 100, "comments": 10, "shares": 5, "collects": 20},
        )
    )["derived"]
    missing_views = validate_creator_outcome_snapshot(
        _snapshot(
            "d",
            captured_at="2026-08-10T02:11:00+00:00",
            metrics={"views": None, "likes": 100, "comments": 10, "shares": 5, "collects": 20},
        )
    )["derived"]
    zero_views = validate_creator_outcome_snapshot(
        _snapshot(
            "e",
            captured_at="2026-08-10T02:12:00+00:00",
            metrics={"views": 0, "likes": 0, "comments": 0, "shares": 0, "collects": 0},
        )
    )["derived"]
    missing_share = validate_creator_outcome_snapshot(
        _snapshot(
            "f",
            captured_at="2026-08-10T02:13:00+00:00",
            metrics={"views": 1000, "likes": 100, "comments": 10, "shares": None, "collects": 20},
        )
    )["derived"]

    assert complete == {
        "known_interactions": 135,
        "known_interaction_metric_count": 4,
        "engagement_rate": 0.135,
        "like_rate": 0.1,
        "comment_rate": 0.01,
        "share_rate": 0.005,
        "collect_rate": 0.02,
        "delta_from_previous": {name: None for name in outcome_module.OUTCOME_METRIC_FIELDS},
    }
    for derived in (missing_views, zero_views):
        assert derived["engagement_rate"] is None
        assert derived["like_rate"] is None
        assert derived["comment_rate"] is None
        assert derived["share_rate"] is None
        assert derived["collect_rate"] is None
    assert missing_share["share_rate"] is None
    assert missing_share["engagement_rate"] is None
    assert missing_share["known_interactions"] == 130
    assert missing_share["known_interaction_metric_count"] == 3


def test_delta_preserves_missing_values_and_allows_negative_numbers() -> None:
    timeline = validate_creator_outcome_timeline(
        _valid_timeline(
            snapshots=[
                _snapshot(
                    "1",
                    captured_at="2026-08-10T02:10:00+00:00",
                    metrics={"views": 1000, "likes": 100, "comments": 10, "shares": None, "collects": 20},
                ),
                _snapshot(
                    "2",
                    captured_at="2026-08-10T03:10:00+00:00",
                    metrics={"views": 1500, "likes": 140, "comments": 15, "shares": 5, "collects": 25},
                ),
                _snapshot(
                    "3",
                    captured_at="2026-08-10T04:10:00+00:00",
                    metrics={"views": 1400, "likes": 130, "comments": 14, "shares": 3, "collects": 24},
                ),
            ]
        )
    )

    assert timeline["snapshots"][1]["derived"]["delta_from_previous"] == {
        "views": 500,
        "likes": 40,
        "comments": 5,
        "shares": None,
        "collects": 5,
    }
    assert timeline["snapshots"][2]["derived"]["delta_from_previous"] == {
        "views": -100,
        "likes": -10,
        "comments": -1,
        "shares": -2,
        "collects": -1,
    }


def test_put_requires_published_execution_record(monkeypatch) -> None:
    def missing_record(_project_id: str):
        raise AppError(ErrorCode.EXECUTION_RECORD_NOT_READY)

    monkeypatch.setattr(outcome_module, "load_creator_execution_record", missing_record)
    missing = client.put(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/outcome",
        json=_publication(),
    )

    assert missing.status_code == 400
    assert missing.json()["error_code"] == ErrorCode.EXECUTION_RECORD_NOT_READY
    for status in ("pending", "skipped"):
        _install_sources(monkeypatch, record=_record(publishing=status))
        response = client.put(
            f"/api/creator-intelligence/projects/{PROJECT_ID}/outcome",
            json=_publication(),
        )
        assert response.status_code == 400
        assert response.json()["error_code"] == ErrorCode.EXECUTION_NOT_PUBLISHED

    _install_sources(monkeypatch, record=_record(publishing="completed"))
    allowed = client.put(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/outcome",
        json=_publication(),
    )
    assert allowed.status_code == 200


def test_outcome_binds_record_and_only_copies_matching_expected_metric(monkeypatch) -> None:
    record = _record()
    _install_sources(monkeypatch, record=record, pack=_pack(expected_metric="互动与关注"))
    matching = upsert_creator_outcome_timeline(PROJECT_ID, _publication())

    assert matching["execution_record_created_at"] == record["created_at"]
    assert matching["execution_pack_generated_at"] == record["execution_pack_generated_at"]
    assert matching["execution_pack_topic_index"] == record["execution_pack_topic_index"]
    assert matching["selected_topic"] == record["selected_topic"]
    assert matching["expected_metric"] == "互动与关注"
    assert matching["warnings"] == []


def test_pack_regeneration_mismatch_does_not_rebind_or_copy_metric(monkeypatch) -> None:
    record = _record()
    _install_sources(
        monkeypatch,
        record=record,
        pack=_pack(
            generated_at="2030-01-01T00:00:00+00:00",
            topic_index=8,
            title="新选题",
            expected_metric="新 Pack 指标",
        ),
    )
    outcome = upsert_creator_outcome_timeline(PROJECT_ID, _publication())

    assert outcome["execution_pack_generated_at"] == record["execution_pack_generated_at"]
    assert outcome["execution_pack_topic_index"] == record["execution_pack_topic_index"]
    assert outcome["selected_topic"] == record["selected_topic"]
    assert outcome["expected_metric"] == ""
    assert "execution_pack_changed_since_record" in outcome["warnings"]


def test_existing_outcome_binding_survives_record_feedback_and_pack_changes(monkeypatch) -> None:
    original_record = _record()
    _install_sources(monkeypatch, record=original_record, pack=_pack())
    created = upsert_creator_outcome_timeline(PROJECT_ID, _publication())

    changed_record = {**original_record, "created_at": "2031-01-01T00:00:00+00:00"}
    _install_sources(
        monkeypatch,
        record=changed_record,
        pack=_pack(generated_at="2031-01-01T00:00:00+00:00", topic_index=9, title="新 Pack"),
    )
    loaded = load_creator_outcome_timeline(PROJECT_ID)

    for field in (
        "execution_record_created_at",
        "execution_pack_generated_at",
        "execution_pack_topic_index",
        "selected_topic",
    ):
        assert loaded[field] == created[field]


def test_publication_put_is_idempotent_and_preserves_snapshots_and_created_at(monkeypatch) -> None:
    _create(monkeypatch)
    append_creator_outcome_snapshot(
        PROJECT_ID,
        {"views": 100, "likes": 10, "comments": 1, "shares": None, "collects": 2},
    )
    before = load_creator_outcome_timeline(PROJECT_ID)

    updated = upsert_creator_outcome_timeline(
        PROJECT_ID,
        _publication(platform_item_id="updated-id", published_at=None),
    )

    assert updated["created_at"] == before["created_at"]
    assert updated["snapshots"] == before["snapshots"]
    assert updated["publication"]["platform_item_id"] == "updated-id"
    assert updated["publication"]["published_at"] is None
    assert updated["project_id"] == before["project_id"]


def test_snapshot_server_fields_ignore_client_values(monkeypatch) -> None:
    _create(monkeypatch)

    response = client.post(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/outcome/snapshots",
        json={
            "views": 0,
            "likes": None,
            "comments": None,
            "shares": None,
            "collects": None,
            "snapshot_id": "snapshot_ffffffffffffffffffffffffffffffff",
            "captured_at": "2030-01-01T00:00:00+00:00",
            "source": "douyin_provider",
            "derived": {"like_rate": 999},
        },
    )

    assert response.status_code == 200
    snapshot = response.json()["snapshot"]
    assert snapshot["snapshot_id"] != "snapshot_ffffffffffffffffffffffffffffffff"
    assert snapshot["source"] == "manual"
    assert snapshot["captured_at"] != "2030-01-01T00:00:00+00:00"
    assert snapshot["derived"]["like_rate"] is None
    assert datetime.fromisoformat(snapshot["captured_at"]).tzinfo is not None


def test_patch_snapshot_preserves_identity_and_recomputes_following_delta(monkeypatch) -> None:
    _create(monkeypatch)
    first, _outcome = append_creator_outcome_snapshot(
        PROJECT_ID,
        {"views": 100, "likes": 10, "comments": 2, "shares": 1, "collects": 3},
    )
    second, _outcome = append_creator_outcome_snapshot(
        PROJECT_ID,
        {"views": 150, "likes": 20, "comments": 3, "shares": 2, "collects": 5},
    )

    response = client.patch(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/outcome/snapshots/{first['snapshot_id']}",
        json={
            "likes": 15,
            "snapshot_id": "snapshot_ffffffffffffffffffffffffffffffff",
            "captured_at": "2030-01-01T00:00:00+00:00",
        },
    )

    assert response.status_code == 200
    corrected = response.json()["snapshot"]
    outcome = response.json()["outcome"]
    assert corrected["snapshot_id"] == first["snapshot_id"]
    assert corrected["captured_at"] == first["captured_at"]
    assert corrected["metrics"]["likes"] == 15
    following = next(item for item in outcome["snapshots"] if item["snapshot_id"] == second["snapshot_id"])
    assert following["derived"]["delta_from_previous"]["likes"] == 5


def test_snapshot_limit_rejects_without_changing_file(monkeypatch) -> None:
    _create(monkeypatch)
    timeline = load_creator_outcome_timeline(PROJECT_ID)
    timeline["snapshots"] = [
        _snapshot(
            f"{index:032x}"[-1],
            captured_at=f"2026-08-{10 + index // 24:02d}T{index % 24:02d}:00:00+00:00",
            metrics={"views": index, "likes": index, "comments": 0, "shares": None, "collects": 0},
        )
        for index in range(OUTCOME_MAX_SNAPSHOTS)
    ]
    for index, item in enumerate(timeline["snapshots"]):
        item["snapshot_id"] = f"snapshot_{index:032x}"
    validated = validate_creator_outcome_timeline(timeline, expected_project_id=PROJECT_ID)
    path = creator_outcome_timeline_path(PROJECT_ID)
    path.write_text(json.dumps(validated, ensure_ascii=False, indent=2), encoding="utf-8")
    before = path.read_bytes()

    response = client.post(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/outcome/snapshots",
        json={"views": 999},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == ErrorCode.OUTCOME_SNAPSHOT_LIMIT_REACHED
    assert path.read_bytes() == before


def test_persistence_is_atomic_and_upstream_artifacts_remain_unchanged(monkeypatch) -> None:
    output_dir = settings.creator_clones_dir / PROJECT_ID
    output_dir.mkdir(parents=True, exist_ok=True)
    upstream_names = (
        "creator_execution_pack.json",
        "creator_execution_record.json",
        "creator_strategy_plan.json",
        "creator_clone_result.json",
        "samples.json",
    )
    for name in upstream_names:
        (output_dir / name).write_bytes(f"unchanged:{name}".encode())
    before = {name: (output_dir / name).read_bytes() for name in upstream_names}
    _install_sources(monkeypatch)

    upsert_creator_outcome_timeline(PROJECT_ID, _publication())
    snapshot, _outcome = append_creator_outcome_snapshot(PROJECT_ID, {"views": 100})
    update_creator_outcome_snapshot(PROJECT_ID, snapshot["snapshot_id"], {"likes": 5})

    assert (output_dir / OUTCOME_TIMELINE_FILENAME).is_file()
    assert {name: (output_dir / name).read_bytes() for name in upstream_names} == before
    assert not list(output_dir.glob(f".{OUTCOME_TIMELINE_FILENAME}.*.tmp"))


def test_outcome_api_redacts_secrets_but_preserves_public_https_url(monkeypatch) -> None:
    record = _record()
    record["selected_topic"] = "Cookie=session-secret /Users/test/private/video.mp4"
    pack = _pack(expected_metric="Authorization: Bearer top-secret sk-1234567890abcdef")
    _install_sources(monkeypatch, record=record, pack=pack)
    public_url = "https://www.douyin.com/video/7654321098765432100?from=profile"

    response = client.put(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/outcome",
        json=_publication(
            platform_item_id="API_KEY=hidden",
            published_url=public_url,
        ),
    )

    assert response.status_code == 200
    api_text = json.dumps(response.json(), ensure_ascii=False).lower()
    file_text = creator_outcome_timeline_path(PROJECT_ID).read_text(encoding="utf-8").lower()
    for text in (api_text, file_text):
        assert "session-secret" not in text
        assert "/users/test" not in text
        assert "bearer top-secret" not in text
        assert "sk-1234567890abcdef" not in text
        assert "api_key=hidden" not in text
        assert public_url.lower() in text


def test_invalid_publication_and_metric_payloads_return_422(monkeypatch) -> None:
    _install_sources(monkeypatch)
    invalid_url = client.put(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/outcome",
        json=_publication(published_url="http://example.com/video/1"),
    )
    float_metric = client.post(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/outcome/snapshots",
        json={"views": 1.5},
    )
    string_metric = client.post(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/outcome/snapshots",
        json={"views": "1"},
    )

    assert invalid_url.status_code == 422
    assert float_metric.status_code == 422
    assert string_metric.status_code == 422


def test_outcome_apis_do_not_create_jobs_or_call_upstream_services(monkeypatch) -> None:
    _install_sources(monkeypatch)
    with SessionLocal() as session:
        jobs_before = session.query(Job).count()
    forbidden_calls: list[str] = []

    def forbidden(*_args, **_kwargs):
        forbidden_calls.append("called")
        raise AssertionError("Outcome must not invoke upstream work")

    monkeypatch.setattr("app.services.profile_scan.scan_profile", forbidden)
    monkeypatch.setattr("app.services.downloader.download_candidate", forbidden)
    monkeypatch.setattr("app.services.asr.run_case_asr", forbidden)
    monkeypatch.setattr("app.services.ocr.run_case_ocr", forbidden)
    monkeypatch.setattr("app.services.creator_clone.distill_creator_clone", forbidden)

    put_response = client.put(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/outcome",
        json=_publication(),
    )
    post_response = client.post(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/outcome/snapshots",
        json={"views": 100, "likes": 10},
    )
    snapshot_id = post_response.json()["snapshot"]["snapshot_id"]
    patch_response = client.patch(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/outcome/snapshots/{snapshot_id}",
        json={"likes": 11},
    )
    get_response = client.get(f"/api/creator-intelligence/projects/{PROJECT_ID}/outcome")

    assert put_response.status_code == post_response.status_code == patch_response.status_code == get_response.status_code == 200
    assert forbidden_calls == []
    with SessionLocal() as session:
        assert session.query(Job).count() == jobs_before


def test_get_missing_outcome_and_invalid_snapshot_use_clear_errors() -> None:
    missing = client.get(f"/api/creator-intelligence/projects/{PROJECT_ID}/outcome")
    invalid_snapshot = client.patch(
        f"/api/creator-intelligence/projects/{PROJECT_ID}/outcome/snapshots/not-safe",
        json={"likes": 1},
    )

    assert missing.status_code == 400
    assert missing.json()["error_code"] == ErrorCode.OUTCOME_NOT_READY
    assert invalid_snapshot.status_code == 400
    assert invalid_snapshot.json()["error_code"] == ErrorCode.OUTCOME_SNAPSHOT_NOT_FOUND


def test_project_id_alias_cannot_open_another_outcome(monkeypatch) -> None:
    _create(monkeypatch)

    response = client.get(f"/api/creator-intelligence/projects/{PROJECT_ID}../outcome")

    assert response.status_code == 400
    assert response.json()["error_code"] == ErrorCode.OUTCOME_NOT_READY
