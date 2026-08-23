import { lazy, Suspense, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Empty, Spin } from 'antd';
import { ArrowRightOutlined, CloseOutlined, EnvironmentOutlined } from '@ant-design/icons';
import { api, type CourseSummary, type Era } from '../utils/api';
import { ERA_OVERLAYS, type EraMapCity } from './courses/eraMap';
import EraTimeline from './courses/EraTimeline';

const EraMap = lazy(() => import('./courses/EraMapView'));
const SECTIONS = ['all', '通史', '思想', '制度', '文化'];
const DEFAULT_ERA = 'qinhan';

function courseAccentStyle(color: string): CSSProperties {
  return { '--course-accent': color } as CSSProperties;
}

export default function CoursesPage() {
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const eraParam = params.get('era') || '';
  const mapEraId = ERA_OVERLAYS.find((era) => era.id === eraParam) ? eraParam : DEFAULT_ERA;
  const courseEra = eraParam || 'all';
  const section = params.get('section') || 'all';
  const q = params.get('q') || '';
  const city = params.get('city') || '';
  const subEra = params.get('sub') || '';
  const cityModern = params.get('cityModern') || '';

  const gridRef = useRef<HTMLElement | null>(null);
  const [eras, setEras] = useState<Era[]>([]);
  const [items, setItems] = useState<CourseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [entered, setEntered] = useState(false);
  const [eraCourses, setEraCourses] = useState<CourseSummary[] | null>(null);

  useEffect(() => {
    const frame = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    api.eras().then((response) => setEras(response.items)).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    api.courses({ era: courseEra, section, q })
      .then((response) => setItems(response.items))
      .finally(() => setLoading(false));
  }, [courseEra, q, section]);

  useEffect(() => {
    setEraCourses(null);
    api.courses({ era: mapEraId })
      .then((response) => setEraCourses(response.items))
      .catch(() => setEraCourses([]));
  }, [mapEraId]);

  const eraTabs = useMemo(
    () => [{ id: 'all', name: '全部', period: '所有时代' }, ...eras],
    [eras],
  );
  const currentEra = ERA_OVERLAYS.find((era) => era.id === mapEraId)!;
  const cityMatches = useMemo(() => {
    if (!city) return [];
    const keywords = [city, cityModern].filter(Boolean);
    return items.filter((item) => keywords.some(
      (keyword) => item.title.includes(keyword) || item.subtitle.includes(keyword),
    ));
  }, [city, cityModern, items]);
  const visibleItems = city && cityMatches.length > 0 ? cityMatches : items;

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value && value !== 'all') next.set(key, value); else next.delete(key);
    setParams(next, { replace: true });
  };

  const setEra = (id: string) => {
    const next = new URLSearchParams(params);
    if (id && id !== 'all') next.set('era', id); else next.delete('era');
    next.delete('sub');
    setParams(next, { replace: true });
  };

  const clearCity = () => {
    const next = new URLSearchParams(params);
    next.delete('city');
    next.delete('cityModern');
    setParams(next, { replace: true });
  };

  const onPickCity = (picked: EraMapCity) => {
    const next = new URLSearchParams(params);
    next.set('era', currentEra.id);
    next.set('city', picked.name);
    if (picked.modern && picked.modern !== picked.name) next.set('cityModern', picked.modern);
    else next.delete('cityModern');
    setParams(next, { replace: true });
    requestAnimationFrame(() => gridRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  };

  return (
    <div className="chrono-courses-v2">
      <header className={`chrono-atlas-heading${entered ? ' entered' : ''}`}>
        <h1>在山河之间，找到一段历史</h1>
        <p>沿时间与地域展开课程，让城邑、道路和事件先建立联系，再进入具体课时。</p>
      </header>

      <section className={`chrono-atlas-frame${entered ? ' entered' : ''}`} aria-label="历史地图与当前时代">
        <div className="chrono-mapwrap">
          <div className="chrono-mapstage">
            <Suspense fallback={<div className="chrono-map-loading"><Spin /><span>正在展开山河图…</span></div>}>
              <EraMap
                era={currentEra}
                onCityClick={onPickCity}
                activeSubEraId={subEra || null}
                onSubEraChange={(id) => setParam('sub', id ?? '')}
                onJumpToCourses={() => gridRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
              />
            </Suspense>
          </div>

          <aside className="chrono-erapanel">
            <div className="chrono-erapanel-name">{currentEra.name}</div>
            <div className="chrono-erapanel-period">{currentEra.period}</div>
            <p className="chrono-erapanel-frontier">{currentEra.frontier}</p>
            <p className="chrono-erapanel-blurb">{currentEra.blurb}</p>

            <ol className="chrono-erapanel-events">
              {currentEra.events.map((event) => (
                <li key={`${event.year}-${event.text}`}>
                  <time>{event.year < 0 ? `前 ${-event.year}` : event.year}</time>
                  <span>{event.text}</span>
                </li>
              ))}
            </ol>

            <div className="chrono-erapanel-course-heading">
              <span>由此进入课程</span>
              <button type="button" onClick={() => setEra(currentEra.id)}>
                查看全部 <ArrowRightOutlined />
              </button>
            </div>
            {eraCourses === null ? (
              <div className="chrono-erapanel-loading"><Spin size="small" /></div>
            ) : eraCourses.length === 0 ? (
              <p className="chrono-erapanel-empty">这个时代的课程仍在整理。</p>
            ) : (
              <div className="chrono-erapanel-courses">
                {eraCourses.slice(0, 3).map((course) => (
                  <button
                    key={course.id}
                    type="button"
                    disabled={course.lesson_count === 0}
                    onClick={() => nav(`/courses/${course.id}`)}
                  >
                    <i style={{ background: course.cover_color }} />
                    <span>
                      <small>{course.section} · {course.lesson_count} 节</small>
                      <strong>{course.title}</strong>
                    </span>
                    <ArrowRightOutlined />
                  </button>
                ))}
              </div>
            )}
          </aside>
        </div>
      </section>

      <div className={`chrono-atlas-timeline${entered ? ' entered' : ''}`}>
        <EraTimeline current={mapEraId} onChange={setEra} />
      </div>

      <section ref={gridRef} className="chrono-course-catalogue" aria-labelledby="course-catalogue-title">
        <header>
          <div>
            <h2 id="course-catalogue-title">课程目录</h2>
            <p>{city
              ? cityMatches.length > 0
                ? `正在查看与「${city}」直接相关的课程。`
                : `「${city}」暂无标题直达课程，先展示${currentEra.name}课程。`
              : courseEra === 'all'
                ? '从时代与主题两个方向筛选。'
                : `当前时代：${currentEra.name} · ${currentEra.period}`}</p>
          </div>
          <EnvironmentOutlined aria-hidden="true" />
        </header>

        <div className="chrono-catalogue-filters" aria-label="课程筛选">
          <div className="chrono-filter-line">
            <span>时代</span>
            <div>
              {eraTabs.map((era) => (
                <button
                  key={era.id}
                  type="button"
                  className={courseEra === era.id ? 'is-active' : ''}
                  aria-pressed={courseEra === era.id}
                  onClick={() => setParam('era', era.id)}
                >
                  {era.name}
                </button>
              ))}
            </div>
          </div>
          <div className="chrono-filter-line">
            <span>主题</span>
            <div>
              {SECTIONS.map((item) => (
                <button
                  key={item}
                  type="button"
                  className={section === item ? 'is-active' : ''}
                  aria-pressed={section === item}
                  onClick={() => setParam('section', item)}
                >
                  {item === 'all' ? '全部' : item}
                </button>
              ))}
            </div>
          </div>
          {(q || city) && (
            <div className="chrono-active-filters" aria-live="polite">
              {q && (
                <span>
                  搜索：{q}
                  <button type="button" aria-label="清除搜索" onClick={() => setParam('q', '')}><CloseOutlined /></button>
                </span>
              )}
              {city && (
                <span>
                  地点：{city}{cityModern ? ` / ${cityModern}` : ''}
                  <button type="button" aria-label="清除地点" onClick={clearCity}><CloseOutlined /></button>
                </span>
              )}
            </div>
          )}
        </div>

        {loading ? (
          <div className="chrono-course-loading"><Spin /><span>正在整理课程目录…</span></div>
        ) : visibleItems.length === 0 ? (
          <Empty description={city ? `未找到与「${city}」相关的课程` : '暂无符合条件的课程'} />
        ) : (
          <div className="chrono-course-grid-v2">
            {visibleItems.map((course) => {
              const disabled = course.lesson_count === 0;
              const eraName = eras.find((era) => era.id === course.era_id)?.name || '历史课程';
              return (
                <button
                  key={course.id}
                  type="button"
                  className="chrono-course-entry"
                  style={courseAccentStyle(course.cover_color)}
                  disabled={disabled}
                  onClick={() => nav(`/courses/${course.id}`)}
                >
                  <span className="chrono-course-entry-cover" aria-hidden="true">
                    <i className="chrono-course-entry-contour" />
                    <small>{eraName}</small>
                    <em>{course.section}</em>
                    <b>{course.title.slice(0, 2)}</b>
                  </span>
                  <span className="chrono-course-entry-body">
                    <strong>{course.title}</strong>
                    <span>{course.subtitle}</span>
                    <small>{disabled ? '内容整理中' : `${course.lesson_count} 节课 · 沿路线进入`}</small>
                  </span>
                  <ArrowRightOutlined />
                </button>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
