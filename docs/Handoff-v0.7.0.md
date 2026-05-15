# 项目状态快照 · V0.7.0 交接

> 给下一位接手智能体看的「当前状态 + 下一步任务」单一文件。
> 写于：V0.7.0（commit `f4cb3e2`）之后，「问」板块已完成、规划文档已落地。

---

## 1. 当前已完成（截至 V0.7.0）

### 1.1 框架与视觉
- 5 模块路由全部联通：`/` `/courses` `/learning` `/practice` `/profile`
- 课程中心改为「SVG 历史地图入场 + 时代切换」（详见 [Map-Design.md](Map-Design.md)），都城点击联动课程过滤
- 个人中心 localStorage 写读、未实装能力统一文案

### 1.2 课程数据（V0.2.x）
- `services/courses/`：6 大时代 + 14 朝代板块，共 48 节正文（教材级文本，含 figures / keywords / sandbox_id / seed_canvas）
- 接口：`GET /api/v1/courses/eras`、`/courses?era=&section=&q=`、`/courses/:id`、`/courses/:cid/lessons/:lid`

### 1.3 「练」saga 互动剧本（V0.3.x ~ V0.6.x）
- `services/saga/__init__.py`（约 100KB）：48 个剧本模板覆盖全朝代
- 流式协议：`POST /practice/saga/{id}/act` 正文 + 末尾 `\n\n[META]{json}` 携带 choices/flags/ended
- 收束触发器、persona 点名、防循环、选项缺失强制清空（V0.6.0 ~ V0.6.3）
- 压力测脚本：默认 7 轮，校验收束/记忆压缩/人物一致

### 1.4 「问」跨时对话（V0.7.0）
- 切到 `deepseek-v4-pro`，与 saga 的 `v4-flash` 并存，统一走 `services/llm/stream_chat(model=...)`
- 双 persona prompt：
  - **expert**：资深研究者+中学教师，学界共识/严禁编造/末行延伸阅读
  - **peer**：第一人称扮演真实历史人物，硬约束"不预言后世"，文言+白话
- 前端 `LessonAsk`：同窗对象下拉（候选自 `lesson.figures`），切换 persona/对象自动重置欢迎语
- 修复 SSE chunk 重复 bug：StrictMode 下 setState 函数被双调用，原代码 mutate 同一对象致每个汉字写两次 → 改为不可变更新

### 1.5 「创」知识画板（V0.3.x）
- React Flow 画布 + 节点云端持久化（`PUT /practice/canvas/:lid`）
- AI 扩充：`POST /practice/canvas/generate` 调用 LLM 生成 6-9 节点 + 关系，前端去重合并

### 1.6 LLM 适配层
- 入口 `services/llm/__init__.py`，OpenAI 兼容协议，DeepSeek + mock 双 provider
- 双模型策略：saga=v4-flash（速度），ask=v4-pro（准确度）
- `GET /practice/llm/info` 同时返回 `provider` 与 `ask_provider`，前端 Tag 实时显示

### 1.7 文档
- [README.md](../README.md)、[Roadmap.md](../Roadmap.md)、[Development_Spec.md](../Development_Spec.md) 已同步到 V0.7.0
- [docs/Planning.md](Planning.md)：短/中/长期规划（**新增于本次**）
- ADR 仍保留 0001/0007/0011 三份，新决策待补

---

## 2. 已知遗留 / 待办

| 项 | 影响 | 优先级 |
| --- | --- | --- |
| 学习进度未持久化（`/learning` 占位） | 用户切机/刷新丢进度 | P0 |
| 「看」板块缺 AI 旁白/视频 | 课程缺第一层入口体验 | P1 |
| sandbox 仅商鞅一个剧本 | "练"层多入口与 saga 重复，待整合 | P1 |
| 画板拖动后需手动「保存到云端」 | 易丢失 | P1 |
| 没有教师后台 / 班级 / 多用户 | 无法真用于课堂 | P2 |
| 没有 ADR 0012+ 记录 saga / ask 设计决策 | 历史可追溯性弱 | P2 |
| 部署仅 Vite/uvicorn dev，缺 Docker/Postgres | 无法生产运行 | P2 |

详细推进顺序见 [docs/Planning.md](Planning.md)。

---

## 3. 关键技术约定（不要踩坑）

### 3.1 工程
- **Node 20 LTS + pnpm 9**；前端目录 `apps/web/`
- **Python 3.11/3.12**（避免 3.14，部分依赖缺 wheel）；后端目录 `apps/api/`，仓库根 `.venv/`
- 提交规范：`V大.中.小 中文提交信息`（三段必填）；中版本递增建 `backup/v0.X.0` 分支
- PowerShell 提交中文：`git commit -F message.txt`（UTF-8 no BOM）；不要直接 `-m "中文"`

### 3.2 前端
- AntD 静态 `message.X()` 取不到主题，已用 `apps/web/src/utils/toast.ts` Proxy + MessageBinder 桥接
- localStorage 走 `apps/web/src/utils/storage.ts`，命名空间 `chronovita.`
- 多列布局优先 CSS Grid `minmax(0,1fr)`
- **SSE 流式更新 React 状态时务必不可变更新**——StrictMode 下 setState 函数会被双调用，mutate 同一引用会重复写入（V0.7.0 LessonAsk 踩过）

### 3.3 LLM
- `services/llm.stream_chat()` 异步迭代；不要在业务层直接 httpx
- saga 默认 v4-flash（速度），ask 显式 `model=settings.deepseek_model_pro`
- `.env` 配置 `CHRONO_DEEPSEEK_API_KEY` / `CHRONO_LLM_PROVIDER=deepseek`，**永不入库**
- 改 `services/*` 后 uvicorn watchfiles 不一定捕获 → touch `apps/api/main.py` 或 kill+重启

### 3.4 浏览器实测
- Playwright MCP `pageId` 在跨会话间不保留，每次新开页面
- 关键 SSE 接口都需要在线实测，不能只看响应码

### 3.5 PowerShell UTF-8
- `Set-Content -Encoding UTF8` 会写 BOM；改用 `[System.IO.File]::WriteAllText($p, $c, (New-Object System.Text.UTF8Encoding($false)))`
- `Get-Content` 默认 ANSI 读，UTF-8 中文会乱码

---

## 4. 立即可做的小事

1. 浏览顶层文档（README/Roadmap/Spec/Planning）确认无冲突
2. `apps/api/.env` 是否已有 `CHRONO_DEEPSEEK_API_KEY`（不在则向用户索取）
3. 启动后端：`& ".\.venv\Scripts\python.exe" -m uvicorn main:app --reload --host 127.0.0.1 --port 8000`（cwd=apps/api）
4. 启动前端：`cd apps/web; pnpm dev`
5. 按 [docs/Planning.md](Planning.md) §短期 第一项开干
