from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from settings import settings
from services import content
from services.content import LessonContentPackage

router = APIRouter()


class SealRequest(BaseModel):
    sealed_by: str = "admin"


def require_admin(
    authorization: Annotated[str | None, Header()] = None,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> str:
    token = x_admin_token or _bearer_token(authorization)
    if not settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin token is not configured.",
        )
    if token != settings.admin_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin token required.")
    return "admin"


@router.get("/")
async def overview(_: str = Depends(require_admin)):
    return {
        "auth": "temporary-token",
        "content_root": str(content.content_root()),
        "drafts": len(content.list_drafts()),
        "sealed": len(content.list_sealed()),
        "endpoints": [
            "GET /api/v1/admin/content/template",
            "POST /api/v1/admin/content/drafts",
            "PUT /api/v1/admin/content/drafts/{lesson_id}",
            "POST /api/v1/admin/content/preview",
            "POST /api/v1/admin/content/drafts/{lesson_id}/seal",
        ],
    }


@router.get("/template")
async def template(_: str = Depends(require_admin)):
    return content.content_template().model_dump(mode="json")


@router.get("/drafts")
async def drafts(_: str = Depends(require_admin)):
    return {"items": [item.model_dump(mode="json") for item in content.list_drafts()]}


@router.get("/drafts/{lesson_id}")
async def draft_detail(lesson_id: str, _: str = Depends(require_admin)):
    draft = content.get_draft(lesson_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found.")
    return draft.model_dump(mode="json")


@router.post("/drafts")
async def create_or_update_draft(payload: LessonContentPackage, admin: str = Depends(require_admin)):
    saved = content.save_draft(payload, saved_by=admin)
    return {"item": saved.model_dump(mode="json")}


@router.put("/drafts/{lesson_id}")
async def update_draft(
    lesson_id: str,
    payload: LessonContentPackage,
    admin: str = Depends(require_admin),
):
    if payload.lesson_id != lesson_id:
        raise HTTPException(status_code=400, detail="Path lesson_id must match payload.lesson_id.")
    saved = content.save_draft(payload, saved_by=admin)
    return {"item": saved.model_dump(mode="json")}


@router.post("/preview")
async def preview(payload: LessonContentPackage, _: str = Depends(require_admin)):
    item = content.preview_package(payload)
    return {"item": item.model_dump(mode="json")}


@router.post("/drafts/{lesson_id}/seal")
async def seal_draft(
    lesson_id: str,
    req: SealRequest | None = None,
    _: str = Depends(require_admin),
):
    try:
        item, path = content.seal_draft(lesson_id, sealed_by=(req.sealed_by if req else "admin"))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Draft not found.") from None
    return {
        "item": item.model_dump(mode="json"),
        "record": content.record_for_package(item, path).model_dump(mode="json"),
    }


@router.get("/sealed")
async def sealed(_: str = Depends(require_admin)):
    return {"items": [item.model_dump(mode="json") for item in content.list_sealed()]}


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()
