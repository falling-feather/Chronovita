from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class BoardRequest(BaseModel):
    title: str


class NodeRequest(BaseModel):
    kind: str
    data: dict
    x: float = 0
    y: float = 0


class EdgeRequest(BaseModel):
    source_id: str
    target_id: str
    label: str = ""


@router.get("/boards")
async def list_boards():
    return {"items": []}


@router.post("/boards")
async def create_board(payload: BoardRequest):
    return {"board_id": "stub", "title": payload.title}


@router.get("/boards/{cid}")
async def get_board(cid: str):
    return {"board_id": cid, "nodes": [], "edges": []}


@router.post("/boards/{cid}/nodes")
async def add_node(cid: str, payload: NodeRequest):
    return {"board_id": cid, "node_id": "stub", **payload.model_dump()}


@router.post("/boards/{cid}/edges")
async def add_edge(cid: str, payload: EdgeRequest):
    return {"board_id": cid, "edge_id": "stub", **payload.model_dump()}


@router.get("/boards/{cid}/export")
async def export_board(cid: str, format: str = "json"):
    return {"board_id": cid, "format": format, "url": None}
