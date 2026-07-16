from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import delete, insert, inspect, select, update
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from services.auth.models import Principal
from services.auth.store import (
    AuditWrite,
    AuthStore,
    AuthStoreError,
    sessions_table,
    users_table,
)
from services.contracts.v1 import (
    Checksum,
    ContractId,
    DossierV1,
    GameSessionV1,
    calculate_contract_checksum,
)
from services.game_runtime.store import (
    GameSessionReleaseIdentityV1,
    GameStoreError,
    StoredDossierIntegrityError,
    StoredSessionIntegrityError,
    decode_stored_dossier,
    decode_stored_session,
    encode_stored_dossier,
    encode_stored_session,
    game_dossiers_table,
    game_sessions_table,
    validate_stored_dossier_link,
)
from services.persistence.db import kv_table


_PROGRESS_NAMESPACE = "lesson_progress"
_CANVAS_NAMESPACE = "canvas"
_RECEIPT_NAMESPACE = "student_asset_migrations"
_LEGACY_PROGRESS_OWNER = "default"
_KNOWN_ROLES = frozenset({"student", "teacher", "reviewer", "admin"})
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")


class StudentAssetMigrationError(RuntimeError):
    code = "student_asset_migration_failed"


class StudentAssetMigrationIntegrityError(StudentAssetMigrationError):
    code = "student_asset_migration_integrity_error"


class StudentAssetMigrationConflict(StudentAssetMigrationError):
    code = "student_asset_migration_conflict"


class StudentAssetMigrationAuthorizationError(StudentAssetMigrationError):
    code = "student_asset_migration_authorization_error"


class UnmappedStudentAssetsError(StudentAssetMigrationError):
    code = "unmapped_student_assets"

    def __init__(self, report: "UnmappedStudentAssets") -> None:
        self.report = report
        counts = report.counts
        super().__init__(
            "accounts mode found unmapped student assets "
            f"(progress={counts.progress}, canvases={counts.canvases}, "
            f"sessions={counts.sessions}, dossiers={counts.dossiers}); "
            "run scripts/migrate_student_assets.py before starting the API"
        )


class StudentAssetCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    progress: int = Field(ge=0)
    canvases: int = Field(ge=0)
    sessions: int = Field(ge=0)
    dossiers: int = Field(ge=0)
    total: int = Field(ge=0)


class UnmappedStudentAssets(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    counts: StudentAssetCounts
    owner_ids: tuple[str, ...] = ()


class StudentAssetMigrationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["student-asset-migration-report/v1"] = (
        "student-asset-migration-report/v1"
    )
    status: Literal["planned", "applied", "already_applied", "empty"]
    migration_id: str = Field(pattern=r"^sam_[a-f0-9]{24}$")
    source_progress_user_id: Literal["default"] = "default"
    source_game_user_id: ContractId
    actor_user_id: str = Field(pattern=r"^usr_[a-f0-9]{32}$")
    actor_username: str
    actor_session_id: str = Field(pattern=r"^ses_[a-f0-9]{32}$")
    request_id: str = Field(min_length=1, max_length=100)
    target_user_id: str = Field(pattern=r"^usr_[a-f0-9]{32}$")
    target_username: str
    target_has_student_role: bool
    counts: StudentAssetCounts
    source_fingerprint: Checksum
    receipt_checksum: Checksum | None = None
    applied_at: str | None = None


class _ProgressLayers(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    watch: bool = False
    practice: bool = False
    ask: bool = False
    create: bool = False


class _ProgressRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: ContractId
    lesson_id: ContractId
    last_layer: Literal["watch", "practice", "ask", "create"] = "watch"
    layers: _ProgressLayers = Field(default_factory=_ProgressLayers)
    updated_at: str


class _CanvasGraph(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class _CanvasEnvelope(_CanvasGraph):
    schema_version: Literal["canvas/v1"]
    revision: int = Field(ge=1)


class _MigrationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["student-asset-migration/v1"] = (
        "student-asset-migration/v1"
    )
    migration_id: str = Field(pattern=r"^sam_[a-f0-9]{24}$")
    source_progress_user_id: Literal["default"] = "default"
    source_game_user_id: ContractId
    actor_user_id: str = Field(pattern=r"^usr_[a-f0-9]{32}$")
    actor_username: str
    actor_session_id: str = Field(pattern=r"^ses_[a-f0-9]{32}$")
    request_id: str = Field(min_length=1, max_length=100)
    target_user_id: str = Field(pattern=r"^usr_[a-f0-9]{32}$")
    target_username: str
    counts: StudentAssetCounts
    source_fingerprint: Checksum
    applied_at: str
    checksum: Checksum


class _StoredAccount(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str = Field(pattern=r"^usr_[a-f0-9]{32}$")
    username: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9._-]+$",
    )
    roles: tuple[Literal["student", "teacher", "reviewer", "admin"], ...] = Field(
        min_length=1
    )
    enabled: bool
    auth_version: int = Field(ge=1)


class _StoredActorSession(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str = Field(pattern=r"^ses_[a-f0-9]{32}$")
    user_id: str = Field(pattern=r"^usr_[a-f0-9]{32}$")
    auth_version: int = Field(ge=1)
    expires_at: datetime
    revoked_at: datetime | None = None


@dataclass(frozen=True)
class _Account:
    user_id: str
    username: str
    roles: frozenset[str]
    enabled: bool
    auth_version: int


@dataclass(frozen=True)
class _KvRow:
    namespace: str
    key: str
    raw_data: str
    updated_at: datetime


@dataclass(frozen=True)
class _ProgressSource:
    row: _KvRow
    owner_id: str
    lesson_id: str
    record: _ProgressRecord


@dataclass(frozen=True)
class _CanvasSource:
    row: _KvRow
    owner_id: str | None
    lesson_id: str


@dataclass(frozen=True)
class _SessionSource:
    session_id: str
    raw_data: str
    updated_at: datetime
    session: GameSessionV1
    release_identity: GameSessionReleaseIdentityV1 | None


@dataclass(frozen=True)
class _DossierSource:
    dossier_id: str
    raw_data: str
    updated_at: datetime
    dossier: DossierV1


@dataclass(frozen=True)
class _AssetScan:
    progress: tuple[_ProgressSource, ...]
    canvases: tuple[_CanvasSource, ...]
    sessions: tuple[_SessionSource, ...]
    dossiers: tuple[_DossierSource, ...]


@dataclass(frozen=True)
class _KvMove:
    source: _KvRow
    target_key: str
    target_raw_data: str


@dataclass(frozen=True)
class _GameUpdate:
    record_id: str
    source_raw_data: str
    target_raw_data: str


@dataclass(frozen=True)
class _MigrationPlan:
    migration_id: str
    actor: _Account
    target: _Account
    source_game_user_id: str
    actor_session_id: str
    request_id: str
    counts: StudentAssetCounts
    source_fingerprint: str
    progress_moves: tuple[_KvMove, ...]
    canvas_moves: tuple[_KvMove, ...]
    session_updates: tuple[_GameUpdate, ...]
    dossier_updates: tuple[_GameUpdate, ...]


def find_unmapped_student_assets(engine: Engine) -> UnmappedStudentAssets:
    tables = _table_names(engine)
    _require_tables(tables, {users_table.name, kv_table.name})
    with engine.connect() as connection:
        accounts = _accounts(connection)
        scan = _scan_assets(connection, tables, _student_owner_ids(accounts))
    owners = {
        item.owner_id for item in scan.progress
    } | {
        item.owner_id for item in scan.canvases if item.owner_id is not None
    } | {
        item.session.user_id for item in scan.sessions
    } | {
        item.dossier.user_id for item in scan.dossiers
    }
    return UnmappedStudentAssets(
        counts=_counts(scan),
        owner_ids=tuple(sorted(owners)),
    )


def assert_no_unmapped_student_assets(engine: Engine) -> None:
    report = find_unmapped_student_assets(engine)
    if report.counts.total:
        raise UnmappedStudentAssetsError(report)


def migrate_legacy_student_assets(
    engine: Engine,
    *,
    actor: Principal,
    request_id: str,
    target_username: str,
    source_game_user_id: str,
    apply: bool = False,
    now: datetime | None = None,
) -> StudentAssetMigrationReport:
    tables = _table_names(engine)
    _require_tables(
        tables,
        {users_table.name, sessions_table.name, kv_table.name},
    )
    timestamp = _utc(now)
    auth_now = _utc(None)
    auth_store = AuthStore(engine) if apply else None
    context = engine.begin() if apply else engine.connect()
    try:
        with context as connection:
            plan, receipt = _plan_migration(
                connection,
                tables,
                actor=actor,
                request_id=request_id,
                target_username=target_username,
                source_game_user_id=source_game_user_id,
                auth_now=auth_now,
            )
            if receipt is not None:
                return _report_from_receipt(receipt, plan.target)
            if plan.counts.total == 0:
                return _report(plan, status="empty")
            if not apply:
                return _report(plan, status="planned")
            if auth_store is None:
                raise StudentAssetMigrationIntegrityError(
                    "migration audit store was not initialized"
                )
            receipt = _apply_plan(
                connection,
                tables,
                plan,
                timestamp,
                auth_store,
            )
            remaining = _scan_assets(
                connection,
                tables,
                _student_owner_ids(_accounts(connection)),
            )
            if _counts(remaining).total:
                raise StudentAssetMigrationIntegrityError(
                    "unmapped student assets remained after migration"
                )
            return _report_from_receipt(receipt, plan.target, status="applied")
    except StudentAssetMigrationError:
        raise
    except IntegrityError as exc:
        raise StudentAssetMigrationConflict(
            "migration lost a concurrent target or receipt race"
        ) from exc
    except AuthStoreError as exc:
        raise StudentAssetMigrationError(
            "student asset migration audit failed"
        ) from exc
    except SQLAlchemyError as exc:
        raise StudentAssetMigrationError(
            "student asset storage operation failed"
        ) from exc


def _plan_migration(
    connection: Connection,
    tables: frozenset[str],
    *,
    actor: Principal,
    request_id: str,
    target_username: str,
    source_game_user_id: str,
    auth_now: datetime,
) -> tuple[_MigrationPlan, _MigrationReceipt | None]:
    accounts = _accounts(connection)
    checked_actor, actor_session_id = _authenticated_actor(
        connection,
        accounts,
        actor,
        auth_now=auth_now,
    )
    target = _account_by_username(accounts, target_username)
    if not target.enabled or "student" not in target.roles:
        raise StudentAssetMigrationAuthorizationError(
            "migration target must be an enabled student"
        )
    checked_request_id = _validate_request_id(request_id)
    source_game_user_id = _validate_contract_id(
        source_game_user_id,
        label="source game user id",
    )
    migration_id = _migration_id(source_game_user_id)
    scan = _scan_assets(connection, tables, _student_owner_ids(accounts))
    _require_expected_legacy_sources(scan, source_game_user_id)
    counts = _counts(scan)
    source_fingerprint = _source_fingerprint(scan)
    receipt = _load_receipt(connection, source_game_user_id)
    empty_plan = _MigrationPlan(
        migration_id=migration_id,
        actor=checked_actor,
        target=target,
        source_game_user_id=source_game_user_id,
        actor_session_id=actor_session_id,
        request_id=checked_request_id,
        counts=counts,
        source_fingerprint=source_fingerprint,
        progress_moves=(),
        canvas_moves=(),
        session_updates=(),
        dossier_updates=(),
    )
    if receipt is not None:
        if (
            receipt.migration_id != migration_id
            or receipt.source_game_user_id != source_game_user_id
            or receipt.target_user_id != target.user_id
        ):
            raise StudentAssetMigrationConflict(
                "legacy assets were already mapped to a different target"
            )
        if counts.total:
            raise StudentAssetMigrationIntegrityError(
                "legacy assets reappeared after a completed migration"
            )
        return empty_plan, receipt
    if counts.total == 0:
        return empty_plan, None

    progress_moves = tuple(
        _progress_move(connection, item, target.user_id)
        for item in scan.progress
    )
    canvas_moves = tuple(
        _canvas_move(connection, item, target.user_id)
        for item in scan.canvases
    )
    session_updates, dossier_updates = _game_updates(
        scan.sessions,
        scan.dossiers,
        target.user_id,
    )
    return (
        _MigrationPlan(
            migration_id=migration_id,
            actor=checked_actor,
            target=target,
            source_game_user_id=source_game_user_id,
            actor_session_id=actor_session_id,
            request_id=checked_request_id,
            counts=counts,
            source_fingerprint=source_fingerprint,
            progress_moves=progress_moves,
            canvas_moves=canvas_moves,
            session_updates=session_updates,
            dossier_updates=dossier_updates,
        ),
        None,
    )


def _scan_assets(
    connection: Connection,
    tables: frozenset[str],
    known_user_ids: frozenset[str],
) -> _AssetScan:
    progress: list[_ProgressSource] = []
    canvases: list[_CanvasSource] = []
    if kv_table.name in tables:
        rows = connection.execute(
            select(
                kv_table.c.namespace,
                kv_table.c.key,
                kv_table.c.data,
                kv_table.c.updated_at,
            ).where(
                kv_table.c.namespace.in_([
                    _PROGRESS_NAMESPACE,
                    _CANVAS_NAMESPACE,
                ])
            )
        ).mappings().fetchall()
        for raw_row in rows:
            row = _kv_row(raw_row)
            if row.namespace == _PROGRESS_NAMESPACE:
                source = _progress_source(row)
                if source.owner_id not in known_user_ids:
                    progress.append(source)
            else:
                source = _canvas_source(row)
                if source.owner_id is None or source.owner_id not in known_user_ids:
                    canvases.append(source)

    sessions: list[_SessionSource] = []
    dossiers: list[_DossierSource] = []
    has_sessions = game_sessions_table.name in tables
    has_dossiers = game_dossiers_table.name in tables
    if has_sessions != has_dossiers:
        raise StudentAssetMigrationIntegrityError(
            "game session and dossier tables must exist together"
        )
    if has_sessions:
        session_rows = connection.execute(
            select(
                game_sessions_table.c.session_id,
                game_sessions_table.c.data,
                game_sessions_table.c.updated_at,
            )
        ).mappings().fetchall()
        for row in session_rows:
            source = _session_source(row)
            if source.session.user_id not in known_user_ids:
                sessions.append(source)
        dossier_rows = connection.execute(
            select(
                game_dossiers_table.c.dossier_id,
                game_dossiers_table.c.data,
                game_dossiers_table.c.updated_at,
            )
        ).mappings().fetchall()
        for row in dossier_rows:
            source = _dossier_source(row)
            if source.dossier.user_id not in known_user_ids:
                dossiers.append(source)
    return _AssetScan(
        progress=tuple(sorted(progress, key=lambda item: item.row.key)),
        canvases=tuple(sorted(canvases, key=lambda item: item.row.key)),
        sessions=tuple(sorted(sessions, key=lambda item: item.session_id)),
        dossiers=tuple(sorted(dossiers, key=lambda item: item.dossier_id)),
    )


def _require_expected_legacy_sources(
    scan: _AssetScan,
    source_game_user_id: str,
) -> None:
    unexpected_progress = {
        item.owner_id
        for item in scan.progress
        if item.owner_id != _LEGACY_PROGRESS_OWNER
    }
    unexpected_canvases = {
        item.owner_id
        for item in scan.canvases
        if item.owner_id is not None
    }
    unexpected_game = {
        item.session.user_id
        for item in scan.sessions
        if item.session.user_id != source_game_user_id
    } | {
        item.dossier.user_id
        for item in scan.dossiers
        if item.dossier.user_id != source_game_user_id
    }
    unexpected = unexpected_progress | unexpected_canvases | unexpected_game
    if unexpected:
        raise StudentAssetMigrationIntegrityError(
            "unmapped assets include owners outside the explicit legacy source: "
            + ", ".join(sorted(str(item) for item in unexpected))
        )


def _progress_move(
    connection: Connection,
    source: _ProgressSource,
    target_user_id: str,
) -> _KvMove:
    target_key = f"{target_user_id}:{source.lesson_id}"
    _require_absent_kv(connection, _PROGRESS_NAMESPACE, target_key)
    target_record = source.record.model_copy(update={"user_id": target_user_id})
    return _KvMove(
        source=source.row,
        target_key=target_key,
        target_raw_data=_canonical_json(target_record.model_dump(mode="json")),
    )


def _canvas_move(
    connection: Connection,
    source: _CanvasSource,
    target_user_id: str,
) -> _KvMove:
    target_key = f"{target_user_id}:{source.lesson_id}"
    _require_absent_kv(connection, _CANVAS_NAMESPACE, target_key)
    return _KvMove(
        source=source.row,
        target_key=target_key,
        target_raw_data=source.row.raw_data,
    )


def _game_updates(
    sessions: tuple[_SessionSource, ...],
    dossiers: tuple[_DossierSource, ...],
    target_user_id: str,
) -> tuple[tuple[_GameUpdate, ...], tuple[_GameUpdate, ...]]:
    try:
        return _build_game_updates(sessions, dossiers, target_user_id)
    except StudentAssetMigrationError:
        raise
    except (ValidationError, ValueError, GameStoreError) as exc:
        raise StudentAssetMigrationIntegrityError(
            "legacy game assets could not be rewritten safely"
        ) from exc


def _build_game_updates(
    sessions: tuple[_SessionSource, ...],
    dossiers: tuple[_DossierSource, ...],
    target_user_id: str,
) -> tuple[tuple[_GameUpdate, ...], tuple[_GameUpdate, ...]]:
    sessions_by_id = {item.session_id: item for item in sessions}
    dossiers_by_id = {item.dossier_id: item for item in dossiers}
    for dossier in dossiers:
        session = sessions_by_id.get(dossier.dossier.session_id)
        if session is None or session.session.dossier_id != dossier.dossier_id:
            raise StudentAssetMigrationIntegrityError(
                f"orphan legacy dossier: {dossier.dossier_id}"
            )
    session_updates: list[_GameUpdate] = []
    dossier_updates: list[_GameUpdate] = []
    for source in sessions:
        dossier_source = None
        if source.session.dossier_id is not None:
            dossier_source = dossiers_by_id.get(source.session.dossier_id)
            if dossier_source is None:
                raise StudentAssetMigrationIntegrityError(
                    f"legacy session lost its dossier: {source.session_id}"
                )
        session_payload = source.session.model_dump(mode="json")
        session_payload["user_id"] = target_user_id
        next_session = GameSessionV1.model_validate(session_payload)
        next_dossier = None
        if dossier_source is not None:
            next_dossier = _replace_dossier_owner(
                dossier_source.dossier,
                target_user_id,
            )
            validate_stored_dossier_link(next_session, next_dossier)
            dossier_updates.append(
                _GameUpdate(
                    record_id=dossier_source.dossier_id,
                    source_raw_data=dossier_source.raw_data,
                    target_raw_data=encode_stored_dossier(next_dossier),
                )
            )
        session_updates.append(
            _GameUpdate(
                record_id=source.session_id,
                source_raw_data=source.raw_data,
                target_raw_data=encode_stored_session(
                    next_session,
                    source.release_identity,
                ),
            )
        )
    return tuple(session_updates), tuple(dossier_updates)


def _replace_dossier_owner(dossier: DossierV1, target_user_id: str) -> DossierV1:
    payload = dossier.model_dump(mode="json")
    payload["user_id"] = target_user_id
    payload["checksum"] = "0" * 64
    unsigned = DossierV1.model_validate(payload)
    payload["checksum"] = calculate_contract_checksum(unsigned)
    return DossierV1.model_validate(payload)


def _apply_plan(
    connection: Connection,
    tables: frozenset[str],
    plan: _MigrationPlan,
    timestamp: datetime,
    auth_store: AuthStore,
) -> _MigrationReceipt:
    for move in (*plan.progress_moves, *plan.canvas_moves):
        connection.execute(
            insert(kv_table).values(
                namespace=move.source.namespace,
                key=move.target_key,
                data=move.target_raw_data,
                updated_at=move.source.updated_at,
            )
        )
        result = connection.execute(
            delete(kv_table).where(
                (kv_table.c.namespace == move.source.namespace)
                & (kv_table.c.key == move.source.key)
                & (kv_table.c.data == move.source.raw_data)
            )
        )
        _require_one(result.rowcount, "legacy KV source changed concurrently")
    if plan.session_updates and game_sessions_table.name not in tables:
        raise StudentAssetMigrationIntegrityError("game session table disappeared")
    for item in plan.session_updates:
        result = connection.execute(
            update(game_sessions_table)
            .where(
                (game_sessions_table.c.session_id == item.record_id)
                & (game_sessions_table.c.data == item.source_raw_data)
            )
            .values(data=item.target_raw_data)
        )
        _require_one(result.rowcount, "legacy game session changed concurrently")
    for item in plan.dossier_updates:
        result = connection.execute(
            update(game_dossiers_table)
            .where(
                (game_dossiers_table.c.dossier_id == item.record_id)
                & (game_dossiers_table.c.data == item.source_raw_data)
            )
            .values(data=item.target_raw_data)
        )
        _require_one(result.rowcount, "legacy game dossier changed concurrently")
    receipt = _build_receipt(plan, timestamp)
    connection.execute(
        insert(kv_table).values(
            namespace=_RECEIPT_NAMESPACE,
            key=_receipt_key(plan.source_game_user_id),
            data=_canonical_json(receipt.model_dump(mode="json")),
            updated_at=timestamp,
        )
    )
    auth_store.append_audit_in_transaction(
        connection,
        AuditWrite(
            occurred_at=timestamp,
            actor_user_id=plan.actor.user_id,
            actor_session_id=plan.actor_session_id,
            actor_roles=tuple(
                role
                for role in ("student", "teacher", "reviewer", "admin")
                if role in plan.actor.roles
            ),
            action="auth.student_assets.migrate",
            resource_type="student_assets",
            resource_id=plan.migration_id,
            outcome="succeeded",
            request_id=plan.request_id,
            details={
                "source_progress_user_id": _LEGACY_PROGRESS_OWNER,
                "source_game_user_id": plan.source_game_user_id,
                "target_user_id": plan.target.user_id,
                "target_username": plan.target.username,
                "counts": plan.counts.model_dump(mode="json"),
                "source_fingerprint": plan.source_fingerprint,
                "receipt_checksum": receipt.checksum,
            },
        ),
    )
    return receipt


def _build_receipt(
    plan: _MigrationPlan,
    timestamp: datetime,
) -> _MigrationReceipt:
    payload = {
        "schema_version": "student-asset-migration/v1",
        "migration_id": plan.migration_id,
        "source_progress_user_id": _LEGACY_PROGRESS_OWNER,
        "source_game_user_id": plan.source_game_user_id,
        "actor_user_id": plan.actor.user_id,
        "actor_username": plan.actor.username,
        "actor_session_id": plan.actor_session_id,
        "request_id": plan.request_id,
        "target_user_id": plan.target.user_id,
        "target_username": plan.target.username,
        "counts": plan.counts.model_dump(mode="json"),
        "source_fingerprint": plan.source_fingerprint,
        "applied_at": timestamp.isoformat(),
    }
    return _MigrationReceipt(
        **payload,
        checksum=_checksum(payload),
    )


def _load_receipt(
    connection: Connection,
    source_game_user_id: str,
) -> _MigrationReceipt | None:
    row = connection.execute(
        select(kv_table.c.data).where(
            (kv_table.c.namespace == _RECEIPT_NAMESPACE)
            & (kv_table.c.key == _receipt_key(source_game_user_id))
        )
    ).first()
    if row is None:
        return None
    payload = _json_object(row[0], label="student asset migration receipt")
    try:
        receipt = _MigrationReceipt.model_validate(payload)
    except ValidationError as exc:
        raise StudentAssetMigrationIntegrityError(
            "student asset migration receipt is invalid"
        ) from exc
    expected = _checksum(receipt.model_dump(mode="json", exclude={"checksum"}))
    if receipt.checksum != expected:
        raise StudentAssetMigrationIntegrityError(
            "student asset migration receipt checksum is invalid"
        )
    return receipt


def _report(
    plan: _MigrationPlan,
    *,
    status: Literal["planned", "empty"],
) -> StudentAssetMigrationReport:
    return StudentAssetMigrationReport(
        status=status,
        migration_id=plan.migration_id,
        source_game_user_id=plan.source_game_user_id,
        actor_user_id=plan.actor.user_id,
        actor_username=plan.actor.username,
        actor_session_id=plan.actor_session_id,
        request_id=plan.request_id,
        target_user_id=plan.target.user_id,
        target_username=plan.target.username,
        target_has_student_role="student" in plan.target.roles,
        counts=plan.counts,
        source_fingerprint=plan.source_fingerprint,
    )


def _report_from_receipt(
    receipt: _MigrationReceipt,
    target: _Account,
    *,
    status: Literal["applied", "already_applied"] = "already_applied",
) -> StudentAssetMigrationReport:
    return StudentAssetMigrationReport(
        status=status,
        migration_id=receipt.migration_id,
        source_game_user_id=receipt.source_game_user_id,
        actor_user_id=receipt.actor_user_id,
        actor_username=receipt.actor_username,
        actor_session_id=receipt.actor_session_id,
        request_id=receipt.request_id,
        target_user_id=receipt.target_user_id,
        target_username=receipt.target_username,
        target_has_student_role="student" in target.roles,
        counts=receipt.counts,
        source_fingerprint=receipt.source_fingerprint,
        receipt_checksum=receipt.checksum,
        applied_at=receipt.applied_at,
    )


def _accounts(connection: Connection) -> dict[str, _Account]:
    rows = connection.execute(
        select(
            users_table.c.user_id,
            users_table.c.username,
            users_table.c.roles,
            users_table.c.enabled,
            users_table.c.auth_version,
        )
    ).mappings().fetchall()
    result = {}
    for row in rows:
        try:
            raw_roles = json.loads(row["roles"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise StudentAssetMigrationIntegrityError(
                "account roles storage is invalid"
            ) from exc
        if not isinstance(raw_roles, list) or any(
            role not in _KNOWN_ROLES for role in raw_roles
        ):
            raise StudentAssetMigrationIntegrityError(
                "account roles storage is invalid"
            )
        try:
            checked = _StoredAccount(
                user_id=row["user_id"],
                username=row["username"],
                roles=tuple(raw_roles),
                enabled=bool(row["enabled"]),
                auth_version=int(row["auth_version"]),
            )
        except ValidationError as exc:
            raise StudentAssetMigrationIntegrityError(
                "account identity storage is invalid"
            ) from exc
        account = _Account(
            user_id=checked.user_id,
            username=checked.username,
            roles=frozenset(checked.roles),
            enabled=checked.enabled,
            auth_version=checked.auth_version,
        )
        result[account.user_id] = account
    return result


def _student_owner_ids(accounts: dict[str, _Account]) -> frozenset[str]:
    return frozenset(
        account.user_id
        for account in accounts.values()
        if "student" in account.roles
    )


def _authenticated_actor(
    connection: Connection,
    accounts: dict[str, _Account],
    principal: Principal,
    *,
    auth_now: datetime,
) -> tuple[_Account, str]:
    if principal.synthetic or principal.session_id is None:
        raise StudentAssetMigrationAuthorizationError(
            "migration requires an authenticated administrator session"
        )
    account = accounts.get(principal.user_id)
    if (
        account is None
        or not account.enabled
        or "admin" not in account.roles
        or account.username != principal.username
        or account.roles != frozenset(principal.roles)
        or account.auth_version != principal.auth_version
    ):
        raise StudentAssetMigrationAuthorizationError(
            "migration actor is not the current enabled administrator"
        )
    row = connection.execute(
        select(
            sessions_table.c.session_id,
            sessions_table.c.user_id,
            sessions_table.c.auth_version,
            sessions_table.c.expires_at,
            sessions_table.c.revoked_at,
        ).where(sessions_table.c.session_id == principal.session_id)
    ).mappings().first()
    if row is None:
        raise StudentAssetMigrationAuthorizationError(
            "migration administrator session does not exist"
        )
    try:
        session = _StoredActorSession(
            session_id=row["session_id"],
            user_id=row["user_id"],
            auth_version=int(row["auth_version"]),
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
        )
    except (ValidationError, TypeError, ValueError) as exc:
        raise StudentAssetMigrationIntegrityError(
            "migration administrator session storage is invalid"
        ) from exc
    if (
        session.user_id != account.user_id
        or session.auth_version != account.auth_version
        or session.revoked_at is not None
        or _utc(session.expires_at) <= auth_now
    ):
        raise StudentAssetMigrationAuthorizationError(
            "migration administrator session is no longer valid"
        )
    return account, session.session_id


def _account_by_username(
    accounts: dict[str, _Account],
    username: str,
) -> _Account:
    normalized = username.strip().lower()
    matches = [item for item in accounts.values() if item.username == normalized]
    if len(matches) != 1:
        raise StudentAssetMigrationAuthorizationError(
            f"account does not exist: {normalized}"
        )
    return matches[0]


def _progress_source(row: _KvRow) -> _ProgressSource:
    owner_id, separator, lesson_id = row.key.partition(":")
    if not separator:
        raise StudentAssetMigrationIntegrityError(
            f"learning progress key has no owner: {row.key}"
        )
    payload = _json_object(row.raw_data, label=f"learning progress {row.key}")
    try:
        record = _ProgressRecord.model_validate(payload)
    except ValidationError as exc:
        raise StudentAssetMigrationIntegrityError(
            f"learning progress record is invalid: {row.key}"
        ) from exc
    if record.user_id != owner_id or record.lesson_id != lesson_id:
        raise StudentAssetMigrationIntegrityError(
            f"learning progress identity mismatch: {row.key}"
        )
    return _ProgressSource(
        row=row,
        owner_id=owner_id,
        lesson_id=lesson_id,
        record=record,
    )


def _canvas_source(row: _KvRow) -> _CanvasSource:
    owner_id, separator, lesson_id = row.key.partition(":")
    if not separator:
        owner_id = None
        lesson_id = row.key
    _validate_contract_id(lesson_id, label="canvas lesson id")
    payload = _json_object(row.raw_data, label=f"canvas {row.key}")
    try:
        if payload.get("schema_version") == "canvas/v1":
            _CanvasEnvelope.model_validate(payload)
        else:
            if "schema_version" in payload:
                raise ValueError("unsupported canvas schema version")
            _CanvasGraph.model_validate(payload)
    except (ValidationError, ValueError) as exc:
        raise StudentAssetMigrationIntegrityError(
            f"canvas record is invalid: {row.key}"
        ) from exc
    return _CanvasSource(row=row, owner_id=owner_id, lesson_id=lesson_id)


def _session_source(row: Any) -> _SessionSource:
    session_id = str(row["session_id"])
    raw_data = row["data"]
    if not isinstance(raw_data, str):
        raise StudentAssetMigrationIntegrityError(
            f"game session is not text: {session_id}"
        )
    try:
        envelope = decode_stored_session(raw_data, session_id)
    except StoredSessionIntegrityError as exc:
        raise StudentAssetMigrationIntegrityError(
            f"game session is invalid: {session_id}"
        ) from exc
    return _SessionSource(
        session_id=session_id,
        raw_data=raw_data,
        updated_at=row["updated_at"],
        session=envelope.session,
        release_identity=envelope.release_identity,
    )


def _dossier_source(row: Any) -> _DossierSource:
    dossier_id = str(row["dossier_id"])
    raw_data = row["data"]
    if not isinstance(raw_data, str):
        raise StudentAssetMigrationIntegrityError(
            f"game dossier is not text: {dossier_id}"
        )
    try:
        dossier = decode_stored_dossier(raw_data, dossier_id)
    except StoredDossierIntegrityError as exc:
        raise StudentAssetMigrationIntegrityError(
            f"game dossier is invalid: {dossier_id}"
        ) from exc
    return _DossierSource(
        dossier_id=dossier_id,
        raw_data=raw_data,
        updated_at=row["updated_at"],
        dossier=dossier,
    )


def _kv_row(row: Any) -> _KvRow:
    raw_data = row["data"]
    if not isinstance(raw_data, str):
        raise StudentAssetMigrationIntegrityError("KV record is not text")
    return _KvRow(
        namespace=str(row["namespace"]),
        key=str(row["key"]),
        raw_data=raw_data,
        updated_at=row["updated_at"],
    )


def _require_absent_kv(
    connection: Connection,
    namespace: str,
    key: str,
) -> None:
    if connection.execute(
        select(kv_table.c.key).where(
            (kv_table.c.namespace == namespace) & (kv_table.c.key == key)
        )
    ).first() is not None:
        raise StudentAssetMigrationConflict(
            f"target student asset already exists: {namespace}/{key}"
        )


def _counts(scan: _AssetScan) -> StudentAssetCounts:
    values = {
        "progress": len(scan.progress),
        "canvases": len(scan.canvases),
        "sessions": len(scan.sessions),
        "dossiers": len(scan.dossiers),
    }
    return StudentAssetCounts(**values, total=sum(values.values()))


def _source_fingerprint(scan: _AssetScan) -> str:
    rows: list[list[str]] = []
    rows.extend(
        ["kv", item.row.namespace, item.row.key, item.row.raw_data]
        for item in scan.progress
    )
    rows.extend(
        ["kv", item.row.namespace, item.row.key, item.row.raw_data]
        for item in scan.canvases
    )
    rows.extend(
        ["session", item.session_id, item.raw_data]
        for item in scan.sessions
    )
    rows.extend(
        ["dossier", item.dossier_id, item.raw_data]
        for item in scan.dossiers
    )
    return hashlib.sha256(_canonical_json(rows).encode("utf-8")).hexdigest()


def _table_names(engine: Engine) -> frozenset[str]:
    try:
        return frozenset(inspect(engine).get_table_names())
    except SQLAlchemyError as exc:
        raise StudentAssetMigrationError(
            "could not inspect student asset database"
        ) from exc


def _require_tables(actual: frozenset[str], required: set[str]) -> None:
    missing = sorted(required - set(actual))
    if missing:
        raise StudentAssetMigrationIntegrityError(
            "required database tables are missing: " + ", ".join(missing)
        )


def _validate_contract_id(value: str, *, label: str) -> str:
    class _IdModel(BaseModel):
        value: ContractId

    try:
        return _IdModel(value=value).value
    except ValidationError as exc:
        raise StudentAssetMigrationIntegrityError(f"invalid {label}") from exc


def _validate_request_id(value: str) -> str:
    if not isinstance(value, str) or _REQUEST_ID.fullmatch(value) is None:
        raise StudentAssetMigrationIntegrityError(
            "request id must use 1 to 100 ASCII letters, digits, dots, colons, "
            "underscores or hyphens"
        )
    return value


def _json_object(raw_data: str, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_data, object_pairs_hook=_reject_duplicate_keys)
    except (TypeError, json.JSONDecodeError, ValueError) as exc:
        raise StudentAssetMigrationIntegrityError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise StudentAssetMigrationIntegrityError(f"{label} must be an object")
    return payload


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _receipt_key(source_game_user_id: str) -> str:
    return f"legacy-v1:{source_game_user_id}"


def _migration_id(source_game_user_id: str) -> str:
    digest = hashlib.sha256(
        f"student-assets-v1\x1f{source_game_user_id}".encode("utf-8")
    ).hexdigest()[:24]
    return f"sam_{digest}"


def _require_one(rowcount: int | None, message: str) -> None:
    if rowcount != 1:
        raise StudentAssetMigrationConflict(message)


def _checksum(payload: object) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


__all__ = [
    "StudentAssetCounts",
    "StudentAssetMigrationAuthorizationError",
    "StudentAssetMigrationConflict",
    "StudentAssetMigrationError",
    "StudentAssetMigrationIntegrityError",
    "StudentAssetMigrationReport",
    "UnmappedStudentAssets",
    "UnmappedStudentAssetsError",
    "assert_no_unmapped_student_assets",
    "find_unmapped_student_assets",
    "migrate_legacy_student_assets",
]
