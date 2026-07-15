from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import CaseArtifact, LocalVideoItem
from app.services.library_assets import build_library_assets


client = TestClient(app)
NODE_CANDIDATES = [
    shutil.which("node"),
    Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node",
]
NODE_BINARY = next(
    (
        Path(value)
        for value in NODE_CANDIDATES
        if value and Path(value).is_file()
    ),
    None,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _add_case(
    index: int,
    *,
    title: str | None = None,
    author: str = "案例作者",
    created_at: datetime | None = None,
    complete: bool = True,
) -> str:
    case_id = f"case_{index:032d}"
    local_video_id = f"local_{index:032d}"
    created = created_at or datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc) + timedelta(minutes=index)
    case_dir = settings.cases_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    if complete:
        (case_dir / "video.mp4").write_bytes(b"video")
        _write_json(case_dir / "metadata.json", {"title": title or f"Case {index}"})
        _write_json(case_dir / "ffprobe.json", {"duration": 3})
        _write_json(case_dir / "analysis_input.json", {"case_id": case_id})
        (case_dir / "prompt.md").write_text("prompt", encoding="utf-8")
    with SessionLocal() as session:
        session.add(
            LocalVideoItem(
                local_video_id=local_video_id,
                title=title or f"Case {index}",
                file_path=str(settings.uploads_dir / f"{local_video_id}.mp4"),
                author=author,
                created_at=created,
            )
        )
        session.add(
            CaseArtifact(
                case_id=case_id,
                local_video_id=local_video_id,
                status="success",
                created_at=created,
            )
        )
        session.commit()
    return case_id


def _add_creator(
    index: int,
    *,
    title: str | None = None,
    creator_name: str | None = None,
    selected_count: int = 3,
    sample_count: int = 10,
    stale_strategy: bool = False,
    report: bool = True,
) -> str:
    set_id = f"clone_{index:032d}"
    clone_dir = settings.creator_clones_dir / set_id
    clone_dir.mkdir(parents=True, exist_ok=True)
    created_at = datetime(2026, 7, 2, 8, 0, tzinfo=timezone.utc) + timedelta(minutes=index)
    _write_json(
        clone_dir / "samples.json",
        {
            "set_id": set_id,
            "title": title or f"Creator {index}",
            "creator_name": creator_name or f"作者 {index}",
            "source_platform": "douyin",
            "sample_count": sample_count,
            "selected_count": selected_count,
            "samples": [{} for _ in range(min(sample_count, 3))],
            "selected_sample_ids": [f"sample_{value}" for value in range(selected_count)],
            "created_at": created_at.isoformat(),
        },
    )
    if report:
        _write_json(
            clone_dir / "creator_clone_result.json",
            {
                "report_quality": {"quality_score": 88, "confidence": "high"},
                "sample_overview": {"confidence": "high"},
            },
        )
        (clone_dir / "creator_clone.html").write_text("<h1>report</h1>", encoding="utf-8")
        (clone_dir / "creator_clone.md").write_text("# report", encoding="utf-8")
    _write_json(
        clone_dir / "creator_strategy_plan.json",
        {
            "source": {"report_quality_score": 88},
            "next_topics": [],
            "low_confidence_notes": [],
        },
    )
    created_timestamp = created_at.timestamp()
    for output_path in clone_dir.iterdir():
        os.utime(output_path, (created_timestamp, created_timestamp))
    if stale_strategy and report:
        strategy_time = created_timestamp
        report_time = strategy_time + 30
        os.utime(clone_dir / "creator_strategy_plan.json", (strategy_time, strategy_time))
        os.utime(clone_dir / "creator_clone_result.json", (report_time, report_time))
        os.utime(clone_dir / "creator_clone.html", (report_time, report_time))
    return set_id


def test_library_page_is_independent_read_only_view():
    response = client.get("/library")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "已有分析产物" in response.text
    assert 'href="/library" aria-current="page"' in response.text
    assert 'id="library-filters"' in response.text
    assert 'id="library-items"' in response.text
    assert "/static/library.js?v=" in response.text
    assert "触发扫描、下载、富化或大模型任务" in response.text


def test_library_api_unifies_case_report_and_strategy_without_paths_or_bodies():
    case_id = _add_case(1, title="镜头拆解", author="案例作者")
    set_id = _add_creator(1, title="甜美账号", creator_name="Creator A")

    response = client.get("/api/library/assets?page_size=20")
    payload = response.json()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert payload["ok"] is True
    assert payload["pagination"]["total"] == 3
    by_type = {item["asset_type"]: item for item in payload["items"]}
    assert by_type["case"]["asset_id"] == case_id
    assert by_type["case"]["open_url"] == f"/cases/{case_id}"
    assert by_type["creator_report"]["asset_id"] == f"{set_id}_report"
    assert by_type["creator_report"]["open_url"].endswith("/creator_clone.html")
    assert by_type["strategy_plan"]["open_url"] == ""
    assert by_type["strategy_plan"]["resume_target"]["resource_id"] == set_id
    assert by_type["creator_report"]["sample_count"] == 10
    assert by_type["creator_report"]["selected_count"] == 3
    serialized = response.text
    assert str(settings.output_dir) not in serialized
    assert "<h1>report</h1>" not in serialized
    assert "# report" not in serialized


def test_creator_assets_only_offer_resume_for_readable_sample_sets():
    runtime_only_id = "clone_runtime_only_done"
    _write_json(
        settings.creator_state_dir / "sessions.json",
        {
            "sessions": {
                runtime_only_id: {
                    "project_id": runtime_only_id,
                    "state": "DONE",
                    "updated_at": "2026-07-03T08:00:00+00:00",
                }
            }
        },
    )

    missing_samples_id = "clone_missing_samples"
    missing_samples_dir = settings.creator_clones_dir / missing_samples_id
    missing_samples_dir.mkdir(parents=True)
    _write_json(missing_samples_dir / "creator_clone_result.json", {"report_quality": {"quality_score": 70}})
    (missing_samples_dir / "creator_clone.html").write_text("<h1>report</h1>", encoding="utf-8")
    _write_json(missing_samples_dir / "creator_strategy_plan.json", {"source": {"report_quality_score": 70}})

    invalid_samples_id = "clone_invalid_samples"
    invalid_samples_dir = settings.creator_clones_dir / invalid_samples_id
    invalid_samples_dir.mkdir(parents=True)
    (invalid_samples_dir / "samples.json").write_text("{broken", encoding="utf-8")
    _write_json(invalid_samples_dir / "creator_clone_result.json", {"report_quality": {"quality_score": 71}})
    (invalid_samples_dir / "creator_clone.html").write_text("<h1>report</h1>", encoding="utf-8")

    valid_id = _add_creator(202, title="可恢复 Creator")

    payload = build_library_assets(page_size=100, refresh=True)
    by_id = {item["asset_id"]: item for item in payload["items"]}

    runtime_only = by_id[f"{runtime_only_id}_report"]
    assert runtime_only["status"] == "missing"
    assert runtime_only["open_url"] == ""
    assert runtime_only["resume_target"]["route"] == ""
    assert runtime_only["resume_target"]["resource_id"] == ""

    missing_report = by_id[f"{missing_samples_id}_report"]
    assert missing_report["status"] == "incomplete"
    assert missing_report["open_url"].endswith("/creator_clone.html")
    assert missing_report["resume_target"]["route"] == ""
    assert missing_report["resume_target"]["resource_id"] == ""

    missing_strategy = by_id[f"{missing_samples_id}_strategy"]
    assert missing_strategy["resume_target"]["route"] == ""
    assert missing_strategy["resume_target"]["resource_id"] == ""

    invalid_report = by_id[f"{invalid_samples_id}_report"]
    assert invalid_report["open_url"].endswith("/creator_clone.html")
    assert invalid_report["resume_target"]["route"] == ""
    assert invalid_report["resume_target"]["resource_id"] == ""

    valid_report = by_id[f"{valid_id}_report"]
    assert valid_report["open_url"].endswith("/creator_clone.html")
    assert valid_report["resume_target"] == {
        "route": "profile",
        "stage": "export",
        "resource_id": valid_id,
        "job_id": "",
        "task_type": "creator_report",
        "mode": "result",
        "open_url": valid_report["open_url"],
    }

    valid_strategy = by_id[f"{valid_id}_strategy"]
    assert valid_strategy["resume_target"]["route"] == "profile"
    assert valid_strategy["resume_target"]["stage"] == "export"
    assert valid_strategy["resume_target"]["resource_id"] == valid_id


def test_library_filters_paginates_and_marks_stale_assets():
    for index in range(1, 26):
        _add_case(index, title=f"检索案例 {index}")
    _add_creator(101, title="目标创作者", stale_strategy=True)

    first_page = client.get("/api/library/assets?type=case&query=检索案例&page=1&page_size=20").json()
    second_page = client.get("/api/library/assets?type=case&query=检索案例&page=2&page_size=20").json()
    stale = client.get("/api/library/assets?type=strategy_plan&status=stale").json()
    dated = client.get(
        "/api/library/assets?type=creator_report&date_from=2026-07-02&date_to=2026-07-02"
    ).json()

    assert len(first_page["items"]) == 20
    assert first_page["pagination"] == {"page": 1, "page_size": 20, "total": 25, "has_next": True}
    assert len(second_page["items"]) == 5
    assert second_page["pagination"]["has_next"] is False
    assert len(stale["items"]) == 1
    assert stale["items"][0]["status"] == "stale"
    assert len(dated["items"]) == 1
    assert client.get("/api/library/assets?page_size=101").status_code == 422
    invalid_range = client.get("/api/library/assets?date_from=2026-07-03&date_to=2026-07-01")
    assert invalid_range.status_code == 400
    assert invalid_range.json()["error_code"] == "LIBRARY_DATE_RANGE_INVALID"


def test_library_redacts_secrets_paths_and_external_urls():
    secret_key = "sk-thismustneverappear123456"
    title = (
        f"Cookie: sessionid=private Authorization=Bearer abc.def API_KEY={secret_key} "
        f"/var/private/archive https://signed.example/video?token=secret"
    )
    _add_case(7, title=title, author="Bearer topsecret")

    response = client.get("/api/library/assets")

    assert response.status_code == 200
    body = response.text
    for forbidden in (
        "sessionid=private",
        "abc.def",
        secret_key,
        "/var/private/archive",
        "signed.example",
        "token=secret",
    ):
        assert forbidden not in body
    assert "敏感配置已隐藏" in body or "授权信息已隐藏" in body
    item = response.json()["items"][0]
    assert item["open_url"].startswith("/cases/")
    assert not item["open_url"].startswith("http")


def test_library_rejects_symlinks_and_survives_invalid_or_oversized_json(tmp_path: Path):
    case_id = _add_case(8)
    case_dir = settings.cases_dir / case_id
    outside = tmp_path / "outside"
    outside.mkdir()
    for child in list(case_dir.iterdir()):
        child.unlink()
    case_dir.rmdir()
    case_dir.symlink_to(outside, target_is_directory=True)

    nested_case_id = _add_case(11)
    outside_enrichment = tmp_path / "outside-enrichment"
    outside_enrichment.mkdir()
    _write_json(outside_enrichment / "manifest.json", {"private": "must not be indexed"})
    (settings.cases_dir / nested_case_id / "enrichment").symlink_to(outside_enrichment, target_is_directory=True)
    with SessionLocal() as session:
        session.add(CaseArtifact(case_id="case_../../etc/passwd", status="success"))
        session.commit()

    good_id = _add_creator(8, title="正常报告")
    bad_id = _add_creator(9, title="损坏报告")
    (settings.creator_clones_dir / bad_id / "samples.json").write_text("{broken", encoding="utf-8")
    huge_id = _add_creator(10, title="超大报告")
    (settings.creator_clones_dir / huge_id / "creator_clone_result.json").write_text(
        "{" + " " * (2 * 1024 * 1024 + 1) + "}",
        encoding="utf-8",
    )

    payload = client.get("/api/library/assets?page_size=100").json()

    assert payload["ok"] is True
    assert payload["meta"]["partial"] is True
    assert payload["source_errors"]
    assert "creator_assets" in payload["meta"]["truncated_sources"]
    by_id = {item["asset_id"]: item for item in payload["items"]}
    assert by_id[case_id]["status"] == "missing"
    assert "enrichment/manifest.json" not in by_id[nested_case_id]["available_files"]
    assert by_id[f"{good_id}_report"]["status"] == "ready"
    assert by_id[f"{bad_id}_report"]["status"] == "incomplete"
    assert by_id[f"{huge_id}_report"]["status"] == "incomplete"
    assert all(".." not in item["asset_id"] for item in payload["items"])
    assert str(outside) not in json.dumps(payload, ensure_ascii=False)


def test_library_source_failure_preserves_other_assets(monkeypatch):
    set_id = _add_creator(12, title="来源降级仍可见")
    monkeypatch.setattr(settings, "database_url", "sqlite:////definitely/missing/library.db")

    response = client.get("/api/library/assets")
    payload = response.json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["meta"]["partial"] is True
    assert any(item["asset_id"] == f"{set_id}_report" for item in payload["items"])
    assert any(error["source"] == "cases" for error in payload["source_errors"])


def test_library_scales_to_500_assets_per_type_without_reading_media(monkeypatch):
    for index in range(500):
        _add_case(index)
        _add_creator(index)

    original_read_text = Path.read_text
    read_count = 0

    def guarded_read_text(path: Path, *args, **kwargs):
        nonlocal read_count
        assert path.suffix in {".json"}, f"unexpected body read: {path.name}"
        read_count += 1
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    started = time.perf_counter()
    payload = build_library_assets(page_size=100)
    duration = time.perf_counter() - started
    first_read_count = read_count
    cached_payload = build_library_assets(page=2, page_size=100)

    assert payload["pagination"]["total"] == 1500
    assert payload["facets"]["types"] == {
        "case": 500,
        "creator_report": 500,
        "strategy_plan": 500,
    }
    assert len(payload["items"]) == 100
    assert payload["pagination"]["has_next"] is True
    assert cached_payload["pagination"]["page"] == 2
    assert read_count == first_read_count
    assert len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) < 250_000
    assert duration < 5.0


@pytest.mark.skipif(NODE_BINARY is None, reason="Node.js is unavailable")
def test_library_frontend_handles_partial_results_and_safe_resume_targets():
    script = """
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync('app/static/library.js', 'utf8');
const document = {readyState: 'complete', querySelector() { return null; }};
const window = {document, location: {search: '', href: 'http://127.0.0.1:8765/library'}};
vm.runInNewContext(source, {window, URL, URLSearchParams, Set, Object, String, Number, Array, JSON, Date});

class FakeNode {
  constructor(tagName, ownerDocument) {
    this.tagName = String(tagName).toUpperCase();
    this.ownerDocument = ownerDocument;
    this.children = [];
    this.dataset = {};
    this.className = '';
    this.textContent = '';
    this.listeners = {};
  }
  appendChild(child) { this.children.push(child); return child; }
  addEventListener(type, callback) { this.listeners[type] = callback; }
}
const fakeDocument = {
  createElement(tagName) { return new FakeNode(tagName, fakeDocument); },
};
function descendants(node) {
  return [node, ...node.children.flatMap(descendants)];
}
function rowText(node) {
  return descendants(node).map((item) => item.textContent || '').join(' ');
}
const writes = [];
const onReturnToCreator = (target) => writes.push(target);
const missingRow = window.LibraryPage.renderAssetRow(fakeDocument, {
  asset_type: 'creator_report', status: 'missing', title: 'Missing Creator', asset_id: 'clone_missing_report',
  open_url: '', resume_target: {}, available_files: [],
}, onReturnToCreator);
const reportOnlyRow = window.LibraryPage.renderAssetRow(fakeDocument, {
  asset_type: 'creator_report', status: 'incomplete', title: 'Report only', asset_id: 'clone_report_only_report',
  open_url: '/api/creator-clone/sets/clone_report_only/files/creator_clone.html',
  resume_target: {}, available_files: ['creator_clone.html'],
}, onReturnToCreator);
[...descendants(missingRow), ...descendants(reportOnlyRow)]
  .filter((node) => node.tagName === 'BUTTON')
  .forEach((button) => button.listeners.click?.());
const result = {
  warnings: window.LibraryPage.partialMessages({
    source_errors: [],
    meta: {partial: true, truncated_sources: ['creator_runtime']},
  }),
  safeTarget: window.LibraryPage.normalizeResumeTarget({
    route: 'profile', stage: 'export', resource_id: 'clone_abc123',
    open_url: '/api/creator-clone/sets/clone_abc123/files/creator_clone.html',
  }),
  badTarget: window.LibraryPage.normalizeResumeTarget({
    route: 'profile', resource_id: '../../etc/passwd', open_url: 'https://evil.example/report',
  }),
  boundedUrl: window.LibraryPage.buildApiUrl({
    type: 'case', status: 'ready', query: '标题', page: 2, pageSize: 500,
  }),
  missingRowText: rowText(missingRow),
  reportOnlyRowText: rowText(reportOnlyRow),
  resumeWrites: writes.length,
};
process.stdout.write(JSON.stringify(result));
"""
    assert NODE_BINARY is not None
    completed = subprocess.run(
        [str(NODE_BINARY), "-e", script],
        cwd=Path.cwd(),
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert len(result["warnings"]) == 1
    assert "Runtime" in result["warnings"][0]
    assert result["safeTarget"]["resource_id"] == "clone_abc123"
    assert result["badTarget"] is None
    assert "page_size=100" in result["boundedUrl"]
    assert "暂无可用入口" in result["missingRowText"]
    assert "返回 Creator" not in result["missingRowText"]
    assert "打开报告" in result["reportOnlyRowText"]
    assert "返回 Creator" not in result["reportOnlyRowText"]
    assert result["resumeWrites"] == 0
