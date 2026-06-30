from __future__ import annotations

import importlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from PIL import Image

from app.config import settings
from app.errors import AppError, ErrorCode
from app.models import CaseArtifact
from app.services.enrichment import ensure_enrichment_dirs, refresh_analysis_input_enrichment, update_manifest


ProgressCallback = Callable[[int, str], None]
FRAME_TIMESTAMP_RE = re.compile(r"frame_\d+_([0-9.]+)s\.jpg$")


class OCRProvider(Protocol):
    provider_name: str

    def recognize(self, image_path: Path) -> list[dict]:
        ...


class RapidOCRProvider:
    provider_name = "rapidocr"

    def __init__(self, language: str = "") -> None:
        self.language = language or settings.ocr_language
        self._engine = None

    def recognize(self, image_path: Path) -> list[dict]:
        engine = self._load_engine()
        try:
            output = engine(str(image_path))
        except Exception as error:
            raise AppError(ErrorCode.OCR_FAILED, str(error)[:500]) from error
        return _normalize_rapidocr_output(output)

    def _load_engine(self):
        if self._engine is not None:
            return self._engine
        try:
            module = importlib.import_module("rapidocr_onnxruntime")
        except ImportError:
            try:
                module = importlib.import_module("rapidocr")
            except ImportError as error:
                raise AppError(
                    ErrorCode.OCR_PROVIDER_NOT_CONFIGURED,
                    "未安装 rapidocr-onnxruntime。请先安装 requirements-ocr.txt，或保持 OCR_PROVIDER=disabled。",
                ) from error
        try:
            rapid_ocr = getattr(module, "RapidOCR")
            self._engine = rapid_ocr()
        except Exception as error:
            raise AppError(ErrorCode.OCR_FAILED, str(error)[:500]) from error
        return self._engine


def run_case_ocr(
    artifact: CaseArtifact,
    provider: OCRProvider | None = None,
    progress: ProgressCallback | None = None,
) -> dict:
    def report(value: int, message: str) -> None:
        if progress:
            progress(value, message)

    paths = ensure_enrichment_dirs(artifact)
    ocr_dir = paths["ocr"]
    crops_dir = ocr_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    try:
        report(10, "检查 OCR provider")
        selected_provider = provider or _configured_provider()
        keyframes = _selected_keyframes(artifact)
        if not keyframes:
            raise AppError(ErrorCode.OCR_FAILED, "关键帧不存在，无法执行 OCR。")

        report(25, "识别封面替代帧")
        cover_result = _recognize_frame(
            selected_provider,
            keyframes[0],
            region="cover_proxy",
            crop_path=None,
        )

        frame_results = []
        subtitle_results = []
        total = len(keyframes)
        for index, frame_path in enumerate(keyframes):
            base_progress = 30 + int((index / max(1, total)) * 55)
            report(base_progress, f"识别关键帧 {index + 1}/{total}")
            frame_results.append(
                _recognize_frame(
                    selected_provider,
                    frame_path,
                    region="full_frame",
                    crop_path=None,
                )
            )
            crop_path = _crop_subtitle_region(frame_path, crops_dir / f"{frame_path.stem}_bottom.jpg")
            subtitle_results.append(
                _recognize_frame(
                    selected_provider,
                    frame_path,
                    region="subtitle_bottom",
                    crop_path=crop_path,
                )
            )

        report(90, "写入 OCR 结果")
        frame_text = _join_text(frame_results)
        subtitle_text = _join_text(subtitle_results)
        cover_text = _join_text([cover_result])
        status = "success" if frame_text or subtitle_text or cover_text else "no_text"

        frame_payload = {
            "status": status,
            "provider": selected_provider.provider_name,
            "generated_at": _now(),
            "frames": frame_results,
            "full_text": frame_text,
        }
        subtitle_payload = {
            "status": status,
            "provider": selected_provider.provider_name,
            "generated_at": _now(),
            "frames": subtitle_results,
            "full_text": subtitle_text,
        }
        cover_payload = {
            "status": "success" if cover_text else "no_text",
            "provider": selected_provider.provider_name,
            "generated_at": _now(),
            "source": "first_keyframe",
            "frame": cover_result,
            "full_text": cover_text,
        }

        _write_json(ocr_dir / "frame_ocr.json", frame_payload)
        _write_json(ocr_dir / "subtitle_ocr.json", subtitle_payload)
        _write_json(ocr_dir / "cover_ocr.json", cover_payload)
        _write_json(
            ocr_dir / "status.json",
            {
                "status": status,
                "provider": selected_provider.provider_name,
                "frame_count": len(frame_results),
                "text_count": _text_count(frame_results) + _text_count(subtitle_results),
                "message": "OCR 完成。" if status == "success" else "未检测到画面文字。",
                "updated_at": _now(),
            },
        )
        update_manifest(artifact, {"ocr": status})
        refresh_analysis_input_enrichment(artifact)
        report(100, "OCR 完成")
        return {
            "status": status,
            "frame_ocr_path": str(ocr_dir / "frame_ocr.json"),
            "subtitle_ocr_path": str(ocr_dir / "subtitle_ocr.json"),
            "cover_ocr_path": str(ocr_dir / "cover_ocr.json"),
            "frame_ocr": frame_payload,
            "subtitle_ocr": subtitle_payload,
            "cover_ocr": cover_payload,
        }
    except AppError as error:
        _write_json(
            ocr_dir / "status.json",
            {
                "status": "provider_missing" if error.code == ErrorCode.OCR_PROVIDER_NOT_CONFIGURED else "failed",
                "provider": settings.ocr_provider,
                "error_code": error.code,
                "message": error.message,
                "updated_at": _now(),
            },
        )
        update_manifest(
            artifact,
            {"ocr": "provider_missing" if error.code == ErrorCode.OCR_PROVIDER_NOT_CONFIGURED else "failed"},
        )
        refresh_analysis_input_enrichment(artifact)
        raise
    except Exception as error:
        app_error = AppError(ErrorCode.OCR_FAILED, str(error)[:500])
        _write_json(
            ocr_dir / "status.json",
            {
                "status": "failed",
                "provider": settings.ocr_provider,
                "error_code": app_error.code,
                "message": app_error.message,
                "updated_at": _now(),
            },
        )
        update_manifest(artifact, {"ocr": "failed"})
        refresh_analysis_input_enrichment(artifact)
        raise app_error from error


def _configured_provider() -> OCRProvider:
    provider_name = settings.ocr_provider
    if provider_name in {"", "disabled", "none", "off"}:
        raise AppError(
            ErrorCode.OCR_PROVIDER_NOT_CONFIGURED,
            "OCR 未启用。请在 .env 中设置 OCR_PROVIDER=auto 或 OCR_PROVIDER=rapidocr，并安装 requirements-ocr.txt。",
        )
    if provider_name == "auto":
        if importlib.util.find_spec("rapidocr_onnxruntime") or importlib.util.find_spec("rapidocr"):
            return RapidOCRProvider()
        raise AppError(
            ErrorCode.OCR_PROVIDER_NOT_CONFIGURED,
            "OCR_PROVIDER=auto 但未检测到 rapidocr-onnxruntime。请安装 requirements-ocr.txt，或将 OCR_PROVIDER 设为 disabled。",
        )
    if provider_name in {"rapidocr", "rapidocr_onnxruntime", "rapidocr-onnxruntime"}:
        return RapidOCRProvider()
    raise AppError(ErrorCode.OCR_PROVIDER_NOT_CONFIGURED, f"不支持的 OCR_PROVIDER：{provider_name}")


def _selected_keyframes(artifact: CaseArtifact) -> list[Path]:
    keyframes_dir = Path(artifact.keyframes_dir)
    if not keyframes_dir.is_dir():
        return []
    max_frames = max(1, settings.ocr_max_frames)
    return sorted(path for path in keyframes_dir.glob("frame_*.jpg") if path.is_file())[:max_frames]


def _recognize_frame(
    provider: OCRProvider,
    frame_path: Path,
    region: str,
    crop_path: Path | None,
) -> dict:
    target_path = crop_path or frame_path
    regions = provider.recognize(target_path)
    return {
        "frame_time": _timestamp_from_frame(frame_path),
        "image": str(frame_path),
        "ocr_image": str(target_path),
        "region": region,
        "regions": regions,
        "text": "\n".join(item.get("text", "") for item in regions if item.get("text")).strip(),
    }


def _crop_subtitle_region(frame_path: Path, crop_path: Path) -> Path:
    ratio = min(0.9, max(0.1, settings.ocr_subtitle_crop_ratio))
    with Image.open(frame_path).convert("RGB") as image:
        top = int(image.height * (1 - ratio))
        cropped = image.crop((0, top, image.width, image.height))
        crop_path.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(crop_path, quality=92)
    return crop_path


def _normalize_rapidocr_output(output) -> list[dict]:
    rows = output
    if isinstance(output, tuple) and output:
        rows = output[0]
    if not rows:
        return []
    normalized = []
    for item in rows:
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("rec_text") or "").strip()
            if not text:
                continue
            normalized.append(
                {
                    "text": text,
                    "bbox": item.get("bbox") or item.get("box") or item.get("points") or [],
                    "confidence": _float(item.get("confidence", item.get("score", 0))),
                }
            )
            continue
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            text = str(item[1] or "").strip()
            if not text:
                continue
            normalized.append(
                {
                    "text": text,
                    "bbox": item[0],
                    "confidence": _float(item[2] if len(item) > 2 else 0),
                }
            )
    return normalized


def _join_text(results: list[dict]) -> str:
    texts = []
    for result in results:
        text = str(result.get("text") or "").strip()
        if text:
            texts.append(text)
    return "\n".join(texts).strip()


def _text_count(results: list[dict]) -> int:
    return sum(len(result.get("regions") or []) for result in results)


def _timestamp_from_frame(path: Path) -> float:
    match = FRAME_TIMESTAMP_RE.search(path.name)
    if not match:
        return 0.0
    return _float(match.group(1))


def _float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
