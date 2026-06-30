from __future__ import annotations

import html
import csv
import io
import json
import re
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


PROFILE_URL_RE = re.compile(r"https?://(?:www\.)?douyin\.com/[^\s]+", re.I)
SEC_USER_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{8,128}$")


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
    endpoint = "https://www.douyin.com/aweme/v1/web/user/post/"

    def scan(self, request: ProfileScanRequest) -> ProfileScanResult:
        douyin_settings = effective_douyin_settings()
        if not (douyin_settings["cookie"] or "").strip():
            raise AppError(ErrorCode.COOKIE_REQUIRED, "Cookie API 增强层未配置 DOUYIN_COOKIE。")
        profile_url = normalize_profile_url(request.profile_url, request.sec_user_id)
        sec_user_id = extract_sec_user_id(profile_url, request.sec_user_id)
        if not sec_user_id:
            raise AppError(ErrorCode.SEC_USER_ID_NOT_FOUND)

        headers = {
            "User-Agent": douyin_settings["user_agent"] or _default_douyin_user_agent(),
            "Accept": "application/json,text/plain,*/*",
            "Referer": douyin_settings["referer"] or profile_url,
            "Cookie": douyin_settings["cookie"],
        }
        items: list[ProfileVideoItem] = []
        seen: set[str] = set()
        max_cursor = "0"
        has_more = False
        max_pages = max(1, min(int(request.max_pages or settings.profile_scan_max_pages), 5))
        count = _safe_count(request.count)
        page_count = max(1, min(count, settings.profile_scan_count_per_page or 20, 50))
        try:
            with httpx.Client(timeout=8.0, follow_redirects=False, trust_env=False) as client:
                for _ in range(max_pages):
                    response = client.get(
                        self.endpoint,
                        params={
                            "sec_user_id": sec_user_id,
                            "max_cursor": max_cursor,
                            "count": page_count,
                            "aid": "6383",
                            "device_platform": "webapp",
                        },
                        headers=headers,
                    )
                    if response.status_code in {401, 403}:
                        raise AppError(ErrorCode.COOKIE_INVALID, "Cookie API 返回未授权或禁止访问。")
                    if response.status_code == 429:
                        raise AppError(ErrorCode.DOUYIN_RISK_CONTROL, "Cookie API 返回限流或风控。")
                    if response.status_code >= 400:
                        raise AppError(ErrorCode.PROFILE_SCAN_FAILED, f"Cookie API 请求失败：HTTP {response.status_code}。")
                    payload = _json_response(response)
                    raw_items = payload.get("aweme_list") or payload.get("awemeList") or []
                    if not isinstance(raw_items, list):
                        raise AppError(ErrorCode.PROFILE_SCAN_STRUCTURE_CHANGED, "Cookie API 返回结构缺少 aweme_list。")
                    for raw_item in raw_items:
                        if not isinstance(raw_item, dict):
                            continue
                        item = normalize_profile_video_item(raw_item, sec_user_id=sec_user_id)
                        if not item or item.aweme_id in seen:
                            continue
                        item.source_provider = self.name
                        seen.add(item.aweme_id)
                        items.append(item)
                    has_more = bool(payload.get("has_more") or payload.get("hasMore"))
                    max_cursor = str(payload.get("max_cursor") or payload.get("maxCursor") or "")
                    if not has_more or len(items) >= count:
                        break
        except AppError:
            raise
        except httpx.HTTPError as error:
            raise AppError(ErrorCode.PROFILE_SCAN_FAILED, f"Cookie API 请求失败：{str(error)[:160]}") from error

        if not items:
            raise AppError(ErrorCode.EMPTY_AWEME_LIST, "Cookie API 没有返回可解析作品。")

        sorted_items = sorted_profile_items(items[:count], request.sort_by)
        result = ProfileScanResult(
            provider=self.name,
            profile_url=profile_url,
            sec_user_id=sec_user_id,
            items=sorted_items,
            has_more=has_more or len(items) > len(sorted_items),
            next_cursor=max_cursor,
            warnings=[
                "Cookie API 是可选增强层，只用于提高公开 Web API 成功率；Cookie 不会写入素材包、prompt 或日志。",
            ],
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

        provider_name = settings.profile_scan_provider or "public"
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
        except AppError as error:
            if failures:
                error.message = f"{error.message} Cookie API 增强也未成功：{_failure_summary(failures)}。"
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
            result.warnings.extend(f"增强数据源失败：{error.code}：{error.message}" for error in failures)
        result.summary = build_profile_summary(result)
        return result


def scan_profile(request: ProfileScanRequest) -> ProfileScanResult:
    return DataSourceManager().scan(request)


def normalize_profile_scan_request(request: ProfileScanRequest) -> ProfileScanRequest:
    return ProfileScanRequest(
        profile_url=(request.profile_url or "").strip() or None,
        sec_user_id=(request.sec_user_id or "").strip() or None,
        manual_links=(request.manual_links or "").strip() or None,
        structured_items=(request.structured_items or "").strip() or None,
        count=_safe_count(request.count),
        max_pages=max(1, min(int(request.max_pages or settings.profile_scan_max_pages), 5)),
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


def _json_response(response: httpx.Response) -> dict:
    try:
        payload = response.json()
    except ValueError as error:
        raise AppError(ErrorCode.PROFILE_SCAN_STRUCTURE_CHANGED, "Cookie API 返回非 JSON。") from error
    if not isinstance(payload, dict):
        raise AppError(ErrorCode.PROFILE_SCAN_STRUCTURE_CHANGED, "Cookie API 返回不是 JSON object。")
    return payload


def _default_douyin_user_agent() -> str:
    return (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )


def _failure_summary(errors: list[AppError]) -> str:
    return "；".join(f"{error.code}" for error in errors[:3])


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
        return max(1, min(int(value or settings.profile_scan_count_per_page), 100))
    except (TypeError, ValueError):
        return settings.profile_scan_count_per_page
