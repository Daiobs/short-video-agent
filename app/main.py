from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routes import cases, downloads, jobs, pages, profile, settings as settings_routes, videos


def create_app() -> FastAPI:
    settings.ensure_directories()
    init_db()
    app = FastAPI(
        title="short-video-agent",
        description="本地短视频爆款分析素材包生成器",
        version="0.1.0",
    )
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(pages.router)
    app.include_router(videos.router)
    app.include_router(cases.router)
    app.include_router(jobs.router)
    app.include_router(profile.router)
    app.include_router(downloads.router)
    app.include_router(settings_routes.router)
    return app


app = create_app()
