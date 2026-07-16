from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.errors import AppError
from app.providers.profile_base import ProfileScanRequest
from app.routes.common import error_response
from app.services.profile_scan import scan_profile


router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfileScanPayload(BaseModel):
    profile_url: str = ""
    sec_user_id: str = ""
    manual_links: str = ""
    structured_items: str = ""
    count: int = 20
    max_pages: int = 0
    sort_by: str = "like_count"


@router.post("/scan")
def scan_profile_endpoint(payload: ProfileScanPayload):
    try:
        result = scan_profile(
            ProfileScanRequest(
                profile_url=payload.profile_url,
                sec_user_id=payload.sec_user_id,
                manual_links=payload.manual_links,
                structured_items=payload.structured_items,
                count=payload.count,
                max_pages=payload.max_pages,
                sort_by=payload.sort_by,
            )
        )
        data = result.to_dict()
        return {"ok": True, **data, "sort_by": payload.sort_by}
    except AppError as error:
        return error_response(error)
