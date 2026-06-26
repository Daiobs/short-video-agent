from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.errors import AppError, ErrorCode
from app.models import CaseArtifact


ProgressCallback = Callable[[int, str], None]
ENRICHMENT_VERSION = "1.0"
COMMENT_WORD_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9_]{2,}")


def build_enrichment_archive(
    artifact: CaseArtifact,
    progress: ProgressCallback | None = None,
    capture_method: str = "case_metadata",
    permission_note: str = "local personal analysis",
) -> dict:
    def report(value: int, message: str) -> None:
        if progress:
            progress(value, message)

    try:
        report(10, "准备 enrichment 目录")
        paths = ensure_enrichment_dirs(artifact)
        manifest = load_or_create_manifest(artifact)

        report(35, "写入指标快照")
        snapshot = create_metrics_snapshot(
            artifact,
            capture_method=capture_method,
            permission_note=permission_note,
        )

        report(60, "刷新评论摘要")
        comment_summary = build_comment_summary(artifact)

        report(80, "生成 case 索引")
        case_index = build_case_index(artifact)

        manifest = update_manifest(
            artifact,
            {
                "metrics": _file_status(paths["metrics"] / "snapshots.jsonl"),
                "comments": _comment_status(artifact),
                "index": _file_status(paths["indexes"] / "case_index.json"),
                "asr": _status_from_file(paths["asr"] / "status.json", default="pending"),
                "ocr": _status_from_file(paths["ocr"] / "status.json", default="pending"),
            },
            permission_note=permission_note,
        )
        analysis_input = refresh_analysis_input_enrichment(artifact)
        report(100, "enrichment 归档完成")
        return {
            "manifest": manifest,
            "metrics_snapshot": snapshot,
            "comment_summary": comment_summary,
            "case_index": case_index,
            "analysis_input": analysis_input,
            "paths": enrichment_paths_payload(artifact),
        }
    except AppError:
        raise
    except Exception as error:
        raise AppError(ErrorCode.ENRICHMENT_FAILED, str(error)[:500]) from error


def ensure_enrichment_dirs(artifact: CaseArtifact) -> dict[str, Path]:
    base = enrichment_dir(artifact)
    paths = {
        "base": base,
        "asr": base / "asr",
        "ocr": base / "ocr",
        "comments": base / "comments",
        "metrics": base / "metrics",
        "indexes": base / "indexes",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def enrichment_dir(artifact: CaseArtifact) -> Path:
    return Path(artifact.video_path).parent / "enrichment"


def enrichment_paths_payload(artifact: CaseArtifact) -> dict:
    base = enrichment_dir(artifact)
    return {
        "base": str(base),
        "manifest": str(base / "manifest.json"),
        "asr": {
            "dir": str(base / "asr"),
            "status": str(base / "asr" / "status.json"),
            "audio": str(base / "asr" / "audio.wav"),
            "transcript_json": str(base / "asr" / "transcript.json"),
            "transcript_srt": str(base / "asr" / "transcript.srt"),
            "transcript_txt": str(base / "asr" / "transcript.txt"),
        },
        "ocr": {
            "dir": str(base / "ocr"),
            "status": str(base / "ocr" / "status.json"),
            "frame_ocr": str(base / "ocr" / "frame_ocr.json"),
            "subtitle_ocr": str(base / "ocr" / "subtitle_ocr.json"),
            "cover_ocr": str(base / "ocr" / "cover_ocr.json"),
        },
        "comments": {
            "dir": str(base / "comments"),
            "raw": str(base / "comments" / "comments_raw.jsonl"),
            "clean": str(base / "comments" / "comments_clean.jsonl"),
            "summary": str(base / "comments" / "comment_summary.json"),
        },
        "metrics": {
            "dir": str(base / "metrics"),
            "snapshots": str(base / "metrics" / "snapshots.jsonl"),
        },
        "indexes": {
            "dir": str(base / "indexes"),
            "case_index": str(base / "indexes" / "case_index.json"),
        },
    }


def load_or_create_manifest(artifact: CaseArtifact) -> dict:
    ensure_enrichment_dirs(artifact)
    path = enrichment_dir(artifact) / "manifest.json"
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    manifest = {
        "version": ENRICHMENT_VERSION,
        "case_id": artifact.case_id,
        "local_video_id": artifact.local_video_id,
        "aweme_id": artifact.aweme_id,
        "source_url": _metadata(artifact).get("source_url", ""),
        "created_at": _now(),
        "updated_at": _now(),
        "permission_note": "local personal analysis",
        "artifacts": enrichment_paths_payload(artifact),
        "statuses": {
            "asr": "pending",
            "ocr": "pending",
            "comments": "pending",
            "metrics": "pending",
            "index": "pending",
        },
    }
    _write_json(path, manifest)
    return manifest


def update_manifest(artifact: CaseArtifact, statuses: dict[str, str] | None = None, **extra) -> dict:
    manifest = load_or_create_manifest(artifact)
    manifest["updated_at"] = _now()
    manifest["artifacts"] = enrichment_paths_payload(artifact)
    if statuses:
        manifest.setdefault("statuses", {}).update(statuses)
    manifest.update(extra)
    _write_json(enrichment_dir(artifact) / "manifest.json", manifest)
    return manifest


def create_metrics_snapshot(
    artifact: CaseArtifact,
    capture_method: str = "case_metadata",
    permission_note: str = "local personal analysis",
) -> dict:
    ensure_enrichment_dirs(artifact)
    metadata = _metadata(artifact)
    analysis_input = _analysis_input(artifact)
    stats = analysis_input.get("stats") or {}
    snapshot = {
        "case_id": artifact.case_id,
        "aweme_id": artifact.aweme_id or metadata.get("aweme_id", ""),
        "source_url": metadata.get("source_url") or analysis_input.get("source_url", ""),
        "captured_at": _now(),
        "capture_method": capture_method,
        "permission_note": permission_note,
        "like_count": _int(stats.get("like_count", metadata.get("like_count", 0))),
        "comment_count": _int(stats.get("comment_count", metadata.get("comment_count", 0))),
        "share_count": _int(stats.get("share_count", metadata.get("share_count", 0))),
        "engagement_score": _int(stats.get("engagement_score", metadata.get("engagement_score", 0))),
    }
    _append_jsonl(enrichment_dir(artifact) / "metrics" / "snapshots.jsonl", snapshot)
    update_manifest(artifact, {"metrics": "success"})
    refresh_analysis_input_enrichment(artifact)
    return snapshot


def import_comments(
    artifact: CaseArtifact,
    text: str = "",
    comments: list[dict] | None = None,
    source: str = "manual",
    permission_note: str = "user provided comments",
) -> dict:
    ensure_enrichment_dirs(artifact)
    raw_comments = _comments_from_payload(text=text, comments=comments or [])
    if not raw_comments:
        raise AppError(ErrorCode.COMMENTS_IMPORT_FAILED, "没有可导入的评论。")

    captured_at = _now()
    raw_path = enrichment_dir(artifact) / "comments" / "comments_raw.jsonl"
    clean_path = enrichment_dir(artifact) / "comments" / "comments_clean.jsonl"
    normalized = []
    for item in raw_comments:
        normalized.append(
            {
                "comment_id": str(item.get("comment_id") or f"comment_{uuid.uuid4().hex}"),
                "user": str(item.get("user") or "匿名"),
                "text": _clean_comment_text(str(item.get("text") or "")),
                "likes": _int(item.get("likes", 0)),
                "time": str(item.get("time") or ""),
                "reply_to": item.get("reply_to"),
                "source": source,
                "source_url": (_metadata(artifact).get("source_url") or ""),
                "captured_at": captured_at,
                "capture_method": source,
                "permission_note": permission_note,
            }
        )
    normalized = [item for item in normalized if item["text"]]
    if not normalized:
        raise AppError(ErrorCode.COMMENTS_IMPORT_FAILED, "评论清洗后为空。")
    for item in normalized:
        _append_jsonl(raw_path, item)
        _append_jsonl(clean_path, item)
    summary = build_comment_summary(artifact)
    update_manifest(artifact, {"comments": "success"})
    refresh_analysis_input_enrichment(artifact)
    return {
        "imported_count": len(normalized),
        "summary": summary,
        "paths": enrichment_paths_payload(artifact)["comments"],
    }


def build_comment_summary(artifact: CaseArtifact) -> dict:
    ensure_enrichment_dirs(artifact)
    clean_path = enrichment_dir(artifact) / "comments" / "comments_clean.jsonl"
    comments = _read_jsonl(clean_path)
    words = Counter()
    for item in comments:
        words.update(_comment_words(str(item.get("text") or "")))
    top_comments = sorted(comments, key=lambda item: _int(item.get("likes", 0)), reverse=True)[:10]
    summary = {
        "case_id": artifact.case_id,
        "generated_at": _now(),
        "total_comments": len(comments),
        "total_likes": sum(_int(item.get("likes", 0)) for item in comments),
        "high_frequency_words": [word for word, _count in words.most_common(20)],
        "top_needs": _infer_comment_needs(comments, words),
        "comment_hooks": _infer_comment_hooks(comments, words),
        "top_comments": [
            {
                "text": item.get("text", ""),
                "likes": _int(item.get("likes", 0)),
                "user": item.get("user", "匿名"),
            }
            for item in top_comments
        ],
    }
    _write_json(enrichment_dir(artifact) / "comments" / "comment_summary.json", summary)
    return summary


def build_case_index(artifact: CaseArtifact) -> dict:
    ensure_enrichment_dirs(artifact)
    metadata = _metadata(artifact)
    analysis_input = _analysis_input(artifact)
    ffprobe = _ffprobe(artifact)
    comment_summary = _optional_json(enrichment_dir(artifact) / "comments" / "comment_summary.json", {})
    manifest = load_or_create_manifest(artifact)
    stats = analysis_input.get("stats") or {}
    index = {
        "case_id": artifact.case_id,
        "aweme_id": artifact.aweme_id or metadata.get("aweme_id", ""),
        "local_video_id": artifact.local_video_id,
        "title": metadata.get("title") or analysis_input.get("title", ""),
        "author": metadata.get("author") or analysis_input.get("author", ""),
        "source_url": metadata.get("source_url") or analysis_input.get("source_url", ""),
        "created_at": artifact.created_at.isoformat() if artifact.created_at else "",
        "content_category": analysis_input.get("content_category", ""),
        "content_category_label": analysis_input.get("content_category_label", ""),
        "stats": {
            "like_count": _int(stats.get("like_count", metadata.get("like_count", 0))),
            "comment_count": _int(stats.get("comment_count", metadata.get("comment_count", 0))),
            "share_count": _int(stats.get("share_count", metadata.get("share_count", 0))),
            "engagement_score": _int(stats.get("engagement_score", metadata.get("engagement_score", 0))),
        },
        "video": {
            "duration": ffprobe.get("duration", 0),
            "width": ffprobe.get("width", 0),
            "height": ffprobe.get("height", 0),
            "fps": ffprobe.get("fps", 0),
            "file_size": ffprobe.get("file_size", 0),
        },
        "comments": {
            "total_comments": comment_summary.get("total_comments", 0),
            "high_frequency_words": comment_summary.get("high_frequency_words", []),
            "top_needs": comment_summary.get("top_needs", []),
        },
        "statuses": manifest.get("statuses", {}),
        "searchable_text": "\n".join(
            str(value)
            for value in (
                metadata.get("title", ""),
                metadata.get("author", ""),
                metadata.get("notes", ""),
                analysis_input.get("content_category_label", ""),
                " ".join(comment_summary.get("high_frequency_words", [])),
            )
            if value
        ),
        "paths": enrichment_paths_payload(artifact),
    }
    _write_json(enrichment_dir(artifact) / "indexes" / "case_index.json", index)
    update_manifest(artifact, {"index": "success"})
    return index


def write_asr_provider_missing(artifact: CaseArtifact) -> dict:
    ensure_enrichment_dirs(artifact)
    status = {
        "status": "provider_missing",
        "provider": "",
        "message": "ASR provider 未配置。后续可接入 faster-whisper、whisper.cpp 或 API ASR。",
        "updated_at": _now(),
    }
    _write_json(enrichment_dir(artifact) / "asr" / "status.json", status)
    update_manifest(artifact, {"asr": "provider_missing"})
    refresh_analysis_input_enrichment(artifact)
    return status


def write_ocr_provider_missing(artifact: CaseArtifact) -> dict:
    ensure_enrichment_dirs(artifact)
    status = {
        "status": "provider_missing",
        "provider": "",
        "message": "OCR provider 未配置。后续可接入 PaddleOCR 或 rapidocr-onnxruntime。",
        "updated_at": _now(),
    }
    _write_json(enrichment_dir(artifact) / "ocr" / "status.json", status)
    update_manifest(artifact, {"ocr": "provider_missing"})
    refresh_analysis_input_enrichment(artifact)
    return status


def enrichment_payload(artifact: CaseArtifact) -> dict:
    ensure_enrichment_dirs(artifact)
    return {
        "manifest": load_or_create_manifest(artifact),
        "paths": enrichment_paths_payload(artifact),
        "comment_summary": _optional_json(enrichment_dir(artifact) / "comments" / "comment_summary.json", {}),
        "case_index": _optional_json(enrichment_dir(artifact) / "indexes" / "case_index.json", {}),
        "asr_status": _optional_json(enrichment_dir(artifact) / "asr" / "status.json", {}),
        "asr_transcript": _optional_json(enrichment_dir(artifact) / "asr" / "transcript.json", {}),
        "ocr_status": _optional_json(enrichment_dir(artifact) / "ocr" / "status.json", {}),
        "ocr_frame": _optional_json(enrichment_dir(artifact) / "ocr" / "frame_ocr.json", {}),
        "ocr_subtitle": _optional_json(enrichment_dir(artifact) / "ocr" / "subtitle_ocr.json", {}),
        "ocr_cover": _optional_json(enrichment_dir(artifact) / "ocr" / "cover_ocr.json", {}),
    }


def analysis_enrichment_payload(artifact: CaseArtifact) -> dict:
    """Build a compact enrichment payload safe for LLM prompts and analysis_input.json."""
    base = enrichment_dir(artifact)
    manifest = load_or_create_manifest(artifact)
    transcript = _optional_json(base / "asr" / "transcript.json", {})
    frame_ocr = _optional_json(base / "ocr" / "frame_ocr.json", {})
    subtitle_ocr = _optional_json(base / "ocr" / "subtitle_ocr.json", {})
    cover_ocr = _optional_json(base / "ocr" / "cover_ocr.json", {})
    comment_summary = _optional_json(base / "comments" / "comment_summary.json", {})
    snapshots = _read_jsonl(base / "metrics" / "snapshots.jsonl")
    return {
        "version": ENRICHMENT_VERSION,
        "statuses": manifest.get("statuses", {}),
        "asr": {
            "status": transcript.get("status") or _status_from_file(base / "asr" / "status.json", "pending"),
            "provider": transcript.get("provider", ""),
            "language": transcript.get("language", ""),
            "segment_count": len(transcript.get("segments") or []),
            "full_text": _truncate_text(transcript.get("full_text", ""), 6000),
            "segments": _compact_segments(transcript.get("segments") or [], limit=80),
        },
        "ocr": {
            "status": frame_ocr.get("status") or _status_from_file(base / "ocr" / "status.json", "pending"),
            "frame_text": _truncate_text(frame_ocr.get("full_text", ""), 4000),
            "subtitle_text": _truncate_text(subtitle_ocr.get("full_text", ""), 4000),
            "cover_text": _truncate_text(cover_ocr.get("full_text", ""), 1200),
            "frame_samples": _compact_ocr_frames(frame_ocr.get("frames") or [], limit=20),
            "subtitle_samples": _compact_ocr_frames(subtitle_ocr.get("frames") or [], limit=20),
        },
        "comments": {
            "status": "success" if comment_summary.get("total_comments", 0) else _comment_status(artifact),
            "total_comments": comment_summary.get("total_comments", 0),
            "high_frequency_words": comment_summary.get("high_frequency_words", [])[:20],
            "top_needs": comment_summary.get("top_needs", [])[:10],
            "comment_hooks": comment_summary.get("comment_hooks", [])[:10],
            "top_comments": (comment_summary.get("top_comments") or [])[:10],
        },
        "metrics": {
            "status": "success" if snapshots else "pending",
            "latest_snapshot": snapshots[-1] if snapshots else {},
            "snapshot_count": len(snapshots),
        },
    }


def refresh_analysis_input_enrichment(artifact: CaseArtifact) -> dict:
    analysis_input_path = Path(artifact.analysis_input_path)
    analysis_input = _read_json(analysis_input_path)
    analysis_input["analysis_enrichment"] = analysis_enrichment_payload(artifact)
    _write_json(analysis_input_path, analysis_input)
    return analysis_input


def _metadata(artifact: CaseArtifact) -> dict:
    return _read_json(Path(artifact.metadata_path))


def _analysis_input(artifact: CaseArtifact) -> dict:
    return _read_json(Path(artifact.analysis_input_path))


def _ffprobe(artifact: CaseArtifact) -> dict:
    return _read_json(Path(artifact.ffprobe_path))


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file_obj:
        file_obj.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _optional_json(path: Path, default: dict) -> dict:
    return _read_json(path) if path.is_file() else default


def _comments_from_payload(text: str, comments: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for item in comments:
        if isinstance(item, dict):
            rows.append(dict(item))
    for line in (text or "").splitlines():
        value = line.strip()
        if not value:
            continue
        parsed = None
        if value.startswith("{") and value.endswith("}"):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = None
        if isinstance(parsed, dict):
            rows.append(parsed)
        else:
            rows.append({"text": value})
    return rows


def _clean_comment_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _comment_words(value: str) -> list[str]:
    return [match.group(0) for match in COMMENT_WORD_RE.finditer(value)]


def _infer_comment_needs(comments: list[dict], words: Counter) -> list[str]:
    text = "\n".join(str(item.get("text") or "") for item in comments)
    needs = []
    if any(word in text for word in ("同款", "链接", "怎么买", "哪里买")):
        needs.append("求同款/购买线索")
    if any(word in text for word in ("接", "好运", "希望", "许愿")):
        needs.append("情绪许愿/好运认同")
    if any(word in text for word in ("真实", "扎心", "哭", "破防")):
        needs.append("情感共鸣")
    if any(word in text for word in ("不对", "争议", "凭什么", "离谱")):
        needs.append("争议讨论")
    for word, _count in words.most_common(8):
        if word not in needs:
            needs.append(word)
    return needs[:8]


def _infer_comment_hooks(comments: list[dict], words: Counter) -> list[str]:
    hooks = []
    needs = _infer_comment_needs(comments, words)
    if "情感共鸣" in needs:
        hooks.append("用户会围绕自身经历表达共鸣。")
    if "情绪许愿/好运认同" in needs:
        hooks.append("用户会在评论区许愿、接好运或寻求情绪确认。")
    if "求同款/购买线索" in needs:
        hooks.append("评论区可能产生同款、链接和购买需求。")
    if "争议讨论" in needs:
        hooks.append("内容具备引发观点对立和讨论的潜力。")
    if not hooks and comments:
        hooks.append("可从高赞评论中提炼二次选题或评论区互动引导。")
    return hooks


def _file_status(path: Path) -> str:
    return "success" if path.is_file() and path.stat().st_size > 0 else "pending"


def _comment_status(artifact: CaseArtifact) -> str:
    clean_path = enrichment_dir(artifact) / "comments" / "comments_clean.jsonl"
    return "success" if clean_path.is_file() and clean_path.stat().st_size > 0 else "pending"


def _status_from_file(path: Path, default: str) -> str:
    data = _optional_json(path, {})
    return str(data.get("status") or default)


def _compact_segments(segments: list[dict], limit: int) -> list[dict]:
    compact = []
    for item in segments[: max(0, limit)]:
        text = _truncate_text(item.get("text", ""), 300)
        if not text:
            continue
        compact.append(
            {
                "start": item.get("start", 0),
                "end": item.get("end", 0),
                "text": text,
            }
        )
    return compact


def _compact_ocr_frames(frames: list[dict], limit: int) -> list[dict]:
    compact = []
    for item in frames[: max(0, limit)]:
        text = _truncate_text(item.get("text", ""), 300)
        if not text:
            continue
        compact.append(
            {
                "frame_time": item.get("frame_time", 0),
                "region": item.get("region", ""),
                "text": text,
            }
        )
    return compact


def _truncate_text(value, limit: int) -> str:
    text = str(value or "").strip()
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
