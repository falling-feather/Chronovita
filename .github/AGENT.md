# 史脉 Chronovita · 工作区全局记忆（Agent 入门）

> 本文档为多会话并行开发时的「智能体冷启动手册」。新对话进入工作区，先读完本页再动手。

---

## 1. 项目身份

- **中文名**：史脉 Chronovita
- **远端仓库**：https://github.com/falling-feather/Chronovita
- **本地路径**：`d:\代码玩具测试\history`
- **定位**：面向高中/大学历史学科的「未来课堂」沙盘推演平台，以 GenAI + DAG 模拟 + 双 Persona 对话 + 知识画布构建「**看 → 练 → 问 → 创**」四模块闭环
- **用户角色**：教师设计课堂任务，学生在四模块中完成推演并产出可回放的学习轨迹
- **当前版本**：**V2.1.0**（已 push main + backup/v2.1.0）

---

## 2. 技术栈速查

| 层 | 技术选型 | 备注 |
| --- | --- | --- |
| 前端 | React 18 + Vite 5 + TypeScript + AntD 5 + react-router-dom + zustand + reactflow | AntD 中式 token：`#F3EBDD` 底 / `#1F1B17` 字 / `#9F2E25` 朱 |
| 后端 | FastAPI 0.115 + Pydantic 2.9 + SQLAlchemy 2.0 + httpx | 同步 SQLAlchemy + SQLite |
| 数据 | SQLite（`data/chronovita.db`，已 gitignore） | 4 张 JSON 镜像表 |
| LLM | mock / openai / deepseek / ollama 适配层 | env `CHRONO_LLM_PROVIDER` 切换，默认 `mock`，失败回退 mock |
| 设计 | pencil MCP，源文件 [assets/design/Chronovita-UI.pen](assets/design/Chronovita-UI.pen) | 4 模块 frame 已就位 |
| 基础设施 | [infra/docker-compose.yml](infra/docker-compose.yml) | postgres+redis+chroma 占位（生产路线），目前实际跑 SQLite |
| Python 环境 | **`.venv` 必须用 Python 3.11**（仓库根） | 3.14 缺 pydantic-core/orjson wheel，必踩 |

---

## 3. 目录结构

```
history/
├── apps/
│   ├── api/                FastAPI 入口
│   │   ├── main.py         lifespan 注入 sys.path + 从 DB 水合
│   │   ├── settings.py     app_version=2.1.0
│   │   ├── .env.example    LLM provider/key 模板
│   │   └── routers/        common / recall / sandbox / agent / canvas / classroom
│   └── web/                Vite + React 前端
│       ├── package.json    version=2.1.0
│       ├── vite.config.ts  /api → http://127.0.0.1:8000 代理
│       └── src/
│           ├── App.tsx     AntdApp 包根（修复 message 静态调用警告）
│           ├── theme.ts    中式 token
│           ├── bridge.ts   sessionStorage 跨页桥（看→练→问→创 串联）
│           └── pages/      HomePage / RecallPage / SandboxPage / AgentPage / CanvasPage / ClassroomPage
├── services/               业务编排层（被 routers 调用）
│   ├── recall/             看：Prompt 链 + Storyboard + ControlNet + pipeline
│   ├── sandbox/            练：DAG + 状压 DP + lru_cache + reachable_nodes BFS + scenarios
│   ├── agent/              问：双 Persona + corpus(11 典籍) + SSE 流式 + llm 适配
│   ├── canvas/             创：5 类节点 + CRUD + layered/radial 布局 + JSON/MD/Mermaid 导出
│   ├── classroom/          课堂：教师任务 + preset_state + recommended_path + 验收
│   └── persistence/        SQLite 持久化（4 张 JSON 镜像表，启动时 hydrate）
├── docs/
│   ├── PROJECT_PLAN.md
│   └── adr/                ADR-0001 ~ ADR-0011（技术栈/看/练/问/创/全链路/持久化/课堂/作业回放/洋务/LLM）
├── assets/design/          Chronovita-UI.pen（pencil MCP 源）
├── infra/                  docker-compose 占位
├── data/                   SQLite 落盘（gitignored）
├── README.md
├── Development_Spec.md     第 12 章版本里程碑 v1.0.0~v2.1.0
├── Roadmap.md              含优化构筑记录
├── .gitignore
└── .gitattributes          .pen binary，文本统一 LF
```

---

## 4. 四模块速览

| 模块 | 中文 | 核心能力 | 关键文件 | 主要 router 路径 |
| --- | --- | --- | --- | --- |
| 看 | 视觉再现 | Prompt 链 → Storyboard → ControlNet 出史诗级图文 | `services/recall/` | `/api/recall/*` |
| 练 | 沙盘推演 | DAG 状态机 + 状压 DP 找最优路径 + 4 剧本 | `services/sandbox/` | `/api/sandbox/*` |
| 问 | 史人对谈 | 双 Persona（保守派/革新派）+ 典籍 corpus + SSE 流式 | `services/agent/` | `/api/agent/*` |
| 创 | 知识谱系 | 5 类节点画布 + 自动布局 + 三种导出 | `services/canvas/` | `/api/canvas/*` |
| 课堂 | 任务编排 | 教师建任务 / 学生作答聚合回放 | `services/classroom/` | `/api/classroom/*` |

**沙盘剧本（4 个）**：`dayu`（大禹治水） / `shang-yang`（商鞅变法） / `wang-anshi`（王安石变法） / `qing-yangwu`（晚清洋务运动）。所有剧本 `/verify` 全可达。

---

## 5. 版本里程碑速查

| 版本 | commit | 主题 |
| --- | --- | --- |
| V1.0.0 | 4348a14 | 项目骨架与初始化文档 |
| V1.0.1 | 5ac140f | UI 设计源 + .gitattributes |
| V1.1.0 | d97bb9d | 看：Prompt 链 + ControlNet |
| V1.1.1 | fab83ea | 看模块小修 |
| V1.2.0 | 40beecf | 练：DAG + 状压 DP |
| V1.2.1 | 0367f1f | DAG react-flow 可视化 |
| V1.3.0 | d6c93e0 | 问：双 Persona + SSE |
| V1.4.0 | 3be03a2 | 创：知识谱系画布 |
| V1.5.0 | 67c48f4 | 全链路联调（看→练→问→创桥接） |
| V1.6.0 | 7baa450 | SQLite 持久化 |
| V1.7.0 | 9a444e4 | 商鞅 + 王安石变法剧本 |
| V1.8.0 | 561d138 | 老师课堂任务 |
| V1.9.0 | 9f47c23 | 学生作业聚合回放 |
| V1.9.1 | afba3fc | 课堂化精修 |
| V2.0.0 | ed06a8b | 晚清洋务运动剧本 |
| **V2.1.0** | **b4502ff** | **真 LLM 适配层（mock/openai/deepseek/ollama）** |

> 中版本及以上均已建 `backup/vX.Y.Z` 分支并推远端。

---

## 6. Git 规范（强制）

- **提交格式**：`V{大}.{中}.{小} 中文说明`，例 `V2.1.0 真 LLM 适配层落地`
  - V 大写、版本号必须三段、与中文说明之间一个空格、**无短横线**
- **分支策略**：每次「中版本」递增（`X.Y.0`）必须建 `backup/vX.Y.Z` 并 push
- **提交方式**：**始终用** `git commit -F message.txt`，message.txt 必须 **UTF-8 NoBOM**
  - 不要用 `git commit -m "中文"`（PowerShell 下大概率乱码）
- **PowerShell 写文件**：禁用 `Set-Content` / `Add-Content`（默认 GBK / 加 BOM）
  - 用 `[System.IO.File]::WriteAllText($path, $content, (New-Object System.Text.UTF8Encoding($false)))`
  - 或直接用 agent 的 `create_file` / `replace_string_in_file` 工具
- **PowerShell 双引号陷阱**：字符串中 `\u` 会被当字面字符（V1.9.1 踩过坑）→ 用单引号或外部文件
- **删 tag**：`git push origin :refs/tags/<name>`

---

## 7. 编码规范

- **不写代码注释**（除非用户明确要求）
- **UI 纯中文**，禁中英混排（按钮、提示、错误信息全中文）
- **文档与提交信息**：中文为主，技术名词保留英文（如 FastAPI、SQLite）
- **AntD 警告**：用 `App.useApp()` 取 `message`，根组件包 `<AntdApp>`；不要用 `bordered` 等已废弃 API
- **跨页传参**：用 `apps/web/src/bridge.ts` 的 sessionStorage 桥，不要塞 URL query

---

## 8. 启动方式

```powershell
# 后端（从仓库根）
& ".\.venv\Scripts\python.exe" -m uvicorn apps.api.main:app --reload --port 8000

# 前端（另一终端）
cd apps\web
npm run dev   # 默认 5173
```

- 浏览器访问 `http://localhost:5173`
- API 文档 `http://127.0.0.1:8000/docs`
- LLM 切换：复制 `apps/api/.env.example` → `.env`，改 `CHRONO_LLM_PROVIDER`、填 key
- **uvicorn watchfiles 不监视 `services/`**：改了 services 后手动 `Set-Content apps/api/main.py ...` 触发 reload，或重启

---

## 9. 持久化

- 文件：`data/chronovita.db`（gitignore）
- 4 张 JSON 镜像表：`canvas_boards` / `sandbox_playthroughs` / `agent_sessions` / `classroom_tasks`
- 启动时 lifespan 自动 hydrate 进内存 store
- 写入路径：业务服务层 save_* / load_all_* （见 [services/persistence/__init__.py](services/persistence/__init__.py)）

---

## 10. 踩坑清单（按出现频率）

1. **PowerShell 中文乱码**：`Get-Content` / `Set-Content` 默认 GBK；管道喂 `git commit -m` 也乱 → 一律 `-F file.txt` + IO.File UTF-8 NoBOM
2. **PowerShell `\u` 转义**：双引号 here-string 中 `\u` 被当字面字符
3. **Python 3.14 wheel 缺失**：pydantic-core / orjson 没预编译 → `.venv` 强制 3.11
4. **uvicorn watchfiles 范围**：默认只监视 `apps/api/`，改 `services/` 不重载
5. **AntD message 静态调用警告**：必须 `App.useApp()` + `<AntdApp>` 包根
6. **CanvasPage upsert bug 模板**：曾把 `CanvasNode` 当 `Board.nodes.slice(-1)` → 直接 cast
7. **Storyboard 启发式漏 keywords**：扫描必须覆盖 keywords 字段
8. **同文件并行补丁**：容易在尾部留重复片段 → 单文件单补丁，改后抽查末尾

---

## 11. 给新会话智能体的行动建议

- **先读本页 → 再读 [Development_Spec.md](Development_Spec.md) 第 12 章 → 再看相关 ADR**
- **新增功能前**：确认是否落入「看/练/问/创/课堂」之一，对齐对应 service + router + page 三件套
- **每次提交前**：用 `git status` 确认改动；提交信息写到 `.git/COMMIT_MSG.txt`（UTF-8 NoBOM），用 `git commit -F`
- **中版本递增**：commit 后 `git branch backup/vX.Y.Z` + `git push origin main backup/vX.Y.Z`
- **文档同步**：`Roadmap.md` 加版本行 + `Development_Spec.md` 第 12 章加段 + 新建 ADR（若引入新决策）
- **不主动推进版本**：除非用户明确发起；遇暂停指令立即收手

---

> 维护：每次主版本（X.0.0）发布或核心架构调整后，更新本页第 1/2/4/5/9 节。
