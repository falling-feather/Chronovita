from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.agent import (
    AgentPersona,
    AskRequest,
    Citation,
    DialogueSession,
    get_session,
    list_corpus,
    list_personas,
    list_sessions,
    new_session,
    stream_answer,
)
from services.agent.llm import get_provider, is_real_llm

router = APIRouter()


class CreateSessionRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=120)


class LlmStatus(BaseModel):
    provider: str
    is_real: bool
    model: str | None = None


@router.get("/llm-status", response_model=LlmStatus, summary="当前 LLM 模式")
async def llm_status() -> LlmStatus:
    import os
    return LlmStatus(
        provider=get_provider(),
        is_real=is_real_llm(),
        model=os.environ.get("CHRONO_LLM_MODEL"),
    )


@router.get("/personas", response_model=list[AgentPersona], summary="智者列表")
async def fetch_personas() -> list[AgentPersona]:
    return list_personas()


@router.get("/corpus", response_model=list[Citation], summary="语料库")
async def fetch_corpus() -> list[Citation]:
    return list_corpus()


@router.post("/sessions", response_model=DialogueSession, summary="新建对话")
async def create_session(payload: CreateSessionRequest) -> DialogueSession:
    return new_session(payload.topic)


@router.get("/sessions", response_model=list[DialogueSession], summary="对话列表")
async def fetch_sessions() -> list[DialogueSession]:
    return list_sessions()


@router.get("/sessions/{sid}", response_model=DialogueSession, summary="对话详情")
async def fetch_session(sid: str) -> DialogueSession:
    sess = get_session(sid)
    if sess is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return sess


@router.post("/sessions/{sid}/ask", summary="流式提问（SSE）")
async def ask(sid: str, payload: AskRequest) -> StreamingResponse:
    sess = get_session(sid)
    if sess is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    async def event_source():
        async for chunk in stream_answer(sid, payload.question):
            data = json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False)
            yield f"data: {data}\n\n"
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
