from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import AppError
from app.routes.common import error_response
from app.services.douyin_importer import import_single_aweme, serialize_aweme
from app.services.douyin_url_parser import extract_aweme_id
from app.services.quality_resolver import resolve_quality_candidates
from app.services.video_importer import save_local_video


router = APIRouter(prefix="/api", tags=["videos"])


class ImportSingleRequest(BaseModel):
    value: str


class ResolveQualitiesRequest(BaseModel):
    aweme_ids: list[str]


@router.post("/import/local-video")
def import_local_video(
    video_file: UploadFile = File(...),
    title: str = Form(""),
    source_url: str = Form(""),
    author: str = Form(""),
    like_count: int = Form(0),
    comment_count: int = Form(0),
    share_count: int = Form(0),
    create_time: str = Form(""),
    remark: str = Form(""),
    db: Session = Depends(get_db),
):
    try:
        item = save_local_video(
            db=db,
            upload=video_file,
            title=title,
            source_url=source_url,
            author=author,
            like_count=like_count,
            comment_count=comment_count,
            share_count=share_count,
            create_time=create_time,
            remark=remark,
        )
        return {
            "ok": True,
            "local_video": {
                "local_video_id": item.local_video_id,
                "title": item.title,
                "source_url": item.source_url,
                "author": item.author,
                "like_count": item.like_count,
                "comment_count": item.comment_count,
                "share_count": item.share_count,
                "engagement_score": item.engagement_score,
                "create_time": item.create_time,
                "remark": item.remark,
            },
        }
    except AppError as error:
        return error_response(error)


@router.post("/videos/import-single")
def import_single_video(payload: ImportSingleRequest, db: Session = Depends(get_db)):
    try:
        item = import_single_aweme(db, payload.value)
        return {"ok": True, "video": serialize_aweme(item)}
    except AppError as error:
        return error_response(error)


@router.post("/videos/qualities")
def resolve_qualities(payload: ResolveQualitiesRequest, db: Session = Depends(get_db)):
    try:
        results = {}
        for value in payload.aweme_ids:
            aweme_id = extract_aweme_id(value)
            results[aweme_id] = resolve_quality_candidates(db, aweme_id)
        return {"ok": True, "results": results}
    except AppError as error:
        return error_response(error)
