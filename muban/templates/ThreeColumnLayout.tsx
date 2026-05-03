/**
 * ThreeColumnLayout · 左目录 / 中主体 / 右辅助
 * 仿《课程中心》。中栏使用 minmax(0,1fr) 防止子内容撑破布局。
 *
 * 需要的 CSS（apps/web/src/styles/global.css 已就位）：
 *   .chrono-courses-grid { display:grid; grid-template-columns:220px minmax(0,1fr) 300px; gap:16px }
 */
import type { ReactNode } from 'react';

interface Props {
  left: ReactNode;
  center: ReactNode;
  right: ReactNode;
  maxWidth?: number;
}

export default function ThreeColumnLayout({ left, center, right, maxWidth = 1536 }: Props) {
  return (
    <div style={{ maxWidth, margin: '0 auto' }}>
      <div className="chrono-courses-grid">
        <div className="chrono-courses-side">{left}</div>
        <div className="chrono-courses-main">{center}</div>
        <div className="chrono-courses-side">{right}</div>
      </div>
    </div>
  );
}
