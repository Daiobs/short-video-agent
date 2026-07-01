from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Platform(StrEnum):
    DOUYIN = "douyin"
    XHS = "xhs"
    BILI = "bili"
    LOCAL = "local"
    MANUAL = "manual"
    UNKNOWN = "unknown"


class MediaKind(StrEnum):
    VIDEO = "video"
    IMAGE = "image"
    MIXED = "mixed"
    TEXT = "text"
    UNKNOWN = "unknown"


class EvidenceLevel(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    METADATA_ONLY = "metadata_only"


@dataclass(frozen=True)
class SampleMetrics:
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    collect_count: int = 0
    view_count: int = 0

    @property
    def engagement_score(self) -> int:
        return int(self.like_count or 0) + int(self.comment_count or 0) * 5 + int(self.share_count or 0) * 8

    def to_dict(self) -> dict[str, int]:
        return {
            "like_count": int(self.like_count or 0),
            "comment_count": int(self.comment_count or 0),
            "share_count": int(self.share_count or 0),
            "collect_count": int(self.collect_count or 0),
            "view_count": int(self.view_count or 0),
            "engagement_score": self.engagement_score,
        }


@dataclass(frozen=True)
class Evidence:
    level: EvidenceLevel = EvidenceLevel.METADATA_ONLY
    has_video: bool = False
    has_frames: bool = False
    has_asr: bool = False
    has_ocr: bool = False
    has_comments: bool = False
    enrichment_status: str = "pending"
    asr_status: str = "pending"
    ocr_status: str = "pending"
    analysis_status: str = "not_analyzed"

    @property
    def ready_for_distillation(self) -> bool:
        return self.level in {EvidenceLevel.FULL, EvidenceLevel.PARTIAL} or any(
            [self.has_frames, self.has_asr, self.has_ocr, self.has_comments]
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "has_video": self.has_video,
            "has_frames": self.has_frames,
            "has_asr": self.has_asr,
            "has_ocr": self.has_ocr,
            "has_comments": self.has_comments,
            "enrichment_status": self.enrichment_status,
            "asr_status": self.asr_status,
            "ocr_status": self.ocr_status,
            "analysis_status": self.analysis_status,
            "ready_for_distillation": self.ready_for_distillation,
        }


@dataclass(frozen=True)
class CreatorProfile:
    creator_id: str
    display_name: str = ""
    platform: Platform = Platform.UNKNOWN
    source_url: str = ""
    bio: str = ""
    audience: str = ""
    content_direction: str = ""
    style_bias: str = ""
    raw_profile: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "creator_id": self.creator_id,
            "display_name": self.display_name,
            "platform": self.platform.value,
            "source_url": self.source_url,
            "bio": self.bio,
            "audience": self.audience,
            "content_direction": self.content_direction,
            "style_bias": self.style_bias,
            "raw_profile": dict(self.raw_profile),
        }


@dataclass(frozen=True)
class CreatorSample:
    sample_id: str
    source: Platform = Platform.UNKNOWN
    source_url: str = ""
    platform_item_id: str = ""
    title: str = ""
    description: str = ""
    author: str = ""
    cover_url: str = ""
    media_kind: MediaKind = MediaKind.UNKNOWN
    metrics: SampleMetrics = field(default_factory=SampleMetrics)
    evidence: Evidence = field(default_factory=Evidence)
    case_id: str = ""
    tags: tuple[str, ...] = ()
    created_at: str = ""
    selected: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "source": self.source.value,
            "source_url": self.source_url,
            "platform_item_id": self.platform_item_id,
            "title": self.title,
            "description": self.description,
            "author": self.author,
            "cover_url": self.cover_url,
            "media_kind": self.media_kind.value,
            "metrics": self.metrics.to_dict(),
            "evidence": self.evidence.to_dict(),
            "case_id": self.case_id,
            "tags": list(self.tags),
            "created_at": self.created_at,
            "selected": self.selected,
            "raw": dict(self.raw),
        }


@dataclass(frozen=True)
class CreatorProject:
    project_id: str
    title: str = ""
    profile: CreatorProfile = field(default_factory=lambda: CreatorProfile(creator_id="unknown"))
    samples: tuple[CreatorSample, ...] = ()
    selected_sample_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    @property
    def selected_samples(self) -> tuple[CreatorSample, ...]:
        selected = set(self.selected_sample_ids)
        if not selected:
            return tuple(sample for sample in self.samples if sample.selected)
        return tuple(sample for sample in self.samples if sample.sample_id in selected)

    @property
    def sample_count(self) -> int:
        return len(self.samples)

    @property
    def selected_count(self) -> int:
        return len(self.selected_samples)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "profile": self.profile.to_dict(),
            "samples": [sample.to_dict() for sample in self.samples],
            "selected_sample_ids": list(self.selected_sample_ids),
            "warnings": list(self.warnings),
            "sample_count": self.sample_count,
            "selected_count": self.selected_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class BehaviorRepresentation:
    project_id: str
    profile: CreatorProfile
    sample_count: int
    selected_count: int
    evidence_matrix: dict[str, Any]
    performance_segments: dict[str, list[dict[str, Any]]]
    media_mix: dict[str, int]
    constraints: tuple[str, ...] = ()
    generated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "profile": self.profile.to_dict(),
            "sample_count": self.sample_count,
            "selected_count": self.selected_count,
            "evidence_matrix": dict(self.evidence_matrix),
            "performance_segments": self.performance_segments,
            "media_mix": dict(self.media_mix),
            "constraints": list(self.constraints),
            "generated_at": self.generated_at,
        }


@dataclass(frozen=True)
class CreatorCloneStrategy:
    positioning: str = ""
    content_strategy: tuple[str, ...] = ()
    hooks: tuple[str, ...] = ()
    templates: tuple[dict[str, Any], ...] = ()
    anti_patterns: tuple[str, ...] = ()
    idea_bank: tuple[dict[str, Any], ...] = ()
    validation_rules: tuple[str, ...] = ()

    @classmethod
    def empty_schema(cls) -> dict[str, Any]:
        return {
            "positioning": "",
            "content_strategy": [],
            "hooks": [],
            "templates": [],
            "anti_patterns": [],
            "idea_bank": [],
            "validation_rules": [],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "positioning": self.positioning,
            "content_strategy": list(self.content_strategy),
            "hooks": list(self.hooks),
            "templates": [dict(item) for item in self.templates],
            "anti_patterns": list(self.anti_patterns),
            "idea_bank": [dict(item) for item in self.idea_bank],
            "validation_rules": list(self.validation_rules),
        }
