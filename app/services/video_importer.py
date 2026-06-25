from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import AppError, ErrorCode
from app.models import LocalVideoItem


ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}


def engagement_score(like_count: int, comment_count: int, share_count: int) -> int:
    return max(0, like_count) + max(0, comment_count) * 5 + max(0, share_count) * 8


def _safe_int(value: int | str | None) -> int:
    if value is None or value == "":
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _validate_video_upload(upload: UploadFile) -> str:
    filename = upload.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_VIDEO_EXTENSIONS:
        raise AppError(ErrorCode.INVALID_VIDEO_FILE)
    return suffix


def save_local_video(
    db: Session,
    upload: UploadFile,
    title: str,
    source_url: str = "",
    author: str = "",
    like_count: int | str | None = 0,
    comment_count: int | str | None = 0,
    share_count: int | str | None = 0,
    create_time: str = "",
    remark: str = "",
) -> LocalVideoItem:
    try:
        suffix = _validate_video_upload(upload)
        local_video_id = f"local_{uuid.uuid4().hex}"
        destination = settings.uploads_dir / f"{local_video_id}{suffix}"
        settings.uploads_dir.mkdir(parents=True, exist_ok=True)

        with destination.open("wb") as target:
            shutil.copyfileobj(upload.file, target)

        if destination.stat().st_size <= 0:
            destination.unlink(missing_ok=True)
            raise AppError(ErrorCode.INVALID_VIDEO_FILE)

        likes = _safe_int(like_count)
        comments = _safe_int(comment_count)
        shares = _safe_int(share_count)
        item = LocalVideoItem(
            local_video_id=local_video_id,
            title=(title or "未命名视频").strip()[:300],
            file_path=str(destination),
            source_url=(source_url or "").strip(),
            author=(author or "").strip()[:200],
            like_count=likes,
            comment_count=comments,
            share_count=shares,
            engagement_score=engagement_score(likes, comments, shares),
            create_time=(create_time or "").strip()[:64],
            remark=(remark or "").strip(),
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item
    except AppError:
        raise
    except Exception as error:
        raise AppError(ErrorCode.LOCAL_UPLOAD_FAILED, str(error)[:500]) from error

