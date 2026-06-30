from __future__ import annotations

import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

import httpx

from app.config import settings
from app.errors import AppError, ErrorCode
from app.services.creator_clone import (
    CloneSample,
    CloneSampleSet,
    creator_clone_dir,
    dedupe_samples,
    detect_source_type,
    load_sample_set,
    normalize_media_type,
    save_sample_set,
)


CHROME_DEBUG_URL = "http://127.0.0.1:9222"
DEFAULT_MAC_CHROME_BINARY = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
TOKEN_TTL_SECONDS = 120
DEFAULT_SCROLL_ROUNDS = 6
MAX_SCROLL_ROUNDS = 12
_TOKENS: dict[str, float] = {}
SENSITIVE_FIELD_RE = re.compile(
    r"(cookie|sessionid|sid_guard|passport|token|authorization|x-bogus|msToken|odin_tt)(\s*[:=]\s*[^&\s;\"'<>]+)?",
    re.IGNORECASE,
)


def _local_chrome_profile_dir() -> Path:
    return settings.output_dir / "local_chrome_profile"


def _default_existing_chrome_user_data_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Google" / "Chrome" / "User Data"
    if sys_platform := os.environ.get("OSTYPE", ""):
        if "darwin" in sys_platform.lower():
            return Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    if Path("/Applications").exists():
        return Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    return Path.home() / ".config" / "google-chrome"


def _chrome_profile_mode() -> str:
    return settings.local_chrome_profile_mode if settings.local_chrome_profile_mode in {"dedicated", "existing"} else "dedicated"


def _chrome_user_data_dir() -> Path:
    if _chrome_profile_mode() != "existing":
        return _local_chrome_profile_dir()
    configured = settings.local_chrome_user_data_dir
    if configured:
        return Path(configured).expanduser()
    return _default_existing_chrome_user_data_dir()


def _chrome_profile_mode_payload() -> dict:
    mode = _chrome_profile_mode()
    return {
        "profile_mode": mode,
        "uses_dedicated_profile": mode == "dedicated",
        "uses_existing_chrome_profile": mode == "existing",
        "user_data_dir": str(_chrome_user_data_dir()),
        "profile_note": (
            "当前使用专用 Chrome profile，安全隔离，但需要在该窗口单独登录。"
            if mode == "dedicated"
            else "当前配置为复用日常 Chrome 用户数据目录；请先完全退出普通 Chrome，再用调试命令启动，否则 Chrome 可能忽略 remote-debugging-port。"
        ),
    }


def _chrome_debug_port(chrome_debug_url: str = CHROME_DEBUG_URL) -> str:
    _validate_local_chrome_debug_url(chrome_debug_url)
    return str(urlparse(chrome_debug_url).port or 9222)


def _manual_chrome_launch_command(
    profile_url: str = "",
    *,
    chrome_binary: str = DEFAULT_MAC_CHROME_BINARY,
    chrome_debug_url: str = CHROME_DEBUG_URL,
) -> str:
    target_url = _normalize_douyin_profile_url(profile_url) if (profile_url or "").strip() else "https://www.douyin.com/"
    args = [
        chrome_binary,
        f"--remote-debugging-port={_chrome_debug_port(chrome_debug_url)}",
        "--remote-allow-origins=http://127.0.0.1:8765,http://127.0.0.1:9222",
        f"--user-data-dir={_chrome_user_data_dir()}",
        "--no-first-run",
        "--no-default-browser-check",
        target_url,
    ]
    return " ".join(shlex.quote(str(value)) for value in args)


def issue_local_scan_token() -> str:
    token = secrets.token_urlsafe(24)
    _TOKENS[token] = time.time() + TOKEN_TTL_SECONDS
    _cleanup_tokens()
    return token


def consume_local_scan_token(token: str) -> None:
    _cleanup_tokens()
    expires_at = _TOKENS.pop(token or "", 0)
    if not expires_at or expires_at < time.time():
        raise AppError(ErrorCode.LOCAL_HELPER_TOKEN_INVALID)


def validate_local_scan_token(token: str) -> None:
    _cleanup_tokens()
    expires_at = _TOKENS.get(token or "", 0)
    if not expires_at or expires_at < time.time():
        raise AppError(ErrorCode.LOCAL_HELPER_TOKEN_INVALID)


def is_loopback_client(host: str | None) -> bool:
    value = (host or "").strip().strip("[]").rstrip(".").lower()
    if value in {"localhost", "testclient"}:
        return True
    try:
        return ip_address(value).is_loopback
    except ValueError:
        return False


def local_helper_security_contract() -> dict:
    return {
        "contract_version": 1,
        "scope": "local_helper_to_analysis_web_app",
        "loopback_only": True,
        "public_site_cookie_free": True,
        "requests_from_user_machine": True,
        "uses_user_local_chrome_session": True,
        "page_confirmation_required": True,
        "one_time_token_required": True,
        "cookie_read": False,
        "cookie_returned": False,
        "cookie_logged": False,
        "login_token_returned": False,
        "signed_media_url_returned": False,
        "raw_headers_returned": False,
        "dom_visible_metadata_only": True,
        "sensitive_fields_redacted": True,
        "returned_data_scope": [
            "account_visible_metadata",
            "visible_work_list",
            "visible_interaction_metrics",
            "sanitized_source_urls",
        ],
        "handoff_excludes": [
            "Cookie",
            "login token",
            "authorization header",
            "signed media URL",
            "raw request headers",
        ],
        "permission_note": "仅用于用户已授权或自有内容的本地学习、复盘和创作者规律分析。",
    }


def _chrome_helper_policy(*, chrome_available: bool, ready_for_profile_scan: bool) -> dict:
    if ready_for_profile_scan:
        next_action = "点击“本机 Chrome 辅助入口”，页面会申请一次性 token，并由用户确认后读取当前主页可见作品。"
    elif not chrome_available:
        next_action = "启动带 DevTools 的本机 Chrome，或复制启动命令手动打开。"
    elif _chrome_profile_mode() == "dedicated":
        next_action = "当前连接的是专用调试 Chrome，不是日常 Chrome；请在该调试 Chrome 中打开目标抖音主页，或切换为 existing 模式复用日常 Chrome 登录态。"
    else:
        next_action = "在本机 Chrome 中打开目标抖音主页，页面加载后重新检测或点击“本机 Chrome 辅助入口”。"
    return {
        "next_action": next_action,
        "request_origin": "user_local_chrome_and_user_local_ip",
        "confirmation_required": True,
        "one_time_token_required": True,
        "cookie_policy": "not_read_not_returned_not_logged",
        "returned_data_scope": local_helper_security_contract()["returned_data_scope"],
        "security_contract": local_helper_security_contract(),
    }


def chrome_helper_diagnostics(chrome_debug_url: str = CHROME_DEBUG_URL) -> dict:
    try:
        tabs = _chrome_tabs(chrome_debug_url)
    except AppError as error:
        if error.code != ErrorCode.LOCAL_CHROME_NOT_AVAILABLE:
            raise
        return {
            "chrome_available": False,
            "chrome_debug_url": chrome_debug_url,
            "tab_count": 0,
            "douyin_tab_count": 0,
            "douyin_profile_tab_count": 0,
            "douyin_tabs": [],
            "ready_for_profile_scan": False,
            "status_message": error.message,
            "launch_hint": _manual_chrome_launch_command(chrome_debug_url=chrome_debug_url),
            **_chrome_profile_mode_payload(),
            **_chrome_helper_policy(chrome_available=False, ready_for_profile_scan=False),
        }
    raw_douyin_tabs = [tab for tab in tabs if _is_douyin_tab(tab)]
    douyin_tabs = [_status_tab_payload(tab, index + 1) for index, tab in enumerate(raw_douyin_tabs)]
    profile_tabs = [tab for tab in raw_douyin_tabs if _is_douyin_profile_url(str(tab.get("url") or ""))]
    if profile_tabs:
        status_message = "已检测到可用的抖音主页标签页。"
    elif douyin_tabs:
        status_message = "已连接 Chrome DevTools，并检测到抖音标签页，但还没有抖音主页标签页。"
    elif _chrome_profile_mode() == "dedicated":
        status_message = "已连接专用调试 Chrome，但没有找到抖音主页标签页；日常 Chrome 中打开的抖音主页不会被这个专用 profile 看到。"
    else:
        status_message = "已连接 Chrome DevTools，但没有找到抖音主页标签页。"
    return {
        "chrome_available": True,
        "chrome_debug_url": chrome_debug_url,
        "tab_count": len(tabs),
        "douyin_tab_count": len(douyin_tabs),
        "douyin_profile_tab_count": len(profile_tabs),
        "douyin_tabs": douyin_tabs[:10],
        "ready_for_profile_scan": bool(profile_tabs),
        "status_message": status_message,
        "launch_hint": "" if profile_tabs else _manual_chrome_launch_command(chrome_debug_url=chrome_debug_url),
        **_chrome_profile_mode_payload(),
        **_chrome_helper_policy(chrome_available=True, ready_for_profile_scan=bool(profile_tabs)),
    }


def launch_local_chrome_debug(
    profile_url: str = "",
    *,
    chrome_binary: str = DEFAULT_MAC_CHROME_BINARY,
    chrome_debug_url: str = CHROME_DEBUG_URL,
) -> dict:
    binary = Path(chrome_binary)
    if not binary.is_file():
        raise AppError(
            ErrorCode.LOCAL_CHROME_NOT_AVAILABLE,
            f"未找到 Chrome 可执行文件：{chrome_binary}。请手动复制启动命令。",
        )
    target_url = _normalize_douyin_profile_url(profile_url) if (profile_url or "").strip() else "https://www.douyin.com/"
    port = _chrome_debug_port(chrome_debug_url)
    user_data_dir = _chrome_user_data_dir()
    user_data_dir.mkdir(parents=True, exist_ok=True)
    args = [
        str(binary),
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=http://127.0.0.1:8765,http://127.0.0.1:9222",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        target_url,
    ]
    safe_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }
    try:
        subprocess.Popen(
            args,
            env=safe_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as error:
        raise AppError(
            ErrorCode.LOCAL_CHROME_NOT_AVAILABLE,
            "无法启动本机 Chrome。请手动复制启动命令后重试。",
        ) from error
    return {
        "launched": True,
        "profile_url": _safe_metadata_url(target_url),
        "chrome_debug_url": chrome_debug_url,
        "user_data_dir": str(user_data_dir),
        **_chrome_profile_mode_payload(),
        "note": (
            "只启动本机 Chrome DevTools，不读取 Cookie；页面扫描仍需再次点击确认。"
            if _chrome_profile_mode() == "dedicated"
            else "已按现有 Chrome profile 模式启动 DevTools；请确认这是你的自用本机环境，扫描仍需页面确认和一次性 token。"
        ),
    }


def clear_local_chrome_profile() -> dict:
    profile_dir = (settings.output_dir / "local_chrome_profile").resolve()
    output_dir = settings.output_dir.resolve()
    if profile_dir == output_dir or output_dir not in profile_dir.parents:
        raise AppError(ErrorCode.LOCAL_CHROME_SCAN_FAILED, "本地 Chrome profile 路径不在 outputs 目录内，已拒绝清理。")
    existed = profile_dir.exists()
    if existed:
        try:
            shutil.rmtree(profile_dir)
        except Exception as error:
            raise AppError(
                ErrorCode.LOCAL_CHROME_SCAN_FAILED,
                "无法清理本地 Chrome profile。请先关闭调试 Chrome 后重试。",
            ) from error
    return {
        "cleared": existed,
        "profile_dir": str(profile_dir),
        "note": "已清理专用本地 Chrome profile；不会影响你的普通 Chrome 用户资料。",
    }


def open_douyin_profile_in_local_chrome(
    profile_url: str,
    *,
    chrome_debug_url: str = CHROME_DEBUG_URL,
) -> dict:
    _validate_local_chrome_debug_url(chrome_debug_url)
    target_url = _normalize_douyin_profile_url(profile_url)
    try:
        with httpx.Client(timeout=3.0, trust_env=False) as client:
            response = client.put(f"{chrome_debug_url.rstrip('/')}/json/new?{quote(target_url, safe='')}")
            response.raise_for_status()
            payload = response.json()
    except Exception as error:
        raise AppError(
            ErrorCode.LOCAL_CHROME_NOT_AVAILABLE,
            "无法通过 127.0.0.1:9222 打开 Chrome 标签页。请确认 Chrome 已用 remote debugging 模式启动。",
        ) from error
    if not isinstance(payload, dict):
        raise AppError(ErrorCode.LOCAL_CHROME_SCAN_FAILED, "Chrome DevTools 没有返回可解析标签页信息。")
    return _safe_tab_payload(payload)


def scan_douyin_profile_from_local_chrome(
    profile_url: str,
    *,
    max_items: int = 100,
    scroll_rounds: int = DEFAULT_SCROLL_ROUNDS,
    merge_sample_set_id: str = "",
    chrome_debug_url: str = CHROME_DEBUG_URL,
    authorization_context: dict | None = None,
) -> CloneSampleSet:
    tabs = _chrome_tabs(chrome_debug_url)
    target = _select_douyin_tab(tabs, profile_url)
    if not target:
        raise AppError(ErrorCode.LOCAL_CHROME_TAB_NOT_FOUND)
    websocket_url = target.get("webSocketDebuggerUrl")
    if not websocket_url:
        raise AppError(ErrorCode.LOCAL_CHROME_SCAN_FAILED, "Chrome tab 没有暴露 DevTools websocket。")
    _validate_local_websocket_url(str(websocket_url))

    payload = _evaluate_tab(
        websocket_url,
        _extractor_script(max_items=max_items, scroll_rounds=scroll_rounds),
    )
    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
    raw_items = payload.get("items") if isinstance(payload.get("items"), list) else []
    samples = [_sample_from_browser_item(item) for item in raw_items if isinstance(item, dict)]
    samples, duplicate_count = dedupe_samples(samples)
    if not samples:
        raise AppError(ErrorCode.LOCAL_CHROME_SCAN_FAILED, _empty_scan_message(profile, payload))

    warnings = [
        "本机 Chrome 辅助采集：仅读取当前页面 DOM 可见作品元数据，不读取 Cookie，不把 Cookie 传给前端或远端。",
        "请求和页面访问发生在你的本机 Chrome / 本机 IP；返回数据已过滤为账号资料和作品元数据。",
    ]
    if duplicate_count:
        warnings.append(f"已自动去重 {duplicate_count} 条重复作品。")
    captured_count = _safe_int(payload.get("captured_count"))
    scroll_count = _safe_int(payload.get("scroll_count"))
    visible_unique_link_count = _safe_int(payload.get("visible_unique_link_count"))
    ignored_link_count = _safe_int(payload.get("ignored_link_count"))
    expected_work_count = _safe_int((profile.get("stats") or {}).get("work_count")) if isinstance(profile.get("stats"), dict) else 0
    if scroll_count:
        warnings.append(f"已在当前 Chrome 标签页进行 {scroll_count} 轮受控滚动，采集到 {captured_count or len(samples)} 条可见作品。")
    if visible_unique_link_count:
        warnings.append(f"页面 DOM 中共检测到 {visible_unique_link_count} 个作品形态链接，其中已过滤 footer / 推荐等非当前账号链接。")
    if ignored_link_count:
        warnings.append("已过滤页面底部热门推荐、搜索引擎引流链接或重复链接，避免混入非当前账号样本。")
    if expected_work_count and expected_work_count > len(samples):
        warnings.append(
            f"账号页显示作品 {expected_work_count} 条，当前页面 DOM 可采集 {len(samples)} 条；"
            "差异通常来自平台分页未完全下发、不可见作品、图文/合集展示差异或风控限制。"
        )
    sample_set = CloneSampleSet(
        set_id=f"clone_{uuid.uuid4().hex}",
        title=f"{profile.get('nickname') or '本机 Chrome'} 素材池",
        creator_name=str(profile.get("nickname") or ""),
        source_platform="douyin",
        profile_metadata=_sanitize_profile_metadata(profile),
        samples=samples[: max(1, min(int(max_items or 100), 200))],
        warnings=warnings,
    )
    if merge_sample_set_id:
        sample_set = _merge_into_existing_sample_set(merge_sample_set_id, sample_set)
    output_dir = creator_clone_dir(sample_set.set_id)
    (output_dir / "browser_profile.json").write_text(
        json.dumps(_sanitize_profile(profile), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    audit = _capture_audit_payload(
        sample_set=sample_set,
        profile_url=profile_url,
        chrome_debug_url=chrome_debug_url,
        target_tab=target,
        capture_payload=payload,
        duplicate_count=duplicate_count,
        pre_merge_sample_count=len(samples),
        merge_sample_set_id=merge_sample_set_id,
        authorization_context=authorization_context,
    )
    _write_capture_audit(output_dir, audit)
    _write_handoff_manifest(output_dir, build_handoff_manifest(sample_set.set_id, sample_set=sample_set, capture_audit=audit))
    save_sample_set(sample_set)
    return sample_set


def load_capture_audit(set_id: str) -> dict:
    path = creator_clone_dir(set_id) / "capture_audit.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_handoff_manifest(set_id: str) -> dict:
    path = creator_clone_dir(set_id) / "handoff_manifest.json"
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            return payload
    sample_set = load_sample_set(set_id)
    manifest = build_handoff_manifest(set_id, sample_set=sample_set, capture_audit=load_capture_audit(set_id))
    _write_handoff_manifest(creator_clone_dir(set_id), manifest)
    return manifest


def build_handoff_manifest(
    set_id: str,
    *,
    sample_set: CloneSampleSet | None = None,
    capture_audit: dict | None = None,
) -> dict:
    sample_set = sample_set or load_sample_set(set_id)
    audit = capture_audit if isinstance(capture_audit, dict) else load_capture_audit(set_id)
    generated_at = datetime.now(timezone.utc).isoformat()
    samples = [_handoff_sample(sample) for sample in sample_set.samples]
    safety = dict(audit.get("safety") or {})
    security_contract = local_helper_security_contract()
    safety.update(
        {
            **{key: value for key, value in security_contract.items() if isinstance(value, bool)},
            "handoff_contains_cookie": False,
            "handoff_contains_login_token": False,
            "handoff_contains_signed_media_url": False,
            "handoff_metadata_only": True,
            "public_site_receives_sanitized_metadata_only": True,
            "local_browser_reads_visible_page_only": True,
        }
    )
    manifest = _sanitize_handoff_payload(
        {
            "handoff_version": 1,
            "generated_at": generated_at,
            "set_id": sample_set.set_id,
            "title": sample_set.title,
            "creator_name": sample_set.creator_name,
            "profile_metadata": sample_set.profile_metadata,
            "source_platform": sample_set.source_platform,
            "sample_count": len(samples),
            "samples": samples,
            "capture_audit": {
                "audit_version": audit.get("audit_version"),
                "captured_at": audit.get("captured_at"),
                "source_platform": audit.get("source_platform") or sample_set.source_platform,
                "capture_method": audit.get("capture_method") or "manual_or_public_import",
                "authorization": audit.get("authorization") or _local_authorization_audit(None),
                "scroll_count": audit.get("scroll_count"),
                "captured_count": audit.get("captured_count"),
                "final_sample_count": audit.get("final_sample_count") or len(samples),
                "media_summary": audit.get("media_summary") or _sample_media_summary(sample_set.samples),
            },
            "safety": safety,
        }
    )
    manifest["security_contract"] = security_contract
    manifest["handoff_scope"] = {
        "intended_receiver": "analysis_web_app",
        "contains": ["creator metadata", "sample metadata", "visible engagement metrics", "source work URLs"],
        "excludes": ["Cookie", "login token", "authorization header", "signed media URL", "raw request headers"],
        "permission_note": "仅用于用户已授权或自有内容的本地学习、复盘和创作者规律分析。",
    }
    return manifest


def _merge_into_existing_sample_set(set_id: str, incoming: CloneSampleSet) -> CloneSampleSet:
    existing = load_sample_set(set_id)
    before_count = len(existing.samples)
    merged_samples, duplicate_count = dedupe_samples([*existing.samples, *incoming.samples])
    added_count = max(0, len(merged_samples) - before_count)
    existing.samples = merged_samples
    existing.creator_name = existing.creator_name or incoming.creator_name
    existing.source_platform = existing.source_platform or incoming.source_platform
    existing.profile_metadata = {**incoming.profile_metadata, **existing.profile_metadata} if existing.profile_metadata else incoming.profile_metadata
    existing.warnings = [
        *existing.warnings,
        *incoming.warnings,
        f"继续采集完成：新增 {added_count} 条，重复 {duplicate_count} 条，当前素材池共 {len(existing.samples)} 条。",
    ]
    return existing


def _capture_audit_payload(
    *,
    sample_set: CloneSampleSet,
    profile_url: str,
    chrome_debug_url: str,
    target_tab: dict,
    capture_payload: dict,
    duplicate_count: int,
    pre_merge_sample_count: int,
    merge_sample_set_id: str,
    authorization_context: dict | None = None,
) -> dict:
    media_summary = _sample_media_summary(sample_set.samples)
    security_contract = local_helper_security_contract()
    authorization = _local_authorization_audit(authorization_context)
    return {
        "audit_version": 1,
        "set_id": sample_set.set_id,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source_platform": "douyin",
        "capture_method": str(capture_payload.get("capture_method") or "local_chrome_dom_readonly_scroll"),
        "requested_profile": _safe_requested_profile(profile_url)[:500],
        "chrome_debug_url": chrome_debug_url,
        "target_tab": _safe_tab_payload(target_tab),
        "scroll_count": _safe_int(capture_payload.get("scroll_count")),
        "captured_count": _safe_int(capture_payload.get("captured_count")),
        "pre_merge_sample_count": pre_merge_sample_count,
        "final_sample_count": len(sample_set.samples),
        "duplicate_count": int(duplicate_count or 0),
        "merged_into_existing_set": bool(merge_sample_set_id),
        "profile_metadata": sample_set.profile_metadata,
        "media_summary": media_summary,
        "field_coverage": _sample_field_coverage(sample_set.samples),
        "authorization": authorization,
        "safety": {
            **{key: value for key, value in security_contract.items() if isinstance(value, bool)},
            "loopback_only": True,
            "one_time_token_required": True,
            "one_time_token_consumed": authorization["one_time_token_consumed"],
            "page_confirmation_required": True,
            "page_confirmed": authorization["page_confirmed"],
            "cookie_read": False,
            "cookie_returned": False,
            "cookie_logged": False,
            "dom_visible_metadata_only": True,
            "sensitive_fields_redacted": True,
            "requests_from_user_machine": True,
        },
        "security_contract": security_contract,
        "returned_fields": [
            "profile nickname",
            "profile bio",
            "profile visible stats",
            "profile sec_user_id",
            "profile visible text length",
            "aweme_id",
            "source_url",
            "title",
            "desc",
            "cover_url",
            "author",
            "create_time",
            "tags",
            "visible like/comment/share/collect counts",
            "visible play count when present",
        ],
    }


def _local_authorization_audit(context: dict | None = None) -> dict:
    payload = context if isinstance(context, dict) else {}
    return {
        "page_confirmed": bool(payload.get("page_confirmed")),
        "one_time_token_consumed": bool(payload.get("one_time_token_consumed")),
        "trigger": _redact_sensitive(str(payload.get("trigger") or "unknown"))[:80],
        "note": "本地助手动作必须由页面按钮触发，并在路由层消费一次性 token。",
    }


def _sample_media_summary(samples: list[CloneSample]) -> dict:
    video_count = sum(1 for sample in samples if sample.media_type == "video")
    image_count = sum(1 for sample in samples if sample.media_type == "image")
    unknown_count = sum(1 for sample in samples if sample.media_type not in {"video", "image"})
    buildable_item_count = sum(
        1
        for sample in samples
        if sample.media_type not in {"image", "text"} and bool(sample.aweme_id or sample.source_url)
    )
    metadata_only_count = sum(1 for sample in samples if sample.understanding_level == "metadata_only")
    partial_count = sum(1 for sample in samples if sample.understanding_level == "partial")
    full_count = sum(1 for sample in samples if sample.understanding_level == "full")
    return {
        "video_count": video_count,
        "image_count": image_count,
        "unknown_count": unknown_count,
        "buildable_item_count": buildable_item_count,
        "metadata_only_count": metadata_only_count,
        "partial_count": partial_count,
        "full_count": full_count,
    }


def _sample_field_coverage(samples: list[CloneSample]) -> dict:
    total = len(samples)
    metric_count = sum(
        1
        for sample in samples
        if sample.like_count or sample.comment_count or sample.share_count or sample.collect_count or sample.view_count
    )
    return {
        "total": total,
        "with_title": sum(1 for sample in samples if sample.title),
        "with_source_url": sum(1 for sample in samples if sample.source_url),
        "with_cover_url": sum(1 for sample in samples if sample.cover_url),
        "with_author": sum(1 for sample in samples if sample.author),
        "with_create_time": sum(1 for sample in samples if sample.create_time),
        "with_tags": sum(1 for sample in samples if sample.tags),
        "with_any_visible_metric": metric_count,
    }


def _write_capture_audit(output_dir: Path, audit: dict) -> None:
    (output_dir / "capture_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (output_dir / "capture_audits.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(audit, ensure_ascii=False, separators=(",", ":")) + "\n")


def _write_handoff_manifest(output_dir: Path, manifest: dict) -> None:
    (output_dir / "handoff_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _handoff_sample(sample: CloneSample) -> dict:
    payload = sample.to_dict()
    allowed = {
        "sample_id",
        "source_type",
        "source_url",
        "aweme_id",
        "title",
        "desc",
        "author",
        "cover_url",
        "media_type",
        "like_count",
        "comment_count",
        "share_count",
        "collect_count",
        "view_count",
        "create_time",
        "case_id",
        "understanding_level",
        "has_video",
        "has_frames",
        "has_asr",
        "has_ocr",
        "has_comments",
        "enrichment_status",
        "asr_status",
        "ocr_status",
        "analysis_status",
        "tags",
        "notes",
        "engagement_score",
    }
    clean = {key: payload.get(key) for key in allowed if key in payload}
    clean["source_url"] = _safe_metadata_url(str(clean.get("source_url") or ""), aweme_id=str(clean.get("aweme_id") or ""))
    clean["cover_url"] = _safe_metadata_url(str(clean.get("cover_url") or ""))
    clean["title"] = _redact_sensitive(str(clean.get("title") or ""))[:220]
    clean["desc"] = _redact_sensitive(str(clean.get("desc") or ""))[:500]
    clean["author"] = _redact_sensitive(str(clean.get("author") or ""))[:120]
    clean["notes"] = _redact_sensitive(str(clean.get("notes") or ""))[:500]
    return clean


def _sanitize_handoff_payload(value):
    if isinstance(value, dict):
        return {str(key): _sanitize_handoff_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_handoff_payload(item) for item in value]
    if isinstance(value, str):
        return _redact_sensitive(value)
    return value


def _cleanup_tokens() -> None:
    now = time.time()
    expired = [token for token, expires_at in _TOKENS.items() if expires_at < now]
    for token in expired:
        _TOKENS.pop(token, None)


def _chrome_tabs(chrome_debug_url: str) -> list[dict]:
    _validate_local_chrome_debug_url(chrome_debug_url)
    try:
        with httpx.Client(timeout=3.0, trust_env=False) as client:
            response = client.get(f"{chrome_debug_url.rstrip('/')}/json")
            response.raise_for_status()
            data = response.json()
    except Exception as error:
        raise AppError(
            ErrorCode.LOCAL_CHROME_NOT_AVAILABLE,
            "未检测到 127.0.0.1:9222 的 Chrome DevTools。可用命令示例：/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222",
        ) from error
    if not isinstance(data, list):
        raise AppError(ErrorCode.LOCAL_CHROME_NOT_AVAILABLE)
    return [item for item in data if isinstance(item, dict)]


def _is_douyin_tab(tab: dict) -> bool:
    return tab.get("type") == "page" and _is_douyin_url(str(tab.get("url") or ""))


def _safe_tab_payload(tab: dict) -> dict:
    url = str(tab.get("url") or "")
    return {
        "id": _redact_sensitive(str(tab.get("id") or ""))[:120],
        "type": _redact_sensitive(str(tab.get("type") or ""))[:40],
        "title": _redact_sensitive(str(tab.get("title") or ""))[:160],
        "url": _safe_metadata_url(url)[:500],
        "is_profile": _is_douyin_profile_url(url),
    }


def _status_tab_payload(tab: dict, index: int) -> dict:
    url = str(tab.get("url") or "")
    is_profile = _is_douyin_profile_url(url)
    return {
        "index": index,
        "type": _redact_sensitive(str(tab.get("type") or ""))[:40],
        "is_profile": is_profile,
        "label": f"{'抖音主页' if is_profile else '抖音标签页'} #{index}",
    }


def _select_douyin_tab(tabs: list[dict], profile_url: str) -> dict | None:
    profile_url = profile_url or ""
    target_token = _profile_match_token(profile_url)
    douyin_tabs = [
        tab
        for tab in tabs
        if _is_douyin_tab(tab)
    ]
    if target_token:
        for tab in douyin_tabs:
            if target_token in str(tab.get("url", "")) and _is_douyin_profile_url(str(tab.get("url") or "")):
                return tab
        return None
    for tab in douyin_tabs:
        if _is_douyin_profile_url(str(tab.get("url") or "")):
            return tab
    return douyin_tabs[0] if douyin_tabs else None


def _is_douyin_url(value: str) -> bool:
    try:
        parsed = urlparse(value or "")
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return parsed.scheme in {"http", "https"} and (host == "douyin.com" or host.endswith(".douyin.com"))


def _is_douyin_profile_url(value: str) -> bool:
    if not _is_douyin_url(value):
        return False
    parsed = urlparse(value or "")
    parts = [part for part in parsed.path.split("/") if part]
    return len(parts) >= 2 and parts[0] == "user"


def _profile_match_token(profile_url: str) -> str:
    parsed = urlparse(profile_url or "")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "user":
        return parts[1]
    return profile_url.strip()


def _normalize_douyin_profile_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise AppError(ErrorCode.INVALID_PROFILE_URL)
    if not re.match(r"^https?://", raw, flags=re.IGNORECASE):
        return f"https://www.douyin.com/user/{quote(raw, safe='')}"
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if not (host == "douyin.com" or host.endswith(".douyin.com")):
        raise AppError(ErrorCode.INVALID_PROFILE_URL, "只能在本机 Chrome 中打开抖音域名主页。")
    if parsed.username or parsed.password:
        raise AppError(ErrorCode.INVALID_PROFILE_URL, "抖音主页 URL 不能包含用户名或密码。")
    path = parsed.path or "/"
    return urlunparse((parsed.scheme, _safe_url_netloc(parsed), path, "", "", ""))


def _validate_local_chrome_debug_url(chrome_debug_url: str) -> None:
    try:
        parsed = urlparse(chrome_debug_url or "")
    except ValueError as error:
        raise AppError(ErrorCode.LOCAL_CHROME_SCAN_FAILED, "Chrome DevTools HTTP 地址无效。") from error
    if parsed.scheme != "http" or not is_loopback_client(parsed.hostname):
        raise AppError(ErrorCode.LOCAL_CHROME_SCAN_FAILED, "已拒绝非本机 Chrome DevTools HTTP 地址。")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise AppError(ErrorCode.LOCAL_CHROME_SCAN_FAILED, "Chrome DevTools HTTP 地址不能包含凭据、查询参数或片段。")


def _validate_local_websocket_url(websocket_url: str) -> None:
    try:
        parsed = urlparse(websocket_url or "")
    except ValueError as error:
        raise AppError(ErrorCode.LOCAL_CHROME_SCAN_FAILED, "Chrome DevTools websocket 地址无效。") from error
    if parsed.scheme != "ws" or not is_loopback_client(parsed.hostname):
        raise AppError(ErrorCode.LOCAL_CHROME_SCAN_FAILED, "已拒绝非本机 Chrome DevTools websocket。")
    if parsed.username or parsed.password:
        raise AppError(ErrorCode.LOCAL_CHROME_SCAN_FAILED, "Chrome DevTools websocket 地址不能包含凭据。")


def _evaluate_tab(websocket_url: str, expression: str) -> dict:
    _validate_local_websocket_url(websocket_url)
    try:
        import websocket  # type: ignore
    except ImportError as error:
        raise AppError(ErrorCode.LOCAL_CHROME_NOT_AVAILABLE, "缺少 websocket-client，请先安装 requirements.txt。") from error

    try:
        ws = websocket.create_connection(websocket_url, timeout=20, origin="http://127.0.0.1:9222")
        try:
            message_id = 1
            ws.send(
                json.dumps(
                    {
                        "id": message_id,
                        "method": "Runtime.evaluate",
                        "params": {
                            "expression": expression,
                            "returnByValue": True,
                            "awaitPromise": True,
                        },
                    }
                )
            )
            while True:
                raw = ws.recv()
                data = json.loads(raw)
                if data.get("id") != message_id:
                    continue
                if data.get("exceptionDetails"):
                    raise AppError(ErrorCode.LOCAL_CHROME_SCAN_FAILED, "Chrome 页面脚本执行失败。")
                value = data.get("result", {}).get("result", {}).get("value")
                if not isinstance(value, dict):
                    raise AppError(ErrorCode.LOCAL_CHROME_SCAN_FAILED, "Chrome 页面没有返回可解析 JSON。")
                return value
        finally:
            ws.close()
    except AppError:
        raise
    except Exception as error:
        raise AppError(ErrorCode.LOCAL_CHROME_SCAN_FAILED, str(error)[:300]) from error


def _extractor_script(max_items: int = 100, scroll_rounds: int = DEFAULT_SCROLL_ROUNDS) -> str:
    max_items = max(1, min(int(max_items or 100), 200))
    scroll_rounds = max(0, min(int(scroll_rounds or 0), MAX_SCROLL_ROUNDS))
    return f"""
(async () => {{
  const maxItems = {max_items};
  const scrollRounds = {scroll_rounds};
  const absUrl = (value) => {{
    try {{ return new URL(value || '', location.href).href; }} catch (_) {{ return ''; }}
  }};
  const textOf = (node) => (node && (node.innerText || node.textContent) || '').replace(/\\s+/g, ' ').trim();
  const parseCount = (value) => {{
    const text = String(value || '').replace(/,/g, '');
    const match = text.match(/(\\d+(?:\\.\\d+)?)(万|亿)?/);
    if (!match) return 0;
    let number = Number(match[1] || 0);
    if (match[2] === '万') number *= 10000;
    if (match[2] === '亿') number *= 100000000;
    return Math.round(number);
  }};
  const awemeIdFromUrl = (url) => {{
    const match = String(url || '').match(/(?:video|note)\\/(\\d{{15,22}})|modal_id=(\\d{{15,22}})/);
    return match ? (match[1] || match[2] || '') : '';
  }};
  const compactTitle = (text, id) => {{
    const cleaned = String(text || '')
      .split(/\\n|\\s{{2,}}/)
      .map((line) => line.trim())
      .filter(Boolean)
      .filter((line) => !/^\\d+(?:\\.\\d+)?[万亿]?$/.test(line))
      .filter((line) => !line.includes('抖音') || line.length < 60);
    return (cleaned[0] || `抖音作品 ${{id}}`).slice(0, 160);
  }};
  const profileNickname = () => (document.querySelector('[data-e2e="user-title"], h1')?.innerText || document.title || '').replace(/\\s+/g, ' ').trim().slice(0, 120);
  const profileBio = () => {{
    const selectors = [
      '[data-e2e="user-desc"]',
      '[class*="user-desc"]',
      '[class*="signature"]',
      '[class*="bio"]',
    ];
    for (const selector of selectors) {{
      const value = textOf(document.querySelector(selector));
      if (value && value.length <= 260) return value;
    }}
    return '';
  }};
  const secUserIdFromLocation = () => {{
    const match = String(location.pathname || '').match(/\\/user\\/([^/?#]+)/);
    return match ? decodeURIComponent(match[1] || '').slice(0, 120) : '';
  }};
  const visibleTime = (text) => {{
    const value = String(text || '').replace(/\\s+/g, ' ');
    const patterns = [
      /\\d{{4}}[-/.年]\\d{{1,2}}[-/.月]\\d{{1,2}}日?/,
      /\\d{{1,2}}[-/.月]\\d{{1,2}}日?/,
      /\\d+\\s*(?:秒|分钟|小时|天|周|月|年)前/,
      /昨天|前天|刚刚/,
    ];
    for (const pattern of patterns) {{
      const match = value.match(pattern);
      if (match) return match[0].slice(0, 40);
    }}
    return '';
  }};
  const visibleTags = (text) => Array.from(String(text || '').matchAll(/#([^#\\s]{{1,30}})/g))
    .map((match) => match[1].replace(/[，。,.!！?？:：;；].*$/, '').trim())
    .filter(Boolean)
    .slice(0, 8);
	  const metricNear = (text, keyword) => {{
	    const normalized = String(text || '').replace(/,/g, '');
	    const patterns = [
	      new RegExp(`${{keyword}}\\\\s*(\\\\d+(?:\\\\.\\\\d+)?)(万|亿)?`),
	      new RegExp(`(\\\\d+(?:\\\\.\\\\d+)?)(万|亿)?\\\\s*${{keyword}}`),
    ];
    for (const pattern of patterns) {{
      const match = normalized.match(pattern);
      if (match) return parseCount(`${{match[1]}}${{match[2] || ''}}`);
	    }}
	    return 0;
	  }};
  const profileWorkCount = () => {{
    const candidates = [
      ...Array.from(document.querySelectorAll('h2.A22Lqe_t, [role="tab"], h2, h3')),
      ...Array.from(document.querySelectorAll('[class*="semi-tabs-tab"]')),
    ];
    for (const node of candidates) {{
      const text = textOf(node);
      if (/^作品\\s*\\d/.test(text)) return metricNear(text, '作品') || parseCount(text.replace('作品', ''));
    }}
    return metricNear(textOf(document.body), '作品');
  }};
		  const metricNodeText = (node) => [
	    textOf(node),
	    node?.getAttribute?.('aria-label') || '',
	    node?.getAttribute?.('title') || '',
	    node?.getAttribute?.('data-e2e') || '',
	  ].join(' ');
	  const leadingCount = (text) => {{
	    const match = String(text || '').trim().match(/^(\\d+(?:\\.\\d+)?)(万|亿)?(?:\\s|$)/);
	    return match ? parseCount(`${{match[1]}}${{match[2] || ''}}`) : 0;
	  }};
	  const metricFromCard = (card, keywords) => {{
	    const nodes = card?.querySelectorAll
	      ? Array.from(card.querySelectorAll('[aria-label], [title], [data-e2e], button, span, div')).slice(0, 90)
	      : [];
	    const texts = [
	      textOf(card),
	      ...nodes.flatMap((node) => [
	        textOf(node),
	        node?.getAttribute?.('aria-label') || '',
	        node?.getAttribute?.('title') || '',
	      ]),
	    ].filter(Boolean);
	    for (const keyword of keywords) {{
	      for (const text of texts) {{
	        const direct = metricNear(text, keyword);
	        if (direct) return direct;
	      }}
	    }}
	    return 0;
	  }};
  const findScrollTarget = () => {{
    const nodes = Array.from(document.querySelectorAll('body, main, div, section'));
    const ranked = nodes
      .map((node) => ({{
        node,
        anchors: node.querySelectorAll
          ? node.querySelectorAll('a[href*="/video/"], a[href*="/note/"], a[href*="modal_id="]').length
          : 0,
        delta: Math.max(0, (node.scrollHeight || 0) - (node.clientHeight || 0)),
      }}))
      .filter((entry) => entry.anchors > 10 && entry.delta > 40)
      .sort((a, b) => (b.anchors - a.anchors) || (b.delta - a.delta));
    return ranked[0]?.node || document.scrollingElement || document.documentElement;
  }};
	  const ignoredAnchor = (anchor) => {{
    if (!anchor) return true;
    let node = anchor;
    for (let i = 0; i < 8 && node; i += 1) {{
      const tag = String(node.tagName || '').toLowerCase();
      const className = String(node.className || '').toLowerCase();
      const text = textOf(node).slice(0, 220);
      if (tag === 'footer' || className.includes('footer')) return true;
      if (text.includes('广告投放') && text.includes('用户服务协议')) return true;
      if (text.startsWith('热门：抖音')) return true;
      node = node.parentElement;
    }}
    const url = absUrl(anchor.getAttribute('href') || anchor.href);
    return /[?&]source=Baiduspider/i.test(url);
  }};
  const nearestCard = (anchor) => {{
    let node = anchor;
    let best = anchor;
    for (let i = 0; i < 6 && node; i += 1) {{
      const text = textOf(node);
      const anchorCount = node.querySelectorAll
        ? node.querySelectorAll('a[href*="/video/"], a[href*="/note/"], a[href*="modal_id="]').length
        : 0;
      if (anchorCount > 1) break;
      if (text.length > textOf(best).length && text.length < 280) best = node;
      node = node.parentElement;
    }}
    return best;
  }};
  const items = [];
  const seen = new Set();
  const seenLinks = new Set();
  let ignoredLinkCount = 0;
  const collect = () => {{
    const anchors = Array.from(document.querySelectorAll('a[href*="/video/"], a[href*="/note/"], a[href*="modal_id="]'));
    for (const anchor of anchors) {{
      const url = absUrl(anchor.getAttribute('href') || anchor.href);
      const id = awemeIdFromUrl(url);
      if (!id) continue;
      if (!seenLinks.has(id)) seenLinks.add(id);
      if (ignoredAnchor(anchor)) {{
        ignoredLinkCount += 1;
        continue;
      }}
      if (seen.has(id)) continue;
      seen.add(id);
      const card = nearestCard(anchor);
      const rawText = textOf(card) || textOf(anchor);
      const image = card.querySelector('img');
      const cover = image ? absUrl(image.currentSrc || image.src || image.getAttribute('src')) : '';
      const mediaType = url.includes('/note/') ? 'image' : 'video';
      const countTexts = Array.from(card.querySelectorAll('*'))
        .map((node) => textOf(node))
        .filter((value) => /^\\d+(?:\\.\\d+)?[万亿]?$/.test(value))
        .slice(0, 4);
      items.push({{
        aweme_id: id,
        source_url: url,
        title: compactTitle(rawText, id),
        desc: rawText.slice(0, 260),
        cover_url: cover,
        media_type: mediaType,
        author: profileNickname(),
	        create_time: visibleTime(rawText),
	        tags: visibleTags(rawText),
	        like_count: metricFromCard(card, ['点赞', '赞', '喜欢']) || leadingCount(rawText) || parseCount(countTexts[0] || 0),
	        comment_count: metricFromCard(card, ['评论']),
	        share_count: metricFromCard(card, ['分享', '转发']),
	        collect_count: metricFromCard(card, ['收藏']),
	        view_count: metricFromCard(card, ['播放', '观看']) || 0,
	      }});
      if (items.length >= maxItems) break;
    }}
  }};
  collect();
  let scrollCount = 0;
  let stableRounds = 0;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const scrollTarget = findScrollTarget();
  for (let round = 0; round < scrollRounds && items.length < maxItems; round += 1) {{
    const before = items.length;
    if (scrollTarget === document.scrollingElement || scrollTarget === document.documentElement || scrollTarget === document.body) {{
      window.scrollBy({{top: Math.max(window.innerHeight * 1.4, 800), left: 0, behavior: 'auto'}});
    }} else {{
      scrollTarget.scrollTop = Math.min(
        scrollTarget.scrollHeight,
        (scrollTarget.scrollTop || 0) + Math.max((scrollTarget.clientHeight || window.innerHeight) * 0.9, 600),
      );
    }}
    scrollCount += 1;
    await sleep(450);
    collect();
    const nearBottom = (
      scrollTarget.scrollTop + (scrollTarget.clientHeight || window.innerHeight)
    ) >= ((scrollTarget.scrollHeight || 0) - 120);
    if (items.length === before) stableRounds += 1;
    else stableRounds = 0;
    if (stableRounds >= 3 && nearBottom) break;
  }}
  const bodyText = textOf(document.body);
  const profile = {{
    nickname: profileNickname(),
    url: location.href,
    sec_user_id: secUserIdFromLocation(),
    bio: profileBio(),
    stats: {{
	      following_count: metricNear(bodyText, '关注'),
	      follower_count: metricNear(bodyText, '粉丝'),
	      liked_count: metricNear(bodyText, '获赞') || metricNear(bodyText, '点赞'),
	      work_count: profileWorkCount(),
    }},
    captured_at: new Date().toISOString(),
    visible_text_excerpt: bodyText.slice(0, 1200),
  }};
  return {{
    ok: true,
    capture_method: 'local_chrome_dom_readonly_scroll',
    profile,
    items,
    captured_count: items.length,
    scroll_count: scrollCount,
    visible_unique_link_count: seenLinks.size,
    ignored_link_count: ignoredLinkCount,
    scroll_target: {{
      tag: scrollTarget?.tagName || '',
      class_name: String(scrollTarget?.className || '').slice(0, 120),
      scroll_top: scrollTarget?.scrollTop || 0,
      scroll_height: scrollTarget?.scrollHeight || 0,
      client_height: scrollTarget?.clientHeight || 0,
    }},
  }};
}})()
"""


def _sample_from_browser_item(item: dict) -> CloneSample:
    aweme_id = str(item.get("aweme_id") or "")
    source_url = _safe_metadata_url(str(item.get("source_url") or ""), aweme_id=aweme_id)
    title = _redact_sensitive(str(item.get("title") or f"抖音作品 {aweme_id}"))[:180]
    desc = _redact_sensitive(str(item.get("desc") or ""))
    cover_url = _safe_metadata_url(str(item.get("cover_url") or ""))
    return CloneSample(
        sample_id=f"sample_{aweme_id or uuid.uuid4().hex}",
        source_type=detect_source_type(source_url),
        source_url=source_url,
        aweme_id=aweme_id,
        title=title,
        desc=desc,
        author=_redact_sensitive(str(item.get("author") or ""))[:80],
        cover_url=cover_url,
        media_type=normalize_media_type(str(item.get("media_type") or "unknown")),
        like_count=_safe_int(item.get("like_count")),
        comment_count=_safe_int(item.get("comment_count")),
        share_count=_safe_int(item.get("share_count")),
        collect_count=_safe_int(item.get("collect_count")),
        view_count=_safe_int(item.get("view_count")),
        create_time=_redact_sensitive(str(item.get("create_time") or ""))[:80],
        understanding_level="metadata_only",
        has_video=False,
        has_frames=False,
        tags=[
            _redact_sensitive(str(value))[:40]
            for value in (item.get("tags") if isinstance(item.get("tags"), list) else [])
            if _redact_sensitive(str(value)).strip()
        ][:8],
        notes="来自本机 Chrome DOM 只读辅助采集，尚未生成素材包。",
    )


def _empty_scan_message(profile: dict, payload: dict) -> str:
    visible_text = _redact_sensitive(str(profile.get("visible_text_excerpt") or ""))[:240]
    title = _redact_sensitive(str(profile.get("nickname") or ""))[:120]
    captured_count = _safe_int(payload.get("captured_count"))
    scroll_count = _safe_int(payload.get("scroll_count"))
    hints = []
    lower_text = visible_text.lower()
    if any(keyword in visible_text for keyword in ["登录", "验证码", "验证", "安全校验", "滑块"]):
        hints.append("请先在专用 Chrome 中登录或完成平台验证")
    if any(keyword in visible_text for keyword in ["刷新", "稍后", "异常", "访问过于频繁"]):
        hints.append("页面可能被限制或尚未加载完成，等待后刷新再试")
    if "verify" in lower_text or "captcha" in lower_text:
        hints.append("页面疑似处于英文验证/验证码状态")
    if not hints:
        hints.append("请确认当前标签页停留在创作者主页作品列表，而不是单个视频页或空白页")
    context = f"当前页面：{title or '未知标题'}；滚动 {scroll_count} 轮；脚本捕获 {captured_count} 条。"
    visible_text_note = f"页面可见文本约 {len(visible_text)} 字，未回传原文。" if visible_text else "未读取到有效可见文本。"
    return f"Chrome 页面未提取到可见作品。{context}{visible_text_note}建议：{'；'.join(hints)}。"


def _sanitize_profile(profile: dict) -> dict:
    allowed = {"nickname", "url", "captured_at"}
    sanitized = {}
    for key, value in profile.items():
        if key not in allowed:
            continue
        if key == "url":
            sanitized[key] = _safe_metadata_url(str(value or ""))[:500]
        else:
            sanitized[key] = _redact_sensitive(str(value)[:2000])
    visible_text = _redact_sensitive(str(profile.get("visible_text_excerpt") or ""))
    if visible_text:
        sanitized["visible_text_excerpt_chars"] = len(visible_text)
    return sanitized


def _sanitize_profile_metadata(profile: dict) -> dict:
    stats = profile.get("stats") if isinstance(profile.get("stats"), dict) else {}
    metadata = {
        "nickname": _redact_sensitive(str(profile.get("nickname") or ""))[:120],
        "sec_user_id": _redact_sensitive(str(profile.get("sec_user_id") or ""))[:160],
        "bio": _redact_sensitive(str(profile.get("bio") or ""))[:260],
        "profile_url": _safe_metadata_url(str(profile.get("url") or ""))[:500],
        "captured_at": _redact_sensitive(str(profile.get("captured_at") or ""))[:80],
        "stats": {
            "following_count": _safe_int(stats.get("following_count")),
            "follower_count": _safe_int(stats.get("follower_count")),
            "liked_count": _safe_int(stats.get("liked_count")),
            "work_count": _safe_int(stats.get("work_count")),
        },
        "capture_method": "local_chrome_dom_visible_profile",
    }
    return {
        key: value
        for key, value in metadata.items()
        if value is not None and value != "" and value != {}
    }


def _safe_requested_profile(value: str) -> str:
    raw = str(value or "").strip()
    if re.match(r"^https?://", raw, flags=re.IGNORECASE):
        return _safe_metadata_url(raw)
    return _redact_sensitive(raw)


def _safe_metadata_url(value: str, *, aweme_id: str = "") -> str:
    raw = _redact_sensitive(str(value or "").strip())
    if not raw:
        return ""
    parsed = urlparse(raw)
    if aweme_id and re.fullmatch(r"\d{15,22}", aweme_id):
        host = (parsed.hostname or "").lower()
        if host == "douyin.com" or host.endswith(".douyin.com"):
            if "/note/" in (parsed.path or ""):
                return f"https://www.douyin.com/note/{aweme_id}"
            return f"https://www.douyin.com/video/{aweme_id}"
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    if _is_private_or_local_host(parsed.hostname):
        return ""
    return _redact_sensitive(urlunparse((parsed.scheme, _safe_url_netloc(parsed), parsed.path or "/", "", "", "")))


def _safe_url_netloc(parsed) -> str:
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parsed.port:
        return f"{host}:{parsed.port}"
    return host


def _is_private_or_local_host(hostname: str) -> bool:
    host = (hostname or "").strip().lower().strip("[]")
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        address = ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local or address.is_reserved


def _redact_sensitive(value: str) -> str:
    if not value:
        return ""
    return SENSITIVE_FIELD_RE.sub("[redacted]", value)


def _safe_int(value) -> int:
    try:
        return int(float(str(value or "0").replace(",", "")))
    except (TypeError, ValueError):
        return 0
