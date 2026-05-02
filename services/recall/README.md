# 看 · 沉浸叙事服务

负责 GenAI 视频生成工作流编排。

## 工作流

文本解析 → 分镜生成 → ControlNet 约束 → Stable Diffusion → AnimateDiff → TTS → 拼接。

## 待实现（v1.1.0）

- Prompt 链
- ControlNet 约束器
- Celery + Redis 异步任务
- 资源落盘策略（本地 / MinIO）
