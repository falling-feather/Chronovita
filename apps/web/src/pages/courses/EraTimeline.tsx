// 时代时间轴 · 6 段位 · v0.2.2
import { ERA_OVERLAYS } from './eraMap';

interface Props {
  current: string;
  onChange: (id: string) => void;
}

export default function EraTimeline({ current, onChange }: Props) {
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
              tabIndex={active ? 0 : -1}
              type="button"
              className={`chrono-eratl-stop${active ? ' active' : ''}`}
              onClick={() => onChange(e.id)}
              onKeyDown={(event) => {
                const next = event.key === 'ArrowLeft' ? Math.max(0, i - 1)
                  : event.key === 'ArrowRight' ? Math.min(ERA_OVERLAYS.length - 1, i + 1)
                    : event.key === 'Home' ? 0 : event.key === 'End' ? ERA_OVERLAYS.length - 1 : null;
                if (next === null) return;
                event.preventDefault();
                onChange(ERA_OVERLAYS[next].id);
                event.currentTarget.parentElement?.querySelectorAll('button')[next]?.focus();
              }}
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
