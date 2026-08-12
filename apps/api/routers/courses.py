from typing import NoReturn

from fastapi import APIRouter, HTTPException, Query

from services.content import ContentIntegrityError
from services.content import workflow as content_workflow
from services import courses as courses_data

router = APIRouter()


@router.get("/eras")
async def eras():
    try:
        return {"items": [e.model_dump() for e in courses_data.list_eras()]}
    except ContentIntegrityError as exc:
        _raise_content_unavailable(exc)


@router.get("/")
async def index(
    era: str | None = Query(default=None),
    section: str | None = Query(default=None),
    q: str | None = Query(default=None),
):
    try:
        items = courses_data.list_courses(era_id=era, section=section, q=q)
    except ContentIntegrityError as exc:
        _raise_content_unavailable(exc)
    return {"items": [c.model_dump() for c in items], "total": len(items)}


@router.get("/{course_id}")
async def detail(course_id: str):
    try:
        c = courses_data.get_course(course_id)
    except ContentIntegrityError as exc:
        _raise_content_unavailable(exc)
    if not c:
        raise HTTPException(status_code=404, detail="课程不存在")
    return c.model_dump()


@router.get("/{course_id}/lessons/{lesson_id}")
async def lesson(course_id: str, lesson_id: str):
    try:
        l = courses_data.get_lesson(lesson_id)
    except ContentIntegrityError as exc:
        _raise_content_unavailable(exc)
    if not l or l.course_id != course_id:
        raise HTTPException(status_code=404, detail="课时不存在")
    return l.model_dump()


@router.get("/{course_id}/lessons/{lesson_id}/presentation")
async def lesson_presentation(course_id: str, lesson_id: str):
    """Return only the exact presentation bound by the active V3 release."""

    try:
        resources = content_workflow.get_published_lesson_resources(
            course_id,
            lesson_id,
        )
    except content_workflow.ContentNotFound as exc:
        raise HTTPException(status_code=404, detail="课时展示资源不存在") from exc
    except ContentIntegrityError as exc:
        _raise_content_unavailable(exc)
    return {
        "release_id": resources.release_id,
        "release_no": resources.release_no,
        "release_checksum": resources.release_checksum,
        "presentation": resources.lesson_presentation.model_dump(mode="json"),
    }


def _raise_content_unavailable(exc: ContentIntegrityError) -> NoReturn:
    raise HTTPException(
        status_code=503,
        detail={
            "code": "published_content_integrity_error",
            "message": "已发布课程完整性校验失败，请联系管理员检查发布清单。",
        },
    ) from exc
