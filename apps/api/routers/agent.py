from fastapi import APIRouter, WebSocket
from pydantic import BaseModel

router = APIRouter()


class CreateSessionRequest(BaseModel):
    persona_id: str
    mode: str = "companion"


class MessageRequest(BaseModel):
    content: str


class SwitchRequest(BaseModel):
    persona_id: str
    mode: str


@router.get("/personas")
async def list_personas():
    return {"items": []}


@router.post("/sessions")
async def create_session(payload: CreateSessionRequest):
    return {"session_id": "stub", "persona_id": payload.persona_id, "mode": payload.mode}


@router.post("/sessions/{sid}/message")
async def post_message(sid: str, payload: MessageRequest):
    return {"session_id": sid, "reply": "", "citations": []}


@router.post("/sessions/{sid}/switch")
async def switch_persona(sid: str, payload: SwitchRequest):
    return {"session_id": sid, "persona_id": payload.persona_id, "mode": payload.mode}


@router.websocket("/ws/{sid}")
async def voice_channel(websocket: WebSocket, sid: str):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_bytes()
            await websocket.send_bytes(data)
    except Exception:
        await websocket.close()
