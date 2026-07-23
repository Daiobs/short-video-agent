from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Mapping
from urllib.parse import urlparse

from app.errors import AppError, ErrorCode
from app.services.runtime_settings import load_local_settings, update_local_section


SCHEMA_VERSION = 1
PAIRING_TTL_SECONDS = 600
SIGNATURE_TOLERANCE_SECONDS = 60
NONCE_TTL_SECONDS = 180
MAX_REQUEST_BODY_BYTES = 64 * 1024
MAX_COOKIE_HEADER_BYTES = 32 * 1024
MAX_COOKIE_PAIRS = 256
MAX_CREDENTIAL_FILE_BYTES = 64 * 1024
LOGIN_COOKIE_NAMES = {"sessionid", "sessionid_ss", "sid_guard", "sid_tt", "uid_tt", "uid_tt_ss"}
PAIRING_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
COOKIE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
SIGNATURE_RE = re.compile(r"^[a-f0-9]{64}$")
EXTENSION_VERSION_RE = re.compile(r"^1\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$")
CREDENTIALS_PATH = Path.home() / ".short-video-agent" / "credentials.json"
LOCAL_METADATA_SECTION = "douyin_extension"

_LOCK = Lock()
_PENDING_PAIR: dict[str, Any] = {}
_USED_NONCES: dict[str, float] = {}


def _now() -> float:
    return time.time()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pairing_digest(code: str) -> str:
    return hashlib.sha256((code or "").strip().upper().encode("utf-8")).hexdigest()


def _secret_bytes(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    try:
        secret = base64.urlsafe_b64decode(f"{encoded}{padding}".encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED) from exc
    if len(secret) != 32:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED)
    return secret


def _new_shared_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")


def _credentials_path() -> Path:
    return Path(CREDENTIALS_PATH).expanduser()


def _validate_storage_path(path: Path) -> None:
    if path.is_symlink():
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED, "本机凭据文件不能是符号链接。")
    parent = path.parent
    if parent.exists() and parent.is_symlink():
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED, "本机凭据目录不能是符号链接。")


def _read_credentials_unlocked() -> dict[str, Any]:
    path = _credentials_path()
    _validate_storage_path(path)
    if not path.exists():
        return {}
    try:
        file_stat = path.stat()
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size > MAX_CREDENTIAL_FILE_BYTES:
            raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED)
        if file_stat.st_mode & 0o077:
            raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED, "本机凭据文件权限必须为 0600。")
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except AppError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED) from exc
    return payload if isinstance(payload, dict) else {}


def read_credentials() -> dict[str, Any]:
    with _LOCK:
        return _read_credentials_unlocked()


def _write_credentials_unlocked(payload: dict[str, Any]) -> None:
    path = _credentials_path()
    _validate_storage_path(path)
    parent = path.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _validate_storage_path(path)
    try:
        os.chmod(parent, 0o700)
    except OSError as exc:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED) from exc

    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    if len(encoded) > MAX_CREDENTIAL_FILE_BYTES:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_PAYLOAD_TOO_LARGE)

    temp_path = parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(temp_path, flags, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, path)
        os.chmod(path, 0o600)
        directory_flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            directory_flags |= os.O_DIRECTORY
        directory_fd = os.open(parent, directory_flags)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except AppError:
        raise
    except OSError as exc:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED) from exc


def write_credentials(payload: dict[str, Any]) -> None:
    with _LOCK:
        _write_credentials_unlocked(payload)


def _safe_credentials() -> dict[str, Any]:
    try:
        return read_credentials()
    except AppError:
        return {}


def start_pairing() -> dict[str, Any]:
    code = "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(8))
    expires_at = _now() + PAIRING_TTL_SECONDS
    with _LOCK:
        _PENDING_PAIR.clear()
        _PENDING_PAIR.update(
            {
                "digest": _pairing_digest(code),
                "expires_at": expires_at,
                "attempts": 0,
            }
        )
    return {
        "pairing_code": code,
        "expires_at": datetime.fromtimestamp(expires_at, timezone.utc).isoformat(),
        "expires_in_seconds": PAIRING_TTL_SECONDS,
        "schema_version": SCHEMA_VERSION,
    }


def _validate_extension_contract(extension_version: str, schema_version: int) -> None:
    try:
        normalized_schema_version = int(schema_version or 0)
    except (TypeError, ValueError) as exc:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_VERSION_UNSUPPORTED) from exc
    if normalized_schema_version != SCHEMA_VERSION:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_VERSION_UNSUPPORTED)
    if not EXTENSION_VERSION_RE.fullmatch(str(extension_version or "").strip()):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_VERSION_UNSUPPORTED)


def complete_pairing(pairing_code: str, extension_version: str, schema_version: int) -> dict[str, Any]:
    _validate_extension_contract(extension_version, schema_version)
    now = _now()
    digest = _pairing_digest(pairing_code)
    with _LOCK:
        pending_digest = str(_PENDING_PAIR.get("digest") or "")
        expires_at = float(_PENDING_PAIR.get("expires_at") or 0)
        if not pending_digest:
            raise AppError(ErrorCode.LOCAL_LOGIN_PAIR_CODE_INVALID)
        if expires_at < now:
            _PENDING_PAIR.clear()
            raise AppError(ErrorCode.LOCAL_LOGIN_PAIR_CODE_EXPIRED)
        if not hmac.compare_digest(digest, pending_digest):
            attempts = int(_PENDING_PAIR.get("attempts") or 0) + 1
            _PENDING_PAIR["attempts"] = attempts
            if attempts >= 10:
                _PENDING_PAIR.clear()
            raise AppError(ErrorCode.LOCAL_LOGIN_PAIR_CODE_INVALID)

        credentials = _read_credentials_unlocked()
        shared_key = _new_shared_key()
        paired_at = _iso_now()
        credentials["schema_version"] = SCHEMA_VERSION
        credentials["pairing"] = {
            "shared_key": shared_key,
            "paired_at": paired_at,
            "extension_version": extension_version,
        }
        _write_credentials_unlocked(credentials)
        _PENDING_PAIR.clear()
        _USED_NONCES.clear()

    update_local_section(
        LOCAL_METADATA_SECTION,
        {
            "paired": True,
            "paired_at": paired_at,
            "extension_version": extension_version,
        },
    )
    return {
        "paired": True,
        "paired_at": paired_at,
        "shared_key": shared_key,
        "schema_version": SCHEMA_VERSION,
        "server_origin": "http://127.0.0.1:8765",
    }


def _parse_cookie_header(cookie_header: str) -> dict[str, Any]:
    if not isinstance(cookie_header, str):
        raise AppError(ErrorCode.DOUYIN_COOKIE_INVALID)
    if len(cookie_header.encode("utf-8")) > MAX_COOKIE_HEADER_BYTES:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_PAYLOAD_TOO_LARGE)
    if "\r" in cookie_header or "\n" in cookie_header:
        raise AppError(ErrorCode.DOUYIN_COOKIE_INVALID)

    names: list[str] = []
    for part in cookie_header.split(";"):
        candidate = part.strip()
        if not candidate:
            continue
        name, separator, value = candidate.partition("=")
        if not separator or not COOKIE_NAME_RE.fullmatch(name) or ";" in value:
            raise AppError(ErrorCode.DOUYIN_COOKIE_INVALID)
        if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
            raise AppError(ErrorCode.DOUYIN_COOKIE_INVALID)
        names.append(name)
    if not names or len(names) > MAX_COOKIE_PAIRS:
        code = ErrorCode.LOCAL_LOGIN_STATE_PAYLOAD_TOO_LARGE if len(names) > MAX_COOKIE_PAIRS else ErrorCode.DOUYIN_COOKIE_INVALID
        raise AppError(code)
    login_key_count = len({name for name in names if name in LOGIN_COOKIE_NAMES})
    if login_key_count <= 0:
        raise AppError(ErrorCode.DOUYIN_LOGIN_REQUIRED)
    return {
        "pair_count": len(names),
        "login_key_count": login_key_count,
    }


def _validate_referer(value: str) -> str:
    referer = str(value or "https://www.douyin.com/").strip()
    if len(referer) > 2048 or "\r" in referer or "\n" in referer:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID)
    parsed = urlparse(referer)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "douyin.com" or host.endswith(".douyin.com")):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID)
    return referer


def normalize_sync_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID)
    schema_version = int(payload.get("schema_version") or 0)
    extension_version = str(payload.get("extension_version") or "").strip()
    _validate_extension_contract(extension_version, schema_version)

    cookie_header = str(payload.get("cookie_header") or "")
    diagnostics = _parse_cookie_header(cookie_header)
    provided_pair_count = int(payload.get("pair_count") or 0)
    provided_login_count = int(payload.get("login_key_count") or 0)
    if (
        provided_pair_count != diagnostics["pair_count"]
        or provided_login_count != diagnostics["login_key_count"]
    ):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID)

    user_agent = str(payload.get("user_agent") or "").strip()
    if not user_agent or len(user_agent) > 1024 or "\r" in user_agent or "\n" in user_agent:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID)

    captured_at = str(payload.get("captured_at") or "").strip()
    try:
        captured_datetime = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID) from exc
    if captured_datetime.tzinfo is None:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID)

    return {
        "cookie_header": cookie_header,
        "user_agent": user_agent,
        "referer": _validate_referer(str(payload.get("referer") or "")),
        "captured_at": captured_at,
        "pair_count": diagnostics["pair_count"],
        "login_key_count": diagnostics["login_key_count"],
        "extension_version": extension_version,
        "schema_version": SCHEMA_VERSION,
    }


def canonical_signature_input(timestamp: str, nonce: str, raw_body: bytes) -> bytes:
    return timestamp.encode("ascii") + b"\n" + nonce.encode("ascii") + b"\n" + raw_body


def compute_signature(shared_key: str, timestamp: str, nonce: str, raw_body: bytes) -> str:
    return hmac.new(
        _secret_bytes(shared_key),
        canonical_signature_input(timestamp, nonce, raw_body),
        hashlib.sha256,
    ).hexdigest()


def _cleanup_nonces(now: float) -> None:
    for nonce, expires_at in list(_USED_NONCES.items()):
        if expires_at < now:
            _USED_NONCES.pop(nonce, None)


def verify_signed_request(headers: Mapping[str, str], raw_body: bytes) -> dict[str, Any]:
    if len(raw_body) > MAX_REQUEST_BODY_BYTES:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_PAYLOAD_TOO_LARGE)
    credentials = read_credentials()
    pairing = credentials.get("pairing")
    if not isinstance(pairing, dict) or not pairing.get("shared_key"):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_NOT_PAIRED)

    timestamp = str(headers.get("x-sva-timestamp") or "").strip()
    nonce = str(headers.get("x-sva-nonce") or "").strip()
    signature = str(headers.get("x-sva-signature") or "").strip().lower()
    extension_version = str(headers.get("x-sva-extension-version") or "").strip()
    try:
        schema_version = int(headers.get("x-sva-schema-version") or 0)
        timestamp_value = int(timestamp)
    except (TypeError, ValueError) as exc:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_AUTH_FAILED) from exc
    _validate_extension_contract(extension_version, schema_version)
    if abs(_now() - timestamp_value) > SIGNATURE_TOLERANCE_SECONDS:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_TIMESTAMP_INVALID)
    if not NONCE_RE.fullmatch(nonce) or not SIGNATURE_RE.fullmatch(signature):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_AUTH_FAILED)

    expected = compute_signature(str(pairing["shared_key"]), timestamp, nonce, raw_body)
    if not hmac.compare_digest(signature, expected):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_AUTH_FAILED)

    now = _now()
    with _LOCK:
        _cleanup_nonces(now)
        if nonce in _USED_NONCES:
            raise AppError(ErrorCode.LOCAL_LOGIN_STATE_REPLAY)
        _USED_NONCES[nonce] = now + NONCE_TTL_SECONDS
    return credentials


def sync_douyin_login_state(payload: dict[str, Any], credentials: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_sync_payload(payload)
    synced_at = _iso_now()
    verified_pairing = credentials.get("pairing")
    verified_shared_key = (
        str(verified_pairing.get("shared_key") or "")
        if isinstance(verified_pairing, dict)
        else ""
    )
    with _LOCK:
        current_credentials = _read_credentials_unlocked()
        current_pairing = current_credentials.get("pairing")
        current_shared_key = (
            str(current_pairing.get("shared_key") or "")
            if isinstance(current_pairing, dict)
            else ""
        )
        if (
            not verified_shared_key
            or not current_shared_key
            or not hmac.compare_digest(verified_shared_key, current_shared_key)
        ):
            raise AppError(ErrorCode.LOCAL_LOGIN_STATE_AUTH_FAILED)
        current_credentials["schema_version"] = SCHEMA_VERSION
        current_credentials["douyin"] = {
            **normalized,
            "last_synced_at": synced_at,
        }
        _write_credentials_unlocked(current_credentials)
    fingerprint = hashlib.sha256(normalized["cookie_header"].encode("utf-8")).hexdigest()
    update_local_section(
        LOCAL_METADATA_SECTION,
        {
            "paired": True,
            "configured": True,
            "credential_fingerprint": fingerprint,
            "last_synced_at": synced_at,
            "captured_at": normalized["captured_at"],
            "pair_count": normalized["pair_count"],
            "login_key_count": normalized["login_key_count"],
            "extension_version": normalized["extension_version"],
        },
    )
    return login_state_status_payload()


def clear_douyin_login_state(credentials: dict[str, Any]) -> dict[str, Any]:
    verified_pairing = credentials.get("pairing")
    verified_shared_key = (
        str(verified_pairing.get("shared_key") or "")
        if isinstance(verified_pairing, dict)
        else ""
    )
    with _LOCK:
        current_credentials = _read_credentials_unlocked()
        current_pairing = current_credentials.get("pairing")
        current_shared_key = (
            str(current_pairing.get("shared_key") or "")
            if isinstance(current_pairing, dict)
            else ""
        )
        if (
            not verified_shared_key
            or not current_shared_key
            or not hmac.compare_digest(verified_shared_key, current_shared_key)
        ):
            raise AppError(ErrorCode.LOCAL_LOGIN_STATE_AUTH_FAILED)
        current_credentials.pop("douyin", None)
        _write_credentials_unlocked(current_credentials)
    update_local_section(
        LOCAL_METADATA_SECTION,
        {
            "configured": False,
            "credential_fingerprint": "",
            "last_synced_at": "",
            "captured_at": "",
            "pair_count": 0,
            "login_key_count": 0,
        },
    )
    return login_state_status_payload()


def extension_douyin_credentials() -> dict[str, str]:
    credentials = _safe_credentials()
    douyin = credentials.get("douyin")
    if not isinstance(douyin, dict):
        return {}
    cookie_header = str(douyin.get("cookie_header") or "")
    if not cookie_header:
        return {}
    return {
        "cookie": cookie_header,
        "user_agent": str(douyin.get("user_agent") or ""),
        "referer": str(douyin.get("referer") or "https://www.douyin.com/"),
        "last_synced_at": str(douyin.get("last_synced_at") or ""),
        "pair_count": str(douyin.get("pair_count") or 0),
        "login_key_count": str(douyin.get("login_key_count") or 0),
        "extension_version": str(douyin.get("extension_version") or ""),
    }


def login_state_status_payload() -> dict[str, Any]:
    credentials = _safe_credentials()
    pairing = credentials.get("pairing")
    douyin = credentials.get("douyin")
    paired = isinstance(pairing, dict) and bool(pairing.get("shared_key"))
    configured = isinstance(douyin, dict) and bool(douyin.get("cookie_header"))
    local_settings = load_local_settings()
    health = local_settings.get("douyin_health")
    safe_health = health if isinstance(health, dict) else {}
    return {
        "paired": paired,
        "configured": configured,
        "source": "chrome_extension" if configured else "",
        "masked_cookie": "********" if configured else "",
        "pair_count": int(douyin.get("pair_count") or 0) if isinstance(douyin, dict) else 0,
        "login_key_count": int(douyin.get("login_key_count") or 0) if isinstance(douyin, dict) else 0,
        "last_synced_at": str(douyin.get("last_synced_at") or "") if isinstance(douyin, dict) else "",
        "captured_at": str(douyin.get("captured_at") or "") if isinstance(douyin, dict) else "",
        "extension_version": str(douyin.get("extension_version") or "") if isinstance(douyin, dict) else "",
        "schema_version": SCHEMA_VERSION,
        "health": {
            "status": str(safe_health.get("status") or ""),
            "checked_at": str(safe_health.get("checked_at") or ""),
        },
    }


def reset_ephemeral_state_for_tests() -> None:
    with _LOCK:
        _PENDING_PAIR.clear()
        _USED_NONCES.clear()
