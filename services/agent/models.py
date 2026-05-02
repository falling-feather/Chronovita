from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class PersonaKind(str, Enum):
    THINKER = "thinker"
    HISTORIAN = "historian"


class AgentPersona(BaseModel):
    persona_id: str
    kind: PersonaKind
    name: str
    style_tag: str
    system_prompt: str


class Citation(BaseModel):
    source_id: str
    title: str
    excerpt: str
    relevance: float = Field(ge=0.0, le=1.0)


class DialogueMessage(BaseModel):
    role: Literal["user", "thinker", "historian"]
    content: str
    citations: list[Citation] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DialogueSession(BaseModel):
    session_id: str
    topic: str
    messages: list[DialogueMessage] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class StreamChunk(BaseModel):
    persona: PersonaKind
    delta: str = ""
    done: bool = False
    citations: list[Citation] = []
