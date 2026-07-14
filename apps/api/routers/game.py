from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, NoReturn

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from settings import settings
from services.contracts.v1 import ContractId, GameSessionV1, PlayerInput
from services.game_runtime import (
    AdvanceResultV1,
    ActionUnavailable,
    DuplicateActionConflict,
    GameRuntimeError,
    RevisionConflict,
    RuntimeCommandV1,
    ScenarioDefinitionError,
    ScenarioFileError,
    ScenarioIntegrityError,
    SessionIntegrityError,
    SessionTerminalError,
    UnknownAction,
)
from services.game_runtime.catalog import ScenarioCatalogNotFound
from services.game_runtime.service import (
    GameSessionNotFound,
    ScenarioSummaryV1,
    get_game_runtime,
)


router = APIRouter()


class GameStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    scenario_id: ContractId


class GameTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    client_action_id: ContractId
    action_id: ContractId
    raw_input: PlayerInput
    expected_revision: int = Field(ge=1)
    action_source: Literal["fixed", "free_input", "fallback"] = "fixed"
    classification_confidence: float | None = Field(default=None, ge=0, le=1)


class GameScenarioListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[ScenarioSummaryV1]
    session_storage: Literal["ephemeral"] = "ephemeral"


class GameStartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario: ScenarioSummaryV1
    session: GameSessionV1
    session_storage: Literal["ephemeral"] = "ephemeral"


@router.get("/scenarios", response_model=GameScenarioListResponse)
async def list_game_scenarios() -> GameScenarioListResponse:
    try:
        items = get_game_runtime().list_scenarios()
    except Exception as exc:
        _raise_runtime_error(exc)
    return GameScenarioListResponse(items=list(items))


@router.post("/sessions", response_model=GameStartResponse)
async def start_game_session(request: GameStartRequest) -> GameStartResponse:
    try:
        scenario, session = get_game_runtime().start_session(
            request.scenario_id,
            user_id=settings.game_user_id,
        )
    except Exception as exc:
        _raise_runtime_error(exc)
    return GameStartResponse(scenario=scenario, session=session)


@router.get("/sessions/{session_id}", response_model=GameSessionV1)
async def get_game_session(session_id: str) -> GameSessionV1:
    try:
        session = get_game_runtime().get_session(session_id)
    except Exception as exc:
        _raise_runtime_error(exc)
    return session


@router.post("/sessions/{session_id}/turns", response_model=AdvanceResultV1)
async def apply_game_turn(
    session_id: str,
    request: GameTurnRequest,
) -> AdvanceResultV1:
    command = RuntimeCommandV1(
        client_action_id=request.client_action_id,
        action_id=request.action_id,
        raw_input=request.raw_input,
        expected_revision=request.expected_revision,
        action_source=request.action_source,
        classification_confidence=request.classification_confidence,
        occurred_at=datetime.now(timezone.utc),
    )
    try:
        result = get_game_runtime().apply_action(session_id, command)
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
