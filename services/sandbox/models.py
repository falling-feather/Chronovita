from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class StateVarKind(str, Enum):
    BOOL = "bool"
    SCALE = "scale"


class StateVar(BaseModel):
    key: str
    label: str
    kind: StateVarKind
    bits: int = Field(default=1, ge=1, le=8)
    initial: int = 0
    description: str = ""

    def max_value(self) -> int:
        return (1 << self.bits) - 1


class DagNode(BaseModel):
    node_id: str
    title: str
    narrative: str
    is_terminal: bool = False


class Effect(BaseModel):
    var: str
    op: Literal["set", "inc", "dec"] = "set"
    value: int = 0


class Condition(BaseModel):
    var: str
    op: Literal["eq", "ne", "ge", "le", "gt", "lt"] = "ge"
    value: int = 0


class DagEdge(BaseModel):
    edge_id: str
    from_node: str
    to_node: str
    label: str
    conditions: list[Condition] = []
    effects: list[Effect] = []
    fallback_narrative: str = ""


class Scenario(BaseModel):
    scenario_id: str
    title: str
    period: str
    summary: str
    state_vars: list[StateVar]
    nodes: list[DagNode]
    edges: list[DagEdge]
    start_node: str


class BranchOption(BaseModel):
    edge_id: str
    label: str
    target_node_id: str
    target_title: str
    preview_narrative: str
    state_after: dict[str, int]


class PlaythroughSnapshot(BaseModel):
    playthrough_id: str
    scenario_id: str
    current_node_id: str
    current_node_title: str
    current_narrative: str
    state: dict[str, int]
    state_bits: int
    history: list[str] = []
    is_terminal: bool = False
    task_id: str | None = None
    student_name: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AdvanceRequest(BaseModel):
    edge_id: str
