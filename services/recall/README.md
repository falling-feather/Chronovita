# 看 · 沉浸叙事服务

负责 GenAI 视频生成工作流编排。

## 工作流（v1.1.0 已落地）

文本解析 → Prompt 链 → 分镜编排 → ControlNet 约束 → Stable Diffusion → AnimateDiff → TTS → 拼接。

详见 `docs/adr/ADR-0002-看模块工作流设计.md`。

## 模块

- `models.py`：Pydantic 数据模型（Storyboard / Shot / PromptChainResult / ControlSignal / RenderJob 等）
- `prompt_chain.py`：六段固定角色 prompt 模板与渲染
- `storyboard.py`：起承转合四段叙事编排，启发式判定人物 / 建筑
- `controlnet.py`：按场景特征动态组装 ControlNet 信号
- `pipeline.py`：阶段机任务推进（v1.1.0 内存占位，v1.2.0 接入 Celery）

## 待实现（v1.2.0+）

- Celery + Redis 真异步
- ControlNet 模型按需加载 / 卸载策略
- 资源落盘（MinIO）
- 朝代形制规则库（结构化校验）
- 分镜审校面板（教师人工确认）
