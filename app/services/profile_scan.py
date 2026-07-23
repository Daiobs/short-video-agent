from __future__ import annotations

import html
import csv
import io
import json
import logging
import re
import time
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx

from app.config import settings
from app.errors import AppError, ErrorCode
from app.providers.profile_base import (
    ProfileScanRequest,
    ProfileScanResult,
    ProfileVideoItem,
    build_profile_summary,
    sorted_profile_items,
)
from app.services.douyin_url_parser import extract_aweme_id, extract_first_url
from app.services.runtime_settings import effective_douyin_settings


logger = logging.getLogger(__name__)
PROFILE_URL_RE = re.compile(r"https?://(?:www\.)?douyin\.com/[^\s]+", re.I)
SEC_USER_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{8,128}$")
COOKIE_LOGIN_KEYS = ("sessionid", "sid_guard", "uid_tt", "uid_tt_ss", "sid_tt")
COOKIE_SESSION_KEYS = ("sessionid", "sessionid_ss", "sid_tt")
COOKIE_IMPORTANT_KEYS = (
    "sessionid",
    "sid_guard",
    "uid_tt",
    "uid_tt_ss",
    "sid_tt",
    "passport_csrf_token",
    "passport_csrf_token_default",
    "s_v_web_id",
    "ttwid",
    "msToken",
    "odin_tt",
)
COOKIE_MAX_LENGTH = 32_768
COOKIE_MAX_PAIR_COUNT = 256
COOKIE_API_ALLOWED_HOSTS = ("www.douyin.com",)
COOKIE_API_TIMEOUT_SECONDS = 8.0
COOKIE_API_MAX_ATTEMPTS = 2
COOKIE_API_RETRY_BACKOFF_SECONDS = 0.15
COOKIE_API_MAX_PAGES = 20
COOKIE_API_MAX_ITEMS = 200
COOKIE_API_MAX_CONSECUTIVE_NO_NEW_PAGES = 2
COOKIE_PLACEHOLDER_VALUES = {
    "cookie",
    "cookie_value",
    "paste_cookie_here",
    "replace_me",
    "your_cookie",
    "your_cookie_here",
}
DOUYIN_COOKIE_API_ENDPOINTS = (
    "https://www.douyin.com/aweme/v1/web/aweme/post/",
    "https://www.douyin.com/aweme/v1/web/user/post/",
)


class ManualLinksProfileProvider:
    name = "manual_links"

    def scan(self, request: ProfileScanRequest) -> ProfileScanResult:
        raw_text = request.manual_links or ""
        values = [line.strip() for line in raw_text.splitlines() if line.strip()]
        if not values and raw_text.strip():
            values = [raw_text.strip()]
        seen: set[str] = set()
        items: list[ProfileVideoItem] = []
        duplicate_count = 0
        invalid_count = 0
        for value in values:
            try:
                aweme_id = extract_aweme_id_or_short_url(value)
            except AppError:
                invalid_count += 1
                continue
            if aweme_id in seen:
                duplicate_count += 1
                continue
            seen.add(aweme_id)
            source_url = extract_first_url(value) or f"https://www.douyin.com/video/{aweme_id}"
            media_type = _media_type_from_url(source_url) or "unknown"
            items.append(
                ProfileVideoItem(
                    aweme_id=aweme_id,
                    title=f"抖音作品 {aweme_id}",
                    desc=value[:180],
                    webpage_url=source_url,
                    media_type=media_type,
                    source_provider=self.name,
                )
            )
        if not items:
            raise AppError(ErrorCode.AWEME_ID_NOT_FOUND, "多作品链接中没有找到有效 aweme_id。")
        limited = sorted_profile_items(items[: _safe_count(request.count)], request.sort_by)
        stats = {
            "input_count": len(values),
            "recognized_count": len(items),
            "duplicate_count": duplicate_count,
            "invalid_count": invalid_count,
            "limited_count": len(limited),
        }
        result = ProfileScanResult(
            provider=self.name,
            profile_url=request.profile_url or "",
            sec_user_id=request.sec_user_id or "",
            items=limited,
            has_more=len(items) > len(limited),
            warnings=[
                f"多链接导入：成功识别 {stats['recognized_count']} 条，去重 {stats['duplicate_count']} 条，忽略 {stats['invalid_count']} 条无效内容。",
                "多链接模式只提取 aweme_id；互动数据会在进入单作品解析后继续补齐。",
            ],
            import_stats=stats,
        )
        result.summary = build_profile_summary(result)
        return result


class StructuredItemsProfileProvider:
    name = "structured_items"

    def scan(self, request: ProfileScanRequest) -> ProfileScanResult:
        raw_text = (request.structured_items or "").strip()
        rows = _parse_structured_items(raw_text)
        seen: set[str] = set()
        items: list[ProfileVideoItem] = []
        duplicate_count = 0
        invalid_count = 0
        for row in rows:
            try:
                item = _profile_item_from_structured_row(row)
            except AppError:
                invalid_count += 1
                continue
            if item.aweme_id in seen:
                duplicate_count += 1
                continue
            seen.add(item.aweme_id)
            items.append(item)
        if not items:
            raise AppError(ErrorCode.AWEME_ID_NOT_FOUND, "JSON / CSV 中没有找到有效作品。")
        limited = sorted_profile_items(items[: _safe_count(request.count)], request.sort_by)
        stats = {
            "input_count": len(rows),
            "recognized_count": len(items),
            "duplicate_count": duplicate_count,
            "invalid_count": invalid_count,
            "limited_count": len(limited),
        }
        result = ProfileScanResult(
            provider=self.name,
            profile_url=request.profile_url or "",
            sec_user_id=request.sec_user_id or "",
            items=limited,
            has_more=len(items) > len(limited),
            warnings=[
                f"JSON / CSV 导入：成功识别 {stats['recognized_count']} 条，去重 {stats['duplicate_count']} 条，忽略 {stats['invalid_count']} 条无效内容。",
            ],
            import_stats=stats,
        )
        result.summary = build_profile_summary(result)
        return result


class DouyinPublicProfileProvider:
    name = "douyin_public"

    def scan(self, request: ProfileScanRequest) -> ProfileScanResult:
        profile_url = normalize_profile_url(request.profile_url, request.sec_user_id)
        sec_user_id = extract_sec_user_id(profile_url, request.sec_user_id)
        if not sec_user_id:
            raise AppError(ErrorCode.SEC_USER_ID_NOT_FOUND)

        try:
            with httpx.Client(timeout=8.0, follow_redirects=True, trust_env=False) as client:
                response = client.get(
                    profile_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 short-video-agent profile scan",
                        "Accept": "text/html,application/xhtml+xml",
                    },
                )
        except httpx.HTTPError as error:
            raise AppError(ErrorCode.PROFILE_SCAN_FAILED, f"主页请求失败：{str(error)[:160]}") from error

        if response.status_code in {401, 403, 429}:
            raise AppError(ErrorCode.PROFILE_SCAN_NEEDS_FALLBACK)
        if response.status_code >= 400:
            raise AppError(ErrorCode.PROFILE_SCAN_FAILED, f"主页请求失败：HTTP {response.status_code}。")

        items = extract_profile_items_from_html(response.text, sec_user_id=sec_user_id)
        if not items:
            if _is_douyin_risk_control_page(response.text):
                raise AppError(
                    ErrorCode.DOUYIN_RISK_CONTROL,
                    "主页扫描失败：抖音返回了浏览器校验脚本。当前不登录、不使用 Cookie、不绕风控，请改用多作品链接粘贴或单作品解析。",
                )
            if _has_aweme_payload_marker(response.text):
                raise AppError(ErrorCode.PROFILE_SCAN_STRUCTURE_CHANGED)
            raise AppError(ErrorCode.PROFILE_SCAN_NEEDS_FALLBACK)
        sorted_items = sorted_profile_items(items[: _safe_count(request.count)], request.sort_by)
        result = ProfileScanResult(
            provider=self.name,
            profile_url=profile_url,
            sec_user_id=sec_user_id,
            items=sorted_items,
            has_more=len(items) > len(sorted_items),
            warnings=["公开主页扫描不使用 Cookie、不登录、不绕风控；结果取决于页面公开数据。"],
        )
        result.summary = build_profile_summary(result)
        return result


class DouyinCookieProfileProvider:
    name = "cookie_api"
    endpoint = DOUYIN_COOKIE_API_ENDPOINTS[0]
    endpoints = DOUYIN_COOKIE_API_ENDPOINTS

    def scan(self, request: ProfileScanRequest) -> ProfileScanResult:
        douyin_settings = effective_douyin_settings()
        cookie_diagnostics = inspect_douyin_cookie(douyin_settings["cookie"])
        _require_cookie_request_ready(cookie_diagnostics)
        profile_url = normalize_profile_url(request.profile_url, request.sec_user_id)
        sec_user_id = extract_sec_user_id(profile_url, request.sec_user_id)
        if not sec_user_id:
            raise AppError(ErrorCode.SEC_USER_ID_NOT_FOUND)

        headers = _douyin_cookie_api_headers(douyin_settings, referer=profile_url)
        max_pages = max(1, min(int(request.max_pages or settings.profile_scan_max_pages), COOKIE_API_MAX_PAGES))
        count = _safe_count(request.count)
        page_count = max(1, min(int(settings.profile_scan_count_per_page or 20), 50))
        endpoint_failures: list[tuple[str, AppError]] = []
        selected_endpoint = ""
        items: list[ProfileVideoItem] = []
        max_cursor = "0"
        has_more = False
        scan_meta: dict = {}
        for endpoint in self.endpoints:
            try:
                items, max_cursor, has_more, scan_meta = _fetch_douyin_cookie_api_items(
                    endpoint=endpoint,
                    sec_user_id=sec_user_id,
                    headers=headers,
                    max_pages=max_pages,
                    count=count,
                    page_count=page_count,
                    cookie_diagnostics=cookie_diagnostics,
                )
                selected_endpoint = endpoint
                break
            except AppError as error:
                endpoint_failures.append((endpoint, error))
                if not _can_try_next_cookie_endpoint(error):
                    raise

        if not items:
            if endpoint_failures:
                raise _combined_cookie_api_error(endpoint_failures)
            raise AppError(ErrorCode.DOUYIN_NO_PUBLIC_WORKS)

        sorted_items = sorted_profile_items(items[:count], request.sort_by)
        warnings = [
            "个人账号 Cookie Web API 是主页扫描主路径；Cookie 仅保存在本机运行时配置，不写入数据库、Job、素材包、Prompt、报告或日志。",
        ]
        truncated_reason = str(scan_meta.get("truncated_reason") or "")
        if truncated_reason:
            warnings.append(_pagination_warning(truncated_reason, scan_meta))
        if len(sorted_items) < count and not has_more:
            warnings.append(
                f"Cookie API 本次实际返回 {len(sorted_items)} 条可解析作品；"
                "抖音主页显示的总作品数可能包含接口不可见、权限受限、已隐藏或当前 Web API 未继续返回的作品。"
            )

        result = ProfileScanResult(
            provider=self.name,
            profile_url=profile_url,
            sec_user_id=sec_user_id,
            items=sorted_items,
            has_more=has_more or len(items) > len(sorted_items),
            next_cursor=max_cursor,
            warnings=warnings,
            scan_meta={
                **scan_meta,
                "endpoint": _safe_endpoint_path(selected_endpoint),
                "item_count": len(sorted_items),
            },
        )
        result.summary = build_profile_summary(result)
        return result


class ExternalApiProfileProvider:
    name = "external_api"

    def scan(self, request: ProfileScanRequest) -> ProfileScanResult:
        if not settings.profile_scan_api_base:
            raise AppError(ErrorCode.PROFILE_SCAN_API_NOT_CONFIGURED)
        raise AppError(
            ErrorCode.PROFILE_SCAN_FAILED,
            "external_api provider 仅预留接口形态，本轮不接入第三方扫描服务。",
        )


class DataSourceManager:
    source_ids = ("manual_links", "browser_dom", "cookie_api", "external_api")

    def __init__(self) -> None:
        self.manual_provider = ManualLinksProfileProvider()
        self.structured_provider = StructuredItemsProfileProvider()
        self.cookie_provider = DouyinCookieProfileProvider()
        self.public_provider = DouyinPublicProfileProvider()
        self.external_provider = ExternalApiProfileProvider()

    def supported_sources(self) -> tuple[str, ...]:
        return self.source_ids

    def scan(self, request: ProfileScanRequest) -> ProfileScanResult:
        normalized = normalize_profile_scan_request(request)
        if normalized.manual_links:
            return self.manual_provider.scan(normalized)
        if normalized.structured_items:
            return self.structured_provider.scan(normalized)

        provider_name = settings.profile_scan_provider or "cookie_api"
        if provider_name == "external_api":
            return self._scan_explicit_external(normalized)

        failures: list[AppError] = []
        if provider_name == "cookie_api" or bool((effective_douyin_settings()["cookie"] or "").strip()):
            try:
                return self._finalize(self.cookie_provider.scan(normalized), normalized, failures)
            except AppError as error:
                failures.append(error)

        try:
            return self._finalize(self.public_provider.scan(normalized), normalized, failures)
        except AppError:
            if failures:
                primary_error = failures[0]
                raise AppError(
                    primary_error.code,
                    f"{primary_error.message} "
                    "公开页面回退也未取得作品；请更新个人 Cookie，或使用作品链接、JSON/CSV、已有 Case 导入。",
                    details=primary_error.details,
                )
            raise

    def _scan_explicit_external(self, request: ProfileScanRequest) -> ProfileScanResult:
        result = self.external_provider.scan(request)
        return self._finalize(result, request, [])

    def _finalize(
        self,
        result: ProfileScanResult,
        request: ProfileScanRequest,
        failures: list[AppError],
    ) -> ProfileScanResult:
        result.items = sorted_profile_items(result.items, request.sort_by)
        if failures:
            result.warnings.extend(
                f"个人账号 Cookie Web API 当前不可用（{error.code}）；已使用公开页面安全回退。"
                for error in failures
            )
            result.scan_meta = {
                **result.scan_meta,
                "fallback_used": True,
                "fallback_from": "cookie_api",
                "fallback_error_codes": [error.code for error in failures[:3]],
            }
        result.summary = build_profile_summary(result)
        return result


def scan_profile(request: ProfileScanRequest) -> ProfileScanResult:
    return DataSourceManager().scan(request)


def inspect_douyin_cookie(cookie: str) -> dict:
    cleaned = (cookie or "").strip()
    has_cookie_prefix = cleaned.lower().startswith("cookie:")
    if has_cookie_prefix:
        cleaned = cleaned.split(":", 1)[1].strip()
    keys: list[str] = []
    malformed_count = 0
    empty_value_count = 0
    placeholder_count = 0
    duplicate_keys: list[str] = []
    seen_keys: set[str] = set()
    for raw_part in cleaned.split(";"):
        part = raw_part.strip()
        if not part:
            continue
        if "=" not in part:
            malformed_count += 1
            continue
        key, value = part.split("=", 1)
        key = key.strip()[:80]
        value = value.strip()
        if not key or not re.fullmatch(r"[A-Za-z0-9_.\-]{1,80}", key):
            malformed_count += 1
            continue
        keys.append(key)
        if key in seen_keys and key not in duplicate_keys:
            duplicate_keys.append(key)
        seen_keys.add(key)
        if not value:
            empty_value_count += 1
        if _looks_like_cookie_placeholder(value):
            placeholder_count += 1
    key_set = set(keys)
    present_important = [key for key in COOKIE_IMPORTANT_KEYS if key in key_set]
    missing_login = [key for key in COOKIE_LOGIN_KEYS if key not in key_set]
    login_key_count = len([key for key in COOKIE_LOGIN_KEYS if key in key_set])
    has_session_key = any(key in key_set for key in COOKIE_SESSION_KEYS)
    too_long = len(cleaned) > COOKIE_MAX_LENGTH
    too_many_pairs = len(keys) > COOKIE_MAX_PAIR_COUNT
    format_valid = bool(cleaned) and not any(
        (
            malformed_count,
            empty_value_count,
            placeholder_count,
            len(duplicate_keys),
            int(too_long),
            int(too_many_pairs),
        )
    )
    login_state_sufficient = has_session_key and login_key_count >= 2
    return {
        "has_cookie": bool(cleaned),
        "cookie_length": len(cleaned),
        "pair_count": len(keys),
        "malformed_pair_count": malformed_count,
        "empty_value_count": empty_value_count,
        "placeholder_count": placeholder_count,
        "duplicate_key_count": len(duplicate_keys),
        "duplicate_keys": duplicate_keys,
        "too_long": too_long,
        "too_many_pairs": too_many_pairs,
        "has_cookie_prefix": has_cookie_prefix,
        "contains_semicolon": ";" in cleaned,
        "present_important_keys": present_important,
        "missing_login_keys": missing_login,
        "login_key_count": login_key_count,
        "format_valid": format_valid,
        "login_state_sufficient": login_state_sufficient,
        "looks_complete": format_valid and login_state_sufficient,
    }


def public_cookie_diagnostics(cookie_diagnostics: dict) -> dict:
    return {
        "has_cookie": bool(cookie_diagnostics.get("has_cookie")),
        "pair_count": int(cookie_diagnostics.get("pair_count") or 0),
        "login_key_count": int(cookie_diagnostics.get("login_key_count") or 0),
        "present_important_keys": list(cookie_diagnostics.get("present_important_keys") or []),
        "missing_login_keys": list(cookie_diagnostics.get("missing_login_keys") or []),
    }


def _looks_like_cookie_placeholder(value: str) -> bool:
    normalized = (value or "").strip().lower()
    if not normalized:
        return False
    if normalized in COOKIE_PLACEHOLDER_VALUES:
        return True
    if normalized.startswith(("<", "${")) and normalized.endswith((">", "}")):
        return True
    return normalized.startswith("your_") or normalized.endswith("_here")


def _cookie_validation_error(cookie_diagnostics: dict) -> AppError | None:
    if not cookie_diagnostics.get("has_cookie"):
        return AppError(ErrorCode.DOUYIN_COOKIE_NOT_CONFIGURED)
    if not cookie_diagnostics.get("format_valid"):
        return AppError(ErrorCode.DOUYIN_COOKIE_INVALID)
    if not cookie_diagnostics.get("login_state_sufficient"):
        return AppError(ErrorCode.DOUYIN_LOGIN_REQUIRED)
    return None


def _require_cookie_request_ready(cookie_diagnostics: dict) -> None:
    error = _cookie_validation_error(cookie_diagnostics)
    if error:
        raise error


def test_douyin_cookie_api(profile_url: str = "", sec_user_id: str = "", count: int = 5) -> dict:
    douyin_settings = effective_douyin_settings()
    cookie_diagnostics = inspect_douyin_cookie(douyin_settings["cookie"])
    result = {
        "provider": DouyinCookieProfileProvider.name,
        "endpoint": _safe_endpoint_path(DouyinCookieProfileProvider.endpoint),
        "candidate_endpoints": [_safe_endpoint_path(endpoint) for endpoint in DouyinCookieProfileProvider.endpoints],
        "configured": bool(cookie_diagnostics["looks_complete"]),
        "cookie_diagnostics": public_cookie_diagnostics(cookie_diagnostics),
        "user_agent_configured": bool((douyin_settings["user_agent"] or "").strip()),
        "api_checked": False,
        "status": "not_configured" if not cookie_diagnostics["has_cookie"] else "config_only",
        "message": "",
        "safe_next_steps": [],
    }
    validation_error = _cookie_validation_error(cookie_diagnostics)
    if validation_error:
        result["status"] = {
            ErrorCode.DOUYIN_COOKIE_NOT_CONFIGURED: "not_configured",
            ErrorCode.DOUYIN_COOKIE_INVALID: "invalid_cookie",
            ErrorCode.DOUYIN_LOGIN_REQUIRED: "login_required",
        }.get(validation_error.code, "invalid_cookie")
        result["error_code"] = validation_error.code
        result["message"] = validation_error.message
        result["safe_next_steps"] = _cookie_error_next_steps(validation_error.code)
        return result
    if not (profile_url or sec_user_id):
        result["message"] = "Cookie 结构已检查。输入主页 URL 或 sec_user_id 后，可继续测试 Cookie Web API 是否能返回作品列表。"
        result["safe_next_steps"] = ["在创作者克隆输入框填入主页 URL 后，再点击 Cookie API 自检。"]
        return result

    try:
        normalized_url = normalize_profile_url(profile_url or None, sec_user_id or None)
        target_sec_user_id = extract_sec_user_id(normalized_url, sec_user_id or None)
        if not target_sec_user_id:
            raise AppError(ErrorCode.SEC_USER_ID_NOT_FOUND)
        headers = _douyin_cookie_api_headers(douyin_settings, referer=normalized_url)
        endpoint_results = []
        selected_diag = None
        for endpoint in DouyinCookieProfileProvider.endpoints:
            endpoint_result = _test_douyin_cookie_api_endpoint(
                endpoint=endpoint,
                sec_user_id=target_sec_user_id,
                headers=headers,
                count=max(1, min(int(count or 5), 5)),
            )
            endpoint_results.append(endpoint_result)
            if endpoint_result.get("status") == "ok":
                selected_diag = endpoint_result
                break
            if selected_diag is None:
                selected_diag = endpoint_result
            if not (
                endpoint_result.get("error_code") == ErrorCode.DOUYIN_UPSTREAM_UNAVAILABLE
                and endpoint_result.get("status_code") in {404, 405}
            ):
                break
        response_diag = selected_diag or (endpoint_results[-1] if endpoint_results else {})
        result.update(
            {
                "api_checked": True,
                "endpoint_results": endpoint_results,
                "selected_endpoint": response_diag.get("endpoint", ""),
                "status_code": response_diag.get("status_code"),
                "content_type": response_diag.get("content_type", ""),
                "redirected": bool(response_diag.get("redirected")),
                "is_json": bool(response_diag.get("is_json")),
                "aweme_count": int(response_diag.get("aweme_count") or 0),
                "has_more": bool(response_diag.get("has_more")),
                "retry_count": int(response_diag.get("retry_count") or 0),
            }
        )
        if response_diag.get("status") == "ok":
            result["status"] = "ok"
            result["message"] = f"个人账号 Cookie Web API 可用，本次返回 {response_diag.get('aweme_count', 0)} 条作品。"
        else:
            error_code = str(response_diag.get("error_code") or ErrorCode.DOUYIN_RESPONSE_INVALID)
            result["status"] = str(response_diag.get("status") or "failed")
            result["error_code"] = error_code
            result["message"] = AppError(error_code).message
        result["safe_next_steps"] = _cookie_test_next_steps(result)
        return result
    except AppError as error:
        result.update(
            {
                "api_checked": False,
                "status": "invalid_target",
                "error_code": error.code,
                "message": error.message,
                "safe_next_steps": ["检查主页 URL / sec_user_id 是否正确，或改用多作品链接粘贴。"],
            }
        )
        return result
    except httpx.HTTPError:
        result.update(
            {
                "api_checked": True,
                "status": "request_failed",
                "error_code": ErrorCode.DOUYIN_UPSTREAM_UNAVAILABLE,
                "message": AppError(ErrorCode.DOUYIN_UPSTREAM_UNAVAILABLE).message,
                "safe_next_steps": _cookie_error_next_steps(ErrorCode.DOUYIN_UPSTREAM_UNAVAILABLE),
            }
        )
        return result


def normalize_profile_scan_request(request: ProfileScanRequest) -> ProfileScanRequest:
    profile_url = (request.profile_url or "").strip() or None
    sec_user_id = (request.sec_user_id or "").strip() or None
    raw_target = profile_url or sec_user_id or ""
    if re.match(r"^(?:(?:www\.)?douyin\.com/user/|v\.douyin\.com/)", raw_target, re.I):
        profile_url = f"https://{raw_target}"
        sec_user_id = None
    return ProfileScanRequest(
        profile_url=profile_url,
        sec_user_id=sec_user_id,
        manual_links=(request.manual_links or "").strip() or None,
        structured_items=(request.structured_items or "").strip() or None,
        count=_safe_count(request.count),
        max_pages=max(1, min(int(request.max_pages or settings.profile_scan_max_pages), COOKIE_API_MAX_PAGES)),
        sort_by=request.sort_by or "like_count",
    )


def extract_aweme_id_or_short_url(value: str) -> str:
    try:
        return extract_aweme_id(value)
    except AppError:
        url = extract_first_url(value)
        if url and urlparse(url).netloc.lower().endswith("v.douyin.com"):
            return _resolve_douyin_short_aweme_id(url)
        raise


def normalize_profile_url(profile_url: str | None, sec_user_id: str | None) -> str:
    if profile_url:
        value = extract_first_url(profile_url) or profile_url.strip()
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            raise AppError(ErrorCode.INVALID_PROFILE_URL)
        host = parsed.netloc.lower()
        if host.endswith("v.douyin.com"):
            return _resolve_douyin_short_profile_url(value)
        if host.endswith("iesdouyin.com"):
            shared_profile_url = _profile_url_from_share_url(value)
            if shared_profile_url:
                return shared_profile_url
            raise AppError(ErrorCode.INVALID_PROFILE_URL, "该短链不是主页链接。请改用单作品解析或多作品链接粘贴。")
        if not (host == "douyin.com" or host.endswith(".douyin.com")):
            raise AppError(ErrorCode.INVALID_PROFILE_URL, "仅支持抖音主页 URL。")
        return value
    if sec_user_id and SEC_USER_ID_RE.fullmatch(sec_user_id.strip()):
        return f"https://www.douyin.com/user/{sec_user_id.strip()}"
    raise AppError(ErrorCode.INVALID_PROFILE_URL)


def extract_sec_user_id(profile_url: str | None, explicit_sec_user_id: str | None = None) -> str:
    if explicit_sec_user_id and SEC_USER_ID_RE.fullmatch(explicit_sec_user_id.strip()):
        return explicit_sec_user_id.strip()
    if not profile_url:
        return ""
    parsed = urlparse(profile_url.strip())
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "user" and SEC_USER_ID_RE.fullmatch(parts[1]):
        return parts[1]
    if len(parts) >= 2 and parts[0] == "share" and parts[1] == "user":
        query_sec_uid = (parse_qs(parsed.query).get("sec_uid") or [""])[0]
        candidate = query_sec_uid or (parts[2] if len(parts) >= 3 else "")
        if SEC_USER_ID_RE.fullmatch(candidate):
            return candidate
    query_sec_uid = (parse_qs(parsed.query).get("sec_user_id") or parse_qs(parsed.query).get("sec_uid") or [""])[0]
    if SEC_USER_ID_RE.fullmatch(query_sec_uid):
        return query_sec_uid
    return ""


def _resolve_douyin_short_profile_url(url: str) -> str:
    try:
        with httpx.Client(timeout=5.0, follow_redirects=False, trust_env=False) as client:
            response = client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 short-video-agent profile scan",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
    except httpx.HTTPError as error:
        raise AppError(ErrorCode.INVALID_PROFILE_URL, f"短链解析失败：{str(error)[:160]}") from error

    location = response.headers.get("location", "")
    if not location and response.is_redirect:
        location = response.headers.get("Location", "")
    if not location:
        raise AppError(ErrorCode.INVALID_PROFILE_URL, "短链没有返回主页跳转地址。请粘贴完整主页 URL。")
    target = urljoin(url, location)
    shared_profile_url = _profile_url_from_share_url(target)
    if shared_profile_url:
        return shared_profile_url
    parsed = urlparse(target)
    if "/video/" in parsed.path or "/note/" in parsed.path:
        raise AppError(ErrorCode.INVALID_PROFILE_URL, "这是作品链接，不是主页链接。请使用单作品解析或多作品链接粘贴。")
    raise AppError(ErrorCode.INVALID_PROFILE_URL, "短链未跳转到可识别的抖音主页。")


def _resolve_douyin_short_aweme_id(url: str) -> str:
    try:
        with httpx.Client(timeout=5.0, follow_redirects=False, trust_env=False) as client:
            response = client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 short-video-agent profile pool",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
    except httpx.HTTPError as error:
        raise AppError(ErrorCode.AWEME_ID_NOT_FOUND, f"短链解析失败：{str(error)[:160]}") from error

    location = response.headers.get("location", "") or response.headers.get("Location", "")
    if not location:
        raise AppError(ErrorCode.AWEME_ID_NOT_FOUND, "短链没有返回作品跳转地址。")
    target = urljoin(url, location)
    return extract_aweme_id(target)


def _profile_url_from_share_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if not host.endswith("iesdouyin.com"):
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0] != "share" or parts[1] != "user":
        return ""
    query_sec_uid = (parse_qs(parsed.query).get("sec_uid") or [""])[0]
    sec_uid = query_sec_uid or (parts[2] if len(parts) >= 3 else "")
    if not SEC_USER_ID_RE.fullmatch(sec_uid):
        return ""
    return f"https://www.douyin.com/user/{sec_uid}"


def _parse_structured_items(text: str) -> list[dict]:
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _parse_csv_items(text)
    if isinstance(payload, dict):
        if isinstance(payload.get("items"), list):
            payload = payload["items"]
        elif isinstance(payload.get("samples"), list):
            payload = payload["samples"]
        elif isinstance(payload.get("aweme_list"), list):
            payload = payload["aweme_list"]
        elif isinstance(payload.get("awemeList"), list):
            payload = payload["awemeList"]
        elif isinstance(payload.get("videos"), list):
            payload = payload["videos"]
        else:
            payload = [payload]
    if not isinstance(payload, list):
        raise AppError(ErrorCode.AWEME_ID_NOT_FOUND, "JSON / CSV 作品列表格式无效。")
    return [item for item in payload if isinstance(item, dict)]


def _parse_csv_items(text: str) -> list[dict]:
    sample = text.strip()
    if not sample:
        return []
    reader = csv.DictReader(io.StringIO(sample))
    if reader.fieldnames and any(field for field in reader.fieldnames):
        return [dict(row) for row in reader]
    rows = []
    for line in sample.splitlines():
        value = line.strip()
        if value:
            rows.append({"source_url": value})
    return rows


def _field(row: dict, *names: str, default=""):
    for name in names:
        value = _nested_field(row, name)
        if value not in (None, ""):
            return value
    return default


def _nested_field(row: dict, name: str):
    current = row
    for part in name.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _profile_item_from_structured_row(row: dict) -> ProfileVideoItem:
    raw_id = str(_field(row, "aweme_id", "awemeId", "awemeIdStr", "id", default="")).strip()
    source_url = str(_field(row, "source_url", "webpage_url", "video_url", "url", "link", default="")).strip()
    aweme_value = raw_id or source_url
    aweme_id = extract_aweme_id_or_short_url(aweme_value)
    source_url = source_url or f"https://www.douyin.com/video/{aweme_id}"
    media_type = str(_field(row, "media_type", "type", default="")).strip().lower()
    if media_type in {"photo", "image_post", "note", "图文", "照片"}:
        media_type = "image"
    if media_type not in {"video", "image", "unknown"}:
        media_type = _media_type_from_url(source_url) or "unknown"
    title = str(_field(row, "title", "desc", "description", "caption", default=f"抖音作品 {aweme_id}")).strip()
    desc = str(_field(row, "desc", "description", "caption", default="")).strip()
    return ProfileVideoItem(
        aweme_id=aweme_id,
        title=title or f"抖音作品 {aweme_id}",
        desc=desc,
        author=str(_field(row, "author", "nickname", default="")).strip(),
        cover_url=str(_field(row, "cover_url", "cover", default="")).strip(),
        create_time=str(_field(row, "create_time", "publish_time", "发布时间", default="")).strip(),
        like_count=_safe_int(_field(row, "like_count", "likes", "digg_count", "statistics.digg_count", "点赞", default=0)),
        comment_count=_safe_int(_field(row, "comment_count", "comments", "statistics.comment_count", "评论", default=0)),
        share_count=_safe_int(_field(row, "share_count", "shares", "statistics.share_count", "分享", default=0)),
        collect_count=_safe_int(_field(row, "collect_count", "collects", "statistics.collect_count", "收藏", default=0)),
        view_count=_safe_int(_field(row, "view_count", "play_count", "statistics.play_count", default=0)),
        webpage_url=source_url,
        media_type=media_type,
        source_provider="structured_items",
    )


def extract_profile_items_from_html(html_text: str, sec_user_id: str = "") -> list[ProfileVideoItem]:
    decoded = html.unescape(unquote(html_text or ""))
    payloads = _extract_json_payloads(decoded)
    items: list[ProfileVideoItem] = []
    seen: set[str] = set()
    for payload in payloads:
        for raw_item in _walk_aweme_items(payload):
            item = normalize_profile_video_item(raw_item, sec_user_id=sec_user_id)
            if not item or item.aweme_id in seen:
                continue
            seen.add(item.aweme_id)
            items.append(item)
    if not items:
        for item in _extract_profile_items_from_links(decoded, sec_user_id=sec_user_id):
            if item.aweme_id in seen:
                continue
            seen.add(item.aweme_id)
            items.append(item)
    return items


def normalize_profile_video_item(raw: dict, sec_user_id: str = "") -> ProfileVideoItem | None:
    aweme_id = str(raw.get("aweme_id") or raw.get("awemeId") or raw.get("id") or "")
    if not re.fullmatch(r"\d{15,22}", aweme_id):
        return None
    desc = str(raw.get("desc") or raw.get("title") or raw.get("caption") or "")
    author = raw.get("author") if isinstance(raw.get("author"), dict) else {}
    statistics = raw.get("statistics") if isinstance(raw.get("statistics"), dict) else {}
    video = raw.get("video") if isinstance(raw.get("video"), dict) else {}
    images = raw.get("images") or raw.get("image_infos") or raw.get("imageInfos") or []
    image_post = raw.get("image_post_info") if isinstance(raw.get("image_post_info"), dict) else {}
    cover = raw.get("cover") if isinstance(raw.get("cover"), dict) else {}
    media_type = _media_type_from_aweme(raw, video, images, image_post)
    cover_url = (
        _first_url(video.get("cover"))
        or _first_url(video.get("origin_cover"))
        or _first_url(image_post.get("cover"))
        or _first_url(images)
        or _first_url(cover)
        or str(raw.get("cover_url") or "")
    )
    item_sec_user_id = str(author.get("sec_uid") or author.get("sec_user_id") or sec_user_id or "")
    return ProfileVideoItem(
        aweme_id=aweme_id,
        title=desc[:120] or f"抖音作品 {aweme_id}",
        desc=desc,
        author=str(author.get("nickname") or raw.get("nickname") or ""),
        sec_user_id=item_sec_user_id,
        cover_url=cover_url,
        create_time=str(raw.get("create_time") or raw.get("createTime") or ""),
        like_count=_safe_int(statistics.get("digg_count") or raw.get("digg_count")),
        comment_count=_safe_int(statistics.get("comment_count") or raw.get("comment_count")),
        share_count=_safe_int(statistics.get("share_count") or raw.get("share_count")),
        collect_count=_safe_int(statistics.get("collect_count") or raw.get("collect_count")),
        view_count=_safe_int(statistics.get("play_count") or raw.get("play_count")),
        duration=_safe_int(video.get("duration") or raw.get("duration")),
        webpage_url=f"https://www.douyin.com/{'note' if media_type == 'image' else 'video'}/{aweme_id}",
        media_type=media_type,
        source_provider=DouyinPublicProfileProvider.name,
    )


def _extract_json_payloads(text: str) -> list:
    payloads = []
    script_patterns = [
        r'<script[^>]+id=["\']RENDER_DATA["\'][^>]*>(.*?)</script>',
        r'<script[^>]+id=["\']SIGI_STATE["\'][^>]*>(.*?)</script>',
    ]
    for pattern in script_patterns:
        for match in re.finditer(pattern, text, re.S | re.I):
            payload = _json_loads(match.group(1).strip())
            if payload is not None:
                payloads.append(payload)
    for marker in ("aweme_list", "awemeList"):
        if marker in text:
            payload = _json_loads(_balanced_json_near_marker(text, marker))
            if payload is not None:
                payloads.append(payload)
    return payloads


def _has_aweme_payload_marker(text: str) -> bool:
    return "aweme_list" in (text or "") or "awemeList" in (text or "")


def _is_douyin_risk_control_page(text: str) -> bool:
    value = text or ""
    markers = ("_$jsvmprt", "byted_acrawler", "__ac_nonce", "secsdk-captcha")
    return any(marker in value for marker in markers)


def _extract_profile_items_from_links(text: str, sec_user_id: str = "") -> list[ProfileVideoItem]:
    items: list[ProfileVideoItem] = []
    patterns = (
        (re.compile(r"https?://(?:www\.)?douyin\.com/video/(\d{15,22})", re.I), "video"),
        (re.compile(r"https?://(?:www\.)?douyin\.com/note/(\d{15,22})", re.I), "image"),
        (re.compile(r"/video/(\d{15,22})", re.I), "video"),
        (re.compile(r"/note/(\d{15,22})", re.I), "image"),
    )
    seen: set[str] = set()
    for pattern, media_type in patterns:
        for match in pattern.finditer(text or ""):
            aweme_id = match.group(1)
            if aweme_id in seen:
                continue
            seen.add(aweme_id)
            items.append(
                ProfileVideoItem(
                    aweme_id=aweme_id,
                    title=f"抖音作品 {aweme_id}",
                    desc="公开主页链接提取，互动数据待进入单作品解析后补齐。",
                    sec_user_id=sec_user_id,
                    webpage_url=f"https://www.douyin.com/{'note' if media_type == 'image' else 'video'}/{aweme_id}",
                    media_type=media_type,
                    source_provider=DouyinPublicProfileProvider.name,
                )
            )
    return items


def _walk_aweme_items(value) -> list[dict]:
    items: list[dict] = []
    if isinstance(value, dict):
        for key in ("aweme_list", "awemeList", "post", "posts"):
            candidate = value.get(key)
            if isinstance(candidate, list):
                items.extend(item for item in candidate if isinstance(item, dict))
            elif isinstance(candidate, dict):
                items.extend(_walk_aweme_items(candidate))
        if re.fullmatch(r"\d{15,22}", str(value.get("aweme_id") or value.get("awemeId") or "")):
            items.append(value)
        for child in value.values():
            if isinstance(child, (dict, list)):
                items.extend(_walk_aweme_items(child))
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, (dict, list)):
                items.extend(_walk_aweme_items(child))
    return items


def _json_loads(value: str | None):
    if not value:
        return None
    candidate = value.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def _balanced_json_near_marker(text: str, marker: str) -> str:
    marker_index = text.find(marker)
    if marker_index < 0:
        return ""
    start = text.rfind("{", 0, marker_index)
    if start < 0:
        return ""
    depth = 0
    in_string = False
    escape = False
    for index in range(start, min(len(text), start + 500_000)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return ""


def _douyin_cookie_api_headers(douyin_settings: dict[str, str], referer: str = "") -> dict[str, str]:
    safe_referer = _safe_douyin_referer(douyin_settings.get("referer") or referer)
    return {
        "User-Agent": douyin_settings["user_agent"] or _default_douyin_user_agent(),
        "Accept": "application/json,text/plain,*/*",
        "Referer": safe_referer,
        "Cookie": douyin_settings["cookie"],
    }


def _fetch_douyin_cookie_api_items(
    endpoint: str,
    sec_user_id: str,
    headers: dict[str, str],
    max_pages: int,
    count: int,
    page_count: int,
    cookie_diagnostics: dict,
) -> tuple[list[ProfileVideoItem], str, bool, dict]:
    _validate_cookie_api_endpoint(endpoint)
    _require_cookie_request_ready(cookie_diagnostics)
    items: list[ProfileVideoItem] = []
    seen: set[str] = set()
    seen_cursors: set[str] = {"0"}
    max_cursor = "0"
    has_more = False
    consecutive_no_new = 0
    meta = {
        "page_count": 0,
        "item_count": 0,
        "duplicate_count": 0,
        "invalid_item_count": 0,
        "retry_count": 0,
        "partial": False,
        "truncated_reason": "",
    }
    with httpx.Client(timeout=COOKIE_API_TIMEOUT_SECONDS, follow_redirects=False, trust_env=False) as client:
        for page_index in range(max_pages):
            try:
                payload, response_meta = _request_cookie_api_page(
                    client,
                    endpoint=endpoint,
                    sec_user_id=sec_user_id,
                    cursor=max_cursor,
                    count=page_count,
                    headers=headers,
                )
            except AppError as error:
                if not items:
                    raise
                meta["retry_count"] += int(error.public_details().get("retry_count") or 0)
                _mark_partial(meta, "upstream_error", error.code)
                has_more = True
                break
            meta["page_count"] += 1
            meta["retry_count"] += int(response_meta.get("retry_count") or 0)
            raw_items = _cookie_api_aweme_list(payload)
            if raw_items is None:
                raise AppError(
                    ErrorCode.DOUYIN_RESPONSE_INVALID,
                    details=_scan_error_details(meta, response_meta),
                )
            if not raw_items and not items:
                raise AppError(
                    ErrorCode.DOUYIN_NO_PUBLIC_WORKS,
                    details=_scan_error_details(meta, response_meta),
                )

            page_new_count = 0
            for raw_item in raw_items:
                if not isinstance(raw_item, dict):
                    meta["invalid_item_count"] += 1
                    continue
                item = normalize_profile_video_item(raw_item, sec_user_id=sec_user_id)
                if not item:
                    meta["invalid_item_count"] += 1
                    continue
                if item.aweme_id in seen:
                    meta["duplicate_count"] += 1
                    continue
                item.source_provider = DouyinCookieProfileProvider.name
                seen.add(item.aweme_id)
                items.append(item)
                page_new_count += 1
                if len(items) >= count:
                    break

            has_more_value, has_more_valid = _cookie_api_has_more(payload)
            next_cursor, cursor_present = _cookie_api_next_cursor(payload)
            if not has_more_valid:
                if items:
                    _mark_partial(meta, "pagination_fields_missing", ErrorCode.DOUYIN_PAGINATION_INVALID)
                    has_more = True
                    break
                raise AppError(
                    ErrorCode.DOUYIN_PAGINATION_INVALID,
                    details=_scan_error_details(meta, response_meta),
                )

            has_more = has_more_value
            if len(items) >= count:
                max_cursor = next_cursor or max_cursor
                if has_more or len(raw_items) > page_new_count:
                    _mark_partial(meta, "item_limit", ErrorCode.DOUYIN_PAGE_LIMIT_REACHED)
                    has_more = True
                break
            if not raw_items:
                _mark_partial(meta, "empty_page", ErrorCode.DOUYIN_PAGINATION_INVALID)
                has_more = bool(has_more)
                break

            consecutive_no_new = consecutive_no_new + 1 if page_new_count == 0 else 0
            if consecutive_no_new >= COOKIE_API_MAX_CONSECUTIVE_NO_NEW_PAGES:
                _mark_partial(meta, "no_new_items", ErrorCode.DOUYIN_PAGINATION_INVALID)
                has_more = True
                break
            if not has_more:
                max_cursor = next_cursor or max_cursor
                break
            if not cursor_present or not next_cursor:
                _mark_partial(meta, "cursor_missing", ErrorCode.DOUYIN_PAGINATION_INVALID)
                has_more = True
                break
            if next_cursor in seen_cursors or next_cursor == max_cursor:
                _mark_partial(meta, "cursor_repeated", ErrorCode.DOUYIN_PAGINATION_INVALID)
                has_more = True
                break
            seen_cursors.add(next_cursor)
            max_cursor = next_cursor

            if page_index + 1 >= max_pages and has_more:
                _mark_partial(meta, "page_limit", ErrorCode.DOUYIN_PAGE_LIMIT_REACHED)

    if not items:
        raise AppError(ErrorCode.DOUYIN_NO_PUBLIC_WORKS, details=_scan_error_details(meta))
    meta["item_count"] = len(items)
    _log_cookie_provider_event("scan_complete", meta)
    return items, max_cursor, has_more, meta


def _test_douyin_cookie_api_endpoint(endpoint: str, sec_user_id: str, headers: dict[str, str], count: int) -> dict:
    _validate_cookie_api_endpoint(endpoint)
    try:
        with httpx.Client(timeout=COOKIE_API_TIMEOUT_SECONDS, follow_redirects=False, trust_env=False) as client:
            payload, response_meta = _request_cookie_api_page(
                client,
                endpoint=endpoint,
                sec_user_id=sec_user_id,
                cursor="0",
                count=count,
                headers=headers,
            )
        raw_items = _cookie_api_aweme_list(payload)
        if raw_items is None:
            raise AppError(ErrorCode.DOUYIN_RESPONSE_INVALID, details=response_meta)
        has_more, has_more_valid = _cookie_api_has_more(payload)
        return {
            "endpoint": _safe_endpoint_path(endpoint),
            "status": "ok" if raw_items else "empty",
            "error_code": "" if raw_items else ErrorCode.DOUYIN_NO_PUBLIC_WORKS,
            "status_code": response_meta.get("status_code"),
            "content_type": response_meta.get("content_type", ""),
            "redirected": False,
            "is_json": True,
            "aweme_count": len(raw_items),
            "has_more": has_more if has_more_valid else False,
            "retry_count": response_meta.get("retry_count", 0),
        }
    except AppError as error:
        details = error.public_details()
        return {
            "endpoint": _safe_endpoint_path(endpoint),
            "status": _cookie_test_status(error.code),
            "error_code": error.code,
            "status_code": details.get("status_code"),
            "content_type": details.get("content_type", ""),
            "redirected": bool(details.get("redirected")),
            "is_json": False,
            "aweme_count": 0,
            "has_more": False,
            "retry_count": details.get("retry_count", 0),
        }


def _cookie_api_response_diagnostics(response: httpx.Response) -> dict:
    headers = getattr(response, "headers", {}) or {}
    content_type = headers.get("content-type", "") if hasattr(headers, "get") else ""
    text = str(getattr(response, "text", "") or "")
    content = getattr(response, "content", None)
    text_sample = text[:3000] if (content or text) else ""
    return {
        "status_code": int(getattr(response, "status_code", 0) or 0),
        "content_type": content_type.split(";")[0].strip().lower(),
        "login_markers": _is_douyin_login_page(text_sample),
        "redirect_location": str(headers.get("location", "") if hasattr(headers, "get") else "")[:500],
    }


def _request_cookie_api_page(
    client,
    *,
    endpoint: str,
    sec_user_id: str,
    cursor: str,
    count: int,
    headers: dict[str, str],
) -> tuple[dict, dict]:
    _validate_cookie_api_endpoint(endpoint)
    retry_count = 0
    for attempt in range(COOKIE_API_MAX_ATTEMPTS):
        try:
            response = client.get(
                endpoint,
                params={
                    "sec_user_id": sec_user_id,
                    "max_cursor": cursor,
                    "count": count,
                    "aid": "6383",
                    "device_platform": "webapp",
                },
                headers=headers,
            )
            response_error = _cookie_api_response_error(response, retry_count=retry_count)
            if response_error:
                raise response_error
            payload = _cookie_api_json_payload(response, retry_count=retry_count)
            return payload, {
                "status_code": int(getattr(response, "status_code", 200) or 200),
                "content_type": _cookie_api_response_diagnostics(response)["content_type"] or "application/json",
                "redirected": False,
                "retry_count": retry_count,
            }
        except httpx.TimeoutException:
            current_error = AppError(
                ErrorCode.DOUYIN_UPSTREAM_TIMEOUT,
                details={"retry_count": retry_count},
            )
        except httpx.HTTPError:
            current_error = AppError(
                ErrorCode.DOUYIN_UPSTREAM_UNAVAILABLE,
                details={"retry_count": retry_count},
            )
        except AppError as error:
            current_error = error

        if not _is_retryable_cookie_error(current_error) or attempt + 1 >= COOKIE_API_MAX_ATTEMPTS:
            details = {**current_error.details, "retry_count": retry_count}
            final_error = AppError(current_error.code, current_error.message, details=details)
            _log_cookie_provider_event("request_failed", {"error_code": final_error.code, **final_error.public_details()})
            raise final_error
        retry_count += 1
        _log_cookie_provider_event("request_retry", {"error_code": current_error.code, "retry_count": retry_count})
        time.sleep(COOKIE_API_RETRY_BACKOFF_SECONDS * retry_count)
    raise AppError(ErrorCode.DOUYIN_UPSTREAM_UNAVAILABLE, details={"retry_count": retry_count})


def _cookie_api_response_error(response, *, retry_count: int = 0) -> AppError | None:
    diagnostics = _cookie_api_response_diagnostics(response)
    status_code = diagnostics["status_code"]
    details = {
        "status_code": status_code,
        "content_type": diagnostics["content_type"],
        "redirected": 300 <= status_code < 400,
        "retry_count": retry_count,
    }
    if 300 <= status_code < 400:
        location = diagnostics["redirect_location"]
        code = ErrorCode.DOUYIN_LOGIN_REQUIRED if _is_login_redirect(location) else ErrorCode.DOUYIN_UPSTREAM_REDIRECT
        return AppError(code, details=details)
    if status_code == 401:
        return AppError(ErrorCode.DOUYIN_AUTH_EXPIRED, details=details)
    if status_code == 403:
        return AppError(ErrorCode.DOUYIN_UPSTREAM_FORBIDDEN, details=details)
    if status_code == 429:
        return AppError(ErrorCode.DOUYIN_UPSTREAM_RATE_LIMITED, details=details)
    if status_code >= 500:
        return AppError(ErrorCode.DOUYIN_UPSTREAM_UNAVAILABLE, details=details)
    if status_code >= 400:
        return AppError(ErrorCode.DOUYIN_UPSTREAM_UNAVAILABLE, details=details)
    content_type = diagnostics["content_type"]
    if content_type and "json" not in content_type:
        code = ErrorCode.DOUYIN_LOGIN_REQUIRED if diagnostics["login_markers"] else ErrorCode.DOUYIN_UPSTREAM_NON_JSON
        return AppError(code, details=details)
    return None


def _cookie_api_json_payload(response, *, retry_count: int = 0) -> dict:
    diagnostics = _cookie_api_response_diagnostics(response)
    details = {
        "status_code": diagnostics["status_code"],
        "content_type": diagnostics["content_type"],
        "redirected": False,
        "retry_count": retry_count,
    }
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError) as error:
        code = ErrorCode.DOUYIN_LOGIN_REQUIRED if diagnostics["login_markers"] else ErrorCode.DOUYIN_RESPONSE_INVALID
        raise AppError(code, details=details) from error
    if not isinstance(payload, dict):
        raise AppError(ErrorCode.DOUYIN_RESPONSE_INVALID, details=details)
    upstream_status = payload.get("status_code") if "status_code" in payload else payload.get("statusCode")
    if upstream_status not in (None, "", 0, "0"):
        status_message = str(payload.get("status_msg") or payload.get("statusMsg") or payload.get("message") or "")
        code = _cookie_api_payload_error_code(upstream_status, status_message)
        raise AppError(code, details=details)
    return payload


def _cookie_api_aweme_list(payload: dict) -> list | None:
    if "aweme_list" in payload:
        value = payload.get("aweme_list")
    elif "awemeList" in payload:
        value = payload.get("awemeList")
    else:
        return None
    return value if isinstance(value, list) else None


def _cookie_api_has_more(payload: dict) -> tuple[bool, bool]:
    if "has_more" in payload:
        value = payload.get("has_more")
    elif "hasMore" in payload:
        value = payload.get("hasMore")
    else:
        return False, False
    if isinstance(value, bool):
        return value, True
    if isinstance(value, int) and value in {0, 1}:
        return bool(value), True
    normalized = str(value).strip().lower()
    if normalized in {"0", "false"}:
        return False, True
    if normalized in {"1", "true"}:
        return True, True
    return False, False


def _cookie_api_next_cursor(payload: dict) -> tuple[str, bool]:
    if "max_cursor" in payload:
        value = payload.get("max_cursor")
    elif "maxCursor" in payload:
        value = payload.get("maxCursor")
    else:
        return "", False
    if isinstance(value, (str, int)):
        return str(value), True
    return "", False


def _cookie_api_payload_error_code(status, message: str) -> str:
    normalized = (message or "").lower()
    if str(status) in {"401", "8"}:
        return ErrorCode.DOUYIN_AUTH_EXPIRED
    if any(marker in normalized for marker in ("expired", "过期", "失效")):
        return ErrorCode.DOUYIN_AUTH_EXPIRED
    if any(marker in normalized for marker in ("login", "passport", "登录", "未登录")):
        return ErrorCode.DOUYIN_LOGIN_REQUIRED
    return ErrorCode.DOUYIN_RESPONSE_INVALID


def _is_douyin_login_page(text: str) -> bool:
    value = (text or "").lower()
    markers = ("passport.douyin.com", "扫码登录", "登录抖音", "login-panel", "sso/login")
    return any(marker in value for marker in markers)


def _is_login_redirect(location: str) -> bool:
    parsed = urlparse(location or "")
    target = f"{parsed.netloc}{parsed.path}".lower()
    return any(marker in target for marker in ("passport", "login", "sso"))


def _safe_douyin_referer(value: str) -> str:
    parsed = urlparse((value or "").strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "https" and (host == "douyin.com" or host.endswith(".douyin.com")):
        return parsed._replace(query="", fragment="").geturl()
    return "https://www.douyin.com/"


def _validate_cookie_api_endpoint(endpoint: str) -> None:
    parsed = urlparse(endpoint or "")
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in COOKIE_API_ALLOWED_HOSTS:
        raise AppError(ErrorCode.DOUYIN_UPSTREAM_UNAVAILABLE)


def _mark_partial(meta: dict, reason: str, error_code: str) -> None:
    meta["partial"] = True
    meta["truncated_reason"] = reason
    meta["truncated_error_code"] = error_code


def _scan_error_details(meta: dict, response_meta: dict | None = None) -> dict:
    response_meta = response_meta or {}
    return {
        "status_code": response_meta.get("status_code"),
        "content_type": str(response_meta.get("content_type") or ""),
        "redirected": bool(response_meta.get("redirected")),
        "page_count": int(meta.get("page_count") or 0),
        "item_count": int(meta.get("item_count") or 0),
        "duplicate_count": int(meta.get("duplicate_count") or 0),
        "invalid_item_count": int(meta.get("invalid_item_count") or 0),
        "partial": bool(meta.get("partial")),
        "truncated_reason": str(meta.get("truncated_reason") or ""),
        "retry_count": int(meta.get("retry_count") or response_meta.get("retry_count") or 0),
    }


def _pagination_warning(reason: str, meta: dict) -> str:
    messages = {
        "page_limit": "主页扫描达到配置页数上限，当前展示部分结果。",
        "item_limit": "主页扫描达到配置作品数上限，当前展示部分结果。",
        "cursor_repeated": "上游返回重复分页 cursor，已停止继续请求并保留当前结果。",
        "cursor_missing": "上游缺少下一页 cursor，已停止继续请求并保留当前结果。",
        "pagination_fields_missing": "上游缺少分页字段，已停止继续请求并保留当前结果。",
        "empty_page": "上游在分页过程中返回空页，已停止继续请求并保留当前结果。",
        "no_new_items": "连续页面没有新增作品，已停止继续请求并保留当前结果。",
        "upstream_error": (
            "后续分页请求失败，已保留当前结果。"
            f"安全错误码：{str(meta.get('truncated_error_code') or ErrorCode.DOUYIN_UPSTREAM_UNAVAILABLE)}。"
        ),
    }
    return messages.get(reason, "主页扫描提前停止，当前展示部分结果。")


def _log_cookie_provider_event(event: str, details: dict) -> None:
    safe = {
        key: value
        for key, value in details.items()
        if key
        in {
            "error_code",
            "status_code",
            "content_type",
            "redirected",
            "page_count",
            "item_count",
            "duplicate_count",
            "invalid_item_count",
            "partial",
            "truncated_reason",
            "retry_count",
        }
    }
    logger.info(
        "douyin_cookie_provider",
        extra={"provider": DouyinCookieProfileProvider.name, "provider_event": event, **safe},
    )


def _can_try_next_cookie_endpoint(error: AppError) -> bool:
    return (
        error.code == ErrorCode.DOUYIN_UPSTREAM_UNAVAILABLE
        and error.public_details().get("status_code") in {404, 405}
    )


def _is_retryable_cookie_error(error: AppError) -> bool:
    if error.code in {ErrorCode.DOUYIN_UPSTREAM_TIMEOUT, ErrorCode.DOUYIN_UPSTREAM_RATE_LIMITED}:
        return True
    if error.code != ErrorCode.DOUYIN_UPSTREAM_UNAVAILABLE:
        return False
    status_code = error.public_details().get("status_code")
    return status_code is None or int(status_code or 0) >= 500


def _cookie_test_status(error_code: str) -> str:
    return {
        ErrorCode.DOUYIN_COOKIE_NOT_CONFIGURED: "not_configured",
        ErrorCode.DOUYIN_COOKIE_INVALID: "invalid_cookie",
        ErrorCode.DOUYIN_LOGIN_REQUIRED: "login_required",
        ErrorCode.DOUYIN_AUTH_EXPIRED: "auth_expired",
        ErrorCode.DOUYIN_UPSTREAM_REDIRECT: "redirected",
        ErrorCode.DOUYIN_UPSTREAM_NON_JSON: "non_json",
        ErrorCode.DOUYIN_UPSTREAM_RATE_LIMITED: "rate_limited",
        ErrorCode.DOUYIN_UPSTREAM_FORBIDDEN: "forbidden",
        ErrorCode.DOUYIN_UPSTREAM_TIMEOUT: "timeout",
        ErrorCode.DOUYIN_UPSTREAM_UNAVAILABLE: "unavailable",
        ErrorCode.DOUYIN_RESPONSE_INVALID: "response_invalid",
        ErrorCode.DOUYIN_NO_PUBLIC_WORKS: "empty",
    }.get(error_code, "failed")


def _cookie_error_next_steps(error_code: str) -> list[str]:
    if error_code == ErrorCode.DOUYIN_COOKIE_NOT_CONFIGURED:
        return ["在本机设置中主动配置个人账号 Cookie。", "也可以改用作品链接、JSON/CSV 或已有 Case 导入。"]
    if error_code in {ErrorCode.DOUYIN_COOKIE_INVALID, ErrorCode.DOUYIN_LOGIN_REQUIRED, ErrorCode.DOUYIN_AUTH_EXPIRED}:
        return ["从本人已登录的抖音会话人工更新完整 Cookie。", "不要把 Cookie 发送给其他人或提交到 Git。"]
    if error_code in {ErrorCode.DOUYIN_UPSTREAM_RATE_LIMITED, ErrorCode.DOUYIN_UPSTREAM_TIMEOUT, ErrorCode.DOUYIN_UPSTREAM_UNAVAILABLE}:
        return ["稍后人工重试一次。", "需要继续工作时可使用作品链接、JSON/CSV 或已有 Case 导入。"]
    return ["检查个人 Cookie 和主页输入。", "仍不可用时改用作品链接、JSON/CSV 或已有 Case 导入。"]


def _cookie_test_next_steps(result: dict) -> list[str]:
    if result.get("status") == "ok":
        return ["可以使用主页导入；系统会把个人账号 Cookie Web API 作为主路径。"]
    if result.get("status") == "config_only":
        return ["填入主页 URL 或 sec_user_id 后再次自检。"]
    return _cookie_error_next_steps(str(result.get("error_code") or ErrorCode.DOUYIN_RESPONSE_INVALID))


def _combined_cookie_api_error(endpoint_failures: list[tuple[str, AppError]]) -> AppError:
    if not endpoint_failures:
        return AppError(ErrorCode.DOUYIN_NO_PUBLIC_WORKS)
    priority = [
        ErrorCode.DOUYIN_AUTH_EXPIRED,
        ErrorCode.DOUYIN_LOGIN_REQUIRED,
        ErrorCode.DOUYIN_COOKIE_INVALID,
        ErrorCode.DOUYIN_UPSTREAM_FORBIDDEN,
        ErrorCode.DOUYIN_UPSTREAM_RATE_LIMITED,
        ErrorCode.DOUYIN_UPSTREAM_TIMEOUT,
        ErrorCode.DOUYIN_RESPONSE_INVALID,
        ErrorCode.DOUYIN_UPSTREAM_UNAVAILABLE,
        ErrorCode.DOUYIN_NO_PUBLIC_WORKS,
    ]
    selected = endpoint_failures[0][1]
    for code in priority:
        matched = next((error for _, error in endpoint_failures if error.code == code), None)
        if matched:
            selected = matched
            break
    return AppError(
        selected.code,
        selected.message,
        details=selected.details,
    )


def _safe_endpoint_path(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    return parsed.path or endpoint


def _default_douyin_user_agent() -> str:
    return (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )


def _first_url(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("url_list", "urlList", "uri"):
            result = _first_url(value.get(key))
            if result:
                return result
    if isinstance(value, list):
        for item in value:
            result = _first_url(item)
            if result:
                return result
    return ""


def _media_type_from_url(url: str) -> str:
    parsed = urlparse(url or "")
    if "/note/" in parsed.path:
        return "image"
    if "/video/" in parsed.path:
        return "video"
    return ""


def _media_type_from_aweme(raw: dict, video: dict, images, image_post: dict) -> str:
    if isinstance(images, list) and images:
        return "image"
    if image_post:
        return "image"
    aweme_type = str(raw.get("aweme_type") or raw.get("awemeType") or "")
    if aweme_type in {"68", "150"}:
        return "image"
    if video and any(video.get(key) for key in ("play_addr", "play_addr_h264", "play_addr_265", "bit_rate", "duration")):
        return "video"
    return "unknown"


def _safe_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_count(value) -> int:
    try:
        return max(1, min(int(value or settings.profile_scan_count_per_page), COOKIE_API_MAX_ITEMS))
    except (TypeError, ValueError):
        return max(1, min(int(settings.profile_scan_count_per_page or 20), COOKIE_API_MAX_ITEMS))
