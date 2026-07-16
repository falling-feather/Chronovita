"""Authenticated learning progress backed by owner-scoped KV records."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from auth_dependencies import AuthContext, require_student_context
from services import persistence
from services.contracts.v1 import ContractId
from services.courses import get_lesson


router = APIRouter()

_LEGACY_USER = "default"
_NS = "lesson_progress"
_LAYER_ORDER = ("watch", "practice", "ask", "create")
_LAYERS = frozenset(_LAYER_ORDER)
_MAX_WRITE_ATTEMPTS = 8


class ProgressLayers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    watch: bool = False
    practice: bool = False
    ask: bool = False
    create: bool = False


class ProgressItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_id: ContractId
    course_id: str | None = None
    title: str | None = None
    last_layer: str = "watch"
    layers: ProgressLayers = Field(default_factory=ProgressLayers)
    updated_at: str


class StoredProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: ContractId
    lesson_id: ContractId
    last_layer: str = "watch"
    layers: ProgressLayers = Field(default_factory=ProgressLayers)
    updated_at: str


class TouchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_id: ContractId
    layer: str = "watch"
    completed: bool = False


def _owner_id(context: AuthContext) -> str:
    if context.source == "legacy-local-student":
        return _LEGACY_USER
    return context.principal.user_id


def _prefix(owner_id: str) -> str:
    return f"{owner_id}:"


def _key(owner_id: str, lesson_id: str) -> str:
    return f"{_prefix(owner_id)}{lesson_id}"


def _parse_progress(
    raw: object,
    *,
    owner_id: str,
    lesson_id: str,
) -> StoredProgress:
    try:
        record = StoredProgress.model_validate(raw)
    except ValidationError as exc:
        raise _progress_integrity_error() from exc
    if (
        record.user_id != owner_id
        or record.lesson_id != lesson_id
        or record.last_layer not in _LAYERS
    ):
        raise _progress_integrity_error()
    return record


def _enrich(record: StoredProgress) -> ProgressItem:
    item = record.model_dump(exclude={"user_id"})
    lesson = get_lesson(record.lesson_id)
    if lesson:
        item["course_id"] = lesson.course_id
        item["title"] = lesson.title
    return ProgressItem.model_validate(item)


def _list_for_owner(owner_id: str) -> list[StoredProgress]:
    prefix = _prefix(owner_id)
    records = []
    for key, raw in persistence.kv_list_prefix(_NS, prefix):
        records.append(
            _parse_progress(
                raw,
                owner_id=owner_id,
                lesson_id=key[len(prefix) :],
            )
        )
    records.sort(key=lambda item: item.updated_at, reverse=True)
    return records


@router.get("/")
async def index(
    context: AuthContext = Depends(require_student_context),
):
    records = _list_for_owner(_owner_id(context))
    return {
        "module": "我的学习",
        "items": [_enrich(item).model_dump() for item in records[:50]],
    }


@router.get("/progress")
async def list_progress(
    context: AuthContext = Depends(require_student_context),
):
    records = _list_for_owner(_owner_id(context))
    return {"items": [_enrich(item).model_dump() for item in records]}


@router.get("/progress/latest")
async def latest_progress(
    context: AuthContext = Depends(require_student_context),
):
    records = _list_for_owner(_owner_id(context))
    return {"item": _enrich(records[0]).model_dump() if records else None}


@router.get("/progress/{lesson_id}")
async def get_progress(
    lesson_id: ContractId,
    context: AuthContext = Depends(require_student_context),
):
    owner_id = _owner_id(context)
    raw = persistence.kv_get(_NS, _key(owner_id, lesson_id))
    if raw is None:
        return {"item": None}
    record = _parse_progress(raw, owner_id=owner_id, lesson_id=lesson_id)
    return {"item": _enrich(record).model_dump()}


@router.post("/progress/touch")
async def touch_progress(
    req: TouchRequest,
    context: AuthContext = Depends(require_student_context),
):
    if req.layer not in _LAYERS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_progress_layer",
                "message": f"Unsupported learning layer: {req.layer}",
            },
        )
    owner_id = _owner_id(context)
    key = _key(owner_id, req.lesson_id)
    for _ in range(_MAX_WRITE_ATTEMPTS):
        found, raw = persistence.kv_get_with_presence(_NS, key)
        if found:
            current = _parse_progress(
                raw,
                owner_id=owner_id,
                lesson_id=req.lesson_id,
            )
            layers = current.layers.model_dump()
        else:
            layers = {layer: False for layer in _LAYER_ORDER}
        if req.completed:
            layers[req.layer] = True
        next_record = StoredProgress(
            user_id=owner_id,
            lesson_id=req.lesson_id,
            last_layer=req.layer,
            layers=layers,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        if persistence.kv_compare_and_set(
            _NS,
            key,
            raw if found else None,
            next_record.model_dump(mode="json"),
            expected_present=found,
        ):
            return {"ok": True, "item": _enrich(next_record).model_dump()}
    raise HTTPException(
        status_code=409,
        detail={
            "code": "progress_write_conflict",
            "message": "Learning progress changed repeatedly; reload and retry.",
        },
    )


def _progress_integrity_error() -> HTTPException:
    return HTTPException(
        status_code=500,
        detail={
            "code": "progress_integrity_error",
            "message": "Learning progress storage failed integrity validation.",
        },
    )
