from __future__ import annotations

from fastapi import APIRouter

from app.routes.common import not_implemented_response


router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.post("/scan")
def scan_profile_placeholder():
    return not_implemented_response()

