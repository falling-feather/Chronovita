// 统一的 API 客户端 · v0.2.0
const BASE = '/api/v1';

interface ApiValidationIssue {
  loc?: Array<string | number>;
  msg?: string;
}

function localizeValidationMessage(message: string): string {
  if (message.includes('String should match pattern')) return '只能使用英文字母、数字、点、下划线和短横线';
  if (message.includes('at least 2 characters')) return '至少需要 2 个字符';
  if (message.includes('at most 64 characters')) return '最多允许 64 个字符';
  if (message.includes('Field required')) return '该字段为必填项';
  return message.replace(/^Value error,\s*/i, '');
}

async function responseError(response: Response): Promise<Error> {
  const raw = await response.text();
  let message = raw || response.statusText;
  try {
    const parsed = JSON.parse(raw) as {
      detail?: string | { message?: string } | ApiValidationIssue[];
    };
    if (typeof parsed.detail === 'string') {
      message = parsed.detail;
    } else if (Array.isArray(parsed.detail)) {
      message = parsed.detail.map((issue) => {
        const field = (issue.loc || []).filter((part) => part !== 'body').join('.');
        const detail = localizeValidationMessage(issue.msg || '字段校验失败');
        return field ? `${field}：${detail}` : detail;
      }).join('；');
    } else if (parsed.detail?.message) {
      message = parsed.detail.message;
    }
  } catch {
    // Keep the raw response when an upstream proxy does not return JSON.
  }
  return new Error(`${response.status} ${message}`);
}

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });
  if (!r.ok) {
    throw await responseError(r);
  }
  return r.json() as Promise<T>;
}

async function adminFetch<T>(token: string, path: string, init?: RequestInit): Promise<T> {
  return jsonFetch<T>(path, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init?.headers || {}),
    },
  });
}

async function adminFile(token: string, path: string): Promise<Blob> {
  const response = await fetch(BASE + path, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw await responseError(response);
  return response.blob();
}

export interface Era { id: string; name: string; period: string; summary: string }
export interface CourseSummary {
  id: string; era_id: string; title: string; subtitle: string;
  cover_color: string; section: string; lesson_count: number;
}
export interface LessonSummary { id: string; num: string; title: string; duration: string; state: string }
export interface CourseDetail {
  summary: CourseSummary; intro: string; lessons: LessonSummary[];
}
export interface Keyword { word: string; pinyin: string; gloss: string }
export interface PersonCard {
  name: string; role?: string; summary?: string; persona?: string; boundaries?: string[];
}
export interface MapPoint {
  label: string; region?: string; lat?: number | null; lng?: number | null; note?: string; kind?: string;
}
export interface SourceRef {
  title: string; source?: string; url_or_path?: string; citation_note?: string; reliability?: string;
}
export interface MaterialPlaceholder {
  title?: string; objective?: string; notes?: string; assets?: string[];
}
export interface LessonContentPackage {
  lesson_id: string; title: string; unit: string; era: string; body: string[];
  course_id?: string; course_title?: string; era_id?: string; section?: string;
  lesson_no?: string; duration?: string; abstract?: string;
  keywords?: Keyword[]; people?: PersonCard[]; map_points?: MapPoint[]; source_refs?: SourceRef[];
  facts?: string[]; qa_points?: string[]; level_goals?: string[];
  saga_material?: MaterialPlaceholder; sandbox_material?: MaterialPlaceholder;
  seed_canvas?: { id?: string; label: string; note?: string }[];
  teacher_notes?: string;
  status?: 'draft' | 'sealed'; version?: number;
  created_at?: string | null; updated_at?: string | null; sealed_at?: string | null; sealed_by?: string | null;
  checksum?: string | null;
}
export interface ContentFileRecord {
  lesson_id: string; title: string; status: string; version: number; path: string;
  updated_at?: string | null; sealed_at?: string | null; sealed_by?: string | null; checksum?: string | null;
}
export type ContentWorkflowState =
  | 'draft'
  | 'validated'
  | 'in_review'
  | 'changes_requested'
  | 'approved'
  | 'sealed'
  | 'published';
export interface ContentValidationIssue {
  code: string; severity: 'error' | 'warning'; field: string; message: string;
}
export interface ContentValidationReport {
  schema_version: string; validator_version: string; lesson_id: string;
  draft_fingerprint: string; valid: boolean; issues: ContentValidationIssue[];
  validated_at: string; validated_by: string;
}
export interface ContentWorkflowRecord {
  lesson_id: string; course_id: string; state: ContentWorkflowState; revision: number;
  draft_fingerprint: string; validation?: ContentValidationReport | null;
  sealed_version?: number | null; sealed_checksum?: string | null;
  published_course_id?: string | null; published_version?: number | null;
  published_release_id?: string | null; updated_at: string; checksum: string;
}
export interface RuntimeArtifactDescriptor {
  kind: 'course-package' | 'scenario-template';
  schema_version: 'course-package/v1' | 'scenario-template/v1';
  artifact_id: string; course_id: string; lesson_id: string;
  version: number; checksum: string; path: string;
}
export interface CourseReleaseItemV1 {
  lesson_id: string; course_id: string; content_version: number;
  source_path: string; source_checksum: string; package_path: string;
  package_checksum: string; package_schema: string;
}
export interface CourseReleaseItemV2 {
  lesson_id: string; course_id: string; content_version: number;
  source_path: string; source_checksum: string;
  course_package: RuntimeArtifactDescriptor;
  scenarios: RuntimeArtifactDescriptor[];
  primary_scenario_id?: string | null;
  audience: 'published';
}
export type CourseReleaseItem = CourseReleaseItemV1 | CourseReleaseItemV2;
export interface CourseReleaseManifest {
  schema_version: string; release_id: string; release_no: number; course_id: string;
  operation: 'bootstrap' | 'publish' | 'rollback'; parent_release_id?: string | null;
  restored_from_release_id?: string | null; created_at: string; created_by: string;
  note: string; items: CourseReleaseItem[]; checksum: string;
}
export interface WorkflowResponse {
  workflow: ContentWorkflowRecord; report?: ContentValidationReport | null;
}
export interface ReleaseResponse {
  release: CourseReleaseManifest; workflow?: ContentWorkflowRecord | null;
}
export interface LessonSourceRecord {
  lesson_id: string; course_id: string; course_title: string; title: string;
  lesson_no: string; era_id: string; era: string; source: string;
}
export interface ContentAssetRecord {
  asset_id: string; title: string; kind: 'person' | 'keyword'; path: string; updated_at?: string | null;
}
export interface PersonProfilePackage {
  asset_id: string; name: string; role?: string; era?: string; summary?: string; persona?: string;
  boundaries?: string[]; keywords?: string[]; related_lessons?: string[]; source_refs?: SourceRef[];
  teacher_notes?: string; status?: 'draft' | 'sealed'; version?: number; updated_at?: string | null;
}
export interface KeywordProfilePackage {
  asset_id: string; word: string; pinyin?: string; gloss?: string; era?: string; category?: string;
  examples?: string[]; related_people?: string[]; related_lessons?: string[]; source_refs?: SourceRef[];
  teacher_notes?: string; status?: 'draft' | 'sealed'; version?: number; updated_at?: string | null;
}
export type ScenarioType = 'crisis_governance' | 'institutional_reform' | 'council';
export type ScenarioConditionKind = 'state' | 'turn' | 'npc';
export type ScenarioEffectKind = 'state' | 'npc';
export type ScenarioComparisonOperator = 'lt' | 'lte' | 'eq' | 'gte' | 'gt';
export interface ScenarioDraftVariable {
  variable_id: string; label: string; description: string;
  initial: number; minimum: number; maximum: number;
}
export interface ScenarioDraftNpc {
  person_id: string; display_name: string; role: string; persona: string;
  boundaries: string[]; initial_attitude: number; initial_trust: number; fact_refs: string[];
}
export interface ScenarioDraftCondition {
  kind: ScenarioConditionKind; variable_id: string; person_id: string;
  field: 'attitude' | 'trust'; operator: ScenarioComparisonOperator; value: number;
}
export interface ScenarioDraftEffect {
  kind: ScenarioEffectKind; variable_id: string; person_id: string;
  operation: 'add' | 'set'; value: number; attitude_delta: number; trust_delta: number;
  reveal_fact_refs: string[];
}
export interface ScenarioDraftAction {
  action_id: string; label: string; description: string; aliases: string[];
  available_when: ScenarioDraftCondition[]; effects: ScenarioDraftEffect[];
  feedback: string; fact_refs: string[]; next_node_id?: string | null;
}
export interface ScenarioDraftEvent {
  event_id: string; title: string; match: 'all' | 'any';
  trigger: ScenarioDraftCondition[]; effects: ScenarioDraftEffect[];
  narrative: string; once: boolean; priority: number; fact_refs: string[];
}
export interface ScenarioDraftEnding {
  ending_id: string; title: string; match: 'all' | 'any';
  conditions: ScenarioDraftCondition[]; summary: string; historical_explanation: string;
  major_costs: string[]; source_ref_ids: string[]; fact_refs: string[]; priority: number;
}
export interface ScenarioDraftNode {
  node_id: string; title: string; narration: string;
  action_ids: string[]; ending_id?: string | null;
}
export interface ScenarioDraftDossier {
  title_template: string; reflection_questions: string[]; knowledge_node_kinds: string[];
}
export interface ScenarioCompatibility {
  kind: string; source_id: string; source_version: string; source_checksum?: string | null;
  notes: string; unresolved_refs: string[]; legacy_materials: unknown[];
  legacy_id_map: Record<string, string>;
}
export interface ScenarioAuthorDraft {
  schema_version: 'scenario-author-draft/v1'; scenario_id: string;
  course_id: string; lesson_id: string; title: string; scenario_type: ScenarioType;
  student_role: string; objective: string; opening: string; max_turns: number;
  variables: ScenarioDraftVariable[]; npcs: ScenarioDraftNpc[];
  action_rules: ScenarioDraftAction[]; event_rules: ScenarioDraftEvent[];
  ending_rules: ScenarioDraftEnding[]; start_node_id?: string | null;
  nodes: ScenarioDraftNode[]; fact_refs: string[]; source_ref_ids: string[];
  dossier_template: ScenarioDraftDossier; compatibility: ScenarioCompatibility;
  revision: number; created_at?: string | null; updated_at?: string | null;
  created_by?: string | null; updated_by?: string | null;
}
export interface ScenarioDraftRecord {
  scenario_id: string; course_id: string; lesson_id: string; title: string;
  scenario_type: ScenarioType; revision: number; updated_at?: string | null; updated_by?: string | null;
}
export interface ScenarioDraftValidationIssue { path: string; code: string; message: string }
export interface ScenarioDraftValidationReport {
  valid: boolean; issues: ScenarioDraftValidationIssue[];
  variable_count: number; npc_count: number; action_count: number;
  event_count: number; ending_count: number;
}
export interface RuntimeScenarioRecord {
  descriptor: RuntimeArtifactDescriptor; title: string; scenario_type: ScenarioType;
  student_role: string; objective: string;
}
export type SealedScenarioTemplate = Record<string, unknown> & {
  scenario_id: string; scenario_version: number; status: 'sealed';
  course_id: string; lesson_id: string; title: string; scenario_type: ScenarioType;
  sealed_at: string; sealed_by: string; checksum: string;
};
export interface ScenarioReleaseSelection {
  scenario_id: string; scenario_version: number; scenario_checksum: string; primary: boolean;
}
export interface LessonScenarioRef {
  scenario_id: string; scenario_version: number; checksum: string; primary: boolean;
}
export interface Lesson {
  id: string; course_id: string; num: string; title: string;
  duration: string; abstract: string; body: string[];
  keywords: Keyword[]; figures: string[];
  sandbox_id: string | null;
  seed_canvas: { id: string; label: string }[];
  unit?: string; era?: string;
  people?: PersonCard[]; map_points?: MapPoint[]; source_refs?: SourceRef[];
  facts?: string[]; qa_points?: string[]; level_goals?: string[];
  saga_material?: MaterialPlaceholder | null; sandbox_material?: MaterialPlaceholder | null;
  content_status?: string; content_version?: number; sealed_at?: string | null; sealed_by?: string | null;
  content_checksum?: string | null;
  release_id?: string | null; release_no?: number | null; release_checksum?: string | null;
  scenario_refs: LessonScenarioRef[]; primary_scenario_id: string | null;
}

export interface ScenarioReleasePin {
  release_id: string; release_no: number; release_checksum: string;
  course_id: string; lesson_id: string;
  course_content_version: number; course_checksum: string;
  scenario_version: number; scenario_checksum: string;
}
export interface GameScenarioSummary {
  scenario_id: string; scenario_version: number; scenario_checksum: string;
  course_id: string; lesson_id: string; title: string; scenario_type: string;
  student_role: string; objective: string; max_turns: number;
  audience: 'development' | 'published';
  release_id: string | null; release_no: number | null; release_checksum: string | null;
}
export interface GameNarrativeMessage {
  role: 'system' | 'player' | 'narrator'; text: string; turn_no: number;
}
export interface GameSession {
  session_id: string; user_id: string; course_id: string; lesson_id: string;
  scenario_id: string; scenario_version: number;
  course_content_version: number; course_checksum: string; scenario_checksum: string;
  status: 'active' | 'completed' | 'abandoned' | 'failed';
  revision: number; current_turn: number; current_state: Record<string, number>;
  available_action_ids: string[]; available_choices: string[];
  summary: string; history: GameNarrativeMessage[]; ending_id: string | null;
  started_at: string; updated_at: string; ended_at: string | null;
}
export interface GameStartRequest {
  scenario_id: string; client_request_id: string; release_pin?: ScenarioReleasePin;
}
export interface GameStartResponse {
  scenario: GameScenarioSummary; session: GameSession; session_storage: 'sqlite-json';
}
export interface GameTurnResponse {
  session: GameSession;
  turn: { turn_id: string; narrative: string; classified_action_id: string };
  action_feedback: string; triggered_event_ids: string[]; ending_id: string | null;
}

export const api = {
  eras: () => jsonFetch<{ items: Era[] }>('/courses/eras'),
  courses: (params: { era?: string; section?: string; q?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.era && params.era !== 'all') qs.set('era', params.era);
    if (params.section && params.section !== 'all') qs.set('section', params.section);
    if (params.q) qs.set('q', params.q);
    const s = qs.toString();
    return jsonFetch<{ items: CourseSummary[]; total: number }>(`/courses/${s ? '?' + s : ''}`);
  },
  course: (id: string) => jsonFetch<CourseDetail>(`/courses/${id}`),
  lesson: (cid: string, lid: string) => jsonFetch<Lesson>(`/courses/${cid}/lessons/${lid}`),
  gameStart: (body: GameStartRequest) =>
    jsonFetch<GameStartResponse>('/practice/game/sessions', {
      method: 'POST', body: JSON.stringify(body),
    }),
  gameSession: (sessionId: string) =>
    jsonFetch<GameSession>(`/practice/game/sessions/${encodeURIComponent(sessionId)}`),
  gameTurn: (
    sessionId: string,
    body: {
      client_action_id: string; action_id: string; raw_input: string;
      expected_revision: number; action_source?: 'fixed';
    },
  ) => jsonFetch<GameTurnResponse>(
    `/practice/game/sessions/${encodeURIComponent(sessionId)}/turns`,
    { method: 'POST', body: JSON.stringify(body) },
  ),
  llmInfo: () => jsonFetch<{ provider: string; ask_provider?: string }>('/practice/llm/info'),
  sandboxGet: (sid: string) => jsonFetch<any>(`/practice/sandbox/${sid}`),
  sandboxStep: (sid: string, body: { node_id: string; choice: string; state: Record<string, number> }) =>
    jsonFetch<any>(`/practice/sandbox/${sid}/step`, { method: 'POST', body: JSON.stringify(body) }),
  canvasGet: (lid: string) => jsonFetch<{ nodes: any[]; edges: any[] }>(`/practice/canvas/${lid}`),
  canvasSave: (lid: string, payload: { nodes: any[]; edges: any[] }) =>
    jsonFetch<{ ok: boolean }>(`/practice/canvas/${lid}`, { method: 'PUT', body: JSON.stringify(payload) }),
  canvasGenerate: (body: { lesson_id: string; lesson_title: string; abstract: string; keywords: string[]; seed: string[] }) =>
    jsonFetch<{ nodes: any[]; edges: any[] }>(`/practice/canvas/generate`, { method: 'POST', body: JSON.stringify(body) }),
  sagaTemplates: () => jsonFetch<{ items: SagaTemplate[] }>(`/practice/saga/templates`),
  sagaStart: (lesson_id: string) => jsonFetch<SagaState>(`/practice/saga/start`, { method: 'POST', body: JSON.stringify({ lesson_id }) }),
  sagaGet: (saga_id: string) => jsonFetch<SagaState>(`/practice/saga/${saga_id}`),
  progressList: () => jsonFetch<{ items: ProgressItem[] }>(`/learning/progress`),
  progressLatest: () => jsonFetch<{ item: ProgressItem | null }>(`/learning/progress/latest`),
  progressGet: (lesson_id: string) => jsonFetch<{ item: ProgressItem | null }>(`/learning/progress/${lesson_id}`),
  progressTouch: (body: { lesson_id: string; layer: string; completed?: boolean }) =>
    jsonFetch<{ ok: boolean; item: ProgressItem }>(`/learning/progress/touch`, { method: 'POST', body: JSON.stringify(body) }),
  adminContentTemplate: (token: string) => adminFetch<LessonContentPackage>(token, '/admin/content/template'),
  adminContentSourceLessons: (token: string) => adminFetch<{ items: LessonSourceRecord[] }>(token, '/admin/content/source-lessons'),
  adminContentSourceLesson: (token: string, lesson_id: string) =>
    adminFetch<LessonContentPackage>(token, `/admin/content/source-lessons/${lesson_id}`),
  adminContentDrafts: (token: string) => adminFetch<{ items: ContentFileRecord[] }>(token, '/admin/content/drafts'),
  adminContentDraft: (token: string, lesson_id: string) =>
    adminFetch<LessonContentPackage>(token, `/admin/content/drafts/${lesson_id}`),
  adminContentPreview: (token: string, body: LessonContentPackage) =>
    adminFetch<{ item: LessonContentPackage }>(token, '/admin/content/preview', { method: 'POST', body: JSON.stringify(body) }),
  adminContentSaveDraft: (token: string, body: LessonContentPackage) =>
    adminFetch<{ item: LessonContentPackage; workflow: ContentWorkflowRecord }>(
      token,
      '/admin/content/drafts',
      { method: 'POST', body: JSON.stringify(body) },
    ),
  adminContentWorkflow: (token: string, lesson_id: string) =>
    adminFetch<WorkflowResponse>(token, `/admin/content/drafts/${lesson_id}/workflow`),
  adminContentValidate: (token: string, lesson_id: string) =>
    adminFetch<WorkflowResponse>(token, `/admin/content/drafts/${lesson_id}/validate`, {
      method: 'POST', body: JSON.stringify({}),
    }),
  adminContentSubmitReview: (token: string, lesson_id: string, note: string) =>
    adminFetch<WorkflowResponse>(token, `/admin/content/drafts/${lesson_id}/submit-review`, {
      method: 'POST', body: JSON.stringify({ note }),
    }),
  adminContentReview: (
    token: string,
    lesson_id: string,
    decision: 'approve' | 'changes_requested',
    note: string,
  ) => adminFetch<WorkflowResponse>(token, `/admin/content/drafts/${lesson_id}/review`, {
    method: 'POST', body: JSON.stringify({ decision, note }),
  }),
  adminContentSeal: (token: string, lesson_id: string) =>
    adminFetch<{
      item: LessonContentPackage;
      record: { path: string };
      workflow: ContentWorkflowRecord;
    }>(
      token,
      `/admin/content/drafts/${lesson_id}/seal`,
      { method: 'POST', body: JSON.stringify({}) },
    ),
  adminContentPublish: (
    token: string,
    lesson_id: string,
    version: number,
    note: string,
    scenarios?: ScenarioReleaseSelection[] | null,
  ) => adminFetch<ReleaseResponse>(
    token,
    `/admin/content/sealed/${lesson_id}/versions/${version}/publish`,
    {
      method: 'POST',
      body: JSON.stringify({
        note,
        ...(scenarios === undefined ? {} : { scenarios }),
      }),
    },
  ),
  adminContentReleases: (token: string, course_id: string) =>
    adminFetch<{ items: CourseReleaseManifest[] }>(
      token,
      `/admin/content/releases?course_id=${encodeURIComponent(course_id)}`,
    ),
  adminContentCurrentRelease: (token: string, course_id: string) =>
    adminFetch<ReleaseResponse>(token, `/admin/content/releases/${course_id}/current`),
  adminContentRollback: (
    token: string,
    course_id: string,
    target_release_id: string,
    note: string,
  ) => adminFetch<ReleaseResponse>(token, `/admin/content/releases/${course_id}/rollback`, {
    method: 'POST', body: JSON.stringify({ note, target_release_id }),
  }),
  adminContentAssets: (token: string, kind?: 'person' | 'keyword') =>
    adminFetch<{ items: ContentAssetRecord[] }>(token, `/admin/content/assets${kind ? `?kind=${kind}` : ''}`),
  adminPersonTemplate: (token: string) => adminFetch<PersonProfilePackage>(token, '/admin/content/assets/people/template'),
  adminPersonAsset: (token: string, asset_id: string) =>
    adminFetch<PersonProfilePackage>(token, `/admin/content/assets/people/${asset_id}`),
  adminSavePersonAsset: (token: string, body: PersonProfilePackage) =>
    adminFetch<{ item: PersonProfilePackage }>(token, '/admin/content/assets/people', { method: 'POST', body: JSON.stringify(body) }),
  adminKeywordTemplate: (token: string) => adminFetch<KeywordProfilePackage>(token, '/admin/content/assets/keywords/template'),
  adminKeywordAsset: (token: string, asset_id: string) =>
    adminFetch<KeywordProfilePackage>(token, `/admin/content/assets/keywords/${asset_id}`),
  adminSaveKeywordAsset: (token: string, body: KeywordProfilePackage) =>
    adminFetch<{ item: KeywordProfilePackage }>(token, '/admin/content/assets/keywords', { method: 'POST', body: JSON.stringify(body) }),
  adminScenarioTemplate: (token: string) =>
    adminFetch<ScenarioAuthorDraft>(token, '/admin/content/scenario-drafts/template'),
  adminScenarioDrafts: (token: string) =>
    adminFetch<{ items: ScenarioDraftRecord[] }>(token, '/admin/content/scenario-drafts'),
  adminScenarioDraft: (token: string, scenario_id: string) =>
    adminFetch<ScenarioAuthorDraft>(token, `/admin/content/scenario-drafts/${encodeURIComponent(scenario_id)}`),
  adminSaveScenarioDraft: (token: string, body: ScenarioAuthorDraft) =>
    adminFetch<{ item: ScenarioAuthorDraft }>(token, '/admin/content/scenario-drafts', {
      method: 'POST', body: JSON.stringify(body),
    }),
  adminValidateScenarioDraft: (token: string, scenario_id: string) =>
    adminFetch<{ report: ScenarioDraftValidationReport }>(
      token,
      `/admin/content/scenario-drafts/${encodeURIComponent(scenario_id)}/validate`,
      { method: 'POST' },
    ),
  adminSealScenarioDraft: (token: string, scenario_id: string) =>
    adminFetch<{
      item: SealedScenarioTemplate; record: RuntimeScenarioRecord; idempotent: boolean;
    }>(
      token,
      `/admin/content/scenario-drafts/${encodeURIComponent(scenario_id)}/seal`,
      { method: 'POST' },
    ),
  adminRuntimeScenarios: (token: string) =>
    adminFetch<{ items: RuntimeScenarioRecord[] }>(token, '/admin/content/runtime-scenarios'),
  adminRuntimeScenario: (token: string, descriptor: RuntimeArtifactDescriptor) => {
    const query = new URLSearchParams({
      course_id: descriptor.course_id,
      lesson_id: descriptor.lesson_id,
      scenario_checksum: descriptor.checksum,
    });
    return adminFetch<{ item: SealedScenarioTemplate; descriptor: RuntimeArtifactDescriptor }>(
      token,
      `/admin/content/runtime-scenarios/${encodeURIComponent(descriptor.artifact_id)}`
        + `/versions/${descriptor.version}?${query.toString()}`,
    );
  },
  adminRuntimeScenarioFile: (token: string, descriptor: RuntimeArtifactDescriptor) => {
    const query = new URLSearchParams({
      course_id: descriptor.course_id,
      lesson_id: descriptor.lesson_id,
      scenario_checksum: descriptor.checksum,
    });
    return adminFile(
      token,
      `/admin/content/runtime-scenarios/${encodeURIComponent(descriptor.artifact_id)}`
        + `/versions/${descriptor.version}/file?${query.toString()}`,
    );
  },
};

export interface ProgressItem {
  lesson_id: string;
  course_id?: string;
  title?: string;
  last_layer: string;
  layers: { watch: boolean; practice: boolean; ask: boolean; create: boolean };
  updated_at: string;
}

export interface SagaTemplate {
  lesson_id: string; title: string; era: string; persona: string; keywords: string[];
}
export interface SagaEntity { name: string; type: string; desc: string }
export interface SagaState {
  saga_id: string; lesson_id: string; title: string; era: string; persona: string;
  history: { role: 'narrator' | 'player'; text: string }[];
  summary: string; choices: string[]; flags: Record<string, any>;
  entities: SagaEntity[]; step: number; ended: boolean; keywords: string[];
}

// Saga · 流式行动（与 streamAsk 同形式；末尾会出现 \n\n[META]{...json...}）
export async function streamSagaAct(
  saga_id: string,
  action: string,
  onChunk: (text: string) => void,
): Promise<void> {
  const r = await fetch(BASE + `/practice/saga/${saga_id}/act`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  });
  if (!r.ok || !r.body) {
    onChunk(`[请求失败 ${r.status}]`);
    return;
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder('utf-8');
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    if (value) onChunk(decoder.decode(value, { stream: true }));
  }
}

// 流式聊天（手动读 ReadableStream）
export async function streamAsk(
  body: {
    user_message: string;
    persona?: 'expert' | 'peer';
    lesson_id?: string;
    lesson_title?: string;
    peer_character?: string;
    peer_intro?: string;
    era?: string;
    history?: { role: 'user' | 'assistant'; content: string }[];
  },
  onChunk: (text: string) => void,
): Promise<void> {
  const r = await fetch(BASE + '/practice/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok || !r.body) {
    onChunk(`[请求失败 ${r.status}]`);
    return;
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder('utf-8');
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    if (value) onChunk(decoder.decode(value, { stream: true }));
  }
}
