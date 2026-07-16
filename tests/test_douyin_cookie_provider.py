from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.errors import AppError, ErrorCode
from app.main import app
from app.models import Job
from app.providers.profile_base import ProfileScanRequest
from app.services import runtime_settings
from app.services.runtime_settings import effective_douyin_settings
from app.services.profile_scan import (
    COOKIE_MAX_LENGTH,
    DouyinCookieProfileProvider,
    inspect_douyin_cookie,
)


client = TestClient(app)
SYNTHETIC_COOKIE = (
    "sessionid=synthetic_test_value; "
    "sid_guard=synthetic_guard; "
    "uid_tt=synthetic_uid; "
    "uid_tt_ss=synthetic_uid_ss; "
    "sid_tt=synthetic_sid"
)
PROFILE_URL = "https://www.douyin.com/user/MS4wLjABAAAAabc12345"


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload=None,
        content_type: str = "application/json",
        text: str | None = None,
        location: str = "",
        json_error: bool = False,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error
        self.headers = {"content-type": content_type}
        if location:
            self.headers["location"] = location
        self.text = text if text is not None else json.dumps(payload, ensure_ascii=False) if payload is not None else ""
        self.content = self.text.encode("utf-8")

    def json(self):
        if self._json_error:
            raise ValueError("synthetic invalid json")
        return self._payload


def _mock_cookie_client(monkeypatch, responses_or_errors: list) -> list[dict]:
    calls: list[dict] = []
    queue = list(responses_or_errors)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.options = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params=None, headers=None):
            calls.append({"url": url, "params": params or {}, "headers": headers or {}})
            outcome = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr("app.services.profile_scan.httpx.Client", FakeClient)
    return calls


def _configure_synthetic_cookie(monkeypatch, value: str = SYNTHETIC_COOKIE) -> None:
    monkeypatch.setattr(settings, "douyin_cookie", value)
    monkeypatch.setattr(settings, "douyin_user_agent", "Synthetic Browser UA")
    monkeypatch.setattr(settings, "douyin_referer", "https://www.douyin.com/")


def _aweme(aweme_id: str, *, title: str = "合成作品") -> dict:
    return {
        "aweme_id": aweme_id,
        "desc": title,
        "statistics": {"digg_count": 10, "comment_count": 2, "share_count": 1},
        "video": {"duration": 1000},
    }


@pytest.mark.parametrize(
    ("cookie", "expected_code"),
    [
        ("", ErrorCode.DOUYIN_COOKIE_NOT_CONFIGURED),
        ("   ", ErrorCode.DOUYIN_COOKIE_NOT_CONFIGURED),
        ("not-a-cookie", ErrorCode.DOUYIN_COOKIE_INVALID),
        (
            "sessionid=synthetic_a; sessionid=synthetic_b; uid_tt=synthetic_uid",
            ErrorCode.DOUYIN_COOKIE_INVALID,
        ),
        ("sessionid=your_cookie; uid_tt=your_uid", ErrorCode.DOUYIN_COOKIE_INVALID),
        ("sessionid=synthetic_only", ErrorCode.DOUYIN_LOGIN_REQUIRED),
    ],
)
def test_cookie_validation_stops_before_remote_request(monkeypatch, cookie: str, expected_code: str) -> None:
    _configure_synthetic_cookie(monkeypatch, cookie)
    calls = _mock_cookie_client(monkeypatch, [FakeResponse(payload={"aweme_list": []})])

    with pytest.raises(AppError) as raised:
        DouyinCookieProfileProvider().scan(ProfileScanRequest(profile_url=PROFILE_URL))

    assert raised.value.code == expected_code
    assert calls == []
    if cookie.strip():
        assert cookie.strip() not in raised.value.message


def test_cookie_length_limit_stops_before_remote_request(monkeypatch) -> None:
    cookie = f"sessionid={'x' * COOKIE_MAX_LENGTH}; uid_tt=synthetic_uid"
    _configure_synthetic_cookie(monkeypatch, cookie)
    calls = _mock_cookie_client(monkeypatch, [FakeResponse(payload={"aweme_list": []})])

    with pytest.raises(AppError) as raised:
        DouyinCookieProfileProvider().scan(ProfileScanRequest(profile_url=PROFILE_URL))

    assert raised.value.code == ErrorCode.DOUYIN_COOKIE_INVALID
    assert calls == []


def test_cookie_diagnostics_never_return_values() -> None:
    diagnostics = inspect_douyin_cookie(SYNTHETIC_COOKIE)
    serialized = json.dumps(diagnostics, ensure_ascii=False)

    assert diagnostics["format_valid"] is True
    assert diagnostics["login_state_sufficient"] is True
    assert diagnostics["looks_complete"] is True
    assert diagnostics["pair_count"] == 5
    assert "synthetic_test_value" not in serialized
    assert "synthetic_guard" not in serialized


def test_cookie_api_success_exposes_bounded_scan_metadata(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    calls = _mock_cookie_client(
        monkeypatch,
        [
            FakeResponse(
                payload={
                    "aweme_list": [_aweme("7622653084993647603")],
                    "has_more": False,
                    "max_cursor": "0",
                }
            )
        ],
    )

    result = DouyinCookieProfileProvider().scan(ProfileScanRequest(profile_url=PROFILE_URL, count=5))

    assert [item.aweme_id for item in result.items] == ["7622653084993647603"]
    assert result.scan_meta == {
        "page_count": 1,
        "item_count": 1,
        "duplicate_count": 0,
        "invalid_item_count": 0,
        "retry_count": 0,
        "partial": False,
        "truncated_reason": "",
        "endpoint": "/aweme/v1/web/aweme/post/",
    }
    assert calls[0]["url"].startswith("https://www.douyin.com/")
    assert calls[0]["headers"]["Cookie"] == SYNTHETIC_COOKIE


def test_cookie_is_never_sent_to_non_allowlisted_endpoint(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    calls = _mock_cookie_client(monkeypatch, [FakeResponse(payload={"aweme_list": []})])
    monkeypatch.setattr(
        DouyinCookieProfileProvider,
        "endpoints",
        ("https://example.test/aweme/v1/web/user/post/",),
    )

    with pytest.raises(AppError) as raised:
        DouyinCookieProfileProvider().scan(ProfileScanRequest(profile_url=PROFILE_URL, count=5))

    assert raised.value.code == ErrorCode.DOUYIN_UPSTREAM_UNAVAILABLE
    assert calls == []


def test_external_referer_is_replaced_before_cookie_request(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    monkeypatch.setattr(settings, "douyin_referer", "https://example.test/collect")
    calls = _mock_cookie_client(
        monkeypatch,
        [
            FakeResponse(
                payload={
                    "aweme_list": [_aweme("7622653084993647603")],
                    "has_more": False,
                    "max_cursor": "0",
                }
            )
        ],
    )

    DouyinCookieProfileProvider().scan(ProfileScanRequest(profile_url=PROFILE_URL, count=5))

    assert calls[0]["headers"]["Referer"] == "https://www.douyin.com/"


def test_douyin_referer_drops_query_and_fragment_before_cookie_request(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    monkeypatch.setattr(
        settings,
        "douyin_referer",
        "https://www.douyin.com/user/MS4wLjABAAAAabc12345?token=synthetic#fragment",
    )
    calls = _mock_cookie_client(
        monkeypatch,
        [
            FakeResponse(
                payload={
                    "aweme_list": [_aweme("7622653084993647603")],
                    "has_more": False,
                    "max_cursor": "0",
                }
            )
        ],
    )

    DouyinCookieProfileProvider().scan(ProfileScanRequest(profile_url=PROFILE_URL, count=5))

    assert calls[0]["headers"]["Referer"] == "https://www.douyin.com/user/MS4wLjABAAAAabc12345"


def test_cookie_api_deduplicates_and_skips_bad_items(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    valid = _aweme("7622653084993647603")
    _mock_cookie_client(
        monkeypatch,
        [
            FakeResponse(
                payload={
                    "aweme_list": [valid, valid, "bad", {"broken": True}],
                    "has_more": False,
                    "max_cursor": "0",
                }
            )
        ],
    )

    result = DouyinCookieProfileProvider().scan(ProfileScanRequest(profile_url=PROFILE_URL, count=20))

    assert len(result.items) == 1
    assert result.scan_meta["duplicate_count"] == 1
    assert result.scan_meta["invalid_item_count"] == 2


def test_cookie_api_cursor_loop_returns_partial_result(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    _mock_cookie_client(
        monkeypatch,
        [
            FakeResponse(
                payload={
                    "aweme_list": [_aweme("7622653084993647603")],
                    "has_more": True,
                    "max_cursor": "1",
                }
            ),
            FakeResponse(
                payload={
                    "aweme_list": [_aweme("7622653084993647604")],
                    "has_more": True,
                    "max_cursor": "1",
                }
            ),
        ],
    )

    result = DouyinCookieProfileProvider().scan(
        ProfileScanRequest(profile_url=PROFILE_URL, count=20, max_pages=5)
    )

    assert len(result.items) == 2
    assert result.scan_meta["partial"] is True
    assert result.scan_meta["truncated_reason"] == "cursor_repeated"
    assert result.has_more is True


def test_cookie_api_page_limit_returns_partial_result(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    _mock_cookie_client(
        monkeypatch,
        [
            FakeResponse(
                payload={
                    "aweme_list": [_aweme("7622653084993647603")],
                    "has_more": True,
                    "max_cursor": "1",
                }
            )
        ],
    )

    result = DouyinCookieProfileProvider().scan(
        ProfileScanRequest(profile_url=PROFILE_URL, count=20, max_pages=1)
    )

    assert result.scan_meta["partial"] is True
    assert result.scan_meta["truncated_reason"] == "page_limit"
    assert result.scan_meta["truncated_error_code"] == ErrorCode.DOUYIN_PAGE_LIMIT_REACHED


def test_cookie_api_uses_configured_page_limit_when_request_omits_it(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    monkeypatch.setattr(settings, "profile_scan_max_pages", 2)
    calls = _mock_cookie_client(
        monkeypatch,
        [
            FakeResponse(
                payload={
                    "aweme_list": [_aweme("7622653084993647603")],
                    "has_more": True,
                    "max_cursor": "1",
                }
            ),
            FakeResponse(
                payload={
                    "aweme_list": [_aweme("7622653084993647604")],
                    "has_more": True,
                    "max_cursor": "2",
                }
            ),
        ],
    )

    result = DouyinCookieProfileProvider().scan(ProfileScanRequest(profile_url=PROFILE_URL, count=20))

    assert len(calls) == 2
    assert result.scan_meta["page_count"] == 2
    assert result.scan_meta["partial"] is True
    assert result.scan_meta["truncated_reason"] == "page_limit"


def test_cookie_api_missing_pagination_fields_returns_partial_result(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    _mock_cookie_client(
        monkeypatch,
        [FakeResponse(payload={"aweme_list": [_aweme("7622653084993647603")]})],
    )

    result = DouyinCookieProfileProvider().scan(ProfileScanRequest(profile_url=PROFILE_URL, count=5))

    assert len(result.items) == 1
    assert result.scan_meta["partial"] is True
    assert result.scan_meta["truncated_reason"] == "pagination_fields_missing"


def test_cookie_api_item_limit_returns_partial_result(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    _mock_cookie_client(
        monkeypatch,
        [
            FakeResponse(
                payload={
                    "aweme_list": [
                        _aweme("7622653084993647603"),
                        _aweme("7622653084993647604"),
                        _aweme("7622653084993647605"),
                    ],
                    "has_more": True,
                    "max_cursor": "1",
                }
            )
        ],
    )

    result = DouyinCookieProfileProvider().scan(
        ProfileScanRequest(profile_url=PROFILE_URL, count=2, max_pages=5)
    )

    assert len(result.items) == 2
    assert result.scan_meta["partial"] is True
    assert result.scan_meta["truncated_reason"] == "item_limit"


def test_cookie_api_hard_caps_requested_item_count(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    calls = _mock_cookie_client(
        monkeypatch,
        [
            FakeResponse(
                payload={
                    "aweme_list": [_aweme(str(7_600_000_000_000_000_000 + index)) for index in range(201)],
                    "has_more": True,
                    "max_cursor": "1",
                }
            )
        ],
    )

    result = DouyinCookieProfileProvider().scan(
        ProfileScanRequest(profile_url=PROFILE_URL, count=999, max_pages=999)
    )

    assert len(calls) == 1
    assert len(result.items) == 200
    assert result.scan_meta["partial"] is True
    assert result.scan_meta["truncated_reason"] == "item_limit"


def test_cookie_api_stops_after_two_pages_without_new_items(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    repeated = _aweme("7622653084993647603")
    calls = _mock_cookie_client(
        monkeypatch,
        [
            FakeResponse(payload={"aweme_list": [repeated], "has_more": True, "max_cursor": "1"}),
            FakeResponse(payload={"aweme_list": [repeated], "has_more": True, "max_cursor": "2"}),
            FakeResponse(payload={"aweme_list": [repeated], "has_more": True, "max_cursor": "3"}),
        ],
    )

    result = DouyinCookieProfileProvider().scan(
        ProfileScanRequest(profile_url=PROFILE_URL, count=20, max_pages=10)
    )

    assert len(calls) == 3
    assert len(result.items) == 1
    assert result.scan_meta["duplicate_count"] == 2
    assert result.scan_meta["partial"] is True
    assert result.scan_meta["truncated_reason"] == "no_new_items"


def test_cookie_api_preserves_partial_result_when_later_page_times_out(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    timeout = httpx.ReadTimeout(
        "synthetic timeout",
        request=httpx.Request("GET", "https://www.douyin.com/"),
    )
    calls = _mock_cookie_client(
        monkeypatch,
        [
            FakeResponse(
                payload={
                    "aweme_list": [_aweme("7622653084993647603")],
                    "has_more": True,
                    "max_cursor": "1",
                }
            ),
            timeout,
        ],
    )

    result = DouyinCookieProfileProvider().scan(
        ProfileScanRequest(profile_url=PROFILE_URL, count=20, max_pages=5)
    )

    assert len(calls) == 3
    assert [item.aweme_id for item in result.items] == ["7622653084993647603"]
    assert result.scan_meta["page_count"] == 1
    assert result.scan_meta["retry_count"] == 1
    assert result.scan_meta["partial"] is True
    assert result.scan_meta["truncated_reason"] == "upstream_error"
    assert result.scan_meta["truncated_error_code"] == ErrorCode.DOUYIN_UPSTREAM_TIMEOUT
    assert any(ErrorCode.DOUYIN_UPSTREAM_TIMEOUT in warning for warning in result.warnings)


@pytest.mark.parametrize(
    ("response", "expected_code"),
    [
        (
            FakeResponse(
                status_code=302,
                content_type="text/html",
                location="https://passport.douyin.com/login/",
            ),
            ErrorCode.DOUYIN_LOGIN_REQUIRED,
        ),
        (
            FakeResponse(
                content_type="text/html",
                text="<html><title>登录抖音</title><div>扫码登录</div></html>",
                json_error=True,
            ),
            ErrorCode.DOUYIN_LOGIN_REQUIRED,
        ),
        (
            FakeResponse(content_type="text/plain", text="upstream error", json_error=True),
            ErrorCode.DOUYIN_UPSTREAM_NON_JSON,
        ),
        (
            FakeResponse(content_type="application/json", text="{broken", json_error=True),
            ErrorCode.DOUYIN_RESPONSE_INVALID,
        ),
        (FakeResponse(payload={"unexpected": []}), ErrorCode.DOUYIN_RESPONSE_INVALID),
        (FakeResponse(status_code=401, payload={}), ErrorCode.DOUYIN_AUTH_EXPIRED),
        (FakeResponse(status_code=403, payload={}), ErrorCode.DOUYIN_UPSTREAM_FORBIDDEN),
        (FakeResponse(status_code=429, payload={}), ErrorCode.DOUYIN_UPSTREAM_RATE_LIMITED),
        (FakeResponse(status_code=500, payload={}), ErrorCode.DOUYIN_UPSTREAM_UNAVAILABLE),
    ],
)
def test_cookie_api_response_error_taxonomy(monkeypatch, response: FakeResponse, expected_code: str) -> None:
    _configure_synthetic_cookie(monkeypatch)
    calls = _mock_cookie_client(monkeypatch, [response])

    with pytest.raises(AppError) as raised:
        DouyinCookieProfileProvider().scan(ProfileScanRequest(profile_url=PROFILE_URL, count=5))

    assert raised.value.code == expected_code
    assert len(calls) == (2 if expected_code in {ErrorCode.DOUYIN_UPSTREAM_RATE_LIMITED, ErrorCode.DOUYIN_UPSTREAM_UNAVAILABLE} and response.status_code >= 429 else 1)
    assert SYNTHETIC_COOKIE not in raised.value.message
    assert "<html" not in raised.value.message
    assert "upstream error" not in raised.value.message


def test_cookie_api_classifies_json_login_state_without_exposing_message(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    _mock_cookie_client(
        monkeypatch,
        [
            FakeResponse(
                payload={
                    "status_code": 8,
                    "status_msg": "synthetic private upstream login detail",
                    "aweme_list": [],
                }
            )
        ],
    )

    with pytest.raises(AppError) as raised:
        DouyinCookieProfileProvider().scan(ProfileScanRequest(profile_url=PROFILE_URL, count=5))

    assert raised.value.code == ErrorCode.DOUYIN_AUTH_EXPIRED
    assert "synthetic private upstream login detail" not in raised.value.message


def test_cookie_api_classifies_non_login_redirect_without_exposing_location(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    private_location = "https://www.douyin.com/notice/?synthetic_private_query=1"
    _mock_cookie_client(
        monkeypatch,
        [FakeResponse(status_code=302, content_type="text/html", location=private_location)],
    )

    with pytest.raises(AppError) as raised:
        DouyinCookieProfileProvider().scan(ProfileScanRequest(profile_url=PROFILE_URL, count=5))

    assert raised.value.code == ErrorCode.DOUYIN_UPSTREAM_REDIRECT
    assert private_location not in raised.value.message
    assert raised.value.public_details()["redirected"] is True


def test_cookie_api_classifies_empty_response_as_invalid(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    _mock_cookie_client(
        monkeypatch,
        [FakeResponse(payload=None, content_type="application/json", text="", json_error=True)],
    )

    with pytest.raises(AppError) as raised:
        DouyinCookieProfileProvider().scan(ProfileScanRequest(profile_url=PROFILE_URL, count=5))

    assert raised.value.code == ErrorCode.DOUYIN_RESPONSE_INVALID


def test_cookie_api_empty_list_returns_no_public_works(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    _mock_cookie_client(
        monkeypatch,
        [FakeResponse(payload={"aweme_list": [], "has_more": False, "max_cursor": "0"})],
    )

    with pytest.raises(AppError) as raised:
        DouyinCookieProfileProvider().scan(ProfileScanRequest(profile_url=PROFILE_URL, count=5))

    assert raised.value.code == ErrorCode.DOUYIN_NO_PUBLIC_WORKS


def test_cookie_api_invalid_pagination_without_valid_items_is_an_error(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    _mock_cookie_client(
        monkeypatch,
        [FakeResponse(payload={"aweme_list": [{"broken": True}]})],
    )

    with pytest.raises(AppError) as raised:
        DouyinCookieProfileProvider().scan(ProfileScanRequest(profile_url=PROFILE_URL, count=5))

    assert raised.value.code == ErrorCode.DOUYIN_PAGINATION_INVALID
    assert raised.value.public_details()["invalid_item_count"] == 1


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (
            httpx.ReadTimeout("synthetic timeout", request=httpx.Request("GET", "https://www.douyin.com/")),
            ErrorCode.DOUYIN_UPSTREAM_TIMEOUT,
        ),
        (
            httpx.ConnectError("synthetic network error", request=httpx.Request("GET", "https://www.douyin.com/")),
            ErrorCode.DOUYIN_UPSTREAM_UNAVAILABLE,
        ),
    ],
)
def test_cookie_api_network_failures_are_bounded(monkeypatch, error: Exception, expected_code: str) -> None:
    _configure_synthetic_cookie(monkeypatch)
    calls = _mock_cookie_client(monkeypatch, [error])

    with pytest.raises(AppError) as raised:
        DouyinCookieProfileProvider().scan(ProfileScanRequest(profile_url=PROFILE_URL, count=5))

    assert raised.value.code == expected_code
    assert len(calls) == 2
    assert raised.value.public_details()["retry_count"] == 1


def test_cookie_provider_logs_only_safe_structured_fields(monkeypatch, caplog) -> None:
    _configure_synthetic_cookie(monkeypatch)
    _mock_cookie_client(monkeypatch, [FakeResponse(status_code=403, payload={})])

    with caplog.at_level(logging.INFO, logger="app.services.profile_scan"):
        with pytest.raises(AppError):
            DouyinCookieProfileProvider().scan(ProfileScanRequest(profile_url=PROFILE_URL, count=5))

    serialized = json.dumps([record.__dict__ for record in caplog.records], ensure_ascii=False, default=str)
    assert "douyin_cookie_provider" in serialized
    assert SYNTHETIC_COOKIE not in serialized
    assert "Cookie" not in serialized
    assert "request_headers" not in serialized


def test_cookie_self_test_and_status_do_not_create_jobs(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    _mock_cookie_client(
        monkeypatch,
        [
            FakeResponse(
                payload={
                    "aweme_list": [_aweme("7622653084993647603")],
                    "has_more": False,
                    "max_cursor": "0",
                }
            )
        ],
    )
    db = SessionLocal()
    try:
        before = db.query(Job).count()
    finally:
        db.close()

    status_response = client.get("/api/settings/data-sources")
    test_response = client.post(
        "/api/settings/data-sources/douyin/test",
        json={"profile_url": PROFILE_URL, "count": 5},
    )

    db = SessionLocal()
    try:
        after = db.query(Job).count()
    finally:
        db.close()
    combined = status_response.text + test_response.text
    assert status_response.status_code == 200
    assert test_response.status_code == 200
    assert test_response.json()["test"]["status"] == "ok"
    assert before == after
    assert SYNTHETIC_COOKIE not in combined
    assert status_response.json()["data_sources"]["masked_cookie"] == "********"
    assert status_response.headers["cache-control"] == "no-store"
    assert test_response.headers["cache-control"] == "no-store"
    sources = {source["id"]: source for source in status_response.json()["data_sources"]["sources"]}
    assert sources["cookie_api"]["role"] == "main"
    assert sources["manual_links"]["role"] == "fallback"


def test_invalid_cookie_update_does_not_overwrite_existing_cookie(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)

    response = client.put(
        "/api/settings/data-sources/douyin",
        json={"douyin_cookie": "sessionid=your_cookie; uid_tt=your_uid"},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == ErrorCode.DOUYIN_COOKIE_INVALID
    assert response.headers["cache-control"] == "no-store"
    assert effective_douyin_settings()["cookie"] == SYNTHETIC_COOKIE
    if runtime_settings.LOCAL_SETTINGS_PATH.exists():
        assert SYNTHETIC_COOKIE not in runtime_settings.LOCAL_SETTINGS_PATH.read_text(encoding="utf-8")


def test_cookie_self_test_hard_caps_count_at_five(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    calls = _mock_cookie_client(
        monkeypatch,
        [
            FakeResponse(
                payload={
                    "aweme_list": [_aweme("7622653084993647603")],
                    "has_more": False,
                    "max_cursor": "0",
                }
            )
        ],
    )

    response = client.post(
        "/api/settings/data-sources/douyin/test",
        json={"profile_url": PROFILE_URL, "count": 999},
    )

    assert response.status_code == 200
    assert response.json()["test"]["status"] == "ok"
    assert calls[0]["params"]["count"] == 5


def test_cookie_self_test_rejects_invalid_cookie_without_network(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch, "sessionid=synthetic_only")
    calls = _mock_cookie_client(monkeypatch, [FakeResponse(payload={"aweme_list": []})])

    response = client.post(
        "/api/settings/data-sources/douyin/test",
        json={"profile_url": PROFILE_URL, "count": 5},
    )

    test_payload = response.json()["test"]
    assert response.status_code == 200
    assert test_payload["configured"] is False
    assert test_payload["api_checked"] is False
    assert test_payload["error_code"] == ErrorCode.DOUYIN_LOGIN_REQUIRED
    assert calls == []


def test_failed_profile_job_never_stores_cookie(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    monkeypatch.setattr(settings, "profile_scan_provider", "cookie_api")
    _mock_cookie_client(monkeypatch, [FakeResponse(status_code=403, payload={}, text="forbidden")])

    create_response = client.post(
        "/api/jobs/profile-scan",
        json={"profile_url": PROFILE_URL, "count": 5, "max_pages": 1},
    )
    job_response = client.get(f"/api/jobs/{create_response.json()['job_id']}")
    serialized = job_response.text

    assert create_response.status_code == 200
    assert job_response.status_code == 200
    assert job_response.json()["job"]["status"] == "failed"
    assert SYNTHETIC_COOKIE not in serialized
    assert "request_headers" not in serialized


def test_successful_profile_job_never_stores_cookie(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    monkeypatch.setattr(settings, "profile_scan_provider", "cookie_api")
    _mock_cookie_client(
        monkeypatch,
        [
            FakeResponse(
                payload={
                    "aweme_list": [_aweme("7622653084993647603")],
                    "has_more": False,
                    "max_cursor": "0",
                }
            )
        ],
    )

    create_response = client.post(
        "/api/jobs/profile-scan",
        json={"profile_url": PROFILE_URL, "count": 5, "max_pages": 1},
    )
    job_response = client.get(f"/api/jobs/{create_response.json()['job_id']}")
    db = SessionLocal()
    try:
        stored_job = db.get(Job, create_response.json()["job_id"])
        stored_payload = " ".join(
            str(value or "")
            for value in (
                stored_job.message,
                stored_job.result_json,
                stored_job.error_code,
            )
        )
    finally:
        db.close()

    assert job_response.json()["job"]["status"] == "success"
    assert SYNTHETIC_COOKIE not in job_response.text
    assert SYNTHETIC_COOKIE not in stored_payload


def test_manual_creator_import_never_writes_cookie_to_artifacts(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)

    response = client.post(
        "/api/creator-clone/import",
        json={
            "title": "合成素材池",
            "manual_links": "https://www.douyin.com/video/7622653084993647603",
            "count": 5,
        },
    )

    assert response.status_code == 200
    assert SYNTHETIC_COOKIE not in response.text
    for path in settings.creator_clones_dir.rglob("*"):
        if path.is_file() and path.stat().st_size <= 2_000_000:
            assert SYNTHETIC_COOKIE not in path.read_text(encoding="utf-8", errors="ignore")


def test_cookie_profile_import_never_writes_cookie_to_creator_artifacts(monkeypatch) -> None:
    _configure_synthetic_cookie(monkeypatch)
    monkeypatch.setattr(settings, "profile_scan_provider", "cookie_api")
    _mock_cookie_client(
        monkeypatch,
        [
            FakeResponse(
                payload={
                    "aweme_list": [_aweme("7622653084993647603")],
                    "has_more": False,
                    "max_cursor": "0",
                }
            )
        ],
    )

    response = client.post(
        "/api/creator-clone/import",
        json={"title": "合成 Cookie 素材池", "profile_url": PROFILE_URL, "count": 5},
    )

    assert response.status_code == 200
    assert SYNTHETIC_COOKIE not in response.text
    for path in settings.creator_clones_dir.rglob("*"):
        if path.is_file() and path.stat().st_size <= 2_000_000:
            assert SYNTHETIC_COOKIE not in path.read_text(encoding="utf-8", errors="ignore")


def test_frontend_does_not_persist_cookie_in_browser_storage() -> None:
    scripts = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            settings.project_root / "app/static/app.js",
            settings.project_root / "app/static/modules/settings-panel.js",
        )
    )
    forbidden = re.compile(r"(?:localStorage|sessionStorage)[^\n]*(?:douyin[_-]?cookie|douyinCookie)", re.I)

    assert not forbidden.search(scripts)
    assert "elements.douyinCookieInput.value = \"\"" in scripts
