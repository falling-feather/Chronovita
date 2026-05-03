import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Tag, Spin, Empty } from 'antd';
import { api, type CourseSummary, type Era } from '../utils/api';
import { ERA_OVERLAYS, type EraMapCity } from './courses/eraMap';
import EraTimeline from './courses/EraTimeline';

// 地图入场图层懒加载，首屏更快
const EraMap = lazy(() => import('./courses/EraMapView'));

const SECTIONS = ['all', '通史', '思想', '制度', '文化'];
const DEFAULT_ERA = 'qinhan'; // 入场默认聚焦秦汉（大一统起点）

export default function CoursesPage() {
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const eraParam = params.get('era') || '';
  const mapEraId = ERA_OVERLAYS.find((e) => e.id === eraParam) ? eraParam : DEFAULT_ERA;
  const courseEra = eraParam || 'all';
  const section = params.get('section') || 'all';
  const q = params.get('q') || '';
  const city = params.get('city') || '';
  const subEra = params.get('sub') || '';

  const gridRef = useRef<HTMLDivElement | null>(null);

  const [eras, setEras] = useState<Era[]>([]);
  const [items, setItems] = useState<CourseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [entered, setEntered] = useState(false);
  useEffect(() => {
    const t = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(t);
  }, []);

  useEffect(() => { api.eras().then((r) => setEras(r.items)).catch(() => {}); }, []);

  useEffect(() => {
    setLoading(true);
    api.courses({ era: courseEra, section, q }).then((r) => setItems(r.items)).finally(() => setLoading(false));
  }, [courseEra, section, q]);

  const eraTabs = useMemo(() => [{ id: 'all', name: '全部', period: '所有时代' }, ...eras], [eras]);
  const currentEra = ERA_OVERLAYS.find((e) => e.id === mapEraId)!;

  // 拉取整个时代的课程（独立于过滤条件，用于侧栏精选）
  const [eraCourses, setEraCourses] = useState<CourseSummary[] | null>(null); // null = 加载中
  useEffect(() => {
    setEraCourses(null);
    api.courses({ era: mapEraId })
      .then((r) => setEraCourses(r.items))
      .catch(() => setEraCourses([]));
  }, [mapEraId]);

  const setParam = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v && v !== 'all') next.set(k, v); else next.delete(k);
    setParams(next, { replace: true });
  };

  const setEra = (id: string) => {
    const next = new URLSearchParams(params);
    if (id && id !== 'all') next.set('era', id); else next.delete('era');
    next.delete('sub'); // 切换时代时清空子时段
    setParams(next, { replace: true });
  };

  // 点击地图都城 → 设置 city 过滤 + 滚动到课程网格
  const onPickCity = (c: EraMapCity) => {
    const next = new URLSearchParams(params);
    // 存古名，现名入 keywords
    next.set('city', c.name);
    if (c.modern && c.modern !== c.name) next.set('cityModern', c.modern);
    else next.delete('cityModern');
    setParams(next, { replace: true });
    requestAnimationFrame(() => {
      gridRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  };

  // 前端按地点过滤（处理 title/subtitle 同时匹配古名与今名）
  const cityModern = params.get('cityModern') || '';
  const visibleItems = useMemo(() => {
    if (!city) return items;
    const keywords = [city, cityModern].filter(Boolean) as string[];
    return items.filter((it) =>
      keywords.some((k) => it.title.includes(k) || it.subtitle.includes(k)),
    );
  }, [items, city, cityModern]);

  return (
    <div style={{ maxWidth: 1392, margin: '0 auto' }}>
      {/* 入场标题 */}
      <div className={`chrono-hero-head${entered ? ' entered' : ''}`}>
        <div className="chrono-hero-eyebrow">CHRONOVITA · 课程中心</div>
        <h1 className="chrono-title chrono-hero-title">在中国版图上，看见时代</h1>
        <div className="chrono-hero-sub">
          拖动下方时间轴 · 六大时代的疆域、都城与文明节点将在地图上动态浮现
        </div>
      </div>

      {/* 地图 + 侧边时代信息 */}
      <div className={`chrono-mapwrap${entered ? ' entered' : ''}`}>
        <div className="chrono-mapstage">
          <Suspense fallback={<div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}><Spin /></div>}>
            <EraMap
              era={currentEra}
              onCityClick={onPickCity}
              activeSubEraId={subEra || null}
              onSubEraChange={(id) => setParam('sub', id ?? '')}
            />
          </Suspense>
        </div>

        <aside className="chrono-erapanel">
          <div className="chrono-erapanel-tag">当前时代</div>
          <div className="chrono-title chrono-erapanel-name">{currentEra.name}</div>
          <div className="chrono-erapanel-period">{currentEra.period} · {currentEra.frontier}</div>
          <div className="chrono-erapanel-blurb">{currentEra.blurb}</div>

          <div className="chrono-erapanel-events">
            {currentEra.events.map((ev) => (
              <div key={ev.year} className="chrono-erapanel-event">
                <span className="chrono-erapanel-year">
                  {ev.year < 0 ? `前 ${-ev.year}` : ev.year}
                </span>
                <span className="chrono-erapanel-text">{ev.text}</span>
              </div>
            ))}
          </div>

          <div className="chrono-erapanel-cta">
            <span className="chrono-erapanel-cta-label">本时代精选课程</span>
            <a className="chrono-erapanel-cta-more" onClick={() => setEra(currentEra.id)}>
              查看全部 →
            </a>
          </div>
          {eraCourses === null ? (
            <div className="chrono-erapanel-courses">
              {[0, 1, 2].map((i) => (
                <div key={i} className="chrono-erapanel-course chrono-skeleton">
                  <span className="chrono-erapanel-course-bar" style={{ background: 'var(--border-soft)' }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="chrono-skel-line" style={{ width: 36 }} />
                    <div className="chrono-skel-line" style={{ width: '80%', height: 14, marginTop: 6 }} />
                    <div className="chrono-skel-line" style={{ width: '60%', marginTop: 6 }} />
                  </div>
                </div>
              ))}
            </div>
          ) : eraCourses.length === 0 ? (
            <div className="chrono-erapanel-empty">尚未上线 · 敬请期待</div>
          ) : (
            <div className="chrono-erapanel-courses">
              {eraCourses.slice(0, 3).map((c) => (
                <div
                  key={c.id}
                  className={`chrono-erapanel-course${c.lesson_count === 0 ? ' disabled' : ''}`}
                  onClick={() => c.lesson_count > 0 && nav(`/courses/${c.id}`)}
                >
                  <span className="chrono-erapanel-course-bar" style={{ background: c.cover_color }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="chrono-erapanel-course-section">{c.section}</div>
                    <div className="chrono-erapanel-course-title">{c.title}</div>
                    <div className="chrono-erapanel-course-sub">
                      {c.lesson_count > 0 ? `${c.lesson_count} 节 · ${c.subtitle}` : '尚未上线'}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </aside>
      </div>

      {/* 时间轴 */}
      <div className={`chrono-eratl-wrap${entered ? ' entered' : ''}`}>
        <EraTimeline current={mapEraId} onChange={setEra} />
      </div>

      {/* 浏览全部课程（保留原 chips + 网格） */}
      <div ref={gridRef} style={{ marginTop: 36, marginBottom: 12 }}>
        <h2 className="chrono-title" style={{ fontSize: 20, margin: 0 }}>浏览全部课程</h2>
        <div style={{ color: 'var(--text-mute)', fontSize: 13, marginTop: 6 }}>
          {city
            ? `已按地点 · ${city} 筛选，点击其他都城可切换，或点 × 清除。`
            : courseEra === 'all'
              ? '按板块筛选课程；点击卡片进入课程详情。'
              : `已锁定时代 · ${currentEra.name}（${currentEra.period}）`}
        </div>
      </div>

      <div className="chrono-card-warm" style={{ marginBottom: 16, padding: '14px 18px' }}>
        <div style={{ fontSize: 12, color: 'var(--text-mute)', marginBottom: 8 }}>时代</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {eraTabs.map((e: any) => (
            <span
              key={e.id}
              className={`chrono-chip${courseEra === e.id ? ' active' : ''}`}
              onClick={() => setParam('era', e.id)}
            >
              {e.name}
              {e.id !== 'all' && (
                <span style={{ color: 'var(--text-disabled)', marginLeft: 6, fontSize: 10 }}>{e.period}</span>
              )}
            </span>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap' }}>
        {SECTIONS.map((s) => (
          <span
            key={s}
            className={`chrono-chip${section === s ? ' active' : ''}`}
            onClick={() => setParam('section', s)}
          >
            {s === 'all' ? '全部板块' : s}
          </span>
        ))}
        {q && (
          <span className="chrono-chip" style={{ background: 'var(--bg-tint)', borderColor: 'var(--accent-gold)' }}>
            搜索: {q}
            <a style={{ marginLeft: 8, color: 'var(--text-mute)' }} onClick={() => setParam('q', '')}>×</a>
          </span>
        )}
        {city && (
          <span className="chrono-chip" style={{ background: 'var(--bg-tint)', borderColor: 'var(--accent-gold)' }}>
            地点: {city}{cityModern ? ` / ${cityModern}` : ''}
            <a style={{ marginLeft: 8, color: 'var(--text-mute)' }} onClick={() => {
              const next = new URLSearchParams(params);
              next.delete('city'); next.delete('cityModern');
              setParams(next, { replace: true });
            }}>×</a>
          </span>
        )}
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
      ) : visibleItems.length === 0 ? (
        <Empty description={city ? `未找到与「${city}」相关的课程` : '暂无符合条件的课程'} />
      ) : (
        <div className="chrono-course-grid">
          {visibleItems.map((c) => {
            const disabled = c.lesson_count === 0;
            return (
              <div
                key={c.id}
                className="chrono-card chrono-course-card"
                style={{ padding: 0, overflow: 'hidden', cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.6 : 1 }}
                onClick={() => !disabled && nav(`/courses/${c.id}`)}
              >
                <div style={{ height: 110, background: c.cover_color, position: 'relative' }}>
                  <Tag color="gold" style={{ position: 'absolute', top: 10, left: 10 }}>
                    {eras.find((e) => e.id === c.era_id)?.name || '—'}
                  </Tag>
                  <Tag style={{ position: 'absolute', top: 10, right: 10 }}>{c.section}</Tag>
                </div>
                <div style={{ padding: 14 }}>
                  <div className="chrono-title" style={{ fontSize: 16 }}>{c.title}</div>
                  <div style={{ color: 'var(--text-mute)', fontSize: 12, margin: '6px 0' }}>{c.subtitle}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-disabled)' }}>
                    {c.lesson_count > 0 ? `共 ${c.lesson_count} 节` : '尚未上线'}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
