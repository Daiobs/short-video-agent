from __future__ import annotations

import json
import logging
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
from app.models import CaseArtifact, Job
from app.providers.profile_base import ProfileScanRequest, ProfileVideoItem
from app.services import local_login_state, runtime_settings
from app.services.local_login_state import compute_signature
from app.services.profile_scan import DataSourceManager, DouyinCookieProfileProvider


client = TestClient(app)
EXTENSION_ID = "abcdefghijklmnopabcdefghijklmnop"
UNKNOWN_EXTENSION_ID = "bcdefghijklmnopabcdefghijklmnopa"
EXTENSION_ORIGIN = f"chrome-extension://{EXTENSION_ID}"
EXTENSION_VERSION = "1.0.0"
SCHEMA_VERSION = 1
COOKIE_HEADER = (
    "sessionid=synthetic-session; sid_guard=synthetic-guard; uid_tt=synthetic-user; "
    "ttwid=synthetic-device; passport_csrf_token=synthetic-csrf"
)


def sync_payload(**overrides) -> dict:
    payload = {
        "cookie_header": COOKIE_HEADER,
        "user_agent": "Mozilla/5.0 Chrome/140.0.0.0",
        "referer": "https://www.douyin.com/user/MS4wExample?from=tracking#fragment",
        "captured_at": "2026-07-24T01:00:00+00:00",
        "pair_count": 5,
        "login_key_count": 3,
        "extension_version": EXTENSION_VERSION,
        "schema_version": SCHEMA_VERSION,
    }
    payload.update(overrides)
    return payload


def pair_extension(origin: str = EXTENSION_ORIGIN) -> str:
    start = client.post("/api/local-login-state/pair/start")
    assert start.status_code == 200
    assert start.headers["cache-control"] == "no-store"
    complete = client.post(
        "/api/local-login-state/pair/complete",
        json={
            "pairing_code": start.json()["pairing"]["pairing_code"],
            "extension_version": EXTENSION_VERSION,
            "schema_version": SCHEMA_VERSION,
        },
        headers={"Origin": origin},
    )
    assert complete.status_code == 200
    assert complete.headers["cache-control"] == "no-store"
    assert complete.headers["access-control-allow-origin"] == origin
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
        "Origin": EXTENSION_ORIGIN,
        "X-SVA-Timestamp": timestamp_text,
        "X-SVA-Nonce": nonce_value,
        "X-SVA-Signature": signature_value,
        "X-SVA-Schema-Version": str(SCHEMA_VERSION),
        "X-SVA-Extension-Version": EXTENSION_VERSION,
    }


def sync_extension(shared_key: str, payload: dict | None = None):
    body, headers = signed_request(shared_key, payload or sync_payload())
    return client.post("/api/local-login-state/douyin/sync", content=body, headers=headers)


def test_pair_start_requires_configured_extension_identity(monkeypatch) -> None:
    monkeypatch.setattr(settings, "douyin_login_extension_ids", ())

    response = client.post("/api/local-login-state/pair/start")

    assert response.status_code == 400
    assert response.json()["error_code"] == ErrorCode.EXTENSION_ID_CONFIGURATION_REQUIRED
    assert response.headers["cache-control"] == "no-store"


def test_pair_start_is_only_available_to_local_web_page() -> None:
    response = client.post(
        "/api/local-login-state/pair/start",
        headers={"Origin": EXTENSION_ORIGIN},
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == ErrorCode.LOCAL_HELPER_FORBIDDEN


def test_pairing_ttl_wrong_code_attempt_bound_one_use_and_rotation(monkeypatch) -> None:
    start = client.post("/api/local-login-state/pair/start").json()["pairing"]
    assert start["expires_in_seconds"] == local_login_state.PAIRING_TTL_SECONDS
    for _index in range(local_login_state.PAIRING_ATTEMPT_LIMIT):
        wrong = client.post(
            "/api/local-login-state/pair/complete",
            json={
                "pairing_code": "WRONG123",
                "extension_version": EXTENSION_VERSION,
                "schema_version": SCHEMA_VERSION,
            },
            headers={"Origin": EXTENSION_ORIGIN},
        )
        assert wrong.status_code == 400
    exhausted = client.post(
        "/api/local-login-state/pair/complete",
        json={
            "pairing_code": start["pairing_code"],
            "extension_version": EXTENSION_VERSION,
            "schema_version": SCHEMA_VERSION,
        },
        headers={"Origin": EXTENSION_ORIGIN},
    )
    assert exhausted.json()["error_code"] == ErrorCode.LOCAL_LOGIN_PAIR_CODE_INVALID

    expiring = client.post("/api/local-login-state/pair/start").json()["pairing"]
    monkeypatch.setattr(
        local_login_state,
        "_now",
        lambda: time.time() + local_login_state.PAIRING_TTL_SECONDS + 1,
    )
    expired = client.post(
        "/api/local-login-state/pair/complete",
        json={
            "pairing_code": expiring["pairing_code"],
            "extension_version": EXTENSION_VERSION,
            "schema_version": SCHEMA_VERSION,
        },
        headers={"Origin": EXTENSION_ORIGIN},
    )
    assert expired.json()["error_code"] == ErrorCode.LOCAL_LOGIN_PAIR_CODE_EXPIRED

    monkeypatch.setattr(local_login_state, "_now", time.time)
    first_key = pair_extension()
    second_start = client.post("/api/local-login-state/pair/start").json()["pairing"]
    completed = client.post(
        "/api/local-login-state/pair/complete",
        json={
            "pairing_code": second_start["pairing_code"],
            "extension_version": EXTENSION_VERSION,
            "schema_version": SCHEMA_VERSION,
        },
        headers={"Origin": EXTENSION_ORIGIN},
    )
    second_key = completed.json()["pairing"]["shared_key"]
    assert second_key != first_key
    reused = client.post(
        "/api/local-login-state/pair/complete",
        json={
            "pairing_code": second_start["pairing_code"],
            "extension_version": EXTENSION_VERSION,
            "schema_version": SCHEMA_VERSION,
        },
        headers={"Origin": EXTENSION_ORIGIN},
    )
    assert reused.json()["error_code"] == ErrorCode.LOCAL_LOGIN_PAIR_CODE_INVALID


def test_extension_identity_allowlist_and_cors_are_exact() -> None:
    start = client.post("/api/local-login-state/pair/start").json()["pairing"]
    unknown_origin = f"chrome-extension://{UNKNOWN_EXTENSION_ID}"
    rejected = client.post(
        "/api/local-login-state/pair/complete",
        json={
            "pairing_code": start["pairing_code"],
            "extension_version": EXTENSION_VERSION,
            "schema_version": SCHEMA_VERSION,
        },
        headers={"Origin": unknown_origin},
    )
    assert rejected.status_code == 403
    assert rejected.json()["error_code"] == ErrorCode.LOCAL_LOGIN_STATE_EXTENSION_FORBIDDEN
    assert "access-control-allow-origin" not in rejected.headers

    preflight = client.options(
        "/api/local-login-state/douyin/sync",
        headers={
            "Origin": EXTENSION_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-sva-signature",
        },
    )
    assert preflight.status_code == 204
    assert preflight.headers["access-control-allow-origin"] == EXTENSION_ORIGIN
    assert preflight.headers["cache-control"] == "no-store"

    local_status = client.get(
        "/api/local-login-state/status",
        headers={"Origin": "http://127.0.0.1:8765"},
    )
    assert local_status.status_code == 200
    assert local_status.headers["cache-control"] == "no-store"

    extension_status = client.get(
        "/api/local-login-state/status",
        headers={"Origin": EXTENSION_ORIGIN},
    )
    assert extension_status.status_code == 200
    assert extension_status.headers["access-control-allow-origin"] == EXTENSION_ORIGIN


def test_receiver_rejects_non_loopback_client(monkeypatch) -> None:
    monkeypatch.setattr("app.main.is_loopback_client", lambda _host: False)
    response = client.get("/api/local-login-state/status")
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"


def test_signed_sync_success_is_no_store_and_secret_free() -> None:
    shared_key = pair_extension()
    response = sync_extension(
        shared_key,
        sync_payload(cookie_source_host="www.douyin.com", cookie_host_only=True),
    )
    status = client.get("/api/local-login-state/status")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert status.status_code == 200
    state = status.json()["login_state"]
    assert state == {
        "paired": True,
        "configured": True,
        "source": "chrome_extension",
        "masked_cookie": "********",
        "pair_count": 5,
        "login_key_count": 3,
        "last_synced_at": state["last_synced_at"],
        "captured_at": "2026-07-24T01:00:00+00:00",
        "extension_version": EXTENSION_VERSION,
        "schema_version": 1,
        "health": state["health"],
    }
    serialized = response.text + status.text
    assert COOKIE_HEADER not in serialized
    assert shared_key not in serialized
    assert "sessionid" not in status.text
    assert "credential_fingerprint" not in status.text


def test_bad_signature_expired_timestamp_and_replay_after_restart_are_rejected() -> None:
    shared_key = pair_extension()
    payload = sync_payload()

    bad_body, bad_headers = signed_request(shared_key, payload, signature="0" * 64)
    bad = client.post("/api/local-login-state/douyin/sync", content=bad_body, headers=bad_headers)
    assert bad.status_code == 401
    assert bad.json()["error_code"] == ErrorCode.LOCAL_LOGIN_STATE_AUTH_FAILED

    stale_body, stale_headers = signed_request(
        shared_key,
        payload,
        timestamp=int(time.time()) - local_login_state.SIGNATURE_TOLERANCE_SECONDS - 2,
    )
    stale = client.post("/api/local-login-state/douyin/sync", content=stale_body, headers=stale_headers)
    assert stale.status_code == 401
    assert stale.json()["error_code"] == ErrorCode.LOCAL_LOGIN_STATE_TIMESTAMP_INVALID

    nonce = secrets.token_urlsafe(18)
    body, headers = signed_request(shared_key, payload, nonce=nonce)
    assert client.post("/api/local-login-state/douyin/sync", content=body, headers=headers).status_code == 200
    local_login_state.reset_ephemeral_state_for_tests()
    replay = client.post("/api/local-login-state/douyin/sync", content=body, headers=headers)
    assert replay.status_code == 409
    assert replay.json()["error_code"] == ErrorCode.LOCAL_LOGIN_STATE_REPLAY


def test_nonce_ledger_is_bounded(monkeypatch) -> None:
    monkeypatch.setattr(local_login_state, "MAX_NONCE_LEDGER_ENTRIES", 3)
    shared_key = pair_extension()
    for index in range(3):
        payload = sync_payload(captured_at=f"2026-07-24T01:0{index}:00+00:00")
        assert sync_extension(shared_key, payload).status_code == 200
    full = sync_extension(shared_key, sync_payload(captured_at="2026-07-24T01:04:00+00:00"))
    assert full.status_code == 500
    assert full.json()["error_code"] == ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED
    assert local_login_state.nonce_ledger_count() == 3
    assert Path(local_login_state.NONCE_LEDGER_PATH).stat().st_size <= local_login_state.MAX_NONCE_LEDGER_BYTES


@pytest.mark.parametrize(
    ("payload_update", "error_code"),
    [
        ({"cookie_header": "sessionid=one; sessionid=two", "pair_count": 2, "login_key_count": 1}, ErrorCode.DOUYIN_COOKIE_INVALID),
        ({"cookie_header": "sessionid=one\nInjected=yes", "pair_count": 1, "login_key_count": 1}, ErrorCode.DOUYIN_COOKIE_INVALID),
        ({"cookie_header": "theme=dark", "pair_count": 1, "login_key_count": 0}, ErrorCode.DOUYIN_LOGIN_REQUIRED),
        ({"referer": "https://example.com/"}, ErrorCode.LOCAL_LOGIN_STATE_INVALID),
        ({"extension_version": "2.0.0"}, ErrorCode.LOCAL_LOGIN_STATE_VERSION_UNSUPPORTED),
    ],
)
def test_sync_rejects_invalid_cookie_and_protocol_fields(payload_update: dict, error_code: str) -> None:
    shared_key = pair_extension()
    response = sync_extension(shared_key, sync_payload(**payload_update))
    assert response.status_code == 400
    assert response.json()["error_code"] == error_code
    assert COOKIE_HEADER not in response.text


def test_referer_query_and_fragment_are_removed() -> None:
    shared_key = pair_extension()
    assert sync_extension(shared_key).status_code == 200
    stored = local_login_state.read_credentials()["douyin"]
    assert stored["referer"] == "https://www.douyin.com/user/MS4wExample"
    assert "?" not in stored["referer"]
    assert "#" not in stored["referer"]


def test_request_body_limit_is_enforced_before_json_parsing() -> None:
    shared_key = pair_extension()
    body = b"{" + b"x" * (local_login_state.MAX_REQUEST_BODY_BYTES + 1) + b"}"
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(18)
    headers = {
        "Content-Type": "application/json",
        "Origin": EXTENSION_ORIGIN,
        "X-SVA-Timestamp": timestamp,
        "X-SVA-Nonce": nonce,
        "X-SVA-Signature": compute_signature(shared_key, timestamp, nonce, body),
        "X-SVA-Schema-Version": "1",
        "X-SVA-Extension-Version": EXTENSION_VERSION,
    }
    response = client.post("/api/local-login-state/douyin/sync", content=body, headers=headers)
    assert response.status_code == 413
    assert response.json()["error_code"] == ErrorCode.LOCAL_LOGIN_STATE_PAYLOAD_TOO_LARGE


def test_secure_store_modes_atomic_replace_and_symlink_refusal(monkeypatch, tmp_path: Path) -> None:
    replace_calls: list[tuple[Path, Path]] = []
    original_replace = os.replace

    def tracked_replace(source, target):
        replace_calls.append((Path(source), Path(target)))
        return original_replace(source, target)

    monkeypatch.setattr(local_login_state.os, "replace", tracked_replace)
    shared_key = pair_extension()
    assert sync_extension(shared_key).status_code == 200
    path = Path(local_login_state.CREDENTIALS_PATH)
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert replace_calls and all(source != target for source, target in replace_calls)

    target = tmp_path / "real.json"
    target.write_text("{}", encoding="utf-8")
    symlink = tmp_path / "credentials.json"
    symlink.symlink_to(target)
    monkeypatch.setattr(local_login_state, "CREDENTIALS_PATH", symlink)
    with pytest.raises(AppError) as raised:
        local_login_state.write_credentials({"schema_version": 1})
    assert raised.value.code == ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED
    assert target.read_text(encoding="utf-8") == "{}"


def test_secure_store_rejects_insecure_file_and_symlink_parent(monkeypatch, tmp_path: Path) -> None:
    insecure_dir = tmp_path / "insecure-store"
    insecure_dir.mkdir(mode=0o700)
    insecure_file = insecure_dir / "credentials.json"
    insecure_file.write_text("{}", encoding="utf-8")
    insecure_file.chmod(0o644)
    monkeypatch.setattr(local_login_state, "CREDENTIALS_PATH", insecure_file)
    with pytest.raises(AppError) as insecure:
        local_login_state.read_credentials()
    assert insecure.value.code == ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED

    real_dir = tmp_path / "real-store"
    real_dir.mkdir(mode=0o700)
    linked_dir = tmp_path / "linked-store"
    linked_dir.symlink_to(real_dir, target_is_directory=True)
    monkeypatch.setattr(local_login_state, "CREDENTIALS_PATH", linked_dir / "credentials.json")
    with pytest.raises(AppError) as linked:
        local_login_state.write_credentials({"schema_version": 1})
    assert linked.value.code == ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED


def test_legacy_plaintext_migration_succeeds_and_removes_secret() -> None:
    legacy_path = runtime_settings.LOCAL_SETTINGS_PATH
    legacy_path.write_text(
        json.dumps(
            {
                "douyin": {
                    "cookie": COOKIE_HEADER,
                    "user_agent": "legacy-agent",
                    "referer": "https://www.douyin.com/legacy?tracking=1",
                }
            }
        ),
        encoding="utf-8",
    )
    effective = runtime_settings.effective_douyin_settings()
    assert effective["source"] == "manual_secure"
    assert effective["cookie"] == COOKIE_HEADER
    local_text = legacy_path.read_text(encoding="utf-8")
    assert COOKIE_HEADER not in local_text
    assert "\"cookie\"" not in local_text
    assert json.loads(local_text)["douyin"]["source"] == "manual_secure"


def test_legacy_plaintext_migration_failure_is_fail_closed(monkeypatch) -> None:
    legacy_path = runtime_settings.LOCAL_SETTINGS_PATH
    legacy_path.write_text(
        json.dumps({"douyin": {"cookie": COOKIE_HEADER, "user_agent": "legacy-agent"}}),
        encoding="utf-8",
    )

    def fail_write(_payload):
        raise AppError(ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED)

    monkeypatch.setattr(local_login_state, "_write_credentials_unlocked", fail_write)
    with pytest.raises(AppError) as raised:
        runtime_settings.effective_douyin_settings()
    assert raised.value.code == ErrorCode.LEGACY_CREDENTIAL_MIGRATION_REQUIRED
    assert COOKIE_HEADER in legacy_path.read_text(encoding="utf-8")
    response = client.get("/api/settings/data-sources")
    assert response.status_code == 409
    assert response.json()["error_code"] == ErrorCode.LEGACY_CREDENTIAL_MIGRATION_REQUIRED
    assert COOKIE_HEADER not in response.text


def test_credential_priority_extension_manual_environment_and_clear(monkeypatch) -> None:
    environment_cookie = "sessionid=environment"
    manual_cookie = "sessionid=manual; sid_guard=manual-guard"
    monkeypatch.setattr(settings, "douyin_cookie", environment_cookie)
    assert runtime_settings.effective_douyin_settings()["source"] == "environment"

    runtime_settings.update_douyin_runtime_settings(
        {
            "cookie": manual_cookie,
            "user_agent": "manual-agent",
            "referer": "https://www.douyin.com/manual?tracking=1",
        }
    )
    assert runtime_settings.effective_douyin_settings()["source"] == "manual_secure"

    shared_key = pair_extension()
    assert sync_extension(shared_key).status_code == 200
    assert runtime_settings.effective_douyin_settings()["source"] == "chrome_extension"

    body, headers = signed_request(shared_key)
    cleared = client.request("DELETE", "/api/local-login-state/douyin", content=body, headers=headers)
    assert cleared.status_code == 200
    effective = runtime_settings.effective_douyin_settings()
    assert effective["source"] == "manual_secure"
    assert effective["cookie"] == manual_cookie


def test_sync_creates_no_job_case_creator_or_secret_log(caplog) -> None:
    with SessionLocal() as session:
        before_jobs = session.query(Job).count()
        before_cases = session.query(CaseArtifact).count()
    before_creator_files = list(settings.creator_clones_dir.rglob("*"))
    before_creator_state_files = list(settings.creator_state_dir.rglob("*"))
    caplog.set_level(logging.DEBUG)

    shared_key = pair_extension()
    assert sync_extension(shared_key).status_code == 200

    with SessionLocal() as session:
        assert session.query(Job).count() == before_jobs
        assert session.query(CaseArtifact).count() == before_cases
    assert list(settings.creator_clones_dir.rglob("*")) == before_creator_files
    assert list(settings.creator_state_dir.rglob("*")) == before_creator_state_files
    assert COOKIE_HEADER not in caplog.text
    assert shared_key not in caplog.text
    assert COOKIE_HEADER not in runtime_settings.LOCAL_SETTINGS_PATH.read_text(encoding="utf-8")


def test_profile_provider_consumes_extension_state_and_preserves_metric_availability(monkeypatch) -> None:
    shared_key = pair_extension()
    assert sync_extension(shared_key).status_code == 200
    captured: dict = {}
    item = ProfileVideoItem(
        aweme_id="7622653084993647603",
        title="扩展登录态测试",
        like_count=0,
        comment_count=0,
        share_count=0,
        metric_availability={
            "like_count": True,
            "comment_count": False,
            "share_count": True,
            "collect_count": False,
        },
        source_provider="cookie_api",
    )

    def fake_fetch(**kwargs):
        captured.update(kwargs)
        return [item], "0", False

    monkeypatch.setattr("app.services.profile_scan._fetch_douyin_cookie_api_items", fake_fetch)
    result = DouyinCookieProfileProvider().scan(
        ProfileScanRequest(sec_user_id="MS4wExampleIdentifier", count=1)
    )
    assert captured["headers"]["Cookie"] == COOKIE_HEADER
    assert result.items[0].metric_availability == item.metric_availability


def test_extension_provider_error_is_not_hidden_by_public_fallback(monkeypatch) -> None:
    shared_key = pair_extension()
    assert sync_extension(shared_key).status_code == 200
    public_called = False

    def fail_cookie(_request):
        raise AppError(ErrorCode.COOKIE_INVALID, "synthetic provider failure")

    def public_scan(_request):
        nonlocal public_called
        public_called = True
        raise AssertionError("public fallback must not run")

    manager = DataSourceManager()
    monkeypatch.setattr(manager.cookie_provider, "scan", fail_cookie)
    monkeypatch.setattr(manager.public_provider, "scan", public_scan)
    with pytest.raises(AppError) as raised:
        manager.scan(ProfileScanRequest(sec_user_id="MS4wExampleIdentifier", count=1))
    assert raised.value.code == ErrorCode.COOKIE_INVALID
    assert public_called is False
