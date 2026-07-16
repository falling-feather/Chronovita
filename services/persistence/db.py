from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator

from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Text,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from services.persistence.database import (
    DatabaseEngineConflict,
    DatabaseEngineOptions,
    DatabaseTarget,
    create_database_engine,
    resolve_database_target,
)

_LOCK = threading.RLock()
_ENGINE: Engine | None = None
_ENGINE_TARGET: DatabaseTarget | None = None
_ENGINE_OPTIONS: DatabaseEngineOptions | None = None
_METADATA = MetaData()


kv_table = Table(
    "kv",
    _METADATA,
    Column("namespace", String, primary_key=True),
    Column("key", String, primary_key=True),
    Column("data", Text, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)


def init_engine(
    sqlite_path: str = "data/chronovita.db",
    *,
    database_url: str | None = None,
    migration_mode: str = "apply-safe",
    engine_options: DatabaseEngineOptions | None = None,
) -> Engine:
    global _ENGINE, _ENGINE_OPTIONS, _ENGINE_TARGET
    target = resolve_database_target(
        database_url=database_url,
        sqlite_path=sqlite_path,
    )
    resolved_options = DatabaseEngineOptions()
    if target.dialect == "postgresql" and engine_options is not None:
        resolved_options = engine_options
    with _LOCK:
        if _ENGINE is not None:
            if _ENGINE_TARGET != target or _ENGINE_OPTIONS != resolved_options:
                raise DatabaseEngineConflict(
                    "persistence engine is already initialized for another target or option set"
                )
            return _ENGINE
        engine = create_database_engine(target, options=resolved_options)
        try:
            from services.persistence.schema import ensure_current_schema

            ensure_current_schema(
                engine,
                mode=migration_mode,
                migration_lock_timeout_seconds=(
                    resolved_options.migration_lock_timeout_seconds
                ),
            )
        except BaseException:
            engine.dispose()
            raise
        _ENGINE = engine
        _ENGINE_TARGET = target
        _ENGINE_OPTIONS = resolved_options
        return engine


def close_engine() -> None:
    global _ENGINE, _ENGINE_OPTIONS, _ENGINE_TARGET
    with _LOCK:
        if _ENGINE is not None:
            _ENGINE.dispose()
            _ENGINE = None
            _ENGINE_TARGET = None
            _ENGINE_OPTIONS = None


def _engine() -> Engine:
    if _ENGINE is None:
        raise RuntimeError("persistence engine 未初始化，请先调用 init_engine()")
    return _ENGINE


def _dumps(obj: Any) -> str:
    return json.dumps(
        obj,
        ensure_ascii=False,
        default=_json_default,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json_default(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat()
    if hasattr(o, "model_dump"):
        return o.model_dump(mode="json")
    raise TypeError(f"无法序列化类型 {type(o).__name__}")


def kv_set(namespace: str, key: str, data: Any) -> None:
    payload = _dumps(data)
    now = datetime.now(timezone.utc)
    with _engine().begin() as conn:
        values = {
            "namespace": namespace,
            "key": key,
            "data": payload,
            "updated_at": now,
        }
        if conn.dialect.name == "sqlite":
            statement = sqlite_insert(kv_table).values(**values)
        elif conn.dialect.name == "postgresql":
            statement = postgresql_insert(kv_table).values(**values)
        else:
            raise RuntimeError(
                f"kv persistence does not support dialect: {conn.dialect.name}"
            )
        conn.execute(
            statement.on_conflict_do_update(
                index_elements=[kv_table.c.namespace, kv_table.c.key],
                set_={"data": payload, "updated_at": now},
            )
        )


def kv_get(namespace: str, key: str) -> Any | None:
    found, data = kv_get_with_presence(namespace, key)
    return data if found else None


def kv_get_with_presence(namespace: str, key: str) -> tuple[bool, Any | None]:
    """Return row presence separately from a JSON value that may itself be null."""
    with _engine().begin() as conn:
        row = conn.execute(
            select(kv_table.c.data).where(
                (kv_table.c.namespace == namespace) & (kv_table.c.key == key)
            )
        ).first()
    return (True, json.loads(row[0])) if row else (False, None)


def kv_compare_and_set(
    namespace: str,
    key: str,
    expected: Any | None,
    data: Any,
    *,
    expected_present: bool | None = None,
) -> bool:
    """Atomically replace one structured JSON value or insert an absent key.

    ``expected_present`` distinguishes an absent key from a stored JSON null. When
    omitted, the legacy contract remains: ``expected is None`` means absent.
    """

    if expected_present is False and expected is not None:
        raise ValueError("expected must be None when expected_present is false")
    payload = _dumps(data)
    expected_payload = _dumps(expected)
    should_exist = (
        expected is not None if expected_present is None else expected_present
    )
    now = datetime.now(timezone.utc)
    try:
        with _kv_write_transaction() as conn:
            row = conn.execute(
                select(kv_table.c.data)
                .where(
                    (kv_table.c.namespace == namespace)
                    & (kv_table.c.key == key)
                )
                .with_for_update()
            ).first()
            if row is None:
                if should_exist:
                    return False
                conn.execute(
                    insert(kv_table).values(
                        namespace=namespace,
                        key=key,
                        data=payload,
                        updated_at=now,
                    )
                )
                return True
            if not should_exist:
                return False
            actual_payload = _dumps(json.loads(row[0]))
            if actual_payload != expected_payload:
                return False
            result = conn.execute(
                update(kv_table)
                .where(
                    (kv_table.c.namespace == namespace)
                    & (kv_table.c.key == key)
                )
                .values(data=payload, updated_at=now)
            )
            return result.rowcount == 1
    except IntegrityError:
        return False


@contextmanager
def _kv_write_transaction() -> Iterator[Connection]:
    with _engine().connect() as conn:
        try:
            if conn.dialect.name == "sqlite":
                conn.exec_driver_sql("BEGIN IMMEDIATE")
            elif conn.dialect.name == "postgresql":
                conn.begin()
            else:
                raise RuntimeError(
                    f"kv persistence does not support dialect: {conn.dialect.name}"
                )
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


def kv_delete(namespace: str, key: str) -> None:
    with _engine().begin() as conn:
        conn.execute(
            delete(kv_table).where(
                (kv_table.c.namespace == namespace) & (kv_table.c.key == key)
            )
        )


def kv_list(namespace: str) -> Iterable[dict]:
    with _engine().begin() as conn:
        rows = conn.execute(
            select(kv_table.c.data).where(kv_table.c.namespace == namespace)
        ).fetchall()
    for (raw,) in rows:
        yield json.loads(raw)


def kv_list_prefix(namespace: str, key_prefix: str) -> Iterable[tuple[str, Any]]:
    """List values whose keys begin with an exact, escaped prefix."""

    with _engine().begin() as conn:
        rows = conn.execute(
            select(kv_table.c.key, kv_table.c.data).where(
                (kv_table.c.namespace == namespace)
                & kv_table.c.key.startswith(key_prefix, autoescape=True)
            )
        ).fetchall()
    for key, raw in rows:
        yield key, json.loads(raw)
