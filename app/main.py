from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from urllib.parse import urlparse

from app.config import settings
from app.database import init_db
from app.routes import cases, creator_clone, downloads, jobs, local_helper, pages, profile, settings as settings_routes, videos
from app.services.local_chrome import is_loopback_client


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
LOCAL_TEST_HOSTS = {"testserver"}


def _host_without_port(value: str) -> str:
    host = (value or "").strip().lower()
    if not host:
        return ""
    if host.startswith("[") and "]" in host:
        return host[1:host.index("]")]
    if host.count(":") > 1:
        return host
    return host.rsplit(":", 1)[0] if ":" in host else host


def _is_allowed_local_host(value: str) -> bool:
    host = _host_without_port(value)
    return host in LOCAL_TEST_HOSTS or is_loopback_client(host)


def _is_allowed_local_url(value: str) -> bool:
    raw = (value or "").strip()
    if not raw:
        return True
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    return _is_allowed_local_host(parsed.hostname)


def _forwarded_for_hosts(value: str) -> list[str]:
    hosts: list[str] = []
    for raw_part in (value or "").split(","):
        part = raw_part.strip().strip('"')
        if not part:
            continue
        if part.startswith("[") and "]" in part:
            hosts.append(part[1:part.index("]")])
            continue
        if ":" in part and part.count(":") == 1:
            hosts.append(part.rsplit(":", 1)[0])
            continue
        hosts.append(part)
    return hosts


def _forwarded_header_hosts(value: str) -> list[str]:
    hosts: list[str] = []
    for entry in (value or "").split(","):
        for part in entry.split(";"):
            key, separator, raw_value = part.strip().partition("=")
            if separator and key.lower() == "for":
                hosts.extend(_forwarded_for_hosts(raw_value))
    return hosts


def _has_non_loopback_forwarded_client(headers) -> bool:
    candidates: list[str] = []
    candidates.extend(_forwarded_for_hosts(headers.get("x-forwarded-for", "")))
    candidates.extend(_forwarded_for_hosts(headers.get("x-real-ip", "")))
    candidates.extend(_forwarded_header_hosts(headers.get("forwarded", "")))
    return any(host and not is_loopback_client(host) for host in candidates)


def _local_forbidden_response(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            "error_code": "LOCAL_HELPER_FORBIDDEN",
            "message": message,
        },
    )


def create_app() -> FastAPI:
    settings.ensure_directories()
    init_db()
    app = FastAPI(
        title="short-video-agent",
        description="本地短视频爆款分析素材包生成器",
        version="0.1.0",
    )

    @app.middleware("http")
    async def local_only_guard(request, call_next):
        client_host = request.client.host if request.client else ""
        if not is_loopback_client(client_host):
            return _local_forbidden_response("short-video-agent 自用版只允许本机 127.0.0.1 / localhost 访问。")
        if _has_non_loopback_forwarded_client(request.headers):
            return _local_forbidden_response("short-video-agent 自用版拒绝经公网代理转发的访问。")
        if not _is_allowed_local_host(request.headers.get("host", "")):
            return _local_forbidden_response("short-video-agent 自用版只接受 127.0.0.1 / localhost Host。")
        if request.method.upper() not in SAFE_METHODS:
            origin = request.headers.get("origin", "")
            referer = request.headers.get("referer", "")
            if origin and not _is_allowed_local_url(origin):
                return _local_forbidden_response("本地网页拒绝非本机 Origin 发起的写操作。")
            if referer and not _is_allowed_local_url(referer):
                return _local_forbidden_response("本地网页拒绝非本机 Referer 发起的写操作。")
        return await call_next(request)

    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(pages.router)
    app.include_router(videos.router)
    app.include_router(cases.router)
    app.include_router(jobs.router)
    app.include_router(profile.router)
    app.include_router(creator_clone.router)
    app.include_router(local_helper.router)
    app.include_router(downloads.router)
    app.include_router(settings_routes.router)
    return app


app = create_app()
