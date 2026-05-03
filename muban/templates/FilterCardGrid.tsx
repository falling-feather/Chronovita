/**
 * FilterCardGrid · 顶部 Chip 筛选 + 卡片网格
 * 仿《实践课堂》。筛选用受控 useState，卡片渲染交给 renderCard。
 */
import { useState, type ReactNode } from 'react';
import { Row, Col } from 'antd';

interface Props<T> {
  filters: string[];
  items: T[];
  filterFn?: (item: T, filterIndex: number) => boolean;
  renderCard: (item: T) => ReactNode;
  span?: number;
}

export default function FilterCardGrid<T>({ filters, items, filterFn, renderCard, span = 8 }: Props<T>) {
  const [active, setActive] = useState(0);
  const visible = filterFn ? items.filter((it) => filterFn(it, active)) : items;
  return (
    <>
      <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
        {filters.map((f, i) => (
          <span key={f} onClick={() => setActive(i)}
                className={`chrono-chip${i === active ? ' active' : ''}`}>{f}</span>
        ))}
      </div>
      <Row gutter={16}>
        {visible.map((it, i) => (
          <Col span={span} key={i}>{renderCard(it)}</Col>
        ))}
      </Row>
    </>
  );
}
