# 模板库 · muban/

> 这里收集 Chronovita 平台所有**可复用的页面 / 区块模板**，作为后续课程页、子模块页、活动页面的参考骨架。
> 这些模板**不会**直接被 `apps/web` 引用，它们是 *设计参考*，由开发者按需复制改造。

## 目录约定

```
muban/
├── README.md                  本文件
├── templates/                 React + AntD 页面模板（.tsx）
│   ├── PageShell.tsx          基础页面外壳（标题 + 副标题 + Slot）
│   ├── ThreeColumnLayout.tsx  左目录 / 中主体 / 右辅助 三栏（仿课程中心）
│   ├── StatTabsList.tsx       顶部统计 + Tab 切换 + 列表（仿我的学习）
│   ├── FilterCardGrid.tsx     Chip 筛选 + 卡片网格（仿实践课堂）
│   └── SidebarFormPanel.tsx   左侧菜单 + 右侧表单（仿个人中心）
└── conventions.md             命名 / 字号 / 间距 / 配色规范
```

## 使用方法

1. 新做一个课程内子页面或新模块页面时，先在 `muban/templates/` 找一个最接近的模板。
2. 复制到 `apps/web/src/pages/` 或 `apps/web/src/modules/` 下，按需改造。
3. 改造完成的页面，如果具备**普适价值**（不绑定具体业务），可反向沉淀回 `muban/`。

## 视觉规范速查

| 项 | 取值 |
| --- | --- |
| 页面最大宽 | `1392px`（首页/学习/实践/个人）/ `1536px`（课程中心三栏） |
| 主背景 | `var(--bg-page)` 米白 |
| 卡片背景 | `#FFFFFF` + `var(--border-soft)` 边 |
| 标题字号 | h1 `26px` · h2 `22px` · h3 `18px` · h4 `16px` |
| 行内强调 | `var(--accent-gold)` `#D4A95C` |
| 暗色卡片 | `chrono-card-dark`（深海蓝 + 米白文字） |

完整 CSS 变量见 `apps/web/src/styles/global.css`。
