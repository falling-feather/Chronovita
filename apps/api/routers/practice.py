from __future__ import annotations

import asyncio
import json
import re
from threading import Lock
from typing import Annotated, Any, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from auth_dependencies import AuthContext, require_student_context
from settings import settings
from services import llm, persistence, sandbox, saga
from services.contracts.v1 import ContractId
from services.operations import ConcurrentCallLimiter, TokenBucketLimiter

router = APIRouter()
_PRACTICE_LLM_RATE_LIMITER = TokenBucketLimiter(
    max_attempts=settings.practice_llm_rate_limit_requests,
    window_seconds=settings.practice_llm_rate_limit_window_seconds,
    max_clients=settings.practice_llm_rate_limit_max_users,
)
_PRACTICE_LLM_CONCURRENCY_LIMITER = ConcurrentCallLimiter(
    max_calls=settings.practice_llm_max_concurrent_per_user,
    max_clients=settings.practice_llm_rate_limit_max_users,
)


class _CleanupStreamingResponse(StreamingResponse):
    def __init__(
        self,
        *args,
        cleanup: Callable[[], None],
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._cleanup = cleanup

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            try:
                await _close_async_iterator(self.body_iterator)
            finally:
                self._cleanup()


def _once(*callbacks: Callable[[], None]) -> Callable[[], None]:
    lock = Lock()
    completed = False

    def run() -> None:
        nonlocal completed
        with lock:
            if completed:
                return
            completed = True
        first_error: BaseException | None = None
        for callback in callbacks:
            try:
                callback()
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error

    return run


async def _close_async_iterator(iterator) -> None:
    close = getattr(iterator, "aclose", None)
    if close is not None:
        await close()


# ============= 「练」 互动小说 saga（V0.3.0 新） =============

class SagaStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_id: str = Field(min_length=1, max_length=64)


class SagaActRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(..., min_length=1, max_length=400)


SagaId = Annotated[
    str,
    Path(min_length=12, max_length=12, pattern=r"^[0-9a-f]{12}$"),
]


@router.get("/saga/templates")
async def saga_templates():
    return {"items": saga.list_templates()}


@router.post("/saga/start")
async def saga_start(
    req: SagaStartRequest,
    context: AuthContext = Depends(require_student_context),
):
    try:
        state = saga.start(
            req.lesson_id,
            owner_user_id=context.principal.user_id,
            ttl_seconds=settings.practice_saga_ttl_seconds,
            max_active_per_owner=settings.practice_saga_max_active_per_user,
            max_active_global=settings.practice_saga_max_active_global,
        )
    except saga.SagaCapacityError as exc:
        raise _saga_capacity_error(exc.scope) from exc
    if not state:
        raise HTTPException(status_code=404, detail="该课程暂无互动剧本")
    return state.public()


@router.get("/saga/{saga_id}")
async def saga_get(
    saga_id: SagaId,
    context: AuthContext = Depends(require_student_context),
):
    public_state = saga.get_public(
        saga_id,
        owner_user_id=context.principal.user_id,
        ttl_seconds=settings.practice_saga_ttl_seconds,
    )
    if public_state is None:
        raise HTTPException(status_code=404, detail="saga 不存在或已过期")
    return public_state


@router.post("/saga/{saga_id}/act")
async def saga_act(
    saga_id: SagaId,
    req: SagaActRequest,
    context: AuthContext = Depends(require_student_context),
):
    try:
        state = saga.begin_act(
            saga_id,
            owner_user_id=context.principal.user_id,
            ttl_seconds=settings.practice_saga_ttl_seconds,
        )
    except saga.SagaBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "saga_action_in_progress",
                "message": "This saga already has an action in progress.",
            },
        ) from exc
    except saga.SagaEndedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "saga_already_ended",
                "message": "This saga has already ended.",
            },
        ) from exc
    if state is None:
        raise HTTPException(status_code=404, detail="saga 不存在或已过期")

    try:
        limiter_key = _acquire_llm_lease(context)
    except HTTPException:
        saga.release_act(state)
        raise

    release_resources = _once(
        lambda: saga.release_act(state),
        lambda: _PRACTICE_LLM_CONCURRENCY_LIMITER.release(limiter_key),
    )

    async def gen():
        stream = saga.act_stream(
            state,
            req.action,
            max_response_chars=settings.practice_llm_max_response_chars,
        )
        try:
            async with asyncio.timeout(settings.practice_llm_timeout_seconds):
                async for chunk in stream:
                    yield chunk
        finally:
            try:
                await _close_async_iterator(stream)
            finally:
                release_resources()

    return _CleanupStreamingResponse(
        gen(),
        media_type="text/plain; charset=utf-8",
        cleanup=release_resources,
    )


def _acquire_llm_lease(context: AuthContext) -> str:
    limiter_key = context.principal.user_id
    decision = _PRACTICE_LLM_RATE_LIMITER.consume(limiter_key)
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "practice_llm_rate_limited",
                "message": "Too many AI practice requests. Try again later.",
            },
            headers={
                "Retry-After": str(decision.retry_after_seconds),
                "Cache-Control": "no-store",
            },
        )
    if not _PRACTICE_LLM_CONCURRENCY_LIMITER.acquire(limiter_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "practice_llm_concurrency_limited",
                "message": "Too many AI practice requests are already running.",
            },
            headers={
                "Retry-After": "1",
                "Cache-Control": "no-store",
            },
        )
    return limiter_key


def _saga_capacity_error(scope: str) -> HTTPException:
    message = (
        "This student already has too many retained sagas."
        if scope == "owner"
        else "The saga service is at capacity."
    )
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "code": "saga_capacity_reached",
            "message": message,
        },
        headers={
            "Retry-After": str(min(settings.practice_saga_ttl_seconds, 3600)),
            "Cache-Control": "no-store",
        },
    )


# ============= 「创」 知识画板 LLM 自动生成（V0.3.0 新） =============

class CanvasGenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_id: ContractId
    lesson_title: str = Field(min_length=1, max_length=200)
    abstract: str = Field(min_length=1, max_length=4000)
    keywords: list[
        Annotated[str, Field(min_length=1, max_length=80)]
    ] = Field(default_factory=list, max_length=32)
    seed: list[
        Annotated[str, Field(min_length=1, max_length=100)]
    ] = Field(default_factory=list, max_length=100)


@router.post("/canvas/generate")
async def canvas_generate(
    req: CanvasGenRequest,
    _context: AuthContext = Depends(require_student_context),
):
    sys = (
        "你是一名历史教师，正在为学生构建一张「知识谱系图」。"
        "给定一节课程的标题与摘要，输出 6-9 个核心知识节点与它们之间的关系（边）。\n"
        "严格输出 JSON：{\"nodes\":[{\"id\":\"n1\",\"label\":\"...\",\"category\":\"事件|人物|制度|概念|地点\"}],"
        "\"edges\":[{\"from\":\"n1\",\"to\":\"n2\",\"label\":\"导致|包含|对应|继承|对立\"}]}\n"
        "不要输出任何 JSON 之外的文字。"
    )
    user = (
        f"课程：{req.lesson_title}\n"
        f"摘要：{req.abstract}\n"
        f"关键词：{', '.join(req.keywords) or '（无）'}\n"
        f"已有节点：{', '.join(req.seed) or '（无）'}\n"
        "请生成 6-9 个节点与若干边。"
    )
    limiter_key = _acquire_llm_lease(_context)
    stream = llm.stream_chat([
        {"role": "system", "content": sys},
        {"role": "user", "content": user},
    ])
    try:
        try:
            async with asyncio.timeout(settings.practice_llm_timeout_seconds):
                full = ""
                async for chunk in stream:
                    full += chunk
                    if len(full) > settings.practice_llm_max_response_chars:
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail={
                                "code": "practice_llm_output_too_large",
                                "message": "The AI response exceeded the allowed size.",
                            },
                        )
        except TimeoutError as exc:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail={
                    "code": "practice_llm_timeout",
                    "message": "The AI response exceeded the allowed time.",
                },
            ) from exc
    finally:
        try:
            await _close_async_iterator(stream)
        finally:
            _PRACTICE_LLM_CONCURRENCY_LIMITER.release(limiter_key)

    # 提取 JSON
    match = re.search(r"\{[\s\S]*\}", full)
    try:
        data = json.loads(match.group(0)) if match else {"nodes": [], "edges": []}
    except json.JSONDecodeError:
        data = {"nodes": [], "edges": [], "raw": full[:500]}
    return data


# ============= 「问」 跨时对话 =============

class AskHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persona: Literal["expert", "peer"] = Field(
        default="expert",
        description="expert(专家) | peer(同窗)",
    )
    lesson_id: str | None = Field(default=None, max_length=64)
    lesson_title: str | None = Field(default=None, max_length=200)
    user_message: str = Field(min_length=1, max_length=2000)
    history: list[AskHistoryItem] = Field(default_factory=list, max_length=12)
    # peer 模式下的对谈历史人物（如 "孔子"、"嵇康"）；为空时取课程默认 figure
    peer_character: str | None = Field(default=None, max_length=80)
    # peer 自定义对象时由前端传入的一句简介，用于帮 LLM 锁定人物身份与时代
    peer_intro: str | None = Field(default=None, max_length=500)
    # 课程时期，用于把同窗回答框定在该时期之内
    era: str | None = Field(default=None, max_length=100)


def _system_prompt(
    persona: str,
    *,
    lesson_title: str | None,
    peer_character: str | None,
    peer_intro: str | None,
    era: str | None,
) -> str:
    if persona == "peer":
        # 同窗 = 同时期历史人物，第一人称代入
        name = (peer_character or "").strip() or "孔子"
        era_clause = f"你生活在{era}时期。" if era else ""
        intro_clause = ""
        if peer_intro and peer_intro.strip():
            intro_clause = f"补充身份说明：{peer_intro.strip()}\n"
        return (
            f"你现在扮演中国历史上的真实人物：{name}。{era_clause}\n"
            f"{intro_clause}"
            "请用第一人称（『吾』『余』『我』均可，依人物风格而定），以贴近该人物身份、思想、口吻的方式与用户对话。\n"
            "硬性约束：\n"
            "1. 严格遵守史实——只谈论你所处时代之前已发生的事件、你认识的人、你提出过或可能持有的观点；绝不预言后世（如『后来汉朝』『千年之后』之类一律禁止）。\n"
            "2. 文风带文言色彩但保持可读，必要时附一句白话解释，让现代中学生能理解。\n"
            "3. 当用户问到你不可能知晓的事，要诚实地以人物口吻反问或表示『此事吾未之闻』。\n"
            "4. 单次回答控制在 200 字以内，避免长篇大论。\n"
            f"当前课程上下文：「{lesson_title or '未指定'}」，对话宜围绕该主题展开。"
        )
    # 专家模式：历史学者/教师
    return (
        "你是一位资深的中国历史研究者兼中学历史教师，治学严谨、语言克制。\n"
        "回答规范：\n"
        "1. 优先依据通行的中学/大学历史教材与主流学界共识作答；不确定或学界有争议时明确标注『学界有争议』并简述两派观点。\n"
        "2. 严禁编造史料、人名、年代；若用户提问超出可靠史实范围，应直说『目前尚无可靠史料证实』。\n"
        "3. 鼓励对比同时期不同文明 / 不同思想流派，凸显历史脉络。\n"
        "4. 单次回答控制在 250 字以内，必要时分点；可在末尾用一行『延伸阅读：…』推荐 1 本书或 1 段史料。\n"
        f"当前课程上下文：「{lesson_title or '未指定'}」，请围绕该课程内容作答。"
    )


@router.post("/ask")
async def ask(
    req: AskRequest,
    context: AuthContext = Depends(require_student_context),
):
    messages = [{
        "role": "system",
        "content": _system_prompt(
            req.persona,
            lesson_title=req.lesson_title,
            peer_character=req.peer_character,
            peer_intro=req.peer_intro,
            era=req.era,
        ),
    }]
    for h in req.history[-6:]:
        messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": req.user_message})

    # 「问」追求准确度而非速度 → 走 deepseek-v4-pro
    use_model = settings.deepseek_model_pro
    limiter_key = _acquire_llm_lease(context)
    release_resources = _once(
        lambda: _PRACTICE_LLM_CONCURRENCY_LIMITER.release(limiter_key),
    )

    async def gen():
        emitted_chars = 0
        stream = llm.stream_chat(messages, model=use_model)
        try:
            async with asyncio.timeout(settings.practice_llm_timeout_seconds):
                async for chunk in stream:
                    emitted_chars += len(chunk)
                    if emitted_chars > settings.practice_llm_max_response_chars:
                        raise RuntimeError("practice LLM output exceeded the limit")
                    yield chunk
        finally:
            try:
                await _close_async_iterator(stream)
            finally:
                release_resources()

    return _CleanupStreamingResponse(
        gen(),
        media_type="text/plain; charset=utf-8",
        cleanup=release_resources,
    )


@router.get("/llm/info")
async def llm_info(
    _context: AuthContext = Depends(require_student_context),
):
    return {
        "provider": llm.current_provider_label(),
        "ask_provider": llm.current_provider_label(settings.deepseek_model_pro),
    }


# ============= 「练」 决策沙盘 =============

@router.get("/sandbox")
async def sandbox_list():
    return {"items": sandbox.list_scenarios()}


@router.get("/sandbox/{sid}")
async def sandbox_get(sid: str):
    sc = sandbox.get_scenario(sid)
    if not sc:
        raise HTTPException(status_code=404, detail="剧本不存在")
    start = sc.nodes[sc.start]
    return {
        "scenario": {"id": sc.id, "title": sc.title, "intro": sc.intro},
        "node": start.model_dump(),
        "state": sc.init_state,
    }


class StepRequest(BaseModel):
    node_id: str
    choice: str
    state: dict[str, int]


@router.post("/sandbox/{sid}/step")
async def sandbox_step(sid: str, req: StepRequest):
    result = sandbox.step(sid, req.node_id, req.choice, req.state)
    if not result:
        raise HTTPException(status_code=400, detail="无效的剧本/节点/选择")
    return result


# ============= 「创」 知识画板（持久化） =============

class CanvasGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class CanvasStoredDocument(CanvasGraph):
    schema_version: Literal["canvas/v1"] = "canvas/v1"
    revision: int = Field(ge=1)


class CanvasResponse(CanvasGraph):
    schema_version: Literal["canvas/v1"] = "canvas/v1"
    found: bool
    revision: int = Field(ge=0)


class CanvasSaveRequest(CanvasGraph):
    expected_revision: int = Field(ge=0)


_CANVAS_NS = "canvas"


@router.get("/canvas/{lesson_id}")
async def canvas_get(
    lesson_id: ContractId,
    context: AuthContext = Depends(require_student_context),
) -> CanvasResponse:
    key = _canvas_key(lesson_id, context)
    found, raw = persistence.kv_get_with_presence(_CANVAS_NS, key)
    if not found:
        return CanvasResponse(found=False, revision=0, nodes=[], edges=[])
    stored = _parse_canvas_document(raw)
    return CanvasResponse(
        found=True,
        revision=stored.revision,
        nodes=stored.nodes,
        edges=stored.edges,
    )


@router.put("/canvas/{lesson_id}")
async def canvas_save(
    lesson_id: ContractId,
    payload: CanvasSaveRequest,
    context: AuthContext = Depends(require_student_context),
) -> CanvasResponse:
    key = _canvas_key(lesson_id, context)
    found, raw = persistence.kv_get_with_presence(_CANVAS_NS, key)
    current_revision = 0 if not found else _parse_canvas_document(raw).revision
    if payload.expected_revision != current_revision:
        raise _canvas_revision_conflict()

    stored = CanvasStoredDocument(
        revision=current_revision + 1,
        nodes=payload.nodes,
        edges=payload.edges,
    )
    if not persistence.kv_compare_and_set(
        _CANVAS_NS,
        key,
        raw,
        stored.model_dump(mode="json"),
        expected_present=found,
    ):
        raise _canvas_revision_conflict()
    return CanvasResponse(
        found=True,
        revision=stored.revision,
        nodes=stored.nodes,
        edges=stored.edges,
    )


def _canvas_key(lesson_id: str, context: AuthContext) -> str:
    if context.source == "legacy-local-student":
        return lesson_id
    return f"{context.principal.user_id}:{lesson_id}"


def _parse_canvas_document(raw: Any) -> CanvasStoredDocument:
    try:
        if isinstance(raw, dict) and raw.get("schema_version") == "canvas/v1":
            return CanvasStoredDocument.model_validate(raw)
        legacy = CanvasGraph.model_validate(raw)
        return CanvasStoredDocument(
            revision=1,
            nodes=legacy.nodes,
            edges=legacy.edges,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "canvas_integrity_error",
                "message": "画板存档损坏，已停止读取和写入。",
            },
        ) from exc


def _canvas_revision_conflict() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "canvas_revision_conflict",
            "message": "画板已在其他页面更新，请重新载入后再合并。",
        },
    )
