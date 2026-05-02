from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ClassroomTask(BaseModel):
    task_id: str
    title: str
    scenario_id: str
    teacher_notes: str = ""
    preset_state: dict[str, int] = Field(default_factory=dict)
    must_visit_nodes: list[str] = Field(default_factory=list)
    accepted_terminals: list[str] = Field(default_factory=list)
    recommended_path: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CreateClassroomTaskRequest(BaseModel):
    title: str
    scenario_id: str
    teacher_notes: str = ""
    preset_state: dict[str, int] = Field(default_factory=dict)
    must_visit_nodes: list[str] = Field(default_factory=list)
    accepted_terminals: list[str] = Field(default_factory=list)
    recommended_path: list[str] = Field(default_factory=list)


class TaskCheckResult(BaseModel):
    task_id: str
    playthrough_id: str
    is_terminal: bool
    terminal_node_id: Optional[str] = None
    visited_nodes: list[str]
    must_visit_hit: list[str]
    must_visit_miss: list[str]
    terminal_accepted: bool
    recommended_match_ratio: float
    summary: str
