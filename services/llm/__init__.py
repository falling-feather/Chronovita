"""LLM adapters for legacy streaming and strict structured completion."""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Iterable

import httpx

from settings import settings

from .adapter import StructuredLLMAdapter, complete_json
from .contracts import (
    LLMFailureCode,
    LLMMessage,
    StructuredCompletion,
    StructuredCompletionInfo,
    StructuredLLMError,
)


Message = dict  # {"role": "system|user|assistant", "content": str}
_STREAM_FALLBACK_NOTICE = "（模型服务暂不可用，已切换离线回答。）\n"


async def _mock_stream(messages: Iterable[Message]) -> AsyncIterator[str]:
    last = ""
    for m in messages:
        if m.get("role") == "user":
            last = str(m.get("content", ""))
    reply = (
        f"（离线 mock 回答）你刚刚问的是：「{last[:60]}」。\n"
        "我现在没有连真实大模型，但我会按教材级口吻给你一个示意性的回答："
        "请关注先秦时期生产工具的演变（青铜→铁器）、政治制度的转型（分封制→郡县制萌芽）"
        "以及思想的多元（百家争鸣）。\n"
        "—— 接通 DeepSeek 后这里会变成真实回答。"
    )
    for ch in reply:
        await asyncio.sleep(0.01)
        yield ch


async def _deepseek_stream(messages: list[Message], *, model: str | None = None) -> AsyncIterator[str]:
    if not settings.deepseek_api_key:
        async for c in _mock_stream(messages):
            yield c
        return

    use_model = model or settings.deepseek_model
    url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "model": use_model,
        "messages": messages,
        "stream": True,
        "temperature": 0.7,
    }
    # DeepSeek V4 思考模式开关（仅对 v4-flash / v4-pro 生效）
    thinking_mode = (settings.deepseek_thinking or "disabled").lower()
    if use_model.startswith("deepseek-v4") and thinking_mode in ("enabled", "disabled"):
        payload["thinking"] = {"type": thinking_mode}
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code >= 400:
                    await resp.aread()
                    yield _STREAM_FALLBACK_NOTICE
                    async for c in _mock_stream(messages):
                        yield c
                    return
                emitted = False
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"].get("content")
                        if delta:
                            emitted = True
                            yield delta
                    except Exception:
                        continue
                if emitted:
                    return
                yield _STREAM_FALLBACK_NOTICE
                async for c in _mock_stream(messages):
                    yield c
    except Exception:  # Legacy callers always receive a stable offline fallback.
        yield _STREAM_FALLBACK_NOTICE
        async for c in _mock_stream(messages):
            yield c


async def stream_chat(
    messages: list[Message],
    *,
    provider: str | None = None,
    model: str | None = None,
) -> AsyncIterator[str]:
    p = (provider or settings.llm_provider or "mock").lower()
    if p == "deepseek":
        async for c in _deepseek_stream(messages, model=model):
            yield c
    else:
        async for c in _mock_stream(messages):
            yield c


def current_provider_label(model: str | None = None) -> str:
    p = (settings.llm_provider or "mock").lower()
    if p == "deepseek" and settings.deepseek_api_key:
        return f"deepseek · {model or settings.deepseek_model}"
    return "mock（离线）"


__all__ = [
    "LLMFailureCode",
    "LLMMessage",
    "StructuredCompletion",
    "StructuredCompletionInfo",
    "StructuredLLMAdapter",
    "StructuredLLMError",
    "complete_json",
    "current_provider_label",
    "stream_chat",
]
