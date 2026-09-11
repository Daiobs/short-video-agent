"""Display-only cover validation and existing Case frame lookup. No network IO."""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import SessionLocal
from app.models import CaseArtifact

MAX_COVER_URL_LENGTH = 4096
COVER_HOSTS = ("douyinpic.com", "byteimg.com", "hdslb.com", "xhscdn.com")
CASE_ID = re.compile(r"case_[a-f0-9]{32}\Z")
FRAME_NAME = re.compile(r"frame_[a-zA-Z0-9_.-]+\.jpg\Z")
ACCOUNT_PARAMS = frozenset({
    "cookie", "cookies", "authorization", "proxy-authorization", "api_key", "apikey",
    "access_token", "refresh_token", "id_token", "sessionid", "sessionid_ss",
    "sid_guard", "sid_tt", "uid_tt", "uid_tt_ss", "password", "passwd", "secret",
    "msToken".lower(), "x-bogus", "passport_csrf_token", "odin_tt",
})


def validated_cover_url(value: object) -> str:
    """Return the exact accepted URL, or empty; never redact/truncate a load URL."""
    if not isinstance(value, str) or not value or len(value) > MAX_COVER_URL_LENGTH:
        return ""
    if re.search(r"[\s\x00-\x1f\x7f\\]", value):
        return ""
    try:
        url = urlsplit(value)
        host = (url.hostname or "").lower()
        if url.scheme not in {"https", "http"} or url.username is not None or url.password is not None:
            return ""
        if url.port not in {None, 80 if url.scheme == "http" else 443} or url.fragment:
            return ""
        if not any(host == suffix or host.endswith("." + suffix) for suffix in COVER_HOSTS):
            return ""
        decoded_path = unquote(url.path)
        if any(part in {".", ".."} for part in decoded_path.split("/")):
            return ""
        if not re.search(r"\.(?:jpe?g|png|webp|avif|heic|gif)(?:[!~@].*)?$", decoded_path, re.I):
            return ""
        # Query values are opaque image signatures, not application login state.
        for key, item in parse_qsl(url.query, keep_blank_values=True):
            if key.lower() in ACCOUNT_PARAMS or re.search(r"(?:^|\s)(?:Bearer\s+|sk-[A-Za-z0-9]{12,})", item, re.I):
                return ""
        decoded = unquote(value)
        if re.search(r"[\x00-\x1f\x7f\\]", decoded):
            return ""
    except (ValueError, UnicodeError):
        return ""
    return value


def existing_frame_name(artifact: CaseArtifact, cases_dir: Path) -> str:
    """Bounded deterministic choice from the Case's own non-symlink frame directory."""
    if not CASE_ID.fullmatch(artifact.case_id or ""):
        return ""
    root = cases_dir.resolve()
    case = root / artifact.case_id
    frames = case / "keyframes"
    try:
        if case.is_symlink() or frames.is_symlink() or not frames.is_dir():
            return ""
        configured = Path(artifact.keyframes_dir)
        if configured.is_symlink() or configured.resolve() != frames:
            return ""
        names = []
        with os.scandir(frames) as entries:
            for index, entry in enumerate(entries):
                if index >= 256:
                    return ""  # Do not offer a non-deterministic partial directory scan.
                if FRAME_NAME.fullmatch(entry.name) and entry.is_file(follow_symlinks=False):
                    if entry.stat(follow_symlinks=False).st_size > 0:
                        names.append(entry.name)
        return min(names, default="")
    except (OSError, ValueError):
        return ""


def attach_frame_previews(samples: list) -> None:
    """One batched read, then bounded metadata-only lookups for associated Cases."""
    ids = {s.case_id for s in samples if CASE_ID.fullmatch(s.case_id or "")}
    for sample in samples:
        sample.preview_url = ""
        sample.preview_source = ""
    if not ids:
        return
    try:
        with SessionLocal() as db:
            artifacts = {}
            ordered = sorted(ids)
            for start in range(0, len(ordered), 500):
                artifacts.update({a.case_id: a for a in db.scalars(select(CaseArtifact).where(CaseArtifact.case_id.in_(ordered[start:start + 500])))})
            for sample in samples:
                artifact = artifacts.get(sample.case_id)
                if artifact is None or (sample.aweme_id and artifact.aweme_id != sample.aweme_id):
                    continue
                name = existing_frame_name(artifact, settings.cases_dir)
                if name:
                    sample.preview_url = f"/api/cases/{artifact.case_id}/keyframes/{name}"
                    sample.preview_source = "video_frame"
    except SQLAlchemyError:
        # Preview availability must not prevent reading the sample pool.
        return
