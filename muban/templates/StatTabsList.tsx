/**
 * StatTabsList · 顶部头像+统计 / 中部 Tab / 下部内容卡
 * 仿《我的学习》。Tab 切换使用受控 useState。
 */
import { useState, type ReactNode } from 'react';
import { Avatar } from 'antd';
import { UserOutlined } from '@ant-design/icons';

interface Stat { v: string; l: string }
interface Props {
  greeting: string;
  hint?: string;
  stats: Stat[];
  tabs: string[];
  renderTab: (index: number) => ReactNode;
}

export default function StatTabsList({ greeting, hint, stats, tabs, renderTab }: Props) {
  const [tab, setTab] = useState(0);
  return (
    <div style={{ maxWidth: 1392, margin: '0 auto' }}>
      <div className="chrono-card-warm" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <Avatar size={56} icon={<UserOutlined />} style={{ background: 'var(--accent-gold)' }} />
          <div>
            <div className="chrono-title" style={{ fontSize: 22 }}>{greeting}</div>
            {hint && <div style={{ color: 'var(--text-mute)', fontSize: 12, marginTop: 4 }}>{hint}</div>}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 32 }}>
          {stats.map((s) => (
            <div key={s.l} style={{ textAlign: 'center' }}>
              <div className="chrono-title" style={{ fontSize: 26, color: 'var(--accent-gold)' }}>{s.v}</div>
              <div style={{ fontSize: 11, color: 'var(--text-mute)' }}>{s.l}</div>
            </div>
          ))}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 24, borderBottom: '1px solid var(--border-soft)', marginBottom: 20 }}>
        {tabs.map((t, i) => (
          <div key={t} onClick={() => setTab(i)}
               style={{
                 padding: '10px 0',
                 borderBottom: i === tab ? '2px solid var(--accent-gold)' : '2px solid transparent',
                 color: i === tab ? 'var(--accent-gold)' : 'var(--text-mute)',
                 fontWeight: i === tab ? 600 : 400, cursor: 'pointer', fontSize: 14,
               }}>{t}</div>
        ))}
      </div>
      {renderTab(tab)}
    </div>
  );
}
