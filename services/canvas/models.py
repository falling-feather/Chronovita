from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class CanvasNodeKind(str, Enum):
    EVENT = "event"
    FIGURE = "figure"
    POLICY = "policy"
    PLACE = "place"
    CONCEPT = "concept"


class CanvasNode(BaseModel):
    node_id: str
    kind: CanvasNodeKind
    label: str = Field(min_length=1, max_length=40)
    detail: str = ""
    period: str = ""
    x: float = 0
    y: float = 0


class CanvasEdge(BaseModel):
    edge_id: str
    source_id: str
    target_id: str
    label: str = ""


class CanvasBoard(BaseModel):
    board_id: str
    title: str
    summary: str = ""
    nodes: list[CanvasNode] = []
    edges: list[CanvasEdge] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CreateBoardRequest(BaseModel):
    title: str = Field(min_length=1, max_length=60)
    summary: str = ""
    seed: bool = False


class UpsertNodeRequest(BaseModel):
    node_id: str | None = None
    kind: CanvasNodeKind
    label: str
    detail: str = ""
    period: str = ""
    x: float = 0
    y: float = 0


class UpsertEdgeRequest(BaseModel):
    edge_id: str | None = None
    source_id: str
    target_id: str
    label: str = ""


class LayoutRequest(BaseModel):
    algorithm: Literal["radial", "layered"] = "layered"


class ExportFormat(str, Enum):
    JSON = "json"
    MARKDOWN = "markdown"
    MERMAID = "mermaid"
