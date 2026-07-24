from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from app.config import settings
from app.database import SessionLocal
from app.errors import AppError, ErrorCode, PROMPT_RECOVERY_LLM_ERROR_CODES
from app.models import CaseArtifact, DouyinVideoItem, Job, utc_now
from app.providers.profile_base import ProfileScanRequest
from app.routes.common import error_response
from app.services.asr import run_case_asr
from app.services.auto_analyzer import analyze_case_artifact
from app.services.case_builder import build_case_from_local_video
from app.services.downloader import download_candidate
from app.services.douyin_url_parser import extract_aweme_id
from app.services.enrichment import build_enrichment_archive
from app.services.ocr import run_case_ocr
from app.services.quality_resolver import resolve_quality_candidates
from app.services.profile_scan import scan_profile
from app.services.creator_clone import (
    BATCH_DISTILL_MAX_SAMPLES,
    CloneSampleSet,
    MAX_DISTILL_SAMPLES,
    batch_distill_creator_clone,
    build_distill_execution_plan,
    creator_intelligence_payload_for_sample_set,
    dedupe_samples,
    distill_creator_clone,
    load_sample_set,
    normalize_content_profile,
    prompt_only_result,
    sample_from_dict,
    save_sample_set,
    update_sample_set_with_case_artifacts,
)
from app.services.creator_intelligence import CreatorRuntimeEngine, WorkflowAction
from app.services.runtime_settings import effective_llm_settings


router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class BuildCaseJobRequest(BaseModel):
    local_video_id: str


class ResolveQualitiesJobRequest(BaseModel):
    aweme_ids: list[str]


class DownloadJobRequest(BaseModel):
    aweme_id: str
    candidate_id: str


class ProfileScanJobRequest(BaseModel):
    profile_url: str = ""
    sec_user_id: str = ""
    manual_links: str = ""
    structured_items: str = ""
    count: int = 20
    max_pages: int = 1
    sort_by: str = "like_count"


class ProfileBuildCaseItem(BaseModel):
    aweme_id: str = ""
    sample_id: str = ""
    case_id: str = ""
    source_url: str = ""
    webpage_url: str = ""
    title: str = ""
    media_type: str = "unknown"


class ProfileBuildCasesJobRequest(BaseModel):
    items: list[ProfileBuildCaseItem]
    selected_sample_ids: list[str] = []
    auto_enrich: bool = True
    auto_asr: bool = True
    auto_ocr: bool = True
    auto_analyze: bool = False
    quality_preference: str = "best"
    sample_set_id: str = ""


class CreatorCloneDistillJobRequest(BaseModel):
    sample_set_id: str = ""
    samples: list[dict] = []
    selected_sample_ids: list[str] = []
    distill_mode: str = "quick"
    include_case_reports: bool = True
    max_samples: int = MAX_DISTILL_SAMPLES
    title: str = ""
    creator_name: str = ""
    source_platform: str = "unknown"
    content_profile: str = "auto"


class CreatorCloneBatchDistillJobRequest(BaseModel):
    sample_set_id: str = ""
    samples: list[dict] = []
    selected_sample_ids: list[str] = []
    distill_mode: str = "quick"
    batch_size: int = MAX_DISTILL_SAMPLES
    max_samples: int = BATCH_DISTILL_MAX_SAMPLES
    title: str = ""
    creator_name: str = ""
    source_platform: str = "unknown"
    content_profile: str = "auto"


class AnalyzeCaseJobRequest(BaseModel):
    case_id: str


class EnrichCaseJobRequest(BaseModel):
    case_id: str


class AsrCaseJobRequest(BaseModel):
    case_id: str


class OcrCaseJobRequest(BaseModel):
    case_id: str


def _artifact_result(artifact) -> dict:
    return {
        "case_id": artifact.case_id,
        "local_video_id": artifact.local_video_id,
        "video_path": artifact.video_path,
        "metadata_path": artifact.metadata_path,
        "analysis_input_path": artifact.analysis_input_path,
        "prompt_path": artifact.prompt_path,
        "contact_sheet_path": artifact.contact_sheet_path,
        "keyframes_dir": artifact.keyframes_dir,
    }


def _analysis_result(result: dict) -> dict:
    return {
        "analysis_result_path": result.get("analysis_result_path", ""),
        "analysis_report_path": result.get("analysis_report_path", ""),
        "analysis_result": result.get("analysis_result", {}),
        "analysis_report": result.get("analysis_report", ""),
    }


def _set_job(
    job: Job,
    status: str,
    progress: int,
    message: str,
    result: dict | None = None,
    error_code: str = "",
) -> None:
    job.status = status
    job.progress = max(0, min(100, progress))
    job.message = message
    job.error_code = error_code
    job.updated_at = utc_now()
    if result is not None:
        job.result_json = json.dumps(result, ensure_ascii=False)


def _run_build_case_job(job_id: str, local_video_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return
        _set_job(job, "running", 1, "任务开始")
        db.commit()

        def progress(value: int, message: str) -> None:
            current = db.get(Job, job_id)
            if current:
                _set_job(current, "running", value, message)
                db.commit()

        artifact = build_case_from_local_video(db, local_video_id, progress=progress)
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "success", 100, "素材包生成完成", result=_artifact_result(artifact))
            db.commit()
    except AppError as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "failed", job.progress, error.message, error_code=error.code)
            db.commit()
    except Exception as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(
                job,
                "failed",
                job.progress,
                str(error)[:500],
                error_code=ErrorCode.CASE_BUILD_FAILED,
            )
            db.commit()
    finally:
        db.close()


def _run_resolve_qualities_job(job_id: str, aweme_ids: list[str]) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "running", 10, "正在解析清晰度候选")
            db.commit()
        results = {}
        for index, value in enumerate(aweme_ids):
            aweme_id = extract_aweme_id(value)
            results[aweme_id] = resolve_quality_candidates(db, aweme_id)
            job = db.get(Job, job_id)
            if job:
                progress = 10 + int(((index + 1) / max(1, len(aweme_ids))) * 80)
                _set_job(job, "running", progress, f"已解析 {index + 1}/{len(aweme_ids)}")
                db.commit()
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "success", 100, "清晰度解析完成", result={"results": results})
            db.commit()
    except AppError as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "failed", job.progress, error.message, error_code=error.code)
            db.commit()
    except Exception as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "failed", job.progress, str(error)[:500], error_code=ErrorCode.PROVIDER_FAILED)
            db.commit()
    finally:
        db.close()


def _run_profile_scan_job(job_id: str, payload: dict) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "running", 10, "正在扫描主页作品列表")
            db.commit()

        result = scan_profile(ProfileScanRequest(**payload))

        job = db.get(Job, job_id)
        if job:
            _set_job(
                job,
                "success",
                100,
                "主页扫描完成",
                result=result.to_dict() | {"sort_by": payload.get("sort_by", "like_count")},
            )
            db.commit()
    except AppError as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "failed", job.progress, error.message, error_code=error.code)
            db.commit()
    except Exception as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "failed", job.progress, str(error)[:500], error_code=ErrorCode.PROFILE_SCAN_FAILED)
            db.commit()
    finally:
        db.close()


def _run_download_job(job_id: str, aweme_id: str, candidate_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "running", 10, "正在下载视频")
            db.commit()

        def progress(value: int, message: str) -> None:
            current = db.get(Job, job_id)
            if current:
                _set_job(current, "running", value, message)
                db.commit()

        result = download_candidate(db, aweme_id, candidate_id, progress=progress)
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "success", 100, "下载完成", result=result)
            db.commit()
    except AppError as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "failed", job.progress, error.message, error_code=error.code)
            db.commit()
    except Exception as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "failed", job.progress, str(error)[:500], error_code=ErrorCode.DOWNLOAD_FAILED)
            db.commit()
    finally:
        db.close()


def _run_download_and_build_case_job(job_id: str, aweme_id: str, candidate_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "running", 3, "准备下载视频")
            db.commit()

        def download_progress(value: int, message: str) -> None:
            current = db.get(Job, job_id)
            if current:
                scaled = 5 + int(max(0, min(100, value)) * 0.4)
                _set_job(current, "running", min(45, scaled), message)
                db.commit()

        download_result = download_candidate(db, aweme_id, candidate_id, progress=download_progress)
        local_video_id = download_result["local_video_id"]

        job = db.get(Job, job_id)
        if job:
            _set_job(job, "running", 50, "下载完成，开始生成素材包", result={"download": download_result})
            db.commit()

        def case_progress(value: int, message: str) -> None:
            current = db.get(Job, job_id)
            if current:
                scaled = 50 + int(max(0, min(100, value)) * 0.45)
                _set_job(current, "running", min(95, scaled), message)
                db.commit()

        artifact = build_case_from_local_video(db, local_video_id, progress=case_progress)
        result = {
            "download": download_result,
            "case": _artifact_result(artifact),
            "local_video_id": local_video_id,
            "case_id": artifact.case_id,
            "analysis_input_path": artifact.analysis_input_path,
            "prompt_path": artifact.prompt_path,
            "contact_sheet_path": artifact.contact_sheet_path,
            "keyframes_dir": artifact.keyframes_dir,
        }
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "success", 100, "下载和素材包生成完成", result=result)
            db.commit()
    except AppError as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "failed", job.progress, error.message, error_code=error.code)
            db.commit()
    except Exception as error:
        job = db.get(Job, job_id)
        if job:
            message = str(error)[:500]
            result_payload = None
            if "sample_set" in locals():
                try:
                    runtime_result = CreatorRuntimeEngine.dispatch_sample_set(
                        sample_set.set_id,
                        WorkflowAction.MARK_EVIDENCE_READY,
                        job_state={
                            "status": "failed",
                            "error_code": ErrorCode.CASE_BUILD_FAILED,
                            "message": message,
                            "job_id": job_id,
                        },
                    )
                    result_payload = {
                        "ok": False,
                        "error_code": ErrorCode.CASE_BUILD_FAILED,
                        "message": message,
                        "creator_intelligence": runtime_result.creator_intelligence,
                    }
                except Exception:
                    result_payload = None
            _set_job(job, "failed", job.progress, message, result=result_payload, error_code=ErrorCode.CASE_BUILD_FAILED)
            db.commit()
    finally:
        db.close()


def _run_analyze_case_job(job_id: str, case_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "running", 5, "准备自动拆解")
            db.commit()
        from app.models import CaseArtifact

        artifact = db.get(CaseArtifact, case_id)
        if not artifact:
            raise AppError(ErrorCode.CASE_BUILD_FAILED, "素材包不存在。")

        def progress(value: int, message: str) -> None:
            current = db.get(Job, job_id)
            if current:
                _set_job(current, "running", value, message)
                db.commit()

        result = analyze_case_artifact(artifact, progress=progress, mode="fast")
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "success", 100, "自动拆解完成", result={"case_id": case_id, **_analysis_result(result)})
            db.commit()
    except AppError as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "failed", job.progress, error.message, error_code=error.code)
            db.commit()
    except Exception as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "failed", job.progress, str(error)[:500], error_code=ErrorCode.AUTO_ANALYSIS_FAILED)
            db.commit()
    finally:
        db.close()


def _run_enrich_case_job(job_id: str, case_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "running", 5, "准备富化归档")
            db.commit()

        artifact = db.get(CaseArtifact, case_id)
        if not artifact:
            raise AppError(ErrorCode.CASE_BUILD_FAILED, "素材包不存在。")

        def progress(value: int, message: str) -> None:
            current = db.get(Job, job_id)
            if current:
                _set_job(current, "running", value, message)
                db.commit()

        result = build_enrichment_archive(artifact, progress=progress)
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "success", 100, "富化归档完成", result={"case_id": case_id, **result})
            db.commit()
    except AppError as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "failed", job.progress, error.message, error_code=error.code)
            db.commit()
    except Exception as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "failed", job.progress, str(error)[:500], error_code=ErrorCode.ENRICHMENT_FAILED)
            db.commit()
    finally:
        db.close()


def _run_asr_case_job(job_id: str, case_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "running", 5, "准备语音识别")
            db.commit()

        artifact = db.get(CaseArtifact, case_id)
        if not artifact:
            raise AppError(ErrorCode.CASE_BUILD_FAILED, "素材包不存在。")

        def progress(value: int, message: str) -> None:
            current = db.get(Job, job_id)
            if current:
                _set_job(current, "running", value, message)
                db.commit()

        result = run_case_asr(artifact, progress=progress)
        job = db.get(Job, job_id)
        if job:
            message = "ASR 完成" if result.get("status") == "success" else "ASR 完成：未检测到语音"
            _set_job(job, "success", 100, message, result={"case_id": case_id, **result})
            db.commit()
    except AppError as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "failed", job.progress, error.message, error_code=error.code)
            db.commit()
    except Exception as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "failed", job.progress, str(error)[:500], error_code=ErrorCode.ASR_FAILED)
            db.commit()
    finally:
        db.close()


def _run_ocr_case_job(job_id: str, case_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "running", 5, "准备画面文字识别")
            db.commit()

        artifact = db.get(CaseArtifact, case_id)
        if not artifact:
            raise AppError(ErrorCode.CASE_BUILD_FAILED, "素材包不存在。")

        def progress(value: int, message: str) -> None:
            current = db.get(Job, job_id)
            if current:
                _set_job(current, "running", value, message)
                db.commit()

        result = run_case_ocr(artifact, progress=progress)
        job = db.get(Job, job_id)
        if job:
            message = "OCR 完成" if result.get("status") == "success" else "OCR 完成：未检测到画面文字"
            _set_job(job, "success", 100, message, result={"case_id": case_id, **result})
            db.commit()
    except AppError as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "failed", job.progress, error.message, error_code=error.code)
            db.commit()
    except Exception as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "failed", job.progress, str(error)[:500], error_code=ErrorCode.OCR_FAILED)
            db.commit()
    finally:
        db.close()


def _run_download_build_analyze_case_job(job_id: str, aweme_id: str, candidate_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "running", 3, "准备下载视频")
            db.commit()

        def download_progress(value: int, message: str) -> None:
            current = db.get(Job, job_id)
            if current:
                scaled = 5 + int(max(0, min(100, value)) * 0.25)
                _set_job(current, "running", min(30, scaled), message)
                db.commit()

        download_result = download_candidate(db, aweme_id, candidate_id, progress=download_progress)
        local_video_id = download_result["local_video_id"]

        job = db.get(Job, job_id)
        if job:
            _set_job(job, "running", 35, "下载完成，开始生成素材包", result={"download": download_result})
            db.commit()

        def case_progress(value: int, message: str) -> None:
            current = db.get(Job, job_id)
            if current:
                scaled = 35 + int(max(0, min(100, value)) * 0.3)
                _set_job(current, "running", min(65, scaled), message)
                db.commit()

        artifact = build_case_from_local_video(db, local_video_id, progress=case_progress)
        analysis_status = "success"
        analysis = {}
        analysis_error = {}
        result = {
            "download": download_result,
            "case": _artifact_result(artifact),
            "local_video_id": local_video_id,
            "case_id": artifact.case_id,
            "analysis_status": "pending",
            "analysis": {},
            "analysis_error": {},
            "analysis_input_path": artifact.analysis_input_path,
            "prompt_path": artifact.prompt_path,
            "contact_sheet_path": artifact.contact_sheet_path,
            "keyframes_dir": artifact.keyframes_dir,
        }
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "running", 65, "素材包已生成，开始自动拆解", result=result)
            db.commit()

        def analysis_progress(value: int, message: str) -> None:
            current = db.get(Job, job_id)
            if current:
                scaled = 65 + int(max(0, min(100, value)) * 0.3)
                _set_job(current, "running", min(95, scaled), message)
                db.commit()

        try:
            analysis = _analysis_result(analyze_case_artifact(artifact, progress=analysis_progress, mode="fast"))
        except AppError as error:
            analysis_status = "skipped" if error.code == ErrorCode.LLM_NOT_CONFIGURED else "failed"
            analysis_error = error.as_dict()

        result["analysis_status"] = analysis_status
        result["analysis"] = analysis
        result["analysis_error"] = analysis_error
        job = db.get(Job, job_id)
        if job:
            if analysis_status == "success":
                message = "下载、素材包和自动拆解完成"
            elif analysis_status == "skipped":
                message = "素材包已生成，自动拆解等待配置大模型"
            else:
                message = "素材包已生成，自动拆解失败，可在分析页重试"
            _set_job(job, "success", 100, message, result=result)
            db.commit()
    except AppError as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "failed", job.progress, error.message, error_code=error.code)
            db.commit()
    except Exception as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "failed", job.progress, str(error)[:500], error_code=ErrorCode.AUTO_ANALYSIS_FAILED)
            db.commit()
    finally:
        db.close()


def _choose_profile_queue_candidate(candidates: list[dict], preference: str) -> dict:
    if not candidates:
        raise AppError(ErrorCode.QUALITY_NOT_FOUND)
    preference = (preference or "best").lower()
    if preference == "1080":
        return next((candidate for candidate in candidates if "1080" in str(candidate.get("quality_label", ""))), candidates[0])
    if preference == "720":
        return next((candidate for candidate in candidates if "720" in str(candidate.get("quality_label", ""))), candidates[0])
    return candidates[0]


def _profile_queue_counts(items: list[dict]) -> dict:
    reference_only_count = sum(
        1
        for item in items
        if item.get("status") == "skipped" and item.get("error_code") == ErrorCode.UNSUPPORTED_PROFILE_ITEM
    )
    return {
        "completed_count": sum(1 for item in items if item.get("status") == "completed"),
        "failed_count": sum(1 for item in items if item.get("status") == "failed"),
        "skipped_count": sum(1 for item in items if item.get("status") == "skipped"),
        "reference_only_count": reference_only_count,
        "downloadable_count": sum(1 for item in items if _is_profile_queue_downloadable(item)),
    }


def _is_profile_queue_downloadable(item: dict) -> bool:
    return bool(str(item.get("aweme_id") or "").strip()) and str(item.get("media_type") or "unknown") not in {"image", "text"}


def _profile_queue_result(items: list[dict], sample_set_id: str = "", selected_sample_ids: list[str] | None = None) -> dict:
    counts = _profile_queue_counts(items)
    result = {"items": items, **counts, "pipeline_summary": _profile_pipeline_summary(items)}
    if sample_set_id:
        result["set"] = {"set_id": sample_set_id}
    if selected_sample_ids:
        result["selected_sample_ids"] = selected_sample_ids
    return result


def _profile_pipeline_summary(items: list[dict]) -> dict:
    counts = _profile_queue_counts(items)
    selected_count = len(items)
    downloadable_count = counts["downloadable_count"]
    processable_items = [item for item in items if _is_profile_queue_downloadable(item)]
    requested_stages = {
        "download": downloadable_count > 0,
        "build_case": downloadable_count > 0,
        "enrichment": any(item.get("enrichment_status") != "skipped" for item in processable_items),
        "asr": any(item.get("asr_status") != "skipped" for item in processable_items),
        "ocr": any(item.get("ocr_status") != "skipped" for item in processable_items),
        "llm_analysis": any(item.get("analysis_status") != "skipped" for item in processable_items),
    }
    downloaded_count = sum(1 for item in items if item.get("local_video_id"))
    case_count = sum(1 for item in items if item.get("case_id"))
    reused_case_count = sum(1 for item in items if item.get("case_reused"))
    enriched_count = sum(1 for item in items if item.get("enrichment_status") == "success")
    asr_success_count = sum(1 for item in items if item.get("asr_status") in {"success", "no_speech"})
    ocr_success_count = sum(1 for item in items if item.get("ocr_status") in {"success", "no_text"})
    asr_provider_missing_count = sum(1 for item in items if item.get("asr_status") == "provider_missing")
    ocr_provider_missing_count = sum(1 for item in items if item.get("ocr_status") == "provider_missing")
    failed_count = counts["failed_count"]
    ready_for_distill_count = sum(
        1
        for item in items
        if item.get("status") != "failed"
        and (
            item.get("case_id")
            or (item.get("status") == "skipped" and item.get("error_code") == ErrorCode.UNSUPPORTED_PROFILE_ITEM)
        )
    )
    notes: list[str] = []
    next_actions: list[str] = []
    if case_count:
        notes.append(f"已生成 {case_count} 个素材包，可作为创作者蒸馏证据。")
    if reused_case_count:
        notes.append(f"其中 {reused_case_count} 个素材包来自本地复用，已跳过重复下载和建包。")
    if counts["reference_only_count"]:
        notes.append(f"{counts['reference_only_count']} 条图文/元数据样本已保留为参考证据。")
    if selected_count:
        notes.append(
            f"本轮选中 {selected_count} 条：{downloadable_count} 条进入下载/素材包流水线，{counts['reference_only_count']} 条作为参考样本。"
        )
    if ready_for_distill_count:
        next_actions.append("可继续点击“大模型蒸馏”，系统会基于现有证据生成创作者规律。")
    if asr_provider_missing_count:
        notes.append(f"ASR provider 未配置，{asr_provider_missing_count} 条样本缺少语音转写。")
        next_actions.append("如需要口播/声音拆解，请配置 ASR_PROVIDER=auto 并安装 requirements-asr.txt。")
    if ocr_provider_missing_count:
        notes.append(f"OCR provider 未配置，{ocr_provider_missing_count} 条样本缺少画面文字识别。")
        next_actions.append("如需要封面字/字幕拆解，请配置 OCR_PROVIDER=auto 并安装 requirements-ocr.txt。")
    if failed_count:
        next_actions.append(f"复核 {failed_count} 条失败样本；其余样本仍可继续蒸馏。")
    return {
        "selected_count": selected_count,
        "downloadable_count": downloadable_count,
        "downloaded_count": downloaded_count,
        "case_count": case_count,
        "reused_case_count": reused_case_count,
        "enriched_count": enriched_count,
        "asr_success_count": asr_success_count,
        "ocr_success_count": ocr_success_count,
        "asr_provider_missing_count": asr_provider_missing_count,
        "ocr_provider_missing_count": ocr_provider_missing_count,
        "reference_only_count": counts["reference_only_count"],
        "ready_for_distill_count": ready_for_distill_count,
        "failed_count": failed_count,
        "requested_stages": requested_stages,
        "notes": notes,
        "next_actions": list(dict.fromkeys(next_actions)),
    }


def _optional_error_payload(error: Exception, fallback_code: str) -> dict:
    if isinstance(error, AppError):
        return error.as_dict()
    return {"error_code": fallback_code, "message": str(error)[:500]}


def _case_dir_from_artifact(artifact: CaseArtifact) -> Path:
    if artifact.video_path:
        return Path(artifact.video_path).parent
    return settings.cases_dir / artifact.case_id


def _case_artifact_reusable(artifact: CaseArtifact | None) -> bool:
    if not artifact:
        return False
    case_dir = _case_dir_from_artifact(artifact)
    required_paths = [
        Path(artifact.video_path),
        Path(artifact.metadata_path),
        Path(artifact.analysis_input_path),
        Path(artifact.contact_sheet_path),
    ]
    return all(path.is_file() for path in required_paths) and Path(artifact.keyframes_dir or case_dir / "keyframes").is_dir()


def _find_reusable_profile_case(db, item: dict) -> CaseArtifact | None:
    case_id = str(item.get("case_id") or "").strip()
    if case_id:
        artifact = db.get(CaseArtifact, case_id)
        if _case_artifact_reusable(artifact):
            return artifact
    aweme_id = str(item.get("aweme_id") or "").strip()
    if not aweme_id:
        return None
    artifacts = (
        db.query(CaseArtifact)
        .filter(CaseArtifact.aweme_id == aweme_id)
        .order_by(CaseArtifact.created_at.desc())
        .all()
    )
    return next((artifact for artifact in artifacts if _case_artifact_reusable(artifact)), None)


def _case_enrichment_dir(artifact: CaseArtifact) -> Path:
    return _case_dir_from_artifact(artifact) / "enrichment"


def _case_has_enrichment_archive(artifact: CaseArtifact) -> bool:
    return (_case_enrichment_dir(artifact) / "manifest.json").is_file()


def _case_has_asr(artifact: CaseArtifact) -> bool:
    asr_dir = _case_enrichment_dir(artifact) / "asr"
    return (asr_dir / "transcript.json").is_file() or (asr_dir / "transcript.txt").is_file()


def _case_has_ocr(artifact: CaseArtifact) -> bool:
    ocr_dir = _case_enrichment_dir(artifact) / "ocr"
    return (ocr_dir / "frame_ocr.json").is_file() or (ocr_dir / "subtitle_ocr.json").is_file()


def _case_has_ai_analysis(artifact: CaseArtifact) -> bool:
    case_dir = _case_dir_from_artifact(artifact)
    return (case_dir / "analysis_result.json").is_file() or (case_dir / "analysis_report.md").is_file()


def _update_profile_queue_job(db, job_id: str, progress: int, message: str, queue_items: list[dict]) -> None:
    job = db.get(Job, job_id)
    if job:
        _set_job(job, "running", min(95, progress), message, result=_profile_queue_result(queue_items))
        db.commit()


def _profile_queue_total_progress(index: int, total: int, item_fraction: float) -> int:
    """Map a per-item stage to overall queue progress."""
    safe_total = max(1, total)
    fraction = max(0.0, min(1.0, item_fraction))
    return max(1, min(95, int(((index + fraction) / safe_total) * 95)))


def _run_profile_optional_case_steps(
    db,
    *,
    job_id: str,
    item: dict,
    artifact: CaseArtifact,
    queue_items: list[dict],
    item_index: int,
    total_items: int,
    auto_enrich: bool,
    auto_asr: bool,
    auto_ocr: bool,
    auto_analyze: bool,
    reused: bool = False,
) -> None:
    if auto_enrich:
        if _case_has_enrichment_archive(artifact):
            item["enrichment_status"] = "success"
            item["enrichment_reused"] = True
        else:
            item["status"] = "enriching"
            item["message"] = "正在写入富化归档"
            _update_profile_queue_job(
                db,
                job_id,
                _profile_queue_total_progress(item_index, total_items, 0.72),
                item["message"],
                queue_items,
            )
            try:
                item["enrichment"] = build_enrichment_archive(
                    artifact,
                    capture_method="profile_build_queue_reuse" if reused else "profile_build_queue",
                    permission_note="local personal analysis",
                )
                item["enrichment_status"] = "success"
            except Exception as error:
                item["enrichment_status"] = "failed"
                item["enrichment_error"] = _optional_error_payload(error, ErrorCode.ENRICHMENT_FAILED)

    if auto_asr:
        if _case_has_asr(artifact):
            item["asr_status"] = "success"
            item["asr_reused"] = True
        else:
            item["status"] = "asr_optional"
            item["message"] = "正在执行可选 ASR"
            _update_profile_queue_job(
                db,
                job_id,
                _profile_queue_total_progress(item_index, total_items, 0.80),
                item["message"],
                queue_items,
            )
            try:
                item["asr"] = run_case_asr(artifact)
                item["asr_status"] = item["asr"].get("status") or "success"
            except AppError as error:
                item["asr_status"] = "provider_missing" if error.code == ErrorCode.ASR_PROVIDER_NOT_CONFIGURED else "failed"
                item["asr_error"] = error.as_dict()
            except Exception as error:
                item["asr_status"] = "failed"
                item["asr_error"] = _optional_error_payload(error, ErrorCode.ASR_FAILED)

    if auto_ocr:
        if _case_has_ocr(artifact):
            item["ocr_status"] = "success"
            item["ocr_reused"] = True
        else:
            item["status"] = "ocr_optional"
            item["message"] = "正在执行可选 OCR"
            _update_profile_queue_job(
                db,
                job_id,
                _profile_queue_total_progress(item_index, total_items, 0.88),
                item["message"],
                queue_items,
            )
            try:
                item["ocr"] = run_case_ocr(artifact)
                item["ocr_status"] = item["ocr"].get("status") or "success"
            except AppError as error:
                item["ocr_status"] = "provider_missing" if error.code == ErrorCode.OCR_PROVIDER_NOT_CONFIGURED else "failed"
                item["ocr_error"] = error.as_dict()
            except Exception as error:
                item["ocr_status"] = "failed"
                item["ocr_error"] = _optional_error_payload(error, ErrorCode.OCR_FAILED)

    if auto_analyze:
        if _case_has_ai_analysis(artifact):
            item["analysis_status"] = "success"
            item["analysis_reused"] = True
        else:
            item["status"] = "analyzing_optional"
            item["message"] = "正在执行可选 AI 拆解"
            _update_profile_queue_job(
                db,
                job_id,
                _profile_queue_total_progress(item_index, total_items, 0.94),
                item["message"],
                queue_items,
            )
            try:
                item["analysis"] = _analysis_result(analyze_case_artifact(artifact, mode="fast"))
                item["analysis_status"] = "success"
            except AppError as error:
                item["analysis_status"] = "skipped" if error.code == ErrorCode.LLM_NOT_CONFIGURED else "failed"
                item["analysis_error"] = error.as_dict()
            except Exception as error:
                item["analysis_status"] = "failed"
                item["analysis_error"] = _optional_error_payload(error, ErrorCode.AUTO_ANALYSIS_FAILED)
    else:
        item["analysis_status"] = "skipped"


def _profile_queue_item_from_payload(
    item: dict,
    *,
    index: int,
    selected_sample_ids: list[str],
    sample_lookup: dict,
    auto_enrich: bool,
    auto_asr: bool,
    auto_ocr: bool,
    auto_analyze: bool,
) -> dict:
    sample_id = str(item.get("sample_id") or (selected_sample_ids[index] if index < len(selected_sample_ids) else ""))
    sample = sample_lookup.get(sample_id)
    source_url = item.get("source_url") or getattr(sample, "source_url", "") or ""
    return {
        "aweme_id": str(item.get("aweme_id") or getattr(sample, "aweme_id", "") or ""),
        "sample_id": sample_id,
        "case_id": str(item.get("case_id") or getattr(sample, "case_id", "") or ""),
        "source_url": source_url,
        "title": item.get("title") or getattr(sample, "title", "") or "",
        "webpage_url": item.get("webpage_url") or source_url,
        "media_type": item.get("media_type") or getattr(sample, "media_type", "") or "unknown",
        "status": "pending",
        "message": "",
        "error_code": "",
        "local_video_id": "",
        "enrichment_status": "pending" if auto_enrich else "skipped",
        "asr_status": "pending" if auto_asr else "skipped",
        "ocr_status": "pending" if auto_ocr else "skipped",
        "analysis_status": "skipped" if not auto_analyze else "pending",
    }


def _run_profile_build_cases_job(job_id: str, payload: dict) -> None:
    raw_items = payload.get("items") or []
    auto_enrich = bool(payload.get("auto_enrich", True))
    auto_asr = bool(payload.get("auto_asr", True))
    auto_ocr = bool(payload.get("auto_ocr", True))
    auto_analyze = bool(payload.get("auto_analyze"))
    quality_preference = payload.get("quality_preference") or "best"
    sample_set_id = str(payload.get("sample_set_id") or "")
    selected_sample_ids = [str(value) for value in payload.get("selected_sample_ids") or [] if str(value)]
    completed_artifacts: list[CaseArtifact] = []
    sample_lookup = {}
    if sample_set_id:
        try:
            sample_lookup = {sample.sample_id: sample for sample in load_sample_set(sample_set_id).samples}
        except AppError:
            sample_lookup = {}
    queue_items = [
        _profile_queue_item_from_payload(
            item,
            index=index,
            selected_sample_ids=selected_sample_ids,
            sample_lookup=sample_lookup,
            auto_enrich=auto_enrich,
            auto_asr=auto_asr,
            auto_ocr=auto_ocr,
            auto_analyze=auto_analyze,
        )
        for index, item in enumerate(raw_items)
    ]
    def queue_result() -> dict:
        return _profile_queue_result(queue_items, sample_set_id=sample_set_id, selected_sample_ids=selected_sample_ids)

    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "running", 1, "素材包队列开始", result=queue_result())
            db.commit()

        total = max(1, len(queue_items))
        for index, item in enumerate(queue_items):
            if not _is_profile_queue_downloadable(item):
                item["status"] = "skipped"
                item["error_code"] = ErrorCode.UNSUPPORTED_PROFILE_ITEM
                item["message"] = "参考样本不执行视频下载，已保留为创作者蒸馏的元数据证据。"
                job = db.get(Job, job_id)
                if job:
                    _set_job(
                        job,
                        "running",
                        _profile_queue_total_progress(index, total, 1.0),
                        f"已保留参考样本 {index + 1}/{total}",
                        result=queue_result(),
                    )
                    db.commit()
                continue

            try:
                stored_item = db.get(DouyinVideoItem, item["aweme_id"])
                if not stored_item:
                    stored_item = DouyinVideoItem(aweme_id=item["aweme_id"])
                    db.add(stored_item)
                stored_item.title = item["title"] or stored_item.title or f"抖音作品 {item['aweme_id']}"
                stored_item.source_url = item["webpage_url"] or stored_item.source_url or f"https://www.douyin.com/video/{item['aweme_id']}"
                stored_item.video_url = stored_item.source_url
                db.commit()

                artifact = _find_reusable_profile_case(db, item)
                if artifact:
                    item["status"] = "reusing_case"
                    item["message"] = "已找到已有素材包，跳过下载和建包"
                    item["case_reused"] = True
                    item["local_video_id"] = artifact.local_video_id
                    item["case_id"] = artifact.case_id
                    item["case"] = _artifact_result(artifact)
                    completed_artifacts.append(artifact)
                    _update_profile_queue_job(
                        db,
                        job_id,
                        _profile_queue_total_progress(index, total, 0.25),
                        item["message"],
                        queue_items,
                    )
                    _run_profile_optional_case_steps(
                        db,
                        job_id=job_id,
                        item=item,
                        artifact=artifact,
                        queue_items=queue_items,
                        item_index=index,
                        total_items=total,
                        auto_enrich=auto_enrich,
                        auto_asr=auto_asr,
                        auto_ocr=auto_ocr,
                        auto_analyze=auto_analyze,
                        reused=True,
                    )
                    item["status"] = "completed"
                    item["message"] = "已复用已有素材包"
                    job = db.get(Job, job_id)
                    if job:
                        _set_job(
                            job,
                            "running",
                            min(98, int(((index + 1) / total) * 95)),
                            f"已处理 {index + 1}/{total}",
                            result=queue_result(),
                        )
                        db.commit()
                    continue

                item["status"] = "resolving"
                item["message"] = "正在解析清晰度候选"
                job = db.get(Job, job_id)
                if job:
                    _set_job(
                        job,
                        "running",
                        _profile_queue_total_progress(index, total, 0.12),
                        item["message"],
                        result=queue_result(),
                    )
                    db.commit()

                candidates = resolve_quality_candidates(db, item["aweme_id"])
                candidate = _choose_profile_queue_candidate(candidates, quality_preference)

                item["status"] = "downloading"
                item["message"] = "正在下载视频"
                job = db.get(Job, job_id)
                if job:
                    _set_job(
                        job,
                        "running",
                        _profile_queue_total_progress(index, total, 0.35),
                        item["message"],
                        result=queue_result(),
                    )
                    db.commit()

                download_result = download_candidate(db, item["aweme_id"], candidate["candidate_id"])
                item["local_video_id"] = download_result.get("local_video_id", "")

                item["status"] = "building_case"
                item["message"] = "正在生成素材包"
                job = db.get(Job, job_id)
                if job:
                    _set_job(
                        job,
                        "running",
                        _profile_queue_total_progress(index, total, 0.58),
                        item["message"],
                        result=queue_result(),
                    )
                    db.commit()

                artifact = build_case_from_local_video(db, item["local_video_id"])
                completed_artifacts.append(artifact)
                item["case_id"] = artifact.case_id
                item["case"] = _artifact_result(artifact)

                _run_profile_optional_case_steps(
                    db,
                    job_id=job_id,
                    item=item,
                    artifact=artifact,
                    queue_items=queue_items,
                    item_index=index,
                    total_items=total,
                    auto_enrich=auto_enrich,
                    auto_asr=auto_asr,
                    auto_ocr=auto_ocr,
                    auto_analyze=auto_analyze,
                    reused=False,
                )

                item["status"] = "completed"
                item["message"] = "素材包已生成"
            except AppError as error:
                item["status"] = "failed"
                item["error_code"] = error.code or ErrorCode.PROFILE_BUILD_ITEM_FAILED
                item["message"] = error.message
            except Exception as error:
                item["status"] = "failed"
                item["error_code"] = ErrorCode.PROFILE_BUILD_ITEM_FAILED
                item["message"] = str(error)[:300]

            job = db.get(Job, job_id)
            if job:
                _set_job(
                    job,
                    "running",
                    _profile_queue_total_progress(index, total, 1.0),
                    f"已处理 {index + 1}/{total}",
                    result=queue_result(),
                )
                db.commit()

        final_result = queue_result()
        updated_sample_set = None
        creator_intelligence = None
        if sample_set_id and selected_sample_ids:
            try:
                runtime_result = CreatorRuntimeEngine.dispatch_sample_set(
                    sample_set_id,
                    WorkflowAction.SELECT_SAMPLES,
                    selected_sample_ids=selected_sample_ids,
                )
                creator_intelligence = runtime_result.creator_intelligence
                updated_sample_set = runtime_result.sample_set
            except AppError as error:
                final_result["set_selection_error"] = error.as_dict()
        if sample_set_id and completed_artifacts:
            try:
                updated_sample_set = update_sample_set_with_case_artifacts(sample_set_id, completed_artifacts)
                if updated_sample_set.selected_sample_ids:
                    runtime_result = CreatorRuntimeEngine.dispatch_sample_set(
                        updated_sample_set.set_id,
                        WorkflowAction.SELECT_SAMPLES,
                        selected_sample_ids=updated_sample_set.selected_sample_ids,
                    )
                    creator_intelligence = runtime_result.creator_intelligence
                    updated_sample_set = runtime_result.sample_set
                else:
                    creator_intelligence = None
            except AppError as error:
                final_result["set_update_error"] = error.as_dict()
        if updated_sample_set:
            final_result["set"] = updated_sample_set.to_dict()
            final_result["creator_intelligence"] = creator_intelligence or creator_intelligence_payload_for_sample_set(updated_sample_set)
        counts = _profile_queue_counts(queue_items)
        job = db.get(Job, job_id)
        if job:
            _set_job(
                job,
                "success",
                100,
                f"队列完成：成功 {counts['completed_count']} 条，失败 {counts['failed_count']} 条，跳过 {counts['skipped_count']} 条",
                result=final_result,
            )
            db.commit()
    except Exception as error:
        job = db.get(Job, job_id)
        if job:
            message = str(error)[:500]
            result_payload = None
            if "sample_set" in locals():
                try:
                    runtime_result = CreatorRuntimeEngine.dispatch_sample_set(
                        sample_set.set_id,
                        WorkflowAction.MARK_EVIDENCE_READY,
                        job_state={
                            "status": "failed",
                            "error_code": ErrorCode.PROFILE_BUILD_ITEM_FAILED,
                            "message": message,
                            "job_id": job_id,
                            "batch": True,
                        },
                    )
                    result_payload = {
                        "ok": False,
                        "error_code": ErrorCode.PROFILE_BUILD_ITEM_FAILED,
                        "message": message,
                        "creator_intelligence": runtime_result.creator_intelligence,
                    }
                except Exception:
                    result_payload = None
            _set_job(job, "failed", job.progress, message, result=result_payload, error_code=ErrorCode.PROFILE_BUILD_ITEM_FAILED)
            db.commit()
    finally:
        db.close()


RECOVERABLE_DISTILL_ERROR_CODES = set(PROMPT_RECOVERY_LLM_ERROR_CODES)


def _inline_creator_clone_sample_set(payload: dict) -> CloneSampleSet:
    samples = [sample_from_dict(item) for item in payload.get("samples") or [] if isinstance(item, dict)]
    if not samples:
        raise AppError(ErrorCode.AWEME_ID_NOT_FOUND, "请先导入素材池并选择样本。")
    unique_samples, duplicate_count = dedupe_samples(samples)
    warnings = []
    if duplicate_count:
        warnings.append(f"已自动去重 {duplicate_count} 条重复素材。")
    sample_set = CloneSampleSet(
        set_id=f"clone_{uuid.uuid4().hex}",
        title=str(payload.get("title") or "创作者克隆实验室素材池"),
        creator_name=str(payload.get("creator_name") or ""),
        source_platform=str(payload.get("source_platform") or "unknown"),
        content_profile=normalize_content_profile(str(payload.get("content_profile") or "auto")),
        samples=unique_samples,
        warnings=warnings,
    )
    save_sample_set(sample_set)
    return sample_set


def _load_creator_clone_distill_set(payload: dict) -> CloneSampleSet:
    sample_set_id = str(payload.get("sample_set_id") or "")
    if sample_set_id:
        sample_set = load_sample_set(sample_set_id)
    else:
        sample_set = _inline_creator_clone_sample_set(payload)
    if "content_profile" in payload:
        sample_set.content_profile = normalize_content_profile(str(payload.get("content_profile") or "auto"))
        save_sample_set(sample_set)
    return sample_set


def _selected_clone_samples(sample_set: CloneSampleSet, selected_sample_ids: list[str]) -> list:
    requested = {str(value) for value in (selected_sample_ids or sample_set.selected_sample_ids or []) if str(value)}
    if requested:
        return [
            sample
            for sample in sample_set.samples
            if sample.sample_id in requested or sample.aweme_id in requested or sample.case_id in requested
        ]
    return list(sample_set.samples)


def _distill_phase_payload(phase: dict | None, *, execution_plan: dict | None = None, message: str = "") -> dict:
    phase = dict(phase or {})
    plan = phase.get("execution_plan") if isinstance(phase.get("execution_plan"), dict) else execution_plan or {}
    current_phase = str(phase.get("current_phase") or "running")
    labels = {
        "planning": "规划分批蒸馏",
        "batch_reduce": "分批大模型蒸馏",
        "final_reduce": "最终账号级汇总",
        "parse_persist": "解析并写入报告",
        "local_fallback": "本地降级汇总",
        "complete": "完成",
        "running": "运行中",
    }
    return {
        "kind": "creator_clone_distill",
        "current_phase": current_phase,
        "current_phase_label": phase.get("current_phase_label") or labels.get(current_phase, "运行中"),
        "message": message,
        "status": phase.get("status") or "running",
        "phase_index": phase.get("phase_index"),
        "phase_count": phase.get("phase_count"),
        "batch_id": phase.get("batch_id") or "",
        "batch_count": phase.get("batch_count") or plan.get("batch_count") or 0,
        "sample_count": phase.get("sample_count") or 0,
        "timeout_seconds": phase.get("timeout_seconds"),
        "total_budget_seconds": phase.get("total_budget_seconds") or phase.get("total_job_budget_seconds"),
        "elapsed_seconds": phase.get("elapsed_seconds"),
        "remaining_seconds": phase.get("remaining_seconds"),
        "attempt_index": phase.get("attempt_index"),
        "attempt_count": phase.get("attempt_count"),
        "http_attempt_index": phase.get("http_attempt_index"),
        "http_attempt_count": phase.get("http_attempt_count"),
        "response_format_fallback_used": bool(phase.get("response_format_fallback_used")),
        "retryable": phase.get("retryable"),
        "failure_class": phase.get("failure_class") or phase.get("error_code") or "",
        "budget_started_at": phase.get("budget_started_at") or "",
        "deadline_at": phase.get("deadline_at") or "",
        "retry_reason": phase.get("retry_reason") or "",
        "diagnostic": phase.get("diagnostic") or "",
        "execution_plan": plan,
    }


def _distill_fallback_message(error: AppError) -> str:
    if error.code == ErrorCode.LLM_RATE_LIMITED:
        return "网关限流，任务已停止；没有继续重试。已保留蒸馏 Prompt。"
    if error.code == ErrorCode.LLM_AUTH_FAILED:
        return "大模型鉴权失败，任务已停止；没有继续重试。已保留蒸馏 Prompt。"
    if error.code == ErrorCode.LLM_QUOTA_EXCEEDED:
        return "大模型额度不足，任务已停止；没有继续重试。已保留蒸馏 Prompt。"
    if error.code == ErrorCode.LLM_GATEWAY_TIMEOUT:
        return "大模型网关请求超时，已生成蒸馏 Prompt；可稍后重试，或在设置中增加等待时间。"
    return "大模型暂不可用，已生成蒸馏 Prompt"


def _run_creator_clone_distill_job(job_id: str, payload: dict) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "running", 5, "准备创作者蒸馏")
            db.commit()

        sample_set = _load_creator_clone_distill_set(payload)
        selected_sample_ids = [str(value) for value in payload.get("selected_sample_ids") or [] if str(value)]
        distill_mode = str(payload.get("distill_mode") or "quick")
        include_case_reports = bool(payload.get("include_case_reports", True))
        max_samples = int(payload.get("max_samples") or MAX_DISTILL_SAMPLES)
        selected_for_engine = selected_sample_ids or sample_set.selected_sample_ids or [sample.sample_id for sample in sample_set.samples]
        runtime_result = CreatorRuntimeEngine.dispatch_sample_set(
            sample_set.set_id,
            WorkflowAction.SELECT_SAMPLES,
            selected_sample_ids=selected_for_engine,
        )
        sample_set = runtime_result.sample_set or sample_set
        selected_samples = _selected_clone_samples(sample_set, selected_for_engine)
        llm_settings = effective_llm_settings()
        execution_plan = build_distill_execution_plan(
            selected_samples,
            batch_size=max_samples,
            single_timeout_seconds=float(llm_settings.get("timeout_seconds") or settings.llm_timeout_seconds),
            final_timeout_seconds=float(llm_settings.get("final_reduce_timeout_seconds") or settings.llm_final_reduce_timeout_seconds),
        )

        def progress(value: int, message: str, phase: dict | None = None) -> None:
            current = db.get(Job, job_id)
            if not current:
                return
            intelligence = creator_intelligence_payload_for_sample_set(sample_set)
            _set_job(
                current,
                "running",
                max(1, min(99, int(value))),
                message,
                result={
                    "set": sample_set.to_dict(),
                    "creator_intelligence": intelligence,
                    "execution_plan": execution_plan,
                    "distill_phase": _distill_phase_payload(phase, execution_plan=execution_plan, message=message),
                },
            )
            db.commit()

        job = db.get(Job, job_id)
        if job:
            _set_job(
                job,
                "running",
                25,
                f"已载入素材池，准备蒸馏 {len(selected_samples)} 条样本",
                result={
                    "set": sample_set.to_dict(),
                    "execution_plan": execution_plan,
                    "distill_phase": _distill_phase_payload(
                        {
                            "current_phase": "planning",
                            "current_phase_label": "准备单批蒸馏",
                            "phase_index": 1,
                            "phase_count": 3,
                            "execution_plan": execution_plan,
                        },
                        execution_plan=execution_plan,
                        message=f"已载入素材池，准备蒸馏 {len(selected_samples)} 条样本",
                    ),
                },
            )
            db.commit()

        try:
            job = db.get(Job, job_id)
            if job:
                intelligence = CreatorRuntimeEngine.dispatch_sample_set(
                    sample_set.set_id,
                    WorkflowAction.START_DISTILLATION,
                ).creator_intelligence
                _set_job(
                    job,
                    "running",
                    35,
                    "进入大模型蒸馏准备阶段",
                    result={
                        "set": sample_set.to_dict(),
                        "creator_intelligence": intelligence,
                        "execution_plan": execution_plan,
                        "distill_phase": _distill_phase_payload(
                            {
                                "current_phase": "distill_prepare",
                                "current_phase_label": "准备蒸馏",
                                "phase_index": 2,
                                "phase_count": 6,
                                "timeout_seconds": int(
                                    (execution_plan.get("timeout_policy") or {}).get("recommended_batch_timeout_seconds")
                                    or settings.llm_timeout_seconds
                                ),
                                "execution_plan": execution_plan,
                                "diagnostic": "接下来会生成 Prompt、调用大模型、解析结果并写入报告。",
                            },
                            execution_plan=execution_plan,
                            message="进入大模型蒸馏准备阶段",
                        ),
                    },
                )
                db.commit()
            result = distill_creator_clone(
                sample_set,
                selected_sample_ids,
                distill_mode=distill_mode,
                include_case_reports=include_case_reports,
                max_samples=max_samples,
                progress=progress,
            )
            job = db.get(Job, job_id)
            if job:
                result_execution_plan = result.get("execution_plan") or execution_plan
                runtime_result = CreatorRuntimeEngine.dispatch_sample_set(
                    sample_set.set_id,
                    WorkflowAction.COMPLETE_DISTILLATION,
                    strategy_output=(result.get("result") or {}).get("creator_clone_strategy") or {},
                    job_state={"status": "success", "message": "创作者蒸馏完成", "job_id": job_id},
                )
                intelligence = runtime_result.creator_intelligence
                intelligence["result"] = result.get("result") or {}
                _set_job(
                    job,
                    "success",
                    100,
                    "创作者蒸馏完成",
                    result={
                        "ok": True,
                        **result,
                        "creator_intelligence": intelligence,
                        "execution_plan": result_execution_plan,
                        "distill_phase": _distill_phase_payload(
                            {
                                "current_phase": "complete",
                                "current_phase_label": "完成",
                                "phase_index": 3,
                                "phase_count": 3,
                                "status": "success",
                                "execution_plan": result_execution_plan,
                            },
                            execution_plan=result_execution_plan,
                            message="创作者蒸馏完成",
                        ),
                    },
                )
                db.commit()
        except AppError as error:
            if error.code not in RECOVERABLE_DISTILL_ERROR_CODES:
                raise
            prompt_payload = prompt_only_result(
                sample_set,
                selected_sample_ids,
                distill_mode=distill_mode,
                include_case_reports=include_case_reports,
            )
            job = db.get(Job, job_id)
            if job:
                fallback_message = _distill_fallback_message(error)
                runtime_result = CreatorRuntimeEngine.dispatch_sample_set(
                    sample_set.set_id,
                    WorkflowAction.MARK_EVIDENCE_READY,
                    job_state={
                        "status": "prompt_only",
                        "recovery": "prompt_only",
                        "error_code": error.code,
                        "message": error.message,
                        "job_id": job_id,
                    },
                )
                intelligence = runtime_result.creator_intelligence
                intelligence["result"] = {}
                _set_job(
                    job,
                    "success",
                    100,
                    fallback_message,
                    result={
                        "ok": False,
                        "recovery": "prompt_only",
                        "error_code": error.code,
                        "message": error.message,
                        **prompt_payload,
                        "creator_intelligence": intelligence,
                        "execution_plan": execution_plan,
                        "distill_phase": _distill_phase_payload(
                            {
                                "current_phase": "local_fallback",
                                "current_phase_label": "降级为 Prompt",
                                "phase_index": 3,
                                "phase_count": 3,
                                "status": "fallback",
                                "error_code": error.code,
                                "failure_class": error.code,
                                **error.public_details(),
                                "execution_plan": execution_plan,
                            },
                            execution_plan=execution_plan,
                            message=fallback_message,
                        ),
                    },
                )
                db.commit()
    except AppError as error:
        job = db.get(Job, job_id)
        if job:
            result_payload = None
            if "sample_set" in locals():
                try:
                    runtime_result = CreatorRuntimeEngine.dispatch_sample_set(
                        sample_set.set_id,
                        WorkflowAction.MARK_EVIDENCE_READY,
                        job_state={
                            "status": "failed",
                            "error_code": error.code,
                            "message": error.message,
                            "job_id": job_id,
                        },
                    )
                    result_payload = {
                        "ok": False,
                        "error_code": error.code,
                        "message": error.message,
                        "creator_intelligence": runtime_result.creator_intelligence,
                    }
                except Exception:
                    result_payload = None
            _set_job(job, "failed", job.progress, error.message, result=result_payload, error_code=error.code)
            db.commit()
    except Exception as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "failed", job.progress, str(error)[:500], error_code=ErrorCode.CASE_BUILD_FAILED)
            db.commit()
    finally:
        db.close()


def _run_creator_clone_batch_distill_job(job_id: str, payload: dict) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "running", 5, "准备分批蒸馏")
            db.commit()

        sample_set = _load_creator_clone_distill_set(payload)
        selected_sample_ids = [str(value) for value in payload.get("selected_sample_ids") or [] if str(value)]
        distill_mode = str(payload.get("distill_mode") or "quick")
        batch_size = int(payload.get("batch_size") or MAX_DISTILL_SAMPLES)
        max_samples = int(payload.get("max_samples") or BATCH_DISTILL_MAX_SAMPLES)
        selected_for_engine = selected_sample_ids or sample_set.selected_sample_ids or [sample.sample_id for sample in sample_set.samples]
        runtime_result = CreatorRuntimeEngine.dispatch_sample_set(
            sample_set.set_id,
            WorkflowAction.SELECT_SAMPLES,
            selected_sample_ids=selected_for_engine,
        )
        sample_set = runtime_result.sample_set or sample_set
        selected_samples = _selected_clone_samples(sample_set, selected_for_engine)
        llm_settings = effective_llm_settings()
        execution_plan = build_distill_execution_plan(
            selected_samples,
            batch_size=batch_size,
            single_timeout_seconds=float(llm_settings.get("timeout_seconds") or settings.llm_timeout_seconds),
            final_timeout_seconds=float(llm_settings.get("final_reduce_timeout_seconds") or settings.llm_final_reduce_timeout_seconds),
        )

        def progress(value: int, message: str, phase: dict | None = None) -> None:
            current = db.get(Job, job_id)
            if current:
                _set_job(
                    current,
                    "running",
                    max(1, min(98, int(value))),
                    message,
                    result={
                        "set": sample_set.to_dict(),
                        "execution_plan": execution_plan,
                        "distill_phase": _distill_phase_payload(phase, execution_plan=execution_plan, message=message),
                    },
                )
                db.commit()

        progress(
            8,
            f"已载入素材池，准备分批蒸馏 {len(selected_samples)} 条样本",
            {
                "current_phase": "planning",
                "current_phase_label": "准备分批蒸馏",
                "phase_index": 0,
                "phase_count": execution_plan.get("batch_count", 0) + 2,
                "batch_count": execution_plan.get("batch_count", 0),
                "execution_plan": execution_plan,
            },
        )
        CreatorRuntimeEngine.dispatch_sample_set(sample_set.set_id, WorkflowAction.START_DISTILLATION)
        result = batch_distill_creator_clone(
            sample_set,
            selected_sample_ids,
            distill_mode=distill_mode,
            batch_size=batch_size,
            max_samples=max_samples,
            progress=progress,
        )
        job = db.get(Job, job_id)
        if job:
            batch_status = str((result.get("batch_distill") or {}).get("job_status") or "")
            message = {
                "completed": "分批蒸馏和总汇总完成",
                "partial": "部分批次已完成，已生成可用的本地汇总报告",
                "budget_exhausted": "总等待预算已耗尽，已保存成功批次和本地汇总报告",
                "rate_limited": "网关限流，任务已停止；没有继续重试。已保存成功批次",
                "auth_failed": "大模型鉴权失败，任务已停止；没有继续重试。已保存成功批次",
            }.get(
                batch_status,
                "分批蒸馏和总汇总完成" if result.get("result") else "已生成分批蒸馏 Prompt，等待可用大模型",
            )
            if result.get("result"):
                runtime_result = CreatorRuntimeEngine.dispatch_sample_set(
                    sample_set.set_id,
                    WorkflowAction.COMPLETE_DISTILLATION,
                    strategy_output=(result.get("result") or {}).get("creator_clone_strategy") or {},
                    job_state={
                        "status": "success",
                        "message": message,
                        "job_id": job_id,
                        "batch": True,
                    },
                )
                intelligence = runtime_result.creator_intelligence
                intelligence["result"] = result.get("result") or {}
            else:
                runtime_result = CreatorRuntimeEngine.dispatch_sample_set(
                    sample_set.set_id,
                    WorkflowAction.MARK_EVIDENCE_READY,
                    job_state={
                        "status": "prompt_only",
                        "recovery": "prompt_only",
                        "message": message,
                        "job_id": job_id,
                        "batch": True,
                    },
                )
                intelligence = runtime_result.creator_intelligence
                intelligence["result"] = {}
            _set_job(
                job,
                "success",
                100,
                message,
                result={
                    "ok": bool(result.get("result")),
                    **result,
                    "creator_intelligence": intelligence,
                    "execution_plan": result.get("execution_plan") or execution_plan,
                    "distill_phase": _distill_phase_payload(
                        {
                            "current_phase": "complete" if result.get("result") else "local_fallback",
                            "current_phase_label": "完成" if result.get("result") else "降级为 Prompt",
                            "status": batch_status or ("success" if result.get("result") else "fallback"),
                            "failure_class": result.get("error_code") or "",
                            "retryable": False if batch_status in {"rate_limited", "auth_failed", "budget_exhausted"} else None,
                            "execution_plan": result.get("execution_plan") or execution_plan,
                        },
                        execution_plan=result.get("execution_plan") or execution_plan,
                        message=message,
                    ),
                },
            )
            db.commit()
    except AppError as error:
        job = db.get(Job, job_id)
        if job:
            result_payload = None
            if "sample_set" in locals():
                try:
                    runtime_result = CreatorRuntimeEngine.dispatch_sample_set(
                        sample_set.set_id,
                        WorkflowAction.MARK_EVIDENCE_READY,
                        job_state={
                            "status": "failed",
                            "error_code": error.code,
                            "message": error.message,
                            "job_id": job_id,
                            "batch": True,
                        },
                    )
                    result_payload = {
                        "ok": False,
                        "error_code": error.code,
                        "message": error.message,
                        "creator_intelligence": runtime_result.creator_intelligence,
                    }
                except Exception:
                    result_payload = None
            _set_job(job, "failed", job.progress, error.message, result=result_payload, error_code=error.code)
            db.commit()
    except Exception as error:
        job = db.get(Job, job_id)
        if job:
            _set_job(job, "failed", job.progress, str(error)[:500], error_code=ErrorCode.PROFILE_BUILD_ITEM_FAILED)
            db.commit()
    finally:
        db.close()


def _create_job(job_type: str, message: str) -> Job:
    db = SessionLocal()
    try:
        job = Job(
            id=f"job_{uuid.uuid4().hex}",
            type=job_type,
            status="pending",
            progress=0,
            message=message,
            result_json="{}",
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job
    finally:
        db.close()


def _seed_job_result(job_id: str, result: dict) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return
        job.result_json = json.dumps(result, ensure_ascii=False)
        job.updated_at = utc_now()
        db.commit()
    finally:
        db.close()


def _seed_job_recovery_context(job_id: str, **context: str) -> None:
    values = {key: str(value) for key, value in context.items() if str(value or "").strip()}
    if values:
        _seed_job_result(job_id, {"recovery_context": values})


def _job_response_payload(job: Job) -> dict:
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "result_json": job.result(),
        "error_code": job.error_code,
        "created_at": job.created_at.isoformat() if job.created_at else "",
        "updated_at": job.updated_at.isoformat() if job.updated_at else "",
    }


@router.post("/build-case")
def create_build_case_job(payload: BuildCaseJobRequest, background_tasks: BackgroundTasks):
    job = _create_job("build-case", "等待生成素材包")
    _seed_job_recovery_context(job.id, local_video_id=payload.local_video_id)
    background_tasks.add_task(_run_build_case_job, job.id, payload.local_video_id)
    return {"ok": True, "job_id": job.id}


@router.get("/profile-build-cases/recent")
def get_recent_profile_build_cases_job(sample_set_id: str = ""):
    db = SessionLocal()
    try:
        jobs = (
            db.query(Job)
            .filter(Job.type == "profile-build-cases")
            .order_by(Job.updated_at.desc())
            .limit(20)
            .all()
        )
        for job in jobs:
            result = job.result()
            result_set_id = str((result.get("set") or {}).get("set_id") or "")
            if sample_set_id:
                if result_set_id and result_set_id != sample_set_id:
                    continue
                if not result_set_id and job.status not in {"pending", "running"}:
                    continue
            return {"ok": True, "job": _job_response_payload(job)}
        return error_response(AppError("JOB_NOT_FOUND", "没有找到最近的素材包队列。"), status_code=404)
    finally:
        db.close()


@router.get("/creator-clone-distill/recent")
def get_recent_creator_clone_distill_job(sample_set_id: str = ""):
    db = SessionLocal()
    try:
        jobs = (
            db.query(Job)
            .filter(Job.type.in_(["creator-clone-distill", "creator-clone-batch-distill"]))
            .filter(Job.status == "success")
            .order_by(Job.updated_at.desc())
            .limit(20)
            .all()
        )
        for job in jobs:
            result = job.result()
            result_set_id = str((result.get("set") or {}).get("set_id") or "")
            if sample_set_id and result_set_id != sample_set_id:
                continue
            if not result_set_id:
                continue
            return {"ok": True, "job": _job_response_payload(job)}
        return error_response(AppError("JOB_NOT_FOUND", "没有找到最近的创作者蒸馏报告。"), status_code=404)
    finally:
        db.close()


@router.get("/{job_id}")
def get_job(job_id: str):
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return error_response(AppError("JOB_NOT_FOUND", "任务不存在。"), status_code=404)
        return {"ok": True, "job": _job_response_payload(job)}
    finally:
        db.close()


@router.post("/profile-scan")
def profile_scan_job(payload: ProfileScanJobRequest, background_tasks: BackgroundTasks):
    job = _create_job("profile-scan", "等待扫描主页")
    background_tasks.add_task(
        _run_profile_scan_job,
        job.id,
        {
            "profile_url": payload.profile_url,
            "sec_user_id": payload.sec_user_id,
            "manual_links": payload.manual_links,
            "structured_items": payload.structured_items,
            "count": payload.count,
            "max_pages": payload.max_pages,
            "sort_by": payload.sort_by,
        },
    )
    return {"ok": True, "job_id": job.id}


@router.post("/profile-build-cases")
def profile_build_cases_job(payload: ProfileBuildCasesJobRequest, background_tasks: BackgroundTasks):
    queued_items = [item.model_dump() for item in payload.items]
    selected_sample_ids = list(dict.fromkeys(str(value) for value in payload.selected_sample_ids if str(value)))
    selected_count = len(selected_sample_ids) or len(queued_items)
    downloadable_count = sum(1 for item in queued_items if _is_profile_queue_downloadable(item))
    if not queued_items and not payload.selected_sample_ids:
        return error_response(AppError(ErrorCode.AWEME_ID_NOT_FOUND, f"请先从作品池选择 1-{settings.profile_build_max_items} 条作品。"))
    if downloadable_count > settings.profile_build_max_items:
        return error_response(
            AppError(
                ErrorCode.PROFILE_BUILD_QUEUE_LIMIT,
                f"当前自用版一次最多富化 {settings.profile_build_max_items} 条可下载视频，避免误批量下载。请减少选择数量后重试。",
            )
        )
    job = _create_job("profile-build-cases", "等待生成素材包队列")
    _seed_job_result(
        job.id,
        {
            "set": {"set_id": payload.sample_set_id} if payload.sample_set_id else {},
            "items": queued_items,
            "selected_sample_ids": selected_sample_ids,
            "pipeline_summary": {
                "selected_count": selected_count,
                "downloadable_count": downloadable_count,
                "reference_only_count": max(0, selected_count - downloadable_count),
                "notes": ["队列已创建，等待后台开始处理。"],
            },
        },
    )
    background_tasks.add_task(
        _run_profile_build_cases_job,
        job.id,
        {
            "items": queued_items,
            "selected_sample_ids": selected_sample_ids,
            "auto_enrich": payload.auto_enrich,
            "auto_asr": payload.auto_asr,
            "auto_ocr": payload.auto_ocr,
            "auto_analyze": payload.auto_analyze,
            "quality_preference": payload.quality_preference,
            "sample_set_id": payload.sample_set_id,
        },
    )
    return {
        "ok": True,
        "job_id": job.id,
        "selected_count": selected_count,
        "downloadable_count": downloadable_count,
        "reference_only_count": max(0, selected_count - downloadable_count),
        "queued_items": queued_items,
    }


@router.post("/creator-clone-distill")
def creator_clone_distill_job(payload: CreatorCloneDistillJobRequest, background_tasks: BackgroundTasks):
    selected_count = len([value for value in payload.selected_sample_ids if str(value)]) or len(payload.samples)
    if selected_count <= 0:
        return error_response(AppError(ErrorCode.AWEME_ID_NOT_FOUND, "请先导入素材池并选择样本。"))
    if selected_count > MAX_DISTILL_SAMPLES or payload.max_samples > MAX_DISTILL_SAMPLES:
        return error_response(
            AppError(
                ErrorCode.PROFILE_BUILD_QUEUE_LIMIT,
                f"当前自用版一次最多选择 {MAX_DISTILL_SAMPLES} 条样本进入蒸馏，避免上下文过长。请减少选择数量后重试。",
            )
        )
    job = _create_job("creator-clone-distill", "等待创作者克隆蒸馏")
    _seed_job_recovery_context(job.id, sample_set_id=payload.sample_set_id)
    background_tasks.add_task(_run_creator_clone_distill_job, job.id, payload.model_dump())
    return {"ok": True, "job_id": job.id, "selected_count": selected_count}


@router.post("/creator-clone-batch-distill")
def creator_clone_batch_distill_job(payload: CreatorCloneBatchDistillJobRequest, background_tasks: BackgroundTasks):
    selected_count = len([value for value in payload.selected_sample_ids if str(value)]) or len(payload.samples)
    if selected_count <= 0:
        return error_response(AppError(ErrorCode.AWEME_ID_NOT_FOUND, "请先导入素材池并选择样本。"))
    if selected_count > BATCH_DISTILL_MAX_SAMPLES or payload.max_samples > BATCH_DISTILL_MAX_SAMPLES:
        return error_response(
            AppError(
                ErrorCode.PROFILE_BUILD_QUEUE_LIMIT,
                f"当前分批蒸馏最多支持 {BATCH_DISTILL_MAX_SAMPLES} 条样本。请减少选择数量后重试。",
            )
        )
    batch_size = max(1, min(int(payload.batch_size or MAX_DISTILL_SAMPLES), MAX_DISTILL_SAMPLES))
    job = _create_job("creator-clone-batch-distill", "等待分批蒸馏")
    _seed_job_recovery_context(job.id, sample_set_id=payload.sample_set_id)
    background_tasks.add_task(_run_creator_clone_batch_distill_job, job.id, payload.model_dump())
    return {
        "ok": True,
        "job_id": job.id,
        "selected_count": selected_count,
        "batch_size": batch_size,
        "batch_count": (selected_count + batch_size - 1) // batch_size,
    }


@router.post("/resolve-qualities")
def resolve_qualities_job(payload: ResolveQualitiesJobRequest, background_tasks: BackgroundTasks):
    job = _create_job("resolve-qualities", "等待解析清晰度")
    if len(payload.aweme_ids) == 1:
        _seed_job_recovery_context(job.id, aweme_id=payload.aweme_ids[0])
    background_tasks.add_task(_run_resolve_qualities_job, job.id, payload.aweme_ids)
    return {"ok": True, "job_id": job.id}


@router.post("/download")
def download_job(payload: DownloadJobRequest, background_tasks: BackgroundTasks):
    job = _create_job("download", "等待下载")
    _seed_job_recovery_context(job.id, aweme_id=payload.aweme_id)
    background_tasks.add_task(_run_download_job, job.id, payload.aweme_id, payload.candidate_id)
    return {"ok": True, "job_id": job.id}


@router.post("/download-and-build-case")
def download_and_build_case_job(payload: DownloadJobRequest, background_tasks: BackgroundTasks):
    job = _create_job("download-and-build-case", "等待下载并生成素材包")
    _seed_job_recovery_context(job.id, aweme_id=payload.aweme_id)
    background_tasks.add_task(_run_download_and_build_case_job, job.id, payload.aweme_id, payload.candidate_id)
    return {"ok": True, "job_id": job.id}


@router.post("/analyze-case")
def analyze_case_job(payload: AnalyzeCaseJobRequest, background_tasks: BackgroundTasks):
    job = _create_job("analyze-case", "等待自动拆解")
    _seed_job_recovery_context(job.id, case_id=payload.case_id)
    background_tasks.add_task(_run_analyze_case_job, job.id, payload.case_id)
    return {"ok": True, "job_id": job.id}


@router.post("/enrich-case")
def enrich_case_job(payload: EnrichCaseJobRequest, background_tasks: BackgroundTasks):
    job = _create_job("enrich-case", "等待富化归档")
    _seed_job_recovery_context(job.id, case_id=payload.case_id)
    background_tasks.add_task(_run_enrich_case_job, job.id, payload.case_id)
    return {"ok": True, "job_id": job.id}


@router.post("/asr-case")
def asr_case_job(payload: AsrCaseJobRequest, background_tasks: BackgroundTasks):
    job = _create_job("asr-case", "等待语音识别")
    _seed_job_recovery_context(job.id, case_id=payload.case_id)
    background_tasks.add_task(_run_asr_case_job, job.id, payload.case_id)
    return {"ok": True, "job_id": job.id}


@router.post("/ocr-case")
def ocr_case_job(payload: OcrCaseJobRequest, background_tasks: BackgroundTasks):
    job = _create_job("ocr-case", "等待画面文字识别")
    _seed_job_recovery_context(job.id, case_id=payload.case_id)
    background_tasks.add_task(_run_ocr_case_job, job.id, payload.case_id)
    return {"ok": True, "job_id": job.id}


@router.post("/download-build-analyze-case")
def download_build_analyze_case_job(payload: DownloadJobRequest, background_tasks: BackgroundTasks):
    job = _create_job("download-build-analyze-case", "等待下载、生成素材包并自动拆解")
    _seed_job_recovery_context(job.id, aweme_id=payload.aweme_id)
    background_tasks.add_task(_run_download_build_analyze_case_job, job.id, payload.aweme_id, payload.candidate_id)
    return {"ok": True, "job_id": job.id}
