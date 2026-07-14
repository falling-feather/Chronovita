from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from services.contracts.v1 import GameSessionV1
from services.game_runtime import (
    AdvanceResultV1,
    RuntimeCommandV1,
    SituationEngineV1,
)
from services.game_runtime.catalog import ScenarioCatalogRepository


class GameSessionNotFound(ValueError):
    code = "game_session_not_found"


class ScenarioSummaryV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    scenario_version: int
    scenario_checksum: str
    course_id: str
    lesson_id: str
    title: str
    scenario_type: str
    student_role: str
    objective: str
    max_turns: int
    audience: Literal["development", "published"]


class GameRuntimeService:
    """Thread-safe ephemeral session coordinator; persistence belongs to BE-002."""

    def __init__(self, repository: ScenarioCatalogRepository) -> None:
        self.repository = repository
        self._lock = threading.RLock()
        self._sessions: dict[str, tuple[SituationEngineV1, GameSessionV1]] = {}

    def list_scenarios(self) -> tuple[ScenarioSummaryV1, ...]:
        return tuple(
            _summary(item.engine, audience=item.entry.audience)
            for item in self.repository.list_active_records()
        )

    def start_session(
        self,
        scenario_id: str,
        *,
        user_id: str,
        now: datetime | None = None,
    ) -> tuple[ScenarioSummaryV1, GameSessionV1]:
        loaded = self.repository.get_active_record(scenario_id)
        engine = loaded.engine
        started_at = now or _utcnow()
        session = engine.start_session(
            session_id=f"session-{uuid.uuid4().hex}",
            user_id=user_id,
            started_at=started_at,
        )
        with self._lock:
            self._sessions[session.session_id] = (engine, _copy_session(session))
        return _summary(engine, audience=loaded.entry.audience), session

    def get_session(self, session_id: str) -> GameSessionV1:
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                raise GameSessionNotFound(f"game session not found: {session_id}")
            return _copy_session(record[1])

    def apply_action(
        self,
        session_id: str,
        command: RuntimeCommandV1,
    ) -> AdvanceResultV1:
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                raise GameSessionNotFound(f"game session not found: {session_id}")
            engine, session = record
            result = engine.apply_action(session, command)
            self._sessions[session_id] = (engine, _copy_session(result.session))
            return result

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()


_SERVICE_LOCK = threading.RLock()
_SERVICE: GameRuntimeService | None = None


def configure_game_runtime(
    *,
    content_root: str | Path,
    catalog_path: str | Path,
) -> GameRuntimeService:
    service = GameRuntimeService(
        ScenarioCatalogRepository(
            content_root=content_root,
            catalog_path=catalog_path,
        )
    )
    global _SERVICE
    with _SERVICE_LOCK:
        _SERVICE = service
    return service


def get_game_runtime() -> GameRuntimeService:
    with _SERVICE_LOCK:
        if _SERVICE is None:
            raise RuntimeError("game runtime service has not been configured")
        return _SERVICE


def shutdown_game_runtime() -> None:
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is not None:
            _SERVICE.clear()
            _SERVICE = None


def _summary(
    engine: SituationEngineV1,
    *,
    audience: Literal["development", "published"],
) -> ScenarioSummaryV1:
    scenario = engine.scenario
    return ScenarioSummaryV1(
        scenario_id=scenario.scenario_id,
        scenario_version=scenario.scenario_version,
        scenario_checksum=str(scenario.checksum),
        course_id=scenario.course_id,
        lesson_id=scenario.lesson_id,
        title=scenario.title,
        scenario_type=scenario.scenario_type,
        student_role=scenario.student_role,
        objective=scenario.objective,
        max_turns=scenario.max_turns,
        audience=audience,
    )


def _copy_session(session: GameSessionV1) -> GameSessionV1:
    return GameSessionV1.model_validate(session.model_dump(mode="json"))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "GameRuntimeService",
    "GameSessionNotFound",
    "ScenarioSummaryV1",
    "configure_game_runtime",
    "get_game_runtime",
    "shutdown_game_runtime",
]
