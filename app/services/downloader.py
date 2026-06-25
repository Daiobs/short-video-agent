from __future__ import annotations

import time
import uuid
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import AppError, ErrorCode
from app.models import DouyinVideoItem, LocalVideoItem
from app.services.quality_resolver import get_candidate_or_error
from app.services.video_importer import engagement_score


def _host_allowed(host: str) -> bool:
    host = (host or "").lower()
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in settings.allowed_cdn_hosts)


def _validate_candidate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise AppError(ErrorCode.HOST_NOT_ALLOWED)
    if not _host_allowed(parsed.hostname or ""):
        raise AppError(ErrorCode.HOST_NOT_ALLOWED)


def _next_response(client: httpx.Client, url: str) -> httpx.Response:
    current_url = url
    for _ in range(5):
        _validate_candidate_url(current_url)
        request = client.build_request("GET", current_url)
        response = client.send(request, stream=True)
        if response.is_redirect:
            location = response.headers.get("Location") or ""
            response.close()
            if not location:
                raise AppError(ErrorCode.DOWNLOAD_FAILED, "下载响应缺少跳转地址。")
            next_url = urljoin(str(response.url), location)
            parsed = urlparse(next_url)
            if parsed.scheme != "https" or not _host_allowed(parsed.hostname or ""):
                raise AppError(ErrorCode.REDIRECT_HOST_NOT_ALLOWED)
            current_url = next_url
            continue
        return response
    raise AppError(ErrorCode.DOWNLOAD_FAILED, "下载跳转次数过多。")


def _validate_response(response: httpx.Response) -> tuple[int, int]:
    if response.status_code >= 400:
        raise AppError(ErrorCode.DOWNLOAD_FAILED, f"下载失败，HTTP {response.status_code}。")
    content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
    if not (content_type.startswith("video/") or content_type == "application/octet-stream"):
        raise AppError(ErrorCode.CONTENT_TYPE_INVALID)
    content_length = int(response.headers.get("Content-Length") or "0")
    max_bytes = settings.max_video_size_mb * 1024 * 1024
    if content_length and content_length > max_bytes:
        raise AppError(ErrorCode.CONTENT_LENGTH_TOO_LARGE)
    return max_bytes, content_length


def download_candidate(db: Session, aweme_id: str, candidate_id: str, progress=None) -> dict:
    candidate = get_candidate_or_error(db, aweme_id, candidate_id)
    _validate_candidate_url(candidate.url)

    settings.downloads_dir.mkdir(parents=True, exist_ok=True)
    download_id = f"download_{uuid.uuid4().hex}"
    output_path = settings.downloads_dir / f"{aweme_id}_{download_id}.mp4"

    try:
        with httpx.Client(
            timeout=settings.download_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            headers={
                "Accept": "*/*",
                "Referer": "https://www.douyin.com/",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            },
        ) as client:
            response = _next_response(client, candidate.url)
            try:
                max_bytes, content_length = _validate_response(response)
                written = 0
                last_progress = 10
                if progress:
                    progress(last_progress, "正在下载视频")
                with output_path.open("wb") as file_obj:
                    for chunk in response.iter_bytes():
                        if not chunk:
                            continue
                        written += len(chunk)
                        if written > max_bytes:
                            output_path.unlink(missing_ok=True)
                            raise AppError(ErrorCode.CONTENT_LENGTH_TOO_LARGE)
                        file_obj.write(chunk)
                        if progress and content_length:
                            current_progress = 10 + int(min(written, content_length) / content_length * 80)
                            if current_progress >= last_progress + 2:
                                last_progress = current_progress
                                progress(current_progress, f"正在下载视频 {current_progress}%")
                if progress:
                    progress(95, "下载已保存，正在登记")
            finally:
                response.close()
    except httpx.TimeoutException as error:
        output_path.unlink(missing_ok=True)
        raise AppError(ErrorCode.DOWNLOAD_TIMEOUT) from error
    except AppError:
        output_path.unlink(missing_ok=True)
        raise
    except Exception as error:
        output_path.unlink(missing_ok=True)
        raise AppError(ErrorCode.DOWNLOAD_FAILED, str(error)[:500]) from error

    if output_path.stat().st_size <= 0:
        output_path.unlink(missing_ok=True)
        raise AppError(ErrorCode.DOWNLOAD_FAILED, "下载文件为空。")

    douyin_item = db.get(DouyinVideoItem, aweme_id)
    local_video_id = f"local_{uuid.uuid4().hex}"
    local_item = LocalVideoItem(
        local_video_id=local_video_id,
        title=(douyin_item.title if douyin_item else f"抖音作品 {aweme_id}"),
        file_path=str(output_path),
        source_url=(douyin_item.source_url if douyin_item else f"https://www.douyin.com/video/{aweme_id}"),
        author=(douyin_item.author if douyin_item else ""),
        like_count=(douyin_item.like_count if douyin_item else 0),
        comment_count=(douyin_item.comment_count if douyin_item else 0),
        share_count=(douyin_item.share_count if douyin_item else 0),
        engagement_score=engagement_score(
            douyin_item.like_count if douyin_item else 0,
            douyin_item.comment_count if douyin_item else 0,
            douyin_item.share_count if douyin_item else 0,
        ),
        create_time=(douyin_item.create_time if douyin_item else ""),
        remark=f"Downloaded from candidate {candidate.candidate_id} at {int(time.time())}",
    )
    db.add(local_item)
    db.commit()
    db.refresh(local_item)

    return {
        "download_id": download_id,
        "aweme_id": aweme_id,
        "candidate_id": candidate_id,
        "file_path": str(output_path),
        "size_bytes": output_path.stat().st_size,
        "local_video_id": local_item.local_video_id,
    }
