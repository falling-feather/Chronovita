from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from settings import settings
from services import content
from services import courses as courses_data
from services.content import KeywordProfilePackage, LessonContentPackage, PersonProfilePackage

router = APIRouter()


class SealRequest(BaseModel):
    sealed_by: str = "admin"


class LessonSourceRecord(BaseModel):
    lesson_id: str
    course_id: str
    course_title: str = ""
    title: str
    lesson_no: str = ""
    era_id: str = ""
    era: str = ""
    source: str = "builtin"


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
            "GET /api/v1/admin/content/source-lessons",
            "GET /api/v1/admin/content/source-lessons/{lesson_id}",
            "POST /api/v1/admin/content/drafts",
            "PUT /api/v1/admin/content/drafts/{lesson_id}",
            "POST /api/v1/admin/content/preview",
            "POST /api/v1/admin/content/drafts/{lesson_id}/seal",
            "GET /api/v1/admin/content/assets",
            "POST /api/v1/admin/content/assets/people",
            "POST /api/v1/admin/content/assets/keywords",
        ],
    }


@router.get("/template")
async def template(_: str = Depends(require_admin)):
    return content.content_template().model_dump(mode="json")


@router.get("/source-lessons")
async def source_lessons(_: str = Depends(require_admin)):
    return {
        "items": [
            _source_record(lesson).model_dump(mode="json")
            for lesson in courses_data.list_builtin_lessons()
        ]
    }


@router.get("/source-lessons/{lesson_id}")
async def source_lesson_detail(lesson_id: str, _: str = Depends(require_admin)):
    lesson = courses_data.get_lesson(lesson_id)
    if lesson is None or lesson.content_status != "builtin":
        raise HTTPException(status_code=404, detail="Source lesson not found.")
    return _lesson_to_content_package(lesson).model_dump(mode="json")


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


@router.get("/assets")
async def assets(
    kind: Literal["person", "keyword"] | None = None,
    _: str = Depends(require_admin),
):
    return {"items": [item.model_dump(mode="json") for item in content.list_assets(kind)]}


@router.get("/assets/people/template")
async def person_template(_: str = Depends(require_admin)):
    return content.person_template().model_dump(mode="json")


@router.get("/assets/people/{asset_id}")
async def person_detail(asset_id: str, _: str = Depends(require_admin)):
    item = content.get_person_profile(asset_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Person profile not found.")
    return item.model_dump(mode="json")


@router.post("/assets/people")
async def save_person(payload: PersonProfilePackage, _: str = Depends(require_admin)):
    saved = content.save_person_profile(payload)
    return {"item": saved.model_dump(mode="json")}


@router.get("/assets/keywords/template")
async def keyword_template(_: str = Depends(require_admin)):
    return content.keyword_template().model_dump(mode="json")


@router.get("/assets/keywords/{asset_id}")
async def keyword_detail(asset_id: str, _: str = Depends(require_admin)):
    item = content.get_keyword_profile(asset_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Keyword profile not found.")
    return item.model_dump(mode="json")


@router.post("/assets/keywords")
async def save_keyword(payload: KeywordProfilePackage, _: str = Depends(require_admin)):
    saved = content.save_keyword_profile(payload)
    return {"item": saved.model_dump(mode="json")}


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def _source_record(lesson: courses_data.Lesson) -> LessonSourceRecord:
    course = courses_data.course_summary_for_lesson(lesson)
    era = _era_name(course.era_id if course else "")
    return LessonSourceRecord(
        lesson_id=lesson.id,
        course_id=lesson.course_id,
        course_title=course.title if course else lesson.course_id,
        title=lesson.title,
        lesson_no=lesson.num,
        era_id=course.era_id if course else "",
        era=era or lesson.era,
    )


def _lesson_to_content_package(lesson: courses_data.Lesson) -> LessonContentPackage:
    source = _source_record(lesson)
    return LessonContentPackage(
        lesson_id=lesson.id,
        course_id=lesson.course_id,
        course_title=source.course_title,
        title=lesson.title,
        unit=source.course_title,
        era=source.era or lesson.era or source.era_id,
        era_id=source.era_id or "content",
        section=courses_data.course_summary_for_lesson(lesson).section if courses_data.course_summary_for_lesson(lesson) else "已实装课程",
        lesson_no=lesson.num,
        duration=lesson.duration,
        abstract=lesson.abstract,
        body=lesson.body,
        keywords=[
            content.KeywordCard(word=item.word, pinyin=item.pinyin, gloss=item.gloss)
            for item in lesson.keywords
        ],
        people=[
            content.PersonCard(name=name, role="", summary=f"{name} 与本课相关，待教师补充人物档案。")
            for name in lesson.figures
        ],
        map_points=[content.MapPoint.model_validate(item) for item in lesson.map_points],
        source_refs=[content.SourceRef.model_validate(item) for item in lesson.source_refs],
        facts=lesson.facts,
        qa_points=lesson.qa_points,
        level_goals=lesson.level_goals,
        saga_material=content.MaterialPlaceholder.model_validate(lesson.saga_material or {}),
        sandbox_material=content.MaterialPlaceholder.model_validate(lesson.sandbox_material or {}),
        seed_canvas=[content.SeedCanvasNode.model_validate(item) for item in lesson.seed_canvas],
        teacher_notes=f"从已实装课程 {lesson.id} 导入，供教师二次修订。",
    )


def _era_name(era_id: str) -> str:
    for era in courses_data.list_eras():
        if era.id == era_id:
            return era.name
    return era_id
