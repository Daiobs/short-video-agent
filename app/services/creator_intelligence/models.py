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
            "evidence_level": self.level.value,
            "has_video": self.has_video,
            "has_frames": self.has_frames,
            "has_asr": self.has_asr,
            "has_ocr": self.has_ocr,
            "has_comments": self.has_comments,
            "metadata_enriched": self.enrichment_status == "success",
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
            "id": self.creator_id,
            "name": self.display_name,
            "source": self.platform.value,
            "metadata": dict(self.raw_profile),
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
            "id": self.sample_id,
            "source_type": self.source.value,
            "aweme_id": self.platform_item_id,
            "media_type": self.media_kind.value,
            "evidence_level": self.evidence.level.value,
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
    recommendation_meta: dict[str, Any] = field(default_factory=dict)
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
            "id": self.project_id,
            "project_id": self.project_id,
            "title": self.title,
            "profile": self.profile.to_dict(),
            "samples": [sample.to_dict() for sample in self.samples],
            "selected_sample_ids": list(self.selected_sample_ids),
            "recommendation_meta": dict(self.recommendation_meta),
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
    behavior_patterns: dict[str, Any] = field(default_factory=dict)
    content_structures: dict[str, Any] = field(default_factory=dict)
    structure_patterns: dict[str, Any] = field(default_factory=dict)
    hook_patterns: dict[str, Any] = field(default_factory=dict)
    risk_patterns: dict[str, Any] = field(default_factory=dict)
    evolution_signals: dict[str, Any] = field(default_factory=dict)
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
            "behavior_patterns": dict(self.behavior_patterns),
            "content_structures": dict(self.content_structures),
            "structure_patterns": dict(self.structure_patterns or self.content_structures),
            "hook_patterns": dict(self.hook_patterns),
            "risk_patterns": dict(self.risk_patterns),
            "anti_patterns": dict(self.risk_patterns),
            "evolution_signals": dict(self.evolution_signals),
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


def _enum_value(enum_cls, value, fallback):
    try:
        return enum_cls(value)
    except Exception:
        return fallback


def sample_metrics_from_dict(value: dict[str, Any] | None) -> SampleMetrics:
    payload = value if isinstance(value, dict) else {}
    return SampleMetrics(
        like_count=int(payload.get("like_count") or 0),
        comment_count=int(payload.get("comment_count") or 0),
        share_count=int(payload.get("share_count") or 0),
        collect_count=int(payload.get("collect_count") or 0),
        view_count=int(payload.get("view_count") or 0),
    )


def evidence_from_dict(value: dict[str, Any] | None) -> Evidence:
    payload = value if isinstance(value, dict) else {}
    level = payload.get("level") or payload.get("evidence_level")
    return Evidence(
        level=_enum_value(EvidenceLevel, level, EvidenceLevel.METADATA_ONLY),
        has_video=bool(payload.get("has_video")),
        has_frames=bool(payload.get("has_frames") or payload.get("has_keyframes")),
        has_asr=bool(payload.get("has_asr") or payload.get("has_asr_text")),
        has_ocr=bool(payload.get("has_ocr") or payload.get("has_ocr_text")),
        has_comments=bool(payload.get("has_comments")),
        enrichment_status=str(payload.get("enrichment_status") or "pending"),
        asr_status=str(payload.get("asr_status") or "pending"),
        ocr_status=str(payload.get("ocr_status") or "pending"),
        analysis_status=str(payload.get("analysis_status") or "not_analyzed"),
    )


def creator_profile_from_dict(value: dict[str, Any] | None) -> CreatorProfile:
    payload = value if isinstance(value, dict) else {}
    creator_id = str(payload.get("creator_id") or payload.get("id") or "unknown")
    return CreatorProfile(
        creator_id=creator_id,
        display_name=str(payload.get("display_name") or payload.get("name") or ""),
        platform=_enum_value(Platform, payload.get("platform") or payload.get("source"), Platform.UNKNOWN),
        source_url=str(payload.get("source_url") or ""),
        bio=str(payload.get("bio") or ""),
        audience=str(payload.get("audience") or ""),
        content_direction=str(payload.get("content_direction") or ""),
        style_bias=str(payload.get("style_bias") or ""),
        raw_profile=dict(payload.get("raw_profile") or payload.get("metadata") or {}),
    )


def creator_sample_from_dict(value: dict[str, Any] | None) -> CreatorSample:
    payload = value if isinstance(value, dict) else {}
    evidence_payload = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else payload
    return CreatorSample(
        sample_id=str(payload.get("sample_id") or payload.get("id") or ""),
        source=_enum_value(Platform, payload.get("source") or payload.get("source_type"), Platform.UNKNOWN),
        source_url=str(payload.get("source_url") or ""),
        platform_item_id=str(payload.get("platform_item_id") or payload.get("aweme_id") or ""),
        title=str(payload.get("title") or ""),
        description=str(payload.get("description") or ""),
        author=str(payload.get("author") or ""),
        cover_url=str(payload.get("cover_url") or ""),
        media_kind=_enum_value(MediaKind, payload.get("media_kind") or payload.get("media_type"), MediaKind.UNKNOWN),
        metrics=sample_metrics_from_dict(payload.get("metrics") if isinstance(payload.get("metrics"), dict) else payload),
        evidence=evidence_from_dict(evidence_payload),
        case_id=str(payload.get("case_id") or ""),
        tags=tuple(str(item) for item in (payload.get("tags") or []) if str(item)),
        created_at=str(payload.get("created_at") or ""),
        selected=bool(payload.get("selected")),
        raw=dict(payload.get("raw") or {}),
    )


def creator_project_from_dict(value: dict[str, Any] | None) -> CreatorProject:
    payload = value if isinstance(value, dict) else {}
    samples = tuple(
        creator_sample_from_dict(item)
        for item in (payload.get("samples") or [])
        if isinstance(item, dict)
    )
    selected = tuple(str(item) for item in (payload.get("selected_sample_ids") or []) if str(item))
    return CreatorProject(
        project_id=str(payload.get("project_id") or payload.get("id") or "unknown_project"),
        title=str(payload.get("title") or ""),
        profile=creator_profile_from_dict(payload.get("profile") if isinstance(payload.get("profile"), dict) else {}),
        samples=samples,
        selected_sample_ids=selected,
        warnings=tuple(str(item) for item in (payload.get("warnings") or []) if str(item)),
        recommendation_meta=dict(payload.get("recommendation_meta") or {}),
        created_at=str(payload.get("created_at") or utc_now_iso()),
        updated_at=str(payload.get("updated_at") or utc_now_iso()),
    )


def behavior_representation_from_dict(value: dict[str, Any] | None) -> BehaviorRepresentation | None:
    payload = value if isinstance(value, dict) else {}
    if not payload:
        return None
    return BehaviorRepresentation(
        project_id=str(payload.get("project_id") or "unknown_project"),
        profile=creator_profile_from_dict(payload.get("profile") if isinstance(payload.get("profile"), dict) else {}),
        sample_count=int(payload.get("sample_count") or 0),
        selected_count=int(payload.get("selected_count") or 0),
        evidence_matrix=dict(payload.get("evidence_matrix") or {}),
        performance_segments=dict(payload.get("performance_segments") or {}),
        media_mix=dict(payload.get("media_mix") or {}),
        behavior_patterns=dict(payload.get("behavior_patterns") or {}),
        content_structures=dict(payload.get("content_structures") or payload.get("structure_patterns") or {}),
        structure_patterns=dict(payload.get("structure_patterns") or payload.get("content_structures") or {}),
        hook_patterns=dict(payload.get("hook_patterns") or {}),
        risk_patterns=dict(payload.get("risk_patterns") or payload.get("anti_patterns") or {}),
        evolution_signals=dict(payload.get("evolution_signals") or {}),
        constraints=tuple(str(item) for item in (payload.get("constraints") or []) if str(item)),
        generated_at=str(payload.get("generated_at") or utc_now_iso()),
    )


def validate_creator_clone_schema(value: dict[str, Any] | None) -> dict[str, Any]:
    """Return a deterministic CreatorCloneSchema payload.

    This validator is part of Creator Intelligence v2 rather than the legacy
    creator-clone compatibility module, so every runtime component can share
    one output contract.
    """
    payload = value if isinstance(value, dict) else {}
    schema = CreatorCloneStrategy.empty_schema()
    result: dict[str, Any] = {"positioning": str(payload.get("positioning") or "")}
    for key in ("content_strategy", "hooks", "anti_patterns", "validation_rules"):
        rows = payload.get(key)
        if not isinstance(rows, list):
            rows = [rows] if rows else []
        result[key] = [str(item).strip() for item in rows if str(item or "").strip()]
    for key in ("templates", "idea_bank"):
        rows = payload.get(key)
        if not isinstance(rows, list):
            rows = [rows] if rows else []
        normalized_rows: list[dict[str, Any]] = []
        for item in rows:
            if isinstance(item, dict):
                cleaned = {item_key: item_value for item_key, item_value in item.items() if item_value not in ("", [], {}, None)}
                if cleaned:
                    normalized_rows.append(cleaned)
            elif str(item or "").strip():
                normalized_rows.append({"text": str(item).strip()})
        result[key] = normalized_rows
    for key, fallback in schema.items():
        result.setdefault(key, fallback)
    return result


Sample = CreatorSample
SampleSet = CreatorProject
EvidenceBundle = Evidence
CreatorClone = CreatorCloneStrategy
