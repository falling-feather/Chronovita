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


canvas_boards_table = Table(
    "canvas_boards",
    _METADATA,
    Column("board_id", String, primary_key=True),
    Column("data", Text, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)

sandbox_playthroughs_table = Table(
    "sandbox_playthroughs",
    _METADATA,
    Column("playthrough_id", String, primary_key=True),
    Column("data", Text, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)

agent_sessions_table = Table(
    "agent_sessions",
    _METADATA,
    Column("session_id", String, primary_key=True),
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


def _upsert(table: Table, key_col: str, key_val: str, data: Any) -> None:
    payload = _dumps(data)
    now = datetime.utcnow()
    with _engine().begin() as conn:
        existing = conn.execute(select(table.c[key_col]).where(table.c[key_col] == key_val)).first()
        if existing is None:
            conn.execute(insert(table).values({key_col: key_val, "data": payload, "updated_at": now}))
        else:
            conn.execute(
                update(table)
                .where(table.c[key_col] == key_val)
                .values(data=payload, updated_at=now)
            )


def _delete(table: Table, key_col: str, key_val: str) -> None:
    with _engine().begin() as conn:
        conn.execute(delete(table).where(table.c[key_col] == key_val))


def _load_all(table: Table) -> Iterable[dict]:
    with _engine().begin() as conn:
        rows = conn.execute(select(table.c.data)).fetchall()
    for (raw,) in rows:
        yield json.loads(raw)


def save_board(board: Any) -> None:
    _upsert(canvas_boards_table, "board_id", board.board_id, board)


def delete_board(board_id: str) -> None:
    _delete(canvas_boards_table, "board_id", board_id)


def load_all_boards() -> Iterable[dict]:
    return _load_all(canvas_boards_table)


def save_playthrough(snap: Any) -> None:
    _upsert(sandbox_playthroughs_table, "playthrough_id", snap.playthrough_id, snap)


def load_all_playthroughs() -> Iterable[dict]:
    return _load_all(sandbox_playthroughs_table)


def save_session(sess: Any) -> None:
    _upsert(agent_sessions_table, "session_id", sess.session_id, sess)


def load_all_sessions() -> Iterable[dict]:
    return _load_all(agent_sessions_table)
