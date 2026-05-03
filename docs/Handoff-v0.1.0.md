# 项目状态快照 · v0.1.0 交接

> 给下一位接手智能体看的"当前状态 + 下一步任务"单一文件。  
> 写于：v0.1.0 提交 `5499aef` 之后，先秦课程内容工作 **尚未开始**。

---

## 1. 当前已完成（v0.1.0）

### 1.1 框架壳层
- 5 模块路由全部联通：`/` `/courses` `/learning` `/practice` `/profile`
- 顶栏：Logo + 5 项导航 + 搜索（按 Enter → `/courses?q=…`） + 铃铛 → `/profile?tab=2` + 头像 → `/profile`
- 全站取消所有 `[测试]` toast；未实装能力统一文案：「该能力将在 vX.Y.x 接入」
- 个人中心基本资料表单接入 `localStorage`（key = `chronovita.profile`）

### 1.2 视觉/布局
- 课程中心：CSS Grid 三栏（`220px / minmax(0,1fr) / 300px`）+ Bilibili iframe + 章节卡时长徽章
- 主题色：`#0B1E3A` 海军蓝 / `#F5E6CC` 米白 / `#D4A95C` 金（`apps/web/src/theme.ts`）
- 全局样式：`apps/web/src/styles/global.css`

### 1.3 模板库（muban/）
开发新页面前先在 `muban/templates/` 找最近模板复制改造：
- `PageShell.tsx` — 标题+副标题+slot
- `ThreeColumnLayout.tsx` — 仿课程中心三栏
- `StatTabsList.tsx` — 仿我的学习
- `FilterCardGrid.tsx` — 仿实践课堂
- `SidebarFormPanel.tsx` — 仿个人中心
- 规范见 `muban/conventions.md`

### 1.4 后端
- FastAPI 5 个空路由（`apps/api/routers/{home,courses,learning,practice,profile}.py`）+ `/healthz`
- 持久化层：SQLAlchemy 2.0 + SQLite（`services/persistence/`）
- 历史业务模块全部下线（agent / canvas / classroom / recall / sandbox）

### 1.5 文档
- `README.md` — 一句话定位 + 五模块速览 + 启动指令
- `Roadmap.md` — 阶段 0 ~ 6 + 优化构筑记录
- `Development_Spec.md` — 9 节工程规范（含 §8 模板库 / §9 占位反馈边界）
- `docs/adr/` — 仅保留 0001 / 0007 / 0011 三份 ADR
- `docs/UI-Backlog.md` — 待美术补充的 UI 元素列表
- `muban/README.md` + `muban/conventions.md`

---

## 2. 下一位智能体的任务（用户最新指令）

> **来源**：用户于 v0.1.0 提交之后的对话原话

### 2.1 课程中心改造
- 现状：点击课程中心**直接进入**单课学习页，不合理
- 目标：
  - 进入 `/courses` 应是**主页面（catalog）**：可按 **时代 / 课程 / 板块** 进一步筛选
  - 选择后再 `/courses/:courseId` 跳转到学习页
  - 学习页内部按 **看 → 练 → 问 → 创** 四层
- 路由建议（待新智能体定稿）：
  - `/courses`                                  课程目录主页
  - `/courses/:courseId`                        课程详情（章节列表）
  - `/courses/:courseId/lesson/:lessonId/:layer` 单节课，layer ∈ `watch|practice|ask|create`

### 2.2 先秦课程内容（v0.2.x 首批）
- 用户允许**自行联网检索**先秦相关知识点
- 至少要包含若干节真实可读的课程文本（教材级、不要编造史料）
- 视频部分用户允许暂时缺位（用占位 / Bilibili iframe）

### 2.3 实践课堂功能实装
- "练"：决策沙盘 — 通用引擎 + 至少 1 个先秦剧本（如商鞅变法 / 春秋争霸择主）
- "问"：跨时对话 — 调用 DeepSeek LLM
- "创"：知识画板 — 节点-连线画布

### 2.4 LLM 接入（DeepSeek v4）
- **API Key 由用户提供**，仅供测试
- 用户要求："**写入一个文档中在本地进行存储**"
  - **强烈建议**写入 `apps/api/.env`（已在 `.gitignore`），**绝不提交**
  - 在 `apps/api/.env.example` 留示例占位 `DEEPSEEK_API_KEY=sk-…`
- 调用方案需自行查官方文档；DeepSeek v4 = `deepseek-chat` 走 OpenAI 兼容协议（base_url 通常为 `https://api.deepseek.com/v1`）
- 现有 ADR-0011 已设计 LLM 适配层，按其落地

### 2.5 验收标准（用户原话）
> 「最终搭建一个**可以基本运行**、仅缺少对应的 AI 视频的真实网站」

---

## 3. 关键技术约定（不要踩坑）

### 3.1 工程
- **Node 20 LTS + pnpm 9**；前端目录 `apps/web/`
- **Python 3.12 强制**；后端目录 `apps/api/`，虚拟环境 `apps/api/.venv/`
- 提交规范：`v大.中.小 - 中文版本说明`，结尾追加 `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`
- 提交时务必加 `git -c i18n.commitEncoding=utf-8 commit -F <file>`，否则中文提交信息乱码

### 3.2 前端
- AntD 静态 `message.X()` 取不到主题；本仓已在 `apps/web/src/utils/toast.ts` 用 Proxy + `MessageBinder` 桥接，**直接 `import { toast } from '../utils/toast'` 即可**
- localStorage 写读用 `apps/web/src/utils/storage.ts`（`loadJSON / saveJSON / removeKey`，命名空间 `chronovita.`）
- 不要在 toast 文案中保留 `[测试]` 字样
- 多列布局优先 CSS Grid `minmax(0,1fr)`，避免 AntD `<Row><Col>` 内容撑破回行问题

### 3.3 PowerShell 工具坏在本环境
- 跑命令一律用 `pylance_mcp_server-pylanceRunCodeSnippet`（Python `subprocess.run`）
- TypeScript 类型检查：`apps/web` 目录下 `node_modules\.bin\tsc.cmd --noEmit`
- 中文路径下 git stdout 是 UTF-8，但 cmd 默认 GBK 显示，用 `r.stdout.decode('utf-8','replace')`

### 3.4 已运行的后台进程（截至本次会话）
- vite dev (5173) pid 42408 · uvicorn (8000) pid 41760 — detached，**仍在运行**
- 新会话首次运行前请先 `Get-Process` / `netstat -ano | findstr :5173` 确认；不在则用 `pnpm dev` / `uvicorn` 重启

### 3.5 Pencil MCP（设计稿同步）
- 主稿 `assets/design/Chronovita-Shell-v3.pen`
- 课程中心改完布局后**未同步**回 Pencil；如需同步，schema 注意：
  - stroke = `{color, thickness}` 对象
  - text 必须先设 `textGrowth = "auto"|"fixed-width"|"fixed-width-height"` 再设宽高
  - cornerRadius 不可用于 group
  - content 内不可写 ASCII 双引号，用 `「」`

---

## 4. 文件入口速查

| 想看 | 看哪 |
| --- | --- |
| 5 路由总入口 | `apps/web/src/App.tsx` |
| 单页代码 | `apps/web/src/pages/*.tsx` |
| 全局样式 / CSS 变量 | `apps/web/src/styles/global.css` |
| AntD 主题 | `apps/web/src/theme.ts` |
| toast / storage 工具 | `apps/web/src/utils/` |
| 后端入口 | `apps/api/main.py` |
| 后端 5 路由 | `apps/api/routers/{home,courses,learning,practice,profile}.py` |
| 持久化 | `services/persistence/db.py` |
| 共享类型 | `packages/shared/` |
| 模板库 | `muban/` |
| UI 视觉稿（美术） | `UI/课程中心.png` `UI/实践课堂.png` |
| UI 组件参考图 | `UI_components_image2/01..06_*.png` |

---

## 5. 推荐推进顺序

1. **先建数据层**：在 `services/` 下加 `courses/` 模块（章节-小节-知识点模型 → SQLAlchemy）
2. **课程目录页**：`/courses` 改为目录，原内容迁到 `/courses/:courseId`
3. **种子数据**：先秦 1~2 课的真实文本（参考人教版七上教材目录），通过 alembic / 启动脚本播种到 SQLite
4. **DeepSeek 适配**：按 ADR-0011 落地 `services/llm/`，先做 mock，再加 DeepSeek 实现
5. **问层 MVP**：课程中心右侧"专家解读"接通 DeepSeek 流式
6. **练层 MVP**：决策沙盘引擎 + 1 个先秦剧本
7. **创层 MVP**：画板（建议 React Flow）
8. 全部接通后 commit `v0.2.0 - 先秦课程内容首发`

---

## 6. 立即可做的小事
- 用户编辑过 5 个 page 文件（见上一条 system context），开工前 `git diff` 看一眼
- API key 收到后**立刻**写入 `apps/api/.env`（不进 git），并在 `.env.example` 加占位
