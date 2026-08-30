from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints, TypeAdapter, model_validator

from services.contracts.evidence_v1 import EvidenceContractModel, EvidenceCorpusV1, EvidenceSourceV1
from services.contracts.v1 import Checksum, ContractId, NonEmptyText


AtomicText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1200)]


class EvidenceBoundaryV1(EvidenceContractModel):
    boundary_id: ContractId
    label: NonEmptyText
    category: Literal[
        "chronology", "source_distance", "claim_limit", "causation",
        "persona_knowledge", "modern_concept", "teaching_model",
    ]
    statement: AtomicText


class EvidenceAnswerSlotV1(EvidenceContractModel):
    slot_id: ContractId
    label: NonEmptyText
    status: Literal["supported", "unsupported"]
    response_mode: Literal["overview", "identity", "topic", "boundary"]
    question_form: Literal[
        "any", "identity", "creator_identity", "causality", "comparison", "evidence_boundary",
    ] = "any"
    term_groups: tuple[tuple[NonEmptyText, ...], ...] = Field(min_length=1)
    passage_ids: tuple[ContractId, ...] = ()
    boundary_ids: tuple[ContractId, ...] = ()
    api_synthesis_allowed: bool = False

    @model_validator(mode="after")
    def validate_slot(self) -> "EvidenceAnswerSlotV1":
        _sorted_unique(self.passage_ids, "answer-slot passage_ids")
        _sorted_unique(self.boundary_ids, "answer-slot boundary_ids")
        if any(not group for group in self.term_groups):
            raise ValueError("answer-slot term_groups cannot contain an empty group")
        for group in self.term_groups:
            _sorted_unique(group, "answer-slot term group")
        if self.status == "supported" and not self.passage_ids:
            raise ValueError("supported answer slots require passage_ids")
        if self.status == "unsupported":
            if self.passage_ids:
                raise ValueError("unsupported answer slots cannot cite passages")
            if not self.boundary_ids:
                raise ValueError("unsupported answer slots require a boundary")
            if self.api_synthesis_allowed:
                raise ValueError("unsupported answer slots cannot allow API synthesis")
        return self


class EvidencePassageV2(EvidenceContractModel):
    passage_id: ContractId
    source_id: ContractId
    title: NonEmptyText
    text: AtomicText
    summary: AtomicText
    source_locator: NonEmptyText
    fact_ids: tuple[ContractId, ...] = ()
    person_ids: tuple[ContractId, ...] = ()
    keywords: tuple[NonEmptyText, ...] = ()
    answer_slot_ids: tuple[ContractId, ...] = ()
    boundary_ids: tuple[ContractId, ...] = ()
    persona_scope: Literal["expert_only", "expert_and_listed_people"] = "expert_only"
    evidence_kind: Literal[
        "curriculum_goal", "transmitted_text", "archaeological_evidence",
        "scholarly_interpretation", "teaching_explanation", "boundary_note",
    ]
    certainty: Literal["consensus", "interpretation", "legend", "disputed"]
    chronology_note: NonEmptyText
    teaching_note: str = ""

    @model_validator(mode="after")
    def validate_references(self) -> "EvidencePassageV2":
        for values, label in (
            (self.fact_ids, "passage fact_ids"), (self.person_ids, "passage person_ids"),
            (self.keywords, "passage keywords"), (self.answer_slot_ids, "passage answer_slot_ids"),
            (self.boundary_ids, "passage boundary_ids"),
        ):
            _sorted_unique(values, label)
        if self.persona_scope == "expert_only" and self.person_ids:
            raise ValueError("expert_only passages cannot bind people")
        if self.persona_scope == "expert_and_listed_people" and not self.person_ids:
            raise ValueError("expert_and_listed_people passages require person_ids")
        return self


class EvidenceCorpusV2(EvidenceContractModel):
    schema_version: Literal["evidence-corpus/v2"] = "evidence-corpus/v2"
    corpus_id: ContractId
    course_id: ContractId
    lesson_id: ContractId
    corpus_version: int = Field(ge=1)
    status: Literal["sealed"] = "sealed"
    title: NonEmptyText
    scope_note: NonEmptyText
    supersedes_checksum: Checksum
    sources: tuple[EvidenceSourceV1, ...] = Field(min_length=1)
    boundaries: tuple[EvidenceBoundaryV1, ...] = Field(min_length=1)
    answer_slots: tuple[EvidenceAnswerSlotV1, ...] = Field(min_length=1)
    passages: tuple[EvidencePassageV2, ...] = Field(min_length=1)
    created_at: AwareDatetime
    sealed_at: AwareDatetime
    sealed_by: NonEmptyText
    checksum: Checksum

    @model_validator(mode="after")
    def validate_corpus(self) -> "EvidenceCorpusV2":
        sources = {item.source_id for item in self.sources}
        passages = {item.passage_id for item in self.passages}
        boundaries = {item.boundary_id for item in self.boundaries}
        boundary_categories = {
            item.boundary_id: item.category for item in self.boundaries
        }
        slots = {item.slot_id for item in self.answer_slots}
        for values, label in (
            ([x.source_id for x in self.sources], "evidence sources"),
            ([x.boundary_id for x in self.boundaries], "evidence boundaries"),
            ([x.slot_id for x in self.answer_slots], "evidence answer slots"),
            ([x.passage_id for x in self.passages], "evidence passages"),
        ):
            _sorted_unique(values, label)
        for passage in self.passages:
            if passage.source_id not in sources:
                raise ValueError(f"passage {passage.passage_id} references unknown source_id")
            if set(passage.boundary_ids) - boundaries or set(passage.answer_slot_ids) - slots:
                raise ValueError(f"passage {passage.passage_id} has unknown slot or boundary references")
            if (
                passage.persona_scope == "expert_and_listed_people"
                and not any(
                    boundary_categories[item] == "persona_knowledge"
                    for item in passage.boundary_ids
                )
            ):
                raise ValueError(
                    "persona-scoped passages require a persona_knowledge boundary"
                )
        for slot in self.answer_slots:
            if set(slot.passage_ids) - passages or set(slot.boundary_ids) - boundaries:
                raise ValueError(f"answer slot {slot.slot_id} has unknown passage or boundary references")
            linked = {passage.passage_id for passage in self.passages if slot.slot_id in passage.answer_slot_ids}
            if set(slot.passage_ids) != linked:
                raise ValueError(f"answer slot {slot.slot_id} passage bindings must be declared bidirectionally")
            if slot.status == "supported":
                linked_passages = [passage for passage in self.passages if passage.passage_id in linked]
                linked_boundaries = {boundary_id for passage in linked_passages for boundary_id in passage.boundary_ids}
                if set(slot.boundary_ids) - linked_boundaries:
                    raise ValueError(f"answer slot {slot.slot_id} boundary bindings must be present on a linked passage")
                if slot.api_synthesis_allowed:
                    if not slot.boundary_ids:
                        raise ValueError(
                            "API-enabled answer slots require at least one boundary"
                        )
                    if len(linked_passages) < 3:
                        raise ValueError("API-enabled answer slots require at least three passages")
                    if len({passage.source_id for passage in linked_passages}) < 2:
                        raise ValueError("API-enabled answer slots require at least two sources")
                    if len({passage.evidence_kind for passage in linked_passages}) < 2:
                        raise ValueError("API-enabled answer slots require at least two evidence kinds")
        if self.sealed_at < self.created_at:
            raise ValueError("sealed_at cannot precede created_at")
        return self


EvidenceCorpusAny = Annotated[EvidenceCorpusV1 | EvidenceCorpusV2, Field(discriminator="schema_version")]
EVIDENCE_CORPUS_ADAPTER = TypeAdapter(EvidenceCorpusAny)
EVIDENCE_V2_SCHEMA_DOCUMENTS = {
    "evidence-corpus.schema.json": (
        EvidenceCorpusV2,
        "https://chronovita.local/schemas/evidence/v2/evidence-corpus.schema.json",
    )
}


def parse_evidence_corpus(payload: object) -> EvidenceCorpusAny:
    return EVIDENCE_CORPUS_ADAPTER.validate_python(payload)


def _sorted_unique(values, label: str) -> None:
    normalized = list(values)
    if normalized != sorted(set(normalized)):
        raise ValueError(f"{label} must be unique and sorted")


__all__ = [
    "EVIDENCE_CORPUS_ADAPTER", "EVIDENCE_V2_SCHEMA_DOCUMENTS", "EvidenceAnswerSlotV1", "EvidenceBoundaryV1",
    "EvidenceCorpusAny", "EvidenceCorpusV2", "EvidencePassageV2", "parse_evidence_corpus",
]
