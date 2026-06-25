from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import AppError
from app.routes.common import error_response
from app.services.downloader import download_candidate


router = APIRouter(prefix="/api", tags=["downloads"])


class DownloadRequest(BaseModel):
    aweme_id: str
    candidate_id: str


@router.post("/downloads")
def download_video(payload: DownloadRequest, db: Session = Depends(get_db)):
    try:
        result = download_candidate(db, payload.aweme_id, payload.candidate_id)
        return {"ok": True, "download": result}
    except AppError as error:
        return error_response(error)
