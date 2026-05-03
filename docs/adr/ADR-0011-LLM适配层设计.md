# ADR-0011 LLM 适配层设计（占位 · 阶段 4 落地）

- 状态：占位
- 日期：2026-05-03（v1 草稿）
- 计划版本：v0.5.x

## 背景

"问 · 双模智者"模块需要接入真实大模型。本 ADR 在 v0.1.0 框架重启时**只保留契约**，具体实现推迟到阶段 4。

## 计划契约

新增 `services/agent/llm.py`，提供单一异步入口：

```python
async def stream_chat(provider, model, messages, *, api_key=None, base_url=None) -> AsyncIterator[str]
```

- `provider ∈ {mock, openai, deepseek, ollama}`
- 返回逐 chunk 文本（不含引证），由调用方拼装
- 任何异常 → 内部捕获 → 回落到 mock 流，对外不抛
- mock 默认可用，离线/无 key 仍能跑课
- 引证仍由后端控制，不交给 LLM 编造

## 后续任务

- [ ] 在阶段 4 启动时新建 `services/agent/`
- [ ] 在 `apps/api/.env.example` 中追加 `CHRONO_LLM_*` 配置项
- [ ] UI 顶栏暴露当前 provider（mock / 真实）的小标识
