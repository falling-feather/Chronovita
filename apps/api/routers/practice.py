from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services import llm, persistence, sandbox, saga

router = APIRouter()


# ============= 「练」 互动小说 saga（V0.3.0 新） =============

class SagaStartRequest(BaseModel):
    lesson_id: str


class SagaActRequest(BaseModel):
    action: str = Field(..., min_length=1, max_length=400)


@router.get("/saga/templates")
async def saga_templates():
    return {"items": saga.list_templates()}


@router.post("/saga/start")
async def saga_start(req: SagaStartRequest):
    state = saga.start(req.lesson_id)
    if not state:
        raise HTTPException(status_code=404, detail="该课程暂无互动剧本")
    return state.public()


@router.get("/saga/{saga_id}")
async def saga_get(saga_id: str):
    state = saga.get(saga_id)
    if not state:
        raise HTTPException(status_code=404, detail="saga 不存在或已过期")
    return state.public()


@router.post("/saga/{saga_id}/act")
async def saga_act(saga_id: str, req: SagaActRequest):
    state = saga.get(saga_id)
    if not state:
        raise HTTPException(status_code=404, detail="saga 不存在或已过期")

    async def gen():
        async for chunk in saga.act_stream(saga_id, req.action):
            yield chunk

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


# ============= 「创」 知识画板 LLM 自动生成（V0.3.0 新） =============

class CanvasGenRequest(BaseModel):
    lesson_id: str
    lesson_title: str
    abstract: str
    keywords: list[str] = []
    seed: list[str] = []  # 已有节点 label


@router.post("/canvas/generate")
async def canvas_generate(req: CanvasGenRequest):
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
    full = ""
    async for c in llm.stream_chat([{"role": "system", "content": sys}, {"role": "user", "content": user}]):
        full += c
    # 提取 JSON
    import json as _json
    import re as _re
    m = _re.search(r"\{[\s\S]*\}", full)
    try:
        data = _json.loads(m.group(0)) if m else {"nodes": [], "edges": []}
    except Exception:
        data = {"nodes": [], "edges": [], "raw": full[:500]}
    return data


# ============= 「问」 跨时对话 =============

class AskRequest(BaseModel):
    persona: str = Field(default="expert", description="expert(专家) | peer(同窗)")
    lesson_id: str | None = None
    lesson_title: str | None = None
    user_message: str
    history: list[dict] = []


def _system_prompt(persona: str, lesson_title: str | None) -> str:
    base_expert = (
        "你是一位中学历史教师，性格温和，讲解严谨。"
        "回答时尽量贴近教材级别的表述，避免编造史料；不确定时直说「学界尚有争议」。"
        "回答控制在 200 字以内，必要时分点。"
    )
    base_peer = (
        "你是一位与用户同班的初中同学，对历史很有兴趣，喜欢用生活化的比喻聊历史。"
        "回答简短活泼，不超过 150 字。"
    )
    sys = base_expert if persona == "expert" else base_peer
    if lesson_title:
        sys += f"\n当前课程上下文：「{lesson_title}」。优先围绕该课程内容作答。"
    return sys


@router.post("/ask")
async def ask(req: AskRequest):
    messages = [{"role": "system", "content": _system_prompt(req.persona, req.lesson_title)}]
    for h in req.history[-6:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])})
    messages.append({"role": "user", "content": req.user_message})

    async def gen():
        async for chunk in llm.stream_chat(messages):
            yield chunk

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


@router.get("/llm/info")
async def llm_info():
    return {"provider": llm.current_provider_label()}


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

class CanvasPayload(BaseModel):
    nodes: list[dict]
    edges: list[dict]


_CANVAS_NS = "canvas"


@router.get("/canvas/{lesson_id}")
async def canvas_get(lesson_id: str) -> Any:
    data = persistence.kv_get(_CANVAS_NS, lesson_id)
    return data or {"nodes": [], "edges": []}


@router.put("/canvas/{lesson_id}")
async def canvas_save(lesson_id: str, payload: CanvasPayload):
    persistence.kv_set(_CANVAS_NS, lesson_id, payload.model_dump())
    return {"ok": True}
