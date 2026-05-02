# ADR-0011 问模块 · LLM 适配层设计

- 状态：已采纳
- 日期：2026-05-03
- 版本：v2.1.0

## 背景

v1.3.0 起，问模块以 mock 流式产出双派对话，已能稳定演示双 Persona / SSE / 引证后置等课堂能力，但所有"思考"都来自硬编码语料；语料覆盖只有 11 条，扩展剧本时（如 v2.0.0 洋务运动）每加一条都要手写文本，难以承载真实课堂的开放式追问。

需要在不破坏既有 mock 演示路径的前提下，给问模块接入真 LLM（OpenAI / DeepSeek / Ollama 本地模型），并保证：

- mock 默认可用，离线/无 key 仍能跑课
- provider 失败自动回退 mock，不让课堂"卡住"
- 引证仍由后端控制，不交给 LLM 编造
- 老师/学生在 UI 能直观看到当前是 mock 还是真模型

## 决策

### 1. 适配层位置

新增 `services/agent/llm.py`，提供单一异步入口：

```python
async def stream_chat(provider, model, messages, *, api_key=None, base_url=None) -> AsyncIterator[str]
```

- `provider ∈ {mock, openai, deepseek, ollama}`
- 返回逐 chunk 文本（不含引证），由调用方拼装
- 任何异常 → 内部捕获 → 回落到 mock 流，对外不抛

### 2. 协议适配

| Provider  | 端点                              | 协议           |
| --------- | --------------------------------- | -------------- |
| openai    | `{base_url}/chat/completions`     | OpenAI SSE     |
| deepseek  | 同上（OpenAI 兼容）               | OpenAI SSE     |
| ollama    | `{base_url}/api/chat`             | NDJSON 流      |
| mock      | —                                 | 内部字符块流   |

OpenAI 兼容路径走 `stream=true`，按 `data: {json}` 解析 `choices[0].delta.content`，遇 `[DONE]` 终止。
Ollama 走每行 JSON 解析 `message.content`，遇 `done=true` 终止。

### 3. 配置入口

`apps/api/settings.py` 新增（CHRONO_ 前缀，对应 .env）：

- `CHRONO_LLM_PROVIDER`（默认 `mock`）
- `CHRONO_LLM_MODEL`
- `CHRONO_LLM_API_KEY`
- `CHRONO_LLM_BASE_URL`

`.env.example` 同步示例，方便老师本地起 ollama 直接跑。

### 4. 编排层改造

`services/agent/dialogue.stream_answer`：

- mock：保留原 `_stream_text` 字符块路径，零行为差异
- 非 mock：两派 Persona 各起一个 task，把 LLM chunk 推入 asyncio.Queue，外层按到达顺序串成 SSE
- 引证：LLM 回答完整生成后，后端再追加 `【引证】...`，**不让 LLM 自己编引证**
- 末尾仍走 `save_session` 持久化

### 5. 状态可见

新增 `GET /api/v1/agent/status` → `{provider, model, base_url, has_api_key}`。
`AgentPage.tsx` 顶部以 AntD Tag 显示：

- mock：灰色「模拟模式」
- 其他：青色「{provider} · {model}」

老师一眼可知当前课堂是否在跑真模型。

## 备选方案

- **A. 直接在 dialogue.py 里 if/else 各 provider**：耦合高，加 provider 要改主流程，弃。
- **B. 引入 LangChain / LlamaIndex**：依赖重，仅为流式 chat 不划算，弃。
- **C. 让 LLM 自己输出引证**：易编造典籍，违背"史料可追溯"原则，弃。

## 影响

- 新增依赖：无（httpx 已在 requirements）
- 兼容性：默认 provider=mock，老用户零感知
- 风险：真 provider 网络抖动 → 已用回退 mock 兜底；引证仍由后端控制，史实安全
- 后续：v2.2+ 可在适配层加 anthropic / 智谱 / 通义 等 provider，无需动 dialogue
