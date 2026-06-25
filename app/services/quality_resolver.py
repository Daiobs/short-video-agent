from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import AppError, ErrorCode
from app.models import DouyinVideoItem, VideoQualityCandidate
from app.providers.base import VideoQualityCandidateDTO
from app.providers.douyin_web import DouyinWebProvider
from app.services.candidate_probe import get_cached_host_latency, rank_fastest_equivalent_candidates
from app.services.video_importer import engagement_score


def _candidate_expired(candidate: VideoQualityCandidate) -> bool:
    now = int(time.time())
    if candidate.expires_at and candidate.expires_at <= now + 30:
        return True
    created_at = candidate.created_at
    if not created_at:
        return True
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at.timestamp() + settings.quality_cache_ttl_seconds <= now


def _public_candidate(candidate: VideoQualityCandidate) -> dict:
    return {
        "candidate_id": candidate.candidate_id,
        "aweme_id": candidate.aweme_id,
        "quality_label": candidate.quality_label,
        "size_bytes": candidate.size_bytes,
        "bitrate": candidate.bitrate,
        "host": candidate.host,
        "object_key": candidate.object_key,
        "expires_at": candidate.expires_at,
        "source": candidate.source,
    }


def _public_candidate_dto(candidate: VideoQualityCandidateDTO) -> dict:
    return {
        "candidate_id": candidate.candidate_id,
        "aweme_id": candidate.aweme_id,
        "quality_label": candidate.quality_label,
        "size_bytes": candidate.size_bytes,
        "bitrate": candidate.bitrate,
        "host": candidate.host,
        "object_key": candidate.object_key,
        "expires_at": candidate.expires_at,
        "source": candidate.source,
    }


def _cached_candidate_sort_key(candidate: VideoQualityCandidate) -> tuple[int, int, int, float, str]:
    source_priority = 1
    if ".bit_rate." in candidate.source:
        source_priority = 3
    elif ".play_addr" in candidate.source:
        source_priority = 2
    latency = get_cached_host_latency(candidate.host)
    latency_score = -latency if latency is not None else -9999.0
    return (source_priority, candidate.bitrate, candidate.size_bytes, latency_score, candidate.quality_label)


def _save_candidates(db: Session, aweme_id: str, candidates: list[VideoQualityCandidateDTO]) -> None:
    db.execute(delete(VideoQualityCandidate).where(VideoQualityCandidate.aweme_id == aweme_id))
    for item in candidates:
        db.add(
            VideoQualityCandidate(
                candidate_id=item.candidate_id,
                aweme_id=item.aweme_id,
                quality_label=item.quality_label,
                url=item.url,
                size_bytes=item.size_bytes,
                bitrate=item.bitrate,
                host=item.host,
                object_key=item.object_key,
                expires_at=item.expires_at,
                source=item.source,
                created_at=datetime.now(timezone.utc),
            )
        )
    db.commit()


def _save_aweme_metadata(db: Session, metadata: dict) -> None:
    aweme_id = metadata.get("aweme_id") or ""
    if not aweme_id:
        return
    item = db.get(DouyinVideoItem, aweme_id)
    if not item:
        item = DouyinVideoItem(aweme_id=aweme_id)
        db.add(item)
    item.title = metadata.get("title") or item.title or f"抖音作品 {aweme_id}"
    item.author = metadata.get("author") or item.author
    item.cover_url = metadata.get("cover_url") or item.cover_url
    item.source_url = metadata.get("source_url") or item.source_url or f"https://www.douyin.com/video/{aweme_id}"
    item.video_url = item.source_url
    item.like_count = int(metadata.get("like_count") or item.like_count or 0)
    item.comment_count = int(metadata.get("comment_count") or item.comment_count or 0)
    item.share_count = int(metadata.get("share_count") or item.share_count or 0)
    item.engagement_score = engagement_score(item.like_count, item.comment_count, item.share_count)
    item.create_time = metadata.get("create_time") or item.create_time


def resolve_quality_candidates(db: Session, aweme_id: str, provider: DouyinWebProvider | None = None) -> list[dict]:
    cached = list(
        db.scalars(
            select(VideoQualityCandidate)
            .where(VideoQualityCandidate.aweme_id == aweme_id)
        )
    )
    if cached and not all(_candidate_expired(candidate) for candidate in cached):
        valid_cached = [candidate for candidate in cached if not _candidate_expired(candidate)]
        valid_cached.sort(key=_cached_candidate_sort_key, reverse=True)
        return [_public_candidate(candidate) for candidate in valid_cached]

    provider = provider or DouyinWebProvider()
    aweme = db.get(DouyinVideoItem, aweme_id)
    source_urls = [aweme.source_url] if aweme and aweme.source_url else []
    metadata, candidates = provider.resolve(aweme_id, source_urls=source_urls)
    if not candidates:
        raise AppError(ErrorCode.QUALITY_NOT_FOUND)
    candidates = rank_fastest_equivalent_candidates(candidates)
    _save_aweme_metadata(db, metadata)
    _save_candidates(db, aweme_id, candidates)
    return [_public_candidate_dto(candidate) for candidate in candidates]


def get_candidate_or_error(db: Session, aweme_id: str, candidate_id: str) -> VideoQualityCandidate:
    candidate = db.get(VideoQualityCandidate, candidate_id)
    if not candidate or candidate.aweme_id != aweme_id:
        raise AppError(ErrorCode.QUALITY_NOT_FOUND)
    if _candidate_expired(candidate):
        db.delete(candidate)
        db.commit()
        raise AppError(ErrorCode.URL_EXPIRED)
    return candidate
