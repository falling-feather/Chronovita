from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import AsyncIterator

from .corpus import search_corpus
from .models import (
    Citation,
    DialogueMessage,
    DialogueSession,
    PersonaKind,
    StreamChunk,
)


_SESSIONS: dict[str, DialogueSession] = {}


def new_session(topic: str) -> DialogueSession:
    sess = DialogueSession(session_id=f"sess_{uuid.uuid4().hex[:10]}", topic=topic)
    _SESSIONS[sess.session_id] = sess
    return sess


def get_session(session_id: str) -> DialogueSession | None:
    return _SESSIONS.get(session_id)


def list_sessions() -> list[DialogueSession]:
    return list(_SESSIONS.values())


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


async def stream_answer(session_id: str, question: str) -> AsyncIterator[StreamChunk]:
    sess = _SESSIONS.get(session_id)
    if sess is None:
        return
    sess.messages.append(DialogueMessage(role="user", content=question))
    sess.updated_at = datetime.utcnow()

    citations = search_corpus(question, top_k=3)
    thinker_text = _thinker_compose(question)
    historian_text = _historian_compose(question, citations)

    queue: asyncio.Queue[StreamChunk | None] = asyncio.Queue()

    async def pump(persona: PersonaKind, text: str, cites: list[Citation]) -> None:
        async for ch in _stream_text(persona, text, cites):
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

    sess.messages.append(
        DialogueMessage(role="thinker", content=thinker_text, citations=[])
    )
    sess.messages.append(
        DialogueMessage(role="historian", content=historian_text, citations=citations)
    )
    sess.updated_at = datetime.utcnow()
