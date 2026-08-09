from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import stat
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Mapping
from urllib.parse import urlparse, urlunparse

from app.config import settings
from app.errors import AppError, ErrorCode
from app.services.runtime_settings import load_local_settings, replace_local_section, update_local_section


SCHEMA_VERSION = 1
PAIRING_TTL_SECONDS = 600
PAIRING_ATTEMPT_LIMIT = 10
SIGNATURE_TOLERANCE_SECONDS = 60
NONCE_TTL_SECONDS = 180
MAX_REQUEST_BODY_BYTES = 64 * 1024
MAX_COOKIE_HEADER_BYTES = 32 * 1024
MAX_COOKIE_PAIRS = 256
MAX_CREDENTIAL_FILE_BYTES = 64 * 1024
MAX_NONCE_LEDGER_BYTES = 4 * 1024 * 1024
MAX_NONCE_LEDGER_ENTRIES = 4096
LOGIN_COOKIE_NAMES = {
    "sessionid",
    "sessionid_ss",
    "sid_guard",
    "sid_tt",
    "uid_tt",
    "uid_tt_ss",
}
PAIRING_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
COOKIE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
SIGNATURE_RE = re.compile(r"^[a-f0-9]{64}$")
EXTENSION_ID_RE = re.compile(r"^[a-p]{32}$")
EXTENSION_VERSION_RE = re.compile(r"^1\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$")
CREDENTIALS_PATH = Path.home() / ".short-video-agent" / "credentials.json"
NONCE_LEDGER_PATH = Path.home() / ".short-video-agent" / "nonce-ledger.sqlite3"
LOCAL_METADATA_SECTION = "douyin_extension"
MANUAL_METADATA_SECTION = "douyin"

_LOCK = RLock()
_LEDGER_LOCK = RLock()
_PENDING_PAIR: dict[str, Any] = {}


def _now() -> float:
    return time.time()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _update_nonsecret_metadata(section: str, values: dict[str, Any]) -> None:
    try:
        update_local_section(section, values)
    except OSError:
        # The secure credential store is authoritative; metadata is rebuildable.
        return


def configured_extension_ids() -> tuple[str, ...]:
    values = tuple(str(value or "").strip().lower() for value in settings.douyin_login_extension_ids)
    if not values or any(not EXTENSION_ID_RE.fullmatch(value) for value in values):
        raise AppError(ErrorCode.EXTENSION_ID_CONFIGURATION_REQUIRED)
    return tuple(dict.fromkeys(values))


def extension_id_from_origin(origin: str) -> str:
    raw = str(origin or "").strip().lower()
    try:
        parsed = urlparse(raw)
        port = parsed.port
    except ValueError as error:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_EXTENSION_FORBIDDEN) from error
    if (
        parsed.scheme != "chrome-extension"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or port
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or not EXTENSION_ID_RE.fullmatch(parsed.hostname)
    ):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_EXTENSION_FORBIDDEN)
    return parsed.hostname


def require_allowed_extension_origin(origin: str) -> str:
    allowed = configured_extension_ids()
    extension_id = extension_id_from_origin(origin)
    if extension_id not in allowed:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_EXTENSION_FORBIDDEN)
    return extension_id


def is_allowed_extension_origin(origin: str) -> bool:
    try:
        require_allowed_extension_origin(origin)
    except AppError:
        return False
    return True


def _pairing_digest(code: str) -> str:
    return hashlib.sha256(str(code or "").strip().upper().encode("utf-8")).hexdigest()


def _secret_bytes(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    try:
        secret = base64.urlsafe_b64decode(f"{encoded}{padding}".encode("ascii"))
    except (ValueError, UnicodeEncodeError) as error:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED) from error
    if len(secret) != 32:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED)
    return secret


def _new_shared_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")


def _credentials_path() -> Path:
    return Path(CREDENTIALS_PATH).expanduser()


def _nonce_ledger_path() -> Path:
    return Path(NONCE_LEDGER_PATH).expanduser()


def _validate_storage_path(path: Path) -> None:
    if path.is_symlink():
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED, "本机安全存储不能是符号链接。")
    parent = path.parent
    if parent.exists() and parent.is_symlink():
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED, "本机安全存储目录不能是符号链接。")
    if parent.exists() and not parent.is_dir():
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED)
    if parent.exists() and stat.S_IMODE(parent.stat().st_mode) != 0o700:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED, "本机安全存储目录权限必须为 0700。")


def _ensure_secure_parent(path: Path) -> None:
    _validate_storage_path(path)
    parent = path.parent
    try:
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(parent, 0o700)
    except OSError as error:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED) from error
    _validate_storage_path(path)
    if stat.S_IMODE(parent.stat().st_mode) != 0o700:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED)


def _read_credentials_unlocked() -> dict[str, Any]:
    path = _credentials_path()
    _validate_storage_path(path)
    if not path.exists():
        return {}
    try:
        file_stat = path.stat()
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_size > MAX_CREDENTIAL_FILE_BYTES
            or stat.S_IMODE(file_stat.st_mode) != 0o600
        ):
            raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED)
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except AppError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED) from error
    if not isinstance(payload, dict):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED)
    return payload


def read_credentials() -> dict[str, Any]:
    with _LOCK:
        return _read_credentials_unlocked()


def _write_credentials_unlocked(payload: dict[str, Any]) -> None:
    path = _credentials_path()
    _ensure_secure_parent(path)
    if path.exists():
        existing = path.stat()
        if (
            not stat.S_ISREG(existing.st_mode)
            or existing.st_size > MAX_CREDENTIAL_FILE_BYTES
            or stat.S_IMODE(existing.st_mode) != 0o600
        ):
            raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED)

    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    if len(encoded) > MAX_CREDENTIAL_FILE_BYTES:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_PAYLOAD_TOO_LARGE)

    parent = path.parent
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
    except OSError as error:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED) from error


def write_credentials(payload: dict[str, Any]) -> None:
    with _LOCK:
        _write_credentials_unlocked(payload)


def _prepare_nonce_ledger() -> Path:
    path = _nonce_ledger_path()
    _ensure_secure_parent(path)
    if path.exists():
        file_stat = path.stat()
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or stat.S_IMODE(file_stat.st_mode) != 0o600
            or file_stat.st_size > MAX_NONCE_LEDGER_BYTES
        ):
            raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED)
        return path
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
        os.close(descriptor)
        os.chmod(path, 0o600)
    except OSError as error:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED) from error
    return path


def _nonce_digest(shared_key: str, nonce: str) -> str:
    key_scope = hashlib.sha256(shared_key.encode("ascii")).digest()
    return hashlib.sha256(key_scope + b"\0" + nonce.encode("ascii")).hexdigest()


def _claim_nonce(shared_key: str, nonce: str, now: float) -> None:
    digest = _nonce_digest(shared_key, nonce)
    with _LEDGER_LOCK:
        path = _prepare_nonce_ledger()
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(path, timeout=2.0, isolation_level=None)
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS nonce_ledger ("
                "digest TEXT PRIMARY KEY, expires_at REAL NOT NULL, created_at REAL NOT NULL)"
            )
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM nonce_ledger WHERE expires_at < ?", (now,))
            row = connection.execute("SELECT COUNT(*) FROM nonce_ledger").fetchone()
            if int(row[0] if row else 0) >= MAX_NONCE_LEDGER_ENTRIES:
                connection.execute("ROLLBACK")
                raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED)
            try:
                connection.execute(
                    "INSERT INTO nonce_ledger(digest, expires_at, created_at) VALUES (?, ?, ?)",
                    (digest, now + NONCE_TTL_SECONDS, now),
                )
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                raise AppError(ErrorCode.LOCAL_LOGIN_STATE_REPLAY) from error
            connection.execute("COMMIT")
            os.chmod(path, 0o600)
        except AppError:
            raise
        except (OSError, sqlite3.Error) as error:
            if connection is not None:
                try:
                    connection.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
            raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED) from error
        finally:
            if connection is not None:
                connection.close()


def nonce_ledger_count() -> int:
    with _LEDGER_LOCK:
        path = _nonce_ledger_path()
        if not path.exists():
            return 0
        _validate_storage_path(path)
        connection = sqlite3.connect(path, timeout=2.0)
        try:
            row = connection.execute("SELECT COUNT(*) FROM nonce_ledger").fetchone()
        finally:
            connection.close()
        return int(row[0] if row else 0)


def start_pairing() -> dict[str, Any]:
    configured_extension_ids()
    code = "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(8))
    expires_at = _now() + PAIRING_TTL_SECONDS
    with _LOCK:
        _PENDING_PAIR.clear()
        _PENDING_PAIR.update(
            {"digest": _pairing_digest(code), "expires_at": expires_at, "attempts": 0}
        )
    return {
        "pairing_code": code,
        "expires_at": datetime.fromtimestamp(expires_at, timezone.utc).isoformat(),
        "expires_in_seconds": PAIRING_TTL_SECONDS,
        "schema_version": SCHEMA_VERSION,
    }


def _validate_extension_contract(extension_version: str, schema_version: int) -> None:
    try:
        normalized_schema = int(schema_version or 0)
    except (TypeError, ValueError) as error:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_VERSION_UNSUPPORTED) from error
    if normalized_schema != SCHEMA_VERSION:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_VERSION_UNSUPPORTED)
    if not EXTENSION_VERSION_RE.fullmatch(str(extension_version or "").strip()):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_VERSION_UNSUPPORTED)


def complete_pairing(
    pairing_code: str,
    extension_version: str,
    schema_version: int,
    extension_id: str,
) -> dict[str, Any]:
    allowed_extension_id = require_allowed_extension_origin(f"chrome-extension://{extension_id}")
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
            if attempts >= PAIRING_ATTEMPT_LIMIT:
                _PENDING_PAIR.clear()
            raise AppError(ErrorCode.LOCAL_LOGIN_PAIR_CODE_INVALID)

        credentials = _read_credentials_unlocked()
        shared_key = _new_shared_key()
        paired_at = _iso_now()
        credentials["schema_version"] = SCHEMA_VERSION
        credentials["pairing"] = {
            "shared_key": shared_key,
            "paired_at": paired_at,
            "extension_version": str(extension_version),
            "extension_id": allowed_extension_id,
        }
        credentials.pop("douyin", None)
        _write_credentials_unlocked(credentials)
        _PENDING_PAIR.clear()

    _update_nonsecret_metadata(
        LOCAL_METADATA_SECTION,
        {"paired": True, "paired_at": paired_at, "extension_version": extension_version},
    )
    return {
        "paired": True,
        "paired_at": paired_at,
        "shared_key": shared_key,
        "schema_version": SCHEMA_VERSION,
        "server_origin": "http://127.0.0.1:8765",
    }


def _parse_cookie_header(cookie_header: str) -> dict[str, int]:
    if not isinstance(cookie_header, str):
        raise AppError(ErrorCode.DOUYIN_COOKIE_INVALID)
    cleaned = cookie_header.strip()
    if not cleaned or len(cleaned.encode("utf-8")) > MAX_COOKIE_HEADER_BYTES:
        code = ErrorCode.LOCAL_LOGIN_STATE_PAYLOAD_TOO_LARGE if cleaned else ErrorCode.DOUYIN_COOKIE_INVALID
        raise AppError(code)
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in cleaned):
        raise AppError(ErrorCode.DOUYIN_COOKIE_INVALID)

    names: list[str] = []
    populated_login_names: set[str] = set()
    seen: set[str] = set()
    for part in cleaned.split(";"):
        candidate = part.strip()
        if not candidate:
            continue
        name, separator, value = candidate.partition("=")
        normalized_name = name.lower()
        if (
            not separator
            or not COOKIE_NAME_RE.fullmatch(name)
            or normalized_name in seen
        ):
            raise AppError(ErrorCode.DOUYIN_COOKIE_INVALID)
        seen.add(normalized_name)
        names.append(normalized_name)
        if normalized_name in LOGIN_COOKIE_NAMES and value:
            populated_login_names.add(normalized_name)
        if len(names) > MAX_COOKIE_PAIRS:
            raise AppError(ErrorCode.LOCAL_LOGIN_STATE_PAYLOAD_TOO_LARGE)
    if not names:
        raise AppError(ErrorCode.DOUYIN_COOKIE_INVALID)
    login_key_count = len(populated_login_names)
    if login_key_count <= 0:
        raise AppError(ErrorCode.DOUYIN_LOGIN_REQUIRED)
    return {"pair_count": len(names), "login_key_count": login_key_count}


def _normalize_referer(value: str) -> str:
    referer = str(value or "https://www.douyin.com/").strip()
    if len(referer) > 2048 or any(
        ord(character) < 0x20 or ord(character) == 0x7F for character in referer
    ):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID)
    try:
        parsed = urlparse(referer)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as error:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID) from error
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username
        or parsed.password
        or port not in {None, 443}
        or not (host == "douyin.com" or host.endswith(".douyin.com"))
    ):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID)
    path = parsed.path or "/"
    return urlunparse(("https", host, path, "", "", ""))


def normalize_sync_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID)
    try:
        schema_version = int(payload.get("schema_version") or 0)
        provided_pair_count = int(payload.get("pair_count") or 0)
        provided_login_count = int(payload.get("login_key_count") or 0)
    except (TypeError, ValueError) as error:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID) from error
    extension_version = str(payload.get("extension_version") or "").strip()
    _validate_extension_contract(extension_version, schema_version)

    cookie_header = str(payload.get("cookie_header") or "").strip()
    diagnostics = _parse_cookie_header(cookie_header)
    if (
        provided_pair_count != diagnostics["pair_count"]
        or provided_login_count != diagnostics["login_key_count"]
    ):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID)

    user_agent = str(payload.get("user_agent") or "").strip()
    if (
        not user_agent
        or len(user_agent) > 1024
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in user_agent)
    ):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID)
    captured_at = str(payload.get("captured_at") or "").strip()
    if not captured_at or len(captured_at) > 128:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID)
    try:
        captured_datetime = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID) from error
    if captured_datetime.tzinfo is None:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID)

    return {
        "cookie_header": cookie_header,
        "user_agent": user_agent,
        "referer": _normalize_referer(str(payload.get("referer") or "")),
        "captured_at": captured_datetime.astimezone(timezone.utc).isoformat(),
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


def verify_signed_request(
    headers: Mapping[str, str],
    raw_body: bytes,
    extension_id: str,
) -> dict[str, Any]:
    if len(raw_body) > MAX_REQUEST_BODY_BYTES:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_PAYLOAD_TOO_LARGE)
    credentials = read_credentials()
    pairing = credentials.get("pairing")
    if not isinstance(pairing, dict) or not pairing.get("shared_key"):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_NOT_PAIRED)
    paired_extension_id = str(pairing.get("extension_id") or "")
    if not paired_extension_id or not hmac.compare_digest(paired_extension_id, extension_id):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_EXTENSION_FORBIDDEN)

    timestamp = str(headers.get("x-sva-timestamp") or "").strip()
    nonce = str(headers.get("x-sva-nonce") or "").strip()
    signature = str(headers.get("x-sva-signature") or "").strip().lower()
    extension_version = str(headers.get("x-sva-extension-version") or "").strip()
    try:
        schema_version = int(headers.get("x-sva-schema-version") or 0)
        timestamp_value = int(timestamp)
    except (TypeError, ValueError) as error:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_AUTH_FAILED) from error
    _validate_extension_contract(extension_version, schema_version)
    if abs(_now() - timestamp_value) > SIGNATURE_TOLERANCE_SECONDS:
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_TIMESTAMP_INVALID)
    if not NONCE_RE.fullmatch(nonce) or not SIGNATURE_RE.fullmatch(signature):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_AUTH_FAILED)

    shared_key = str(pairing["shared_key"])
    expected = compute_signature(shared_key, timestamp, nonce, raw_body)
    if not hmac.compare_digest(signature, expected):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_AUTH_FAILED)
    _claim_nonce(shared_key, nonce, _now())
    return {
        "credentials": credentials,
        "shared_key": shared_key,
        "extension_id": extension_id,
        "extension_version": extension_version,
    }


def _verified_current_credentials(verified: dict[str, Any]) -> dict[str, Any]:
    verified_key = str(verified.get("shared_key") or "")
    verified_extension_id = str(verified.get("extension_id") or "")
    current = _read_credentials_unlocked()
    pairing = current.get("pairing")
    current_key = str(pairing.get("shared_key") or "") if isinstance(pairing, dict) else ""
    current_extension_id = str(pairing.get("extension_id") or "") if isinstance(pairing, dict) else ""
    if (
        not verified_key
        or not current_key
        or not hmac.compare_digest(verified_key, current_key)
        or not hmac.compare_digest(verified_extension_id, current_extension_id)
    ):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_AUTH_FAILED)
    return current


def sync_douyin_login_state(payload: dict[str, Any], verified: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_sync_payload(payload)
    if normalized["extension_version"] != str(verified.get("extension_version") or ""):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_AUTH_FAILED)
    synced_at = _iso_now()
    with _LOCK:
        current = _verified_current_credentials(verified)
        current["schema_version"] = SCHEMA_VERSION
        current["douyin"] = {**normalized, "last_synced_at": synced_at}
        _write_credentials_unlocked(current)
    _update_nonsecret_metadata(
        LOCAL_METADATA_SECTION,
        {
            "paired": True,
            "configured": True,
            "last_synced_at": synced_at,
            "captured_at": normalized["captured_at"],
            "pair_count": normalized["pair_count"],
            "login_key_count": normalized["login_key_count"],
            "extension_version": normalized["extension_version"],
        },
    )
    return login_state_status_payload()


def clear_douyin_login_state(verified: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        current = _verified_current_credentials(verified)
        current.pop("douyin", None)
        _write_credentials_unlocked(current)
    _update_nonsecret_metadata(
        LOCAL_METADATA_SECTION,
        {
            "paired": True,
            "configured": False,
            "last_synced_at": "",
            "captured_at": "",
            "pair_count": 0,
            "login_key_count": 0,
            "extension_version": str(verified.get("extension_version") or ""),
        },
    )
    return login_state_status_payload()


def store_manual_douyin_credentials(values: Mapping[str, Any]) -> dict[str, Any]:
    updated_at = _iso_now()
    with _LOCK:
        credentials = _read_credentials_unlocked()
        existing = credentials.get("manual_douyin")
        manual = dict(existing) if isinstance(existing, dict) else {}

        if "cookie" in values:
            cookie_header = str(values.get("cookie") or "").strip()
            if cookie_header:
                diagnostics = _parse_cookie_header(cookie_header)
                manual.update(
                    {
                        "cookie_header": cookie_header,
                        "pair_count": diagnostics["pair_count"],
                        "login_key_count": diagnostics["login_key_count"],
                    }
                )
            else:
                manual = {}

        if manual.get("cookie_header"):
            if "user_agent" in values:
                user_agent = str(values.get("user_agent") or "").strip()
                if len(user_agent) > 1024 or any(
                    ord(character) < 0x20 or ord(character) == 0x7F
                    for character in user_agent
                ):
                    raise AppError(ErrorCode.LOCAL_LOGIN_STATE_INVALID)
                manual["user_agent"] = user_agent
            if "referer" in values:
                manual["referer"] = _normalize_referer(str(values.get("referer") or ""))
            manual.setdefault("user_agent", "")
            manual.setdefault("referer", "https://www.douyin.com/")
            manual["updated_at"] = updated_at
            credentials["manual_douyin"] = manual
        else:
            credentials.pop("manual_douyin", None)
        credentials["schema_version"] = SCHEMA_VERSION
        _write_credentials_unlocked(credentials)

    replace_local_section(
        MANUAL_METADATA_SECTION,
        {
            "configured": bool(manual.get("cookie_header")),
            "source": "manual_secure" if manual.get("cookie_header") else "",
            "updated_at": str(manual.get("updated_at") or ""),
            "pair_count": int(manual.get("pair_count") or 0),
            "login_key_count": int(manual.get("login_key_count") or 0),
        },
    )
    return manual_douyin_credentials()


def migrate_legacy_douyin_credentials(legacy: Mapping[str, Any]) -> None:
    cookie_header = str(legacy.get("cookie") or "").strip()
    if not cookie_header:
        return
    store_manual_douyin_credentials(
        {
            "cookie": cookie_header,
            "user_agent": str(legacy.get("user_agent") or settings.douyin_user_agent or ""),
            "referer": str(legacy.get("referer") or settings.douyin_referer or "https://www.douyin.com/"),
        }
    )


def manual_douyin_credentials() -> dict[str, Any]:
    manual = read_credentials().get("manual_douyin")
    if not isinstance(manual, dict) or not manual.get("cookie_header"):
        return {}
    return {
        "cookie": str(manual["cookie_header"]),
        "user_agent": str(manual.get("user_agent") or ""),
        "referer": str(manual.get("referer") or "https://www.douyin.com/"),
        "last_synced_at": "",
        "captured_at": "",
        "pair_count": int(manual.get("pair_count") or 0),
        "login_key_count": int(manual.get("login_key_count") or 0),
        "extension_version": "",
    }


def extension_douyin_credentials() -> dict[str, Any]:
    douyin = read_credentials().get("douyin")
    if not isinstance(douyin, dict) or not douyin.get("cookie_header"):
        return {}
    return {
        "cookie": str(douyin["cookie_header"]),
        "user_agent": str(douyin.get("user_agent") or ""),
        "referer": str(douyin.get("referer") or "https://www.douyin.com/"),
        "last_synced_at": str(douyin.get("last_synced_at") or ""),
        "captured_at": str(douyin.get("captured_at") or ""),
        "pair_count": int(douyin.get("pair_count") or 0),
        "login_key_count": int(douyin.get("login_key_count") or 0),
        "extension_version": str(douyin.get("extension_version") or ""),
    }


def _safe_status_timestamp(value: Any) -> str:
    candidate = str(value or "").strip()
    if not candidate or len(candidate) > 64:
        return ""
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return candidate if parsed.tzinfo is not None else ""


def _safe_status_count(value: Any, maximum: int = MAX_COOKIE_PAIRS) -> int:
    try:
        return max(0, min(int(value or 0), maximum))
    except (TypeError, ValueError):
        return 0


def login_state_status_payload() -> dict[str, Any]:
    credentials = read_credentials()
    pairing = credentials.get("pairing")
    douyin = credentials.get("douyin")
    paired = isinstance(pairing, dict) and bool(pairing.get("shared_key"))
    configured = isinstance(douyin, dict) and bool(douyin.get("cookie_header"))
    local_settings = load_local_settings()
    raw_health = local_settings.get("douyin_health")
    health = raw_health if isinstance(raw_health, dict) else {}
    try:
        configured_extension_ids()
        identity_status = "configured"
    except AppError:
        identity_status = "extension_id_configuration_required"
    safe_health_status = str(health.get("status") or identity_status)
    if safe_health_status not in {
        "configured",
        "extension_id_configuration_required",
        "not_configured",
        "pending",
        "success",
        "failed",
        "invalid",
    }:
        safe_health_status = "pending"
    return {
        "paired": paired,
        "configured": configured,
        "source": "chrome_extension" if configured else "",
        "masked_cookie": "********" if configured else "",
        "pair_count": _safe_status_count(douyin.get("pair_count")) if isinstance(douyin, dict) else 0,
        "login_key_count": _safe_status_count(douyin.get("login_key_count"), len(LOGIN_COOKIE_NAMES)) if isinstance(douyin, dict) else 0,
        "last_synced_at": _safe_status_timestamp(douyin.get("last_synced_at")) if isinstance(douyin, dict) else "",
        "captured_at": _safe_status_timestamp(douyin.get("captured_at")) if isinstance(douyin, dict) else "",
        "extension_version": (
            str(douyin.get("extension_version") or "")
            if isinstance(douyin, dict)
            and EXTENSION_VERSION_RE.fullmatch(str(douyin.get("extension_version") or ""))
            else ""
        ),
        "schema_version": SCHEMA_VERSION,
        "health": {
            "status": safe_health_status,
            "checked_at": _safe_status_timestamp(health.get("checked_at")),
        },
    }


def reset_ephemeral_state_for_tests() -> None:
    with _LOCK:
        _PENDING_PAIR.clear()
