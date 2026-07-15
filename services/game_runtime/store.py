from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import Column, DateTime, MetaData, String, Table, Text, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from services.contracts.v1 import (
    Checksum,
    ContractId,
    DossierV1,
    GameSessionV1,
    verify_contract_checksum,
)


MAX_SESSION_RECORD_BYTES = 4 * 1024 * 1024
MAX_DOSSIER_RECORD_BYTES = 2 * 1024 * 1024


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


class StoredDossierNotFound(GameStoreError):
    pass


class StoredDossierIntegrityError(GameStoreError):
    pass


class GameSessionReleaseIdentityV1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        strict=True,
        str_strip_whitespace=True,
    )

    release_id: ContractId
    release_no: int = Field(ge=1)
    release_checksum: Checksum


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
    release_identity: GameSessionReleaseIdentityV1 | None = None
    checksum: Checksum

    @model_validator(mode="after")
    def validate_checksum(self) -> "PersistedGameSessionV1":
        if self.checksum != _session_checksum(
            self.session,
            self.release_identity,
        ):
            raise ValueError("persisted game session checksum is invalid")
        return self


@dataclass(frozen=True)
class StoredSessionRecord:
    envelope: PersistedGameSessionV1
    raw_data: str

    @property
    def session(self) -> GameSessionV1:
        return self.envelope.session


@dataclass(frozen=True)
class StoredDossierRecord:
    dossier: DossierV1
    raw_data: str


_METADATA = MetaData()

game_sessions_table = Table(
    "game_sessions",
    _METADATA,
    Column("session_id", String, primary_key=True),
    Column("data", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

game_dossiers_table = Table(
    "game_dossiers",
    _METADATA,
    Column("dossier_id", String, primary_key=True),
    Column("data", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


class GameRuntimeStore:
    """SQLAlchemy Core JSON mirror with whole-record optimistic CAS."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        _METADATA.create_all(engine)

    def create_session(
        self,
        session: GameSessionV1,
        dossier: DossierV1 | None = None,
        *,
        release_identity: GameSessionReleaseIdentityV1 | None = None,
    ) -> None:
        raw_data = _encode_session(session, release_identity)
        dossier_raw = None
        if dossier is not None:
            _validate_dossier_link(session, dossier)
            dossier_raw = _encode_dossier(dossier)
        elif session.dossier_id is not None:
            raise ValueError("a referenced dossier must be stored atomically")
        try:
            with self.engine.begin() as connection:
                try:
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
                if dossier is not None and dossier_raw is not None:
                    _insert_dossier(connection, dossier, dossier_raw)
        except (StoredSessionAlreadyExists, StoredDossierIntegrityError):
            raise
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

    def load_dossier(self, dossier_id: str) -> StoredDossierRecord:
        try:
            with self.engine.connect() as connection:
                row = connection.execute(
                    select(game_dossiers_table.c.data).where(
                        game_dossiers_table.c.dossier_id == dossier_id
                    )
                ).first()
        except SQLAlchemyError as exc:
            raise GameStoreError("game dossier storage read failed") from exc
        if row is None:
            raise StoredDossierNotFound(f"game dossier not found: {dossier_id}")
        raw_data = row[0]
        if not isinstance(raw_data, str):
            raise StoredDossierIntegrityError(
                f"game dossier record is not text: {dossier_id}"
            )
        return StoredDossierRecord(
            dossier=_decode_dossier(raw_data, dossier_id),
            raw_data=raw_data,
        )

    def compare_and_swap(
        self,
        current: StoredSessionRecord,
        next_session: GameSessionV1,
        dossier: DossierV1 | None = None,
    ) -> None:
        previous = current.session
        if next_session.session_id != previous.session_id:
            raise ValueError("compare-and-swap cannot change session_id")
        if next_session.revision != previous.revision + 1:
            raise ValueError("compare-and-swap requires exactly one new revision")
        raw_data = _encode_session(
            next_session,
            current.envelope.release_identity,
        )
        dossier_raw = None
        if dossier is not None:
            _validate_dossier_link(next_session, dossier)
            dossier_raw = _encode_dossier(dossier)
        elif next_session.dossier_id is not None:
            raise ValueError("a newly referenced dossier must be stored atomically")
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
                if result.rowcount != 1:
                    raise StoredSessionWriteConflict(
                        f"game session revision changed concurrently: {previous.session_id}"
                    )
                if dossier is not None and dossier_raw is not None:
                    _insert_dossier(connection, dossier, dossier_raw)
        except (StoredSessionWriteConflict, StoredDossierIntegrityError):
            raise
        except SQLAlchemyError as exc:
            raise GameStoreError("game session storage update failed") from exc

    def attach_dossier(
        self,
        current: StoredSessionRecord,
        next_session: GameSessionV1,
        dossier: DossierV1,
    ) -> None:
        previous = current.session
        if next_session.session_id != previous.session_id:
            raise ValueError("dossier attachment cannot change session_id")
        if next_session.revision != previous.revision:
            raise ValueError("dossier attachment cannot change revision")
        expected = previous.model_dump(mode="json")
        expected["dossier_id"] = dossier.dossier_id
        if next_session.model_dump(mode="json") != expected:
            raise ValueError("dossier attachment can only set dossier_id")
        _validate_dossier_link(next_session, dossier)
        raw_data = _encode_session(
            next_session,
            current.envelope.release_identity,
        )
        dossier_raw = _encode_dossier(dossier)
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
                if result.rowcount != 1:
                    raise StoredSessionWriteConflict(
                        f"game session changed while attaching dossier: {previous.session_id}"
                    )
                _insert_dossier(connection, dossier, dossier_raw)
        except (StoredSessionWriteConflict, StoredDossierIntegrityError):
            raise
        except SQLAlchemyError as exc:
            raise GameStoreError("game dossier attachment failed") from exc


def _session_checksum(
    session: GameSessionV1,
    release_identity: GameSessionReleaseIdentityV1 | None = None,
) -> str:
    payload: object = session.model_dump(mode="json")
    if release_identity is not None:
        payload = {
            "session": payload,
            "release_identity": release_identity.model_dump(mode="json"),
        }
    raw = _canonical_json(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _encode_session(
    session: GameSessionV1,
    release_identity: GameSessionReleaseIdentityV1 | None = None,
) -> str:
    checked_release_identity = (
        GameSessionReleaseIdentityV1.model_validate(
            release_identity.model_dump(mode="python")
        )
        if release_identity is not None
        else None
    )
    envelope = PersistedGameSessionV1(
        session=GameSessionV1.model_validate(session.model_dump(mode="json")),
        release_identity=checked_release_identity,
        checksum=_session_checksum(session, checked_release_identity),
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


def _encode_dossier(dossier: DossierV1) -> str:
    checked = DossierV1.model_validate(dossier.model_dump(mode="json"))
    if checked.status != "final" or not verify_contract_checksum(checked):
        raise StoredDossierIntegrityError(
            "only final dossiers with a valid checksum can be persisted"
        )
    raw = _canonical_json(checked.model_dump(mode="json"))
    _validate_record_size(
        raw,
        limit=MAX_DOSSIER_RECORD_BYTES,
        label="game dossier record",
        error_type=StoredDossierIntegrityError,
    )
    return raw


def _decode_dossier(raw_data: str, dossier_id: str) -> DossierV1:
    _validate_record_size(
        raw_data,
        limit=MAX_DOSSIER_RECORD_BYTES,
        label=f"game dossier record {dossier_id}",
        error_type=StoredDossierIntegrityError,
    )
    try:
        payload = json.loads(raw_data, object_pairs_hook=_reject_duplicate_json_keys)
        dossier = DossierV1.model_validate(payload)
    except (UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise StoredDossierIntegrityError(
            f"invalid persisted game dossier {dossier_id}: {exc}"
        ) from exc
    if dossier.dossier_id != dossier_id:
        raise StoredDossierIntegrityError(
            f"persisted game dossier identity mismatch: {dossier_id}"
        )
    if dossier.status != "final" or not verify_contract_checksum(dossier):
        raise StoredDossierIntegrityError(
            f"persisted game dossier checksum is invalid: {dossier_id}"
        )
    return dossier


def _insert_dossier(connection, dossier: DossierV1, raw_data: str) -> None:
    try:
        connection.execute(
            insert(game_dossiers_table).values(
                dossier_id=dossier.dossier_id,
                data=raw_data,
                updated_at=dossier.generated_at,
            )
        )
    except IntegrityError as exc:
        raise StoredDossierIntegrityError(
            f"game dossier insert violated storage integrity: {dossier.dossier_id}"
        ) from exc


def _validate_dossier_link(session: GameSessionV1, dossier: DossierV1) -> None:
    if session.status != "completed":
        raise ValueError("only completed sessions can reference a dossier")
    if session.dossier_id != dossier.dossier_id:
        raise ValueError("session dossier_id must match the stored dossier")
    if (session.session_id, session.user_id) != (
        dossier.session_id,
        dossier.user_id,
    ):
        raise ValueError("dossier session identity does not match")
    if (
        session.course_id,
        session.lesson_id,
        session.scenario_id,
        session.course_content_version,
        session.scenario_version,
        session.course_checksum,
        session.scenario_checksum,
        session.ending_id,
    ) != (
        dossier.course_id,
        dossier.lesson_id,
        dossier.scenario_id,
        dossier.course_content_version,
        dossier.scenario_version,
        dossier.course_checksum,
        dossier.scenario_checksum,
        dossier.ending_id,
    ):
        raise ValueError("dossier artifact identity does not match the session")


def _validate_record_size(
    raw_data: str,
    *,
    limit: int,
    label: str,
    error_type,
) -> None:
    try:
        encoded_size = len(raw_data.encode("utf-8"))
    except UnicodeError as exc:
        raise error_type(f"{label} is not valid UTF-8") from exc
    if encoded_size > limit:
        raise error_type(f"{label} exceeds {limit} bytes")


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
    "GameSessionReleaseIdentityV1",
    "GameRuntimeStore",
    "GameStoreError",
    "MAX_DOSSIER_RECORD_BYTES",
    "PersistedGameSessionV1",
    "StoredDossierIntegrityError",
    "StoredDossierNotFound",
    "StoredDossierRecord",
    "StoredSessionAlreadyExists",
    "StoredSessionIntegrityError",
    "StoredSessionNotFound",
    "StoredSessionRecord",
    "StoredSessionWriteConflict",
    "game_dossiers_table",
    "game_sessions_table",
]
