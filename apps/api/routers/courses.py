from pathlib import Path
from typing import Literal, NoReturn

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from services import content
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
        "asset_urls": {
            asset: (
                f"/api/v1/courses/{course_id}/lessons/{lesson_id}"
                f"/presentation/assets/{asset}"
                f"?release_checksum={resources.release_checksum}"
            )
            for asset in ("video", "poster", "transcript")
        },
    }


@router.get("/{course_id}/lessons/{lesson_id}/presentation/assets/{asset}")
async def lesson_presentation_asset(
    course_id: str,
    lesson_id: str,
    asset: Literal["video", "poster", "transcript"],
    release_checksum: str = Query(min_length=64, max_length=64),
):
    """Serve only an immutable media file pinned by the active V3 release."""

    try:
        resources = content_workflow.get_published_lesson_resources(
            course_id,
            lesson_id,
        )
    except content_workflow.ContentNotFound as exc:
        raise HTTPException(status_code=404, detail="课时展示资源不存在") from exc
    except ContentIntegrityError as exc:
        _raise_content_unavailable(exc)
    if resources.release_checksum != release_checksum:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "presentation_release_changed",
                "message": "课程发布版本已更新，请重新载入课时。",
            },
        )

    presentation = resources.lesson_presentation
    relative_path, expected_sha256, media_type = {
        "video": (presentation.video_path, presentation.video_sha256, "video/mp4"),
        "poster": (presentation.poster_path, presentation.poster_sha256, "image/webp"),
        "transcript": (
            presentation.transcript_path,
            presentation.transcript_sha256,
            "text/markdown; charset=utf-8",
        ),
    }[asset]
    try:
        root = content.lesson_media_dir().resolve(strict=True)
        path = (content.content_root() / Path(relative_path)).resolve(strict=True)
        path.relative_to(root)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="课时展示资源文件不可用") from exc
    if not path.is_file():
        raise HTTPException(status_code=503, detail="课时展示资源文件不可用")
    return FileResponse(
        path,
        media_type=media_type,
        filename=path.name if asset == "transcript" else None,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": f'"{expected_sha256}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


def _raise_content_unavailable(exc: ContentIntegrityError) -> NoReturn:
    raise HTTPException(
        status_code=503,
        detail={
            "code": "published_content_integrity_error",
            "message": "已发布课程完整性校验失败，请联系管理员检查发布清单。",
        },
    ) from exc
