# Chronovita 项目总规划 · Project Plan

> 本文是本会话产出的整体项目规划文档，与 [Roadmap.md](../Roadmap.md) 偏向时间维度不同，本文偏向于「方法论、决策、阶段任务、验证方式」。

---

## 1. 立项依据收束

来源：《浙江传媒学院大学生创新训练项目申报书（钮玉彬）》。

- 战略背景：教育数字化战略行动 2.0、《「人工智能 + 教育」行动计划》、《国家文化数字化战略意见》。
- 学科困境：传统历史教学受限于静态图文，时空不可逆，宏观演进难感知。
- 项目主张：以 GenAI 驱动的「看-练-问-创」四段式实践教学，构建可量化、可干预的动态历史沙盘。
- 团队既有资产：
  - 历史方向可视化互动平台底层节点渲染引擎（已成熟跑通）
  - 基于 Flux + Lora 的 ComfyUI 工作流
  - 河北定州中学的应用支持
  - 多篇国际会议论文（VRT 2025、AIGC 2025、ICIMH 2025）
  - 与扶摇玖翼、网易、央视/中新社的内容合作经验

## 2. 关键决策记录（ADR 摘要）

| 决策 | 选择 | 理由 |
| --- | --- | --- |
| 仓库根 | `d:\代码玩具测试\history` | 与现有 `todo/` 共存，远端仍指向 falling-feather/Chronovita |
| 前端栈 | React + Vite + TypeScript + Ant Design 5 | 生态、HMR、类型、组件库齐备，加速 MVP |
| 后端栈 | Python FastAPI + Pydantic v2 + SQLAlchemy 2.0 | 异步、类型安全、自带 OpenAPI |
| 数据层 | PostgreSQL 16 + Redis 7 + Chroma | 关系/缓存/向量分层；Chroma 短期 → Milvus 中期 |
| Python | 3.12 强制 | 规避 3.14 与 pydantic-core/orjson Rust 编译失败 |
| UI 调性 | 纯中式古典 · 纸麦底色 · 黑蒋色主调 · 宋/楷体 | 沉浸式历史主题 |
| 文案规范 | 全中文，禁止中英文混排 | 沉浸感与一致性 |
| 代码注释 | 不写注释 | 团队既有约定 |
| Git 提交 | `v大.中.小 - 中文说明` | 团队既有约定 |
| 设计工具 | pencil MCP（.pen 文件） | 与对话环境无缝集成 |
| 首次推送 | 先 `git pull --rebase`，再 push | 避免覆盖远端已有内容 |

## 3. 实施阶段总览

```
阶段 A 工程骨架 ──┐
                  ├─ 阶段 E v1.0.0 提交
阶段 B 三份文档 ──┤
                  │
阶段 C 四份 .pen ─┘
                  │
阶段 D 模块技术细化（写入 Development_Spec）
```

### 阶段 A · 工程骨架（已落地）

- `.gitignore`、根 README、Roadmap、Development_Spec、本规划
- `apps/web` 前端骨架：Vite + React + TS + AntD + Zustand + 中式 token
- `apps/api` 后端骨架：FastAPI + Pydantic + 四模块 router 占位
- `services/{recall,sandbox,agent,canvas}` 服务包占位
- `packages/shared` 共享类型占位
- `infra/docker-compose.yml`：postgres + redis + chroma
- `docs/adr/` 决策记录目录

### 阶段 B · 三份核心 Markdown（已落地）

- [README.md](../README.md) · 项目愿景、四模块速览、快速启动
- [Development_Spec.md](../Development_Spec.md) · 文档分级、架构、接口契约、模块清单、规范
- [Roadmap.md](../Roadmap.md) · 短中长期、优化构筑记录专区

### 阶段 C · 四份 .pen 设计占位（已落地）

位于 `assets/design/`：

1. `01-看-沉浸叙事.pen` · 历史微视频播放页 + 关键帧时间轴
2. `02-练-沙盘推演.pen` · DAG 节点画布 + 变量调节面板 + 平行历史分支结果
3. `03-问-双模态智能体.pen` · 同伴/专家对话窗 + 模式切换 + 语音波形
4. `04-创-知识谱系.pen` · 拖拽画布 + 学习卡片库 + 自动生成预览

阶段 C 仅留占位框架，等待用户后续提供布局范例后细化。

### 阶段 D · 四模块技术细化

详见 [Development_Spec.md](../Development_Spec.md) 第 3、6、7 节。本文不重复。

### 阶段 E · 首版提交

- 提交信息：`v1.0.0 - 项目骨架与初始化文档落地`
- 推送策略：`git pull --rebase origin main` → `git push origin main`
- 推送前需用户二次确认，避免覆盖远端已有内容。

## 4. 验证清单

- [x] `.gitignore` 含 Node / Python / 媒体大文件 / 数据卷
- [x] 三份核心 Markdown 在仓库根
- [x] 四个 .pen 文件在 `assets/design/`
- [x] 前端骨架 `pnpm install && pnpm dev` 可在 5173 启动
- [x] 后端骨架 `uvicorn main:app --reload` 在 8000 启动且 `/docs` 显示四模块 endpoint
- [x] `docker compose -f infra/docker-compose.yml up -d` 三件套健康
- [x] UI 抽样无中英文混排
- [x] 全工程基本无行级注释
- [x] Git log 仅见 `v1.0.0 - 项目骨架与初始化文档落地`

## 5. 显式范围

**本次包含**：
- 仓库初始化与 Git 规范
- 三份核心 Markdown 与本总规划
- 四个 .pen 占位
- 四模块工程骨架与接口契约
- docker-compose 基础设施

**本次不包含**（后续单独迭代）：
- 实际 GenAI 模型推理代码（ControlNet 微调等）
- DAG 状压 DP 完整实现
- RAG 知识库灌库与评测集
- UI 视觉细节（等待用户布局范例）
- 试点学校接入与教师培训

## 6. 待用户后续输入

1. UI 布局范例（用于细化 4 个 .pen）
2. 「大禹治水」DAG 的具体节点与变量取值
3. 双 Persona 的初始 system prompt 草稿
4. 首批知识库语料（建议教材 + 权威史料）
5. 远端仓库是否有历史内容、是否允许首次 force-with-lease 推送

## 7. 与申报书的对照

- 立项依据 § 1 → 本文 § 1
- 研究内容四模块 → Development_Spec § 3
- 创新点（工作流 / 状态机沙盘 / 双模态智能体 / 学生创造 / Web 部署） → Development_Spec § 3 + § 7
- 拟解决问题（演进静态化 / 共情缺失 / AI 不准确 / 个性化缺失） → Development_Spec § 3 + § 11
- 进度安排 2026-05 ~ 2027-04 → Roadmap § 短/中/长期
- 已具备条件（节点渲染引擎、历史素材库、教师团队认可） → Development_Spec § 3.4 + README 鸣谢
