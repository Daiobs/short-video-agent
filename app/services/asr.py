from __future__ import annotations

import importlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from app.config import settings
from app.errors import AppError, ErrorCode
from app.models import CaseArtifact
from app.services.enrichment import ensure_enrichment_dirs, refresh_analysis_input_enrichment, update_manifest


ProgressCallback = Callable[[int, str], None]


class ASRProvider(Protocol):
    provider_name: str

    def transcribe(self, audio_path: Path) -> dict:
        ...


class FasterWhisperProvider:
    provider_name = "faster-whisper"

    def __init__(
        self,
        model_size: str = "",
        device: str = "",
        compute_type: str = "",
        language: str = "",
        beam_size: int = 5,
    ) -> None:
        self.model_size = model_size or settings.asr_model_size
        self.device = device or settings.asr_device
        self.compute_type = compute_type or settings.asr_compute_type
        self.language = language or settings.asr_language or None
        self.beam_size = beam_size or settings.asr_beam_size

    def transcribe(self, audio_path: Path) -> dict:
        try:
            module = importlib.import_module("faster_whisper")
        except ImportError as error:
            raise AppError(
                ErrorCode.ASR_PROVIDER_NOT_CONFIGURED,
                "未安装 faster-whisper。请先安装 requirements-asr.txt，或保持 ASR_PROVIDER=disabled。",
            ) from error

        model_kwargs = {}
        if self.device and self.device != "auto":
            model_kwargs["device"] = self.device
        if self.compute_type and self.compute_type != "default":
            model_kwargs["compute_type"] = self.compute_type

        try:
            model = module.WhisperModel(self.model_size, **model_kwargs)
            segments_iter, info = model.transcribe(
                str(audio_path),
                language=self.language or None,
                beam_size=self.beam_size,
                vad_filter=True,
            )
            segments = []
            for index, segment in enumerate(segments_iter):
                text = str(getattr(segment, "text", "") or "").strip()
                if not text:
                    continue
                segments.append(
                    {
                        "index": index,
                        "start": round(float(getattr(segment, "start", 0.0) or 0.0), 3),
                        "end": round(float(getattr(segment, "end", 0.0) or 0.0), 3),
                        "text": text,
                        "confidence": None,
                    }
                )
        except AppError:
            raise
        except Exception as error:
            raise AppError(ErrorCode.ASR_FAILED, str(error)[:500]) from error

        language = getattr(info, "language", None) or self.language or ""
        language_probability = getattr(info, "language_probability", None)
        return {
            "provider": self.provider_name,
            "model": self.model_size,
            "language": language,
            "language_probability": language_probability,
            "segments": segments,
            "full_text": "\n".join(item["text"] for item in segments).strip(),
        }


def run_case_asr(
    artifact: CaseArtifact,
    provider: ASRProvider | None = None,
    progress: ProgressCallback | None = None,
) -> dict:
    def report(value: int, message: str) -> None:
        if progress:
            progress(value, message)

    paths = ensure_enrichment_dirs(artifact)
    asr_dir = paths["asr"]
    audio_path = asr_dir / "audio.wav"

    try:
        report(10, "检查 ASR provider")
        selected_provider = provider or _configured_provider()

        report(25, "准备抽取音频")
        _extract_audio(Path(artifact.video_path), audio_path)
        report(45, "音频已抽取，准备语音识别")

        transcript = selected_provider.transcribe(audio_path)
        report(80, "语音识别完成，写入转写文件")

        status = "success" if transcript.get("full_text") else "no_speech"
        transcript["status"] = status
        transcript["generated_at"] = _now()
        transcript["audio_path"] = str(audio_path)

        transcript_json = asr_dir / "transcript.json"
        transcript_txt = asr_dir / "transcript.txt"
        transcript_srt = asr_dir / "transcript.srt"
        status_path = asr_dir / "status.json"

        _write_json(transcript_json, transcript)
        transcript_txt.write_text(transcript.get("full_text", ""), encoding="utf-8")
        transcript_srt.write_text(_segments_to_srt(transcript.get("segments") or []), encoding="utf-8")
        _write_json(
            status_path,
            {
                "status": status,
                "provider": transcript.get("provider", ""),
                "model": transcript.get("model", ""),
                "language": transcript.get("language", ""),
                "segment_count": len(transcript.get("segments") or []),
                "message": "语音识别完成。" if status == "success" else "未检测到可转写语音。",
                "updated_at": _now(),
            },
        )
        update_manifest(artifact, {"asr": status})
        refresh_analysis_input_enrichment(artifact)
        report(100, "ASR 完成")
        return {
            "status": status,
            "audio_path": str(audio_path),
            "transcript_json": str(transcript_json),
            "transcript_srt": str(transcript_srt),
            "transcript_txt": str(transcript_txt),
            "transcript": transcript,
        }
    except AppError as error:
        _write_json(
            asr_dir / "status.json",
            {
                "status": "failed" if error.code != ErrorCode.ASR_PROVIDER_NOT_CONFIGURED else "provider_missing",
                "provider": settings.asr_provider,
                "error_code": error.code,
                "message": error.message,
                "updated_at": _now(),
            },
        )
        update_manifest(
            artifact,
            {"asr": "provider_missing" if error.code == ErrorCode.ASR_PROVIDER_NOT_CONFIGURED else "failed"},
        )
        refresh_analysis_input_enrichment(artifact)
        raise
    except Exception as error:
        app_error = AppError(ErrorCode.ASR_FAILED, str(error)[:500])
        _write_json(
            asr_dir / "status.json",
            {
                "status": "failed",
                "provider": settings.asr_provider,
                "error_code": app_error.code,
                "message": app_error.message,
                "updated_at": _now(),
            },
        )
        update_manifest(artifact, {"asr": "failed"})
        refresh_analysis_input_enrichment(artifact)
        raise app_error from error


def _configured_provider() -> ASRProvider:
    provider_name = settings.asr_provider
    if provider_name in {"", "disabled", "none", "off"}:
        raise AppError(
            ErrorCode.ASR_PROVIDER_NOT_CONFIGURED,
            "ASR 未启用。请在 .env 中设置 ASR_PROVIDER=auto 或 ASR_PROVIDER=faster_whisper，并安装 requirements-asr.txt。",
        )
    if provider_name == "auto":
        if importlib.util.find_spec("faster_whisper"):
            return FasterWhisperProvider()
        raise AppError(
            ErrorCode.ASR_PROVIDER_NOT_CONFIGURED,
            "ASR_PROVIDER=auto 但未检测到 faster-whisper。请安装 requirements-asr.txt，或将 ASR_PROVIDER 设为 disabled。",
        )
    if provider_name in {"faster_whisper", "faster-whisper"}:
        return FasterWhisperProvider()
    raise AppError(ErrorCode.ASR_PROVIDER_NOT_CONFIGURED, f"不支持的 ASR_PROVIDER：{provider_name}")


def _extract_audio(video_path: Path, audio_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise AppError(ErrorCode.FFMPEG_NOT_FOUND)
    if not video_path.is_file():
        raise AppError(ErrorCode.ASR_FAILED, "视频文件不存在，无法抽取音频。")
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        str(audio_path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
    except subprocess.TimeoutExpired as error:
        raise AppError(ErrorCode.ASR_FAILED, "音频抽取超时。") from error
    if result.returncode != 0 or not audio_path.is_file():
        message = (result.stderr or result.stdout or "音频抽取失败。")[:500]
        raise AppError(ErrorCode.ASR_FAILED, message)


def _segments_to_srt(segments: list[dict]) -> str:
    blocks = []
    for index, segment in enumerate(segments, start=1):
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{_srt_timestamp(segment.get('start', 0))} --> {_srt_timestamp(segment.get('end', 0))}",
                    text,
                ]
            )
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _srt_timestamp(value) -> str:
    seconds = max(0.0, float(value or 0.0))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    whole_seconds = int(seconds % 60)
    milliseconds = int(round((seconds - int(seconds)) * 1000))
    if milliseconds >= 1000:
        whole_seconds += 1
        milliseconds -= 1000
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def _write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
