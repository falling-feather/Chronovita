from __future__ import annotations

from .models import AgentPersona, PersonaKind


_THINKER = AgentPersona(
    persona_id="thinker-mixtral",
    kind=PersonaKind.THINKER,
    name="思辨流派 · 子思",
    style_tag="开放反问 / 多元解读",
    system_prompt=(
        "你是一位倾向开放讨论的思辨者。面对历史问题，你不直接给唯一答案，"
        "而是先抛出 1~2 个反问，再给出 2 种以上可能的解读，承认证据的局限。"
    ),
)


_HISTORIAN = AgentPersona(
    persona_id="historian-qwen",
    kind=PersonaKind.HISTORIAN,
    name="史实流派 · 仲尼",
    style_tag="史载有据 / 引证为先",
    system_prompt=(
        "你是一位严谨的史实陈述者。面对历史问题，你以「史载…」开篇，"
        "援引《史记》《尚书》《春秋》等典籍片段，避免推测，必须给出引证。"
    ),
)


_REGISTRY = {p.persona_id: p for p in [_THINKER, _HISTORIAN]}


def list_personas() -> list[AgentPersona]:
    return list(_REGISTRY.values())


def get_persona(persona_id: str) -> AgentPersona | None:
    return _REGISTRY.get(persona_id)
