from __future__ import annotations

from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import DouyinVideoItem
from app.services.douyin_url_parser import extract_aweme_id, extract_first_url


def import_single_aweme(db: Session, value: str) -> DouyinVideoItem:
    aweme_id = extract_aweme_id(value)
    source_url = extract_first_url(value) or f"https://www.douyin.com/video/{aweme_id}"
    item = db.get(DouyinVideoItem, aweme_id)
    if not item:
        item = DouyinVideoItem(
            aweme_id=aweme_id,
            title=f"抖音作品 {aweme_id}",
            source_url=source_url,
            video_url=source_url,
        )
        db.add(item)
    else:
        item.source_url = item.source_url or source_url
        item.video_url = item.video_url or source_url
    db.commit()
    db.refresh(item)
    return item


def serialize_aweme(item: DouyinVideoItem) -> dict:
    return {
        "aweme_id": item.aweme_id,
        "title": item.title,
        "cover_url": item.cover_url,
        "like_count": item.like_count,
        "comment_count": item.comment_count,
        "share_count": item.share_count,
        "engagement_score": item.engagement_score,
        "create_time": item.create_time,
        "video_url": item.video_url,
        "author": item.author,
        "source_url": item.source_url,
    }

