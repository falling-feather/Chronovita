# 历史未来课堂 · Chronovita

> 面向中小学历史教学的 AI 实践平台。先把"未来课堂"的壳搭好，再让历史课程一节一节长进来。

[远端仓库](https://github.com/falling-feather/Chronovita) · [开发文档](Development_Spec.md) · [研发路线](Roadmap.md)

## 一句话定位

把传统"听讲—背诵—考试"的历史课，重构为「**看 → 练 → 问 → 创**」四层递进的实践课堂，由生成式 AI 驱动，由真实课堂验证。

四层教学法是底层方法论，**不是顶层导航**。顶层呈现给学生的是一个完整的课堂平台。

## 平台五大模块

| 模块 | 职责 |
| --- | --- |
| 首页 | 学情概览、今日课表、推荐课程、平台公告 |
| 课程中心 | 按学段/年级/单元浏览课程，进入"看练问创"四层学习 |
| 我的学习 | 已选课程、学习进度、笔记、作业、错题与回放 |
| 实践课堂 | 决策推演、沙盘剧本、即时反馈与课堂任务 |
| 个人中心 | 账号信息、学习偏好、设置、消息中心 |

每一节课内部都按「看 · 沉浸叙事 → 练 · 沙盘推演 → 问 · 双模智者 → 创 · 知识谱系」的四层流程组织，环环相扣、逐步递进。

## 技术栈（保持不变）

- 前端：React 18 + Vite 5 + TypeScript 5 + Ant Design 5 + React Router 6 + Zustand
- 后端：Python 3.12（强制）+ FastAPI + Pydantic v2 + SQLAlchemy 2.0 + SQLite（开发）
- 包管理：pnpm 9 / Node 20 LTS / uv 或 venv
- 设计：Pencil（`assets/design/*.pen`）
- 基础设施：Docker Compose（中长期接入 Postgres / Redis / 向量库）

## 仓库结构

```
.
├── apps/
│   ├── web/                  前端平台壳（5 模块）
│   └── api/                  后端 FastAPI（5 模块占位 + 持久化）
├── packages/
│   └── shared/               前后端共享类型与常量
├── services/
│   └── persistence/          SQLAlchemy + SQLite 持久化层
├── infra/                    docker-compose 与基础设施
├── assets/design/            Pencil 设计稿（.pen）
├── muban/                    可复用页面 / 区块模板（开发参考）
├── docs/                     ADR 与设计决策
├── UI/                       美术绘制的 UI 视觉稿
└── todo/                     立项申报书与初始引导
```

> 课程级业务（看练问创各自的具体引擎、剧本、人物语料）在框架打稳后，按课程一节一节追加到 `services/` 与 `apps/api/routers/` 中。

## 视觉规范

- 主题色：深海军蓝 `#0B1E3A` 底 / 米白 `#F5E6CC` 文 / 金色 `#D4A95C` 强调
- 字体：标题"霞鹜文楷 / 思源宋体"，正文"思源黑体"
- 风格：古典中式 + 现代教育平台，禁止中英混排，禁止花哨配色

## 快速启动

### 先决条件
- Node.js 20 LTS · pnpm 9
- Python 3.12（强制）

### 启动后端
```powershell
cd apps/api
python -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".\.venv\Scripts\uvicorn.exe" main:app --reload --port 8000
```
后端文档：`http://127.0.0.1:8000/docs`

### 启动前端
```powershell
cd apps/web
pnpm install
pnpm dev
```
前端：`http://127.0.0.1:5173`

## 提交规范

- 提交信息：`v大.中.小 - 中文版本说明`，例如 `v0.1.0 - 平台五模块壳层落地`
- 微小修复合并入下一次正式提交
- 详见 [Development_Spec.md](Development_Spec.md)

## 许可

待定。在确定许可前，仓库内容仅供 Chronovita 团队内部研发使用。
