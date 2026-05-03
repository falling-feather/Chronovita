import { useState } from 'react';
import { Avatar, Button, Progress, Row, Col } from 'antd';
import { UserOutlined, PlusOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

const stats = [
  { v: '0', l: '进行中' },
  { v: '0', l: '已完成' },
  { v: '0', l: '收藏' },
  { v: '0min', l: '本周时长' },
];

const tabs = ['进行中', '我的收藏', '学习记录', '我的笔记'];

export default function LearningPage() {
  const nav = useNavigate();
  const [tab, setTab] = useState(0);
  return (
    <div style={{ maxWidth: 1392, margin: '0 auto' }}>
      <div className="chrono-card-warm" style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <Avatar size={56} icon={<UserOutlined />} style={{ background: 'var(--accent-gold)' }} />
          <div>
            <div className="chrono-title" style={{ fontSize: 22 }}>你好，未命名学徒</div>
            <div style={{ color: 'var(--text-mute)', fontSize: 12, marginTop: 4 }}>
              v0.1.0 占位 · 待你开启第一节课
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 32 }}>
          {stats.map((s) => (
            <div key={s.l}
                 style={{ textAlign: 'center' }}>
              <div className="chrono-title" style={{ fontSize: 26, color: 'var(--accent-gold)' }}>{s.v}</div>
              <div style={{ fontSize: 11, color: 'var(--text-mute)' }}>{s.l}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, borderBottom: '1px solid var(--border-soft)', marginBottom: 20 }}>
        {tabs.map((t, i) => (
          <div key={t}
               onClick={() => setTab(i)}
               style={{
                 padding: '10px 0',
                 borderBottom: i === tab ? '2px solid var(--accent-gold)' : '2px solid transparent',
                 color: i === tab ? 'var(--accent-gold)' : 'var(--text-mute)',
                 fontWeight: i === tab ? 600 : 400,
                 cursor: 'pointer',
                 fontSize: 14,
               }}>{t}</div>
        ))}
      </div>

      <Row gutter={16} style={{ marginBottom: 32 }}>
        <Col span={12}>
          <div className="chrono-card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{ display: 'flex' }}>
              <div style={{ width: 180, background: 'var(--accent-bronze)' }} />
              <div style={{ padding: 20, flex: 1 }}>
                <div className="chrono-title" style={{ fontSize: 16 }}>华夏文明的起源与发展</div>
                <div style={{ color: 'var(--text-mute)', fontSize: 12, margin: '6px 0 14px' }}>
                  上次学到：第一单元 · 1.3 大禹治水
                </div>
                <Progress percent={42} strokeColor="var(--accent-gold)" showInfo={false} />
                <div style={{ fontSize: 11, color: 'var(--text-mute)', margin: '4px 0 14px' }}>已完成 42%</div>
                <Button type="primary"
                        onClick={() => nav('/courses')}>
                  继续学习
                </Button>
              </div>
            </div>
          </div>
        </Col>
        <Col span={12}>
          <div className="chrono-empty"
               onClick={() => nav('/courses')}
               style={{
                 display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%',
                 border: '1px dashed var(--border-soft)', cursor: 'pointer',
               }}>
            <PlusOutlined style={{ fontSize: 28, color: 'var(--text-disabled)', marginBottom: 8 }} />
            <div style={{ color: 'var(--text-mute)' }}>添加新课程</div>
          </div>
        </Col>
      </Row>

      <h3 className="chrono-title" style={{ fontSize: 16, marginBottom: 12 }}>我的收藏</h3>
      <div className="chrono-empty">
        <div style={{ color: 'var(--text-disabled)', marginBottom: 4 }}>暂无收藏</div>
        <div style={{ fontSize: 12 }}>课程详情页点击 ☆ 即可加入收藏</div>
      </div>
    </div>
  );
}
