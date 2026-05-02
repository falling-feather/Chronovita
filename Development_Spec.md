# Chronovita 开发文档 · Development Specification

> 本文是 Chronovita 项目最权威、最详尽的工程级开发说明。所有研发活动以本文为单一信源（Single Source of Truth），任何与本文冲突的实现均视为缺陷。

---

## 目录

- 1. 文档分级结构
- 2. 系统总体架构
- 3. 业务模块详解
- 4. 数据模型设计
- 5. 前后端接口契约
- 6. 核心待实现功能模块
- 7. GenAI 工作流与算法设计
- 8. 短期项目研发规划
- 9. 编码与提交规范
- 10. 测试与质量保证
- 11. 安全与合规

---

## 1. 文档分级结构

| 层级 | 文档 | 受众 | 更新频率 |
| --- | --- | --- | --- |
| 顶层 | [README.md](README.md) | 所有人 | 按版本 |
| 顶层 | [Roadmap.md](Roadmap.md) | 项目管理 / 教师 / 投资方 | 每月 |
| 顶层 | Development_Spec.md（本文） | 全体研发 | 每次中版本递增 |
| 总规划 | [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) | 全体研发 | 每次大决策 |
| 决策记录 | docs/adr/ADR-XXXX.md | 架构师 | 每次架构决策 |
| 接口契约 | apps/api/openapi.yaml（自动生成） | 前后端联调 | 每次接口变更 |
| 数据迁移 | apps/api/alembic/versions/ | 后端 / DBA | 每次模型变更 |

## 2. 系统总体架构

### 2.1 部署拓扑

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────────┐
│   浏览器    │ <-> │  Nginx 反代 │ <-> │  apps/web (静态)    │
│  React SPA  │     └─────────────┘     └─────────────────────┘
└─────────────┘             │
        │                   v
        │           ┌──────────────────┐    ┌──────────────────┐
        └---WS---->│   apps/api       │<-> │  Postgres 主库   │
                   │   FastAPI        │    └──────────────────┘
                   │                  │    ┌──────────────────┐
                   │                  │<-> │  Redis 缓存/队列 │
                   │                  │    └──────────────────┘
                   │                  │    ┌──────────────────┐
                   │                  │<-> │  Chroma 向量库   │
                   └──────────────────┘    └──────────────────┘
                            │
            ┌───────────────┼─────────────────┐
            v               v                 v
   ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
   │ services/    │ │ services/    │ │ services/canvas  │
   │ recall(GenAI)│ │ sandbox(DAG) │ │ services/agent   │
   └──────────────┘ └──────────────┘ └──────────────────┘
```

### 2.2 技术栈选型

| 层 | 选型 | 理由 |
| --- | --- | --- |
| 前端框架 | React 18 + Vite 5 + TypeScript 5 | 生态成熟、HMR 快、类型安全 |
| 前端 UI | Ant Design 5 + 中式 token 定制 | 加速 MVP，保留视觉自由度 |
| 前端状态 | Zustand | 轻量、无样板 |
| 前端路由 | React Router 6 | 与 Vite 配合最佳 |
| 前端字体 | 思源宋体 / 霞鹜文楷 | 中式古典调性 |
| 后端框架 | FastAPI 0.115+ | 异步、自带 OpenAPI、Pydantic v2 |
| ORM | SQLAlchemy 2.0 + Alembic | 业界标准，迁移可控 |
| 数据校验 | Pydantic v2 | 与 FastAPI 原生集成 |
| 关系库 | PostgreSQL 16 | JSONB 支持，与历史叙事数据契合 |
| 缓存与队列 | Redis 7 + Celery | 异步视频生成任务 |
| 向量库 | Chroma（短期） → Milvus（中期） | 轻量起步，后续切换 |
| 容器 | Docker Compose（开发）+ K8s（远期） | 渐进式部署 |
| Python 版本 | 3.12（强制） | 规避 3.14 与 pydantic-core/orjson Rust 编译问题 |

### 2.3 服务划分

| 服务 | 职责 | 主要依赖 |
| --- | --- | --- |
| `apps/api` | HTTP/WS 入口、鉴权、路由分发 | FastAPI |
| `services/recall` | 看 · GenAI 视频生成工作流编排 | Celery, Stable Diffusion, AnimateDiff, TTS |
| `services/sandbox` | 练 · DAG 因果推演引擎 | NetworkX, 自研状压 DP |
| `services/agent` | 问 · 双模态智能体 + RAG | Chroma, LangChain（可选）, ASR/TTS |
| `services/canvas` | 创 · 知识谱系画布数据服务 | SQLAlchemy |

## 3. 业务模块详解

### 3.1 看 · 沉浸式叙事生成

工作流：

```
课程章节关键词
  ↓ 历史文本解析（LLM + 规则）
分镜脚本（JSON）
  ↓ 关键帧 Prompt 构造（Prompt 链）
ControlNet 约束（服饰/建筑/器物风格）
  ↓ Stable Diffusion 出图
关键帧序列
  ↓ AnimateDiff 插帧
动态片段
  ↓ TTS 声线克隆 + BGM
最终微视频（mp4）
```

输出：每章节 60–120 秒微视频，分辨率 1280x720，码率 ≤ 2 Mbps。

### 3.2 练 · 沙盘推演

数据结构：

- DAG 节点：历史关键节点（事件/抉择点），含 `state_vars`（核心参量字典，如劳动力、地形、粮仓）。
- DAG 边：因果转移，含触发条件 `condition` 与转移函数 `transition`。
- 状态压缩：核心参量取值集合编码为 bitmask，`dp[bitmask] = 当前最优后续历史链`。
- LLM 仅在转移函数边缘负责文本生成，逻辑骨架由代码保证可重放。
- RAG 校验：每次状态转移生成的叙事先入向量库检索权威史料，相似度 < 阈值则回退至预置兜底剧本。

首发剧本：「大禹治水」，参量包含劳动力 ∈ {寡, 中, 众}、地形 ∈ {高, 中, 低}、治水策略 ∈ {堵, 疏, 混}。

### 3.3 问 · 双模态智能体

- 同伴（Companion）模式：扮演同时代历史人物，使用方言化口语、降低认知门槛。
- 专家（Expert）模式：扮演考古/史学专家，使用学术语言、补充文献出处。
- 双 Persona 通过系统提示模板与温度参数差异化实现。
- 防幻觉三层：
  1. RAG 召回（top-k=8）+ rerank（cross-encoder）
  2. 规则正则与黑名单过滤（朝代年份、人物关系等结构化校验）
  3. 轻量级审核模型二次确认（关键事实绑定到知识库 ID）
- 语音通道：浏览器端 WebRTC → 服务端 ASR（Whisper）→ LLM → TTS → WebSocket 推流。

### 3.4 创 · 知识谱系

- 复用团队既有「理科实验室互动网站」的节点渲染引擎，前端以 ReactFlow 包装。
- 学习卡片来源：四模块交互行为日志聚合后由 LLM 抽取要点。
- 自动布局：基于力导向 + 时间轴双视图。
- 导出：PNG / JSON / Markdown。
- 行为数据反哺：路径长度、决策正确率、问答深度入参用于教学评估模型。

## 4. 数据模型设计

> Pydantic v2 + SQLAlchemy 2.0；表名小写下划线；主键统一 UUIDv7。

### 4.1 通用

- `users(id, name, role[student|teacher|admin], school, created_at)`
- `courses(id, title, dynasty, grade_level, syllabus_json)`
- `chapters(id, course_id, ord, title, summary, keywords)`

### 4.2 看

- `recall_jobs(id, chapter_id, status, prompt_chain_json, controlnet_config_json, video_url, error)`
- `recall_assets(id, job_id, kind[keyframe|clip|audio], url, meta_json)`

### 4.3 练

- `sandbox_dags(id, chapter_id, name, version, graph_json)`
- `sandbox_sessions(id, user_id, dag_id, current_node_id, state_vars_json, score)`
- `sandbox_decisions(id, session_id, node_id, choice_json, generated_narrative, rag_score, created_at)`

### 4.4 问

- `agent_personas(id, kind[companion|expert], name, era, system_prompt, voice_model)`
- `agent_sessions(id, user_id, persona_id, started_at)`
- `agent_messages(id, session_id, role[user|assistant], content, audio_url, citations_json, created_at)`

### 4.5 创

- `canvas_boards(id, user_id, title, layout_json, updated_at)`
- `canvas_nodes(id, board_id, kind[card|note|media], data_json, x, y)`
- `canvas_edges(id, board_id, source_id, target_id, label)`

### 4.6 评价

- `eval_metrics(id, user_id, course_id, dim[participation|mastery|satisfaction], value, captured_at)`

## 5. 前后端接口契约

> 全部接口 base path：`/api/v1`。响应统一信封：`{ "code": 0, "data": ..., "message": "" }`。错误使用标准 HTTP 状态码 + `code` 子码。

### 5.1 通用

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/auth/login` | 账号登录，返回 JWT |
| GET | `/users/me` | 当前用户信息 |
| GET | `/courses` | 课程列表 |
| GET | `/courses/{id}/chapters` | 章节列表 |

### 5.2 看 · recall

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/recall/storyboard` | 文本 → 分镜脚本 |
| POST | `/recall/render` | 分镜 → 提交渲染任务 |
| GET | `/recall/jobs/{id}` | 渲染任务状态与产物 |
| GET | `/recall/assets/{id}` | 单一资源元信息 |

### 5.3 练 · sandbox

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/sandbox/sessions` | 开启沙盘会话（指定 DAG） |
| GET | `/sandbox/sessions/{sid}` | 会话当前状态 |
| GET | `/sandbox/sessions/{sid}/dag` | 当前 DAG 可视化数据 |
| POST | `/sandbox/sessions/{sid}/decision` | 学生输入决策变量 |
| POST | `/sandbox/sessions/{sid}/rewind` | 回到上一节点 |
| GET | `/sandbox/sessions/{sid}/timeline` | 推演时间轴回放 |

### 5.4 问 · agent

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/agent/personas` | 可用 persona 列表（按朝代/角色筛选） |
| POST | `/agent/sessions` | 开启对话（mode=companion\|expert） |
| POST | `/agent/sessions/{sid}/message` | 文本消息 |
| WS | `/ws/agent/{sid}` | 实时语音通道（双向） |
| POST | `/agent/sessions/{sid}/switch` | 切换 persona |

### 5.5 创 · canvas

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/canvas/boards` | 我的画布列表 |
| POST | `/canvas/boards` | 新建画布 |
| GET | `/canvas/boards/{cid}` | 画布详情 |
| POST | `/canvas/boards/{cid}/nodes` | 新增节点 |
| PATCH | `/canvas/boards/{cid}/nodes/{nid}` | 更新节点 |
| POST | `/canvas/boards/{cid}/edges` | 新增连线 |
| GET | `/canvas/boards/{cid}/export` | 导出（query: format=png\|json\|md） |

### 5.6 评价

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/eval/users/{uid}/summary` | 学生综合评估 |
| GET | `/eval/courses/{cid}/dashboard` | 教师仪表盘 |

## 6. 核心待实现功能模块

| 序号 | 模块 | 优先级 | 负责服务 | 预计版本 |
| --- | --- | --- | --- | --- |
| F-01 | 文本 → 分镜 Prompt 链 | P0 | recall | v1.1.0 |
| F-02 | ControlNet 约束器（服饰/建筑/器物） | P0 | recall | v1.1.0 |
| F-03 | AnimateDiff 插帧与拼接 | P0 | recall | v1.1.0 |
| F-04 | 声线克隆 TTS | P1 | recall | v1.1.0 |
| F-05 | DAG 数据模型与图编辑器 | P0 | sandbox | v1.2.0 |
| F-06 | 状态压缩 DP 推演内核 | P0 | sandbox | v1.2.0 |
| F-07 | LLM 转移函数生成器 | P0 | sandbox | v1.2.0 |
| F-08 | RAG 史实校验与兜底 | P0 | sandbox | v1.2.0 |
| F-09 | 双 Persona 系统提示库 | P0 | agent | v1.3.0 |
| F-10 | 防幻觉三层管线 | P0 | agent | v1.3.0 |
| F-11 | 实时语音 WebSocket 通道 | P1 | agent | v1.3.0 |
| F-12 | 知识谱系节点渲染引擎迁移 | P0 | canvas | v1.4.0 |
| F-13 | 画布自动布局算法 | P1 | canvas | v1.4.0 |
| F-14 | 量化教学评估模型 v1 | P1 | api | v1.5.0 |

## 7. GenAI 工作流与算法设计

### 7.1 看 · Prompt 链

```
[章节关键词] → [历史背景检索] → [分镜大纲生成] → [镜头细化 Prompt]
                                                    ↓
                                         [ControlNet 风格约束]
                                                    ↓
                                              [SD 关键帧]
                                                    ↓
                                          [AnimateDiff 插帧]
                                                    ↓
                                          [TTS + BGM 合成]
```

### 7.2 练 · DAG 状压 DP

```python
# 伪代码（实际实现不写注释）
state_bits = encode(state_vars)
if (node_id, state_bits) in cache:
    return cache[(node_id, state_bits)]
candidates = []
for edge in dag.out_edges(node_id):
    if edge.condition(state_vars):
        next_state = edge.transition(state_vars)
        narrative = llm.generate(edge.template, next_state)
        if rag.validate(narrative).score < THRESHOLD:
            narrative = edge.fallback_narrative
        candidates.append((edge, next_state, narrative))
cache[(node_id, state_bits)] = candidates
return candidates
```

### 7.3 问 · 防幻觉三层

```
用户问句
  ↓
RAG 召回（Chroma top-k=8） + Rerank（bge-reranker）
  ↓
LLM 生成（system prompt 绑定 persona）
  ↓
规则过滤：朝代年份正则、人物关系黑名单
  ↓
轻量审核模型：判定关键事实是否落在知识库 ID 集合内
  ↓
返回（带引用 ID）
```

### 7.4 创 · 自动布局

- 力导向（D3-force）+ 时间轴对齐双视图。
- 用户拖拽优先级最高，算法在剩余自由度内重排。

## 8. 短期项目研发规划

| 周次 | 任务 | 验收标准 |
| --- | --- | --- |
| W1（2026-05-04 ~ 05-10） | 仓库骨架、文档、设计稿占位 | v1.0.0 提交、CI 跑通 |
| W2 ~ W4 | 看模块 Prompt 链、ControlNet 接入 | 单章节可生成 60s 微视频 |
| W5 ~ W6 | 练模块 DAG 编辑器、首发「大禹治水」 | 学生可完成一次完整推演 |
| W7 ~ W8 | 问模块双 Persona、RAG 三层 | 关键事实零幻觉抽样验证 |
| W9 ~ W10 | 创模块画布迁移、自动布局 | 学生可生成并导出谱系图 |
| W11 ~ W12 | 全链路联调、教师试用 | E2E 无阻塞、教师认可度 ≥ 80% |

## 9. 编码与提交规范

### 9.1 代码风格

- **不写注释**：代码自解释优先；命名表达意图；复杂逻辑拆函数。
- 前端遵循 ESLint + Prettier 默认；后端遵循 Ruff + Black 默认。
- 全部 UI 文案使用纯中文，禁止中英文混排。

### 9.2 Git 提交

- 提交信息：`V{大版本}.{中版本}.{小版本} 中文提交信息`（V 大写、无短横线，三段位完整，不省略）
  - 示例：`V1.1.0 看模块 Prompt 链与 ControlNet 工作流落地`
- 微小修复合入下一次正式提交，不单独成行
- 中版本递增时同步执行分支合并管理（整理/合并相关分支后再入主干）
- 历史整理前先建备份分支，使用 `git push --force-with-lease`
- 中文提交信息一律 `git commit -F message.txt`（UTF-8 无 BOM），避免 PowerShell 管道编码丢失

### 9.3 分支模型

- `main`：主干，仅中/大版本提交
- `feature/<模块>-<简述>`：功能分支，完成后合并并清理
- `release/<vX.Y.Z>`：发布前冻结分支
- `hotfix/<vX.Y.Z>`：紧急修复

## 10. 测试与质量保证

| 层 | 工具 | 覆盖目标 |
| --- | --- | --- |
| 前端单测 | Vitest + Testing Library | 关键组件、Hooks |
| 前端 E2E | Playwright | 看-练-问-创核心流程 |
| 后端单测 | pytest + pytest-asyncio | 服务层、算法层 |
| 后端集成 | pytest + httpx | 全部 API 契约 |
| 算法基准 | pytest-benchmark | 状压 DP 推演耗时 |
| 史实校验 | 自研评测集 | 1000 条历史问答的 RAG 命中率 |

## 11. 安全与合规

- OWASP Top 10：参数化查询（SQLAlchemy）、CSRF token、XSS 转义、JWT 短时效 + Refresh
- LLM 输入过滤：禁止越狱 Prompt 注入到 system prompt
- 教育数据：学生未成年信息脱敏存储，遵循《个人信息保护法》
- 文化合规：历史叙事内容禁止偏离主流史观；敏感朝代过渡（如近现代）由人工审稿

## 12. 版本里程碑

### v1.1.0（2026-05-03）看模块工作流编排骨架

落地内容：

- `services/recall/`：Prompt 链、分镜编排、ControlNet 信号编排、阶段机任务推进四模块
- `apps/api/routers/recall.py`：分镜生成 / 分镜查询 / 提交渲染 / 任务列表 / 任务详情 五端点
- `apps/web/src/pages/RecallPage.tsx`：分镜表单、分镜预览、任务列表轮询（2s 间隔）
- `docs/adr/ADR-0002-看模块工作流设计.md`：决策记录

阶段机推进流程：`queued → prompt_chain → storyboard → controlnet → diffusion → animation → tts → compose → done`，v1.1.0 为内存占位（每次查询前进一阶），v1.2.0 替换为 Celery + Redis 真异步。

Prompt 链六段固定角色：`system / history_context / scene / character / camera / style`，可分段编辑、可审计。

ControlNet 信号按场景特征动态组装：人物 → pose；建筑 → lineart + depth；参考图 → reference；兜底 → scribble。

### v1.1.1（2026-05-03）看模块运行时收敛

落地内容：

- 修复 AntD 5 静态 `message` API 在动态主题上下文下的告警：根布局用 `<App>` 包裹，组件内通过 `App.useApp()` 获取 `message` 实例
- 移除 `Card` 组件已废弃的 `bordered` 属性
- 启发式扫描扩展 `scan_text` 拼入 `keywords`，"堤坝/河道"等地理关键词可正确触发 lineart + depth 信号
- 端到端浏览器实测打通：分镜生成 → 4 镜显示 + ControlNet tag → 提交渲染 → 阶段机轮询推进

### v1.2.0（2026-05-03）练模块 DAG 与状压 DP 推演雏形

落地内容：

- `services/sandbox/`：`models.py`（StateVar / DagNode / DagEdge / Condition / Effect / Scenario / PlaythroughSnapshot）+ `engine.py`（位编码、记忆化分支、推演前进）+ `scenarios.py`（首发剧本「大禹治水」）
- `apps/api/routers/sandbox.py`：剧本列表 / 剧本详情 / 推演开始 / 推演详情 / 候选分支 / 推演前进 六端点
- `apps/web/src/pages/SandboxPage.tsx`：剧本选择 + 状态变量面板 + 当前节点叙事 + 候选分支决策 + 时间线
- `docs/adr/ADR-0003-练模块状压DP设计.md`：决策记录

状态编码策略：每个 `StateVar` 声明 `bits`，按声明顺序左移拼接为整数，作为 `lru_cache` key，确保「相同状态、相同节点」分支结果可复用。

剧本「大禹治水」共 4 状态变量（合计 9 bit）、8 节点、9 条边、2 终局（溃堤之变 / 开夏之基）。后续版本接入 LLM 动态叙事 + RAG 校验 + 剧本编辑器。

### v1.2.1（2026-05-03）练模块 DAG 拓扑可视化

- `apps/web/src/pages/SandboxPage.tsx` 接入 `reactflow ^11.11.4`，BFS 层级布局：`x = layer * 220, y = col * 90 - (rowCount-1) * 45`
- 节点配色：当前 #9F2E25 / 已访 #3F5F4D / 候选可达 #7A5C2E / 终局 #1F1B17 / 默认 #F3EBDD；终局节点 label 加 ⛩
- 边样式：候选边 `animated + #9F2E25 + 2px`，其余 `#D9C9A8 + 1px`；标签底色 #F3EBDD opacity 0.85
- `nodesDraggable=false / nodesConnectable=false`，仅作只读拓扑展示

### v1.3.0（2026-05-03）问模块双模智者 + 流式对话 + RAG 引证

落地内容：

- `services/agent/`：`models.py`（AgentPersona / Citation / DialogueMessage / DialogueSession / AskRequest / StreamChunk）+ `personas.py`（思辨派 + 史实派两 Persona）+ `corpus.py`（7 条典籍 + 关键词命中）+ `dialogue.py`（异步队列双流 + 字符块 yield）
- `apps/api/routers/agent.py`：`/personas` / `/corpus` / `/sessions` CRUD / `/sessions/{id}/ask` SSE 流式六端点
- `apps/web/src/pages/AgentPage.tsx`：主题输入 + 双栏并置（左思辨 #7A5C2E / 右史实 #3F5F4D）+ 提问输入 + 引证 Drawer + 历史消息列表
- `docs/adr/ADR-0004-问模块双模智者设计.md`：决策记录

流式协议：`text/event-stream` + `data: {json}\n\n` + `event: end` 收尾；前端 `fetch` + `ReadableStream` 解析，逐字渲染并按 `persona` 分流到左右栏。

Mock LLM 策略：思辨派 `_thinker_compose` 模板生成开放反问，史实派 `_historian_compose` 拼接 `search_corpus` 命中典籍片段。后续 v1.4.x 替换为真实 LLM 时，仅替换 `compose` + `search` 两层，SSE 协议与前端不变。

### v1.4.0（2026-05-03）创模块知识谱系画布

落地内容：

- `services/canvas/`：`models.py`（CanvasNodeKind 五分类 / CanvasNode / CanvasEdge / CanvasBoard / 多个 Upsert 请求）+ `store.py`（内存字典 + 「大禹治水」种子谱系）+ `layout.py`（layered / radial 双算法）+ `exporter.py`（JSON / Markdown / Mermaid）
- `apps/api/routers/canvas.py`：谱系 CRUD + 节点 upsert/delete + 边 upsert/delete + 自动布局 + 导出共十端点
- `apps/web/src/pages/CanvasPage.tsx`：谱系列表 + reactflow 可编辑画布（拖动、连线、单击编辑、双击删边、Delete 删点）+ 顶栏「新增节点 / 分层 / 放射 / MD / JSON / Mermaid」
- `docs/adr/ADR-0005-创模块知识谱系画布.md`：决策记录

布局策略：layered 走 BFS 层级，节点按 (layer×240, col×120) 网格排布；radial 取度数最大节点为中心，余者按等角分布在半径 260 圆上。

导出策略：JSON 即 `model_dump`，Markdown 按节点类型分组 + 关系段落，Mermaid 输出 `graph LR`。三种均通过 `Content-Disposition: attachment` 触发浏览器下载。

### v1.5.0（2026-05-03）看练问创全链路联调

落地内容：

- `apps/web/src/bridge.ts`：sessionStorage 桥模块，三段载荷类型（RecallToSandbox / SandboxToAgent / AgentToCanvas）+ set/take 一对 API（take 后即清）
- RecallPage：分镜生成后追加「送入练模块 →」按钮，携带 chapter_id / title / keywords / history_context
- SandboxPage：useEffect 接收看模块素材并 alert 提示；终局节点新增「送入问模块 →」，携带 scenario_title / ending_summary / keywords
- AgentPage：自动设置 topic 与预填问题；双派输出后追加「沉淀为创模块谱系 →」，携带 topic / 双派文本 / 引证去重列表
- CanvasPage：useEffect 自动 POST 创建谱系，依次 upsert 议题/思辨派/史实派/引证节点并按「辩 / 证 / 引」连边，最后调用 layered 布局
- HomePage：追加 v1.5.0 全链路引导 Steps 卡片
- `docs/adr/ADR-0006-看练问创全链路联调.md`：决策记录

关键约束：桥接全部走前端 sessionStorage，不新增后端 API；引证按 source_id 去重并截至前 6 条避免画布过密。

### v1.6.0（2026-05-03）后端持久化

落地内容：

- `services/persistence/`：基于已声明的 SQLAlchemy 2.0 + SQLite 的轻量持久化层，三张「JSON 镜像」表 `canvas_boards / sandbox_playthroughs / agent_sessions`，对外暴露 `save_* / delete_* / load_all_*` 与 `init_engine`
- `services/canvas/store.py`、`services/sandbox/engine.py`、`services/agent/dialogue.py`：写路径同步落盘，新增 `hydrate_from_db()` 启动装载
- `apps/api/main.py` lifespan：`init_engine → canvas/sandbox/agent.hydrate_from_db()`
- `apps/api/settings.py`：新增 `sqlite_path = "../../data/chronovita.db"`（相对 uvicorn cwd 回到仓库根）
- `docs/adr/ADR-0007-后端持久化.md`：决策记录

策略：内存仍为热路径，DB 作镜像；写时整段 `model_dump(mode="json")` 覆盖入表，读时用 `Model.model_validate` 反序列化；脏数据 silently skip 不阻塞启动。

验证：创建测试板 → SQLite 出现行 → 触发 reload → 接口仍返回该板 → 删除后 DB 行消失。

### v1.7.0（2026-05-03）多剧本拓展

落地内容：

- `services/sandbox/scenarios.py`：新增两条剧本
  - 商鞅变法（`qin-shang-yang-bianfa`）9 节点 9 边，状态变量 `trust / opposition / strength / law_kept` 共 10 位，含「姑息一时」与「孝公薨 · 旧贵反扑」两条终局
  - 王安石变法 · 熙宁新法（`song-wang-anshi-bianfa`）10 节点 11 边，状态变量 `emperor_will / conservative / finance / people` 共 12 位，含「罢免新党」与「元祐更化」两条终局
- `services/agent/corpus.py`：新增 4 条变法相关典籍（《宋史·王安石传》《临川集·本朝百年无事札子》《苏轼集·上神宗皇帝书》《续资治通鉴长编·熙宁三年》）+ 关键词索引扩充商鞅相关条目
- `services/recall/storyboard.py`：`_heuristic_flags` 人物/建筑识别 token 扩充至覆盖战国/宋朝场景
- `apps/web/src/pages/RecallPage.tsx`：「新建分镜」Card extra 区追加「快速模板」Select，一键填入三大剧本配套分镜素材

设计选择：剧本仍以代码常量形式声明（`_REGISTRY` 字典），重启即在；不引入剧本编辑后台，保持「研究者直接 PR 剧本」的轻流程。状态位宽预算（≤60 位）严格遵守，本期最大占用 12 位，余量充足。

验证：`GET /api/v1/sandbox/scenarios` 返回 3 条；商鞅 / 王安石 playthrough 起始节点正确，分支可枚举；新 playthrough 自动持久化入 sqlite。

### v1.8.0（2026-05-03）课堂化「老师预设」

落地内容：

- `services/classroom/`
  - `models.py`：`ClassroomTask`（task_id/title/scenario_id/teacher_notes/preset_state/must_visit_nodes/accepted_terminals/recommended_path/created_at）+ `CreateClassroomTaskRequest` + `TaskCheckResult`
  - `store.py`：内存 `_TASKS` + `list/get/create/delete/hydrate_from_db`，写时调用 `persistence.save_task` 落盘
- `services/persistence/db.py`：新增 `classroom_tasks` 表（task_id PK + data TEXT + updated_at DateTime）+ `save_task / delete_task / load_all_tasks`
- `services/sandbox/engine.py`：`new_playthrough(scenario_id, preset_state=None)` 支持课堂任务预调初始状态（按位宽 clamp）
- `apps/api/routers/classroom.py`：`GET /tasks`、`POST /tasks`（校验 must_visit / accepted_terminals 节点 id 是否存在）、`GET /tasks/{id}`、`DELETE /tasks/{id}`、`GET /tasks/{id}/check?playthrough_id=...`（自动比对 history 给出 must_visit_hit / miss、terminal_accepted、recommended_match_ratio、summary 文案）
- `apps/api/routers/sandbox.py`：`POST /playthroughs?scenario_id=&task_id=` 支持自动应用任务的 preset_state
- `apps/api/main.py`：挂载 classroom router，lifespan 增加 `classroom_store.hydrate_from_db()`
- 前端 `apps/web/src/pages/ClassroomPage.tsx`：老师面板，剧本动态表单（InputNumber 调初始状态、Checkbox.Group 选必经节点/合格终局、Select 多选推荐路径），创建后弹窗显示 task_id 与可分享链接
- `apps/web/src/pages/SandboxPage.tsx`：`useSearchParams` 读取 `?task=task_id` 自动加载任务卡（必经节点进度提示）；新推演 POST 携带 task_id；终局加「验收任务」按钮，弹 Modal 展示验收报告（含 Progress 推荐路径匹配率）
- `apps/web/src/App.tsx` + `HomePage.tsx`：新增 `/classroom` 路由与首页入口

设计选择：preset_state 仅在 `new_playthrough` 时生效（不修改 advance 路径），保持 DAG 状态转移规则纯粹；推荐路径以 edge_id 列表表达，验收时反查 history 相邻节点对应的边求集合交集；must_visit_nodes 与 accepted_terminals 在创建时强制校验 id 合法性；任务 ID 短哈希形式 `task_xxxxxxxxxx`，可由学生在 URL 中直接粘贴。

验证：端到端跑通——创建大禹治水任务（必经 n_reform/n_field_survey、合格终局 n_dynasty、4 条推荐边）→ 起新推演 → 沿推荐路径走 4 步 → `/check` 返回 `is_terminal=true / accepted=true / ratio=1.0 / must_hit_count=2 / miss_count=0`，summary 文案为「已圆满达成本任务的全部老师预设」。

### v1.9.0（2026-05-03）学生作业 · 推演记录回放

落地内容：

- `services/sandbox/models.py`：`PlaythroughSnapshot` 增 `task_id: str | None`、`student_name: str | None` 字段（向后兼容，旧记录默认 None）
- `services/sandbox/engine.py`：`new_playthrough` 增加 `task_id` / `student_name` 入参；新增 `list_playthroughs_by_task(task_id)`
- `apps/api/routers/sandbox.py`：`POST /playthroughs` 增加可选 `student_name` 查询参数透传
- `apps/api/routers/classroom.py`：抽离 `_check_one(task, snap)` 复用；新增 `GET /tasks/{id}/submissions` 端点，输出 `SubmissionsAggregate`（含 `node_visit_counts` / `edge_traverse_counts` / `terminal_distribution` / `accepted_count` / 逐学生 `SubmissionItem`）
- 前端 `SandboxPage`：任务模式新增学生姓名 Input（sessionStorage 缓存），未填禁止开始推演；POST 携带 student_name
- 前端 `ClassroomPage`：每张任务卡新增「作业回放」按钮，打开 760px Drawer——上方三宫格统计（提交总数 / 合格人次 / 合格率）+ 终局分布 Tag + 节点/边热力 Top 10 Progress 条 + 学生提交 Table（可展开看完整路径）

设计选择：聚合接口在服务端一次性算完热力计数，前端只做排序与展示；提交分数不存历史快照，每次重新计算（数据集小、计算简单），不引入额外存储；学生姓名走前端 sessionStorage，避免每次推演都让学生重填。

验证：用同一个大禹治水任务以「小明/小红/小李」三个 student_name 各跑一遍推荐路径，`GET /classroom/tasks/{id}/submissions` 返回 `total_count=3 / accepted_count=3`，`node_visit_counts` 五节点各 ×3，`edge_traverse_counts` 四边各 ×3，`terminal_distribution` `{n_dynasty: 3}`。

### v1.9.1（2026-05-04）课堂化精修

落地内容：

- `services/sandbox/engine.py`：新增 `reachable_nodes(scenario_id, preset_state)`——以 `(node_id, state_bits)` 为去重键的 BFS，复用既有 `_branches_cached` lru，无新增缓存
- `apps/api/routers/classroom.py`：新增 `GET /tasks/{id}/verify` → `TaskVerifyResult`（reachable_count / total_node_count / unreachable_must_visit / unreachable_accepted_terminals / unreachable_recommended_edges / warnings / ok）
- 前端 `ClassroomPage`：任务卡按钮组追加「预检」（弹 Modal 显示警告）「复制为模板」（回填 form 字段并打开 Drawer）
- 前端 `SandboxPage`：任务模式下用 `task.recommended_path` 在 ReactFlow DAG 中以青色（#3F5F4D）虚线 + ★ 标注推荐边，与当前候选边（红色实线）正交不冲突

设计选择：可达性算法采用状态位完整去重而非节点级去重，避免「同一节点不同状态可达不同后继」被误判为不可达；预检结果不持久化，每次现算（任务数量小、剧本变更频繁），保证与最新剧本一致。

验证：对大禹治水任务 `task_5eaf0a02ea` 调用 `/verify` 返回 `reachable_count=8 / total_node_count=8 / warnings=[] / ok=true`；前端任务模式打开沙盘可见推荐边以青虚线标注。

### v2.0.0（2026-05-05）第四条剧本 · 洋务运动

落地内容：

- `services/sandbox/scenarios.py`：新增 `_yangwu`（scenario_id `qing-yangwu-yundong`），10 节点 / 12 边 / 5 状态变量（industry / navy / frontier / conservatives / merchant），起点 `n_zongli`（设总理衙门），三类终局——`n_jiawu`（甲午之殇）/ `n_wuxu_eve`（维新前夜）/ `n_collapse`（顽固反扑）
- 关键分支：海防塞防之争 `n_haifang_saifang` 是必经路口；`n_xizheng` / `n_beiyang` 互斥后汇入 `n_guandu_shangban`；甲午败局可由「海军未振」或「未引商办」两条路径触发
- `services/agent/corpus.py`：新增 4 条洋务史料 Citation（曾国藩奏稿/李鸿章筹议海防折/左宗棠塞防疏/盛宣怀招商局章程）与对应关键词索引
- 版本号 → 2.0.0：标志四条剧本贯通先秦至晚清（夏 · 大禹 / 战国 · 商鞅 / 北宋 · 王安石 / 晚清 · 洋务），「看 · 练 · 问 · 创」全链路在四个历史阶段完整可运行

设计选择：洋务剧本节点数（10）与变量数（5）控制在与王安石变法（11/5）相近规模，避免认知超载；海防塞防之争作为强制汇聚节点，让两条主线必然交汇并在后续的官督商办抉择中暴露「制度未变」的核心矛盾——剧本叙事内嵌于状态机结构。

验证：`POST /classroom/tasks` 创建洋务任务（推荐路径 5 条边） → `/verify` 返回 `reachable_count=10 / total_node_count=10 / warnings=[] / ok=true`，所有节点全可达，推荐路径合法。

### v2.1.0（2026-05-03）问模块 · 真 LLM 接入

落地内容：

- 新增 `services/agent/llm.py`：异步适配层 `stream_chat(provider, model, messages, *, api_key, base_url) -> AsyncIterator[str]`，支持 `mock` / `openai` / `deepseek`（OpenAI 兼容） / `ollama`；OpenAI 兼容路径走 `{base_url}/chat/completions` SSE，Ollama 走 `{base_url}/api/chat` NDJSON；任何异常内部捕获后回落 mock，对外不抛
- `services/agent/dialogue.py`：`stream_answer` 按 `settings.llm_provider` 分支——mock 维持原 `_stream_text` 字符块路径，零行为差异；非 mock 时两派 Persona 各起 task 把 LLM chunk 推入 `asyncio.Queue` 串成 SSE；引证仍由后端在 LLM 输出完成后追加 `【引证】...`，**不让 LLM 自己编引证**；末尾持久化 `sess.messages`
- `apps/api/settings.py` + `.env.example`：新增 `CHRONO_LLM_PROVIDER`（默认 `mock`）/ `CHRONO_LLM_MODEL` / `CHRONO_LLM_API_KEY` / `CHRONO_LLM_BASE_URL`
- `apps/api/routers/agent.py`：新增 `GET /api/v1/agent/status` → `{provider, model, base_url, has_api_key}`
- `apps/web/src/pages/AgentPage.tsx`：顶部 AntD Tag 显示当前 provider/model；mock 模式标识「模拟模式」，老师一眼可知课堂是否在跑真模型
- 版本号 → 2.1.0：问模块从硬编码语料演示走向真模型接入，同时保留 mock 兜底确保离线/无 key 课堂可用

设计选择：适配层一函数三协议（OpenAI SSE / Ollama NDJSON / mock 字符块），避免引入 LangChain 等重型依赖；引证后置策略保证「史料可追溯」原则不被 LLM 幻觉污染；失败回退 mock 而非报错，保证课堂连续性优先于功能完备性。

验证：`CHRONO_LLM_PROVIDER=mock` 默认配置下 e2e 回归通过——`POST /api/v1/agent/answer` 流式两派输出 + 引证后置正常，`GET /api/v1/agent/status` 返回 `{provider: "mock"}`，AgentPage 顶部 Tag 显示「模拟模式」；真 provider 联调待用户提供 key 后逐家压测。

