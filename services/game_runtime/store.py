from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator
from sqlalchemy import Column, DateTime, MetaData, String, Table, Text, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from services.contracts.v1 import Checksum, GameSessionV1


MAX_SESSION_RECORD_BYTES = 4 * 1024 * 1024


class GameStoreError(RuntimeError):
    code = "game_storage_unavailable"


class StoredSessionNotFound(GameStoreError):
    pass


class StoredSessionAlreadyExists(GameStoreError):
    pass


class StoredSessionWriteConflict(GameStoreError):
    pass


class StoredSessionIntegrityError(GameStoreError):
    pass


class PersistedGameSessionV1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    schema_version: Literal["persisted-game-session/v1"] = (
        "persisted-game-session/v1"
    )
    session: GameSessionV1
    checksum: Checksum

    @model_validator(mode="after")
    def validate_checksum(self) -> "PersistedGameSessionV1":
        if self.checksum != _session_checksum(self.session):
            raise ValueError("persisted game session checksum is invalid")
        return self


@dataclass(frozen=True)
class StoredSessionRecord:
    envelope: PersistedGameSessionV1
    raw_data: str

    @property
    def session(self) -> GameSessionV1:
        return self.envelope.session


_METADATA = MetaData()

game_sessions_table = Table(
    "game_sessions",
    _METADATA,
    Column("session_id", String, primary_key=True),
    Column("data", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


class GameRuntimeStore:
    """SQLAlchemy Core JSON mirror with whole-record optimistic CAS."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        _METADATA.create_all(engine)

    def create_session(self, session: GameSessionV1) -> None:
        raw_data = _encode_session(session)
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    insert(game_sessions_table).values(
                        session_id=session.session_id,
                        data=raw_data,
                        updated_at=session.updated_at,
                    )
                )
        except IntegrityError as exc:
            raise StoredSessionAlreadyExists(
                f"game session already exists: {session.session_id}"
            ) from exc
        except SQLAlchemyError as exc:
            raise GameStoreError("game session storage write failed") from exc

    def load_session(self, session_id: str) -> StoredSessionRecord:
        try:
            with self.engine.connect() as connection:
                row = connection.execute(
                    select(game_sessions_table.c.data).where(
                        game_sessions_table.c.session_id == session_id
                    )
                ).first()
        except SQLAlchemyError as exc:
            raise GameStoreError("game session storage read failed") from exc
        if row is None:
            raise StoredSessionNotFound(f"game session not found: {session_id}")
        raw_data = row[0]
        if not isinstance(raw_data, str):
            raise StoredSessionIntegrityError(
                f"game session record is not text: {session_id}"
            )
        return StoredSessionRecord(
            envelope=_decode_session(raw_data, session_id),
            raw_data=raw_data,
        )

    def compare_and_swap(
        self,
        current: StoredSessionRecord,
        next_session: GameSessionV1,
    ) -> None:
        previous = current.session
        if next_session.session_id != previous.session_id:
            raise ValueError("compare-and-swap cannot change session_id")
        if next_session.revision != previous.revision + 1:
            raise ValueError("compare-and-swap requires exactly one new revision")
        raw_data = _encode_session(next_session)
        try:
            with self.engine.begin() as connection:
                result = connection.execute(
                    update(game_sessions_table)
                    .where(
                        game_sessions_table.c.session_id == previous.session_id,
                        game_sessions_table.c.data == current.raw_data,
                    )
                    .values(data=raw_data, updated_at=next_session.updated_at)
                )
        except SQLAlchemyError as exc:
            raise GameStoreError("game session storage update failed") from exc
        if result.rowcount != 1:
            raise StoredSessionWriteConflict(
                f"game session revision changed concurrently: {previous.session_id}"
            )


def _session_checksum(session: GameSessionV1) -> str:
    raw = _canonical_json(session.model_dump(mode="json"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _encode_session(session: GameSessionV1) -> str:
    envelope = PersistedGameSessionV1(
        session=GameSessionV1.model_validate(session.model_dump(mode="json")),
        checksum=_session_checksum(session),
    )
    raw = _canonical_json(envelope.model_dump(mode="json"))
    try:
        encoded_size = len(raw.encode("utf-8"))
    except UnicodeError as exc:
        raise StoredSessionIntegrityError(
            "game session record is not valid UTF-8"
        ) from exc
    if encoded_size > MAX_SESSION_RECORD_BYTES:
        raise StoredSessionIntegrityError(
            f"game session record exceeds {MAX_SESSION_RECORD_BYTES} bytes"
        )
    return raw


def _decode_session(raw_data: str, session_id: str) -> PersistedGameSessionV1:
    try:
        encoded_size = len(raw_data.encode("utf-8"))
    except UnicodeError as exc:
        raise StoredSessionIntegrityError(
            f"game session record is not valid UTF-8: {session_id}"
        ) from exc
    if encoded_size > MAX_SESSION_RECORD_BYTES:
        raise StoredSessionIntegrityError(
            f"game session record exceeds {MAX_SESSION_RECORD_BYTES} bytes: {session_id}"
        )
    try:
        payload = json.loads(raw_data, object_pairs_hook=_reject_duplicate_json_keys)
        envelope = PersistedGameSessionV1.model_validate(payload)
    except (UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise StoredSessionIntegrityError(
            f"invalid persisted game session {session_id}: {exc}"
        ) from exc
    if envelope.session.session_id != session_id:
        raise StoredSessionIntegrityError(
            f"persisted game session identity mismatch: {session_id}"
        )
    return envelope


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


__all__ = [
    "GameRuntimeStore",
    "GameStoreError",
    "PersistedGameSessionV1",
    "StoredSessionAlreadyExists",
    "StoredSessionIntegrityError",
    "StoredSessionNotFound",
    "StoredSessionRecord",
    "StoredSessionWriteConflict",
    "game_sessions_table",
]
