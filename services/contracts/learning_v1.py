from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from services.contracts.v1 import Checksum, ContractId


SubmissionId = Annotated[
    str,
    StringConstraints(pattern=r"^sub_[a-f0-9]{32}$"),
]
FeedbackId = Annotated[
    str,
    StringConstraints(pattern=r"^fbk_[a-f0-9]{32}$"),
]
UserId = Annotated[
    str,
    StringConstraints(min_length=2, max_length=64),
]
LearningEventKind = Literal[
    "stage_entered",
    "keyword_opened",
    "decision_completed",
    "question_answered",
    "temporary_note_saved",
]
LearningCompletionStatus = Literal["in_review", "changes_requested", "completed"]
StickyColor = Literal["ochre", "jade", "cinnabar"]
StrokeMode = Literal["ink", "erase"]
MetadataValue = str | int | float | bool | None


class LearningContract(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        str_strip_whitespace=True,
    )


class LearningStickyNoteV1(LearningContract):
    note_id: str = Field(min_length=1, max_length=160)
    body: str = Field(max_length=1_000)
    color: StickyColor = "ochre"


class LearningPointV1(LearningContract):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class LearningStrokeV1(LearningContract):
    stroke_id: str = Field(min_length=1, max_length=160)
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    width: float = Field(ge=1, le=24)
    mode: StrokeMode = "ink"
    points: tuple[LearningPointV1, ...] = Field(min_length=1, max_length=20_000)


class LearningEventSnapshotV1(LearningContract):
    event_id: str = Field(min_length=1, max_length=160)
    kind: LearningEventKind
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=1_200)
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)
    occurred_at: AwareDatetime

    @field_validator("metadata")
    @classmethod
    def validate_metadata(
        cls,
        value: dict[str, MetadataValue],
    ) -> dict[str, MetadataValue]:
        if len(value) > 20:
            raise ValueError("learning event metadata has too many fields")
        for key, item in value.items():
            if not key.strip() or len(key) > 80:
                raise ValueError("learning event metadata key is invalid")
            if isinstance(item, str) and len(item) > 600:
                raise ValueError("learning event metadata text is too long")
        return value


class LearningSubmissionRequestV1(LearningContract):
    schema_version: Literal["learning-submission-request/v1"] = (
        "learning-submission-request/v1"
    )
    client_submission_id: ContractId
    course_id: ContractId
    lesson_id: ContractId
    title: str = Field(min_length=1, max_length=160)
    body_markdown: str = Field(default="", max_length=60_000)
    sticky_notes: tuple[LearningStickyNoteV1, ...] = Field(
        default_factory=tuple,
        max_length=24,
    )
    drawing_strokes: tuple[LearningStrokeV1, ...] = Field(
        default_factory=tuple,
        max_length=600,
    )
    learning_events: tuple[LearningEventSnapshotV1, ...] = Field(
        default_factory=tuple,
        max_length=240,
    )
    local_draft_updated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_material(self) -> "LearningSubmissionRequestV1":
        if len({item.note_id for item in self.sticky_notes}) != len(self.sticky_notes):
            raise ValueError("sticky note ids must be unique")
        if len({item.stroke_id for item in self.drawing_strokes}) != len(
            self.drawing_strokes
        ):
            raise ValueError("drawing stroke ids must be unique")
        if len({item.event_id for item in self.learning_events}) != len(
            self.learning_events
        ):
            raise ValueError("learning event ids must be unique")
        if sum(len(item.points) for item in self.drawing_strokes) > 20_000:
            raise ValueError("drawing point budget exceeded")
        has_content = bool(
            self.body_markdown.strip()
            or any(item.body.strip() for item in self.sticky_notes)
            or self.drawing_strokes
            or self.learning_events
        )
        if not has_content:
            raise ValueError("a learning submission must contain student work")
        return self


class LearningCanvasSnapshotV1(LearningContract):
    schema_version: Literal["learning-canvas-snapshot/v1"] = (
        "learning-canvas-snapshot/v1"
    )
    found: bool
    revision: int = Field(ge=0)
    nodes: tuple[dict[str, Any], ...] = Field(default_factory=tuple, max_length=500)
    edges: tuple[dict[str, Any], ...] = Field(default_factory=tuple, max_length=1_000)

    @model_validator(mode="after")
    def validate_presence(self) -> "LearningCanvasSnapshotV1":
        if not self.found and (self.revision != 0 or self.nodes or self.edges):
            raise ValueError("an absent canvas snapshot must be empty")
        if self.found and self.revision < 1:
            raise ValueError("a present canvas snapshot requires a revision")
        return self


class LearningSubmissionV1(LearningContract):
    schema_version: Literal["learning-submission/v1"] = "learning-submission/v1"
    submission_id: SubmissionId
    client_submission_id: ContractId
    student_id: UserId
    course_id: ContractId
    lesson_id: ContractId
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=160)
    body_markdown: str = Field(default="", max_length=60_000)
    sticky_notes: tuple[LearningStickyNoteV1, ...] = Field(
        default_factory=tuple,
        max_length=24,
    )
    drawing_strokes: tuple[LearningStrokeV1, ...] = Field(
        default_factory=tuple,
        max_length=600,
    )
    learning_events: tuple[LearningEventSnapshotV1, ...] = Field(
        default_factory=tuple,
        max_length=240,
    )
    canvas: LearningCanvasSnapshotV1
    local_draft_updated_at: AwareDatetime
    submitted_at: AwareDatetime
    source_payload_checksum: Checksum
    checksum: Checksum

    @model_validator(mode="after")
    def validate_checksums(self) -> "LearningSubmissionV1":
        source_payload = _submission_source_payload(self)
        if self.source_payload_checksum != canonical_checksum(source_payload):
            raise ValueError("learning submission source payload checksum is invalid")
        if self.checksum != canonical_checksum(
            self.model_dump(mode="json", exclude={"checksum"})
        ):
            raise ValueError("learning submission checksum is invalid")
        return self


class LearningFeedbackRequestV1(LearningContract):
    schema_version: Literal["learning-feedback-request/v1"] = (
        "learning-feedback-request/v1"
    )
    client_feedback_id: ContractId
    completion_status: LearningCompletionStatus
    comment: str = Field(min_length=1, max_length=4_000)


class LearningFeedbackV1(LearningContract):
    schema_version: Literal["learning-feedback/v1"] = "learning-feedback/v1"
    feedback_id: FeedbackId
    client_feedback_id: ContractId
    submission_id: SubmissionId
    sequence: int = Field(ge=1)
    teacher_id: UserId
    teacher_display_name: str = Field(min_length=1, max_length=80)
    completion_status: LearningCompletionStatus
    comment: str = Field(min_length=1, max_length=4_000)
    created_at: AwareDatetime
    source_payload_checksum: Checksum
    checksum: Checksum

    @model_validator(mode="after")
    def validate_checksums(self) -> "LearningFeedbackV1":
        source_payload = _feedback_source_payload(self)
        if self.source_payload_checksum != canonical_checksum(source_payload):
            raise ValueError("learning feedback source payload checksum is invalid")
        if self.checksum != canonical_checksum(
            self.model_dump(mode="json", exclude={"checksum"})
        ):
            raise ValueError("learning feedback checksum is invalid")
        return self


def submission_source_checksum(request: LearningSubmissionRequestV1) -> Checksum:
    return canonical_checksum(
        {
            "schema_version": "learning-submission-request/v1",
            "client_submission_id": request.client_submission_id,
            "course_id": request.course_id,
            "lesson_id": request.lesson_id,
            "title": request.title,
            "body_markdown": request.body_markdown,
            "sticky_notes": [
                item.model_dump(mode="json") for item in request.sticky_notes
            ],
            "drawing_strokes": [
                item.model_dump(mode="json") for item in request.drawing_strokes
            ],
            "learning_events": [
                item.model_dump(mode="json") for item in request.learning_events
            ],
            "local_draft_updated_at": request.local_draft_updated_at.isoformat(),
        }
    )


def feedback_source_checksum(request: LearningFeedbackRequestV1) -> Checksum:
    return canonical_checksum(request.model_dump(mode="json"))


def canonical_checksum(payload: object) -> Checksum:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _submission_source_payload(submission: LearningSubmissionV1) -> dict[str, Any]:
    return {
        "schema_version": "learning-submission-request/v1",
        "client_submission_id": submission.client_submission_id,
        "course_id": submission.course_id,
        "lesson_id": submission.lesson_id,
        "title": submission.title,
        "body_markdown": submission.body_markdown,
        "sticky_notes": [item.model_dump(mode="json") for item in submission.sticky_notes],
        "drawing_strokes": [
            item.model_dump(mode="json") for item in submission.drawing_strokes
        ],
        "learning_events": [
            item.model_dump(mode="json") for item in submission.learning_events
        ],
        "local_draft_updated_at": submission.local_draft_updated_at.isoformat(),
    }


def _feedback_source_payload(feedback: LearningFeedbackV1) -> dict[str, Any]:
    return {
        "schema_version": "learning-feedback-request/v1",
        "client_feedback_id": feedback.client_feedback_id,
        "completion_status": feedback.completion_status,
        "comment": feedback.comment,
    }


__all__ = [
    "FeedbackId",
    "LearningCanvasSnapshotV1",
    "LearningCompletionStatus",
    "LearningEventSnapshotV1",
    "LearningFeedbackRequestV1",
    "LearningFeedbackV1",
    "LearningPointV1",
    "LearningStickyNoteV1",
    "LearningStrokeV1",
    "LearningSubmissionRequestV1",
    "LearningSubmissionV1",
    "SubmissionId",
    "canonical_checksum",
    "feedback_source_checksum",
    "submission_source_checksum",
]
