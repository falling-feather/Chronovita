# Chronovita 开发文档 · Development Specification

> 工程级单一信源。任何与本文冲突的实现均视为缺陷。当前版本 **V0.7.0**。

---

## 1. 文档分级

| 层级 | 文档 | 受众 | 更新频率 |
| --- | --- | --- | --- |
| 顶层 | [README.md](README.md) | 所有人 | 每个中版本 |
| 顶层 | [Roadmap.md](Roadmap.md) | 项目管理 / 教师 | 每次提交 |
| 顶层 | Development_Spec.md（本文） | 全体研发 | 每次中版本递增 |
| 规划 | [docs/Planning.md](docs/Planning.md) | 项目管理 / 研发 | 每轮迭代 |
| 交接 | [docs/Handoff-v0.7.0.md](docs/Handoff-v0.7.0.md) | 接手智能体 | 每个版本节点 |
| 交接（旧） | [docs/Handoff-v0.1.0.md](docs/Handoff-v0.1.0.md) | 仅历史参考 | 冻结 |
| 决策记录 | docs/adr/ADR-XXXX.md | 架构师 | 每次架构决策 |
| UI 待补 | [docs/UI-Backlog.md](docs/UI-Backlog.md) | 美术 / 前端 | 每周 |
| 地图设计 | [docs/Map-Design.md](docs/Map-Design.md) | 前端 | 随地图迭代 |
| 接口契约 | apps/api（FastAPI 自动生成 OpenAPI） | 前后端联调 | 每次接口变更 |

## 2. 系统总体架构

### 2.1 部署拓扑（v0.x 开发期）

```
┌─────────────┐     ┌──────────────────┐
│   浏览器    │ <-> │  apps/web        │  Vite 5 Dev Server (5173)
│  React SPA  │     └──────────────────┘
└─────────────┘             │
        │                   v
        │           ┌──────────────────┐
        └---HTTP--->│  apps/api        │  FastAPI + Uvicorn (8000)
                    └──────────────────┘
                            │
                            v
                    ┌──────────────────┐
                    │  SQLite          │  data/chronovita.db
                    └──────────────────┘
```

中长期演进至 Postgres + Redis + 向量库，部署到 Docker Compose / K8s。

### 2.2 仓库分层

- `apps/web` — 前端平台壳，顶层 5 路由 + `pages/lesson/` 课内四层面板（Watch/Practice/Ask/Create）
- `apps/api` — 后端 API 入口，路由按 5 模块拆分；`practice` 下集成 saga/sandbox/canvas/ask 四子体系
- `services/` — 后端业务逻辑层：
  - `persistence/` — SQLAlchemy + SQLite（canvas 节点 KV、saga session 起始点）
  - `courses/` — 14 朝代 48 节课程数据集（Pydantic 模型）
  - `saga/` — 互动剧本引擎 + 48 个模板（收束触发器 / persona 点名 / 防循环）
  - `sandbox/` — 决策推演通用引擎（当前仅商鞅变法示例剧本）
  - `llm/` — DeepSeek + mock 双 provider，支持 `model` 参数透传（saga=v4-flash / ask=v4-pro）
- `packages/shared` — 前后端共享类型常量

### 2.3 五模块路由约定

| 模块 | 前端路由 | 后端 API 前缀 |
| --- | --- | --- |
| 首页 | `/` | `/api/v1/home` |
| 课程中心 | `/courses` | `/api/v1/courses` |
| 我的学习 | `/learning` | `/api/v1/learning` |
| 实践课堂 | `/practice` | `/api/v1/practice` |
| 个人中心 | `/profile` | `/api/v1/profile` |

## 3. 教学法 · 看练问创

四层方法论嵌入"课程"内部，**不**作为顶层导航（课内路由 `/courses/:cid/lessons/:lid?layer=watch|practice|ask|create`）：

| 层 | layer | 职责 | 当前实装 |
| --- | --- | --- | --- |
| **看** | `watch` | 沉浸叙事：正文 + 关键词卡 + 视频入口 | 正文/关键词已实装；AI 视频占位 |
| **练** | `practice` | 沙盘推演 = saga 互动剧本 + 决策分支 | saga 48 节全覆盖 + sandbox 示例剧本 |
| **问** | `ask` | 双模智者：专家（学界共识）+ 同窗（同时期真实人物） | DeepSeek v4-pro 流式 |
| **创** | `create` | 知识谱系：React Flow 画板 + AI 扩充节点/边 | 画板云端持久化 + AI 扩充已接入 |

每节课按"看 → 练 → 问 → 创"递进，具体引擎实现见 [services/](services/)。

## 4. 视觉规范

- 主题色：`#0B1E3A`（海军蓝） / `#F5E6CC`（米白） / `#D4A95C`（金）
- 辅助：`#1B3A66`（中蓝） / `#0A1628`（深蓝） / `#A0826B`（古铜）
- 字体：标题 `"霞鹜文楷", "Noto Serif SC", serif`；正文 `"思源黑体", "Noto Sans SC", sans-serif`
- 圆角 4px，阴影克制，强调金色描边而非投影

详见 `apps/web/src/theme.ts` 与 `assets/design/Chronovita-Shell-v3.pen`。

## 5. 编码与提交

### 5.1 命名
- 前端组件 PascalCase；hook `useXxx`；样式文件与组件同名
- 后端文件 snake_case；路由模块名与模块名一致

### 5.2 提交信息
- 格式：`V大.中.小 中文提交信息`（示例：`V0.7.0 「问」板块接入 deepseek-v4-pro`）
- 三段必填，不使用省略写法
- 中版本递增时同步建立 `backup/v0.X.0` 备份分支并推送
- PowerShell 下提交中文：`git commit -F message.txt`（文件需 UTF-8 no BOM）避免乱码

### 5.3 禁止事项
- 禁止中英文混排（中文文案中夹"AI"、"Lv"等英文术语除非属专有名词）
- 禁止破坏 5 模块路由约定
- 禁止提交 `apps/api/.env` 中的真实 API Key（已在 `.gitignore`）
- 禁止在 saga / ask prompt 中提示 LLM「允许虚构史料」

## 6. 测试与质量

- 后端：`pytest` 单测随业务逐步追加；saga 包括压力测试脚本（多轮 ended/记忆压缩/人物一致，详见 V0.5.1 / V0.6.1）
- 前端：以 Playwright MCP 跨服务烟囱（路由可达 + saga/ask 流式实测 + 画板交互）
- 上线前必跑：TypeScript 类型检查（`pnpm tsc --noEmit`） + saga 批量验证脚本

## 7. 安全与合规

- 不得提交任何真实 API Key、学生个人数据、教师手机号
- LLM 适配层启用需在 `apps/api/.env` 配置，**不得**写入仓库；变量名使用 `CHRONO_` 前缀（见 [apps/api/settings.py](apps/api/settings.py)）
- saga / ask 输出仅限中学课堂适龄，发现 LLM 产出不实先调 prompt、不仅靠过滤
- 用户上传内容（后期）需走过滤管线，避免课堂出现违规叙事

## 8. 模板库 · muban/

- 路径：仓库根 `muban/`，与 `apps/`、`docs/` 平级
- 用途：沉淀**与具体业务解耦**的页面 / 区块骨架（外壳、三栏、Tab 列表、Chip 网格、菜单+表单）
- 使用规则：
  - 新增页面前先在 `muban/templates/` 找最近模板复制改造
  - 改完若仍具普适性，可反向沉淀回 `muban/`
  - **不**被 `apps/web` 直接引用，避免业务改动污染模板
- 文件清单与规范：见 `muban/README.md` 与 `muban/conventions.md`

## 9. 占位反馈与真实功能边界

- **真实功能**（路由跳转、本地状态切换、localStorage 读写）→ 直接执行，不弹 toast
- **后端写操作**完成 → `toast.success('已保存')`、失败 → `toast.error('…')`
- **未实装能力**（AI 生成、跨时对话、画板、专家解读…）→ `toast.info('该能力将在 vX.Y.x 接入')`
- **禁止**在 toast 文案中保留 `[测试]` 字样（v0.1.0 已全部清理）

## 10. LLM 适配层与双模型策略

- 入口：[services/llm/__init__.py](services/llm/__init__.py) `stream_chat(messages, *, provider=None, model=None)`
- Provider：`mock`（离线兜底）/ `deepseek`（OpenAI 兼容）；`CHRONO_LLM_PROVIDER` 环境变量切换
- DeepSeek V4 双模型：
  - `deepseek-v4-flash`：默认，**saga 引擎使用**——追求流式速度与节奏感
  - `deepseek-v4-pro`：[apps/api/routers/practice.py](apps/api/routers/practice.py) `/ask` 显式覆盖——准确度优先
  - 两者均支持 `thinking` 字段（`disabled`/`enabled`），由 `CHRONO_DEEPSEEK_THINKING` 控制
- 调用约定：业务层不直接拼 HTTP，统一 `await llm.stream_chat(messages, model=...)` 异步迭代
- 异常回落：网络/鉴权失败 → mock 流，对外不抛
- 元数据接口：`GET /api/v1/practice/llm/info` 同时返回 `provider`（saga 用）和 `ask_provider`（ask 用），前端 Tag 实时显示

## 11. saga 互动剧本引擎

- 入口：[services/saga/__init__.py](services/saga/__init__.py)（约 100KB，包含全部 48 个模板）
- 状态机：`SagaState{ history, summary, choices, flags, entities, step, ended }`
- 流式协议：`POST /api/v1/practice/saga/{id}/act` 返回 `text/plain`，正文为剧情叙述，**末尾追加 `\n\n[META]{...json...}`** 携带新 choices/flags/ended
  - 前端解析见 [apps/web/src/utils/api.ts](apps/web/src/utils/api.ts) `streamSagaAct`
- 收束触发器（V0.6.0+）：达到 `max_steps` 或剧情命中关键 flag 时，强制注入"收束"提示
- 防循环 / persona 点名：避免 LLM 反复抛同一个选项；选项缺失时强制清空避免陈旧残留（V0.6.3）
- 模板组织：每个 `lesson_id` 对应一个模板，包含 `era / persona / keywords / opening / collapse_hints`
- 验证脚本：`tools/saga_smoke.py`（见 V0.5.1 / V0.6.1）默认 7 轮压力测，校验 `ended` 收束率 / 人物一致性 / 关键词覆盖

## 12. 文件入口速查

| 想看 | 看哪 |
| --- | --- |
| 5 路由总入口 | [apps/web/src/App.tsx](apps/web/src/App.tsx) |
| 课内四层面板 | [apps/web/src/pages/lesson/](apps/web/src/pages/lesson/) |
| 全局样式 / CSS 变量 | [apps/web/src/styles/global.css](apps/web/src/styles/global.css) |
| AntD 主题 | [apps/web/src/theme.ts](apps/web/src/theme.ts) |
| 前端 API 客户端 | [apps/web/src/utils/api.ts](apps/web/src/utils/api.ts) |
| 后端入口 | [apps/api/main.py](apps/api/main.py) |
| 后端 5 路由 | [apps/api/routers/](apps/api/routers/) |
| 后端配置项 | [apps/api/settings.py](apps/api/settings.py) |
| 持久化 | [services/persistence/db.py](services/persistence/db.py) |
| 课程数据 | [services/courses/__init__.py](services/courses/__init__.py) |
| LLM 适配层 | [services/llm/__init__.py](services/llm/__init__.py) |
| saga 引擎 + 模板 | [services/saga/__init__.py](services/saga/__init__.py) |
| sandbox 决策引擎 | [services/sandbox/__init__.py](services/sandbox/__init__.py) |
| 模板库 | [muban/](muban/) |
