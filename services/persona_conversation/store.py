from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

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
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .models import (
    MAX_CONVERSATION_TURNS,
    RECENT_CONTEXT_TURNS,
    PersonaConversationContextV1,
    PersonaConversationTurnInputV1,
    PersonaConversationTurnV1,
    PersonaConversationV1,
    calculate_persona_conversation_checksum,
    conversation_turn_input_checksum,
)

MAX_CONVERSATION_RECORD_BYTES = 256 * 1024
MAX_CONVERSATION_TURN_BYTES = 16 * 1024


class PersonaConversationStoreError(RuntimeError):
    code = "persona_conversation_storage_unavailable"


class PersonaConversationNotFound(PersonaConversationStoreError):
    code = "persona_conversation_not_found"


class PersonaConversationConflict(PersonaConversationStoreError):
    code = "persona_conversation_conflict"


class PersonaConversationAlreadyExists(PersonaConversationConflict):
    code = "persona_conversation_already_exists"


class PersonaConversationWriteConflict(PersonaConversationConflict):
    code = "persona_conversation_write_conflict"


class PersonaMessageIdConflict(PersonaConversationConflict):
    code = "persona_message_id_conflict"


class PersonaConversationLimitReached(PersonaConversationConflict):
    code = "persona_conversation_limit_reached"


class PersonaConversationIntegrityError(PersonaConversationStoreError):
    code = "persona_conversation_integrity_error"


@dataclass(frozen=True)
class StoredPersonaConversationRecord:
    conversation: PersonaConversationV1
    raw_data: str


@dataclass(frozen=True)
class PersonaConversationAppendResult:
    conversation: PersonaConversationV1
    turn: PersonaConversationTurnV1
    reused: bool


_METADATA = MetaData()

persona_conversations_table = Table(
    "persona_conversations",
    _METADATA,
    Column("conversation_id", String(64), primary_key=True),
    Column("owner_user_id", String(64), nullable=False),
    Column("course_id", String(64), nullable=False),
    Column("lesson_id", String(64), nullable=False),
    Column("release_id", String(64), nullable=False),
    Column("release_no", Integer, nullable=False),
    Column("release_checksum", String(64), nullable=False),
    Column("persona_pack_id", String(64), nullable=False),
    Column("persona_pack_version", Integer, nullable=False),
    Column("persona_pack_checksum", String(64), nullable=False),
    Column("evidence_corpus_id", String(64), nullable=False),
    Column("evidence_version", Integer, nullable=False),
    Column("evidence_checksum", String(64), nullable=False),
    Column("person_id", String(64), nullable=False),
    Column("channel", String(16), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("data", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index(
        "ix_persona_conversation_owner_lesson",
        "owner_user_id",
        "course_id",
        "lesson_id",
    ),
    Index(
        "ix_persona_conversation_owner_person",
        "owner_user_id",
        "person_id",
    ),
    Index("ix_persona_conversation_updated_at", "updated_at"),
)


class PersonaConversationStore:
    """Checksum-validated whole-record CAS for bounded persona memory."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create_conversation(
        self,
        conversation: PersonaConversationV1,
    ) -> StoredPersonaConversationRecord:
        checked = _validate_conversation(conversation)
        if checked.revision != 1 or checked.turns:
            raise ValueError("a new persona conversation must be empty")
        raw_data = encode_persona_conversation(checked)
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    insert(persona_conversations_table).values(
                        **_row_values(checked, raw_data)
                    )
                )
        except IntegrityError as exc:
            raise PersonaConversationAlreadyExists(
                "persona conversation already exists"
            ) from exc
        except SQLAlchemyError as exc:
            raise PersonaConversationStoreError(
                "persona conversation write failed"
            ) from exc
        return StoredPersonaConversationRecord(
            conversation=checked,
            raw_data=raw_data,
        )

    def load_conversation(
        self,
        conversation_id: str,
        *,
        owner_user_id: str,
    ) -> StoredPersonaConversationRecord:
        try:
            with self.engine.connect() as connection:
                row = (
                    connection.execute(
                        select(persona_conversations_table).where(
                            persona_conversations_table.c.conversation_id
                            == conversation_id,
                            persona_conversations_table.c.owner_user_id
                            == owner_user_id,
                        )
                    )
                    .mappings()
                    .first()
                )
        except SQLAlchemyError as exc:
            raise PersonaConversationStoreError(
                "persona conversation read failed"
            ) from exc
        if row is None:
            raise PersonaConversationNotFound("resource not found")
        return _decode_row(row, conversation_id=conversation_id)

    def append_turn(
        self,
        conversation_id: str,
        *,
        owner_user_id: str,
        expected_revision: int,
        turn: PersonaConversationTurnInputV1,
        occurred_at: datetime | None = None,
    ) -> PersonaConversationAppendResult:
        if isinstance(expected_revision, bool) or expected_revision < 1:
            raise ValueError("expected_revision must be a positive integer")
        checked_turn = PersonaConversationTurnInputV1.model_validate(
            turn.model_dump(mode="json")
        )
        _validate_turn_size(checked_turn)

        current = self.load_conversation(
            conversation_id,
            owner_user_id=owner_user_id,
        )
        existing = _find_turn(
            current.conversation,
            checked_turn.client_message_id,
        )
        if existing is not None:
            _require_same_message(existing, checked_turn)
            return PersonaConversationAppendResult(
                conversation=current.conversation,
                turn=existing,
                reused=True,
            )

        conversation = current.conversation
        if conversation.revision != expected_revision:
            raise PersonaConversationWriteConflict(
                "persona conversation revision changed"
            )
        if len(conversation.turns) >= MAX_CONVERSATION_TURNS:
            raise PersonaConversationLimitReached(
                f"persona conversation is limited to {MAX_CONVERSATION_TURNS} turns"
            )

        timestamp = occurred_at or datetime.now(timezone.utc)
        stored_turn = _build_stored_turn(
            checked_turn,
            turn_no=len(conversation.turns) + 1,
            based_on_revision=expected_revision,
            occurred_at=timestamp,
        )
        next_conversation = _append_conversation_turn(
            conversation,
            stored_turn,
        )
        raw_data = encode_persona_conversation(next_conversation)

        try:
            with self.engine.begin() as connection:
                result = connection.execute(
                    update(persona_conversations_table)
                    .where(
                        persona_conversations_table.c.conversation_id
                        == conversation.conversation_id,
                        persona_conversations_table.c.owner_user_id == owner_user_id,
                        persona_conversations_table.c.revision == expected_revision,
                        persona_conversations_table.c.data == current.raw_data,
                    )
                    .values(
                        revision=next_conversation.revision,
                        data=raw_data,
                        updated_at=next_conversation.updated_at,
                    )
                )
        except SQLAlchemyError as exc:
            raise PersonaConversationStoreError(
                "persona conversation update failed"
            ) from exc

        if result.rowcount == 1:
            return PersonaConversationAppendResult(
                conversation=next_conversation,
                turn=stored_turn,
                reused=False,
            )

        latest = self.load_conversation(
            conversation_id,
            owner_user_id=owner_user_id,
        )
        concurrent = _find_turn(
            latest.conversation,
            checked_turn.client_message_id,
        )
        if concurrent is not None:
            _require_same_message(concurrent, checked_turn)
            return PersonaConversationAppendResult(
                conversation=latest.conversation,
                turn=concurrent,
                reused=True,
            )
        raise PersonaConversationWriteConflict(
            "persona conversation revision changed concurrently"
        )

    def recent_turns(
        self,
        conversation_id: str,
        *,
        owner_user_id: str,
    ) -> tuple[PersonaConversationTurnV1, ...]:
        conversation = self.load_conversation(
            conversation_id,
            owner_user_id=owner_user_id,
        ).conversation
        return conversation.turns[-RECENT_CONTEXT_TURNS:]

    def load_recent_context(
        self,
        conversation_id: str,
        *,
        owner_user_id: str,
        current_allowed_passage_ids: Iterable[str] = (),
    ) -> PersonaConversationContextV1:
        """Return six recent turns without promoting old passage IDs to evidence."""

        conversation = self.load_conversation(
            conversation_id,
            owner_user_id=owner_user_id,
        ).conversation
        return PersonaConversationContextV1(
            conversation_id=conversation.conversation_id,
            identity=conversation.identity(),
            revision=conversation.revision,
            recent_turns=conversation.turns[-RECENT_CONTEXT_TURNS:],
            current_allowed_passage_ids=tuple(current_allowed_passage_ids),
        )


def encode_persona_conversation(
    conversation: PersonaConversationV1,
) -> str:
    checked = _validate_conversation(conversation)
    raw_data = _canonical_json(checked.model_dump(mode="json"))
    _validate_record_size(raw_data)
    return raw_data


def decode_persona_conversation(
    raw_data: object,
    *,
    conversation_id: str | None = None,
) -> PersonaConversationV1:
    if not isinstance(raw_data, str):
        raise PersonaConversationIntegrityError(
            "persona conversation record is not text"
        )
    _validate_record_size(raw_data)
    try:
        payload = json.loads(
            raw_data,
            object_pairs_hook=_reject_duplicate_json_keys,
        )
        if not isinstance(payload, dict):
            raise TypeError("persona conversation record must be an object")
        conversation = PersonaConversationV1.model_validate(payload)
    except (
        UnicodeError,
        json.JSONDecodeError,
        ValidationError,
        TypeError,
        ValueError,
    ) as exc:
        raise PersonaConversationIntegrityError(
            "persona conversation failed integrity validation"
        ) from exc
    if conversation_id is not None and conversation.conversation_id != conversation_id:
        raise PersonaConversationIntegrityError(
            "persona conversation identity mismatch"
        )
    return conversation


def _validate_conversation(
    conversation: PersonaConversationV1,
) -> PersonaConversationV1:
    try:
        return PersonaConversationV1.model_validate(
            conversation.model_dump(mode="json")
        )
    except (UnicodeError, ValidationError, TypeError, ValueError) as exc:
        raise PersonaConversationIntegrityError(
            "persona conversation failed integrity validation"
        ) from exc


def _build_stored_turn(
    turn: PersonaConversationTurnInputV1,
    *,
    turn_no: int,
    based_on_revision: int,
    occurred_at: datetime,
) -> PersonaConversationTurnV1:
    payload = turn.model_dump(mode="json")
    payload.update(
        turn_no=turn_no,
        based_on_revision=based_on_revision,
        occurred_at=occurred_at,
        source_payload_checksum=conversation_turn_input_checksum(turn),
    )
    return PersonaConversationTurnV1.model_validate(payload)


def _append_conversation_turn(
    conversation: PersonaConversationV1,
    turn: PersonaConversationTurnV1,
) -> PersonaConversationV1:
    candidate = conversation.model_copy(
        update={
            "revision": conversation.revision + 1,
            "turns": (*conversation.turns, turn),
            "updated_at": turn.occurred_at,
        }
    )
    signed = candidate.model_copy(
        update={
            "checksum": calculate_persona_conversation_checksum(candidate),
        }
    )
    try:
        return PersonaConversationV1.model_validate(signed.model_dump(mode="json"))
    except (UnicodeError, ValidationError, TypeError, ValueError) as exc:
        raise PersonaConversationIntegrityError(
            "next persona conversation failed integrity validation"
        ) from exc


def _find_turn(
    conversation: PersonaConversationV1,
    client_message_id: str,
) -> PersonaConversationTurnV1 | None:
    return next(
        (
            item
            for item in conversation.turns
            if item.client_message_id == client_message_id
        ),
        None,
    )


def _require_same_message(
    existing: PersonaConversationTurnV1,
    turn: PersonaConversationTurnInputV1,
) -> None:
    if existing.source_payload_checksum != conversation_turn_input_checksum(turn):
        raise PersonaMessageIdConflict(
            "client_message_id was already used for different content"
        )


def _decode_row(row, *, conversation_id: str) -> StoredPersonaConversationRecord:
    raw_data = row["data"]
    conversation = decode_persona_conversation(
        raw_data,
        conversation_id=conversation_id,
    )
    expected_columns = _identity_column_values(conversation)
    if any(row[column] != value for column, value in expected_columns.items()):
        raise PersonaConversationIntegrityError(
            "persona conversation storage identity mismatch"
        )
    if row["revision"] != conversation.revision:
        raise PersonaConversationIntegrityError(
            "persona conversation storage revision mismatch"
        )
    return StoredPersonaConversationRecord(
        conversation=conversation,
        raw_data=raw_data,
    )


def _identity_column_values(
    conversation: PersonaConversationV1,
) -> dict[str, object]:
    return {
        "conversation_id": conversation.conversation_id,
        "owner_user_id": conversation.owner_user_id,
        "course_id": conversation.course_id,
        "lesson_id": conversation.lesson_id,
        "release_id": conversation.release_id,
        "release_no": conversation.release_no,
        "release_checksum": conversation.release_checksum,
        "persona_pack_id": conversation.persona_pack_id,
        "persona_pack_version": conversation.persona_pack_version,
        "persona_pack_checksum": conversation.persona_pack_checksum,
        "evidence_corpus_id": conversation.evidence_corpus_id,
        "evidence_version": conversation.evidence_version,
        "evidence_checksum": conversation.evidence_checksum,
        "person_id": conversation.person_id,
        "channel": conversation.channel,
    }


def _row_values(
    conversation: PersonaConversationV1,
    raw_data: str,
) -> dict[str, object]:
    return {
        **_identity_column_values(conversation),
        "revision": conversation.revision,
        "data": raw_data,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }


def _validate_turn_size(turn: PersonaConversationTurnInputV1) -> None:
    raw_data = _canonical_json(turn.model_dump(mode="json"))
    try:
        size = len(raw_data.encode("utf-8"))
    except UnicodeError as exc:
        raise PersonaConversationIntegrityError(
            "persona conversation turn is not valid UTF-8"
        ) from exc
    if size > MAX_CONVERSATION_TURN_BYTES:
        raise PersonaConversationIntegrityError(
            f"persona conversation turn exceeds {MAX_CONVERSATION_TURN_BYTES} bytes"
        )


def _validate_record_size(raw_data: str) -> None:
    try:
        size = len(raw_data.encode("utf-8"))
    except UnicodeError as exc:
        raise PersonaConversationIntegrityError(
            "persona conversation record is not valid UTF-8"
        ) from exc
    if size > MAX_CONVERSATION_RECORD_BYTES:
        raise PersonaConversationIntegrityError(
            f"persona conversation record exceeds {MAX_CONVERSATION_RECORD_BYTES} bytes"
        )


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"duplicate JSON key: {key}")
        payload[key] = value
    return payload


def _canonical_json(payload: object) -> str:
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, UnicodeError, ValueError) as exc:
        raise PersonaConversationIntegrityError(
            "persona conversation is not canonical JSON"
        ) from exc


__all__ = [
    "MAX_CONVERSATION_RECORD_BYTES",
    "MAX_CONVERSATION_TURN_BYTES",
    "PersonaConversationAlreadyExists",
    "PersonaConversationAppendResult",
    "PersonaConversationConflict",
    "PersonaConversationIntegrityError",
    "PersonaConversationLimitReached",
    "PersonaConversationNotFound",
    "PersonaConversationStore",
    "PersonaConversationStoreError",
    "PersonaConversationWriteConflict",
    "PersonaMessageIdConflict",
    "StoredPersonaConversationRecord",
    "decode_persona_conversation",
    "encode_persona_conversation",
    "persona_conversations_table",
]
