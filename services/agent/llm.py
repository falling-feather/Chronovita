from __future__ import annotations

import json
import os
from typing import AsyncIterator

import httpx


def get_provider() -> str:
    return os.environ.get("CHRONO_LLM_PROVIDER", "mock").strip().lower()


def is_real_llm() -> bool:
    return get_provider() in {"openai", "deepseek", "ollama"}


def _resolve_endpoint() -> tuple[str, str, str | None]:
    provider = get_provider()
    if provider == "openai":
        base = os.environ.get("CHRONO_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        model = os.environ.get("CHRONO_LLM_MODEL", "gpt-4o-mini")
        key = os.environ.get("CHRONO_LLM_API_KEY")
        return f"{base}/chat/completions", model, key
    if provider == "deepseek":
        base = os.environ.get("CHRONO_LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
        model = os.environ.get("CHRONO_LLM_MODEL", "deepseek-chat")
        key = os.environ.get("CHRONO_LLM_API_KEY")
        return f"{base}/chat/completions", model, key
    if provider == "ollama":
        base = os.environ.get("CHRONO_LLM_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        model = os.environ.get("CHRONO_LLM_MODEL", "qwen2.5:7b")
        return f"{base}/v1/chat/completions", model, None
    raise RuntimeError(f"未知 LLM provider: {provider}")


async def stream_chat(system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
    url, model, api_key = _resolve_endpoint()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": True,
        "temperature": 0.7,
    }
    timeout = httpx.Timeout(60.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    line = line[6:]
                if line.strip() == "[DONE]":
                    return
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                if content:
                    yield content
