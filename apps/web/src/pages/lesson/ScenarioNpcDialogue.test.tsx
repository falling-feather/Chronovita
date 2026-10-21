import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import {
  ScenarioNpcDialogue,
  scenarioNpcRouteLabel,
  type ScenarioNpcDialogueRoute,
} from './ScenarioNpcDialogue';

const ROUTES: ScenarioNpcDialogueRoute[] = [
  'local-script',
  'local-evidence',
  'api-assisted',
  'safe-fallback',
  'rejected',
];

describe('ScenarioNpcDialogue', () => {
  it('renders the decision, neutral situation and attributed character speech separately', () => {
    const html = renderToStaticMarkup(
      <ScenarioNpcDialogue
        turnNo={2}
        person={{
          name: '禹',
          role: '治水共同体的协调者',
          portrait: { src: '/assets/persona/yu.webp', alt: '课堂情境中的禹' },
        }}
        playerStatement="先踏勘地势，再组织各聚落疏导河道。"
        situationNarrative="众人重新标记低地与支流，洪水风险尚未解除。"
        speech="此策可行，但须说明由谁承担劳役，又如何照顾下游聚落。"
        route={{ kind: 'local-evidence' }}
      />,
    );

    expect(html).toContain('第 2 回合');
    expect(html).toContain('你的陈策');
    expect(html).toContain('局势旁白');
    expect(html).toContain('禹的回应');
    expect(html).toContain('课程资料回应');
    expect(html).toContain('角色化教学表达，不是史料原话。');
    expect(html.indexOf('你的陈策')).toBeLessThan(html.indexOf('局势旁白'));
    expect(html.indexOf('局势旁白')).toBeLessThan(html.indexOf('禹的回应'));
  });

  it('uses a text portrait fallback and exposes terminal state without decorative image noise', () => {
    const html = renderToStaticMarkup(
      <ScenarioNpcDialogue
        turnNo={6}
        person={{ name: '商鞅', role: '秦国改革主持者', portrait: { alt: '商鞅人物剪影' } }}
        playerStatement="以公开法令推动改革。"
        situationNarrative="新令已经公布，但执行代价仍在累积。"
        speech="法令既出，仍须检验能否持续执行。"
        route={{ kind: 'safe-fallback' }}
        status="completed"
      />,
    );

    expect(html).toContain('推演完成');
    expect(html).toContain('离线安全回应');
    expect(html).toContain('aria-label="商鞅人物剪影"');
    expect(html).not.toContain('<img');
  });

  it('keeps every internal route translated into classroom language', () => {
    expect(ROUTES.map(scenarioNpcRouteLabel)).toEqual([
      '课堂规则回应',
      '课程资料回应',
      '资料核对后回应',
      '离线安全回应',
      '本轮未作答',
    ]);
    expect(ROUTES.map(scenarioNpcRouteLabel).join(' ')).not.toMatch(/API|RAG|LLM/i);
  });
});
