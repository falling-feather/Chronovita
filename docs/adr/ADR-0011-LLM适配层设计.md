# ADR-0011 LLM 适配层设计（兼容流式入口）

- 状态：部分落地；AI-001 结构化编排由 ADR-0012 接续
- 日期：2026-05-03（v1 草稿）
- 计划版本：v0.5.x

## 背景

"问 · 双模智者"模块需要接入真实大模型。本 ADR 在 v0.1.0 框架重启时**只保留契约**，具体实现推迟到阶段 4。

## 计划契约

现有兼容实现位于 `services/llm/`，提供流式入口：

```python
async def stream_chat(provider, model, messages, *, api_key=None, base_url=None) -> AsyncIterator[str]
```

- 当前 `provider ∈ {mock, deepseek}`；其他 OpenAI 兼容供应商须另行显式登记
- 返回逐 chunk 文本（不含引证），由调用方拼装
- 任何异常 → 内部捕获 → 回落到 mock 流，对外不抛
- mock 默认可用，离线/无 key 仍能跑课
- 引证仍由后端控制，不交给 LLM 编造

## AI-001 接续边界

- 流式 `stream_chat()` 继续服务 legacy saga/ask，不因 AI-001 破坏兼容调用方。
- 非流式严格 JSON、类型化供应商故障、行动分类、规则后叙事和离线回放遵循 [ADR-0012](ADR-0012-看练问创闭环与史实护栏.md)。
- `CHRONO_LLM_*` 只从环境变量读取；真实 API key 不写入仓库、测试夹具、日志或学生响应。
