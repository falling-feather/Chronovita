# 课程中心地图入场页 · 设计文档

> 路径：`apps/web/src/pages/CoursesPage.tsx` + `apps/web/src/pages/courses/`
> 首发：v0.2.2 — v0.2.6
> 目标：以"中国版图 + 时间轴"作为课程中心入场媒介，让用户在 5 秒内理解"时代变换"，并通过点击都城进入相应课程。

---

## 1. 子模块清单

| 文件 | 职责 |
|---|---|
| `courses/eraMap.ts` | 纯数据层：时代叠加（都城/事件/边疆/路径） + 中国轮廓 + 9 大水系几何 |
| `courses/EraMapView.tsx` | SVG 渲染层（默认导出 `EraMap`），分静态层 + 时代叠加层 |
| `courses/EraTimeline.tsx` | 6 段位时间轴 + 键盘 ←/→ |
| `CoursesPage.tsx` | 容器 + URL 状态 + 后续课程网格 |

`EraMap` 通过 `React.lazy` + `Suspense` 懒加载，首屏更轻。

---

## 2. 坐标系约定

- **viewBox**：`0 0 1000 720`（4:3 偏宽，便于横向铺开"东海岸"）
- **所有几何（轮廓/河流/都城/路径）共享同一坐标系**，单位为像素
- 经纬度 → 像素：当前为手摇校准（未做正式投影），覆盖范围约 73°E—135°E、18°N—54°N
- **添加新都城/路径时**，对照 [CHINA_OUTLINE](apps/web/src/pages/courses/eraMap.ts) 的关键拐点取舍位置

---

## 3. 数据模型

### 3.1 EraOverlay

```ts
interface EraOverlay {
  id: string;            // 与后端 era_id 对齐：prequin/qinhan/weijin/suitang/songyuan/mingqing
  name: string;          // 中文名 「秦汉」
  period: string;        // 「前 221 — 220」
  anchor: number;        // 0—1 时间轴归一化锚点
  hue: { primary; secondary }; // 当代主色（背景径向渐变 + tracks/halo 取色）
  blurb: string;         // 一句话气韵
  cities: EraMapCity[];  // 都城与节点城市
  events: EraMapEvent[]; // 时点 (year, text) — 负数为公元前
  frontier: string;      // 边疆短语 「北抗匈奴 · 西通西域」
  tracks?: EraMapTrack[];// 当代历史路径（长城/丝路/运河/航路…）
}
```

### 3.2 EraMapCity

```ts
interface EraMapCity {
  name: string;     // 古名 「咸阳」
  x: number; y: number;
  modern?: string;  // 今名 「咸阳」/「西安」
  capital?: boolean;// 是否当代主都
}
```

### 3.3 EraMapTrack

```ts
interface EraMapTrack {
  id: string; name: string;
  geometry: string; // SVG path d
  color: string;
  dash?: string;    // virtual = '6 6'，长城/运河可加大
  width?: number;   // 主线 stroke width
}
```

渲染：每条 track 实际画两条 path（外发光底线 + 流动主线），主线 dash flow 由 CSS keyframes 驱动（无 JS 动画）。

### 3.4 中国轮廓 / 水系

- `CHINA_OUTLINE`：单 path 字符串，含 3 个 subpath（大陆 + 海南岛 + 台湾岛），全部用 cubic bezier 平滑
- `RIVERS`：9 条主水系（黄/长/珠/雅鲁/澜沧/松花/辽/海/淮），其中黄河长江描更粗

---

## 4. 渲染分层（自下而上）

```
chrono-eramap (背景径向渐变 = era.hue)
└── <svg>
    ├── <StaticLayer/>            ← React.memo，时代切换时不重绘
    │   ├── 海面 seaGlow
    │   ├── 陆地阴影 + 陆地（含海南、台湾）
    │   ├── 9 条水系
    │   └── 经纬装饰刻度
    ├── chrono-era-tracks         ← key={pulseKey} 时代切换重触发动画
    │   └── 每条 track：外发光底线 + 主线（dash flow）
    ├── chrono-era-overlay        ← key={pulseKey}
    │   └── 都城节点：halo（capital 限定）+ 圆点 + 文字（描边底）
    └── 右下水印：era.name + period（半透明）
```

---

## 5. 交互闭环

| 触发 | 行为 |
|---|---|
| 点击时间轴段位 / 按 ←/→ | URL `?era=` 变更 → 地图叠加层重渲（保留静态层） |
| 点击地图都城 | URL `?city=&cityModern=` → 课程网格按地名过滤 → 平滑滚到网格 |
| 点击 chip ✕ | 清除该过滤维度 |
| 点击「查看全部」 | 锁定时代过滤为当前时代 |
| 点击侧栏精选课程卡 | 进入课程详情 `/courses/:id` |

URL 状态完全可分享，刷新后保持。

---

## 6. 性能与可达性

- 地图组件代码分包（`React.lazy`），首屏不依赖
- 静态层 `React.memo` 隔离，时代切换时仅更新叠加层
- 全 SVG，不依赖图片或 canvas，移动端缩放无锯齿
- 所有动画由 CSS keyframes 驱动（`chrono-city-in/halo/track-in/track-flow`），不阻塞主线程
- `<svg role="img" aria-label="${era.name}时代地图">`，键盘可达
- 响应式：≤ 1100px 宽度自动堆叠为单列

---

## 7. 扩展点（后续路线）

- [ ] 时代切换时的色调过渡（背景渐变 transition + tracks crossfade）
- [ ] 时间轴拖拽手柄 Slider（连续滑动，触发 anchor 插值）
- [ ] tracks hover tooltip（替代 `<title>`）
- [ ] 都城 hover 卡片（朝代沿革 + 关联人物）
- [ ] 后端 city → courses 索引（替代当前前端模糊匹配）
- [ ] 用户实际定位 → 显示"你所在地的历史"侧栏

---

## 8. 数据更新约定

- 增加新时代：在 `ERA_OVERLAYS` 末尾追加，并在 [EraTimeline.tsx](apps/web/src/pages/courses/EraTimeline.tsx) 的 stops 列表中保持 6 段以内（超出需重做时间轴布局）
- 城市坐标必须落在 `CHINA_OUTLINE` 内，肉眼校验即可
- tracks geometry 用 `M ... C ... C ...` 连续 cubic 写法，便于 dash flow 均匀
- 修改 `CHINA_OUTLINE` 时务必复核所有现有城市 / tracks 是否仍在合理位置
