/**
 * PageShell · 最基础的页面外壳
 * 用法：复制到 apps/web/src/pages/，把 children 替换成业务区块即可。
 */
import type { ReactNode } from 'react';

interface Props {
  title: string;
  subtitle?: string;
  maxWidth?: number;
  extra?: ReactNode;
  children: ReactNode;
}

export default function PageShell({ title, subtitle, maxWidth = 1392, extra, children }: Props) {
  return (
    <div style={{ maxWidth, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 24 }}>
        <div>
          <h1 className="chrono-title" style={{ fontSize: 26, margin: 0 }}>{title}</h1>
          {subtitle && (
            <div style={{ color: 'var(--text-mute)', fontSize: 13, marginTop: 6 }}>{subtitle}</div>
          )}
        </div>
        {extra}
      </div>
      {children}
    </div>
  );
}
