import { useState } from 'react';
import { toast } from '../utils/toast';
import { Button, Row, Col } from 'antd';
import { useNavigate } from 'react-router-dom';

const filters = ['全部', '先秦', '秦汉', '隋唐', '宋元', '明清'];

const panels = [
  { tag: '练', title: '决策沙盘', desc: '在历史关键节点上做选择，体验事件的不同走向。', meta: 'v0.4.x · 决策推演引擎', cta: '进入沙盘', stage: 'v0.4.x' },
  { tag: '问', title: '跨时对话', desc: '与历史人物面对面追问 — 由 LLM 适配层驱动，可切换专家视角。', meta: 'v0.5.x · 双模智者', cta: '开始对话', stage: 'v0.5.x' },
  { tag: '创', title: '历史画板', desc: '用节点与连线整理因果脉络，把「我学到了什么」画成一张图谱。', meta: 'v0.6.x · 知识谱系画布', cta: '进入画板', stage: 'v0.6.x' },
];

export default function PracticePage() {
  const [filter, setFilter] = useState(0);
  const nav = useNavigate();
  return (
    <div style={{ maxWidth: 1392, margin: '0 auto' }}>
      <div style={{ marginBottom: 16 }}>
        <h1 className="chrono-title" style={{ fontSize: 26, margin: 0 }}>实践课堂</h1>
        <div style={{ color: 'var(--text-mute)', fontSize: 13, marginTop: 6 }}>
          自己上沙盘、找古人对谈、把所学画成图 — 在做中学，用历史解释当下。
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
        {filters.map((f, i) => (
          <span key={f}
                onClick={() => setFilter(i)}
                className={`chrono-chip${i === filter ? ' active' : ''}`}>
            {f}
          </span>
        ))}
      </div>

      <Row gutter={16} style={{ marginBottom: 32 }}>
        {panels.map((p) => (
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
                <div style={{ color: 'var(--text-mute)', fontSize: 12, marginBottom: 8 }}>{p.desc}</div>
                <div style={{ color: 'var(--text-disabled)', fontSize: 10, marginBottom: 14 }}>{p.meta}</div>
                <Button type="primary"
                        onClick={() => {
                          toast.info(`「${p.title}」将在 ${p.stage} 上线，先到课程中心看看吧`);
                          nav('/courses');
                        }}>
                  {p.cta} ›
                </Button>
              </div>
            </div>
          </Col>
        ))}
      </Row>

      <h3 className="chrono-title" style={{ fontSize: 16, marginBottom: 12 }}>我的实践记录</h3>
      <div className="chrono-empty">
        <div style={{ color: 'var(--text-disabled)', marginBottom: 4 }}>暂无实践记录</div>
        <div style={{ fontSize: 12 }}>完成的沙盘、对话与画板会出现在这里</div>
      </div>
    </div>
  );
}
