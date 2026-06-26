from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from app.database import SessionLocal
from app.errors import AppError, ErrorCode
from app.models import CaseArtifact, Job, utc_now
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
    count: int = 20
    max_pages: int = 1
    sort_by: str = "like_count"


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
            _set_job(job, "failed", job.progress, str(error)[:500], error_code=ErrorCode.CASE_BUILD_FAILED)
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
            _set_job(job, "success", 100, "自动拆解完成", result=_analysis_result(result))
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
            _set_job(job, "success", 100, "富化归档完成", result=result)
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


@router.post("/build-case")
def create_build_case_job(payload: BuildCaseJobRequest, background_tasks: BackgroundTasks):
    job = _create_job("build-case", "等待生成素材包")
    background_tasks.add_task(_run_build_case_job, job.id, payload.local_video_id)
    return {"ok": True, "job_id": job.id}


@router.get("/{job_id}")
def get_job(job_id: str):
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return error_response(AppError("JOB_NOT_FOUND", "任务不存在。"), status_code=404)
        return {
            "ok": True,
            "job": {
                "id": job.id,
                "type": job.type,
                "status": job.status,
                "progress": job.progress,
                "message": job.message,
                "result_json": job.result(),
                "error_code": job.error_code,
                "created_at": job.created_at.isoformat() if job.created_at else "",
                "updated_at": job.updated_at.isoformat() if job.updated_at else "",
            },
        }
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
            "count": payload.count,
            "max_pages": payload.max_pages,
            "sort_by": payload.sort_by,
        },
    )
    return {"ok": True, "job_id": job.id}


@router.post("/resolve-qualities")
def resolve_qualities_job(payload: ResolveQualitiesJobRequest, background_tasks: BackgroundTasks):
    job = _create_job("resolve-qualities", "等待解析清晰度")
    background_tasks.add_task(_run_resolve_qualities_job, job.id, payload.aweme_ids)
    return {"ok": True, "job_id": job.id}


@router.post("/download")
def download_job(payload: DownloadJobRequest, background_tasks: BackgroundTasks):
    job = _create_job("download", "等待下载")
    background_tasks.add_task(_run_download_job, job.id, payload.aweme_id, payload.candidate_id)
    return {"ok": True, "job_id": job.id}


@router.post("/download-and-build-case")
def download_and_build_case_job(payload: DownloadJobRequest, background_tasks: BackgroundTasks):
    job = _create_job("download-and-build-case", "等待下载并生成素材包")
    background_tasks.add_task(_run_download_and_build_case_job, job.id, payload.aweme_id, payload.candidate_id)
    return {"ok": True, "job_id": job.id}


@router.post("/analyze-case")
def analyze_case_job(payload: AnalyzeCaseJobRequest, background_tasks: BackgroundTasks):
    job = _create_job("analyze-case", "等待自动拆解")
    background_tasks.add_task(_run_analyze_case_job, job.id, payload.case_id)
    return {"ok": True, "job_id": job.id}


@router.post("/enrich-case")
def enrich_case_job(payload: EnrichCaseJobRequest, background_tasks: BackgroundTasks):
    job = _create_job("enrich-case", "等待富化归档")
    background_tasks.add_task(_run_enrich_case_job, job.id, payload.case_id)
    return {"ok": True, "job_id": job.id}


@router.post("/asr-case")
def asr_case_job(payload: AsrCaseJobRequest, background_tasks: BackgroundTasks):
    job = _create_job("asr-case", "等待语音识别")
    background_tasks.add_task(_run_asr_case_job, job.id, payload.case_id)
    return {"ok": True, "job_id": job.id}


@router.post("/ocr-case")
def ocr_case_job(payload: OcrCaseJobRequest, background_tasks: BackgroundTasks):
    job = _create_job("ocr-case", "等待画面文字识别")
    background_tasks.add_task(_run_ocr_case_job, job.id, payload.case_id)
    return {"ok": True, "job_id": job.id}


@router.post("/download-build-analyze-case")
def download_build_analyze_case_job(payload: DownloadJobRequest, background_tasks: BackgroundTasks):
    job = _create_job("download-build-analyze-case", "等待下载、生成素材包并自动拆解")
    background_tasks.add_task(_run_download_build_analyze_case_job, job.id, payload.aweme_id, payload.candidate_id)
    return {"ok": True, "job_id": job.id}
