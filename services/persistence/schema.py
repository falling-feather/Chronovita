from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic, sleep
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    inspect,
    insert,
    select,
    text,
)
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from services.auth.store import (
    audit_events_table,
    audit_head_table,
    sessions_table,
    users_table,
)
from services.game_runtime.store import game_dossiers_table, game_sessions_table
from services.persistence.db import kv_table


MigrationMode = Literal["apply-safe", "validate"]
LATEST_SCHEMA_VERSION = 3
_SUPPORTED_DIALECTS = frozenset({"sqlite", "postgresql"})
_SQLITE_LOCK_ERRORS = ("database is locked", "database table is locked")
_POSTGRES_MIGRATION_LOCK_ID = 0x4348524F4E4F
_POSTGRES_MIGRATION_LOCK_POLL_SECONDS = 0.05
_ZERO_HASH = "0" * 64


class DatabaseSchemaError(RuntimeError):
    code = "database_schema_error"


class UnsupportedDatabaseDialect(DatabaseSchemaError):
    code = "unsupported_database_dialect"


class DatabaseMigrationPending(DatabaseSchemaError):
    code = "database_migration_pending"

    def __init__(self, status: "DatabaseSchemaStatus") -> None:
        self.status = status
        super().__init__(
            "database schema migration is required "
            f"(current={status.current_version}, latest={status.latest_version})"
        )


class DatabaseSchemaTooNew(DatabaseSchemaError):
    code = "database_schema_too_new"


class DatabaseMigrationHistoryError(DatabaseSchemaError):
    code = "database_migration_history_error"


class DatabaseSchemaDrift(DatabaseSchemaError):
    code = "database_schema_drift"


class DatabaseMigrationBusy(DatabaseSchemaError):
    code = "database_migration_busy"


class DatabaseSchemaStorageError(DatabaseSchemaError):
    code = "database_schema_storage_error"


class DatabaseSchemaStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["chronovita-database-status/v1"] = (
        "chronovita-database-status/v1"
    )
    dialect: Literal["sqlite", "postgresql"]
    ledger_present: bool
    current_version: int
    latest_version: int
    pending_versions: tuple[int, ...]
    is_current: bool


_SCHEMA_METADATA = MetaData()
schema_migrations_table = Table(
    "chronovita_schema_migrations",
    _SCHEMA_METADATA,
    Column("version", Integer, primary_key=True, autoincrement=False),
    Column("migration_id", String(80), nullable=False, unique=True),
    Column("contract_checksum", String(64), nullable=False),
    Column("applied_at", DateTime(timezone=True), nullable=False),
    Column("app_version", String(20), nullable=False),
)


@dataclass(frozen=True)
class _Migration:
    version: int
    migration_id: str
    app_version: str
    tables: tuple[Table, ...]
    invariant_id: str = "none"
    initialize: Callable[[Connection], None] | None = None
    validate: Callable[[Connection], None] | None = None

    @property
    def contract_checksum(self) -> str:
        return _checksum(_migration_contract(self))


def ensure_current_schema(
    engine: Engine,
    *,
    mode: MigrationMode = "apply-safe",
    migration_lock_timeout_seconds: float = 30.0,
) -> DatabaseSchemaStatus:
    """Validate or safely advance the registered Chronovita database schema."""

    _validate_mode(mode)
    _validate_migration_lock_timeout(migration_lock_timeout_seconds)
    dialect = _dialect(engine)
    if mode == "validate":
        status = inspect_schema(engine)
        if not status.is_current:
            raise DatabaseMigrationPending(status)
        return status
    status = inspect_schema(engine)
    if status.is_current:
        return status
    try:
        with engine.connect() as connection:
            _begin_migration_transaction(
                connection,
                dialect,
                lock_timeout_seconds=migration_lock_timeout_seconds,
            )
            try:
                status = _apply_registered_migrations(connection, dialect)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                _end_migration_transaction(connection, dialect)
            return status
    except DatabaseSchemaError:
        raise
    except OperationalError as exc:
        if dialect == "sqlite" and any(
            marker in str(exc).lower() for marker in _SQLITE_LOCK_ERRORS
        ):
            raise DatabaseMigrationBusy(
                "another process is migrating the database"
            ) from exc
        raise DatabaseSchemaStorageError(
            "database schema operation failed"
        ) from exc
    except SQLAlchemyError as exc:
        raise DatabaseSchemaStorageError(
            "database schema operation failed"
        ) from exc


def inspect_schema(engine: Engine) -> DatabaseSchemaStatus:
    """Inspect the ledger and table contracts without writing to the database."""

    dialect = _dialect(engine)
    try:
        with engine.connect() as connection:
            _configure_snapshot_isolation(connection, dialect)
            table_names = _table_names(connection)
            ledger_present = schema_migrations_table.name in table_names
            if not ledger_present:
                _reject_unknown_tables(table_names)
                _validate_legacy_layout(connection, table_names)
                return _status(dialect, ledger_present=False, current_version=0)
            _reject_too_new_ledger(connection)
            _validate_table(connection, schema_migrations_table)
            rows = _migration_rows(connection)
            current_version = _validate_history(rows)
            _reject_unknown_tables(table_names)
            _validate_applied_migrations(
                connection,
                current_version=current_version,
            )
            _validate_pending_layout(
                table_names,
                current_version=current_version,
            )
            return _status(
                dialect,
                ledger_present=True,
                current_version=current_version,
            )
    except DatabaseSchemaError:
        raise
    except SQLAlchemyError as exc:
        raise DatabaseSchemaStorageError(
            "database schema inspection failed"
        ) from exc


def migration_contract_checksums() -> tuple[str, ...]:
    return tuple(item.contract_checksum for item in _MIGRATIONS)


def _apply_registered_migrations(
    connection: Connection,
    dialect: str,
) -> DatabaseSchemaStatus:
    table_names = _table_names(connection)
    ledger_present = schema_migrations_table.name in table_names
    if ledger_present:
        _reject_too_new_ledger(connection)
        _reject_unknown_tables(table_names)
        _validate_table(connection, schema_migrations_table)
        current_version = _validate_history(_migration_rows(connection))
        _validate_applied_migrations(
            connection,
            current_version=current_version,
        )
        _validate_pending_layout(
            table_names,
            current_version=current_version,
        )
    else:
        _reject_unknown_tables(table_names)
        _validate_legacy_layout(connection, table_names)
        schema_migrations_table.create(connection, checkfirst=False)
        ledger_present = True
        current_version = 0

    for migration in _MIGRATIONS[current_version:]:
        table_names = _table_names(connection)
        managed_names = {table.name for table in migration.tables}
        present_names = managed_names & table_names
        if present_names and present_names != managed_names:
            raise DatabaseSchemaDrift(
                f"migration {migration.migration_id} has a partial table set"
            )
        if present_names == managed_names:
            _validate_migration(connection, migration)
        else:
            for table in migration.tables:
                table.create(connection, checkfirst=False)
            if migration.initialize is not None:
                migration.initialize(connection)
            _validate_migration(connection, migration)
        connection.execute(
            insert(schema_migrations_table).values(
                version=migration.version,
                migration_id=migration.migration_id,
                contract_checksum=migration.contract_checksum,
                applied_at=datetime.now(timezone.utc),
                app_version=migration.app_version,
            )
        )
        current_version = migration.version

    _reject_unknown_tables(_table_names(connection))
    _validate_table(connection, schema_migrations_table)
    _validate_history(_migration_rows(connection))
    return _status(
        dialect,
        ledger_present=ledger_present,
        current_version=LATEST_SCHEMA_VERSION,
    )


def _begin_migration_transaction(
    connection: Connection,
    dialect: str,
    *,
    lock_timeout_seconds: float,
) -> None:
    if dialect == "sqlite":
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        return
    _acquire_postgres_migration_lock(
        connection,
        timeout_seconds=lock_timeout_seconds,
    )
    try:
        _configure_snapshot_isolation(connection, dialect)
        connection.begin()
    except BaseException:
        _end_migration_transaction(connection, dialect)
        raise


def _acquire_postgres_migration_lock(
    connection: Connection,
    *,
    timeout_seconds: float,
) -> None:
    deadline = monotonic() + timeout_seconds
    while True:
        acquired = False
        try:
            acquired = bool(
                connection.execute(
                    text("SELECT pg_try_advisory_lock(:lock_id)"),
                    {"lock_id": _POSTGRES_MIGRATION_LOCK_ID},
                ).scalar_one()
            )
            connection.commit()
        except BaseException:
            connection.invalidate()
            raise
        if acquired:
            return
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise DatabaseMigrationBusy(
                "timed out waiting for the database migration lock"
            )
        sleep(min(_POSTGRES_MIGRATION_LOCK_POLL_SECONDS, remaining))


def _end_migration_transaction(connection: Connection, dialect: str) -> None:
    if dialect != "postgresql":
        return
    try:
        if connection.in_transaction():
            connection.rollback()
        released = connection.execute(
            text("SELECT pg_advisory_unlock(:lock_id)"),
            {"lock_id": _POSTGRES_MIGRATION_LOCK_ID},
        ).scalar_one()
        connection.commit()
    except SQLAlchemyError as exc:
        connection.invalidate()
        raise DatabaseSchemaStorageError(
            "database migration lock release failed"
        ) from exc
    if released is not True:
        connection.invalidate()
        raise DatabaseSchemaStorageError(
            "database migration lock ownership was lost"
        )


def _configure_snapshot_isolation(connection: Connection, dialect: str) -> None:
    if dialect == "postgresql":
        connection.execution_options(isolation_level="REPEATABLE READ")


def _validate_legacy_layout(
    connection: Connection,
    table_names: frozenset[str],
) -> None:
    missing_predecessor = False
    for migration in _MIGRATIONS:
        managed_names = {table.name for table in migration.tables}
        present_names = managed_names & table_names
        if present_names and present_names != managed_names:
            raise DatabaseSchemaDrift(
                f"migration {migration.migration_id} has a partial table set"
            )
        if present_names == managed_names:
            if missing_predecessor:
                raise DatabaseSchemaDrift(
                    "legacy database table groups are not a contiguous prefix"
                )
            _validate_migration(connection, migration)
        else:
            missing_predecessor = True


def _validate_pending_layout(
    table_names: frozenset[str],
    *,
    current_version: int,
) -> None:
    for migration in _MIGRATIONS[current_version:]:
        managed_names = {table.name for table in migration.tables}
        present_names = managed_names & table_names
        if present_names:
            raise DatabaseSchemaDrift(
                f"migration {migration.migration_id} has unregistered tables"
            )


def _validate_applied_migrations(
    connection: Connection,
    *,
    current_version: int,
) -> None:
    for migration in _MIGRATIONS[:current_version]:
        _validate_migration(connection, migration)


def _validate_migration(connection: Connection, migration: _Migration) -> None:
    for table in migration.tables:
        _validate_table(connection, table)
    if migration.validate is not None:
        migration.validate(connection)


def _validate_table(connection: Connection, expected: Table) -> None:
    inspector = inspect(connection)
    try:
        actual_columns = inspector.get_columns(expected.name)
        actual_pk = inspector.get_pk_constraint(expected.name)
        actual_unique = inspector.get_unique_constraints(expected.name)
        actual_indexes = inspector.get_indexes(expected.name)
    except SQLAlchemyError as exc:
        raise DatabaseSchemaDrift(
            f"could not inspect table contract: {expected.name}"
        ) from exc
    expected_pk = tuple(column.name for column in expected.primary_key.columns)
    found_pk = tuple(actual_pk.get("constrained_columns") or ())
    if found_pk != expected_pk:
        raise DatabaseSchemaDrift(
            f"table primary key drifted: {expected.name}"
        )
    expected_columns = tuple(_column_contract(column) for column in expected.columns)
    found_pk_names = frozenset(found_pk)
    found_columns = tuple(
        _inspected_column_contract(column, primary_keys=found_pk_names)
        for column in actual_columns
    )
    if found_columns != expected_columns:
        raise DatabaseSchemaDrift(
            f"table column contract drifted: {expected.name}"
        )
    expected_unique = {
        tuple(column.name for column in constraint.columns)
        for constraint in expected.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    found_unique = {
        tuple(item.get("column_names") or ())
        for item in actual_unique
    }
    if found_unique != expected_unique:
        raise DatabaseSchemaDrift(
            f"table unique constraints drifted: {expected.name}"
        )
    expected_indexes = sorted(
        (tuple(column.name for column in index.columns), bool(index.unique))
        for index in expected.indexes
    )
    found_indexes = sorted(
        (tuple(item.get("column_names") or ()), bool(item.get("unique")))
        for item in actual_indexes
        if not item.get("duplicates_constraint")
    )
    if found_indexes != expected_indexes:
        raise DatabaseSchemaDrift(
            f"table indexes drifted: {expected.name}"
        )


def _column_contract(column: Column) -> tuple[object, ...]:
    return (
        column.name,
        _type_contract(column.type),
        bool(column.nullable),
        bool(column.primary_key),
    )


def _inspected_column_contract(
    column: dict,
    *,
    primary_keys: frozenset[str],
) -> tuple[object, ...]:
    return (
        str(column["name"]),
        _type_contract(column["type"]),
        bool(column.get("nullable", True)),
        str(column["name"]) in primary_keys,
    )


def _type_contract(value: object) -> tuple[object, ...]:
    if isinstance(value, Text):
        return ("text",)
    if isinstance(value, String):
        return ("string", value.length)
    if isinstance(value, Boolean):
        return ("boolean",)
    if isinstance(value, Integer):
        return ("integer",)
    if isinstance(value, DateTime):
        return ("datetime",)
    return (type(value).__name__.lower(),)


def _migration_rows(connection: Connection) -> list[dict]:
    return list(
        connection.execute(
            select(schema_migrations_table).order_by(
                schema_migrations_table.c.version
            )
        ).mappings()
    )


def _reject_too_new_ledger(connection: Connection) -> None:
    try:
        latest = connection.execute(
            select(schema_migrations_table.c.version)
            .order_by(schema_migrations_table.c.version.desc())
            .limit(1)
        ).scalar_one_or_none()
    except SQLAlchemyError as exc:
        raise DatabaseSchemaDrift(
            "database migration ledger version is unreadable"
        ) from exc
    if latest is None:
        return
    try:
        latest_version = int(latest)
    except (TypeError, ValueError) as exc:
        raise DatabaseMigrationHistoryError(
            "database migration ledger version is invalid"
        ) from exc
    if latest_version > LATEST_SCHEMA_VERSION:
        raise DatabaseSchemaTooNew(
            "database schema is newer than this application"
        )


def _validate_history(rows: list[dict]) -> int:
    if not rows:
        return 0
    versions = [int(row["version"]) for row in rows]
    if versions[-1] > LATEST_SCHEMA_VERSION:
        raise DatabaseSchemaTooNew(
            "database schema is newer than this application"
        )
    expected_versions = list(range(1, versions[-1] + 1))
    if versions != expected_versions:
        raise DatabaseMigrationHistoryError(
            "database migration history is not contiguous"
        )
    for row, migration in zip(
        rows,
        _MIGRATIONS[: len(rows)],
        strict=True,
    ):
        if (
            row["migration_id"] != migration.migration_id
            or row["contract_checksum"] != migration.contract_checksum
            or row["app_version"] != migration.app_version
        ):
            raise DatabaseMigrationHistoryError(
                f"database migration history was rewritten at version {migration.version}"
            )
    return versions[-1]


def _initialize_identity_audit(connection: Connection) -> None:
    connection.execute(
        insert(audit_head_table).values(
            head_id=1,
            sequence=0,
            event_hash=_ZERO_HASH,
        )
    )


def _validate_identity_audit(connection: Connection) -> None:
    heads = connection.execute(
        select(audit_head_table).order_by(audit_head_table.c.head_id)
    ).mappings().all()
    if len(heads) != 1 or int(heads[0]["head_id"]) != 1:
        raise DatabaseSchemaDrift("identity audit head invariant is invalid")
    events = connection.execute(
        select(audit_events_table).order_by(audit_events_table.c.sequence)
    ).mappings()
    previous_hash = _ZERO_HASH
    event_count = 0
    for expected_sequence, event in enumerate(events, start=1):
        event_count = expected_sequence
        if (
            int(event["sequence"]) != expected_sequence
            or event["previous_hash"] != previous_hash
        ):
            raise DatabaseSchemaDrift("identity audit chain is not contiguous")
        try:
            actor_roles = json.loads(event["actor_roles"])
            details = json.loads(event["details"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise DatabaseSchemaDrift(
                "identity audit event JSON is invalid"
            ) from exc
        payload = {
            "sequence": expected_sequence,
            "event_id": event["event_id"],
            "occurred_at": event["occurred_at"],
            "actor_user_id": event["actor_user_id"],
            "actor_session_id": event["actor_session_id"],
            "actor_roles": actor_roles,
            "action": event["action"],
            "resource_type": event["resource_type"],
            "resource_id": event["resource_id"],
            "outcome": event["outcome"],
            "request_id": event["request_id"],
            "details": details,
            "previous_hash": previous_hash,
        }
        if event["event_hash"] != _checksum(payload):
            raise DatabaseSchemaDrift("identity audit event checksum is invalid")
        previous_hash = event["event_hash"]
    head = heads[0]
    if (
        int(head["sequence"]) != event_count
        or head["event_hash"] != previous_hash
    ):
        raise DatabaseSchemaDrift("identity audit head does not match its events")


def _migration_contract(migration: _Migration) -> dict:
    return {
        "version": migration.version,
        "migration_id": migration.migration_id,
        "app_version": migration.app_version,
        "tables": [_table_contract(table) for table in migration.tables],
        "invariant_id": migration.invariant_id,
    }


def _table_contract(table: Table) -> dict:
    return {
        "name": table.name,
        "columns": [list(_column_contract(column)) for column in table.columns],
        "primary_key": [column.name for column in table.primary_key.columns],
        "unique": sorted(
            [column.name for column in constraint.columns]
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        ),
        "indexes": sorted(
            [
                {
                    "columns": [column.name for column in index.columns],
                    "unique": bool(index.unique),
                }
                for index in table.indexes
            ],
            key=lambda item: (item["columns"], item["unique"]),
        ),
    }


def _status(
    dialect: str,
    *,
    ledger_present: bool,
    current_version: int,
) -> DatabaseSchemaStatus:
    return DatabaseSchemaStatus(
        dialect=dialect,
        ledger_present=ledger_present,
        current_version=current_version,
        latest_version=LATEST_SCHEMA_VERSION,
        pending_versions=tuple(
            range(current_version + 1, LATEST_SCHEMA_VERSION + 1)
        ),
        is_current=(
            ledger_present and current_version == LATEST_SCHEMA_VERSION
        ),
    )


def _reject_unknown_tables(table_names: frozenset[str]) -> None:
    unknown = table_names - _KNOWN_TABLE_NAMES
    if unknown:
        raise DatabaseSchemaDrift(
            "database contains unknown application tables: "
            + ", ".join(sorted(unknown))
        )


def _table_names(connection: Connection) -> frozenset[str]:
    return frozenset(inspect(connection).get_table_names())


def _dialect(engine: Engine) -> Literal["sqlite", "postgresql"]:
    name = engine.dialect.name
    if name not in _SUPPORTED_DIALECTS:
        raise UnsupportedDatabaseDialect(
            f"database dialect is not supported: {name}"
        )
    return name


def _validate_mode(mode: str) -> None:
    if mode not in ("apply-safe", "validate"):
        raise ValueError("database migration mode must be apply-safe or validate")


def _validate_migration_lock_timeout(value: float) -> None:
    if not 0.1 <= value <= 300:
        raise ValueError(
            "database migration lock timeout must be between 0.1 and 300 seconds"
        )


def _checksum(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


_MIGRATIONS = (
    _Migration(
        version=1,
        migration_id="core-kv-v1",
        app_version="0.9.7",
        tables=(kv_table,),
    ),
    _Migration(
        version=2,
        migration_id="game-runtime-v1",
        app_version="0.9.7",
        tables=(game_sessions_table, game_dossiers_table),
    ),
    _Migration(
        version=3,
        migration_id="identity-audit-v1",
        app_version="0.9.7",
        tables=(users_table, sessions_table, audit_head_table, audit_events_table),
        invariant_id="identity-audit-chain-v1",
        initialize=_initialize_identity_audit,
        validate=_validate_identity_audit,
    ),
)
_KNOWN_TABLE_NAMES = frozenset(
    {
        schema_migrations_table.name,
        *(
            table.name
            for migration in _MIGRATIONS
            for table in migration.tables
        ),
    }
)


__all__ = [
    "DatabaseMigrationBusy",
    "DatabaseMigrationHistoryError",
    "DatabaseMigrationPending",
    "DatabaseSchemaDrift",
    "DatabaseSchemaError",
    "DatabaseSchemaStatus",
    "DatabaseSchemaStorageError",
    "DatabaseSchemaTooNew",
    "LATEST_SCHEMA_VERSION",
    "MigrationMode",
    "UnsupportedDatabaseDialect",
    "ensure_current_schema",
    "inspect_schema",
    "migration_contract_checksums",
    "schema_migrations_table",
]
