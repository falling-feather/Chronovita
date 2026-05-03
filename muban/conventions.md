# 模板规范

## 1. 文件命名
- 页面组件：`PascalCase.tsx`，导出 `default function PageName()`。
- 公共子组件：放在 `apps/web/src/components/`。
- 模块化业务：`apps/web/src/modules/<module>/`。

## 2. 路由
- 顶层 5 个：`/`、`/courses`、`/learning`、`/practice`、`/profile`。
- 课程内子路由（待落地）：`/courses/:courseId`、`/courses/:courseId/lesson/:lessonId/:layer`，
  其中 `:layer ∈ { watch | practice | ask | create }` 对应"看 · 练 · 问 · 创"。

## 3. 间距
- 顶部 padding：`24px`（由 `<Content>` 提供，不在页面内重复）。
- 卡片 padding：默认 `20px`，紧凑卡 `12px`。
- 区块之间：`marginBottom: 16/24/32`，从内向外递增。

## 4. 交互反馈
- **真实功能**：直接 `nav(...)` 跳转 / 修改本地状态，**不**弹 toast。
- **后端写操作**：`toast.success('已保存')` / `toast.error('保存失败：…')`。
- **未实装能力**：`toast.info('该能力将在 v0.X 接入')`，**不要**带 `[测试]` 字样。

## 5. 占位文案
- 标识当前是占位的句子用一段 `color: var(--text-disabled), fontSize: 11` 的小字。
- 不在 UI 上写"假数据"三个字。

## 6. 表单提交（占位期）
- 写 `localStorage` 即可，key 前缀 `chronovita.`，例如 `chronovita.profile`。
- 后端真实接入后改为 `services/api/*` 调用，删除 `localStorage` 兜底。
