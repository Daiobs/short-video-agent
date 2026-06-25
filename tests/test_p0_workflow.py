from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import CaseArtifact, DouyinVideoItem, VideoQualityCandidate
from app.providers.base import VideoQualityCandidateDTO
from app.providers.douyin_web import DouyinWebProvider, normalize_douyin_detail_payload, normalize_douyin_html_payload
from app.services.auto_analyzer import analyze_case_artifact
from app.services.douyin_url_parser import extract_aweme_id
from app.services.quality_resolver import resolve_quality_candidates
from app.services.ffmpeg_service import plan_keyframe_timestamps
from app.services.video_importer import engagement_score
from app.services import candidate_probe


client = TestClient(app)


def require_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required for this test")


def make_sample_video(path: Path, duration: float = 2.0) -> Path:
    require_ffmpeg()
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size=320x240:rate=10:duration={duration}",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    return path


def upload_video(video_path: Path, source_url: str = "https://example.com/source") -> dict:
    with video_path.open("rb") as file_obj:
        response = client.post(
            "/api/import/local-video",
            data={
                "title": "测试视频",
                "source_url": source_url,
                "author": "tester",
                "like_count": "10",
                "comment_count": "2",
                "share_count": "3",
                "create_time": "2026-06-24",
                "remark": "用于测试",
            },
            files={"video_file": ("sample.mp4", file_obj, "video/mp4")},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    return payload["local_video"]


def test_engagement_score_formula() -> None:
    assert engagement_score(10, 2, 3) == 44
    assert engagement_score(-1, 2, 0) == 10


def test_home_uses_versioned_static_assets() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "/static/app.js?v=" in response.text
    assert "/static/app.css?v=" in response.text


def test_extract_aweme_id_from_modal_and_path() -> None:
    assert extract_aweme_id("7647533902413173321") == "7647533902413173321"
    assert (
        extract_aweme_id("https://www.douyin.com/video/7647533902413173321")
        == "7647533902413173321"
    )
    assert (
        extract_aweme_id("https://www.douyin.com/user/self?modal_id=7647533902413173321")
        == "7647533902413173321"
    )


def test_douyin_detail_payload_returns_web_candidates_without_exposing_provider_url_in_public_api() -> None:
    payload = {
        "aweme_detail": {
            "aweme_id": "7647533902413173321",
            "desc": "测试作品",
            "author": {"nickname": "作者"},
            "create_time": 1782300000,
            "statistics": {"digg_count": 100, "comment_count": 7, "share_count": 3},
            "video": {
                "cover": {"url_list": ["https://example.com/cover.jpg"]},
                "bit_rate": [
                    {
                        "gear_name": "normal_720p",
                        "bit_rate": 1_000_000,
                        "play_addr": {
                            "width": 720,
                            "height": 1280,
                            "data_size": 1_000,
                            "url_list": ["https://aweme.snssdk.com/aweme/v1/play/?video_id=low"],
                        },
                    },
                    {
                        "gear_name": "normal_1080p",
                        "bit_rate": 2_500_000,
                        "play_addr": {
                            "width": 1080,
                            "height": 1920,
                            "data_size": 2_000,
                            "url_list": ["https://v3-dy-o.zjcdn.com/video/tos/cn/high.mp4"],
                        },
                    },
                ],
            },
        }
    }

    metadata, candidates = normalize_douyin_detail_payload(payload, "7647533902413173321")

    assert metadata["title"] == "测试作品"
    assert metadata["like_count"] == 100
    assert metadata["comment_count"] == 7
    assert metadata["share_count"] == 3
    assert metadata["create_time"].startswith("2026-06-24")
    assert candidates[0].quality_label.startswith("normal_1080p")
    assert candidates[0].bitrate == 2_500_000


def test_douyin_html_payload_fallback_reads_render_data() -> None:
    aweme_id = "7622653084993647603"
    payload = {
        "loaderData": {
            "video": {
                "aweme_detail": {
                    "aweme_id": aweme_id,
                    "desc": "HTML作品",
                    "author": {"nickname": "网页作者"},
                    "video": {
                        "play_addr": {
                            "width": 1080,
                            "height": 1920,
                            "data_size": 4096,
                            "url_list": ["https://v3-dy-o.zjcdn.com/video/tos/cn/html.mp4"],
                        }
                    },
                }
            }
        }
    }
    encoded = json.dumps(payload, ensure_ascii=False)
    html = f'<html><script id="RENDER_DATA" type="application/json">{encoded}</script></html>'

    metadata, candidates = normalize_douyin_html_payload(html, aweme_id)

    assert metadata["title"] == "HTML作品"
    assert metadata["author"] == "网页作者"
    assert candidates[0].quality_label == "web 1080x1920"
    assert candidates[0].url.endswith("html.mp4")


def test_douyin_provider_falls_back_to_video_page_when_detail_is_not_json() -> None:
    aweme_id = "7622653084993647603"
    html_payload = {
        "aweme_detail": {
            "aweme_id": aweme_id,
            "desc": "fallback",
            "video": {
                "bit_rate": [
                    {
                        "gear_name": "normal_1080p",
                        "bit_rate": 2_000_000,
                        "play_addr": {
                            "width": 1080,
                            "height": 1920,
                            "data_size": 2048,
                            "url_list": ["https://aweme.snssdk.com/aweme/v1/play/?video_id=fallback"],
                        },
                    }
                ]
            },
        }
    }
    html = f'<script id="RENDER_DATA">{json.dumps(html_payload)}</script>'

    class FakeResponse:
        status_code = 200

        def __init__(self, text="", json_error=False):
            self.text = text
            self.json_error = json_error

        def json(self):
            if self.json_error:
                raise ValueError("not json")
            return {}

    class FakeClient:
        def __init__(self):
            self.urls = []

        def get(self, url, headers=None):
            self.urls.append(url)
            if "aweme/detail" in url:
                return FakeResponse("<html></html>", json_error=True)
            return FakeResponse(html)

    fake_client = FakeClient()
    metadata, candidates = DouyinWebProvider(client=fake_client).resolve(aweme_id)

    assert metadata["title"] == "fallback"
    assert candidates[0].candidate_id
    assert len(fake_client.urls) == 2


def test_keyframe_plan_caps_long_video_at_30_frames() -> None:
    timestamps = plan_keyframe_timestamps(120)
    assert len(timestamps) == 30
    assert timestamps[0] == 0
    assert timestamps[-1] < 120


def test_invalid_local_upload_returns_error_code(tmp_path: Path) -> None:
    invalid = tmp_path / "not-video.txt"
    invalid.write_text("not a video", encoding="utf-8")
    with invalid.open("rb") as file_obj:
        response = client.post(
            "/api/import/local-video",
            data={"title": "bad"},
            files={"video_file": ("not-video.txt", file_obj, "text/plain")},
        )
    payload = response.json()
    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["error_code"] == "INVALID_VIDEO_FILE"


def test_local_upload_and_sync_case_build_generate_artifact(tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "sample.mp4")
    local_video = upload_video(video_path, source_url="https://www.douyin.com/video/7651938969785849192")

    response = client.post(
        "/api/cases/build",
        json={"local_video_id": local_video["local_video_id"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True

    case = payload["case"]
    case_dir = Path(case["video_path"]).parent
    expected = [
        "video.mp4",
        "metadata.json",
        "qualities.json",
        "ffprobe.json",
        "analysis_input.json",
        "prompt.md",
        "worksheet.json",
        "analysis_brief.md",
        "README.md",
        "contact_sheet.jpg",
    ]
    for filename in expected:
        assert (case_dir / filename).is_file(), filename
    assert Path(case["keyframes_dir"]).is_dir()
    assert list(Path(case["keyframes_dir"]).glob("frame_*.jpg"))

    metadata = json.loads((case_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["title"] == "测试视频"
    assert metadata["engagement_score"] == 44
    assert metadata["aweme_id"] == "7651938969785849192"

    qualities = json.loads((case_dir / "qualities.json").read_text(encoding="utf-8"))
    assert qualities == {"source": "local", "candidates": []}

    analysis_input = json.loads((case_dir / "analysis_input.json").read_text(encoding="utf-8"))
    assert analysis_input["local_video_id"] == local_video["local_video_id"]
    assert analysis_input["aweme_id"] == "7651938969785849192"
    assert analysis_input["stats"]["engagement_score"] == 44
    assert analysis_input["content_category"] == "generic"
    assert analysis_input["analysis_context"]["label"] == "通用短视频"
    assert analysis_input["analysis_lens"]
    assert analysis_input["key_questions"]
    assert analysis_input["content_ratio"]
    assert "前3秒钩子" in analysis_input["analysis_focus"]

    prompt = (case_dir / "prompt.md").read_text(encoding="utf-8")
    assert "# 爆款案例拆解 Prompt" in prompt
    assert "内容类型：通用短视频" in prompt
    assert "## 10. 分镜表" in prompt

    worksheet = json.loads((case_dir / "worksheet.json").read_text(encoding="utf-8"))
    assert worksheet["case_id"] == case["case_id"]
    assert worksheet["content_category"] == "generic"
    assert "hook" in worksheet["sections"]
    analysis_brief = (case_dir / "analysis_brief.md").read_text(encoding="utf-8")
    assert "# 短视频案例分析工作表" in analysis_brief

    detail_response = client.get(f"/cases/{case['case_id']}")
    assert detail_response.status_code == 200
    assert "素材包分析视图" in detail_response.text
    assert "case_detail.js?v=" in detail_response.text

    api_response = client.get(f"/api/cases/{case['case_id']}")
    assert api_response.status_code == 200
    api_payload = api_response.json()
    assert api_payload["ok"] is True
    assert api_payload["case"]["analysis_input"]["case_id"] == case["case_id"]
    assert api_payload["case"]["analysis_profiles"]
    assert api_payload["case"]["artifact_urls"]["keyframes"]
    assert api_payload["case"]["worksheet"]["sections"]["hook"]
    assert "# 短视频案例分析工作表" in api_payload["case"]["analysis_brief"]
    assert "# 爆款案例拆解 Prompt" in api_payload["case"]["prompt"]

    update_response = client.post(
        f"/api/cases/{case['case_id']}/analysis-category",
        json={"category_id": "tutorial"},
    )
    assert update_response.status_code == 200
    update_payload = update_response.json()
    assert update_payload["ok"] is True
    updated_case = update_payload["case"]
    assert updated_case["analysis_input"]["content_category"] == "tutorial"
    assert updated_case["analysis_input"]["content_category_label"] == "教学 / 教程"
    assert any("解决了什么具体问题" in item for item in updated_case["analysis_input"]["key_questions"])
    assert "内容类型：教学 / 教程" in updated_case["prompt"]

    persisted_analysis = json.loads((case_dir / "analysis_input.json").read_text(encoding="utf-8"))
    assert persisted_analysis["content_category"] == "tutorial"

    worksheet_payload = updated_case["worksheet"]
    worksheet_payload["summary"] = "这条视频适合拆教程结构。"
    worksheet_payload["sections"]["hook"]["fields"]["first_impression"]["value"] = "开头需要直接给出结果承诺。"
    worksheet_response = client.post(
        f"/api/cases/{case['case_id']}/worksheet",
        json={"worksheet": worksheet_payload},
    )
    assert worksheet_response.status_code == 200
    worksheet_update = worksheet_response.json()
    assert worksheet_update["ok"] is True
    assert worksheet_update["case"]["worksheet"]["summary"] == "这条视频适合拆教程结构。"
    assert "开头需要直接给出结果承诺" in worksheet_update["case"]["analysis_brief"]
    persisted_worksheet = json.loads((case_dir / "worksheet.json").read_text(encoding="utf-8"))
    assert persisted_worksheet["summary"] == "这条视频适合拆教程结构。"
    assert "开头需要直接给出结果承诺" in (case_dir / "analysis_brief.md").read_text(encoding="utf-8")

    class FakeLLMProvider:
        def analyze(self, prompt, image_paths):
            assert "只输出合法 JSON" in prompt
            assert image_paths
            return {
                "summary": "自动拆解结果",
                "content_category": "tutorial",
                "content_category_label": "教学 / 教程",
                "confidence": 0.88,
                "hook_analysis": {
                    "first_impression": "开头直接给结果",
                    "why_stop_scrolling": "用户能马上知道收益",
                    "first_3_seconds": ["0s 展示结果"],
                    "optimization": "补一个更强对比",
                },
                "visual_analysis": {"scene": "测试场景"},
                "copywriting_analysis": {"title_click_reason": "有明确承诺"},
                "replication": {"remake_angle": "拆成三步教程"},
                "publish_package": {"titles": ["一招学会"]},
            }

    db = SessionLocal()
    try:
        artifact = db.get(CaseArtifact, case["case_id"])
        analysis = analyze_case_artifact(artifact, provider=FakeLLMProvider())
    finally:
        db.close()
    assert analysis["analysis_result"]["summary"] == "自动拆解结果"
    assert Path(analysis["analysis_result_path"]).is_file()
    assert Path(analysis["analysis_report_path"]).is_file()

    analyzed_api_response = client.get(f"/api/cases/{case['case_id']}")
    analyzed_case = analyzed_api_response.json()["case"]
    assert analyzed_case["analysis_result"]["summary"] == "自动拆解结果"
    assert "# AI 自动拆解报告" in analyzed_case["analysis_report"]

    image_response = client.get(f"/api/cases/{case['case_id']}/contact-sheet")
    assert image_response.status_code == 200
    assert image_response.headers["content-type"].startswith("image/jpeg")

    keyframe_url = api_payload["case"]["artifact_urls"]["keyframes"][0]["url"]
    keyframe_response = client.get(keyframe_url)
    assert keyframe_response.status_code == 200
    assert keyframe_response.headers["content-type"].startswith("image/jpeg")


def test_build_case_job_reports_success(tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "job.mp4")
    local_video = upload_video(video_path)

    create_response = client.post(
        "/api/jobs/build-case",
        json={"local_video_id": local_video["local_video_id"]},
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["job_id"]

    deadline = time.time() + 10
    job = None
    while time.time() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()["job"]
        if job["status"] in {"success", "failed"}:
            break
        time.sleep(0.1)

    assert job is not None
    assert job["status"] == "success"
    assert job["progress"] == 100
    assert job["error_code"] == ""
    assert job["result_json"]["case_id"].startswith("case_")


def test_download_and_build_case_job_reports_case_result(monkeypatch, tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "download-build.mp4")
    local_video = upload_video(video_path)

    def fake_download_candidate(db, aweme_id, candidate_id, progress=None):
        if progress:
            progress(100, "下载完成")
        return {
            "download_id": "download_fake",
            "aweme_id": aweme_id,
            "candidate_id": candidate_id,
            "file_path": local_video["local_video_id"],
            "size_bytes": Path(local_video["local_video_id"]).stat().st_size if Path(local_video["local_video_id"]).exists() else 0,
            "local_video_id": local_video["local_video_id"],
        }

    monkeypatch.setattr("app.routes.jobs.download_candidate", fake_download_candidate)

    create_response = client.post(
        "/api/jobs/download-and-build-case",
        json={"aweme_id": "7650000000000000200", "candidate_id": "cand_chain"},
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["job_id"]

    deadline = time.time() + 10
    job = None
    while time.time() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()["job"]
        if job["status"] in {"success", "failed"}:
            break
        time.sleep(0.1)

    assert job is not None
    assert job["status"] == "success"
    assert job["progress"] == 100
    assert job["result_json"]["download"]["download_id"] == "download_fake"
    assert job["result_json"]["case"]["case_id"].startswith("case_")
    assert Path(job["result_json"]["case"]["analysis_input_path"]).is_file()


def test_download_build_analyze_case_job_reports_auto_analysis(monkeypatch, tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "download-build-analyze.mp4")
    local_video = upload_video(video_path)

    def fake_download_candidate(db, aweme_id, candidate_id, progress=None):
        if progress:
            progress(100, "下载完成")
        return {
            "download_id": "download_fake_auto",
            "aweme_id": aweme_id,
            "candidate_id": candidate_id,
            "file_path": local_video["local_video_id"],
            "size_bytes": 100,
            "local_video_id": local_video["local_video_id"],
        }

    def fake_analyze_case_artifact(artifact, progress=None):
        if progress:
            progress(100, "自动拆解完成")
        case_dir = Path(artifact.prompt_path).parent
        result_path = case_dir / "analysis_result.json"
        report_path = case_dir / "analysis_report.md"
        result = {"summary": "job 自动拆解", "hook_analysis": {}, "replication": {}}
        report = "# AI 自动拆解报告\n\njob 自动拆解\n"
        result_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        report_path.write_text(report, encoding="utf-8")
        return {
            "analysis_result_path": str(result_path),
            "analysis_report_path": str(report_path),
            "analysis_result": result,
            "analysis_report": report,
        }

    monkeypatch.setattr("app.routes.jobs.download_candidate", fake_download_candidate)
    monkeypatch.setattr("app.routes.jobs.analyze_case_artifact", fake_analyze_case_artifact)

    create_response = client.post(
        "/api/jobs/download-build-analyze-case",
        json={"aweme_id": "7650000000000000300", "candidate_id": "cand_chain_auto"},
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["job_id"]

    deadline = time.time() + 10
    job = None
    while time.time() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()["job"]
        if job["status"] in {"success", "failed"}:
            break
        time.sleep(0.1)

    assert job is not None
    assert job["status"] == "success"
    assert job["result_json"]["analysis_status"] == "success"
    assert job["result_json"]["analysis"]["analysis_result"]["summary"] == "job 自动拆解"
    assert Path(job["result_json"]["analysis"]["analysis_report_path"]).is_file()


def test_quality_resolver_caches_candidates_without_public_url() -> None:
    class FakeProvider:
        def resolve(self, aweme_id, source_urls=None):
            return (
                {
                    "aweme_id": aweme_id,
                    "title": "网页作品",
                    "source_url": f"https://www.douyin.com/video/{aweme_id}",
                    "like_count": 10,
                    "comment_count": 2,
                    "share_count": 3,
                    "create_time": "2026-06-24T11:20:00+00:00",
                },
                [
                    VideoQualityCandidateDTO(
                        candidate_id="cand_test_cache",
                        aweme_id=aweme_id,
                        quality_label="1080p",
                        url="https://aweme.snssdk.com/aweme/v1/play/?video_id=abc",
                        size_bytes=100,
                        bitrate=2000,
                        host="aweme.snssdk.com",
                        object_key="video_id:abc",
                        expires_at=0,
                        source="douyin_web",
                    )
                ],
            )

    db = SessionLocal()
    try:
        aweme_id = "7650000000000000001"
        existing_candidate = db.get(VideoQualityCandidate, "cand_test_cache")
        if existing_candidate:
            db.delete(existing_candidate)
        existing_aweme = db.get(DouyinVideoItem, aweme_id)
        if existing_aweme:
            db.delete(existing_aweme)
        db.commit()

        results = resolve_quality_candidates(db, aweme_id, provider=FakeProvider())
        assert results[0]["candidate_id"] == "cand_test_cache"
        assert "url" not in results[0]
        cached = db.get(VideoQualityCandidate, "cand_test_cache")
        assert cached is not None
        assert cached.url.startswith("https://aweme.snssdk.com/")
        aweme = db.get(DouyinVideoItem, aweme_id)
        assert aweme is not None
        assert aweme.title == "网页作品"
        assert aweme.like_count == 10
        assert aweme.comment_count == 2
        assert aweme.share_count == 3
        assert aweme.engagement_score == 44
        assert aweme.create_time == "2026-06-24T11:20:00+00:00"
    finally:
        db.close()


def test_candidate_probe_ranks_fastest_equivalent_without_promoting_lower_quality(monkeypatch) -> None:
    candidate_probe._HOST_LATENCY_SECONDS.clear()
    candidates = [
        VideoQualityCandidateDTO(
            candidate_id="slow_high",
            aweme_id="7650000000000000100",
            quality_label="1080p",
            url="https://slow.example-cdn.com/video.mp4",
            size_bytes=1000,
            bitrate=3000,
            host="slow.example-cdn.com",
            object_key="video.mp4",
            expires_at=0,
            source="douyin_native.bit_rate.0.play_addr",
        ),
        VideoQualityCandidateDTO(
            candidate_id="fast_high",
            aweme_id="7650000000000000100",
            quality_label="1080p",
            url="https://fast.example-cdn.com/video.mp4",
            size_bytes=1000,
            bitrate=3000,
            host="fast.example-cdn.com",
            object_key="video.mp4",
            expires_at=0,
            source="douyin_native.bit_rate.0.play_addr",
        ),
        VideoQualityCandidateDTO(
            candidate_id="fast_low",
            aweme_id="7650000000000000100",
            quality_label="720p",
            url="https://fast.example-cdn.com/low.mp4",
            size_bytes=500,
            bitrate=1000,
            host="fast.example-cdn.com",
            object_key="low.mp4",
            expires_at=0,
            source="douyin_native.bit_rate.1.play_addr",
        ),
    ]

    monkeypatch.setattr(
        "app.services.candidate_probe._probe_candidate_latency",
        lambda candidate: {"slow_high": 0.5, "fast_high": 0.05}.get(candidate.candidate_id),
    )

    ranked = candidate_probe.rank_fastest_equivalent_candidates(candidates)

    assert [candidate.candidate_id for candidate in ranked] == ["fast_high", "slow_high", "fast_low"]


def test_single_import_and_qualities_api_use_candidate_id(monkeypatch) -> None:
    class FakeProvider:
        def resolve(self, aweme_id, source_urls=None):
            return (
                {"aweme_id": aweme_id, "title": "API作品"},
                [
                    VideoQualityCandidateDTO(
                        candidate_id="cand_api_test",
                        aweme_id=aweme_id,
                        quality_label="1080p",
                        url="https://aweme.snssdk.com/aweme/v1/play/?video_id=api",
                        size_bytes=100,
                        bitrate=2000,
                        host="aweme.snssdk.com",
                        object_key="video_id:api",
                        expires_at=0,
                        source="douyin_web",
                    )
                ],
            )

    monkeypatch.setattr("app.services.quality_resolver.DouyinWebProvider", FakeProvider)
    import_response = client.post(
        "/api/videos/import-single",
        json={"value": "7650000000000000002"},
    )
    assert import_response.status_code == 200
    assert import_response.json()["video"]["aweme_id"] == "7650000000000000002"

    quality_response = client.post(
        "/api/videos/qualities",
        json={"aweme_ids": ["7650000000000000002"]},
    )
    assert quality_response.status_code == 200
    candidate = quality_response.json()["results"]["7650000000000000002"][0]
    assert candidate["candidate_id"] == "cand_api_test"
    assert "url" not in candidate


def test_download_rejects_non_video_content_type(monkeypatch) -> None:
    class FakeResponse:
        is_redirect = False
        status_code = 200
        headers = {"Content-Type": "text/html", "Content-Length": "12"}
        url = "https://aweme.snssdk.com/aweme/v1/play/?video_id=html"

        def iter_bytes(self):
            yield b"<html></html>"

        def close(self):
            pass

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def build_request(self, method, url):
            return (method, url)

        def send(self, request, stream=False):
            return FakeResponse()

    monkeypatch.setattr("app.services.downloader.httpx.Client", FakeClient)
    db = SessionLocal()
    try:
        aweme_id = "7650000000000000003"
        existing = db.get(VideoQualityCandidate, "cand_html")
        if existing:
            db.delete(existing)
            db.commit()
        db.add(
            VideoQualityCandidate(
                candidate_id="cand_html",
                aweme_id=aweme_id,
                quality_label="bad",
                url="https://aweme.snssdk.com/aweme/v1/play/?video_id=html",
                size_bytes=10,
                bitrate=10,
                host="aweme.snssdk.com",
                object_key="video_id:html",
                expires_at=0,
                source="douyin_web",
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/downloads",
        json={"aweme_id": aweme_id, "candidate_id": "cand_html"},
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "CONTENT_TYPE_INVALID"


def test_download_success_creates_local_video_item(monkeypatch) -> None:
    class FakeResponse:
        is_redirect = False
        status_code = 200
        headers = {"Content-Type": "video/mp4", "Content-Length": "5"}
        url = "https://aweme.snssdk.com/aweme/v1/play/?video_id=ok"

        def iter_bytes(self):
            yield b"video"

        def close(self):
            pass

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def build_request(self, method, url):
            return (method, url)

        def send(self, request, stream=False):
            return FakeResponse()

    monkeypatch.setattr("app.services.downloader.httpx.Client", FakeClient)
    db = SessionLocal()
    try:
        aweme_id = "7650000000000000004"
        existing = db.get(VideoQualityCandidate, "cand_ok")
        if existing:
            db.delete(existing)
            db.commit()
        existing_aweme = db.get(DouyinVideoItem, aweme_id)
        if existing_aweme:
            db.delete(existing_aweme)
            db.commit()
        db.add(
            DouyinVideoItem(
                aweme_id=aweme_id,
                title="下载作品",
                source_url=f"https://www.douyin.com/video/{aweme_id}",
            )
        )
        db.add(
            VideoQualityCandidate(
                candidate_id="cand_ok",
                aweme_id=aweme_id,
                quality_label="1080p",
                url="https://aweme.snssdk.com/aweme/v1/play/?video_id=ok",
                size_bytes=5,
                bitrate=100,
                host="aweme.snssdk.com",
                object_key="video_id:ok",
                expires_at=0,
                source="douyin_web",
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/downloads",
        json={"aweme_id": aweme_id, "candidate_id": "cand_ok"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["download"]["local_video_id"].startswith("local_")
    assert Path(payload["download"]["file_path"]).read_bytes() == b"video"


def test_sync_case_build_returns_ffmpeg_not_found(monkeypatch, tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "missing-ffmpeg.mp4")
    local_video = upload_video(video_path)

    monkeypatch.setattr("app.services.ffmpeg_service.shutil.which", lambda name: None)
    response = client.post(
        "/api/cases/build",
        json={"local_video_id": local_video["local_video_id"]},
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error_code"] == "FFMPEG_NOT_FOUND"


def test_placeholder_endpoints_return_not_implemented() -> None:
    for path in (
        "/api/profile/scan",
        "/api/jobs/profile-scan",
    ):
        response = client.post(path)
        assert response.status_code == 501
        assert response.json()["error_code"] == "NOT_IMPLEMENTED"
