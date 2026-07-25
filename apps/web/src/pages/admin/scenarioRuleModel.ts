import type {
  RuntimeScenarioRecord,
  ScenarioAuthorDraft,
  ScenarioDraftAction,
  ScenarioDraftCondition,
  ScenarioDraftEffect,
  ScenarioDraftEnding,
  ScenarioDraftEvent,
  ScenarioDraftNpc,
  ScenarioDraftValidationIssue,
  ScenarioDraftVariable,
  ScenarioType,
} from '../../utils/api';

export const SCENARIO_TYPE_OPTIONS: { value: ScenarioType; label: string }[] = [
  { value: 'crisis_governance', label: '危机治理' },
  { value: 'institutional_reform', label: '制度改革' },
  { value: 'council', label: '议事决策' },
];

export const COMPARISON_OPTIONS = [
  { value: 'gte', label: '大于等于' },
  { value: 'lte', label: '小于等于' },
  { value: 'gt', label: '大于' },
  { value: 'lt', label: '小于' },
  { value: 'eq', label: '等于' },
] as const;

export function createScenarioDraft(): ScenarioAuthorDraft {
  return {
    schema_version: 'scenario-author-draft/v1',
    scenario_id: `scenario-${Date.now().toString(36)}`,
    course_id: 'C-course-id',
    lesson_id: 'lesson-id',
    title: '历史抉择局',
    scenario_type: 'crisis_governance',
    student_role: '本课历史情境中的决策者',
    objective: '通过取舍推动局势，并说明每次选择的依据与代价。',
    opening: '教师在这里交代学生进入关卡时面对的局势。',
    max_turns: 6,
    variables: [createVariable('progress', '推进度')],
    npcs: [],
    action_rules: [createAction('advance-carefully', '稳步推进', 'progress')],
    event_rules: [],
    ending_rules: [
      createEnding('ending-progress', '阶段目标达成', 'progress'),
      {
        ...createEnding('ending-turn-limit', '进入复盘', ''),
        conditions: [createCondition('turn', '')],
        summary: '达到回合上限，进入课堂复盘。',
        priority: 1000,
      },
    ],
    start_node_id: null,
    nodes: [],
    fact_refs: [],
    source_ref_ids: [],
    dossier_template: {
      title_template: '《{scenario_title}卷宗》',
      reflection_questions: ['哪一次选择最关键？依据和代价分别是什么？'],
      knowledge_node_kinds: ['cause', 'consequence', 'concept'],
    },
    compatibility: {
      kind: 'native-v1',
      source_id: '',
      source_version: '',
      source_checksum: null,
      notes: '',
      unresolved_refs: [],
      legacy_materials: [],
      legacy_id_map: {},
    },
    revision: 0,
    created_at: null,
    updated_at: null,
    created_by: null,
    updated_by: null,
  };
}

export function createVariable(variableId: string, label = '新指标'): ScenarioDraftVariable {
  return {
    variable_id: variableId,
    label,
    description: '',
    initial: 50,
    minimum: 0,
    maximum: 100,
  };
}

export function createNpc(personId: string): ScenarioDraftNpc {
  return {
    person_id: personId,
    display_name: '历史人物',
    role: '',
    persona: '',
    boundaries: [],
    initial_attitude: 0,
    initial_trust: 0,
    fact_refs: [],
  };
}

export function createCondition(
  kind: ScenarioDraftCondition['kind'],
  targetId: string,
): ScenarioDraftCondition {
  return {
    kind,
    variable_id: kind === 'state' ? targetId : '',
    person_id: kind === 'npc' ? targetId : '',
    field: 'attitude',
    operator: 'gte',
    value: kind === 'turn' ? 6 : 60,
  };
}

export function createEffect(
  kind: ScenarioDraftEffect['kind'],
  targetId: string,
): ScenarioDraftEffect {
  return {
    kind,
    variable_id: kind === 'state' ? targetId : '',
    person_id: kind === 'npc' ? targetId : '',
    operation: 'add',
    value: 10,
    attitude_delta: 0,
    trust_delta: 0,
    reveal_fact_refs: [],
  };
}

export function createAction(
  actionId: string,
  label = '新行动',
  variableId = '',
): ScenarioDraftAction {
  return {
    action_id: actionId,
    label,
    description: '',
    aliases: [],
    available_when: [],
    effects: variableId ? [createEffect('state', variableId)] : [],
    feedback: '',
    fact_refs: [],
    next_node_id: null,
  };
}

export function createEvent(
  eventId: string,
  variableId = '',
): ScenarioDraftEvent {
  return {
    event_id: eventId,
    title: '新自动事件',
    match: 'all',
    trigger: [createCondition('state', variableId)],
    effects: [],
    narrative: '',
    once: true,
    priority: 100,
    fact_refs: [],
  };
}

export function createEnding(
  endingId: string,
  title = '新结局',
  variableId = '',
): ScenarioDraftEnding {
  return {
    ending_id: endingId,
    title,
    match: 'all',
    conditions: [createCondition('state', variableId)],
    summary: '教师在这里概括学生抵达这一结局时发生了什么。',
    historical_explanation: '',
    major_costs: [],
    source_ref_ids: [],
    fact_refs: [],
    priority: 100,
  };
}

export function nextStableId(prefix: string, existing: string[]): string {
  const used = new Set(existing);
  for (let index = 1; index < 10000; index += 1) {
    const candidate = `${prefix}-${index}`;
    if (!used.has(candidate)) return candidate;
  }
  return `${prefix}-${Date.now().toString(36)}`;
}

export function linesToList(value: string): string[] {
  return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
}

export function listToLines(value: string[]): string {
  return value.join('\n');
}

export function scenarioTypeLabel(type: ScenarioType): string {
  return SCENARIO_TYPE_OPTIONS.find((item) => item.value === type)?.label || type;
}

export function validationIssueText(issue: ScenarioDraftValidationIssue): string {
  const message = issue.message;
  if (message.includes('unknown state variable')) return '规则引用了不存在的局势指标。';
  if (message.includes('unknown NPC')) return '规则引用了不存在的人物。';
  if (message.includes('duplicates')) return '存在重复 ID，请为每一项使用不同的英文 ID。';
  if (message.includes('initial must stay inside')) return '指标初始值必须位于最小值和最大值之间。';
  if (message.includes('minimum must be lower')) return '指标最小值必须小于最大值。';
  if (message.includes('sealed scenarios require')) return '至少需要一个指标、一个行动和一个结局。';
  if (message.includes('String should have at least 1 character')) return '该字段不能为空。';
  if (message.includes('String should match pattern')) return 'ID 只能使用英文字母、数字、点、下划线和短横线。';
  if (message.includes('at most 64 characters')) return 'ID 最长 64 个字符。';
  if (message.includes('at least 2 characters')) return 'ID 至少 2 个字符。';
  if (message.includes('reachable ending')) return '节点流程必须能够抵达一个结局。';
  if (message.includes('Field required')) return '缺少必填字段。';
  return message.replace(/^Value error,\s*/i, '');
}

export function conditionSummary(
  condition: ScenarioDraftCondition,
  variables: ScenarioDraftVariable[],
  npcs: ScenarioDraftNpc[],
): string {
  const operator = COMPARISON_OPTIONS.find((item) => item.value === condition.operator)?.label;
  if (condition.kind === 'turn') return `回合数 ${operator} ${condition.value}`;
  if (condition.kind === 'npc') {
    const person = npcs.find((item) => item.person_id === condition.person_id);
    const field = condition.field === 'trust' ? '信任' : '态度';
    return `${person?.display_name || condition.person_id || '未选人物'}的${field} ${operator} ${condition.value}`;
  }
  const variable = variables.find((item) => item.variable_id === condition.variable_id);
  return `${variable?.label || condition.variable_id || '未选指标'} ${operator} ${condition.value}`;
}

export function effectSummary(
  effect: ScenarioDraftEffect,
  variables: ScenarioDraftVariable[],
  npcs: ScenarioDraftNpc[],
): string {
  if (effect.kind === 'npc') {
    const person = npcs.find((item) => item.person_id === effect.person_id);
    return `${person?.display_name || effect.person_id || '未选人物'}：态度 ${signed(effect.attitude_delta)}，信任 ${signed(effect.trust_delta)}`;
  }
  const variable = variables.find((item) => item.variable_id === effect.variable_id);
  const operation = effect.operation === 'set' ? '设为' : '变化';
  return `${variable?.label || effect.variable_id || '未选指标'} ${operation} ${effect.operation === 'set' ? effect.value : signed(effect.value)}`;
}

export function runtimeScenarioKey(item: RuntimeScenarioRecord): string {
  const descriptor = item.descriptor;
  return `${descriptor.artifact_id}@${descriptor.version}:${descriptor.checksum}`;
}

export function safeFileBase(title: string, fallback: string): string {
  const normalized = title.trim().replace(/[\\/:*?"<>|]+/g, '-').replace(/\s+/g, ' ');
  return normalized || fallback;
}

function signed(value: number): string {
  return value > 0 ? `+${value}` : String(value);
}
