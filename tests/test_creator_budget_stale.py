import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.services import workbench_overview as overview


def _phase(now):
    return {
        "budget_started_at": (now - timedelta(seconds=2400)).isoformat(),
        "deadline_at": (now + timedelta(seconds=4800)).isoformat(),
        "total_budget_seconds": 7200,
        "remaining_seconds": 7200,
    }


@pytest.mark.parametrize("change", [
    {"total_budget_seconds": 14401}, {"total_budget_seconds": float("nan")},
    {"total_budget_seconds": float("inf")}, {"total_budget_seconds": -1},
    {"total_budget_seconds": True}, {"deadline_at": "bad"},
    {"deadline_at": "2020-01-01T00:00:00Z"}, {"remaining_seconds": 0},
    {"remaining_seconds": float("inf")}, {"budget_started_at": ""},
    {"total_budget_seconds": 100},
])
def test_invalid_budget_does_not_extend_stale(change):
    now = datetime.now(timezone.utc)
    phase = {**_phase(now), **change}
    assert not overview._creator_budget_active(
        "creator-clone-distill", "running", json.dumps({"distill_phase": phase}),
        now - timedelta(hours=1), now - timedelta(minutes=40), now=now,
    )


@pytest.mark.parametrize("kind,status", [
    ("analyze-case", "running"), ("profile-scan", "running"),
    ("creator-clone-distill", "pending"), ("creator-clone-distill", "failed"),
])
def test_budget_extension_only_applies_to_running_creator(kind, status):
    now = datetime.now(timezone.utc)
    assert not overview._creator_budget_active(
        kind, status, json.dumps({"distill_phase": _phase(now)}),
        now - timedelta(hours=1), now - timedelta(minutes=40), now=now,
    )


def test_long_creator_list_count_and_detail_agree_without_writes(tmp_path):
    path = tmp_path / "jobs.db"
    now = datetime.now(timezone.utc)
    created = (now - timedelta(hours=1)).replace(tzinfo=None).isoformat(sep=" ")
    updated = (now - timedelta(minutes=40)).replace(tzinfo=None).isoformat(sep=" ")
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE jobs (id TEXT, type TEXT, status TEXT, progress INTEGER, message TEXT, error_code TEXT, created_at TEXT, updated_at TEXT, result_json TEXT)")
        for identifier, phase in [
            ("job_active", _phase(now)),
            ("job_expired", {**_phase(now), "deadline_at": (now - timedelta(seconds=1)).isoformat()}),
            ("job_invalid", {**_phase(now), "total_budget_seconds": 14401}),
        ]:
            db.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                identifier, "creator-clone-batch-distill", "running", 45, "waiting", "", created, updated,
                json.dumps({"distill_phase": phase}),
            ))
    before = path.read_bytes()
    url = f"sqlite:///{path}"
    running, stale, _, running_count, stale_count = overview._collect_job_sections(url)
    assert running_count == 1
    assert stale_count == 2
    assert [row["task_id"] for row in running] == ["job_active"]
    assert {row["task_id"] for row in stale} == {"job_expired", "job_invalid"}
    for identifier, expected in [("job_active", "running"), ("job_expired", "stale"), ("job_invalid", "stale")]:
        detail = overview.build_workbench_job_detail(identifier, database_url=url)
        assert detail["status"] == expected
        if identifier == "job_active":
            assert detail["result_json"]["distill_phase"]["total_budget_seconds"] == 7200
            assert 4790 < detail["result_json"]["distill_phase"]["remaining_seconds"] <= 4800
        else:
            assert "distill_phase" not in detail["result_json"]
    assert path.read_bytes() == before


def test_future_start_or_deadline_beyond_budget_is_rejected():
    now = datetime.now(timezone.utc)
    for changes in [
        {"budget_started_at": (now + timedelta(seconds=30)).isoformat()},
        {"deadline_at": (now + timedelta(hours=5)).isoformat()},
    ]:
        assert not overview._creator_budget_active(
            "creator-clone-distill", "running", json.dumps({"distill_phase": {**_phase(now), **changes}}),
            now - timedelta(hours=1), now - timedelta(minutes=40), now=now,
        )
