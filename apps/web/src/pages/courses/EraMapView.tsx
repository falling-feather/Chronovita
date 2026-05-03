// 时空地图入场组件 · 纯 SVG · v0.2.2
import { memo, useEffect, useState } from 'react';
import { CHINA_OUTLINE, RIVERS, type EraMapCity, type EraOverlay } from './eraMap';

interface Props {
  era: EraOverlay;
  /** 选择城市时回调（传出完整 city 对象） */
  onCityClick?: (city: EraMapCity) => void;
}

const VW = 1000;
const VH = 720;

// 静态层抽离 → 时代切换时不重绘，避免 path 抖动
const StaticLayer = memo(function StaticLayer() {
  return (
    <>
      {/* 海面填充（左上斜光） */}
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

      {/* 海面 */}
      <rect x="0" y="0" width={VW} height={VH} fill="url(#seaGlow)" />

      {/* 陆地阴影 */}
      <path d={CHINA_OUTLINE} fill="rgba(0,0,0,0.35)" filter="url(#landShadow)" transform="translate(8 10)" />
      {/* 陆地 */}
      <path
        d={CHINA_OUTLINE}
        fill="url(#landFill)"
        stroke="rgba(212,169,92,0.55)"
        strokeWidth={1.4}
        strokeDasharray="2 4"
      />

      {/* 河流 */}
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

      {/* 经纬刻度（暗淡装饰） */}
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

export default function EraMap({ era, onCityClick }: Props) {
  // 切换时代时短暂强调动画
  const [pulseKey, setPulseKey] = useState(era.id);
  useEffect(() => { setPulseKey(era.id); }, [era.id]);

  return (
    <div className="chrono-eramap" style={{
      background: `radial-gradient(ellipse at 50% 45%, ${era.hue.primary}33, ${era.hue.secondary}cc 70%, ${era.hue.secondary} 100%)`,
    }}>
      <svg
        viewBox={`0 0 ${VW} ${VH}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`${era.name}时代地图`}
        style={{ width: '100%', height: '100%', display: 'block' }}
      >
        <StaticLayer />

        {/* 时代叠加 — 历史路径（长城/丝路/运河/航路 …） */}
        {era.tracks && era.tracks.length > 0 && (
          <g key={`${pulseKey}-tracks`} className="chrono-era-tracks" pointerEvents="none">
            {era.tracks.map((t, i) => (
              <g key={t.id} className="chrono-track" style={{ animationDelay: `${120 + i * 90}ms` }}>
                {/* 外发光底线 */}
                <path
                  d={t.geometry}
                  fill="none"
                  stroke={t.color}
                  strokeWidth={(t.width ?? 1.6) + 3}
                  opacity={0.18}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                {/* 主线 */}
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
        <g key={pulseKey} className="chrono-era-overlay">
          {era.cities.map((c, i) => (
            <g
              key={`${c.name}-${i}`}
              transform={`translate(${c.x} ${c.y})`}
              style={{ cursor: onCityClick ? 'pointer' : 'default', animationDelay: `${i * 80}ms` }}
              className="chrono-city-node"
              onClick={() => onCityClick?.(c)}
            >
              {c.capital && (
                <circle r={16} fill={era.hue.primary} opacity={0.18} className="chrono-city-halo" />
              )}
              <circle
                r={c.capital ? 6 : 4}
                fill={c.capital ? '#F4ECDC' : '#F4ECDC'}
                stroke={c.capital ? era.hue.primary : 'rgba(11,30,58,0.55)'}
                strokeWidth={c.capital ? 2.5 : 1.6}
                filter="url(#cityGlow)"
              />
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

        {/* 标题层 — 时代名称水印 */}
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
            {era.period}
          </text>
        </g>
      </svg>
    </div>
  );
}
