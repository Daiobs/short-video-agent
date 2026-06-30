from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.services.creator_clone import MAX_DISTILL_SAMPLES


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _static_version() -> str:
    paths = [
        Path("app/static/app.js"),
        Path("app/static/case_detail.js"),
        Path("app/static/calibration.js"),
        Path("app/static/app.css"),
    ]
    try:
        return str(max(path.stat().st_mtime_ns for path in paths))
    except OSError:
        return "dev"


@router.get("/")
def home(request: Request):
    response = templates.TemplateResponse(
        request,
        "index.html",
        {
            "static_version": _static_version(),
            "profile_build_max_items": settings.profile_build_max_items,
            "creator_clone_max_distill_samples": MAX_DISTILL_SAMPLES,
        },
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/cases/{case_id}")
def case_detail(request: Request, case_id: str):
    response = templates.TemplateResponse(
        request,
        "case_detail.html",
        {"case_id": case_id, "static_version": _static_version()},
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/calibration")
def calibration_records(request: Request):
    response = templates.TemplateResponse(
        request,
        "calibration.html",
        {"static_version": _static_version()},
    )
    response.headers["Cache-Control"] = "no-store"
    return response
