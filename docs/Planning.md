# Chronovita 演进规划 · Planning

> 与 [Roadmap.md](../Roadmap.md) 阶段表呼应：Roadmap 记录"做了什么"，本文件记录"接下来做什么、为什么、怎么做、怎么验收"。
> 当前基线：**V0.7.0**。短期面向 v0.8.x，中期面向 v0.9 ~ v1.x，长期面向 v2.x+。

---

## 短期规划（v0.8.x · 系统化打磨）

聚焦"把现有体验做扎实"，让一个学生从首页进入到完成一节课的闭环可用。

### S1. 学习进度持久化　【优先级 P0】
- **为什么**：刷新/换设备后无法继续，「我的学习」目前是占位假数据。
- **怎么做**：
  - 后端：在 [services/persistence/db.py](../services/persistence/db.py) 增加 `LessonProgress(user_id, lesson_id, layer, status, last_visited_at)`；先单用户 `default`，多用户在中期接入后扩
  - 后端：在 [apps/api/routers/learning.py](../apps/api/routers/learning.py) 暴露 `GET /learning/progress`、`POST /learning/progress/touch`
  - 前端：进入 `LessonShell` 时打点 `touch`；离开时记录最后 layer
  - 前端：[LearningPage](../apps/web/src/pages/LearningPage.tsx) 接通真实数据，"今日继续"取最近 1 条
- **验收**：刷新后能恢复"上次到 X 课 X 层"；卸载浏览器缓存后从后端拉回相同进度。

### S2. 画板自动保存　【P0】
- **为什么**：[LessonCreate](../apps/web/src/pages/lesson/LessonCreate.tsx) 当前需手动点"保存到云端"，断网或忘点即丢。
- **怎么做**：debounce 800ms 监听 nodes/edges 变化 → 后台静默 `PUT /practice/canvas/:lid`；右上角 chip 显示"已保存于 HH:mm"。
- **验收**：拖动节点 1 秒后状态自动同步；toast 不打扰；网络失败显示一次降级提示。

### S3. 首页接入真实数据　【P0】
- **为什么**：[HomePage](../apps/web/src/pages/HomePage.tsx) 当前是静态占位，与 LearningPage 数据脱节。
- **怎么做**：复用 S1 的 progress 接口，"继续学习"取最近 1 条；"今日推荐"按时代 cursor 推下一节。
- **验收**：首屏卡片可点击直达正确 lesson + layer。

### S4. 「同窗」自定义对象输入框　【P1】
- **为什么**：当前下拉只列 `lesson.figures`，学生想问"周公"但当节没列出就无法选。
- **怎么做**：在下拉末尾加"自定义…"项，弹 `Modal` 输入姓名 + 简介（一句话），后端 `peer` prompt 拼入；本地缓存常用 5 个。
- **验收**：自定义"周公"后能正常对话且不预言后世；下次仍出现在下拉中。

### S5. 专家末尾延伸阅读卡片化　【P1】
- **为什么**：现在末行是普通文本，关键词混在叙述中不显眼。
- **怎么做**：在 expert prompt 强约束 `[FURTHER]\n- 主题|一句话` 行；前端流结束后解析渲染为 AntD `Card.Grid`。
- **验收**：连续 5 次提问，渲染成功率 ≥ 4/5；解析失败回退纯文本不报错。

### S6. SSE 错误提示统一化　【P1】
- **为什么**：[streamAsk](../apps/web/src/utils/api.ts) / `streamSagaAct` 失败现仅把异常文本拼进 chunk，体验差。
- **怎么做**：抽出 `withSseFallback` 包裹器：成功照常；失败 toast.error + 把已收到的 chunk 标记斜体灰字注释「（连接中断，建议重试）」。
- **验收**：手动断网测试时，UI 不出现裸异常字符串。

### S7. 文档同步检查　【P2】
- **为什么**：本次发现 README/Spec/Roadmap 都落后 6 个版本，缺自动提醒。
- **怎么做**：加 `tools/check_docs_freshness.py`：扫描 `git tag --sort=-creatordate` 最大版本号 vs README 头部声明版本，不一致则 stderr 告警；可选挂 pre-commit。
- **验收**：故意降版本号能触发警告。

---

## 中期规划（v0.9.x ~ v1.x · 内容深化与多角色）

### M1. 「看」AI 旁白与微视频
- 第一阶段：每节"keywords + 概要"喂给 LLM 生成 3 段口播脚本 + 关键画面文字描述；前端用 TTS 直接朗读
- 第二阶段：脚本 + 配图（先静态合成，后续接 Sora-like）→ MP4 缓存；CDN 化
- 验收：每节"看"层至少 1 段可播放音频，时长 60-120 秒

### M2. 关键词词汇卡 + 正文双向高亮
- 鼠标 hover 正文中的关键词，右侧词汇卡高亮；点击词汇卡反向定位正文
- 数据来源：lesson.keywords，已存在
- 验收：48 节全部生效，无错位

### M3. Sandbox 剧本扩充
- 目标：每个朝代板块至少 1 个决策沙盘（当前仅商鞅）
- 流程：选取朝代标志性决策 → 设计 3 阶段 5 选项 → 注入 [services/sandbox/__init__.py](../services/sandbox/__init__.py)
- 验收：14 朝代覆盖率 100%，每剧本通过烟雾测

### M4. 教师后台基础
- 班级管理 / 作业布置 / 学生 saga 回放查看
- 后端新增 `apps/api/routers/teacher.py`，前端新增 `/teacher` 路由（与 5 模块平级，按角色路由分流）
- 验收：教师能看到任一学生的最近 saga 完整对话流

### M5. 多用户认证
- 轻量 JWT + SQLite users 表；不接 OAuth
- 前端 AuthGuard + 用户上下文；所有 API `Depends(current_user)`
- 验收：教师/学生区分；个人数据隔离

### M6. 我的学习面板深化
- 笔记（Markdown 编辑）/ 错题（saga 回放归档）/ 创意画板列表
- 复用 S1 的 progress + 新增 `notes` 表
- 验收：3 子页可写可读

### M7. 课程内容人审工作流
- 教师可对单节标注"已审/待修/退回"，附评语
- 验收：审校状态显示在课程卡片上

---

## 长期规划（v2.x+ · 平台化）

### L1. 数据库与缓存升级
- SQLite → Postgres；Redis 缓存 LLM 流热门会话
- 迁移工具：`alembic`

### L2. 容器化部署
- `infra/docker-compose.yml` 已有骨架；补 `Dockerfile.api / Dockerfile.web` 与 nginx 反代
- CI：GitHub Actions build + push image

### L3. 课程内容 RAG
- pgvector + 课程文本切片入库；ask 在 system prompt 引证课文段落 + 行号
- 验收：专家回答中可见"（见《XX节》第N段）"引证标注

### L4. 多 LLM 适配
- OpenAI / Claude / 本地 Ollama；`services/llm/` 加 provider；统一 OpenAI 兼容协议
- 验收：env 切换 `CHRONO_LLM_PROVIDER` 即可换厂商

### L5. 移动端响应式
- 课程地图、saga 对话、画板均需重排
- 优先 PWA 而非原生

### L6. 课程内容 CMS
- 教师在线编辑 lesson 文本与 saga 模板，无需改代码部署
- 验收：教师上传新章节 5 分钟内学生可见

### L7. A/B 与课堂数据看板
- 同节课 saga 不同收束触发器对比转化率
- 验收：admin 看板能展示选项分布与平均轮次

### L8. 国际化
- 先做繁体中文（受众广），框架 `react-i18next`
- 验收：UI 与课程文本独立翻译

---

## 阶段映射表

| 短期 | 对应 Roadmap 阶段 4 | 节奏 |
| --- | --- | --- |
| S1-S7 | 「系统化打磨」v0.8.x | 1-2 周/项，串行优先 S1→S2→S3 |

| 中期 | 对应 Roadmap 阶段 5-6 | 节奏 |
| --- | --- | --- |
| M1-M2 | 「看」板块完成 v0.9.x | M1 跨 1-2 个版本 |
| M3 | 「练」深化 v0.9.x | 与 M1 并行 |
| M4-M5 | 教师后台 v1.x | 中版本，触发 backup 分支 |
| M6-M7 | 教学闭环 v1.x | 接在 M5 之后 |

| 长期 | 对应 Roadmap 阶段 7 | 节奏 |
| --- | --- | --- |
| L1-L8 | 部署/扩展 v2.x+ | 按需启动 |

---

## 决策原则

1. **不与现有约定冲突**：5 模块路由、`V大.中.小` 提交、Python 3.11/3.12、saga/ask 双模型策略不动摇
2. **优先做闭环 > 优先做新功能**：S1-S3 闭合后再开 M 段
3. **每个短期项都有"如何回退"**：DB 改动写 alembic 脚本，前端改动隔离在新文件/分支
4. **LLM 相关变更必须有 mock 兜底**：保证离线能跑测试
