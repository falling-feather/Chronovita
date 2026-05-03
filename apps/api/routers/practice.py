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
    # peer 模式下的对谈历史人物（如 "孔子"、"嵇康"）；为空时取课程默认 figure
    peer_character: str | None = None
    # 课程时期，用于把同窗回答框定在该时期之内
    era: str | None = None


def _system_prompt(
    persona: str,
    *,
    lesson_title: str | None,
    peer_character: str | None,
    era: str | None,
) -> str:
    if persona == "peer":
        # 同窗 = 同时期历史人物，第一人称代入
        name = (peer_character or "").strip() or "孔子"
        era_clause = f"你生活在{era}时期。" if era else ""
        return (
            f"你现在扮演中国历史上的真实人物：{name}。{era_clause}\n"
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
async def ask(req: AskRequest):
    messages = [{
        "role": "system",
        "content": _system_prompt(
            req.persona,
            lesson_title=req.lesson_title,
            peer_character=req.peer_character,
            era=req.era,
        ),
    }]
    for h in req.history[-6:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])})
    messages.append({"role": "user", "content": req.user_message})

    # 「问」追求准确度而非速度 → 走 deepseek-v4-pro
    from settings import settings as _settings
    use_model = _settings.deepseek_model_pro

    async def gen():
        async for chunk in llm.stream_chat(messages, model=use_model):
            yield chunk

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


@router.get("/llm/info")
async def llm_info():
    from settings import settings as _settings
    return {
        "provider": llm.current_provider_label(),
        "ask_provider": llm.current_provider_label(_settings.deepseek_model_pro),
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
