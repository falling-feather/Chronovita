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
  llmInfo: () => jsonFetch<{ provider: string }>('/practice/llm/info'),
  sandboxGet: (sid: string) => jsonFetch<any>(`/practice/sandbox/${sid}`),
  sandboxStep: (sid: string, body: { node_id: string; choice: string; state: Record<string, number> }) =>
    jsonFetch<any>(`/practice/sandbox/${sid}/step`, { method: 'POST', body: JSON.stringify(body) }),
  canvasGet: (lid: string) => jsonFetch<{ nodes: any[]; edges: any[] }>(`/practice/canvas/${lid}`),
  canvasSave: (lid: string, payload: { nodes: any[]; edges: any[] }) =>
    jsonFetch<{ ok: boolean }>(`/practice/canvas/${lid}`, { method: 'PUT', body: JSON.stringify(payload) }),
};

// 流式聊天（手动读 ReadableStream）
export async function streamAsk(
  body: {
    user_message: string;
    persona?: 'expert' | 'peer';
    lesson_id?: string;
    lesson_title?: string;
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
