import type {
  GameDossier,
  GameDossierKnowledgeEdge,
  GameDossierKnowledgeNode,
} from '../../utils/api';

export interface DossierKnowledgeProjection {
  nodes: GameDossierKnowledgeNode[];
  edges: GameDossierKnowledgeEdge[];
  derived: boolean;
}

function stateTrajectorySummary(dossier: GameDossier): string {
  return dossier.state_trajectory.map((snapshot) => {
    const values = Object.entries(snapshot.state)
      .map(([key, value]) => `${key} ${value}`)
      .join('、');
    return `第 ${snapshot.turn_no} 回合：${values}`;
  }).join('；');
}

/**
 * DossierV1 permits a final dossier without authored knowledge nodes. Older
 * releases used that valid shape, so the student client derives a stable
 * canvas projection instead of changing the signed dossier itself.
 */
export function projectDossierKnowledge(dossier: GameDossier): DossierKnowledgeProjection {
  if (dossier.knowledge_nodes.length > 0) {
    return {
      nodes: dossier.knowledge_nodes,
      edges: dossier.knowledge_edges,
      derived: false,
    };
  }

  const sourceRefIds = [...dossier.source_ref_ids];
  const nodes: GameDossierKnowledgeNode[] = [];
  const edges: GameDossierKnowledgeEdge[] = [];

  nodes.push({
    node_id: 'strategy',
    label: '治理策略',
    kind: 'concept',
    summary: dossier.strategy_summary || '本次推演形成的总体治理策略。',
    source_ref_ids: sourceRefIds,
  });

  let previousNodeId = 'strategy';
  dossier.key_choices.forEach((choice) => {
    const nodeId = `choice-${choice.turn_no}-${choice.action_id}`;
    nodes.push({
      node_id: nodeId,
      label: `第 ${choice.turn_no} 回合：${choice.choice}`,
      kind: 'cause',
      summary: choice.consequence || '这一选择推动了后续局势变化。',
      source_ref_ids: sourceRefIds,
    });
    edges.push({
      edge_id: `sequence-${previousNodeId}-${nodeId}`,
      source_node_id: previousNodeId,
      target_node_id: nodeId,
      relation: previousNodeId === 'strategy' ? '落实为' : '继而',
      explanation: '按本次六回合推演的选择顺序连接。',
      source_ref_ids: sourceRefIds,
    });
    previousNodeId = nodeId;
  });

  if (dossier.state_trajectory.length > 0) {
    nodes.push({
      node_id: 'state-trajectory',
      label: '状态轨迹',
      kind: 'event',
      summary: stateTrajectorySummary(dossier),
      source_ref_ids: sourceRefIds,
    });
    edges.push({
      edge_id: `trajectory-${previousNodeId}`,
      source_node_id: previousNodeId,
      target_node_id: 'state-trajectory',
      relation: '产生变化',
      explanation: '选择序列与推演状态轨迹的对应关系。',
      source_ref_ids: sourceRefIds,
    });
    previousNodeId = 'state-trajectory';
  }

  nodes.push({
    node_id: 'historical-explanation',
    label: '历史解释',
    kind: 'consequence',
    summary: dossier.historical_explanation || '本次卷宗尚未配置结局解释。',
    source_ref_ids: sourceRefIds,
  });
  edges.push({
    edge_id: `explanation-${previousNodeId}`,
    source_node_id: previousNodeId,
    target_node_id: 'historical-explanation',
    relation: '据此解释',
    explanation: '由推演过程进入经审校的历史解释。',
    source_ref_ids: sourceRefIds,
  });

  if (dossier.major_costs.length > 0) {
    nodes.push({
      node_id: 'major-costs',
      label: '制度与治理代价',
      kind: 'consequence',
      summary: dossier.major_costs.join('；'),
      source_ref_ids: sourceRefIds,
    });
    edges.push({
      edge_id: 'costs-historical-explanation-major-costs',
      source_node_id: 'historical-explanation',
      target_node_id: 'major-costs',
      relation: '同时付出',
      explanation: '成功、折中或失败结局均需与其代价一并复盘。',
      source_ref_ids: sourceRefIds,
    });
  }

  return { nodes, edges, derived: true };
}
