# 历史未来课堂 · Chronovita

> 面向中小学历史教学与历史仿真创新训练的 AI 实践平台。当前候选版本 **V0.9.38**；`class` 分支已完成确定性课程归档、GitHub PR 后端链路、教师发布界面和无密钥 Windows 教师包，并根据独立审查收紧重试绑定、GitHub API 主机、归档路径与包体密钥扫描。首个可下载教师版本仍为 [v0.9.37 prerelease](https://github.com/falling-feather/Chronovita/releases/tag/v0.9.37)，V0.9.38 等待远端门禁与新标签发行复验。

[远端仓库](https://github.com/falling-feather/Chronovita) · [项目总纲](docs/00-项目总纲.md) · [开发者文档](docs/01-开发者文档.md) · [项目规划](docs/02-项目规划与设计总纲.md) · [开发历史](docs/05-发布历史与归档.md)

## 一句话定位

把传统"听讲—背诵—考试"的历史课，重构为「**看 → 练 → 问 → 创**」四层递进的实践课堂，由生成式 AI 驱动，由真实课堂验证。

四层教学法是底层方法论，**不是顶层导航**。顶层呈现给学生的是一个完整的课堂平台。

## 平台五大模块

| 模块 | 职责 | 状态 |
| --- | --- | --- |
| 首页 | 学情概览、继续学习、推荐课程、平台公告 | 可用，继续学习读取真实进度 |
| 课程中心 | 以历史地图为入口，按朝代、板块和关键词进入课程 | 可用 |
| 我的学习 | 已选课程、学习进度、笔记与学习成果 | 可用，进度由后端 KV 持久化 |
| 实践课堂 | 决策推演、沙盘剧本、即时反馈与课堂任务 | 可用，48 节 saga 模板覆盖 |
| 个人中心 | 账号信息、学习偏好和设置 | 本地体验可用，组织级账号前端待建设 |

每一节课内部都按「**看** · 沉浸叙事 → **练** · 沙盘推演 → **问** · 双模智者 → **创** · 知识谱系」的四层流程组织，环环相扣、逐步递进。各层当前实现见 [开发者文档](docs/01-开发者文档.md)，后续任务见 [项目规划](docs/02-项目规划与设计总纲.md)；`Development_Spec.md` 仅保留为 V0.7.4 历史快照。

## 技术栈

- 前端：React 18 + Vite 8 + TypeScript 5 + Ant Design 5 + React Router 7 + React Flow 11 + Zustand
- 后端：Python 3.11-3.13 + FastAPI + Pydantic v2 + SQLAlchemy 2.0 + SQLite（本地）/ PostgreSQL（生产边界）
- LLM：DeepSeek v4-flash（saga 流式叙事） + DeepSeek v4-pro（「问」跨时对话，准确度优先） + mock 回落
- 包管理：npm + package lock / Node.js LTS / Python venv
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
├── content/                  课程草稿、封存件、运行制品与发布清单
├── scripts/                  一键启动、维护、迁移、校验与发行打包
├── distribution/             教师发行包说明等受控发行源
├── assets/design/            Pencil 设计稿（.pen）
├── muban/                    可复用页面 / 区块模板
├── docs/                     项目总纲、开发者文档、规划、历史、内容规范与 ADR
├── UI/                       美术绘制的 UI 视觉稿
└── todo/                     立项申报书与初始引导
```

> 课程级业务（看练问创各自的具体引擎、剧本、人物语料）已随朝代详表完成于 `services/courses/`、`services/saga/`、`services/sandbox/`中。

## 视觉规范

- 主题色：深海军蓝 `#0B1E3A` 底 / 米白 `#F5E6CC` 文 / 金色 `#D4A95C` 强调
- 字体：标题"霞鹜文楷 / 思源宋体"，正文"思源黑体"
- 风格：古典中式 + 现代教育平台，禁止中英混排，禁止花哨配色

## 快速启动

### 教师一键启动

Windows 教师从 [v0.9.37 Release](https://github.com/falling-feather/Chronovita/releases/tag/v0.9.37) 下载 `Chronovita-Teacher-Editor-v0.9.37-windows.zip` 并完整解压后，双击根目录的 `点我一键启动（部署）.cmd`。首次运行会自动创建本地环境、按完整哈希锁安装后端依赖、按 package lock 安装前端依赖、完成生产构建，并以生产预览服务打开 `http://127.0.0.1:5173/admin/content`；依赖安装完成后，本地编辑与预览不依赖 Google Fonts 或 GitHub。发行包不携带数据库、草稿、缓存、日志或 GitHub 凭据，ZIP 的 SHA-256 为 `40bb46496727a101c3257ed20950e820a8e1ce3ca0c2f06eea880cbdf827b518`。当前教师包要求电脑预先安装 Python 3.11-3.13 和 Node.js 20.19+ 或 22.12+ LTS。

课程历史投稿凭据由项目管理员单独发放，教师运行 `scripts/configure-content-history.cmd` 后以 Windows DPAPI 加密保存在本机；普通编辑、保存和 ZIP 导出不要求配置凭据。停止服务使用 `scripts/stop-teacher-editor.cmd`。完整说明见 [课程内容历史库运维指南](docs/07-课程内容历史库运维指南.md)。

### 先决条件
- Node.js 20.19+ 或 22.12+ LTS
- Python 3.11、3.12 或 3.13
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
npm ci
npm run dev
```
前端：`http://127.0.0.1:5173`

## 提交规范

- 提交信息：`V大.中.小 GROUP type(scope): 描述（TASK-ID）`，例如 `V0.9.31 FE feat(content): 接通教师课程历史发布界面（FE-004）`
- 中版本递增时同步创建 `backup/v0.X.0` 分支作为历史可查点
- 详见 [项目总纲第 6 节](docs/00-项目总纲.md#6-版本与任务规则) 与 [项目规划](docs/02-项目规划与设计总纲.md)

## 许可

待定。在确定许可前，仓库内容仅供 Chronovita 团队内部研发使用。
