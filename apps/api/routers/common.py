from fastapi import APIRouter

router = APIRouter()


@router.get("/courses")
async def list_courses():
    return {"items": []}


@router.get("/courses/{course_id}/chapters")
async def list_chapters(course_id: str):
    return {"course_id": course_id, "items": []}


@router.get("/users/me")
async def current_user():
    return {"id": "anonymous", "name": "访客", "role": "student"}
