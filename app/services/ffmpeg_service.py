from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.config import settings
from app.errors import AppError, ErrorCode


def _require_binary(name: str, error_code: str) -> str:
    path = shutil.which(name)
    if not path:
        raise AppError(error_code)
    return path


def ensure_ffmpeg_available() -> None:
    _require_binary("ffmpeg", ErrorCode.FFMPEG_NOT_FOUND)
    _require_binary("ffprobe", ErrorCode.FFMPEG_NOT_FOUND)


def _parse_fps(value: str) -> float:
    if not value or value == "0/0":
        return 0.0
    if "/" in value:
        left, right = value.split("/", 1)
        try:
            denominator = float(right)
            return float(left) / denominator if denominator else 0.0
        except ValueError:
            return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def probe_video(video_path: Path) -> dict:
    _require_binary("ffprobe", ErrorCode.FFMPEG_NOT_FOUND)
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except subprocess.TimeoutExpired as error:
        raise AppError(ErrorCode.FFPROBE_FAILED, "ffprobe 执行超时。") from error
    if result.returncode != 0:
        raise AppError(ErrorCode.FFPROBE_FAILED, (result.stderr or result.stdout)[:500])

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise AppError(ErrorCode.FFPROBE_FAILED, "ffprobe 返回了无效 JSON。") from error

    streams = payload.get("streams") or []
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
    fmt = payload.get("format") or {}
    duration = float(fmt.get("duration") or video_stream.get("duration") or 0)
    return {
        "duration": duration,
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "fps": _parse_fps(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate") or ""),
        "video_codec": video_stream.get("codec_name") or "",
        "audio_codec": audio_stream.get("codec_name") or "",
        "bitrate": int(fmt.get("bit_rate") or video_stream.get("bit_rate") or 0),
        "format": fmt.get("format_name") or "",
        "file_size": int(fmt.get("size") or video_path.stat().st_size),
    }


def normalize_case_video(source: Path, destination: Path) -> None:
    _require_binary("ffmpeg", ErrorCode.FFMPEG_NOT_FOUND)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".mp4":
        shutil.copy2(source, destination)
        return

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-c",
        "copy",
        str(destination),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    if result.returncode != 0:
        raise AppError(ErrorCode.CASE_BUILD_FAILED, (result.stderr or result.stdout)[:500])


def plan_keyframe_timestamps(duration: float) -> list[float]:
    max_count = max(1, settings.keyframe_max_count)
    interval = max(0.1, settings.keyframe_interval_seconds)
    if duration <= 0:
        return [0.0]
    if duration <= max_count * interval:
        count = min(max_count, max(1, int(math.ceil(duration / interval))))
        return [round(index * interval, 2) for index in range(count)]
    step = duration / max_count
    return [round(index * step, 2) for index in range(max_count)]


def extract_keyframes(video_path: Path, output_dir: Path, duration: float) -> list[dict]:
    _require_binary("ffmpeg", ErrorCode.FFMPEG_NOT_FOUND)
    output_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for index, timestamp in enumerate(plan_keyframe_timestamps(duration)):
        frame_name = f"frame_{index:04d}_{timestamp:05.2f}s.jpg"
        frame_path = output_dir / frame_name
        command = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{timestamp:.2f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(frame_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        if result.returncode != 0 or not frame_path.exists():
            raise AppError(ErrorCode.KEYFRAME_EXTRACT_FAILED, (result.stderr or result.stdout)[:500])
        frames.append({"index": index, "timestamp": timestamp, "path": str(frame_path)})
    return frames


def build_contact_sheet(frames: list[dict], output_path: Path) -> None:
    if not frames:
        raise AppError(ErrorCode.KEYFRAME_EXTRACT_FAILED, "没有可用于 contact sheet 的关键帧。")

    thumb_width = 240
    label_height = 28
    columns = min(5, max(1, len(frames)))
    rows = math.ceil(len(frames) / columns)
    thumbnails: list[tuple[Image.Image, str]] = []

    for frame in frames:
        image = Image.open(frame["path"]).convert("RGB")
        ratio = thumb_width / image.width
        thumb_height = max(1, int(image.height * ratio))
        image = image.resize((thumb_width, thumb_height))
        label = f"{frame['timestamp']:.2f}s"
        thumbnails.append((image, label))

    thumb_height = max(image.height for image, _ in thumbnails)
    sheet = Image.new("RGB", (columns * thumb_width, rows * (thumb_height + label_height)), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()

    for index, (image, label) in enumerate(thumbnails):
        row = index // columns
        col = index % columns
        x = col * thumb_width
        y = row * (thumb_height + label_height)
        sheet.paste(image, (x, y))
        draw.rectangle((x, y + thumb_height, x + thumb_width, y + thumb_height + label_height), fill=(245, 245, 245))
        draw.text((x + 8, y + thumb_height + 8), label, fill=(20, 20, 20), font=font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, quality=92)

