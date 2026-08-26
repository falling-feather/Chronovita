"""Authenticated learning progress backed by owner-scoped KV records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from auth_dependencies import (
    AuthContext,
    audit_authorized_action,
    require_permission,
    require_student_context,
)
from services import persistence
from services.auth import AccountsModeRequired, AuthStoreError, get_identity
from services.contracts.learning_v1 import (
    LearningCanvasSnapshotV1,
    LearningFeedbackRequestV1,
    LearningFeedbackV1,
    LearningSubmissionRequestV1,
    LearningSubmissionV1,
    SubmissionId,
)
from services.contracts.v1 import ContractId
from services.courses import get_lesson
from services.learning_assets import (
    LearningAssetStoreError,
    LearningFeedbackIntegrityError,
    LearningSubmissionConflict,
    LearningSubmissionIntegrityError,
    LearningSubmissionNotFound,
    get_learning_assets,
)


router = APIRouter()

_LEGACY_USER = "default"
_NS = "lesson_progress"
_LAYER_ORDER = ("watch", "practice", "ask", "create")
_LAYERS = frozenset(_LAYER_ORDER)
_MAX_WRITE_ATTEMPTS = 8


class ProgressLayers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    watch: bool = False
    practice: bool = False
    ask: bool = False
    create: bool = False


class ProgressItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_id: ContractId
    course_id: str | None = None
    title: str | None = None
    last_layer: str = "watch"
    layers: ProgressLayers = Field(default_factory=ProgressLayers)
    updated_at: str


class StoredProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: ContractId
    lesson_id: ContractId
    last_layer: str = "watch"
    layers: ProgressLayers = Field(default_factory=ProgressLayers)
    updated_at: str


class TouchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_id: ContractId
    layer: str = "watch"
    completed: bool = False


class SubmissionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: str
    student_id: str
    student_display_name: str
    student_username: str | None = None
    course_id: str
    lesson_id: str
    version: int
    title: str
    body_excerpt: str
    sticky_note_count: int
    stroke_count: int
    event_count: int
    canvas_node_count: int
    submitted_at: str
    checksum: str
    latest_feedback: LearningFeedbackV1 | None = None


class SubmissionDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission: LearningSubmissionV1
    student_display_name: str
    student_username: str | None = None
    feedback: list[LearningFeedbackV1] = Field(default_factory=list)


def _owner_id(context: AuthContext) -> str:
    if context.source == "legacy-local-student":
        return _LEGACY_USER
    return context.principal.user_id


def _prefix(owner_id: str) -> str:
    return f"{owner_id}:"


def _key(owner_id: str, lesson_id: str) -> str:
    return f"{_prefix(owner_id)}{lesson_id}"


def _parse_progress(
    raw: object,
    *,
    owner_id: str,
    lesson_id: str,
) -> StoredProgress:
    try:
        record = StoredProgress.model_validate(raw)
    except ValidationError as exc:
        raise _progress_integrity_error() from exc
    if (
        record.user_id != owner_id
        or record.lesson_id != lesson_id
        or record.last_layer not in _LAYERS
    ):
        raise _progress_integrity_error()
    return record


def _enrich(record: StoredProgress) -> ProgressItem:
    item = record.model_dump(exclude={"user_id"})
    lesson = get_lesson(record.lesson_id)
    if lesson:
        item["course_id"] = lesson.course_id
        item["title"] = lesson.title
    return ProgressItem.model_validate(item)


def _list_for_owner(owner_id: str) -> list[StoredProgress]:
    prefix = _prefix(owner_id)
    records = []
    for key, raw in persistence.kv_list_prefix(_NS, prefix):
        records.append(
            _parse_progress(
                raw,
                owner_id=owner_id,
                lesson_id=key[len(prefix) :],
            )
        )
    records.sort(key=lambda item: item.updated_at, reverse=True)
    return records


@router.get("/")
async def index(
    context: AuthContext = Depends(require_student_context),
):
    records = _list_for_owner(_owner_id(context))
    return {
        "module": "我的学习",
        "items": [_enrich(item).model_dump() for item in records[:50]],
    }


@router.get("/progress")
async def list_progress(
    context: AuthContext = Depends(require_student_context),
):
    records = _list_for_owner(_owner_id(context))
    return {"items": [_enrich(item).model_dump() for item in records]}


@router.get("/progress/latest")
async def latest_progress(
    context: AuthContext = Depends(require_student_context),
):
    records = _list_for_owner(_owner_id(context))
    return {"item": _enrich(records[0]).model_dump() if records else None}


@router.get("/progress/{lesson_id}")
async def get_progress(
    lesson_id: ContractId,
    context: AuthContext = Depends(require_student_context),
):
    owner_id = _owner_id(context)
    raw = persistence.kv_get(_NS, _key(owner_id, lesson_id))
    if raw is None:
        return {"item": None}
    record = _parse_progress(raw, owner_id=owner_id, lesson_id=lesson_id)
    return {"item": _enrich(record).model_dump()}


@router.post("/progress/touch")
async def touch_progress(
    req: TouchRequest,
    context: AuthContext = Depends(require_student_context),
):
    if req.layer not in _LAYERS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_progress_layer",
                "message": f"Unsupported learning layer: {req.layer}",
            },
        )
    owner_id = _owner_id(context)
    key = _key(owner_id, req.lesson_id)
    for _ in range(_MAX_WRITE_ATTEMPTS):
        found, raw = persistence.kv_get_with_presence(_NS, key)
        if found:
            current = _parse_progress(
                raw,
                owner_id=owner_id,
                lesson_id=req.lesson_id,
            )
            layers = current.layers.model_dump()
        else:
            layers = {layer: False for layer in _LAYER_ORDER}
        if req.completed:
            layers[req.layer] = True
        next_record = StoredProgress(
            user_id=owner_id,
            lesson_id=req.lesson_id,
            last_layer=req.layer,
            layers=layers,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        if persistence.kv_compare_and_set(
            _NS,
            key,
            raw if found else None,
            next_record.model_dump(mode="json"),
            expected_present=found,
        ):
            return {"ok": True, "item": _enrich(next_record).model_dump()}
    raise HTTPException(
        status_code=409,
        detail={
            "code": "progress_write_conflict",
            "message": "Learning progress changed repeatedly; reload and retry.",
        },
    )


def _progress_integrity_error() -> HTTPException:
    return HTTPException(
        status_code=500,
        detail={
            "code": "progress_integrity_error",
            "message": "Learning progress storage failed integrity validation.",
        },
    )


# ============= 明确提交的学习成果与教师反馈 =============


@router.post("/submissions", status_code=status.HTTP_201_CREATED)
async def create_submission(
    payload: LearningSubmissionRequestV1,
    request: Request,
    context: AuthContext = Depends(require_student_context),
):
    _require_persisted_account(context)
    lesson = get_lesson(payload.lesson_id)
    if lesson is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "lesson_not_found",
                "message": "The lesson does not exist.",
            },
        )
    if lesson.course_id != payload.course_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "lesson_course_mismatch",
                "message": "The lesson does not belong to the submitted course.",
            },
        )

    owner_id = _owner_id(context)
    canvas = _canvas_snapshot(owner_id, payload.lesson_id, context)
    try:
        result = get_learning_assets().create_submission(
            student_id=owner_id,
            request=payload,
            canvas=canvas,
        )
    except Exception as exc:
        _raise_learning_asset_error(exc)
    audit_authorized_action(
        request,
        context,
        permission="student.own",
        action="student.submission.create",
        resource_type="learning_submission",
        resource_id=result.submission.submission_id,
        details={
            "course_id": payload.course_id,
            "lesson_id": payload.lesson_id,
            "version": result.submission.version,
            "reused": result.reused,
        },
    )
    return {
        "submission": result.submission.model_dump(mode="json"),
        "reused": result.reused,
    }


@router.get("/submissions")
async def list_own_submissions(
    course_id: str | None = Query(default=None, min_length=2, max_length=64),
    lesson_id: str | None = Query(default=None, min_length=2, max_length=64),
    limit: int = Query(default=50, ge=1, le=100),
    context: AuthContext = Depends(require_student_context),
):
    owner_id = _owner_id(context)
    try:
        submissions = get_learning_assets().list_student_submissions(
            owner_id,
            course_id=course_id,
            lesson_id=lesson_id,
            limit=limit,
        )
        labels = _student_labels(submissions, context=context)
        items = [
            _submission_list_item(item, labels=labels)
            for item in submissions
        ]
    except Exception as exc:
        _raise_learning_asset_error(exc)
    return {"items": [item.model_dump(mode="json") for item in items]}


@router.get("/submissions/{submission_id}")
async def get_own_submission(
    submission_id: SubmissionId,
    context: AuthContext = Depends(require_student_context),
):
    owner_id = _owner_id(context)
    try:
        submission = get_learning_assets().load_student_submission(
            submission_id,
            owner_id,
        )
        labels = _student_labels([submission], context=context)
        detail = _submission_detail(submission, labels=labels)
    except Exception as exc:
        _raise_learning_asset_error(exc)
    return detail.model_dump(mode="json")


@router.get("/review/submissions")
async def list_review_submissions(
    request: Request,
    student_id: str | None = Query(default=None, min_length=2, max_length=64),
    course_id: str | None = Query(default=None, min_length=2, max_length=64),
    lesson_id: str | None = Query(default=None, min_length=2, max_length=64),
    limit: int = Query(default=100, ge=1, le=100),
    context: AuthContext = Depends(require_permission("student.summary")),
):
    try:
        submissions = get_learning_assets().list_submissions(
            student_id=student_id,
            course_id=course_id,
            lesson_id=lesson_id,
            limit=limit,
        )
        labels = _student_labels(submissions, context=context)
        items = [
            _submission_list_item(item, labels=labels)
            for item in submissions
        ]
    except Exception as exc:
        _raise_learning_asset_error(exc)
    audit_authorized_action(
        request,
        context,
        permission="student.summary",
        action="student.submission.list",
        resource_type="learning_submission_collection",
        resource_id="submitted-learning-work",
        details={
            "student_id": student_id,
            "course_id": course_id,
            "lesson_id": lesson_id,
            "result_count": len(items),
        },
    )
    return {"items": [item.model_dump(mode="json") for item in items]}


@router.get("/review/submissions/{submission_id}")
async def get_review_submission(
    submission_id: SubmissionId,
    request: Request,
    context: AuthContext = Depends(require_permission("student.summary")),
):
    try:
        submission = get_learning_assets().load_submission(submission_id)
        labels = _student_labels([submission], context=context)
        detail = _submission_detail(submission, labels=labels)
    except Exception as exc:
        _raise_learning_asset_error(exc)
    audit_authorized_action(
        request,
        context,
        permission="student.summary",
        action="student.submission.read",
        resource_type="learning_submission",
        resource_id=submission_id,
        details={
            "student_id": submission.student_id,
            "course_id": submission.course_id,
            "lesson_id": submission.lesson_id,
        },
    )
    return detail.model_dump(mode="json")


@router.post(
    "/review/submissions/{submission_id}/feedback",
    status_code=status.HTTP_201_CREATED,
)
async def create_review_feedback(
    submission_id: SubmissionId,
    payload: LearningFeedbackRequestV1,
    request: Request,
    context: AuthContext = Depends(require_permission("student.feedback")),
):
    _require_persisted_account(context)
    try:
        submission = get_learning_assets().load_submission(submission_id)
        result = get_learning_assets().create_feedback(
            submission_id=submission_id,
            teacher_id=context.principal.user_id,
            teacher_display_name=context.principal.display_name,
            request=payload,
        )
    except Exception as exc:
        _raise_learning_asset_error(exc)
    audit_authorized_action(
        request,
        context,
        permission="student.feedback",
        action="student.submission.feedback",
        resource_type="learning_submission",
        resource_id=submission_id,
        details={
            "student_id": submission.student_id,
            "completion_status": result.feedback.completion_status,
            "feedback_sequence": result.feedback.sequence,
            "reused": result.reused,
        },
    )
    return {
        "feedback": result.feedback.model_dump(mode="json"),
        "reused": result.reused,
    }


def _canvas_snapshot(
    owner_id: str,
    lesson_id: str,
    context: AuthContext,
) -> LearningCanvasSnapshotV1:
    key = lesson_id if context.source == "legacy-local-student" else f"{owner_id}:{lesson_id}"
    found, raw = persistence.kv_get_with_presence("canvas", key)
    if not found:
        return LearningCanvasSnapshotV1(found=False, revision=0)
    try:
        if not isinstance(raw, dict):
            raise ValueError("canvas record must be an object")
        if raw.get("schema_version") == "canvas/v1":
            revision = raw.get("revision")
        else:
            revision = 1
        return LearningCanvasSnapshotV1(
            found=True,
            revision=revision,
            nodes=raw.get("nodes", []),
            edges=raw.get("edges", []),
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise LearningSubmissionIntegrityError(
            "the saved canvas cannot be included in a submission"
        ) from exc


def _require_persisted_account(context: AuthContext) -> None:
    if context.principal.synthetic:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "accounts_mode_required",
                "message": "Versioned learning work requires a persisted account.",
            },
        )


def _submission_list_item(
    submission: LearningSubmissionV1,
    *,
    labels: dict[str, tuple[str, str | None]],
) -> SubmissionListItem:
    feedback = get_learning_assets().list_feedback(submission.submission_id)
    display_name, username = labels.get(
        submission.student_id,
        (submission.student_id, None),
    )
    excerpt = " ".join(submission.body_markdown.split())[:180]
    return SubmissionListItem(
        submission_id=submission.submission_id,
        student_id=submission.student_id,
        student_display_name=display_name,
        student_username=username,
        course_id=submission.course_id,
        lesson_id=submission.lesson_id,
        version=submission.version,
        title=submission.title,
        body_excerpt=excerpt,
        sticky_note_count=len(submission.sticky_notes),
        stroke_count=len(submission.drawing_strokes),
        event_count=len(submission.learning_events),
        canvas_node_count=len(submission.canvas.nodes),
        submitted_at=submission.submitted_at.isoformat(),
        checksum=submission.checksum,
        latest_feedback=feedback[-1] if feedback else None,
    )


def _submission_detail(
    submission: LearningSubmissionV1,
    *,
    labels: dict[str, tuple[str, str | None]],
) -> SubmissionDetail:
    display_name, username = labels.get(
        submission.student_id,
        (submission.student_id, None),
    )
    return SubmissionDetail(
        submission=submission,
        student_display_name=display_name,
        student_username=username,
        feedback=get_learning_assets().list_feedback(submission.submission_id),
    )


def _student_labels(
    submissions: list[LearningSubmissionV1],
    *,
    context: AuthContext,
) -> dict[str, tuple[str, str | None]]:
    labels = {
        item.student_id: (item.student_id, None)
        for item in submissions
    }
    if context.principal.synthetic:
        labels[context.principal.user_id] = (
            context.principal.display_name,
            context.principal.username,
        )
        return labels
    try:
        users = get_identity().list_users()
    except AccountsModeRequired:
        return labels
    except AuthStoreError as exc:
        raise LearningAssetStoreError("student identity read failed") from exc
    for user in users:
        if user.user_id in labels:
            labels[user.user_id] = (user.display_name, user.username)
    return labels


def _raise_learning_asset_error(exc: Exception) -> None:
    if isinstance(exc, LearningSubmissionNotFound):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": exc.code,
                "message": "The submitted learning work was not found.",
            },
        ) from exc
    if isinstance(exc, LearningSubmissionConflict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": str(exc),
            },
        ) from exc
    if isinstance(
        exc,
        (LearningSubmissionIntegrityError, LearningFeedbackIntegrityError),
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": exc.code,
                "message": "Stored learning work failed integrity validation.",
            },
        ) from exc
    if isinstance(exc, (LearningAssetStoreError, RuntimeError)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": getattr(exc, "code", "learning_asset_unavailable"),
                "message": "Learning work storage is temporarily unavailable.",
            },
        ) from exc
    raise exc
