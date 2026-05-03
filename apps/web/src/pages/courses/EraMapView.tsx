// 时空地图入场组件 · 纯 SVG · v0.2.8
// v0.2.8：① 子时段（朝代切片）chip 切换 ② 鼠标滚轮缩放 + 拖拽平移 + 复位按钮
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CHINA_OUTLINE, RIVERS, MOUNTAINS, type EraMapCity, type EraOverlay } from './eraMap';

interface Props {
  era: EraOverlay;
  /** 选择城市时回调（传出完整 city 对象） */
  onCityClick?: (city: EraMapCity) => void;
  /** 当前激活的子时段 id（受控）；不传则不过滤 */
  activeSubEraId?: string | null;
  /** 子时段变化回调（用于父级保持 URL 同步等） */
  onSubEraChange?: (subEraId: string | null) => void;
  /** 点击「进入课程列表 ↓」时回调（父级负责滚动到课程区） */
  onJumpToCourses?: () => void;
}

const VW = 1000;
const VH = 720;
const MIN_W = 160;   // 最大放大 ~6.25×
const MAX_W = 1600;  // 缩到 0.625×

// 静态层抽离 → 时代切换时不重绘，避免 path 抖动
const StaticLayer = memo(function StaticLayer() {
  return (
    <>
      <defs>
        <radialGradient id="seaGlow" cx="0.55" cy="0.45" r="0.7">
          <stop offset="0%" stopColor="rgba(91,163,208,0.18)" />
          <stop offset="100%" stopColor="rgba(91,163,208,0)" />
        </radialGradient>
        <linearGradient id="landFill" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="rgba(244,236,220,0.96)" />
          <stop offset="100%" stopColor="rgba(220,206,178,0.88)" />
        </linearGradient>
        <filter id="landShadow" x="-10%" y="-10%" width="120%" height="120%">
          <feGaussianBlur stdDeviation="6" />
        </filter>
        <filter id="cityGlow" x="-200%" y="-200%" width="500%" height="500%">
          <feGaussianBlur stdDeviation="3" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <rect x="0" y="0" width={VW} height={VH} fill="url(#seaGlow)" />

      {/* 现代中国轮廓 — 作为备考底图（超淮、虚线） */}
      <path
        d={CHINA_OUTLINE}
        fill="none"
        stroke="rgba(11,30,58,0.12)"
        strokeWidth={1}
        strokeDasharray="3 5"
      />

      <g opacity={0.85}>
        {RIVERS.map((r) => (
          <path
            key={r.id}
            d={r.geometry}
            fill="none"
            stroke={r.color}
            strokeWidth={r.id === 'yellow' || r.id === 'yangtze' ? 2.4 : 1.4}
            strokeLinecap="round"
            opacity={r.id === 'yellow' || r.id === 'yangtze' ? 0.9 : 0.55}
          />
        ))}
      </g>

      {/* 山脉脊线 — v0.3.0 锯齿描边 */}
      <g opacity={0.55}>
        {MOUNTAINS.map((m) => (
          <path
            key={m.id}
            d={m.geometry}
            fill="none"
            stroke="#8B6F47"
            strokeWidth={1.8}
            strokeLinecap="round"
            strokeDasharray="1 4"
          />
        ))}
      </g>

      <g stroke="rgba(11,30,58,0.06)" strokeWidth={0.6}>
        {[160, 240, 320, 400, 480, 560, 640].map((y) => (
          <line key={`h${y}`} x1={0} y1={y} x2={VW} y2={y} />
        ))}
        {[150, 280, 410, 540, 670, 800].map((x) => (
          <line key={`v${x}`} x1={x} y1={0} x2={x} y2={VH} />
        ))}
      </g>
    </>
  );
});

interface ViewBoxState { x: number; y: number; w: number; h: number }
const INIT_VIEW: ViewBoxState = { x: 0, y: 0, w: VW, h: VH };

export default function EraMap({ era, onCityClick, activeSubEraId, onSubEraChange, onJumpToCourses }: Props) {
  const [pulseKey, setPulseKey] = useState(era.id);
  useEffect(() => { setPulseKey(era.id); }, [era.id]);

  // —— 视口（缩放 / 平移） ——
  const [view, setView] = useState<ViewBoxState>(INIT_VIEW);
  const svgRef = useRef<SVGSVGElement | null>(null);
  // 切换时代/子时段时复位视口
  useEffect(() => { setView(INIT_VIEW); }, [era.id, activeSubEraId]);

  const clampView = useCallback((v: ViewBoxState): ViewBoxState => {
    const w = Math.max(MIN_W, Math.min(MAX_W, v.w));
    const ratio = VH / VW;
    const h = w * ratio;
    // 允许稍微越界，但限制在画布 1.2 倍内
    const minX = -VW * 0.2;
    const maxX = VW + VW * 0.2 - w;
    const minY = -VH * 0.2;
    const maxY = VH + VH * 0.2 - h;
    return {
      x: Math.max(minX, Math.min(maxX, v.x)),
      y: Math.max(minY, Math.min(maxY, v.y)),
      w,
      h,
    };
  }, []);

  // 滚轮缩放（围绕鼠标点）
  const onWheel = useCallback((e: React.WheelEvent<SVGSVGElement>) => {
    if (!svgRef.current) return;
    e.preventDefault();
    const rect = svgRef.current.getBoundingClientRect();
    // 鼠标在 SVG 内的相对比例
    const rx = (e.clientX - rect.left) / rect.width;
    const ry = (e.clientY - rect.top) / rect.height;
    setView((prev) => {
      const factor = e.deltaY > 0 ? 1.18 : 1 / 1.18;
      const newW = Math.max(MIN_W, Math.min(MAX_W, prev.w * factor));
      const newH = newW * (VH / VW);
      // 鼠标位置在 viewBox 中的实际坐标
      const mx = prev.x + prev.w * rx;
      const my = prev.y + prev.h * ry;
      const nx = mx - newW * rx;
      const ny = my - newH * ry;
      return clampView({ x: nx, y: ny, w: newW, h: newH });
    });
  }, [clampView]);

  // 拖拽平移
  const dragRef = useRef<{ startX: number; startY: number; vx: number; vy: number; pid: number } | null>(null);
  const onPointerDown = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    // 仅左键
    if (e.button !== 0) return;
    // 点击城市时由城市层处理，不发起拖拽
    const target = e.target as Element;
    if (target.closest('.chrono-city-node')) return;
    (e.currentTarget as SVGSVGElement).setPointerCapture(e.pointerId);
    dragRef.current = { startX: e.clientX, startY: e.clientY, vx: view.x, vy: view.y, pid: e.pointerId };
  }, [view.x, view.y]);
  const onPointerMove = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    if (!dragRef.current || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const dx = (e.clientX - dragRef.current.startX) * (view.w / rect.width);
    const dy = (e.clientY - dragRef.current.startY) * (view.h / rect.height);
    setView(clampView({ ...view, x: dragRef.current.vx - dx, y: dragRef.current.vy - dy }));
  }, [view, clampView]);
  const endDrag = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    if (dragRef.current && e.currentTarget.hasPointerCapture(dragRef.current.pid)) {
      e.currentTarget.releasePointerCapture(dragRef.current.pid);
    }
    dragRef.current = null;
  }, []);

  const zoomBy = useCallback((factor: number) => {
    setView((prev) => {
      const newW = Math.max(MIN_W, Math.min(MAX_W, prev.w * factor));
      const newH = newW * (VH / VW);
      // 围绕中心缩放
      const cx = prev.x + prev.w / 2;
      const cy = prev.y + prev.h / 2;
      return clampView({ x: cx - newW / 2, y: cy - newH / 2, w: newW, h: newH });
    });
  }, [clampView]);

  // —— 子时段过滤 ——
  const subEras = era.subEras ?? [];
  const activeSub = useMemo(
    () => subEras.find((s) => s.id === activeSubEraId) ?? null,
    [subEras, activeSubEraId],
  );
  const visibleCities = useMemo(() => {
    if (!activeSub) return era.cities;
    const set = new Set(activeSub.dynasties);
    return era.cities.filter((c) => !c.dynasty || set.has(c.dynasty));
  }, [era.cities, activeSub]);

  const zoomLevel = (VW / view.w);

  return (
    <div
      className="chrono-eramap"
      style={{
        background: `radial-gradient(ellipse at 50% 45%, ${era.hue.primary}33, ${era.hue.secondary}cc 70%, ${era.hue.secondary} 100%)`,
      }}
    >
      {/* 子时段切换条 */}
      {subEras.length > 0 && (
        <div className="chrono-eramap-subera">
          <button
            type="button"
            className={`chrono-chip chrono-subera-chip${activeSub ? '' : ' active'}`}
            onClick={() => onSubEraChange?.(null)}
          >
            全部 · {era.period}
          </button>
          {subEras.map((s) => (
            <button
              key={s.id}
              type="button"
              className={`chrono-chip chrono-subera-chip${activeSub?.id === s.id ? ' active' : ''}`}
              onClick={() => onSubEraChange?.(s.id)}
              title={s.period}
            >
              {s.name}<span className="chrono-chip-period">{s.period}</span>
            </button>
          ))}
        </div>
      )}

      {/* 缩放工具条 */}
      <div className="chrono-eramap-zoom" aria-label="地图缩放">
        <button type="button" onClick={() => zoomBy(1 / 1.4)} title="放大">＋</button>
        <button type="button" onClick={() => zoomBy(1.4)} title="缩小">－</button>
        <button type="button" onClick={() => setView(INIT_VIEW)} title="复位">⟳</button>
        <span className="chrono-eramap-zoom-level">{zoomLevel.toFixed(1)}×</span>
      </div>

      {/* 进入课程列表 — 显眼按钮 */}
      {onJumpToCourses && (
        <button
          type="button"
          className="chrono-eramap-jump"
          onClick={onJumpToCourses}
          title="跳转到下方课程列表"
        >
          进入课程列表 <span className="chrono-eramap-jump-arrow">↓</span>
        </button>
      )}

      <svg
        ref={svgRef}
        viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`${era.name}时代地图`}
        style={{
          width: '100%',
          height: '100%',
          display: 'block',
          cursor: dragRef.current ? 'grabbing' : 'grab',
          touchAction: 'none',
        }}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        <StaticLayer />

        {/* 朝代版图 — 受 era 切换驱动，有柔和过渡动画 */}
        <g key={`${pulseKey}-outline`} className="chrono-era-outline">
          {/* 阴影 */}
          <path
            d={era.outline ?? CHINA_OUTLINE}
            fill="rgba(0,0,0,0.32)"
            filter="url(#landShadow)"
            transform="translate(8 10)"
          />
          {/* 实身 */}
          <path
            d={era.outline ?? CHINA_OUTLINE}
            fill="url(#landFill)"
            fillOpacity={0.55}
            stroke={era.hue.primary}
            strokeWidth={1.6}
            strokeOpacity={0.7}
          />
        </g>

        {/* 河流 / 山脉 — v0.3.0 改为绘制在朝代版图之上，避免被遮挡 */}
        <g opacity={0.9} pointerEvents="none">
          {RIVERS.map((r) => (
            <path
              key={`top-${r.id}`}
              d={r.geometry}
              fill="none"
              stroke={r.color}
              strokeWidth={r.id === 'yellow' || r.id === 'yangtze' ? 2.4 : 1.4}
              strokeLinecap="round"
              opacity={r.id === 'yellow' || r.id === 'yangtze' ? 0.95 : 0.65}
            />
          ))}
          {MOUNTAINS.map((m) => (
            <path
              key={`top-${m.id}`}
              d={m.geometry}
              fill="none"
              stroke="#8B6F47"
              strokeWidth={1.8}
              strokeLinecap="round"
              strokeDasharray="1 4"
              opacity={0.55}
            />
          ))}
        </g>

        {/* 时代叠加 — 历史路径 */}
        {era.tracks && era.tracks.length > 0 && (
          <g key={`${pulseKey}-tracks`} className="chrono-era-tracks" pointerEvents="none">
            {era.tracks.map((t, i) => (
              <g key={t.id} className="chrono-track" style={{ animationDelay: `${120 + i * 90}ms` }}>
                <path
                  d={t.geometry}
                  fill="none"
                  stroke={t.color}
                  strokeWidth={(t.width ?? 1.6) + 3}
                  opacity={0.18}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d={t.geometry}
                  fill="none"
                  stroke={t.color}
                  strokeWidth={t.width ?? 1.6}
                  strokeDasharray={t.dash ?? '6 6'}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  opacity={0.9}
                >
                  <title>{t.name}</title>
                </path>
              </g>
            ))}
          </g>
        )}

        {/* 时代叠加 — 城市与都城 */}
        <g key={`${pulseKey}-${activeSub?.id ?? 'all'}`} className="chrono-era-overlay">
          {visibleCities.map((c, i) => (
            <g
              key={`${c.dynasty ?? '_'}-${c.name}-${i}`}
              transform={`translate(${c.x} ${c.y})`}
              style={{ cursor: onCityClick ? 'pointer' : 'default', animationDelay: `${i * 60}ms` }}
              className="chrono-city-node"
              onClick={() => onCityClick?.(c)}
            >
              {c.capital && (
                <circle r={16} fill={era.hue.primary} opacity={0.18} className="chrono-city-halo" />
              )}
              <circle
                r={c.capital ? 6 : 4}
                fill="#F4ECDC"
                stroke={c.capital ? era.hue.primary : 'rgba(11,30,58,0.55)'}
                strokeWidth={c.capital ? 2.5 : 1.6}
                filter="url(#cityGlow)"
              />
              <title>
                {c.name}
                {c.modern && c.modern !== c.name ? `（今${c.modern}）` : ''}
                {c.dynasty ? ` · ${c.dynasty}` : ''}
                {c.note ? `\n${c.note}` : ''}
              </title>
              <text
                x={c.capital ? 12 : 9}
                y={5}
                fontSize={c.capital ? 14 : 12}
                fontWeight={c.capital ? 700 : 500}
                fill="#0B1E3A"
                style={{ paintOrder: 'stroke', stroke: 'rgba(244,236,220,0.85)', strokeWidth: 3 }}
              >
                {c.name}
                {c.modern && c.modern !== c.name && (
                  <tspan fontSize={10} fill="#6B7280" dx={4}>{c.modern}</tspan>
                )}
              </text>
            </g>
          ))}
        </g>

        {/* 时代水印 */}
        <g pointerEvents="none">
          <text
            x={VW - 40}
            y={VH - 32}
            textAnchor="end"
            fontSize={64}
            fontWeight={700}
            fill={era.hue.primary}
            opacity={0.16}
            style={{ fontFamily: '"Noto Serif SC", serif', letterSpacing: 6 }}
          >
            {era.name}
          </text>
          <text
            x={VW - 40}
            y={VH - 12}
            textAnchor="end"
            fontSize={12}
            fill={era.hue.primary}
            opacity={0.55}
            style={{ letterSpacing: 2 }}
          >
            {activeSub ? `${activeSub.name} · ${activeSub.period}` : era.period}
          </text>
        </g>
      </svg>
    </div>
  );
}
