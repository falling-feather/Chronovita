from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    insert,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from services.contracts.learning_v1 import (
    LearningCanvasSnapshotV1,
    LearningFeedbackRequestV1,
    LearningFeedbackV1,
    LearningSubmissionRequestV1,
    LearningSubmissionV1,
    canonical_checksum,
    feedback_source_checksum,
    submission_source_checksum,
)


MAX_SUBMISSION_RECORD_BYTES = 4 * 1024 * 1024
MAX_FEEDBACK_RECORD_BYTES = 256 * 1024
MAX_WRITE_ATTEMPTS = 8


class LearningAssetStoreError(RuntimeError):
    code = "learning_asset_storage_unavailable"


class LearningSubmissionNotFound(LearningAssetStoreError):
    code = "learning_submission_not_found"


class LearningSubmissionConflict(LearningAssetStoreError):
    code = "learning_submission_conflict"


class LearningSubmissionIntegrityError(LearningAssetStoreError):
    code = "learning_submission_integrity_error"


class LearningFeedbackIntegrityError(LearningAssetStoreError):
    code = "learning_feedback_integrity_error"


@dataclass(frozen=True)
class SubmissionCreateResult:
    submission: LearningSubmissionV1
    reused: bool


@dataclass(frozen=True)
class FeedbackCreateResult:
    feedback: LearningFeedbackV1
    reused: bool


_METADATA = MetaData()

learning_submissions_table = Table(
    "learning_submissions",
    _METADATA,
    Column("submission_id", String(36), primary_key=True),
    Column("student_id", String(64), nullable=False),
    Column("course_id", String(64), nullable=False),
    Column("lesson_id", String(64), nullable=False),
    Column("version", Integer, nullable=False),
    Column("client_submission_id", String(64), nullable=False),
    Column("data", Text, nullable=False),
    Column("submitted_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "student_id",
        "course_id",
        "lesson_id",
        "version",
        name="uq_learning_submission_version",
    ),
    UniqueConstraint(
        "student_id",
        "client_submission_id",
        name="uq_learning_submission_client_id",
    ),
    Index(
        "ix_learning_submission_scope",
        "student_id",
        "course_id",
        "lesson_id",
    ),
    Index("ix_learning_submission_submitted_at", "submitted_at"),
)

learning_feedback_table = Table(
    "learning_feedback",
    _METADATA,
    Column("feedback_id", String(36), primary_key=True),
    Column("submission_id", String(36), nullable=False),
    Column("teacher_id", String(64), nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("client_feedback_id", String(64), nullable=False),
    Column("data", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "submission_id",
        "sequence",
        name="uq_learning_feedback_sequence",
    ),
    UniqueConstraint(
        "teacher_id",
        "client_feedback_id",
        name="uq_learning_feedback_client_id",
    ),
    Index("ix_learning_feedback_submission", "submission_id"),
    Index("ix_learning_feedback_created_at", "created_at"),
)


class LearningAssetStore:
    """Immutable student submissions and append-only teacher feedback."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create_submission(
        self,
        *,
        student_id: str,
        request: LearningSubmissionRequestV1,
        canvas: LearningCanvasSnapshotV1,
    ) -> SubmissionCreateResult:
        source_checksum = submission_source_checksum(request)
        submitted_at = datetime.now(timezone.utc)
        submission_id = f"sub_{uuid4().hex}"
        for _ in range(MAX_WRITE_ATTEMPTS):
            try:
                with self.engine.begin() as connection:
                    existing = connection.execute(
                        select(learning_submissions_table.c.data).where(
                            learning_submissions_table.c.student_id == student_id,
                            learning_submissions_table.c.client_submission_id
                            == request.client_submission_id,
                        )
                    ).scalar_one_or_none()
                    if existing is not None:
                        submission = decode_submission(existing)
                        _require_same_submission_payload(submission, source_checksum)
                        return SubmissionCreateResult(submission=submission, reused=True)

                    latest = connection.execute(
                        select(func.max(learning_submissions_table.c.version)).where(
                            learning_submissions_table.c.student_id == student_id,
                            learning_submissions_table.c.course_id == request.course_id,
                            learning_submissions_table.c.lesson_id == request.lesson_id,
                        )
                    ).scalar_one()
                    version = int(latest or 0) + 1
                    submission = _build_submission(
                        submission_id=submission_id,
                        student_id=student_id,
                        version=version,
                        request=request,
                        canvas=canvas,
                        submitted_at=submitted_at,
                        source_checksum=source_checksum,
                    )
                    raw_data = encode_submission(submission)
                    connection.execute(
                        insert(learning_submissions_table).values(
                            submission_id=submission.submission_id,
                            student_id=submission.student_id,
                            course_id=submission.course_id,
                            lesson_id=submission.lesson_id,
                            version=submission.version,
                            client_submission_id=submission.client_submission_id,
                            data=raw_data,
                            submitted_at=submission.submitted_at,
                        )
                    )
                return SubmissionCreateResult(submission=submission, reused=False)
            except IntegrityError:
                existing = self._load_submission_by_client_id(
                    student_id,
                    request.client_submission_id,
                )
                if existing is not None:
                    _require_same_submission_payload(existing, source_checksum)
                    return SubmissionCreateResult(submission=existing, reused=True)
                continue
            except (
                LearningSubmissionConflict,
                LearningSubmissionIntegrityError,
            ):
                raise
            except SQLAlchemyError as exc:
                raise LearningAssetStoreError(
                    "learning submission write failed"
                ) from exc
        raise LearningSubmissionConflict(
            "learning submission version changed repeatedly"
        )

    def list_student_submissions(
        self,
        student_id: str,
        *,
        course_id: str | None = None,
        lesson_id: str | None = None,
        limit: int = 100,
    ) -> list[LearningSubmissionV1]:
        conditions = [learning_submissions_table.c.student_id == student_id]
        if course_id is not None:
            conditions.append(learning_submissions_table.c.course_id == course_id)
        if lesson_id is not None:
            conditions.append(learning_submissions_table.c.lesson_id == lesson_id)
        return self._list_submissions(conditions=conditions, limit=limit)

    def list_submissions(
        self,
        *,
        student_id: str | None = None,
        course_id: str | None = None,
        lesson_id: str | None = None,
        limit: int = 100,
    ) -> list[LearningSubmissionV1]:
        conditions = []
        if student_id is not None:
            conditions.append(learning_submissions_table.c.student_id == student_id)
        if course_id is not None:
            conditions.append(learning_submissions_table.c.course_id == course_id)
        if lesson_id is not None:
            conditions.append(learning_submissions_table.c.lesson_id == lesson_id)
        return self._list_submissions(conditions=conditions, limit=limit)

    def load_student_submission(
        self,
        submission_id: str,
        student_id: str,
    ) -> LearningSubmissionV1:
        return self._load_submission(
            submission_id,
            student_id=student_id,
        )

    def load_submission(self, submission_id: str) -> LearningSubmissionV1:
        return self._load_submission(submission_id)

    def create_feedback(
        self,
        *,
        submission_id: str,
        teacher_id: str,
        teacher_display_name: str,
        request: LearningFeedbackRequestV1,
    ) -> FeedbackCreateResult:
        source_checksum = feedback_source_checksum(request)
        created_at = datetime.now(timezone.utc)
        feedback_id = f"fbk_{uuid4().hex}"
        for _ in range(MAX_WRITE_ATTEMPTS):
            try:
                with self.engine.begin() as connection:
                    if connection.execute(
                        select(learning_submissions_table.c.submission_id).where(
                            learning_submissions_table.c.submission_id == submission_id
                        )
                    ).scalar_one_or_none() is None:
                        raise LearningSubmissionNotFound("learning submission not found")

                    existing = connection.execute(
                        select(learning_feedback_table.c.data).where(
                            learning_feedback_table.c.teacher_id == teacher_id,
                            learning_feedback_table.c.client_feedback_id
                            == request.client_feedback_id,
                        )
                    ).scalar_one_or_none()
                    if existing is not None:
                        feedback = decode_feedback(existing)
                        _require_same_feedback_payload(
                            feedback,
                            submission_id=submission_id,
                            source_checksum=source_checksum,
                        )
                        return FeedbackCreateResult(feedback=feedback, reused=True)

                    latest = connection.execute(
                        select(func.max(learning_feedback_table.c.sequence)).where(
                            learning_feedback_table.c.submission_id == submission_id
                        )
                    ).scalar_one()
                    sequence = int(latest or 0) + 1
                    feedback = _build_feedback(
                        feedback_id=feedback_id,
                        submission_id=submission_id,
                        teacher_id=teacher_id,
                        teacher_display_name=teacher_display_name,
                        sequence=sequence,
                        request=request,
                        created_at=created_at,
                        source_checksum=source_checksum,
                    )
                    raw_data = encode_feedback(feedback)
                    connection.execute(
                        insert(learning_feedback_table).values(
                            feedback_id=feedback.feedback_id,
                            submission_id=feedback.submission_id,
                            teacher_id=feedback.teacher_id,
                            sequence=feedback.sequence,
                            client_feedback_id=feedback.client_feedback_id,
                            data=raw_data,
                            created_at=feedback.created_at,
                        )
                    )
                return FeedbackCreateResult(feedback=feedback, reused=False)
            except IntegrityError:
                existing = self._load_feedback_by_client_id(
                    teacher_id,
                    request.client_feedback_id,
                )
                if existing is not None:
                    _require_same_feedback_payload(
                        existing,
                        submission_id=submission_id,
                        source_checksum=source_checksum,
                    )
                    return FeedbackCreateResult(feedback=existing, reused=True)
                continue
            except (
                LearningSubmissionNotFound,
                LearningSubmissionConflict,
                LearningSubmissionIntegrityError,
                LearningFeedbackIntegrityError,
            ):
                raise
            except SQLAlchemyError as exc:
                raise LearningAssetStoreError("learning feedback write failed") from exc
        raise LearningSubmissionConflict(
            "learning feedback sequence changed repeatedly"
        )

    def list_feedback(self, submission_id: str) -> list[LearningFeedbackV1]:
        try:
            with self.engine.connect() as connection:
                rows = connection.execute(
                    select(learning_feedback_table.c.data)
                    .where(learning_feedback_table.c.submission_id == submission_id)
                    .order_by(learning_feedback_table.c.sequence)
                ).scalars().all()
        except SQLAlchemyError as exc:
            raise LearningAssetStoreError("learning feedback read failed") from exc
        return [decode_feedback(item) for item in rows]

    def _list_submissions(
        self,
        *,
        conditions: list,
        limit: int,
    ) -> list[LearningSubmissionV1]:
        statement = select(learning_submissions_table.c.data)
        if conditions:
            statement = statement.where(*conditions)
        statement = statement.order_by(
            learning_submissions_table.c.submitted_at.desc(),
            learning_submissions_table.c.submission_id.desc(),
        ).limit(limit)
        try:
            with self.engine.connect() as connection:
                rows = connection.execute(statement).scalars().all()
        except SQLAlchemyError as exc:
            raise LearningAssetStoreError("learning submission list failed") from exc
        return [decode_submission(item) for item in rows]

    def _load_submission(
        self,
        submission_id: str,
        *,
        student_id: str | None = None,
    ) -> LearningSubmissionV1:
        statement = select(learning_submissions_table.c.data).where(
            learning_submissions_table.c.submission_id == submission_id
        )
        if student_id is not None:
            statement = statement.where(
                learning_submissions_table.c.student_id == student_id
            )
        try:
            with self.engine.connect() as connection:
                raw_data = connection.execute(statement).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise LearningAssetStoreError("learning submission read failed") from exc
        if raw_data is None:
            raise LearningSubmissionNotFound("learning submission not found")
        return decode_submission(raw_data)

    def _load_submission_by_client_id(
        self,
        student_id: str,
        client_submission_id: str,
    ) -> LearningSubmissionV1 | None:
        try:
            with self.engine.connect() as connection:
                raw_data = connection.execute(
                    select(learning_submissions_table.c.data).where(
                        learning_submissions_table.c.student_id == student_id,
                        learning_submissions_table.c.client_submission_id
                        == client_submission_id,
                    )
                ).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise LearningAssetStoreError("learning submission read failed") from exc
        return decode_submission(raw_data) if raw_data is not None else None

    def _load_feedback_by_client_id(
        self,
        teacher_id: str,
        client_feedback_id: str,
    ) -> LearningFeedbackV1 | None:
        try:
            with self.engine.connect() as connection:
                raw_data = connection.execute(
                    select(learning_feedback_table.c.data).where(
                        learning_feedback_table.c.teacher_id == teacher_id,
                        learning_feedback_table.c.client_feedback_id
                        == client_feedback_id,
                    )
                ).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise LearningAssetStoreError("learning feedback read failed") from exc
        return decode_feedback(raw_data) if raw_data is not None else None


def encode_submission(submission: LearningSubmissionV1) -> str:
    raw_data = _canonical_json(submission.model_dump(mode="json"))
    if len(raw_data.encode("utf-8")) > MAX_SUBMISSION_RECORD_BYTES:
        raise LearningSubmissionIntegrityError("learning submission is too large")
    return raw_data


def decode_submission(raw_data: object) -> LearningSubmissionV1:
    if not isinstance(raw_data, str):
        raise LearningSubmissionIntegrityError("learning submission is not text")
    if len(raw_data.encode("utf-8")) > MAX_SUBMISSION_RECORD_BYTES:
        raise LearningSubmissionIntegrityError("learning submission is too large")
    try:
        return LearningSubmissionV1.model_validate_json(raw_data)
    except (ValidationError, ValueError) as exc:
        raise LearningSubmissionIntegrityError(
            "learning submission failed integrity validation"
        ) from exc


def encode_feedback(feedback: LearningFeedbackV1) -> str:
    raw_data = _canonical_json(feedback.model_dump(mode="json"))
    if len(raw_data.encode("utf-8")) > MAX_FEEDBACK_RECORD_BYTES:
        raise LearningFeedbackIntegrityError("learning feedback is too large")
    return raw_data


def decode_feedback(raw_data: object) -> LearningFeedbackV1:
    if not isinstance(raw_data, str):
        raise LearningFeedbackIntegrityError("learning feedback is not text")
    if len(raw_data.encode("utf-8")) > MAX_FEEDBACK_RECORD_BYTES:
        raise LearningFeedbackIntegrityError("learning feedback is too large")
    try:
        return LearningFeedbackV1.model_validate_json(raw_data)
    except (ValidationError, ValueError) as exc:
        raise LearningFeedbackIntegrityError(
            "learning feedback failed integrity validation"
        ) from exc


def _build_submission(
    *,
    submission_id: str,
    student_id: str,
    version: int,
    request: LearningSubmissionRequestV1,
    canvas: LearningCanvasSnapshotV1,
    submitted_at: datetime,
    source_checksum: str,
) -> LearningSubmissionV1:
    payload = {
        "schema_version": "learning-submission/v1",
        "submission_id": submission_id,
        "client_submission_id": request.client_submission_id,
        "student_id": student_id,
        "course_id": request.course_id,
        "lesson_id": request.lesson_id,
        "version": version,
        "title": request.title,
        "body_markdown": request.body_markdown,
        "sticky_notes": [item.model_dump(mode="json") for item in request.sticky_notes],
        "drawing_strokes": [
            item.model_dump(mode="json") for item in request.drawing_strokes
        ],
        "learning_events": [
            item.model_dump(mode="json") for item in request.learning_events
        ],
        "canvas": canvas.model_dump(mode="json"),
        "local_draft_updated_at": _json_datetime(request.local_draft_updated_at),
        "submitted_at": _json_datetime(submitted_at),
        "source_payload_checksum": source_checksum,
    }
    payload["checksum"] = canonical_checksum(payload)
    return LearningSubmissionV1.model_validate(payload)


def _build_feedback(
    *,
    feedback_id: str,
    submission_id: str,
    teacher_id: str,
    teacher_display_name: str,
    sequence: int,
    request: LearningFeedbackRequestV1,
    created_at: datetime,
    source_checksum: str,
) -> LearningFeedbackV1:
    payload = {
        "schema_version": "learning-feedback/v1",
        "feedback_id": feedback_id,
        "client_feedback_id": request.client_feedback_id,
        "submission_id": submission_id,
        "sequence": sequence,
        "teacher_id": teacher_id,
        "teacher_display_name": teacher_display_name,
        "completion_status": request.completion_status,
        "comment": request.comment,
        "created_at": _json_datetime(created_at),
        "source_payload_checksum": source_checksum,
    }
    payload["checksum"] = canonical_checksum(payload)
    return LearningFeedbackV1.model_validate(payload)


def _require_same_submission_payload(
    submission: LearningSubmissionV1,
    source_checksum: str,
) -> None:
    if submission.source_payload_checksum != source_checksum:
        raise LearningSubmissionConflict(
            "client submission id was already used for different content"
        )


def _require_same_feedback_payload(
    feedback: LearningFeedbackV1,
    *,
    submission_id: str,
    source_checksum: str,
) -> None:
    if (
        feedback.submission_id != submission_id
        or feedback.source_payload_checksum != source_checksum
    ):
        raise LearningSubmissionConflict(
            "client feedback id was already used for different content"
        )


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _json_datetime(value: datetime) -> str:
    rendered = value.isoformat()
    return rendered[:-6] + "Z" if rendered.endswith("+00:00") else rendered


__all__ = [
    "FeedbackCreateResult",
    "LearningAssetStore",
    "LearningAssetStoreError",
    "LearningFeedbackIntegrityError",
    "LearningSubmissionConflict",
    "LearningSubmissionIntegrityError",
    "LearningSubmissionNotFound",
    "SubmissionCreateResult",
    "decode_feedback",
    "decode_submission",
    "encode_feedback",
    "encode_submission",
    "learning_feedback_table",
    "learning_submissions_table",
]
