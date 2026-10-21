from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal, TypeVar

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    model_validator,
)

from services import content as content_data
from services.content import runtime_artifacts
from services.content import workflow as content_workflow
from services.contracts.evidence_v1 import (
    EvidenceCorpusV1,
    EvidencePassageV1,
    EvidenceSourceV1,
    sign_evidence_contract,
)
from services.contracts.v1 import (
    Checksum,
    ContractId,
    NonEmptyText,
    course_package_from_legacy,
)
from services.game_runtime import ScenarioFileError, load_contract_file


BoundedText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=4000),
]
_CONTRACT_ID_ADAPTER = TypeAdapter(ContractId)
EvidenceModelT = TypeVar("EvidenceModelT", bound=BaseModel)
EvidenceWorkflowState = Literal[
    "draft",
    "validated",
    "in_review",
    "changes_requested",
    "approved",
    "sealed",
]
EvidenceWorkflowAction = Literal[
    "save",
    "validation_passed",
    "validation_failed",
    "submit_review",
    "request_changes",
    "approve",
    "seal",
]


class EvidenceWorkflowError(content_workflow.ContentWorkflowError):
    code = "evidence_workflow_error"


class EvidenceDraftNotFound(EvidenceWorkflowError):
    code = "evidence_draft_not_found"


class EvidenceDraftConflict(EvidenceWorkflowError):
    code = "evidence_draft_conflict"


class EvidenceInvalidTransition(EvidenceWorkflowError):
    code = "invalid_evidence_transition"


class EvidenceValidationFailed(EvidenceWorkflowError):
    code = "evidence_validation_failed"

    def __init__(
        self,
        message: str,
        report: EvidenceValidationReportV1 | None = None,
    ) -> None:
        super().__init__(message)
        self.report = report


class EvidenceAuthoringModel(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        str_strip_whitespace=True,
    )


class EvidenceCorpusDraftV1(EvidenceAuthoringModel):
    schema_version: Literal["evidence-corpus-draft/v1"] = (
        "evidence-corpus-draft/v1"
    )
    corpus_id: ContractId
    course_id: ContractId
    lesson_id: ContractId
    title: BoundedText = ""
    scope_note: BoundedText = ""
    sources: tuple[EvidenceSourceV1, ...] = ()
    passages: tuple[EvidencePassageV1, ...] = ()
    revision: int = Field(default=0, ge=0)
    created_at: AwareDatetime | None = None
    updated_at: AwareDatetime | None = None
    created_by: str | None = None
    updated_by: str | None = None


class EvidenceValidationIssueV1(EvidenceAuthoringModel):
    code: NonEmptyText
    severity: Literal["error", "warning"]
    field: NonEmptyText
    message: NonEmptyText


class EvidenceValidationReportV1(EvidenceAuthoringModel):
    schema_version: Literal["evidence-validation/v1"] = "evidence-validation/v1"
    validator_version: Literal["evidence-publication/v1"] = (
        "evidence-publication/v1"
    )
    corpus_id: ContractId
    course_id: ContractId
    lesson_id: ContractId
    draft_revision: int = Field(ge=1)
    draft_fingerprint: Checksum
    valid: bool
    issues: tuple[EvidenceValidationIssueV1, ...] = ()
    source_count: int = Field(ge=0)
    passage_count: int = Field(ge=0)
    validated_at: AwareDatetime
    validated_by: NonEmptyText

    @model_validator(mode="after")
    def validate_result(self) -> "EvidenceValidationReportV1":
        has_errors = any(item.severity == "error" for item in self.issues)
        if self.valid == has_errors:
            raise ValueError("valid must be true exactly when no error issues exist")
        return self


class EvidenceWorkflowEventV1(EvidenceAuthoringModel):
    sequence: int = Field(ge=1)
    action: EvidenceWorkflowAction
    from_state: EvidenceWorkflowState
    to_state: EvidenceWorkflowState
    actor: NonEmptyText
    note: str = ""
    occurred_at: AwareDatetime
    draft_revision: int = Field(ge=1)
    draft_fingerprint: Checksum
    sealed_version: int | None = Field(default=None, ge=1)


class EvidenceWorkflowRecordV1(EvidenceAuthoringModel):
    schema_version: Literal["evidence-workflow/v1"] = "evidence-workflow/v1"
    corpus_id: ContractId
    course_id: ContractId
    lesson_id: ContractId
    state: EvidenceWorkflowState
    revision: int = Field(ge=1)
    draft_revision: int = Field(ge=1)
    draft_fingerprint: Checksum
    validation: EvidenceValidationReportV1 | None = None
    sealed_version: int | None = Field(default=None, ge=1)
    sealed_checksum: Checksum | None = None
    updated_at: AwareDatetime
    history: tuple[EvidenceWorkflowEventV1, ...]
    checksum: Checksum

    @model_validator(mode="after")
    def validate_record(self) -> "EvidenceWorkflowRecordV1":
        sequences = [event.sequence for event in self.history]
        if sequences != list(range(1, len(self.history) + 1)):
            raise ValueError("workflow history must use contiguous sequence numbers")
        if self.revision != len(self.history):
            raise ValueError("workflow revision must equal the number of events")
        previous: EvidenceWorkflowState = "draft"
        for event in self.history:
            if event.from_state != previous:
                raise ValueError("workflow event states must form a continuous chain")
            previous = event.to_state
        if not self.history or previous != self.state:
            raise ValueError("workflow state must match the final event")
        latest = self.history[-1]
        if (
            latest.draft_revision != self.draft_revision
            or latest.draft_fingerprint != self.draft_fingerprint
        ):
            raise ValueError("latest workflow event must identify the current draft")
        if self.validation is not None and (
            self.validation.corpus_id != self.corpus_id
            or self.validation.draft_revision != self.draft_revision
            or self.validation.draft_fingerprint != self.draft_fingerprint
        ):
            raise ValueError("validation report must identify the current draft")
        if self.state in {
            "validated",
            "in_review",
            "changes_requested",
            "approved",
        } and (self.validation is None or not self.validation.valid):
            raise ValueError("review states require a passing validation report")
        if (self.sealed_version is None) != (self.sealed_checksum is None):
            raise ValueError("sealed version and checksum must be stored together")
        if self.state == "sealed" and self.sealed_version is None:
            raise ValueError("sealed state requires an immutable corpus identity")
        return self


def save_evidence_draft(
    payload: EvidenceCorpusDraftV1,
    *,
    saved_by: str,
) -> tuple[EvidenceCorpusDraftV1, EvidenceWorkflowRecordV1]:
    actor = _actor(saved_by)
    with content_workflow.workflow_write_lock():
        existing = get_evidence_draft(payload.corpus_id)
        if existing is None:
            if payload.revision != 0:
                raise EvidenceDraftConflict(
                    "A new evidence draft must start with revision 0."
                )
        elif payload.revision != existing.revision:
            raise EvidenceDraftConflict(
                "Evidence draft revision changed; reload before saving."
            )
        if existing is not None and (
            payload.course_id,
            payload.lesson_id,
        ) != (existing.course_id, existing.lesson_id):
            raise EvidenceDraftConflict(
                "An evidence corpus cannot move to another course or lesson."
            )

        now = _now()
        data = payload.model_dump(mode="json")
        data.update(
            sources=sorted(
                data["sources"], key=lambda item: str(item["source_id"])
            ),
            passages=sorted(
                data["passages"], key=lambda item: str(item["passage_id"])
            ),
            revision=(existing.revision + 1 if existing else 1),
            created_at=(existing.created_at if existing else now),
            updated_at=now,
            created_by=(existing.created_by if existing else actor),
            updated_by=actor,
        )
        saved = EvidenceCorpusDraftV1.model_validate(data)
        if existing is not None and evidence_draft_fingerprint(
            existing
        ) == evidence_draft_fingerprint(saved):
            record = get_evidence_workflow(saved.corpus_id)
            if record is None:
                raise content_data.ContentIntegrityError(
                    "Evidence draft exists without its workflow metadata."
                )
            return existing, record

        previous_record = get_evidence_workflow(payload.corpus_id)
        if existing is not None and previous_record is None:
            raise content_data.ContentIntegrityError(
                "Evidence draft exists without its workflow metadata."
            )
        record = _saved_record(saved, previous_record, actor=actor)
        draft_path = _draft_path(saved.corpus_id)
        workflow_path = _workflow_path(saved.corpus_id)
        try:
            content_data._atomic_write_json(
                draft_path,
                saved.model_dump(mode="json"),
            )
            content_data._atomic_write_json(
                workflow_path,
                record.model_dump(mode="json"),
            )
        except BaseException:
            _restore_pair(
                draft_path=draft_path,
                draft=existing,
                workflow_path=workflow_path,
                workflow=previous_record,
            )
            raise
        return saved, record


def get_evidence_draft(corpus_id: str) -> EvidenceCorpusDraftV1 | None:
    path = _draft_path(corpus_id)
    if not path.exists():
        return None
    draft = _read_model(path, EvidenceCorpusDraftV1)
    if draft.corpus_id != corpus_id or path.resolve() != _canonical_draft_path(
        corpus_id
    ):
        raise content_data.ContentIntegrityError(
            f"Evidence draft path identity mismatch: {path}"
        )
    return draft


def list_evidence_drafts() -> list[EvidenceCorpusDraftV1]:
    content_data.ensure_content_dirs()
    root = content_data.evidence_draft_dir()
    if root.is_symlink() or not root.is_dir():
        raise content_data.ContentIntegrityError(
            f"Evidence draft root must be a real directory: {root}"
        )
    drafts: list[EvidenceCorpusDraftV1] = []
    for path in sorted(root.glob("*.json")):
        if path.is_symlink():
            raise content_data.ContentIntegrityError(
                f"Evidence draft cannot be a symlink: {path}"
            )
        item = get_evidence_draft(path.stem)
        if item is not None:
            drafts.append(item)
    return drafts


def get_evidence_workflow(corpus_id: str) -> EvidenceWorkflowRecordV1 | None:
    path = _workflow_path(corpus_id)
    if not path.exists():
        return None
    record = _read_signed(path, EvidenceWorkflowRecordV1)
    if record.corpus_id != corpus_id or path.resolve() != _canonical_workflow_path(
        corpus_id
    ):
        raise content_data.ContentIntegrityError(
            f"Evidence workflow path identity mismatch: {path}"
        )
    return record


def validate_evidence_draft(
    corpus_id: str,
    *,
    actor: str,
) -> tuple[EvidenceWorkflowRecordV1, EvidenceValidationReportV1]:
    with content_workflow.workflow_write_lock():
        draft, record = _current(corpus_id)
        report = _validation_report(draft, actor=actor)
        action: EvidenceWorkflowAction = (
            "validation_passed" if report.valid else "validation_failed"
        )
        state: EvidenceWorkflowState = "validated" if report.valid else "draft"
        updated = _transition(
            record,
            state=state,
            action=action,
            actor=actor,
            validation=report,
        )
        _write_workflow(updated)
        return updated, report


def submit_evidence_for_review(
    corpus_id: str,
    *,
    actor: str,
    note: str = "",
) -> EvidenceWorkflowRecordV1:
    with content_workflow.workflow_write_lock():
        _, record = _current(corpus_id)
        if record.state not in {"validated", "changes_requested"}:
            raise EvidenceInvalidTransition(
                f"Cannot submit evidence in {record.state} state."
            )
        if record.validation is None or not record.validation.valid:
            raise EvidenceInvalidTransition(
                "Evidence must pass validation before review."
            )
        updated = _transition(
            record,
            state="in_review",
            action="submit_review",
            actor=actor,
            note=note,
        )
        _write_workflow(updated)
        return updated


def review_evidence_draft(
    corpus_id: str,
    *,
    actor: str,
    decision: Literal["approve", "changes_requested"],
    note: str = "",
) -> EvidenceWorkflowRecordV1:
    reviewer = _actor(actor)
    with content_workflow.workflow_write_lock():
        _, record = _current(corpus_id)
        if record.state != "in_review":
            raise EvidenceInvalidTransition(
                f"Cannot review evidence in {record.state} state."
            )
        author_ids = {
            event.actor for event in record.history if event.action == "save"
        }
        if reviewer in author_ids:
            raise EvidenceInvalidTransition(
                "An evidence author cannot review the same draft."
            )
        if decision == "changes_requested" and not note.strip():
            raise EvidenceValidationFailed(
                "A change request must explain what needs revision."
            )
        updated = _transition(
            record,
            state=("approved" if decision == "approve" else "changes_requested"),
            action=("approve" if decision == "approve" else "request_changes"),
            actor=reviewer,
            note=note,
        )
        _write_workflow(updated)
        return updated


def seal_approved_evidence(
    corpus_id: str,
    *,
    actor: str,
) -> tuple[
    EvidenceCorpusV1,
    runtime_artifacts.RuntimeEvidenceRecord,
    EvidenceWorkflowRecordV1,
    bool,
]:
    publisher = _actor(actor)
    with content_workflow.workflow_write_lock():
        draft, record = _current(corpus_id)
        if record.state == "sealed":
            if record.sealed_version is None or record.sealed_checksum is None:
                raise content_data.ContentIntegrityError(
                    "Sealed evidence workflow is missing its immutable identity."
                )
            corpus, descriptor = runtime_artifacts.load_evidence_corpus(
                course_id=record.course_id,
                lesson_id=record.lesson_id,
                corpus_id=record.corpus_id,
                corpus_version=record.sealed_version,
                corpus_checksum=record.sealed_checksum,
            )
            return (
                corpus,
                runtime_artifacts.RuntimeEvidenceRecord(
                    descriptor=descriptor,
                    title=corpus.title,
                    source_count=len(corpus.sources),
                    passage_count=len(corpus.passages),
                ),
                record,
                True,
            )
        if record.state != "approved":
            raise EvidenceInvalidTransition(
                f"Cannot seal evidence in {record.state} state."
            )
        report = _validation_report(draft, actor=publisher)
        if not report.valid:
            raise EvidenceValidationFailed(
                "Approved evidence no longer passes validation.", report
            )

        previous = runtime_artifacts.list_staged_evidence(
            corpus_id=corpus_id,
        )
        version = max(
            (item.descriptor.version for item in previous),
            default=0,
        ) + 1
        now = _now()
        provisional = EvidenceCorpusV1(
            corpus_id=draft.corpus_id,
            course_id=draft.course_id,
            lesson_id=draft.lesson_id,
            corpus_version=version,
            title=draft.title,
            scope_note=draft.scope_note,
            sources=draft.sources,
            passages=draft.passages,
            created_at=draft.created_at or now,
            sealed_at=now,
            sealed_by=publisher,
            checksum="0" * 64,
        )
        corpus = sign_evidence_contract(provisional)
        descriptor = runtime_artifacts.descriptor_for_evidence(corpus)
        target = content_data.content_root() / Path(descriptor.path)
        existed = target.exists()
        staged = runtime_artifacts.stage_evidence_corpus(corpus)
        try:
            updated = _transition(
                record,
                state="sealed",
                action="seal",
                actor=publisher,
                note=f"Sealed immutable evidence corpus version {version}.",
                validation=report,
                sealed_version=version,
                sealed_checksum=str(corpus.checksum),
                event_sealed_version=version,
            )
            _write_workflow(updated)
        except BaseException:
            if not existed:
                target.unlink(missing_ok=True)
            raise
        return corpus, staged, updated, False


def evidence_draft_fingerprint(payload: EvidenceCorpusDraftV1) -> str:
    data = payload.model_dump(mode="json")
    for field in (
        "revision",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    ):
        data.pop(field, None)
    return _canonical_checksum(data)


def _validation_report(
    draft: EvidenceCorpusDraftV1,
    *,
    actor: str,
) -> EvidenceValidationReportV1:
    issues: list[EvidenceValidationIssueV1] = []
    if not draft.title.strip():
        _issue(issues, "title_required", "error", "title", "请填写证据库标题。")
    if not draft.scope_note.strip():
        _issue(
            issues,
            "scope_note_required",
            "error",
            "scope_note",
            "请说明证据库适用范围与史实边界。",
        )
    if not draft.sources:
        _issue(
            issues,
            "sources_required",
            "error",
            "sources",
            "证据库至少需要一项可复核来源。",
        )
    if not draft.passages:
        _issue(
            issues,
            "passages_required",
            "error",
            "passages",
            "证据库至少需要一个稳定证据片段。",
        )

    source_ids = [item.source_id for item in draft.sources]
    passage_ids = [item.passage_id for item in draft.passages]
    if len(source_ids) != len(set(source_ids)):
        _issue(
            issues,
            "duplicate_source_id",
            "error",
            "sources",
            "来源 source_id 必须唯一。",
        )
    if len(passage_ids) != len(set(passage_ids)):
        _issue(
            issues,
            "duplicate_passage_id",
            "error",
            "passages",
            "证据 passage_id 必须唯一。",
        )
    known_sources = set(source_ids)
    for index, passage in enumerate(draft.passages):
        if passage.source_id not in known_sources:
            _issue(
                issues,
                "unknown_source_id",
                "error",
                f"passages.{index}.source_id",
                f"证据片段引用了不存在的来源 {passage.source_id}。",
            )
        if not passage.fact_ids:
            _issue(
                issues,
                "fact_binding_required",
                "error",
                f"passages.{index}.fact_ids",
                "每个证据片段至少绑定一项课程事实。",
            )

    course = content_data.get_draft(draft.lesson_id)
    if course is None:
        _issue(
            issues,
            "course_draft_missing",
            "error",
            "lesson_id",
            "请先保存对应课时草稿，再校验证据事实绑定。",
        )
    elif course.course_id != draft.course_id:
        _issue(
            issues,
            "course_identity_mismatch",
            "error",
            "course_id",
            "证据库与课时草稿的 course_id 不一致。",
        )
    else:
        package = course_package_from_legacy(course)
        known_facts = {item.fact_id for item in package.facts}
        known_people = {item.person_id for item in package.people}
        for index, passage in enumerate(draft.passages):
            missing_facts = sorted(set(passage.fact_ids) - known_facts)
            missing_people = sorted(set(passage.person_ids) - known_people)
            if missing_facts:
                _issue(
                    issues,
                    "unknown_fact_binding",
                    "error",
                    f"passages.{index}.fact_ids",
                    "证据片段绑定了课时中不存在的事实："
                    + "、".join(missing_facts),
                )
            if missing_people:
                _issue(
                    issues,
                    "unknown_person_binding",
                    "error",
                    f"passages.{index}.person_ids",
                    "证据片段绑定了课时中不存在的人物："
                    + "、".join(missing_people),
                )

    if 0 < len(draft.sources) < 8:
        _issue(
            issues,
            "flagship_source_depth",
            "warning",
            "sources",
            "旗舰课发布验收建议准备 8–12 项可复核来源。",
        )
    if 0 < len(draft.passages) < 25:
        _issue(
            issues,
            "flagship_passage_depth",
            "warning",
            "passages",
            "旗舰课发布验收建议准备 25–40 个稳定证据片段。",
        )

    return EvidenceValidationReportV1(
        corpus_id=draft.corpus_id,
        course_id=draft.course_id,
        lesson_id=draft.lesson_id,
        draft_revision=draft.revision,
        draft_fingerprint=evidence_draft_fingerprint(draft),
        valid=not any(item.severity == "error" for item in issues),
        issues=tuple(issues),
        source_count=len(draft.sources),
        passage_count=len(draft.passages),
        validated_at=_now(),
        validated_by=_actor(actor),
    )


def _saved_record(
    draft: EvidenceCorpusDraftV1,
    previous: EvidenceWorkflowRecordV1 | None,
    *,
    actor: str,
) -> EvidenceWorkflowRecordV1:
    fingerprint = evidence_draft_fingerprint(draft)
    now = _now()
    if previous is None:
        event = EvidenceWorkflowEventV1(
            sequence=1,
            action="save",
            from_state="draft",
            to_state="draft",
            actor=actor,
            occurred_at=now,
            draft_revision=draft.revision,
            draft_fingerprint=fingerprint,
        )
        record = EvidenceWorkflowRecordV1(
            corpus_id=draft.corpus_id,
            course_id=draft.course_id,
            lesson_id=draft.lesson_id,
            state="draft",
            revision=1,
            draft_revision=draft.revision,
            draft_fingerprint=fingerprint,
            updated_at=now,
            history=(event,),
            checksum="0" * 64,
        )
        return _sign(record)
    if (
        previous.course_id,
        previous.lesson_id,
    ) != (draft.course_id, draft.lesson_id):
        raise EvidenceDraftConflict(
            "Evidence workflow identity cannot move between lessons."
        )
    return _transition(
        previous,
        state="draft",
        action="save",
        actor=actor,
        draft_revision=draft.revision,
        draft_fingerprint=fingerprint,
        validation=None,
    )


def _current(
    corpus_id: str,
) -> tuple[EvidenceCorpusDraftV1, EvidenceWorkflowRecordV1]:
    draft = get_evidence_draft(corpus_id)
    record = get_evidence_workflow(corpus_id)
    if draft is None or record is None:
        raise EvidenceDraftNotFound(f"Evidence draft not found: {corpus_id}")
    if (
        record.draft_revision != draft.revision
        or record.draft_fingerprint != evidence_draft_fingerprint(draft)
        or (record.course_id, record.lesson_id)
        != (draft.course_id, draft.lesson_id)
    ):
        raise content_data.ContentIntegrityError(
            "Evidence draft and workflow metadata disagree."
        )
    return draft, record


def _transition(
    record: EvidenceWorkflowRecordV1,
    *,
    state: EvidenceWorkflowState,
    action: EvidenceWorkflowAction,
    actor: str,
    note: str = "",
    draft_revision: int | None = None,
    draft_fingerprint: str | None = None,
    validation: EvidenceValidationReportV1 | None | object = ...,
    sealed_version: int | None | object = ...,
    sealed_checksum: str | None | object = ...,
    event_sealed_version: int | None = None,
) -> EvidenceWorkflowRecordV1:
    now = _now()
    data = record.model_dump(mode="json")
    current_revision = draft_revision or record.draft_revision
    current_fingerprint = draft_fingerprint or record.draft_fingerprint
    if validation is not ...:
        data["validation"] = (
            validation.model_dump(mode="json")
            if isinstance(validation, EvidenceValidationReportV1)
            else validation
        )
    if sealed_version is not ...:
        data["sealed_version"] = sealed_version
    if sealed_checksum is not ...:
        data["sealed_checksum"] = sealed_checksum
    event = EvidenceWorkflowEventV1(
        sequence=len(record.history) + 1,
        action=action,
        from_state=record.state,
        to_state=state,
        actor=_actor(actor),
        note=note,
        occurred_at=now,
        draft_revision=current_revision,
        draft_fingerprint=current_fingerprint,
        sealed_version=event_sealed_version,
    )
    data.update(
        state=state,
        revision=record.revision + 1,
        draft_revision=current_revision,
        draft_fingerprint=current_fingerprint,
        updated_at=now,
        history=[*data["history"], event.model_dump(mode="json")],
        checksum="0" * 64,
    )
    return _sign(EvidenceWorkflowRecordV1.model_validate(data))


def _write_workflow(record: EvidenceWorkflowRecordV1) -> None:
    content_data._atomic_write_json(
        _workflow_path(record.corpus_id),
        record.model_dump(mode="json"),
    )


def _restore_pair(
    *,
    draft_path: Path,
    draft: EvidenceCorpusDraftV1 | None,
    workflow_path: Path,
    workflow: EvidenceWorkflowRecordV1 | None,
) -> None:
    try:
        if draft is None:
            draft_path.unlink(missing_ok=True)
        else:
            content_data._atomic_write_json(
                draft_path, draft.model_dump(mode="json")
            )
        if workflow is None:
            workflow_path.unlink(missing_ok=True)
        else:
            content_data._atomic_write_json(
                workflow_path, workflow.model_dump(mode="json")
            )
    except OSError as exc:
        raise content_data.ContentIntegrityError(
            "Evidence save failed and previous metadata could not be restored."
        ) from exc


def _issue(
    issues: list[EvidenceValidationIssueV1],
    code: str,
    severity: Literal["error", "warning"],
    field: str,
    message: str,
) -> None:
    issues.append(
        EvidenceValidationIssueV1(
            code=code,
            severity=severity,
            field=field,
            message=message,
        )
    )


def _read_model(
    path: Path,
    model_type: type[EvidenceModelT],
) -> EvidenceModelT:
    try:
        return load_contract_file(path, model_type)
    except ScenarioFileError as exc:
        raise content_data.ContentIntegrityError(
            f"Cannot read evidence metadata: {path}"
        ) from exc


def _read_signed(path: Path, model_type):
    record = _read_model(path, model_type)
    if record.checksum != _model_checksum(record):
        raise content_data.ContentIntegrityError(
            f"Evidence workflow checksum mismatch: {path}"
        )
    return record


def _sign(record: EvidenceWorkflowRecordV1) -> EvidenceWorkflowRecordV1:
    data = record.model_dump(mode="json")
    data["checksum"] = _model_checksum(record)
    return EvidenceWorkflowRecordV1.model_validate(data)


def _model_checksum(record: BaseModel) -> str:
    data = record.model_dump(mode="json")
    data["checksum"] = None
    return _canonical_checksum(data)


def _canonical_checksum(payload: object) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _draft_path(corpus_id: str) -> Path:
    return content_data.evidence_draft_dir() / f"{_id(corpus_id)}.json"


def _canonical_draft_path(corpus_id: str) -> Path:
    return content_data.evidence_draft_dir().resolve() / f"{_id(corpus_id)}.json"


def _workflow_path(corpus_id: str) -> Path:
    return content_data.evidence_workflow_dir() / f"{_id(corpus_id)}.json"


def _canonical_workflow_path(corpus_id: str) -> Path:
    return content_data.evidence_workflow_dir().resolve() / f"{_id(corpus_id)}.json"


def _id(value: str) -> str:
    return _CONTRACT_ID_ADAPTER.validate_python(value)


def _actor(value: str) -> str:
    return value.strip() or "admin"


def _now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "EvidenceCorpusDraftV1",
    "EvidenceDraftConflict",
    "EvidenceDraftNotFound",
    "EvidenceInvalidTransition",
    "EvidenceValidationFailed",
    "EvidenceValidationIssueV1",
    "EvidenceValidationReportV1",
    "EvidenceWorkflowRecordV1",
    "evidence_draft_fingerprint",
    "get_evidence_draft",
    "get_evidence_workflow",
    "list_evidence_drafts",
    "review_evidence_draft",
    "save_evidence_draft",
    "seal_approved_evidence",
    "submit_evidence_for_review",
    "validate_evidence_draft",
]
