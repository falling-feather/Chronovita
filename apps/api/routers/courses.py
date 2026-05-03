from fastapi import APIRouter, HTTPException, Query

from services import courses as courses_data

router = APIRouter()


@router.get("/eras")
async def eras():
    return {"items": [e.model_dump() for e in courses_data.list_eras()]}


@router.get("/")
async def index(
    era: str | None = Query(default=None),
    section: str | None = Query(default=None),
    q: str | None = Query(default=None),
):
    items = courses_data.list_courses(era_id=era, section=section, q=q)
    return {"items": [c.model_dump() for c in items], "total": len(items)}


@router.get("/{course_id}")
async def detail(course_id: str):
    c = courses_data.get_course(course_id)
    if not c:
        raise HTTPException(status_code=404, detail="课程不存在")
    return c.model_dump()


@router.get("/{course_id}/lessons/{lesson_id}")
async def lesson(course_id: str, lesson_id: str):
    l = courses_data.get_lesson(lesson_id)
    if not l or l.course_id != course_id:
        raise HTTPException(status_code=404, detail="课时不存在")
    return l.model_dump()
