from __future__ import annotations

from typing import Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from auth_dependencies import (
    AuthContext,
    audit_authorized_action,
    require_permission,
    require_student_context,
)
from services.contracts.v1 import (
    ContractId,
    DossierV1,
    GameSessionV1,
    PlayerInput,
)
from services.game_runtime import (
    AdvanceResultV1,
    ActionUnavailable,
    DuplicateActionConflict,
    GameRuntimeError,
    RevisionConflict,
    ScenarioDefinitionError,
    ScenarioFileError,
    ScenarioIntegrityError,
    SessionIntegrityError,
    SessionTerminalError,
    UnknownAction,
)
from services.game_runtime.catalog import ScenarioCatalogNotFound
from services.game_runtime.service import (
    DossierNotReady,
    DuplicateStartConflict,
    FreeInputResultV1,
    GameSessionNotFound,
    PublishedScenarioPinRequired,
    ScenarioReleasePinV1,
    ScenarioSummaryV1,
    SessionReplayV1,
    TeacherSessionSummaryV1,
    get_game_runtime,
)


router = APIRouter()


class GameStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    scenario_id: ContractId
    client_request_id: ContractId
    release_pin: ScenarioReleasePinV1 | None = None


class GameTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    client_action_id: ContractId
    action_id: ContractId
    expected_revision: int = Field(ge=1)


class GameFreeInputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    client_action_id: ContractId
    raw_input: PlayerInput
    expected_revision: int = Field(ge=1)


class GameScenarioListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[ScenarioSummaryV1]
    session_storage: Literal["sqlite-json"] = "sqlite-json"


class GameStartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario: ScenarioSummaryV1
    session: GameSessionV1
    session_storage: Literal["sqlite-json"] = "sqlite-json"


@router.get("/scenarios", response_model=GameScenarioListResponse)
async def list_game_scenarios() -> GameScenarioListResponse:
    try:
        items = get_game_runtime().list_scenarios()
    except Exception as exc:
        _raise_runtime_error(exc)
    return GameScenarioListResponse(items=list(items))


@router.post("/sessions", response_model=GameStartResponse)
async def start_game_session(
    request: GameStartRequest,
    context: AuthContext = Depends(require_student_context),
) -> GameStartResponse:
    try:
        runtime = get_game_runtime().for_owner(context.principal.user_id)
        scenario, session = runtime.start_session(
            request.scenario_id,
            client_request_id=request.client_request_id,
            release_pin=request.release_pin,
        )
    except Exception as exc:
        _raise_runtime_error(exc)
    return GameStartResponse(scenario=scenario, session=session)


@router.get("/sessions/{session_id}", response_model=GameSessionV1)
async def get_game_session(
    session_id: str,
    context: AuthContext = Depends(require_student_context),
) -> GameSessionV1:
    try:
        runtime = get_game_runtime().for_owner(context.principal.user_id)
        session = runtime.get_session(session_id)
    except Exception as exc:
        _raise_runtime_error(exc)
    return session


@router.get(
    "/sessions/{session_id}/replay",
    response_model=SessionReplayV1,
)
async def replay_game_session(
    session_id: str,
    context: AuthContext = Depends(require_student_context),
) -> SessionReplayV1:
    try:
        runtime = get_game_runtime().for_owner(context.principal.user_id)
        replay = runtime.replay_session(session_id)
    except Exception as exc:
        _raise_runtime_error(exc)
    return replay


@router.get(
    "/sessions/{session_id}/dossier",
    response_model=DossierV1,
)
async def get_game_dossier(
    session_id: str,
    context: AuthContext = Depends(require_student_context),
) -> DossierV1:
    try:
        runtime = get_game_runtime().for_owner(context.principal.user_id)
        dossier = runtime.get_dossier(session_id)
    except Exception as exc:
        _raise_runtime_error(exc)
    return dossier


@router.post(
    "/sessions/{session_id}/dossier",
    response_model=DossierV1,
)
async def ensure_game_dossier(
    session_id: str,
    context: AuthContext = Depends(require_student_context),
) -> DossierV1:
    try:
        runtime = get_game_runtime().for_owner(context.principal.user_id)
        dossier = runtime.ensure_dossier(session_id)
    except Exception as exc:
        _raise_runtime_error(exc)
    return dossier


@router.get(
    "/sessions/{session_id}/summary",
    response_model=TeacherSessionSummaryV1,
)
async def get_teacher_session_summary(
    session_id: str,
    request: Request,
    context: AuthContext = Depends(require_permission("student.summary")),
) -> TeacherSessionSummaryV1:
    try:
        summary = get_game_runtime().teacher_summary(session_id)
    except Exception as exc:
        _raise_runtime_error(exc)
    audit_authorized_action(
        request,
        context,
        permission="student.summary",
        action="student.summary.read",
        resource_type="game_session",
        resource_id=session_id,
    )
    return summary


@router.post("/sessions/{session_id}/turns", response_model=AdvanceResultV1)
async def apply_game_turn(
    session_id: str,
    request: GameTurnRequest,
    context: AuthContext = Depends(require_student_context),
) -> AdvanceResultV1:
    try:
        runtime = get_game_runtime().for_owner(context.principal.user_id)
        result = await runtime.submit_fixed_action(
            session_id,
            client_action_id=request.client_action_id,
            action_id=request.action_id,
            expected_revision=request.expected_revision,
        )
    except Exception as exc:
        _raise_runtime_error(exc)
    return result


@router.post(
    "/sessions/{session_id}/free-input",
    response_model=FreeInputResultV1,
)
async def apply_game_free_input(
    session_id: str,
    request: GameFreeInputRequest,
    context: AuthContext = Depends(require_student_context),
) -> FreeInputResultV1:
    try:
        runtime = get_game_runtime().for_owner(context.principal.user_id)
        result = await runtime.apply_free_input(
            session_id,
            client_action_id=request.client_action_id,
            raw_input=request.raw_input,
            expected_revision=request.expected_revision,
        )
    except Exception as exc:
        _raise_runtime_error(exc)
    return result


def _raise_runtime_error(exc: Exception) -> NoReturn:
    if isinstance(exc, (ScenarioCatalogNotFound, GameSessionNotFound)):
        status = 404
    elif isinstance(
        exc,
        (
            ActionUnavailable,
            DossierNotReady,
            DuplicateStartConflict,
            PublishedScenarioPinRequired,
            DuplicateActionConflict,
            RevisionConflict,
            SessionTerminalError,
        ),
    ):
        status = 409
    elif isinstance(exc, UnknownAction):
        status = 422
    elif isinstance(
        exc,
        (
            ScenarioFileError,
            ScenarioDefinitionError,
            ScenarioIntegrityError,
            SessionIntegrityError,
            RuntimeError,
        ),
    ):
        status = 503
    elif isinstance(exc, GameRuntimeError):
        status = 400
    else:
        raise exc
    code = getattr(exc, "code", "game_runtime_unavailable")
    raise HTTPException(
        status_code=status,
        detail={"code": code, "message": str(exc)},
    ) from exc
