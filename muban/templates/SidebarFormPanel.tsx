/**
 * SidebarFormPanel · 左侧菜单 + 右侧表单
 * 仿《个人中心》。菜单状态受控；右侧 children 由调用方根据 active 决定。
 */
import { useState, type ReactNode } from 'react';
import { Row, Col } from 'antd';

interface MenuItem { icon?: ReactNode; label: string; dim?: boolean; onClick?: () => void }
interface Props {
  menu: MenuItem[];
  header?: ReactNode;
  renderRight: (activeIndex: number) => ReactNode;
}

export default function SidebarFormPanel({ menu, header, renderRight }: Props) {
  const [active, setActive] = useState(0);
  return (
    <div style={{ maxWidth: 1392, margin: '0 auto' }}>
      <Row gutter={16}>
        <Col flex="280px">
          <div className="chrono-card" style={{ padding: 0 }}>
            {header}
            <div style={{ height: 1, background: 'var(--border-soft)' }} />
            <div style={{ padding: '12px 0' }}>
              {menu.map((m, i) => {
                const isActive = i === active;
                return (
                  <div key={m.label}
                       onClick={() => { if (m.onClick) m.onClick(); else setActive(i); }}
                       style={{
                         display: 'flex', alignItems: 'center', gap: 10, padding: '10px 20px',
                         background: isActive ? 'var(--bg-tint)' : 'transparent',
                         color: isActive ? 'var(--accent-gold)' : (m.dim ? 'var(--text-disabled)' : 'var(--text-dark)'),
                         fontWeight: isActive ? 600 : 400, cursor: 'pointer', fontSize: 13,
                       }}>
                    {m.icon}<span>{m.label}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </Col>
        <Col flex="auto">{renderRight(active)}</Col>
      </Row>
    </div>
  );
}
