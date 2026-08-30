from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from services.contracts.v1 import Checksum, ContractId

MAX_CONVERSATION_TURNS = 24
RECENT_CONTEXT_TURNS = 6
MAX_CURRENT_EVIDENCE_PASSAGES = 32

ClientMessageId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
ConversationQuestion = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=400),
]
AnswerSnapshot = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000),
]
RouteReason = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]
PersonaConversationChannel = Literal["consult", "scenario"]
PersonaRouteTarget = Literal[
    "local_template",
    "external_api",
    "clarify",
    "refuse",
]
PersonaAnswerSource = Literal[
    "model",
    "extractive",
    "insufficient_evidence",
]
PersonaAnswerUncertainty = Literal["low", "medium", "high"]
PersonaRetrievalMode = Literal["lexical", "hybrid"]


class PersonaConversationModel(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        str_strip_whitespace=True,
    )


class PersonaConversationIdentityV1(PersonaConversationModel):
    """Exact immutable artifact and owner scope for one persona conversation."""

    owner_user_id: ContractId
    course_id: ContractId
    lesson_id: ContractId
    release_id: ContractId
    release_no: int = Field(ge=1)
    release_checksum: Checksum
    persona_pack_id: ContractId
    persona_pack_version: int = Field(ge=1)
    persona_pack_checksum: Checksum
    evidence_corpus_id: ContractId
    evidence_version: int = Field(ge=1)
    evidence_checksum: Checksum
    person_id: ContractId
    channel: PersonaConversationChannel


class PersonaConversationTurnInputV1(PersonaConversationModel):
    """The bounded semantic payload used for message idempotency."""

    client_message_id: ClientMessageId
    question: ConversationQuestion
    answer_snapshot: AnswerSnapshot = Field(
        description=(
            "Non-authoritative display snapshot. It is conversation continuity, "
            "not evidence and not a source quotation."
        )
    )
    route_target: PersonaRouteTarget
    route_reason: RouteReason
    answer_source: PersonaAnswerSource
    uncertainty: PersonaAnswerUncertainty
    retrieval_mode: PersonaRetrievalMode = "lexical"
    slot_ids: tuple[ContractId, ...] = Field(default=(), max_length=12)
    boundary_ids: tuple[ContractId, ...] = Field(default=(), max_length=12)
    passage_ids: tuple[ContractId, ...] = Field(default=(), max_length=12)
    retrieved_passage_ids: tuple[ContractId, ...] = Field(
        default=(),
        max_length=12,
    )

    @model_validator(mode="after")
    def validate_reference_ids(self) -> PersonaConversationTurnInputV1:
        _require_unique(self.slot_ids, "slot_ids")
        _require_unique(self.boundary_ids, "boundary_ids")
        _require_unique(self.passage_ids, "passage_ids")
        _require_unique(self.retrieved_passage_ids, "retrieved_passage_ids")
        if any(
            passage_id not in self.retrieved_passage_ids
            for passage_id in self.passage_ids
        ):
            raise ValueError("cited passage_ids must belong to retrieved_passage_ids")
        return self


class PersonaConversationTurnV1(PersonaConversationTurnInputV1):
    turn_no: int = Field(ge=1, le=MAX_CONVERSATION_TURNS)
    based_on_revision: int = Field(ge=1, le=MAX_CONVERSATION_TURNS)
    occurred_at: AwareDatetime
    source_payload_checksum: Checksum

    @model_validator(mode="after")
    def validate_source_payload_checksum(self) -> PersonaConversationTurnV1:
        if self.source_payload_checksum != conversation_turn_input_checksum(self):
            raise ValueError("persona conversation turn checksum is invalid")
        return self


class PersonaConversationV1(PersonaConversationModel):
    schema_version: Literal["persona-conversation/v1"] = "persona-conversation/v1"
    conversation_id: ContractId
    owner_user_id: ContractId
    course_id: ContractId
    lesson_id: ContractId
    release_id: ContractId
    release_no: int = Field(ge=1)
    release_checksum: Checksum
    persona_pack_id: ContractId
    persona_pack_version: int = Field(ge=1)
    persona_pack_checksum: Checksum
    evidence_corpus_id: ContractId
    evidence_version: int = Field(ge=1)
    evidence_checksum: Checksum
    person_id: ContractId
    channel: PersonaConversationChannel
    revision: int = Field(ge=1, le=MAX_CONVERSATION_TURNS + 1)
    turns: tuple[PersonaConversationTurnV1, ...] = Field(
        default=(),
        max_length=MAX_CONVERSATION_TURNS,
    )
    created_at: AwareDatetime
    updated_at: AwareDatetime
    checksum: Checksum

    @model_validator(mode="after")
    def validate_conversation(self) -> PersonaConversationV1:
        if self.revision != len(self.turns) + 1:
            raise ValueError("conversation revision must equal turn count plus one")
        expected_turns = list(range(1, len(self.turns) + 1))
        if [item.turn_no for item in self.turns] != expected_turns:
            raise ValueError("conversation turn numbers must be contiguous")
        if [item.based_on_revision for item in self.turns] != expected_turns:
            raise ValueError(
                "conversation turns must record the revision they answered"
            )
        _require_unique(
            [item.client_message_id for item in self.turns],
            "client_message_ids",
        )
        if self.updated_at < self.created_at:
            raise ValueError("conversation updated_at cannot precede created_at")
        if not self.turns:
            if self.updated_at != self.created_at:
                raise ValueError("an empty conversation must have matching timestamps")
        else:
            previous = self.created_at
            for turn in self.turns:
                if turn.occurred_at < previous:
                    raise ValueError(
                        "conversation turn timestamps must be chronological"
                    )
                previous = turn.occurred_at
            if self.updated_at != self.turns[-1].occurred_at:
                raise ValueError("conversation updated_at must match the latest turn")
        if self.checksum != calculate_persona_conversation_checksum(self):
            raise ValueError("persona conversation checksum is invalid")
        return self

    def identity(self) -> PersonaConversationIdentityV1:
        return PersonaConversationIdentityV1(
            **{field: getattr(self, field) for field in _IDENTITY_FIELDS}
        )


class PersonaConversationContextV1(PersonaConversationModel):
    """Recent memory plus a caller-owned, never-memory-derived evidence allowlist."""

    schema_version: Literal["persona-conversation-context/v1"] = (
        "persona-conversation-context/v1"
    )
    conversation_id: ContractId
    identity: PersonaConversationIdentityV1
    revision: int = Field(ge=1)
    recent_turns: tuple[PersonaConversationTurnV1, ...] = Field(
        default=(),
        max_length=RECENT_CONTEXT_TURNS,
    )
    current_allowed_passage_ids: tuple[ContractId, ...] = Field(
        default=(),
        max_length=MAX_CURRENT_EVIDENCE_PASSAGES,
        description=(
            "Whitelist supplied by the current retrieval only; remembered passage "
            "IDs are never unioned into it."
        ),
    )
    evidence_allowlist_source: Literal["current_request_only"] = "current_request_only"

    @model_validator(mode="after")
    def validate_context(self) -> PersonaConversationContextV1:
        _require_unique(
            self.current_allowed_passage_ids,
            "current_allowed_passage_ids",
        )
        if len(self.recent_turns) > RECENT_CONTEXT_TURNS:
            raise ValueError("persona context exceeds the recent-turn limit")
        return self


_IDENTITY_FIELDS = (
    "owner_user_id",
    "course_id",
    "lesson_id",
    "release_id",
    "release_no",
    "release_checksum",
    "persona_pack_id",
    "persona_pack_version",
    "persona_pack_checksum",
    "evidence_corpus_id",
    "evidence_version",
    "evidence_checksum",
    "person_id",
    "channel",
)
_TURN_INPUT_FIELDS = (
    "client_message_id",
    "question",
    "answer_snapshot",
    "route_target",
    "route_reason",
    "answer_source",
    "uncertainty",
    "retrieval_mode",
    "slot_ids",
    "boundary_ids",
    "passage_ids",
    "retrieved_passage_ids",
)


def new_persona_conversation(
    identity: PersonaConversationIdentityV1,
    *,
    conversation_id: str | None = None,
    created_at: datetime | None = None,
) -> PersonaConversationV1:
    checked_identity = PersonaConversationIdentityV1.model_validate(
        identity.model_dump(mode="json")
    )
    timestamp = created_at or datetime.now(timezone.utc)
    payload = {
        "schema_version": "persona-conversation/v1",
        "conversation_id": conversation_id or f"pcv_{uuid4().hex}",
        **checked_identity.model_dump(mode="json"),
        "revision": 1,
        "turns": [],
        "created_at": _json_datetime(timestamp),
        "updated_at": _json_datetime(timestamp),
        "checksum": None,
    }
    payload["checksum"] = _checksum(payload)
    return PersonaConversationV1.model_validate(payload)


def conversation_turn_input_checksum(
    turn: PersonaConversationTurnInputV1 | PersonaConversationTurnV1,
) -> str:
    payload = {field: getattr(turn, field) for field in _TURN_INPUT_FIELDS}
    return _checksum(payload)


def calculate_persona_conversation_checksum(
    conversation: PersonaConversationV1,
) -> str:
    payload = conversation.model_dump(mode="json")
    payload["checksum"] = None
    return _checksum(payload)


def conversation_identity_tuple(
    conversation: PersonaConversationV1,
) -> tuple[object, ...]:
    return tuple(getattr(conversation, field) for field in _IDENTITY_FIELDS)


def _checksum(payload: object) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _require_unique(values, label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _json_datetime(value: datetime) -> str:
    rendered = value.isoformat()
    return rendered[:-6] + "Z" if rendered.endswith("+00:00") else rendered


__all__ = [
    "MAX_CONVERSATION_TURNS",
    "MAX_CURRENT_EVIDENCE_PASSAGES",
    "RECENT_CONTEXT_TURNS",
    "AnswerSnapshot",
    "ClientMessageId",
    "ConversationQuestion",
    "PersonaAnswerSource",
    "PersonaAnswerUncertainty",
    "PersonaConversationChannel",
    "PersonaConversationContextV1",
    "PersonaConversationIdentityV1",
    "PersonaConversationTurnInputV1",
    "PersonaConversationTurnV1",
    "PersonaConversationV1",
    "PersonaRouteTarget",
    "PersonaRetrievalMode",
    "RouteReason",
    "calculate_persona_conversation_checksum",
    "conversation_identity_tuple",
    "conversation_turn_input_checksum",
    "new_persona_conversation",
]
