import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Tag, Row, Col } from 'antd';
import { api } from '../utils/api';

const PANELS = [
  {
    tag: '练', title: '决策沙盘', desc: '在历史关键节点上做选择，体验事件的不同走向。',
    target: '/courses/C-prequin-state/lessons/L103?layer=practice',
    cta: '进入「商鞅变法」沙盘',
  },
  {
    tag: '问', title: '跨时对话', desc: '与历史教师/同窗对话 — 由 DeepSeek 驱动，可流式输出。',
    target: '/courses/C-prequin-state/lessons/L103?layer=ask',
    cta: '开始对话',
  },
  {
    tag: '创', title: '历史画板', desc: '用节点与连线整理因果脉络 — 节点会保存到云端。',
    target: '/courses/C-prequin-state/lessons/L103?layer=create',
    cta: '进入画板',
  },
];

export default function PracticePage() {
  const nav = useNavigate();
  const [provider, setProvider] = useState('');
  useEffect(() => { api.llmInfo().then((r) => setProvider(r.provider)).catch(() => {}); }, []);

  return (
    <div style={{ maxWidth: 1392, margin: '0 auto' }}>
      <div style={{ marginBottom: 16 }}>
        <h1 className="chrono-title" style={{ fontSize: 26, margin: 0 }}>实践课堂</h1>
        <div style={{ color: 'var(--text-mute)', fontSize: 13, marginTop: 6 }}>
          自己上沙盘、找古人对谈、把所学画成图 — 在做中学，用历史解释当下。
          {provider && <Tag color="gold" style={{ marginLeft: 12 }}>当前 LLM：{provider}</Tag>}
        </div>
      </div>

      <Row gutter={16} style={{ marginBottom: 32 }}>
        {PANELS.map((p) => (
          <Col span={8} key={p.tag}>
            <div className="chrono-card" style={{ padding: 0, overflow: 'hidden' }}>
              <div style={{
                background: 'var(--bg-navy)', height: 160,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <div style={{ fontSize: 64, fontWeight: 700, color: 'var(--accent-gold)' }}>{p.tag}</div>
              </div>
              <div style={{ padding: 20 }}>
                <div className="chrono-title" style={{ fontSize: 18, marginBottom: 6 }}>{p.title}</div>
                <div style={{ color: 'var(--text-mute)', fontSize: 12, marginBottom: 14 }}>{p.desc}</div>
                <Button type="primary" onClick={() => nav(p.target)}>{p.cta} ›</Button>
              </div>
            </div>
          </Col>
        ))}
      </Row>

      <h3 className="chrono-title" style={{ fontSize: 16, marginBottom: 12 }}>已上线剧本</h3>
      <div className="chrono-card" style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <Tag color="gold">先秦</Tag>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14 }}>商鞅变法 · 你是秦孝公的谋臣</div>
          <div style={{ fontSize: 12, color: 'var(--text-mute)' }}>5 个决策节点 · 3 种结局 · 含国力/民心/贵族支持三维状态</div>
        </div>
        <Button onClick={() => nav('/courses/C-prequin-state/lessons/L103?layer=practice')}>立即进入</Button>
      </div>

      <div style={{ marginTop: 24, color: 'var(--text-disabled)', fontSize: 12 }}>
        更多剧本将在后续版本上线 · 也可以在课程页面中按节进入对应的练问创层。
      </div>
    </div>
  );
}
