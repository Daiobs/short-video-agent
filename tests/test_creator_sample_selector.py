from __future__ import annotations

import json
import math
import socket
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import Job
from app.services.creator_clone import CloneSample, CloneSampleSet, load_sample_set, save_sample_set
from app.services.creator_sample_selector import (
    ALGORITHM_VERSION,
    MAX_INPUT_COUNT,
    RepresentativeRole,
    RepresentativeSampleSelectorError,
    recommend_representative_samples,
)


client = TestClient(app)


def _sample(
    index: int,
    *,
    likes: int | None = None,
    comments: int | None = None,
    shares: int | None = None,
    collects: int | None = None,
    title: str | None = None,
    days_ago: int | None = None,
    media_type: str = "video",
) -> dict:
    created_at = ""
    if days_ago is not None:
        created_at = (datetime(2026, 8, 1, tzinfo=timezone.utc) - timedelta(days=days_ago)).isoformat()
    payload = {
        "sample_id": f"sample_{index:03d}",
        "title": title if title is not None else f"样本 {index}",
        "desc": f"样本 {index} 的公开描述",
        "media_type": media_type,
        "duration": 8 + index,
        "create_time": created_at,
    }
    for key, value in {
        "like_count": likes,
        "comment_count": comments,
        "share_count": shares,
        "collect_count": collects,
    }.items():
        if value is not None:
            payload[key] = value
    return payload


def _role_ids(selection, role: RepresentativeRole) -> list[str]:
    return [item.sample_id for item in selection.recommendations if role.value in item.roles]


def _representative_pool(count: int = 24) -> list[dict]:
    return [
        _sample(
            index,
            likes=1000 + index * 170,
            comments=20 + index * 5,
            shares=8 + index * 3,
            collects=10 + index * 4,
            title=(f"甜美 COS 变装 第 {index} 集" if index < count - 3 else f"手机摄影教学 第 {index} 集"),
            days_ago=count - index,
        )
        for index in range(count)
    ]


def test_selector_is_deterministic_unique_and_bounded() -> None:
    samples = _representative_pool()
    outputs = [recommend_representative_samples(samples, 6).to_dict() for _ in range(20)]

    assert all(output == outputs[0] for output in outputs)
    ids = outputs[0]["recommended_sample_ids"]
    assert len(ids) == 6
    assert len(ids) == len(set(ids))
    assert outputs[0]["algorithm_version"] == ALGORITHM_VERSION
    assert all(outputs[0]["coverage"].values())
    assert all(0 <= item["score"] <= 100 for item in outputs[0]["recommendations"])


def test_selector_returns_all_when_pool_is_smaller_than_target() -> None:
    selection = recommend_representative_samples(_representative_pool(4), 6)

    assert selection.available_count == 4
    assert selection.recommended_count == 4
    assert set(selection.recommended_sample_ids) == {f"sample_{index:03d}" for index in range(4)}


def test_selector_rejects_invalid_bounds() -> None:
    with pytest.raises(RepresentativeSampleSelectorError):
        recommend_representative_samples(_representative_pool(3), 2)
    with pytest.raises(RepresentativeSampleSelectorError):
        recommend_representative_samples(_representative_pool(11), 11)
    with pytest.raises(RepresentativeSampleSelectorError):
        recommend_representative_samples(
            [_sample(index, likes=index) for index in range(MAX_INPUT_COUNT + 1)],
            6,
        )


def test_selector_handles_zero_and_missing_metrics_without_nan() -> None:
    zero_samples = [
        _sample(index, likes=0, comments=0, shares=0, collects=0, days_ago=None)
        for index in range(8)
    ]
    missing_samples = [
        {
            "sample_id": f"sample_missing_{index}",
            "title": "" if index % 2 else f"本地样本 {index}",
            "media_type": "unknown",
        }
        for index in range(8)
    ]

    for samples in (zero_samples, missing_samples):
        first = recommend_representative_samples(samples, 6).to_dict()
        second = recommend_representative_samples(samples, 6).to_dict()
        assert first == second
        assert first["recommended_count"] == 6
        for item in first["recommendations"]:
            assert math.isfinite(item["score"])
            assert all(value is None or math.isfinite(value) for value in item["metrics"].values())


@pytest.mark.parametrize(
    "missing_fields",
    [
        {"comment_count"},
        {"share_count"},
        {"collect_count"},
        {"create_time"},
        {"title", "desc"},
    ],
)
def test_selector_degrades_when_individual_fields_are_missing(missing_fields: set[str]) -> None:
    samples = _representative_pool(12)
    for sample in samples:
        for field in missing_fields:
            sample.pop(field, None)

    selection = recommend_representative_samples(samples, 6)

    assert selection.recommended_count == 6
    assert len(set(selection.recommended_sample_ids)) == 6
    assert selection.to_dict() == recommend_representative_samples(samples, 6).to_dict()


def test_single_breakout_does_not_collapse_other_roles_to_like_order() -> None:
    samples = _representative_pool(21)
    samples[0].update(like_count=1_000_000, comment_count=800, share_count=900, collect_count=1000)
    samples[7].update(like_count=3500, comment_count=9000)
    samples[8].update(like_count=3300, share_count=16_000, collect_count=22_000)

    selection = recommend_representative_samples(samples, 6)

    assert _role_ids(selection, RepresentativeRole.BREAKOUT_HIT) == ["sample_000"]
    assert "sample_007" in _role_ids(selection, RepresentativeRole.COMMENT_MAGNET)
    assert "sample_008" in _role_ids(selection, RepresentativeRole.SAVE_SHARE_VALUE)
    assert len(set(selection.recommended_sample_ids)) == 6


def test_recent_winner_requires_performance_not_only_latest_timestamp() -> None:
    samples = _representative_pool(12)
    samples[-1].update(like_count=1, comment_count=0, share_count=0, collect_count=0)
    samples[-2].update(like_count=120_000, comment_count=4200, share_count=3400, collect_count=5100)

    selection = recommend_representative_samples(samples, 6)

    recent_ids = _role_ids(selection, RepresentativeRole.RECENT_WINNER)
    assert recent_ids
    assert "sample_011" not in recent_ids
    winner_index = int(recent_ids[0].rsplit("_", 1)[-1])
    assert samples[winner_index]["like_count"] > samples[-1]["like_count"]


def test_baseline_is_not_the_top_performer_when_pool_is_sufficient() -> None:
    samples = _representative_pool(15)
    samples[-1].update(like_count=500_000, comment_count=80_000, share_count=70_000, collect_count=90_000)

    selection = recommend_representative_samples(samples, 6)

    baseline_ids = _role_ids(selection, RepresentativeRole.BASELINE_TYPICAL)
    assert baseline_ids
    assert "sample_014" not in baseline_ids


def test_diversity_anchor_can_select_distinct_local_content() -> None:
    samples = [
        _sample(
            index,
            likes=2000 + index * 10,
            comments=100 + index,
            shares=30 + index,
            collects=40 + index,
            title=f"甜美 COS 变装 粉色裙子 第 {index} 集",
            days_ago=20 - index,
        )
        for index in range(8)
    ]
    samples.extend(
        [
            _sample(8, likes=1800, comments=90, shares=25, collects=35, title="手机夜景摄影参数教学", days_ago=3),
            _sample(9, likes=1700, comments=80, shares=24, collects=34, title="厨房低脂晚餐做法教程", days_ago=2),
        ]
    )

    selection = recommend_representative_samples(samples, 6)

    diversity_ids = _role_ids(selection, RepresentativeRole.DIVERSITY_ANCHOR)
    assert diversity_ids
    assert diversity_ids[0] in {"sample_008", "sample_009"}


def test_stable_tie_break_prefers_newer_then_sample_id() -> None:
    samples = [
        _sample(index, likes=100, comments=10, shares=5, collects=5, title="相同内容", days_ago=2)
        for index in range(8)
    ]
    samples[6]["create_time"] = datetime(2026, 8, 1, tzinfo=timezone.utc).isoformat()
    samples[7]["create_time"] = samples[6]["create_time"]

    first = recommend_representative_samples(samples, 6)
    second = recommend_representative_samples(list(reversed(samples)), 6)

    assert first.recommended_sample_ids == second.recommended_sample_ids
    assert first.recommended_sample_ids.index("sample_006") < first.recommended_sample_ids.index("sample_007")


def test_recommendation_api_is_local_read_only_and_persists_safe_audit(monkeypatch) -> None:
    set_id = "clone_representative_api"
    sample_set = CloneSampleSet(
        set_id=set_id,
        title="代表样本接口",
        selected_sample_ids=["sample_001"],
        samples=[CloneSample(**sample) for sample in _representative_pool(12)],
    )
    save_sample_set(sample_set)

    calls = {"llm": 0, "download": 0, "quality": 0, "network": 0}

    def blocked(kind):
        def fail(*args, **kwargs):
            calls[kind] += 1
            raise AssertionError(f"unexpected {kind} side effect")

        return fail

    monkeypatch.setattr("app.services.creator_clone.get_llm_provider", blocked("llm"))
    monkeypatch.setattr("app.services.downloader.download_candidate", blocked("download"))
    monkeypatch.setattr("app.services.quality_resolver.resolve_quality_candidates", blocked("quality"))
    monkeypatch.setattr(socket, "create_connection", blocked("network"))

    db = SessionLocal()
    try:
        jobs_before = db.query(Job).count()
    finally:
        db.close()

    response = client.post(
        "/api/creator-clone/sample-recommendations",
        json={"sample_set_id": set_id, "target_count": 6},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["ok"] is True
    assert payload["recommended_count"] == 6
    assert payload["artifact_url"].endswith("/sample_recommendations.json")
    assert load_sample_set(set_id).selected_sample_ids == ["sample_001"]
    db = SessionLocal()
    try:
        assert db.query(Job).count() == jobs_before
    finally:
        db.close()
    assert calls == {"llm": 0, "download": 0, "quality": 0, "network": 0}

    artifact_path = settings.creator_clones_dir / set_id / "sample_recommendations.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert set(artifact) == {
        "algorithm_version",
        "generated_at",
        "input_count",
        "target_count",
        "recommendations",
        "coverage",
        "warnings",
    }
    serialized = json.dumps(artifact, ensure_ascii=False).lower()
    for secret in ("cookie", "authorization", "api_key", "bearer ", "/users/", "http://", "https://"):
        assert secret not in serialized

    artifact_response = client.get(payload["artifact_url"])
    assert artifact_response.status_code == 200
    assert artifact_response.headers["content-type"].startswith("application/json")
    assert artifact_response.json() == artifact


def test_inline_recommendation_does_not_persist_or_return_input_secrets() -> None:
    samples = _representative_pool(8)
    samples[0].update(
        notes="Cookie=sessionid-secret Authorization: Bearer token-secret api_key=sk-secret",
        source_url="https://v.example.test/signed?token=secret",
    )

    response = client.post(
        "/api/creator-clone/sample-recommendations",
        json={"samples": samples, "target_count": 6},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "artifact_url" not in payload
    serialized = response.text.lower()
    for secret in ("sessionid-secret", "token-secret", "sk-secret", "v.example.test"):
        assert secret not in serialized


def test_recommendation_api_rejects_more_than_200_inline_samples() -> None:
    response = client.post(
        "/api/creator-clone/sample-recommendations",
        json={
            "samples": [_sample(index, likes=index) for index in range(MAX_INPUT_COUNT + 1)],
            "target_count": 6,
        },
    )

    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    assert "200" in response.json()["message"]


def test_recommendation_api_rejects_target_outside_three_to_ten() -> None:
    response = client.post(
        "/api/creator-clone/sample-recommendations",
        json={"samples": _representative_pool(8), "target_count": 2},
    )

    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    assert "3–10" in response.json()["message"]


def test_selector_200_item_local_smoke_is_bounded() -> None:
    started = time.perf_counter()
    selection = recommend_representative_samples(_representative_pool(MAX_INPUT_COUNT), 10)
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert selection.recommended_count == 10
    assert elapsed_ms < 1000
