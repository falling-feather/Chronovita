from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock, local
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from services import content as content_data
from services.contracts.v1 import (
    CoursePackageV1,
    course_package_from_legacy,
    verify_contract_checksum,
)


Checksum = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
ContractId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=2,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]+$",
    ),
]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
WorkflowState = Literal[
    "draft",
    "validated",
    "in_review",
    "changes_requested",
    "approved",
    "sealed",
    "published",
]
WorkflowAction = Literal[
    "save",
    "validation_passed",
    "validation_failed",
    "submit_review",
    "request_changes",
    "approve",
    "seal",
    "bootstrap",
    "publish",
    "rollback",
]
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$")
_RELEASE_ID_PATTERN = re.compile(r"^rel-[0-9a-f]{10}-\d{4,}$")
_LOCK = RLock()
_FILE_LOCK_STATE = local()


class ContentWorkflowError(RuntimeError):
    code = "content_workflow_error"


class ContentNotFound(ContentWorkflowError):
    code = "content_not_found"


class ContentConflict(ContentWorkflowError):
    code = "content_conflict"


class InvalidTransition(ContentWorkflowError):
    code = "invalid_content_transition"


class ContentValidationFailed(ContentWorkflowError):
    code = "content_validation_failed"

    def __init__(self, message: str, report: ContentValidationReport | None = None):
        super().__init__(message)
        self.report = report


class LifecycleModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ValidationIssue(LifecycleModel):
    code: NonEmptyText
    severity: Literal["error", "warning"]
    field: NonEmptyText
    message: NonEmptyText


class ContentValidationReport(LifecycleModel):
    schema_version: Literal["content-validation/v1"] = "content-validation/v1"
    validator_version: Literal["course-minimum/v1"] = "course-minimum/v1"
    lesson_id: ContractId
    draft_fingerprint: Checksum
    valid: bool
    issues: tuple[ValidationIssue, ...] = ()
    validated_at: AwareDatetime
    validated_by: NonEmptyText

    @model_validator(mode="after")
    def validate_result(self) -> "ContentValidationReport":
        has_errors = any(issue.severity == "error" for issue in self.issues)
        if self.valid == has_errors:
            raise ValueError("valid must be true exactly when no error issues exist")
        return self


class WorkflowEvent(LifecycleModel):
    sequence: int = Field(ge=1)
    action: WorkflowAction
    from_state: WorkflowState
    to_state: WorkflowState
    actor: NonEmptyText
    note: str = ""
    occurred_at: AwareDatetime
    draft_fingerprint: Checksum | None = None
    sealed_version: int | None = Field(default=None, ge=1)
    release_id: str | None = None


class ContentWorkflowRecord(LifecycleModel):
    schema_version: Literal["content-workflow/v1"] = "content-workflow/v1"
    lesson_id: ContractId
    course_id: ContractId
    state: WorkflowState = "draft"
    revision: int = Field(ge=1)
    draft_fingerprint: Checksum
    validation: ContentValidationReport | None = None
    sealed_version: int | None = Field(default=None, ge=1)
    sealed_checksum: Checksum | None = None
    published_course_id: ContractId | None = None
    published_version: int | None = Field(default=None, ge=1)
    published_release_id: str | None = None
    updated_at: AwareDatetime
    history: tuple[WorkflowEvent, ...] = ()
    checksum: Checksum

    @model_validator(mode="after")
    def validate_record(self) -> "ContentWorkflowRecord":
        sequences = [event.sequence for event in self.history]
        if sequences != list(range(1, len(self.history) + 1)):
            raise ValueError("workflow history must use contiguous sequence numbers")
        if self.revision != len(self.history):
            raise ValueError("workflow revision must equal the number of audit events")
        previous_state: WorkflowState = "draft"
        for event in self.history:
            if event.from_state != previous_state:
                raise ValueError("workflow event states must form a continuous chain")
            previous_state = event.to_state
        if not self.history or previous_state != self.state:
            raise ValueError("workflow state must match the final audit event")
        if self.history[-1].draft_fingerprint != self.draft_fingerprint:
            raise ValueError("latest audit event must reference the current draft")
        if self.validation is not None and (
            self.validation.lesson_id != self.lesson_id
            or self.validation.draft_fingerprint != self.draft_fingerprint
        ):
            raise ValueError("validation report must belong to the current draft")
        if self.state in {"validated", "in_review", "changes_requested", "approved"} and (
            self.validation is None or not self.validation.valid
        ):
            raise ValueError("review states require a passing validation report")
        if (self.sealed_version is None) != (self.sealed_checksum is None):
            raise ValueError("sealed version and checksum must be stored together")
        if self.state in {"sealed", "published"} and self.sealed_version is None:
            raise ValueError("sealed and published states require a sealed artifact")
        publication = (
            self.published_course_id,
            self.published_version,
            self.published_release_id,
        )
        if any(item is None for item in publication) and any(item is not None for item in publication):
            raise ValueError("published course, version and release must be stored together")
        if self.state == "published" and self.published_release_id is None:
            raise ValueError("published state requires publication identity")
        return self


class ReleaseItem(LifecycleModel):
    lesson_id: ContractId
    course_id: ContractId
    content_version: int = Field(ge=1)
    source_path: NonEmptyText
    source_checksum: Checksum
    package_path: NonEmptyText
    package_checksum: Checksum
    package_schema: Literal["course-package/v1"] = "course-package/v1"


class LegacyReleaseSelection(LifecycleModel):
    lesson_id: ContractId
    content_version: int = Field(ge=1)


class CourseReleaseManifest(LifecycleModel):
    schema_version: Literal["course-release/v1"] = "course-release/v1"
    release_id: NonEmptyText
    release_no: int = Field(ge=1)
    course_id: ContractId
    operation: Literal["bootstrap", "publish", "rollback"]
    parent_release_id: str | None = None
    restored_from_release_id: str | None = None
    created_at: AwareDatetime
    created_by: NonEmptyText
    note: str = ""
    items: tuple[ReleaseItem, ...] = ()
    checksum: Checksum

    @model_validator(mode="after")
    def validate_manifest(self) -> "CourseReleaseManifest":
        if not _RELEASE_ID_PATTERN.fullmatch(self.release_id):
            raise ValueError("invalid release_id")
        if int(self.release_id.rsplit("-", 1)[1]) != self.release_no:
            raise ValueError("release_id sequence must match release_no")
        lesson_ids = [item.lesson_id for item in self.items]
        if lesson_ids != sorted(set(lesson_ids)):
            raise ValueError("release items must be unique and sorted by lesson_id")
        if any(item.course_id != self.course_id for item in self.items):
            raise ValueError("every release item must belong to manifest.course_id")
        if self.operation == "bootstrap" and self.parent_release_id is not None:
            raise ValueError("bootstrap releases cannot have a parent")
        if self.operation == "publish" and self.parent_release_id is None:
            raise ValueError("publish releases require a parent")
        if self.operation == "rollback" and self.restored_from_release_id is None:
            raise ValueError("rollback releases require restored_from_release_id")
        if self.operation == "rollback" and self.parent_release_id is None:
            raise ValueError("rollback releases require a parent")
        if self.operation != "rollback" and self.restored_from_release_id is not None:
            raise ValueError("only rollback releases may restore another release")
        return self


class ActiveReleasePointer(LifecycleModel):
    schema_version: Literal["course-release-pointer/v1"] = "course-release-pointer/v1"
    course_id: ContractId
    release_id: NonEmptyText
    release_no: int = Field(ge=1)
    manifest_path: NonEmptyText
    manifest_checksum: Checksum
    generation: int = Field(ge=1)
    previous_release_id: str | None = None
    activated_at: AwareDatetime
    activated_by: NonEmptyText
    checksum: Checksum

    @model_validator(mode="after")
    def validate_pointer(self) -> "ActiveReleasePointer":
        if not _RELEASE_ID_PATTERN.fullmatch(self.release_id):
            raise ValueError("invalid release_id")
        if int(self.release_id.rsplit("-", 1)[1]) != self.release_no:
            raise ValueError("release_id sequence must match release_no")
        if self.generation == 1 and self.previous_release_id is not None:
            raise ValueError("first pointer generation cannot have a previous release")
        if self.generation > 1 and self.previous_release_id is None:
            raise ValueError("later pointer generations require a previous release")
        return self


class PublishedCourseSnapshot(LifecycleModel):
    package: CoursePackageV1
    release_id: str | None = None
    release_no: int | None = Field(default=None, ge=1)
    release_checksum: Checksum | None = None

    @model_validator(mode="after")
    def validate_release_identity(self) -> "PublishedCourseSnapshot":
        release_identity = (self.release_id, self.release_no, self.release_checksum)
        if any(item is None for item in release_identity) and any(
            item is not None for item in release_identity
        ):
            raise ValueError("release id, number and checksum must be stored together")
        return self


class ReleaseTransactionJournal(LifecycleModel):
    schema_version: Literal["course-release-transaction/v1"] = (
        "course-release-transaction/v1"
    )
    course_id: ContractId
    manifest: CourseReleaseManifest
    pointer: ActiveReleasePointer
    previous_pointer: ActiveReleasePointer | None = None
    original_workflows: tuple[ContentWorkflowRecord, ...] = ()
    updated_workflows: tuple[ContentWorkflowRecord, ...] = ()
    cleanup_paths: tuple[NonEmptyText, ...]
    prepared_at: AwareDatetime
    checksum: Checksum

    @model_validator(mode="after")
    def validate_transaction(self) -> "ReleaseTransactionJournal":
        if (
            self.manifest.course_id != self.course_id
            or self.pointer.course_id != self.course_id
            or self.pointer.release_id != self.manifest.release_id
            or self.pointer.manifest_checksum != self.manifest.checksum
        ):
            raise ValueError("release transaction identities must agree")
        if self.previous_pointer and self.previous_pointer.course_id != self.course_id:
            raise ValueError("previous pointer belongs to another course")
        original_ids = [record.lesson_id for record in self.original_workflows]
        updated_ids = [record.lesson_id for record in self.updated_workflows]
        if original_ids != sorted(set(original_ids)):
            raise ValueError("original workflow records must be unique and sorted")
        if updated_ids != sorted(set(updated_ids)):
            raise ValueError("updated workflow records must be unique and sorted")
        if not set(updated_ids).issubset(original_ids):
            raise ValueError("updated workflows require a matching original record")
        if not self.cleanup_paths:
            raise ValueError("release transaction must identify cleanup paths")
        return self


def record_draft_saved(
    draft: content_data.LessonContentPackage,
    *,
    actor: str,
) -> ContentWorkflowRecord:
    with _workflow_operation_lock():
        existing = _load_workflow(draft.lesson_id, required=False)
        now = _now()
        fingerprint = content_data.draft_fingerprint(draft)
        content_unchanged = bool(
            existing
            and existing.course_id == draft.course_id
            and existing.draft_fingerprint == fingerprint
        )
        state: WorkflowState = existing.state if content_unchanged and existing else "draft"
        event = WorkflowEvent(
            sequence=(len(existing.history) + 1 if existing else 1),
            action="save",
            from_state=(existing.state if existing else "draft"),
            to_state=state,
            actor=_actor(actor),
            note=(
                "Draft saved without substantive content changes."
                if content_unchanged
                else "Draft changed; prior validation and approval are no longer authoritative."
            ),
            occurred_at=now,
            draft_fingerprint=fingerprint,
        )
        record = ContentWorkflowRecord(
            lesson_id=draft.lesson_id,
            course_id=draft.course_id,
            state=state,
            revision=(existing.revision + 1 if existing else 1),
            draft_fingerprint=fingerprint,
            validation=(existing.validation if content_unchanged and existing else None),
            sealed_version=(existing.sealed_version if existing else None),
            sealed_checksum=(existing.sealed_checksum if existing else None),
            published_course_id=(existing.published_course_id if existing else None),
            published_version=(existing.published_version if existing else None),
            published_release_id=(existing.published_release_id if existing else None),
            updated_at=now,
            history=[*(existing.history if existing else []), event],
            checksum="0" * 64,
        )
        return _write_workflow(_sign(record, ContentWorkflowRecord))


def get_workflow(lesson_id: str) -> ContentWorkflowRecord | None:
    with _LOCK:
        return _load_workflow(lesson_id, required=False)


def validate_draft(lesson_id: str, *, actor: str) -> ContentWorkflowRecord:
    with _workflow_operation_lock():
        draft, record = _current_draft_and_record(lesson_id, actor)
        report = validate_package(draft, actor=actor)
        state: WorkflowState = "validated" if report.valid else "draft"
        action: WorkflowAction = "validation_passed" if report.valid else "validation_failed"
        note = "Minimum content validation passed." if report.valid else "Blocking validation issues remain."
        return _transition(
            record,
            state=state,
            action=action,
            actor=actor,
            note=note,
            validation=report,
        )


def validate_package(
    package: content_data.LessonContentPackage,
    *,
    actor: str,
) -> ContentValidationReport:
    issues: list[ValidationIssue] = []

    def add(code: str, severity: Literal["error", "warning"], field: str, message: str) -> None:
        issues.append(ValidationIssue(code=code, severity=severity, field=field, message=message))

    for field, value in (
        ("title", package.title),
        ("unit", package.unit),
        ("era", package.era),
    ):
        if not _has_text(value):
            add("required_text", "error", field, f"{field} must contain visible text.")

    body = [item for item in package.body if _has_text(item)]
    if not body:
        add("body_required", "error", "body", "At least one non-empty lesson paragraph is required.")
    elif len(body) < 3:
        add("body_depth", "warning", "body", "A production lesson should usually contain at least three paragraphs.")

    if not package.keywords:
        add("keywords_required", "error", "keywords", "At least one keyword is required.")
    for index, keyword in enumerate(package.keywords):
        if not _has_text(keyword.word) or not _has_text(keyword.gloss):
            add(
                "keyword_incomplete",
                "error",
                f"keywords.{index}",
                "Each keyword requires both word and student-facing gloss.",
            )
    if 0 < len(package.keywords) < 5:
        add("keyword_depth", "warning", "keywords", "A main lesson should usually provide five keywords.")
    _add_duplicate_warning(
        [item.word for item in package.keywords],
        "keywords",
        "duplicate_keywords",
        add,
    )

    if not package.people:
        add("people_required", "error", "people", "At least one related historical person is required.")
    for index, person in enumerate(package.people):
        if not _has_text(person.name) or not _has_text(person.summary):
            add(
                "person_incomplete",
                "error",
                f"people.{index}",
                "Each person requires a name and student-facing summary.",
            )
        if not _has_text(person.persona) or not person.boundaries:
            add(
                "person_ai_boundary",
                "warning",
                f"people.{index}",
                "Persona and historical boundaries should be completed before AI character use.",
            )
    if 0 < len(package.people) < 2:
        add("people_depth", "warning", "people", "A main lesson should usually provide two people.")
    _add_duplicate_warning(
        [item.name for item in package.people],
        "people",
        "duplicate_people",
        add,
    )

    facts = [item for item in package.facts if _has_text(item)]
    if not facts:
        add("facts_required", "error", "facts", "At least one historical fact boundary is required.")
    elif len(facts) < 5:
        add("facts_depth", "warning", "facts", "A main lesson should usually provide five facts.")

    if not package.source_refs:
        add("sources_required", "error", "source_refs", "At least one reviewable source is required.")
    for index, source in enumerate(package.source_refs):
        if not _has_text(source.title) or not (
            _has_text(source.source) or _has_text(source.url_or_path)
        ):
            add(
                "source_incomplete",
                "error",
                f"source_refs.{index}",
                "Each source requires a title and publisher or URL/path.",
            )
        if source.reliability not in {"pending", "reviewed", "disputed"}:
            add(
                "source_reliability",
                "error",
                f"source_refs.{index}.reliability",
                "Source reliability must be pending, reviewed or disputed.",
            )
    if 0 < len(package.source_refs) < 2:
        add("sources_depth", "warning", "source_refs", "A main lesson should usually provide two sources.")

    if not any(_has_text(item) for item in package.qa_points):
        add("qa_points_missing", "warning", "qa_points", "Add question-answer knowledge points for later AI use.")
    if not any(_has_text(item) for item in package.level_goals):
        add("level_goals_missing", "warning", "level_goals", "Add at least one learning or level goal.")
    if not package.map_points:
        add("map_points_missing", "warning", "map_points", "Add map points when the lesson has spatial context.")
    if not (
        _has_text(package.saga_material.objective)
        or _has_text(package.sandbox_material.objective)
    ):
        add(
            "interactive_objective_missing",
            "warning",
            "saga_material",
            "Reserve a saga or sandbox objective for later interactive learning.",
        )

    try:
        course_package_from_legacy(package)
    except (TypeError, ValueError) as exc:
        add("v1_contract", "error", "package", f"V1 contract normalization failed: {exc}")

    return ContentValidationReport(
        lesson_id=package.lesson_id,
        draft_fingerprint=content_data.draft_fingerprint(package),
        valid=not any(issue.severity == "error" for issue in issues),
        issues=issues,
        validated_at=_now(),
        validated_by=_actor(actor),
    )


def submit_for_review(
    lesson_id: str,
    *,
    actor: str,
    note: str = "",
) -> ContentWorkflowRecord:
    with _workflow_operation_lock():
        _, record = _current_draft_and_record(lesson_id, actor)
        if record.state not in {"validated", "changes_requested"}:
            raise InvalidTransition(f"Cannot submit {record.state} content for review.")
        if record.validation is None or not record.validation.valid:
            raise ContentValidationFailed("A passing validation report is required before review.")
        if record.validation.draft_fingerprint != record.draft_fingerprint:
            raise ContentConflict("Draft changed after validation; validate it again.")
        return _transition(
            record,
            state="in_review",
            action="submit_review",
            actor=actor,
            note=note,
        )


def request_changes(
    lesson_id: str,
    *,
    actor: str,
    note: str,
) -> ContentWorkflowRecord:
    with _workflow_operation_lock():
        record = _load_workflow(lesson_id)
        if record.state != "in_review":
            raise InvalidTransition(f"Cannot request changes from {record.state} state.")
        if not _has_text(note):
            raise ContentValidationFailed("A review note is required when requesting changes.")
        return _transition(
            record,
            state="changes_requested",
            action="request_changes",
            actor=actor,
            note=note,
        )


def approve_draft(
    lesson_id: str,
    *,
    actor: str,
    note: str = "",
) -> ContentWorkflowRecord:
    with _workflow_operation_lock():
        draft, record = _current_draft_and_record(lesson_id, actor)
        if record.state != "in_review":
            raise InvalidTransition(f"Cannot approve content in {record.state} state.")
        report = validate_package(draft, actor=actor)
        if not report.valid:
            raise ContentValidationFailed("Draft no longer passes validation.", report)
        return _transition(
            record,
            state="approved",
            action="approve",
            actor=actor,
            note=note,
            validation=report,
        )


def seal_approved_draft(
    lesson_id: str,
    *,
    actor: str,
) -> tuple[content_data.LessonContentPackage, Path, ContentWorkflowRecord]:
    with _workflow_operation_lock():
        draft, record = _current_draft_and_record(lesson_id, actor)
        if record.state != "approved":
            raise InvalidTransition(f"Cannot seal content in {record.state} state.")
        report = validate_package(draft, actor=actor)
        if not report.valid:
            raise ContentValidationFailed("Approved draft no longer passes validation.", report)
        try:
            sealed, path = content_data._seal_draft_unchecked(
                lesson_id,
                sealed_by=_actor(actor),
                expected_fingerprint=record.draft_fingerprint,
            )
        except content_data.DraftFingerprintMismatch as exc:
            raise ContentConflict(
                "Draft changed after approval; submit it for review again."
            ) from exc
        try:
            updated = _transition(
                record,
                state="sealed",
                action="seal",
                actor=actor,
                note=f"Sealed immutable source version {sealed.version}.",
                validation=report,
                sealed_version=sealed.version,
                sealed_checksum=sealed.checksum,
                event_sealed_version=sealed.version,
            )
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return sealed, path, updated


def publish_version(
    lesson_id: str,
    version: int,
    *,
    actor: str,
    note: str = "",
) -> tuple[CourseReleaseManifest, ContentWorkflowRecord]:
    with _release_operation_lock():
        record = _load_workflow(lesson_id)
        if record.state not in {"sealed", "published"}:
            raise InvalidTransition(f"Cannot publish content in {record.state} state.")
        if record.sealed_version != version:
            raise ContentConflict("Only the workflow's approved sealed version can be published.")
        if record.published_course_id and record.published_course_id != record.course_id:
            raise ContentConflict("A published lesson cannot move to another course implicitly.")

        sealed = content_data.get_sealed_package(lesson_id, version)
        if sealed.checksum != record.sealed_checksum:
            raise content_data.ContentIntegrityError("Workflow and sealed source checksum disagree.")
        report = validate_package(sealed, actor=actor)
        if not report.valid:
            raise ContentValidationFailed("Sealed content does not pass publication validation.", report)

        item = _materialize_release_item(sealed)
        previous_pointer = _load_pointer(record.course_id, required=False)
        current = get_current_release(record.course_id)
        cleanup_paths: list[Path] = []
        if current is None:
            current, baseline_path = _write_release_manifest(
                course_id=record.course_id,
                operation="bootstrap",
                items=(),
                actor=actor,
                note="Empty baseline created for the first managed publication.",
                parent=None,
            )
            cleanup_paths.append(baseline_path)

        by_lesson = {existing.lesson_id: existing for existing in current.items}
        if by_lesson.get(lesson_id) == item:
            if cleanup_paths:
                for path in cleanup_paths:
                    path.unlink(missing_ok=True)
                raise ContentConflict(
                    "An unpublished baseline cannot already contain the requested lesson version."
                )
            updated = _synchronize_workflows_without_pointer_change(
                current,
                actor=actor,
                note=note or "Publication already points to this sealed version.",
                action="publish",
                required_lesson_id=lesson_id,
            )
            if updated is None:
                updated = _load_workflow(lesson_id)
            return current, updated

        by_lesson[lesson_id] = item
        try:
            manifest, manifest_path = _write_release_manifest(
                course_id=record.course_id,
                operation="publish",
                items=list(by_lesson.values()),
                actor=actor,
                note=note or f"Publish {lesson_id} v{version}.",
                parent=current,
            )
        except BaseException:
            for path in reversed(cleanup_paths):
                path.unlink(missing_ok=True)
            raise
        cleanup_paths.append(manifest_path)
        updated = _commit_release(
            manifest,
            actor=actor,
            note=note or f"Published in {manifest.release_id}.",
            action="publish",
            previous_pointer=previous_pointer,
            cleanup_paths=cleanup_paths,
            required_lesson_id=lesson_id,
        )
        if updated is None:
            raise content_data.ContentIntegrityError(
                f"Publication did not project workflow state for {lesson_id}."
            )
        return manifest, updated


def bootstrap_legacy_release(
    course_id: str,
    selections: Sequence[LegacyReleaseSelection],
    *,
    actor: str,
    note: str = "",
) -> CourseReleaseManifest:
    """Explicitly publish a whitelisted set of pre-workflow sealed packages."""
    with _release_operation_lock():
        course_id = _validated_id(course_id)
        if get_current_release(course_id) is not None:
            raise ContentConflict(f"Course {course_id} already has an active release.")
        if not selections:
            raise ContentValidationFailed("At least one legacy sealed version must be selected.")

        lesson_ids = [selection.lesson_id for selection in selections]
        if len(lesson_ids) != len(set(lesson_ids)):
            raise ContentValidationFailed("Legacy bootstrap selections must use unique lesson_id values.")

        items: list[ReleaseItem] = []
        for selection in selections:
            sealed = content_data.get_sealed_package(
                selection.lesson_id,
                selection.content_version,
            )
            if sealed.course_id != course_id:
                raise ContentConflict(
                    f"Legacy package {sealed.lesson_id} belongs to {sealed.course_id}, not {course_id}."
                )
            report = validate_package(sealed, actor=actor)
            if not report.valid:
                raise ContentValidationFailed(
                    f"Legacy package {sealed.lesson_id} does not pass publication validation.",
                    report,
                )
            items.append(_materialize_release_item(sealed))

        manifest, manifest_path = _write_release_manifest(
            course_id=course_id,
            operation="bootstrap",
            items=items,
            actor=actor,
            note=note or "Explicit migration of whitelisted legacy sealed content.",
            parent=None,
        )
        _commit_release(
            manifest,
            actor=actor,
            note=note or f"Migrated legacy content in {manifest.release_id}.",
            action="bootstrap",
            previous_pointer=None,
            cleanup_paths=[manifest_path],
        )
        return manifest


def rollback_release(
    course_id: str,
    *,
    actor: str,
    target_release_id: str | None = None,
    note: str = "",
) -> CourseReleaseManifest:
    with _release_operation_lock():
        current = get_current_release(course_id)
        if current is None:
            raise ContentNotFound(f"No active release for course {course_id}.")
        target_id = target_release_id or current.parent_release_id
        if target_id is None:
            raise InvalidTransition("The active release has no parent to roll back to.")
        if target_id == current.release_id:
            raise ContentConflict("Rollback target is already active.")
        target = get_release(course_id, target_id)
        previous_pointer = _load_pointer(course_id)
        manifest, manifest_path = _write_release_manifest(
            course_id=course_id,
            operation="rollback",
            items=target.items,
            actor=actor,
            note=note or f"Restore content snapshot from {target.release_id}.",
            parent=current,
            restored_from_release_id=target.release_id,
        )
        _commit_release(
            manifest,
            actor=actor,
            note=note or f"Publication pointer moved to {manifest.release_id}.",
            action="rollback",
            previous_pointer=previous_pointer,
            cleanup_paths=[manifest_path],
        )
        return manifest


def get_current_release(course_id: str) -> CourseReleaseManifest | None:
    pointer_path = _active_pointer_path(course_id)
    if not pointer_path.exists():
        return None
    pointer = _read_signed(pointer_path, ActiveReleasePointer)
    if pointer.course_id != course_id:
        raise content_data.ContentIntegrityError("Active release pointer course_id mismatch.")
    manifest_path = _resolve_content_path(pointer.manifest_path)
    manifest = _read_signed(manifest_path, CourseReleaseManifest)
    if (
        manifest.course_id != course_id
        or manifest.release_id != pointer.release_id
        or manifest.release_no != pointer.release_no
        or manifest.checksum != pointer.manifest_checksum
        or manifest_path != _canonical_release_path(course_id, manifest.release_id)
    ):
        raise content_data.ContentIntegrityError("Active pointer and release manifest disagree.")
    return manifest


def get_release(course_id: str, release_id: str) -> CourseReleaseManifest:
    if not _RELEASE_ID_PATTERN.fullmatch(release_id):
        raise ContentNotFound("Release not found.")
    path = _release_path(course_id, release_id)
    if not path.exists():
        raise ContentNotFound(f"Release not found: {release_id}")
    manifest = _read_signed(path, CourseReleaseManifest)
    if (
        manifest.course_id != course_id
        or manifest.release_id != release_id
        or path.resolve() != _canonical_release_path(course_id, release_id)
    ):
        raise content_data.ContentIntegrityError("Release manifest identity mismatch.")
    if release_id not in {item.release_id for item in list_releases(course_id)}:
        raise ContentNotFound(f"Release is not part of the active history: {release_id}")
    return manifest


def list_releases(course_id: str | None = None) -> list[CourseReleaseManifest]:
    root = _manifest_root()
    paths = (
        sorted((root / _validated_id(course_id)).glob("rel-*.json"))
        if course_id
        else sorted(root.glob("*/rel-*.json"))
    )
    manifests: list[CourseReleaseManifest] = []
    for path in paths:
        manifest = _read_signed(path, CourseReleaseManifest)
        expected_path = _canonical_release_path(manifest.course_id, manifest.release_id)
        if path.resolve() != expected_path or (
            course_id is not None and manifest.course_id != course_id
        ):
            raise content_data.ContentIntegrityError(
                f"Release manifest path identity mismatch: {path}"
            )
        manifests.append(manifest)

    by_course: dict[str, dict[str, CourseReleaseManifest]] = {}
    for manifest in manifests:
        by_course.setdefault(manifest.course_id, {})[manifest.release_id] = manifest

    reachable: set[tuple[str, str]] = set()
    if course_id is not None:
        selected_courses = [course_id]
    else:
        active_courses: set[str] = set()
        for pointer_path in sorted(_active_root().glob("*.json")):
            pointer = _read_signed(pointer_path, ActiveReleasePointer)
            if pointer_path.resolve() != _canonical_active_pointer_path(pointer.course_id):
                raise content_data.ContentIntegrityError(
                    f"Active release pointer path identity mismatch: {pointer_path}"
                )
            active_courses.add(pointer.course_id)
        selected_courses = sorted(set(by_course).union(active_courses))
    for selected_course in selected_courses:
        pointer = _load_pointer(selected_course, required=False)
        if pointer is None:
            continue
        current = get_current_release(selected_course)
        if current is None:
            raise content_data.ContentIntegrityError(
                f"Active release disappeared for course {selected_course}."
            )
        course_manifests = by_course.get(selected_course, {})
        release_id: str | None = current.release_id
        seen: set[str] = set()
        while release_id is not None:
            if release_id in seen:
                raise content_data.ContentIntegrityError(
                    f"Release history contains a cycle for course {selected_course}."
                )
            seen.add(release_id)
            manifest = course_manifests.get(release_id)
            if manifest is None:
                raise content_data.ContentIntegrityError(
                    f"Release history is missing manifest {release_id}."
                )
            reachable.add((selected_course, release_id))
            release_id = manifest.parent_release_id

    return sorted(
        [
            manifest
            for manifest in manifests
            if (manifest.course_id, manifest.release_id) in reachable
        ],
        key=lambda item: (item.course_id, item.release_no),
    )


def load_published_snapshots() -> list[PublishedCourseSnapshot]:
    with _LOCK:
        content_data.ensure_content_dirs()
        snapshots: list[PublishedCourseSnapshot] = []
        lesson_ids: set[str] = set()

        for pointer_path in sorted(_active_root().glob("*.json")):
            pointer = _read_signed(pointer_path, ActiveReleasePointer)
            if pointer_path.resolve() != _canonical_active_pointer_path(pointer.course_id):
                raise content_data.ContentIntegrityError(
                    f"Active release pointer path identity mismatch: {pointer_path}"
                )
            manifest = get_current_release(pointer.course_id)
            if manifest is None:
                raise content_data.ContentIntegrityError("Active release pointer disappeared during read.")
            for item in manifest.items:
                package = _load_release_item(item)
                if package.lesson_id in lesson_ids:
                    raise content_data.ContentIntegrityError(
                        f"Published lesson_id appears in multiple courses: {package.lesson_id}"
                )
                lesson_ids.add(package.lesson_id)
                snapshots.append(
                    PublishedCourseSnapshot(
                        package=package,
                        release_id=manifest.release_id,
                        release_no=manifest.release_no,
                        release_checksum=manifest.checksum,
                    )
                )

        return sorted(
            snapshots,
            key=lambda item: (
                item.package.course_id,
                item.package.lesson_no,
                item.package.lesson_id,
            ),
        )


def load_published_packages() -> list[CoursePackageV1]:
    return [snapshot.package for snapshot in load_published_snapshots()]


def _current_draft_and_record(
    lesson_id: str,
    actor: str,
) -> tuple[content_data.LessonContentPackage, ContentWorkflowRecord]:
    draft = content_data.get_draft(lesson_id)
    if draft is None:
        raise ContentNotFound(f"Draft not found: {lesson_id}")
    record = _load_workflow(lesson_id, required=False)
    fingerprint = content_data.draft_fingerprint(draft)
    if (
        record is None
        or record.draft_fingerprint != fingerprint
        or record.course_id != draft.course_id
    ):
        record = record_draft_saved(draft, actor=actor)
    return draft, record


def _transition(
    record: ContentWorkflowRecord,
    *,
    state: WorkflowState,
    action: WorkflowAction,
    actor: str,
    note: str = "",
    validation: ContentValidationReport | None | object = ...,
    sealed_version: int | None | object = ...,
    sealed_checksum: str | None | object = ...,
    published_course_id: str | None | object = ...,
    published_version: int | None | object = ...,
    published_release_id: str | None | object = ...,
    event_sealed_version: int | None = None,
    event_release_id: str | None = None,
) -> ContentWorkflowRecord:
    updated = _build_transition(
        record,
        state=state,
        action=action,
        actor=actor,
        note=note,
        validation=validation,
        sealed_version=sealed_version,
        sealed_checksum=sealed_checksum,
        published_course_id=published_course_id,
        published_version=published_version,
        published_release_id=published_release_id,
        event_sealed_version=event_sealed_version,
        event_release_id=event_release_id,
    )
    return _write_workflow(updated)


def _build_transition(
    record: ContentWorkflowRecord,
    *,
    state: WorkflowState,
    action: WorkflowAction,
    actor: str,
    note: str = "",
    validation: ContentValidationReport | None | object = ...,
    sealed_version: int | None | object = ...,
    sealed_checksum: str | None | object = ...,
    published_course_id: str | None | object = ...,
    published_version: int | None | object = ...,
    published_release_id: str | None | object = ...,
    event_sealed_version: int | None = None,
    event_release_id: str | None = None,
) -> ContentWorkflowRecord:
    now = _now()
    data = record.model_dump(mode="json")
    updates = {
        "validation": validation,
        "sealed_version": sealed_version,
        "sealed_checksum": sealed_checksum,
        "published_course_id": published_course_id,
        "published_version": published_version,
        "published_release_id": published_release_id,
    }
    for key, value in updates.items():
        if value is not ...:
            data[key] = value
    event = WorkflowEvent(
        sequence=len(record.history) + 1,
        action=action,
        from_state=record.state,
        to_state=state,
        actor=_actor(actor),
        note=note,
        occurred_at=now,
        draft_fingerprint=record.draft_fingerprint,
        sealed_version=event_sealed_version,
        release_id=event_release_id,
    )
    data.update(
        state=state,
        revision=record.revision + 1,
        updated_at=now,
        history=[*data["history"], event.model_dump(mode="json")],
        checksum="0" * 64,
    )
    updated = ContentWorkflowRecord.model_validate(data)
    return _sign(updated, ContentWorkflowRecord)


def _write_release_manifest(
    *,
    course_id: str,
    operation: Literal["bootstrap", "publish", "rollback"],
    items: Sequence[ReleaseItem],
    actor: str,
    note: str,
    parent: CourseReleaseManifest | None,
    restored_from_release_id: str | None = None,
) -> tuple[CourseReleaseManifest, Path]:
    course_id = _validated_id(course_id)
    release_no = _next_release_no(course_id)
    release_id = _release_id(course_id, release_no)
    manifest = CourseReleaseManifest(
        release_id=release_id,
        release_no=release_no,
        course_id=course_id,
        operation=operation,
        parent_release_id=(parent.release_id if parent else None),
        restored_from_release_id=restored_from_release_id,
        created_at=_now(),
        created_by=_actor(actor),
        note=note,
        items=sorted(items, key=lambda item: item.lesson_id),
        checksum="0" * 64,
    )
    manifest = _sign(manifest, CourseReleaseManifest)
    manifest_path = _release_path(course_id, release_id)
    content_data._atomic_write_json(
        manifest_path,
        manifest.model_dump(mode="json"),
        overwrite=False,
    )
    return manifest, manifest_path


def _commit_release(
    manifest: CourseReleaseManifest,
    *,
    actor: str,
    note: str,
    action: Literal["bootstrap", "publish", "rollback"],
    previous_pointer: ActiveReleasePointer | None,
    cleanup_paths: Sequence[Path],
    required_lesson_id: str | None = None,
) -> ContentWorkflowRecord | None:
    """Persist projections first, then switch students with crash recovery metadata."""
    transaction_written = False
    try:
        observed_pointer = _load_pointer(manifest.course_id, required=False)
        if _pointer_identity(observed_pointer) != _pointer_identity(previous_pointer):
            raise ContentConflict(
                f"Active release changed while preparing {manifest.release_id}; retry publication."
            )

        pointer = _build_pointer(manifest, actor=actor, previous_pointer=previous_pointer)
        originals, updates = _build_release_workflow_updates(
            manifest,
            actor=actor,
            note=note,
            action=action,
        )
        target_record = None
        if required_lesson_id is not None:
            target_record = updates.get(required_lesson_id) or originals.get(required_lesson_id)
            if target_record is None:
                raise content_data.ContentIntegrityError(
                    f"Workflow projection is missing required lesson {required_lesson_id}."
                )

        for item in manifest.items:
            _load_release_item(item)
        _assert_release_lesson_ids_are_globally_unique(manifest)
        transaction = _build_release_transaction(
            manifest=manifest,
            pointer=pointer,
            previous_pointer=previous_pointer,
            originals=originals,
            updates=updates,
            cleanup_paths=cleanup_paths,
        )
        transaction_path = _transaction_path(manifest.course_id)
        try:
            content_data._atomic_write_json(
                transaction_path,
                transaction.model_dump(mode="json"),
                overwrite=False,
            )
            transaction_written = True
            _write_workflow_updates(originals, updates)
            content_data._atomic_write_json(
                _active_pointer_path(manifest.course_id),
                pointer.model_dump(mode="json"),
            )
        except Exception:
            activated = _active_pointer_targets(manifest)
            if transaction_path.exists():
                transaction_written = True
                _recover_release_transaction(manifest.course_id)
            if activated:
                return target_record
            raise
        except BaseException:
            if transaction_path.exists():
                transaction_written = True
                _recover_release_transaction(manifest.course_id)
            raise
        try:
            transaction_path.unlink(missing_ok=True)
        except OSError:
            # The active pointer is already authoritative; startup recovery is idempotent.
            pass
        return target_record
    except BaseException:
        if not transaction_written and not _active_pointer_targets(manifest):
            for path in reversed(tuple(cleanup_paths)):
                path.unlink(missing_ok=True)
        raise


def _build_release_transaction(
    *,
    manifest: CourseReleaseManifest,
    pointer: ActiveReleasePointer,
    previous_pointer: ActiveReleasePointer | None,
    originals: dict[str, ContentWorkflowRecord],
    updates: dict[str, ContentWorkflowRecord],
    cleanup_paths: Sequence[Path],
) -> ReleaseTransactionJournal:
    changed_originals = [originals[lesson_id] for lesson_id in sorted(updates)]
    transaction = ReleaseTransactionJournal(
        course_id=manifest.course_id,
        manifest=manifest,
        pointer=pointer,
        previous_pointer=previous_pointer,
        original_workflows=changed_originals,
        updated_workflows=[updates[lesson_id] for lesson_id in sorted(updates)],
        cleanup_paths=[_relative_content_path(path) for path in cleanup_paths],
        prepared_at=_now(),
        checksum="0" * 64,
    )
    return _sign(transaction, ReleaseTransactionJournal)


def recover_pending_release_transactions() -> None:
    """Finish or roll back release metadata left by an interrupted process."""
    with _workflow_operation_lock():
        pass


@contextmanager
def workflow_write_lock() -> Iterator[None]:
    """Coordinate content-file writes with workflow and release projections."""
    with _workflow_operation_lock():
        yield


def _recover_all_release_transactions() -> None:
    for path in sorted(_transaction_root().glob("*.json")):
        transaction = _read_signed(path, ReleaseTransactionJournal)
        if path.resolve() != _canonical_transaction_path(transaction.course_id):
            raise content_data.ContentIntegrityError(
                f"Release transaction path identity mismatch: {path}"
            )
        _recover_release_transaction(transaction.course_id, transaction=transaction)


def _recover_release_transaction(
    course_id: str,
    *,
    transaction: ReleaseTransactionJournal | None = None,
) -> None:
    path = _transaction_path(course_id)
    if transaction is None:
        if not path.exists():
            return
        transaction = _read_signed(path, ReleaseTransactionJournal)
    if (
        transaction.course_id != course_id
        or path.resolve() != _canonical_transaction_path(course_id)
    ):
        raise content_data.ContentIntegrityError(
            f"Release transaction identity mismatch: {path}"
        )

    active_pointer = _load_pointer(course_id, required=False)
    active_identity = _pointer_identity(active_pointer)
    target_identity = _pointer_identity(transaction.pointer)
    previous_identity = _pointer_identity(transaction.previous_pointer)
    if active_identity == target_identity:
        _restore_workflow_records(
            {record.lesson_id: record for record in transaction.updated_workflows}
        )
    elif active_identity == previous_identity:
        _restore_workflow_records(
            {record.lesson_id: record for record in transaction.original_workflows}
        )
        for relative_path in reversed(transaction.cleanup_paths):
            _validated_release_cleanup_path(relative_path, course_id).unlink(missing_ok=True)
    else:
        raise content_data.ContentIntegrityError(
            "Active release pointer conflicts with an interrupted release transaction."
        )
    path.unlink(missing_ok=True)


def _validated_release_cleanup_path(relative_path: str, course_id: str) -> Path:
    path = _resolve_content_path(relative_path)
    expected_parent = _manifest_root().resolve() / _validated_id(course_id)
    if path.parent != expected_parent or not _RELEASE_ID_PATTERN.fullmatch(path.stem):
        raise content_data.ContentIntegrityError(
            f"Release transaction cleanup path is not canonical: {relative_path}"
        )
    return path


def _assert_release_lesson_ids_are_globally_unique(
    manifest: CourseReleaseManifest,
) -> None:
    candidate_ids = {item.lesson_id for item in manifest.items}
    if not candidate_ids:
        return
    for pointer_path in sorted(_active_root().glob("*.json")):
        pointer = _read_signed(pointer_path, ActiveReleasePointer)
        if pointer_path.resolve() != _canonical_active_pointer_path(pointer.course_id):
            raise content_data.ContentIntegrityError(
                f"Active release pointer path identity mismatch: {pointer_path}"
            )
        if pointer.course_id == manifest.course_id:
            continue
        other_manifest = get_current_release(pointer.course_id)
        if other_manifest is None:
            raise content_data.ContentIntegrityError(
                f"Active release disappeared for course {pointer.course_id}."
            )
        duplicates = sorted(
            candidate_ids.intersection(item.lesson_id for item in other_manifest.items)
        )
        if duplicates:
            raise ContentConflict(
                "lesson_id must be globally unique across active courses: "
                + ", ".join(duplicates)
            )


def _synchronize_workflows_without_pointer_change(
    manifest: CourseReleaseManifest,
    *,
    actor: str,
    note: str,
    action: Literal["bootstrap", "publish", "rollback"],
    required_lesson_id: str | None = None,
) -> ContentWorkflowRecord | None:
    originals, updates = _build_release_workflow_updates(
        manifest,
        actor=actor,
        note=note,
        action=action,
    )
    target_record = None
    if required_lesson_id is not None:
        target_record = updates.get(required_lesson_id) or originals.get(required_lesson_id)
        if target_record is None:
            raise content_data.ContentIntegrityError(
                f"Workflow projection is missing required lesson {required_lesson_id}."
            )
    _write_workflow_updates(originals, updates)
    return target_record


def _build_pointer(
    manifest: CourseReleaseManifest,
    *,
    actor: str,
    previous_pointer: ActiveReleasePointer | None,
) -> ActiveReleasePointer:
    manifest_path = _release_path(manifest.course_id, manifest.release_id)
    pointer = ActiveReleasePointer(
        course_id=manifest.course_id,
        release_id=manifest.release_id,
        release_no=manifest.release_no,
        manifest_path=_relative_content_path(manifest_path),
        manifest_checksum=manifest.checksum,
        generation=(previous_pointer.generation + 1 if previous_pointer else 1),
        previous_release_id=(previous_pointer.release_id if previous_pointer else None),
        activated_at=_now(),
        activated_by=_actor(actor),
        checksum="0" * 64,
    )
    return _sign(pointer, ActiveReleasePointer)


def _build_release_workflow_updates(
    manifest: CourseReleaseManifest,
    *,
    actor: str,
    note: str,
    action: Literal["bootstrap", "publish", "rollback"],
) -> tuple[dict[str, ContentWorkflowRecord], dict[str, ContentWorkflowRecord]]:
    published = {item.lesson_id: item for item in manifest.items}
    originals: dict[str, ContentWorkflowRecord] = {}
    updates: dict[str, ContentWorkflowRecord] = {}
    for record in _course_workflow_records(manifest.course_id):
        item = published.get(record.lesson_id)
        published_course_id = manifest.course_id if item else None
        published_version = item.content_version if item else None
        published_release_id = manifest.release_id if item else None
        state = record.state
        if item and record.sealed_version == item.content_version and state in {
            "sealed",
            "published",
        }:
            state = "published"
        elif state == "published":
            state = "sealed" if record.sealed_version is not None else "draft"

        desired = (
            state,
            published_course_id,
            published_version,
            published_release_id,
        )
        current = (
            record.state,
            record.published_course_id,
            record.published_version,
            record.published_release_id,
        )
        originals[record.lesson_id] = record
        if desired == current:
            continue
        updates[record.lesson_id] = _build_transition(
            record,
            state=state,
            action=action,
            actor=actor,
            note=note,
            published_course_id=published_course_id,
            published_version=published_version,
            published_release_id=published_release_id,
            event_release_id=manifest.release_id,
        )
    return originals, updates


def _course_workflow_records(course_id: str) -> list[ContentWorkflowRecord]:
    records: list[ContentWorkflowRecord] = []
    for path in sorted(content_data.workflow_dir().glob("*.json")):
        record = _read_signed(path, ContentWorkflowRecord)
        if path.resolve() != _canonical_workflow_path(record.lesson_id):
            raise content_data.ContentIntegrityError(
                f"Workflow file path identity mismatch: {path}"
            )
        if record.course_id == course_id or record.published_course_id == course_id:
            records.append(record)
    return records


def _write_workflow_updates(
    originals: dict[str, ContentWorkflowRecord],
    updates: dict[str, ContentWorkflowRecord],
) -> None:
    try:
        for lesson_id in sorted(updates):
            _write_workflow(updates[lesson_id])
    except BaseException:
        _restore_workflow_records(
            {lesson_id: originals[lesson_id] for lesson_id in updates}
        )
        raise


def _restore_workflow_records(records: dict[str, ContentWorkflowRecord]) -> None:
    errors: list[Exception] = []
    for lesson_id in sorted(records):
        try:
            content_data._atomic_write_json(
                _workflow_path(lesson_id),
                records[lesson_id].model_dump(mode="json"),
            )
        except Exception as exc:
            errors.append(exc)
    if errors:
        raise content_data.ContentIntegrityError(
            "Publication failed and workflow metadata could not be restored."
        ) from errors[0]


def _pointer_identity(
    pointer: ActiveReleasePointer | None,
) -> tuple[str, int, str] | None:
    if pointer is None:
        return None
    return pointer.release_id, pointer.generation, pointer.checksum


def _active_pointer_targets(manifest: CourseReleaseManifest) -> bool:
    try:
        pointer = _load_pointer(manifest.course_id, required=False)
    except (ContentWorkflowError, content_data.ContentIntegrityError):
        return False
    return bool(
        pointer
        and pointer.release_id == manifest.release_id
        and pointer.manifest_checksum == manifest.checksum
    )


def _materialize_release_item(
    sealed: content_data.LessonContentPackage,
) -> ReleaseItem:
    if sealed.status != "sealed" or not content_data.verify_package_checksum(sealed):
        raise content_data.ContentIntegrityError("Only verified sealed content can be released.")
    package = course_package_from_legacy(sealed)
    if not verify_contract_checksum(package):
        raise content_data.ContentIntegrityError("Normalized CoursePackageV1 checksum is invalid.")
    filename = f"{sealed.lesson_id}-v{sealed.version:03d}.json"
    package_path = content_data.package_dir() / filename
    if package_path.exists():
        existing = _read_contract(package_path)
        if existing.checksum != package.checksum:
            raise ContentConflict(f"Canonical package already exists with different content: {filename}")
    else:
        content_data._atomic_write_json(
            package_path,
            package.model_dump(mode="json"),
            overwrite=False,
        )
    source_path = content_data.sealed_dir() / filename
    return ReleaseItem(
        lesson_id=sealed.lesson_id,
        course_id=sealed.course_id,
        content_version=sealed.version,
        source_path=_relative_content_path(source_path),
        source_checksum=str(sealed.checksum),
        package_path=_relative_content_path(package_path),
        package_checksum=str(package.checksum),
    )


def _load_release_item(item: ReleaseItem) -> CoursePackageV1:
    expected_filename = f"{item.lesson_id}-v{item.content_version:03d}.json"
    source_path = _resolve_content_path(item.source_path)
    package_path = _resolve_content_path(item.package_path)
    if source_path != content_data.sealed_dir() / expected_filename:
        raise content_data.ContentIntegrityError("Release source_path is not canonical.")
    if package_path != content_data.package_dir() / expected_filename:
        raise content_data.ContentIntegrityError("Release package_path is not canonical.")
    try:
        source = content_data.get_sealed_package(item.lesson_id, item.content_version)
    except FileNotFoundError as exc:
        raise content_data.ContentIntegrityError(
            f"Release source artifact is missing: {item.source_path}"
        ) from exc
    package = _read_contract(package_path)
    if (
        source.course_id != item.course_id
        or source.checksum != item.source_checksum
        or package.course_id != item.course_id
        or package.lesson_id != item.lesson_id
        or package.content_version != item.content_version
        or package.checksum != item.package_checksum
        or package.compatibility.source_checksum != item.source_checksum
    ):
        raise content_data.ContentIntegrityError("Release item does not match its source artifacts.")
    return package


def _load_workflow(
    lesson_id: str,
    required: bool = True,
) -> ContentWorkflowRecord | None:
    path = _workflow_path(lesson_id)
    if not path.exists():
        if required:
            raise ContentNotFound(f"Workflow not found: {lesson_id}")
        return None
    record = _read_signed(path, ContentWorkflowRecord)
    if (
        record.lesson_id != lesson_id
        or path.resolve() != _canonical_workflow_path(lesson_id)
    ):
        raise content_data.ContentIntegrityError(
            f"Workflow file identity mismatch: {path}"
        )
    return record


def _write_workflow(record: ContentWorkflowRecord) -> ContentWorkflowRecord:
    content_data._atomic_write_json(
        _workflow_path(record.lesson_id),
        record.model_dump(mode="json"),
    )
    return record


def _load_pointer(
    course_id: str,
    required: bool = True,
) -> ActiveReleasePointer | None:
    path = _active_pointer_path(course_id)
    if not path.exists():
        if required:
            raise ContentNotFound(f"Active release not found: {course_id}")
        return None
    pointer = _read_signed(path, ActiveReleasePointer)
    if (
        pointer.course_id != course_id
        or path.resolve() != _canonical_active_pointer_path(course_id)
    ):
        raise content_data.ContentIntegrityError(
            f"Active release pointer identity mismatch: {path}"
        )
    return pointer


def _read_contract(path: Path) -> CoursePackageV1:
    try:
        package = CoursePackageV1.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise content_data.ContentIntegrityError(f"Cannot read CoursePackageV1: {path}") from exc
    if not verify_contract_checksum(package):
        raise content_data.ContentIntegrityError(f"CoursePackageV1 checksum mismatch: {path}")
    return package


def _read_signed(path: Path, model_type):
    try:
        model = model_type.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise content_data.ContentIntegrityError(f"Cannot read signed content metadata: {path}") from exc
    if model.checksum != _model_checksum(model):
        raise content_data.ContentIntegrityError(f"Signed content metadata checksum mismatch: {path}")
    return model


def _sign(model: BaseModel, model_type):
    data = model.model_dump(mode="json")
    data["checksum"] = _model_checksum(model)
    return model_type.model_validate(data)


def _model_checksum(model: BaseModel) -> str:
    data = model.model_dump(mode="json")
    if "checksum" not in data:
        raise ValueError("signed model does not expose checksum")
    data["checksum"] = None
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _workflow_path(lesson_id: str) -> Path:
    return content_data.workflow_dir() / f"{_validated_id(lesson_id)}.json"


def _canonical_workflow_path(lesson_id: str) -> Path:
    return content_data.workflow_dir().resolve() / f"{_validated_id(lesson_id)}.json"


def _manifest_root() -> Path:
    path = content_data.release_dir() / "manifests"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _active_root() -> Path:
    path = content_data.release_dir() / "active"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _transaction_root() -> Path:
    path = content_data.release_dir() / "transactions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _lock_root() -> Path:
    path = content_data.release_dir() / ".locks"
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def _workflow_file_lock() -> Iterator[None]:
    """Serialize workflow and release writes across API worker processes."""
    path = _lock_root() / "workflow-global.lock"
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _workflow_operation_lock() -> Iterator[None]:
    with _LOCK:
        depth = getattr(_FILE_LOCK_STATE, "depth", 0)
        if depth:
            _FILE_LOCK_STATE.depth = depth + 1
            try:
                yield
            finally:
                _FILE_LOCK_STATE.depth = depth
            return

        with _workflow_file_lock():
            _FILE_LOCK_STATE.depth = 1
            try:
                _recover_all_release_transactions()
                yield
            finally:
                _FILE_LOCK_STATE.depth = 0


@contextmanager
def _release_operation_lock() -> Iterator[None]:
    with _workflow_operation_lock():
        yield


def _release_path(course_id: str, release_id: str) -> Path:
    if not _RELEASE_ID_PATTERN.fullmatch(release_id):
        raise ContentNotFound("Release not found.")
    directory = _manifest_root() / _validated_id(course_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{release_id}.json"


def _canonical_release_path(course_id: str, release_id: str) -> Path:
    if not _RELEASE_ID_PATTERN.fullmatch(release_id):
        raise ContentNotFound("Release not found.")
    return (
        _manifest_root().resolve()
        / _validated_id(course_id)
        / f"{release_id}.json"
    )


def _active_pointer_path(course_id: str) -> Path:
    return _active_root() / f"{_validated_id(course_id)}.json"


def _canonical_active_pointer_path(course_id: str) -> Path:
    return _active_root().resolve() / f"{_validated_id(course_id)}.json"


def _transaction_path(course_id: str) -> Path:
    return _transaction_root() / f"{_validated_id(course_id)}.json"


def _canonical_transaction_path(course_id: str) -> Path:
    return _transaction_root().resolve() / f"{_validated_id(course_id)}.json"


def _next_release_no(course_id: str) -> int:
    directory = _manifest_root() / _validated_id(course_id)
    numbers: list[int] = []
    for path in directory.glob("rel-*.json") if directory.exists() else []:
        try:
            numbers.append(int(path.stem.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            raise content_data.ContentIntegrityError(f"Invalid release filename: {path}") from None
    return max(numbers, default=0) + 1


def _release_id(course_id: str, release_no: int) -> str:
    digest = hashlib.sha1(course_id.encode("utf-8")).hexdigest()[:10]
    return f"rel-{digest}-{release_no:04d}"


def _relative_content_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(content_data.content_root().resolve()).as_posix()
    except ValueError as exc:
        raise content_data.ContentIntegrityError(f"Path escapes content root: {path}") from exc


def _resolve_content_path(relative_path: str) -> Path:
    path = (content_data.content_root() / relative_path).resolve()
    root = content_data.content_root().resolve()
    if not path.is_relative_to(root):
        raise content_data.ContentIntegrityError(f"Path escapes content root: {relative_path}")
    return path


def _validated_id(value: str) -> str:
    if not _ID_PATTERN.fullmatch(value):
        raise ValueError("Use 2-64 ASCII letters, numbers, dot, underscore or dash.")
    return value


def _actor(value: str) -> str:
    actor = value.strip()
    if not actor:
        raise ValueError("actor cannot be empty")
    return actor


def _has_text(value: str) -> bool:
    return bool(value and value.strip())


def _add_duplicate_warning(values, field, code, add) -> None:
    normalized = [value.strip().casefold() for value in values if _has_text(value)]
    if len(normalized) != len(set(normalized)):
        add(code, "warning", field, f"{field} contains duplicate display values.")


def _now() -> datetime:
    return datetime.now(timezone.utc)
