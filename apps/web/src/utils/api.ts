// 统一的 API 客户端 · v0.2.0
const BASE = '/api/v1';

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
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
export interface Lesson {
  id: string; course_id: string; num: string; title: string;
  duration: string; abstract: string; body: string[];
  keywords: Keyword[]; figures: string[];
  sandbox_id: string | null;
  seed_canvas: { id: string; label: string }[];
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
