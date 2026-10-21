import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import {
  AimOutlined,
  CompassOutlined,
  MinusOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { CHINA_REFERENCE_PATH } from './chinaReferencePath';
import { CHINA_OUTLINE, MOUNTAINS, RIVERS, type EraMapCity, type EraOverlay } from './eraMap';
import {
  ERA_MAP_HEIGHT,
  ERA_MAP_INITIAL_VIEW,
  ERA_MAP_WIDTH,
  getEraMapZoomLevel,
  isEraMapAtMaximumZoom,
  isEraMapAtMinimumZoom,
  panEraMapBy,
  shouldCaptureEraMapWheel,
  zoomEraMapAt,
  type EraMapViewport,
} from './eraMapViewport';
import { publicAssetUrl } from '../../runtime';

interface Props {
  era: EraOverlay;
  onCityClick?: (city: EraMapCity) => void;
  activeSubEraId?: string | null;
  onSubEraChange?: (subEraId: string | null) => void;
  onJumpToCourses?: () => void;
}

type EdgeHint = 'minimum' | 'maximum' | null;

interface DragState {
  pointerId: number;
  startX: number;
  startY: number;
  view: EraMapViewport;
}

interface PinchState {
  distance: number;
  relativeX: number;
  relativeY: number;
  view: EraMapViewport;
}

const TERRAIN_ASSET = publicAssetUrl('/assets/maps/chronovita-terrain-atlas-v1.webp');

function cityKey(city: EraMapCity): string {
  return `${city.dynasty ?? '_'}-${city.name}-${city.modern ?? ''}`;
}

function pointerDistance(points: Array<{ x: number; y: number }>): number {
  if (points.length < 2) return 0;
  return Math.hypot(points[1].x - points[0].x, points[1].y - points[0].y);
}

const StaticMapLayers = memo(function StaticMapLayers() {
  return (
    <>
      <defs>
        <linearGradient id="cv-map-sea" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#e4d2aa" stopOpacity=".18" />
          <stop offset="58%" stopColor="#1a3136" stopOpacity=".18" />
          <stop offset="100%" stopColor="#06131c" stopOpacity=".62" />
        </linearGradient>
        <linearGradient id="cv-map-territory" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#f0d8a7" stopOpacity=".3" />
          <stop offset="55%" stopColor="#b88d55" stopOpacity=".2" />
          <stop offset="100%" stopColor="#6d3d2d" stopOpacity=".14" />
        </linearGradient>
        <radialGradient id="cv-map-city-glow">
          <stop offset="0%" stopColor="#fff3cf" stopOpacity=".96" />
          <stop offset="36%" stopColor="#d9a95b" stopOpacity=".5" />
          <stop offset="100%" stopColor="#a64235" stopOpacity="0" />
        </radialGradient>
        <filter id="cv-map-soft-shadow" x="-20%" y="-20%" width="150%" height="150%">
          <feGaussianBlur stdDeviation="7" />
        </filter>
        <filter id="cv-map-city-shadow" x="-300%" y="-300%" width="700%" height="700%">
          <feGaussianBlur stdDeviation="2.8" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <pattern id="cv-map-grid" width="80" height="80" patternUnits="userSpaceOnUse">
          <path d="M 80 0 L 0 0 0 80" fill="none" stroke="#243a3e" strokeOpacity=".18" strokeWidth=".7" />
        </pattern>
      </defs>

      <rect width={ERA_MAP_WIDTH} height={ERA_MAP_HEIGHT} fill="#9e8a67" />
      <image
        href={TERRAIN_ASSET}
        x="0"
        y="0"
        width={ERA_MAP_WIDTH}
        height={ERA_MAP_HEIGHT}
        preserveAspectRatio="xMidYMid slice"
        opacity=".78"
      />
      <rect width={ERA_MAP_WIDTH} height={ERA_MAP_HEIGHT} fill="url(#cv-map-sea)" />
      <rect width={ERA_MAP_WIDTH} height={ERA_MAP_HEIGHT} fill="url(#cv-map-grid)" />

      <path
        d={CHINA_REFERENCE_PATH}
        fill="rgba(242, 231, 207, .075)"
        fillRule="evenodd"
        stroke="rgba(242, 231, 207, .25)"
        strokeWidth="1"
        strokeDasharray="3 7"
        vectorEffect="non-scaling-stroke"
        aria-hidden="true"
      />
    </>
  );
});

export default function EraMap({
  era,
  onCityClick,
  activeSubEraId,
  onSubEraChange,
  onJumpToCourses,
}: Props) {
  const [view, setView] = useState<EraMapViewport>(ERA_MAP_INITIAL_VIEW);
  const [selectedCity, setSelectedCity] = useState<EraMapCity | null>(null);
  const [hoveredCity, setHoveredCity] = useState<EraMapCity | null>(null);
  const [edgeHint, setEdgeHint] = useState<EdgeHint>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const viewRef = useRef(view);
  const pointersRef = useRef(new Map<number, { x: number; y: number }>());
  const dragRef = useRef<DragState | null>(null);
  const pinchRef = useRef<PinchState | null>(null);
  const edgeTimerRef = useRef<number | null>(null);

  const subEras = era.subEras ?? [];
  const activeSub = useMemo(
    () => subEras.find((subEra) => subEra.id === activeSubEraId) ?? null,
    [activeSubEraId, subEras],
  );
  const visibleCities = useMemo(() => {
    if (!activeSub) return era.cities;
    const dynasties = new Set(activeSub.dynasties);
    return era.cities.filter((city) => !city.dynasty || dynasties.has(city.dynasty));
  }, [activeSub, era.cities]);
  const plottedCities = useMemo(() => {
    const occupied: Array<{ x: number; y: number }> = [];
    const overviewLabels: Array<{ x: number; y: number }> = [];
    return visibleCities.map((city, cityIndex) => {
      let x = city.x;
      let y = city.y;
      const overlaps = (candidateX: number, candidateY: number) => occupied.some(
        (point) => Math.hypot(point.x - candidateX, point.y - candidateY) < 34,
      );

      if (overlaps(x, y)) {
        for (let attempt = 0; attempt < 32; attempt += 1) {
          const ring = Math.floor(attempt / 8) + 1;
          const angle = ((attempt % 8) * Math.PI) / 4 + cityIndex * 0.37;
          const radius = ring * 22;
          const candidateX = city.x + Math.cos(angle) * radius;
          const candidateY = city.y + Math.sin(angle) * radius;
          if (!overlaps(candidateX, candidateY)) {
            x = candidateX;
            y = candidateY;
            break;
          }
        }
      }
      occupied.push({ x, y });
      const overviewLabel = Boolean(city.capital) && !overviewLabels.some(
        (label) => Math.abs(label.x - x) < 105 && Math.abs(label.y - y) < 28,
      );
      if (overviewLabel) overviewLabels.push({ x, y });
      return { city, x, y, overviewLabel };
    });
  }, [visibleCities]);
  const activeCity = hoveredCity ?? selectedCity;
  const zoomLevel = getEraMapZoomLevel(view);
  const atMinimumZoom = isEraMapAtMinimumZoom(view);
  const atMaximumZoom = isEraMapAtMaximumZoom(view);

  const mapStyle = {
    '--map-era-primary': era.hue.primary,
    '--map-era-secondary': era.hue.secondary,
  } as CSSProperties;

  const commitView = useCallback((next: EraMapViewport) => {
    viewRef.current = next;
    setView(next);
  }, []);

  const resetView = useCallback(() => {
    commitView(ERA_MAP_INITIAL_VIEW);
  }, [commitView]);

  useEffect(() => {
    resetView();
    setSelectedCity(null);
    setHoveredCity(null);
  }, [activeSubEraId, era.id, resetView]);

  useEffect(() => () => {
    if (edgeTimerRef.current !== null) window.clearTimeout(edgeTimerRef.current);
  }, []);

  const showEdgeHint = useCallback((hint: Exclude<EdgeHint, null>) => {
    setEdgeHint(hint);
    if (edgeTimerRef.current !== null) window.clearTimeout(edgeTimerRef.current);
    edgeTimerRef.current = window.setTimeout(() => setEdgeHint(null), 1100);
  }, []);

  const zoomBy = useCallback((factor: number, relativeX = 0.5, relativeY = 0.5) => {
    commitView(zoomEraMapAt(viewRef.current, factor, relativeX, relativeY));
  }, [commitView]);

  const onWheel = useCallback((event: WheelEvent) => {
    if (!svgRef.current) return;
    const current = viewRef.current;
    if (!shouldCaptureEraMapWheel(current, event.deltaY)) {
      showEdgeHint(event.deltaY > 0 ? 'minimum' : 'maximum');
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    const rect = svgRef.current.getBoundingClientRect();
    const relativeX = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    const relativeY = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
    zoomBy(event.deltaY > 0 ? 1.16 : 1 / 1.16, relativeX, relativeY);
  }, [showEdgeHint, zoomBy]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return undefined;
    svg.addEventListener('wheel', onWheel, { passive: false });
    return () => svg.removeEventListener('wheel', onWheel);
  }, [onWheel]);

  const startPinch = useCallback(() => {
    if (!svgRef.current || pointersRef.current.size < 2) return;
    const points = Array.from(pointersRef.current.values()).slice(0, 2);
    const rect = svgRef.current.getBoundingClientRect();
    const midpointX = (points[0].x + points[1].x) / 2;
    const midpointY = (points[0].y + points[1].y) / 2;
    pinchRef.current = {
      distance: pointerDistance(points),
      relativeX: (midpointX - rect.left) / rect.width,
      relativeY: (midpointY - rect.top) / rect.height,
      view: viewRef.current,
    };
    dragRef.current = null;
  }, []);

  const onPointerDown = useCallback((event: ReactPointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    const target = event.target as Element;
    if (target.closest('.chrono-city-node')) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointersRef.current.size >= 2) {
      startPinch();
      return;
    }
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      view: viewRef.current,
    };
  }, [startPinch]);

  const onPointerMove = useCallback((event: ReactPointerEvent<SVGSVGElement>) => {
    if (!svgRef.current || !pointersRef.current.has(event.pointerId)) return;
    pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointersRef.current.size >= 2 && pinchRef.current) {
      const distance = pointerDistance(Array.from(pointersRef.current.values()).slice(0, 2));
      if (distance > 0) {
        commitView(zoomEraMapAt(
          pinchRef.current.view,
          pinchRef.current.distance / distance,
          pinchRef.current.relativeX,
          pinchRef.current.relativeY,
        ));
      }
      return;
    }
    if (!dragRef.current || dragRef.current.pointerId !== event.pointerId) return;
    const rect = svgRef.current.getBoundingClientRect();
    const deltaX = (dragRef.current.startX - event.clientX) * (dragRef.current.view.w / rect.width);
    const deltaY = (dragRef.current.startY - event.clientY) * (dragRef.current.view.h / rect.height);
    commitView(panEraMapBy(dragRef.current.view, deltaX, deltaY));
  }, [commitView]);

  const endPointer = useCallback((event: ReactPointerEvent<SVGSVGElement>) => {
    pointersRef.current.delete(event.pointerId);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    pinchRef.current = null;
    dragRef.current = null;
    const remaining = Array.from(pointersRef.current.entries())[0];
    if (remaining) {
      dragRef.current = {
        pointerId: remaining[0],
        startX: remaining[1].x,
        startY: remaining[1].y,
        view: viewRef.current,
      };
    }
  }, []);

  const onMapKeyDown = useCallback((event: ReactKeyboardEvent<SVGSVGElement>) => {
    const stepX = viewRef.current.w * 0.08;
    const stepY = viewRef.current.h * 0.08;
    let next: EraMapViewport | null = null;
    if (event.key === '+' || event.key === '=') next = zoomEraMapAt(viewRef.current, 1 / 1.24);
    if (event.key === '-') next = zoomEraMapAt(viewRef.current, 1.24);
    if (event.key === 'ArrowLeft') next = panEraMapBy(viewRef.current, -stepX, 0);
    if (event.key === 'ArrowRight') next = panEraMapBy(viewRef.current, stepX, 0);
    if (event.key === 'ArrowUp') next = panEraMapBy(viewRef.current, 0, -stepY);
    if (event.key === 'ArrowDown') next = panEraMapBy(viewRef.current, 0, stepY);
    if (event.key === 'Home' || event.key === '0') next = ERA_MAP_INITIAL_VIEW;
    if (!next) return;
    event.preventDefault();
    commitView(next);
  }, [commitView]);

  const selectCity = useCallback((city: EraMapCity) => {
    setSelectedCity(city);
    setHoveredCity(null);
  }, []);

  return (
    <div
      className={`chrono-eramap chrono-eramap-v2${zoomLevel >= 1.34 ? ' is-detailed' : ''}`}
      style={mapStyle}
    >
      {subEras.length > 0 && (
        <div className="chrono-eramap-subera" aria-label="地图子时段">
          <button
            type="button"
            className={`chrono-chip chrono-subera-chip${activeSub ? '' : ' active'}`}
            aria-pressed={!activeSub}
            onClick={() => onSubEraChange?.(null)}
          >
            全部 <span className="chrono-chip-period">{era.period}</span>
          </button>
          {subEras.map((subEra) => (
            <button
              key={subEra.id}
              type="button"
              className={`chrono-chip chrono-subera-chip${activeSub?.id === subEra.id ? ' active' : ''}`}
              aria-pressed={activeSub?.id === subEra.id}
              onClick={() => onSubEraChange?.(subEra.id)}
              title={subEra.period}
            >
              {subEra.name}<span className="chrono-chip-period">{subEra.period}</span>
            </button>
          ))}
        </div>
      )}

      <div className="chrono-eramap-zoom" role="group" aria-label="地图缩放与复位">
        <button
          type="button"
          onClick={() => zoomBy(1 / 1.32)}
          disabled={atMaximumZoom}
          aria-label="放大地图"
          title="放大（+）"
        ><PlusOutlined /></button>
        <button
          type="button"
          onClick={() => zoomBy(1.32)}
          disabled={atMinimumZoom}
          aria-label="缩小地图"
          title="缩小（-）"
        ><MinusOutlined /></button>
        <button type="button" onClick={resetView} disabled={atMinimumZoom} aria-label="复位地图" title="复位（0）">
          <ReloadOutlined />
        </button>
        <span className="chrono-eramap-zoom-level">{Math.round(zoomLevel * 100)}%</span>
      </div>

      <div className="chrono-map-compass" aria-hidden="true">
        <CompassOutlined />
        <span>北</span>
      </div>

      <p id="chrono-map-instructions" className="chrono-map-guidance">
        <AimOutlined /> 滚轮缩放 · 拖动巡览 · 点击城邑查看札记
      </p>

      <div className={`chrono-map-edge-hint${edgeHint ? ' is-visible' : ''}`} aria-live="polite">
        {edgeHint === 'minimum' ? '已是全图，继续滚动浏览页面' : edgeHint === 'maximum' ? '已到最大细节' : ''}
      </div>

      <svg
        ref={svgRef}
        viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
        preserveAspectRatio="xMidYMid slice"
        role="img"
        tabIndex={0}
        aria-label={`${era.name}时代课堂地图；历史范围为教学示意`}
        aria-describedby="chrono-map-instructions"
        style={{ cursor: dragRef.current ? 'grabbing' : 'grab', touchAction: atMinimumZoom ? 'pan-y' : 'none' }}
        onKeyDown={onMapKeyDown}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endPointer}
        onPointerCancel={endPointer}
      >
        <StaticMapLayers />

        <g key={`${era.id}-${activeSub?.id ?? 'all'}-territory`} className="chrono-era-outline-v2" pointerEvents="none">
          <path
            d={era.outline ?? CHINA_OUTLINE}
            fill="rgba(3, 13, 18, .15)"
            filter="url(#cv-map-soft-shadow)"
            transform="translate(7 10)"
          />
          <path
            d={era.outline ?? CHINA_OUTLINE}
            fill="url(#cv-map-territory)"
            fillRule="evenodd"
            stroke="var(--map-era-primary)"
            strokeWidth="1.45"
            strokeOpacity=".84"
            vectorEffect="non-scaling-stroke"
          />
          <path
            d={era.outline ?? CHINA_OUTLINE}
            fill="none"
            stroke="rgba(242, 231, 207, .44)"
            strokeWidth=".9"
            strokeDasharray="2 8"
            vectorEffect="non-scaling-stroke"
          />
        </g>

        <g className="chrono-map-relief-lines" pointerEvents="none">
          {RIVERS.map((river) => (
            <path
              key={river.id}
              d={river.geometry}
              fill="none"
              stroke={river.id === 'yellow' ? '#d9aa5a' : '#79afba'}
              strokeWidth={river.id === 'yellow' || river.id === 'yangtze' ? 2.2 : 1.1}
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
            ><title>{river.name}</title></path>
          ))}
          {MOUNTAINS.map((mountain) => (
            <path
              key={mountain.id}
              d={mountain.geometry}
              fill="none"
              stroke="#4b3b2b"
              strokeWidth="1.25"
              strokeLinecap="round"
              strokeDasharray="1 5"
              vectorEffect="non-scaling-stroke"
            ><title>{mountain.name}</title></path>
          ))}
        </g>

        {era.tracks && era.tracks.length > 0 && (
          <g key={`${era.id}-tracks`} className="chrono-era-tracks-v2" pointerEvents="none">
            {era.tracks.map((track, index) => (
              <g key={track.id} style={{ animationDelay: `${index * 100}ms` }}>
                <path
                  d={track.geometry}
                  fill="none"
                  stroke="#071921"
                  strokeWidth={(track.width ?? 1.6) + 4}
                  strokeOpacity=".28"
                  strokeLinecap="round"
                  vectorEffect="non-scaling-stroke"
                />
                <path
                  d={track.geometry}
                  fill="none"
                  stroke={track.color}
                  strokeWidth={track.width ?? 1.6}
                  strokeDasharray={track.dash ?? '7 6'}
                  strokeLinecap="round"
                  vectorEffect="non-scaling-stroke"
                ><title>{track.name}</title></path>
              </g>
            ))}
          </g>
        )}

        <g key={`${era.id}-${activeSub?.id ?? 'all'}-cities`} className="chrono-era-cities-v2">
          {plottedCities.map(({ city, x, y, overviewLabel }, index) => {
            const isActive = activeCity ? cityKey(activeCity) === cityKey(city) : false;
            return (
              <g
                key={`${cityKey(city)}-${index}`}
                transform={`translate(${x} ${y})`}
                className={`chrono-city-node${city.capital ? ' is-capital' : ''}${overviewLabel ? ' is-overview-label' : ''}${isActive ? ' is-active' : ''}`}
                role="button"
                tabIndex={0}
                aria-label={`${city.name}${city.modern && city.modern !== city.name ? `，今${city.modern}` : ''}${city.note ? `，${city.note}` : ''}`}
                onMouseEnter={() => setHoveredCity(city)}
                onMouseLeave={() => setHoveredCity(null)}
                onFocus={() => setHoveredCity(city)}
                onBlur={() => setHoveredCity(null)}
                onClick={(event) => { event.stopPropagation(); selectCity(city); }}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    selectCity(city);
                  }
                }}
              >
                {city.capital && <circle className="chrono-city-orbit" r="18" />}
                <circle className="chrono-city-glow" r={city.capital ? 24 : 17} fill="url(#cv-map-city-glow)" />
                <circle className="chrono-city-dot" r={city.capital ? 5.8 : 4} filter="url(#cv-map-city-shadow)" />
                <text className="chrono-city-label" x={city.capital ? 13 : 10} y="5">
                  {city.name}
                  {city.modern && city.modern !== city.name && (
                    <tspan className="chrono-city-modern" dx="4">{city.modern}</tspan>
                  )}
                </text>
              </g>
            );
          })}
        </g>

        <g className="chrono-map-watermark" pointerEvents="none">
          <text x="938" y="627" textAnchor="end">{era.name}</text>
          <text x="938" y="651" textAnchor="end">{activeSub ? `${activeSub.name} · ${activeSub.period}` : era.period}</text>
        </g>
      </svg>

      <aside className={`chrono-map-city-card${activeCity ? ' is-visible' : ''}`} aria-live="polite">
        {activeCity ? (
          <>
            <span>{activeCity.capital ? '都城 / 政治中心' : '历史地标'}</span>
            <strong>{activeCity.name}</strong>
            <small>{activeCity.modern && activeCity.modern !== activeCity.name ? `今 ${activeCity.modern}` : activeCity.dynasty ?? era.name}</small>
            <p>{activeCity.note ?? '选择这座城邑，查看相关课程与时代线索。'}</p>
            {onCityClick && (
              <button type="button" onClick={() => onCityClick(activeCity)}>
                查看关联课程 <span>→</span>
              </button>
            )}
          </>
        ) : (
          <>
            <span>山河札记</span>
            <strong>{era.frontier}</strong>
            <p>选择发光城邑，可查看当时名称、现代定位与一条历史线索。</p>
          </>
        )}
      </aside>

      <div className="chrono-map-legend" aria-label="地图图例">
        <span><i className="is-capital" /> 都城</span>
        <span><i className="is-city" /> 城邑</span>
        <span><i className="is-water" /> 水系</span>
        {era.tracks?.slice(0, 2).map((track) => (
          <span key={track.id}><i className="is-route" style={{ color: track.color }} /> {track.name}</span>
        ))}
        <em>历史范围为课堂示意 · 现代轮廓仅作定位</em>
      </div>

      {onJumpToCourses && (
        <button type="button" className="chrono-eramap-jump" onClick={onJumpToCourses}>
          进入课程目录 <span>↓</span>
        </button>
      )}
    </div>
  );
}
