from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LocalVideoItem(Base):
    __tablename__ = "local_video_items"

    local_video_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    author: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    share_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    engagement_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    create_time: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    remark: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DouyinVideoItem(Base):
    __tablename__ = "douyin_video_items"

    aweme_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    cover_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    share_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    engagement_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    create_time: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    video_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    author: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    source_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class VideoQualityCandidate(Base):
    __tablename__ = "video_quality_candidates"

    candidate_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    aweme_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    quality_label: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bitrate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    host: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    object_key: Mapped[str] = mapped_column(Text, default="", nullable=False)
    expires_at: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CaseArtifact(Base):
    __tablename__ = "case_artifacts"

    case_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    aweme_id: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    local_video_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    video_path: Mapped[str] = mapped_column(Text, default="", nullable=False)
    metadata_path: Mapped[str] = mapped_column(Text, default="", nullable=False)
    qualities_path: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ffprobe_path: Mapped[str] = mapped_column(Text, default="", nullable=False)
    analysis_input_path: Mapped[str] = mapped_column(Text, default="", nullable=False)
    prompt_path: Mapped[str] = mapped_column(Text, default="", nullable=False)
    contact_sheet_path: Mapped[str] = mapped_column(Text, default="", nullable=False)
    keyframes_dir: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="success", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    result_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    error_code: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    def result(self) -> dict:
        try:
            return json.loads(self.result_json or "{}")
        except json.JSONDecodeError:
            return {}

