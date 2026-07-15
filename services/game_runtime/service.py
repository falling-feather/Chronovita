from __future__ import annotations

import hashlib
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Protocol

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)
from sqlalchemy.engine import Engine

from services.ai.contracts import ActionClassificationV1, ClassificationReason
from services.contracts.v1 import (
    Checksum,
    ContractId,
    DossierChoiceV1,
    DossierV1,
    GameSessionV1,
    RuntimeBundleV1,
    StateSnapshotV1,
    TurnV1,
)
from services.game_runtime import (
    AdvanceResultV1,
    AvailableActionV1,
    DuplicateActionConflict,
    RevisionConflict,
    RuntimeCommandV1,
    SessionIntegrityError,
    SituationEngineV1,
)
from services.game_runtime.catalog import (
    LoadedScenarioV1,
    ScenarioCatalogNotFound,
    ScenarioCatalogRepository,
)
from services.game_runtime.dossier import (
    DossierGenerationError,
    build_final_dossier,
)
from services.game_runtime.store import (
    GameSessionReleaseIdentityV1,
    GameRuntimeStore,
    StoredDossierIntegrityError,
    StoredDossierNotFound,
    StoredSessionAlreadyExists,
    StoredSessionIntegrityError,
    StoredSessionNotFound,
    StoredSessionRecord,
    StoredSessionWriteConflict,
)


class GameSessionNotFound(ValueError):
    code = "game_session_not_found"


class DossierNotReady(ValueError):
    code = "dossier_not_ready"


class DuplicateStartConflict(ValueError):
    code = "duplicate_start_conflict"


class PublishedScenarioPinRequired(ValueError):
    code = "published_scenario_pin_required"


class ActionClassifierProtocol(Protocol):
    async def classify(
        self,
        engine: SituationEngineV1,
        session: GameSessionV1,
        raw_input: str,
    ) -> ActionClassificationV1:
        ...


class ScenarioReleasePinV1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        str_strip_whitespace=True,
        strict=True,
    )

    release_id: ContractId
    release_no: int = Field(ge=1)
    release_checksum: Checksum
    course_id: ContractId
    lesson_id: ContractId
    course_content_version: int = Field(ge=1)
    course_checksum: Checksum
    scenario_version: int = Field(ge=1)
    scenario_checksum: Checksum


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
    release_id: ContractId | None = None
    release_no: int | None = None
    release_checksum: Checksum | None = None


class SessionReplayV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["game-session-replay/v1"] = (
        "game-session-replay/v1"
    )
    verified: Literal[True] = True
    commands: list[RuntimeCommandV1]
    session: GameSessionV1


class FreeInputResultV1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        strict=True,
        str_strip_whitespace=True,
    )

    schema_version: Literal["free-input-result/v1"] = "free-input-result/v1"
    kind: Literal[
        "advanced",
        "clarification_required",
        "rejected",
        "provider_unavailable",
    ]
    reason_code: ClassificationReason | None = None
    message: str = Field(min_length=1, max_length=240)
    available_actions: tuple[AvailableActionV1, ...] = ()
    result: AdvanceResultV1 | None = None

    @model_validator(mode="after")
    def validate_result_shape(self) -> "FreeInputResultV1":
        if self.kind == "advanced":
            if self.result is None or self.reason_code is not None:
                raise ValueError(
                    "advanced free input requires a result and no reason_code"
                )
        elif self.result is not None or self.reason_code is None:
            raise ValueError(
                "non-advanced free input requires a reason_code and no result"
            )
        return self


_FREE_INPUT_ADVANCED_MESSAGE = (
    "已按你的表述执行，并由规则引擎完成本回合结算。"
)


class TeacherSessionSummaryV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["teacher-session-summary/v1"] = (
        "teacher-session-summary/v1"
    )
    session_id: ContractId
    user_id: ContractId
    course_id: ContractId
    lesson_id: ContractId
    scenario_id: ContractId
    scenario_version: int
    scenario_checksum: Checksum
    scenario_title: str
    student_role: str
    objective: str
    status: Literal["active", "completed", "abandoned", "failed"]
    revision: int
    current_turn: int
    started_at: AwareDatetime
    updated_at: AwareDatetime
    ended_at: AwareDatetime | None = None
    ending_id: ContractId | None = None
    ending_title: str = ""
    ending_summary: str = ""
    key_choices: list[DossierChoiceV1]
    state_trajectory: list[StateSnapshotV1]
    fact_refs: list[ContractId]
    source_ref_ids: list[ContractId]
    dossier_id: ContractId | None = None
    dossier_checksum: Checksum | None = None


class GameRuntimeService:
    """Durable session coordinator backed by optimistic whole-record CAS."""

    def __init__(
        self,
        repository: ScenarioCatalogRepository,
        store: GameRuntimeStore,
        classifier: ActionClassifierProtocol | None = None,
    ) -> None:
        self.repository = repository
        self.store = store
        self._classifier = classifier
        self._lock = threading.RLock()

    def list_scenarios(self) -> tuple[ScenarioSummaryV1, ...]:
        return tuple(
            _summary(item)
            for item in self.repository.list_active_records()
        )

    def start_session(
        self,
        scenario_id: str,
        *,
        user_id: str,
        client_request_id: str | None = None,
        release_pin: ScenarioReleasePinV1 | None = None,
        now: datetime | None = None,
    ) -> tuple[ScenarioSummaryV1, GameSessionV1]:
        if release_pin is None:
            loaded = self.repository.get_active_record(scenario_id)
            if loaded.entry.audience == "published":
                raise PublishedScenarioPinRequired(
                    "published scenarios require a complete release_pin"
                )
        else:
            checked_pin = ScenarioReleasePinV1.model_validate(
                release_pin.model_dump(mode="python")
            )
            loaded = self.repository.get_published_record(
                scenario_id,
                checked_pin.scenario_version,
                str(checked_pin.scenario_checksum),
                release_id=checked_pin.release_id,
                release_no=checked_pin.release_no,
                release_checksum=str(checked_pin.release_checksum),
                course_id=checked_pin.course_id,
                lesson_id=checked_pin.lesson_id,
                course_content_version=checked_pin.course_content_version,
                course_checksum=str(checked_pin.course_checksum),
            )
        engine = loaded.engine
        started_at = now or _utcnow()
        session_id = (
            _session_id_for_request(user_id, client_request_id)
            if client_request_id is not None
            else f"session-{uuid.uuid4().hex}"
        )
        session = engine.start_session(
            session_id=session_id,
            user_id=user_id,
            started_at=started_at,
        )
        dossier = None
        if session.status == "completed":
            session, dossier = self._build_dossier(engine, session)
        try:
            self.store.create_session(
                session,
                dossier,
                release_identity=_release_identity(loaded),
            )
        except StoredSessionAlreadyExists as exc:
            if client_request_id is None:
                raise SessionIntegrityError(str(exc)) from exc
            existing = self._load_record(session_id)
            existing_engine = self._engine_for(existing.session)
            existing_session = self._validated_session(
                existing_engine,
                existing.session,
            )
            if (
                existing_session.user_id != user_id
                or _runtime_identity(existing_session) != _runtime_identity(session)
                or existing.envelope.release_identity != _release_identity(loaded)
            ):
                raise DuplicateStartConflict(
                    "client_request_id was already used for another game session"
                ) from exc
            if existing_session.dossier_id is not None:
                self._load_validated_dossier(
                    existing_engine,
                    existing_session,
                )
            return (
                _summary(loaded),
                existing_session,
            )
        except (
            StoredSessionIntegrityError,
            StoredDossierIntegrityError,
        ) as exc:
            raise SessionIntegrityError(str(exc)) from exc
        return _summary(loaded), session

    def get_session(self, session_id: str) -> GameSessionV1:
        record = self._load_record(session_id)
        engine = self._engine_for(record.session)
        session = self._validated_session(engine, record.session)
        if session.dossier_id is not None:
            self._load_validated_dossier(engine, session)
        return session

    def get_dossier(self, session_id: str) -> DossierV1:
        record = self._load_record(session_id)
        engine = self._engine_for(record.session)
        session = self._validated_session(engine, record.session)
        if session.status != "completed":
            raise DossierNotReady(
                f"game session {session_id} is still {session.status}"
            )
        if session.dossier_id is None:
            raise DossierNotReady(
                "completed session has no materialized dossier; use POST to create it"
            )
        return self._load_validated_dossier(engine, session)

    def ensure_dossier(self, session_id: str) -> DossierV1:
        with self._lock:
            record = self._load_record(session_id)
            engine = self._engine_for(record.session)
            session = self._validated_session(engine, record.session)
            if session.status != "completed":
                raise DossierNotReady(
                    f"game session {session_id} is still {session.status}"
                )
            if session.dossier_id is not None:
                return self._load_validated_dossier(engine, session)
            attached_session, dossier = self._build_dossier(engine, session)
            try:
                self.store.attach_dossier(record, attached_session, dossier)
            except StoredSessionWriteConflict:
                latest = self._load_record(session_id)
                latest_engine = self._engine_for(latest.session)
                latest_session = self._validated_session(
                    latest_engine,
                    latest.session,
                )
                if latest_session.dossier_id is None:
                    raise SessionIntegrityError(
                        "completed session changed without attaching its dossier"
                    )
                return self._load_validated_dossier(
                    latest_engine,
                    latest_session,
                )
            except (
                StoredDossierIntegrityError,
                StoredSessionIntegrityError,
            ) as exc:
                raise SessionIntegrityError(str(exc)) from exc
            return dossier

    def replay_session(self, session_id: str) -> SessionReplayV1:
        record = self._load_record(session_id)
        engine = self._engine_for(record.session)
        session = self._validated_session(engine, record.session)
        if session.dossier_id is not None:
            self._load_validated_dossier(engine, session)
        commands = _commands_from_session(session)
        replayed = engine.replay(
            session_id=session.session_id,
            user_id=session.user_id,
            started_at=session.started_at,
            commands=commands,
            random_seed=session.random_seed,
        )
        replayed_payload = replayed.model_dump(mode="json")
        replayed_payload["dossier_id"] = session.dossier_id
        replayed = GameSessionV1.model_validate(replayed_payload)
        if replayed.model_dump(mode="json") != session.model_dump(mode="json"):
            raise SessionIntegrityError(
                "persisted session does not exactly match deterministic replay"
            )
        return SessionReplayV1(commands=commands, session=replayed)

    def teacher_summary(self, session_id: str) -> TeacherSessionSummaryV1:
        session = self.get_session(session_id)
        dossier = None
        if session.status == "completed" and session.dossier_id is not None:
            dossier = self.get_dossier(session_id)
        engine = self._engine_for(session)
        return _teacher_summary(engine, session, dossier)

    def apply_fixed_action(
        self,
        session_id: str,
        *,
        client_action_id: str,
        action_id: str,
        expected_revision: int,
        occurred_at: datetime | None = None,
    ) -> AdvanceResultV1:
        """Apply a fixed choice without trusting client-authored turn metadata."""

        with self._lock:
            record = self._load_record(session_id)
            engine = self._engine_for(record.session)
            session = self._validated_session(engine, record.session)
            self._validate_linked_dossier(engine, session)
            existing = _turn_for_client_action(session, client_action_id)
            if existing is not None:
                if (
                    existing.action_source != "fixed"
                    or existing.classified_action_id != action_id
                    or existing.turn_no != expected_revision
                ):
                    raise DuplicateActionConflict(
                        f"client_action_id {client_action_id} was already used"
                    )
                return _existing_advance_result(engine, session, existing)

            engine.resolve_action_id(action_id, action_id)
            label = next(
                item.label
                for item in engine.scenario.action_rules
                if item.action_id == action_id
            )
            event_time = occurred_at or max(_utcnow(), session.updated_at)
            return self.apply_action(
                session_id,
                RuntimeCommandV1(
                    client_action_id=client_action_id,
                    action_id=action_id,
                    raw_input=label,
                    action_source="fixed",
                    classification_confidence=None,
                    expected_revision=expected_revision,
                    occurred_at=event_time,
                ),
            )

    async def apply_free_input(
        self,
        session_id: str,
        *,
        client_action_id: str,
        raw_input: str,
        expected_revision: int,
        occurred_at: datetime | None = None,
    ) -> FreeInputResultV1:
        """Classify outside the state lock, then settle against the same revision."""

        with self._lock:
            record = self._load_record(session_id)
            engine = self._engine_for(record.session)
            session = self._validated_session(engine, record.session)
            self._validate_linked_dossier(engine, session)
            existing = _turn_for_client_action(session, client_action_id)
            if existing is not None:
                return _existing_free_input_result(
                    engine,
                    session,
                    existing,
                    raw_input=raw_input,
                    expected_revision=expected_revision,
                )
            if expected_revision != session.revision:
                raise RevisionConflict(
                    f"expected revision {expected_revision}, current revision is {session.revision}"
                )
            snapshot_actions = engine.available_actions(session)
            snapshot_action_ids = tuple(
                item.action_id for item in snapshot_actions
            )
            classifier = self._get_classifier()

        try:
            unchecked = await classifier.classify(engine, session, raw_input)
        except Exception:
            classification = _classification_unavailable(
                snapshot_action_ids,
                reason_code="provider_unavailable",
            )
        else:
            try:
                classification = ActionClassificationV1.model_validate(
                    unchecked.model_dump(mode="python"),
                    strict=True,
                )
                if (
                    tuple(classification.available_action_ids)
                    != snapshot_action_ids
                ):
                    raise ValueError(
                        "classifier action context does not match the pinned revision"
                    )
            except Exception:
                classification = _classification_unavailable(
                    snapshot_action_ids,
                    reason_code="classifier_context_invalid",
                )

        with self._lock:
            latest_record = self._load_record(session_id)
            latest_engine = self._engine_for(latest_record.session)
            latest_session = self._validated_session(
                latest_engine,
                latest_record.session,
            )
            self._validate_linked_dossier(
                latest_engine,
                latest_session,
            )
            existing = _turn_for_client_action(
                latest_session,
                client_action_id,
            )
            if existing is not None:
                return _existing_free_input_result(
                    latest_engine,
                    latest_session,
                    existing,
                    raw_input=raw_input,
                    expected_revision=expected_revision,
                )
            if latest_session.revision != expected_revision:
                raise RevisionConflict(
                    f"expected revision {expected_revision}, current revision is {latest_session.revision}"
                )
            if classification.kind != "matched":
                return _free_input_no_write_result(
                    classification,
                    latest_engine.available_actions(latest_session),
                )

            event_time = occurred_at or max(
                _utcnow(),
                latest_session.updated_at,
            )
            command = RuntimeCommandV1(
                client_action_id=client_action_id,
                action_id=classification.action_id,
                raw_input=raw_input,
                action_source="free_input",
                classification_confidence=classification.confidence,
                expected_revision=expected_revision,
                occurred_at=event_time,
            )
            try:
                result = self.apply_action(session_id, command)
            except DuplicateActionConflict:
                raced_record = self._load_record(session_id)
                raced_engine = self._engine_for(raced_record.session)
                raced_session = self._validated_session(
                    raced_engine,
                    raced_record.session,
                )
                self._validate_linked_dossier(
                    raced_engine,
                    raced_session,
                )
                raced_turn = _turn_for_client_action(
                    raced_session,
                    client_action_id,
                )
                if raced_turn is None:
                    raise
                return _existing_free_input_result(
                    raced_engine,
                    raced_session,
                    raced_turn,
                    raw_input=raw_input,
                    expected_revision=expected_revision,
                )
            return FreeInputResultV1(
                kind="advanced",
                message=_FREE_INPUT_ADVANCED_MESSAGE,
                available_actions=latest_engine.available_actions(
                    result.session
                ),
                result=result,
            )

    def apply_action(
        self,
        session_id: str,
        command: RuntimeCommandV1,
    ) -> AdvanceResultV1:
        with self._lock:
            record = self._load_record(session_id)
            engine = self._engine_for(record.session)
            session = self._validated_session(engine, record.session)
            if session.dossier_id is not None:
                self._load_validated_dossier(engine, session)
            result = engine.apply_action(session, command)
            if result.session.revision == session.revision:
                return result
            next_session = result.session
            dossier = None
            if next_session.status == "completed":
                next_session, dossier = self._build_dossier(
                    engine,
                    next_session,
                )
                result = AdvanceResultV1.model_validate(
                    {
                        **result.model_dump(mode="json"),
                        "session": next_session.model_dump(mode="json"),
                    }
                )
            try:
                self.store.compare_and_swap(record, next_session, dossier)
            except (
                StoredSessionIntegrityError,
                StoredDossierIntegrityError,
            ) as exc:
                raise SessionIntegrityError(str(exc)) from exc
            except StoredSessionWriteConflict:
                latest = self._load_record(session_id)
                latest_engine = self._engine_for(latest.session)
                latest_session = self._validated_session(
                    latest_engine,
                    latest.session,
                )
                if latest_session.dossier_id is not None:
                    self._load_validated_dossier(
                        latest_engine,
                        latest_session,
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

    def _get_classifier(self) -> ActionClassifierProtocol:
        with self._lock:
            if self._classifier is None:
                from services.ai import ActionClassifierV1

                self._classifier = ActionClassifierV1()
            return self._classifier

    def _validate_linked_dossier(
        self,
        engine: SituationEngineV1,
        session: GameSessionV1,
    ) -> None:
        if session.dossier_id is not None:
            self._load_validated_dossier(engine, session)

    def _engine_for(self, session: GameSessionV1) -> SituationEngineV1:
        try:
            return self.repository.get_exact(
                session.scenario_id,
                session.scenario_version,
                session.scenario_checksum,
                course_id=session.course_id,
                lesson_id=session.lesson_id,
                course_content_version=session.course_content_version,
                course_checksum=session.course_checksum,
            )
        except ScenarioCatalogNotFound as exc:
            raise SessionIntegrityError(
                "the pinned scenario artifact is no longer available"
            ) from exc

    def _load_validated_dossier(
        self,
        engine: SituationEngineV1,
        session: GameSessionV1,
    ) -> DossierV1:
        if session.dossier_id is None:
            raise SessionIntegrityError("session does not reference a dossier")
        try:
            stored = self.store.load_dossier(session.dossier_id)
        except (StoredDossierNotFound, StoredDossierIntegrityError) as exc:
            raise SessionIntegrityError(str(exc)) from exc
        try:
            bundle = RuntimeBundleV1.model_validate(
                {
                    "course": engine.course.model_dump(mode="json"),
                    "scenario": engine.scenario.model_dump(mode="json"),
                    "session": session.model_dump(mode="json"),
                    "dossier": stored.dossier.model_dump(mode="json"),
                }
            )
        except ValidationError as exc:
            raise SessionIntegrityError(
                f"persisted dossier failed runtime bundle validation: {exc}"
            ) from exc
        if bundle.dossier is None:
            raise SessionIntegrityError("persisted runtime bundle lost its dossier")
        expected_session, expected_dossier = self._build_dossier(engine, session)
        if (
            expected_session.model_dump(mode="json")
            != session.model_dump(mode="json")
            or expected_dossier.model_dump(mode="json")
            != bundle.dossier.model_dump(mode="json")
        ):
            raise SessionIntegrityError(
                "persisted dossier does not match deterministic derivation"
            )
        return bundle.dossier

    @staticmethod
    def _build_dossier(
        engine: SituationEngineV1,
        session: GameSessionV1,
    ) -> tuple[GameSessionV1, DossierV1]:
        try:
            return build_final_dossier(engine, session)
        except (DossierGenerationError, ValidationError) as exc:
            raise SessionIntegrityError(str(exc)) from exc

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
    classifier: ActionClassifierProtocol | None = None,
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
        classifier,
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
    loaded: LoadedScenarioV1,
) -> ScenarioSummaryV1:
    engine = loaded.engine
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
        audience=loaded.entry.audience,
        release_id=loaded.release_id,
        release_no=loaded.release_no,
        release_checksum=loaded.release_checksum,
    )


def _runtime_identity(session: GameSessionV1) -> tuple[str, str, int, str, str, int, str]:
    return (
        session.course_id,
        session.lesson_id,
        session.course_content_version,
        str(session.course_checksum),
        session.scenario_id,
        session.scenario_version,
        str(session.scenario_checksum),
    )


def _release_identity(
    loaded: LoadedScenarioV1,
) -> GameSessionReleaseIdentityV1 | None:
    if loaded.entry.audience == "development":
        return None
    return GameSessionReleaseIdentityV1(
        release_id=loaded.release_id,
        release_no=loaded.release_no,
        release_checksum=loaded.release_checksum,
    )


def _commands_from_session(session: GameSessionV1) -> list[RuntimeCommandV1]:
    commands = []
    for turn in session.turns:
        if turn.status != "applied":
            raise SessionIntegrityError(
                "deterministic command replay only supports applied turns"
            )
        commands.append(
            RuntimeCommandV1(
                client_action_id=turn.client_action_id,
                raw_input=turn.raw_input,
                action_id=turn.classified_action_id,
                action_source=turn.action_source,
                classification_confidence=turn.classification_confidence,
                expected_revision=turn.turn_no,
                occurred_at=turn.created_at,
            )
        )
    return commands


def _session_id_for_request(user_id: str, client_request_id: str) -> str:
    digest = hashlib.sha256(
        f"{user_id}\x1f{client_request_id}".encode("utf-8")
    ).hexdigest()[:32]
    return f"session-{digest}"


def _teacher_summary(
    engine: SituationEngineV1,
    session: GameSessionV1,
    dossier: DossierV1 | None,
) -> TeacherSessionSummaryV1:
    ending = next(
        (
            item
            for item in engine.scenario.ending_rules
            if item.ending_id == session.ending_id
        ),
        None,
    )
    key_choices = (
        list(dossier.key_choices)
        if dossier is not None
        else [
            DossierChoiceV1(
                turn_id=turn.turn_id,
                turn_no=turn.turn_no,
                action_id=turn.classified_action_id,
                choice=turn.raw_input,
                consequence=turn.narrative,
            )
            for turn in session.turns
            if turn.status == "applied"
        ]
    )
    initial_state = {
        item.variable_id: item.initial
        for item in engine.scenario.variables
    }
    state_trajectory = (
        list(dossier.state_trajectory)
        if dossier is not None
        else [
            StateSnapshotV1(turn_no=0, state=initial_state),
            *[
                StateSnapshotV1(
                    turn_no=turn.turn_no,
                    state=dict(turn.state_after),
                )
                for turn in session.turns
            ],
        ]
    )
    fact_refs = (
        list(dossier.fact_refs)
        if dossier is not None
        else list(
            dict.fromkeys(
                [
                    fact_id
                    for turn in session.turns
                    for fact_id in turn.fact_refs
                ]
                + (list(ending.fact_refs) if ending is not None else [])
            )
        )
    )
    facts = {item.fact_id: item for item in engine.course.facts}
    source_ref_ids = (
        list(dossier.source_ref_ids)
        if dossier is not None
        else list(
            dict.fromkeys(
                [
                    source_id
                    for fact_id in fact_refs
                    for source_id in facts[fact_id].source_ref_ids
                ]
                + (
                    list(ending.source_ref_ids)
                    if ending is not None
                    else []
                )
            )
        )
    )
    return TeacherSessionSummaryV1(
        session_id=session.session_id,
        user_id=session.user_id,
        course_id=session.course_id,
        lesson_id=session.lesson_id,
        scenario_id=session.scenario_id,
        scenario_version=session.scenario_version,
        scenario_checksum=session.scenario_checksum,
        scenario_title=engine.scenario.title,
        student_role=engine.scenario.student_role,
        objective=engine.scenario.objective,
        status=session.status,
        revision=session.revision,
        current_turn=session.current_turn,
        started_at=session.started_at,
        updated_at=session.updated_at,
        ended_at=session.ended_at,
        ending_id=session.ending_id,
        ending_title=ending.title if ending is not None else "",
        ending_summary=ending.summary if ending is not None else session.summary,
        key_choices=key_choices,
        state_trajectory=state_trajectory,
        fact_refs=fact_refs,
        source_ref_ids=source_ref_ids,
        dossier_id=session.dossier_id,
        dossier_checksum=(dossier.checksum if dossier is not None else None),
    )


def _turn_for_client_action(
    session: GameSessionV1,
    client_action_id: str,
) -> TurnV1 | None:
    return next(
        (
            turn
            for turn in session.turns
            if turn.client_action_id == client_action_id
        ),
        None,
    )


def _existing_advance_result(
    engine: SituationEngineV1,
    session: GameSessionV1,
    turn: TurnV1,
) -> AdvanceResultV1:
    return engine.apply_action(
        session,
        RuntimeCommandV1(
            client_action_id=turn.client_action_id,
            action_id=turn.classified_action_id,
            raw_input=turn.raw_input,
            action_source=turn.action_source,
            classification_confidence=turn.classification_confidence,
            expected_revision=turn.turn_no,
            occurred_at=turn.created_at,
        ),
    )


def _existing_free_input_result(
    engine: SituationEngineV1,
    session: GameSessionV1,
    turn: TurnV1,
    *,
    raw_input: str,
    expected_revision: int,
) -> FreeInputResultV1:
    if (
        turn.action_source != "free_input"
        or turn.raw_input != raw_input
        or turn.turn_no != expected_revision
    ):
        raise DuplicateActionConflict(
            f"client_action_id {turn.client_action_id} was already used"
        )
    result = _existing_advance_result(engine, session, turn)
    return FreeInputResultV1(
        kind="advanced",
        message=_FREE_INPUT_ADVANCED_MESSAGE,
        available_actions=engine.available_actions(result.session),
        result=result,
    )


def _classification_unavailable(
    available_action_ids: tuple[str, ...],
    *,
    reason_code: Literal[
        "classifier_context_invalid",
        "provider_unavailable",
    ],
) -> ActionClassificationV1:
    return ActionClassificationV1.model_validate(
        {
            "kind": "provider_unavailable",
            "source": "fallback",
            "reason_code": reason_code,
            "available_action_ids": list(available_action_ids),
        },
        strict=True,
    )


def _free_input_no_write_result(
    classification: ActionClassificationV1,
    available_actions: tuple[AvailableActionV1, ...],
) -> FreeInputResultV1:
    if classification.kind == "matched":
        raise SessionIntegrityError(
            "matched classification cannot produce a no-write result"
        )
    if classification.kind == "clarification_required":
        message = "我还不能确定你的意思，请换一种说法，或直接选择下方行动。"
    elif classification.kind == "provider_unavailable":
        message = "自由输入暂时不可用，请使用下方固定行动继续。"
    elif classification.reason_code == "prompt_injection":
        message = "这段输入包含无法作为历史行动处理的控制指令。"
    elif classification.reason_code == "anachronism":
        message = "这项行动不属于当前历史情境，请依据当时条件重新选择。"
    elif classification.reason_code == "fact_conflict":
        message = "这项行动与本关卡已审校的史实边界冲突，请重新表述。"
    elif classification.reason_code == "out_of_scope":
        message = "这项行动超出当前关卡范围，请围绕本回合目标重新表述。"
    elif classification.reason_code == "action_unavailable":
        message = "这项行动当前不可执行，请从下方可用行动中选择。"
    elif classification.reason_code == "session_not_active":
        message = "当前关卡已结束，不能再提交新的行动。"
    else:
        message = "这段输入目前不能作为有效行动，请调整后重试。"
    return FreeInputResultV1(
        kind=classification.kind,
        reason_code=classification.reason_code,
        message=message,
        available_actions=available_actions,
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "ActionClassifierProtocol",
    "DossierNotReady",
    "DuplicateStartConflict",
    "FreeInputResultV1",
    "GameRuntimeService",
    "GameSessionNotFound",
    "PublishedScenarioPinRequired",
    "ScenarioReleasePinV1",
    "ScenarioSummaryV1",
    "SessionReplayV1",
    "TeacherSessionSummaryV1",
    "configure_game_runtime",
    "get_game_runtime",
    "shutdown_game_runtime",
]
