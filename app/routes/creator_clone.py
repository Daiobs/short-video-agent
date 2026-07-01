from __future__ import annotations

import json
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import AppError, ErrorCode
from app.routes.common import error_response
from app.services.creator_clone import (
    MAX_DISTILL_SAMPLES,
    build_sample_set,
    build_sample_set_from_handoff_manifest,
    creator_clone_dir,
    distill_creator_clone,
    export_paths,
    load_sample_set,
    normalize_content_profile,
    prompt_only_result,
    sample_from_dict,
    save_sample_set,
)
from app.services.creator_intelligence import (
    WorkflowEngine,
    WorkflowState,
    build_behavior_representation,
    project_from_clone_sample_set,
)
from app.services.local_chrome import load_capture_audit, load_handoff_manifest, local_helper_security_contract


router = APIRouter(prefix="/api/creator-clone", tags=["creator-clone"])
HANDOFF_TOKEN_TTL_SECONDS = 120
_HANDOFF_TOKENS: dict[str, float] = {}
RECOVERABLE_DISTILL_ERROR_CODES = {
    ErrorCode.LLM_NOT_CONFIGURED,
    ErrorCode.LLM_REQUEST_FAILED,
    ErrorCode.LLM_RESPONSE_INVALID,
}


class CreatorCloneImportRequest(BaseModel):
    title: str = ""
    creator_name: str = ""
    source_platform: str = "douyin"
    profile_url: str = ""
    sec_user_id: str = ""
    manual_links: str = ""
    structured_items: str = ""
    case_ids: str = ""
    count: int = 20
    max_pages: int = 1
    sort_by: str = "engagement_score"


class CreatorCloneDistillRequest(BaseModel):
    sample_set_id: str = ""
    samples: list[dict] = Field(default_factory=list)
    selected_sample_ids: list[str] = Field(default_factory=list)
    distill_mode: str = "quick"
    include_case_reports: bool = True
    max_samples: int = MAX_DISTILL_SAMPLES
    title: str = ""
    creator_name: str = ""
    source_platform: str = "unknown"
    content_profile: str = "auto"


class CreatorCloneHandoffImportRequest(BaseModel):
    handoff_manifest: dict = Field(default_factory=dict)
    handoff_token: str = ""


def _cleanup_handoff_tokens() -> None:
    now = time.time()
    expired = [token for token, expires_at in _HANDOFF_TOKENS.items() if expires_at < now]
    for token in expired:
        _HANDOFF_TOKENS.pop(token, None)


def _issue_handoff_token() -> str:
    token = secrets.token_urlsafe(24)
    _HANDOFF_TOKENS[token] = time.time() + HANDOFF_TOKEN_TTL_SECONDS
    _cleanup_handoff_tokens()
    return token


def _consume_handoff_token(token: str) -> None:
    _cleanup_handoff_tokens()
    expires_at = _HANDOFF_TOKENS.pop(token or "", 0)
    if not expires_at or expires_at < time.time():
        raise AppError(ErrorCode.HANDOFF_TOKEN_INVALID)


@router.post("/import")
def import_creator_clone_samples(payload: CreatorCloneImportRequest, db: Session = Depends(get_db)):
    try:
        sample_set = build_sample_set(
            db=db,
            title=payload.title,
            creator_name=payload.creator_name,
            source_platform=payload.source_platform,
            profile_url=payload.profile_url,
            sec_user_id=payload.sec_user_id,
            manual_links=payload.manual_links,
            structured_items=payload.structured_items,
            case_ids=payload.case_ids,
            count=payload.count,
            max_pages=payload.max_pages,
            sort_by=payload.sort_by,
        )
        return {"ok": True, "set": sample_set.to_dict(), "exports": export_paths(sample_set.set_id)}
    except AppError as error:
        return error_response(error)


@router.post("/handoff-token")
def creator_clone_handoff_token():
    return {
        "ok": True,
        "token": _issue_handoff_token(),
        "expires_in_seconds": HANDOFF_TOKEN_TTL_SECONDS,
        "security_contract": local_helper_security_contract(),
        "handoff_scope": {
            "intended_receiver": "analysis_web_app",
            "contains": ["creator metadata", "sample metadata", "visible engagement metrics", "source work URLs"],
            "excludes": ["Cookie", "login token", "authorization header", "signed media URL", "raw request headers"],
        },
    }


def load_creator_strategy_output(set_id: str) -> dict:
    result_path = creator_clone_dir(set_id) / "creator_clone_result.json"
    if not result_path.is_file():
        return {}
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    strategy = payload.get("creator_clone_strategy") if isinstance(payload, dict) else {}
    return strategy if isinstance(strategy, dict) else {}


def creator_intelligence_payload(sample_set, strategy_output: dict | None = None) -> dict:
    project = project_from_clone_sample_set(sample_set)
    engine = WorkflowEngine.from_project(project)
    strategy = strategy_output if isinstance(strategy_output, dict) else load_creator_strategy_output(sample_set.set_id)
    if strategy:
        engine.strategy_output = strategy
        engine.state = WorkflowState.DONE
        engine.message = "Creator strategy output ready."
    payload = {"workflow": engine.get_state().to_dict()}
    if project.selected_samples:
        payload["behavior_model"] = build_behavior_representation(project).to_dict()
    if strategy:
        payload["strategy_output"] = strategy
    return payload


@router.post("/import-handoff")
def import_creator_clone_handoff(payload: CreatorCloneHandoffImportRequest):
    try:
        _consume_handoff_token(payload.handoff_token)
        sample_set = build_sample_set_from_handoff_manifest(payload.handoff_manifest)
        return {
            "ok": True,
            "set": sample_set.to_dict(),
            "exports": export_paths(sample_set.set_id),
            "security_contract": local_helper_security_contract(),
        }
    except AppError as error:
        return error_response(error)


@router.get("/sets/{set_id}")
def get_creator_clone_set(set_id: str):
    try:
        sample_set = load_sample_set(set_id)
        result_path = creator_clone_dir(set_id) / "creator_clone_result.json"
        prompt_path = creator_clone_dir(set_id) / "distill_prompt.md"
        return {
            "ok": True,
            "set": sample_set.to_dict(),
            "has_result": result_path.is_file(),
            "has_prompt": prompt_path.is_file(),
            "creator_intelligence": creator_intelligence_payload(sample_set),
            "capture_audit": load_capture_audit(set_id),
            "handoff_manifest": load_handoff_manifest(set_id),
            "exports": export_paths(set_id),
        }
    except AppError as error:
        return error_response(error)


@router.post("/distill")
def distill_creator_clone_endpoint(payload: CreatorCloneDistillRequest):
    try:
        if payload.sample_set_id:
            sample_set = load_sample_set(payload.sample_set_id)
            sample_set.content_profile = normalize_content_profile(payload.content_profile)
        else:
            samples = [sample_from_dict(item) for item in payload.samples if isinstance(item, dict)]
            if not samples:
                raise AppError(ErrorCode.AWEME_ID_NOT_FOUND, "请先导入素材池并选择样本。")
            sample_set = build_sample_set_from_inline(
                samples,
                title=payload.title,
                creator_name=payload.creator_name,
                source_platform=payload.source_platform,
                content_profile=payload.content_profile,
            )
        save_sample_set(sample_set)

        try:
            result = distill_creator_clone(
                sample_set,
                payload.selected_sample_ids,
                distill_mode=payload.distill_mode,
                include_case_reports=payload.include_case_reports,
                max_samples=payload.max_samples,
            )
            return {
                "ok": True,
                **result,
                "creator_intelligence": creator_intelligence_payload(sample_set, (result.get("result") or {}).get("creator_clone_strategy")),
            }
        except AppError as error:
            if error.code not in RECOVERABLE_DISTILL_ERROR_CODES:
                raise
            prompt_payload = prompt_only_result(
                sample_set,
                payload.selected_sample_ids,
                distill_mode=payload.distill_mode,
                include_case_reports=payload.include_case_reports,
            )
            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "error_code": error.code,
                    "message": error.message,
                    "recovery": "prompt_only",
                    **prompt_payload,
                },
            )
    except AppError as error:
        return error_response(error)


@router.get("/sets/{set_id}/files/{filename}")
def download_creator_clone_file(set_id: str, filename: str):
    allowed = {
        "samples.json",
        "handoff_manifest.json",
        "distill_prompt.md",
        "creator_clone_result.json",
        "creator_clone.md",
    }
    if filename not in allowed:
        return error_response(AppError(ErrorCode.HOST_NOT_ALLOWED, "不允许下载该文件。"))
    if filename == "handoff_manifest.json":
        load_handoff_manifest(set_id)
    file_path = creator_clone_dir(set_id) / filename
    if not file_path.is_file():
        return error_response(AppError(ErrorCode.CASE_BUILD_FAILED, "文件尚未生成。"), status_code=404)
    media_type = "application/json" if file_path.suffix == ".json" else "text/markdown; charset=utf-8"
    return FileResponse(file_path, media_type=media_type, filename=filename)


def build_sample_set_from_inline(
    samples: list,
    title: str = "",
    creator_name: str = "",
    source_platform: str = "unknown",
    content_profile: str = "auto",
):
    from app.services.creator_clone import CloneSampleSet, dedupe_samples, save_sample_set
    import uuid

    unique_samples, duplicate_count = dedupe_samples(samples)
    warnings = []
    if duplicate_count:
        warnings.append(f"已自动去重 {duplicate_count} 条重复素材。")
    sample_set = CloneSampleSet(
        set_id=f"clone_{uuid.uuid4().hex}",
        title=title or "创作者克隆实验室素材池",
        creator_name=creator_name,
        source_platform=source_platform,
        content_profile=normalize_content_profile(content_profile),
        samples=unique_samples,
        warnings=warnings,
    )
    save_sample_set(sample_set)
    return sample_set
