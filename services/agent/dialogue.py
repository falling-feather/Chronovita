from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import AsyncIterator

from .corpus import search_corpus
from .llm import is_real_llm, stream_chat
from .models import (
    Citation,
    DialogueMessage,
    DialogueSession,
    PersonaKind,
    StreamChunk,
)
from .personas import get_persona
from services import persistence


_SESSIONS: dict[str, DialogueSession] = {}


def new_session(topic: str) -> DialogueSession:
    sess = DialogueSession(session_id=f"sess_{uuid.uuid4().hex[:10]}", topic=topic)
    _SESSIONS[sess.session_id] = sess
    persistence.save_session(sess)
    return sess


def get_session(session_id: str) -> DialogueSession | None:
    return _SESSIONS.get(session_id)


def list_sessions() -> list[DialogueSession]:
    return list(_SESSIONS.values())


def hydrate_from_db() -> int:
    count = 0
    for raw in persistence.load_all_sessions():
        try:
            sess = DialogueSession.model_validate(raw)
        except Exception:
            continue
        _SESSIONS[sess.session_id] = sess
        count += 1
    return count


def _thinker_compose(question: str) -> str:
    return (
        f"问得好。我们先按下「{question[:18]}」这一断言，回到两个先决问题：\n"
        f"  · 当时的史料叙述者，是否带有立场？\n"
        f"  · 同一事件，不同地区的回响是否相同？\n\n"
        f"由此至少可见两种解读：\n"
        f"  ① 主流叙事侧重正统传承，强调英雄个体的决断；\n"
        f"  ② 边缘视角则更关注被沉默者的代价。\n"
        f"两者并非排他——把它们并置，才能贴近历史的复杂层次。"
    )


def _historian_compose(question: str, citations: list[Citation]) -> str:
    if not citations:
        return (
            "史载之处难觅直证。可循常法，先订时空，再考人物，循其制度推因果。"
            "若问题缺乏典籍佐证，宜暂止断言，留待新出土文献或简帛复核。"
        )
    head = "史载："
    bodies = []
    for c in citations:
        bodies.append(f"{c.title}云：「{c.excerpt}」")
    body = "；".join(bodies)
    return f"{head}{body}。综观以上典籍，关于「{question[:16]}」可作以下平实叙述：诸源互证、择其稳处而陈之。"


async def _stream_text(persona: PersonaKind, text: str, citations: list[Citation]) -> AsyncIterator[StreamChunk]:
    chunk_size = 10
    for i in range(0, len(text), chunk_size):
        yield StreamChunk(persona=persona, delta=text[i : i + chunk_size], done=False)
        await asyncio.sleep(0.05)
    yield StreamChunk(persona=persona, delta="", done=True, citations=citations)


def _persona_system(persona: PersonaKind, citations: list[Citation]) -> str:
    base = get_persona("thinker-mixtral" if persona == PersonaKind.THINKER else "historian-qwen")
    sys = base.system_prompt if base else ""
    if persona == PersonaKind.HISTORIAN and citations:
        cite_block = "\n".join(f"- {c.title}：{c.excerpt}" for c in citations)
        sys = f"{sys}\n\n你可以引用如下原典片段（必须保持原文）：\n{cite_block}"
    return sys


async def _stream_llm(persona: PersonaKind, question: str, citations: list[Citation]) -> AsyncIterator[StreamChunk]:
    sys = _persona_system(persona, citations)
    accumulated: list[str] = []
    try:
        async for piece in stream_chat(sys, question):
            accumulated.append(piece)
            yield StreamChunk(persona=persona, delta=piece, done=False)
    except Exception as exc:
        fallback = f"[LLM 调用失败，降级回 mock：{type(exc).__name__}] "
        yield StreamChunk(persona=persona, delta=fallback, done=False)
        text = (
            _historian_compose(question, citations)
            if persona == PersonaKind.HISTORIAN
            else _thinker_compose(question)
        )
        async for ch in _stream_text(persona, text, citations):
            yield ch
        return
    yield StreamChunk(persona=persona, delta="", done=True, citations=citations)


async def stream_answer(session_id: str, question: str) -> AsyncIterator[StreamChunk]:
    sess = _SESSIONS.get(session_id)
    if sess is None:
        return
    sess.messages.append(DialogueMessage(role="user", content=question))
    sess.updated_at = datetime.utcnow()

    citations = search_corpus(question, top_k=3)
    use_llm = is_real_llm()
    thinker_text = _thinker_compose(question)
    historian_text = _historian_compose(question, citations)

    queue: asyncio.Queue[StreamChunk | None] = asyncio.Queue()
    captured: dict[PersonaKind, list[str]] = {PersonaKind.THINKER: [], PersonaKind.HISTORIAN: []}

    async def pump(persona: PersonaKind, fallback_text: str, cites: list[Citation]) -> None:
        if use_llm:
            iterator = _stream_llm(persona, question, cites)
        else:
            iterator = _stream_text(persona, fallback_text, cites)
        async for ch in iterator:
            if ch.delta:
                captured[persona].append(ch.delta)
            await queue.put(ch)
        await queue.put(None)

    t1 = asyncio.create_task(pump(PersonaKind.THINKER, thinker_text, []))
    t2 = asyncio.create_task(pump(PersonaKind.HISTORIAN, historian_text, citations))

    finished = 0
    while finished < 2:
        item = await queue.get()
        if item is None:
            finished += 1
            continue
        yield item

    await asyncio.gather(t1, t2)

    final_thinker = "".join(captured[PersonaKind.THINKER]) or thinker_text
    final_historian = "".join(captured[PersonaKind.HISTORIAN]) or historian_text

    sess.messages.append(
        DialogueMessage(role="thinker", content=final_thinker, citations=[])
    )
    sess.messages.append(
        DialogueMessage(role="historian", content=final_historian, citations=citations)
    )
    sess.updated_at = datetime.utcnow()
    persistence.save_session(sess)
