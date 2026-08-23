# 历史未来课堂 · Chronovita

> 面向中小学历史教学与历史仿真创新训练的 AI 实践平台。当前开发版本 **V0.10.17**；本版本在可信 accounts 课堂基线上建立原创学生端视觉系统、展馆式全局壳和随本机时间变化的 Three.js 日晷首页。课程地图、课程头图、四阶段交互与学习书案继续按十一项长期任务推进；最终 prerelease 仍须经过用户验收和发行物复核，不宣称公网或多学校生产部署已经完成。

[远端仓库](https://github.com/falling-feather/Chronovita) · [项目总纲](doc/00-项目总纲.md) · [开发者文档](doc/01-开发者文档.md) · [项目规划](doc/02-项目规划.md) · [开发历史](doc/03-开发历史.md)

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

每一节课内部都按「**看** · 沉浸叙事 → **练** · 沙盘推演 → **问** · 双模智者 → **创** · 知识谱系」的四层流程组织，环环相扣、逐步递进。各层当前实现见 [开发者文档](doc/01-开发者文档.md)，后续任务见 [项目规划](doc/02-项目规划.md)；`Development_Spec.md` 仅保留为 V0.7.4 历史快照。

## 技术栈

- 前端：React 18 + Vite 8 + TypeScript 5 + Ant Design 5 + React Router 7 + React Flow 11 + Zustand
- 后端：Python 3.11-3.13 + FastAPI + Pydantic v2 + SQLAlchemy 2.0 + SQLite（本地）/ PostgreSQL（生产边界）
- LLM/RAG：DeepSeek 兼容在线模型 + 本地抽取式回退；L101/L103 各 30 个稳定证据片段由 SQLite FTS5 中文字词/二元组与本地 `BAAI/bge-small-zh-v1.5` 检索，经 RRF 融合后由 `/practice/ask/rag` 返回当前发布 checksum、引用卡和不确定性；模型或向量缺失时保持 FTS/抽取可用
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
│   ├── rag/                  发布内 FTS5/BGE 混合检索与证据约束回答
│   └── llm/                  DeepSeek + mock 适配层
├── infra/                    docker-compose 与基础设施
├── content/                  课程草稿、封存件、运行制品与发布清单
├── scripts/                  一键启动、维护、迁移、校验与发行打包
├── distribution/             教师发行包说明等受控发行源
├── assets/design/            Pencil 设计稿（.pen）
├── muban/                    可复用页面 / 区块模板
├── doc/                      当前项目总纲、开发者文档、规划与开发历史
├── docs/                     兼容快照、内容专项、依据库、运维说明与 ADR
├── UI/                       美术绘制的 UI 视觉稿
└── todo/                     立项申报书与初始引导
```

> 课程级业务（看练问创各自的具体引擎、剧本、人物语料）已随朝代详表完成于 `services/courses/`、`services/saga/`、`services/sandbox/`中。

## 视觉规范

- 主题色：深海军蓝 `#0B1E3A` 底 / 米白 `#F5E6CC` 文 / 金色 `#D4A95C` 强调
- 字体：标题"霞鹜文楷 / 思源宋体"，正文"思源黑体"
- 风格：古典中式 + 现代教育平台，禁止中英混排，禁止花哨配色

## 快速启动

### 当前可用教师包与 V0.10 课堂包

当前已公开验收的稳定发行物仍是 [v0.9.41 教师编辑器](https://github.com/falling-feather/Chronovita/releases/tag/v0.9.41)。V0.10.14 已能在 CI 或本机确定性生成 `Chronovita-Classroom-v0.10.14-windows.zip`、对应 SHA-256 和依赖/模型许可清单，并以 Edge 在 1366×768、1920×1080 两档完成本地双课整链；最终 prerelease 尚待用户内容验收和最终发行物复核，因此不要把开发分支描述成已公开发布版本。

课堂包完整解压后双击 `启动Chronovita课堂.cmd`；默认只监听 `127.0.0.1:8000`，首次启动安全创建管理员密码。仅在可信课堂网络中从 PowerShell 显式执行 `.\scripts\classroom.ps1 -Lan`，才会绑定 LAN 并显示学生地址。完整说明见 [课堂包使用说明](distribution/classroom/课堂使用说明.txt)。

V0.9.41 教师包完整解压后可双击根目录的 `点我一键启动（部署）.cmd`；课程历史投稿凭据由项目管理员单独发放，并由 Windows DPAPI 绑定当前账号加密保存。完整说明见 [课程内容历史库运维指南](docs/07-课程内容历史库运维指南.md)。

### 先决条件
- Node.js 20.19+ 或 22.12+ LTS
- Python 3.11、3.12 或 3.13
- 项目根虚拟环境 `.venv/`，后端以 PowerShell `& ".\.venv\Scripts\python.exe" -m uvicorn ...` 启动

### 正式双端口验收

不要手工拼接任意 Vite/API 端口。开发工作树中统一执行：

```powershell
.\scripts\classroom-review.ps1
```

默认使用 Web `5174`、API `8010`，自动把实际 Web Origin 写入 Cookie 白名单，并强制复验打包 BGE 模型后以混合检索启动。端口冲突时显式传入 `-WebPort` 与 `-ApiPort`；只有明确验证离线回退时才使用 `-LexicalOnly`。停止执行 `.\scripts\stop-classroom-review.ps1`。

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

> 本地向量资源不直接提交大文件。执行 `& ".\.venv\Scripts\python.exe" scripts\prepare_rag_model.py` 会下载固定 revision、逐文件复验 SHA-256，并以 `local_files_only` 完成离线自检；缺少资源时 API 自动保留 FTS5 与抽取式回答。

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
- 详见 [项目总纲第 6 节](doc/00-项目总纲.md#6-git-与工作树边界) 与 [项目规划](doc/02-项目规划.md)

## 许可

待定。在确定许可前，仓库内容仅供 Chronovita 团队内部研发使用。
