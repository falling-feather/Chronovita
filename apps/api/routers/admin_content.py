from __future__ import annotations

import secrets
from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from settings import settings
from services import content
from services import courses as courses_data
from services.content import KeywordProfilePackage, LessonContentPackage, PersonProfilePackage
from services.content import runtime_artifacts
from services.content import workflow as content_workflow
from services.contracts.v1 import ScenarioTemplateV1

router = APIRouter()


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ActorRequest(ApiModel):
    actor: str | None = Field(
        default=None,
        max_length=80,
        description="Optional display label; audit identity comes from authentication.",
    )
    note: str = Field(default="", max_length=2000)


class SealRequest(ApiModel):
    sealed_by: str | None = Field(
        default=None,
        max_length=80,
        description="Legacy display label; audit identity comes from authentication.",
    )


class ReviewRequest(ActorRequest):
    decision: Literal["approve", "changes_requested"]


class RollbackRequest(ActorRequest):
    target_release_id: str | None = None


class LegacyBootstrapRequest(ActorRequest):
    selections: list[content_workflow.LegacyReleaseSelection] = Field(min_length=1)


class PublishRequest(ActorRequest):
    scenarios: list[content_workflow.ScenarioReleaseSelection] | None = Field(
        default=None,
        description=(
            "Omit or use null to preserve current bindings; use [] to remove all; "
            "provide an explicit list to replace them."
        ),
    )


class WorkflowResponse(ApiModel):
    workflow: content_workflow.ContentWorkflowRecord
    report: content_workflow.ContentValidationReport | None = None


class ReleaseResponse(ApiModel):
    release: content_workflow.CourseReleaseManifestAny
    workflow: content_workflow.ContentWorkflowRecord | None = None


class ReleaseListResponse(ApiModel):
    items: list[content_workflow.CourseReleaseManifestAny]


class LessonSourceRecord(ApiModel):
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
    if token is None or not secrets.compare_digest(token, settings.admin_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin token required.")
    return settings.admin_actor


@router.get("/")
async def overview(_: str = Depends(require_admin)):
    try:
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
                "POST /api/v1/admin/content/drafts/{lesson_id}/validate",
                "POST /api/v1/admin/content/drafts/{lesson_id}/submit-review",
                "POST /api/v1/admin/content/drafts/{lesson_id}/review",
                "POST /api/v1/admin/content/drafts/{lesson_id}/seal",
                "GET /api/v1/admin/content/runtime-scenarios",
                "POST /api/v1/admin/content/runtime-scenarios",
                "POST /api/v1/admin/content/sealed/{lesson_id}/versions/{version}/publish",
                "POST /api/v1/admin/content/releases/{course_id}/bootstrap-legacy",
                "POST /api/v1/admin/content/releases/{course_id}/rollback",
                "GET /api/v1/admin/content/assets",
                "POST /api/v1/admin/content/assets/people",
                "POST /api/v1/admin/content/assets/keywords",
            ],
        }
    except Exception as exc:
        _raise_content_error(exc)


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
    lesson = courses_data.get_builtin_lesson(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Source lesson not found.")
    return _lesson_to_content_package(lesson).model_dump(mode="json")


@router.get("/drafts")
async def drafts(_: str = Depends(require_admin)):
    try:
        return {"items": [item.model_dump(mode="json") for item in content.list_drafts()]}
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/drafts/{lesson_id}")
async def draft_detail(lesson_id: str, _: str = Depends(require_admin)):
    try:
        draft = content.get_draft(lesson_id)
        if draft is None:
            raise content_workflow.ContentNotFound(f"Draft not found: {lesson_id}")
        return draft.model_dump(mode="json")
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/drafts/{lesson_id}/workflow", response_model=WorkflowResponse)
async def draft_workflow(lesson_id: str, _: str = Depends(require_admin)):
    try:
        workflow = content_workflow.get_workflow(lesson_id)
        if workflow is None:
            raise content_workflow.ContentNotFound(f"Workflow not found: {lesson_id}")
        return WorkflowResponse(workflow=workflow, report=workflow.validation)
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/drafts")
async def create_or_update_draft(payload: LessonContentPackage, admin: str = Depends(require_admin)):
    try:
        saved = content.save_draft(payload, saved_by=admin)
        workflow = content_workflow.get_workflow(saved.lesson_id)
        return {
            "item": saved.model_dump(mode="json"),
            "workflow": workflow.model_dump(mode="json") if workflow else None,
        }
    except Exception as exc:
        _raise_content_error(exc)


@router.put("/drafts/{lesson_id}")
async def update_draft(
    lesson_id: str,
    payload: LessonContentPackage,
    admin: str = Depends(require_admin),
):
    if payload.lesson_id != lesson_id:
        raise HTTPException(status_code=400, detail="Path lesson_id must match payload.lesson_id.")
    try:
        saved = content.save_draft(payload, saved_by=admin)
        workflow = content_workflow.get_workflow(saved.lesson_id)
        return {
            "item": saved.model_dump(mode="json"),
            "workflow": workflow.model_dump(mode="json") if workflow else None,
        }
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/preview")
async def preview(payload: LessonContentPackage, _: str = Depends(require_admin)):
    item = content.preview_package(payload)
    return {"item": item.model_dump(mode="json")}


@router.post("/drafts/{lesson_id}/validate", response_model=WorkflowResponse)
async def validate_draft(
    lesson_id: str,
    req: ActorRequest | None = None,
    admin: str = Depends(require_admin),
):
    try:
        workflow = content_workflow.validate_draft(
            lesson_id,
            actor=admin,
        )
        return WorkflowResponse(workflow=workflow, report=workflow.validation)
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/drafts/{lesson_id}/submit-review", response_model=WorkflowResponse)
async def submit_review(
    lesson_id: str,
    req: ActorRequest | None = None,
    admin: str = Depends(require_admin),
):
    try:
        workflow = content_workflow.submit_for_review(
            lesson_id,
            actor=admin,
            note=(req.note if req else ""),
        )
        return WorkflowResponse(workflow=workflow, report=workflow.validation)
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/drafts/{lesson_id}/review", response_model=WorkflowResponse)
async def review_draft(
    lesson_id: str,
    req: ReviewRequest,
    admin: str = Depends(require_admin),
):
    try:
        if req.decision == "approve":
            workflow = content_workflow.approve_draft(
                lesson_id,
                actor=admin,
                note=req.note,
            )
        else:
            workflow = content_workflow.request_changes(
                lesson_id,
                actor=admin,
                note=req.note,
            )
        return WorkflowResponse(workflow=workflow, report=workflow.validation)
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/drafts/{lesson_id}/seal")
async def seal_draft(
    lesson_id: str,
    req: SealRequest | None = None,
    admin: str = Depends(require_admin),
):
    try:
        item, path, workflow = content_workflow.seal_approved_draft(
            lesson_id,
            actor=admin,
        )
    except Exception as exc:
        _raise_content_error(exc)
    return {
        "item": item.model_dump(mode="json"),
        "record": content.record_for_package(item, path).model_dump(mode="json"),
        "workflow": workflow.model_dump(mode="json"),
    }


@router.get("/sealed")
async def sealed(_: str = Depends(require_admin)):
    try:
        return {"items": [item.model_dump(mode="json") for item in content.list_sealed()]}
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/runtime-scenarios")
async def runtime_scenarios(_: str = Depends(require_admin)):
    try:
        return {
            "items": [
                item.model_dump(mode="json")
                for item in runtime_artifacts.list_staged_scenarios()
            ]
        }
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/runtime-scenarios")
async def stage_runtime_scenario(
    payload: ScenarioTemplateV1,
    _: str = Depends(require_admin),
):
    try:
        with content_workflow.workflow_write_lock():
            item = runtime_artifacts.stage_scenario(payload)
        return {"item": item.model_dump(mode="json")}
    except Exception as exc:
        _raise_content_error(exc)


@router.post(
    "/sealed/{lesson_id}/versions/{version}/publish",
    response_model=ReleaseResponse,
)
async def publish_version(
    lesson_id: str,
    version: int,
    req: PublishRequest | None = None,
    admin: str = Depends(require_admin),
):
    try:
        release, workflow = content_workflow.publish_version(
            lesson_id,
            version,
            actor=admin,
            note=(req.note if req else ""),
            scenario_selections=(req.scenarios if req else None),
        )
        return ReleaseResponse(release=release, workflow=workflow)
    except Exception as exc:
        _raise_content_error(exc)


@router.post(
    "/releases/{course_id}/bootstrap-legacy",
    response_model=ReleaseResponse,
)
async def bootstrap_legacy_release(
    course_id: str,
    req: LegacyBootstrapRequest,
    admin: str = Depends(require_admin),
):
    try:
        release = content_workflow.bootstrap_legacy_release(
            course_id,
            req.selections,
            actor=admin,
            note=req.note,
        )
        return ReleaseResponse(release=release)
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/releases", response_model=ReleaseListResponse)
async def releases(
    course_id: str | None = None,
    _: str = Depends(require_admin),
):
    try:
        return ReleaseListResponse(items=content_workflow.list_releases(course_id))
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/releases/{course_id}/current", response_model=ReleaseResponse)
async def current_release(course_id: str, _: str = Depends(require_admin)):
    try:
        release = content_workflow.get_current_release(course_id)
        if release is None:
            raise content_workflow.ContentNotFound(f"No active release for course {course_id}.")
        return ReleaseResponse(release=release)
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/releases/{course_id}/{release_id}", response_model=ReleaseResponse)
async def release_detail(
    course_id: str,
    release_id: str,
    _: str = Depends(require_admin),
):
    try:
        return ReleaseResponse(release=content_workflow.get_release(course_id, release_id))
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/releases/{course_id}/rollback", response_model=ReleaseResponse)
async def rollback_release(
    course_id: str,
    req: RollbackRequest | None = None,
    admin: str = Depends(require_admin),
):
    try:
        release = content_workflow.rollback_release(
            course_id,
            actor=admin,
            target_release_id=(req.target_release_id if req else None),
            note=(req.note if req else ""),
        )
        return ReleaseResponse(release=release)
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/assets")
async def assets(
    kind: Literal["person", "keyword"] | None = None,
    _: str = Depends(require_admin),
):
    try:
        return {"items": [item.model_dump(mode="json") for item in content.list_assets(kind)]}
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/assets/people/template")
async def person_template(_: str = Depends(require_admin)):
    return content.person_template().model_dump(mode="json")


@router.get("/assets/people/{asset_id}")
async def person_detail(asset_id: str, _: str = Depends(require_admin)):
    try:
        item = content.get_person_profile(asset_id)
        if item is None:
            raise content_workflow.ContentNotFound("Person profile not found.")
        return item.model_dump(mode="json")
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/assets/people")
async def save_person(payload: PersonProfilePackage, _: str = Depends(require_admin)):
    try:
        saved = content.save_person_profile(payload)
        return {"item": saved.model_dump(mode="json")}
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/assets/keywords/template")
async def keyword_template(_: str = Depends(require_admin)):
    return content.keyword_template().model_dump(mode="json")


@router.get("/assets/keywords/{asset_id}")
async def keyword_detail(asset_id: str, _: str = Depends(require_admin)):
    try:
        item = content.get_keyword_profile(asset_id)
        if item is None:
            raise content_workflow.ContentNotFound("Keyword profile not found.")
        return item.model_dump(mode="json")
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/assets/keywords")
async def save_keyword(payload: KeywordProfilePackage, _: str = Depends(require_admin)):
    try:
        saved = content.save_keyword_profile(payload)
        return {"item": saved.model_dump(mode="json")}
    except Exception as exc:
        _raise_content_error(exc)


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def _raise_content_error(exc: Exception) -> NoReturn:
    detail: dict[str, object] = {
        "code": getattr(exc, "code", "content_operation_failed"),
        "message": str(exc),
    }
    if isinstance(exc, FileNotFoundError):
        detail["code"] = "content_not_found"
    elif isinstance(exc, FileExistsError):
        detail["code"] = "content_conflict"
    elif isinstance(exc, ValueError) and not isinstance(
        exc,
        content_workflow.ContentWorkflowError,
    ):
        detail["code"] = "content_validation_failed"
    if isinstance(exc, content_workflow.ContentValidationFailed) and exc.report is not None:
        detail["issues"] = [
            issue.model_dump(mode="json")
            for issue in exc.report.issues
        ]
    if isinstance(exc, (content_workflow.ContentNotFound, FileNotFoundError)):
        raise HTTPException(status_code=404, detail=detail) from exc
    if isinstance(
        exc,
        (
            content_workflow.ContentConflict,
            content_workflow.InvalidTransition,
            FileExistsError,
        ),
    ):
        raise HTTPException(status_code=409, detail=detail) from exc
    if isinstance(exc, (content_workflow.ContentValidationFailed, ValueError)):
        raise HTTPException(status_code=422, detail=detail) from exc
    if isinstance(exc, (content.ContentIntegrityError, OSError)):
        detail["code"] = "content_integrity_error"
        raise HTTPException(status_code=503, detail=detail) from exc
    raise exc


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
