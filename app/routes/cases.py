from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import AppError, ErrorCode
from app.models import CaseArtifact
from app.routes.common import error_response
from app.services.analysis_taxonomy import (
    BASE_ANALYSIS_FOCUS,
    build_analysis_context,
    build_prompt,
    infer_content_category,
    list_analysis_profiles,
)
from app.services.analysis_worksheet import (
    build_default_worksheet,
    normalize_worksheet,
    render_analysis_brief,
)
from app.services.auto_analyzer import existing_auto_analysis
from app.services.case_builder import build_case_from_local_video


router = APIRouter(prefix="/api/cases", tags=["cases"])


class BuildCaseRequest(BaseModel):
    local_video_id: str


class UpdateAnalysisCategoryRequest(BaseModel):
    category_id: str


class UpdateWorksheetRequest(BaseModel):
    worksheet: dict


def _case_or_error(db: Session, case_id: str) -> CaseArtifact:
    artifact = db.get(CaseArtifact, case_id)
    if not artifact:
        raise AppError(ErrorCode.CASE_BUILD_FAILED, "素材包不存在。")
    return artifact


def _read_json_file(path: str) -> dict:
    file_path = Path(path)
    if not file_path.is_file():
        raise AppError(ErrorCode.CASE_BUILD_FAILED, f"素材包文件缺失：{file_path.name}")
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise AppError(ErrorCode.CASE_BUILD_FAILED, f"素材包 JSON 无法读取：{file_path.name}") from error


def _read_text_file(path: str) -> str:
    file_path = Path(path)
    if not file_path.is_file():
        raise AppError(ErrorCode.CASE_BUILD_FAILED, f"素材包文件缺失：{file_path.name}")
    return file_path.read_text(encoding="utf-8")


def _write_json_file(path: str, payload: dict | list) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _case_dir(artifact: CaseArtifact) -> Path:
    return Path(artifact.prompt_path).parent


def _worksheet_path(artifact: CaseArtifact) -> Path:
    return _case_dir(artifact) / "worksheet.json"


def _analysis_brief_path(artifact: CaseArtifact) -> Path:
    return _case_dir(artifact) / "analysis_brief.md"


def _analysis_result_path(artifact: CaseArtifact) -> Path:
    return _case_dir(artifact) / "analysis_result.json"


def _analysis_report_path(artifact: CaseArtifact) -> Path:
    return _case_dir(artifact) / "analysis_report.md"


def _infer_case_category(metadata: dict, analysis_input: dict) -> str:
    existing = (
        analysis_input.get("content_category")
        or metadata.get("content_category")
        or analysis_input.get("analysis_context", {}).get("category_id")
    )
    if existing:
        return str(existing)
    return infer_content_category(
        " ".join(
            [
                str(metadata.get("title") or ""),
                str(metadata.get("notes") or ""),
                str(metadata.get("author") or ""),
                str(metadata.get("source_url") or ""),
            ]
        )
    )


def _apply_analysis_context(metadata: dict, analysis_input: dict, category_id: str) -> tuple[dict, dict]:
    analysis_context = build_analysis_context(category_id)
    metadata["content_category"] = analysis_context["category_id"]
    metadata["content_category_label"] = analysis_context["label"]
    analysis_input["content_category"] = analysis_context["category_id"]
    analysis_input["content_category_label"] = analysis_context["label"]
    analysis_input["analysis_context"] = analysis_context
    analysis_input["analysis_lens"] = analysis_context["analysis_lens"]
    analysis_input["key_questions"] = analysis_context["key_questions"]
    analysis_input["content_ratio"] = analysis_context["content_ratio"]
    analysis_input.setdefault("analysis_focus", list(BASE_ANALYSIS_FOCUS))
    return metadata, analysis_input


def _load_case_parts(artifact: CaseArtifact) -> tuple[dict, dict, dict, str]:
    metadata = _read_json_file(artifact.metadata_path)
    ffprobe = _read_json_file(artifact.ffprobe_path)
    analysis_input = _read_json_file(artifact.analysis_input_path)
    category_id = _infer_case_category(metadata, analysis_input)
    metadata, analysis_input = _apply_analysis_context(metadata, analysis_input, category_id)
    prompt = _read_text_file(artifact.prompt_path)
    if "## 2. 本类型优先分析镜头" not in prompt:
        prompt = build_prompt(metadata, ffprobe, analysis_input["analysis_context"])
    return metadata, ffprobe, analysis_input, prompt


def _load_or_create_worksheet(artifact: CaseArtifact, metadata: dict, ffprobe: dict, analysis_input: dict) -> tuple[dict, str]:
    worksheet_file = _worksheet_path(artifact)
    existing = None
    if worksheet_file.is_file():
        existing = json.loads(worksheet_file.read_text(encoding="utf-8"))
    worksheet = normalize_worksheet(artifact.case_id, analysis_input, None, existing=existing)
    brief = render_analysis_brief(metadata, ffprobe, analysis_input, worksheet)
    _write_json_file(str(worksheet_file), worksheet)
    _analysis_brief_path(artifact).write_text(brief, encoding="utf-8")
    return worksheet, brief


def _update_case_category(artifact: CaseArtifact, category_id: str) -> None:
    metadata = _read_json_file(artifact.metadata_path)
    ffprobe = _read_json_file(artifact.ffprobe_path)
    analysis_input = _read_json_file(artifact.analysis_input_path)
    metadata, analysis_input = _apply_analysis_context(metadata, analysis_input, category_id)
    _write_json_file(artifact.metadata_path, metadata)
    _write_json_file(artifact.analysis_input_path, analysis_input)
    Path(artifact.prompt_path).write_text(
        build_prompt(metadata, ffprobe, analysis_input["analysis_context"]),
        encoding="utf-8",
    )
    _load_or_create_worksheet(artifact, metadata, ffprobe, analysis_input)


def _update_case_worksheet(artifact: CaseArtifact, payload: dict) -> None:
    metadata, ffprobe, analysis_input, _prompt = _load_case_parts(artifact)
    existing = None
    worksheet_file = _worksheet_path(artifact)
    if worksheet_file.is_file():
        existing = json.loads(worksheet_file.read_text(encoding="utf-8"))
    worksheet = normalize_worksheet(artifact.case_id, analysis_input, payload, existing=existing)
    _write_json_file(str(worksheet_file), worksheet)
    _analysis_brief_path(artifact).write_text(
        render_analysis_brief(metadata, ffprobe, analysis_input, worksheet),
        encoding="utf-8",
    )


def _case_payload(artifact: CaseArtifact) -> dict:
    case_id = artifact.case_id
    metadata, ffprobe, analysis_input, prompt = _load_case_parts(artifact)
    worksheet, analysis_brief = _load_or_create_worksheet(artifact, metadata, ffprobe, analysis_input)
    analysis_result, analysis_report = existing_auto_analysis(artifact)
    keyframes_dir = Path(artifact.keyframes_dir)
    keyframe_files = []
    if keyframes_dir.is_dir():
        keyframe_files = sorted(path.name for path in keyframes_dir.glob("frame_*.jpg") if path.is_file())
    return {
        "case_id": case_id,
        "local_video_id": artifact.local_video_id,
        "status": artifact.status,
        "paths": {
            "video": artifact.video_path,
            "metadata": artifact.metadata_path,
            "qualities": artifact.qualities_path,
            "ffprobe": artifact.ffprobe_path,
            "analysis_input": artifact.analysis_input_path,
            "prompt": artifact.prompt_path,
            "worksheet": str(_worksheet_path(artifact)),
            "analysis_brief": str(_analysis_brief_path(artifact)),
            "analysis_result": str(_analysis_result_path(artifact)),
            "analysis_report": str(_analysis_report_path(artifact)),
            "contact_sheet": artifact.contact_sheet_path,
            "keyframes_dir": artifact.keyframes_dir,
        },
        "artifact_urls": {
            "contact_sheet": f"/api/cases/{case_id}/contact-sheet",
            "keyframes": [
                {
                    "filename": filename,
                    "url": f"/api/cases/{case_id}/keyframes/{filename}",
                }
                for filename in keyframe_files
            ],
        },
        "analysis_profiles": list_analysis_profiles(),
        "metadata": metadata,
        "qualities": _read_json_file(artifact.qualities_path),
        "ffprobe": ffprobe,
        "analysis_input": analysis_input,
        "worksheet": worksheet,
        "analysis_brief": analysis_brief,
        "analysis_result": analysis_result,
        "analysis_report": analysis_report,
        "prompt": prompt,
    }


@router.post("/build")
def build_case_sync(payload: BuildCaseRequest, db: Session = Depends(get_db)):
    try:
        artifact = build_case_from_local_video(db, payload.local_video_id)
        return {
            "ok": True,
            "case": {
                "case_id": artifact.case_id,
                "local_video_id": artifact.local_video_id,
                "video_path": artifact.video_path,
                "metadata_path": artifact.metadata_path,
                "analysis_input_path": artifact.analysis_input_path,
                "prompt_path": artifact.prompt_path,
                "contact_sheet_path": artifact.contact_sheet_path,
                "keyframes_dir": artifact.keyframes_dir,
                "status": artifact.status,
            },
        }
    except AppError as error:
        return error_response(error)


@router.get("/{case_id}")
def get_case(case_id: str, db: Session = Depends(get_db)):
    try:
        artifact = _case_or_error(db, case_id)
        return {"ok": True, "case": _case_payload(artifact)}
    except AppError as error:
        return error_response(error)


@router.post("/{case_id}/analysis-category")
def update_case_analysis_category(
    case_id: str,
    payload: UpdateAnalysisCategoryRequest,
    db: Session = Depends(get_db),
):
    try:
        artifact = _case_or_error(db, case_id)
        _update_case_category(artifact, payload.category_id)
        return {"ok": True, "case": _case_payload(artifact)}
    except AppError as error:
        return error_response(error)


@router.post("/{case_id}/worksheet")
def update_case_worksheet(
    case_id: str,
    payload: UpdateWorksheetRequest,
    db: Session = Depends(get_db),
):
    try:
        artifact = _case_or_error(db, case_id)
        _update_case_worksheet(artifact, payload.worksheet)
        return {"ok": True, "case": _case_payload(artifact)}
    except AppError as error:
        return error_response(error)


@router.get("/{case_id}/contact-sheet")
def get_case_contact_sheet(case_id: str, db: Session = Depends(get_db)):
    try:
        artifact = _case_or_error(db, case_id)
        path = Path(artifact.contact_sheet_path)
        if not path.is_file():
            raise AppError(ErrorCode.CASE_BUILD_FAILED, "关键帧总览图不存在。")
        return FileResponse(path, media_type="image/jpeg")
    except AppError as error:
        return error_response(error)


@router.get("/{case_id}/keyframes/{filename}")
def get_case_keyframe(case_id: str, filename: str, db: Session = Depends(get_db)):
    try:
        if "/" in filename or "\\" in filename or not filename.startswith("frame_") or not filename.endswith(".jpg"):
            raise AppError(ErrorCode.CASE_BUILD_FAILED, "关键帧文件名无效。")
        artifact = _case_or_error(db, case_id)
        path = Path(artifact.keyframes_dir) / filename
        if not path.is_file():
            raise AppError(ErrorCode.CASE_BUILD_FAILED, "关键帧不存在。")
        return FileResponse(path, media_type="image/jpeg")
    except AppError as error:
        return error_response(error)
