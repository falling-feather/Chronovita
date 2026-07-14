from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.engine import Engine

from services.contracts.v1 import GameSessionV1, RuntimeBundleV1
from services.game_runtime import (
    AdvanceResultV1,
    RuntimeCommandV1,
    SessionIntegrityError,
    SituationEngineV1,
)
from services.game_runtime.catalog import (
    ScenarioCatalogNotFound,
    ScenarioCatalogRepository,
)
from services.game_runtime.store import (
    GameRuntimeStore,
    StoredSessionAlreadyExists,
    StoredSessionIntegrityError,
    StoredSessionNotFound,
    StoredSessionRecord,
    StoredSessionWriteConflict,
)


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
    """Durable session coordinator backed by optimistic whole-record CAS."""

    def __init__(
        self,
        repository: ScenarioCatalogRepository,
        store: GameRuntimeStore,
    ) -> None:
        self.repository = repository
        self.store = store
        self._lock = threading.RLock()

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
        try:
            self.store.create_session(session)
        except (
            StoredSessionAlreadyExists,
            StoredSessionIntegrityError,
        ) as exc:
            raise SessionIntegrityError(str(exc)) from exc
        return _summary(engine, audience=loaded.entry.audience), session

    def get_session(self, session_id: str) -> GameSessionV1:
        record = self._load_record(session_id)
        engine = self._engine_for(record.session)
        return self._validated_session(engine, record.session)

    def apply_action(
        self,
        session_id: str,
        command: RuntimeCommandV1,
    ) -> AdvanceResultV1:
        with self._lock:
            record = self._load_record(session_id)
            engine = self._engine_for(record.session)
            session = self._validated_session(engine, record.session)
            result = engine.apply_action(session, command)
            if result.session.revision == session.revision:
                return result
            try:
                self.store.compare_and_swap(record, result.session)
            except StoredSessionIntegrityError as exc:
                raise SessionIntegrityError(str(exc)) from exc
            except StoredSessionWriteConflict:
                latest = self._load_record(session_id)
                latest_engine = self._engine_for(latest.session)
                latest_session = self._validated_session(
                    latest_engine,
                    latest.session,
                )
                return latest_engine.apply_action(latest_session, command)
            return result

    def _load_record(self, session_id: str) -> StoredSessionRecord:
        try:
            return self.store.load_session(session_id)
        except StoredSessionNotFound as exc:
            raise GameSessionNotFound(str(exc)) from exc
        except StoredSessionIntegrityError as exc:
            raise SessionIntegrityError(str(exc)) from exc

    def _engine_for(self, session: GameSessionV1) -> SituationEngineV1:
        try:
            return self.repository.get_exact(
                session.scenario_id,
                session.scenario_version,
                session.scenario_checksum,
            )
        except ScenarioCatalogNotFound as exc:
            raise SessionIntegrityError(
                "the pinned scenario artifact is no longer available"
            ) from exc

    @staticmethod
    def _validated_session(
        engine: SituationEngineV1,
        session: GameSessionV1,
    ) -> GameSessionV1:
        try:
            bundle = RuntimeBundleV1.model_validate(
                {
                    "course": engine.course.model_dump(mode="json"),
                    "scenario": engine.scenario.model_dump(mode="json"),
                    "session": session.model_dump(mode="json"),
                }
            )
        except ValidationError as exc:
            raise SessionIntegrityError(
                f"persisted session failed deterministic replay: {exc}"
            ) from exc
        if bundle.session is None:
            raise SessionIntegrityError("persisted runtime bundle lost its session")
        return bundle.session


_SERVICE_LOCK = threading.RLock()
_SERVICE: GameRuntimeService | None = None


def configure_game_runtime(
    *,
    content_root: str | Path,
    catalog_path: str | Path,
    engine: Engine | None = None,
    store: GameRuntimeStore | None = None,
) -> GameRuntimeService:
    if store is None:
        if engine is None:
            raise ValueError("configure_game_runtime requires an engine or store")
        store = GameRuntimeStore(engine)
    elif engine is not None:
        raise ValueError("configure_game_runtime accepts either engine or store")
    service = GameRuntimeService(
        ScenarioCatalogRepository(
            content_root=content_root,
            catalog_path=catalog_path,
        ),
        store,
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
