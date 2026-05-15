# 历史未来课堂 · Chronovita

> 面向中小学历史教学的 AI 实践平台。当前版本 **V0.7.0**：14 朝代 48 节教材级正文 + 全朝代 saga 互动剧本 + DeepSeek v4-pro 跨时对话 + 知识画板 AI 扩充。

[远端仓库](https://github.com/falling-feather/Chronovita) · [开发文档](Development_Spec.md) · [研发路线](Roadmap.md) · [规划](docs/Planning.md)

## 一句话定位

把传统"听讲—背诵—考试"的历史课，重构为「**看 → 练 → 问 → 创**」四层递进的实践课堂，由生成式 AI 驱动，由真实课堂验证。

四层教学法是底层方法论，**不是顶层导航**。顶层呈现给学生的是一个完整的课堂平台。

## 平台五大模块

| 模块 | 职责 | 状态 |
| --- | --- | --- |
| 首页 | 学情概览、今日课表、推荐课程、平台公告 | 占位 · 待 v0.8 接入进度 |
| 课程中心 | 以 SVG 历史地图为入口，按朝代 / 板块 / 关键字浏览进入课程 | ✅ |
| 我的学习 | 已选课程、学习进度、笔记、作业、错题与回放 | 占位 · 进度未持久化 |
| 实践课堂 | 决策推演、沙盘剧本、即时反馈与课堂任务 | ✅ saga 全朝代覆盖 |
| 个人中心 | 账号信息、学习偏好、设置、消息中心 | 本地 localStorage |

每一节课内部都按「**看** · 沉浸叙事 → **练** · 沙盘推演 → **问** · 双模智者 → **创** · 知识谱系」的四层流程组织，环环相扣、逐步递进。各层实装状态见 [Development_Spec.md](Development_Spec.md) §3。

## 技术栈

- 前竲：React 18 + Vite 5 + TypeScript 5 + Ant Design 5 + React Router 6 + React Flow 11 + Zustand
- 后竲：Python 3.11/3.12 + FastAPI + Pydantic v2 + SQLAlchemy 2.0 + SQLite（开发）
- LLM：DeepSeek v4-flash（saga 流式叙事） + DeepSeek v4-pro（「问」跨时对话，准确度优先） + mock 回落
- 包管理：pnpm 9 / Node 20 LTS / venv
- 设计：Pencil（`assets/design/*.pen`）
- 基础设施：Docker Compose（中长期接入 Postgres / Redis / 向量库）

## 仓库结构

```
.
├── apps/
│   ├── web/                  前端平台壳（5 模块 + lesson 四层面板）
│   └── api/                  后端 FastAPI（5 路由 + practice 下 saga/sandbox/canvas/ask）
├── packages/
│   └── shared/               前后端共享类型与常量
├── services/
│   ├── persistence/          SQLAlchemy + SQLite 持久化层
│   ├── courses/              14 朝代 48 节课程数据集
│   ├── saga/                 互动剧本引擎 + 48 个模板
│   ├── sandbox/              决策推演通用引擎（商鞅变法首发）
│   └── llm/                  DeepSeek + mock 适配层
├── infra/                    docker-compose 与基础设施
├── assets/design/            Pencil 设计稿（.pen）
├── muban/                    可复用页面 / 区块模板
├── docs/                     ADR 与设计决策、规划文档
├── UI/                       美术绘制的 UI 视觉稿
└── todo/                     立项申报书与初始引导
```

> 课程级业务（看练问创各自的具体引擎、剧本、人物语料）已随朝代详表完成于 `services/courses/`、`services/saga/`、`services/sandbox/`中。

## 视觉规范

- 主题色：深海军蓝 `#0B1E3A` 底 / 米白 `#F5E6CC` 文 / 金色 `#D4A95C` 强调
- 字体：标题"霞鹜文楷 / 思源宋体"，正文"思源黑体"
- 风格：古典中式 + 现代教育平台，禁止中英混排，禁止花哨配色

## 快速启动

### 先决条件
- Node.js 20 LTS · pnpm 9
- Python 3.11/3.12（避免 3.14，部分依赖缺 wheel）
- 项目根虚拟环境 `.venv/`，后端以 PowerShell `& ".\.venv\Scripts\python.exe" -m uvicorn ...` 启动

### 启动后端
```powershell
# 仓库根
Python -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install -r apps/api/requirements.txt
cd apps/api
& "..\..\.venv\Scripts\python.exe" -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
后端文档：`http://127.0.0.1:8000/docs`

> 访问真 DeepSeek：复制 `apps/api/.env.example` 为 `apps/api/.env`，填入 `CHRONO_DEEPSEEK_API_KEY`，并将 `CHRONO_LLM_PROVIDER=deepseek`；`.env` 已在 `.gitignore`。

### 启动前端
```powershell
cd apps/web
pnpm install
pnpm dev
```
前端：`http://127.0.0.1:5173`

## 提交规范

- 提交信息：`V大.中.小 中文提交信息`，例如 `V0.7.0 「问」板块接入 deepseek-v4-pro`
- 中版本递增时同步创建 `backup/v0.X.0` 分支作为历史可查点
- 详见 [Development_Spec.md](Development_Spec.md) §5 与 [docs/Planning.md](docs/Planning.md) 末尾所附版本节奏

## 许可

待定。在确定许可前，仓库内容仅供 Chronovita 团队内部研发使用。
