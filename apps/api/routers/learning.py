"""我的学习 · S1 学习进度持久化（V0.7.2）

当前为单用户实现：所有进度归属 user_id="default"，多用户接入留待 M5。
存储复用 services.persistence 的 KV：namespace="lesson_progress"，key=f"{user_id}:{lesson_id}"。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import persistence
from services.courses import get_lesson

router = APIRouter()

_DEFAULT_USER = "default"
_NS = "lesson_progress"
_LAYERS = {"watch", "practice", "ask", "create"}


class ProgressLayers(BaseModel):
    watch: bool = False
    practice: bool = False
    ask: bool = False
    create: bool = False


class ProgressItem(BaseModel):
    lesson_id: str
    course_id: Optional[str] = None
    title: Optional[str] = None
    last_layer: str = "watch"
    layers: ProgressLayers = Field(default_factory=ProgressLayers)
    updated_at: str


class TouchRequest(BaseModel):
    lesson_id: str
    layer: str = "watch"
    completed: bool = False


def _key(lesson_id: str) -> str:
    return f"{_DEFAULT_USER}:{lesson_id}"


def _enrich(item: dict) -> ProgressItem:
    lesson = get_lesson(item["lesson_id"])
    if lesson:
        item.setdefault("course_id", lesson.course_id)
        item.setdefault("title", lesson.title)
    return ProgressItem.model_validate(item)


@router.get("/")
async def index():
    raws = list(persistence.kv_list(_NS))
    raws.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    items = [_enrich(dict(r)).model_dump() for r in raws[:50]]
    return {"module": "我的学习", "items": items}


@router.get("/progress")
async def list_progress():
    raws = list(persistence.kv_list(_NS))
    raws.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    return {"items": [_enrich(dict(r)).model_dump() for r in raws]}


@router.get("/progress/latest")
async def latest_progress():
    raws = list(persistence.kv_list(_NS))
    if not raws:
        return {"item": None}
    raws.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    return {"item": _enrich(dict(raws[0])).model_dump()}


@router.get("/progress/{lesson_id}")
async def get_progress(lesson_id: str):
    raw = persistence.kv_get(_NS, _key(lesson_id))
    if raw is None:
        return {"item": None}
    return {"item": _enrich(dict(raw)).model_dump()}


@router.post("/progress/touch")
async def touch_progress(req: TouchRequest):
    if req.layer not in _LAYERS:
        raise HTTPException(status_code=422, detail=f"非法 layer={req.layer}")
    existing = persistence.kv_get(_NS, _key(req.lesson_id)) or {
        "user_id": _DEFAULT_USER,
        "lesson_id": req.lesson_id,
        "layers": {l: False for l in _LAYERS},
    }
    existing.setdefault("layers", {l: False for l in _LAYERS})
    existing["last_layer"] = req.layer
    if req.completed:
        existing["layers"][req.layer] = True
    existing["updated_at"] = datetime.utcnow().isoformat()
    persistence.kv_set(_NS, _key(req.lesson_id), existing)
    return {"ok": True, "item": _enrich(dict(existing)).model_dump()}
