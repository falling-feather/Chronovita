from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, TypeVar

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from services.contracts.v1 import Checksum, ContractId, NonEmptyText


class EvidenceContractModel(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        str_strip_whitespace=True,
    )


EvidenceContractT = TypeVar("EvidenceContractT", bound=EvidenceContractModel)


class EvidenceSourceV1(EvidenceContractModel):
    source_id: ContractId
    title: NonEmptyText
    kind: Literal[
        "curriculum",
        "textbook",
        "primary_source",
        "archaeology",
        "museum",
        "research",
        "other",
    ]
    author_or_institution: str = ""
    publisher: str = ""
    published_year: int | None = Field(default=None, ge=-3000, le=3000)
    url_or_path: NonEmptyText
    locator: str = ""
    citation_note: str = ""
    reliability: Literal["reviewed", "disputed"] = "reviewed"
    rights_note: NonEmptyText


class EvidencePassageV1(EvidenceContractModel):
    passage_id: ContractId
    source_id: ContractId
    title: NonEmptyText
    text: NonEmptyText
    summary: NonEmptyText
    fact_ids: tuple[ContractId, ...] = ()
    person_ids: tuple[ContractId, ...] = ()
    keywords: tuple[NonEmptyText, ...] = ()
    evidence_kind: Literal[
        "curriculum_goal",
        "transmitted_text",
        "archaeological_evidence",
        "scholarly_interpretation",
        "teaching_explanation",
        "boundary_note",
    ]
    certainty: Literal["consensus", "interpretation", "legend", "disputed"]
    chronology_note: NonEmptyText
    teaching_note: str = ""

    @model_validator(mode="after")
    def validate_ordered_references(self) -> "EvidencePassageV1":
        _require_sorted_unique(self.fact_ids, "passage fact_ids")
        _require_sorted_unique(self.person_ids, "passage person_ids")
        _require_sorted_unique(self.keywords, "passage keywords")
        return self


class EvidenceCorpusV1(EvidenceContractModel):
    schema_version: Literal["evidence-corpus/v1"] = "evidence-corpus/v1"
    corpus_id: ContractId
    course_id: ContractId
    lesson_id: ContractId
    corpus_version: int = Field(ge=1)
    status: Literal["sealed"] = "sealed"
    title: NonEmptyText
    scope_note: NonEmptyText
    sources: tuple[EvidenceSourceV1, ...] = Field(min_length=1)
    passages: tuple[EvidencePassageV1, ...] = Field(min_length=1)
    created_at: AwareDatetime
    sealed_at: AwareDatetime
    sealed_by: NonEmptyText
    checksum: Checksum

    @model_validator(mode="after")
    def validate_corpus(self) -> "EvidenceCorpusV1":
        source_ids = [item.source_id for item in self.sources]
        passage_ids = [item.passage_id for item in self.passages]
        _require_sorted_unique(source_ids, "evidence sources")
        _require_sorted_unique(passage_ids, "evidence passages")
        known_sources = set(source_ids)
        for passage in self.passages:
            if passage.source_id not in known_sources:
                raise ValueError(
                    f"passage {passage.passage_id} references unknown source_id"
                )
        if self.sealed_at < self.created_at:
            raise ValueError("sealed_at cannot precede created_at")
        return self


class LessonPresentationV1(EvidenceContractModel):
    schema_version: Literal["lesson-presentation/v1"] = "lesson-presentation/v1"
    presentation_id: ContractId
    course_id: ContractId
    lesson_id: ContractId
    presentation_version: int = Field(ge=1)
    status: Literal["sealed"] = "sealed"
    title: NonEmptyText
    estimated_minutes: int = Field(ge=35, le=45)
    phase_minutes: dict[Literal["observe", "decide", "consult", "dossier"], int]
    video_path: NonEmptyText
    poster_path: NonEmptyText
    transcript_path: NonEmptyText
    video_duration_seconds: float = Field(ge=45, le=60)
    video_width: Literal[1920] = 1920
    video_height: Literal[1080] = 1080
    video_fps: Literal[30] = 30
    video_sha256: Checksum
    poster_sha256: Checksum
    transcript_sha256: Checksum
    skip_allowed: Literal[True] = True
    accessibility_note: NonEmptyText
    sealed_at: AwareDatetime
    sealed_by: NonEmptyText
    checksum: Checksum

    @model_validator(mode="after")
    def validate_presentation(self) -> "LessonPresentationV1":
        if set(self.phase_minutes) != {"observe", "decide", "consult", "dossier"}:
            raise ValueError("phase_minutes must define all four classroom phases")
        phase_limits = {
            "observe": (8, 10),
            "decide": (12, 15),
            "consult": (5, 8),
            "dossier": (8, 10),
        }
        for phase, (minimum, maximum) in phase_limits.items():
            if not minimum <= self.phase_minutes[phase] <= maximum:
                raise ValueError(
                    f"{phase} phase must be between {minimum} and {maximum} minutes"
                )
        if sum(self.phase_minutes.values()) != self.estimated_minutes:
            raise ValueError("phase_minutes must sum to estimated_minutes")
        for path, suffix in (
            (self.video_path, ".mp4"),
            (self.poster_path, ".webp"),
            (self.transcript_path, ".md"),
        ):
            _require_release_asset_path(path, self.lesson_id, suffix)
        expected_root = (
            f"media/lessons/{self.lesson_id}/"
            f"v{self.presentation_version:03d}/"
        )
        if any(
            not path.startswith(expected_root)
            for path in (
                self.video_path,
                self.poster_path,
                self.transcript_path,
            )
        ):
            raise ValueError(
                "presentation assets must stay inside their immutable version root: "
                f"{expected_root}"
            )
        return self


class RagCitationV1(EvidenceContractModel):
    citation_id: ContractId
    passage_id: ContractId
    source_id: ContractId
    source_title: NonEmptyText
    locator: str = ""
    excerpt: NonEmptyText
    relevance: float = Field(ge=0, le=1)
    certainty: Literal["consensus", "interpretation", "legend", "disputed"]


RagQuestion = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=400),
]


class RagAskRequestV1(EvidenceContractModel):
    course_id: ContractId
    lesson_id: ContractId
    persona_mode: Literal["expert", "person"]
    person_id: ContractId | None = None
    question: RagQuestion

    @model_validator(mode="after")
    def validate_persona(self) -> "RagAskRequestV1":
        if self.persona_mode == "person" and self.person_id is None:
            raise ValueError("person persona_mode requires person_id")
        if self.persona_mode == "expert" and self.person_id is not None:
            raise ValueError("expert persona_mode cannot carry person_id")
        return self


class RagAnswerV1(EvidenceContractModel):
    schema_version: Literal["rag-answer/v1"] = "rag-answer/v1"
    answer_source: Literal["model", "extractive", "insufficient_evidence"]
    retrieval_mode: Literal["hybrid", "lexical"] = "lexical"
    body: NonEmptyText
    persona_mode: Literal["expert", "person"]
    person_id: ContractId | None = None
    role_disclaimer: Literal["角色化教学表达，不是史料原话。"] | None = None
    citations: tuple[RagCitationV1, ...] = ()
    retrieved_passage_ids: tuple[ContractId, ...] = ()
    course_id: ContractId
    lesson_id: ContractId
    release_id: ContractId
    release_no: int = Field(ge=1)
    release_checksum: Checksum
    evidence_corpus_id: ContractId
    evidence_version: int = Field(ge=1)
    evidence_checksum: Checksum
    uncertainty: Literal["low", "medium", "high"]

    @model_validator(mode="after")
    def validate_grounding(self) -> "RagAnswerV1":
        _require_unique(self.retrieved_passage_ids, "retrieved_passage_ids")
        citation_ids = [item.citation_id for item in self.citations]
        _require_sorted_unique(citation_ids, "citation ids")
        _require_unique(
            [item.passage_id for item in self.citations],
            "citation passage ids",
        )
        retrieved = set(self.retrieved_passage_ids)
        if any(item.passage_id not in retrieved for item in self.citations):
            raise ValueError("every citation must belong to retrieved_passage_ids")
        if self.answer_source == "insufficient_evidence" and self.citations:
            raise ValueError("insufficient evidence answers cannot manufacture citations")
        if self.answer_source != "insufficient_evidence" and not self.citations:
            raise ValueError("grounded answers require at least one citation")
        if self.persona_mode == "person":
            if self.person_id is None:
                raise ValueError("person persona_mode requires person_id")
            if self.role_disclaimer is None:
                raise ValueError("person answers require the role-expression disclaimer")
        elif self.person_id is not None or self.role_disclaimer is not None:
            raise ValueError("expert answers cannot carry a person identity or disclaimer")
        return self


def calculate_evidence_checksum(payload: BaseModel) -> str:
    data = payload.model_dump(mode="json")
    if "checksum" not in data:
        raise ValueError("evidence contract does not expose checksum")
    data["checksum"] = None
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sign_evidence_contract(payload: EvidenceContractT) -> EvidenceContractT:
    data = payload.model_dump(mode="json")
    data["checksum"] = calculate_evidence_checksum(payload)
    return type(payload).model_validate(data)


def verify_evidence_checksum(payload: BaseModel) -> bool:
    checksum = getattr(payload, "checksum", None)
    return isinstance(checksum, str) and checksum == calculate_evidence_checksum(payload)


def evidence_schema_document(model: type[BaseModel], schema_id: str) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": schema_id,
        "$comment": (
            "Pydantic semantic validation additionally enforces stable ordering, "
            "cross-source references, classroom media boundaries and citation grounding."
        ),
        **model.model_json_schema(ref_template="#/$defs/{model}"),
    }


EVIDENCE_SCHEMA_DOCUMENTS: dict[str, tuple[type[BaseModel], str]] = {
    "evidence-corpus.schema.json": (
        EvidenceCorpusV1,
        "https://chronovita.local/schemas/evidence/v1/evidence-corpus.schema.json",
    ),
    "lesson-presentation.schema.json": (
        LessonPresentationV1,
        "https://chronovita.local/schemas/evidence/v1/lesson-presentation.schema.json",
    ),
    "rag-ask-request.schema.json": (
        RagAskRequestV1,
        "https://chronovita.local/schemas/evidence/v1/rag-ask-request.schema.json",
    ),
    "rag-answer.schema.json": (
        RagAnswerV1,
        "https://chronovita.local/schemas/evidence/v1/rag-answer.schema.json",
    ),
}


def _require_sorted_unique(values, label: str) -> None:
    normalized = list(values)
    if normalized != sorted(set(normalized)):
        raise ValueError(f"{label} must be unique and sorted")


def _require_unique(values, label: str) -> None:
    normalized = list(values)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} must be unique")


def _require_release_asset_path(path: str, lesson_id: str, suffix: str) -> None:
    prefix = f"media/lessons/{lesson_id}/"
    if (
        not path.startswith(prefix)
        or "\\" in path
        or ".." in path.split("/")
        or not path.endswith(suffix)
    ):
        raise ValueError(
            "presentation assets must use the canonical path for their lesson: "
            f"{prefix}*{suffix}"
        )


__all__ = [
    "EVIDENCE_SCHEMA_DOCUMENTS",
    "EvidenceCorpusV1",
    "EvidencePassageV1",
    "EvidenceSourceV1",
    "LessonPresentationV1",
    "RagAskRequestV1",
    "RagAnswerV1",
    "RagCitationV1",
    "calculate_evidence_checksum",
    "evidence_schema_document",
    "sign_evidence_contract",
    "verify_evidence_checksum",
]
