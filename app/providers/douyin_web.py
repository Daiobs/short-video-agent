from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from html import unescape
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse, unquote

import httpx

from app.config import settings
from app.errors import AppError, ErrorCode
from app.providers.base import VideoQualityCandidateDTO


DOUYIN_DETAIL_URL = (
    "https://www.douyin.com/aweme/v1/web/aweme/detail/"
    "?aweme_id={aweme_id}&aid=6383&device_platform=webapp"
)
DOUYIN_VIDEO_PAGE_URL = "https://www.douyin.com/video/{aweme_id}"
DOUYIN_MOBILE_SHARE_URLS = (
    "https://www.iesdouyin.com/share/video/{aweme_id}/?region=CN",
    "https://www.iesdouyin.com/share/note/{aweme_id}/?region=CN",
)
DOUYIN_MOBILE_FEED_URL = "https://aweme.snssdk.com/aweme/v1/feed/?{query}"
PREFERRED_VIDEO_RATIOS = ("1080p_60fps", "1080p", "720p", "540p")
VIDEO_RATIO_SCORES = {
    "1080p_60fps": 3500,
    "1080p": 3000,
    "720p": 2000,
    "540p": 1000,
}


def _host_allowed(host: str) -> bool:
    host = (host or "").lower()
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in settings.allowed_cdn_hosts)


def _int_value(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _format_create_time(value) -> str:
    timestamp = _int_value(value)
    if not timestamp:
        return ""
    try:
        return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return str(timestamp)


def _candidate_id(aweme_id: str, url: str, source: str) -> str:
    digest = hashlib.sha256(f"{aweme_id}:{source}:{url}".encode("utf-8")).hexdigest()[:24]
    return f"cand_{digest}"


def _object_key(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    video_id = (query.get("video_id") or query.get("vid") or [""])[0]
    if video_id:
        return f"video_id:{video_id}"
    return parsed.path.lstrip("/")


def _replace_query_param(url: str, key: str, value: str) -> str:
    parsed = urlparse(url)
    query_items = [
        (item_key, item_value)
        for item_key, item_value in parse_qsl(parsed.query, keep_blank_values=True)
        if item_key != key
    ]
    query_items.append((key, value))
    return urlunparse(parsed._replace(query=urlencode(query_items)))


def _normalize_media_url(url: str) -> str:
    value = (url or "").strip()
    if value.startswith("http://"):
        value = "https://" + value[len("http://"):]
    return value.replace("/playwm/", "/play/")


def _url_ratio(url: str) -> str:
    return dict(parse_qsl(urlparse(url).query, keep_blank_values=True)).get("ratio", "")


def _ratio_score(ratio: str) -> int:
    return VIDEO_RATIO_SCORES.get(ratio, 0)


def _expand_video_quality_urls(url: str) -> list[tuple[int, str]]:
    url = _normalize_media_url(url)
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if (
        "video_id" not in query
        or "/aweme/v1/play" not in parsed.path
        or query.get("sign")
        or query.get("biz_sign")
        or query.get("is_play_url")
    ):
        return [(_ratio_score(_url_ratio(url)), url)]

    expanded: list[tuple[int, str]] = []
    seen = set()
    for ratio in PREFERRED_VIDEO_RATIOS:
        candidate = _replace_query_param(url, "ratio", ratio)
        if candidate in seen:
            continue
        seen.add(candidate)
        expanded.append((_ratio_score(ratio), candidate))
    if url not in seen:
        expanded.append((_ratio_score(_url_ratio(url)), url))
    return expanded


def _iter_urls(addr: dict) -> list[str]:
    urls = []
    for value in addr.get("url_list") or []:
        if isinstance(value, str):
            urls.append(value)
    for key in ("url", "download_url"):
        value = addr.get(key)
        if isinstance(value, str):
            urls.append(value)
    return list(dict.fromkeys(urls))


def _iter_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_dicts(child)


def _extract_balanced_object(text: str, start: int) -> str:
    brace_index = text.find("{", start)
    if brace_index == -1:
        return ""
    depth = 0
    quoted = False
    escaped = False
    for index in range(brace_index, len(text)):
        character = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
            continue
        if character == '"':
            quoted = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[brace_index : index + 1]
    return ""


def _load_json_candidates_from_html(html: str) -> list[dict]:
    candidates: list[str] = []
    raw_text = unquote(unescape((html or "").strip()))
    if raw_text.startswith("{") and raw_text.endswith("}"):
        candidates.append(raw_text)

    for match in re.finditer(
        r'<script(?P<attrs>[^>]*)>(?P<content>.*?)</script>',
        html or "",
        flags=re.IGNORECASE | re.DOTALL,
    ):
        attrs = match.group("attrs") or ""
        content = unescape(match.group("content") or "").strip()
        if not content:
            continue
        script_id_match = re.search(r'id=["\']([^"\']+)["\']', attrs)
        script_id = script_id_match.group(1) if script_id_match else ""
        if script_id in {"RENDER_DATA", "__UNIVERSAL_DATA_FOR_REHYDRATION__"}:
            candidates.append(unquote(content))
            continue
        if content.startswith("{") and content.endswith("}"):
            candidates.append(content)
        for marker in (
            "window._ROUTER_DATA",
            "window._SSR_DATA",
            "window.__INIT_PROPS__",
            "window.__UNIVERSAL_DATA_FOR_REHYDRATION__",
        ):
            marker_index = content.find(marker)
            if marker_index != -1:
                json_text = _extract_balanced_object(content, marker_index)
                if json_text:
                    candidates.append(json_text)
        for json_parse in re.finditer(r"JSON\.parse\((?P<quote>['\"])(?P<value>.*?)(?P=quote)\)", content):
            try:
                candidates.append(json.loads(f'"{json_parse.group("value")}"'))
            except json.JSONDecodeError:
                continue

    parsed = []
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed.append(json.loads(candidate))
        except json.JSONDecodeError:
            continue
    return parsed


def _looks_like_risk_page(html: str) -> bool:
    text = html or ""
    risk_markers = (
        "验证码中间页",
        "captcha",
        "sec_sdk_build",
        "_$jsvmprt",
        "byted_acrawler",
    )
    return any(marker in text for marker in risk_markers)


def _find_aweme_detail(data: dict, aweme_id: str) -> dict:
    for item in _iter_dicts(data):
        aweme_detail = item.get("aweme_detail")
        if isinstance(aweme_detail, dict) and str(aweme_detail.get("aweme_id") or "") == aweme_id:
            return aweme_detail
        item_list = item.get("item_list")
        if isinstance(item_list, list):
            for candidate in item_list:
                if isinstance(candidate, dict) and str(candidate.get("aweme_id") or "") == aweme_id:
                    return candidate
        aweme = item.get("aweme")
        if isinstance(aweme, dict) and str(aweme.get("aweme_id") or "") == aweme_id:
            return aweme
        if str(item.get("aweme_id") or "") == aweme_id and ("video" in item or "images" in item):
            return item
    return {}


def _find_aweme_list_item(data: dict, aweme_id: str) -> dict:
    aweme_list = data.get("aweme_list")
    if isinstance(aweme_list, list):
        for item in aweme_list:
            if isinstance(item, dict) and str(item.get("aweme_id") or "") == aweme_id:
                return item
    return _find_aweme_detail(data, aweme_id)


def _mobile_feed_url(aweme_id: str) -> str:
    params = {
        "aid": "1128",
        "app_name": "aweme",
        "version_name": "26.0.0",
        "version_code": "260000",
        "device_platform": "android",
        "os": "android",
        "ssmix": "a",
        "device_type": "Pixel 6",
        "device_brand": "google",
        "language": "zh",
        "os_api": "31",
        "os_version": "12",
        "openudid": "1234567890",
        "manifest_version_code": "260000",
        "resolution": "1080*1920",
        "dpi": "420",
        "update_version_code": "26009900",
        "aweme_id": aweme_id,
    }
    return DOUYIN_MOBILE_FEED_URL.format(query=urlencode(params))


def _video_variants(video: dict) -> list[tuple[str, int, dict]]:
    variants: list[tuple[str, int, dict]] = []
    for index, raw_variant in enumerate(video.get("bit_rate") or []):
        if isinstance(raw_variant, dict):
            variants.append((f"bit_rate.{index}", index, raw_variant))

    if variants:
        return variants

    for key in ("play_addr_h264", "play_addr", "play_addr_265"):
        if isinstance(video.get(key), dict):
            variants.append((key, len(variants), {"gear_name": "web", key: video[key]}))
    return variants


def _candidate_sort_key(item: VideoQualityCandidateDTO) -> tuple[int, int, int, int, str]:
    ratio = _url_ratio(item.url) or item.quality_label
    source_priority = 2 if item.source.startswith("bit_rate") else 1
    return (source_priority, max(_ratio_score(ratio), item.bitrate), item.size_bytes, item.bitrate, item.quality_label)


def normalize_douyin_detail_payload(payload: dict, aweme_id: str) -> tuple[dict, list[VideoQualityCandidateDTO]]:
    aweme = payload.get("aweme_detail") or _find_aweme_detail(payload, aweme_id)
    if str(aweme.get("aweme_id") or "") != aweme_id:
        raise AppError(ErrorCode.AWEME_ID_NOT_FOUND, "抖音接口未返回请求的作品。")

    video = aweme.get("video") or {}
    candidates: list[VideoQualityCandidateDTO] = []
    for source_prefix, index, raw_variant in _video_variants(video):
        if not isinstance(raw_variant, dict):
            continue
        bitrate = _int_value(raw_variant.get("bit_rate"))
        gear_name = str(raw_variant.get("gear_name") or raw_variant.get("quality_type") or "web")
        for key in ("play_addr", "play_addr_h264", "play_addr_265"):
            addr = raw_variant.get(key)
            if not isinstance(addr, dict):
                continue
            size_bytes = _int_value(addr.get("data_size") or addr.get("size"))
            width = _int_value(addr.get("width"))
            height = _int_value(addr.get("height"))
            label = f"{gear_name} {width}x{height}".strip()
            for url in _iter_urls(addr):
                for ratio_score, expanded_url in _expand_video_quality_urls(url):
                    parsed = urlparse(expanded_url)
                    host = (parsed.hostname or "").lower()
                    if parsed.scheme != "https" or not _host_allowed(host):
                        continue
                    ratio = _url_ratio(expanded_url)
                    label = ratio or f"{gear_name} {width}x{height}".strip()
                    source = f"{source_prefix}.{key}"
                    candidates.append(
                        VideoQualityCandidateDTO(
                            candidate_id=_candidate_id(aweme_id, expanded_url, source),
                            aweme_id=aweme_id,
                            quality_label=label,
                            url=expanded_url,
                            size_bytes=size_bytes,
                            bitrate=max(bitrate, ratio_score),
                            host=host,
                            object_key=_object_key(expanded_url),
                            expires_at=0,
                            source=f"douyin_native.{source}",
                        )
                    )

    candidates.sort(key=_candidate_sort_key, reverse=True)
    statistics = aweme.get("statistics") or {}
    metadata = {
        "aweme_id": aweme_id,
        "title": aweme.get("desc") or f"抖音作品 {aweme_id}",
        "author": ((aweme.get("author") or {}).get("nickname") or ""),
        "cover_url": ((((video.get("cover") or {}).get("url_list") or [""]) or [""])[0]),
        "source_url": f"https://www.douyin.com/video/{aweme_id}",
        "like_count": _int_value(statistics.get("digg_count")),
        "comment_count": _int_value(statistics.get("comment_count")),
        "share_count": _int_value(statistics.get("share_count")),
        "create_time": _format_create_time(aweme.get("create_time")),
    }
    return metadata, candidates


def normalize_douyin_html_payload(html: str, aweme_id: str) -> tuple[dict, list[VideoQualityCandidateDTO]]:
    for payload in _load_json_candidates_from_html(html):
        if _find_aweme_detail(payload, aweme_id):
            return normalize_douyin_detail_payload(payload, aweme_id)
    raise AppError(ErrorCode.DOUYIN_RISK_CONTROL, "抖音作品页未包含可解析的视频数据。")


class DouyinWebProvider:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client

    def resolve(self, aweme_id: str, source_urls: list[str] | None = None) -> tuple[dict, list[VideoQualityCandidateDTO]]:
        web_headers = {
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://www.douyin.com/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/149.0 Safari/537.36",
        }
        if settings.douyin_cookie:
            web_headers["Cookie"] = settings.douyin_cookie

        owns_client = self.client is None
        client = self.client or httpx.Client(timeout=12.0, follow_redirects=False, trust_env=False)
        try:
            native_result = self._fetch_mobile_feed_payload(client, aweme_id)
            if native_result:
                metadata, candidates = normalize_douyin_detail_payload(native_result, aweme_id)
                if candidates:
                    return metadata, candidates

            share_payload = self._fetch_mobile_share_payload(client, aweme_id)
            if share_payload:
                metadata, candidates = normalize_douyin_detail_payload(share_payload, aweme_id)
                if candidates:
                    return metadata, candidates

            response = client.get(DOUYIN_DETAIL_URL.format(aweme_id=aweme_id), headers=web_headers)
            if response.status_code in {401, 403}:
                raise AppError(ErrorCode.COOKIE_REQUIRED)
            if response.status_code >= 400:
                raise AppError(ErrorCode.DOUYIN_RISK_CONTROL)
            try:
                payload = response.json()
            except ValueError:
                payload = self._fetch_video_page_payload(client, web_headers, aweme_id, source_urls=source_urls)
            metadata, candidates = normalize_douyin_detail_payload(payload, aweme_id)
            if not candidates:
                raise AppError(ErrorCode.QUALITY_NOT_FOUND)
            return metadata, candidates
        except AppError:
            raise
        except httpx.TimeoutException as error:
            raise AppError(ErrorCode.DOUYIN_RISK_CONTROL, "抖音作品解析超时，可以改用本地视频上传。") from error
        except ValueError as error:
            raise AppError(ErrorCode.DOUYIN_RISK_CONTROL, "抖音接口结构变化或返回非 JSON。") from error
        except httpx.HTTPError as error:
            raise AppError(ErrorCode.DOUYIN_RISK_CONTROL, str(error)[:500]) from error
        finally:
            if owns_client:
                client.close()

    def _fetch_mobile_feed_payload(self, client: httpx.Client, aweme_id: str) -> dict:
        headers = {
            "Accept": "application/json",
            "Referer": "https://www.douyin.com/",
            "User-Agent": (
                "com.ss.android.ugc.aweme/260000 "
                "(Linux; U; Android 12; zh_CN; Pixel 6; Build/SP1A.210812.016)"
            ),
        }
        try:
            response = client.get(_mobile_feed_url(aweme_id), headers=headers)
            if response.status_code != 200:
                return {}
            data = response.json()
        except (ValueError, httpx.HTTPError):
            return {}
        aweme = _find_aweme_list_item(data, aweme_id)
        return {"aweme_detail": aweme} if aweme else {}

    def _fetch_mobile_share_payload(self, client: httpx.Client, aweme_id: str) -> dict:
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Referer": "https://www.iesdouyin.com/",
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
                "aweme_260000 JsSdk/2.0 NetType/WIFI Channel/App Store ByteLocale/zh-CN"
            ),
        }
        for template in DOUYIN_MOBILE_SHARE_URLS:
            try:
                response = client.get(template.format(aweme_id=aweme_id), headers=headers)
            except httpx.HTTPError:
                continue
            if response.status_code != 200:
                continue
            if _looks_like_risk_page(response.text):
                continue
            for payload in _load_json_candidates_from_html(response.text):
                if _find_aweme_detail(payload, aweme_id):
                    return payload
        return {}

    def _fetch_video_page_payload(
        self,
        client: httpx.Client,
        headers: dict[str, str],
        aweme_id: str,
        source_urls: list[str] | None = None,
    ) -> dict:
        urls = list(dict.fromkeys([*(source_urls or []), DOUYIN_VIDEO_PAGE_URL.format(aweme_id=aweme_id)]))
        saw_risk_page = False
        for url in urls:
            response = client.get(url, headers={**headers, "Accept": "text/html,*/*"})
            if response.status_code in {401, 403}:
                raise AppError(ErrorCode.COOKIE_REQUIRED)
            if response.status_code >= 400:
                continue
            text = response.text or ""
            if _looks_like_risk_page(text):
                saw_risk_page = True
                continue
            for payload in _load_json_candidates_from_html(text):
                if _find_aweme_detail(payload, aweme_id):
                    return payload
        if saw_risk_page:
            raise AppError(ErrorCode.DOUYIN_RISK_CONTROL, "抖音返回验证码或 JS 风控页。请配置 DOUYIN_COOKIE，或换用可访问的作品链接。")
        raise AppError(ErrorCode.DOUYIN_RISK_CONTROL, "抖音作品页未包含可解析的视频数据。")
