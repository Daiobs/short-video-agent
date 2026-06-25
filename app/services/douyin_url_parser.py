from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from app.errors import AppError, ErrorCode


AWEME_ID_RE = re.compile(r"^\d{15,22}$")
AWEME_IN_TEXT_RE = re.compile(r"(?<!\d)(\d{15,22})(?!\d)")
SHORT_URL_RE = re.compile(r"https?://[^\s]+")


def extract_aweme_id(value: str) -> str:
    text = (value or "").strip()
    if AWEME_ID_RE.fullmatch(text):
        return text

    parsed = urlparse(text)
    if parsed.scheme and parsed.netloc:
        query = parse_qs(parsed.query)
        modal_id = (query.get("modal_id") or [""])[0]
        if AWEME_ID_RE.fullmatch(modal_id):
            return modal_id

        path_match = AWEME_IN_TEXT_RE.search(parsed.path)
        if path_match:
            return path_match.group(1)

    text_match = AWEME_IN_TEXT_RE.search(text)
    if text_match:
        return text_match.group(1)

    raise AppError(ErrorCode.AWEME_ID_NOT_FOUND)


def extract_first_url(value: str) -> str:
    match = SHORT_URL_RE.search(value or "")
    return match.group(0) if match else ""

