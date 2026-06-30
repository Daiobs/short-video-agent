from __future__ import annotations

import csv
import io
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from ipaddress import ip_address
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from sqlalchemy.orm import Session

from app.config import settings
from app.errors import AppError, ErrorCode
from app.models import CaseArtifact
from app.providers.profile_base import ProfileScanResult, ProfileVideoItem, profile_engagement_score
from app.services.douyin_url_parser import extract_aweme_id, extract_first_url
from app.services.llm_provider import get_llm_provider
from app.services.llm_settings import llm_is_configured
from app.services.profile_scan import scan_profile
from app.providers.profile_base import ProfileScanRequest


VALID_SOURCE_TYPES = {"douyin", "xhs", "bili", "local", "manual", "unknown"}
VALID_MEDIA_TYPES = {"video", "image", "mixed", "text", "unknown"}
VALID_UNDERSTANDING_LEVELS = {"full", "partial", "metadata_only"}
MAX_DISTILL_SAMPLES = 20
HANDOFF_SENSITIVE_RE = re.compile(
    r"(cookie|sessionid|sid_guard|passport|token|authorization|x-bogus|mstoken|odin_tt)(\s*[:=]\s*(?:bearer\s+)?[^&;\"'<>]+)?",
    re.IGNORECASE,
)
HANDOFF_DISALLOWED_KEY_RE = re.compile(
    r"(^|[_-])(cookie|cookies|raw_headers|request_headers|response_headers|headers|authorization|set_cookie|"
    r"localstorage|sessionstorage|local_storage|session_storage|signed_url|signed_media_url|download_url|"
    r"play_addr|video_url|url_list|signature)([_-]|$)|x-bogus|mstoken|odin_tt|sid_guard|passport|sessionid",
    re.IGNORECASE,
)
HANDOFF_SIGNED_MEDIA_HOST_SUFFIXES = ("365yg.com", "douyinvod.com")
HANDOFF_CONTRACT_SECTIONS = {"safety", "security_contract", "handoff_scope"}
HANDOFF_FREE_TEXT_KEYS = {"title", "creator_name", "nickname", "bio", "desc", "author", "notes", "create_time"}
HANDOFF_TOP_LEVEL_SENSITIVE_FIELDS = ("title", "creator_name", "source_url")
HANDOFF_SAMPLE_SENSITIVE_FIELDS = (
    "sample_id",
    "source_url",
    "cover_url",
    "title",
    "desc",
    "author",
    "notes",
)
HANDOFF_ALLOWED_AUDIT_PATHS = {
    ("capture_audit", "authorization"),
    ("capture_audit", "authorization", "page_confirmed"),
    ("capture_audit", "authorization", "one_time_token_consumed"),
    ("capture_audit", "authorization", "trigger"),
}


@dataclass
class CloneSample:
    sample_id: str
    source_type: str = "unknown"
    source_url: str = ""
    aweme_id: str = ""
    title: str = ""
    desc: str = ""
    author: str = ""
    cover_url: str = ""
    media_type: str = "unknown"
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    collect_count: int = 0
    view_count: int = 0
    create_time: str = ""
    case_id: str = ""
    understanding_level: str = "metadata_only"
    has_video: bool = False
    has_frames: bool = False
    has_asr: bool = False
    has_ocr: bool = False
    has_comments: bool = False
    enrichment_status: str = "pending"
    asr_status: str = "pending"
    ocr_status: str = "pending"
    analysis_status: str = "not_analyzed"
    selected: bool = False
    tags: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def engagement_score(self) -> int:
        return profile_engagement_score(self.like_count, self.comment_count, self.share_count)

    def to_dict(self) -> dict:
        return {
            "sample_id": self.sample_id,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "aweme_id": self.aweme_id,
            "title": self.title,
            "desc": self.desc,
            "author": self.author,
            "cover_url": self.cover_url,
            "media_type": self.media_type,
            "like_count": self.like_count,
            "comment_count": self.comment_count,
            "share_count": self.share_count,
            "collect_count": self.collect_count,
            "view_count": self.view_count,
            "create_time": self.create_time,
            "case_id": self.case_id,
            "understanding_level": self.understanding_level,
            "has_video": self.has_video,
            "has_frames": self.has_frames,
            "has_asr": self.has_asr,
            "has_ocr": self.has_ocr,
            "has_comments": self.has_comments,
            "enrichment_status": self.enrichment_status,
            "asr_status": self.asr_status,
            "ocr_status": self.ocr_status,
            "analysis_status": self.analysis_status,
            "selected": self.selected,
            "tags": list(self.tags),
            "notes": self.notes,
            "engagement_score": self.engagement_score,
        }


@dataclass
class CloneSampleSet:
    set_id: str
    title: str = "创作者克隆实验室素材池"
    creator_name: str = ""
    source_platform: str = "unknown"
    profile_metadata: dict[str, Any] = field(default_factory=dict)
    samples: list[CloneSample] = field(default_factory=list)
    selected_sample_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        counts = understanding_counts(self.samples)
        return {
            "set_id": self.set_id,
            "title": self.title,
            "creator_name": self.creator_name,
            "source_platform": self.source_platform,
            "profile_metadata": dict(self.profile_metadata),
            "samples": [sample.to_dict() for sample in self.samples],
            "selected_sample_ids": list(self.selected_sample_ids),
            "warnings": list(self.warnings),
            "created_at": self.created_at,
            "sample_count": len(self.samples),
            "selected_count": len(self.selected_sample_ids),
            "understanding_counts": counts,
            "performance_segments": performance_segments(self.samples),
        }


def creator_clone_dir(set_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_\-]", "", set_id)
    if not safe_id:
        raise AppError(ErrorCode.PROFILE_SCAN_FAILED, "素材池 ID 无效。")
    path = settings.creator_clones_dir / safe_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_sample_set(
    *,
    db: Session | None = None,
    title: str = "",
    creator_name: str = "",
    source_platform: str = "douyin",
    profile_url: str = "",
    sec_user_id: str = "",
    manual_links: str = "",
    structured_items: str = "",
    case_ids: str = "",
    count: int = 20,
    sort_by: str = "engagement_score",
) -> CloneSampleSet:
    samples: list[CloneSample] = []
    warnings: list[str] = []

    if profile_url.strip() or sec_user_id.strip():
        try:
            result = scan_profile(
                ProfileScanRequest(
                    profile_url=profile_url,
                    sec_user_id=sec_user_id,
                    count=count,
                    sort_by=sort_by,
                )
            )
            samples.extend(samples_from_profile_result(result))
            warnings.extend(result.warnings)
            warnings.append("公开主页扫描优先执行；仅使用平台公开返回的数据，不登录、不使用 Cookie、不绕风控。")
        except AppError as error:
            if not (manual_links.strip() or structured_items.strip() or case_ids.strip()):
                raise
            warnings.append(f"公开主页扫描失败，已继续使用兜底导入：{error.code}：{error.message}")

    if manual_links.strip():
        try:
            result = scan_profile(
                ProfileScanRequest(
                    manual_links=manual_links,
                    count=count,
                    sort_by=sort_by,
                )
            )
            samples.extend(samples_from_profile_result(result))
            warnings.extend(result.warnings)
        except AppError:
            pass
        generic_manual_samples = samples_from_manual_text(manual_links)
        if generic_manual_samples:
            samples.extend(generic_manual_samples)

    if structured_items.strip():
        structured_samples = samples_from_structured_text(structured_items)
        if structured_samples:
            samples.extend(structured_samples)
        else:
            result = scan_profile(
                ProfileScanRequest(
                    structured_items=structured_items,
                    count=count,
                    sort_by=sort_by,
                )
            )
            samples.extend(samples_from_profile_result(result))
            warnings.extend(result.warnings)

    if case_ids.strip():
        if db is None:
            raise AppError(ErrorCode.CASE_BUILD_FAILED, "已有 Case 导入需要数据库会话。")
        samples.extend(samples_from_case_ids(db, case_ids))

    samples, duplicate_count = dedupe_samples(samples)
    if duplicate_count:
        warnings.append(f"已自动去重 {duplicate_count} 条重复素材。")
    if not samples:
        raise AppError(ErrorCode.AWEME_ID_NOT_FOUND, "没有导入可用素材。请粘贴多作品链接、JSON/CSV 或 case_id。")

    sample_set = CloneSampleSet(
        set_id=f"clone_{uuid.uuid4().hex}",
        title=title.strip() or "创作者克隆实验室素材池",
        creator_name=creator_name.strip(),
        source_platform=normalize_source_type(source_platform),
        samples=samples,
        selected_sample_ids=[],
        warnings=warnings,
    )
    save_sample_set(sample_set)
    return sample_set


def samples_from_profile_result(result: ProfileScanResult) -> list[CloneSample]:
    return [sample_from_profile_item(item) for item in result.items]


def sample_from_profile_item(item: ProfileVideoItem) -> CloneSample:
    source_type = "douyin" if (item.webpage_url or "").find("douyin.com") >= 0 or item.aweme_id else "unknown"
    media_type = normalize_media_type(item.media_type)
    source_url = _safe_public_metadata_url(item.webpage_url or (f"https://www.douyin.com/video/{item.aweme_id}" if item.aweme_id else ""))
    sample = CloneSample(
        sample_id=f"sample_{item.aweme_id or uuid.uuid4().hex}",
        source_type=source_type,
        source_url=source_url,
        aweme_id=item.aweme_id,
        title=_safe_public_metadata_text(item.title, 220),
        desc=_safe_public_metadata_text(item.desc, 500),
        author=_safe_public_metadata_text(item.author, 120),
        cover_url=_safe_public_metadata_url(item.cover_url),
        media_type=media_type,
        like_count=int(item.like_count or 0),
        comment_count=int(item.comment_count or 0),
        share_count=int(item.share_count or 0),
        collect_count=int(item.collect_count or 0),
        view_count=int(getattr(item, "view_count", 0) or 0),
        create_time=_safe_public_metadata_text(item.create_time, 80),
        understanding_level="metadata_only",
        has_video=False,
        notes="来自作品池导入，尚未生成素材包。" if media_type != "image" else "图文/照片样本，当前仅作为元数据样本。",
    )
    return sample


def samples_from_manual_text(text: str) -> list[CloneSample]:
    samples: list[CloneSample] = []
    for line in [line.strip() for line in (text or "").splitlines() if line.strip()]:
        url = extract_first_url(line)
        raw_id = ""
        try:
            raw_id = extract_aweme_id(line)
        except AppError:
            raw_id = ""
        if not url and not raw_id:
            continue
        source_url = url or (f"https://www.douyin.com/video/{raw_id}" if raw_id else "")
        source_type = detect_source_type(source_url)
        sample_id = f"sample_{raw_id}" if raw_id else f"sample_{_stable_token(source_url or line)}"
        samples.append(
            CloneSample(
                sample_id=sample_id,
                source_type=source_type,
                source_url=source_url,
                aweme_id=raw_id,
                title=line[:120] if not raw_id else f"抖音作品 {raw_id}",
                desc=line[:260],
                media_type="video" if raw_id or source_type in {"douyin", "bili"} else "unknown",
                understanding_level="metadata_only",
                notes="来自手动链接导入，尚未生成素材包。",
            )
        )
    return samples


def samples_from_structured_text(text: str) -> list[CloneSample]:
    rows = parse_structured_samples(text)
    return [sample_from_structured_row(row) for row in rows]


def build_sample_set_from_handoff_manifest(payload: dict) -> CloneSampleSet:
    if not isinstance(payload, dict):
        raise AppError(ErrorCode.HANDOFF_MANIFEST_INVALID, "handoff_manifest 必须是 JSON 对象。")
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    security_contract = payload.get("security_contract") if isinstance(payload.get("security_contract"), dict) else {}
    if not _handoff_safety_ok(safety) or not _handoff_security_contract_ok(security_contract):
        raise AppError(
            ErrorCode.HANDOFF_MANIFEST_INVALID,
            "handoff_manifest 缺少安全声明，或声明包含 Cookie、登录 token、签名 URL。",
        )
    if _handoff_payload_has_sensitive_sample_data(payload):
        raise AppError(
            ErrorCode.HANDOFF_MANIFEST_INVALID,
            "handoff_manifest 包含 Cookie、登录 token、签名参数或其他敏感字段，请重新从本机助手导出净化后的交接包。",
        )
    raw_samples = payload.get("samples") if isinstance(payload.get("samples"), list) else []
    samples = [sample_from_handoff_item(item) for item in raw_samples if isinstance(item, dict)]
    samples = [sample for sample in samples if sample.aweme_id or sample.source_url or sample.title]
    samples, duplicate_count = dedupe_samples(samples)
    if not samples:
        raise AppError(ErrorCode.HANDOFF_MANIFEST_INVALID, "handoff_manifest 没有可导入的样本。")
    warnings = [
        "来自本地助手 handoff_manifest.json：公开网站只接收净化后的作品列表和元数据，不接收 Cookie、登录 token、签名 URL 或原始请求头。",
    ]
    if duplicate_count:
        warnings.append(f"已自动去重 {duplicate_count} 条重复素材。")
    sample_set = CloneSampleSet(
        set_id=f"clone_{uuid.uuid4().hex}",
        title=_safe_handoff_text(str(payload.get("title") or "安全交接包素材池"), 160),
        creator_name=_safe_handoff_text(str(payload.get("creator_name") or ""), 120),
        source_platform=normalize_source_type(str(payload.get("source_platform") or "douyin")),
        profile_metadata=_safe_handoff_object(payload.get("profile_metadata")) if isinstance(payload.get("profile_metadata"), dict) else {},
        samples=samples,
        warnings=warnings,
    )
    save_sample_set(sample_set)
    clean_manifest = _sanitize_handoff_import_payload(payload, sample_set)
    _write_json(creator_clone_dir(sample_set.set_id) / "handoff_manifest.json", clean_manifest)
    return sample_set


def sample_from_handoff_item(item: dict) -> CloneSample:
    source_url = _safe_handoff_url(str(item.get("source_url") or ""), aweme_id=str(item.get("aweme_id") or ""))
    cover_url = _safe_handoff_url(str(item.get("cover_url") or ""))
    source_type = normalize_source_type(str(item.get("source_type") or "")) if item.get("source_type") else detect_source_type(source_url)
    return CloneSample(
        sample_id=_safe_handoff_text(str(item.get("sample_id") or f"sample_{uuid.uuid4().hex}"), 120),
        source_type=source_type,
        source_url=source_url,
        aweme_id=_safe_handoff_aweme_id(str(item.get("aweme_id") or ""), source_url),
        title=_safe_handoff_text(str(item.get("title") or ""), 220),
        desc=_safe_handoff_text(str(item.get("desc") or ""), 500),
        author=_safe_handoff_text(str(item.get("author") or ""), 120),
        cover_url=cover_url,
        media_type=normalize_media_type(str(item.get("media_type") or "unknown")),
        like_count=_safe_int(item.get("like_count")),
        comment_count=_safe_int(item.get("comment_count")),
        share_count=_safe_int(item.get("share_count")),
        collect_count=_safe_int(item.get("collect_count")),
        view_count=_safe_int(item.get("view_count")),
        create_time=_safe_handoff_text(str(item.get("create_time") or ""), 80),
        case_id=_safe_handoff_text(str(item.get("case_id") or ""), 120),
        understanding_level=normalize_understanding_level(str(item.get("understanding_level") or "metadata_only")),
        has_video=bool(item.get("has_video")),
        has_frames=bool(item.get("has_frames")),
        has_asr=bool(item.get("has_asr")),
        has_ocr=bool(item.get("has_ocr")),
        has_comments=bool(item.get("has_comments")),
        enrichment_status=_safe_handoff_text(str(item.get("enrichment_status") or "pending"), 80),
        asr_status=_safe_handoff_text(str(item.get("asr_status") or "pending"), 80),
        ocr_status=_safe_handoff_text(str(item.get("ocr_status") or "pending"), 80),
        analysis_status=_safe_handoff_text(str(item.get("analysis_status") or "not_analyzed"), 80),
        tags=[_safe_handoff_text(str(tag), 40) for tag in item.get("tags", []) if isinstance(item.get("tags"), list)],
        notes=_safe_handoff_text(str(item.get("notes") or "来自安全交接包导入，尚未生成素材包。"), 500),
    )


def sample_from_structured_row(row: dict) -> CloneSample:
    raw_id = str(_row_field(row, "aweme_id", "awemeId", "awemeIdStr", "id", default="")).strip()
    source_url = str(_row_field(row, "source_url", "webpage_url", "video_url", "url", "link", default="")).strip()
    aweme_id = ""
    if raw_id and re.fullmatch(r"\d{15,22}", raw_id):
        aweme_id = raw_id
    elif source_url:
        try:
            aweme_id = extract_aweme_id(source_url)
        except AppError:
            aweme_id = ""
    safe_source_url = _safe_public_metadata_url(source_url)
    if not safe_source_url and aweme_id:
        safe_source_url = f"https://www.douyin.com/video/{aweme_id}"
    source_type = normalize_source_type(str(_row_field(row, "source_type", "platform", default="")).strip()) if _row_field(row, "source_type", "platform", default="") else detect_source_type(source_url)
    media_type = normalize_media_type(str(_row_field(row, "media_type", "type", default="unknown")).strip())
    title = _safe_public_metadata_text(str(_row_field(row, "title", "desc", "description", "caption", default="")).strip(), 220)
    sample_id = f"sample_{aweme_id or _stable_token(safe_source_url or title or raw_id)}"
    return CloneSample(
        sample_id=sample_id,
        source_type=source_type,
        source_url=safe_source_url,
        aweme_id=aweme_id,
        title=title or (f"抖音作品 {aweme_id}" if aweme_id else _safe_public_metadata_text(raw_id, 120) or "未命名样本"),
        desc=_safe_public_metadata_text(str(_row_field(row, "desc", "description", "caption", default="")).strip(), 500),
        author=_safe_public_metadata_text(str(_row_field(row, "author", "nickname", default="")).strip(), 120),
        cover_url=_safe_public_metadata_url(str(_row_field(row, "cover_url", "cover", default="")).strip()),
        media_type=media_type,
        like_count=_safe_int(_row_field(row, "like_count", "likes", "digg_count", "statistics.digg_count", default=0)),
        comment_count=_safe_int(_row_field(row, "comment_count", "comments", "statistics.comment_count", default=0)),
        share_count=_safe_int(_row_field(row, "share_count", "shares", "statistics.share_count", default=0)),
        collect_count=_safe_int(_row_field(row, "collect_count", "collects", "statistics.collect_count", default=0)),
        view_count=_safe_int(_row_field(row, "view_count", "play_count", "statistics.play_count", default=0)),
        create_time=_safe_public_metadata_text(str(_row_field(row, "create_time", "publish_time", default="")).strip(), 80),
        case_id=_safe_public_metadata_text(str(_row_field(row, "case_id", default="")).strip(), 120),
        understanding_level=normalize_understanding_level(str(_row_field(row, "understanding_level", default="metadata_only"))),
        has_video=bool(_row_field(row, "has_video", default=False)),
        has_frames=bool(_row_field(row, "has_frames", default=False)),
        has_asr=bool(_row_field(row, "has_asr", default=False)),
        has_ocr=bool(_row_field(row, "has_ocr", default=False)),
        has_comments=bool(_row_field(row, "has_comments", default=False)),
        enrichment_status=_safe_public_metadata_text(str(_row_field(row, "enrichment_status", default="pending") or "pending"), 80),
        asr_status=_safe_public_metadata_text(str(_row_field(row, "asr_status", default="pending") or "pending"), 80),
        ocr_status=_safe_public_metadata_text(str(_row_field(row, "ocr_status", default="pending") or "pending"), 80),
        analysis_status=_safe_public_metadata_text(str(_row_field(row, "analysis_status", default="not_analyzed") or "not_analyzed"), 80),
        tags=[_safe_public_metadata_text(tag, 40) for tag in _tags_from_value(_row_field(row, "tags", default=[]))],
        notes=_safe_public_metadata_text(str(_row_field(row, "notes", "remark", default="")).strip(), 500),
    )


def samples_from_case_ids(db: Session, case_ids_text: str) -> list[CloneSample]:
    samples: list[CloneSample] = []
    for value in re.split(r"[\s,，]+", case_ids_text.strip()):
        case_id = value.strip()
        if not case_id:
            continue
        artifact = db.get(CaseArtifact, case_id)
        if not artifact:
            continue
        samples.append(sample_from_case_artifact(artifact))
    return samples


def sample_from_case_artifact(artifact: CaseArtifact) -> CloneSample:
    metadata = _read_json(Path(artifact.metadata_path))
    analysis_result_path = Path(artifact.prompt_path).parent / "analysis_result.json"
    case_dir = Path(artifact.prompt_path).parent
    asr_dir = case_dir / "enrichment" / "asr"
    ocr_dir = case_dir / "enrichment" / "ocr"
    comments_dir = case_dir / "enrichment" / "comments"
    manifest = _read_json(case_dir / "enrichment" / "manifest.json")
    statuses = manifest.get("statuses") if isinstance(manifest.get("statuses"), dict) else {}
    asr_status = _status_from_file(asr_dir / "status.json", str(statuses.get("asr") or "pending"))
    ocr_status = _status_from_file(ocr_dir / "status.json", str(statuses.get("ocr") or "pending"))
    enrichment_status = "success" if (case_dir / "enrichment" / "manifest.json").is_file() else "pending"
    analysis_status = "success" if analysis_result_path.is_file() else "not_analyzed"
    sample = CloneSample(
        sample_id=f"sample_{artifact.case_id}",
        source_type="douyin" if artifact.aweme_id else "local",
        source_url=str(metadata.get("source_url") or ""),
        aweme_id=artifact.aweme_id,
        title=str(metadata.get("title") or artifact.case_id),
        desc=str(metadata.get("notes") or ""),
        author=str(metadata.get("author") or ""),
        media_type="video",
        like_count=_safe_int(metadata.get("like_count")),
        comment_count=_safe_int(metadata.get("comment_count")),
        share_count=_safe_int(metadata.get("share_count")),
        create_time=str(metadata.get("create_time") or ""),
        case_id=artifact.case_id,
        understanding_level="full" if analysis_result_path.is_file() else "partial",
        has_video=Path(artifact.video_path).is_file(),
        has_frames=Path(artifact.contact_sheet_path).is_file() or Path(artifact.keyframes_dir).is_dir(),
        has_asr=(asr_dir / "transcript.json").is_file() or (asr_dir / "transcript.txt").is_file(),
        has_ocr=(ocr_dir / "frame_ocr.json").is_file() or (ocr_dir / "subtitle_ocr.json").is_file(),
        has_comments=(comments_dir / "comment_summary.json").is_file(),
        enrichment_status=enrichment_status,
        asr_status=asr_status,
        ocr_status=ocr_status,
        analysis_status=analysis_status,
        notes="已有 Case 导入。",
    )
    if not (sample.has_asr or sample.has_ocr):
        sample.understanding_level = "partial" if sample.has_frames else "metadata_only"
    return sample


def update_sample_set_with_case_artifacts(set_id: str, artifacts: list[CaseArtifact]) -> CloneSampleSet:
    sample_set = load_sample_set(set_id)
    by_aweme = {artifact.aweme_id: artifact for artifact in artifacts if artifact.aweme_id}
    by_case = {artifact.case_id: artifact for artifact in artifacts if artifact.case_id}
    updated = 0
    for sample in sample_set.samples:
        artifact = by_aweme.get(sample.aweme_id) or by_case.get(sample.case_id)
        if not artifact:
            continue
        evidence = sample_from_case_artifact(artifact)
        sample.case_id = evidence.case_id
        sample.has_video = evidence.has_video
        sample.has_frames = evidence.has_frames
        sample.has_asr = evidence.has_asr
        sample.has_ocr = evidence.has_ocr
        sample.has_comments = evidence.has_comments
        sample.enrichment_status = evidence.enrichment_status
        sample.asr_status = evidence.asr_status
        sample.ocr_status = evidence.ocr_status
        sample.analysis_status = evidence.analysis_status
        sample.understanding_level = evidence.understanding_level
        sample.notes = "已生成素材包，可用于蒸馏证据。" if evidence.has_frames else evidence.notes
        if not sample.title and evidence.title:
            sample.title = evidence.title
        if not sample.source_url and evidence.source_url:
            sample.source_url = evidence.source_url
        updated += 1
    if updated:
        sample_set.warnings = [
            *sample_set.warnings,
            f"已回写 {updated} 条样本的素材包证据；蒸馏时会优先使用对应 case 报告和富化数据。",
        ]
        save_sample_set(sample_set)
    return sample_set


def update_sample_set_selection(set_id: str, selected_sample_ids: list[str]) -> CloneSampleSet:
    sample_set = load_sample_set(set_id)
    selected_keys = {str(value) for value in selected_sample_ids if str(value)}
    selected: list[str] = []
    for sample in sample_set.samples:
        selected_now = (
            sample.sample_id in selected_keys
            or sample.aweme_id in selected_keys
            or sample.case_id in selected_keys
            or sample.source_url in selected_keys
        )
        sample.selected = selected_now
        if selected_now:
            selected.append(sample.sample_id)
    sample_set.selected_sample_ids = selected
    save_sample_set(sample_set)
    return sample_set


def dedupe_samples(samples: list[CloneSample]) -> tuple[list[CloneSample], int]:
    seen: set[str] = set()
    result: list[CloneSample] = []
    duplicate_count = 0
    for sample in samples:
        key = sample.aweme_id or sample.case_id or sample.source_url or sample.sample_id
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        result.append(sample)
    return result, duplicate_count


def save_sample_set(sample_set: CloneSampleSet) -> None:
    output_dir = creator_clone_dir(sample_set.set_id)
    _write_json(output_dir / "samples.json", sample_set.to_dict())


def load_sample_set(set_id: str) -> CloneSampleSet:
    payload = _read_json(creator_clone_dir(set_id) / "samples.json")
    samples = [sample_from_dict(item) for item in payload.get("samples", []) if isinstance(item, dict)]
    return CloneSampleSet(
        set_id=str(payload.get("set_id") or set_id),
        title=str(payload.get("title") or "创作者克隆实验室素材池"),
        creator_name=str(payload.get("creator_name") or ""),
        source_platform=normalize_source_type(str(payload.get("source_platform") or "unknown")),
        profile_metadata=payload.get("profile_metadata") if isinstance(payload.get("profile_metadata"), dict) else {},
        samples=samples,
        selected_sample_ids=[str(value) for value in payload.get("selected_sample_ids", [])],
        warnings=[str(value) for value in payload.get("warnings", [])],
        created_at=str(payload.get("created_at") or datetime.now(timezone.utc).isoformat()),
    )


def sample_from_dict(item: dict) -> CloneSample:
    sample = CloneSample(
        sample_id=_safe_public_metadata_text(str(item.get("sample_id") or f"sample_{uuid.uuid4().hex}"), 120),
        source_type=normalize_source_type(str(item.get("source_type") or "unknown")),
        source_url=_safe_public_metadata_url(str(item.get("source_url") or "")),
        aweme_id=str(item.get("aweme_id") or "") if re.fullmatch(r"\d{15,22}", str(item.get("aweme_id") or "")) else "",
        title=_safe_public_metadata_text(str(item.get("title") or ""), 220),
        desc=_safe_public_metadata_text(str(item.get("desc") or ""), 500),
        author=_safe_public_metadata_text(str(item.get("author") or ""), 120),
        cover_url=_safe_public_metadata_url(str(item.get("cover_url") or "")),
        media_type=normalize_media_type(str(item.get("media_type") or "unknown")),
        like_count=_safe_int(item.get("like_count")),
        comment_count=_safe_int(item.get("comment_count")),
        share_count=_safe_int(item.get("share_count")),
        collect_count=_safe_int(item.get("collect_count")),
        view_count=_safe_int(item.get("view_count")),
        create_time=_safe_public_metadata_text(str(item.get("create_time") or ""), 80),
        case_id=_safe_public_metadata_text(str(item.get("case_id") or ""), 120),
        understanding_level=normalize_understanding_level(str(item.get("understanding_level") or "metadata_only")),
        has_video=bool(item.get("has_video")),
        has_frames=bool(item.get("has_frames")),
        has_asr=bool(item.get("has_asr")),
        has_ocr=bool(item.get("has_ocr")),
        has_comments=bool(item.get("has_comments")),
        enrichment_status=_safe_public_metadata_text(str(item.get("enrichment_status") or "pending"), 80),
        asr_status=_safe_public_metadata_text(str(item.get("asr_status") or "pending"), 80),
        ocr_status=_safe_public_metadata_text(str(item.get("ocr_status") or "pending"), 80),
        analysis_status=_safe_public_metadata_text(str(item.get("analysis_status") or "not_analyzed"), 80),
        selected=bool(item.get("selected")),
        tags=[_safe_public_metadata_text(str(value), 40) for value in item.get("tags", [])] if isinstance(item.get("tags"), list) else [],
        notes=_safe_public_metadata_text(str(item.get("notes") or ""), 500),
    )
    return sample


def validate_selected_samples(samples: list[CloneSample], selected_sample_ids: list[str], max_samples: int = MAX_DISTILL_SAMPLES) -> tuple[list[CloneSample], list[str]]:
    selected_ids = set(selected_sample_ids)
    selected = [sample for sample in samples if sample.sample_id in selected_ids or sample.aweme_id in selected_ids or sample.case_id in selected_ids]
    warnings: list[str] = []
    if len(selected) > max_samples or len(selected) > MAX_DISTILL_SAMPLES:
        raise AppError(
            ErrorCode.PROFILE_BUILD_QUEUE_LIMIT,
            f"当前 MVP 最多选择 {MAX_DISTILL_SAMPLES} 条进行蒸馏，避免上下文过长。",
        )
    if len(selected) < 1:
        raise AppError(ErrorCode.AWEME_ID_NOT_FOUND, "请至少选择 1 条素材。")
    if len(selected) < 2:
        warnings.append("样本过少，结果仅供参考。建议至少选择 2-5 条代表素材。")
    metadata_only_count = sum(1 for sample in selected if sample.understanding_level == "metadata_only")
    if metadata_only_count > len(selected) / 2:
        warnings.append("当前多数样本只有元数据，创作者表达方式和镜头节奏判断可能不准确。建议先选择部分样本生成素材包。")
    return selected, warnings


def understanding_counts(samples: list[CloneSample]) -> dict:
    return {
        "full": sum(1 for sample in samples if sample.understanding_level == "full"),
        "partial": sum(1 for sample in samples if sample.understanding_level == "partial"),
        "metadata_only": sum(1 for sample in samples if sample.understanding_level == "metadata_only"),
    }


def media_type_counts(samples: list[CloneSample]) -> dict:
    counts = {media_type: 0 for media_type in sorted(VALID_MEDIA_TYPES)}
    for sample in samples:
        media_type = normalize_media_type(sample.media_type)
        counts[media_type] = counts.get(media_type, 0) + 1
    return counts


def performance_segments(samples: list[CloneSample], limit: int = 5) -> dict:
    limit = max(1, min(int(limit or 5), 10))

    def segment(key: str, reverse: bool = True, require_positive: bool = True) -> list[dict]:
        candidates = [sample for sample in samples if not require_positive or _metric_value(sample, key) > 0]
        ordered = sorted(candidates, key=lambda sample: _metric_value(sample, key), reverse=reverse)
        return [_segment_sample_payload(sample, key) for sample in ordered[:limit]]

    weak_candidates = sorted(samples, key=lambda sample: (sample.engagement_score, sample.like_count, sample.comment_count))
    return {
        "highest_like_samples": segment("like_count"),
        "highest_comment_samples": segment("comment_count"),
        "highest_share_samples": segment("share_count"),
        "highest_collect_samples": segment("collect_count"),
        "weak_or_reference_samples": [_segment_sample_payload(sample, "engagement_score") for sample in weak_candidates[:limit]],
    }


def _metric_value(sample: CloneSample, key: str) -> int:
    if key == "engagement_score":
        return int(sample.engagement_score or 0)
    return int(getattr(sample, key, 0) or 0)


def _segment_sample_payload(sample: CloneSample, metric_key: str) -> dict:
    return {
        "sample_id": sample.sample_id,
        "aweme_id": sample.aweme_id,
        "case_id": sample.case_id,
        "title": sample.title,
        "metric": metric_key,
        "metric_value": _metric_value(sample, metric_key),
        "like_count": sample.like_count,
        "comment_count": sample.comment_count,
        "share_count": sample.share_count,
        "collect_count": sample.collect_count,
        "engagement_score": sample.engagement_score,
        "understanding_level": sample.understanding_level,
    }


def build_distill_prompt(sample_set: CloneSampleSet, selected_samples: list[CloneSample], distill_mode: str = "quick", include_case_reports: bool = True) -> str:
    compact_samples = [sample_to_prompt_payload(sample, include_case_reports=include_case_reports) for sample in selected_samples]
    counts = understanding_counts(selected_samples)
    media_counts = media_type_counts(selected_samples)
    segments = performance_segments(selected_samples)
    evidence_matrix = selected_evidence_matrix(selected_samples)
    evidence_constraints = selected_evidence_constraints(selected_samples)
    schema = creator_clone_schema()
    return f"""你是 Creator Clone Lab 的创作者规律蒸馏引擎。

请基于下方素材池，提炼创作者的选题规则、表达方式、爆款公式和 AI 创作者克隆规则。

重要要求：
- 只输出合法 JSON，不要输出 Markdown。
- 不要伪造没有证据的数据。
- 如果样本是 metadata_only，必须在 evidence_gaps 中说明视觉、ASR、OCR 或评论证据不足。
- 必须区分 video / image / text / mixed / unknown：视频样本才能推断镜头节奏、动作和口播；图文/照片样本只能推断封面、标题、视觉承诺和静态构图；unknown 样本只能作为元数据参考。
- 区分高赞、高评论、高分享、高收藏和弱样本；没有数据时用空数组。
- 输出要适合后续在网页可视化展示。

蒸馏模式：{distill_mode}
素材池标题：{sample_set.title}
创作者：{sample_set.creator_name or "未知"}
平台：{sample_set.source_platform}
账号可见资料：{json.dumps(sample_set.profile_metadata or {}, ensure_ascii=False)}
样本数：{len(selected_samples)}
理解状态统计：{json.dumps(counts, ensure_ascii=False)}
媒体类型统计：{json.dumps(media_counts, ensure_ascii=False)}
本地预分层样本：{json.dumps(segments, ensure_ascii=False, indent=2)}
证据矩阵：{json.dumps(evidence_matrix, ensure_ascii=False, indent=2)}
证据约束：{json.dumps(evidence_constraints, ensure_ascii=False, indent=2)}

请严格返回这个 JSON 结构，字段缺失时用空字符串、空数组或空对象：
{json.dumps(schema, ensure_ascii=False, indent=2)}

选中样本：
{json.dumps(compact_samples, ensure_ascii=False, indent=2)}
"""


def selected_evidence_matrix(samples: list[CloneSample]) -> dict:
    rows = list(samples or [])
    total = len(rows)
    matrix = {
        "selected_count": total,
        "with_case": sum(1 for sample in rows if sample.case_id),
        "with_video": sum(1 for sample in rows if sample.has_video),
        "with_keyframes": sum(1 for sample in rows if sample.has_frames),
        "with_asr_text": sum(1 for sample in rows if sample.has_asr),
        "with_ocr_text": sum(1 for sample in rows if sample.has_ocr),
        "with_comments": sum(1 for sample in rows if sample.has_comments),
        "with_ai_report": sum(1 for sample in rows if sample.analysis_status == "success"),
        "asr_provider_missing": sum(1 for sample in rows if sample.asr_status == "provider_missing"),
        "ocr_provider_missing": sum(1 for sample in rows if sample.ocr_status == "provider_missing"),
        "metadata_only": sum(1 for sample in rows if sample.understanding_level == "metadata_only"),
        "partial": sum(1 for sample in rows if sample.understanding_level == "partial"),
        "full": sum(1 for sample in rows if sample.understanding_level == "full"),
    }
    matrix["coverage"] = {
        key: round(value / total, 3) if total else 0
        for key, value in matrix.items()
        if key.startswith("with_")
    }
    return matrix


def selected_evidence_constraints(samples: list[CloneSample]) -> list[str]:
    matrix = selected_evidence_matrix(samples)
    total = matrix["selected_count"]
    if not total:
        return ["没有选中样本，不能蒸馏创作者规律。"]
    constraints: list[str] = []
    if matrix["metadata_only"] >= max(1, total // 2):
        constraints.append("半数以上样本只有元数据，不能过度推断画面节奏、口播结构或评论动机。")
    if matrix["with_keyframes"] < max(1, total // 2):
        constraints.append("关键帧覆盖不足，视觉风格和镜头节奏结论必须标注为低置信。")
    if matrix["with_asr_text"] == 0:
        constraints.append("没有 ASR 文本，不能断言口播文案、声音节奏或台词结构。")
    if matrix["with_ocr_text"] == 0:
        constraints.append("没有 OCR 文本，不能断言字幕、封面大字或画面文字策略。")
    if matrix["with_comments"] == 0:
        constraints.append("没有评论证据，互动动机、受众需求和评论区钩子只能作为假设。")
    if matrix["asr_provider_missing"]:
        constraints.append("部分样本 ASR provider 未配置，缺少转写不等于无语音。")
    if matrix["ocr_provider_missing"]:
        constraints.append("部分样本 OCR provider 未配置，缺少识别文本不等于无字幕或无画面文字。")
    return constraints


def sample_to_prompt_payload(sample: CloneSample, include_case_reports: bool = True) -> dict:
    payload = sample.to_dict()
    payload["evidence_status"] = _sample_evidence_status(sample)
    payload["evidence_note"] = _sample_evidence_note(sample)
    if include_case_reports and sample.case_id:
        case_dir = _case_dir_from_sample(sample)
        evidence_pack = _case_prompt_evidence_pack(case_dir)
        analysis_result = _read_json(case_dir / "analysis_result.json")
        analysis_report = _read_text(case_dir / "analysis_report.md")
        if evidence_pack:
            payload["case_evidence_pack"] = evidence_pack
        if analysis_result:
            payload["case_analysis_result"] = analysis_result
        if analysis_report:
            payload["case_analysis_report_excerpt"] = analysis_report[:4000]
    return payload


def _case_prompt_evidence_pack(case_dir: Path) -> dict:
    analysis_input = _read_json(case_dir / "analysis_input.json")
    assets = analysis_input.get("assets") if isinstance(analysis_input.get("assets"), dict) else {}
    enrichment = analysis_input.get("analysis_enrichment") if isinstance(analysis_input.get("analysis_enrichment"), dict) else {}
    asr = enrichment.get("asr") if isinstance(enrichment.get("asr"), dict) else {}
    ocr = enrichment.get("ocr") if isinstance(enrichment.get("ocr"), dict) else {}
    comments = enrichment.get("comments") if isinstance(enrichment.get("comments"), dict) else {}
    manifest = _read_json(case_dir / "enrichment" / "manifest.json")
    statuses = manifest.get("statuses") if isinstance(manifest.get("statuses"), dict) else {}

    if not asr:
        asr = _case_asr_prompt_payload(case_dir)
    if not ocr:
        ocr = _case_ocr_prompt_payload(case_dir)
    if not comments:
        comments = _read_json(case_dir / "enrichment" / "comments" / "comment_summary.json")

    keyframes = assets.get("keyframes") if isinstance(assets.get("keyframes"), list) else []
    pack = {
        "content_category": analysis_input.get("content_category") or "",
        "content_category_label": analysis_input.get("content_category_label") or "",
        "video": analysis_input.get("video") if isinstance(analysis_input.get("video"), dict) else {},
        "stats": analysis_input.get("stats") if isinstance(analysis_input.get("stats"), dict) else {},
        "assets": {
            "has_contact_sheet": bool(assets.get("contact_sheet") or (case_dir / "contact_sheet.jpg").is_file()),
            "keyframe_count": len(keyframes) or len(list((case_dir / "keyframes").glob("frame_*.jpg"))),
        },
        "statuses": {
            "asr": asr.get("status") or statuses.get("asr") or "pending",
            "ocr": ocr.get("status") or statuses.get("ocr") or "pending",
            "comments": comments.get("status") or statuses.get("comments") or "pending",
        },
        "asr_excerpt": _truncate_text(asr.get("full_text") or asr.get("text") or "", 800),
        "ocr_excerpt": {
            "cover_text": _truncate_text(ocr.get("cover_text") or "", 300),
            "subtitle_text": _truncate_text(ocr.get("subtitle_text") or "", 500),
            "frame_text": _truncate_text(ocr.get("frame_text") or "", 500),
        },
        "comment_summary": _case_comment_prompt_payload(comments),
    }
    return _drop_empty_prompt_values(pack)


def _case_asr_prompt_payload(case_dir: Path) -> dict:
    asr_dir = case_dir / "enrichment" / "asr"
    status = _read_json(asr_dir / "status.json")
    transcript = _read_json(asr_dir / "transcript.json")
    full_text = transcript.get("full_text") or _read_text(asr_dir / "transcript.txt")
    return {"status": status.get("status") or "", "full_text": full_text}


def _case_ocr_prompt_payload(case_dir: Path) -> dict:
    ocr_dir = case_dir / "enrichment" / "ocr"
    status = _read_json(ocr_dir / "status.json")
    frame = _read_json(ocr_dir / "frame_ocr.json")
    subtitle = _read_json(ocr_dir / "subtitle_ocr.json")
    cover = _read_json(ocr_dir / "cover_ocr.json")
    return {
        "status": status.get("status") or "",
        "frame_text": frame.get("full_text") or "",
        "subtitle_text": subtitle.get("full_text") or "",
        "cover_text": cover.get("full_text") or "",
    }


def _case_comment_prompt_payload(comments: dict) -> dict:
    if not comments:
        return {}
    return {
        "status": comments.get("status") or "",
        "total_comments": _safe_int(comments.get("total_comments")),
        "top_needs": comments.get("top_needs") if isinstance(comments.get("top_needs"), list) else [],
        "high_frequency_words": comments.get("high_frequency_words") if isinstance(comments.get("high_frequency_words"), list) else [],
        "comment_hooks": comments.get("comment_hooks") if isinstance(comments.get("comment_hooks"), list) else [],
    }


def _truncate_text(value: str, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _drop_empty_prompt_values(value):
    if isinstance(value, dict):
        return {
            key: cleaned
            for key, item in value.items()
            if (cleaned := _drop_empty_prompt_values(item)) not in ({}, [], "")
        }
    if isinstance(value, list):
        return [_drop_empty_prompt_values(item) for item in value if _drop_empty_prompt_values(item) not in ({}, [], "")]
    return value


def distill_creator_clone(
    sample_set: CloneSampleSet,
    selected_sample_ids: list[str],
    *,
    distill_mode: str = "quick",
    include_case_reports: bool = True,
    max_samples: int = MAX_DISTILL_SAMPLES,
) -> dict:
    selected_samples, warnings = validate_selected_samples(sample_set.samples, selected_sample_ids, max_samples=max_samples)
    sample_set.selected_sample_ids = [sample.sample_id for sample in selected_samples]
    for sample in sample_set.samples:
        sample.selected = sample.sample_id in set(sample_set.selected_sample_ids)
    save_sample_set(sample_set)

    prompt = build_distill_prompt(sample_set, selected_samples, distill_mode=distill_mode, include_case_reports=include_case_reports)
    output_dir = creator_clone_dir(sample_set.set_id)
    (output_dir / "distill_prompt.md").write_text(prompt, encoding="utf-8")

    if not llm_is_configured():
        raise AppError(ErrorCode.LLM_NOT_CONFIGURED)

    result = get_llm_provider().analyze(prompt, [])
    normalized = normalize_creator_clone_result(result, sample_set, selected_samples, warnings)
    _write_json(output_dir / "creator_clone_result.json", normalized)
    (output_dir / "creator_clone.md").write_text(render_creator_clone_markdown(normalized), encoding="utf-8")
    return {
        "set": sample_set.to_dict(),
        "result": normalized,
        "exports": export_paths(sample_set.set_id),
        "warnings": warnings,
    }


def prompt_only_result(sample_set: CloneSampleSet, selected_sample_ids: list[str], distill_mode: str = "quick", include_case_reports: bool = True) -> dict:
    selected_samples, warnings = validate_selected_samples(sample_set.samples, selected_sample_ids)
    sample_set.selected_sample_ids = [sample.sample_id for sample in selected_samples]
    for sample in sample_set.samples:
        sample.selected = sample.sample_id in set(sample_set.selected_sample_ids)
    save_sample_set(sample_set)
    prompt = build_distill_prompt(sample_set, selected_samples, distill_mode=distill_mode, include_case_reports=include_case_reports)
    output_dir = creator_clone_dir(sample_set.set_id)
    (output_dir / "distill_prompt.md").write_text(prompt, encoding="utf-8")
    return {
        "set": sample_set.to_dict(),
        "prompt": prompt,
        "exports": export_paths(sample_set.set_id),
        "warnings": warnings,
    }


def normalize_creator_clone_result(raw: dict, sample_set: CloneSampleSet, selected_samples: list[CloneSample], warnings: list[str] | None = None) -> dict:
    result = creator_clone_schema()
    _deep_merge(result, raw if isinstance(raw, dict) else {})
    result["summary"] = str(result.get("summary") or "创作者克隆蒸馏完成。")
    result["sample_overview"] = {
        "set_id": sample_set.set_id,
        "sample_count": len(sample_set.samples),
        "selected_count": len(selected_samples),
        "understanding_counts": understanding_counts(selected_samples),
        "confidence": _confidence_label(selected_samples),
        "warnings": list(warnings or []),
    }
    fallback_segments = performance_segments(selected_samples)
    current_segments = result.get("performance_segments") if isinstance(result.get("performance_segments"), dict) else {}
    result["performance_segments"] = {
        key: current_segments.get(key) or fallback_segments.get(key) or []
        for key in creator_clone_schema()["performance_segments"]
    }
    return result


def creator_clone_schema() -> dict:
    return {
        "summary": "",
        "creator_positioning": {
            "what_the_creator_sells": "",
            "audience_promise": "",
            "hidden_genre": "",
            "audience_assumption": "",
        },
        "performance_segments": {
            "highest_like_samples": [],
            "highest_comment_samples": [],
            "highest_share_samples": [],
            "highest_collect_samples": [],
            "weak_or_reference_samples": [],
        },
        "topic_buckets": [],
        "thinking_patterns": {
            "assumptions": [],
            "tension_sources": [],
            "detail_selection_rules": [],
            "novelty_vs_familiarity": "",
        },
        "expression_patterns": {
            "opening_hooks": [],
            "scene_order": [],
            "shot_types": [],
            "subtitle_voice": [],
            "visual_style": [],
            "ending_patterns": [],
        },
        "transferable_formulas": [],
        "creator_clone_spec": {
            "taste": "",
            "topic_selection_rules": [],
            "structure_rules": [],
            "expression_rules": [],
            "visual_rules": [],
            "caption_voice": "",
            "ending_rules": [],
            "anti_patterns": [],
            "self_check_rubric": [],
        },
        "candidate_ideas": [],
        "evidence_gaps": [],
        "next_actions": [],
    }


def render_creator_clone_markdown(result: dict) -> str:
    positioning = result.get("creator_positioning") or {}
    spec = result.get("creator_clone_spec") or {}
    lines = [
        "# Creator Clone Report",
        "",
        f"## Summary\n\n{result.get('summary') or ''}",
        "",
        "## Creator Positioning",
        "",
        f"- What the creator sells: {positioning.get('what_the_creator_sells') or ''}",
        f"- Audience promise: {positioning.get('audience_promise') or ''}",
        f"- Hidden genre: {positioning.get('hidden_genre') or ''}",
        f"- Audience assumption: {positioning.get('audience_assumption') or ''}",
        "",
        "## Performance Segments",
        "",
        _markdown_list(result.get("performance_segments")),
        "",
        "## Topic Buckets",
        "",
        _markdown_list(result.get("topic_buckets")),
        "",
        "## Transferable Formulas",
        "",
        _markdown_list(result.get("transferable_formulas")),
        "",
        "## AI Creator Clone Spec",
        "",
        f"- Taste: {spec.get('taste') or ''}",
        f"- Caption voice: {spec.get('caption_voice') or ''}",
        "",
        "### Topic Rules",
        "",
        _markdown_list(spec.get("topic_selection_rules")),
        "",
        "### Anti-patterns",
        "",
        _markdown_list(spec.get("anti_patterns")),
        "",
        "## Candidate Ideas",
        "",
        _markdown_list(result.get("candidate_ideas")),
        "",
        "## Evidence Gaps",
        "",
        _markdown_list(result.get("evidence_gaps")),
        "",
        "## Next Actions",
        "",
        _markdown_list(result.get("next_actions")),
        "",
    ]
    return "\n".join(lines)


def export_paths(set_id: str) -> dict:
    base = creator_clone_dir(set_id)
    return {
        "samples_json": str(base / "samples.json"),
        "handoff_manifest_json": str(base / "handoff_manifest.json"),
        "distill_prompt_md": str(base / "distill_prompt.md"),
        "creator_clone_result_json": str(base / "creator_clone_result.json"),
        "creator_clone_md": str(base / "creator_clone.md"),
    }


def normalize_source_type(value: str) -> str:
    candidate = (value or "unknown").strip().lower()
    return candidate if candidate in VALID_SOURCE_TYPES else "unknown"


def normalize_media_type(value: str) -> str:
    candidate = (value or "unknown").strip().lower()
    aliases = {"photo": "image", "note": "image", "image_post": "image", "图文": "image", "照片": "image"}
    candidate = aliases.get(candidate, candidate)
    return candidate if candidate in VALID_MEDIA_TYPES else "unknown"


def normalize_understanding_level(value: str) -> str:
    candidate = (value or "metadata_only").strip().lower().replace("-", "_")
    if candidate == "metadata":
        candidate = "metadata_only"
    return candidate if candidate in VALID_UNDERSTANDING_LEVELS else "metadata_only"


def detect_source_type(url: str) -> str:
    value = (url or "").lower()
    if "douyin.com" in value or "iesdouyin.com" in value:
        return "douyin"
    if "xiaohongshu.com" in value or "xhslink.com" in value:
        return "xhs"
    if "bilibili.com" in value or "b23.tv" in value:
        return "bili"
    if value.startswith("file:"):
        return "local"
    return "manual" if value else "unknown"


def parse_structured_samples(text: str) -> list[dict]:
    # Public helper for tests and future adapters. The active import path still
    # reuses profile_scan so behavior remains consistent with the existing pool.
    raw = (text or "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return list(csv.DictReader(io.StringIO(raw)))
    if isinstance(payload, dict):
        for key in ("items", "samples", "aweme_list", "awemeList"):
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, dict)]
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _handoff_safety_ok(safety: dict) -> bool:
    return (
        safety.get("public_site_cookie_free") is True
        and safety.get("public_site_receives_sanitized_metadata_only") is True
        and safety.get("handoff_contains_cookie") is False
        and safety.get("handoff_contains_login_token") is False
        and safety.get("handoff_contains_signed_media_url") is False
    )


def _handoff_security_contract_ok(contract: dict) -> bool:
    if not contract:
        return False
    returned_scope = contract.get("returned_data_scope") if isinstance(contract.get("returned_data_scope"), list) else []
    returned_scope_set = {str(item) for item in returned_scope}
    required_scope = {
        "account_visible_metadata",
        "visible_work_list",
        "visible_interaction_metrics",
        "sanitized_source_urls",
    }
    handoff_excludes = contract.get("handoff_excludes") if isinstance(contract.get("handoff_excludes"), list) else []
    excludes_text = " ".join(str(item).lower() for item in handoff_excludes)
    return (
        contract.get("loopback_only") is True
        and contract.get("public_site_cookie_free") is True
        and contract.get("requests_from_user_machine") is True
        and contract.get("uses_user_local_chrome_session") is True
        and contract.get("page_confirmation_required") is True
        and contract.get("one_time_token_required") is True
        and contract.get("cookie_read") is False
        and contract.get("cookie_returned") is False
        and contract.get("cookie_logged") is False
        and contract.get("login_token_returned") is False
        and contract.get("signed_media_url_returned") is False
        and contract.get("raw_headers_returned") is False
        and contract.get("dom_visible_metadata_only") is True
        and contract.get("sensitive_fields_redacted") is True
        and required_scope.issubset(returned_scope_set)
        and "cookie" in excludes_text
        and "login token" in excludes_text
        and "authorization header" in excludes_text
        and "signed media url" in excludes_text
        and "raw request headers" in excludes_text
    )


def _handoff_payload_has_sensitive_sample_data(payload: dict) -> bool:
    for field_name in HANDOFF_TOP_LEVEL_SENSITIVE_FIELDS:
        if _handoff_sensitive_value(payload.get(field_name)):
            return True
    raw_samples = payload.get("samples") if isinstance(payload.get("samples"), list) else []
    for item in raw_samples:
        if not isinstance(item, dict):
            continue
        for field_name in HANDOFF_SAMPLE_SENSITIVE_FIELDS:
            if _handoff_sensitive_value(item.get(field_name)):
                return True
    return _handoff_metadata_tree_has_sensitive_data(payload)


def _handoff_metadata_tree_has_sensitive_data(value: Any, path: tuple[str, ...] = ()) -> bool:
    if path and path[0] in HANDOFF_CONTRACT_SECTIONS:
        return False
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            child_path = (*path, key_text)
            if HANDOFF_DISALLOWED_KEY_RE.search(key_text) and child_path not in HANDOFF_ALLOWED_AUDIT_PATHS:
                return True
            if _handoff_metadata_tree_has_sensitive_data(item, child_path):
                return True
        return False
    if isinstance(value, list):
        return any(_handoff_metadata_tree_has_sensitive_data(item, path) for item in value)
    if not isinstance(value, str):
        return False
    if _handoff_signed_media_url_value(value):
        return True
    parent_key = path[-1] if path else ""
    return parent_key not in HANDOFF_FREE_TEXT_KEYS and _handoff_sensitive_value(value)


def _handoff_sensitive_value(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return bool(HANDOFF_SENSITIVE_RE.search(value))


def _handoff_signed_media_url_value(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in HANDOFF_SIGNED_MEDIA_HOST_SUFFIXES)


def _normalized_handoff_security_contract(payload: dict) -> dict:
    contract = payload.get("security_contract") if isinstance(payload.get("security_contract"), dict) else {}
    returned_scope = contract.get("returned_data_scope") if isinstance(contract.get("returned_data_scope"), list) else []
    return {
        "contract_version": int(_safe_int(contract.get("contract_version")) or 1),
        "scope": _safe_handoff_text(str(contract.get("scope") or "local_helper_to_analysis_web_app"), 80),
        "loopback_only": bool(contract.get("loopback_only", True)),
        "public_site_cookie_free": True,
        "requests_from_user_machine": bool(contract.get("requests_from_user_machine", True)),
        "uses_user_local_chrome_session": bool(contract.get("uses_user_local_chrome_session", False)),
        "page_confirmation_required": bool(contract.get("page_confirmation_required", True)),
        "one_time_token_required": bool(contract.get("one_time_token_required", True)),
        "cookie_read": False,
        "cookie_returned": False,
        "cookie_logged": False,
        "login_token_returned": False,
        "signed_media_url_returned": False,
        "raw_headers_returned": False,
        "dom_visible_metadata_only": True,
        "sensitive_fields_redacted": True,
        "returned_data_scope": [
            _safe_handoff_text(str(item), 80)
            for item in returned_scope
            if str(item)
        ]
        or [
            "account_visible_metadata",
            "visible_work_list",
            "visible_interaction_metrics",
            "sanitized_source_urls",
        ],
        "handoff_excludes": ["Cookie", "login token", "authorization header", "signed media URL", "raw request headers"],
        "permission_note": _safe_handoff_text(
            str(contract.get("permission_note") or "仅用于用户已授权或自有内容的本地学习、复盘和创作者规律分析。"),
            160,
        ),
    }


def _sanitize_handoff_import_payload(payload: dict, sample_set: CloneSampleSet) -> dict:
    capture_audit = payload.get("capture_audit") if isinstance(payload.get("capture_audit"), dict) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    return {
        "handoff_version": int(_safe_int(payload.get("handoff_version")) or 1),
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "set_id": sample_set.set_id,
        "title": sample_set.title,
        "creator_name": sample_set.creator_name,
        "source_platform": sample_set.source_platform,
        "profile_metadata": sample_set.profile_metadata,
        "sample_count": len(sample_set.samples),
        "samples": [sample.to_dict() for sample in sample_set.samples],
        "capture_audit": {
            "audit_version": capture_audit.get("audit_version"),
            "captured_at": _safe_handoff_text(str(capture_audit.get("captured_at") or ""), 80),
            "source_platform": _safe_handoff_text(str(capture_audit.get("source_platform") or sample_set.source_platform), 40),
            "capture_method": _safe_handoff_text(str(capture_audit.get("capture_method") or "handoff_import"), 120),
            "authorization": _safe_handoff_authorization(capture_audit.get("authorization")),
            "scroll_count": _safe_int(capture_audit.get("scroll_count")),
            "captured_count": _safe_int(capture_audit.get("captured_count")),
            "final_sample_count": len(sample_set.samples),
            "media_summary": capture_audit.get("media_summary") if isinstance(capture_audit.get("media_summary"), dict) else {},
        },
        "safety": {
            **safety,
            "handoff_contains_cookie": False,
            "handoff_contains_login_token": False,
            "handoff_contains_signed_media_url": False,
            "public_site_cookie_free": True,
            "public_site_receives_sanitized_metadata_only": True,
        },
        "security_contract": _normalized_handoff_security_contract(payload),
        "handoff_scope": {
            "intended_receiver": "analysis_web_app",
            "contains": ["creator metadata", "sample metadata", "visible engagement metrics", "source work URLs"],
            "excludes": ["Cookie", "login token", "authorization header", "signed media URL", "raw request headers"],
            "permission_note": "仅用于用户已授权或自有内容的本地学习、复盘和创作者规律分析。",
        },
    }


def _safe_handoff_authorization(value) -> dict:
    payload = value if isinstance(value, dict) else {}
    return {
        "page_confirmed": bool(payload.get("page_confirmed")),
        "one_time_token_consumed": bool(payload.get("one_time_token_consumed")),
        "trigger": _safe_handoff_text(str(payload.get("trigger") or "unknown"), 80),
    }


def _safe_handoff_aweme_id(raw: str, source_url: str = "") -> str:
    value = str(raw or "").strip()
    if re.fullmatch(r"\d{15,22}", value):
        return value
    if source_url:
        try:
            return extract_aweme_id(source_url)
        except AppError:
            return ""
    return ""


def _safe_handoff_text(value: str, limit: int = 500) -> str:
    return HANDOFF_SENSITIVE_RE.sub("[redacted]", str(value or ""))[: max(0, int(limit or 500))]


def _safe_public_metadata_text(value: str, limit: int = 500) -> str:
    return _safe_handoff_text(value, limit)


def _safe_public_metadata_url(value: str) -> str:
    raw = _safe_public_metadata_text(str(value or "").strip(), 1000)
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    if _is_private_or_local_handoff_host(parsed.hostname):
        return ""
    return urlunparse((parsed.scheme, _safe_handoff_netloc(parsed), parsed.path or "/", "", "", ""))


def _safe_handoff_object(value):
    if isinstance(value, dict):
        return {str(key)[:80]: _safe_handoff_object(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_handoff_object(item) for item in value[:50]]
    if isinstance(value, str):
        return _safe_handoff_text(value, 500)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _safe_handoff_text(str(value), 500)


def _safe_handoff_url(value: str, *, aweme_id: str = "") -> str:
    raw = _safe_handoff_text(str(value or "").strip(), 1000)
    if not raw:
        return ""
    parsed = urlparse(raw)
    if aweme_id and re.fullmatch(r"\d{15,22}", aweme_id):
        host = (parsed.hostname or "").lower()
        if host == "douyin.com" or host.endswith(".douyin.com"):
            return f"https://www.douyin.com/video/{aweme_id}"
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    if _is_private_or_local_handoff_host(parsed.hostname):
        return ""
    return urlunparse((parsed.scheme, _safe_handoff_netloc(parsed), parsed.path or "/", "", "", ""))


def _safe_handoff_netloc(parsed) -> str:
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parsed.port:
        return f"{host}:{parsed.port}"
    return host


def _is_private_or_local_handoff_host(hostname: str) -> bool:
    host = (hostname or "").strip().lower().strip("[]")
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        address = ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local or address.is_reserved


def _sample_evidence_note(sample: CloneSample) -> str:
    if sample.understanding_level == "full":
        return "该样本有较完整的视频、关键帧和富化证据，可用于表达方式判断。"
    if sample.understanding_level == "partial":
        return "该样本只有部分视频/关键帧/ASR/OCR 证据，结论需谨慎。"
    return "该样本只有元数据，不能假装理解镜头节奏、口播或画面细节。"


def _sample_evidence_status(sample: CloneSample) -> dict:
    asr_checked = sample.asr_status not in {"", "pending", "skipped"}
    ocr_checked = sample.ocr_status not in {"", "pending", "skipped"}
    status = {
        "understanding_level": sample.understanding_level,
        "media_type": sample.media_type,
        "has_video": sample.has_video,
        "has_keyframes": sample.has_frames,
        "has_asr_text": sample.has_asr,
        "has_ocr_text": sample.has_ocr,
        "has_comments": sample.has_comments,
        "enrichment_status": sample.enrichment_status,
        "asr_status": sample.asr_status,
        "ocr_status": sample.ocr_status,
        "analysis_status": sample.analysis_status,
        "asr_checked": asr_checked,
        "ocr_checked": ocr_checked,
        "can_infer_visual_rhythm": bool(sample.has_frames),
        "can_infer_spoken_script": bool(sample.has_asr),
        "can_infer_screen_text": bool(sample.has_ocr),
        "can_use_comment_reaction": bool(sample.has_comments),
        "limits": [],
    }
    if sample.media_type in {"image", "text"}:
        status["limits"].append("非视频样本不能推断镜头运动、动作节奏或口播结构。")
    if not sample.has_frames:
        status["limits"].append("缺少关键帧，不能强推画面节奏。")
    if sample.asr_status == "provider_missing":
        status["limits"].append("ASR provider 未配置，不能把缺少转写等同于无口播。")
    elif sample.asr_status == "no_speech":
        status["limits"].append("ASR 已检查并确认无可转写语音。")
    elif not sample.has_asr:
        status["limits"].append("缺少 ASR 文本，口播/声音判断需要保守。")
    if sample.ocr_status == "provider_missing":
        status["limits"].append("OCR provider 未配置，不能把缺少识别结果等同于无画面文字。")
    elif sample.ocr_status == "no_text":
        status["limits"].append("OCR 已检查并确认无可识别画面文字。")
    elif not sample.has_ocr:
        status["limits"].append("缺少 OCR 文本，字幕/封面字判断需要保守。")
    if not sample.has_comments:
        status["limits"].append("缺少评论样本，互动动机和评论区需求只能推测。")
    return status


def _case_dir_from_sample(sample: CloneSample) -> Path:
    return settings.cases_dir / sample.case_id


def _confidence_label(samples: list[CloneSample]) -> str:
    counts = understanding_counts(samples)
    if counts["full"] >= max(1, len(samples) // 2):
        return "medium_high"
    if counts["partial"] + counts["full"] >= max(1, len(samples) // 2):
        return "medium"
    return "low_metadata_only"


def _deep_merge(target: dict, source: dict) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _status_from_file(path: Path, default: str = "pending") -> str:
    payload = _read_json(path)
    return str(payload.get("status") or default or "pending")


def _write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _row_field(row: dict, *names: str, default=""):
    for name in names:
        current = row
        for part in name.split("."):
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(part)
        if current not in (None, ""):
            return current
    return default


def _tags_from_value(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,，#\s]+", value) if item.strip()]
    return []


def _stable_token(value: str) -> str:
    import hashlib

    return hashlib.sha1((value or uuid.uuid4().hex).encode("utf-8")).hexdigest()[:16]


def _markdown_list(value: Any) -> str:
    items = value if isinstance(value, list) else ([] if not value else [value])
    if not items:
        return "- 暂无"
    lines = []
    for item in items:
        if isinstance(item, dict):
            title = item.get("name") or item.get("title") or item.get("formula_used") or "item"
            detail = "；".join(f"{key}: {val}" for key, val in item.items() if key not in {"name", "title"} and val not in ("", [], {}))
            lines.append(f"- {title}" + (f"：{detail}" if detail else ""))
        else:
            lines.append(f"- {item}")
    return "\n".join(lines)


def _safe_int(value) -> int:
    try:
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0
