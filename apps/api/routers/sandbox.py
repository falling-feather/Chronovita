from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class CreateSessionRequest(BaseModel):
    dag_id: str


class DecisionRequest(BaseModel):
    node_id: str
    state_vars: dict


@router.post("/sessions")
async def create_session(payload: CreateSessionRequest):
    return {"session_id": "stub", "dag_id": payload.dag_id, "current_node_id": "root"}


@router.get("/sessions/{sid}")
async def get_session(sid: str):
    return {"session_id": sid, "current_node_id": "root", "state_vars": {}, "score": 0}


@router.get("/sessions/{sid}/dag")
async def get_dag(sid: str):
    return {"session_id": sid, "nodes": [], "edges": []}


@router.post("/sessions/{sid}/decision")
async def post_decision(sid: str, payload: DecisionRequest):
    return {"session_id": sid, "next_node_id": "stub", "narrative": "", "rag_score": 0.0}


@router.post("/sessions/{sid}/rewind")
async def rewind(sid: str):
    return {"session_id": sid, "current_node_id": "root"}


@router.get("/sessions/{sid}/timeline")
async def timeline(sid: str):
    return {"session_id": sid, "events": []}
