import { Button, Row, Col } from 'antd';
import { useNavigate } from 'react-router-dom';

const recommended = [
  { title: '先秦 · 礼乐之邦', meta: '七年级 · 8 章 · 已选 0 人' },
  { title: '秦汉 · 大一统', meta: '七年级 · 10 章 · 已选 0 人' },
  { title: '隋唐 · 风华长安', meta: '七年级 · 9 章 · 已选 0 人' },
  { title: '隋唐 · 万邦来朝', meta: '七年级 · 9 章 · 已选 0 人' },
];

const pedagogy = [
  { tag: '看', title: '沉浸情景', desc: 'AI 生成的微视频带你回到历史现场' },
  { tag: '练', title: '决策沙盘', desc: '在关键节点做选择，看历史的另一种走向' },
  { tag: '问', title: '跨时对话', desc: '与商鞅、王安石们对谈，问出你的疑问' },
  { tag: '创', title: '历史画板', desc: '用节点和连线整理你眼中的因果脉络' },
];

export default function HomePage() {
  const nav = useNavigate();
  return (
    <div style={{ maxWidth: 1392, margin: '0 auto' }}>
      {/* Hero */}
      <Row gutter={20} style={{ marginBottom: 32 }}>
        <Col flex="auto">
          <div className="chrono-hero" style={{ height: '100%' }}>
            <div style={{ fontSize: 12, color: 'var(--accent-gold)', letterSpacing: 2, marginBottom: 8 }}>
              CHRONOVITA · v0.1.0
            </div>
            <h1>以史为鉴 · 看练问创</h1>
            <p>沉浸情景、决策沙盘、跨时对话、历史画板 — 让每一段历史都可以被推演、被追问、被再创作。</p>
            <Button type="primary" size="large" style={{ marginRight: 12 }} onClick={() => nav('/courses')}>
              进入课程中心
            </Button>
            <Button size="large" onClick={() => {
              const el = document.getElementById('chrono-pedagogy');
              if (el) el.scrollIntoView({ behavior: 'smooth' });
            }}>
              了解教学法
            </Button>
          </div>
        </Col>
        <Col flex="320px">
          <div
            className="chrono-card-dark"
            style={{ height: '100%', cursor: 'pointer' }}
            onClick={() => nav('/courses')}
          >
            <div style={{ color: 'var(--accent-gold)', fontSize: 12, marginBottom: 8 }}>本周精选</div>
            <div className="chrono-title" style={{ fontSize: 22, marginBottom: 12 }}>
              华夏文明的起源与发展
            </div>
            <div style={{ color: 'var(--text-cream-mute)', fontSize: 12 }}>
              七年级 · 第一单元
            </div>
          </div>
        </Col>
      </Row>

      {/* 推荐课程 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
        <h3 className="chrono-title" style={{ fontSize: 18, margin: 0 }}>推荐课程</h3>
        <a style={{ color: 'var(--accent-gold)', fontSize: 12 }} onClick={() => nav('/courses')}>查看更多 ›</a>
      </div>
      <Row gutter={16} style={{ marginBottom: 32 }}>
        {recommended.map((c) => (
          <Col span={6} key={c.title}>
            <div
              className="chrono-card"
              style={{ padding: 0, overflow: 'hidden', cursor: 'pointer' }}
              onClick={() => nav('/courses')}
            >
              <div style={{ height: 120, background: 'var(--accent-bronze)' }} />
              <div style={{ padding: 16 }}>
                <div className="chrono-title" style={{ fontSize: 15, marginBottom: 6 }}>{c.title}</div>
                <div style={{ color: 'var(--text-mute)', fontSize: 11 }}>{c.meta}</div>
              </div>
            </div>
          </Col>
        ))}
      </Row>

      {/* 教学法 */}
      <h3 id="chrono-pedagogy" className="chrono-title" style={{ fontSize: 18, marginBottom: 12 }}>教学法 · 看练问创</h3>
      <Row gutter={16}>
        {pedagogy.map((p) => (
          <Col span={6} key={p.tag}>
            <div
              className="chrono-card-dark"
              style={{ minHeight: 180, cursor: 'pointer' }}
              onClick={() => nav('/practice')}
            >
              <div style={{ fontSize: 48, color: 'var(--accent-gold)', fontWeight: 700, marginBottom: 8 }}>
                {p.tag}
              </div>
              <div className="chrono-title" style={{ fontSize: 16, marginBottom: 6, color: 'var(--text-cream)' }}>
                {p.title}
              </div>
              <div style={{ color: 'var(--text-cream-mute)', fontSize: 12 }}>{p.desc}</div>
            </div>
          </Col>
        ))}
      </Row>
    </div>
  );
}
