# Chronovita · 工作区智能体冷启动手册

> 多会话并行开发时的入门指南。新会话先读完本页，再动手。

---

## 1. 项目身份
- **中文名**：历史未来课堂 / Chronovita
- **远端**：https://github.com/falling-feather/Chronovita
- **本地**：`d:\代码玩具测试\history`
- **定位**：面向中小学历史教学的 AI 实践平台。当前阶段是**框架先行**——把 5 模块平台壳搭好，再让具体课程一节一节长进来。
- **教学法**：看 → 练 → 问 → 创 四层递进，**嵌入"课程"内部**，不作为顶层导航。
- **当前版本**：**v0.1.0**（框架重启）

## 2. 技术栈
| 层 | 技术 | 备注 |
| --- | --- | --- |
| 前端 | React 18 + Vite 5 + TS 5 + AntD 5 + react-router-dom + zustand | 主题：深海蓝 `#0B1E3A` + 米白 `#F5E6CC` + 金 `#D4A95C` |
| 后端 | FastAPI 0.115 + Pydantic 2.9 + SQLAlchemy 2.0 + httpx | 同步 SQLAlchemy + SQLite |
| 数据 | SQLite（`data/chronovita.db`，gitignored） | v0.1.0 仅含空库骨架 |
| 设计 | Pencil MCP，源文件 `assets/design/Chronovita-Shell-v3.pen` | |
| Python | 3.12 强制 | 3.14 缺 pydantic-core / orjson wheel |

## 3. 五模块路由
| 模块 | 前端 | 后端 |
| --- | --- | --- |
| 首页 | `/` | `/api/v1/home` |
| 课程中心 | `/courses` | `/api/v1/courses` |
| 我的学习 | `/learning` | `/api/v1/learning` |
| 实践课堂 | `/practice` | `/api/v1/practice` |
| 个人中心 | `/profile` | `/api/v1/profile` |

## 4. 目录速览
```
history/
├── apps/
│   ├── api/         FastAPI 入口（main / settings / routers/{common,home,courses,learning,practice,profile}）
│   └── web/         前端壳（5 页面 + 顶栏）
├── services/
│   └── persistence/ 通用 SQLite 持久化骨架（具体业务表后续追加）
├── packages/shared/ 前后端共享类型（占位）
├── assets/design/   Chronovita-Shell-v3.pen
├── docs/            ADR + UI-Backlog
├── UI/              美术视觉稿（课程中心.png / 实践课堂.png）
└── todo/            申报书
```

## 5. Git 规范
- 提交格式：`v大.中.小 - 中文版本说明`，例 `v0.1.0 - 平台五模块壳层落地`
- 中版本递增（X.Y.0）建 `backup/vX.Y.Z` 分支并推远端
- 提交信息走 `git commit -F message.txt`（UTF-8 NoBOM），避免 PowerShell 中文乱码

## 6. 编码规范
- **不写代码注释**（除非用户明确要求）
- **UI 全中文**，禁中英混排（专有名词如 AI、Vite 例外）
- **AntD message** 必须 `App.useApp()` + `<AntdApp>` 包根
- **禁止**在框架层引入任何具体课程内容（大禹、洋务、商鞅等）

## 7. 启动
```powershell
# 后端
cd apps\api
& "..\..\.venv\Scripts\python.exe" -m uvicorn main:app --reload --port 8000

# 前端
cd apps\web
pnpm install
pnpm dev
```
- 前端 `http://localhost:5173`
- API 文档 `http://127.0.0.1:8000/docs`

## 8. 行动建议
1. 先读 `README.md` → `Development_Spec.md` → `Roadmap.md` → 相关 ADR
2. 看待办：用户后续会按"阶段 1 → 6"的顺序推进，**不要主动跳过**
3. 改动文档后同步更新 `Roadmap.md` 的"优化构筑记录"
