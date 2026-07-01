from __future__ import annotations

from typing import Any

from app.services.creator_intelligence.models import (
    CreatorProfile,
    CreatorProject,
    CreatorSample,
    Evidence,
    EvidenceLevel,
    MediaKind,
    Platform,
    SampleMetrics,
)


def normalize_platform(value: str) -> Platform:
    candidate = (value or "unknown").strip().lower()
    aliases = {"rednote": "xhs", "xiaohongshu": "xhs", "bilibili": "bili"}
    candidate = aliases.get(candidate, candidate)
    return Platform(candidate) if candidate in Platform._value2member_map_ else Platform.UNKNOWN


def normalize_media_kind(value: str) -> MediaKind:
    candidate = (value or "unknown").strip().lower()
    aliases = {"photo": "image", "note": "image", "image_post": "image", "图文": "image", "照片": "image"}
    candidate = aliases.get(candidate, candidate)
    return MediaKind(candidate) if candidate in MediaKind._value2member_map_ else MediaKind.UNKNOWN


def normalize_evidence_level(value: str) -> EvidenceLevel:
    candidate = (value or "metadata_only").strip().lower().replace("-", "_")
    return EvidenceLevel(candidate) if candidate in EvidenceLevel._value2member_map_ else EvidenceLevel.METADATA_ONLY


def sample_from_clone_sample(sample: Any) -> CreatorSample:
    return CreatorSample(
        sample_id=str(getattr(sample, "sample_id", "") or getattr(sample, "aweme_id", "") or getattr(sample, "case_id", "") or "sample"),
        source=normalize_platform(str(getattr(sample, "source_type", "") or "unknown")),
        source_url=str(getattr(sample, "source_url", "") or ""),
        platform_item_id=str(getattr(sample, "aweme_id", "") or ""),
        title=str(getattr(sample, "title", "") or ""),
        description=str(getattr(sample, "desc", "") or ""),
        author=str(getattr(sample, "author", "") or ""),
        cover_url=str(getattr(sample, "cover_url", "") or ""),
        media_kind=normalize_media_kind(str(getattr(sample, "media_type", "") or "unknown")),
        metrics=SampleMetrics(
            like_count=int(getattr(sample, "like_count", 0) or 0),
            comment_count=int(getattr(sample, "comment_count", 0) or 0),
            share_count=int(getattr(sample, "share_count", 0) or 0),
            collect_count=int(getattr(sample, "collect_count", 0) or 0),
            view_count=int(getattr(sample, "view_count", 0) or 0),
        ),
        evidence=Evidence(
            level=normalize_evidence_level(str(getattr(sample, "understanding_level", "") or "metadata_only")),
            has_video=bool(getattr(sample, "has_video", False)),
            has_frames=bool(getattr(sample, "has_frames", False)),
            has_asr=bool(getattr(sample, "has_asr", False)),
            has_ocr=bool(getattr(sample, "has_ocr", False)),
            has_comments=bool(getattr(sample, "has_comments", False)),
            enrichment_status=str(getattr(sample, "enrichment_status", "") or "pending"),
            asr_status=str(getattr(sample, "asr_status", "") or "pending"),
            ocr_status=str(getattr(sample, "ocr_status", "") or "pending"),
            analysis_status=str(getattr(sample, "analysis_status", "") or "not_analyzed"),
        ),
        case_id=str(getattr(sample, "case_id", "") or ""),
        tags=tuple(str(item) for item in (getattr(sample, "tags", None) or []) if str(item)),
        created_at=str(getattr(sample, "create_time", "") or ""),
        selected=bool(getattr(sample, "selected", False)),
        raw=sample.to_dict() if hasattr(sample, "to_dict") else {},
    )


def profile_from_clone_sample_set(sample_set: Any) -> CreatorProfile:
    metadata = getattr(sample_set, "profile_metadata", None) or {}
    creator_id = (
        str(metadata.get("sec_user_id") or "")
        or str(getattr(sample_set, "creator_name", "") or "")
        or str(getattr(sample_set, "set_id", "") or "unknown")
    )
    return CreatorProfile(
        creator_id=creator_id,
        display_name=str(getattr(sample_set, "creator_name", "") or metadata.get("nickname") or metadata.get("name") or ""),
        platform=normalize_platform(str(getattr(sample_set, "source_platform", "") or metadata.get("source_platform") or "unknown")),
        source_url=str(metadata.get("profile_url") or metadata.get("source_url") or ""),
        bio=str(metadata.get("bio") or metadata.get("signature") or ""),
        raw_profile=dict(metadata),
    )


def project_from_clone_sample_set(sample_set: Any) -> CreatorProject:
    samples = tuple(sample_from_clone_sample(sample) for sample in (getattr(sample_set, "samples", None) or []))
    return CreatorProject(
        project_id=str(getattr(sample_set, "set_id", "") or "project"),
        title=str(getattr(sample_set, "title", "") or ""),
        profile=profile_from_clone_sample_set(sample_set),
        samples=samples,
        selected_sample_ids=tuple(str(item) for item in (getattr(sample_set, "selected_sample_ids", None) or []) if str(item)),
        warnings=tuple(str(item) for item in (getattr(sample_set, "warnings", None) or []) if str(item)),
        created_at=str(getattr(sample_set, "created_at", "") or ""),
    )


def project_from_clone_selection(sample_set: Any, selected_samples: list[Any]) -> CreatorProject:
    samples = tuple(sample_from_clone_sample(sample) for sample in selected_samples)
    return CreatorProject(
        project_id=str(getattr(sample_set, "set_id", "") or "project"),
        title=str(getattr(sample_set, "title", "") or ""),
        profile=profile_from_clone_sample_set(sample_set),
        samples=samples,
        selected_sample_ids=tuple(sample.sample_id for sample in samples),
        warnings=tuple(str(item) for item in (getattr(sample_set, "warnings", None) or []) if str(item)),
        created_at=str(getattr(sample_set, "created_at", "") or ""),
    )
