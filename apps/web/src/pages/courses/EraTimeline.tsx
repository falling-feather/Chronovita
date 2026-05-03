// 时代时间轴 · 6 段位 · v0.2.2
import { useEffect } from 'react';
import { ERA_OVERLAYS } from './eraMap';

interface Props {
  current: string;
  onChange: (id: string) => void;
}

export default function EraTimeline({ current, onChange }: Props) {
  // 键盘 ←/→ 切换时代
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      const idx = ERA_OVERLAYS.findIndex((x) => x.id === current);
      if (idx === -1) return;
      if (e.key === 'ArrowLeft' && idx > 0) onChange(ERA_OVERLAYS[idx - 1].id);
      if (e.key === 'ArrowRight' && idx < ERA_OVERLAYS.length - 1) onChange(ERA_OVERLAYS[idx + 1].id);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [current, onChange]);

  const idx = ERA_OVERLAYS.findIndex((x) => x.id === current);
  const progress = idx === -1 ? 0 : (idx / (ERA_OVERLAYS.length - 1)) * 100;

  return (
    <div className="chrono-eratl" role="tablist" aria-label="时代时间轴">
      <div className="chrono-eratl-track" />
      <div className="chrono-eratl-progress" style={{ width: `${progress}%` }} />
      <div className="chrono-eratl-rail">
        {ERA_OVERLAYS.map((e, i) => {
          const active = e.id === current;
          return (
            <button
              key={e.id}
              role="tab"
              aria-selected={active}
              type="button"
              className={`chrono-eratl-stop${active ? ' active' : ''}`}
              onClick={() => onChange(e.id)}
              style={{ left: `${(i / (ERA_OVERLAYS.length - 1)) * 100}%` }}
            >
              <span className="chrono-eratl-dot" style={active ? { background: e.hue.primary } : undefined} />
              <span className="chrono-eratl-label">
                <span className="chrono-eratl-name">{e.name}</span>
                <span className="chrono-eratl-period">{e.period}</span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
