from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class JobStage(str, Enum):
    QUEUED = "queued"
    PROMPT_CHAIN = "prompt_chain"
    STORYBOARD = "storyboard"
    CONTROLNET = "controlnet"
    DIFFUSION = "diffusion"
    ANIMATION = "animation"
    TTS = "tts"
    COMPOSE = "compose"
    DONE = "done"
    FAILED = "failed"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PromptStep(BaseModel):
    role: Literal["system", "history_context", "scene", "character", "camera", "style"]
    template: str
    rendered: Optional[str] = None


class PromptChainResult(BaseModel):
    chain_id: str
    steps: list[PromptStep]
    final_prompt: str
    negative_prompt: str = ""


class ControlSignal(BaseModel):
    kind: Literal["pose", "depth", "lineart", "scribble", "reference"]
    weight: float = Field(default=1.0, ge=0.0, le=2.0)
    source_uri: Optional[str] = None
    note: str = ""


class Shot(BaseModel):
    index: int
    duration_sec: float = Field(default=4.0, ge=0.5, le=30.0)
    summary: str
    prompt: PromptChainResult
    control_signals: list[ControlSignal] = []
    voiceover: str = ""


class Storyboard(BaseModel):
    storyboard_id: str
    chapter_id: str
    title: str
    style: str = "工笔淡彩"
    shots: list[Shot]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StoryboardRequest(BaseModel):
    chapter_id: str
    title: str
    history_context: str
    keywords: list[str] = []
    style: str = "工笔淡彩"
    target_shot_count: int = Field(default=4, ge=1, le=12)


class RenderJob(BaseModel):
    job_id: str
    storyboard_id: str
    status: JobStatus = JobStatus.PENDING
    stage: JobStage = JobStage.QUEUED
    progress: float = 0.0
    video_url: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
