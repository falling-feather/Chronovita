import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Tag, Spin, Empty } from 'antd';
import { api, type CourseSummary, type Era } from '../utils/api';

const SECTIONS = ['all', '通史', '思想', '制度', '文化'];

export default function CoursesPage() {
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const era = params.get('era') || 'all';
  const section = params.get('section') || 'all';
  const q = params.get('q') || '';

  const [eras, setEras] = useState<Era[]>([]);
  const [items, setItems] = useState<CourseSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { api.eras().then((r) => setEras(r.items)).catch(() => {}); }, []);

  useEffect(() => {
    setLoading(true);
    api.courses({ era, section, q }).then((r) => setItems(r.items)).finally(() => setLoading(false));
  }, [era, section, q]);

  const eraTabs = useMemo(() => [{ id: 'all', name: '全部', period: '所有时代' }, ...eras], [eras]);

  const setParam = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v && v !== 'all') next.set(k, v); else next.delete(k);
    setParams(next, { replace: true });
  };

  return (
    <div style={{ maxWidth: 1392, margin: '0 auto' }}>
      <div style={{ marginBottom: 12 }}>
        <h1 className="chrono-title" style={{ fontSize: 28, margin: 0 }}>课程中心</h1>
        <div style={{ color: 'var(--text-mute)', fontSize: 13, marginTop: 6 }}>
          按时代 / 板块筛选课程；选择后进入课程详情，再开始学习。
        </div>
      </div>

      {/* 时代筛选 */}
      <div className="chrono-card-warm" style={{ marginBottom: 16, padding: '14px 18px' }}>
        <div style={{ fontSize: 12, color: 'var(--text-mute)', marginBottom: 8 }}>时代</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {eraTabs.map((e: any) => (
            <span key={e.id}
                  className={`chrono-chip${era === e.id ? ' active' : ''}`}
                  onClick={() => setParam('era', e.id)}>
              {e.name}{e.id !== 'all' && <span style={{ color: 'var(--text-disabled)', marginLeft: 6, fontSize: 10 }}>{e.period}</span>}
            </span>
          ))}
        </div>
      </div>

      {/* 板块筛选 */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap' }}>
        {SECTIONS.map((s) => (
          <span key={s}
                className={`chrono-chip${section === s ? ' active' : ''}`}
                onClick={() => setParam('section', s)}>
            {s === 'all' ? '全部板块' : s}
          </span>
        ))}
        {q && (
          <span className="chrono-chip" style={{ background: 'var(--bg-tint)', borderColor: 'var(--accent-gold)' }}>
            搜索: {q}
            <a style={{ marginLeft: 8, color: 'var(--text-mute)' }}
               onClick={() => setParam('q', '')}>×</a>
          </span>
        )}
      </div>

      {/* 课程网格 */}
      {loading ? <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div> :
        items.length === 0 ? <Empty description="暂无符合条件的课程" /> :
        <div className="chrono-course-grid">
          {items.map((c) => {
            const disabled = c.lesson_count === 0;
            return (
              <div key={c.id}
                   className="chrono-card chrono-course-card"
                   style={{ padding: 0, overflow: 'hidden', cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.6 : 1 }}
                   onClick={() => !disabled && nav(`/courses/${c.id}`)}>
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
      }
    </div>
  );
}
