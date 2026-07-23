from __future__ import annotations

import json
import os
import secrets
import stat
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.errors import AppError, ErrorCode
from app.main import app
from app.models import Job
from app.services import local_login_state, runtime_settings
from app.services.local_login_state import compute_signature


client = TestClient(app)
EXTENSION_VERSION = "1.0.0"
SCHEMA_VERSION = 1
COOKIE_HEADER = (
    "sessionid=session-value; sid_guard=guard-value; uid_tt=user-value; "
    "ttwid=device-value; passport_csrf_token=csrf-value"
)


def sync_payload(**overrides) -> dict:
    payload = {
        "cookie_header": COOKIE_HEADER,
        "user_agent": "Mozilla/5.0 Chrome/140.0.0.0",
        "referer": "https://www.douyin.com/user/MS4wExample",
        "captured_at": "2026-07-24T01:00:00+00:00",
        "pair_count": 5,
        "login_key_count": 3,
        "extension_version": EXTENSION_VERSION,
        "schema_version": SCHEMA_VERSION,
    }
    payload.update(overrides)
    return payload


def pair_extension() -> str:
    start = client.post("/api/local-login-state/pair/start")
    assert start.status_code == 200
    pairing = start.json()["pairing"]
    complete = client.post(
        "/api/local-login-state/pair/complete",
        json={
            "pairing_code": pairing["pairing_code"],
            "extension_version": EXTENSION_VERSION,
            "schema_version": SCHEMA_VERSION,
        },
        headers={"Origin": "chrome-extension://abcdefghijklmnopabcdefghijklmnop"},
    )
    assert complete.status_code == 200
    return complete.json()["pairing"]["shared_key"]


def signed_request(
    shared_key: str,
    payload: dict | None = None,
    *,
    timestamp: int | None = None,
    nonce: str | None = None,
    signature: str | None = None,
) -> tuple[bytes, dict[str, str]]:
    body = (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if payload is not None
        else b""
    )
    timestamp_text = str(timestamp if timestamp is not None else int(time.time()))
    nonce_value = nonce or secrets.token_urlsafe(18)
    signature_value = signature or compute_signature(shared_key, timestamp_text, nonce_value, body)
    return body, {
        "Content-Type": "application/json",
        "Origin": "chrome-extension://abcdefghijklmnopabcdefghijklmnop",
        "X-SVA-Timestamp": timestamp_text,
        "X-SVA-Nonce": nonce_value,
        "X-SVA-Signature": signature_value,
        "X-SVA-Schema-Version": str(SCHEMA_VERSION),
        "X-SVA-Extension-Version": EXTENSION_VERSION,
    }


def sync_extension(shared_key: str, payload: dict | None = None):
    body, headers = signed_request(shared_key, payload or sync_payload())
    return client.post("/api/local-login-state/douyin/sync", content=body, headers=headers)


def test_pair_once_then_sync_multiple_times_without_exposing_secrets() -> None:
    shared_key = pair_extension()

    first = sync_extension(shared_key)
    second = sync_extension(shared_key, sync_payload(captured_at="2026-07-24T01:01:00+00:00"))
    status = client.get("/api/local-login-state/status")

    assert first.status_code == 200
    assert second.status_code == 200
    assert status.status_code == 200
    state = status.json()["login_state"]
    assert state["paired"] is True
    assert state["configured"] is True
    assert state["source"] == "chrome_extension"
    assert state["masked_cookie"] == "********"
    assert state["pair_count"] == 5
    assert state["login_key_count"] == 3
    serialized = first.text + second.text + status.text
    assert COOKIE_HEADER not in serialized
    assert shared_key not in serialized
    local_settings_text = runtime_settings.LOCAL_SETTINGS_PATH.read_text(encoding="utf-8")
    assert COOKIE_HEADER not in local_settings_text
    assert shared_key not in local_settings_text
    assert "credential_fingerprint" in local_settings_text


def test_wrong_and_expired_pairing_codes_are_rejected(monkeypatch) -> None:
    start = client.post("/api/local-login-state/pair/start").json()["pairing"]
    wrong = client.post(
        "/api/local-login-state/pair/complete",
        json={
            "pairing_code": "WRONG123",
            "extension_version": EXTENSION_VERSION,
            "schema_version": SCHEMA_VERSION,
        },
    )
    assert wrong.status_code == 400
    assert wrong.json()["error_code"] == "LOCAL_LOGIN_PAIR_CODE_INVALID"

    expires_at = local_login_state._now() + local_login_state.PAIRING_TTL_SECONDS + 1
    monkeypatch.setattr(local_login_state, "_now", lambda: expires_at)
    expired = client.post(
        "/api/local-login-state/pair/complete",
        json={
            "pairing_code": start["pairing_code"],
            "extension_version": EXTENSION_VERSION,
            "schema_version": SCHEMA_VERSION,
        },
    )
    assert expired.status_code == 400
    assert expired.json()["error_code"] == "LOCAL_LOGIN_PAIR_CODE_EXPIRED"


def test_pairing_code_can_only_be_started_from_local_web_page() -> None:
    response = client.post(
        "/api/local-login-state/pair/start",
        headers={"Origin": "chrome-extension://abcdefghijklmnopabcdefghijklmnop"},
    )

    assert response.status_code == 403
    assert response.json()["error_code"] == "LOCAL_HELPER_FORBIDDEN"


def test_extension_cors_preflight_is_limited_to_local_login_state_api() -> None:
    origin = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"
    response = client.options(
        "/api/local-login-state/douyin/sync",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-sva-signature",
        },
    )

    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == origin
    assert "X-SVA-Signature" in response.headers["access-control-allow-headers"]
    assert response.headers["cache-control"] == "no-store"

    unrelated = client.options(
        "/api/profile/scan",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
        },
    )
    assert unrelated.status_code != 204
    assert "access-control-allow-origin" not in unrelated.headers


def test_signed_sync_rejects_bad_hmac_stale_timestamp_and_nonce_replay() -> None:
    shared_key = pair_extension()
    payload = sync_payload()

    bad_body, bad_headers = signed_request(shared_key, payload, signature="0" * 64)
    bad = client.post("/api/local-login-state/douyin/sync", content=bad_body, headers=bad_headers)
    assert bad.status_code == 401
    assert bad.json()["error_code"] == "LOCAL_LOGIN_STATE_AUTH_FAILED"

    stale_body, stale_headers = signed_request(
        shared_key,
        payload,
        timestamp=int(time.time()) - local_login_state.SIGNATURE_TOLERANCE_SECONDS - 2,
    )
    stale = client.post("/api/local-login-state/douyin/sync", content=stale_body, headers=stale_headers)
    assert stale.status_code == 401
    assert stale.json()["error_code"] == "LOCAL_LOGIN_STATE_TIMESTAMP_INVALID"

    nonce = secrets.token_urlsafe(18)
    replay_body, replay_headers = signed_request(shared_key, payload, nonce=nonce)
    first = client.post("/api/local-login-state/douyin/sync", content=replay_body, headers=replay_headers)
    replay = client.post("/api/local-login-state/douyin/sync", content=replay_body, headers=replay_headers)
    assert first.status_code == 200
    assert replay.status_code == 409
    assert replay.json()["error_code"] == "LOCAL_LOGIN_STATE_REPLAY"


def test_old_verified_request_cannot_restore_credentials_after_repairing() -> None:
    old_shared_key = pair_extension()
    payload = sync_payload()
    raw_body, headers = signed_request(old_shared_key, payload)
    old_credentials = local_login_state.verify_signed_request(
        {key.lower(): value for key, value in headers.items()},
        raw_body,
    )

    new_shared_key = pair_extension()
    assert new_shared_key != old_shared_key

    with pytest.raises(AppError) as raised:
        local_login_state.sync_douyin_login_state(payload, old_credentials)

    assert raised.value.code == ErrorCode.LOCAL_LOGIN_STATE_AUTH_FAILED
    stored = local_login_state.read_credentials()
    assert stored["pairing"]["shared_key"] == new_shared_key
    assert "douyin" not in stored


@pytest.mark.parametrize(
    ("payload_update", "error_code"),
    [
        ({"pair_count": 4}, "LOCAL_LOGIN_STATE_INVALID"),
        ({"login_key_count": 2}, "LOCAL_LOGIN_STATE_INVALID"),
        ({"referer": "https://example.com/"}, "LOCAL_LOGIN_STATE_INVALID"),
        ({"user_agent": ""}, "LOCAL_LOGIN_STATE_INVALID"),
        ({"cookie_header": "theme=dark", "pair_count": 1, "login_key_count": 0}, "DOUYIN_LOGIN_REQUIRED"),
        ({"extension_version": "2.0.0"}, "LOCAL_LOGIN_STATE_VERSION_UNSUPPORTED"),
    ],
)
def test_sync_payload_validation(payload_update: dict, error_code: str) -> None:
    shared_key = pair_extension()
    response = sync_extension(shared_key, sync_payload(**payload_update))

    assert response.status_code == 400
    assert response.json()["error_code"] == error_code


def test_request_body_limit_is_enforced_before_json_parsing() -> None:
    shared_key = pair_extension()
    oversized_body = b"{" + b"x" * (local_login_state.MAX_REQUEST_BODY_BYTES + 1) + b"}"
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(18)
    headers = {
        "Content-Type": "application/json",
        "X-SVA-Timestamp": timestamp,
        "X-SVA-Nonce": nonce,
        "X-SVA-Signature": compute_signature(shared_key, timestamp, nonce, oversized_body),
        "X-SVA-Schema-Version": str(SCHEMA_VERSION),
        "X-SVA-Extension-Version": EXTENSION_VERSION,
    }
    response = client.post("/api/local-login-state/douyin/sync", content=oversized_body, headers=headers)

    assert response.status_code == 413
    assert response.json()["error_code"] == "LOCAL_LOGIN_STATE_PAYLOAD_TOO_LARGE"


def test_credentials_are_atomic_mode_0600_and_outside_repository(monkeypatch) -> None:
    replace_calls: list[tuple[Path, Path]] = []
    original_replace = os.replace

    def tracked_replace(source, target):
        replace_calls.append((Path(source), Path(target)))
        return original_replace(source, target)

    monkeypatch.setattr(local_login_state.os, "replace", tracked_replace)
    shared_key = pair_extension()
    assert sync_extension(shared_key).status_code == 200

    path = Path(local_login_state.CREDENTIALS_PATH)
    assert path.is_file()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert replace_calls
    assert all(source != target for source, target in replace_calls)
    assert not path.is_relative_to(settings.project_root)


def test_credentials_symbolic_link_is_rejected(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "real-credentials.json"
    target.write_text("{}", encoding="utf-8")
    symlink = tmp_path / "credentials.json"
    symlink.symlink_to(target)
    monkeypatch.setattr(local_login_state, "CREDENTIALS_PATH", symlink)

    start = client.post("/api/local-login-state/pair/start").json()["pairing"]
    response = client.post(
        "/api/local-login-state/pair/complete",
        json={
            "pairing_code": start["pairing_code"],
            "extension_version": EXTENSION_VERSION,
            "schema_version": SCHEMA_VERSION,
        },
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "LOCAL_LOGIN_STATE_STORAGE_FAILED"
    assert target.read_text(encoding="utf-8") == "{}"


def test_extension_credentials_override_manual_and_fall_back_after_clear(monkeypatch) -> None:
    manual_cookie = "sessionid=manual; sid_guard=manual-guard"
    monkeypatch.setattr(settings, "douyin_cookie", "sessionid=environment; sid_guard=environment-guard")
    runtime_settings.update_douyin_runtime_settings(
        {
            "cookie": manual_cookie,
            "user_agent": "manual-agent",
            "referer": "https://www.douyin.com/manual",
        }
    )
    assert runtime_settings.effective_douyin_settings()["source"] == "manual_local"

    shared_key = pair_extension()
    assert sync_extension(shared_key).status_code == 200
    effective = runtime_settings.effective_douyin_settings()
    assert effective["source"] == "chrome_extension"
    assert effective["cookie"] == COOKIE_HEADER
    assert effective["user_agent"] == "Mozilla/5.0 Chrome/140.0.0.0"

    body, headers = signed_request(shared_key)
    cleared = client.request("DELETE", "/api/local-login-state/douyin", content=body, headers=headers)
    assert cleared.status_code == 200
    effective_after_clear = runtime_settings.effective_douyin_settings()
    assert effective_after_clear["source"] == "manual_local"
    assert effective_after_clear["cookie"] == manual_cookie


def test_local_login_state_rejects_non_loopback_client(monkeypatch) -> None:
    monkeypatch.setattr("app.main.is_loopback_client", lambda _host: False)
    response = client.get("/api/local-login-state/status")

    assert response.status_code == 403
    assert response.json()["error_code"] == "LOCAL_HELPER_FORBIDDEN"


def test_data_source_status_matches_extension_without_exposing_cookie() -> None:
    shared_key = pair_extension()
    assert sync_extension(shared_key).status_code == 200

    response = client.get("/api/settings/data-sources")
    assert response.status_code == 200
    status = response.json()["data_sources"]
    assert status["configured"] is True
    assert status["source"] == "chrome_extension"
    assert status["provider"] == "cookie_api"
    assert status["masked_cookie"] == "********"
    assert status["pair_count"] == 5
    assert status["login_key_count"] == 3
    assert COOKIE_HEADER not in response.text
    assert "shared_key" not in response.text


def test_profile_provider_uses_extension_credentials_without_creating_job(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}
        text = ""
        content = b""

        @staticmethod
        def json():
            return {
                "aweme_list": [
                    {
                        "aweme_id": "7622653084993647603",
                        "desc": "扩展凭据测试作品",
                        "statistics": {"digg_count": 10, "comment_count": 2, "share_count": 1},
                        "video": {"duration": 1000},
                    }
                ],
                "has_more": False,
                "max_cursor": "0",
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params=None, headers=None):
            calls.append({"url": url, "headers": headers or {}})
            return FakeResponse()

    monkeypatch.setattr(settings, "profile_scan_provider", "cookie_api")
    monkeypatch.setattr(settings, "douyin_cookie", "")
    monkeypatch.setattr("app.services.profile_scan.httpx.Client", FakeClient)
    shared_key = pair_extension()
    assert sync_extension(shared_key).status_code == 200

    with SessionLocal() as session:
        jobs_before = session.query(Job).count()
    response = client.post(
        "/api/profile/scan",
        json={
            "profile_url": "https://www.douyin.com/user/MS4wLjABAAAAabc12345",
            "count": 5,
            "max_pages": 1,
        },
    )
    with SessionLocal() as session:
        jobs_after = session.query(Job).count()

    assert response.status_code == 200
    assert response.json()["provider"] == "cookie_api"
    assert len(response.json()["items"]) == 1
    assert calls[0]["headers"]["Cookie"] == COOKIE_HEADER
    assert COOKIE_HEADER not in response.text
    assert jobs_after == jobs_before
