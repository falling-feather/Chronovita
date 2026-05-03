"""LLM 适配层 · v0.2.0

提供统一的异步流式入口，支持 DeepSeek（OpenAI 兼容）与 mock。
按 ADR-0011 落地：异常一律回落到 mock，对外不抛。
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Iterable

import httpx

from settings import settings


Message = dict  # {"role": "system|user|assistant", "content": str}


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


async def _deepseek_stream(messages: list[Message]) -> AsyncIterator[str]:
    if not settings.deepseek_api_key:
        async for c in _mock_stream(messages):
            yield c
        return

    url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "model": settings.deepseek_model,
        "messages": messages,
        "stream": True,
        "temperature": 0.7,
    }
    # DeepSeek V4 思考模式开关（仅对 v4-flash / v4-pro 生效）
    thinking_mode = (settings.deepseek_thinking or "disabled").lower()
    if settings.deepseek_model.startswith("deepseek-v4") and thinking_mode in ("enabled", "disabled"):
        payload["thinking"] = {"type": thinking_mode}
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    yield f"\n[LLM 错误 {resp.status_code}] {body.decode('utf-8', 'replace')[:200]}"
                    return
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
                            yield delta
                    except Exception:
                        continue
    except Exception as e:  # 网络/超时 → 回落 mock
        yield f"\n[LLM 异常，已回落 mock] {type(e).__name__}: {e}\n"
        async for c in _mock_stream(messages):
            yield c


async def stream_chat(messages: list[Message], *, provider: str | None = None) -> AsyncIterator[str]:
    p = (provider or settings.llm_provider or "mock").lower()
    if p == "deepseek":
        async for c in _deepseek_stream(messages):
            yield c
    else:
        async for c in _mock_stream(messages):
            yield c


def current_provider_label() -> str:
    p = (settings.llm_provider or "mock").lower()
    if p == "deepseek" and settings.deepseek_api_key:
        return f"deepseek · {settings.deepseek_model}"
    return "mock（离线）"
