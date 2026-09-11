"""Bounded, local-only inputs from a sample's explicitly assigned Case."""
from __future__ import annotations

import io
import itertools
import json
import math
import re
import warnings
from pathlib import Path

from PIL import Image

MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_JSON_DEPTH = 24
MAX_IMAGE_BYTES = 3 * 1024 * 1024
MAX_IMAGE_PIXELS = 12_000_000
MAX_ENCODED_BYTES = 4 * 1024 * 1024
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")


def clean_material_text(value, limit: int = 1600) -> str:
    """Reuse the execution sanitizer; never stringify arbitrary objects."""
    from app.services.creator_intelligence.execution_record import _safe_text

    if isinstance(value, str) and value.strip() in {"{}", "[]", "null"}:
        return ""
    return _safe_text(value, max(0, limit)) if isinstance(value, str) else ""


def _no_symlinks(path: Path) -> bool:
    return not any(part.is_symlink() for part in (path, *path.parents))


def safe_case_dir(case_id, cases_dir: Path) -> Path | None:
    if not isinstance(case_id, str) or not _ID.fullmatch(case_id):
        return None
    try:
        root = Path(cases_dir).absolute()
        path = root / case_id
        if _no_symlinks(path) and path.is_dir() and path.resolve().parent == root.resolve():
            return path
    except (OSError, ValueError):
        pass
    return None


def _asset(case_dir: Path, relative) -> Path | None:
    try:
        relative = Path(relative)
        if relative.is_absolute() or ".." in relative.parts:
            return None
        path = case_dir / relative
        if _no_symlinks(path) and path.resolve().is_relative_to(case_dir.resolve()) and path.is_file():
            return path
    except (OSError, ValueError, TypeError):
        pass
    return None


def _read(case_dir: Path, relative, limit=MAX_JSON_BYTES) -> bytes:
    path = _asset(case_dir, relative)
    if path is None:
        return b""
    try:
        if path.stat().st_size > limit:
            return b""
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
        return data if len(data) <= limit else b""
    except OSError:
        return b""


def _parse(data: bytes) -> dict:
    try:
        value = json.loads(data)
        stack = [(value, 0)]
        while stack:
            item, depth = stack.pop()
            if depth > MAX_JSON_DEPTH:
                return {}
            if isinstance(item, dict):
                stack.extend((child, depth + 1) for child in item.values())
            elif isinstance(item, list):
                stack.extend((child, depth + 1) for child in item)
        return value if isinstance(value, dict) else {}
    except (ValueError, UnicodeError, RecursionError):
        return {}


def read_material_json(case_dir: Path, relative) -> dict:
    """Bounded JSON reader, not a prompt sanitizer. Callers must allowlist fields."""
    return _parse(_read(case_dir, relative))


def _get(sample, name):
    return sample.get(name, "") if isinstance(sample, dict) else getattr(sample, name, "")


def _texts(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value[:40]:
            if isinstance(item, str):
                yield item
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                yield item["text"]


def collect_materials(sample, cases_dir: Path, compact: bool = False) -> dict:
    """Collect original text and explicitly secondhand observations, never metadata."""
    sources = {kind: {"status": "missing", "source": "none"} for kind in ("asr", "ocr", "comments", "existing_analysis")}
    result = {"version": 1, "sample_id": clean_material_text(_get(sample, "sample_id"), 128), "sources": sources, "omissions": []}
    case = safe_case_dir(_get(sample, "case_id"), cases_dir)
    if case is None:
        result["omissions"].append("case_missing_or_unsafe")
        return result
    budgets = dict(zip(sources, (800, 1000, 800, 1600)))
    if compact:
        budgets = {key: value // 2 for key, value in budgets.items()}
    embedded = read_material_json(case, "analysis_input.json").get("analysis_enrichment")
    embedded = embedded if isinstance(embedded, dict) else {}

    def saved(kind):
        value = embedded.get(kind)
        return value if isinstance(value, dict) else {}

    statuses = {}
    for kind in ("asr", "ocr", "comments"):
        status = read_material_json(case, f"enrichment/{kind}/status.json").get("status") or saved(kind).get("status")
        allowed = {"success", "failed", "no_speech", "no_text", "pending", "skipped", "provider_missing", "not_run", "empty"}
        statuses[kind] = status if isinstance(status, str) and status in allowed else "missing"
        sources[kind]["status"] = statuses[kind]

    def excerpt(kind, values):
        text = "\n".join(clean_material_text(item, MAX_JSON_BYTES) for item in _texts(values))
        cleaned = clean_material_text(text, len(text))
        if len(cleaned) > budgets[kind]:
            result["omissions"].append(kind + "_truncated")
        return cleaned[:budgets[kind]]

    transcript = read_material_json(case, "enrichment/asr/transcript.json")
    raw = transcript.get("full_text")
    if not isinstance(raw, str) or not raw.strip():
        raw = _read(case, "enrichment/asr/transcript.txt").decode("utf-8", errors="replace")
    asr_source = "original_asr"
    if not clean_material_text(raw, 1) and not transcript.get("segments"):
        transcript = saved("asr")
        raw = transcript.get("full_text") or transcript.get("text") or ""
        asr_source = "analysis_input_enrichment_asr"
    segments = transcript.get("segments")
    segments = segments if isinstance(segments, list) else []
    if not raw:
        raw = "\n".join(item.get("text", "") for item in segments if isinstance(item, dict) and isinstance(item.get("text"), str))
    text = excerpt("asr", raw)
    if text:
        sources["asr"] = {"status": statuses["asr"] if statuses["asr"] != "missing" else "available", "source": asr_source, "excerpt": text}
        # Split the per-kind budget between context and timestamped speech.
        if segments:
            result["omissions"].append("asr_context_segments_budgeted")
            sources["asr"]["excerpt"] = text[:budgets["asr"] // 2]
            remaining = budgets["asr"] - len(sources["asr"]["excerpt"])
            selected = []
            for item in segments[:40]:
                if not isinstance(item, dict):
                    continue
                speech = clean_material_text(item.get("text"), remaining)
                if not speech:
                    continue
                segment = {"text": speech}
                for key in ("start", "end"):
                    stamp = item.get(key)
                    if type(stamp) in (int, float) and math.isfinite(stamp) and stamp >= 0:
                        segment[key] = stamp
                selected.append(segment)
                remaining -= len(speech)
                if remaining <= 0:
                    break
            sources["asr"]["segments"] = selected

    ocr = {}
    ocr_sources = set()
    remaining = budgets["ocr"]
    for kind in ("cover", "subtitle", "frame"):
        payload = read_material_json(case, f"enrichment/ocr/{kind}_ocr.json")
        full = clean_material_text(payload.get("full_text"), MAX_JSON_BYTES)
        origin = "original_ocr"
        if not full:
            full = clean_material_text(saved("ocr").get(kind + "_text"), MAX_JSON_BYTES)
            origin = "analysis_input_enrichment_ocr"
        if len(full) > remaining:
            result["omissions"].append("ocr_" + kind + "_truncated")
        if full[:remaining]:
            ocr_sources.add(origin)
            ocr[kind + "_text"] = full[:remaining]
            remaining -= len(ocr[kind + "_text"])
    if ocr:
        sources["ocr"] = {"status": statuses["ocr"] if statuses["ocr"] != "missing" else "available", "source": "+".join(sorted(ocr_sources)), **ocr}

    summary = read_material_json(case, "enrichment/comments/comment_summary.json")
    comments = []
    comment_source = "saved_comment_summary_derived"
    for key in ("top_comments", "top_needs", "high_frequency_words", "comment_hooks"):
        comments.extend(_texts(summary.get(key)))
    comments = [text for text in comments if clean_material_text(text, 1)]
    if not comments:
        for key in ("top_comments", "top_needs", "high_frequency_words", "comment_hooks"):
            comments.extend(_texts(saved("comments").get(key)))
        comments = [text for text in comments if clean_material_text(text, 1)]
        comment_source = "analysis_input_enrichment_comments_derived"
    if not comments:
        comment_source = "original_comments_clean"
        data = _read(case, "enrichment/comments/comments_clean.jsonl")
        # Bound both lines inspected and individual JSON objects.
        stream = io.BytesIO(data)
        for _ in range(100):
            line = stream.readline(16385)
            if not line or len(line) > 16384:
                break
            comments.extend(_texts(_parse(line).get("text")))
    text = excerpt("comments", comments)
    if text:
        sources["comments"] = {"status": statuses["comments"] if statuses["comments"] != "missing" else "available", "source": comment_source, "excerpt": text}

    analysis = read_material_json(case, "analysis_result.json")
    observations = list(_texts(analysis.get("summary")))
    for key, fields in {
        "hook_analysis": ("first_impression", "why_stop_scrolling", "first_3_seconds"),
        "visual_analysis": ("scene", "subject", "composition", "lighting_color", "movement_rhythm", "style_keywords"),
        "speech_analysis": ("opening_line", "spoken_hook", "script_structure"),
        "screen_text_analysis": ("cover_text", "subtitle_role", "key_phrases"),
    }.items():
        section = analysis.get(key)
        if isinstance(section, dict):
            for field in fields:
                observations.extend(_texts(section.get(field)))
    evidence = analysis.get("evidence_summary")
    limits = list(_texts(analysis.get("limitations")))
    limits.extend(_texts(analysis.get("risks")))
    if isinstance(evidence, dict):
        limits.extend(_texts(evidence.get("evidence_gaps")))
    if analysis.get("is_fallback") or any(analysis.get(key) in ("fallback", "local_fallback", "prompt_only", "failed") for key in ("status", "_analysis_mode", "analysis_mode")):
        observations = []
        result["omissions"].append("existing_analysis_fallback")
    limit_text = clean_material_text("\n".join(limits), budgets["existing_analysis"] // 3)
    text = excerpt("existing_analysis", observations)
    text = text[:budgets["existing_analysis"] - len(limit_text)]
    if text or limit_text:
        sources["existing_analysis"] = {"status": "available", "source": "saved_single_analysis", "secondhand": True, "observations": text, "limits": limit_text}
    for kind, source in sources.items():
        if source["source"] == "none":
            result["omissions"].append(kind + "_missing_empty_or_rejected")
    return result


def _valid_image(case: Path, relative) -> Path | None:
    path = _asset(case, relative)
    if path is None:
        return None
    data = _read(case, relative, MAX_IMAGE_BYTES)
    if not data or 4 * ((len(data) + 2) // 3) > MAX_ENCODED_BYTES:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"} or image.width * image.height > MAX_IMAGE_PIXELS:
                    return None
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
        return path
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        return None


def select_images(samples, cases_dir: Path, provider) -> tuple[list[Path], list[dict]]:
    """One image per sample; indexes refer to the returned transport order."""
    paths, diagnostics = [], []
    maximum = getattr(provider, "max_keyframes", 6)
    maximum = min(6, max(0, maximum)) if type(maximum) is int else 6
    from app.services.runtime_settings import effective_llm_settings
    from app.services.llm_provider import _optimized_image_payload

    maximum = min(maximum, max(0, int(effective_llm_settings()["max_keyframes"])))
    encoded_total = 0
    for sample in samples:
        diagnostic = {"sample_id": clean_material_text(_get(sample, "sample_id"), 128), "status": "missing_or_rejected", "index": None, "kind": None}
        diagnostics.append(diagnostic)
        if getattr(provider, "supports_images", None) is False:
            diagnostic["status"] = "text_only_provider"
            continue
        if len(paths) >= maximum:
            diagnostic["status"] = "limit_reached"
            continue
        case = safe_case_dir(_get(sample, "case_id"), cases_dir)
        if case is None:
            diagnostic["status"] = "case_missing_or_unsafe"
            continue
        path = _valid_image(case, "contact_sheet.jpg")
        kind = "contact_sheet"
        if path is None:
            kind = "keyframe"
            frames = case / "keyframes"
            if _no_symlinks(frames) and frames.is_dir():
                # Bound enumeration, including directories with unrelated entries.
                try:
                    candidates = sorted(itertools.islice(frames.iterdir(), 128))
                    for candidate in candidates:
                        if candidate.name.startswith("frame_") and candidate.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                            path = _valid_image(case, candidate.relative_to(case))
                            if path:
                                break
                except OSError:
                    pass
        if path is not None:
            try:
                _, encoded = _optimized_image_payload(path)
                encoded_size = 4 * ((len(encoded) + 2) // 3)
            except (OSError, ValueError):
                diagnostic["status"] = "encoding_rejected"
                continue
            if encoded_size > MAX_ENCODED_BYTES or encoded_total + encoded_size > 8 * 1024 * 1024:
                diagnostic["status"] = "encoded_size_limit"
                continue
            encoded_total += encoded_size
            paths.append(path)
            diagnostic.update(status="selected", index=len(paths), kind=kind)
    return paths, diagnostics
