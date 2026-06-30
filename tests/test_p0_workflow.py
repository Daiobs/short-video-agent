from __future__ import annotations

import json
import base64
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings
from app.database import SessionLocal
from app.errors import AppError, ErrorCode
from app.main import app
from app.models import CaseArtifact, DouyinVideoItem, VideoQualityCandidate
from app.providers.base import VideoQualityCandidateDTO
from app.providers.douyin_web import DouyinWebProvider, normalize_douyin_detail_payload, normalize_douyin_html_payload
from app.providers.profile_base import ProfileScanRequest, ProfileVideoItem, profile_engagement_score, sorted_profile_items
from app.routes import cases as case_routes
from app.services.analysis_taxonomy import explain_content_category
from app.services.analysis_worksheet import normalize_worksheet, worksheet_quality_review
from app.services.auto_analyzer import analyze_case_artifact, existing_auto_analysis
from app.services.asr import run_case_asr
from app.services.douyin_url_parser import extract_aweme_id
from app.services.profile_scan import (
    DouyinPublicProfileProvider,
    ManualLinksProfileProvider,
    extract_sec_user_id,
    extract_profile_items_from_html,
    normalize_profile_url,
    scan_profile,
)
from app.services.quality_resolver import resolve_quality_candidates
from app.services.ffmpeg_service import plan_keyframe_timestamps
from app.services.llm_provider import AnthropicCompatibleProvider, OpenAICompatibleProvider, OpenAIResponsesProvider, parse_json_text
from app.services.ocr import run_case_ocr
from app.services.video_importer import engagement_score
from app.services import auto_analyzer, candidate_probe
from app.services.creator_clone import (
    CloneSample,
    CloneSampleSet,
    MAX_DISTILL_SAMPLES,
    build_distill_prompt,
    dedupe_samples,
    load_sample_set,
    normalize_creator_clone_result,
    performance_segments,
    save_sample_set,
    sample_from_dict,
    selected_evidence_constraints,
    selected_evidence_matrix,
    update_sample_set_selection,
    update_sample_set_with_case_artifacts,
    validate_selected_samples,
)


client = TestClient(app)


def detailed_visual_analysis() -> dict:
    return {
        "scene": "室内近景，背景留白突出主体",
        "subject": "人物居中看镜头，字幕贴近主体出现",
        "movement_rhythm": "0-2s 从静止到抬手，节奏逐秒推进",
    }


def detailed_timeline() -> list[dict]:
    return [{"time_range": "0-3s", "visual": "人物近景出现，字幕和抬手动作同步推进", "purpose": "停留"}]


def detailed_emotion_path() -> list[str]:
    return ["开头用近景主体抓注意", "中段用字幕承诺维持价值感", "结尾用互动问题引导评论"]


def detailed_content_ratio() -> list[dict]:
    return [
        {"name": "钩子", "percent": 40, "reason": "前三秒用近景和字幕制造停留"},
        {"name": "主体信息", "percent": 35, "reason": "中段用动作和字幕维持观看"},
        {"name": "互动转化", "percent": 25, "reason": "结尾引导评论和复刻需求"},
    ]


def detailed_shot_table() -> list[dict]:
    return [
        {
            "time": "0-3s",
            "visual": "人物近景抬手，字幕给出结果承诺",
            "action": "看镜头后抬手指向字幕",
            "subtitle": "先给结果，再给步骤",
            "purpose": "第一秒建立停留理由",
        }
    ]


def detailed_publish_package() -> dict:
    return {
        "titles": ["3 秒学会这个近景开头"],
        "caption": "保存这个近景开头结构，下次换成自己的角色视频直接复刻。",
        "hashtags": ["近景开头", "角色反差"],
    }


def detailed_copywriting_analysis() -> dict:
    return {"title_click_reason": "标题用 3 秒学会制造明确收益，并承接近景动作教程"}


def detailed_comment_insights() -> dict:
    return {
        "audience_needs": ["求同款链接和拍摄动作教程"],
        "comment_triggers": ["观众会追问近景开头怎么拍"],
        "replicable_interaction_design": "引导评论区留下想看的角色版本和动作难度",
    }


def detailed_avoid_copying() -> list[str]:
    return ["不要照搬原视频妆造和字幕表达，保留自己的角色设定与动作节奏"]


def detailed_evidence_summary() -> dict:
    return {
        "visual_input_mode": "multi_image",
        "visual_evidence": [
            {"claim": "前三秒近景和字幕共同制造停留", "evidence": "0-3s 关键帧显示人物居中抬手，字幕同步出现", "confidence": "high"}
        ],
        "asr_evidence": [
            {"claim": "口播开头先给结果承诺", "evidence": "ASR 转写出现“先给结果，再给步骤”的开头结构", "confidence": "high"}
        ],
        "ocr_evidence": [
            {"claim": "画面文字强化教程承诺", "evidence": "OCR 识别到“三秒学会”和步骤提示字幕", "confidence": "high"}
        ],
        "comment_evidence": [
            {"claim": "评论区存在复刻需求", "evidence": "评论里多次询问同款链接和拍摄动作教程", "confidence": "high"}
        ],
        "inferred_points": [],
        "evidence_gaps": [],
    }


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


def make_sample_video_with_audio(path: Path, duration: float = 2.0) -> Path:
    require_ffmpeg()
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size=320x240:rate=10:duration={duration}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={duration}",
        "-shortest",
        "-pix_fmt",
        "yuv420p",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
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


def test_content_category_explain_reports_local_rule_reason() -> None:
    guess = explain_content_category("黑婚纱申请出战 cos 写真 美拍")

    assert guess["category_id"] == "beauty_cos"
    assert guess["label"] == "美拍 / COS / 颜值向"
    assert guess["confidence"] in {"medium", "high"}
    assert "cos" in [keyword.lower() for keyword in guess["matched_keywords"]]
    assert guess["source"] == "local_rules"


def test_case_build_persists_beauty_content_category_guess(tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "beauty-category.mp4")
    with video_path.open("rb") as file_obj:
        upload_response = client.post(
            "/api/import/local-video",
            data={
                "title": "黑婚纱申请出战 cos 写真",
                "source_url": "https://example.com/beauty",
                "author": "coser",
                "like_count": "0",
                "comment_count": "0",
                "share_count": "0",
                "remark": "美拍 颜值",
            },
            files={"video_file": ("beauty.mp4", file_obj, "video/mp4")},
        )
    assert upload_response.status_code == 200
    local_video_id = upload_response.json()["local_video"]["local_video_id"]

    case_response = client.post("/api/cases/build", json={"local_video_id": local_video_id})
    assert case_response.status_code == 200
    case_id = case_response.json()["case"]["case_id"]
    case_payload = client.get(f"/api/cases/{case_id}").json()["case"]
    analysis_input = case_payload["analysis_input"]

    assert analysis_input["content_category"] == "beauty_cos"
    assert analysis_input["content_category_label"] == "美拍 / COS / 颜值向"
    assert analysis_input["content_category_guess"]["category_id"] == "beauty_cos"
    assert analysis_input["content_category_guess"]["matched_keywords"]
    assert "第一眼" in " ".join(analysis_input["analysis_lens"])


def test_home_uses_versioned_static_assets() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "/static/app.js?v=" in response.text
    assert "/static/app.css?v=" in response.text
    assert 'data-profile-build-max-items="10"' in response.text
    assert 'data-creator-clone-max-distill-samples="20"' in response.text
    assert "单作品解析" in response.text
    assert "创作者克隆实验室" in response.text
    assert "主页 URL / sec_user_id" in response.text
    assert "导入一组对标素材" in response.text
    assert "1. 导入素材" in response.text
    assert "2. 选择样本" in response.text
    assert "3. 富化证据" in response.text
    assert "4. 大模型蒸馏" in response.text
    assert "5. 导出规则" in response.text
    assert "粘贴作品链接" in response.text
    assert 'id="profile-scan-button"' in response.text
    assert 'id="profile-sort"' in response.text
    assert 'id="profile-evidence-filter"' in response.text
    assert "证据筛选" in response.text
    assert "可富化视频" in response.text
    assert "已有关键帧" in response.text
    assert 'id="profile-results-body"' in response.text
    assert 'id="profile-capture-audit"' in response.text
    assert 'id="profile-decision-board"' in response.text
    assert 'id="profile-segments-preview"' in response.text
    assert "不登录、不使用 Cookie" in response.text
    assert "不绕风控" in response.text
    assert "Creator Clone Lab" in response.text
    assert "浏览器辅助采集" in response.text
    assert "粘贴作品链接" in response.text
    assert "JSON / CSV 导入" in response.text
    assert "已有 Case 导入" in response.text
    assert "高级 / 安全交接包" in response.text
    assert "导入交接包" in response.text
    assert 'id="profile-handoff-file"' in response.text
    assert 'accept=".json,application/json"' in response.text
    assert 'id="profile-handoff-manifest"' in response.text
    assert "公开主页扫描（优先）" not in response.text
    assert "公开主页扫描（实验）" in response.text
    public_section = response.text[
        response.text.index('id="profile-public-section"') : response.text.index('id="profile-manual-section"')
    ]
    assert 'id="profile-browser-helper-button"' in public_section
    assert 'id="profile-chrome-status"' in public_section
    assert "主页 URL / sec_user_id" in public_section
    assert "插件辅助采集" in response.text
    assert "素材池概览" in response.text
    assert "样本选择" in response.text
    assert "证据富化" in response.text
    assert "导出规则" in response.text
    assert "插件辅助采集" in response.text
    assert 'id="profile-chrome-status"' in response.text
    assert 'id="profile-helper-tools"' in response.text
    assert 'id="profile-chrome-confirm"' in response.text
    assert "我确认本次辅助采集由本机 Chrome / 本机 IP 发起" in response.text
    assert 'id="profile-chrome-refresh-button"' not in response.text
    assert 'id="profile-launch-chrome-button"' not in response.text
    assert 'id="profile-open-chrome-profile-button"' not in response.text
    assert 'id="profile-copy-chrome-command-button"' not in response.text
    assert 'id="profile-clear-chrome-profile-button"' not in response.text
    assert 'id="profile-continue-chrome-button"' in response.text
    assert "本机 Chrome 辅助状态：尚未检测" in response.text
    assert "本地文件导入（后续接入）" in response.text
    assert "全选" in response.text
    assert "推荐组合" in response.text
    assert "高赞 Top 3" in response.text
    assert "高评 Top 3" in response.text
    assert "高分享 Top 3" in response.text
    assert "低表现 3 条" in response.text
    assert 'data-profile-preset="recommended_mix"' in response.text
    assert 'data-profile-preset="top_likes"' in response.text
    assert 'data-profile-preset="top_comments"' in response.text
    assert 'data-profile-preset="top_shares"' in response.text
    assert 'data-profile-preset="low_performance"' in response.text
    assert "继续采集更多" in response.text
    assert "检测 Chrome" not in response.text
    assert "启动 Chrome" not in response.text
    assert "复制启动命令" not in response.text
    assert "清理辅助 Profile" not in response.text
    assert "导入链接" in response.text
    assert "导入列表" in response.text
    assert "导入 Case" in response.text
    assert "summary-actions" in response.text
    assert "toolbar-actions summary-actions" not in response.text
    assert 'data-profile-source="public"' in response.text
    assert 'data-profile-source="manual"' in response.text
    assert 'data-profile-source="structured"' in response.text
    assert 'data-profile-source="handoff"' in response.text
    assert 'data-profile-source="case"' in response.text
    assert 'data-profile-import="' not in response.text
    assert 'data-profile-build="' not in response.text
    assert 'id="profile-selected-import-button"' not in response.text
    assert "<th>选择</th>" in response.text
    assert "<th>素材</th>" in response.text
    assert "<th>类型</th>" in response.text
    assert "<th>互动数据</th>" in response.text
    assert "<th>理解状态</th>" in response.text
    assert "<th>处理状态</th>" in response.text
    assert "<th>操作</th>" in response.text
    assert "确认样本并富化" in response.text
    assert 'id="profile-selection-basket"' in response.text
    assert "本轮样本篮" in Path("app/static/app.js").read_text(encoding="utf-8")
    assert 'id="profile-auto-distill"' in response.text
    assert "富化完成后自动大模型蒸馏" in response.text
    assert 'id="profile-auto-analyze"' not in response.text
    assert 'id="profile-evidence-status"' in response.text
    assert 'id="profile-distill-readiness"' in response.text
    assert "富化后会回填视频、关键帧、OCR、ASR" in response.text
    assert "下载视频" in response.text
    assert "生成素材包" in response.text
    assert "写入富化归档" in response.text
    assert "本地工作流预检" in response.text
    assert 'id="refresh-preflight-button"' in response.text
    assert 'id="preflight-summary"' in response.text
    assert 'id="preflight-list"' in response.text
    assert "大模型蒸馏" in response.text
    stylesheet = Path("app/static/app.css").read_text(encoding="utf-8")
    script = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "// Settings" in script
    assert "// Single Work" in script
    assert "// Creator Clone: import" in script
    assert "// Creator Clone: sample pool" in script
    assert "// Creator Clone: selection" in script
    assert "// Creator Clone: enrichment queue" in script
    assert "// Creator Clone: distillation" in script
    assert "// Creator Clone: export" in script
    assert "function firstUrlFromText" in script
    assert "function loadChromeHelperStatus" in script
    assert "function chromeHelperNextAction" in script
    assert "下一步：点击“插件辅助采集”" in script
    assert "一次性 token" in script
    assert "helper-readiness" in script
    assert "returned_data_scope" in script
    assert "用户本机 Chrome / 本机 IP" in script
    assert "function copyTextToClipboard" in script
    assert "function renderProfileCaptureAudit" in script
    assert "function renderProfileDecisionBoard" in script
    assert "素材池决策概览" in script
    assert "推荐选样" in script
    assert "建议样本组合" in script
    assert "选择推荐组合后仍可手动增删" in script
    assert "sample-strategy-list" in script
    assert ".sample-strategy-list" in stylesheet
    assert "样本结构" in script
    assert "代表样本线索" in script
    assert "profileDecisionBoard?.addEventListener" in script
    assert "本机辅助采集边界通过" in script
    assert "请求由用户本机 Chrome / 本机 IP 发起" in script
    assert "确认样本并富化" in script
    assert "capture-audit-verdict" in script
    assert "tab.label" in script
    assert "tab.title || tab.url" not in script
    assert "media_summary" in script
    assert "handoff_manifest.json" in script
    assert "profileHandoffFile" in script
    assert "HANDOFF_MANIFEST_MAX_BYTES" in script
    assert "2 * 1024 * 1024" in script
    assert "file.text()" in script
    assert "公开网站只接收净化后的元数据" in script
    assert "可富化素材" in script
    assert "图文/照片" in script
    assert "renderProfileSegmentsPreview" in script
    assert "highest_collect_samples" in script
    assert "高收藏样本" in script
    assert "最新样本" in script
    assert "选这组" in script
    assert "function applyProfilePresetSelection" in script
    assert "function renderProfileSelectionBasket" in script
    assert "function selectedSampleReason" in script
    assert "function renderProfileEnrichmentPlan" in script
    assert "function pollCreatorCloneDistillJob" in script
    assert "/api/jobs/creator-clone-distill" in script
    assert 'fetch("/api/creator-clone/distill"' not in script
    assert "function profileEvidenceCounts" in script
    assert "富化计划" in script
    assert "待补关键帧" in script
    assert "写入蒸馏输入" in script
    assert "data-profile-remove-selection" in script
    assert 'profileSelectionBasket?.addEventListener("click"' in script
    assert 'profileSegmentsPreview?.addEventListener("click"' in script
    assert "最近采集审计" in script
    assert "字段覆盖" in script
    assert "capture-field-coverage" in script
    assert "with_create_time" in script
    assert "with_any_visible_metric" in script
    assert "未读取 Cookie" in script
    assert "security-contract-card" in script
    assert "安全契约" in script
    assert "本次授权" in script
    assert "one_time_token_consumed" in script
    assert "只有页面按钮触发并消费一次性 token" in script
    assert "请求来源" in script
    assert "公开站接收" in script
    assert "不读 / 不传 / 不记" in script
    assert "回传范围" in script
    assert ".security-contract-card" in stylesheet
    assert ".capture-field-coverage" in stylesheet
    assert ".capture-field-grid" in stylesheet
    assert ".profile-selection-basket" in stylesheet
    assert ".selection-basket-item" in stylesheet
    assert ".selection-basket-item .profile-evidence-badges" in stylesheet
    assert ".enrichment-plan-metrics" in stylesheet
    assert ".enrichment-plan-steps" in stylesheet
    assert "/api/local-helper/chrome/status" in script
    assert "ready_for_profile_scan" in script
    assert "sample_set_id" in script
    assert "continueScan" in script
    assert "profileChromeLaunchCommand" in script
    assert 'button[type="submit"]' in script
    assert "event.submitter?.dataset.profileSource" in script
    assert 'activeSource === "manual"' in script
    assert 'activeSource === "handoff"' in script
    assert "/api/creator-clone/import-handoff" in script
    assert "/api/creator-clone/handoff-token" in script
    assert "handoff_manifest.json 不是合法 JSON" in script
    assert "HANDOFF_MANIFEST_INVALID" in script
    assert "function requestChromeScanToken" in script
    assert "function requireProfileChromeConfirmation" in script
    assert "function resetProfileChromeConfirmation" in script
    assert "function localChromeConfirmationPayload" in script
    assert "page_confirmed: Boolean(profileChromeConfirm?.checked)" in script
    assert "请先勾选本次辅助采集确认" in script
    assert "function openProfileInLocalChrome" in script
    assert "function launchLocalChrome" in script
    assert "/api/local-helper/chrome/launch" in script
    assert "/api/local-helper/chrome/clear-profile" not in script
    assert "function clearLocalChromeProfile" not in script
    assert "function loadPreflightStatus" in script
    assert "function renderPreflightStatus" in script
    assert "/api/settings/preflight" in script
    assert "preflight-action" in script
    assert "preflight-contract-summary" in script
    assert "preflightCopySnippets" in script
    assert "data-preflight-copy-index" in script
    assert 'preflightList?.addEventListener("click"' in script
    assert "复制命令" in script
    assert "contract_summary" in script
    assert "preflight-env-snippet" in script
    assert ".local-helper-confirmation" in stylesheet
    assert ".preflight-command-row" in stylesheet
    assert ".preflight-copy-button" in stylesheet
    assert "profileEvidenceStatus" in script
    assert "profileEvidenceFilter" in script
    assert "let profileSelectedKeys = new Set()" in script
    assert "selected_sample_ids: selectedProfileItems().map(profileItemKey)" in script
    assert "persistedSelected" in script
    assert "function filterProfileItems" in script
    assert "function visibleProfileItems" in script
    assert "profileSelectedKeys.has" in script
    assert "已全选当前列表" in script
    assert "function isProfileItemBuildable" in script
    assert '"collect_count"' in script
    assert "收藏样本" in script
    assert '["image", "text"].includes' in script
    assert "可富化" in script
    assert "图文/元数据样本会作为蒸馏参考" in script
    assert "这些样本不下载视频，可直接进入大模型蒸馏" in script
    assert "请先选择代表样本。视频样本会下载富化" in script
    assert "保存 ${selected.length} 条参考样本，不执行视频下载" in script
    assert "不执行视频下载，可直接进入大模型蒸馏" in script
    assert "不可富化" in script
    assert "超过当前上限" in script
    assert "disabledReason" in script
    assert "profileSelectedBuildButton.title" in script
    assert "将富化" in script
    assert "has_frames" in script
    assert "has_asr" in script
    assert "has_ocr" in script
    assert "function profileEvidenceBadges" in script
    assert 'label: "素材包"' in script
    assert 'label: "AI"' in script
    assert 'item.analysis_status === "success"' in script
    assert "${profileEvidenceBadges(item)}" in script
    assert "function profileEvidenceCoverageSummary" in script
    assert "function needsEnrichmentProfileItems" in script
    assert "function readyEvidenceProfileItems" in script
    assert "profileEvidenceScore" in script
    assert "function profileDistillReadiness" in script
    assert "function renderProfileDistillReadiness" in script
    assert "function confirmProfileDistillReadiness" in script
    assert "profileDistillReadinessStatus" in script
    assert "蒸馏准备度：建议先富化" in script
    assert "蒸馏准备度：可开始" in script
    assert "distill-readiness-matrix" in script
    assert "蒸馏证据矩阵" in script
    assert "后续可导入评论" in script
    assert "当前选样证据不足" in script
    assert "混合格式样本" in script
    assert "只能作为封面、标题或元数据参考" in script
    assert "确认样本并富化" in script
    assert "profileAutoDistill?.checked" in script
    assert "样本富化完成，正在调用大模型蒸馏创作者规则" in script
    assert "function renderProfileQueuePipeline" in script
    assert "profilePipelineStatusClass" in script
    assert "creatorCloneResultCard.scrollIntoView" in script
    assert "auto_analyze: false" in script
    assert "profileAutoAnalyze" not in script
    assert "样本证据完整度" in script
    assert "证据覆盖" in script
    assert "evidence-chip" in script
    assert "asr_status" in script
    assert "ocr_status" in script
    assert "provider_missing" in script
    assert "当前证据" in script
    assert "auto_asr: true" in script
    assert "auto_ocr: true" in script
    assert "样本富化队列完成" in script
    assert "当前连接的是项目专用调试 Chrome" in script
    assert "日常 Chrome 里已经打开的抖音主页不会被识别" in script
    assert "已打开目标主页。请等待页面加载" in script
    assert "已尝试启动调试 Chrome" in script
    assert "已尝试复制启动命令" in script
    assert "/api/local-helper/chrome/open-profile" in script
    assert "currentProfileTargetValue" in script
    assert "const rawProfileValue" in script
    assert "showProfileFallback" in script
    assert "async function prepareChromeProfileFallback" in script
    assert "公开扫描受限。请确认本机 Chrome 辅助采集边界后" in script
    assert "await prepareChromeProfileFallback(error)" in script
    assert "await scanProfileWithLocalChrome({fromPublicFallback: true})" not in script
    assert "profile-build-cases" in script
    assert "pipeline_summary" in script
    assert "function renderProfileQueueSummary" in script
    assert "ASR 未配置" in script
    assert "OCR 未配置" in script
    assert "参考样本已保留" in script
    assert "reference_only_count" in script
    assert "UNSUPPORTED_PROFILE_ITEM" in script
    assert "aweme_id: awemeId" in script
    assert "sample_id: item.sample_id" in script
    assert "case_id: item.case_id" in script
    assert '|| "参考样本"' in script
    assert "profile_metadata" in script
    assert "账号资料" in script
    assert "document.body.dataset.profileBuildMaxItems" in script
    assert "PROFILE_BUILD_MAX_ITEMS" in script
    assert "document.body.dataset.creatorCloneMaxDistillSamples" in script
    assert "CREATOR_CLONE_MAX_DISTILL_SAMPLES" in script
    assert "蒸馏样本超过当前上限" in script
    assert "将蒸馏" in script
    assert "renderCreatorCloneEvidenceOverview" in script
    assert "function renderCreatorCloneActionSummary" in script
    assert "可执行摘要" in script
    assert "核心定位" in script
    assert "可复用公式" in script
    assert "不要照搬" in script
    assert "creatorCloneOverviewFromSet" in script
    assert "创作者克隆证据完整度" in script
    assert "完整证据" in script
    assert "仅元数据" in script
    assert "LLM 未配置" in script
    assert "renderCreatorCloneEvidenceOverview(overview)" in script
    assert ".creator-clone-evidence-strip" in stylesheet
    assert ".creator-clone-action-summary" in stylesheet
    assert ".creator-clone-action-grid" in stylesheet
    assert "当前自用版最多一次富化" in script
    assert "可下载视频超过当前富化上限" in script
    assert "选中样本超过当前蒸馏上限" in script
    assert ".profile-source-card" in stylesheet
    assert ".profile-selection-stage" in stylesheet
    assert "#fbf9ff" in stylesheet
    assert ".local-helper-status" in stylesheet
    assert ".helper-readiness" in stylesheet
    assert ".local-helper-status ul" in stylesheet
    assert ".capture-audit-verdict" in stylesheet
    assert ".summary-actions" in stylesheet
    assert ".handoff-manifest-callout" in stylesheet
    assert ".text-button" in stylesheet
    assert ".local-helper-actions" not in stylesheet
    assert ".preflight-item" in stylesheet
    assert ".preflight-status" in stylesheet
    assert ".preflight-contract-summary" in stylesheet
    assert ".preflight-env-snippet" in stylesheet
    assert ".capture-audit-card" in stylesheet
    assert ".profile-decision-board" in stylesheet
    assert ".profile-decision-grid" in stylesheet
    assert ".profile-decision-card.featured" in stylesheet
    assert ".profile-queue-item" in stylesheet
    assert ".profile-queue-summary-grid" in stylesheet
    assert ".profile-queue-next-actions" in stylesheet
    assert ".profile-pipeline-strip" in stylesheet
    assert ".profile-queue-pipeline" in stylesheet
    assert ".distill-readiness-matrix" in stylesheet
    assert ".distill-readiness-actions" in stylesheet
    assert ".profile-evidence-badges" in stylesheet
    assert ".evidence-chip.ready" in stylesheet
    assert ".evidence-chip.checked" in stylesheet
    assert ".profile-media-type.image" in stylesheet
    assert ".profile-segments-preview" in stylesheet
    assert ".profile-segment-grid" in stylesheet
    assert ".profile-segment-column-head" in stylesheet
    assert ".profile-evidence-status.warning" in stylesheet
    assert "图文/照片" in script
    assert "图文/元数据样本会保存为蒸馏参考" in script
    assert "API 与解析设置" in response.text
    assert 'id="test-llm-button"' in response.text
    assert "解析结果" in response.text
    assert "关键帧总览" in response.text
    assert "AI 拆解报告" in response.text
    assert "本地拆解底稿" not in response.text
    assert 'id="home-category-guess"' not in response.text
    assert 'id="home-template-preview"' not in response.text
    assert 'data-home-route="single"' in response.text
    assert 'data-home-route="profile"' in response.text
    assert "主页扫描</button>" not in response.text
    assert 'data-home-route="cases"' not in response.text
    assert 'data-home-route="settings"' not in response.text
    assert 'id="settings-modal"' in response.text
    assert 'id="download-selected-button"' not in response.text
    assert "下载并生成素材包" not in response.text


def test_calibration_page_uses_versioned_static_assets() -> None:
    response = client.get("/calibration")
    assert response.status_code == 200
    assert "校准样本库" in response.text
    assert "/static/calibration.js?v=" in response.text
    assert "/static/app.css?v=" in response.text


def test_readme_documents_main_workflow_before_advanced_quality_loop() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    env_example = Path(".env.example").read_text(encoding="utf-8")

    assert "没有 API Key 也能生成" in readme
    assert "## 业务模块规划" in readme
    assert "单作品解析：当前可用" in readme
    assert "创作者克隆实验室" in readme
    assert "公开主页扫描是上线主入口" in readme
    assert "公开网站 / 本机助手模式的目标边界" in readme
    assert "`handoff_manifest.json` 必须带有安全契约声明" in readme
    assert "公开站 / 本机助手边界" in readme
    assert "首页主流程只暴露“插件辅助采集”" in readme
    assert "状态检查只返回匿名标签页数量和就绪状态" in readme
    assert "真正读取当前 Chrome 页面 DOM 中可见作品列表，必须走一次性 token + 页面确认后的“插件辅助采集”" in readme
    assert "扫描主页和清理辅助 profile 除了 token 之外还需要页面确认" in readme
    assert "多作品粘贴是当前账号级分析的稳定入口" in readme
    assert "作品池队列默认一次最多处理 10 条" in readme
    assert "yt-dlp 用于后续公开视频解析 / 下载能力" in readme
    requirements = Path("requirements.txt").read_text(encoding="utf-8")
    assert "websocket-client" in requirements
    assert "yt-dlp" in requirements
    assert "PROFILE_BUILD_MAX_ITEMS" in readme
    assert "PROFILE_BUILD_MAX_ITEMS=10" in env_example
    assert "默认 `LLM_PROVIDER=disabled` 时，系统不会自动调用任何大模型" in readme
    assert "单作品主流程已收敛为一个“解析”按钮：解析候选 → 下载视频 → 自动生成素材包；配置大模型后可自动拆解。" in readme
    assert "如果浏览器能访问 API 但页面“测试连接”失败，请检查本机代理" in readme
    assert "自动调用大模型" not in readme
    assert "按设置下载并自动拆解" not in readme
    assert "## 进阶用法：单条作品拆解质量闭环" in readme
    assert "实验 / 高级能力" in readme
    assert "AI 自检" in readme
    assert "人工质量验收" in readme
    assert "重新 AI 自动拆解" in readme
    assert "保存校准样本" in readme
    assert "校准样本库" in readme
    assert "复制对比报告" in readme
    assert "quality_acceptance.json" in readme
    assert "quality_calibration_record.json" in readme
    assert "rerun_plan.json" in readme
    assert "rerun_plan.md" in readme
    assert "quality_calibration_index.json" in readme
    assert "needs_rerun" in readme
    assert "accepted" in readme
    assert "GET /calibration" in readme
    assert "POST /api/cases/{case_id}/quality-acceptance" in readme
    assert "GET /api/cases/quality-calibration/report" in readme


def test_gitignore_excludes_local_capture_and_clone_runtime_outputs() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "outputs/creator_clones/*" in gitignore
    assert "!outputs/creator_clones/.gitkeep" in gitignore
    assert "outputs/local_chrome_profile/*" in gitignore
    assert "--remote-allow-origins=http://127.0.0.1:8765,http://127.0.0.1:9222" in readme
    assert "--no-first-run" in readme
    assert "--no-default-browser-check" in readme
    assert "POST /api/local-helper/chrome/clear-profile" in readme
    assert "只清理专用 profile，不影响普通 Chrome 用户资料" in readme
    assert "POST /api/local-helper/chrome/clear-profile" in readme
    assert "samples/" in gitignore


def test_dev_server_script_binds_loopback_only() -> None:
    script = Path("scripts/dev_server.py").read_text(encoding="utf-8")

    assert 'host="127.0.0.1"' in script
    assert "port=8765" in script
    assert "reload=True" in script
    assert 'reload_dirs=["app"]' in script
    assert "0.0.0.0" not in script


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


def test_worksheet_quality_review_scores_complete_manual_notes() -> None:
    analysis_input = {
        "content_category": "beauty_cos",
        "content_category_label": "美拍 / COS / 颜值向",
        "analysis_context": {"category_id": "beauty_cos", "label": "美拍 / COS / 颜值向"},
    }
    worksheet = normalize_worksheet(
        "case_manual",
        analysis_input,
        {
            "summary": "这条视频最值得学习的是前3秒用近景人物和动作变化锁住注意力。",
            "sections": {
                "hook": {
                    "fields": {
                        "first_impression": {"value": "0s 直接看到人物近景和强服装亮点。"},
                        "stop_reason": {"value": "停留理由是妆造反差、眼神和快速动作。"},
                        "first_3s_notes": {"value": "0s 人物出现；1s 抬手；2s 字幕强化人设。"},
                    }
                },
                "structure": {
                    "fields": {
                        "rhythm_notes": {"value": "前半段动作快，后半段停顿给观众看清造型。"},
                        "subtitle_notes": {"value": "标题把角色气质转成点击理由。"},
                    }
                },
                "category": {
                    "fields": {
                        "content_ratio_notes": {"value": "视觉吸引约45%，人物人设约25%，动作节奏约15%。"},
                        "reusable_points": {"value": "可借鉴近景开头、服装亮点、动作节奏和标题结构。"},
                        "risk_or_mismatch": {"value": "不要照搬尺度和原动作，可替换成更符合账号人设的姿态。"},
                    }
                },
                "remake": {
                    "fields": {
                        "remake_angle": {"value": "改成原创角色出场，用甜美人设替代原视频表达。"},
                        "shot_script": {"value": "0-1s 近景看镜头；1-2s 抬手转身；2-3s 字幕给角色设定。"},
                        "publish_package": {"value": "标题、正文、标签和置顶评论都围绕角色反差。"},
                    }
                },
            },
        },
    )

    review = worksheet_quality_review(worksheet)

    assert review["score"] == 100
    assert review["level"] == "complete"
    assert not review["gaps"]
    assert worksheet["review"]["level"] == "complete"
    assert worksheet["sections"]["hook"]["fields"]["first_impression"]["hint"]


def test_llm_settings_returns_unconfigured_status_without_secret(monkeypatch) -> None:
    monkeypatch.setattr("app.services.llm_settings.settings.llm_provider", "disabled")
    monkeypatch.setattr("app.services.llm_settings.settings.llm_api_key", "")
    monkeypatch.setattr("app.services.llm_settings.settings.llm_model", "")

    response = client.get("/api/settings/llm")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["llm"]["configured"] is False
    assert payload["llm"]["has_api_key"] is False
    assert "LLM_PROVIDER" in payload["llm"]["status_message"]


def test_llm_settings_masks_configured_api_key(monkeypatch) -> None:
    secret = "sk-test-secret-abcd"
    monkeypatch.setattr("app.services.llm_settings.settings.llm_provider", "openai_compatible")
    monkeypatch.setattr("app.services.llm_settings.settings.llm_api_base", "https://api.example.test/v1")
    monkeypatch.setattr("app.services.llm_settings.settings.llm_api_key", secret)
    monkeypatch.setattr("app.services.llm_settings.settings.llm_model", "vision-model")

    response = client.get("/api/settings/llm")

    assert response.status_code == 200
    payload = response.json()
    assert payload["llm"]["configured"] is True
    assert payload["llm"]["has_api_key"] is True
    assert payload["llm"]["masked_api_key"] == "sk-****abcd"
    assert secret not in json.dumps(payload, ensure_ascii=False)


def test_llm_settings_accepts_openai_responses_provider(monkeypatch) -> None:
    monkeypatch.setattr("app.services.llm_settings.settings.llm_provider", "openai_responses")
    monkeypatch.setattr("app.services.llm_settings.settings.llm_api_base", "https://api.openai.com/v1")
    monkeypatch.setattr("app.services.llm_settings.settings.llm_api_key", "sk-test-responses")
    monkeypatch.setattr("app.services.llm_settings.settings.llm_model", "gpt-5.5")

    response = client.get("/api/settings/llm")

    assert response.status_code == 200
    payload = response.json()
    assert payload["llm"]["configured"] is True
    assert payload["llm"]["provider"] == "openai_responses"
    assert payload["llm"]["model"] == "gpt-5.5"


def test_llm_settings_accepts_anthropic_provider(monkeypatch) -> None:
    monkeypatch.setattr("app.services.llm_settings.settings.llm_provider", "anthropic_compatible")
    monkeypatch.setattr("app.services.llm_settings.settings.llm_api_base", "https://www.wintoken.dev/v1")
    monkeypatch.setattr("app.services.llm_settings.settings.llm_api_key", "sk-test-anthropic")
    monkeypatch.setattr("app.services.llm_settings.settings.llm_model", "claude-fable-5")

    response = client.get("/api/settings/llm")

    assert response.status_code == 200
    payload = response.json()
    assert payload["llm"]["configured"] is True
    assert payload["llm"]["provider"] == "anthropic_compatible"
    assert payload["llm"]["model"] == "claude-fable-5"


def test_settings_preflight_reports_local_workflow_checks(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.tool_preflight.chrome_helper_diagnostics",
        lambda: {
            "chrome_available": True,
            "ready_for_profile_scan": False,
            "status_message": "已连接 Chrome DevTools，但没有找到抖音主页标签页。",
            "launch_hint": "",
        },
    )
    monkeypatch.setattr("app.services.tool_preflight.settings.asr_provider", "disabled")
    monkeypatch.setattr("app.services.tool_preflight.settings.ocr_provider", "disabled")
    monkeypatch.setattr("app.services.llm_settings.settings.llm_provider", "disabled")
    monkeypatch.setattr("app.services.llm_settings.settings.llm_api_key", "")
    monkeypatch.setattr("app.services.llm_settings.settings.llm_model", "")

    response = client.get("/api/settings/preflight")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    checks = {item["id"]: item for item in payload["preflight"]["checks"]}
    assert checks["chrome"]["status"] == "partial"
    assert "打开目标抖音主页" in checks["chrome"]["action_hint"]
    assert checks["websocket"]["label"] == "Chrome DevTools websocket"
    assert "websocket" in checks["websocket"]["message"]
    assert checks["yt-dlp"]["label"] == "yt-dlp"
    assert checks["yt-dlp"]["status"] in {"ready", "missing"}
    assert checks["ffmpeg"]["label"] == "ffmpeg"
    assert checks["ffprobe"]["label"] == "ffprobe"
    assert checks["asr"]["status"] == "disabled"
    assert checks["asr"]["env_snippet"].startswith("ASR_PROVIDER=auto")
    assert "ASR_PROVIDER=auto" in checks["asr"]["action_hint"]
    assert "首次运行可能下载 Whisper 模型" in checks["asr"]["action_hint"]
    assert checks["ocr"]["status"] == "disabled"
    assert checks["ocr"]["env_snippet"].startswith("OCR_PROVIDER=auto")
    assert "OCR_PROVIDER=auto" in checks["ocr"]["action_hint"]
    assert checks["llm"]["status"] == "disabled"
    assert checks["local_access_guard"]["status"] == "ready"
    assert "Origin" in checks["local_access_guard"]["message"]
    assert checks["dev_server_binding"]["status"] == "ready"
    assert "127.0.0.1" in checks["dev_server_binding"]["message"]
    assert "不要用 0.0.0.0" in checks["dev_server_binding"]["action_hint"]
    assert checks["local_helper_confirmation"]["status"] == "ready"
    assert "一次性 token" in checks["local_helper_confirmation"]["message"]
    assert "清理辅助 profile" in checks["local_helper_confirmation"]["message"]
    assert checks["public_bridge_boundary"]["status"] == "ready"
    assert "公开网站只接收净化后的账号素材清单" in checks["public_bridge_boundary"]["message"]
    assert "用户本机 Chrome / 本机 IP" in " ".join(checks["public_bridge_boundary"]["contract_summary"])
    assert "不读取、不返回、不记录 Cookie" in " ".join(checks["public_bridge_boundary"]["contract_summary"])
    assert checks["handoff_bridge"]["status"] == "ready"
    assert "handoff_manifest" in checks["handoff_bridge"]["message"]
    assert "一次性 token" in checks["handoff_bridge"]["message"]
    assert "公开网站只接收净化后的作品列表和元数据" in checks["handoff_bridge"]["message"]
    assert checks["runtime_outputs_gitignore"]["status"] == "ready"
    assert "sk-" not in json.dumps(payload, ensure_ascii=False)


def test_settings_preflight_surfaces_chrome_launch_command_when_missing(monkeypatch) -> None:
    launch_hint = "/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222"
    monkeypatch.setattr(
        "app.services.tool_preflight.chrome_helper_diagnostics",
        lambda: {
            "chrome_available": False,
            "ready_for_profile_scan": False,
            "status_message": "未检测到 Chrome DevTools。",
            "launch_hint": launch_hint,
        },
    )

    response = client.get("/api/settings/preflight")

    assert response.status_code == 200
    checks = {item["id"]: item for item in response.json()["preflight"]["checks"]}
    assert checks["chrome"]["status"] == "missing"
    assert checks["chrome"]["launch_hint"] == launch_hint
    assert checks["chrome"]["env_snippet"] == launch_hint
    assert "复制下方命令" in checks["chrome"]["action_hint"]


def test_settings_preflight_accepts_yt_dlp_python_module_without_binary(monkeypatch) -> None:
    import app.services.tool_preflight as tool_preflight

    real_find_spec = tool_preflight.importlib.util.find_spec
    monkeypatch.setattr(
        "app.services.tool_preflight.chrome_helper_diagnostics",
        lambda: {
            "chrome_available": True,
            "ready_for_profile_scan": True,
            "status_message": "已检测到可用的抖音主页标签页。",
            "launch_hint": "",
        },
    )
    monkeypatch.setattr("app.services.tool_preflight.shutil.which", lambda name: None if name == "yt-dlp" else f"/usr/bin/{name}")

    def fake_find_spec(name):
        if name == "yt_dlp":
            return object()
        return real_find_spec(name)

    monkeypatch.setattr("app.services.tool_preflight.importlib.util.find_spec", fake_find_spec)

    response = client.get("/api/settings/preflight")

    assert response.status_code == 200
    checks = {item["id"]: item for item in response.json()["preflight"]["checks"]}
    assert checks["yt-dlp"]["status"] == "ready"
    assert checks["yt-dlp"]["available"] is True
    assert checks["yt-dlp"]["module"] == "yt_dlp"
    assert "-m yt_dlp" in checks["yt-dlp"]["run_hint"]
    assert "命令行入口不在 PATH" in checks["yt-dlp"]["message"]


def test_parse_json_text_extracts_object_from_extra_model_text() -> None:
    payload = parse_json_text(
        '下面是拆解结果：\n{"summary":"可用","nested":{"text":"这里有 { 大括号 } 字符"},"items":[1,2]}\n请查收。'
    )

    assert payload["summary"] == "可用"
    assert payload["nested"]["text"] == "这里有 { 大括号 } 字符"
    assert payload["items"] == [1, 2]


def test_parse_json_text_rejects_non_object_json() -> None:
    with pytest.raises(AppError) as error:
        parse_json_text("说明文字 [1, 2, 3]")

    assert error.value.code == ErrorCode.LLM_RESPONSE_INVALID


def test_llm_connection_test_uses_mock_provider(monkeypatch) -> None:
    class FakeProvider:
        def analyze(self, prompt, image_paths):
            assert "pong" in prompt
            assert image_paths == []
            return {"ok": True, "message": "pong"}

    monkeypatch.setattr("app.services.llm_settings.settings.llm_provider", "openai_compatible")
    monkeypatch.setattr("app.services.llm_settings.settings.llm_api_base", "https://api.example.test/v1")
    monkeypatch.setattr("app.services.llm_settings.settings.llm_api_key", "sk-mocked-secret")
    monkeypatch.setattr("app.services.llm_settings.settings.llm_model", "vision-model")
    monkeypatch.setattr("app.services.llm_settings.get_llm_provider", lambda: FakeProvider())

    response = client.post("/api/settings/llm/test")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["test"]["message"] == "pong"
    assert "sk-mocked-secret" not in json.dumps(payload, ensure_ascii=False)


def test_openai_compatible_provider_requests_json_object(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200
        text = "{\"choices\": []}"

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": "{\"ok\": true, \"message\": \"pong\"}"
                        }
                    }
                ]
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            assert url == "https://www.wintoken.dev/v1/chat/completions"
            assert json["response_format"] == {"type": "json_object"}
            assert json["max_tokens"] == 1200
            return FakeResponse()

    monkeypatch.setattr("app.services.llm_provider.httpx.Client", FakeClient)
    result = OpenAICompatibleProvider(
        api_base="https://www.wintoken.dev/v1",
        api_key="sk-test",
        model="gpt-5.4-high",
    ).analyze("ping", [])

    assert result == {"ok": True, "message": "pong"}


def test_openai_compatible_provider_parses_list_content(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200
        text = "{\"choices\": []}"

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"type": "text", "text": "```json\n{\"ok\": true}\n```"}
                            ]
                        }
                    }
                ]
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            return FakeResponse()

    monkeypatch.setattr("app.services.llm_provider.httpx.Client", FakeClient)
    result = OpenAICompatibleProvider(api_key="sk-test", model="gpt-5.4-high").analyze("ping", [])

    assert result == {"ok": True}


def test_openai_compatible_provider_sends_optimized_image_payload(monkeypatch, tmp_path: Path) -> None:
    image_path = tmp_path / "contact_sheet.png"
    Image.new("RGB", (2400, 1200), color=(220, 120, 160)).save(image_path, compress_level=0)
    original_size = image_path.stat().st_size

    class FakeResponse:
        status_code = 200
        text = "{\"choices\": []}"

        def json(self):
            return {"choices": [{"message": {"content": "{\"ok\": true}"}}]}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            image_url = json["messages"][1]["content"][1]["image_url"]["url"]
            assert image_url.startswith("data:image/jpeg;base64,")
            encoded = image_url.split(",", 1)[1]
            assert len(base64.b64decode(encoded)) < original_size
            return FakeResponse()

    monkeypatch.setattr("app.services.llm_provider.httpx.Client", FakeClient)
    result = OpenAICompatibleProvider(api_key="sk-test", model="gpt-5.4-high").analyze("ping", [image_path])

    assert result == {"ok": True}


def test_openai_responses_provider_parses_output_text(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"output_text": "{\"ok\": true, \"message\": \"pong\"}"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.payload = None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            assert url == "https://api.openai.com/v1/responses"
            assert headers["Authorization"] == "Bearer sk-test"
            assert json["model"] == "gpt-5.5"
            assert json["input"][0]["content"][0]["type"] == "input_text"
            assert json["max_output_tokens"] == 1200
            return FakeResponse()

    monkeypatch.setattr("app.services.llm_provider.httpx.Client", FakeClient)
    result = OpenAIResponsesProvider(
        api_base="https://api.openai.com/v1",
        api_key="sk-test",
        model="gpt-5.5",
    ).analyze("ping", [])

    assert result == {"ok": True, "message": "pong"}


def test_openai_responses_provider_parses_nested_output(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": "```json\n{\"ok\": true}\n```"}
                        ],
                    }
                ]
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            return FakeResponse()

    monkeypatch.setattr("app.services.llm_provider.httpx.Client", FakeClient)
    result = OpenAIResponsesProvider(
        api_base="https://api.openai.com/v1",
        api_key="sk-test",
        model="gpt-5.5",
    ).analyze("ping", [])

    assert result == {"ok": True}


def test_anthropic_compatible_provider_uses_messages_api(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "{\"ok\": true, \"message\": \"pong\"}",
                    }
                ]
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            assert url == "https://www.wintoken.dev/v1/messages"
            assert headers["x-api-key"] == "sk-test"
            assert headers["anthropic-version"] == "2023-06-01"
            assert json["model"] == "claude-fable-5"
            assert json["messages"][0]["content"][0]["type"] == "text"
            assert json["max_tokens"] == 1200
            return FakeResponse()

    monkeypatch.setattr("app.services.llm_provider.httpx.Client", FakeClient)
    result = AnthropicCompatibleProvider(
        api_base="https://www.wintoken.dev/v1",
        api_key="sk-test",
        model="claude-fable-5",
    ).analyze("ping", [])

    assert result == {"ok": True, "message": "pong"}


def test_anthropic_compatible_provider_accepts_root_base_url(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"content": [{"type": "text", "text": "{\"ok\": true}"}]}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            assert url == "https://www.wintoken.dev/v1/messages"
            return FakeResponse()

    monkeypatch.setattr("app.services.llm_provider.httpx.Client", FakeClient)
    result = AnthropicCompatibleProvider(
        api_base="https://www.wintoken.dev",
        api_key="sk-test",
        model="claude-fable-5",
    ).analyze("ping", [])

    assert result == {"ok": True}


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
    assert analysis_input["content_category_guess"]["category_id"] == "generic"
    assert analysis_input["content_category_guess"]["confidence"] == "low"
    assert analysis_input["analysis_lens"]
    assert analysis_input["key_questions"]
    assert analysis_input["content_ratio"]
    assert "前3秒钩子" in analysis_input["analysis_focus"]

    prompt = (case_dir / "prompt.md").read_text(encoding="utf-8")
    assert "# 爆款案例拆解 Prompt" in prompt
    assert "内容类型：通用短视频" in prompt
    assert "## 11. 分镜表" in prompt
    assert "## 7. 富化数据拆解" in prompt

    worksheet = json.loads((case_dir / "worksheet.json").read_text(encoding="utf-8"))
    assert worksheet["case_id"] == case["case_id"]
    assert worksheet["content_category"] == "generic"
    assert "hook" in worksheet["sections"]
    assert worksheet["sections"]["hook"]["fields"]["first_impression"]["hint"]
    assert worksheet["review"]["level"] == "empty"
    analysis_brief = (case_dir / "analysis_brief.md").read_text(encoding="utf-8")
    assert "# 短视频案例分析工作表" in analysis_brief
    assert "## 我的拆解" in analysis_brief

    detail_response = client.get(f"/cases/{case['case_id']}")
    assert detail_response.status_code == 200
    assert "短视频拆解报告" in detail_response.text
    assert "primary-workflow-summary" in detail_response.text
    assert "完整分析" in detail_response.text
    assert "高级 / 后台材料" in detail_response.text
    assert "素材包文件" in detail_response.text
    assert "人工质量验收" in detail_response.text
    assert "高级富化" in detail_response.text
    assert "校准样本" in detail_response.text
    assert "case-diagnosis-summary" in detail_response.text
    assert "auto-analysis-cards" in detail_response.text
    assert "readiness-summary" in detail_response.text
    assert "case_detail.js?v=" in detail_response.text

    api_response = client.get(f"/api/cases/{case['case_id']}")
    assert api_response.status_code == 200
    api_payload = api_response.json()
    assert api_payload["ok"] is True
    assert api_payload["case"]["analysis_input"]["case_id"] == case["case_id"]
    assert api_payload["case"]["analysis_input"]["content_category_guess"]["source"] == "local_rules"
    assert api_payload["case"]["analysis_profiles"]
    assert api_payload["case"]["artifact_urls"]["keyframes"]
    assert api_payload["case"]["artifact_urls"]["analysis_input"].endswith("/analysis-input")
    assert api_payload["case"]["artifact_urls"]["rerun_plan"].endswith("/rerun-plan")
    assert api_payload["case"]["artifact_urls"]["rerun_plan_markdown"].endswith("/rerun-plan.md")
    assert api_payload["case"]["artifact_descriptions"]["analysis_input.json"].startswith("交给大模型")
    assert api_payload["case"]["artifact_descriptions"]["quality_acceptance.json"].startswith("人工质量验收")
    assert api_payload["case"]["artifact_descriptions"]["quality_calibration_record.json"].startswith("单条作品校准样本")
    assert api_payload["case"]["artifact_descriptions"]["rerun_plan.json"].startswith("下一轮拆解任务单")
    assert api_payload["case"]["artifact_descriptions"]["rerun_plan.md"].startswith("下一轮拆解任务单")
    primary = api_payload["case"]["primary_workflow"]
    assert primary["artifact_ready"] is True
    assert primary["analysis_status"] in {"not_configured", "not_analyzed"}
    assert primary["next_action"] in {"copy_prompt", "run_ai_analysis"}
    assert primary["next_action_label"]
    assert isinstance(primary["llm_configured"], bool)
    quality_acceptance_path = Path(api_payload["case"]["paths"]["quality_acceptance"])
    assert quality_acceptance_path.name == "quality_acceptance.json"
    assert quality_acceptance_path.is_file()
    assert api_payload["case"]["paths"]["quality_calibration_record"].endswith("quality_calibration_record.json")
    rerun_plan_path = Path(api_payload["case"]["paths"]["rerun_plan"])
    assert rerun_plan_path.name == "rerun_plan.json"
    assert rerun_plan_path.is_file()
    rerun_plan_markdown_path = Path(api_payload["case"]["paths"]["rerun_plan_markdown"])
    assert rerun_plan_markdown_path.name == "rerun_plan.md"
    assert rerun_plan_markdown_path.is_file()
    initial_rerun_plan = api_payload["case"]["rerun_plan"]
    assert initial_rerun_plan["case_id"] == case["case_id"]
    assert initial_rerun_plan["status"] == "needs_ai_analysis"
    assert initial_rerun_plan["diagnosis"]["status"] == "needs_ai_analysis"
    assert initial_rerun_plan["execution_gate"]["mode"] == "run_first_analysis"
    assert initial_rerun_plan["execution_gate"]["can_rerun_now"] is True
    assert initial_rerun_plan["execution_gate"]["next_best_action"]["target"] == "#run-auto-analysis-button"
    assert initial_rerun_plan["evidence_plan"]["critical_readiness_gaps"]
    quality_acceptance = api_payload["case"]["quality_acceptance"]
    assert quality_acceptance["verdict"] == "pending"
    assert quality_acceptance["checks"]["summary_matches_video"] == ""
    assert quality_acceptance["quality_snapshot"]["score"] == 0
    assert api_payload["case"]["manual_review_context"]["rerun_strategy"]["active"] is False
    calibration = api_payload["case"]["quality_calibration"]
    assert calibration["status"] == "needs_ai_analysis"
    assert calibration["ai_quality"]["has_report"] is False
    assert calibration["human_acceptance"]["verdict"] == "pending"
    assert any(action["target"] == "#run-auto-analysis-button" for action in calibration["next_actions"])
    assert api_payload["case"]["llm_settings"]["configured"] in {True, False}
    readiness = api_payload["case"]["analysis_readiness"]
    assert readiness["score"] >= 40
    assert readiness["label"] == "基础素材可用"
    assert readiness["checks"][0]["id"] == "base_package"
    assert readiness["checks"][0]["ready"] is True
    assert any(gap["id"] == "speech_asr" for gap in readiness["improvement_gaps"])
    assert any("ASR" in action for action in readiness["next_actions"])
    diagnosis = api_payload["case"]["case_diagnosis"]
    assert diagnosis["status"] == "needs_ai_analysis"
    assert diagnosis["score"]["quality"] == 0
    assert diagnosis["score"]["readiness"] == readiness["score"]
    assert diagnosis["primary_actions"][0]["target"] == "#run-auto-analysis-button"
    assert diagnosis["primary_actions"][0]["mode"] == "click"
    assert [action["label"] for action in diagnosis["primary_actions"]].count("开始 AI 拆解") == 1
    asr_gap = next(gap for gap in readiness["improvement_gaps"] if gap["id"] == "speech_asr")
    assert asr_gap["action_label"] == "运行 ASR"
    assert asr_gap["action_target"] == "#asr-placeholder-button"
    assert readiness["next_action_items"][0]["target"] == "#asr-placeholder-button"
    assert api_payload["case"]["worksheet"]["sections"]["hook"]
    assert api_payload["case"]["worksheet_review"]["level"] == "empty"
    assert any(gap["id"] == "summary" for gap in api_payload["case"]["worksheet_review"]["gaps"])
    assert "# 短视频案例分析工作表" in api_payload["case"]["analysis_brief"]
    assert "# 爆款案例拆解 Prompt" in api_payload["case"]["prompt"]

    analysis_input_download = client.get(api_payload["case"]["artifact_urls"]["analysis_input"])
    assert analysis_input_download.status_code == 200
    assert analysis_input_download.json()["case_id"] == case["case_id"]
    rerun_plan_download = client.get(api_payload["case"]["artifact_urls"]["rerun_plan"])
    assert rerun_plan_download.status_code == 200
    assert rerun_plan_download.json()["case_id"] == case["case_id"]
    rerun_plan_markdown_download = client.get(api_payload["case"]["artifact_urls"]["rerun_plan_markdown"])
    assert rerun_plan_markdown_download.status_code == 200
    assert "# 下一轮拆解任务单" in rerun_plan_markdown_download.text
    assert "## 1. 执行闸门" in rerun_plan_markdown_download.text

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

    quality_response = client.post(
        f"/api/cases/{case['case_id']}/quality-acceptance",
        json={
            "acceptance": {
                "verdict": "needs_fix",
                "score": "72",
                "reviewer": "xingkong",
                "summary": "钩子判断基本正确，但分镜需要修正。",
                "checks": {
                    "summary_matches_video": "pass",
                    "evidence_is_sufficient": "needs_fix",
                    "copyable_points_are_useful": "pass",
                    "shot_table_is_actionable": "needs_fix",
                    "publish_package_is_usable": "pass",
                },
                "notes": "评论证据还不够。",
                "next_actions": "补评论后重跑。",
            }
        },
    )
    assert quality_response.status_code == 200
    quality_payload = quality_response.json()
    assert quality_payload["ok"] is True
    saved_acceptance = quality_payload["case"]["quality_acceptance"]
    assert saved_acceptance["verdict"] == "needs_fix"
    assert saved_acceptance["score"] == "72"
    assert saved_acceptance["reviewer"] == "xingkong"
    assert saved_acceptance["checks"]["evidence_is_sufficient"] == "needs_fix"
    assert saved_acceptance["checks"]["shot_table_is_actionable"] == "needs_fix"
    assert saved_acceptance["notes"] == "评论证据还不够。"
    saved_calibration = quality_payload["case"]["quality_calibration"]
    assert saved_calibration["status"] == "needs_ai_analysis"
    assert saved_calibration["human_acceptance"]["blocker_count"] == 2
    assert any(blocker["id"] == "evidence_is_sufficient" for blocker in saved_calibration["human_acceptance"]["blockers"])
    assert any(
        item["id"] == "import_comments_before_rerun"
        for item in saved_calibration["recommendations"]
    )
    pending_comment_recommendation = next(
        item for item in saved_calibration["recommendations"] if item["id"] == "import_comments_before_rerun"
    )
    assert pending_comment_recommendation["action_label"] == "导入评论"
    assert pending_comment_recommendation["action_target"] == "#comments-import-text"
    saved_strategy = quality_payload["case"]["manual_review_context"]["rerun_strategy"]
    assert saved_strategy["active"] is True
    assert saved_strategy["priority"] == "high"
    assert saved_strategy["evidence_summary"]["missing"] >= 1
    assert any(item["id"] == "shot_table_is_actionable" for item in saved_strategy["fix_targets"])
    assert any(item["id"] == "comments" and item["status"] == "missing" for item in saved_strategy["required_evidence"])
    comment_evidence_action = next(item for item in saved_strategy["required_evidence"] if item["id"] == "comments")
    assert comment_evidence_action["action_label"] == "导入评论"
    assert comment_evidence_action["target"] == "#comments-import-text"
    assert comment_evidence_action["mode"] == "focus"
    saved_rerun_plan = quality_payload["case"]["rerun_plan"]
    assert saved_rerun_plan["status"] == "missing_required_evidence"
    assert saved_rerun_plan["execution_gate"]["mode"] == "collect_evidence_first"
    assert saved_rerun_plan["execution_gate"]["can_rerun_now"] is False
    assert any("评论摘要" in reason for reason in saved_rerun_plan["execution_gate"]["blocking_reasons"])
    assert saved_rerun_plan["rerun_strategy"]["active"] is True
    assert saved_rerun_plan["rerun_strategy"]["priority"] == "high"
    assert any(item["id"] == "comments" for item in saved_rerun_plan["evidence_plan"]["missing_evidence"])
    assert any(action["target"] == "#comments-import-text" for action in saved_rerun_plan["recommended_actions"])
    persisted_rerun_plan = json.loads(rerun_plan_path.read_text(encoding="utf-8"))
    assert persisted_rerun_plan["status"] == "missing_required_evidence"
    persisted_rerun_plan_markdown = rerun_plan_markdown_path.read_text(encoding="utf-8")
    assert "是否建议立即重跑：否" in persisted_rerun_plan_markdown
    assert "评论摘要" in persisted_rerun_plan_markdown
    persisted_acceptance = json.loads(quality_acceptance_path.read_text(encoding="utf-8"))
    assert persisted_acceptance["summary"] == "钩子判断基本正确，但分镜需要修正。"
    assert persisted_acceptance["next_actions"] == "补评论后重跑。"

    class FakeLLMProvider:
        def analyze(self, prompt, image_paths):
            assert "只输出合法 JSON" in prompt
            assert "manual_review" in prompt
            assert "quality_acceptance" in prompt
            assert "人工质量验收反馈" in prompt
            assert "rerun_strategy" in prompt
            assert "fix_targets" in prompt
            assert "do_not_repeat" in prompt
            assert "required_evidence" in prompt
            assert "这条视频适合拆教程结构" in prompt
            assert "开头需要直接给出结果承诺" in prompt
            assert "钩子判断基本正确，但分镜需要修正" in prompt
            assert "评论证据还不够" in prompt
            assert "补评论后重跑" in prompt
            assert "不要凭空新增原视频没有的镜头" in prompt
            assert "本次仍缺评论" in prompt
            assert "replication.copyable_points 每一条都必须能追溯" in prompt
            assert "replication.shot_table 每一行都必须基于" in prompt
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
    assert analysis["analysis_result"]["manual_review_context"]["used"] is True
    assert analysis["analysis_result"]["manual_review_context"]["summary"] == "这条视频适合拆教程结构。"
    acceptance_context = analysis["analysis_result"]["manual_review_context"]["quality_acceptance"]
    assert acceptance_context["used"] is True
    assert acceptance_context["verdict"] == "needs_fix"
    assert acceptance_context["score"] == "72"
    assert acceptance_context["summary"] == "钩子判断基本正确，但分镜需要修正。"
    assert acceptance_context["notes"] == "评论证据还不够。"
    assert acceptance_context["next_actions"] == "补评论后重跑。"
    assert any(check["id"] == "shot_table_is_actionable" for check in acceptance_context["checks"])
    rerun_strategy = analysis["analysis_result"]["manual_review_context"]["rerun_strategy"]
    assert rerun_strategy["active"] is True
    assert rerun_strategy["priority"] == "high"
    assert any(item["id"] == "shot_table_is_actionable" for item in rerun_strategy["fix_targets"])
    assert any(item["id"] == "comments" and item["status"] == "missing" for item in rerun_strategy["required_evidence"])
    assert any("不要凭空新增原视频没有的镜头" in item for item in rerun_strategy["do_not_repeat"])
    rerun_compliance = analysis["analysis_result"]["rerun_compliance"]
    assert rerun_compliance["active"] is True
    assert rerun_compliance["status"] == "needs_attention"
    assert any(check["id"] == "required_evidence:comments" for check in rerun_compliance["checks"])
    assert any(gap["id"] == "rerun_compliance" for gap in analysis["analysis_result"]["quality_review"]["gaps"])
    assert "## 重跑合规检查" in analysis["analysis_report"]
    assert "## 重跑修正策略" in analysis["analysis_report"]
    assert any(
        "第一眼看到了什么" in section["filled_fields"]
        for section in analysis["analysis_result"]["manual_review_context"]["sections"]
    )
    assert Path(analysis["analysis_result_path"]).is_file()
    assert Path(analysis["analysis_report_path"]).is_file()

    analyzed_api_response = client.get(f"/api/cases/{case['case_id']}")
    analyzed_case = analyzed_api_response.json()["case"]
    assert analyzed_case["analysis_result"]["summary"] == "自动拆解结果"
    assert analyzed_case["analysis_result"]["manual_review_context"]["used"] is True
    assert analyzed_case["analysis_result"]["rerun_compliance"]["status"] == "needs_attention"
    assert analyzed_case["rerun_plan"]["rerun_compliance"]["status"] == "needs_attention"
    assert analyzed_case["rerun_plan"]["rerun_compliance"]["blocking_count"] >= 1
    assert any(
        check["id"] == "required_evidence:comments"
        for check in analyzed_case["rerun_plan"]["rerun_compliance"]["checks"]
    )
    assert analyzed_case["quality_acceptance"]["summary"] == "钩子判断基本正确，但分镜需要修正。"
    assert analyzed_case["quality_acceptance"]["quality_snapshot"]["score"] >= 0
    analyzed_calibration = analyzed_case["quality_calibration"]
    assert analyzed_calibration["status"] == "needs_rerun"
    assert analyzed_calibration["ai_quality"]["has_report"] is True
    assert analyzed_calibration["human_acceptance"]["blocker_count"] == 2
    assert any(action["target"] == "#run-auto-analysis-button" for action in analyzed_calibration["next_actions"])
    assert any("补评论后重跑" in action["description"] for action in analyzed_calibration["next_actions"])
    assert any(
        item["id"] == "tighten_shot_table_gate"
        for item in analyzed_calibration["recommendations"]
    )
    assert any(
        item["id"] == "import_comments_before_rerun"
        for item in analyzed_calibration["recommendations"]
    )
    comment_recommendation = next(
        item for item in analyzed_calibration["recommendations"] if item["id"] == "import_comments_before_rerun"
    )
    assert comment_recommendation["action_label"] == "导入评论"
    assert comment_recommendation["action_target"] == "#comments-import-text"
    assert comment_recommendation["action_mode"] == "focus"
    analyzed_diagnosis = analyzed_case["case_diagnosis"]
    assert analyzed_diagnosis["status"] == "needs_rerun"
    assert analyzed_diagnosis["score"]["human_blocking"] == 2
    assert any(item["source"] == "human_acceptance" for item in analyzed_diagnosis["blockers"])
    assert analyzed_diagnosis["primary_actions"][0]["target"] == "#save-quality-acceptance-and-rerun-button"
    assert analyzed_diagnosis["primary_actions"][0]["mode"] == "click"
    assert any(action["target"] == "#run-auto-analysis-button" for action in analyzed_diagnosis["primary_actions"])
    assert "# AI 自动拆解报告" in analyzed_case["analysis_report"]
    assert "## 人工工作表上下文" in analyzed_case["analysis_report"]
    assert "## 人工质量验收反馈" in analyzed_case["analysis_report"]
    assert "评论证据还不够" in analyzed_case["analysis_report"]
    assert "这条视频适合拆教程结构" in analyzed_case["analysis_report"]

    calibration_record_response = client.post(f"/api/cases/{case['case_id']}/quality-calibration/record")
    assert calibration_record_response.status_code == 200
    calibration_record_payload = calibration_record_response.json()
    assert calibration_record_payload["ok"] is True
    record = calibration_record_payload["record"]
    assert record["case_id"] == case["case_id"]
    assert record["quality_calibration"]["status"] == "needs_rerun"
    assert record["case_diagnosis"]["status"] == "needs_rerun"
    assert record["case_diagnosis"]["score"]["human_blocking"] == 2
    assert record["case_diagnosis"]["primary_actions"][0]["target"] == "#save-quality-acceptance-and-rerun-button"
    assert record["rerun_strategy"]["active"] is True
    assert any(item["id"] == "comments" for item in record["rerun_strategy"]["required_evidence"])
    assert record["rerun_compliance"]["status"] == "needs_attention"
    assert record["rerun_compliance"]["blocking_count"] >= 1
    assert any(check["id"] == "required_evidence:comments" for check in record["rerun_compliance"]["checks"])
    assert any(item["id"] == "tighten_shot_table_gate" for item in record["recommendations"])
    assert any(item["id"] == "import_comments_before_rerun" for item in record["recommendations"])
    assert record["quality_acceptance"]["summary"] == "钩子判断基本正确，但分镜需要修正。"
    assert record["analysis_summary"] == "自动拆解结果"
    record_path = Path(calibration_record_payload["record_path"])
    index_path = Path(calibration_record_payload["index_path"])
    assert record_path.name == "quality_calibration_record.json"
    assert record_path.is_file()
    assert index_path.name == "quality_calibration_index.json"
    assert index_path.is_file()
    persisted_record = json.loads(record_path.read_text(encoding="utf-8"))
    assert persisted_record["case_id"] == case["case_id"]
    assert persisted_record["case_diagnosis"]["status"] == "needs_rerun"
    assert persisted_record["rerun_strategy"]["priority"] == "high"
    persisted_index = json.loads(index_path.read_text(encoding="utf-8"))
    indexed_record = next(item for item in persisted_index["records"] if item["case_id"] == case["case_id"])
    assert indexed_record["case_diagnosis"]["status"] == "needs_rerun"
    assert indexed_record["rerun_strategy"]["active"] is True

    record_list_response = client.get(
        "/api/cases/quality-calibration/records?status=needs_rerun&diagnosis_status=needs_rerun"
    )
    assert record_list_response.status_code == 200
    record_list_payload = record_list_response.json()
    assert record_list_payload["ok"] is True
    assert record_list_payload["filters"]["diagnosis_status"] == "needs_rerun"
    assert record_list_payload["filtered_summary"]["total"] >= 1
    assert record_list_payload["filtered_summary"]["by_diagnosis_status"]["needs_rerun"] >= 1
    assert "evidence_completion" in record_list_payload["filtered_summary"]
    assert record_list_payload["filtered_summary"]["evidence_completion"]["with_required_evidence"] >= 1
    assert record_list_payload["filtered_insights"]["top_human_blockers"]
    assert record_list_payload["filtered_insights"]["top_diagnosis_blockers"]
    assert record_list_payload["filtered_insights"]["top_diagnosis_actions"]
    assert record_list_payload["filtered_insights"]["top_rerun_evidence_gaps"]
    assert record_list_payload["filtered_insights"]["top_rerun_compliance_failures"]
    assert any(
        str(issue["id"]).startswith("fix_target:")
        for issue in record_list_payload["filtered_insights"]["top_rerun_compliance_failures"]
    )
    assert any(
        item["id"] == "import_comments_before_rerun"
        for item in record_list_payload["filtered_recommendations"]
    )
    assert any(
        item["id"] == "enforce_rerun_fix_targets"
        for item in record_list_payload["filtered_recommendations"]
    )
    assert any(
        issue["id"] == "shot_table_is_actionable"
        for issue in record_list_payload["filtered_insights"]["top_human_blockers"]
    )
    assert record_list_payload["filtered_insights"]["top_next_actions"]
    assert any(
        item["id"] == "tighten_shot_table_gate"
        for item in record_list_payload["filtered_recommendations"]
    )
    matched_record = next(item for item in record_list_payload["records"] if item["case_id"] == case["case_id"])
    assert matched_record["case_diagnosis"]["primary_actions"][0]["label"] == "保存反馈并重跑"
    assert any(item["case_id"] == case["case_id"] for item in record_list_payload["records"])

    record_search_response = client.get(
        "/api/cases/quality-calibration/records",
        params={"search": case["case_id"], "verdict": "needs_fix"},
    )
    assert record_search_response.status_code == 200
    search_payload = record_search_response.json()
    assert any(item["case_id"] == case["case_id"] for item in search_payload["records"])

    report_response = client.get(
        "/api/cases/quality-calibration/report",
        params={"status": "needs_rerun", "diagnosis_status": "needs_rerun", "verdict": "needs_fix"},
    )
    assert report_response.status_code == 200
    report_payload = report_response.json()
    assert report_payload["ok"] is True
    assert report_payload["summary"]["total"] >= 1
    report_markdown = report_payload["report_markdown"]
    assert "# 单条作品拆解质量校准报告" in report_markdown
    assert "## 2. 常见质量问题" in report_markdown
    assert "## 3. 规则改进建议" in report_markdown
    assert "诊断状态" in report_markdown
    assert "diagnosis_status=needs_rerun" in report_markdown
    assert "证据完成度：" in report_markdown
    assert "触发项：comments / audience" in report_markdown
    assert "页面动作：导入评论 -> #comments-import-text" in report_markdown
    assert "顶部诊断阻塞" in report_markdown
    assert "诊断推荐动作" in report_markdown
    assert "重跑仍缺证据" in report_markdown
    assert "重跑合规失败" in report_markdown
    assert "fix_target:" in report_markdown
    assert "逐项回应人工修正目标" in report_markdown
    assert "收紧分镜表闸门" in report_markdown
    assert "分镜表是否可执行" in report_markdown
    assert case["case_id"] in report_markdown

    image_response = client.get(f"/api/cases/{case['case_id']}/contact-sheet")
    assert image_response.status_code == 200
    assert image_response.headers["content-type"].startswith("image/jpeg")

    keyframe_url = api_payload["case"]["artifact_urls"]["keyframes"][0]["url"]
    keyframe_response = client.get(keyframe_url)
    assert keyframe_response.status_code == 200
    assert keyframe_response.headers["content-type"].startswith("image/jpeg")


def test_comment_import_refreshes_rerun_evidence_and_recommendations(tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "comment-evidence-refresh.mp4")
    local_video = upload_video(video_path, source_url="https://www.douyin.com/video/7650000000000000001")
    case_response = client.post("/api/cases/build", json={"local_video_id": local_video["local_video_id"]})
    assert case_response.status_code == 200
    case_id = case_response.json()["case"]["case_id"]

    quality_response = client.post(
        f"/api/cases/{case_id}/quality-acceptance",
        json={
            "acceptance": {
                "verdict": "needs_fix",
                "summary": "需要补评论证据再判断互动钩子。",
                "checks": {
                    "summary_matches_video": "pass",
                    "evidence_is_sufficient": "needs_fix",
                    "copyable_points_are_useful": "pass",
                    "shot_table_is_actionable": "needs_fix",
                    "publish_package_is_usable": "pass",
                },
                "notes": "当前缺少用户反馈。",
                "next_actions": "先导入评论。",
            }
        },
    )
    assert quality_response.status_code == 200
    missing_case = quality_response.json()["case"]
    missing_strategy = missing_case["manual_review_context"]["rerun_strategy"]
    assert any(item["id"] == "comments" and item["status"] == "missing" for item in missing_strategy["required_evidence"])
    assert any(item["id"] == "import_comments_before_rerun" for item in missing_case["quality_calibration"]["recommendations"])

    comments_response = client.post(
        f"/api/cases/{case_id}/comments/import",
        json={
            "text": "想看完整教程\n这个开头很抓人\n求同款拍摄方法",
            "source": "manual",
            "permission_note": "user provided comments",
        },
    )
    assert comments_response.status_code == 200
    assert comments_response.json()["comments"]["imported_count"] == 3

    refreshed_response = client.get(f"/api/cases/{case_id}")
    assert refreshed_response.status_code == 200
    refreshed_case = refreshed_response.json()["case"]
    refreshed_strategy = refreshed_case["manual_review_context"]["rerun_strategy"]
    comment_evidence = next(item for item in refreshed_strategy["required_evidence"] if item["id"] == "comments")
    assert comment_evidence["status"] == "success"
    assert comment_evidence["count"] == 3
    assert refreshed_strategy["evidence_summary"]["total"] == 1
    assert refreshed_strategy["evidence_summary"]["ready"] == 1
    assert refreshed_strategy["evidence_summary"]["missing"] == 0
    assert refreshed_strategy["evidence_summary"]["complete"] is True
    assert not any(
        item["id"] == "import_comments_before_rerun"
        for item in refreshed_case["quality_calibration"]["recommendations"]
    )
    assert not any(gap["id"] == "comments" for gap in refreshed_case["analysis_readiness"]["critical_gaps"])
    assert refreshed_case["analysis_input"]["analysis_enrichment"]["comments"]["total_comments"] == 3

    record_response = client.post(f"/api/cases/{case_id}/quality-calibration/record")
    assert record_response.status_code == 200
    record = record_response.json()["record"]
    record_comment_evidence = next(item for item in record["rerun_strategy"]["required_evidence"] if item["id"] == "comments")
    assert record_comment_evidence["status"] == "success"
    assert record_comment_evidence["count"] == 3

    report_response = client.get("/api/cases/quality-calibration/report", params={"search": case_id})
    assert report_response.status_code == 200
    report_markdown = report_response.json()["report_markdown"]
    assert "证据完成度：已就绪 1 / 缺失 0 / 总计 1" in report_markdown
    assert "证据完成度：样本 1，已齐 1，仍缺 0，证据项 1/1" in report_markdown
    assert "重跑证据：" in report_markdown
    assert "评论摘要:success（评论 3 条）" in report_markdown


def test_analyze_case_job_reports_llm_not_configured(monkeypatch, tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "no-llm.mp4")
    local_video = upload_video(video_path)
    case_response = client.post("/api/cases/build", json={"local_video_id": local_video["local_video_id"]})
    assert case_response.status_code == 200
    case_id = case_response.json()["case"]["case_id"]

    monkeypatch.setattr("app.services.llm_settings.settings.llm_provider", "disabled")
    monkeypatch.setattr("app.services.llm_settings.settings.llm_api_key", "")
    monkeypatch.setattr("app.services.llm_settings.settings.llm_model", "")
    monkeypatch.setattr("app.services.llm_provider.settings.llm_provider", "disabled")
    monkeypatch.setattr("app.services.llm_provider.settings.llm_api_key", "")
    monkeypatch.setattr("app.services.llm_provider.settings.llm_model", "")

    create_response = client.post("/api/jobs/analyze-case", json={"case_id": case_id})
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
    assert job["status"] == "failed"
    assert job["error_code"] == "LLM_NOT_CONFIGURED"


def test_auto_analyzer_falls_back_to_text_when_vision_request_fails(tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "vision-fallback.mp4")
    local_video = upload_video(video_path)
    case_response = client.post("/api/cases/build", json={"local_video_id": local_video["local_video_id"]})
    assert case_response.status_code == 200
    case_id = case_response.json()["case"]["case_id"]

    class VisionFailTextOkProvider:
        def __init__(self):
            self.calls = []

        def analyze(self, prompt, image_paths):
            self.calls.append(len(image_paths))
            if image_paths:
                raise AppError(ErrorCode.LLM_REQUEST_FAILED, "大模型 API 返回 HTTP 504。")
            assert "文本降级拆解" in prompt
            assert "confidence 不要虚高" in prompt
            assert "publish_package 不能只有标题" in prompt
            assert "replication.avoid_copying 或 risks 必须说明不要照搬" in prompt
            assert "replication.copyable_points 必须来自标题、互动数据、富化文本或人工工作表" in prompt
            assert "shot_table 不得凭空新增画面镜头" in prompt
            return {
                "summary": "文本降级拆解结果：未成功读取视觉图片，需要人工复核 contact sheet。",
                "hook_analysis": {},
                "visual_analysis": {},
                "copywriting_analysis": {},
                "replication": {},
                "publish_package": {},
                "risks": ["本次未成功读取视觉图片，视觉判断置信度较低。"],
            }

    provider = VisionFailTextOkProvider()
    db = SessionLocal()
    try:
        artifact = db.get(CaseArtifact, case_id)
        analysis = analyze_case_artifact(artifact, provider=provider)
    finally:
        db.close()

    assert provider.calls[0] > 1
    assert provider.calls[1] == 1
    assert provider.calls[2] == 0
    assert "文本降级拆解结果" in analysis["analysis_result"]["summary"]
    assert Path(analysis["analysis_report_path"]).is_file()


def test_auto_analyzer_fast_mode_uses_contact_sheet_only(tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "fast-analysis.mp4")
    local_video = upload_video(video_path, source_url="https://www.douyin.com/video/7651938969785849999")
    case_response = client.post("/api/cases/build", json={"local_video_id": local_video["local_video_id"]})
    assert case_response.status_code == 200
    case_id = case_response.json()["case"]["case_id"]

    class FastProvider:
        def __init__(self):
            self.prompt = ""
            self.image_names = []

        def analyze(self, prompt, image_paths):
            self.prompt = prompt
            self.image_names = [Path(path).name for path in image_paths]
            assert "快速输出一个简短 JSON" in prompt
            assert "输出必须满足质量门槛" not in prompt
            assert self.image_names == ["contact_sheet.jpg"]
            return {
                "summary": "快速拆解：第一眼靠人物和画面氛围吸引。",
                "content_category": "beauty_cos",
                "content_category_label": "美拍 / COS / 颜值向",
                "confidence": 0.72,
                "hook_analysis": {
                    "first_impression": "人物主体明确",
                    "why_stop_scrolling": "画面氛围直接",
                    "first_3_seconds": ["0-1s 人物出现", "1-3s 动作延续"],
                    "optimization": "强化标题点击理由",
                },
                "visual_analysis": {"subject": "人物", "movement_rhythm": "轻动作"},
                "replication": {"copyable_points": ["保留人物居中和妆造氛围"], "avoid_copying": ["不要照搬原片"]},
                "publish_package": {"titles": ["今天这套氛围感拉满"]},
            }

    provider = FastProvider()
    db = SessionLocal()
    try:
        artifact = db.get(CaseArtifact, case_id)
        analysis = analyze_case_artifact(artifact, provider=provider, mode="fast")
    finally:
        db.close()

    assert provider.image_names == ["contact_sheet.jpg"]
    assert analysis["analysis_result"]["summary"].startswith("快速拆解")
    assert analysis["analysis_result"]["evidence_summary"]["visual_input_mode"] == "contact_sheet_only"
    assert Path(analysis["analysis_report_path"]).is_file()



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

    def fake_analyze_case_artifact(artifact, progress=None, mode="deep"):
        assert mode == "fast"
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
    assert "job 自动拆解" in job["result_json"]["analysis"]["analysis_report"]
    assert Path(job["result_json"]["analysis"]["analysis_report_path"]).is_file()


def test_download_build_analyze_case_job_keeps_case_when_ai_fails(monkeypatch, tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "download-build-analyze-ai-fail.mp4")
    local_video = upload_video(video_path)

    def fake_download_candidate(db, aweme_id, candidate_id, progress=None):
        if progress:
            progress(100, "下载完成")
        return {
            "download_id": "download_fake_ai_fail",
            "aweme_id": aweme_id,
            "candidate_id": candidate_id,
            "file_path": local_video["local_video_id"],
            "size_bytes": 100,
            "local_video_id": local_video["local_video_id"],
        }

    def fake_analyze_case_artifact(artifact, progress=None, mode="deep"):
        assert mode == "fast"
        if progress:
            progress(35, "调用大模型自动拆解")
        raise AppError(ErrorCode.LLM_REQUEST_FAILED, "大模型 API 返回 HTTP 504。")

    monkeypatch.setattr("app.routes.jobs.download_candidate", fake_download_candidate)
    monkeypatch.setattr("app.routes.jobs.analyze_case_artifact", fake_analyze_case_artifact)

    create_response = client.post(
        "/api/jobs/download-build-analyze-case",
        json={"aweme_id": "7650000000000000400", "candidate_id": "cand_chain_ai_fail"},
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
    assert job["result_json"]["case"]["case_id"].startswith("case_")
    assert job["result_json"]["analysis_status"] == "failed"
    assert job["result_json"]["analysis_error"]["error_code"] == "LLM_REQUEST_FAILED"
    assert Path(job["result_json"]["case"]["analysis_input_path"]).is_file()


def test_profile_build_cases_queue_rejects_more_than_configured_limit() -> None:
    response = client.post(
        "/api/jobs/profile-build-cases",
        json={
            "items": [
                {"aweme_id": f"76500000000000005{index:02d}", "media_type": "video"}
                for index in range(11)
            ]
        },
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "PROFILE_BUILD_QUEUE_LIMIT"
    assert "10 条作品" in response.json()["message"]


def test_profile_build_cases_queue_rejects_too_many_selected_reference_samples() -> None:
    response = client.post(
        "/api/jobs/profile-build-cases",
        json={
            "items": [
                {"sample_id": f"sample_ref_{index}", "media_type": "text", "title": f"参考样本 {index}"}
                for index in range(MAX_DISTILL_SAMPLES + 1)
            ],
            "selected_sample_ids": [f"sample_ref_{index}" for index in range(MAX_DISTILL_SAMPLES + 1)],
        },
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "PROFILE_BUILD_QUEUE_LIMIT"
    assert f"{MAX_DISTILL_SAMPLES} 条样本" in response.json()["message"]


def test_profile_build_cases_queue_continues_after_item_failure(monkeypatch, tmp_path: Path) -> None:
    case_dir = tmp_path / "case_fake"
    case_dir.mkdir()

    def fake_resolve_quality_candidates(db, aweme_id):
        if aweme_id == "7650000000000000601":
            raise AppError(ErrorCode.QUALITY_NOT_FOUND, "第一条候选失败。")
        return [{"candidate_id": f"cand_{aweme_id}", "quality_label": "720p"}]

    def fake_download_candidate(db, aweme_id, candidate_id, progress=None):
        return {
            "download_id": f"download_{aweme_id}",
            "aweme_id": aweme_id,
            "candidate_id": candidate_id,
            "file_path": str(tmp_path / f"{aweme_id}.mp4"),
            "size_bytes": 100,
            "local_video_id": f"local_{aweme_id}",
        }

    class FakeArtifact:
        case_id = "case_profile_queue_ok"
        local_video_id = "local_7650000000000000602"
        video_path = str(case_dir / "video.mp4")
        metadata_path = str(case_dir / "metadata.json")
        analysis_input_path = str(case_dir / "analysis_input.json")
        prompt_path = str(case_dir / "prompt.md")
        contact_sheet_path = str(case_dir / "contact_sheet.jpg")
        keyframes_dir = str(case_dir / "keyframes")

    def fake_build_case_from_local_video(db, local_video_id, progress=None):
        return FakeArtifact()

    monkeypatch.setattr("app.routes.jobs.resolve_quality_candidates", fake_resolve_quality_candidates)
    monkeypatch.setattr("app.routes.jobs.download_candidate", fake_download_candidate)
    monkeypatch.setattr("app.routes.jobs.build_case_from_local_video", fake_build_case_from_local_video)

    create_response = client.post(
        "/api/jobs/profile-build-cases",
        json={
            "items": [
                {"aweme_id": "7650000000000000601", "title": "失败作品", "media_type": "video"},
                {"aweme_id": "7650000000000000602", "title": "成功作品", "media_type": "video"},
                {"aweme_id": "7650000000000000603", "title": "图文作品", "media_type": "image"},
            ],
            "auto_analyze": False,
        },
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
    result = job["result_json"]
    assert result["completed_count"] == 1
    assert result["failed_count"] == 1
    assert result["skipped_count"] == 1
    assert result["reference_only_count"] == 1
    assert result["downloadable_count"] == 2
    statuses = {item["aweme_id"]: item["status"] for item in result["items"]}
    assert statuses["7650000000000000601"] == "failed"
    assert statuses["7650000000000000602"] == "completed"
    assert statuses["7650000000000000603"] == "skipped"
    completed_item = result["items"][1]
    assert completed_item["case_id"] == "case_profile_queue_ok"
    assert completed_item["enrichment_status"] in {"success", "failed"}
    assert completed_item["asr_status"] in {"success", "no_speech", "provider_missing", "failed"}
    assert completed_item["ocr_status"] in {"success", "no_text", "provider_missing", "failed"}


def test_profile_build_cases_queue_backfills_asr_ocr_evidence_into_sample_set(monkeypatch, tmp_path: Path) -> None:
    set_id = "clone_profile_queue_backfill_asr_ocr"
    aweme_id = "7650000000000000801"
    case_id = "case_profile_queue_backfill_asr_ocr"
    case_dir = settings.cases_dir / case_id
    shutil.rmtree(settings.creator_clones_dir / set_id, ignore_errors=True)
    shutil.rmtree(case_dir, ignore_errors=True)
    case_dir.mkdir(parents=True)
    (case_dir / "keyframes").mkdir()
    (case_dir / "video.mp4").write_bytes(b"video")
    (case_dir / "contact_sheet.jpg").write_bytes(b"image")
    (case_dir / "metadata.json").write_text(
        json.dumps(
            {
                "title": "可富化样本",
                "source_url": f"https://www.douyin.com/video/{aweme_id}",
                "like_count": 1200,
                "comment_count": 88,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (case_dir / "analysis_input.json").write_text(
        json.dumps(
            {
                "content_category": "beauty_cos",
                "content_category_label": "美拍 / COS / 颜值向",
                "assets": {"contact_sheet": "contact_sheet.jpg", "keyframes": [{"timestamp": 0}, {"timestamp": 3}]},
                "analysis_enrichment": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (case_dir / "prompt.md").write_text("prompt", encoding="utf-8")
    (case_dir / "qualities.json").write_text("[]", encoding="utf-8")
    (case_dir / "ffprobe.json").write_text("{}", encoding="utf-8")

    artifact = CaseArtifact(
        case_id=case_id,
        aweme_id=aweme_id,
        local_video_id=f"local_{aweme_id}",
        video_path=str(case_dir / "video.mp4"),
        metadata_path=str(case_dir / "metadata.json"),
        qualities_path=str(case_dir / "qualities.json"),
        ffprobe_path=str(case_dir / "ffprobe.json"),
        analysis_input_path=str(case_dir / "analysis_input.json"),
        prompt_path=str(case_dir / "prompt.md"),
        contact_sheet_path=str(case_dir / "contact_sheet.jpg"),
        keyframes_dir=str(case_dir / "keyframes"),
    )
    save_sample_set(
        CloneSampleSet(
            set_id=set_id,
            title="队列回写富化证据测试",
            source_platform="douyin",
            samples=[
                CloneSample(
                    sample_id=f"sample_{aweme_id}",
                    aweme_id=aweme_id,
                    title="可富化样本",
                    media_type="video",
                    like_count=1200,
                )
            ],
        )
    )

    monkeypatch.setattr(
        "app.routes.jobs.resolve_quality_candidates",
        lambda db, item_aweme_id: [{"candidate_id": f"cand_{item_aweme_id}", "quality_label": "720p"}],
    )
    monkeypatch.setattr(
        "app.routes.jobs.download_candidate",
        lambda db, item_aweme_id, candidate_id, progress=None: {
            "download_id": f"download_{item_aweme_id}",
            "aweme_id": item_aweme_id,
            "candidate_id": candidate_id,
            "file_path": str(tmp_path / f"{item_aweme_id}.mp4"),
            "size_bytes": 100,
            "local_video_id": f"local_{item_aweme_id}",
        },
    )
    monkeypatch.setattr("app.routes.jobs.build_case_from_local_video", lambda db, local_video_id, progress=None: artifact)

    def fake_build_enrichment_archive(artifact_arg, capture_method="", permission_note=""):
        enrichment_dir = case_dir / "enrichment"
        enrichment_dir.mkdir()
        (enrichment_dir / "manifest.json").write_text(
            json.dumps({"statuses": {"asr": "success", "ocr": "success", "comments": "pending"}}, ensure_ascii=False),
            encoding="utf-8",
        )
        return {"manifest_path": str(enrichment_dir / "manifest.json")}

    def fake_run_case_asr(artifact_arg):
        asr_dir = case_dir / "enrichment" / "asr"
        asr_dir.mkdir(parents=True, exist_ok=True)
        (asr_dir / "status.json").write_text(json.dumps({"status": "success"}, ensure_ascii=False), encoding="utf-8")
        (asr_dir / "transcript.json").write_text(
            json.dumps({"status": "success", "full_text": "前三秒用眼神和动作制造停留"}, ensure_ascii=False),
            encoding="utf-8",
        )
        return {"status": "success", "full_text": "前三秒用眼神和动作制造停留"}

    def fake_run_case_ocr(artifact_arg):
        ocr_dir = case_dir / "enrichment" / "ocr"
        ocr_dir.mkdir(parents=True, exist_ok=True)
        (ocr_dir / "status.json").write_text(json.dumps({"status": "success"}, ensure_ascii=False), encoding="utf-8")
        (ocr_dir / "frame_ocr.json").write_text(
            json.dumps({"status": "success", "full_text": "封面字：甜美反差感"}, ensure_ascii=False),
            encoding="utf-8",
        )
        return {"status": "success", "frame_text": "封面字：甜美反差感"}

    monkeypatch.setattr("app.routes.jobs.build_enrichment_archive", fake_build_enrichment_archive)
    monkeypatch.setattr("app.routes.jobs.run_case_asr", fake_run_case_asr)
    monkeypatch.setattr("app.routes.jobs.run_case_ocr", fake_run_case_ocr)

    create_response = client.post(
        "/api/jobs/profile-build-cases",
        json={
            "items": [{"aweme_id": aweme_id, "sample_id": f"sample_{aweme_id}", "title": "可富化样本", "media_type": "video"}],
            "sample_set_id": set_id,
            "selected_sample_ids": [f"sample_{aweme_id}"],
            "auto_enrich": True,
            "auto_asr": True,
            "auto_ocr": True,
            "auto_analyze": False,
        },
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
    result = job["result_json"]
    assert result["completed_count"] == 1
    assert result["pipeline_summary"]["selected_count"] == 1
    assert result["pipeline_summary"]["downloadable_count"] == 1
    assert result["pipeline_summary"]["downloaded_count"] == 1
    assert result["pipeline_summary"]["case_count"] == 1
    assert result["pipeline_summary"]["asr_success_count"] == 1
    assert result["pipeline_summary"]["ocr_success_count"] == 1
    assert result["pipeline_summary"]["ready_for_distill_count"] == 1
    assert result["pipeline_summary"]["requested_stages"] == {
        "download": True,
        "build_case": True,
        "enrichment": True,
        "asr": True,
        "ocr": True,
        "llm_analysis": False,
    }
    assert result["pipeline_summary"]["next_actions"][0].startswith("可继续点击")
    assert any("素材包" in note for note in result["pipeline_summary"]["notes"])
    assert any("本轮选中 1 条" in note for note in result["pipeline_summary"]["notes"])
    assert result["set"]["selected_sample_ids"] == [f"sample_{aweme_id}"]
    updated_sample = load_sample_set(set_id).samples[0]
    assert updated_sample.case_id == case_id
    assert updated_sample.has_video is True
    assert updated_sample.has_frames is True
    assert updated_sample.has_asr is True
    assert updated_sample.has_ocr is True
    assert updated_sample.enrichment_status == "success"
    assert updated_sample.asr_status == "success"
    assert updated_sample.ocr_status == "success"
    prompt = build_distill_prompt(load_sample_set(set_id), [updated_sample], include_case_reports=True)
    assert "with_asr_text" in prompt
    assert "with_ocr_text" in prompt
    assert "前三秒用眼神和动作制造停留" in prompt
    assert "甜美反差感" in prompt


def test_profile_build_cases_queue_skips_text_items_without_download() -> None:
    set_id = "clone_profile_queue_selection_skip"
    shutil.rmtree(settings.creator_clones_dir / set_id, ignore_errors=True)
    save_sample_set(
        CloneSampleSet(
            set_id=set_id,
            title="队列选样跳过测试",
            source_platform="douyin",
            samples=[
                CloneSample(
                    sample_id="sample_text",
                    aweme_id="7650000000000000701",
                    title="纯文本样本",
                    media_type="text",
                )
            ],
        )
    )
    create_response = client.post(
        "/api/jobs/profile-build-cases",
        json={
            "items": [
                {
                    "aweme_id": "7650000000000000701",
                    "title": "纯文本样本",
                    "media_type": "text",
                }
            ],
            "sample_set_id": set_id,
            "selected_sample_ids": ["sample_text"],
            "auto_analyze": False,
        },
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
    result = job["result_json"]
    assert result["completed_count"] == 0
    assert result["failed_count"] == 0
    assert result["skipped_count"] == 1
    assert result["reference_only_count"] == 1
    assert result["downloadable_count"] == 0
    assert result["pipeline_summary"]["selected_count"] == 1
    assert result["pipeline_summary"]["downloadable_count"] == 0
    assert result["pipeline_summary"]["downloaded_count"] == 0
    assert result["pipeline_summary"]["case_count"] == 0
    assert result["pipeline_summary"]["reference_only_count"] == 1
    assert result["pipeline_summary"]["ready_for_distill_count"] == 1
    assert result["pipeline_summary"]["requested_stages"] == {
        "download": False,
        "build_case": False,
        "enrichment": False,
        "asr": False,
        "ocr": False,
        "llm_analysis": False,
    }
    assert result["pipeline_summary"]["next_actions"][0].startswith("可继续点击")
    assert any("参考证据" in note for note in result["pipeline_summary"]["notes"])
    assert any("本轮选中 1 条" in note for note in result["pipeline_summary"]["notes"])
    assert result["set"]["selected_sample_ids"] == ["sample_text"]
    assert load_sample_set(set_id).selected_sample_ids == ["sample_text"]
    item = result["items"][0]
    assert item["status"] == "skipped"
    assert item["error_code"] == ErrorCode.UNSUPPORTED_PROFILE_ITEM
    assert "保留为创作者蒸馏的元数据证据" in item["message"]


def test_profile_build_cases_queue_keeps_case_reference_without_aweme_id() -> None:
    set_id = "clone_profile_queue_case_reference"
    shutil.rmtree(settings.creator_clones_dir / set_id, ignore_errors=True)
    save_sample_set(
        CloneSampleSet(
            set_id=set_id,
            title="已有 Case 参考样本",
            source_platform="douyin",
            samples=[
                CloneSample(
                    sample_id="sample_case_ref",
                    case_id="case_existing_reference",
                    title="已有素材包参考",
                    media_type="unknown",
                    understanding_level="partial",
                )
            ],
        )
    )

    create_response = client.post(
        "/api/jobs/profile-build-cases",
        json={
            "items": [
                {
                    "aweme_id": "",
                    "title": "已有素材包参考",
                    "media_type": "unknown",
                }
            ],
            "sample_set_id": set_id,
            "selected_sample_ids": ["sample_case_ref"],
            "auto_analyze": False,
        },
    )

    assert create_response.status_code == 200
    create_payload = create_response.json()
    assert create_payload["selected_count"] == 1
    assert create_payload["downloadable_count"] == 0
    assert create_payload["reference_only_count"] == 1
    job_id = create_payload["job_id"]

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
    result = job["result_json"]
    assert result["completed_count"] == 0
    assert result["failed_count"] == 0
    assert result["skipped_count"] == 1
    assert result["reference_only_count"] == 1
    assert result["downloadable_count"] == 0
    assert result["pipeline_summary"]["case_count"] == 1
    assert result["pipeline_summary"]["reference_only_count"] == 1
    assert result["pipeline_summary"]["ready_for_distill_count"] == 1
    assert result["set"]["selected_sample_ids"] == ["sample_case_ref"]
    assert load_sample_set(set_id).selected_sample_ids == ["sample_case_ref"]
    item = result["items"][0]
    assert item["status"] == "skipped"
    assert item["error_code"] == ErrorCode.UNSUPPORTED_PROFILE_ITEM
    assert "参考样本不执行视频下载" in item["message"]


def test_profile_build_cases_queue_accepts_reference_item_without_aweme_field() -> None:
    set_id = "clone_profile_queue_reference_without_aweme_field"
    shutil.rmtree(settings.creator_clones_dir / set_id, ignore_errors=True)
    save_sample_set(
        CloneSampleSet(
            set_id=set_id,
            title="无作品 ID 参考样本",
            source_platform="douyin",
            samples=[
                CloneSample(
                    sample_id="sample_metadata_ref",
                    case_id="case_metadata_reference",
                    title="公开主页可见封面参考",
                    media_type="unknown",
                    source_url="https://www.douyin.com/user/example",
                    understanding_level="metadata-only",
                )
            ],
        )
    )

    create_response = client.post(
        "/api/jobs/profile-build-cases",
        json={
            "items": [
                {
                    "sample_id": "sample_metadata_ref",
                    "case_id": "case_metadata_reference",
                    "source_url": "https://www.douyin.com/user/example",
                    "title": "公开主页可见封面参考",
                    "media_type": "unknown",
                }
            ],
            "sample_set_id": set_id,
            "selected_sample_ids": ["sample_metadata_ref"],
            "auto_analyze": False,
        },
    )

    assert create_response.status_code == 200
    create_payload = create_response.json()
    assert create_payload["selected_count"] == 1
    assert create_payload["downloadable_count"] == 0
    assert create_payload["reference_only_count"] == 1
    assert create_payload["queued_items"][0]["aweme_id"] == ""
    assert create_payload["queued_items"][0]["sample_id"] == "sample_metadata_ref"
    assert create_payload["queued_items"][0]["case_id"] == "case_metadata_reference"
    job_id = create_payload["job_id"]

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
    result = job["result_json"]
    assert result["completed_count"] == 0
    assert result["reference_only_count"] == 1
    assert result["downloadable_count"] == 0
    assert result["pipeline_summary"]["case_count"] == 1
    assert result["pipeline_summary"]["reference_only_count"] == 1
    assert result["pipeline_summary"]["ready_for_distill_count"] == 1
    assert result["set"]["selected_sample_ids"] == ["sample_metadata_ref"]
    item = result["items"][0]
    assert item["status"] == "skipped"
    assert item["aweme_id"] == ""
    assert item["sample_id"] == "sample_metadata_ref"
    assert item["case_id"] == "case_metadata_reference"
    assert item["error_code"] == ErrorCode.UNSUPPORTED_PROFILE_ITEM


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


def test_enrichment_archive_comments_metrics_and_provider_placeholders(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.services.asr.settings.asr_provider", "disabled")
    monkeypatch.setattr("app.services.ocr.settings.ocr_provider", "disabled")
    video_path = make_sample_video(tmp_path / "enrichment.mp4")
    local_video = upload_video(video_path, source_url="https://www.douyin.com/video/7651938969785849111")
    case_response = client.post("/api/cases/build", json={"local_video_id": local_video["local_video_id"]})
    assert case_response.status_code == 200
    case_id = case_response.json()["case"]["case_id"]
    case_dir = Path(case_response.json()["case"]["video_path"]).parent

    detail_response = client.get(f"/api/cases/{case_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["case"]["enrichment"]["manifest"]["case_id"] == case_id
    assert detail_payload["case"]["enrichment"]["manifest"]["statuses"]["comments"] == "pending"

    enrich_response = client.post(f"/api/cases/{case_id}/archive/enrich")
    assert enrich_response.status_code == 200
    enrich_payload = enrich_response.json()
    assert enrich_payload["ok"] is True
    manifest = enrich_payload["enrichment"]["manifest"]
    assert manifest["statuses"]["metrics"] == "success"
    assert manifest["statuses"]["index"] == "success"
    assert (case_dir / "enrichment" / "manifest.json").is_file()
    assert (case_dir / "enrichment" / "metrics" / "snapshots.jsonl").is_file()
    assert (case_dir / "enrichment" / "indexes" / "case_index.json").is_file()

    comments_response = client.post(
        f"/api/cases/{case_id}/comments/import",
        json={
            "text": "接好运\n真实扎心，求同款\n{\"text\":\"太有用了，链接在哪里\",\"likes\":8}",
            "source": "manual",
            "permission_note": "test provided comments",
        },
    )
    assert comments_response.status_code == 200
    comments_payload = comments_response.json()
    assert comments_payload["comments"]["imported_count"] == 3
    summary = comments_payload["comments"]["summary"]
    assert summary["total_comments"] == 3
    assert "情感共鸣" in summary["top_needs"]
    assert "求同款/购买线索" in summary["top_needs"]

    snapshot_response = client.post(
        f"/api/cases/{case_id}/metrics/snapshot",
        json={"capture_method": "pytest", "permission_note": "local test"},
    )
    assert snapshot_response.status_code == 200
    assert snapshot_response.json()["snapshot"]["capture_method"] == "pytest"

    asr_response = client.post(f"/api/cases/{case_id}/asr")
    assert asr_response.status_code == 501
    assert asr_response.json()["error_code"] == "ASR_PROVIDER_NOT_CONFIGURED"
    ocr_response = client.post(f"/api/cases/{case_id}/ocr")
    assert ocr_response.status_code == 501
    assert ocr_response.json()["error_code"] == "OCR_PROVIDER_NOT_CONFIGURED"

    enrichment_response = client.get(f"/api/cases/{case_id}/enrichment")
    assert enrichment_response.status_code == 200
    enrichment = enrichment_response.json()["enrichment"]
    assert enrichment["manifest"]["statuses"]["comments"] == "success"
    assert enrichment["manifest"]["statuses"]["asr"] == "provider_missing"
    assert enrichment["manifest"]["statuses"]["ocr"] == "provider_missing"
    assert enrichment["comment_summary"]["total_comments"] == 3
    assert enrichment["case_index"]["stats"]["engagement_score"] == 44
    assert (case_dir / "enrichment" / "comments" / "comments_clean.jsonl").is_file()
    assert (case_dir / "enrichment" / "asr" / "status.json").is_file()
    assert (case_dir / "enrichment" / "ocr" / "status.json").is_file()


def test_case_asr_writes_audio_transcripts_and_manifest(tmp_path: Path) -> None:
    video_path = make_sample_video_with_audio(tmp_path / "asr.mp4")
    local_video = upload_video(video_path, source_url="https://www.douyin.com/video/7651938969785849222")
    case_response = client.post("/api/cases/build", json={"local_video_id": local_video["local_video_id"]})
    assert case_response.status_code == 200
    case_id = case_response.json()["case"]["case_id"]
    case_dir = Path(case_response.json()["case"]["video_path"]).parent

    class FakeASRProvider:
        provider_name = "fake-asr"

        def transcribe(self, audio_path):
            assert Path(audio_path).is_file()
            return {
                "provider": self.provider_name,
                "model": "mock",
                "language": "zh",
                "segments": [
                    {
                        "index": 0,
                        "start": 0.0,
                        "end": 1.2,
                        "text": "真正厉害的人会先抓住前三秒",
                        "confidence": 0.95,
                    }
                ],
                "full_text": "真正厉害的人会先抓住前三秒",
            }

    db = SessionLocal()
    try:
        artifact = db.get(CaseArtifact, case_id)
        result = run_case_asr(artifact, provider=FakeASRProvider())
    finally:
        db.close()

    assert result["status"] == "success"
    asr_dir = case_dir / "enrichment" / "asr"
    assert (asr_dir / "audio.wav").is_file()
    assert (asr_dir / "transcript.json").is_file()
    assert (asr_dir / "transcript.txt").read_text(encoding="utf-8") == "真正厉害的人会先抓住前三秒"
    assert "真正厉害的人" in (asr_dir / "transcript.srt").read_text(encoding="utf-8")

    manifest = json.loads((case_dir / "enrichment" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["statuses"]["asr"] == "success"

    enrichment_response = client.get(f"/api/cases/{case_id}/enrichment")
    assert enrichment_response.status_code == 200
    enrichment = enrichment_response.json()["enrichment"]
    assert enrichment["asr_status"]["status"] == "success"
    assert enrichment["asr_transcript"]["full_text"] == "真正厉害的人会先抓住前三秒"
    enriched_input = json.loads((case_dir / "analysis_input.json").read_text(encoding="utf-8"))
    assert enriched_input["analysis_enrichment"]["asr"]["full_text"] == "真正厉害的人会先抓住前三秒"

    detail_response = client.get(f"/api/cases/{case_id}")
    assert detail_response.status_code == 200
    rerun_evidence = detail_response.json()["case"]["manual_review_context"]["rerun_strategy"]["required_evidence"]
    asr_evidence = next(item for item in rerun_evidence if item["id"] == "asr")
    assert asr_evidence["status"] == "success"
    assert asr_evidence["char_count"] == len("真正厉害的人会先抓住前三秒")
    assert asr_evidence["segment_count"] == 1
    assert asr_evidence["excerpt"] == "真正厉害的人会先抓住前三秒"


def test_asr_case_job_reports_provider_not_configured(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.services.asr.settings.asr_provider", "disabled")
    video_path = make_sample_video(tmp_path / "asr-disabled.mp4")
    local_video = upload_video(video_path)
    case_response = client.post("/api/cases/build", json={"local_video_id": local_video["local_video_id"]})
    assert case_response.status_code == 200
    case_id = case_response.json()["case"]["case_id"]

    create_response = client.post("/api/jobs/asr-case", json={"case_id": case_id})
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
    assert job["status"] == "failed"
    assert job["error_code"] == "ASR_PROVIDER_NOT_CONFIGURED"


def test_asr_auto_provider_selects_faster_whisper_when_installed(monkeypatch) -> None:
    from app.services.asr import FasterWhisperProvider, _configured_provider

    monkeypatch.setattr("app.services.asr.settings.asr_provider", "auto")
    monkeypatch.setattr("app.services.asr.importlib.util.find_spec", lambda name: object() if name == "faster_whisper" else None)

    provider = _configured_provider()

    assert isinstance(provider, FasterWhisperProvider)


def test_case_ocr_writes_frame_subtitle_cover_outputs(tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "ocr.mp4")
    local_video = upload_video(video_path, source_url="https://www.douyin.com/video/7651938969785849333")
    case_response = client.post("/api/cases/build", json={"local_video_id": local_video["local_video_id"]})
    assert case_response.status_code == 200
    case_id = case_response.json()["case"]["case_id"]
    case_dir = Path(case_response.json()["case"]["video_path"]).parent

    class FakeOCRProvider:
        provider_name = "fake-ocr"

        def recognize(self, image_path):
            name = Path(image_path).name
            if "bottom" in name:
                return [{"text": "先抓住前三秒", "bbox": [0, 120, 320, 200], "confidence": 0.93}]
            return [{"text": "封面承诺", "bbox": [10, 20, 200, 80], "confidence": 0.91}]

    db = SessionLocal()
    try:
        artifact = db.get(CaseArtifact, case_id)
        result = run_case_ocr(artifact, provider=FakeOCRProvider())
    finally:
        db.close()

    assert result["status"] == "success"
    ocr_dir = case_dir / "enrichment" / "ocr"
    assert (ocr_dir / "frame_ocr.json").is_file()
    assert (ocr_dir / "subtitle_ocr.json").is_file()
    assert (ocr_dir / "cover_ocr.json").is_file()
    assert list((ocr_dir / "crops").glob("*_bottom.jpg"))

    frame_ocr = json.loads((ocr_dir / "frame_ocr.json").read_text(encoding="utf-8"))
    subtitle_ocr = json.loads((ocr_dir / "subtitle_ocr.json").read_text(encoding="utf-8"))
    cover_ocr = json.loads((ocr_dir / "cover_ocr.json").read_text(encoding="utf-8"))
    assert "封面承诺" in frame_ocr["full_text"]
    assert "先抓住前三秒" in subtitle_ocr["full_text"]
    assert cover_ocr["source"] == "first_keyframe"

    manifest = json.loads((case_dir / "enrichment" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["statuses"]["ocr"] == "success"

    enrichment_response = client.get(f"/api/cases/{case_id}/enrichment")
    assert enrichment_response.status_code == 200
    enrichment = enrichment_response.json()["enrichment"]
    assert enrichment["ocr_status"]["status"] == "success"
    assert "封面承诺" in enrichment["ocr_frame"]["full_text"]
    assert "先抓住前三秒" in enrichment["ocr_subtitle"]["full_text"]
    enriched_input = json.loads((case_dir / "analysis_input.json").read_text(encoding="utf-8"))
    assert "封面承诺" in enriched_input["analysis_enrichment"]["ocr"]["frame_text"]
    assert "先抓住前三秒" in enriched_input["analysis_enrichment"]["ocr"]["subtitle_text"]

    detail_response = client.get(f"/api/cases/{case_id}")
    assert detail_response.status_code == 200
    rerun_evidence = detail_response.json()["case"]["manual_review_context"]["rerun_strategy"]["required_evidence"]
    ocr_evidence = next(item for item in rerun_evidence if item["id"] == "ocr")
    assert ocr_evidence["status"] == "success"
    assert ocr_evidence["char_count"] >= len("封面承诺")
    assert set(ocr_evidence["sources"]) >= {"frame", "subtitle", "cover"}
    assert "封面承诺" in ocr_evidence["excerpt"]


def test_auto_analyzer_uses_asr_ocr_and_comment_enrichment(tmp_path: Path) -> None:
    video_path = make_sample_video_with_audio(tmp_path / "rich-analysis.mp4")
    local_video = upload_video(video_path, source_url="https://www.douyin.com/video/7651938969785849444")
    case_response = client.post("/api/cases/build", json={"local_video_id": local_video["local_video_id"]})
    assert case_response.status_code == 200
    case_id = case_response.json()["case"]["case_id"]

    class FakeASRProvider:
        provider_name = "fake-asr"

        def transcribe(self, audio_path):
            return {
                "provider": self.provider_name,
                "model": "mock",
                "language": "zh",
                "segments": [
                    {"index": 0, "start": 0.0, "end": 1.8, "text": "真正厉害的人会先抓住前三秒", "confidence": 0.95}
                ],
                "full_text": "真正厉害的人会先抓住前三秒",
            }

    class FakeOCRProvider:
        provider_name = "fake-ocr"

        def recognize(self, image_path):
            if "bottom" in Path(image_path).name:
                return [{"text": "先抓住前三秒", "bbox": [0, 120, 320, 200], "confidence": 0.93}]
            return [{"text": "封面承诺", "bbox": [10, 20, 200, 80], "confidence": 0.91}]

    db = SessionLocal()
    try:
        artifact = db.get(CaseArtifact, case_id)
        run_case_asr(artifact, provider=FakeASRProvider())
        run_case_ocr(artifact, provider=FakeOCRProvider())
    finally:
        db.close()

    comments_response = client.post(
        f"/api/cases/{case_id}/comments/import",
        json={"text": "求同款链接\n接好运\n真实扎心", "source": "manual"},
    )
    assert comments_response.status_code == 200

    class FakeRichLLMProvider:
        def analyze(self, prompt, image_paths):
            assert image_paths
            assert "analysis_enrichment" in prompt
            assert "真正厉害的人会先抓住前三秒" in prompt
            assert "封面承诺" in prompt
            assert "先抓住前三秒" in prompt
            assert "求同款/购买线索" in prompt
            assert "evidence_summary" in prompt
            assert "证据不足的结论必须放入 inferred_points 或 evidence_gaps" in prompt
            assert "first_3_seconds 至少写两个具体时间点" in prompt
            assert "publish_package 不能只有标题" in prompt
            assert "replication.avoid_copying 或 risks 必须说明不要照搬" in prompt
            assert "replication.copyable_points 每一条都必须能追溯" in prompt
            assert "不要凭空新增原视频没有的镜头" in prompt
            return {
                "summary": "这条视频用前三秒人物入镜、金句口播和封面承诺形成强停留，评论区求同款说明可复刻需求明确。",
                "content_category": "generic",
                "content_category_label": "通用短视频",
                "confidence": 0.9,
                "hook_analysis": {
                    "first_impression": "开头主体直接进入画面",
                    "why_stop_scrolling": "第一秒给出强视觉主体和金句口播",
                    "first_3_seconds": ["0s 人物近景居中出现", "1s 金句开场", "2s 字幕强化"],
                    "optimization": "前三秒保留主体和文字承诺",
                },
                "visual_analysis": {
                    "scene": "室内短视频场景",
                    "subject": "画面主体清晰",
                    "composition": "主体居中",
                    "lighting_color": "明亮",
                    "movement_rhythm": "前三秒节奏紧凑",
                    "style_keywords": ["强主体", "短句"],
                },
                "copywriting_analysis": {
                    "title_click_reason": "标题承诺清晰",
                    "subtitle_or_text_role": "字幕强化钩子",
                    "comment_trigger": "引导用户接好运和求同款",
                    "reusable_patterns": ["金句开场 + 评论承接"],
                },
                "speech_analysis": {
                    "has_speech": True,
                    "opening_line": "真正厉害的人会先抓住前三秒",
                    "spoken_hook": "直接给出能力判断",
                    "script_structure": "金句开场",
                    "quotable_lines": ["真正厉害的人会先抓住前三秒"],
                },
                "screen_text_analysis": {
                    "cover_text_role": "封面承诺",
                    "subtitle_text_role": "强化前三秒",
                    "screen_text_patterns": ["短句承诺"],
                    "text_visual_conflicts": [],
                },
                "comment_insights": {
                    "audience_needs": ["求同款/购买线索"],
                    "comment_triggers": ["接好运"],
                    "high_frequency_words": ["同款", "好运"],
                    "replicable_interaction_design": "引导用户在评论区接好运和问链接",
                },
                "emotion_path": ["开头抓注意", "中段给价值", "结尾引导互动"],
                "content_ratio": detailed_content_ratio(),
                "timeline": [{"time_range": "0-2s", "visual": "主体和字幕出现", "purpose": "抓注意力"}],
                "replication": {
                    "copyable_points": ["金句开场", "字幕强化", "评论引导"],
                    "avoid_copying": detailed_avoid_copying(),
                    "remake_angle": "换成自己的角色和场景复刻结构",
                    "opening_3s": "第一秒给出角色和金句",
                    "shot_table": [
                        {
                            "time": "0-2s",
                            "visual": "角色正面入镜",
                            "action": "看镜头",
                            "subtitle": "先抓住前三秒",
                            "music_rhythm": "鼓点进入",
                            "purpose": "停留",
                        }
                    ],
                },
                "publish_package": {
                    "titles": ["真正厉害的人，都懂前三秒"],
                    "caption": "把钩子做扎实。",
                    "hashtags": ["短视频拆解"],
                    "pinned_comment": "你会停在哪一秒？",
                },
                "enrichment_usage": {
                    "asr_used": True,
                    "ocr_used": True,
                    "comments_used": True,
                    "notes": ["使用了 ASR/OCR/评论摘要"],
                },
                "evidence_summary": {
                    "visual_input_mode": "multi_image",
                        "visual_evidence": [
                            {
                                "claim": "前三秒以画面主体吸引",
                                    "evidence": "contact_sheet 0-2s 显示主体连续入镜并配合字幕推进",
                                "confidence": "high",
                            }
                        ],
                    "asr_evidence": [
                        {
                            "claim": "口播以金句开场",
                            "evidence": "真正厉害的人会先抓住前三秒",
                            "confidence": "high",
                        }
                    ],
                    "ocr_evidence": [
                        {
                            "claim": "封面字和字幕共同强化前三秒承诺",
                            "evidence": "OCR 识别到封面承诺和底部字幕“先抓住前三秒”",
                            "confidence": "high",
                        }
                    ],
                    "comment_evidence": [
                        {"claim": "评论区存在求同款需求", "evidence": "求同款/购买线索", "confidence": "high"}
                    ],
                    "inferred_points": [],
                    "evidence_gaps": [],
                },
            }

    db = SessionLocal()
    try:
        artifact = db.get(CaseArtifact, case_id)
        analysis = analyze_case_artifact(artifact, provider=FakeRichLLMProvider())
    finally:
        db.close()

    result = analysis["analysis_result"]
    assert result["summary"] == "这条视频用前三秒人物入镜、金句口播和封面承诺形成强停留，评论区求同款说明可复刻需求明确。"
    assert result["speech_analysis"]["opening_line"] == "真正厉害的人会先抓住前三秒"
    assert result["screen_text_analysis"]["cover_text_role"] == "封面承诺"
    assert result["comment_insights"]["audience_needs"] == ["求同款/购买线索"]
    assert result["enrichment_usage"]["asr_used"] is True
    assert result["enrichment_coverage"]["items"]["asr"]["verdict"] == "used"
    assert result["enrichment_coverage"]["items"]["ocr"]["verdict"] == "used"
    assert result["enrichment_coverage"]["items"]["comments"]["verdict"] == "used"
    assert result["enrichment_coverage"]["summary"]["blocking_count"] == 0
    assert result["evidence_summary"]["visual_input_mode"] == "multi_image"
    assert result["evidence_summary"]["visual_evidence"][0]["claim"] == "前三秒以画面主体吸引"
    assert result["evidence_summary"]["asr_evidence"][0]["evidence"] == "真正厉害的人会先抓住前三秒"
    assert result["quality_review"]["level"] == "strong"
    assert result["quality_review"]["score"] >= 85
    assert not result["quality_review"]["gaps"]
    assert "## 语音/口播拆解" in analysis["analysis_report"]
    assert "## 画面文字/OCR 拆解" in analysis["analysis_report"]
    assert "## 评论反馈洞察" in analysis["analysis_report"]
    assert "## 证据与推断边界" in analysis["analysis_report"]
    assert "## 富化证据使用核对" in analysis["analysis_report"]
    assert "## 拆解质量自检" in analysis["analysis_report"]
    assert "ASR 证据" in analysis["analysis_report"]

    detail_response = client.get(f"/api/cases/{case_id}")
    assert detail_response.status_code == 200
    detail_case = detail_response.json()["case"]
    readiness = detail_case["analysis_readiness"]
    assert readiness["level"] == "high"
    assert readiness["score"] >= 85
    assert not any(gap["id"] in {"speech_asr", "screen_ocr", "comments", "ai_report"} for gap in readiness["improvement_gaps"])
    assert readiness["next_action_items"] == []
    diagnosis = detail_case["case_diagnosis"]
    assert diagnosis["status"] == "reviewable"
    assert diagnosis["score"]["quality"] >= 85
    assert diagnosis["score"]["enrichment_blocking"] == 0
    assert diagnosis["blockers"] == []
    assert diagnosis["primary_actions"][0]["target"] == "#quality-acceptance-verdict"
    assert diagnosis["primary_actions"][0]["mode"] == "focus"

    script = Path("app/static/case_detail.js").read_text(encoding="utf-8")
    assert "renderAutoAnalysisCards" in script
    assert "语音/口播" in script
    assert "画面文字/OCR" in script
    assert "评论反馈" in script
    assert "renderShotTable" in script
    assert "证据与推断边界" in script
    assert "evidence-card" in script
    assert "拆解质量自检" in script
    assert "quality-card" in script
    assert "renderQualityChecks" in script
    assert "renderAutoAnalysisOverview" in script
    assert "analysis-trust-panel" in script
    assert "证据覆盖" in script
    assert "富化证据使用" in script
    assert "renderEnrichmentCoverage" in script
    assert "coverageVerdictLabels" in script
    assert "准备度关键缺口" in script
    assert "关键缺口与下一步" in script
    assert "无关键缺口" in script
    assert "富化说明" in script
    assert "enrichmentUsage.notes" in script
    assert "renderReadinessActionButton" in script
    assert "activateReadinessTarget" in script
    assert "data-action-target" in script
    assert "data-action-mode" in script
    assert "target.click()" in script
    stylesheet = Path("app/static/app.css").read_text(encoding="utf-8")
    assert ".analysis-trust-panel" in stylesheet
    assert ".analysis-trust-grid" in stylesheet
    assert ".evidence-pill" in stylesheet
    assert ".enrichment-coverage-item" in stylesheet


def test_evidence_summary_fills_empty_model_lists_from_case_enrichment() -> None:
    analysis_input = {
        "assets": {"keyframes": [{"path": "outputs/cases/case_demo/keyframes/frame_0000_00.00s.jpg"}]},
        "analysis_enrichment": {
            "asr": {"full_text": "真正厉害的人会先抓住前三秒"},
            "ocr": {"cover_text": "封面承诺", "subtitle_text": "先抓住前三秒", "frame_text": ""},
            "comments": {
                "total_comments": 2,
                "top_needs": ["求同款/购买线索"],
                "high_frequency_words": ["同款", "好运"],
                "comment_hooks": ["接好运"],
            },
        },
    }
    result = auto_analyzer._normalize_evidence_summary(
        {
            "visual_input_mode": "multi_image",
            "visual_evidence": [],
            "asr_evidence": [],
            "ocr_evidence": [],
            "comment_evidence": [],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        analysis_input,
        "multi_image",
    )

    assert result["visual_evidence"][0]["claim"] == "画面主体、节奏和分镜判断"
    assert "真正厉害的人" in result["asr_evidence"][0]["evidence"]
    assert "封面承诺" in result["ocr_evidence"][0]["evidence"]
    assert "求同款/购买线索" in result["comment_evidence"][0]["evidence"]


def test_evidence_summary_preserves_contact_sheet_visual_evidence() -> None:
    analysis_input = {
        "assets": {"keyframes": [{"path": "outputs/cases/case_demo/keyframes/frame_0000_00.00s.jpg"}]},
        "analysis_enrichment": {
            "asr": {"full_text": "第一句直接抛出结果承诺"},
            "ocr": {"cover_text": "封面字：三秒学会"},
            "comments": {
                "total_comments": 2,
                "top_needs": ["求教程"],
                "high_frequency_words": ["教程"],
                "comment_hooks": ["求下一版"],
            },
        },
    }
    result = auto_analyzer._normalize_evidence_summary(
        {
            "visual_evidence": [
                {
                    "claim": "开头使用近景人物和大幅动作制造停留",
                    "evidence": "contact_sheet 0-2s 可见人物居中并快速抬手",
                    "confidence": "medium",
                }
            ],
            "evidence_gaps": [],
        },
        analysis_input,
        "contact_sheet_only",
    )

    assert result["visual_evidence"][0]["claim"] == "开头使用近景人物和大幅动作制造停留"
    assert any("只使用 contact_sheet" in gap for gap in result["evidence_gaps"])


def test_evidence_summary_coerces_string_and_object_evidence() -> None:
    analysis_input = {
        "assets": {"keyframes": [{"path": "outputs/cases/case_demo/keyframes/frame_0000_00.00s.jpg"}]},
        "analysis_enrichment": {
            "asr": {"full_text": "第一句直接抛出结果承诺"},
            "ocr": {"cover_text": "封面字：三秒学会"},
            "comments": {
                "total_comments": 2,
                "top_needs": ["求教程"],
                "high_frequency_words": ["教程"],
                "comment_hooks": ["求下一版"],
            },
        },
    }
    result = auto_analyzer._normalize_evidence_summary(
        {
            "visual_input_mode": "multi_image",
            "visual_evidence": "contact_sheet 显示 0-2s 人物居中并抬手。",
            "asr_evidence": {"claim": "口播开头", "text": "第一句直接抛出结果承诺", "confidence": "HIGH"},
            "ocr_evidence": [{"value": "封面字：三秒学会"}],
            "comment_evidence": "评论区多次出现求教程。",
            "inferred_points": "推断适合教程类复刻；需要人工确认节奏",
            "evidence_gaps": "评论样本较少",
        },
        analysis_input,
        "multi_image",
    )

    assert result["visual_evidence"][0] == {
        "claim": "视觉证据",
        "evidence": "contact_sheet 显示 0-2s 人物居中并抬手。",
        "confidence": "medium",
    }
    assert result["asr_evidence"][0]["claim"] == "口播开头"
    assert result["asr_evidence"][0]["evidence"] == "第一句直接抛出结果承诺"
    assert result["asr_evidence"][0]["confidence"] == "high"
    assert result["ocr_evidence"][0]["evidence"] == "封面字：三秒学会"
    assert result["comment_evidence"][0]["evidence"] == "评论区多次出现求教程。"
    assert result["inferred_points"] == ["推断适合教程类复刻", "需要人工确认节奏"]
    assert "评论样本较少" in result["evidence_gaps"]


def test_evidence_summary_ignores_empty_or_placeholder_evidence_items() -> None:
    analysis_input = {
        "assets": {"keyframes": [{"path": "outputs/cases/case_demo/keyframes/frame_0000_00.00s.jpg"}]},
        "analysis_enrichment": {
            "asr": {"full_text": "开头口播直接给结果。"},
            "ocr": {"cover_text": "三秒学会"},
            "comments": {
                "total_comments": 1,
                "top_needs": ["求教程"],
                "high_frequency_words": ["教程"],
                "comment_hooks": ["求下一版"],
            },
        },
    }
    result = auto_analyzer._normalize_evidence_summary(
        {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{}],
            "asr_evidence": [{"claim": "口播证据", "evidence": "待补充"}],
            "ocr_evidence": [{"claim": "OCR 证据"}],
            "comment_evidence": ["暂无"],
            "inferred_points": ["待补充"],
            "evidence_gaps": ["暂无"],
        },
        analysis_input,
        "multi_image",
    )

    assert result["visual_evidence"][0]["claim"] == "画面主体、节奏和分镜判断"
    assert result["asr_evidence"][0]["evidence"] == "开头口播直接给结果。"
    assert result["ocr_evidence"][0]["evidence"] == "三秒学会"
    assert "求教程" in result["comment_evidence"][0]["evidence"]
    assert result["inferred_points"] == []
    assert "暂无" not in result["evidence_gaps"]


def test_evidence_summary_flags_empty_comment_summary_even_when_comments_exist() -> None:
    analysis_input = {
        "assets": {"keyframes": [{"path": "outputs/cases/case_demo/keyframes/frame_0000_00.00s.jpg"}]},
        "analysis_enrichment": {
            "asr": {"full_text": "开头口播直接给结果。"},
            "ocr": {"cover_text": "三秒学会"},
            "comments": {
                "total_comments": 3,
                "top_needs": [],
                "high_frequency_words": [],
                "comment_hooks": [],
            },
        },
    }

    result = auto_analyzer._normalize_evidence_summary(None, analysis_input, "multi_image")

    assert result["comment_evidence"] == []
    assert any("评论摘要为空" in gap for gap in result["evidence_gaps"])


def test_default_enrichment_usage_does_not_mark_empty_comment_summary_as_used() -> None:
    usage = auto_analyzer._default_enrichment_usage(
        {
            "analysis_enrichment": {
                "comments": {
                    "total_comments": 5,
                    "top_needs": [],
                    "high_frequency_words": ["待补充"],
                    "comment_hooks": [],
                }
            }
        }
    )

    assert usage["comments_used"] is False
    assert any("评论摘要为空" in note for note in usage["notes"])


def test_default_enrichment_usage_explains_checked_empty_asr_and_ocr() -> None:
    usage = auto_analyzer._default_enrichment_usage(
        {
            "analysis_enrichment": {
                "asr": {"status": "no_speech", "full_text": ""},
                "ocr": {"status": "no_text", "frame_text": "", "subtitle_text": "", "cover_text": ""},
                "comments": {
                    "total_comments": 1,
                    "top_needs": ["求教程"],
                    "high_frequency_words": ["教程"],
                    "comment_hooks": ["催更"],
                },
            }
        }
    )

    assert usage["asr_used"] is False
    assert usage["ocr_used"] is False
    assert usage["comments_used"] is True
    assert any("ASR 已检测" in note for note in usage["notes"])
    assert any("OCR 已检测" in note for note in usage["notes"])
    assert not any("未提供 ASR" in note for note in usage["notes"])
    assert not any("未提供 OCR" in note for note in usage["notes"])


def test_evidence_summary_ignores_placeholder_asr_ocr_and_comment_summaries() -> None:
    analysis_input = {
        "assets": {"keyframes": [{"path": "outputs/cases/case_demo/keyframes/frame_0000_00.00s.jpg"}]},
        "analysis_enrichment": {
            "asr": {"status": "success", "full_text": "待补充"},
            "ocr": {"status": "success", "cover_text": "暂无", "subtitle_text": "待填写", "frame_text": ""},
            "comments": {
                "total_comments": 4,
                "top_needs": ["暂无"],
                "high_frequency_words": ["待补充"],
                "comment_hooks": ["未提供"],
            },
        },
    }

    result = auto_analyzer._normalize_evidence_summary(None, analysis_input, "multi_image")
    usage = auto_analyzer._default_enrichment_usage(analysis_input)

    assert result["asr_evidence"] == []
    assert result["ocr_evidence"] == []
    assert result["comment_evidence"] == []
    assert any("ASR 已完成但转写文本为空或无效" in gap for gap in result["evidence_gaps"])
    assert any("OCR 已完成但识别文本为空或无效" in gap for gap in result["evidence_gaps"])
    assert any("评论摘要为空" in gap for gap in result["evidence_gaps"])
    assert usage["asr_used"] is False
    assert usage["ocr_used"] is False
    assert usage["comments_used"] is False


def test_evidence_summary_treats_no_speech_and_no_text_as_checked_states() -> None:
    analysis_input = {
        "assets": {"keyframes": [{"path": "outputs/cases/case_demo/keyframes/frame_0000_00.00s.jpg"}]},
        "analysis_enrichment": {
            "asr": {"status": "no_speech", "full_text": ""},
            "ocr": {"status": "no_text", "cover_text": "", "subtitle_text": "", "frame_text": ""},
            "comments": {
                "total_comments": 1,
                "top_needs": ["情绪共鸣"],
                "high_frequency_words": ["好看"],
                "comment_hooks": ["夸画面"],
            },
        },
    }

    result = auto_analyzer._normalize_evidence_summary(None, analysis_input, "multi_image")

    assert result["asr_evidence"][0]["confidence"] == "high"
    assert "未检测到可转写语音" in result["asr_evidence"][0]["evidence"]
    assert result["ocr_evidence"][0]["confidence"] == "high"
    assert "未检测到封面字" in result["ocr_evidence"][0]["evidence"]
    assert not any("未提供 ASR" in gap for gap in result["evidence_gaps"])
    assert not any("未提供 OCR" in gap for gap in result["evidence_gaps"])


def test_rerun_evidence_completion_treats_unknown_status_as_missing() -> None:
    required_evidence = [
        {"id": "asr", "label": "ASR 转写", "status": "success"},
        {"id": "comments", "label": "评论摘要", "status": ""},
        {"id": "ocr", "label": "OCR 文字", "status": "failed"},
        {"id": "metrics", "label": "指标快照"},
    ]

    evidence_summary = auto_analyzer._rerun_evidence_summary(required_evidence)
    calibration_summary = case_routes._quality_calibration_summary(
        [{"rerun_strategy": {"required_evidence": required_evidence, "evidence_summary": evidence_summary}}]
    )

    assert evidence_summary["ready"] == 1
    assert evidence_summary["missing"] == 3
    assert evidence_summary["complete"] is False
    assert evidence_summary["missing_ids"] == ["comments", "ocr", "metrics"]
    assert calibration_summary["evidence_completion"]["with_required_evidence"] == 1
    assert calibration_summary["evidence_completion"]["complete_records"] == 0
    assert calibration_summary["evidence_completion"]["missing_records"] == 1
    assert calibration_summary["evidence_completion"]["ready_items"] == 1
    assert calibration_summary["evidence_completion"]["missing_items"] == 3


def test_enrichment_coverage_flags_checked_empty_conflicts() -> None:
    result = {
        "summary": "模型在空检测下仍输出了口播和字幕洞察。",
        "confidence": 0.8,
        "hook_analysis": {
            "first_impression": "开头主体出现",
            "why_stop_scrolling": "动作和字幕吸引",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "speech_analysis": {"opening_line": "模型编出的口播"},
        "screen_text_analysis": {"cover_text_role": "模型编出的封面字作用"},
        "comment_insights": {},
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧显示主体动作", "confidence": "high"}],
            "asr_evidence": [],
            "ocr_evidence": [],
            "comment_evidence": [],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "timeline": detailed_timeline(),
        "replication": {
            "copyable_points": ["近景开头"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "换成自己的角色",
            "opening_3s": "主体先出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }
    analysis_input = {
        "content_category": "generic",
        "content_category_label": "通用短视频",
        "stats": {"like_count": 10, "comment_count": 0, "share_count": 1},
        "video": {},
        "assets": {"keyframes": [{"path": "outputs/cases/case_demo/keyframes/frame_0000_00.00s.jpg"}]},
        "analysis_enrichment": {
            "asr": {"status": "no_speech", "full_text": ""},
            "ocr": {"status": "no_text", "cover_text": "", "subtitle_text": "", "frame_text": ""},
            "comments": {"status": "pending", "total_comments": 0},
        },
    }

    normalized = auto_analyzer._normalize_result(
        result,
        metadata={"title": "测试"},
        ffprobe={},
        analysis_input=analysis_input,
        analysis_context={"category_id": "generic", "label": "通用短视频"},
        visual_input_mode="multi_image",
    )

    coverage = normalized["enrichment_coverage"]
    assert coverage["items"]["asr"]["verdict"] == "insight_without_evidence"
    assert coverage["items"]["ocr"]["verdict"] == "insight_without_evidence"
    assert coverage["summary"]["blocking_count"] == 2
    assert any(gap["id"] == "enrichment_usage" for gap in normalized["quality_review"]["gaps"])


def test_case_diagnosis_prioritizes_enrichment_mismatch() -> None:
    analysis_result = {
        "quality_review": {"score": 82, "gaps": []},
        "enrichment_coverage": {
            "summary": {"blocking_count": 1},
            "items": {
                "asr": {
                    "label": "语音 / ASR",
                    "verdict": "available_not_used",
                    "message": "ASR 转写已可用，但报告没有把它作为有效口播证据使用。",
                    "action": "基于 ASR 转写补充口播拆解后重跑。",
                }
            },
        },
    }
    readiness = {"score": 90, "critical_gaps": []}
    calibration = {
        "status": "awaiting_review",
        "summary": "等待人工验收",
        "human_acceptance": {"blocker_count": 0, "blockers": []},
        "next_actions": [],
    }

    diagnosis = case_routes._case_diagnosis_payload(analysis_result, readiness, calibration)

    assert diagnosis["status"] == "enrichment_mismatch"
    assert diagnosis["score"]["enrichment_blocking"] == 1
    assert diagnosis["blockers"][0]["source"] == "enrichment"
    assert "ASR 转写已可用" in diagnosis["blockers"][0]["message"]
    assert diagnosis["primary_actions"][0]["target"] == "#run-auto-analysis-button"
    assert diagnosis["primary_actions"][0]["mode"] == "focus"
    assert any(action["target"] == "#auto-analysis-summary" for action in diagnosis["primary_actions"])


def test_case_diagnosis_prioritizes_saving_accepted_calibration_sample() -> None:
    analysis_result = {
        "quality_review": {
            "score": 92,
            "gaps": [],
            "summary": "拆解质量较完整",
        },
        "enrichment_coverage": {"summary": {"blocking_count": 0}, "items": {}},
    }
    readiness = {"score": 90, "critical_gaps": []}
    calibration = {
        "status": "accepted",
        "summary": "AI 拆解已通过人工验收，可以作为样例沉淀。",
        "human_acceptance": {"blocker_count": 0, "blockers": []},
        "next_actions": [],
    }

    diagnosis = case_routes._case_diagnosis_payload(analysis_result, readiness, calibration)

    assert diagnosis["status"] == "accepted"
    assert diagnosis["primary_actions"][0]["target"] == "#save-quality-calibration-record-button"
    assert diagnosis["primary_actions"][0]["label"] == "保存校准样本"
    assert diagnosis["primary_actions"][0]["mode"] == "click"


def test_case_readiness_explains_no_speech_and_no_text_as_checked_states(tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "checked-empty.mp4")
    local_video = upload_video(video_path, source_url="https://www.douyin.com/video/7651938969785849777")
    case_response = client.post("/api/cases/build", json={"local_video_id": local_video["local_video_id"]})
    assert case_response.status_code == 200
    case_id = case_response.json()["case"]["case_id"]

    db = SessionLocal()
    try:
        artifact = db.get(CaseArtifact, case_id)
        case_dir = Path(artifact.video_path).parent
        asr_dir = case_dir / "enrichment" / "asr"
        ocr_dir = case_dir / "enrichment" / "ocr"
        asr_dir.mkdir(parents=True, exist_ok=True)
        ocr_dir.mkdir(parents=True, exist_ok=True)
        (asr_dir / "transcript.json").write_text(
            json.dumps({"status": "no_speech", "full_text": "", "segments": []}, ensure_ascii=False),
            encoding="utf-8",
        )
        (ocr_dir / "frame_ocr.json").write_text(
            json.dumps({"status": "no_text", "full_text": "", "frames": []}, ensure_ascii=False),
            encoding="utf-8",
        )
        (ocr_dir / "subtitle_ocr.json").write_text(
            json.dumps({"status": "no_text", "full_text": "", "frames": []}, ensure_ascii=False),
            encoding="utf-8",
        )
        (ocr_dir / "cover_ocr.json").write_text(
            json.dumps({"status": "no_text", "full_text": ""}, ensure_ascii=False),
            encoding="utf-8",
        )
    finally:
        db.close()

    response = client.get(f"/api/cases/{case_id}")
    assert response.status_code == 200
    checks = response.json()["case"]["analysis_readiness"]["checks"]
    asr_check = next(check for check in checks if check["id"] == "speech_asr")
    ocr_check = next(check for check in checks if check["id"] == "screen_ocr")
    assert asr_check["ready"] is True
    assert "已检测" in asr_check["message"]
    assert "尚未" not in asr_check["message"]
    assert ocr_check["ready"] is True
    assert "已检测" in ocr_check["message"]
    assert "尚未" not in ocr_check["message"]


def test_case_readiness_missing_comments_does_not_report_high(tmp_path: Path) -> None:
    class DummyArtifact:
        pass

    for filename in [
        "video.mp4",
        "metadata.json",
        "ffprobe.json",
        "contact_sheet.jpg",
        "analysis_input.json",
        "prompt.md",
    ]:
        (tmp_path / filename).write_text("ready", encoding="utf-8")

    artifact = DummyArtifact()
    artifact.video_path = str(tmp_path / "video.mp4")
    artifact.metadata_path = str(tmp_path / "metadata.json")
    artifact.ffprobe_path = str(tmp_path / "ffprobe.json")
    artifact.contact_sheet_path = str(tmp_path / "contact_sheet.jpg")
    artifact.analysis_input_path = str(tmp_path / "analysis_input.json")
    artifact.prompt_path = str(tmp_path / "prompt.md")

    analysis_input = {
        "content_category": "generic",
        "content_category_label": "通用短视频",
        "analysis_context": {"category_id": "generic"},
        "analysis_enrichment": {
            "asr": {"status": "success", "full_text": "开头口播直接抛出情绪钩子。"},
            "ocr": {"status": "success", "frame_text": "封面大字", "subtitle_text": "", "cover_text": ""},
            "comments": {"status": "pending", "total_comments": 0},
            "metrics": {"status": "success", "snapshot_count": 1},
        },
    }

    readiness = case_routes._analysis_readiness_payload(
        artifact,
        ["frame_0000_00.00s.jpg"],
        analysis_input,
        {},
        {"summary": "AI report exists"},
    )

    assert readiness["score"] == 85
    assert readiness["level"] == "ready"
    assert readiness["label"] == "可开始分析"
    assert any(gap["id"] == "comments" for gap in readiness["critical_gaps"])
    assert any(gap["id"] == "comments" for gap in readiness["improvement_gaps"])
    assert any(item["target"] == "#comments-import-text" for item in readiness["next_action_items"])


def test_case_readiness_accepts_usable_manual_worksheet_as_analysis_output(tmp_path: Path) -> None:
    class DummyArtifact:
        pass

    for filename in [
        "video.mp4",
        "metadata.json",
        "ffprobe.json",
        "contact_sheet.jpg",
        "analysis_input.json",
        "prompt.md",
    ]:
        (tmp_path / filename).write_text("ready", encoding="utf-8")

    artifact = DummyArtifact()
    artifact.video_path = str(tmp_path / "video.mp4")
    artifact.metadata_path = str(tmp_path / "metadata.json")
    artifact.ffprobe_path = str(tmp_path / "ffprobe.json")
    artifact.contact_sheet_path = str(tmp_path / "contact_sheet.jpg")
    artifact.analysis_input_path = str(tmp_path / "analysis_input.json")
    artifact.prompt_path = str(tmp_path / "prompt.md")

    analysis_input = {
        "content_category": "generic",
        "content_category_label": "通用短视频",
        "analysis_context": {"category_id": "generic"},
        "analysis_enrichment": {
            "asr": {"status": "no_speech", "full_text": ""},
            "ocr": {"status": "no_text", "frame_text": "", "subtitle_text": "", "cover_text": ""},
            "comments": {"status": "success", "total_comments": 3},
            "metrics": {"status": "success", "snapshot_count": 1},
        },
    }

    readiness = case_routes._analysis_readiness_payload(
        artifact,
        ["frame_0000_00.00s.jpg"],
        analysis_input,
        {},
        None,
        {"score": 75, "level": "usable", "label": "人工拆解可用"},
    )

    output_check = next(check for check in readiness["checks"] if check["id"] == "analysis_output")
    assert output_check["ready"] is True
    assert output_check["status"] == "manual_worksheet"
    assert "人工工作表" in output_check["message"]
    assert readiness["level"] == "high"
    assert not readiness["critical_gaps"]


def test_evidence_summary_downgrades_visual_claims_for_contact_sheet_only_mode() -> None:
    analysis_input = {
        "assets": {"keyframes": [{"path": "outputs/cases/case_demo/keyframes/frame_0000_00.00s.jpg"}]},
        "analysis_enrichment": {},
    }

    result = auto_analyzer._normalize_evidence_summary(
        {
            "visual_input_mode": "multi_image",
            "visual_evidence": [
                {
                    "claim": "逐帧细节动作判断",
                    "evidence": "模型声称看到了所有关键帧",
                    "confidence": "high",
                }
            ],
            "asr_evidence": [],
            "ocr_evidence": [],
            "comment_evidence": [],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        analysis_input,
        "contact_sheet_only",
    )

    assert result["visual_input_mode"] == "contact_sheet_only"
    assert result["visual_evidence"][0]["claim"] == "整体画面节奏和关键帧变化"
    assert result["visual_evidence"][0]["confidence"] == "medium"
    assert "逐帧细节动作判断" not in json.dumps(result["visual_evidence"], ensure_ascii=False)
    assert any("只使用 contact_sheet" in gap for gap in result["evidence_gaps"])


def test_auto_analyzer_marks_contact_sheet_only_when_keyframes_are_unavailable(tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "contact-only.mp4")
    local_video = upload_video(video_path, source_url="https://www.douyin.com/video/7651938969785849566")
    case_response = client.post("/api/cases/build", json={"local_video_id": local_video["local_video_id"]})
    assert case_response.status_code == 200
    case_id = case_response.json()["case"]["case_id"]
    keyframes_dir = Path(case_response.json()["case"]["keyframes_dir"])
    for keyframe in keyframes_dir.glob("frame_*.jpg"):
        keyframe.unlink()

    class FakeContactOnlyProvider:
        def analyze(self, prompt, image_paths):
            assert len(image_paths) == 1
            assert Path(image_paths[0]).name == "contact_sheet.jpg"
            return {
                "summary": "仅使用 contact sheet 的拆解",
                "evidence_summary": {
                    "visual_input_mode": "multi_image",
                    "visual_evidence": [],
                    "asr_evidence": [],
                    "ocr_evidence": [],
                    "comment_evidence": [],
                    "inferred_points": [],
                    "evidence_gaps": [],
                },
            }

    db = SessionLocal()
    try:
        artifact = db.get(CaseArtifact, case_id)
        analysis = analyze_case_artifact(artifact, provider=FakeContactOnlyProvider())
    finally:
        db.close()

    evidence = analysis["analysis_result"]["evidence_summary"]
    assert evidence["visual_input_mode"] == "contact_sheet_only"
    assert evidence["visual_evidence"][0]["confidence"] == "medium"
    assert any("只使用 contact_sheet" in gap for gap in evidence["evidence_gaps"])


def test_quality_review_requires_comment_evidence_for_audience_check() -> None:
    result = {
        "summary": "模型写了看似完整的拆解",
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": {
            "scene": "室内近景，背景留白突出主体",
            "subject": "人物居中看镜头，字幕贴近主体出现",
            "movement_rhythm": "0-2s 从静止到抬手，节奏逐秒推进",
        },
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [
                {
                    "claim": "前三秒靠人物近景和姿态变化制造停留",
                    "evidence": "0-3s 关键帧显示人物近景居中，1s 姿态变化，2s 镜头轻微推进",
                    "confidence": "high",
                }
            ],
            "asr_evidence": [],
            "ocr_evidence": [],
            "comment_evidence": [],
            "inferred_points": [],
            "evidence_gaps": ["未导入评论，用户需求和评论触发点只能作为推断。"],
        },
        "timeline": [{"time_range": "0-3s", "visual": "人物近景出现，字幕和抬手动作同步推进", "purpose": "停留"}],
        "replication": {
            "copyable_points": ["前三秒主体"],
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    audience_check = next(check for check in review["checks"] if check["id"] == "audience")
    assert audience_check["passed"] is False
    assert any(item["id"] == "audience_comment_evidence_missing" for item in audience_check["details"])
    assert any(item["id"] == "audience_insight_without_evidence" for item in audience_check["details"])
    assert any(gap["id"] == "audience" for gap in review["gaps"])
    assert review["score"] <= 90
    assert review["level"] == "usable"


def test_rerun_compliance_flags_unanswered_feedback_constraints() -> None:
    result = {
        "summary": "模型写了看似完整的拆解",
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": {},
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [
                {"claim": "视觉", "evidence": "关键帧显示主体动作", "confidence": "high"}
            ],
            "asr_evidence": [],
            "ocr_evidence": [],
            "comment_evidence": [],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "replication": {
            "copyable_points": ["主体开头"],
            "remake_angle": "复刻开头",
            "opening_3s": "主体出现",
            "shot_table": [],
        },
        "publish_package": detailed_publish_package(),
        "next_actions": [],
        "manual_review_context": {
            "rerun_strategy": {
                "active": True,
                "priority": "high",
                "required_evidence": [
                    {
                        "id": "comments",
                        "label": "评论摘要",
                        "status": "missing",
                        "instruction": "本次仍缺评论；不要编造用户反馈。",
                    }
                ],
                "fix_targets": [
                    {
                        "id": "shot_table_is_actionable",
                        "label": "分镜表是否可执行",
                        "instruction": "修正不可执行分镜。",
                    }
                ],
                "output_requirements": ["next_actions 必须说明本次重跑后仍缺什么。"],
            }
        },
    }

    compliance = auto_analyzer._build_rerun_compliance(result)
    result["rerun_compliance"] = compliance
    review = auto_analyzer._analysis_quality_review(result)

    assert compliance["active"] is True
    assert compliance["status"] == "needs_attention"
    assert compliance["blocking_count"] == 3
    assert any(check["id"] == "required_evidence:comments" and not check["passed"] for check in compliance["checks"])
    assert any(check["id"] == "fix_target:shot_table_is_actionable" and not check["passed"] for check in compliance["checks"])
    assert any(check["id"] == "output_requirements:next_actions" and not check["passed"] for check in compliance["checks"])
    assert any(gap["id"] == "rerun_compliance" for gap in review["gaps"])


def test_rerun_compliance_accepts_acknowledged_missing_comments() -> None:
    result = {
        "summary": "这条视频主要靠前三秒近景动作形成停留，但评论摘要仍缺失，用户反馈需要补评论后复核。",
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [
                {"claim": "视觉", "evidence": "关键帧显示主体动作", "confidence": "high"}
            ],
            "asr_evidence": [],
            "ocr_evidence": [],
            "comment_evidence": [],
            "inferred_points": [],
            "evidence_gaps": ["评论摘要缺失，用户反馈不能作为确定结论。"],
        },
        "risks": ["评论缺失会影响受众判断。"],
        "next_actions": ["导入评论后重跑。"],
        "manual_review_context": {
            "rerun_strategy": {
                "active": True,
                "required_evidence": [
                    {"id": "comments", "label": "评论摘要", "status": "missing"}
                ],
            }
        },
    }

    compliance = auto_analyzer._build_rerun_compliance(result)

    assert compliance["status"] == "passed"
    assert compliance["blocking_count"] == 0
    assert compliance["checks"][0]["passed"] is True


def test_quality_review_rejects_generic_summary_text() -> None:
    result = {
        "summary": "可用",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [
                {
                    "claim": "前三秒靠人物近景和姿态变化制造停留",
                    "evidence": "0-3s 关键帧显示人物近景居中，1s 姿态变化，2s 镜头轻微推进",
                    "confidence": "high",
                }
            ],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "求同款", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    summary_check = next(check for check in review["checks"] if check["id"] == "summary")
    assert summary_check["passed"] is False
    assert summary_check["details"][0]["id"] == "summary_placeholder"
    assert summary_check["details"][0]["location"] == "summary"
    assert any(gap["id"] == "summary" for gap in review["gaps"])
    assert review["level"] == "usable"


def test_quality_review_rejects_vague_positive_summary_text() -> None:
    result = {
        "summary": "这条视频表现不错，适合复刻。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    summary_check = next(check for check in review["checks"] if check["id"] == "summary")
    assert summary_check["passed"] is False
    assert summary_check["details"][0]["id"] == "summary_too_generic"
    assert summary_check["details"][0]["location"] == "summary"
    assert any(gap["id"] == "summary" for gap in review["gaps"])


def test_quality_review_accepts_specific_summary_with_replication_reason() -> None:
    result = {
        "summary": "这条视频用前三秒近景动作、字幕承诺和评论求教程形成停留闭环，适合复刻开头结构但不能照搬原妆造。",
        "confidence": 0.82,
        "source": {"duration": 3.2},
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    summary_check = next(check for check in review["checks"] if check["id"] == "summary")
    traceability_check = next(check for check in review["checks"] if check["id"] == "claim_traceability")
    assert summary_check["passed"] is True
    assert summary_check["details"] == []
    assert traceability_check["passed"] is True
    assert traceability_check["details"] == []
    assert review["level"] == "strong"


def test_quality_review_rejects_out_of_bounds_timeline_and_shot_table() -> None:
    result = {
        "summary": "这条视频用前三秒近景动作、字幕承诺和评论求教程形成停留闭环，适合复刻开头结构但不能照搬原妆造。",
        "confidence": 0.82,
        "source": {"duration": 3.0},
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "4s 字幕出现"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": [{"time_range": "0-5s", "visual": "人物近景出现，字幕和抬手动作同步推进", "purpose": "停留"}],
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": [
                {
                    "time": "4-5s",
                    "visual": "人物近景抬手，字幕给出结果承诺",
                    "action": "看镜头后抬手指向字幕",
                    "subtitle": "先给结果，再给步骤",
                    "purpose": "第一秒建立停留理由",
                }
            ],
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    time_bounds_check = next(check for check in review["checks"] if check["id"] == "time_bounds")
    assert time_bounds_check["passed"] is False
    assert {item["id"] for item in time_bounds_check["details"]} == {
        "hook_first_3_seconds",
        "timeline_out_of_bounds",
        "shot_table_out_of_bounds",
    }
    assert any(gap["id"] == "time_bounds" for gap in review["gaps"])
    assert review["level"] != "strong"


def test_quality_review_accepts_timeline_within_video_duration() -> None:
    result = {
        "summary": "这条视频用前三秒近景动作、字幕承诺和评论求教程形成停留闭环，适合复刻开头结构但不能照搬原妆造。",
        "confidence": 0.82,
        "source": {"duration": 3.2},
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    time_bounds_check = next(check for check in review["checks"] if check["id"] == "time_bounds")
    assert time_bounds_check["passed"] is True
    assert time_bounds_check["details"] == []
    assert not any(gap["id"] == "time_bounds" for gap in review["gaps"])


def test_quality_review_rejects_summary_claim_without_matching_comment_evidence() -> None:
    evidence = detailed_evidence_summary()
    evidence["comment_evidence"] = [{"claim": "评论", "evidence": "求同款", "confidence": "high"}]
    result = {
        "summary": "这条视频用前三秒近景动作、字幕承诺和评论区求教程形成停留闭环。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": evidence,
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    evidence_check = next(check for check in review["checks"] if check["id"] == "evidence")
    traceability_check = next(check for check in review["checks"] if check["id"] == "claim_traceability")
    assert evidence_check["passed"] is True
    assert traceability_check["passed"] is False
    assert traceability_check["details"][0]["id"] == "core_claim_missing_comment_evidence"
    assert "评论证据" in traceability_check["details"][0]["message"]
    assert any(gap["id"] == "claim_traceability" for gap in review["gaps"])
    assert review["level"] == "usable"


def test_quality_review_accepts_traceable_copyable_points() -> None:
    result = {
        "summary": "这条视频用前三秒近景动作、字幕承诺和评论求教程形成停留闭环，适合复刻开头结构但不能照搬原妆造。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "前三秒近景动作和字幕承诺共同制造停留",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒近景动作", "字幕承诺强化", "评论区求教程"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻前三秒近景动作和字幕承诺结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    copyable_check = next(check for check in review["checks"] if check["id"] == "copyable_traceability")
    assert copyable_check["passed"] is True
    assert copyable_check["details"] == []
    assert review["level"] == "strong"


def test_quality_review_rejects_untraceable_copyable_points() -> None:
    result = {
        "summary": "这条视频用前三秒近景动作、字幕承诺和评论求教程形成停留闭环，适合复刻开头结构但不能照搬原妆造。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "前三秒近景动作和字幕承诺共同制造停留",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒近景动作", "黑屏反转开头"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻前三秒近景动作和字幕承诺结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    replication_check = next(check for check in review["checks"] if check["id"] == "replication")
    copyable_check = next(check for check in review["checks"] if check["id"] == "copyable_traceability")
    assert replication_check["passed"] is True
    assert copyable_check["passed"] is False
    assert copyable_check["details"][0]["id"] == "copyable_point_untraceable"
    assert "黑屏反转开头" in copyable_check["details"][0]["message"]
    assert any(gap["id"] == "copyable_traceability" for gap in review["gaps"])
    assert review["level"] == "usable"


def test_quality_review_rejects_generic_evidence_summary() -> None:
    result = {
        "summary": "这条视频用近景动作和字幕承诺制造前三秒停留，适合复刻开头结构。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "求同款", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    evidence_check = next(check for check in review["checks"] if check["id"] == "evidence")
    assert evidence_check["passed"] is False
    assert any(gap["id"] == "evidence" for gap in review["gaps"])
    assert review["level"] == "usable"


def test_quality_review_rejects_generic_comment_insights() -> None:
    result = {
        "summary": "其他模块完整，但评论洞察只是泛化标签。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": {
            "audience_needs": ["求同款"],
            "comment_triggers": ["接好运"],
            "replicable_interaction_design": "引导求同款",
        },
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "评论里有人问同款链接", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    audience_check = next(check for check in review["checks"] if check["id"] == "audience")
    assert audience_check["passed"] is False
    assert any(item["id"] == "audience_insight_too_generic" for item in audience_check["details"])
    assert any(gap["id"] == "audience" for gap in review["gaps"])
    assert review["level"] == "usable"


def test_quality_review_rejects_generic_copywriting_text() -> None:
    result = {
        "summary": "其他模块完整，但文案拆解只是泛化说明。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": {"title_click_reason": "标题有点击理由"},
        "speech_analysis": {},
        "screen_text_analysis": {},
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "评论里有人问同款链接", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    copy_check = next(check for check in review["checks"] if check["id"] == "copy_speech_text")
    assert copy_check["passed"] is False
    assert any(gap["id"] == "copy_speech_text" for gap in review["gaps"])
    assert review["level"] == "usable"


def test_normalize_result_rejects_llm_claimed_enrichment_evidence_without_source_data() -> None:
    result = {
        "summary": "模型声称自己用了富化数据",
        "hook_analysis": {
            "first_impression": "开头强",
            "why_stop_scrolling": "有动作和字幕",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺"],
        },
        "visual_analysis": {"scene": "室内", "subject": "人物"},
        "copywriting_analysis": detailed_copywriting_analysis(),
        "speech_analysis": {
            "has_speech": True,
            "opening_line": "模型声称第一句是痛点金句",
            "script_structure": "痛点、反转、号召",
        },
        "screen_text_analysis": {
            "cover_text_role": "模型声称封面字承诺收益",
            "subtitle_text_role": "模型声称字幕推动完播",
        },
        "comment_insights": {
            "audience_needs": ["求教程"],
            "comment_triggers": ["催更"],
            "replicable_interaction_design": "引导评论",
        },
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧显示人物入镜", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "模型声称有口播金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "模型声称有封面字", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "模型声称评论区求教程", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "enrichment_usage": {
            "asr_used": "是",
            "ocr_used": "true",
            "comments_used": "yes",
            "notes": "模型自称使用了富化数据",
        },
        "timeline": detailed_timeline(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "remake_angle": "换成自己的主题",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }
    analysis_input = {
        "content_category": "generic",
        "content_category_label": "通用短视频",
        "stats": {"like_count": 10, "comment_count": 1, "share_count": 1},
        "video": {},
        "assets": {"keyframes": [{"path": "outputs/cases/case_demo/keyframes/frame_0000_00.00s.jpg"}]},
        "analysis_enrichment": {},
    }

    normalized = auto_analyzer._normalize_result(
        result,
        metadata={"title": "测试"},
        ffprobe={},
        analysis_input=analysis_input,
        analysis_context={"category_id": "generic", "label": "通用短视频"},
        visual_input_mode="multi_image",
    )

    evidence = normalized["evidence_summary"]
    usage = normalized["enrichment_usage"]
    assert evidence["asr_evidence"] == []
    assert evidence["ocr_evidence"] == []
    assert evidence["comment_evidence"] == []
    assert any("未提供 ASR" in gap for gap in evidence["evidence_gaps"])
    assert any("未提供 OCR" in gap for gap in evidence["evidence_gaps"])
    assert any("未导入评论" in gap for gap in evidence["evidence_gaps"])
    assert usage["asr_used"] is False
    assert usage["ocr_used"] is False
    assert usage["comments_used"] is False
    assert normalized["enrichment_coverage"]["items"]["asr"]["verdict"] == "insight_without_evidence"
    assert normalized["enrichment_coverage"]["items"]["ocr"]["verdict"] == "insight_without_evidence"
    assert normalized["enrichment_coverage"]["items"]["comments"]["verdict"] == "insight_without_evidence"
    assert normalized["enrichment_coverage"]["summary"]["blocking_count"] == 3
    assert any(gap["id"] == "enrichment_usage" for gap in normalized["quality_review"]["gaps"])
    assert "模型自称使用了富化数据" in usage["notes"]
    assert any("口播/声音洞察缺少 ASR" in item for item in evidence["inferred_points"])
    assert any("画面文字/字幕洞察缺少 OCR" in item for item in evidence["inferred_points"])
    assert any("评论反馈洞察缺少评论摘要" in item for item in evidence["inferred_points"])
    assert any("口播/声音洞察缺少 ASR" in item for item in evidence["evidence_gaps"])
    assert any("画面文字/字幕洞察缺少 OCR" in item for item in evidence["evidence_gaps"])
    assert any("评论反馈洞察缺少评论摘要" in item for item in evidence["evidence_gaps"])
    assert any("口播/声音洞察缺少 ASR" in item for item in normalized["risks"])
    assert any("画面文字/字幕洞察缺少 OCR" in item for item in normalized["risks"])
    assert any("评论反馈洞察缺少评论摘要" in item for item in normalized["risks"])
    assert any("补充 ASR" in item for item in normalized["next_actions"])
    assert any("补充 OCR" in item for item in normalized["next_actions"])
    assert any("导入高赞/典型评论" in item for item in normalized["next_actions"])
    assert any(gap["id"] == "audience" for gap in normalized["quality_review"]["gaps"])
    assert any(gap["id"] == "evidence_gaps" for gap in normalized["quality_review"]["gaps"])
    assert normalized["quality_review"]["level"] != "strong"


def test_normalize_result_flags_speech_and_text_claims_after_checked_empty_asr_ocr() -> None:
    result = {
        "summary": "模型把纯视觉内容写成了口播和字幕分析",
        "confidence": 0.8,
        "hook_analysis": {
            "first_impression": "画面动作很强",
            "why_stop_scrolling": "主体动作有停留点",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 抬手动作变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": {"title_click_reason": "标题有明确承诺"},
        "speech_analysis": {
            "has_speech": True,
            "opening_line": "模型声称第一句是口播钩子",
            "script_structure": "痛点、反转、号召",
        },
        "screen_text_analysis": {
            "has_text": True,
            "cover_text_role": "模型声称封面字负责承诺收益",
            "subtitle_text_role": "模型声称字幕推动完播",
        },
        "comment_insights": {
            "audience_needs": ["求同款"],
            "comment_triggers": ["催更"],
            "replicable_interaction_design": "引导评论",
        },
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧显示主体动作", "confidence": "high"}],
            "asr_evidence": [],
            "ocr_evidence": [],
            "comment_evidence": [{"claim": "评论", "evidence": "需求：求同款", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": [{"time_range": "0-3s", "visual": "主体动作变化", "purpose": "停留"}],
        "emotion_path": ["开头吸引", "中段维持"],
        "content_ratio": [{"name": "钩子", "percent": 50, "reason": "前三秒强"}],
        "replication": {
            "copyable_points": ["动作节奏"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "换成自己的角色动作",
            "opening_3s": "主体动作先出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }
    analysis_input = {
        "content_category": "generic",
        "content_category_label": "通用短视频",
        "stats": {"like_count": 10, "comment_count": 1, "share_count": 1},
        "video": {},
        "assets": {"keyframes": [{"path": "outputs/cases/case_demo/keyframes/frame_0000_00.00s.jpg"}]},
        "analysis_enrichment": {
            "asr": {"status": "no_speech", "full_text": ""},
            "ocr": {"status": "no_text", "cover_text": "", "subtitle_text": "", "frame_text": ""},
            "comments": {
                "total_comments": 2,
                "top_needs": ["求同款"],
                "high_frequency_words": ["同款"],
                "comment_hooks": ["催更"],
            },
        },
    }

    normalized = auto_analyzer._normalize_result(
        result,
        metadata={"title": "测试"},
        ffprobe={},
        analysis_input=analysis_input,
        analysis_context={"category_id": "generic", "label": "通用短视频"},
        visual_input_mode="multi_image",
    )

    evidence = normalized["evidence_summary"]
    usage = normalized["enrichment_usage"]
    assert usage["asr_used"] is False
    assert usage["ocr_used"] is False
    assert usage["comments_used"] is True
    assert normalized["speech_analysis"]["has_speech"] is False
    assert normalized["screen_text_analysis"]["has_text"] is False
    assert any("未检测到可转写语音" in item["evidence"] for item in evidence["asr_evidence"])
    assert any("未检测到封面字" in item["evidence"] for item in evidence["ocr_evidence"])
    assert any("ASR 已确认无可转写语音" in item for item in evidence["evidence_gaps"])
    assert any("OCR 已确认无封面字" in item for item in evidence["evidence_gaps"])
    assert any("口播/声音洞察缺少 ASR" in item for item in evidence["inferred_points"])
    assert any("画面文字/字幕洞察缺少 OCR" in item for item in evidence["inferred_points"])
    assert not any("评论反馈洞察缺少评论摘要" in item for item in evidence["inferred_points"])
    assert any("口播/声音洞察缺少 ASR" in item for item in evidence["evidence_gaps"])
    assert any("画面文字/字幕洞察缺少 OCR" in item for item in evidence["evidence_gaps"])
    assert any("口播/声音洞察缺少 ASR" in item for item in normalized["risks"])
    assert any("画面文字/字幕洞察缺少 OCR" in item for item in normalized["risks"])
    assert not any("评论反馈洞察缺少评论摘要" in item for item in normalized["risks"])
    assert any(gap["id"] == "evidence_gaps" for gap in normalized["quality_review"]["gaps"])
    assert normalized["quality_review"]["level"] != "strong"


def test_normalize_result_corrects_false_no_speech_flag_when_asr_has_text() -> None:
    result = {
        "summary": "模型误判为无口播",
        "confidence": 0.8,
        "hook_analysis": {
            "first_impression": "开头直接给承诺",
            "why_stop_scrolling": "字幕和口播都给收益",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 口播给承诺"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": {"title_click_reason": "标题有明确承诺"},
        "speech_analysis": {
            "has_speech": False,
            "opening_line": "真正厉害的人会先抓住前三秒",
            "script_structure": "痛点、承诺、行动",
        },
        "screen_text_analysis": {
            "has_text": False,
            "cover_text_role": "封面字给出教程承诺",
            "subtitle_text_role": "字幕强化步骤",
        },
        "comment_insights": {
            "audience_needs": ["求教程"],
            "comment_triggers": ["催更"],
            "replicable_interaction_design": "引导评论",
        },
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧显示主体动作", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "真正厉害的人会先抓住前三秒", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "三秒学会", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "需求：求教程", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": [{"time_range": "0-3s", "visual": "主体动作变化", "purpose": "停留"}],
        "emotion_path": ["开头吸引", "中段维持"],
        "content_ratio": [{"name": "钩子", "percent": 50, "reason": "前三秒强"}],
        "replication": {
            "copyable_points": ["动作节奏"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "换成自己的角色动作",
            "opening_3s": "主体动作先出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }
    analysis_input = {
        "content_category": "generic",
        "content_category_label": "通用短视频",
        "stats": {"like_count": 10, "comment_count": 1, "share_count": 1},
        "video": {},
        "assets": {"keyframes": [{"path": "outputs/cases/case_demo/keyframes/frame_0000_00.00s.jpg"}]},
        "analysis_enrichment": {
            "asr": {"status": "success", "full_text": "真正厉害的人会先抓住前三秒"},
            "ocr": {"status": "success", "cover_text": "三秒学会", "subtitle_text": "", "frame_text": ""},
            "comments": {
                "total_comments": 2,
                "top_needs": ["求教程"],
                "high_frequency_words": ["教程"],
                "comment_hooks": ["催更"],
            },
        },
    }

    normalized = auto_analyzer._normalize_result(
        result,
        metadata={"title": "测试"},
        ffprobe={},
        analysis_input=analysis_input,
        analysis_context={"category_id": "generic", "label": "通用短视频"},
        visual_input_mode="multi_image",
    )

    assert normalized["enrichment_usage"]["asr_used"] is True
    assert normalized["enrichment_usage"]["ocr_used"] is True
    assert normalized["speech_analysis"]["has_speech"] is True
    assert normalized["screen_text_analysis"]["has_text"] is True
    assert any("ASR 存在转写文本" in item for item in normalized["evidence_summary"]["evidence_gaps"])
    assert any("OCR 存在识别文本" in item for item in normalized["evidence_summary"]["evidence_gaps"])
    assert normalized["quality_review"]["level"] != "strong"


def test_normalize_result_flags_available_enrichment_that_model_did_not_use() -> None:
    result = {
        "summary": "模型没有使用富化证据",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "0s 人物近景居中出现",
            "why_stop_scrolling": "画面主体清楚",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 抬手动作变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": {"title_click_reason": "标题有明确收益"},
        "speech_analysis": {"has_speech": True},
        "screen_text_analysis": {"has_text": True},
        "comment_insights": {},
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧显示主体动作", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头说明收益", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "需求：求教程", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "emotion_path": ["开头吸引", "中段维持"],
        "content_ratio": [{"name": "钩子", "percent": 50, "reason": "前三秒强"}],
        "timeline": [{"time_range": "0-3s", "visual": "主体动作变化", "purpose": "停留"}],
        "replication": {
            "copyable_points": ["动作节奏"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "换成自己的角色动作",
            "opening_3s": "主体动作先出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }
    analysis_input = {
        "content_category": "tutorial",
        "content_category_label": "教学 / 教程",
        "stats": {"like_count": 10, "comment_count": 2, "share_count": 1},
        "video": {},
        "assets": {"keyframes": [{"path": "outputs/cases/case_demo/keyframes/frame_0000_00.00s.jpg"}]},
        "analysis_enrichment": {
            "asr": {"full_text": "开头说明收益"},
            "ocr": {"cover_text": "封面承诺"},
            "comments": {
                "total_comments": 2,
                "top_needs": ["求教程"],
                "high_frequency_words": ["教程"],
                "comment_hooks": ["求下一版"],
            },
        },
    }

    normalized = auto_analyzer._normalize_result(
        result,
        metadata={"title": "测试"},
        ffprobe={},
        analysis_input=analysis_input,
        analysis_context={"category_id": "tutorial", "label": "教学 / 教程"},
        visual_input_mode="multi_image",
    )

    gaps = normalized["evidence_summary"]["evidence_gaps"]
    assert normalized["enrichment_usage"]["asr_used"] is True
    assert normalized["enrichment_usage"]["ocr_used"] is True
    assert normalized["enrichment_usage"]["comments_used"] is True
    assert normalized["enrichment_coverage"]["items"]["asr"]["verdict"] == "evidence_without_insight"
    assert normalized["enrichment_coverage"]["items"]["ocr"]["verdict"] == "evidence_without_insight"
    assert normalized["enrichment_coverage"]["items"]["comments"]["verdict"] == "evidence_without_insight"
    assert normalized["enrichment_coverage"]["summary"]["blocking_count"] == 3
    assert any("ASR 转写已可用" in gap for gap in gaps)
    assert any("OCR 文字已可用" in gap for gap in gaps)
    assert any("评论摘要已可用" in gap for gap in gaps)
    assert any("ASR 转写已可用" in risk for risk in normalized["risks"])
    assert any("基于 ASR 转写" in action for action in normalized["next_actions"])
    assert any(gap["id"] == "enrichment_usage" for gap in normalized["quality_review"]["gaps"])
    assert any(gap["id"] == "evidence_gaps" for gap in normalized["quality_review"]["gaps"])
    assert normalized["quality_review"]["level"] != "strong"


def test_normalize_result_coerces_common_llm_string_shapes() -> None:
    result = {
        "summary": "模型返回了有用内容，但部分字段是字符串。",
        "confidence": "86%",
        "hook_analysis": {
            "first_impression": "0s 人物近景直接出现",
            "why_stop_scrolling": "动作和字幕同时给出停留理由",
            "first_3_seconds": "0s 人物出现；1s 字幕强化承诺；2s 动作变化",
        },
        "visual_analysis": {
            "scene": "室内近景布景，背景留白突出主体",
            "subject": "人物居中看镜头，手部动作带出步骤",
            "movement_rhythm": "0-2s 字幕和动作逐秒推进",
            "style_keywords": "近景；反差；节奏快",
        },
        "copywriting_analysis": {
            "title_click_reason": "标题给出明确收益",
            "reusable_patterns": "先给结果；再给步骤",
        },
        "speech_analysis": {
            "opening_line": "开头说明收益",
            "script_structure": "先给收益，再给步骤。",
        },
        "screen_text_analysis": {
            "cover_text_role": "封面承诺强化点击",
            "subtitle_text_role": "字幕承接教程步骤",
        },
        "comment_insights": {
            "audience_needs": "想学同款动作；求教程",
            "replicable_interaction_design": "引导评论区说出想看的下一版",
        },
        "evidence_summary": detailed_evidence_summary(),
        "emotion_path": "开头抓注意；中段给价值；结尾引导互动",
        "content_ratio": "钩子 40%，教程步骤 40%，互动 20%",
        "timeline": "0-3s 人物近景和字幕同步出现；3-6s 抬手展示动作步骤",
        "replication": {
            "copyable_points": "近景开头；字幕承诺",
            "avoid_copying": "不要照搬原动作和原字幕",
            "remake_angle": "换成自己的角色和动作",
            "opening_3s": "0s 近景看镜头，1s 字幕给承诺",
            "shot_table": "0-3s 人物近景抬手，字幕给结果；3-6s 展示动作步骤",
        },
        "publish_package": {
            "titles": "3 秒抓住注意力的开头模板",
            "caption": "保存这套开头结构，下次直接复刻。",
            "hashtags": "短视频拆解；内容复盘",
        },
    }
    analysis_input = {
        "content_category": "tutorial",
        "content_category_label": "教学 / 教程",
        "stats": {"like_count": 10, "comment_count": 2, "share_count": 1},
        "video": {},
        "assets": {"keyframes": [{"path": "outputs/cases/case_demo/keyframes/frame_0000_00.00s.jpg"}]},
        "analysis_enrichment": {
            "asr": {"full_text": "开头说明收益"},
            "ocr": {"cover_text": "封面承诺"},
            "comments": {
                "total_comments": 2,
                "top_needs": ["求教程"],
                "high_frequency_words": ["教程"],
                "comment_hooks": ["求下一版"],
            },
        },
    }
    normalized = auto_analyzer._normalize_result(
        result,
        metadata={"title": "测试"},
        ffprobe={},
        analysis_input=analysis_input,
        analysis_context={"category_id": "tutorial", "label": "教学 / 教程"},
        visual_input_mode="multi_image",
    )

    assert normalized["hook_analysis"]["first_3_seconds"] == [
        "0s 人物出现",
        "1s 字幕强化承诺",
        "2s 动作变化",
    ]
    assert normalized["visual_analysis"]["style_keywords"] == ["近景", "反差", "节奏快"]
    assert normalized["publish_package"]["titles"] == ["3 秒抓住注意力的开头模板"]
    assert normalized["publish_package"]["hashtags"] == ["短视频拆解", "内容复盘"]
    assert normalized["replication"]["shot_table"][0]["time"] == "0-3s"
    assert normalized["replication"]["shot_table"][0]["visual"] == "人物近景抬手，字幕给结果"
    assert normalized["content_ratio"] == [
        {"name": "钩子", "percent": 40, "reason": ""},
        {"name": "教程步骤", "percent": 40, "reason": ""},
        {"name": "互动", "percent": 20, "reason": ""},
    ]
    assert normalized["confidence"] == 0.86
    content_ratio_check = next(
        check for check in normalized["quality_review"]["checks"] if check["id"] == "content_ratio_balance"
    )
    assert content_ratio_check["passed"] is False
    assert normalized["quality_review"]["level"] == "usable"


def test_model_confidence_normalizes_common_llm_formats() -> None:
    assert auto_analyzer._normalize_model_confidence("86%") == 0.86
    assert auto_analyzer._normalize_model_confidence("86") == 0.86
    assert auto_analyzer._normalize_model_confidence(86) == 0.86
    assert auto_analyzer._normalize_model_confidence("置信度：较高") == 0.8
    assert auto_analyzer._normalize_model_confidence("低") == 0.35
    assert auto_analyzer._has_usable_model_confidence("65%") is True
    assert auto_analyzer._has_usable_model_confidence("35%") is False


def test_normalize_result_preserves_string_object_sections() -> None:
    result = {
        "summary": "模型把多个对象字段写成了整段文字。",
        "confidence": 0.7,
        "hook_analysis": "0s 人物近景出现，1s 字幕给出结果承诺。",
        "visual_analysis": "室内近景，人物居中，动作节奏快。",
        "copywriting_analysis": "标题用结果承诺制造点击理由。",
        "speech_analysis": "口播按痛点、步骤、结果推进。",
        "screen_text_analysis": "字幕强调先看结果再学步骤。",
        "comment_insights": "用户会追问下一版教程。",
        "replication": "换成自己的角色，用同样的先结果后步骤结构。",
        "publish_package": "标题：3 秒学会这个开头；正文：保存复盘；标签：短视频拆解",
        "timeline": "0-3s 人物和字幕出现",
        "emotion_path": "开头抓注意；中段给价值",
        "content_ratio": "钩子 50%；步骤 50%",
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "痛点步骤结果", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "结果承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "求教程", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
    }
    analysis_input = {
        "stats": {"like_count": 1},
        "video": {},
        "assets": {"keyframes": [{"path": "outputs/cases/case_demo/keyframes/frame_0000_00.00s.jpg"}]},
        "analysis_enrichment": {
            "asr": {"full_text": "痛点步骤结果"},
            "ocr": {"cover_text": "结果承诺"},
            "comments": {"total_comments": 1, "top_needs": ["求教程"], "high_frequency_words": ["教程"]},
        },
    }

    normalized = auto_analyzer._normalize_result(
        result,
        metadata={},
        ffprobe={},
        analysis_input=analysis_input,
        analysis_context={"category_id": "tutorial", "label": "教学 / 教程"},
        visual_input_mode="multi_image",
    )

    assert normalized["hook_analysis"]["first_impression"].startswith("0s 人物近景")
    assert normalized["visual_analysis"]["scene"].startswith("室内近景")
    assert normalized["copywriting_analysis"]["title_click_reason"].startswith("标题用结果承诺")
    assert normalized["speech_analysis"]["script_structure"].startswith("口播按痛点")
    assert normalized["screen_text_analysis"]["subtitle_text_role"].startswith("字幕强调")
    assert normalized["comment_insights"]["replicable_interaction_design"].startswith("用户会追问")
    assert normalized["replication"]["remake_angle"].startswith("换成自己的角色")
    assert normalized["publish_package"]["caption"].startswith("标题：3 秒学会")
    assert normalized["content_ratio"] == [
        {"name": "钩子", "percent": 50, "reason": ""},
        {"name": "步骤", "percent": 50, "reason": ""},
    ]


def test_quality_review_downgrades_when_evidence_gaps_remain() -> None:
    result = {
        "summary": "完整拆解但仍有证据缺口",
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "求同款", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": ["只使用 contact_sheet，细节动作和字幕位置可能需要人工复核。"],
        },
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    evidence_gap_check = next(check for check in review["checks"] if check["id"] == "evidence_gaps")
    assert evidence_gap_check["passed"] is False
    assert evidence_gap_check["details"][0]["id"] == "evidence_gap_item"
    assert evidence_gap_check["details"][0]["location"] == "evidence_summary.evidence_gaps[0]"
    assert "只使用 contact_sheet" in evidence_gap_check["details"][0]["message"]
    assert any(gap["id"] == "evidence_gaps" for gap in review["gaps"])
    assert review["score"] >= 85
    assert review["level"] == "usable"


def test_quality_review_flags_low_confidence_evidence() -> None:
    result = {
        "summary": "其他模块完整，但视觉证据置信度很低。",
        "confidence": 0.9,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧模糊不确定", "confidence": "low"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "求同款", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": detailed_timeline(),
        "emotion_path": ["开头抓注意", "中段给价值", "结尾引导互动"],
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    confidence_check = next(check for check in review["checks"] if check["id"] == "evidence_confidence")
    assert confidence_check["passed"] is False
    assert confidence_check["details"][0]["id"] == "low_confidence_visual_evidence"
    assert confidence_check["details"][0]["location"] == "evidence_summary.visual_evidence[0]"
    assert "关键帧模糊不确定" in confidence_check["details"][0]["message"]
    assert any(gap["id"] == "evidence_confidence" for gap in review["gaps"])
    assert any("低置信" in action for action in review["next_actions"])
    assert review["score"] >= 85
    assert review["level"] == "usable"


def test_quality_review_flags_low_model_confidence() -> None:
    result = {
        "summary": "其他模块完整，但模型整体置信度偏低。",
        "confidence": 0.35,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": detailed_timeline(),
        "emotion_path": ["开头抓注意", "中段给价值", "结尾引导互动"],
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    confidence_check = next(check for check in review["checks"] if check["id"] == "model_confidence")
    assert confidence_check["passed"] is False
    assert any(gap["id"] == "model_confidence" for gap in review["gaps"])
    assert any("confidence 偏低" in action for action in review["next_actions"])
    assert review["score"] >= 85
    assert review["level"] == "usable"


def test_quality_review_caps_text_only_reports_even_when_fields_look_complete() -> None:
    result = {
        "summary": "字段看起来完整，但没有真实视觉输入",
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": {
            "visual_input_mode": "text_only",
            "visual_evidence": [],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "求同款", "confidence": "high"}],
            "inferred_points": ["视觉判断来自文本推断"],
            "evidence_gaps": ["缺少可用视觉输入"],
        },
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    visual_input_check = next(check for check in review["checks"] if check["id"] == "visual_input")
    assert visual_input_check["passed"] is False
    assert review["score"] >= 85
    assert review["level"] == "needs_review"
    assert review["label"] == "缺少视觉输入"
    assert any(gap["id"] == "visual_input" for gap in review["gaps"])
    assert any("contact_sheet/keyframes" in action for action in review["next_actions"])


def test_quality_review_accepts_checked_visual_only_content_without_speech_or_text() -> None:
    result = {
        "summary": "纯视觉作品主要靠人物状态和镜头节奏吸引。",
        "confidence": 0.86,
        "hook_analysis": {
            "first_impression": "人物脸和动作第一秒出现",
            "why_stop_scrolling": "服化和姿态有明确第一眼吸引点",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 姿态变化", "2s 镜头推进"],
        },
        "visual_analysis": {
            "scene": "室内暖色布景，背景留白突出人物",
            "subject": "人物近景居中，服化妆造是第一眼亮点",
            "movement_rhythm": "1s 姿态变化，2s 镜头轻微推进",
        },
        "copywriting_analysis": {},
        "speech_analysis": {},
        "screen_text_analysis": {},
        "comment_insights": {
            "audience_needs": ["求同款/妆造线索"],
            "comment_triggers": ["夸画面"],
            "replicable_interaction_design": "引导观众评论最喜欢哪一秒",
        },
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [
                {
                    "claim": "前三秒靠人物近景和姿态变化制造停留",
                    "evidence": "0-3s 关键帧显示人物近景居中，1s 姿态变化，2s 镜头轻微推进",
                    "confidence": "high",
                }
            ],
            "asr_evidence": [
                {
                    "claim": "口播/脚本结构判断",
                    "evidence": "ASR 已完成，未检测到可转写语音；本条更适合按画面拆解。",
                    "confidence": "high",
                }
            ],
            "ocr_evidence": [
                {
                    "claim": "封面字、字幕和画面文字判断",
                    "evidence": "OCR 已完成，未检测到封面字、字幕或画面文字；本条更适合按视觉动作和构图拆解。",
                    "confidence": "high",
                }
            ],
            "comment_evidence": [{"claim": "评论", "evidence": "夸画面/求妆造", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": [{"time_range": "0-3s", "visual": "人物近景抬手并伴随镜头推进", "purpose": "停留"}],
        "emotion_path": ["开头给第一眼视觉吸引", "中段靠动作变化维持停留", "结尾引导评论最喜欢哪一秒"],
        "content_ratio": [
            {"name": "视觉吸引", "percent": 60, "reason": "核心依赖人物状态、妆造和动作变化"},
            {"name": "动作维持", "percent": 25, "reason": "中段靠动作变化维持停留"},
            {"name": "评论互动", "percent": 15, "reason": "结尾引导观众选择喜欢的瞬间"},
        ],
        "replication": {
            "copyable_points": ["第一秒给脸和服化亮点"],
            "avoid_copying": ["不要照搬原视频妆造和姿势，保留自己的角色设定"],
            "remake_angle": "复刻视觉结构",
            "opening_3s": "先给人物状态，再给动作变化",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": {
            "titles": ["今天最喜欢哪一秒"],
            "caption": "第一眼就被这个动作抓住了。",
            "hashtags": ["短视频拆解"],
        },
    }

    review = auto_analyzer._analysis_quality_review(result)
    copy_check = next(check for check in review["checks"] if check["id"] == "copy_speech_text")
    assert copy_check["passed"] is True
    assert not any(gap["id"] == "copy_speech_text" for gap in review["gaps"])
    assert review["level"] == "strong"


def test_quality_review_still_requires_detection_when_speech_and_text_are_missing() -> None:
    result = {
        "summary": "纯视觉作品，但还没有 ASR/OCR 检测证据。",
        "hook_analysis": {
            "first_impression": "人物脸和动作第一秒出现",
            "why_stop_scrolling": "服化和姿态有明确第一眼吸引点",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 姿态变化", "2s 镜头推进"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": {},
        "speech_analysis": {},
        "screen_text_analysis": {},
        "comment_insights": {
            "audience_needs": ["求同款/妆造线索"],
            "comment_triggers": ["夸画面"],
            "replicable_interaction_design": "引导观众评论最喜欢哪一秒",
        },
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [],
            "ocr_evidence": [],
            "comment_evidence": [{"claim": "评论", "evidence": "夸画面/求妆造", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["第一秒给脸和服化亮点"],
            "avoid_copying": ["不要照搬原视频妆造和姿势，保留自己的角色设定"],
            "remake_angle": "复刻视觉结构",
            "opening_3s": "先给人物状态，再给动作变化",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": {"titles": ["今天最喜欢哪一秒"], "caption": "第一眼最重要。"},
    }

    review = auto_analyzer._analysis_quality_review(result)
    copy_check = next(check for check in review["checks"] if check["id"] == "copy_speech_text")
    assert copy_check["passed"] is False
    assert any(gap["id"] == "copy_speech_text" for gap in review["gaps"])
    assert any("ASR/OCR 空内容检测" in action for action in review["next_actions"])
    assert review["level"] == "usable"


def test_quality_review_rejects_shallow_visual_description() -> None:
    result = {
        "summary": "其他模块完整，但视觉拆解只有泛泛场景。",
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": {"scene": "室内"},
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "求同款", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": detailed_timeline(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    visual_check = next(check for check in review["checks"] if check["id"] == "visual")
    assert visual_check["passed"] is False
    assert visual_check["details"][0]["id"] == "visual_fields_too_shallow"
    assert "场景=室内" in visual_check["details"][0]["message"]
    assert any(gap["id"] == "visual" for gap in review["gaps"])
    assert any("泛泛描述" in action for action in review["next_actions"])
    assert review["level"] == "usable"


def test_quality_review_rejects_multiple_generic_visual_fields() -> None:
    result = {
        "summary": "其他模块完整，但视觉字段都是泛词。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": {"scene": "室内", "subject": "人物", "movement_rhythm": "紧凑"},
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "求同款", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": detailed_timeline(),
        "emotion_path": ["开头抓注意", "中段给价值", "结尾引导互动"],
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    visual_check = next(check for check in review["checks"] if check["id"] == "visual")
    assert visual_check["passed"] is False
    assert visual_check["details"][0]["id"] == "visual_fields_too_shallow"
    assert "主体=人物" in visual_check["details"][0]["message"]
    assert any(gap["id"] == "visual" for gap in review["gaps"])
    assert review["level"] == "usable"


def test_quality_review_rejects_visual_analysis_without_usable_timeline() -> None:
    result = {
        "summary": "其他模块完整，但缺少关键时间线。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": [{"time_range": "0-3s", "visual": "画面", "purpose": "停留"}],
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    visual_check = next(check for check in review["checks"] if check["id"] == "visual")
    assert visual_check["passed"] is False
    assert visual_check["details"][0]["id"] == "visual_timeline_missing"
    assert any(gap["id"] == "visual" for gap in review["gaps"])
    assert review["level"] == "usable"


def test_quality_review_rejects_placeholder_text_as_missing_content() -> None:
    result = {
        "summary": "待补充",
        "confidence": 0.9,
        "hook_analysis": {
            "first_impression": "待补充",
            "why_stop_scrolling": "暂无",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 待补充", "2s 未提供"],
        },
        "visual_analysis": {"scene": "不清楚", "subject": "人物", "movement_rhythm": "未知"},
        "copywriting_analysis": {"title_click_reason": "未提供"},
        "speech_analysis": {"opening_line": "暂无"},
        "screen_text_analysis": {"cover_text_role": "待完善"},
        "comment_insights": {
            "audience_needs": ["暂无"],
            "comment_triggers": ["未提供"],
            "replicable_interaction_design": "待补充",
        },
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "求同款", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": [{"time_range": "0-3s", "visual": "待补充", "purpose": "未提供"}],
        "emotion_path": ["开头抓注意", "待补充"],
        "content_ratio": [{"name": "钩子", "reason": "待补充"}],
        "replication": {
            "copyable_points": ["待补充"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "待定",
            "opening_3s": "暂无",
            "shot_table": [{"time": "0-3s", "visual": "待补充", "action": "未提供"}],
        },
        "publish_package": {"titles": ["待补充"], "caption": "暂无", "hashtags": ["未提供"]},
    }

    review = auto_analyzer._analysis_quality_review(result)

    assert review["score"] < 50
    assert review["level"] == "weak"
    failed_ids = {gap["id"] for gap in review["gaps"]}
    assert {"summary", "hook", "copy_speech_text", "audience", "replication", "publishing"} <= failed_ids


def test_quality_review_rejects_thin_first_three_seconds() -> None:
    result = {
        "summary": "其他模块完整，但前三秒只有一句占位。",
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现"],
        },
        "visual_analysis": {
            "scene": "室内近景，背景留白突出主体",
            "subject": "人物居中看镜头，字幕贴近主体出现",
            "movement_rhythm": "0-2s 从静止到抬手，节奏逐秒推进",
        },
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "求同款", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": [{"time_range": "0-3s", "visual": "人物近景出现，字幕和抬手动作同步推进", "purpose": "停留"}],
        "replication": {
            "copyable_points": ["前三秒主体"],
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    hook_check = next(check for check in review["checks"] if check["id"] == "hook")
    assert hook_check["passed"] is False
    assert hook_check["details"][0]["id"] == "hook_first_3_seconds_too_few"
    assert any(gap["id"] == "hook" for gap in review["gaps"])
    assert any("至少写出两个时间点" in action for action in review["next_actions"])
    assert review["level"] == "usable"


def test_quality_review_rejects_untimed_first_three_second_observations() -> None:
    result = {
        "summary": "其他模块完整，但前三秒没有具体时间点。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["主体出现", "字幕出现", "节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "求同款", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": detailed_timeline(),
        "emotion_path": ["开头抓注意", "中段给价值", "结尾引导互动"],
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    hook_check = next(check for check in review["checks"] if check["id"] == "hook")
    assert hook_check["passed"] is False
    assert hook_check["details"][0]["id"] == "hook_first_3_seconds_too_few"
    assert any(item["id"] == "hook_observation_missing_time" for item in hook_check["details"])
    assert any(gap["id"] == "hook" for gap in review["gaps"])
    assert review["level"] == "usable"


def test_quality_review_rejects_generic_timed_first_three_second_observations() -> None:
    result = {
        "summary": "其他模块完整，但前三秒只是泛化观察。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 主体出现", "1s 字幕出现", "2s 节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    hook_check = next(check for check in review["checks"] if check["id"] == "hook")
    assert hook_check["passed"] is False
    assert hook_check["details"][0]["id"] == "hook_first_3_seconds_too_few"
    assert any(item["id"] == "hook_observation_too_generic" for item in hook_check["details"])
    assert any(gap["id"] == "hook" for gap in review["gaps"])
    assert review["level"] == "usable"


def test_quality_review_accepts_structured_timed_first_three_second_observations() -> None:
    result = {
        "summary": "结构化前三秒观察可以直接用于拆解。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": [
                {"time": "0s", "visual": "主体近景出现"},
                {"time": "1s", "subtitle": "字幕给出结果承诺"},
                {"time": "2s", "action": "动作节奏变化"},
            ],
        },
        "visual_analysis": {
            "scene": "室内近景，背景留白突出主体",
            "subject": "人物居中看镜头，字幕贴近主体出现",
            "movement_rhythm": "0-2s 从静止到抬手，节奏逐秒推进",
        },
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": [{"time_range": "0-3s", "visual": "人物近景出现，字幕和抬手动作同步推进", "purpose": "停留"}],
        "emotion_path": ["开头抓注意", "中段给价值", "结尾引导互动"],
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    hook_check = next(check for check in review["checks"] if check["id"] == "hook")
    assert hook_check["passed"] is True
    assert hook_check["details"] == []
    assert review["level"] == "strong"


def test_quality_review_rejects_placeholder_shot_table() -> None:
    result = {
        "summary": "其他模块完整，但分镜表只是占位。",
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "求同款", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": [{"time": "0-3s"}],
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    replication_check = next(check for check in review["checks"] if check["id"] == "replication")
    assert replication_check["passed"] is False
    assert any(gap["id"] == "replication" for gap in review["gaps"])
    assert any("可拍摄分镜表" in action for action in review["next_actions"])
    assert review["level"] == "usable"


def test_quality_review_rejects_generic_shot_table_details() -> None:
    result = {
        "summary": "其他模块完整，但分镜表只有泛化动作。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "求同款", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": [{"time": "0-3s", "visual": "主体", "action": "看镜头"}],
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    replication_check = next(check for check in review["checks"] if check["id"] == "replication")
    assert replication_check["passed"] is False
    assert any(gap["id"] == "replication" for gap in review["gaps"])
    assert review["level"] == "usable"


def test_quality_review_accepts_traceable_shot_table() -> None:
    result = {
        "summary": "这条视频用前三秒近景动作、字幕承诺和评论求教程形成停留闭环，适合复刻开头结构。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "前三秒近景动作和字幕承诺共同制造停留",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒近景动作", "字幕承诺强化", "评论区求教程"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻前三秒近景动作和字幕承诺结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    shot_trace_check = next(check for check in review["checks"] if check["id"] == "shot_table_traceability")
    assert shot_trace_check["passed"] is True
    assert shot_trace_check["details"] == []
    assert review["level"] == "strong"


def test_quality_review_rejects_untraceable_shot_table() -> None:
    result = {
        "summary": "这条视频用前三秒近景动作、字幕承诺和评论求教程形成停留闭环，适合复刻开头结构。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "前三秒近景动作和字幕承诺共同制造停留",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒近景动作", "字幕承诺强化", "评论区求教程"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻前三秒近景动作和字幕承诺结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": [
                {
                    "time": "0-3s",
                    "visual": "黑屏闪白后拔剑转场",
                    "action": "挥剑劈裂山峰",
                    "subtitle": "命运开始反转",
                    "purpose": "制造史诗冲突",
                }
            ],
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    replication_check = next(check for check in review["checks"] if check["id"] == "replication")
    shot_trace_check = next(check for check in review["checks"] if check["id"] == "shot_table_traceability")
    assert replication_check["passed"] is True
    assert shot_trace_check["passed"] is False
    assert shot_trace_check["details"][0]["id"] == "shot_row_untraceable"
    assert "黑屏闪白后拔剑转场" in shot_trace_check["details"][0]["message"]
    assert any(gap["id"] == "shot_table_traceability" for gap in review["gaps"])
    assert review["level"] == "usable"


def test_render_analysis_report_lists_quality_gap_details() -> None:
    report = auto_analyzer.render_analysis_report(
        {
            "summary": "报告示例",
            "confidence": 0.8,
            "evidence_summary": {"visual_input_mode": "multi_image"},
            "quality_review": {
                "score": 85,
                "max_score": 100,
                "label": "可用但建议复核",
                "summary": "分镜表存在来源缺口。",
                "gaps": [
                    {
                        "id": "shot_table_traceability",
                        "label": "分镜表来源对应",
                        "message": "分镜表里新增了原视频没有的镜头。",
                        "action": "把分镜表改写为基于原视频时间线和证据的拍摄步骤。",
                        "details": [
                            {
                                "label": "分镜表越界",
                                "location": "replication.shot_table[0].time",
                                "time": 5,
                                "limit": 3,
                                "message": "分镜表写到了 5s，但视频时长约 3s。",
                            }
                        ],
                    },
                    {
                        "id": "content_ratio_balance",
                        "label": "内容占比自洽",
                        "message": "内容占比总和不接近 100%。",
                        "action": "把 content_ratio 改成 2-5 个结构段。",
                        "details": [
                            {
                                "label": "占比总和不自洽",
                                "location": "content_ratio",
                                "total": 160,
                                "limit": "90-110",
                                "message": "内容占比总和为 160%，应接近 100%。",
                            }
                        ],
                    },
                    {
                        "id": "engagement_data",
                        "label": "互动数据边界",
                        "message": "点赞、评论、分享不足以判断真实爆款强度。",
                        "action": "补齐作品链接互动数据或指标快照。",
                        "details": [
                            {
                                "label": "互动数据缺失",
                                "location": "engagement_data_quality",
                                "message": "点赞、评论、分享均为空或缺失，不能判断真实爆款强度。",
                            }
                        ],
                    },
                    {
                        "id": "audience",
                        "label": "受众与评论反馈",
                        "message": "评论洞察缺少评论证据支撑。",
                        "action": "导入评论后重跑，或把这部分标记为基于内容结构的推断。",
                        "details": [
                            {
                                "label": "缺少评论证据",
                                "location": "evidence_summary.comment_evidence",
                                "message": "没有评论证据时，用户需求和评论触发只能作为内容结构推断。",
                            }
                        ],
                    }
                ],
                "checks": [
                    {"id": "evidence", "label": "证据与推断边界", "passed": True},
                    {
                        "id": "shot_table_traceability",
                        "label": "分镜表来源对应",
                        "passed": False,
                        "action": "把分镜表改写为基于原视频时间线和证据的拍摄步骤。",
                    },
                ],
                "next_actions": ["把分镜表改写为基于原视频时间线和证据的拍摄步骤。"],
            },
        }
    )

    assert "### 优先质量缺口" in report
    assert "- [分镜来源] 分镜表来源对应" in report
    assert "问题：分镜表里新增了原视频没有的镜头。" in report
    assert "建议：把分镜表改写为基于原视频时间线和证据的拍摄步骤。" in report
    assert "细节：分镜表越界；replication.shot_table[0].time；5s / 上限 3s；分镜表写到了 5s，但视频时长约 3s。" in report
    assert "- [内容占比] 内容占比自洽" in report
    assert "细节：占比总和不自洽；content_ratio；160% / 目标 90-110%；内容占比总和为 160%，应接近 100%。" in report
    assert "- [互动数据] 互动数据边界" in report
    assert "细节：互动数据缺失；engagement_data_quality；点赞、评论、分享均为空或缺失，不能判断真实爆款强度。" in report
    assert "- [评论] 受众与评论反馈" in report
    assert "细节：缺少评论证据；evidence_summary.comment_evidence；没有评论证据时，用户需求和评论触发只能作为内容结构推断。" in report
    assert "### 模块检查明细" in report
    assert "通过 · [证据] 证据与推断边界" in report
    assert "待补 · [分镜来源] 分镜表来源对应" in report


def test_quality_review_requires_emotion_path_and_content_ratio_for_strong_report() -> None:
    result = {
        "summary": "其他模块完整，但缺少结构路径。",
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "求同款", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": detailed_timeline(),
        "emotion_path": [],
        "content_ratio": [],
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    structure_check = next(check for check in review["checks"] if check["id"] == "structure_depth")
    assert structure_check["passed"] is False
    assert any(gap["id"] == "structure_depth" for gap in review["gaps"])
    assert any("情绪路径" in action for action in review["next_actions"])
    assert review["score"] >= 85
    assert review["level"] == "usable"


def test_quality_review_rejects_emotion_path_without_ending_stage() -> None:
    result = {
        "summary": "其他模块完整，但情绪路径缺少结尾。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": detailed_timeline(),
        "emotion_path": ["开头用近景主体抓注意", "中段用字幕承诺维持价值感"],
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    structure_check = next(check for check in review["checks"] if check["id"] == "structure_depth")
    assert structure_check["passed"] is False
    assert structure_check["details"][0]["id"] == "emotion_path_too_short"
    assert any(gap["id"] == "structure_depth" for gap in review["gaps"])
    assert review["level"] == "usable"


def test_quality_review_accepts_structured_three_stage_emotion_path() -> None:
    result = {
        "summary": "其他模块完整，情绪路径覆盖三段。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": detailed_timeline(),
        "emotion_path": [
            {"stage": "开头", "emotion": "近景主体和字幕承诺共同制造停留"},
            {"stage": "中段", "emotion": "动作和字幕继续维持价值感"},
            {"stage": "结尾", "emotion": "用评论问题引导互动和复看"},
        ],
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    structure_check = next(check for check in review["checks"] if check["id"] == "structure_depth")
    assert structure_check["passed"] is True
    assert structure_check["details"] == []
    assert not any(gap["id"] == "structure_depth" for gap in review["gaps"])


def test_quality_review_rejects_vague_content_ratio_without_ratio_number() -> None:
    result = {
        "summary": "其他模块完整，但内容占比只是空泛描述。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "求同款", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": detailed_timeline(),
        "emotion_path": ["开头抓注意", "中段给价值", "结尾引导互动"],
        "content_ratio": ["开头吸引，中段承接，结尾互动"],
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    structure_check = next(check for check in review["checks"] if check["id"] == "structure_depth")
    assert structure_check["passed"] is False
    assert any(gap["id"] == "structure_depth" for gap in review["gaps"])
    assert any("内容占比" in action for action in review["next_actions"])
    assert review["level"] == "usable"


def test_quality_review_rejects_single_item_content_ratio_for_strong_report() -> None:
    result = {
        "summary": "其他模块完整，但内容占比只写了一个结构段。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": [{"name": "钩子", "percent": 40, "reason": "前三秒强"}],
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    ratio_check = next(check for check in review["checks"] if check["id"] == "content_ratio_balance")
    assert ratio_check["passed"] is False
    assert any(item["id"] == "content_ratio_too_few_items" for item in ratio_check["details"])
    assert any(gap["id"] == "content_ratio_balance" for gap in review["gaps"])
    assert review["level"] == "usable"


def test_quality_review_rejects_content_ratio_total_far_from_one_hundred() -> None:
    result = {
        "summary": "其他模块完整，但内容占比总和明显不对。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": [
            {"name": "钩子", "percent": 70, "reason": "前三秒强"},
            {"name": "动作", "percent": 60, "reason": "中段动作多"},
            {"name": "互动", "percent": 30, "reason": "结尾互动"},
        ],
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    ratio_check = next(check for check in review["checks"] if check["id"] == "content_ratio_balance")
    assert ratio_check["passed"] is False
    total_issue = next(item for item in ratio_check["details"] if item["id"] == "content_ratio_total")
    assert total_issue["total"] == 160
    assert total_issue["limit"] == "90-110"
    assert review["level"] == "usable"


def test_quality_review_accepts_balanced_content_ratio() -> None:
    result = {
        "summary": "其他模块完整，内容占比覆盖完整结构。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    ratio_check = next(check for check in review["checks"] if check["id"] == "content_ratio_balance")
    assert ratio_check["passed"] is True
    assert ratio_check["details"] == []
    assert not any(gap["id"] == "content_ratio_balance" for gap in review["gaps"])
    assert review["level"] == "strong"


def test_quality_review_rejects_category_mismatched_content_ratio() -> None:
    result = {
        "summary": "教程视频被拆成了通用钩子模板。",
        "content_category": "tutorial",
        "content_category_label": "教学 / 教程",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": [
            {"name": "钩子", "percent": 40, "reason": "前三秒强"},
            {"name": "主体信息", "percent": 35, "reason": "中段维持观看"},
            {"name": "互动转化", "percent": 25, "reason": "结尾引导评论"},
        ],
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    category_check = next(check for check in review["checks"] if check["id"] == "category_alignment")
    assert category_check["passed"] is False
    assert category_check["details"][0]["id"] == "category_ratio_mismatch"
    assert "教学 / 教程" in category_check["details"][0]["message"]
    assert any(gap["id"] == "category_alignment" for gap in review["gaps"])
    assert review["level"] == "usable"


def test_quality_review_accepts_category_specific_content_ratio() -> None:
    result = {
        "summary": "教程视频按痛点、步骤和结果拆解。",
        "content_category": "tutorial",
        "content_category_label": "教学 / 教程",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": [
            {"name": "痛点承诺", "percent": 30, "reason": "开头直接说明要解决的问题"},
            {"name": "教程步骤", "percent": 45, "reason": "中段拆操作方法和关键步骤"},
            {"name": "结果证明", "percent": 25, "reason": "结尾展示效果并给收藏理由"},
        ],
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    category_check = next(check for check in review["checks"] if check["id"] == "category_alignment")
    ratio_check = next(check for check in review["checks"] if check["id"] == "content_ratio_balance")
    assert category_check["passed"] is True
    assert category_check["details"] == []
    assert ratio_check["passed"] is True
    assert not any(gap["id"] == "category_alignment" for gap in review["gaps"])


def test_quality_review_marks_missing_engagement_data_as_review_gap() -> None:
    result = {
        "summary": "其他模块完整，但互动数据缺失。",
        "confidence": 0.82,
        "engagement_data_quality": "missing",
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    engagement_check = next(check for check in review["checks"] if check["id"] == "engagement_data")
    assert engagement_check["passed"] is False
    assert engagement_check["details"][0]["id"] == "engagement_data_missing"
    assert any(gap["id"] == "engagement_data" for gap in review["gaps"])
    assert any("指标快照" in action for action in review["next_actions"])
    assert review["level"] == "usable"


def test_quality_review_rejects_emotion_path_with_phase_names_only() -> None:
    result = {
        "summary": "其他模块完整，但情绪路径只有阶段名。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "求同款", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": detailed_timeline(),
        "emotion_path": ["开头", "中段", "结尾"],
        "content_ratio": [{"name": "钩子", "percent": 40, "reason": "前三秒强"}],
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }

    review = auto_analyzer._analysis_quality_review(result)
    structure_check = next(check for check in review["checks"] if check["id"] == "structure_depth")
    assert structure_check["passed"] is False
    assert any(gap["id"] == "structure_depth" for gap in review["gaps"])
    assert review["level"] == "usable"


def test_quality_review_requires_adaptation_boundary_for_strong_report() -> None:
    result = {
        "summary": "其他模块完整，但没有说明哪些不要照搬。",
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "求同款", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": detailed_timeline(),
        "emotion_path": ["开头抓注意", "中段给价值", "结尾引导互动"],
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": [],
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
        "risks": [],
    }

    review = auto_analyzer._analysis_quality_review(result)
    boundary_check = next(check for check in review["checks"] if check["id"] == "adaptation_boundary")
    assert boundary_check["passed"] is False
    assert any(gap["id"] == "adaptation_boundary" for gap in review["gaps"])
    assert any("不要照搬" in action for action in review["next_actions"])
    assert review["score"] >= 85
    assert review["level"] == "usable"


def test_quality_review_rejects_generic_adaptation_boundary() -> None:
    result = {
        "summary": "其他模块完整，但改编边界只是套话。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "评论里有人问同款链接", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": ["不要照搬原文"],
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
        "risks": [],
    }

    review = auto_analyzer._analysis_quality_review(result)
    boundary_check = next(check for check in review["checks"] if check["id"] == "adaptation_boundary")
    assert boundary_check["passed"] is False
    assert any(gap["id"] == "adaptation_boundary" for gap in review["gaps"])
    assert review["level"] == "usable"


def test_quality_review_requires_publish_package_beyond_title() -> None:
    result = {
        "summary": "其他模块完整，但发布包只有标题。",
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": detailed_evidence_summary(),
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": {"titles": ["3 秒学会这个近景开头"]},
    }

    review = auto_analyzer._analysis_quality_review(result)
    publishing_check = next(check for check in review["checks"] if check["id"] == "publishing")
    assert publishing_check["passed"] is False
    assert publishing_check["details"][0]["id"] == "publish_support_missing"
    assert any(gap["id"] == "publishing" for gap in review["gaps"])
    assert any("发布文案" in action for action in review["next_actions"])
    assert review["level"] == "usable"


def test_quality_review_rejects_generic_publish_package_support() -> None:
    result = {
        "summary": "其他模块完整，但发布包只有占位文案。",
        "confidence": 0.82,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "求同款", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": {
            "titles": ["测试标题"],
            "caption": "保存这套结构。",
            "hashtags": ["短视频拆解"],
        },
    }

    review = auto_analyzer._analysis_quality_review(result)
    publishing_check = next(check for check in review["checks"] if check["id"] == "publishing")
    assert publishing_check["passed"] is False
    issue_ids = {item["id"] for item in publishing_check["details"]}
    assert "publish_titles_too_generic" in issue_ids
    assert "publish_caption_too_generic" in issue_ids
    assert "publish_hashtags_too_generic" in issue_ids
    assert any(gap["id"] == "publishing" for gap in review["gaps"])
    assert review["level"] == "usable"


def test_existing_auto_analysis_migrates_quality_fields_for_old_reports(tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "old-report.mp4")
    local_video = upload_video(video_path, source_url="https://www.douyin.com/video/7651938969785849555")
    case_response = client.post("/api/cases/build", json={"local_video_id": local_video["local_video_id"]})
    assert case_response.status_code == 200
    case_id = case_response.json()["case"]["case_id"]
    case_dir = Path(case_response.json()["case"]["video_path"]).parent

    old_result = {
        "summary": "旧版拆解",
        "hook_analysis": {
            "first_impression": "开头主体清晰",
            "why_stop_scrolling": "前 3 秒有明确画面主体",
            "first_3_seconds": ["0s 人物近景居中出现"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": {"audience_needs": ["求同款"]},
        "timeline": detailed_timeline(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
    }
    (case_dir / "analysis_result.json").write_text(json.dumps(old_result, ensure_ascii=False, indent=2), encoding="utf-8")
    (case_dir / "analysis_report.md").write_text("# 旧版报告\n", encoding="utf-8")

    db = SessionLocal()
    try:
        artifact = db.get(CaseArtifact, case_id)
        result, report = existing_auto_analysis(artifact)
    finally:
        db.close()

    assert result is not None
    assert "evidence_summary" in result
    assert "quality_review" in result
    assert "manual_review_context" in result
    assert result["quality_review"]["score"] > 0
    assert "## 拆解质量自检" in report
    persisted = json.loads((case_dir / "analysis_result.json").read_text(encoding="utf-8"))
    assert "quality_review" in persisted
    assert "## 证据与推断边界" in (case_dir / "analysis_report.md").read_text(encoding="utf-8")


def test_existing_auto_analysis_recomputes_stale_quality_review(tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "stale-report.mp4")
    local_video = upload_video(video_path, source_url="https://www.douyin.com/video/7651938969785849666")
    case_response = client.post("/api/cases/build", json={"local_video_id": local_video["local_video_id"]})
    assert case_response.status_code == 200
    case_id = case_response.json()["case"]["case_id"]
    case_dir = Path(case_response.json()["case"]["video_path"]).parent

    stale_result = {
        "summary": "旧规则标成 strong 的报告",
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺", "2s 抬手动作带动节奏变化"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "comment_insights": detailed_comment_insights(),
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头金句", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "求同款", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": ["旧报告遗留的证据缺口"],
        },
        "timeline": detailed_timeline(),
        "emotion_path": detailed_emotion_path(),
        "content_ratio": detailed_content_ratio(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": detailed_publish_package(),
        "quality_review": {
            "score": 100,
            "max_score": 100,
            "level": "strong",
            "label": "旧规则强行完整",
            "summary": "旧规则结果",
            "checks": [],
            "gaps": [],
            "next_actions": [],
        },
    }
    (case_dir / "analysis_result.json").write_text(
        json.dumps(stale_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (case_dir / "analysis_report.md").write_text("# 旧版 strong 报告\n", encoding="utf-8")

    db = SessionLocal()
    try:
        artifact = db.get(CaseArtifact, case_id)
        result, report = existing_auto_analysis(artifact)
    finally:
        db.close()

    assert result is not None
    assert result["quality_review"]["level"] == "usable"
    assert any(gap["id"] == "evidence_gaps" for gap in result["quality_review"]["gaps"])
    persisted = json.loads((case_dir / "analysis_result.json").read_text(encoding="utf-8"))
    assert persisted["quality_review"]["level"] == "usable"
    assert "## 拆解质量自检" in report


def test_existing_auto_analysis_applies_current_enrichment_usage_gates(tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "old-enrichment-gates.mp4")
    local_video = upload_video(video_path, source_url="https://www.douyin.com/video/7651938969785849771")
    case_response = client.post("/api/cases/build", json={"local_video_id": local_video["local_video_id"]})
    assert case_response.status_code == 200
    case_id = case_response.json()["case"]["case_id"]
    case_dir = Path(case_response.json()["case"]["video_path"]).parent

    asr_dir = case_dir / "enrichment" / "asr"
    ocr_dir = case_dir / "enrichment" / "ocr"
    comments_dir = case_dir / "enrichment" / "comments"
    asr_dir.mkdir(parents=True, exist_ok=True)
    ocr_dir.mkdir(parents=True, exist_ok=True)
    comments_dir.mkdir(parents=True, exist_ok=True)
    (asr_dir / "transcript.json").write_text(
        json.dumps({"status": "success", "full_text": "开头说明收益", "segments": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (ocr_dir / "frame_ocr.json").write_text(
        json.dumps({"status": "success", "full_text": "封面承诺", "frames": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (ocr_dir / "subtitle_ocr.json").write_text(
        json.dumps({"status": "success", "full_text": "", "frames": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (ocr_dir / "cover_ocr.json").write_text(
        json.dumps({"status": "success", "full_text": "三秒学会"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (comments_dir / "comment_summary.json").write_text(
        json.dumps(
            {
                "total_comments": 3,
                "top_needs": ["求教程"],
                "high_frequency_words": ["教程"],
                "comment_hooks": ["催更"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    old_result = {
        "summary": "旧报告没有真正消费富化证据",
        "confidence": 0.9,
        "hook_analysis": {
            "first_impression": "第一眼强",
            "why_stop_scrolling": "有停留理由",
            "first_3_seconds": ["0s 人物近景居中出现", "1s 字幕给出结果承诺"],
        },
        "visual_analysis": detailed_visual_analysis(),
        "copywriting_analysis": detailed_copywriting_analysis(),
        "speech_analysis": {"has_speech": True},
        "screen_text_analysis": {"has_text": True},
        "comment_insights": {},
        "emotion_path": ["开头抓注意", "中段给价值"],
        "content_ratio": [{"name": "钩子", "percent": 50, "reason": "前三秒强"}],
        "timeline": detailed_timeline(),
        "replication": {
            "copyable_points": ["前三秒主体"],
            "avoid_copying": detailed_avoid_copying(),
            "remake_angle": "复刻结构",
            "opening_3s": "主体和字幕同时出现",
            "shot_table": detailed_shot_table(),
        },
        "publish_package": {"titles": ["测试标题"], "caption": "测试文案"},
        "evidence_summary": {
            "visual_input_mode": "multi_image",
            "visual_evidence": [{"claim": "视觉", "evidence": "关键帧", "confidence": "high"}],
            "asr_evidence": [{"claim": "口播", "evidence": "开头说明收益", "confidence": "high"}],
            "ocr_evidence": [{"claim": "字幕", "evidence": "封面承诺", "confidence": "high"}],
            "comment_evidence": [{"claim": "评论", "evidence": "求教程", "confidence": "high"}],
            "inferred_points": [],
            "evidence_gaps": [],
        },
        "quality_review": {"score": 100, "level": "strong", "gaps": [], "checks": [], "next_actions": []},
    }
    (case_dir / "analysis_result.json").write_text(json.dumps(old_result, ensure_ascii=False, indent=2), encoding="utf-8")
    (case_dir / "analysis_report.md").write_text("# 旧版 strong 报告\n", encoding="utf-8")

    db = SessionLocal()
    try:
        artifact = db.get(CaseArtifact, case_id)
        result, report = existing_auto_analysis(artifact)
    finally:
        db.close()

    assert result is not None
    gaps = result["evidence_summary"]["evidence_gaps"]
    assert result["enrichment_usage"]["asr_used"] is True
    assert result["enrichment_usage"]["ocr_used"] is True
    assert result["enrichment_usage"]["comments_used"] is True
    assert any("ASR 转写已可用" in gap for gap in gaps)
    assert any("OCR 文字已可用" in gap for gap in gaps)
    assert any("评论摘要已可用" in gap for gap in gaps)
    assert any(gap["id"] == "evidence_gaps" for gap in result["quality_review"]["gaps"])
    assert result["quality_review"]["level"] != "strong"
    persisted = json.loads((case_dir / "analysis_result.json").read_text(encoding="utf-8"))
    assert any("ASR 转写已可用" in gap for gap in persisted["evidence_summary"]["evidence_gaps"])
    assert "ASR 转写已可用" in report


def test_existing_auto_analysis_keeps_historical_text_only_visual_mode(tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "text-only-report.mp4")
    local_video = upload_video(video_path, source_url="https://www.douyin.com/video/7651938969785849888")
    case_response = client.post("/api/cases/build", json={"local_video_id": local_video["local_video_id"]})
    assert case_response.status_code == 200
    case_id = case_response.json()["case"]["case_id"]
    case_dir = Path(case_response.json()["case"]["video_path"]).parent
    assert list((case_dir / "keyframes").glob("frame_*.jpg"))

    text_only_result = {
        "summary": "旧报告是文本降级生成的",
        "hook_analysis": {
            "first_impression": "基于标题推断",
            "why_stop_scrolling": "文本推断",
            "first_3_seconds": ["无视觉输入"],
        },
        "visual_analysis": {"scene": "文本推断", "subject": "文本推断", "movement_rhythm": "文本推断"},
        "copywriting_analysis": detailed_copywriting_analysis(),
        "evidence_summary": {
            "visual_input_mode": "text_only",
            "visual_evidence": [
                {"claim": "旧模型错误保留的视觉判断", "evidence": "并未真实看图", "confidence": "high"}
            ],
            "asr_evidence": [],
            "ocr_evidence": [],
            "comment_evidence": [],
            "inferred_points": ["本次没有成功读取视觉图片，视觉拆解需要人工复核"],
            "evidence_gaps": ["缺少可用视觉输入"],
        },
        "timeline": [{"time_range": "0-3s", "visual": "文本推断", "purpose": "待复核"}],
        "replication": {
            "copyable_points": ["标题结构"],
            "remake_angle": "复刻标题",
            "opening_3s": "待看图确认",
            "shot_table": [{"time": "0-3s", "visual": "待复核", "action": "待复核"}],
        },
        "publish_package": detailed_publish_package(),
    }
    (case_dir / "analysis_result.json").write_text(
        json.dumps(text_only_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (case_dir / "analysis_report.md").write_text("# 旧版 text_only 报告\n", encoding="utf-8")

    db = SessionLocal()
    try:
        artifact = db.get(CaseArtifact, case_id)
        result, report = existing_auto_analysis(artifact)
    finally:
        db.close()

    assert result is not None
    evidence = result["evidence_summary"]
    assert evidence["visual_input_mode"] == "text_only"
    assert evidence["visual_evidence"] == []
    assert "旧模型错误保留的视觉判断" not in json.dumps(evidence, ensure_ascii=False)
    assert any("缺少可用视觉输入" in gap for gap in evidence["evidence_gaps"])
    assert result["quality_review"]["level"] == "weak"
    assert any(gap["id"] == "visual_input" for gap in result["quality_review"]["gaps"])
    assert "## 证据与推断边界" in report
    persisted = json.loads((case_dir / "analysis_result.json").read_text(encoding="utf-8"))
    assert persisted["evidence_summary"]["visual_input_mode"] == "text_only"
    assert persisted["quality_review"]["level"] == "weak"


def test_case_detail_job_polling_keeps_buttons_disabled_until_terminal_state() -> None:
    script = Path("app/static/case_detail.js").read_text(encoding="utf-8")
    assert "function wait(ms)" in script
    assert "await wait(900);\n  return pollAnalysisJob(jobId);" in script
    assert "await wait(700);\n  return pollEnrichmentJob(jobId);" in script
    assert "await wait(900);\n  return pollAsrJob(jobId);" in script
    assert "await wait(900);\n  return pollOcrJob(jobId);" in script
    assert "pollAnalysisJob(jobId).catch" not in script
    assert "pollEnrichmentJob(jobId).catch" not in script
    assert "pollAsrJob(jobId).catch" not in script
    assert "pollOcrJob(jobId).catch" not in script


def test_case_detail_renders_critical_readiness_gaps() -> None:
    script = Path("app/static/case_detail.js").read_text(encoding="utf-8")
    stylesheet = Path("app/static/app.css").read_text(encoding="utf-8")
    template = Path("app/templates/case_detail.html").read_text(encoding="utf-8")

    assert "function renderCriticalGaps(gaps)" in script
    assert "readiness.critical_gaps || []" in script
    assert "关键缺口" in script
    assert "关键证据已齐" in script
    assert ".readiness-critical-gaps" in stylesheet
    assert ".readiness-critical-item" in stylesheet
    assert 'id="worksheet-review"' in template
    assert "function renderWorksheetReview(review)" in script
    assert "field.hint" in script
    assert ".worksheet-review-grid" in stylesheet


def test_case_detail_renders_top_diagnosis_panel() -> None:
    script = Path("app/static/case_detail.js").read_text(encoding="utf-8")
    stylesheet = Path("app/static/app.css").read_text(encoding="utf-8")
    template = Path("app/templates/case_detail.html").read_text(encoding="utf-8")

    assert 'id="primary-workflow-summary"' in template
    assert 'data-primary-action="copy_prompt"' in template
    assert 'data-primary-action="download_input"' in template
    assert 'data-primary-action="run_ai"' in template
    assert 'data-case-tab="' not in template
    assert 'data-case-tab-panel' not in template
    assert "完整分析" in template
    assert "高级 / 后台材料" in template
    assert "素材包与 Prompt" in template
    assert "人工验收与工作表" in template
    assert "富化数据：ASR / OCR / 评论 / 指标" in template
    assert "质量校准：诊断 / rerun_plan / 样本库" in template
    assert "toolbar-actions" not in template
    assert 'id="copy-ai-report-button"' in template
    assert template.index("素材包与 Prompt") < template.index('data-primary-action="copy_prompt"')
    assert template.index("素材包与 Prompt") < template.index('id="run-auto-analysis-button"')
    assert '<details class="advanced-subsection" open>' not in template
    assert "高级富化" in template
    assert template.index("富化数据：ASR / OCR / 评论 / 指标") < template.index('id="asr-placeholder-button"')
    assert template.index("富化数据：ASR / OCR / 评论 / 指标") < template.index('id="ocr-placeholder-button"')
    assert template.index("高级富化") < template.index('id="comments-import-text"')
    assert "function setCaseTab(tab)" not in script
    assert "caseTabButtons" not in script
    assert "caseTabPanels" not in script
    assert ".case-tab-nav" not in stylesheet
    assert ".case-tab-button" not in stylesheet
    assert ".developer-workspace" in stylesheet
    assert ".advanced-subsection" in stylesheet
    assert ".advanced-subsection > summary" in stylesheet
    assert ".public-report-grid" in stylesheet
    assert "function renderPrimaryWorkflow(data)" in script
    assert "data.primary_workflow" in script
    assert ".primary-workflow-card" in stylesheet
    assert 'id="case-diagnosis-summary"' in template
    assert "拆解诊断" in template
    assert "用于校准 AI 输出质量" in template
    assert "const caseDiagnosisSummary" in script
    assert "function renderCaseDiagnosis(data)" in script
    assert "function renderDiagnosisActions(actions)" in script
    assert "diagnosisSourceLabels" in script
    assert "data.case_diagnosis" in script
    assert "renderCaseDiagnosis(loadedCase)" in script
    assert "caseDiagnosisSummary.addEventListener" in script
    assert "推荐动作" in script
    assert 'action.mode === "click"' in script
    assert "人工验收" in script
    assert "AI 质量" in script
    assert "富化阻塞" in script
    assert ".case-diagnosis-card" in stylesheet
    assert ".case-diagnosis-hero" in stylesheet
    assert ".case-diagnosis-featured-action" in stylesheet
    assert ".case-diagnosis-score-grid" in stylesheet
    assert ".case-diagnosis-blocker" in stylesheet


def test_case_detail_renders_quality_gap_panel() -> None:
    script = Path("app/static/case_detail.js").read_text(encoding="utf-8")
    stylesheet = Path("app/static/app.css").read_text(encoding="utf-8")

    assert "function renderQualityGapPanel(gaps)" in script
    assert "function renderQualityGapDetails(details)" in script
    assert "function qualityGapCategory(gap)" in script
    assert "优先质量缺口" in script
    assert "质量闸门已通过" in script
    assert "claim_traceability" in script
    assert "enrichment_usage" in script
    assert "copyable_traceability" in script
    assert "shot_table_traceability" in script
    assert "time_bounds" in script
    assert "content_ratio_balance" in script
    assert "engagement_data" in script
    assert "item.location" in script
    assert "item.time" in script
    assert "item.total" in script
    assert "${renderQualityGapPanel(quality.gaps)}" in script
    assert ".quality-gap-panel" in stylesheet
    assert ".quality-gap-item" in stylesheet
    assert ".quality-gap-label" in stylesheet
    assert ".quality-gap-detail-list" in stylesheet
    assert ".quality-gap-item.time" in stylesheet


def test_case_detail_renders_quality_acceptance_panel() -> None:
    script = Path("app/static/case_detail.js").read_text(encoding="utf-8")
    stylesheet = Path("app/static/app.css").read_text(encoding="utf-8")
    template = Path("app/templates/case_detail.html").read_text(encoding="utf-8")

    assert 'id="quality-acceptance-summary"' in template
    assert 'id="rerun-strategy-panel"' in template
    assert 'id="save-quality-acceptance-button"' in template
    assert 'id="save-quality-acceptance-and-rerun-button"' in template
    assert 'id="download-rerun-plan-button"' in template
    assert 'id="download-rerun-plan-markdown-button"' in template
    assert "保存并重新拆解" in template
    assert "下载 rerun_plan.json" in template
    assert "下载 rerun_plan.md" in template
    assert "function renderQualityAcceptance(acceptance)" in script
    assert "function renderRerunCompliance(compliance)" in script
    assert "result.rerun_compliance" in script
    assert "重跑合规" in script
    assert "function renderRerunStrategy(data)" in script
    assert "function renderRerunEvidenceSummary(strategy)" in script
    assert "summary.ready" in script
    assert "summary.missing" in script
    assert "function renderRerunEvidenceMeta(item)" in script
    assert "item.char_count" in script
    assert "item.segment_count" in script
    assert "item.count" in script
    assert "item.sources" in script
    assert "item.excerpt" in script
    assert "function currentRerunStrategy(data)" in script
    assert "function missingRerunEvidence(strategy)" in script
    assert "function confirmMissingEvidenceBeforeRerun(data)" in script
    assert "function renderRerunEvidenceWarning(strategy)" in script
    assert "manual_review_context.rerun_strategy" in script
    assert "item.action_label" in script
    assert "item.target || item.action_target" in script
    assert "rerunStrategyPanel.addEventListener" in script
    assert "修正目标" in script
    assert "禁止重复" in script
    assert "必须核对证据" in script
    assert "先补证据会更准" in script
    assert "window.confirm" in script
    assert "已取消重新拆解" in script
    assert "confirmMissingEvidenceBeforeRerun(loadedCase)" in script
    assert "renderRerunStrategy(loadedCase)" in script
    assert "function collectQualityAcceptance()" in script
    assert "function saveQualityAcceptance(successMessage)" in script
    assert "function startAutoAnalysisJob()" in script
    assert "saveQualityAcceptanceAndRerunButton.addEventListener" in script
    assert "人工验收反馈会进入本次分析上下文" in script
    assert 'job.status === "success"' in script
    assert "已保存质量验收，但重新拆解失败" in script
    assert "quality_acceptance.json" in script
    assert "rerun_plan.json" in script
    assert "rerun_plan.md" in script
    assert "downloadRerunPlanButton.addEventListener" in script
    assert "downloadRerunPlanMarkdownButton.addEventListener" in script
    assert "artifact_urls?.rerun_plan" in script
    assert "artifact_urls?.rerun_plan_markdown" in script
    assert "/quality-acceptance" in script
    assert ".quality-acceptance-form" in stylesheet
    assert ".acceptance-overview" in stylesheet
    assert ".rerun-strategy-panel" in stylesheet
    assert ".rerun-strategy-grid" in stylesheet
    assert ".rerun-strategy-item" in stylesheet
    assert ".rerun-evidence-summary" in stylesheet
    assert ".rerun-evidence-meta" in stylesheet
    assert ".rerun-evidence-excerpt" in stylesheet
    assert ".rerun-evidence-warning" in stylesheet


def test_case_detail_renders_quality_calibration_panel() -> None:
    script = Path("app/static/case_detail.js").read_text(encoding="utf-8")
    stylesheet = Path("app/static/app.css").read_text(encoding="utf-8")
    template = Path("app/templates/case_detail.html").read_text(encoding="utf-8")

    assert 'id="quality-calibration-summary"' in template
    assert 'id="save-quality-calibration-record-button"' in template
    assert "校准样本" in template
    assert "function renderQualityCalibration(data)" in script
    assert "function renderRecommendationList(recommendations)" in script
    assert "item.source_issue_ids" in script
    assert "item.action_target" in script
    assert "item.action_mode" in script
    assert "触发项" in script
    assert "data.quality_calibration" in script
    assert "renderQualityCalibration(loadedCase)" in script
    assert "/quality-calibration/record" in script
    assert "规则建议" in script
    assert "calibration.recommendations" in script
    assert "renderRecommendationList(recommendations)" in script
    assert "quality-calibration-hero" in script
    assert "qualityCalibrationSummary.addEventListener" in script
    assert ".quality-calibration-summary" in stylesheet
    assert ".quality-calibration-grid" in stylesheet
    assert ".quality-calibration-cardlet" in stylesheet
    assert ".quality-recommendation-list" in stylesheet
    assert ".quality-recommendation-item" in stylesheet
    assert ".quality-recommendation-title" in stylesheet
    assert ".recommendation-action" in stylesheet


def test_calibration_page_renders_filterable_record_list() -> None:
    script = Path("app/static/calibration.js").read_text(encoding="utf-8")
    stylesheet = Path("app/static/app.css").read_text(encoding="utf-8")
    template = Path("app/templates/calibration.html").read_text(encoding="utf-8")

    assert 'id="copy-calibration-report-button"' in template
    assert 'id="download-calibration-report-button"' in template
    assert 'id="calibration-filter-form"' in template
    assert 'id="calibration-diagnosis-status-filter"' in template
    assert 'id="calibration-insights"' in template
    assert 'id="calibration-recommendations"' in template
    assert 'id="calibration-records"' in template
    assert "校准样本库" in template
    assert "常见质量问题" in template
    assert "规则改进建议" in template
    assert "/api/cases/quality-calibration/records" in script
    assert "/api/cases/quality-calibration/report" in script
    assert "function loadCalibrationReport()" in script
    assert "quality_calibration_report.md" in script
    assert "function renderInsights(payload)" in script
    assert "function renderRecommendations(payload)" in script
    assert "function renderIssueList(items)" in script
    assert "function renderRecords(records)" in script
    assert "function formatEvidenceCompletion(summary)" in script
    assert "summary?.evidence_completion" in script
    assert "function renderRerunEvidenceList(items)" in script
    assert "function renderRerunEvidenceSummary(strategy)" in script
    assert "证据完成度" in script
    assert "筛选证据" in script
    assert "calibrationStatusLabels" in script
    assert "diagnosisStatusLabels" in script
    assert "calibrationDiagnosisStatusFilter" in script
    assert 'params.set("diagnosis_status"' in script
    assert "top_human_blockers" in script
    assert "top_diagnosis_blockers" in script
    assert "top_diagnosis_actions" in script
    assert "top_rerun_evidence_gaps" in script
    assert "top_rerun_compliance_failures" in script
    assert "重跑合规失败" in script
    assert "by_diagnosis_status" in script
    assert "record.case_diagnosis" in script
    assert "record.rerun_strategy" in script
    assert "item.char_count" in script
    assert "item.segment_count" in script
    assert "item.count" in script
    assert "item.sources" in script
    assert "item.excerpt" in script
    assert "item.source_issue_ids" in script
    assert "item.action_target" in script
    assert "页面动作" in script
    assert "重跑策略" in script
    assert "filtered_recommendations" in script
    assert ".calibration-record-list" in stylesheet
    assert ".calibration-record-grid" in stylesheet
    assert ".calibration-evidence-list" in stylesheet
    assert ".calibration-insights-grid" in stylesheet
    assert ".calibration-recommendation-list" in stylesheet
    assert ".issue-list" in stylesheet


def test_quality_calibration_recommendations_use_rerun_evidence_gaps() -> None:
    recommendations = case_routes._quality_calibration_recommendations(
        {
            "top_ai_gaps": [],
            "top_human_blockers": [],
            "top_readiness_gaps": [],
            "top_rerun_evidence_gaps": [
                {"id": "asr", "label": "ASR 转写", "count": 2},
                {"id": "ocr", "label": "OCR 文字", "count": 1},
                {"id": "comments", "label": "评论摘要", "count": 3},
            ],
        }
    )

    recommendation_ids = {item["id"] for item in recommendations}
    assert "complete_asr_before_rerun" in recommendation_ids
    assert "complete_ocr_before_rerun" in recommendation_ids
    assert "import_comments_before_rerun" in recommendation_ids
    recommendation_by_id = {item["id"]: item for item in recommendations}
    assert recommendation_by_id["complete_asr_before_rerun"]["action_target"] == "#asr-placeholder-button"
    assert recommendation_by_id["complete_asr_before_rerun"]["action_mode"] == "click"
    assert recommendation_by_id["complete_ocr_before_rerun"]["action_target"] == "#ocr-placeholder-button"
    assert recommendation_by_id["complete_ocr_before_rerun"]["action_mode"] == "click"
    assert recommendation_by_id["import_comments_before_rerun"]["action_target"] == "#comments-import-text"
    assert recommendation_by_id["import_comments_before_rerun"]["action_mode"] == "focus"


def test_quality_calibration_recommendations_use_time_bounds_gap() -> None:
    recommendations = case_routes._quality_calibration_recommendations(
        {
            "top_ai_gaps": [
                {"id": "time_bounds", "label": "时间边界", "count": 2},
            ],
            "top_human_blockers": [],
            "top_readiness_gaps": [],
            "top_rerun_evidence_gaps": [],
        }
    )

    recommendation_by_id = {item["id"]: item for item in recommendations}
    assert "enforce_source_time_bounds" in recommendation_by_id
    recommendation = recommendation_by_id["enforce_source_time_bounds"]
    assert recommendation["label"] == "锁定原片时间边界"
    assert recommendation["priority"] == 84
    assert recommendation["source_issue_ids"] == ["time_bounds"]
    assert recommendation["action_target"] == "#run-auto-analysis-button"
    assert recommendation["action_mode"] == "click"
    assert "ffprobe" in recommendation["action"]


def test_quality_calibration_recommendations_use_content_ratio_gap() -> None:
    recommendations = case_routes._quality_calibration_recommendations(
        {
            "top_ai_gaps": [
                {"id": "content_ratio_balance", "label": "内容占比自洽", "count": 2},
            ],
            "top_human_blockers": [],
            "top_readiness_gaps": [],
            "top_rerun_evidence_gaps": [],
        }
    )

    recommendation_by_id = {item["id"]: item for item in recommendations}
    assert "tighten_content_ratio_gate" in recommendation_by_id
    recommendation = recommendation_by_id["tighten_content_ratio_gate"]
    assert recommendation["label"] == "校准内容占比结构"
    assert recommendation["priority"] == 82
    assert "content_ratio_balance" in recommendation["source_issue_ids"]
    assert recommendation["action_target"] == "#run-auto-analysis-button"
    assert recommendation["action_mode"] == "click"
    assert "percent 总和约 100%" in recommendation["action"]


def test_quality_calibration_recommendations_use_category_alignment_gap() -> None:
    recommendations = case_routes._quality_calibration_recommendations(
        {
            "top_ai_gaps": [
                {"id": "category_alignment", "label": "内容类型适配", "count": 2},
            ],
            "top_human_blockers": [],
            "top_readiness_gaps": [],
            "top_rerun_evidence_gaps": [],
        }
    )

    recommendation_by_id = {item["id"]: item for item in recommendations}
    assert "enforce_category_specific_lens" in recommendation_by_id
    recommendation = recommendation_by_id["enforce_category_specific_lens"]
    assert recommendation["label"] == "收紧内容类型拆解"
    assert recommendation["priority"] == 81
    assert recommendation["source_issue_ids"] == ["category_alignment"]
    assert recommendation["action_label"] == "调整类型"
    assert recommendation["action_target"] == "#analysis-category-select"
    assert recommendation["action_mode"] == "focus"
    assert "content_category" in recommendation["action"]


def test_quality_calibration_recommendations_use_engagement_data_gap() -> None:
    recommendations = case_routes._quality_calibration_recommendations(
        {
            "top_ai_gaps": [
                {"id": "engagement_data", "label": "互动数据边界", "count": 2},
            ],
            "top_human_blockers": [],
            "top_readiness_gaps": [],
            "top_rerun_evidence_gaps": [],
        }
    )

    recommendation_by_id = {item["id"]: item for item in recommendations}
    assert "complete_engagement_metrics" in recommendation_by_id
    recommendation = recommendation_by_id["complete_engagement_metrics"]
    assert recommendation["label"] == "先补互动指标边界"
    assert recommendation["priority"] == 81
    assert "engagement_data" in recommendation["source_issue_ids"]
    assert recommendation["action_label"] == "记录指标"
    assert recommendation["action_target"] == "#metric-snapshot-button"
    assert recommendation["action_mode"] == "click"
    assert "爆款强度判断降级" in recommendation["action"]


def test_ocr_case_job_reports_provider_not_configured(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.services.ocr.settings.ocr_provider", "disabled")
    video_path = make_sample_video(tmp_path / "ocr-disabled.mp4")
    local_video = upload_video(video_path)
    case_response = client.post("/api/cases/build", json={"local_video_id": local_video["local_video_id"]})
    assert case_response.status_code == 200
    case_id = case_response.json()["case"]["case_id"]

    create_response = client.post("/api/jobs/ocr-case", json={"case_id": case_id})
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
    assert job["status"] == "failed"
    assert job["error_code"] == "OCR_PROVIDER_NOT_CONFIGURED"


def test_ocr_auto_provider_selects_rapidocr_when_installed(monkeypatch) -> None:
    from app.services.ocr import RapidOCRProvider, _configured_provider

    monkeypatch.setattr("app.services.ocr.settings.ocr_provider", "auto")
    monkeypatch.setattr("app.services.ocr.importlib.util.find_spec", lambda name: object() if name == "rapidocr_onnxruntime" else None)

    provider = _configured_provider()

    assert isinstance(provider, RapidOCRProvider)


def test_enrich_case_job_reports_success(tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "enrichment-job.mp4")
    local_video = upload_video(video_path)
    case_response = client.post("/api/cases/build", json={"local_video_id": local_video["local_video_id"]})
    assert case_response.status_code == 200
    case_id = case_response.json()["case"]["case_id"]

    create_response = client.post("/api/jobs/enrich-case", json={"case_id": case_id})
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
    assert job["result_json"]["manifest"]["case_id"] == case_id
    assert job["result_json"]["manifest"]["statuses"]["metrics"] == "success"


def test_profile_video_item_engagement_score() -> None:
    assert profile_engagement_score(100, 3, 4) == 147
    item = ProfileVideoItem(aweme_id="7622653084993647603", like_count=100, comment_count=3, share_count=4)
    assert item.engagement_score == 147


def test_manual_links_profile_provider_extracts_and_deduplicates_aweme_ids() -> None:
    provider = ManualLinksProfileProvider()
    result = provider.scan(
        ProfileScanRequest(
            manual_links="""
            https://www.douyin.com/video/7622653084993647603
            复制口令 https://www.douyin.com/user/self?modal_id=7622653084993647603
            https://www.douyin.com/video/7539896907901062452
            这行没有作品
            """,
            count=20,
            sort_by="like_count",
        )
    )

    assert result.provider == "manual_links"
    assert [item.aweme_id for item in result.items] == ["7622653084993647603", "7539896907901062452"]
    assert result.items[0].webpage_url.endswith("7622653084993647603")
    assert result.import_stats["recognized_count"] == 2
    assert result.import_stats["duplicate_count"] == 1
    assert result.import_stats["invalid_count"] == 1
    assert "成功识别 2 条" in result.warnings[0]


def test_manual_links_profile_provider_resolves_short_work_url(monkeypatch) -> None:
    class FakeResponse:
        status_code = 302
        is_redirect = True
        headers = {"location": "https://www.douyin.com/video/7622653084993647603"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.services.profile_scan.httpx.Client", FakeClient)
    result = ManualLinksProfileProvider().scan(
        ProfileScanRequest(
            manual_links="8.19 abc:/ 作品标题 https://v.douyin.com/abc123/ 复制此链接打开抖音",
            count=20,
            sort_by="like_count",
        )
    )

    assert result.items[0].aweme_id == "7622653084993647603"
    assert result.import_stats["recognized_count"] == 1


def test_structured_profile_import_supports_json_and_csv() -> None:
    json_response = client.post(
        "/api/profile/scan",
        json={
            "structured_items": json.dumps(
                [
                    {
                        "aweme_id": "7622653084993647603",
                        "title": "JSON作品",
                        "source_url": "https://www.douyin.com/video/7622653084993647603",
                        "media_type": "video",
                        "like_count": 100,
                    },
                    {
                        "aweme_id": "7622653084993647604",
                        "title": "图文",
                        "source_url": "https://www.douyin.com/note/7622653084993647604",
                        "media_type": "image",
                    },
                ],
                ensure_ascii=False,
            ),
            "count": 20,
        },
    )
    assert json_response.status_code == 200
    json_payload = json_response.json()
    assert json_payload["provider"] == "structured_items"
    assert json_payload["import_stats"]["recognized_count"] == 2
    assert json_payload["items"][0]["can_build_case"] is True
    assert json_payload["items"][1]["can_build_case"] is False

    csv_response = client.post(
        "/api/profile/scan",
        json={
            "structured_items": "aweme_id,title,source_url,media_type,like_count\n7622653084993647605,CSV作品,https://www.douyin.com/video/7622653084993647605,video,20\n",
            "count": 20,
        },
    )
    assert csv_response.status_code == 200
    assert csv_response.json()["items"][0]["title"] == "CSV作品"


def test_profile_items_sort_by_metrics() -> None:
    items = [
        ProfileVideoItem(aweme_id="100000000000000001", like_count=10, comment_count=1, share_count=0, create_time="2026-01-01"),
        ProfileVideoItem(aweme_id="100000000000000002", like_count=2, comment_count=9, share_count=0, create_time="2026-01-03"),
        ProfileVideoItem(aweme_id="100000000000000003", like_count=1, comment_count=0, share_count=10, create_time="2026-01-02"),
    ]

    assert sorted_profile_items(items, "like_count")[0].aweme_id == "100000000000000001"
    assert sorted_profile_items(items, "comment_count")[0].aweme_id == "100000000000000002"
    assert sorted_profile_items(items, "share_count")[0].aweme_id == "100000000000000003"
    assert sorted_profile_items(items, "engagement_score")[0].aweme_id == "100000000000000003"
    assert sorted_profile_items(items, "create_time")[0].aweme_id == "100000000000000002"


def test_profile_share_url_normalizes_to_douyin_profile_url() -> None:
    sec_uid = "MS4wLjABAAAAhlyWuh2hl4qtSRklFBUXI2OeIFZHcSVT8gAwdYEVEER_BL6pkbRCLoyncMBeVWwV"
    share_url = f"https://www.iesdouyin.com/share/user/{sec_uid}?sec_uid={sec_uid}&from_aid=6383"

    normalized = normalize_profile_url(share_url, None)

    assert normalized == f"https://www.douyin.com/user/{sec_uid}"
    assert extract_sec_user_id(normalized) == sec_uid


def test_profile_short_share_text_normalizes_to_douyin_profile_url(monkeypatch) -> None:
    sec_uid = "MS4wLjABAAAAhlyWuh2hl4qtSRklFBUXI2OeIFZHcSVT8gAwdYEVEER_BL6pkbRCLoyncMBeVWwV"

    class FakeResponse:
        status_code = 302
        is_redirect = True
        headers = {
            "location": f"https://www.iesdouyin.com/share/user/{sec_uid}?sec_uid={sec_uid}",
        }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.services.profile_scan.httpx.Client", FakeClient)
    normalized = normalize_profile_url("长按复制此条消息，打开抖音搜索。 https://v.douyin.com/RufqmHm2wSk/", None)

    assert normalized == f"https://www.douyin.com/user/{sec_uid}"
    assert extract_sec_user_id(normalized) == sec_uid


def test_profile_short_url_rejects_video_redirect(monkeypatch) -> None:
    class FakeResponse:
        status_code = 302
        is_redirect = True
        headers = {"location": "https://www.douyin.com/video/7622653084993647603"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.services.profile_scan.httpx.Client", FakeClient)

    with pytest.raises(AppError) as raised:
        normalize_profile_url("https://v.douyin.com/workShortLink/", None)

    assert raised.value.code == "INVALID_PROFILE_URL"
    assert "作品链接" in raised.value.message


def test_douyin_public_profile_provider_returns_fallback_error(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200
        text = "<html><title>profile</title></html>"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.services.profile_scan.httpx.Client", FakeClient)
    provider = DouyinPublicProfileProvider()

    with pytest.raises(AppError) as raised:
        provider.scan(ProfileScanRequest(profile_url="https://www.douyin.com/user/MS4wLjABAAAAabc12345"))

    assert raised.value.code == "PROFILE_SCAN_NEEDS_FALLBACK"


def test_douyin_public_profile_provider_reports_risk_control_page(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200
        text = "<html><body></body><script>window._$jsvmprt = {}; byted_acrawler.init()</script></html>"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.services.profile_scan.httpx.Client", FakeClient)
    provider = DouyinPublicProfileProvider()

    with pytest.raises(AppError) as raised:
        provider.scan(ProfileScanRequest(profile_url="https://www.douyin.com/user/MS4wLjABAAAAabc12345"))

    assert raised.value.code == "DOUYIN_RISK_CONTROL"
    assert "浏览器校验" in raised.value.message


def test_profile_scan_endpoint_reports_risk_control_without_html_leak(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200
        text = "<html><script>window._$jsvmprt = {}; byted_acrawler.init()</script></html>"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.services.profile_scan.httpx.Client", FakeClient)
    response = client.post(
        "/api/profile/scan",
        json={"profile_url": "https://www.douyin.com/user/MS4wLjABAAAAabc12345", "count": 20},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error_code"] == "DOUYIN_RISK_CONTROL"
    assert "多作品链接粘贴" in payload["message"]
    assert "_$jsvmprt" not in response.text
    assert "byted_acrawler" not in response.text


def test_douyin_public_profile_provider_reports_structure_changed(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200
        text = '<script id="RENDER_DATA" type="application/json">{"aweme_list":[{"broken":true}]}</script>'

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.services.profile_scan.httpx.Client", FakeClient)
    provider = DouyinPublicProfileProvider()

    with pytest.raises(AppError) as raised:
        provider.scan(ProfileScanRequest(profile_url="https://www.douyin.com/user/MS4wLjABAAAAabc12345"))

    assert raised.value.code == "PROFILE_SCAN_STRUCTURE_CHANGED"


def test_extract_profile_items_from_public_html_payload() -> None:
    payload = {
        "aweme_list": [
            {
                "aweme_id": "7622653084993647603",
                "desc": "测试标题 #COS",
                "author": {"nickname": "测试作者", "sec_uid": "MS4wLjABAAAAabc12345"},
                "statistics": {
                    "digg_count": 300,
                    "comment_count": 7,
                    "share_count": 4,
                    "collect_count": 11,
                },
                "video": {"duration": 12000, "cover": {"url_list": ["https://example.com/cover.jpg"]}},
                "create_time": 1780000000,
            }
        ]
    }
    html = f'<script id="RENDER_DATA" type="application/json">{json.dumps(payload)}</script>'

    items = extract_profile_items_from_html(html, sec_user_id="MS4wLjABAAAAabc12345")

    assert len(items) == 1
    assert items[0].aweme_id == "7622653084993647603"
    assert items[0].title == "测试标题 #COS"
    assert items[0].author == "测试作者"
    assert items[0].like_count == 300
    assert items[0].comment_count == 7
    assert items[0].share_count == 4
    assert items[0].collect_count == 11
    assert items[0].engagement_score == 367
    assert items[0].cover_url == "https://example.com/cover.jpg"
    assert items[0].media_type == "video"
    assert items[0].can_build_case is True


def test_extract_profile_items_keeps_image_posts_from_payload() -> None:
    payload = {
        "aweme_list": [
            {
                "aweme_id": "7622653084993647604",
                "desc": "图文照片作品",
                "author": {"nickname": "图文作者"},
                "statistics": {"digg_count": 20},
                "images": [{"url_list": ["https://example.com/photo.jpg"]}],
                "create_time": 1780000001,
            }
        ]
    }
    html = f'<script id="RENDER_DATA" type="application/json">{json.dumps(payload)}</script>'

    items = extract_profile_items_from_html(html)

    assert len(items) == 1
    assert items[0].aweme_id == "7622653084993647604"
    assert items[0].media_type == "image"
    assert items[0].can_build_case is False
    assert items[0].webpage_url == "https://www.douyin.com/note/7622653084993647604"
    assert items[0].cover_url == "https://example.com/photo.jpg"


def test_extract_profile_items_from_note_links() -> None:
    html = '<a href="https://www.douyin.com/note/7622653084993647605">图文</a>'

    items = extract_profile_items_from_html(html, sec_user_id="MS4wLjABAAAAabc12345")

    assert len(items) == 1
    assert items[0].aweme_id == "7622653084993647605"
    assert items[0].media_type == "image"
    assert items[0].can_build_case is False
    assert items[0].sec_user_id == "MS4wLjABAAAAabc12345"


def test_manual_links_profile_provider_marks_note_as_image() -> None:
    provider = ManualLinksProfileProvider()
    result = provider.scan(
        ProfileScanRequest(
            manual_links="https://www.douyin.com/note/7622653084993647605",
            count=20,
            sort_by="like_count",
        )
    )

    assert result.items[0].media_type == "image"
    assert result.items[0].can_build_case is False


def test_profile_scan_endpoint_returns_manual_items() -> None:
    response = client.post(
        "/api/profile/scan",
        json={
            "manual_links": "https://www.douyin.com/video/7622653084993647603\n7539896907901062452",
            "count": 20,
            "sort_by": "like_count",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["provider"] == "manual_links"
    assert [item["aweme_id"] for item in payload["items"]] == ["7622653084993647603", "7539896907901062452"]
    assert payload["summary"]["scanned_count"] == 2
    assert payload["sort_by"] == "like_count"


def test_profile_scan_job_returns_items() -> None:
    response = client.post(
        "/api/jobs/profile-scan",
        json={"manual_links": "https://www.douyin.com/video/7622653084993647603", "count": 20},
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    deadline = time.time() + 10
    job = None
    while time.time() < deadline:
        job_response = client.get(f"/api/jobs/{job_id}")
        assert job_response.status_code == 200
        job = job_response.json()["job"]
        if job["status"] in {"success", "failed"}:
            break
        time.sleep(0.1)

    assert job is not None
    assert job["status"] == "success"
    assert job["result_json"]["items"][0]["aweme_id"] == "7622653084993647603"


def test_external_profile_provider_requires_api_base(monkeypatch) -> None:
    monkeypatch.setattr("app.services.profile_scan.settings.profile_scan_provider", "external_api")
    monkeypatch.setattr("app.services.profile_scan.settings.profile_scan_api_base", "")

    with pytest.raises(AppError) as raised:
        scan_profile(ProfileScanRequest(profile_url="https://www.douyin.com/user/MS4wLjABAAAAabc12345"))

    assert raised.value.code == "PROFILE_SCAN_API_NOT_CONFIGURED"


def test_creator_clone_lab_home_replaces_profile_scan_copy() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "创作者克隆实验室" in response.text
    assert "Creator Clone Lab" in response.text
    assert "导入一组对标素材" in response.text
    assert "主页 URL / sec_user_id" in response.text
    assert "浏览器辅助采集" in response.text
    assert "插件辅助采集" in response.text
    assert "主页扫描</button>" not in response.text
    assert "不登录、不使用 Cookie" in response.text
    assert "不绕验证码、不绕风控" in response.text
    assert "JSON / CSV 导入" in response.text
    assert "已有 Case 导入" in response.text
    assert "本地文件导入（后续接入）" in response.text
    assert "确认样本并富化" in response.text
    assert "素材池概览" in response.text
    assert "样本选择" in response.text
    assert "证据富化" in response.text
    assert "大模型蒸馏" in response.text
    assert "creator-clone-distill-button" in response.text
    assert "报告文件" in response.text
    assert "复制规则" in response.text
    assert "下载报告" in response.text
    script = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "/api/local-helper/chrome/status" in script
    assert "/api/local-helper/chrome/scan-token" in script
    assert "/api/local-helper/chrome/open-profile" in script
    assert script.index("/api/local-helper/chrome/status") < script.index("/api/local-helper/chrome/scan-token")
    assert "未检测到 Chrome DevTools" in script
    assert "只打开页面，不读取 Cookie" in script
    assert "已复制 Chrome 启动命令" not in script
    assert script.count("if (!requireProfileChromeConfirmation())") == 1
    assert '"page_confirmed": true' not in script
    assert "page_confirmed: true" not in script
    assert script.count("resetProfileChromeConfirmation();") >= 4
    assert "recommendedProfileSampleMix" in script
    assert "dedupeProfileItems" in script


def test_creator_clone_import_manual_links_generates_sample_set() -> None:
    response = client.post(
        "/api/creator-clone/import",
        json={
            "manual_links": "https://www.douyin.com/video/7622653084993647603\nhttps://www.douyin.com/video/7539896907901062452",
            "count": 20,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["set"]["sample_count"] == 2
    assert payload["set"]["samples"][0]["source_type"] == "douyin"
    assert payload["set"]["samples"][0]["understanding_level"] == "metadata_only"
    assert payload["exports"]["samples_json"].endswith("samples.json")


def test_creator_clone_import_profile_url_prioritizes_public_scan(monkeypatch) -> None:
    html_payload = {
        "aweme_list": [
            {
                "aweme_id": "7622653084993647603",
                "desc": "主页公开扫描样本",
                "statistics": {"digg_count": 321, "comment_count": 12, "share_count": 6},
                "video": {"duration": 1000},
            }
        ]
    }

    class FakeResponse:
        status_code = 200
        text = f'<script id="RENDER_DATA" type="application/json">{json.dumps(html_payload)}</script>'

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.services.profile_scan.httpx.Client", FakeClient)
    response = client.post(
        "/api/creator-clone/import",
        json={"profile_url": "https://www.douyin.com/user/MS4wLjABAAAAabc12345", "count": 20},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["set"]["sample_count"] == 1
    sample = payload["set"]["samples"][0]
    assert sample["aweme_id"] == "7622653084993647603"
    assert sample["title"] == "主页公开扫描样本"
    assert sample["like_count"] == 321
    assert payload["set"]["performance_segments"]["highest_like_samples"][0]["title"] == "主页公开扫描样本"
    assert payload["set"]["performance_segments"]["highest_comment_samples"][0]["metric_value"] == 12
    assert any("公开主页扫描优先执行" in warning for warning in payload["set"]["warnings"])


def test_creator_clone_import_structured_aweme_list_and_nested_statistics() -> None:
    response = client.post(
        "/api/creator-clone/import",
        json={
            "structured_items": json.dumps(
                {
                    "aweme_list": [
                        {
                            "aweme_id": "7622653084993647603",
                            "desc": "嵌套统计样本",
                            "statistics": {"digg_count": 100, "comment_count": 4, "share_count": 3, "collect_count": 2, "play_count": 1000},
                            "webpage_url": "https://www.douyin.com/video/7622653084993647603",
                        },
                        {
                            "id": "BV1xx411c7mD",
                            "platform": "bili",
                            "title": "B站对标样本",
                            "source_url": "https://www.bilibili.com/video/BV1xx411c7mD",
                            "view_count": 5000,
                        }
                    ]
                },
                ensure_ascii=False,
            )
        },
    )

    assert response.status_code == 200
    sample = response.json()["set"]["samples"][0]
    assert sample["title"] == "嵌套统计样本"
    assert sample["like_count"] == 100
    assert sample["comment_count"] == 4
    assert sample["share_count"] == 3
    assert sample["collect_count"] == 2
    assert sample["view_count"] == 1000
    bili_sample = response.json()["set"]["samples"][1]
    assert bili_sample["source_type"] == "bili"
    assert bili_sample["title"] == "B站对标样本"
    assert bili_sample["view_count"] == 5000


def test_creator_clone_import_structured_items_sanitizes_sensitive_metadata() -> None:
    response = client.post(
        "/api/creator-clone/import",
        json={
            "structured_items": json.dumps(
                [
                    {
                        "aweme_id": "7622653084993647603",
                        "title": "标题 sessionid=abc",
                        "desc": "描述 Authorization: Bearer secret",
                        "author": "作者 token=secret",
                        "source_url": "https://viewer:password@www.douyin.com/video/7622653084993647603?msToken=secret#frag",
                        "cover_url": "http://127.0.0.1:8000/cover.jpg?token=secret",
                        "raw_headers": {"Cookie": "sessionid=secret"},
                        "tags": ["甜美", "token=tagsecret"],
                        "notes": "备注 passport=secret",
                    }
                ],
                ensure_ascii=False,
            )
        },
    )

    assert response.status_code == 200
    sample = response.json()["set"]["samples"][0]
    assert sample["source_url"] == "https://www.douyin.com/video/7622653084993647603"
    assert sample["cover_url"] == ""
    assert sample["tags"] == ["甜美", "[redacted]"]
    payload_text = json.dumps(response.json(), ensure_ascii=False).lower()
    assert "sessionid" not in payload_text
    assert "authorization" not in payload_text
    assert "bearer" not in payload_text
    assert "passport" not in payload_text
    assert "token" not in payload_text
    assert "secret" not in payload_text
    assert "viewer:password" not in payload_text
    assert "raw_headers" not in payload_text


def test_creator_clone_inline_samples_are_sanitized_before_prompt_only_result() -> None:
    sample = sample_from_dict(
        {
            "sample_id": "sample_cookie=secret",
            "aweme_id": "not-a-real-id token=secret",
            "source_url": "https://user:pass@example.com/video/123?token=secret#frag",
            "cover_url": "http://localhost/private.jpg?token=secret",
            "title": "标题 cookie=secret",
            "notes": "备注 sid_guard=secret",
            "tags": ["正常", "authorization=secret"],
        }
    )

    payload = sample.to_dict()
    assert payload["aweme_id"] == ""
    assert payload["source_url"] == "https://example.com/video/123"
    assert payload["cover_url"] == ""
    assert payload["tags"] == ["正常", "[redacted]"]
    payload_text = json.dumps(payload, ensure_ascii=False).lower()
    assert "cookie" not in payload_text
    assert "sid_guard" not in payload_text
    assert "authorization" not in payload_text
    assert "secret" not in payload_text
    assert "user:pass" not in payload_text


def _valid_handoff_security_contract() -> dict:
    return {
        "contract_version": 1,
        "scope": "local_helper_to_analysis_web_app",
        "loopback_only": True,
        "public_site_cookie_free": True,
        "requests_from_user_machine": True,
        "uses_user_local_chrome_session": True,
        "page_confirmation_required": True,
        "one_time_token_required": True,
        "cookie_read": False,
        "cookie_returned": False,
        "cookie_logged": False,
        "login_token_returned": False,
        "signed_media_url_returned": False,
        "raw_headers_returned": False,
        "dom_visible_metadata_only": True,
        "sensitive_fields_redacted": True,
        "returned_data_scope": [
            "account_visible_metadata",
            "visible_work_list",
            "visible_interaction_metrics",
            "sanitized_source_urls",
        ],
        "handoff_excludes": ["Cookie", "login token", "authorization header", "signed media URL", "raw request headers"],
    }


def test_creator_clone_import_handoff_manifest_accepts_sanitized_metadata_only() -> None:
    handoff_manifest = {
        "handoff_version": 1,
        "title": "本机助手交接包",
        "creator_name": "测试创作者",
        "source_platform": "douyin",
        "profile_metadata": {
            "nickname": "测试创作者",
            "bio": "甜美 COS 账号",
            "stats": {"follower_count": 12000, "liked_count": 98000, "work_count": 36},
        },
        "samples": [
            {
                "sample_id": "sample_7622653084993647603",
                "source_type": "douyin",
                "source_url": "https://www.douyin.com/video/7622653084993647603",
                "aweme_id": "7622653084993647603",
                "title": "交接作品",
                "desc": "来自本机页面",
                "cover_url": "https://example.com/cover.jpg",
                "media_type": "video",
                "like_count": 200,
                "comment_count": 8,
                "share_count": 3,
                "understanding_level": "metadata_only",
            }
        ],
        "capture_audit": {
            "capture_method": "local_chrome_dom_readonly_scroll",
            "authorization": {
                "page_confirmed": True,
                "one_time_token_consumed": True,
                "trigger": "profile_page_plugin_assisted_scan",
            },
            "scroll_count": 5,
            "captured_count": 1,
        },
        "safety": {
            "public_site_cookie_free": True,
            "public_site_receives_sanitized_metadata_only": True,
            "handoff_contains_cookie": False,
            "handoff_contains_login_token": False,
            "handoff_contains_signed_media_url": False,
            "requests_from_user_machine": True,
        },
        "security_contract": {
            "contract_version": 1,
            "scope": "local_helper_to_analysis_web_app",
            "loopback_only": True,
            "public_site_cookie_free": True,
            "requests_from_user_machine": True,
            "uses_user_local_chrome_session": True,
            "page_confirmation_required": True,
            "one_time_token_required": True,
            "cookie_read": False,
            "cookie_returned": False,
            "cookie_logged": False,
            "login_token_returned": False,
            "signed_media_url_returned": False,
            "raw_headers_returned": False,
            "dom_visible_metadata_only": True,
            "sensitive_fields_redacted": True,
            "returned_data_scope": [
                "account_visible_metadata",
                "visible_work_list",
                "visible_interaction_metrics",
                "sanitized_source_urls",
            ],
            "handoff_excludes": ["Cookie", "login token", "authorization header", "signed media URL", "raw request headers"],
        },
    }

    token_payload = client.post("/api/creator-clone/handoff-token").json()
    assert token_payload["security_contract"]["public_site_cookie_free"] is True
    assert token_payload["security_contract"]["cookie_read"] is False
    assert token_payload["security_contract"]["signed_media_url_returned"] is False
    assert "Cookie" in token_payload["handoff_scope"]["excludes"]
    token = token_payload["token"]
    response = client.post("/api/creator-clone/import-handoff", json={"handoff_manifest": handoff_manifest, "handoff_token": token})

    assert response.status_code == 200
    payload = response.json()
    assert payload["set"]["sample_count"] == 1
    assert payload["security_contract"]["public_site_cookie_free"] is True
    assert payload["security_contract"]["cookie_logged"] is False
    assert payload["set"]["profile_metadata"]["nickname"] == "测试创作者"
    assert payload["set"]["profile_metadata"]["bio"] == "甜美 COS 账号"
    assert payload["set"]["profile_metadata"]["stats"]["follower_count"] == 12000
    assert any("handoff_manifest.json" in value for value in payload["exports"].values())
    sample = payload["set"]["samples"][0]
    assert sample["source_url"] == "https://www.douyin.com/video/7622653084993647603"
    assert sample["cover_url"] == "https://example.com/cover.jpg"
    assert sample["like_count"] == 200
    assert sample["title"] == "交接作品"
    assert "secret" not in json.dumps(payload, ensure_ascii=False).lower()
    set_id = payload["set"]["set_id"]
    handoff_response = client.get(f"/api/creator-clone/sets/{set_id}/files/handoff_manifest.json")
    assert handoff_response.status_code == 200
    imported_handoff = handoff_response.json()
    assert imported_handoff["safety"]["public_site_cookie_free"] is True
    assert imported_handoff["safety"]["public_site_receives_sanitized_metadata_only"] is True
    assert imported_handoff["profile_metadata"]["stats"]["liked_count"] == 98000
    assert imported_handoff["capture_audit"]["authorization"]["page_confirmed"] is True
    assert imported_handoff["capture_audit"]["authorization"]["one_time_token_consumed"] is True
    assert imported_handoff["capture_audit"]["authorization"]["trigger"] == "profile_page_plugin_assisted_scan"
    assert imported_handoff["security_contract"]["public_site_cookie_free"] is True
    assert imported_handoff["security_contract"]["cookie_read"] is False
    assert imported_handoff["security_contract"]["raw_headers_returned"] is False
    assert "Cookie" in imported_handoff["security_contract"]["handoff_excludes"]
    assert "Cookie" in imported_handoff["handoff_scope"]["excludes"]
    assert "secret" not in json.dumps(imported_handoff, ensure_ascii=False).lower()
    reused = client.post("/api/creator-clone/import-handoff", json={"handoff_manifest": handoff_manifest, "handoff_token": token})
    assert reused.status_code == 400
    assert reused.json()["error_code"] == "HANDOFF_TOKEN_INVALID"


def test_creator_clone_import_handoff_manifest_rejects_sensitive_sample_fields() -> None:
    token = client.post("/api/creator-clone/handoff-token").json()["token"]
    response = client.post(
        "/api/creator-clone/import-handoff",
        json={
            "handoff_token": token,
            "handoff_manifest": {
                "handoff_version": 1,
                "title": "本机助手交接包",
                "creator_name": "测试创作者",
                "source_platform": "douyin",
                "samples": [
                    {
                        "sample_id": "sample_7622653084993647603",
                        "source_type": "douyin",
                        "source_url": "https://www.douyin.com/video/7622653084993647603?msToken=secret",
                        "aweme_id": "7622653084993647603",
                        "title": "交接作品",
                        "media_type": "video",
                    }
                ],
                "safety": {
                    "public_site_cookie_free": True,
                    "public_site_receives_sanitized_metadata_only": True,
                    "handoff_contains_cookie": False,
                    "handoff_contains_login_token": False,
                    "handoff_contains_signed_media_url": False,
                },
                "security_contract": {
                    "contract_version": 1,
                    "scope": "local_helper_to_analysis_web_app",
                    "loopback_only": True,
                    "public_site_cookie_free": True,
                    "requests_from_user_machine": True,
                    "uses_user_local_chrome_session": True,
                    "page_confirmation_required": True,
                    "one_time_token_required": True,
                    "cookie_read": False,
                    "cookie_returned": False,
                    "cookie_logged": False,
                    "login_token_returned": False,
                    "signed_media_url_returned": False,
                    "raw_headers_returned": False,
                    "dom_visible_metadata_only": True,
                    "sensitive_fields_redacted": True,
                    "returned_data_scope": [
                        "account_visible_metadata",
                        "visible_work_list",
                        "visible_interaction_metrics",
                        "sanitized_source_urls",
                    ],
                    "handoff_excludes": ["Cookie", "login token", "authorization header", "signed media URL", "raw request headers"],
                },
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "HANDOFF_MANIFEST_INVALID"


def test_creator_clone_import_handoff_manifest_rejects_nested_raw_headers_and_cookie_values() -> None:
    token = client.post("/api/creator-clone/handoff-token").json()["token"]
    response = client.post(
        "/api/creator-clone/import-handoff",
        json={
            "handoff_token": token,
            "handoff_manifest": {
                "handoff_version": 1,
                "title": "本机助手交接包",
                "creator_name": "测试创作者",
                "source_platform": "douyin",
                "profile_metadata": {
                    "nickname": "测试账号",
                    "debug": {
                        "raw_headers": {
                            "Cookie": "sessionid=secret",
                            "Authorization": "Bearer secret",
                        }
                    },
                },
                "samples": [
                    {
                        "sample_id": "sample_7622653084993647603",
                        "source_type": "douyin",
                        "source_url": "https://www.douyin.com/video/7622653084993647603",
                        "aweme_id": "7622653084993647603",
                        "title": "交接作品",
                        "media_type": "video",
                    }
                ],
                "safety": {
                    "public_site_cookie_free": True,
                    "public_site_receives_sanitized_metadata_only": True,
                    "handoff_contains_cookie": False,
                    "handoff_contains_login_token": False,
                    "handoff_contains_signed_media_url": False,
                },
                "security_contract": _valid_handoff_security_contract(),
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "HANDOFF_MANIFEST_INVALID"


def test_creator_clone_import_handoff_manifest_rejects_signed_media_cdn_urls() -> None:
    token = client.post("/api/creator-clone/handoff-token").json()["token"]
    response = client.post(
        "/api/creator-clone/import-handoff",
        json={
            "handoff_token": token,
            "handoff_manifest": {
                "handoff_version": 1,
                "title": "本机助手交接包",
                "creator_name": "测试创作者",
                "source_platform": "douyin",
                "samples": [
                    {
                        "sample_id": "sample_7622653084993647603",
                        "source_type": "douyin",
                        "source_url": "https://www.douyin.com/video/7622653084993647603",
                        "aweme_id": "7622653084993647603",
                        "title": "交接作品",
                        "media_type": "video",
                        "metadata": {
                            "best_url": "https://v26-default.365yg.com/video/tos/cn/tos-cn-v-0015/test.mp4?l=secret"
                        },
                    }
                ],
                "safety": {
                    "public_site_cookie_free": True,
                    "public_site_receives_sanitized_metadata_only": True,
                    "handoff_contains_cookie": False,
                    "handoff_contains_login_token": False,
                    "handoff_contains_signed_media_url": False,
                },
                "security_contract": _valid_handoff_security_contract(),
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "HANDOFF_MANIFEST_INVALID"


def test_creator_clone_import_handoff_manifest_strips_url_userinfo() -> None:
    handoff_manifest = {
        "handoff_version": 1,
        "title": "URL userinfo 清洗测试",
        "creator_name": "测试创作者",
        "source_platform": "douyin",
        "samples": [
            {
                "sample_id": "sample_external_cover",
                "source_type": "douyin",
                "source_url": "https://viewer:password@example.com/video/7622653084993647603?x=1",
                "aweme_id": "",
                "title": "外部元数据 URL",
                "cover_url": "https://cover_user:cover_pass@example.com/cover.jpg?x=1",
                "media_type": "video",
            }
        ],
        "safety": {
            "public_site_cookie_free": True,
            "public_site_receives_sanitized_metadata_only": True,
            "handoff_contains_cookie": False,
            "handoff_contains_login_token": False,
            "handoff_contains_signed_media_url": False,
        },
        "security_contract": {
            "contract_version": 1,
            "scope": "local_helper_to_analysis_web_app",
            "loopback_only": True,
            "public_site_cookie_free": True,
            "requests_from_user_machine": True,
            "uses_user_local_chrome_session": True,
            "page_confirmation_required": True,
            "one_time_token_required": True,
            "cookie_read": False,
            "cookie_returned": False,
            "cookie_logged": False,
            "login_token_returned": False,
            "signed_media_url_returned": False,
            "raw_headers_returned": False,
            "dom_visible_metadata_only": True,
            "sensitive_fields_redacted": True,
            "returned_data_scope": [
                "account_visible_metadata",
                "visible_work_list",
                "visible_interaction_metrics",
                "sanitized_source_urls",
            ],
            "handoff_excludes": ["Cookie", "login token", "authorization header", "signed media URL", "raw request headers"],
        },
    }
    token = client.post("/api/creator-clone/handoff-token").json()["token"]
    response = client.post("/api/creator-clone/import-handoff", json={"handoff_manifest": handoff_manifest, "handoff_token": token})

    assert response.status_code == 200
    sample = response.json()["set"]["samples"][0]
    assert sample["source_url"] == "https://example.com/video/7622653084993647603"
    assert sample["cover_url"] == "https://example.com/cover.jpg"
    payload_text = json.dumps(response.json(), ensure_ascii=False).lower()
    assert "viewer:password" not in payload_text
    assert "cover_user:cover_pass" not in payload_text


def test_creator_clone_import_handoff_manifest_rejects_unsafe_manifest() -> None:
    token = client.post("/api/creator-clone/handoff-token").json()["token"]
    response = client.post(
        "/api/creator-clone/import-handoff",
        json={
            "handoff_token": token,
            "handoff_manifest": {
                "samples": [{"aweme_id": "7622653084993647603", "source_url": "https://www.douyin.com/video/7622653084993647603"}],
                "safety": {
                    "public_site_cookie_free": True,
                    "public_site_receives_sanitized_metadata_only": True,
                    "handoff_contains_cookie": True,
                    "handoff_contains_login_token": False,
                    "handoff_contains_signed_media_url": False,
                },
            }
        },
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "HANDOFF_MANIFEST_INVALID"


def test_creator_clone_import_handoff_manifest_rejects_unsafe_security_contract() -> None:
    token = client.post("/api/creator-clone/handoff-token").json()["token"]
    response = client.post(
        "/api/creator-clone/import-handoff",
        json={
            "handoff_token": token,
            "handoff_manifest": {
                "samples": [{"aweme_id": "7622653084993647603", "source_url": "https://www.douyin.com/video/7622653084993647603"}],
                "safety": {
                    "public_site_cookie_free": True,
                    "public_site_receives_sanitized_metadata_only": True,
                    "handoff_contains_cookie": False,
                    "handoff_contains_login_token": False,
                    "handoff_contains_signed_media_url": False,
                },
                "security_contract": {
                    "public_site_cookie_free": True,
                    "requests_from_user_machine": True,
                    "page_confirmation_required": True,
                    "one_time_token_required": True,
                    "cookie_read": True,
                    "cookie_returned": False,
                    "cookie_logged": False,
                    "login_token_returned": False,
                    "signed_media_url_returned": False,
                    "raw_headers_returned": False,
                    "dom_visible_metadata_only": True,
                    "sensitive_fields_redacted": True,
                },
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "HANDOFF_MANIFEST_INVALID"


def test_creator_clone_import_handoff_manifest_requires_complete_security_contract_scope() -> None:
    token = client.post("/api/creator-clone/handoff-token").json()["token"]
    response = client.post(
        "/api/creator-clone/import-handoff",
        json={
            "handoff_token": token,
            "handoff_manifest": {
                "samples": [{"aweme_id": "7622653084993647603", "source_url": "https://www.douyin.com/video/7622653084993647603"}],
                "safety": {
                    "public_site_cookie_free": True,
                    "public_site_receives_sanitized_metadata_only": True,
                    "handoff_contains_cookie": False,
                    "handoff_contains_login_token": False,
                    "handoff_contains_signed_media_url": False,
                },
                "security_contract": {
                    "contract_version": 1,
                    "scope": "local_helper_to_analysis_web_app",
                    "loopback_only": True,
                    "public_site_cookie_free": True,
                    "requests_from_user_machine": True,
                    "uses_user_local_chrome_session": True,
                    "page_confirmation_required": True,
                    "one_time_token_required": True,
                    "cookie_read": False,
                    "cookie_returned": False,
                    "cookie_logged": False,
                    "login_token_returned": False,
                    "signed_media_url_returned": False,
                    "raw_headers_returned": False,
                    "dom_visible_metadata_only": True,
                    "sensitive_fields_redacted": True,
                    "returned_data_scope": ["visible_work_list"],
                    "handoff_excludes": ["Cookie", "login token"],
                },
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "HANDOFF_MANIFEST_INVALID"


def test_creator_clone_import_handoff_manifest_requires_security_contract() -> None:
    token = client.post("/api/creator-clone/handoff-token").json()["token"]
    response = client.post(
        "/api/creator-clone/import-handoff",
        json={
            "handoff_token": token,
            "handoff_manifest": {
                "samples": [{"aweme_id": "7622653084993647603", "source_url": "https://www.douyin.com/video/7622653084993647603"}],
                "safety": {
                    "public_site_cookie_free": True,
                    "public_site_receives_sanitized_metadata_only": True,
                    "handoff_contains_cookie": False,
                    "handoff_contains_login_token": False,
                    "handoff_contains_signed_media_url": False,
                },
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "HANDOFF_MANIFEST_INVALID"


def test_creator_clone_import_handoff_manifest_requires_one_time_token() -> None:
    response = client.post(
        "/api/creator-clone/import-handoff",
        json={
            "handoff_manifest": {
                "samples": [{"aweme_id": "7622653084993647603"}],
                "safety": {
                    "public_site_cookie_free": True,
                    "public_site_receives_sanitized_metadata_only": True,
                    "handoff_contains_cookie": False,
                    "handoff_contains_login_token": False,
                    "handoff_contains_signed_media_url": False,
                },
            }
        },
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "HANDOFF_TOKEN_INVALID"


def test_creator_clone_selection_validation_warns_and_limits() -> None:
    samples = [
        CloneSample(sample_id=f"sample_{index}", title=f"样本 {index}", like_count=index)
        for index in range(21)
    ]
    selected, warnings = validate_selected_samples(samples, ["sample_0"])
    assert len(selected) == 1
    assert any("样本过少" in warning for warning in warnings)

    with pytest.raises(AppError) as raised:
        validate_selected_samples(samples, [sample.sample_id for sample in samples])

    assert raised.value.code == ErrorCode.PROFILE_BUILD_QUEUE_LIMIT


def test_update_sample_set_selection_persists_free_sample_choices() -> None:
    set_id = "clone_selection_persist_test"
    shutil.rmtree(settings.creator_clones_dir / set_id, ignore_errors=True)
    save_sample_set(
        CloneSampleSet(
            set_id=set_id,
            title="选样持久化测试",
            source_platform="douyin",
            samples=[
                CloneSample(sample_id="sample_a", aweme_id="7622653084993647603", title="高赞样本"),
                CloneSample(sample_id="sample_b", aweme_id="7539896907901062452", title="高评样本"),
                CloneSample(sample_id="sample_c", aweme_id="7472297018141052169", title="低表现样本"),
            ],
        )
    )

    updated = update_sample_set_selection(set_id, ["sample_a", "7539896907901062452"])

    assert updated.selected_sample_ids == ["sample_a", "sample_b"]
    assert [sample.selected for sample in updated.samples] == [True, True, False]
    reloaded = load_sample_set(set_id)
    assert reloaded.selected_sample_ids == ["sample_a", "sample_b"]
    assert [sample.selected for sample in reloaded.samples] == [True, True, False]


def test_creator_clone_prompt_marks_metadata_only_samples() -> None:
    sample_set = CloneSampleSet(
        set_id="clone_test_prompt",
        title="测试素材池",
        creator_name="测试创作者",
        source_platform="douyin",
        profile_metadata={
            "nickname": "测试创作者",
            "bio": "甜美 COS 账号",
            "stats": {"follower_count": 12000, "liked_count": 98000, "work_count": 36},
        },
        samples=[
            CloneSample(sample_id="sample_a", aweme_id="7622653084993647603", title="高赞样本", like_count=100),
            CloneSample(sample_id="sample_b", aweme_id="7539896907901062452", title="低赞样本", like_count=5),
        ],
    )
    prompt = build_distill_prompt(sample_set, sample_set.samples)

    assert "只输出合法 JSON" in prompt
    assert "metadata_only" in prompt
    assert "不能假装理解镜头节奏" in prompt
    assert "媒体类型统计" in prompt
    assert "账号可见资料" in prompt
    assert "甜美 COS 账号" in prompt
    assert "follower_count" in prompt
    assert "图文/照片样本只能推断封面、标题、视觉承诺和静态构图" in prompt
    assert "CreatorCloneResult" not in prompt
    assert "creator_clone_spec" in prompt


def test_creator_clone_prompt_includes_local_performance_segments() -> None:
    sample_set = CloneSampleSet(
        set_id="clone_test_segments",
        title="分层测试素材池",
        source_platform="douyin",
        samples=[
            CloneSample(sample_id="sample_like", title="高赞样本", like_count=1000, comment_count=5, share_count=1, collect_count=2),
            CloneSample(sample_id="sample_comment", title="高评论样本", like_count=100, comment_count=88, share_count=2, collect_count=1),
            CloneSample(sample_id="sample_share", title="高分享样本", like_count=120, comment_count=3, share_count=66, collect_count=4),
            CloneSample(sample_id="sample_weak", title="弱样本", like_count=1, comment_count=0, share_count=0, collect_count=0),
        ],
    )

    segments = performance_segments(sample_set.samples)
    assert segments["highest_like_samples"][0]["title"] == "高赞样本"
    assert segments["highest_comment_samples"][0]["title"] == "高评论样本"
    assert segments["highest_share_samples"][0]["title"] == "高分享样本"
    assert segments["weak_or_reference_samples"][0]["title"] == "弱样本"

    prompt = build_distill_prompt(sample_set, sample_set.samples)
    assert "本地预分层样本" in prompt
    assert "高赞样本" in prompt
    assert "高评论样本" in prompt
    assert "高分享样本" in prompt

    normalized = normalize_creator_clone_result({"summary": "ok", "performance_segments": {}}, sample_set, sample_set.samples)
    assert normalized["performance_segments"]["highest_like_samples"][0]["title"] == "高赞样本"
    assert normalized["performance_segments"]["weak_or_reference_samples"][0]["title"] == "弱样本"


def test_creator_clone_prompt_includes_selected_evidence_matrix_and_constraints() -> None:
    samples = [
        CloneSample(
            sample_id="sample_ready",
            title="证据较完整样本",
            media_type="video",
            understanding_level="partial",
            case_id="case_ready",
            has_video=True,
            has_frames=True,
            has_asr=True,
            has_ocr=True,
            has_comments=False,
            analysis_status="success",
        ),
        CloneSample(
            sample_id="sample_meta",
            title="仅元数据样本",
            media_type="video",
            understanding_level="metadata_only",
            asr_status="provider_missing",
            ocr_status="provider_missing",
        ),
    ]
    sample_set = CloneSampleSet(set_id="clone_test_evidence_matrix", title="证据矩阵测试", source_platform="douyin", samples=samples)

    matrix = selected_evidence_matrix(samples)
    constraints = selected_evidence_constraints(samples)
    prompt = build_distill_prompt(sample_set, samples)

    assert matrix["selected_count"] == 2
    assert matrix["with_case"] == 1
    assert matrix["with_keyframes"] == 1
    assert matrix["with_ai_report"] == 1
    assert matrix["asr_provider_missing"] == 1
    assert any("没有评论证据" in item for item in constraints)
    assert any("ASR provider 未配置" in item for item in constraints)
    assert "证据矩阵" in prompt
    assert "证据约束" in prompt
    assert "with_ai_report" in prompt
    assert "没有评论证据" in prompt


def test_creator_clone_sample_set_updates_with_generated_case_artifact() -> None:
    set_id = "clone_test_case_backfill"
    case_id = "case_creator_clone_backfill"
    case_dir = settings.cases_dir / case_id
    clone_dir = settings.creator_clones_dir / set_id
    shutil.rmtree(case_dir, ignore_errors=True)
    shutil.rmtree(clone_dir, ignore_errors=True)
    case_dir.mkdir(parents=True)
    (case_dir / "keyframes").mkdir()
    (case_dir / "video.mp4").write_bytes(b"video")
    (case_dir / "contact_sheet.jpg").write_bytes(b"image")
    (case_dir / "prompt.md").write_text("prompt", encoding="utf-8")
    (case_dir / "enrichment" / "asr").mkdir(parents=True)
    (case_dir / "enrichment" / "ocr").mkdir(parents=True)
    (case_dir / "enrichment" / "comments").mkdir(parents=True)
    (case_dir / "enrichment" / "manifest.json").write_text(
        json.dumps(
            {
                "statuses": {
                    "asr": "provider_missing",
                    "ocr": "no_text",
                    "comments": "pending",
                    "metrics": "success",
                    "index": "success",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (case_dir / "enrichment" / "asr" / "status.json").write_text(
        json.dumps({"status": "provider_missing"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (case_dir / "enrichment" / "ocr" / "status.json").write_text(
        json.dumps({"status": "no_text"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (case_dir / "analysis_input.json").write_text(
        json.dumps(
            {
                "content_category": "beauty_cos",
                "content_category_label": "美拍 / COS / 颜值向",
                "stats": {"like_count": 100, "comment_count": 8, "share_count": 3},
                "video": {"duration": 7.2, "width": 1080, "height": 1920},
                "assets": {"contact_sheet": "contact_sheet.jpg", "keyframes": [{"timestamp": 0}, {"timestamp": 3}]},
                "analysis_enrichment": {
                    "asr": {"status": "success", "full_text": "真正厉害的人会先抓住前三秒"},
                    "ocr": {
                        "status": "success",
                        "cover_text": "封面承诺",
                        "subtitle_text": "先抓住前三秒",
                        "frame_text": "画面文字补充",
                    },
                    "comments": {
                        "status": "success",
                        "total_comments": 3,
                        "top_needs": ["求教程"],
                        "high_frequency_words": ["好看"],
                        "comment_hooks": ["评论区会求同款拍法"],
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (case_dir / "metadata.json").write_text(
        json.dumps(
            {
                "title": "已生成素材包样本",
                "source_url": "https://www.douyin.com/video/7622653084993647603",
                "like_count": 100,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (case_dir / "analysis_result.json").write_text(json.dumps({"summary": "已经有视觉报告"}, ensure_ascii=False), encoding="utf-8")
    (case_dir / "analysis_report.md").write_text("## 已有 Case 报告\n这个样本已经抽帧分析。", encoding="utf-8")

    sample_set = CloneSampleSet(
        set_id=set_id,
        title="回写测试素材池",
        source_platform="douyin",
        samples=[
            CloneSample(
                sample_id="sample_7622653084993647603",
                aweme_id="7622653084993647603",
                title="元数据样本",
                like_count=100,
            )
        ],
    )
    save_sample_set(sample_set)
    artifact = CaseArtifact(
        case_id=case_id,
        aweme_id="7622653084993647603",
        local_video_id="local_backfill",
        video_path=str(case_dir / "video.mp4"),
        metadata_path=str(case_dir / "metadata.json"),
        qualities_path=str(case_dir / "qualities.json"),
        ffprobe_path=str(case_dir / "ffprobe.json"),
        analysis_input_path=str(case_dir / "analysis_input.json"),
        prompt_path=str(case_dir / "prompt.md"),
        contact_sheet_path=str(case_dir / "contact_sheet.jpg"),
        keyframes_dir=str(case_dir / "keyframes"),
    )

    updated = update_sample_set_with_case_artifacts(set_id, [artifact])
    updated_sample = updated.samples[0]

    assert updated_sample.case_id == case_id
    assert updated_sample.has_video is True
    assert updated_sample.has_frames is True
    assert updated_sample.understanding_level == "partial"
    assert updated_sample.enrichment_status == "success"
    assert updated_sample.asr_status == "provider_missing"
    assert updated_sample.ocr_status == "no_text"
    assert updated_sample.analysis_status == "success"
    assert "素材包" in updated_sample.notes
    assert "蒸馏证据" in updated_sample.notes
    assert load_sample_set(set_id).samples[0].case_id == case_id
    prompt = build_distill_prompt(updated, [updated_sample], include_case_reports=True)
    assert "已有 Case 报告" in prompt
    assert "这个样本已经抽帧分析" in prompt
    assert "case_evidence_pack" in prompt
    assert "evidence_status" in prompt
    assert "provider_missing" in prompt
    assert "no_text" in prompt
    assert "ASR provider 未配置" in prompt
    assert "OCR 已检查并确认无可识别画面文字" in prompt
    assert "真正厉害的人会先抓住前三秒" in prompt
    assert "先抓住前三秒" in prompt
    assert "求教程" in prompt
    assert "keyframe_count" in prompt


def test_creator_clone_distill_unconfigured_returns_prompt(monkeypatch) -> None:
    monkeypatch.setattr("app.services.creator_clone.settings.llm_provider", "disabled")
    import_response = client.post(
        "/api/creator-clone/import",
        json={
            "manual_links": "https://www.douyin.com/video/7622653084993647603\nhttps://www.douyin.com/video/7539896907901062452",
            "count": 20,
        },
    )
    set_id = import_response.json()["set"]["set_id"]
    samples = import_response.json()["set"]["samples"]

    response = client.post(
        "/api/creator-clone/distill",
        json={
            "sample_set_id": set_id,
            "selected_sample_ids": [sample["sample_id"] for sample in samples],
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error_code"] == "LLM_NOT_CONFIGURED"
    assert "prompt" in payload
    assert payload["recovery"] == "prompt_only"
    assert "distill_prompt.md" in payload["exports"]["distill_prompt_md"]


def test_creator_clone_distill_llm_request_failure_returns_prompt_recovery(monkeypatch) -> None:
    class FailingProvider:
        def analyze(self, prompt: str, image_paths: list[Path]) -> dict:
            raise AppError(ErrorCode.LLM_REQUEST_FAILED, "大模型 API 请求超时。")

    monkeypatch.setattr("app.services.creator_clone.llm_is_configured", lambda: True)
    monkeypatch.setattr("app.services.creator_clone.get_llm_provider", lambda: FailingProvider())
    import_response = client.post(
        "/api/creator-clone/import",
        json={
            "manual_links": "https://www.douyin.com/video/7622653084993647603\nhttps://www.douyin.com/video/7539896907901062452",
            "count": 20,
        },
    )
    set_id = import_response.json()["set"]["set_id"]
    samples = import_response.json()["set"]["samples"]

    response = client.post(
        "/api/creator-clone/distill",
        json={
            "sample_set_id": set_id,
            "selected_sample_ids": [sample["sample_id"] for sample in samples],
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error_code"] == "LLM_REQUEST_FAILED"
    assert payload["recovery"] == "prompt_only"
    assert "prompt" in payload
    assert "本地预分层样本" in payload["prompt"]
    assert "7622653084993647603" in payload["prompt"]
    assert payload["set"]["set_id"] == set_id
    assert Path(payload["exports"]["distill_prompt_md"]).is_file()
    assert "sk-" not in Path(payload["exports"]["distill_prompt_md"]).read_text(encoding="utf-8")


def test_creator_clone_distill_job_unconfigured_returns_prompt(monkeypatch) -> None:
    monkeypatch.setattr("app.services.creator_clone.settings.llm_provider", "disabled")
    import_response = client.post(
        "/api/creator-clone/import",
        json={
            "manual_links": "https://www.douyin.com/video/7622653084993647603\nhttps://www.douyin.com/video/7539896907901062452",
            "count": 20,
        },
    )
    set_id = import_response.json()["set"]["set_id"]
    samples = import_response.json()["set"]["samples"]

    create_response = client.post(
        "/api/jobs/creator-clone-distill",
        json={
            "sample_set_id": set_id,
            "selected_sample_ids": [sample["sample_id"] for sample in samples],
        },
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
    assert job["type"] == "creator-clone-distill"
    assert job["message"] == "大模型暂不可用，已生成蒸馏 Prompt"
    assert job["result_json"]["recovery"] == "prompt_only"
    assert job["result_json"]["error_code"] == "LLM_NOT_CONFIGURED"
    assert "prompt" in job["result_json"]
    assert "distill_prompt.md" in job["result_json"]["exports"]["distill_prompt_md"]


def test_creator_clone_distill_with_mock_llm_saves_visual_result(monkeypatch) -> None:
    class FakeProvider:
        def analyze(self, prompt: str, image_paths: list[Path]) -> dict:
            assert "高赞样本" in prompt
            return {
                "summary": "用轻剧情和标题判断题驱动停留。",
                "creator_positioning": {
                    "what_the_creator_sells": "现场轻剧情",
                    "audience_promise": "快速看到人物反应",
                    "hidden_genre": "景区互动短剧",
                    "audience_assumption": "观众愿意参与判断",
                },
                "topic_buckets": [{"name": "判断题", "description": "赚亏/奖惩", "why_it_works": "评论门槛低"}],
                "transferable_formulas": [{"name": "判断题公式", "when_to_use": "有反应点时", "beat_structure": ["标题", "反应"], "risks": ["同质化"]}],
                "creator_clone_spec": {"taste": "轻剧情", "topic_selection_rules": ["先找反应"], "anti_patterns": ["硬广"]},
                "candidate_ideas": [{"title": "这算奖励还是惩罚", "formula_used": "判断题公式", "likely_strength": "high", "production_requirements": ["人物", "场景"]}],
            }

    monkeypatch.setattr("app.services.creator_clone.llm_is_configured", lambda: True)
    monkeypatch.setattr("app.services.creator_clone.get_llm_provider", lambda: FakeProvider())
    response = client.post(
        "/api/creator-clone/distill",
        json={
            "samples": [
                {"sample_id": "sample_a", "title": "高赞样本", "like_count": 100},
                {"sample_id": "sample_b", "title": "低赞样本", "like_count": 5},
            ],
            "selected_sample_ids": ["sample_a", "sample_b"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["result"]["summary"] == "用轻剧情和标题判断题驱动停留。"
    assert payload["result"]["sample_overview"]["selected_count"] == 2
    assert Path(payload["exports"]["creator_clone_result_json"]).is_file()
    assert Path(payload["exports"]["creator_clone_md"]).is_file()


def test_creator_clone_distill_job_with_mock_llm_saves_visual_result(monkeypatch) -> None:
    class FakeProvider:
        def analyze(self, prompt: str, image_paths: list[Path]) -> dict:
            assert "高赞样本" in prompt
            return {
                "summary": "后台任务蒸馏完成。",
                "creator_positioning": {"what_the_creator_sells": "稳定工作流"},
                "creator_clone_spec": {"taste": "证据优先", "topic_selection_rules": ["先看高赞高评"]},
            }

    monkeypatch.setattr("app.services.creator_clone.llm_is_configured", lambda: True)
    monkeypatch.setattr("app.services.creator_clone.get_llm_provider", lambda: FakeProvider())
    response = client.post(
        "/api/jobs/creator-clone-distill",
        json={
            "samples": [
                {"sample_id": "sample_job_a", "title": "高赞样本", "like_count": 100},
                {"sample_id": "sample_job_b", "title": "低赞样本", "like_count": 5},
            ],
            "selected_sample_ids": ["sample_job_a", "sample_job_b"],
        },
    )

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    deadline = time.time() + 10
    job = None
    while time.time() < deadline:
        job_response = client.get(f"/api/jobs/{job_id}")
        assert job_response.status_code == 200
        job = job_response.json()["job"]
        if job["status"] in {"success", "failed"}:
            break
        time.sleep(0.1)

    assert job is not None
    assert job["status"] == "success"
    payload = job["result_json"]
    assert payload["ok"] is True
    assert payload["result"]["summary"] == "后台任务蒸馏完成。"
    assert payload["result"]["sample_overview"]["selected_count"] == 2
    assert Path(payload["exports"]["creator_clone_result_json"]).is_file()
    assert Path(payload["exports"]["creator_clone_md"]).is_file()
    assert "sk-" not in Path(payload["exports"]["creator_clone_result_json"]).read_text(encoding="utf-8")


def test_local_chrome_helper_token_and_invalid_token() -> None:
    token_response = client.post("/api/local-helper/chrome/scan-token")
    assert token_response.status_code == 200
    assert token_response.json()["token"]
    assert token_response.json()["security_contract"]["public_site_cookie_free"] is True
    assert token_response.json()["security_contract"]["raw_headers_returned"] is False

    scan_response = client.post(
        "/api/local-helper/chrome/scan-profile",
        json={"profile_url": "https://www.douyin.com/user/MS4wLjABAAAAabc12345", "token": "bad-token"},
    )
    assert scan_response.status_code == 400
    assert scan_response.json()["error_code"] == "LOCAL_HELPER_TOKEN_INVALID"


def test_local_chrome_open_profile_requires_token(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routes.local_helper.open_douyin_profile_in_local_chrome",
        lambda profile_url: {"url": profile_url, "title": "opened"},
    )
    response = client.post(
        "/api/local-helper/chrome/open-profile",
        json={"profile_url": "https://www.douyin.com/user/MS4wLjABAAAAabc12345", "token": "bad-token"},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "LOCAL_HELPER_TOKEN_INVALID"


def test_local_chrome_open_profile_uses_one_time_token(monkeypatch) -> None:
    opened = {}

    def fake_open(profile_url: str):
        opened["profile_url"] = profile_url
        return {
            "id": "tab_1",
            "type": "page",
            "title": "抖音主页",
            "url": profile_url,
            "is_profile": True,
        }

    monkeypatch.setattr("app.routes.local_helper.open_douyin_profile_in_local_chrome", fake_open)
    token = client.post("/api/local-helper/chrome/scan-token").json()["token"]
    response = client.post(
        "/api/local-helper/chrome/open-profile",
        json={
            "profile_url": "https://www.douyin.com/user/MS4wLjABAAAAabc12345",
            "token": token,
            "page_confirmed": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["tab"]["is_profile"] is True
    assert response.json()["security_contract"]["loopback_only"] is True
    assert response.json()["security_contract"]["cookie_read"] is False
    assert response.json()["security_contract"]["raw_headers_returned"] is False
    assert opened["profile_url"].endswith("MS4wLjABAAAAabc12345")
    reused = client.post(
        "/api/local-helper/chrome/open-profile",
        json={
            "profile_url": "https://www.douyin.com/user/MS4wLjABAAAAabc12345",
            "token": token,
            "page_confirmed": True,
        },
    )
    assert reused.status_code == 400
    assert reused.json()["error_code"] == "LOCAL_HELPER_TOKEN_INVALID"


def test_local_chrome_launch_requires_token(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routes.local_helper.launch_local_chrome_debug",
        lambda profile_url: {"launched": True, "profile_url": profile_url},
    )
    response = client.post(
        "/api/local-helper/chrome/launch",
        json={"profile_url": "https://www.douyin.com/user/MS4wLjABAAAAabc12345", "token": "bad-token"},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "LOCAL_HELPER_TOKEN_INVALID"


def test_local_chrome_launch_uses_one_time_token(monkeypatch) -> None:
    launched = {}

    def fake_launch(profile_url: str):
        launched["profile_url"] = profile_url
        return {
            "launched": True,
            "profile_url": profile_url,
            "note": "只启动本机 Chrome DevTools，不读取 Cookie；页面扫描仍需再次点击确认。",
        }

    monkeypatch.setattr("app.routes.local_helper.launch_local_chrome_debug", fake_launch)
    token = client.post("/api/local-helper/chrome/scan-token").json()["token"]
    response = client.post(
        "/api/local-helper/chrome/launch",
        json={
            "profile_url": "https://www.douyin.com/user/MS4wLjABAAAAabc12345",
            "token": token,
            "page_confirmed": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["launch"]["launched"] is True
    assert "不读取 Cookie" in response.json()["launch"]["note"]
    assert response.json()["security_contract"]["loopback_only"] is True
    assert response.json()["security_contract"]["cookie_returned"] is False
    assert response.json()["security_contract"]["signed_media_url_returned"] is False
    assert launched["profile_url"].endswith("MS4wLjABAAAAabc12345")
    reused = client.post(
        "/api/local-helper/chrome/launch",
        json={
            "profile_url": "https://www.douyin.com/user/MS4wLjABAAAAabc12345",
            "token": token,
            "page_confirmed": True,
        },
    )
    assert reused.status_code == 400
    assert reused.json()["error_code"] == "LOCAL_HELPER_TOKEN_INVALID"


def test_local_chrome_clear_profile_requires_token_and_confirmation(monkeypatch) -> None:
    cleared = {}

    def fake_clear():
        cleared["called"] = True
        return {
            "cleared": True,
            "profile_dir": str(settings.output_dir / "local_chrome_profile"),
            "note": "已清理专用本地 Chrome profile；不会影响你的普通 Chrome 用户资料。",
        }

    monkeypatch.setattr("app.routes.local_helper.clear_local_chrome_profile", fake_clear)
    token = client.post("/api/local-helper/chrome/scan-token").json()["token"]
    missing_confirmation = client.post(
        "/api/local-helper/chrome/clear-profile",
        json={"token": token},
    )

    assert missing_confirmation.status_code == 400
    assert missing_confirmation.json()["error_code"] == "LOCAL_HELPER_CONFIRMATION_REQUIRED"
    assert not cleared

    token = client.post("/api/local-helper/chrome/scan-token").json()["token"]
    response = client.post(
        "/api/local-helper/chrome/clear-profile",
        json={"token": token, "page_confirmed": True},
    )

    assert response.status_code == 200
    assert response.json()["cleanup"]["cleared"] is True
    assert response.json()["security_contract"]["cookie_returned"] is False
    assert cleared["called"] is True
    reused = client.post(
        "/api/local-helper/chrome/clear-profile",
        json={"token": token, "page_confirmed": True},
    )
    assert reused.status_code == 400
    assert reused.json()["error_code"] == "LOCAL_HELPER_TOKEN_INVALID"


def test_local_helper_requires_page_confirmation_before_local_actions(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routes.local_helper.open_douyin_profile_in_local_chrome",
        lambda profile_url: {"url": profile_url, "title": "opened"},
    )
    token = client.post("/api/local-helper/chrome/scan-token").json()["token"]
    response = client.post(
        "/api/local-helper/chrome/open-profile",
        json={"profile_url": "https://www.douyin.com/user/MS4wLjABAAAAabc12345", "token": token},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "LOCAL_HELPER_CONFIRMATION_REQUIRED"


def test_local_chrome_open_profile_service_rejects_non_douyin_url() -> None:
    from app.services.local_chrome import open_douyin_profile_in_local_chrome

    with pytest.raises(AppError) as raised:
        open_douyin_profile_in_local_chrome("https://example.com/")

    assert raised.value.code == ErrorCode.INVALID_PROFILE_URL


def test_local_chrome_launch_service_uses_minimal_environment(monkeypatch, tmp_path: Path) -> None:
    from app.services.local_chrome import launch_local_chrome_debug

    fake_binary = tmp_path / "Google Chrome"
    fake_binary.write_text("#!/bin/sh\n", encoding="utf-8")
    launched = {}
    monkeypatch.setenv("LLM_API_KEY", "sk-secret-should-not-leak")

    def fake_popen(args, **kwargs):
        launched["args"] = args
        launched["env"] = kwargs.get("env", {})
        launched["stdout"] = kwargs.get("stdout")
        launched["stderr"] = kwargs.get("stderr")
        launched["start_new_session"] = kwargs.get("start_new_session")

        class FakeProcess:
            pid = 12345

        return FakeProcess()

    monkeypatch.setattr("app.services.local_chrome.subprocess.Popen", fake_popen)

    result = launch_local_chrome_debug(
        "MS4wLjABAAAAabc12345",
        chrome_binary=str(fake_binary),
    )

    assert result["launched"] is True
    assert result["profile_url"] == "https://www.douyin.com/user/MS4wLjABAAAAabc12345"
    assert "--remote-debugging-port=9222" in launched["args"]
    assert "--remote-allow-origins=http://127.0.0.1:8765,http://127.0.0.1:9222" in launched["args"]
    assert any(value.startswith("--user-data-dir=") and "local_chrome_profile" in value for value in launched["args"])
    assert "--no-first-run" in launched["args"]
    assert "--no-default-browser-check" in launched["args"]
    assert "https://www.douyin.com/user/MS4wLjABAAAAabc12345" in launched["args"]
    assert "LLM_API_KEY" not in launched["env"]
    assert launched["start_new_session"] is True
    assert result["user_data_dir"].endswith("outputs/local_chrome_profile")
    assert result["profile_mode"] == "dedicated"


def test_local_chrome_launch_can_use_existing_profile_mode(monkeypatch, tmp_path: Path) -> None:
    from app.services.local_chrome import _manual_chrome_launch_command, launch_local_chrome_debug

    fake_binary = tmp_path / "Google Chrome"
    fake_binary.write_text("#!/bin/sh\n", encoding="utf-8")
    existing_dir = tmp_path / "Existing Chrome User Data"
    launched = {}
    monkeypatch.setattr("app.services.local_chrome.settings.local_chrome_profile_mode", "existing")
    monkeypatch.setattr("app.services.local_chrome.settings.local_chrome_user_data_dir", str(existing_dir))

    def fake_popen(args, **kwargs):
        launched["args"] = args

        class FakeProcess:
            pid = 12345

        return FakeProcess()

    monkeypatch.setattr("app.services.local_chrome.subprocess.Popen", fake_popen)

    command = _manual_chrome_launch_command("MS4wLjABAAAAabc12345", chrome_binary=str(fake_binary))
    result = launch_local_chrome_debug("MS4wLjABAAAAabc12345", chrome_binary=str(fake_binary))

    assert result["profile_mode"] == "existing"
    assert result["uses_existing_chrome_profile"] is True
    assert result["user_data_dir"] == str(existing_dir)
    assert "复用日常 Chrome 用户数据目录" in result["profile_note"]
    assert f"--user-data-dir={existing_dir}" in launched["args"]
    assert f"--user-data-dir={existing_dir}" in command
    assert "local_chrome_profile" not in command


def test_local_chrome_clear_profile_service_removes_only_dedicated_profile() -> None:
    from app.services.local_chrome import clear_local_chrome_profile

    profile_dir = settings.output_dir / "local_chrome_profile"
    shutil.rmtree(profile_dir, ignore_errors=True)
    profile_dir.mkdir(parents=True)
    (profile_dir / "Cookies").write_text("cookie-store", encoding="utf-8")
    sibling = settings.output_dir / "local_chrome_profile_keep.txt"
    sibling.write_text("keep", encoding="utf-8")

    result = clear_local_chrome_profile()

    assert result["cleared"] is True
    assert not profile_dir.exists()
    assert sibling.read_text(encoding="utf-8") == "keep"
    sibling.unlink()


def test_local_chrome_launch_service_does_not_echo_profile_query(monkeypatch, tmp_path: Path) -> None:
    from app.services.local_chrome import launch_local_chrome_debug

    fake_binary = tmp_path / "Google Chrome"
    fake_binary.write_text("#!/bin/sh\n", encoding="utf-8")
    launched = {}

    def fake_popen(args, **kwargs):
        launched["args"] = args

        class FakeProcess:
            pid = 12345

        return FakeProcess()

    monkeypatch.setattr("app.services.local_chrome.subprocess.Popen", fake_popen)

    result = launch_local_chrome_debug(
        "https://www.douyin.com/user/MS4wLjABAAAAabc12345?msToken=secret&from_tab_name=main#frag",
        chrome_binary=str(fake_binary),
    )

    assert result["profile_url"] == "https://www.douyin.com/user/MS4wLjABAAAAabc12345"
    assert launched["args"][-1] == "https://www.douyin.com/user/MS4wLjABAAAAabc12345"
    assert "msToken=secret" not in json.dumps(launched["args"], ensure_ascii=False)
    assert "#frag" not in json.dumps(launched["args"], ensure_ascii=False)
    assert "msToken=secret" not in json.dumps(result, ensure_ascii=False)
    assert "#frag" not in json.dumps(result, ensure_ascii=False)


def test_local_chrome_launch_service_rejects_non_douyin_url(tmp_path: Path) -> None:
    from app.services.local_chrome import launch_local_chrome_debug

    fake_binary = tmp_path / "Google Chrome"
    fake_binary.write_text("#!/bin/sh\n", encoding="utf-8")

    with pytest.raises(AppError) as raised:
        launch_local_chrome_debug("https://example.com/", chrome_binary=str(fake_binary))

    assert raised.value.code == ErrorCode.INVALID_PROFILE_URL


def test_local_chrome_launch_service_rejects_non_loopback_debug_url(tmp_path: Path, monkeypatch) -> None:
    from app.services.local_chrome import launch_local_chrome_debug

    fake_binary = tmp_path / "Google Chrome"
    fake_binary.write_text("#!/bin/sh\n", encoding="utf-8")

    def fail_popen(*args, **kwargs):
        raise AssertionError("remote Chrome debug URL must be rejected before launch")

    monkeypatch.setattr("app.services.local_chrome.subprocess.Popen", fail_popen)

    with pytest.raises(AppError) as raised:
        launch_local_chrome_debug(
            "https://www.douyin.com/user/MS4wLjABAAAAabc12345",
            chrome_binary=str(fake_binary),
            chrome_debug_url="http://203.0.113.10:9222",
        )

    assert raised.value.code == ErrorCode.LOCAL_CHROME_SCAN_FAILED
    assert "非本机 Chrome DevTools HTTP" in raised.value.message


def test_local_chrome_launch_service_rejects_debug_url_with_credentials(tmp_path: Path, monkeypatch) -> None:
    from app.services.local_chrome import launch_local_chrome_debug

    fake_binary = tmp_path / "Google Chrome"
    fake_binary.write_text("#!/bin/sh\n", encoding="utf-8")

    def fail_popen(*args, **kwargs):
        raise AssertionError("credential-bearing Chrome debug URL must be rejected before launch")

    monkeypatch.setattr("app.services.local_chrome.subprocess.Popen", fail_popen)

    with pytest.raises(AppError) as raised:
        launch_local_chrome_debug(
            "https://www.douyin.com/user/MS4wLjABAAAAabc12345",
            chrome_binary=str(fake_binary),
            chrome_debug_url="http://user:secret@127.0.0.1:9222?token=secret#frag",
        )

    assert raised.value.code == ErrorCode.LOCAL_CHROME_SCAN_FAILED
    assert "不能包含凭据" in raised.value.message


def test_local_chrome_evaluate_tab_sets_allowed_websocket_origin(monkeypatch) -> None:
    from app.services.local_chrome import _evaluate_tab

    captured = {}

    class FakeWebSocket:
        def send(self, payload):
            captured["payload"] = json.loads(payload)

        def recv(self):
            return json.dumps({"id": 1, "result": {"result": {"value": {"ok": True}}}})

        def close(self):
            captured["closed"] = True

    def fake_create_connection(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeWebSocket()

    monkeypatch.setattr("websocket.create_connection", fake_create_connection)

    payload = _evaluate_tab("ws://127.0.0.1:9222/devtools/page/test", "(() => ({ok: true}))()")

    assert payload == {"ok": True}
    assert captured["kwargs"]["origin"] == "http://127.0.0.1:9222"
    assert captured["closed"] is True


def test_local_chrome_evaluate_tab_rejects_non_loopback_websocket(monkeypatch) -> None:
    from app.services.local_chrome import _evaluate_tab

    def fail_create_connection(url, **kwargs):
        raise AssertionError("non-loopback websocket must be rejected before connect")

    monkeypatch.setattr("websocket.create_connection", fail_create_connection)

    with pytest.raises(AppError) as exc_info:
        _evaluate_tab("ws://203.0.113.10:9222/devtools/page/test", "(() => ({ok: true}))()")

    assert exc_info.value.code == ErrorCode.LOCAL_CHROME_SCAN_FAILED
    assert "非本机 Chrome DevTools websocket" in exc_info.value.message


def test_local_chrome_evaluate_tab_rejects_websocket_userinfo(monkeypatch) -> None:
    from app.services.local_chrome import _evaluate_tab

    def fail_create_connection(url, **kwargs):
        raise AssertionError("credential-bearing websocket must be rejected before connect")

    monkeypatch.setattr("websocket.create_connection", fail_create_connection)

    with pytest.raises(AppError) as exc_info:
        _evaluate_tab("ws://user:secret@127.0.0.1:9222/devtools/page/test", "(() => ({ok: true}))()")

    assert exc_info.value.code == ErrorCode.LOCAL_CHROME_SCAN_FAILED
    assert "不能包含凭据" in exc_info.value.message


def test_local_chrome_tabs_reject_non_loopback_debug_url(monkeypatch) -> None:
    from app.services.local_chrome import _chrome_tabs

    class FailClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("remote Chrome debug URL must be rejected before HTTP client")

    monkeypatch.setattr("app.services.local_chrome.httpx.Client", FailClient)

    with pytest.raises(AppError) as exc_info:
        _chrome_tabs("http://203.0.113.10:9222")

    assert exc_info.value.code == ErrorCode.LOCAL_CHROME_SCAN_FAILED
    assert "非本机 Chrome DevTools HTTP" in exc_info.value.message


def test_local_chrome_tabs_reject_debug_url_query_or_fragment(monkeypatch) -> None:
    from app.services.local_chrome import _chrome_tabs

    class FailClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("query-bearing Chrome debug URL must be rejected before HTTP client")

    monkeypatch.setattr("app.services.local_chrome.httpx.Client", FailClient)

    with pytest.raises(AppError) as exc_info:
        _chrome_tabs("http://127.0.0.1:9222?token=secret#frag")

    assert exc_info.value.code == ErrorCode.LOCAL_CHROME_SCAN_FAILED
    assert "不能包含凭据" in exc_info.value.message


def test_local_chrome_profile_url_normalization_strips_query_fragment_and_rejects_userinfo() -> None:
    from app.services.local_chrome import _manual_chrome_launch_command, _normalize_douyin_profile_url

    normalized = _normalize_douyin_profile_url(
        "https://www.douyin.com/user/MS4wLjABAAAAabc12345?msToken=secret#frag"
    )
    assert normalized == "https://www.douyin.com/user/MS4wLjABAAAAabc12345"

    command = _manual_chrome_launch_command(
        "https://www.douyin.com/user/MS4wLjABAAAAabc12345?msToken=secret#frag",
        chrome_binary="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    )
    assert "https://www.douyin.com/user/MS4wLjABAAAAabc12345" in command
    assert "msToken" not in command
    assert "secret" not in command
    assert "#frag" not in command

    with pytest.raises(AppError) as exc_info:
        _normalize_douyin_profile_url("https://viewer:password@www.douyin.com/user/MS4wLjABAAAAabc12345")

    assert exc_info.value.code == ErrorCode.INVALID_PROFILE_URL


def test_local_chrome_open_profile_service_accepts_sec_user_id(monkeypatch) -> None:
    from app.services.local_chrome import open_douyin_profile_in_local_chrome

    opened_urls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "id": "tab_1",
                "type": "page",
                "title": "抖音主页 msToken=secret",
                "url": opened_urls[-1],
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def put(self, url):
            opened_urls.append(url)
            return FakeResponse()

    monkeypatch.setattr("app.services.local_chrome.httpx.Client", FakeClient)
    tab = open_douyin_profile_in_local_chrome("MS4wLjABAAAAabc12345")

    assert "https%3A%2F%2Fwww.douyin.com%2Fuser%2FMS4wLjABAAAAabc12345" in opened_urls[0]
    payload_text = json.dumps(tab, ensure_ascii=False).lower()
    assert "mstoken" not in payload_text
    assert "secret" not in payload_text
    assert tab["is_profile"] is False or isinstance(tab["is_profile"], bool)


def test_local_chrome_open_profile_rejects_non_loopback_debug_url(monkeypatch) -> None:
    from app.services.local_chrome import open_douyin_profile_in_local_chrome

    class FailClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("remote Chrome debug URL must be rejected before HTTP client")

    monkeypatch.setattr("app.services.local_chrome.httpx.Client", FailClient)

    with pytest.raises(AppError) as exc_info:
        open_douyin_profile_in_local_chrome(
            "https://www.douyin.com/user/MS4wLjABAAAAabc12345",
            chrome_debug_url="http://203.0.113.10:9222",
        )

    assert exc_info.value.code == ErrorCode.LOCAL_CHROME_SCAN_FAILED
    assert "非本机 Chrome DevTools HTTP" in exc_info.value.message


def test_local_chrome_status_reports_diagnostics_without_sensitive_fields(monkeypatch) -> None:
    tabs = [
        {
            "id": "tab_1",
            "type": "page",
            "title": "抖音主页 sessionid=abc",
            "url": "https://www.douyin.com/user/MS4wLjABAAAAabc12345?msToken=secret",
        },
        {"id": "tab_2", "type": "page", "title": "其他页面", "url": "https://example.com/"},
    ]
    monkeypatch.setattr("app.services.local_chrome._chrome_tabs", lambda chrome_debug_url: tabs)
    response = client.get("/api/local-helper/chrome/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["chrome_available"] is True
    assert payload["tab_count"] == 2
    assert payload["douyin_tab_count"] == 1
    assert payload["douyin_profile_tab_count"] == 1
    assert payload["ready_for_profile_scan"] is True
    assert payload["confirmation_required"] is True
    assert payload["one_time_token_required"] is True
    assert payload["request_origin"] == "user_local_chrome_and_user_local_ip"
    assert payload["cookie_policy"] == "not_read_not_returned_not_logged"
    assert "visible_work_list" in payload["returned_data_scope"]
    assert payload["security_contract"]["public_site_cookie_free"] is True
    assert payload["security_contract"]["requests_from_user_machine"] is True
    assert payload["security_contract"]["cookie_read"] is False
    assert "signed media URL" in payload["security_contract"]["handoff_excludes"]
    assert "插件辅助采集" in payload["next_action"]
    payload_text = json.dumps(payload, ensure_ascii=False).lower()
    assert "sessionid" not in payload_text
    assert "mstoken" not in payload_text
    assert "secret" not in payload_text
    assert "title" not in payload["douyin_tabs"][0]
    assert "url" not in payload["douyin_tabs"][0]
    assert payload["douyin_tabs"][0]["label"] == "抖音主页 #1"
    assert any("启动 Chrome、打开主页、扫描或清理辅助 profile" in item for item in payload["security"])


def test_local_chrome_status_requires_profile_tab_for_scan_ready(monkeypatch) -> None:
    tabs = [
        {
            "id": "tab_video",
            "type": "page",
            "title": "抖音视频",
            "url": "https://www.douyin.com/video/7622653084993647603",
        }
    ]
    monkeypatch.setattr("app.services.local_chrome._chrome_tabs", lambda chrome_debug_url: tabs)

    response = client.get("/api/local-helper/chrome/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["chrome_available"] is True
    assert payload["douyin_tab_count"] == 1
    assert payload["douyin_profile_tab_count"] == 0
    assert payload["ready_for_profile_scan"] is False
    assert "还没有抖音主页标签页" in payload["status_message"]
    assert payload["confirmation_required"] is True
    assert payload["one_time_token_required"] is True
    assert "打开目标抖音主页" in payload["next_action"]


def test_local_chrome_status_ignores_spoofed_non_douyin_tab_urls(monkeypatch) -> None:
    tabs = [
        {
            "id": "tab_spoof",
            "type": "page",
            "title": "伪装页面",
            "url": "https://evil.example/?next=https://www.douyin.com/user/MS4wLjABAAAAabc12345",
        },
        {
            "id": "tab_spoof_path",
            "type": "page",
            "title": "伪装路径",
            "url": "https://evil.example/douyin.com/user/MS4wLjABAAAAabc12345",
        },
    ]
    monkeypatch.setattr("app.services.local_chrome._chrome_tabs", lambda chrome_debug_url: tabs)

    response = client.get("/api/local-helper/chrome/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["chrome_available"] is True
    assert payload["tab_count"] == 2
    assert payload["douyin_tab_count"] == 0
    assert payload["douyin_profile_tab_count"] == 0
    assert payload["ready_for_profile_scan"] is False
    assert payload["douyin_tabs"] == []


def test_local_chrome_scan_does_not_evaluate_spoofed_douyin_url_tab(monkeypatch) -> None:
    from app.services.local_chrome import scan_douyin_profile_from_local_chrome

    monkeypatch.setattr(
        "app.services.local_chrome._chrome_tabs",
        lambda chrome_debug_url: [
            {
                "type": "page",
                "url": "https://evil.example/?next=https://www.douyin.com/user/MS4wLjABAAAAabc12345",
                "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/evil",
            }
        ],
    )

    def fail_evaluate(websocket_url, expression):
        raise AssertionError("spoofed non-Douyin tab must not be evaluated")

    monkeypatch.setattr("app.services.local_chrome._evaluate_tab", fail_evaluate)

    with pytest.raises(AppError) as exc_info:
        scan_douyin_profile_from_local_chrome("https://www.douyin.com/user/MS4wLjABAAAAabc12345")

    assert exc_info.value.code == ErrorCode.LOCAL_CHROME_TAB_NOT_FOUND


def test_local_chrome_scan_does_not_fallback_to_previous_profile_tab(monkeypatch) -> None:
    from app.services.local_chrome import scan_douyin_profile_from_local_chrome

    monkeypatch.setattr(
        "app.services.local_chrome._chrome_tabs",
        lambda chrome_debug_url: [
            {
                "type": "page",
                "url": "https://www.douyin.com/user/MS4wLjABAAAAPreviousProfile",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/previous",
            }
        ],
    )

    def fail_evaluate(websocket_url, expression):
        raise AssertionError("previous profile tab must not be evaluated for a new target")

    monkeypatch.setattr("app.services.local_chrome._evaluate_tab", fail_evaluate)

    with pytest.raises(AppError) as exc_info:
        scan_douyin_profile_from_local_chrome("https://www.douyin.com/user/MS4wLjABAAAANewProfile")

    assert exc_info.value.code == ErrorCode.LOCAL_CHROME_TAB_NOT_FOUND


def test_local_chrome_scan_rejects_non_loopback_websocket_url(monkeypatch) -> None:
    from app.services.local_chrome import scan_douyin_profile_from_local_chrome

    monkeypatch.setattr(
        "app.services.local_chrome._chrome_tabs",
        lambda chrome_debug_url: [
            {
                "type": "page",
                "url": "https://www.douyin.com/user/MS4wLjABAAAAabc12345",
                "webSocketDebuggerUrl": "ws://203.0.113.10:9222/devtools/page/remote",
            }
        ],
    )

    def fail_evaluate(websocket_url, expression):
        raise AssertionError("remote websocket must be rejected before evaluate")

    monkeypatch.setattr("app.services.local_chrome._evaluate_tab", fail_evaluate)

    with pytest.raises(AppError) as exc_info:
        scan_douyin_profile_from_local_chrome("https://www.douyin.com/user/MS4wLjABAAAAabc12345")

    assert exc_info.value.code == ErrorCode.LOCAL_CHROME_SCAN_FAILED
    assert "非本机 Chrome DevTools websocket" in exc_info.value.message


def test_local_chrome_status_reports_unavailable_without_failing(monkeypatch) -> None:
    def fake_tabs(chrome_debug_url):
        raise AppError(ErrorCode.LOCAL_CHROME_NOT_AVAILABLE, "Chrome 未启动。")

    monkeypatch.setattr("app.services.local_chrome._chrome_tabs", fake_tabs)
    response = client.get("/api/local-helper/chrome/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["chrome_available"] is False
    assert payload["ready_for_profile_scan"] is False
    assert payload["douyin_tabs"] == []
    assert payload["profile_mode"] == "dedicated"
    assert payload["uses_dedicated_profile"] is True
    assert "单独登录" in payload["profile_note"]
    assert "remote-debugging-port=9222" in payload["launch_hint"]
    assert "--user-data-dir=" in payload["launch_hint"]
    assert "local_chrome_profile" in payload["launch_hint"]
    assert "--no-first-run" in payload["launch_hint"]
    assert "--no-default-browser-check" in payload["launch_hint"]
    assert "https://www.douyin.com/" in payload["launch_hint"]
    assert payload["request_origin"] == "user_local_chrome_and_user_local_ip"
    assert payload["security_contract"]["loopback_only"] is True
    assert payload["security_contract"]["one_time_token_required"] is True
    assert "启动带 DevTools" in payload["next_action"]


def test_local_chrome_helper_scan_profile_returns_sanitized_sample_set(monkeypatch) -> None:
    from app.services.creator_clone import CloneSample, CloneSampleSet

    def fake_scan(
        profile_url: str,
        max_items: int = 100,
        scroll_rounds: int = 6,
        merge_sample_set_id: str = "",
        authorization_context: dict | None = None,
    ):
        assert profile_url.endswith("MS4wLjABAAAAabc12345")
        assert max_items == 50
        assert scroll_rounds == 4
        assert merge_sample_set_id == ""
        assert authorization_context == {
            "page_confirmed": True,
            "one_time_token_consumed": True,
            "trigger": "profile_page_plugin_assisted_scan",
        }
        return CloneSampleSet(
            set_id="clone_local_chrome_test",
            title="本机 Chrome 素材池",
            creator_name="测试账号",
            source_platform="douyin",
            samples=[
                CloneSample(
                    sample_id="sample_7622653084993647603",
                    source_type="douyin",
                    source_url="https://www.douyin.com/video/7622653084993647603",
                    aweme_id="7622653084993647603",
                    title="Chrome 可见作品",
                    like_count=123,
                    notes="来自本机 Chrome DOM 只读辅助采集，尚未生成素材包。",
                )
            ],
            warnings=["不读取 Cookie，不返回 Cookie。"],
        )

    monkeypatch.setattr("app.routes.local_helper.scan_douyin_profile_from_local_chrome", fake_scan)
    token = client.post("/api/local-helper/chrome/scan-token").json()["token"]
    response = client.post(
        "/api/local-helper/chrome/scan-profile",
        json={
            "profile_url": "https://www.douyin.com/user/MS4wLjABAAAAabc12345",
            "token": token,
            "page_confirmed": True,
            "max_items": 50,
            "scroll_rounds": 4,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["set"]["sample_count"] == 1
    assert "capture_audit" in payload
    assert payload["security_contract"]["dom_visible_metadata_only"] is True
    assert payload["security_contract"]["cookie_logged"] is False
    sample = payload["set"]["samples"][0]
    assert sample["title"] == "Chrome 可见作品"
    assert sample["like_count"] == 123
    payload_text = json.dumps(payload, ensure_ascii=False).lower()
    assert "sessionid" not in payload_text
    assert "passport" not in payload_text
    assert "sid_guard" not in payload_text


def test_local_chrome_helper_scan_profile_can_merge_existing_sample_set(monkeypatch) -> None:
    from app.services.creator_clone import CloneSample, CloneSampleSet

    set_id = "clone_local_chrome_merge_test"
    shutil.rmtree(settings.creator_clones_dir / set_id, ignore_errors=True)
    save_sample_set(
        CloneSampleSet(
            set_id=set_id,
            title="已有素材池",
            source_platform="douyin",
            samples=[
                CloneSample(
                    sample_id="sample_7622653084993647603",
                    source_type="douyin",
                    aweme_id="7622653084993647603",
                    title="已有作品",
                    source_url="https://www.douyin.com/video/7622653084993647603",
                )
            ],
        )
    )

    def fake_scan(
        profile_url: str,
        max_items: int = 100,
        scroll_rounds: int = 6,
        merge_sample_set_id: str = "",
        authorization_context: dict | None = None,
    ):
        assert authorization_context and authorization_context["one_time_token_consumed"] is True
        existing = load_sample_set(merge_sample_set_id)
        existing.samples.extend(
            [
                CloneSample(
                    sample_id="sample_7622653084993647603",
                    source_type="douyin",
                    aweme_id="7622653084993647603",
                    title="重复作品",
                    source_url="https://www.douyin.com/video/7622653084993647603",
                ),
                CloneSample(
                    sample_id="sample_7539896907901062452",
                    source_type="douyin",
                    aweme_id="7539896907901062452",
                    title="新增作品",
                    source_url="https://www.douyin.com/video/7539896907901062452",
                ),
            ]
        )
        existing.samples, duplicate_count = dedupe_samples(existing.samples)
        existing.warnings.append(f"继续采集完成：重复 {duplicate_count} 条。")
        save_sample_set(existing)
        return existing

    monkeypatch.setattr("app.routes.local_helper.scan_douyin_profile_from_local_chrome", fake_scan)
    token = client.post("/api/local-helper/chrome/scan-token").json()["token"]
    response = client.post(
        "/api/local-helper/chrome/scan-profile",
        json={
            "profile_url": "https://www.douyin.com/user/MS4wLjABAAAAabc12345",
            "token": token,
            "page_confirmed": True,
            "max_items": 200,
            "scroll_rounds": 12,
            "sample_set_id": set_id,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["set"]["set_id"] == set_id
    assert payload["set"]["sample_count"] == 2
    assert "capture_audit" in payload
    assert {sample["aweme_id"] for sample in payload["set"]["samples"]} == {
        "7622653084993647603",
        "7539896907901062452",
    }
    assert any("继续采集完成" in warning for warning in payload["set"]["warnings"])


def test_local_chrome_service_merges_scanned_items_into_existing_set(monkeypatch) -> None:
    from app.services.local_chrome import scan_douyin_profile_from_local_chrome

    set_id = "clone_local_chrome_service_merge"
    shutil.rmtree(settings.creator_clones_dir / set_id, ignore_errors=True)
    save_sample_set(
        CloneSampleSet(
            set_id=set_id,
            title="服务合并测试",
            source_platform="douyin",
            samples=[
                CloneSample(
                    sample_id="sample_7622653084993647603",
                    source_type="douyin",
                    aweme_id="7622653084993647603",
                    title="已有作品",
                    source_url="https://www.douyin.com/video/7622653084993647603",
                )
            ],
        )
    )

    monkeypatch.setattr(
        "app.services.local_chrome._chrome_tabs",
        lambda chrome_debug_url: [
            {
                "type": "page",
                "url": "https://www.douyin.com/user/MS4wLjABAAAAabc12345",
                "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/1",
            }
        ],
    )
    monkeypatch.setattr(
        "app.services.local_chrome._evaluate_tab",
        lambda websocket_url, expression: {
            "profile": {
                "nickname": "测试账号",
                "url": "https://www.douyin.com/user/MS4wLjABAAAAabc12345?msToken=secret",
                "sec_user_id": "MS4wLjABAAAAabc12345",
                "bio": "甜美 COS 账号 token=secret",
                "stats": {
                    "following_count": 12,
                    "follower_count": 34000,
                    "liked_count": 560000,
                    "work_count": 42,
                },
            },
            "items": [
                {
                    "aweme_id": "7622653084993647603",
                    "source_url": "https://www.douyin.com/video/7622653084993647603",
                    "title": "重复作品",
                    "media_type": "video",
                },
                {
                    "aweme_id": "7539896907901062452",
                    "source_url": "https://www.douyin.com/video/7539896907901062452",
                    "title": "新增作品",
                    "media_type": "video",
                    "like_count": 88,
                },
            ],
            "captured_count": 2,
            "scroll_count": 3,
        },
    )

    sample_set = scan_douyin_profile_from_local_chrome(
        "https://www.douyin.com/user/MS4wLjABAAAAabc12345",
        max_items=200,
        scroll_rounds=12,
        merge_sample_set_id=set_id,
    )

    assert sample_set.set_id == set_id
    assert len(sample_set.samples) == 2
    assert sample_set.profile_metadata["nickname"] == "测试账号"
    assert sample_set.profile_metadata["sec_user_id"] == "MS4wLjABAAAAabc12345"
    assert sample_set.profile_metadata["stats"]["follower_count"] == 34000
    assert "[redacted]" in sample_set.profile_metadata["bio"]
    assert "secret" not in json.dumps(sample_set.profile_metadata, ensure_ascii=False).lower()
    assert load_sample_set(set_id).samples[1].aweme_id == "7539896907901062452"
    assert any("继续采集完成" in warning for warning in sample_set.warnings)
    browser_profile_path = settings.creator_clones_dir / set_id / "browser_profile.json"
    assert browser_profile_path.is_file()
    browser_profile = json.loads(browser_profile_path.read_text(encoding="utf-8"))
    assert "visible_text_excerpt" not in browser_profile
    persisted = load_sample_set(set_id)
    assert persisted.profile_metadata["nickname"] == "测试账号"
    assert persisted.profile_metadata["stats"]["liked_count"] == 560000
    audit_path = settings.creator_clones_dir / set_id / "capture_audit.json"
    audit_history_path = settings.creator_clones_dir / set_id / "capture_audits.jsonl"
    assert audit_path.is_file()
    assert audit_history_path.is_file()
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["set_id"] == set_id
    assert audit["capture_method"] == "local_chrome_dom_readonly_scroll"
    assert audit["scroll_count"] == 3
    assert audit["final_sample_count"] == 2
    assert audit["merged_into_existing_set"] is True
    assert audit["media_summary"]["video_count"] == 1
    assert audit["media_summary"]["unknown_count"] == 1
    assert audit["media_summary"]["buildable_item_count"] == 2
    assert audit["media_summary"]["image_count"] == 0
    assert audit["media_summary"]["metadata_only_count"] == 2
    assert audit["field_coverage"]["total"] == 2
    assert audit["field_coverage"]["with_title"] == 2
    assert "field_coverage" in audit
    assert audit["profile_metadata"]["nickname"] == "测试账号"
    assert audit["profile_metadata"]["stats"]["work_count"] == 42
    assert audit["safety"]["loopback_only"] is True
    assert audit["safety"]["one_time_token_required"] is True
    assert audit["safety"]["one_time_token_consumed"] is False
    assert audit["safety"]["page_confirmation_required"] is True
    assert audit["safety"]["page_confirmed"] is False
    assert audit["authorization"]["page_confirmed"] is False
    assert audit["authorization"]["one_time_token_consumed"] is False
    assert audit["authorization"]["trigger"] == "unknown"
    assert audit["safety"]["cookie_read"] is False
    assert audit["safety"]["cookie_returned"] is False
    assert audit["safety"]["cookie_logged"] is False
    assert audit["safety"]["dom_visible_metadata_only"] is True
    assert audit["safety"]["public_site_cookie_free"] is True
    assert audit["safety"]["login_token_returned"] is False
    assert audit["security_contract"]["uses_user_local_chrome_session"] is True
    assert audit["security_contract"]["returned_data_scope"] == [
        "account_visible_metadata",
        "visible_work_list",
        "visible_interaction_metrics",
        "sanitized_source_urls",
    ]
    audit_text = audit_path.read_text(encoding="utf-8").lower()
    assert "mstoken" not in audit_text
    assert "sessionid" not in audit_text
    assert "secret" not in audit_text
    assert "websocketdebuggerurl" not in audit_text
    assert "devtools/page" not in audit_text
    assert audit_history_path.read_text(encoding="utf-8").strip()
    handoff_path = settings.creator_clones_dir / set_id / "handoff_manifest.json"
    assert handoff_path.is_file()
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert handoff["handoff_version"] == 1
    assert handoff["set_id"] == set_id
    assert handoff["sample_count"] == 2
    assert handoff["profile_metadata"]["nickname"] == "测试账号"
    assert handoff["profile_metadata"]["profile_url"] == "https://www.douyin.com/user/MS4wLjABAAAAabc12345"
    assert handoff["capture_audit"]["authorization"]["page_confirmed"] is False
    assert handoff["capture_audit"]["authorization"]["one_time_token_consumed"] is False
    assert handoff["capture_audit"]["authorization"]["trigger"] == "unknown"
    assert handoff["safety"]["public_site_cookie_free"] is True
    assert handoff["safety"]["public_site_receives_sanitized_metadata_only"] is True
    assert handoff["safety"]["handoff_contains_cookie"] is False
    assert handoff["safety"]["handoff_contains_login_token"] is False
    assert handoff["safety"]["handoff_contains_signed_media_url"] is False
    assert handoff["security_contract"]["public_site_cookie_free"] is True
    assert handoff["security_contract"]["signed_media_url_returned"] is False
    assert "Cookie" in handoff["security_contract"]["handoff_excludes"]
    assert handoff["handoff_scope"]["intended_receiver"] == "analysis_web_app"
    assert "Cookie" in handoff["handoff_scope"]["excludes"]
    assert "signed media URL" in handoff["handoff_scope"]["excludes"]
    handoff_text = json.dumps(handoff, ensure_ascii=False).lower()
    assert "mstoken" not in handoff_text
    assert "sessionid" not in handoff_text
    assert "sid_guard" not in handoff_text
    assert "passport" not in handoff_text
    assert "secret" not in handoff_text
    assert "websocketdebuggerurl" not in handoff_text
    assert "devtools/page" not in handoff_text

    set_response = client.get(f"/api/creator-clone/sets/{set_id}")
    assert set_response.status_code == 200
    set_payload = set_response.json()
    assert set_payload["capture_audit"]["set_id"] == set_id
    assert set_payload["capture_audit"]["safety"]["cookie_read"] is False
    assert set_payload["handoff_manifest"]["set_id"] == set_id
    assert set_payload["exports"]["handoff_manifest_json"].endswith("handoff_manifest.json")

    handoff_response = client.get(f"/api/creator-clone/sets/{set_id}/files/handoff_manifest.json")
    assert handoff_response.status_code == 200
    assert handoff_response.json()["safety"]["public_site_cookie_free"] is True


def test_local_chrome_extractor_ignores_footer_and_baiduspider_recommendations() -> None:
    from app.services.local_chrome import _extractor_script

    script = _extractor_script(max_items=30, scroll_rounds=4)

    assert "ignoredAnchor" in script
    assert "tag === 'footer'" in script
    assert "用户服务协议" in script
    assert "source=Baiduspider" in script
    assert "anchorCount > 1" in script


def test_local_chrome_extractor_collects_profile_metadata_without_cookie_fields() -> None:
    from app.services.local_chrome import _extractor_script

    script = _extractor_script(max_items=30, scroll_rounds=4)

    assert "profileBio" in script
    assert "secUserIdFromLocation" in script
    assert "profileWorkCount" in script
    assert "h2.A22Lqe_t" in script
    assert "follower_count" in script
    assert "liked_count" in script
    assert "work_count" in script
    assert "document.cookie" not in script
    assert "localStorage" not in script


def test_local_chrome_extractor_does_not_read_sensitive_browser_state_or_network() -> None:
    from app.services.local_chrome import _extractor_script

    script = _extractor_script(max_items=30, scroll_rounds=4)
    forbidden_fragments = [
        "document.cookie",
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "cookieStore",
        "navigator.credentials",
        "performance.getEntries",
        "fetch(",
        "XMLHttpRequest",
        "Authorization",
        "Network.",
    ]

    for fragment in forbidden_fragments:
        assert fragment not in script


def test_local_chrome_extractor_reads_visible_card_metric_attributes_safely() -> None:
    from app.services.local_chrome import _extractor_script

    script = _extractor_script(max_items=30, scroll_rounds=4)

    assert "metricFromCard" in script
    assert "metricNodeText" in script
    assert "[aria-label], [title], [data-e2e], button, span, div" in script
    assert "metricFromCard(card, ['点赞', '赞', '喜欢'])" in script
    assert "metricFromCard(card, ['评论'])" in script
    assert "metricFromCard(card, ['分享', '转发'])" in script
    assert "metricFromCard(card, ['收藏'])" in script
    assert "metricFromCard(card, ['播放', '观看'])" in script
    assert "comment_count: metricFromCard(card, ['评论'])" in script
    assert "share_count: metricFromCard(card, ['分享', '转发'])" in script
    assert "collect_count: metricFromCard(card, ['收藏'])" in script
    assert "parseCount(countTexts[1]" not in script
    assert "parseCount(countTexts[2]" not in script
    assert "parseCount(countTexts[3]" not in script
    assert "document.cookie" not in script
    assert "localStorage" not in script


def test_local_only_guard_rejects_non_loopback_client() -> None:
    remote_client = TestClient(app, client=("203.0.113.10", 12345))
    response = remote_client.get("/")
    assert response.status_code == 403
    assert response.json()["error_code"] == "LOCAL_HELPER_FORBIDDEN"


def test_local_only_guard_rejects_non_loopback_host_header() -> None:
    response = client.get("/", headers={"host": "example.com"})

    assert response.status_code == 403
    assert response.json()["error_code"] == "LOCAL_HELPER_FORBIDDEN"
    assert "Host" in response.json()["message"]


def test_local_only_guard_allows_loopback_host_variants() -> None:
    ipv4_response = client.get("/", headers={"host": "127.0.0.2:8765"})
    ipv6_response = client.get("/", headers={"host": "[::1]:8765"})
    localhost_response = client.get("/", headers={"host": "localhost.:8765"})

    assert ipv4_response.status_code == 200
    assert ipv6_response.status_code == 200
    assert localhost_response.status_code == 200


def test_local_only_guard_rejects_forwarded_public_client() -> None:
    response = client.get("/", headers={"x-forwarded-for": "203.0.113.10"})

    assert response.status_code == 403
    assert response.json()["error_code"] == "LOCAL_HELPER_FORBIDDEN"
    assert "公网代理" in response.json()["message"]


def test_local_only_guard_rejects_real_ip_public_client() -> None:
    response = client.get("/", headers={"x-real-ip": "203.0.113.10"})

    assert response.status_code == 403
    assert response.json()["error_code"] == "LOCAL_HELPER_FORBIDDEN"
    assert "公网代理" in response.json()["message"]


def test_local_only_guard_rejects_forwarded_header_public_client() -> None:
    response = client.get("/", headers={"forwarded": 'for="203.0.113.10";proto=https;host=example.com'})

    assert response.status_code == 403
    assert response.json()["error_code"] == "LOCAL_HELPER_FORBIDDEN"
    assert "公网代理" in response.json()["message"]


def test_local_only_guard_allows_loopback_forwarded_client() -> None:
    response = client.get("/", headers={"x-forwarded-for": "127.0.0.1"})

    assert response.status_code == 200


def test_local_only_guard_rejects_cross_site_write_origin() -> None:
    response = client.post(
        "/api/local-helper/chrome/scan-token",
        headers={"origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["error_code"] == "LOCAL_HELPER_FORBIDDEN"
    assert "Origin" in response.json()["message"]


def test_local_only_guard_rejects_userinfo_origin_spoof() -> None:
    response = client.post(
        "/api/local-helper/chrome/scan-token",
        headers={"origin": "http://127.0.0.1:8765@evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["error_code"] == "LOCAL_HELPER_FORBIDDEN"
    assert "Origin" in response.json()["message"]


def test_local_only_guard_rejects_userinfo_referer_spoof() -> None:
    response = client.post(
        "/api/local-helper/chrome/scan-token",
        headers={"referer": "http://127.0.0.1:8765@evil.example/path"},
    )

    assert response.status_code == 403
    assert response.json()["error_code"] == "LOCAL_HELPER_FORBIDDEN"
    assert "Referer" in response.json()["message"]


def test_local_only_guard_allows_loopback_write_origin() -> None:
    response = client.post(
        "/api/local-helper/chrome/scan-token",
        headers={"origin": "http://127.0.0.1:8765"},
    )

    assert response.status_code == 200
    assert response.json()["token"]


def test_local_chrome_empty_scan_message_guides_login_and_redacts_sensitive_text() -> None:
    from app.services.local_chrome import _empty_scan_message

    message = _empty_scan_message(
        {
            "nickname": "抖音验证页",
            "visible_text_excerpt": "请登录后继续 验证码 sessionid=abc msToken=secret",
        },
        {"captured_count": 0, "scroll_count": 4},
    )

    assert "Chrome 页面未提取到可见作品" in message
    assert "登录或完成平台验证" in message
    assert "滚动 4 轮" in message
    assert "未回传原文" in message
    assert "请登录后继续" not in message
    assert "验证码" not in message
    assert "sessionid" not in message.lower()
    assert "mstoken" not in message.lower()
    assert "secret" not in message.lower()


def test_local_chrome_profile_redacts_sensitive_visible_text() -> None:
    from app.services.local_chrome import _sanitize_profile

    profile = _sanitize_profile(
        {
            "nickname": "测试账号",
            "visible_text_excerpt": "sessionid=secretcookie passport=secretpassport sid_guard=secretsid 普通标题",
            "url": "https://www.douyin.com/user/MS4wLjABAAAAabc12345?msToken=secret&from_tab_name=main",
        }
    )
    text = json.dumps(profile, ensure_ascii=False).lower()
    assert "sessionid" not in text
    assert "passport" not in text
    assert "sid_guard" not in text
    assert "visible_text_excerpt" not in profile
    assert profile["visible_text_excerpt_chars"] > 0
    assert "secretcookie" not in text
    assert "secretpassport" not in text
    assert "secretsid" not in text
    assert "普通标题" not in text
    assert profile["url"] == "https://www.douyin.com/user/MS4wLjABAAAAabc12345"


def test_local_chrome_sample_redacts_sensitive_dom_fields() -> None:
    from app.services.local_chrome import _sample_from_browser_item

    sample = _sample_from_browser_item(
        {
            "aweme_id": "7622653084993647603",
            "source_url": "https://www.douyin.com/video/7622653084993647603?msToken=secret",
            "title": "标题 sessionid=abc",
            "desc": "描述 passport=def sid_guard=ghi",
            "author": "作者 token=authorsecret",
            "create_time": "2026-06-01 msToken=timesecret",
            "tags": ["甜美", "token=tagsecret", "COS"],
            "cover_url": "https://example.com/cover.jpg?token=secret",
            "media_type": "video",
            "view_count": "1200",
        }
    )
    payload_text = json.dumps(sample.to_dict(), ensure_ascii=False).lower()
    assert "sessionid" not in payload_text
    assert "passport" not in payload_text
    assert "sid_guard" not in payload_text
    assert "mstoken" not in payload_text
    assert "token" not in payload_text
    assert "secret" not in payload_text
    assert "abc" not in payload_text
    assert "def" not in payload_text
    assert "ghi" not in payload_text
    assert "authorsecret" not in payload_text
    assert "timesecret" not in payload_text
    assert "tagsecret" not in payload_text
    assert "标题" in sample.title
    assert "描述" in sample.desc
    assert "作者" in sample.author
    assert "2026-06-01" in sample.create_time
    assert sample.view_count == 1200
    assert sample.tags == ["甜美", "[redacted]", "COS"]
    assert sample.source_url == "https://www.douyin.com/video/7622653084993647603"
    assert sample.cover_url == "https://example.com/cover.jpg"


def test_local_chrome_sample_preserves_visible_metadata_fields() -> None:
    from app.services.local_chrome import _sample_from_browser_item

    sample = _sample_from_browser_item(
        {
            "aweme_id": "7622653084993647603",
            "source_url": "https://www.douyin.com/video/7622653084993647603",
            "title": "甜美 COS 变装",
            "author": "测试账号",
            "create_time": "2026-06-01",
            "tags": ["甜美", "COS", "变装"],
            "view_count": 35000,
            "like_count": "1200",
            "comment_count": 34,
            "share_count": 5,
            "collect_count": 8,
            "media_type": "video",
        }
    )

    assert sample.author == "测试账号"
    assert sample.create_time == "2026-06-01"
    assert sample.tags == ["甜美", "COS", "变装"]
    assert sample.view_count == 35000
    assert sample.like_count == 1200
    assert sample.comment_count == 34
    assert sample.share_count == 5
    assert sample.collect_count == 8


def test_local_chrome_sample_preserves_douyin_note_source_url() -> None:
    from app.services.local_chrome import _sample_from_browser_item

    sample = _sample_from_browser_item(
        {
            "aweme_id": "7622653084993647604",
            "source_url": "https://www.douyin.com/note/7622653084993647604?msToken=secret",
            "title": "图文作品",
            "media_type": "image",
        }
    )

    assert sample.media_type == "image"
    assert sample.source_url == "https://www.douyin.com/note/7622653084993647604"


def test_local_chrome_sample_drops_private_metadata_urls() -> None:
    from app.services.local_chrome import _sample_from_browser_item

    sample = _sample_from_browser_item(
        {
            "aweme_id": "7622653084993647603",
            "source_url": "https://www.douyin.com/video/7622653084993647603?msToken=secret",
            "cover_url": "http://127.0.0.1:8000/private-cover.jpg?token=secret",
            "media_type": "video",
        }
    )

    assert sample.source_url == "https://www.douyin.com/video/7622653084993647603"
    assert sample.cover_url == ""


def test_local_chrome_sample_strips_url_userinfo() -> None:
    from app.services.local_chrome import _sample_from_browser_item

    sample = _sample_from_browser_item(
        {
            "aweme_id": "",
            "source_url": "https://viewer:password@example.com/video/7622653084993647603?x=1",
            "cover_url": "https://cover_user:cover_pass@example.com/cover.jpg?x=1",
            "media_type": "video",
        }
    )

    assert sample.source_url == "https://example.com/video/7622653084993647603"
    assert sample.cover_url == "https://example.com/cover.jpg"
    payload_text = json.dumps(sample.to_dict(), ensure_ascii=False).lower()
    assert "viewer:password" not in payload_text
    assert "cover_user:cover_pass" not in payload_text
