from __future__ import annotations

from typing import Annotated, Literal, NoReturn
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from auth_dependencies import (
    AuthContext,
    audit_authorized_action,
    require_permission,
    trusted_actor,
)
from settings import secret_value, settings
from services import content
from services import courses as courses_data
from services.content import KeywordProfilePackage, LessonContentPackage, PersonProfilePackage
from services.content import runtime_artifacts
from services.content import evidence_workflow
from services.content import scenario_authoring
from services.content import workflow as content_workflow
from services.content_history import (
    ArchiveBuildError,
    CoursePublicationService,
    PublicationArchiveChanged,
    PublicationConfigurationError,
    PublicationConflict,
    PublicationDisabled,
    PublicationNotFound,
    PublicationRetryRejected,
    PublicationStore,
    PublicationStoreError,
    archive_download_filename,
    build_course_archive,
    build_course_archive_zip,
    load_repository_binding,
)
from services.content_history.asset_archive import (
    ContentAssetArchiveBuildError,
    ContentAssetArchiveChanged,
    build_content_asset_archive,
    build_content_asset_archive_zip,
    content_asset_archive_download_filename,
)
from services.content_history.asset_service import ContentAssetPublicationService
from services.content_history.github import GitHubGitDataClient
from services.contracts.archive_v1 import (
    ContentAssetArchiveManifestV1,
    ContentAssetArchivePublishRequestV1,
    ContentAssetKind,
    CourseArchiveManifestV1,
    CourseArchivePublishRequestV1,
    GitPublicationRecordV1,
    PublicationStatus,
)
from services.contracts.v1 import ScenarioTemplateV1
from services.contracts.evidence_v1 import LessonPresentationV1

router = APIRouter()

ContentReader = Annotated[AuthContext, Depends(require_permission("content.read"))]
ContentAuthor = Annotated[AuthContext, Depends(require_permission("content.author"))]
ContentReviewer = Annotated[AuthContext, Depends(require_permission("content.review"))]
ContentPublisher = Annotated[AuthContext, Depends(require_permission("content.publish"))]


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
    evidence: content_workflow.EvidenceReleaseSelection | None = None
    presentation: content_workflow.PresentationReleaseSelection | None = None


class EvidenceReviewRequest(ActorRequest):
    decision: Literal["approve", "changes_requested"]


class EvidenceWorkflowResponse(ApiModel):
    workflow: evidence_workflow.EvidenceWorkflowRecordV1
    report: evidence_workflow.EvidenceValidationReportV1 | None = None


class WorkflowResponse(ApiModel):
    workflow: content_workflow.ContentWorkflowRecord
    report: content_workflow.ContentValidationReport | None = None


class ReleaseResponse(ApiModel):
    release: content_workflow.CourseReleaseManifestAny
    workflow: content_workflow.ContentWorkflowRecord | None = None


class ReleaseListResponse(ApiModel):
    items: list[content_workflow.CourseReleaseManifestAny]


class ArchivePreviewResponse(ApiModel):
    archive: CourseArchiveManifestV1
    download_url: str


class ContentAssetArchivePreviewResponse(ApiModel):
    archive: ContentAssetArchiveManifestV1
    download_url: str


class PublicationResponse(ApiModel):
    publication: GitPublicationRecordV1
    reused: bool = False


class PublicationListResponse(ApiModel):
    items: list[GitPublicationRecordV1]


class PublicationRetryRequest(ApiModel):
    expected_revision: int | None = Field(default=None, ge=0)


class LessonSourceRecord(ApiModel):
    lesson_id: str
    course_id: str
    course_title: str = ""
    title: str
    lesson_no: str = ""
    era_id: str = ""
    era: str = ""
    source: str = "builtin"


@router.get("/")
async def overview(context: ContentReader):
    try:
        return {
            "auth": "legacy-local" if context.principal.synthetic else "accounts",
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
                "GET /api/v1/admin/content/evidence-drafts",
                "POST /api/v1/admin/content/evidence-drafts",
                "PUT /api/v1/admin/content/evidence-drafts/{corpus_id}",
                "POST /api/v1/admin/content/evidence-drafts/{corpus_id}/validate",
                "POST /api/v1/admin/content/evidence-drafts/{corpus_id}/submit-review",
                "POST /api/v1/admin/content/evidence-drafts/{corpus_id}/review",
                "POST /api/v1/admin/content/evidence-drafts/{corpus_id}/seal",
                "GET /api/v1/admin/content/runtime-evidence",
                "POST /api/v1/admin/content/lesson-presentations",
                "GET /api/v1/admin/content/lesson-presentations",
                "GET /api/v1/admin/content/runtime-scenarios",
                "GET /api/v1/admin/content/runtime-scenarios/{scenario_id}/versions/{scenario_version}",
                "GET /api/v1/admin/content/runtime-scenarios/{scenario_id}/versions/{scenario_version}/file",
                "POST /api/v1/admin/content/runtime-scenarios",
                "GET /api/v1/admin/content/scenario-drafts/template",
                "GET /api/v1/admin/content/scenario-drafts",
                "GET /api/v1/admin/content/scenario-drafts/{scenario_id}",
                "POST /api/v1/admin/content/scenario-drafts",
                "PUT /api/v1/admin/content/scenario-drafts/{scenario_id}",
                "POST /api/v1/admin/content/scenario-drafts/{scenario_id}/validate",
                "POST /api/v1/admin/content/scenario-drafts/{scenario_id}/seal",
                "POST /api/v1/admin/content/sealed/{lesson_id}/versions/{version}/publish",
                "POST /api/v1/admin/content/releases/{course_id}/bootstrap-legacy",
                "POST /api/v1/admin/content/releases/{course_id}/{release_id}/archive-preview",
                "GET /api/v1/admin/content/releases/{course_id}/{release_id}/archive.zip",
                "POST /api/v1/admin/content/publications",
                "GET /api/v1/admin/content/publications",
                "GET /api/v1/admin/content/publications/{publication_id}",
                "POST /api/v1/admin/content/publications/{publication_id}/retry",
                "POST /api/v1/admin/content/asset-archives/{asset_kind}/{asset_id}/versions/{version}/preview",
                "GET /api/v1/admin/content/asset-archives/{asset_kind}/{asset_id}/versions/{version}/archive.zip",
                "POST /api/v1/admin/content/asset-publications",
                "GET /api/v1/admin/content/asset-publications",
                "GET /api/v1/admin/content/asset-publications/{publication_id}",
                "POST /api/v1/admin/content/asset-publications/{publication_id}/retry",
                "POST /api/v1/admin/content/releases/{course_id}/rollback",
                "GET /api/v1/admin/content/assets",
                "POST /api/v1/admin/content/assets/people",
                "POST /api/v1/admin/content/assets/people/{asset_id}/validate",
                "POST /api/v1/admin/content/assets/people/{asset_id}/seal",
                "POST /api/v1/admin/content/assets/keywords",
                "POST /api/v1/admin/content/assets/keywords/{asset_id}/validate",
                "POST /api/v1/admin/content/assets/keywords/{asset_id}/seal",
            ],
        }
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/template")
async def template(_: ContentReader):
    return content.content_template().model_dump(mode="json")


@router.get("/source-lessons")
async def source_lessons(_: ContentReader):
    return {
        "items": [
            _source_record(lesson).model_dump(mode="json")
            for lesson in courses_data.list_builtin_lessons()
        ]
    }


@router.get("/source-lessons/{lesson_id}")
async def source_lesson_detail(lesson_id: str, _: ContentReader):
    lesson = courses_data.get_builtin_lesson(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Source lesson not found.")
    return _lesson_to_content_package(lesson).model_dump(mode="json")


@router.get("/drafts")
async def drafts(_: ContentReader):
    try:
        return {"items": [item.model_dump(mode="json") for item in content.list_drafts()]}
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/drafts/{lesson_id}")
async def draft_detail(lesson_id: str, _: ContentReader):
    try:
        draft = content.get_draft(lesson_id)
        if draft is None:
            raise content_workflow.ContentNotFound(f"Draft not found: {lesson_id}")
        return draft.model_dump(mode="json")
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/drafts/{lesson_id}/workflow", response_model=WorkflowResponse)
async def draft_workflow(lesson_id: str, _: ContentReader):
    try:
        workflow = content_workflow.get_workflow(lesson_id)
        if workflow is None:
            raise content_workflow.ContentNotFound(f"Workflow not found: {lesson_id}")
        return WorkflowResponse(workflow=workflow, report=workflow.validation)
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/drafts")
async def create_or_update_draft(
    payload: LessonContentPackage,
    request: Request,
    context: ContentAuthor,
):
    try:
        with content_workflow.workflow_write_lock():
            _require_lesson_author(context, payload.lesson_id, allow_missing=True)
            _audit_content_write(
                request,
                context,
                permission="content.author",
                action="content.draft.save.authorize",
                resource_type="lesson-draft",
                resource_id=payload.lesson_id,
            )
            saved = content.save_draft(payload, saved_by=trusted_actor(context))
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
    request: Request,
    context: ContentAuthor,
):
    if payload.lesson_id != lesson_id:
        raise HTTPException(status_code=400, detail="Path lesson_id must match payload.lesson_id.")
    try:
        with content_workflow.workflow_write_lock():
            _require_lesson_author(context, lesson_id)
            _audit_content_write(
                request,
                context,
                permission="content.author",
                action="content.draft.save.authorize",
                resource_type="lesson-draft",
                resource_id=lesson_id,
            )
            saved = content.save_draft(payload, saved_by=trusted_actor(context))
        workflow = content_workflow.get_workflow(saved.lesson_id)
        return {
            "item": saved.model_dump(mode="json"),
            "workflow": workflow.model_dump(mode="json") if workflow else None,
        }
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/preview")
async def preview(payload: LessonContentPackage, _: ContentReader):
    item = content.preview_package(payload)
    return {"item": item.model_dump(mode="json")}


@router.post("/drafts/{lesson_id}/validate", response_model=WorkflowResponse)
async def validate_draft(
    lesson_id: str,
    request: Request,
    context: ContentAuthor,
    req: ActorRequest | None = None,
):
    try:
        _require_lesson_author(context, lesson_id)
        _audit_content_write(
            request,
            context,
            permission="content.author",
            action="content.draft.validate.authorize",
            resource_type="lesson-draft",
            resource_id=lesson_id,
        )
        workflow = content_workflow.validate_draft(
            lesson_id,
            actor=trusted_actor(context),
        )
        return WorkflowResponse(workflow=workflow, report=workflow.validation)
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/drafts/{lesson_id}/submit-review", response_model=WorkflowResponse)
async def submit_review(
    lesson_id: str,
    request: Request,
    context: ContentAuthor,
    req: ActorRequest | None = None,
):
    try:
        _require_lesson_author(context, lesson_id)
        _audit_content_write(
            request,
            context,
            permission="content.author",
            action="content.draft.submit_review.authorize",
            resource_type="lesson-draft",
            resource_id=lesson_id,
        )
        workflow = content_workflow.submit_for_review(
            lesson_id,
            actor=trusted_actor(context),
            note=(req.note if req else ""),
        )
        return WorkflowResponse(workflow=workflow, report=workflow.validation)
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/drafts/{lesson_id}/review", response_model=WorkflowResponse)
async def review_draft(
    lesson_id: str,
    req: ReviewRequest,
    request: Request,
    context: ContentReviewer,
):
    try:
        _require_independent_reviewer(context, lesson_id)
        action = (
            "content.draft.approve.authorize"
            if req.decision == "approve"
            else "content.draft.request_changes.authorize"
        )
        _audit_content_write(
            request,
            context,
            permission="content.review",
            action=action,
            resource_type="lesson-draft",
            resource_id=lesson_id,
            details={"decision": req.decision},
        )
        if req.decision == "approve":
            workflow = content_workflow.approve_draft(
                lesson_id,
                actor=trusted_actor(context),
                note=req.note,
            )
        else:
            workflow = content_workflow.request_changes(
                lesson_id,
                actor=trusted_actor(context),
                note=req.note,
            )
        return WorkflowResponse(workflow=workflow, report=workflow.validation)
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/drafts/{lesson_id}/seal")
async def seal_draft(
    lesson_id: str,
    request: Request,
    context: ContentPublisher,
    req: SealRequest | None = None,
):
    try:
        _audit_content_write(
            request,
            context,
            permission="content.publish",
            action="content.draft.seal.authorize",
            resource_type="lesson-draft",
            resource_id=lesson_id,
        )
        item, path, workflow = content_workflow.seal_approved_draft(
            lesson_id,
            actor=trusted_actor(context),
        )
    except Exception as exc:
        _raise_content_error(exc)
    return {
        "item": item.model_dump(mode="json"),
        "record": content.record_for_package(item, path).model_dump(mode="json"),
        "workflow": workflow.model_dump(mode="json"),
    }


@router.get("/sealed")
async def sealed(_: ContentReader):
    try:
        return {"items": [item.model_dump(mode="json") for item in content.list_sealed()]}
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/evidence-drafts")
async def evidence_drafts(_: ContentReader):
    try:
        return {
            "items": [
                item.model_dump(mode="json")
                for item in evidence_workflow.list_evidence_drafts()
            ]
        }
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/evidence-drafts/{corpus_id}")
async def evidence_draft_detail(corpus_id: str, _: ContentReader):
    try:
        item = evidence_workflow.get_evidence_draft(corpus_id)
        if item is None:
            raise evidence_workflow.EvidenceDraftNotFound(
                f"Evidence draft not found: {corpus_id}"
            )
        record = evidence_workflow.get_evidence_workflow(corpus_id)
        return {
            "item": item.model_dump(mode="json"),
            "workflow": record.model_dump(mode="json") if record else None,
        }
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/evidence-drafts")
async def save_evidence_draft(
    payload: evidence_workflow.EvidenceCorpusDraftV1,
    request: Request,
    context: ContentAuthor,
):
    try:
        with content_workflow.workflow_write_lock():
            _require_evidence_author(
                context,
                payload.corpus_id,
                allow_missing=True,
            )
            _audit_content_write(
                request,
                context,
                permission="content.author",
                action="content.evidence_draft.save.authorize",
                resource_type="evidence-draft",
                resource_id=payload.corpus_id,
            )
            item, record = evidence_workflow.save_evidence_draft(
                payload,
                saved_by=trusted_actor(context),
            )
        return {
            "item": item.model_dump(mode="json"),
            "workflow": record.model_dump(mode="json"),
        }
    except Exception as exc:
        _raise_content_error(exc)


@router.put("/evidence-drafts/{corpus_id}")
async def update_evidence_draft(
    corpus_id: str,
    payload: evidence_workflow.EvidenceCorpusDraftV1,
    request: Request,
    context: ContentAuthor,
):
    if payload.corpus_id != corpus_id:
        raise HTTPException(
            status_code=400,
            detail="Path corpus_id must match payload.corpus_id.",
        )
    try:
        with content_workflow.workflow_write_lock():
            _require_evidence_author(context, corpus_id)
            _audit_content_write(
                request,
                context,
                permission="content.author",
                action="content.evidence_draft.save.authorize",
                resource_type="evidence-draft",
                resource_id=corpus_id,
            )
            item, record = evidence_workflow.save_evidence_draft(
                payload,
                saved_by=trusted_actor(context),
            )
        return {
            "item": item.model_dump(mode="json"),
            "workflow": record.model_dump(mode="json"),
        }
    except Exception as exc:
        _raise_content_error(exc)


@router.post(
    "/evidence-drafts/{corpus_id}/validate",
    response_model=EvidenceWorkflowResponse,
)
async def validate_evidence_draft(
    corpus_id: str,
    request: Request,
    context: ContentAuthor,
):
    try:
        _require_evidence_author(context, corpus_id)
        _audit_content_write(
            request,
            context,
            permission="content.author",
            action="content.evidence_draft.validate.authorize",
            resource_type="evidence-draft",
            resource_id=corpus_id,
        )
        record, report = evidence_workflow.validate_evidence_draft(
            corpus_id,
            actor=trusted_actor(context),
        )
        return EvidenceWorkflowResponse(workflow=record, report=report)
    except Exception as exc:
        _raise_content_error(exc)


@router.post(
    "/evidence-drafts/{corpus_id}/submit-review",
    response_model=EvidenceWorkflowResponse,
)
async def submit_evidence_review(
    corpus_id: str,
    request: Request,
    context: ContentAuthor,
    req: ActorRequest | None = None,
):
    try:
        _require_evidence_author(context, corpus_id)
        _audit_content_write(
            request,
            context,
            permission="content.author",
            action="content.evidence_draft.submit_review.authorize",
            resource_type="evidence-draft",
            resource_id=corpus_id,
        )
        record = evidence_workflow.submit_evidence_for_review(
            corpus_id,
            actor=trusted_actor(context),
            note=(req.note if req else ""),
        )
        return EvidenceWorkflowResponse(
            workflow=record,
            report=record.validation,
        )
    except Exception as exc:
        _raise_content_error(exc)


@router.post(
    "/evidence-drafts/{corpus_id}/review",
    response_model=EvidenceWorkflowResponse,
)
async def review_evidence_draft(
    corpus_id: str,
    req: EvidenceReviewRequest,
    request: Request,
    context: ContentReviewer,
):
    try:
        _require_independent_evidence_reviewer(context, corpus_id)
        _audit_content_write(
            request,
            context,
            permission="content.review",
            action=(
                "content.evidence_draft.approve.authorize"
                if req.decision == "approve"
                else "content.evidence_draft.request_changes.authorize"
            ),
            resource_type="evidence-draft",
            resource_id=corpus_id,
            details={"decision": req.decision},
        )
        record = evidence_workflow.review_evidence_draft(
            corpus_id,
            actor=trusted_actor(context),
            decision=req.decision,
            note=req.note,
        )
        return EvidenceWorkflowResponse(
            workflow=record,
            report=record.validation,
        )
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/evidence-drafts/{corpus_id}/seal")
async def seal_evidence_draft(
    corpus_id: str,
    request: Request,
    context: ContentPublisher,
):
    try:
        _audit_content_write(
            request,
            context,
            permission="content.publish",
            action="content.evidence_draft.seal.authorize",
            resource_type="evidence-draft",
            resource_id=corpus_id,
        )
        corpus, record, workflow_record, idempotent = (
            evidence_workflow.seal_approved_evidence(
                corpus_id,
                actor=trusted_actor(context),
            )
        )
        return {
            "item": corpus.model_dump(mode="json"),
            "record": record.model_dump(mode="json"),
            "workflow": workflow_record.model_dump(mode="json"),
            "idempotent": idempotent,
        }
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/runtime-evidence")
async def runtime_evidence(_: ContentReader):
    try:
        return {
            "items": [
                item.model_dump(mode="json")
                for item in runtime_artifacts.list_staged_evidence()
            ]
        }
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/lesson-presentations")
async def lesson_presentations(_: ContentReader):
    try:
        return {
            "items": [
                item.model_dump(mode="json")
                for item in runtime_artifacts.list_staged_presentations()
            ]
        }
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/lesson-presentations")
async def stage_lesson_presentation(
    payload: LessonPresentationV1,
    request: Request,
    context: ContentPublisher,
):
    try:
        _audit_content_write(
            request,
            context,
            permission="content.publish",
            action="content.lesson_presentation.seal.authorize",
            resource_type="lesson-presentation",
            resource_id=payload.presentation_id,
        )
        record = runtime_artifacts.stage_lesson_presentation(
            payload,
            sealed_by=trusted_actor(context),
        )
        return {"record": record.model_dump(mode="json")}
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/runtime-scenarios")
async def runtime_scenarios(_: ContentReader):
    try:
        return {
            "items": [
                item.model_dump(mode="json")
                for item in runtime_artifacts.list_staged_scenarios()
            ]
        }
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/runtime-scenarios/{scenario_id}/versions/{scenario_version}")
async def runtime_scenario_detail(
    scenario_id: str,
    scenario_version: int,
    course_id: str,
    lesson_id: str,
    scenario_checksum: str,
    _: ContentReader,
):
    try:
        item, descriptor = runtime_artifacts.load_staged_scenario(
            course_id=course_id,
            lesson_id=lesson_id,
            scenario_id=scenario_id,
            scenario_version=scenario_version,
            scenario_checksum=scenario_checksum,
        )
        return {
            "item": item.model_dump(mode="json"),
            "descriptor": descriptor.model_dump(mode="json"),
        }
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/runtime-scenarios/{scenario_id}/versions/{scenario_version}/file")
async def runtime_scenario_file(
    scenario_id: str,
    scenario_version: int,
    course_id: str,
    lesson_id: str,
    scenario_checksum: str,
    _: ContentReader,
):
    try:
        raw, descriptor = runtime_artifacts.load_staged_scenario_bytes(
            course_id=course_id,
            lesson_id=lesson_id,
            scenario_id=scenario_id,
            scenario_version=scenario_version,
            scenario_checksum=scenario_checksum,
        )
        return Response(
            content=raw,
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{scenario_id}-v{scenario_version:03d}.json"'
                ),
                "X-Content-Checksum": descriptor.checksum,
            },
        )
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/runtime-scenarios")
async def stage_runtime_scenario(
    payload: ScenarioTemplateV1,
    request: Request,
    context: ContentPublisher,
):
    try:
        _audit_content_write(
            request,
            context,
            permission="content.publish",
            action="content.scenario.stage.authorize",
            resource_type="runtime-scenario",
            resource_id=payload.scenario_id,
            details={"scenario_version": payload.scenario_version},
        )
        with content_workflow.workflow_write_lock():
            item = runtime_artifacts.stage_scenario(
                payload,
                sealed_by=trusted_actor(context),
            )
        return {"item": item.model_dump(mode="json")}
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/scenario-drafts/template")
async def scenario_draft_template(_: ContentReader):
    return scenario_authoring.scenario_draft_template().model_dump(mode="json")


@router.get("/scenario-drafts")
async def scenario_drafts(_: ContentReader):
    try:
        return {
            "items": [
                item.model_dump(mode="json")
                for item in scenario_authoring.list_scenario_drafts()
            ]
        }
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/scenario-drafts/{scenario_id}")
async def scenario_draft_detail(scenario_id: str, _: ContentReader):
    try:
        item = scenario_authoring.get_scenario_draft(scenario_id)
        if item is None:
            raise FileNotFoundError(f"Scenario draft not found: {scenario_id}")
        return item.model_dump(mode="json")
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/scenario-drafts")
async def save_scenario_draft(
    payload: scenario_authoring.ScenarioAuthorDraftV1,
    request: Request,
    context: ContentAuthor,
):
    try:
        with content_workflow.workflow_write_lock():
            _require_scenario_author(context, payload.scenario_id, allow_missing=True)
            _audit_content_write(
                request,
                context,
                permission="content.author",
                action="content.scenario_draft.save.authorize",
                resource_type="scenario-draft",
                resource_id=payload.scenario_id,
            )
            item = scenario_authoring.save_scenario_draft(
                payload,
                saved_by=trusted_actor(context),
            )
        return {"item": item.model_dump(mode="json")}
    except Exception as exc:
        _raise_content_error(exc)


@router.put("/scenario-drafts/{scenario_id}")
async def update_scenario_draft(
    scenario_id: str,
    payload: scenario_authoring.ScenarioAuthorDraftV1,
    request: Request,
    context: ContentAuthor,
):
    if payload.scenario_id != scenario_id:
        raise HTTPException(
            status_code=400,
            detail="Path scenario_id must match payload.scenario_id.",
        )
    try:
        with content_workflow.workflow_write_lock():
            _require_scenario_author(context, scenario_id)
            _audit_content_write(
                request,
                context,
                permission="content.author",
                action="content.scenario_draft.save.authorize",
                resource_type="scenario-draft",
                resource_id=scenario_id,
            )
            item = scenario_authoring.save_scenario_draft(
                payload,
                saved_by=trusted_actor(context),
            )
        return {"item": item.model_dump(mode="json")}
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/scenario-drafts/{scenario_id}/validate")
async def validate_scenario_draft(
    scenario_id: str,
    request: Request,
    context: ContentAuthor,
):
    try:
        _require_scenario_author(context, scenario_id)
        _audit_content_write(
            request,
            context,
            permission="content.author",
            action="content.scenario_draft.validate.authorize",
            resource_type="scenario-draft",
            resource_id=scenario_id,
        )
        report = scenario_authoring.validate_saved_scenario_draft(scenario_id)
        return {"report": report.model_dump(mode="json")}
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/scenario-drafts/{scenario_id}/seal")
async def seal_scenario_draft(
    scenario_id: str,
    request: Request,
    context: ContentPublisher,
):
    try:
        _audit_content_write(
            request,
            context,
            permission="content.publish",
            action="content.scenario_draft.seal.authorize",
            resource_type="scenario-draft",
            resource_id=scenario_id,
        )
        with content_workflow.workflow_write_lock():
            item, record, idempotent = scenario_authoring.seal_scenario_draft(
                scenario_id,
                sealed_by=trusted_actor(context),
            )
        return {
            "item": item.model_dump(mode="json"),
            "record": record.model_dump(mode="json"),
            "idempotent": idempotent,
        }
    except scenario_authoring.ScenarioDraftValidationFailed as exc:
        detail = {
            "code": exc.code,
            "message": str(exc),
            "issues": [item.model_dump(mode="json") for item in exc.report.issues],
        }
        raise HTTPException(status_code=422, detail=detail) from exc
    except Exception as exc:
        _raise_content_error(exc)


@router.post(
    "/sealed/{lesson_id}/versions/{version}/publish",
    response_model=ReleaseResponse,
)
async def publish_version(
    lesson_id: str,
    version: int,
    request: Request,
    context: ContentPublisher,
    req: PublishRequest | None = None,
):
    try:
        _audit_content_write(
            request,
            context,
            permission="content.publish",
            action="content.release.publish.authorize",
            resource_type="sealed-lesson",
            resource_id=f"{lesson_id}:v{version}",
        )
        release, workflow = content_workflow.publish_version(
            lesson_id,
            version,
            actor=trusted_actor(context),
            note=(req.note if req else ""),
            scenario_selections=(req.scenarios if req else None),
            evidence_selection=(req.evidence if req else None),
            presentation_selection=(req.presentation if req else None),
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
    request: Request,
    context: ContentPublisher,
):
    try:
        _audit_content_write(
            request,
            context,
            permission="content.publish",
            action="content.release.bootstrap_legacy.authorize",
            resource_type="course-release",
            resource_id=course_id,
        )
        release = content_workflow.bootstrap_legacy_release(
            course_id,
            req.selections,
            actor=trusted_actor(context),
            note=req.note,
        )
        return ReleaseResponse(release=release)
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/releases", response_model=ReleaseListResponse)
async def releases(
    _: ContentReader,
    course_id: str | None = None,
):
    try:
        return ReleaseListResponse(items=content_workflow.list_releases(course_id))
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/releases/{course_id}/current", response_model=ReleaseResponse)
async def current_release(course_id: str, _: ContentReader):
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
    _: ContentReader,
):
    try:
        return ReleaseResponse(release=content_workflow.get_release(course_id, release_id))
    except Exception as exc:
        _raise_content_error(exc)


@router.post(
    "/releases/{course_id}/{release_id}/archive-preview",
    response_model=ArchivePreviewResponse,
)
async def archive_preview(
    course_id: str,
    release_id: str,
    _: ContentReader,
):
    try:
        archive = build_course_archive(course_id, release_id)
        return ArchivePreviewResponse(
            archive=archive.manifest,
            download_url=(
                f"/api/v1/admin/content/releases/{course_id}/{release_id}/archive.zip"
            ),
        )
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/releases/{course_id}/{release_id}/archive.zip")
async def archive_download(
    course_id: str,
    release_id: str,
    _: ContentReader,
):
    try:
        archive = build_course_archive(course_id, release_id)
        filename = archive_download_filename(archive.manifest)
        return Response(
            content=build_course_archive_zip(archive),
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    "attachment; filename=chronovita-course-archive.zip; "
                    f"filename*=UTF-8''{quote(filename)}"
                ),
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, no-store",
            },
        )
    except Exception as exc:
        _raise_content_error(exc)


@router.post(
    "/publications",
    response_model=PublicationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_publication(
    payload: CourseArchivePublishRequestV1,
    request: Request,
    context: ContentPublisher,
):
    client: GitHubGitDataClient | None = None
    try:
        _require_direct_commit_admin(context, payload.mode)
        _audit_content_write(
            request,
            context,
            permission="content.publish",
            action="content.archive.publication.authorize",
            resource_type="course-archive",
            resource_id=payload.archive_id,
            details={
                "binding_id": payload.binding_id,
                "course_id": payload.course_id,
                "release_id": payload.release_id,
                "mode": payload.mode,
            },
        )
        service, client = _new_publication_service()
        async with client:
            submitted = await service.submit(
                payload,
                requested_by=trusted_actor(context),
            )
        return PublicationResponse(
            publication=submitted.publication,
            reused=submitted.reused,
        )
    except Exception as exc:
        if client is not None and not client.is_closed:
            await client.aclose()
        _raise_content_error(exc)


@router.get("/publications", response_model=PublicationListResponse)
async def publications(
    _: ContentReader,
    course_id: str | None = None,
    release_id: str | None = None,
    publication_status: PublicationStatus | None = None,
):
    try:
        return PublicationListResponse(
            items=list(
                PublicationStore().list(
                    publication_kind="course",
                    course_id=course_id,
                    release_id=release_id,
                    status=publication_status,
                )
            )
        )
    except Exception as exc:
        _raise_content_error(exc)


@router.get(
    "/publications/{publication_id}",
    response_model=PublicationResponse,
)
async def publication_detail(
    publication_id: str,
    _: ContentReader,
):
    try:
        record = PublicationStore().get(publication_id)
        if not isinstance(record.intent.request, CourseArchivePublishRequestV1):
            raise PublicationNotFound(
                f"course publication was not found: {publication_id}"
            )
        return PublicationResponse(
            publication=record,
            reused=True,
        )
    except Exception as exc:
        _raise_content_error(exc)


@router.post(
    "/publications/{publication_id}/retry",
    response_model=PublicationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_publication(
    publication_id: str,
    payload: PublicationRetryRequest,
    request: Request,
    context: ContentPublisher,
):
    client: GitHubGitDataClient | None = None
    try:
        existing = PublicationStore().get(publication_id)
        if not isinstance(
            existing.intent.request,
            CourseArchivePublishRequestV1,
        ):
            raise PublicationNotFound(
                f"course publication was not found: {publication_id}"
            )
        _require_direct_commit_admin(context, existing.intent.request.mode)
        _audit_content_write(
            request,
            context,
            permission="content.publish",
            action="content.archive.publication.retry.authorize",
            resource_type="course-publication",
            resource_id=publication_id,
            details={
                "expected_revision": payload.expected_revision,
                "mode": existing.intent.request.mode,
            },
        )
        service, client = _new_publication_service()
        async with client:
            publication = await service.retry(
                publication_id,
                expected_revision=payload.expected_revision,
            )
        return PublicationResponse(publication=publication, reused=True)
    except Exception as exc:
        if client is not None and not client.is_closed:
            await client.aclose()
        _raise_content_error(exc)


@router.post(
    "/asset-archives/{asset_kind}/{asset_id}/versions/{version}/preview",
    response_model=ContentAssetArchivePreviewResponse,
)
async def content_asset_archive_preview(
    asset_kind: ContentAssetKind,
    asset_id: str,
    version: int,
    source_checksum: str,
    _: ContentReader,
):
    try:
        archive = build_content_asset_archive(
            asset_kind,
            asset_id,
            version,
            expected_source_checksum=source_checksum,
        )
        return ContentAssetArchivePreviewResponse(
            archive=archive.manifest,
            download_url=(
                f"/api/v1/admin/content/asset-archives/{asset_kind}/"
                f"{asset_id}/versions/{version}/archive.zip"
                f"?source_checksum={source_checksum}"
            ),
        )
    except Exception as exc:
        _raise_content_error(exc)


@router.get(
    "/asset-archives/{asset_kind}/{asset_id}/versions/{version}/archive.zip"
)
async def content_asset_archive_download(
    asset_kind: ContentAssetKind,
    asset_id: str,
    version: int,
    source_checksum: str,
    _: ContentReader,
):
    try:
        archive = build_content_asset_archive(
            asset_kind,
            asset_id,
            version,
            expected_source_checksum=source_checksum,
        )
        filename = content_asset_archive_download_filename(archive.manifest)
        return Response(
            content=build_content_asset_archive_zip(archive),
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    "attachment; filename=chronovita-content-asset.zip; "
                    f"filename*=UTF-8''{quote(filename)}"
                ),
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, no-store",
            },
        )
    except Exception as exc:
        _raise_content_error(exc)


@router.post(
    "/asset-publications",
    response_model=PublicationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_content_asset_publication(
    payload: ContentAssetArchivePublishRequestV1,
    request: Request,
    context: ContentPublisher,
):
    client: GitHubGitDataClient | None = None
    try:
        _require_direct_commit_admin(context, payload.mode)
        _audit_content_write(
            request,
            context,
            permission="content.publish",
            action="content.asset.publication.authorize",
            resource_type=f"{payload.asset_kind}-archive",
            resource_id=payload.archive_id,
            details={
                "binding_id": payload.binding_id,
                "asset_kind": payload.asset_kind,
                "asset_id": payload.asset_id,
                "version": payload.version,
                "mode": payload.mode,
            },
        )
        service, client = _new_asset_publication_service()
        async with client:
            submitted = await service.submit(
                payload,
                requested_by=trusted_actor(context),
            )
        return PublicationResponse(
            publication=submitted.publication,
            reused=submitted.reused,
        )
    except Exception as exc:
        if client is not None and not client.is_closed:
            await client.aclose()
        _raise_content_error(exc)


@router.get(
    "/asset-publications",
    response_model=PublicationListResponse,
)
async def content_asset_publications(
    _: ContentReader,
    asset_kind: ContentAssetKind | None = None,
    asset_id: str | None = None,
    asset_version: int | None = None,
    publication_status: PublicationStatus | None = None,
):
    try:
        return PublicationListResponse(
            items=list(
                PublicationStore().list(
                    publication_kind="asset",
                    asset_kind=asset_kind,
                    asset_id=asset_id,
                    asset_version=asset_version,
                    status=publication_status,
                )
            )
        )
    except Exception as exc:
        _raise_content_error(exc)


@router.get(
    "/asset-publications/{publication_id}",
    response_model=PublicationResponse,
)
async def content_asset_publication_detail(
    publication_id: str,
    _: ContentReader,
):
    try:
        record = PublicationStore().get(publication_id)
        if not isinstance(
            record.intent.request,
            ContentAssetArchivePublishRequestV1,
        ):
            raise PublicationNotFound(
                f"content asset publication was not found: {publication_id}"
            )
        return PublicationResponse(publication=record, reused=True)
    except Exception as exc:
        _raise_content_error(exc)


@router.post(
    "/asset-publications/{publication_id}/retry",
    response_model=PublicationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_content_asset_publication(
    publication_id: str,
    payload: PublicationRetryRequest,
    request: Request,
    context: ContentPublisher,
):
    client: GitHubGitDataClient | None = None
    try:
        existing = PublicationStore().get(publication_id)
        if not isinstance(
            existing.intent.request,
            ContentAssetArchivePublishRequestV1,
        ):
            raise PublicationNotFound(
                f"content asset publication was not found: {publication_id}"
            )
        _require_direct_commit_admin(context, existing.intent.request.mode)
        _audit_content_write(
            request,
            context,
            permission="content.publish",
            action="content.asset.publication.retry.authorize",
            resource_type="content-asset-publication",
            resource_id=publication_id,
            details={
                "expected_revision": payload.expected_revision,
                "mode": existing.intent.request.mode,
            },
        )
        service, client = _new_asset_publication_service()
        async with client:
            publication = await service.retry(
                publication_id,
                expected_revision=payload.expected_revision,
            )
        return PublicationResponse(publication=publication, reused=True)
    except Exception as exc:
        if client is not None and not client.is_closed:
            await client.aclose()
        _raise_content_error(exc)


@router.post("/releases/{course_id}/rollback", response_model=ReleaseResponse)
async def rollback_release(
    course_id: str,
    request: Request,
    context: ContentPublisher,
    req: RollbackRequest | None = None,
):
    try:
        _audit_content_write(
            request,
            context,
            permission="content.publish",
            action="content.release.rollback.authorize",
            resource_type="course-release",
            resource_id=course_id,
            details={
                "target_release_id": req.target_release_id if req else None,
            },
        )
        release = content_workflow.rollback_release(
            course_id,
            actor=trusted_actor(context),
            target_release_id=(req.target_release_id if req else None),
            note=(req.note if req else ""),
        )
        return ReleaseResponse(release=release)
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/assets")
async def assets(
    _: ContentReader,
    kind: Literal["person", "keyword"] | None = None,
):
    try:
        return {"items": [item.model_dump(mode="json") for item in content.list_assets(kind)]}
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/assets/people/template")
async def person_template(_: ContentReader):
    return content.person_template().model_dump(mode="json")


@router.get("/assets/people/{asset_id}")
async def person_detail(asset_id: str, _: ContentReader):
    try:
        item = content.get_person_profile(asset_id)
        if item is None:
            raise content_workflow.ContentNotFound("Person profile not found.")
        return item.model_dump(mode="json")
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/assets/people")
async def save_person(
    payload: PersonProfilePackage,
    request: Request,
    context: ContentAuthor,
):
    try:
        _audit_content_write(
            request,
            context,
            permission="content.author",
            action="content.person.save.authorize",
            resource_type="person-profile",
            resource_id=payload.asset_id,
        )
        saved = content.save_person_profile(payload)
        return {"item": saved.model_dump(mode="json")}
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/assets/people/{asset_id}/validate")
async def validate_person_asset(
    asset_id: str,
    request: Request,
    context: ContentAuthor,
):
    try:
        _audit_content_write(
            request,
            context,
            permission="content.author",
            action="content.person.validate.authorize",
            resource_type="person-profile",
            resource_id=asset_id,
        )
        return {
            "report": content.validate_person_profile(asset_id).model_dump(
                mode="json"
            )
        }
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/assets/people/{asset_id}/seal")
async def seal_person_asset(
    asset_id: str,
    request: Request,
    context: ContentPublisher,
):
    try:
        _audit_content_write(
            request,
            context,
            permission="content.publish",
            action="content.person.seal.authorize",
            resource_type="person-profile",
            resource_id=asset_id,
        )
        report = content.validate_person_profile(asset_id)
        if not report.valid:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "content_asset_validation_failed",
                    "message": "人物档案仍有阻断项。",
                    "issues": [
                        item.model_dump(mode="json")
                        for item in report.issues
                    ],
                },
            )
        item, path, idempotent = content.seal_person_profile(
            asset_id,
            sealed_by=trusted_actor(context),
        )
        record = content.record_for_asset(item, path, kind="person")
        return {
            "item": item.model_dump(mode="json"),
            "record": record.model_dump(mode="json"),
            "idempotent": idempotent,
        }
    except HTTPException:
        raise
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/assets/people/{asset_id}/versions")
async def person_asset_versions(asset_id: str, _: ContentReader):
    try:
        return {
            "items": [
                item.model_dump(mode="json")
                for item in content.list_sealed_people(asset_id)
            ]
        }
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/assets/people/{asset_id}/versions/{version}")
async def sealed_person_asset(
    asset_id: str,
    version: int,
    _: ContentReader,
):
    try:
        return content.get_sealed_person_profile(
            asset_id,
            version,
        ).model_dump(mode="json")
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/assets/keywords/template")
async def keyword_template(_: ContentReader):
    return content.keyword_template().model_dump(mode="json")


@router.get("/assets/keywords/{asset_id}")
async def keyword_detail(asset_id: str, _: ContentReader):
    try:
        item = content.get_keyword_profile(asset_id)
        if item is None:
            raise content_workflow.ContentNotFound("Keyword profile not found.")
        return item.model_dump(mode="json")
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/assets/keywords")
async def save_keyword(
    payload: KeywordProfilePackage,
    request: Request,
    context: ContentAuthor,
):
    try:
        _audit_content_write(
            request,
            context,
            permission="content.author",
            action="content.keyword.save.authorize",
            resource_type="keyword-profile",
            resource_id=payload.asset_id,
        )
        saved = content.save_keyword_profile(payload)
        return {"item": saved.model_dump(mode="json")}
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/assets/keywords/{asset_id}/validate")
async def validate_keyword_asset(
    asset_id: str,
    request: Request,
    context: ContentAuthor,
):
    try:
        _audit_content_write(
            request,
            context,
            permission="content.author",
            action="content.keyword.validate.authorize",
            resource_type="keyword-profile",
            resource_id=asset_id,
        )
        return {
            "report": content.validate_keyword_profile(asset_id).model_dump(
                mode="json"
            )
        }
    except Exception as exc:
        _raise_content_error(exc)


@router.post("/assets/keywords/{asset_id}/seal")
async def seal_keyword_asset(
    asset_id: str,
    request: Request,
    context: ContentPublisher,
):
    try:
        _audit_content_write(
            request,
            context,
            permission="content.publish",
            action="content.keyword.seal.authorize",
            resource_type="keyword-profile",
            resource_id=asset_id,
        )
        report = content.validate_keyword_profile(asset_id)
        if not report.valid:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "content_asset_validation_failed",
                    "message": "关键词档案仍有阻断项。",
                    "issues": [
                        item.model_dump(mode="json")
                        for item in report.issues
                    ],
                },
            )
        item, path, idempotent = content.seal_keyword_profile(
            asset_id,
            sealed_by=trusted_actor(context),
        )
        record = content.record_for_asset(item, path, kind="keyword")
        return {
            "item": item.model_dump(mode="json"),
            "record": record.model_dump(mode="json"),
            "idempotent": idempotent,
        }
    except HTTPException:
        raise
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/assets/keywords/{asset_id}/versions")
async def keyword_asset_versions(asset_id: str, _: ContentReader):
    try:
        return {
            "items": [
                item.model_dump(mode="json")
                for item in content.list_sealed_keywords(asset_id)
            ]
        }
    except Exception as exc:
        _raise_content_error(exc)


@router.get("/assets/keywords/{asset_id}/versions/{version}")
async def sealed_keyword_asset(
    asset_id: str,
    version: int,
    _: ContentReader,
):
    try:
        return content.get_sealed_keyword_profile(
            asset_id,
            version,
        ).model_dump(mode="json")
    except Exception as exc:
        _raise_content_error(exc)


def _audit_content_write(
    request: Request,
    context: AuthContext,
    *,
    permission: str,
    action: str,
    resource_type: str,
    resource_id: str,
    details: dict[str, object] | None = None,
) -> None:
    audit_authorized_action(
        request,
        context,
        permission=permission,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
    )


def _new_publication_service() -> tuple[CoursePublicationService, GitHubGitDataClient]:
    if not settings.github_publication_enabled:
        raise PublicationDisabled("GitHub publication is not enabled")
    token = secret_value(settings.github_publication_token)
    if not token:
        raise PublicationConfigurationError(
            "GitHub publication credential is not configured"
        )
    binding = load_repository_binding(settings.content_history_target_path)
    client = GitHubGitDataClient(
        token=token,
        repository_id=binding.repository_id,
        full_name=binding.full_name,
        api_base_url=settings.github_api_base_url,
        timeout_seconds=settings.github_timeout_seconds,
    )
    return (
        CoursePublicationService(
            binding=binding,
            github=client,
            stale_after_seconds=settings.github_publication_stale_seconds,
        ),
        client,
    )


def _new_asset_publication_service() -> tuple[
    ContentAssetPublicationService,
    GitHubGitDataClient,
]:
    if not settings.github_publication_enabled:
        raise PublicationDisabled("GitHub publication is not enabled")
    token = secret_value(settings.github_publication_token)
    if not token:
        raise PublicationConfigurationError(
            "GitHub publication credential is not configured"
        )
    binding = load_repository_binding(settings.content_history_target_path)
    client = GitHubGitDataClient(
        token=token,
        repository_id=binding.repository_id,
        full_name=binding.full_name,
        api_base_url=settings.github_api_base_url,
        timeout_seconds=settings.github_timeout_seconds,
    )
    return (
        ContentAssetPublicationService(
            binding=binding,
            github=client,
            stale_after_seconds=settings.github_publication_stale_seconds,
        ),
        client,
    )


def _require_direct_commit_admin(
    context: AuthContext,
    mode: Literal["pull_request", "direct_commit"],
) -> None:
    if mode == "direct_commit" and "admin" not in context.principal.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "admin_role_required",
                "message": "Direct publication requires an administrator.",
            },
        )


def _require_lesson_author(
    context: AuthContext,
    lesson_id: str,
    *,
    allow_missing: bool = False,
) -> None:
    if "admin" in context.principal.roles:
        return
    workflow = content_workflow.get_workflow(lesson_id)
    if workflow is None:
        if allow_missing:
            return
        raise content_workflow.ContentNotFound(f"Workflow not found: {lesson_id}")
    owner = next((event.actor for event in workflow.history if event.action == "save"), None)
    if owner != trusted_actor(context):
        _raise_ownership_error("lesson draft")


def _require_independent_reviewer(context: AuthContext, lesson_id: str) -> None:
    if "admin" in context.principal.roles:
        return
    workflow = content_workflow.get_workflow(lesson_id)
    if workflow is None:
        raise content_workflow.ContentNotFound(f"Workflow not found: {lesson_id}")
    actor = trusted_actor(context)
    if any(event.action == "save" and event.actor == actor for event in workflow.history):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "self_review_forbidden",
                "message": "An author cannot review the same lesson draft.",
            },
        )


def _require_scenario_author(
    context: AuthContext,
    scenario_id: str,
    *,
    allow_missing: bool = False,
) -> None:
    if "admin" in context.principal.roles:
        return
    draft = scenario_authoring.get_scenario_draft(scenario_id)
    if draft is None:
        if allow_missing:
            return
        raise FileNotFoundError(f"Scenario draft not found: {scenario_id}")
    if draft.created_by != trusted_actor(context):
        _raise_ownership_error("scenario draft")


def _require_evidence_author(
    context: AuthContext,
    corpus_id: str,
    *,
    allow_missing: bool = False,
) -> None:
    if "admin" in context.principal.roles:
        return
    draft = evidence_workflow.get_evidence_draft(corpus_id)
    if draft is None:
        if allow_missing:
            return
        raise evidence_workflow.EvidenceDraftNotFound(
            f"Evidence draft not found: {corpus_id}"
        )
    if draft.created_by != trusted_actor(context):
        _raise_ownership_error("evidence draft")


def _require_independent_evidence_reviewer(
    context: AuthContext,
    corpus_id: str,
) -> None:
    record = evidence_workflow.get_evidence_workflow(corpus_id)
    if record is None:
        raise evidence_workflow.EvidenceDraftNotFound(
            f"Evidence workflow not found: {corpus_id}"
        )
    actor = trusted_actor(context)
    if any(
        event.action == "save" and event.actor == actor
        for event in record.history
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "self_review_forbidden",
                "message": "An evidence author cannot review the same draft.",
            },
        )


def _raise_ownership_error(resource: str) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "content_owner_required",
            "message": f"Only the owning author or an administrator may change this {resource}.",
        },
    )


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
    if isinstance(exc, evidence_workflow.EvidenceValidationFailed) and exc.report is not None:
        detail["issues"] = [
            issue.model_dump(mode="json")
            for issue in exc.report.issues
        ]
    if isinstance(exc, ContentAssetArchiveChanged):
        raise HTTPException(status_code=409, detail=detail) from exc
    if isinstance(exc, ArchiveBuildError):
        detail["code"] = exc.code
        raise HTTPException(status_code=503, detail=detail) from exc
    if isinstance(exc, PublicationNotFound):
        raise HTTPException(status_code=404, detail=detail) from exc
    if isinstance(
        exc,
        (
            PublicationArchiveChanged,
            PublicationConflict,
            PublicationRetryRejected,
        ),
    ):
        raise HTTPException(status_code=409, detail=detail) from exc
    if isinstance(
        exc,
        (
            PublicationConfigurationError,
            PublicationDisabled,
            PublicationStoreError,
        ),
    ):
        raise HTTPException(status_code=503, detail=detail) from exc
    if isinstance(
        exc,
        (
            content_workflow.ContentNotFound,
            evidence_workflow.EvidenceDraftNotFound,
            FileNotFoundError,
        ),
    ):
        raise HTTPException(status_code=404, detail=detail) from exc
    if isinstance(exc, scenario_authoring.ScenarioDraftConflict):
        raise HTTPException(status_code=409, detail=detail) from exc
    if isinstance(
        exc,
        (
            content_workflow.ContentConflict,
            content_workflow.InvalidTransition,
            evidence_workflow.EvidenceDraftConflict,
            evidence_workflow.EvidenceInvalidTransition,
            FileExistsError,
        ),
    ):
        raise HTTPException(status_code=409, detail=detail) from exc
    if isinstance(
        exc,
        (
            content_workflow.ContentValidationFailed,
            evidence_workflow.EvidenceValidationFailed,
            ValueError,
        ),
    ):
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
