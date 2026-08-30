import './ScenarioNpcDialogue.css';

export type ScenarioNpcDialogueRoute =
  | 'local-script'
  | 'local-evidence'
  | 'api-assisted'
  | 'safe-fallback'
  | 'rejected';

export type ScenarioNpcDialogueStatus =
  | 'active'
  | 'completed'
  | 'failed'
  | 'abandoned';

export interface ScenarioNpcPortrait {
  src?: string;
  srcSet?: string;
  alt: string;
}

export interface ScenarioNpcDialogueProps {
  turnNo: number;
  person: {
    name: string;
    role: string;
    portrait: ScenarioNpcPortrait;
  };
  playerStatement: string;
  situationNarrative: string;
  speech: string;
  route: {
    kind: ScenarioNpcDialogueRoute;
    label?: string;
  };
  status?: ScenarioNpcDialogueStatus;
  statusLabel?: string;
  disclaimer?: string;
}

const ROUTE_LABELS: Record<ScenarioNpcDialogueRoute, string> = {
  'local-script': '课堂规则回应',
  'local-evidence': '课程资料回应',
  'api-assisted': '资料核对后回应',
  'safe-fallback': '离线安全回应',
  rejected: '本轮未作答',
};

const STATUS_LABELS: Record<ScenarioNpcDialogueStatus, string> = {
  active: '推演进行中',
  completed: '推演完成',
  failed: '推演结束 · 需要复盘',
  abandoned: '推演已结束',
};

const DEFAULT_DISCLAIMER = '角色化教学表达，不是史料原话。';

export function scenarioNpcRouteLabel(route: ScenarioNpcDialogueRoute): string {
  return ROUTE_LABELS[route];
}

export function ScenarioNpcDialogue({
  turnNo,
  person,
  playerStatement,
  situationNarrative,
  speech,
  route,
  status = 'active',
  statusLabel,
  disclaimer = DEFAULT_DISCLAIMER,
}: ScenarioNpcDialogueProps) {
  const resolvedRouteLabel = route.label?.trim() || scenarioNpcRouteLabel(route.kind);
  const resolvedStatusLabel = statusLabel?.trim() || STATUS_LABELS[status];
  const initial = person.name.trim().slice(0, 1) || '史';

  return (
    <article
      className={`chrono-scenario-dialogue route-${route.kind} status-${status}`}
      aria-label={`第 ${turnNo} 回合人物回应`}
      aria-live="polite"
    >
      <header className="chrono-scenario-dialogue__header">
        <div className="chrono-scenario-dialogue__turn">
          <span>第 {turnNo} 回合</span>
          <strong>{resolvedStatusLabel}</strong>
        </div>
        <span
          className="chrono-scenario-dialogue__route"
          aria-label={`回答路径：${resolvedRouteLabel}`}
        >
          <i aria-hidden="true" />
          {resolvedRouteLabel}
        </span>
      </header>

      <section className="chrono-scenario-dialogue__statement" aria-label="你的陈策">
        <span>你的陈策</span>
        <blockquote>{playerStatement}</blockquote>
      </section>

      <section className="chrono-scenario-dialogue__situation" aria-label="局势旁白">
        <span aria-hidden="true">局势</span>
        <p>{situationNarrative}</p>
      </section>

      <section className="chrono-scenario-dialogue__response" aria-label={`${person.name}的回应`}>
        <div className="chrono-scenario-dialogue__portrait">
          {person.portrait.src ? (
            <img
              src={person.portrait.src}
              srcSet={person.portrait.srcSet}
              alt={person.portrait.alt}
              loading="lazy"
              decoding="async"
            />
          ) : (
            <span role="img" aria-label={`${person.name}人物剪影`}>{initial}</span>
          )}
        </div>
        <div className="chrono-scenario-dialogue__voice">
          <header>
            <strong>{person.name}</strong>
            <span>{person.role}</span>
          </header>
          <blockquote>{speech}</blockquote>
          <small>{disclaimer}</small>
        </div>
      </section>
    </article>
  );
}
