from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Iterable

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
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from services.persistence.database import (
    DatabaseEngineConflict,
    DatabaseTarget,
    create_database_engine,
    resolve_database_target,
)

_LOCK = threading.RLock()
_ENGINE: Engine | None = None
_ENGINE_TARGET: DatabaseTarget | None = None
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
) -> Engine:
    global _ENGINE, _ENGINE_TARGET
    target = resolve_database_target(
        database_url=database_url,
        sqlite_path=sqlite_path,
    )
    with _LOCK:
        if _ENGINE is not None:
            if _ENGINE_TARGET != target:
                raise DatabaseEngineConflict(
                    "persistence engine is already initialized for another target"
                )
            return _ENGINE
        engine = create_database_engine(target)
        try:
            from services.persistence.schema import ensure_current_schema

            ensure_current_schema(engine, mode=migration_mode)
        except BaseException:
            engine.dispose()
            raise
        _ENGINE = engine
        _ENGINE_TARGET = target
        return engine


def close_engine() -> None:
    global _ENGINE, _ENGINE_TARGET
    with _LOCK:
        if _ENGINE is not None:
            _ENGINE.dispose()
            _ENGINE = None
            _ENGINE_TARGET = None


def _engine() -> Engine:
    if _ENGINE is None:
        raise RuntimeError("persistence engine 未初始化，请先调用 init_engine()")
    return _ENGINE


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=_json_default)


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
        existing = conn.execute(
            select(kv_table.c.key).where(
                (kv_table.c.namespace == namespace) & (kv_table.c.key == key)
            )
        ).first()
        if existing is None:
            conn.execute(
                insert(kv_table).values(
                    namespace=namespace, key=key, data=payload, updated_at=now
                )
            )
        else:
            conn.execute(
                update(kv_table)
                .where((kv_table.c.namespace == namespace) & (kv_table.c.key == key))
                .values(data=payload, updated_at=now)
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
) -> bool:
    """Atomically insert an absent key or replace the exact value previously read."""
    payload = _dumps(data)
    expected_payload = _dumps(expected) if expected is not None else None
    now = datetime.now(timezone.utc)
    try:
        with _engine().begin() as conn:
            if expected_payload is None:
                conn.execute(
                    insert(kv_table).values(
                        namespace=namespace,
                        key=key,
                        data=payload,
                        updated_at=now,
                    )
                )
                return True
            result = conn.execute(
                update(kv_table)
                .where(
                    (kv_table.c.namespace == namespace)
                    & (kv_table.c.key == key)
                    & (kv_table.c.data == expected_payload)
                )
                .values(data=payload, updated_at=now)
            )
            return result.rowcount == 1
    except IntegrityError:
        return False


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
