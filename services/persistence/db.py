from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine

_LOCK = threading.RLock()
_ENGINE: Engine | None = None
_METADATA = MetaData()


kv_table = Table(
    "kv",
    _METADATA,
    Column("namespace", String, primary_key=True),
    Column("key", String, primary_key=True),
    Column("data", Text, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)


def init_engine(sqlite_path: str) -> Engine:
    global _ENGINE
    with _LOCK:
        if _ENGINE is not None:
            return _ENGINE
        path = Path(sqlite_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{path.as_posix()}"
        _ENGINE = create_engine(url, connect_args={"check_same_thread": False}, future=True)
        _METADATA.create_all(_ENGINE)
        return _ENGINE


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
    now = datetime.utcnow()
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
    with _engine().begin() as conn:
        row = conn.execute(
            select(kv_table.c.data).where(
                (kv_table.c.namespace == namespace) & (kv_table.c.key == key)
            )
        ).first()
    return json.loads(row[0]) if row else None


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
