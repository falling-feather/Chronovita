import { describe, expect, it } from 'vitest';
import type { GameDossier } from '../../utils/api';
import { projectDossierKnowledge } from './dossierProjection';

function dossier(overrides: Partial<GameDossier> = {}): GameDossier {
  return {
    schema_version: 'dossier/v1', dossier_id: 'd1', session_id: 's1', user_id: 'u1',
    course_id: 'C-prequin-state', lesson_id: 'L103', scenario_id: 'scenario-l103',
    course_content_version: 3, scenario_version: 1, course_checksum: 'course-sha',
    scenario_checksum: 'scenario-sha', status: 'final', title: '商鞅变法史官卷宗',
    ending_id: 'ending-1', strategy_summary: '公开规则并分阶段推进。',
    key_choices: [{ turn_id: 't1', turn_no: 1, action_id: 'listen', choice: '听取陈述', consequence: '争议显现。' }],
    state_trajectory: [{ turn_no: 1, state: { 国力: 3, 民生: 2 } }],
    major_costs: ['执行成本上升'], historical_explanation: '改革改变了国家动员方式。',
    knowledge_nodes: [], knowledge_edges: [], follow_up_questions: [], reflection_notes: [],
    fact_refs: ['fact-1'], source_ref_ids: ['source-1'], generated_at: '2026-08-14T00:00:00Z',
    checksum: 'dossier-sha', ...overrides,
  };
}

describe('projectDossierKnowledge', () => {
  it('derives a stable source-bound graph for a valid legacy final dossier', () => {
    const first = projectDossierKnowledge(dossier());
    const second = projectDossierKnowledge(dossier());

    expect(first).toEqual(second);
    expect(first.derived).toBe(true);
    expect(first.nodes.map((node) => node.node_id)).toContain('state-trajectory');
    expect(first.nodes.every((node) => node.source_ref_ids.includes('source-1'))).toBe(true);
    expect(first.edges.length).toBeGreaterThan(0);
  });

  it('preserves authored knowledge nodes and edges unchanged', () => {
    const authoredNode = {
      node_id: 'authored', label: '既有节点', kind: 'concept' as const,
      summary: '已审校。', source_ref_ids: ['source-1'],
    };
    const result = projectDossierKnowledge(dossier({ knowledge_nodes: [authoredNode] }));

    expect(result).toEqual({ nodes: [authoredNode], edges: [], derived: false });
  });
});
