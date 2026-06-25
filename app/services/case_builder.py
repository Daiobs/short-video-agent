from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from app.config import settings
from app.errors import AppError, ErrorCode
from app.models import CaseArtifact, LocalVideoItem
from app.services.analysis_taxonomy import (
    BASE_ANALYSIS_FOCUS,
    build_analysis_context,
    build_prompt,
    infer_content_category,
)
from app.services.analysis_worksheet import build_default_worksheet, render_analysis_brief
from app.services.douyin_url_parser import extract_aweme_id
from app.services.ffmpeg_service import (
    build_contact_sheet,
    ensure_ffmpeg_available,
    extract_keyframes,
    normalize_case_video,
    probe_video,
)

ProgressCallback = Callable[[int, str], None]


def _write_json(path: Path, payload: dict | list) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _relative_or_absolute(path: Path) -> str:
    try:
        return str(path.relative_to(settings.project_root))
    except ValueError:
        return str(path)


def _extract_optional_aweme_id(value: str) -> str:
    try:
        return extract_aweme_id(value)
    except AppError:
        return ""


def build_case_from_local_video(
    db: Session,
    local_video_id: str,
    progress: ProgressCallback | None = None,
) -> CaseArtifact:
    def report(value: int, message: str) -> None:
        if progress:
            progress(value, message)

    local_video = db.get(LocalVideoItem, local_video_id)
    if not local_video:
        raise AppError(ErrorCode.INVALID_VIDEO_FILE, "未找到本地视频记录。")

    source_path = Path(local_video.file_path)
    if not source_path.is_file() or source_path.stat().st_size <= 0:
        raise AppError(ErrorCode.INVALID_VIDEO_FILE)

    case_id = f"case_{uuid.uuid4().hex}"
    case_dir = settings.cases_dir / case_id
    keyframes_dir = case_dir / "keyframes"
    video_path = case_dir / "video.mp4"
    case_dir.mkdir(parents=True, exist_ok=False)

    try:
        report(5, "检查 ffmpeg/ffprobe")
        ensure_ffmpeg_available()

        report(15, "复制并规范化视频")
        normalize_case_video(source_path, video_path)

        report(30, "读取视频元数据")
        ffprobe = probe_video(video_path)
        ffprobe_path = case_dir / "ffprobe.json"
        _write_json(ffprobe_path, ffprobe)

        report(50, "抽取关键帧")
        frames = extract_keyframes(video_path, keyframes_dir, float(ffprobe.get("duration") or 0))

        report(65, "生成 contact sheet")
        contact_sheet_path = case_dir / "contact_sheet.jpg"
        build_contact_sheet(frames, contact_sheet_path)

        imported_at = datetime.now(timezone.utc).isoformat()
        aweme_id = _extract_optional_aweme_id(local_video.source_url)
        category_id = infer_content_category(
            " ".join(
                [
                    local_video.title or "",
                    local_video.remark or "",
                    local_video.author or "",
                    local_video.source_url or "",
                ]
            )
        )
        analysis_context = build_analysis_context(category_id)
        metadata = {
            "aweme_id": aweme_id,
            "local_video_id": local_video.local_video_id,
            "title": local_video.title,
            "author": local_video.author,
            "source_url": local_video.source_url,
            "like_count": local_video.like_count,
            "comment_count": local_video.comment_count,
            "share_count": local_video.share_count,
            "engagement_score": local_video.engagement_score,
            "create_time": local_video.create_time,
            "imported_at": imported_at,
            "provider": "local",
            "notes": local_video.remark,
            "content_category": analysis_context["category_id"],
            "content_category_label": analysis_context["label"],
        }
        qualities = {"source": "local", "candidates": []}
        analysis_input = {
            "case_id": case_id,
            "aweme_id": aweme_id,
            "local_video_id": local_video.local_video_id,
            "title": local_video.title,
            "source_url": local_video.source_url,
            "author": local_video.author,
            "stats": {
                "like_count": local_video.like_count,
                "comment_count": local_video.comment_count,
                "share_count": local_video.share_count,
                "engagement_score": local_video.engagement_score,
            },
            "video": {
                "duration": ffprobe.get("duration", 0),
                "width": ffprobe.get("width", 0),
                "height": ffprobe.get("height", 0),
                "fps": ffprobe.get("fps", 0),
                "bitrate": ffprobe.get("bitrate", 0),
                "file_size": ffprobe.get("file_size", 0),
            },
            "assets": {
                "video_path": _relative_or_absolute(video_path),
                "keyframes_dir": _relative_or_absolute(keyframes_dir),
                "keyframes": [
                    {
                        "index": frame["index"],
                        "timestamp": frame["timestamp"],
                        "path": _relative_or_absolute(Path(frame["path"])),
                    }
                    for frame in frames
                ],
                "contact_sheet": _relative_or_absolute(contact_sheet_path),
                "ffprobe": _relative_or_absolute(ffprobe_path),
            },
            "content_category": analysis_context["category_id"],
            "content_category_label": analysis_context["label"],
            "analysis_context": analysis_context,
            "analysis_lens": analysis_context["analysis_lens"],
            "key_questions": analysis_context["key_questions"],
            "content_ratio": analysis_context["content_ratio"],
            "analysis_focus": list(BASE_ANALYSIS_FOCUS),
        }

        report(80, "写入素材包 JSON 和 prompt")
        metadata_path = case_dir / "metadata.json"
        qualities_path = case_dir / "qualities.json"
        analysis_input_path = case_dir / "analysis_input.json"
        prompt_path = case_dir / "prompt.md"
        worksheet_path = case_dir / "worksheet.json"
        analysis_brief_path = case_dir / "analysis_brief.md"
        readme_path = case_dir / "README.md"
        worksheet = build_default_worksheet(case_id, analysis_input)
        _write_json(metadata_path, metadata)
        _write_json(qualities_path, qualities)
        _write_json(analysis_input_path, analysis_input)
        _write_json(worksheet_path, worksheet)
        prompt_path.write_text(build_prompt(metadata, ffprobe, analysis_context), encoding="utf-8")
        analysis_brief_path.write_text(
            render_analysis_brief(metadata, ffprobe, analysis_input, worksheet),
            encoding="utf-8",
        )
        readme_path.write_text(
            "# 短视频分析素材包\n\n"
            "本目录由 short-video-agent 生成，用于本地学习、复盘和内容分析。\n\n"
            "- `video.mp4`：分析用视频文件\n"
            "- `metadata.json`：手动填写或导入的作品元数据\n"
            "- `ffprobe.json`：视频技术参数\n"
            "- `analysis_input.json`：给 LLM 的结构化输入\n"
            "- `prompt.md`：按内容类型生成的爆款案例拆解 Prompt 模板\n"
            "- `worksheet.json`：本地人工拆解工作表\n"
            "- `analysis_brief.md`：可复制、可沉淀的分析工作表文本\n"
            "- `contact_sheet.jpg`：关键帧总览图\n"
            "- `keyframes/`：按时间抽取的关键帧\n",
            encoding="utf-8",
        )

        artifact = CaseArtifact(
            case_id=case_id,
            aweme_id=aweme_id,
            local_video_id=local_video.local_video_id,
            video_path=str(video_path),
            metadata_path=str(metadata_path),
            qualities_path=str(qualities_path),
            ffprobe_path=str(ffprobe_path),
            analysis_input_path=str(analysis_input_path),
            prompt_path=str(prompt_path),
            contact_sheet_path=str(contact_sheet_path),
            keyframes_dir=str(keyframes_dir),
            status="success",
        )
        db.add(artifact)
        db.commit()
        db.refresh(artifact)
        report(100, "素材包生成完成")
        return artifact
    except AppError:
        shutil.rmtree(case_dir, ignore_errors=True)
        raise
    except Exception as error:
        shutil.rmtree(case_dir, ignore_errors=True)
        raise AppError(ErrorCode.CASE_BUILD_FAILED, str(error)[:500]) from error
