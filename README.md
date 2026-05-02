# 史脉 Chronovita

> 面向中国历史学科的「未来课堂」沙盘推演平台 —— 让固化的史册化作可干预、可推演、可创造的因果时空。

[远端仓库](https://github.com/falling-feather/Chronovita) · [开发文档](Development_Spec.md) · [研发路线](Roadmap.md) · [项目总规划](docs/PROJECT_PLAN.md)

## 项目愿景

落实国家「人工智能 + 教育」与「文化数字化」双重战略，将传统历史教学中「时空不可逆、宏观难感知、决策不可验」的客观困境，重构为「情境模拟 — 变量决策 — 史实校验 — 架构重组」的连续推演闭环。以生成式人工智能驱动的「看 — 练 — 问 — 创」四段式实践教学，引导学生从被动记忆走向主动思辨。

## 核心业务架构

| 模块 | 主张 | 关键技术 |
| --- | --- | --- |
| 看 · 沉浸式叙事生成 | 历史文本 → 高保真微视频 | Prompt 链 · ControlNet 视觉约束 · Stable Diffusion · AnimateDiff · 少样本声线克隆 |
| 练 · 沙盘推演 | 学生干预历史变量，推演平行时空 | DAG 历史因果拓扑 · 状态压缩 DP · LLM 转移函数 · RAG 史实校验 |
| 问 · 双模态智能体 | 历史人物同伴与考古专家无缝切换 | 双 Persona 系统提示 · RAG 召回 · 规则过滤 · 轻量审核三层防幻觉 · 语音 ASR/TTS |
| 创 · 知识谱系 | 低代码画布生成个性化知识图谱 | 拖拽式节点画布 · 自动布局 · 学习行为分析 · 量化教学评估 |

## 仓库结构

```
.
├── apps/
│   ├── web/                  前端（React + Vite + TypeScript）
│   └── api/                  后端（Python FastAPI）
├── packages/
│   └── shared/               前后端共享类型与常量
├── services/
│   ├── recall/               看 · GenAI 工作流编排
│   ├── sandbox/              练 · DAG 推演引擎
│   ├── agent/                问 · 双模态智能体与 RAG
│   └── canvas/               创 · 知识谱系画布
├── infra/                    docker-compose 与基础设施
├── assets/design/            pencil 设计稿（.pen）
├── docs/                     设计文档与决策记录
└── todo/                     立项申报书与初始引导
```

## 快速启动

### 先决条件

- Node.js 20 LTS · pnpm 9
- Python 3.12（虚拟环境优先）
- Docker Desktop（用于本地 Postgres / Redis / Chroma）

### 启动基础设施

```powershell
docker compose -f infra/docker-compose.yml up -d
```

### 启动后端

```powershell
cd apps/api
python -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".\.venv\Scripts\uvicorn.exe" main:app --reload --port 8000
```

后端文档默认位于 `http://127.0.0.1:8000/docs`。

### 启动前端

```powershell
cd apps/web
pnpm install
pnpm dev
```

前端默认位于 `http://127.0.0.1:5173`。

## 视觉与文案规范

- 总体调性：纯中式古典 —— 纸麦底色、黑蒋色主调、宋/楷体标题。
- 文案：全中文沉浸式排版，禁止中英文混排。
- 字体：思源宋体 · 霞鹜文楷 · 等宽用霞鹜文楷等宽。

## 提交与分支规范

- 提交信息：`v大版本.中版本.小版本 - 中文版本说明`，例如 `v1.0.0 - 项目骨架与初始化文档落地`。
- 微小修复不单独提交，合并入下一次正式提交。
- 中版本递增时合并相关分支历史，主干仅保留中版本与大版本节点。
- 详见 [Development_Spec.md](Development_Spec.md) 的「编码与提交规范」章节。

## 鸣谢与合作

- 河北定州中学理科教师团队（应用支持与推广建议）
- 杭州市钱塘区新围小学（AI 教育宣传片合作）
- 中国新闻社（「马可波罗的运河奇遇」联合创作）
- 扶摇玖翼、网易（AI 影像工业化管线合作意向）

## 许可

待定。在确定许可前，仓库内容仅供 Chronovita 团队内部研发使用。
