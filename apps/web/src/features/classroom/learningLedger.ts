export const LEARNING_LEDGER_SCHEMA = 'learning-ledger/v1' as const;
export const LEARNING_DESK_DRAFT_SCHEMA = 'learning-desk-draft/v1' as const;
export const LEARNING_EVENT_REQUEST = 'chronovita:learning-event-request';
export const LEARNING_LEDGER_UPDATED = 'chronovita:learning-ledger-updated';

const DATABASE_NAME = 'chronovita-learning-desk-v1';
const DATABASE_VERSION = 2;
const EVENT_STORE = 'events';
const DRAFT_STORE = 'drafts';
const FALLBACK_EVENT_LIMIT = 240;

export type LearningEventKind =
  | 'stage_entered'
  | 'keyword_opened'
  | 'decision_completed'
  | 'question_answered'
  | 'temporary_note_saved';

export interface LearningScopeIdentity {
  ownerId: string;
  courseId: string;
  lessonId: string;
}

export interface LearningEventRequest {
  course_id: string;
  lesson_id: string;
  kind: LearningEventKind;
  title: string;
  summary: string;
  metadata?: Record<string, string | number | boolean | null>;
}

export interface LearningEventRecord extends LearningEventRequest {
  schema_version: typeof LEARNING_LEDGER_SCHEMA;
  event_id: string;
  scope_key: string;
  owner_id: string;
  occurred_at: string;
}

export interface LearningDeskStickyNote {
  note_id: string;
  body: string;
  color: 'ochre' | 'jade' | 'cinnabar';
}

export interface LearningDeskPoint {
  x: number;
  y: number;
}

export interface LearningDeskStroke {
  stroke_id: string;
  color: string;
  width: number;
  mode: 'ink' | 'erase';
  points: LearningDeskPoint[];
}

export interface LearningDeskDraftRecord {
  schema_version: typeof LEARNING_DESK_DRAFT_SCHEMA;
  scope_key: string;
  owner_id: string;
  course_id: string;
  lesson_id: string;
  title: string;
  body_html: string;
  body_markdown: string;
  sticky_notes: LearningDeskStickyNote[];
  drawing_strokes: LearningDeskStroke[];
  created_at: string;
  updated_at: string;
}

export interface LearningDeskDraftInput {
  title: string;
  body_html: string;
  body_markdown: string;
  sticky_notes: LearningDeskStickyNote[];
  drawing_strokes: LearningDeskStroke[];
}

export interface LearningFallbackStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

const safePart = (value: string) => encodeURIComponent(value.trim() || '_');

export function learningScopeKey(identity: LearningScopeIdentity): string {
  return [safePart(identity.ownerId), safePart(identity.courseId), safePart(identity.lessonId)].join('::');
}

const fallbackEventKey = (identity: LearningScopeIdentity) => (
  `chronovita.learning.ledger.v1.${learningScopeKey(identity)}`
);
const fallbackDraftKey = (identity: LearningScopeIdentity) => (
  `chronovita.learning.desk.v1.${learningScopeKey(identity)}`
);

function makeId(prefix: string): string {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}:${suffix}`;
}

function normalizedText(value: string, maximum: number): string {
  return value.replace(/\r\n?/g, '\n').trim().slice(0, maximum);
}

function normalizedMetadata(
  value: LearningEventRequest['metadata'],
): LearningEventRequest['metadata'] {
  if (!value) return undefined;
  const result: Record<string, string | number | boolean | null> = {};
  for (const [key, item] of Object.entries(value).slice(0, 20)) {
    const safeKey = normalizedText(key, 80);
    if (!safeKey) continue;
    if (typeof item === 'string') result[safeKey] = normalizedText(item, 600);
    else if (typeof item === 'number' && Number.isFinite(item)) result[safeKey] = item;
    else if (typeof item === 'boolean' || item === null) result[safeKey] = item;
  }
  return result;
}

export function createLearningEventRecord(
  identity: LearningScopeIdentity,
  request: LearningEventRequest,
  now = new Date(),
  eventId = makeId('learning-event'),
): LearningEventRecord {
  if (request.course_id !== identity.courseId || request.lesson_id !== identity.lessonId) {
    throw new Error('Learning event scope does not match the authenticated lesson.');
  }
  if (!request.title.trim() || !request.summary.trim()) {
    throw new Error('Learning events require a title and summary.');
  }
  return {
    schema_version: LEARNING_LEDGER_SCHEMA,
    event_id: eventId,
    scope_key: learningScopeKey(identity),
    owner_id: identity.ownerId,
    course_id: identity.courseId,
    lesson_id: identity.lessonId,
    kind: request.kind,
    title: normalizedText(request.title, 120),
    summary: normalizedText(request.summary, 1200),
    metadata: normalizedMetadata(request.metadata),
    occurred_at: now.toISOString(),
  };
}

export function isLearningEventRequest(value: unknown): value is LearningEventRequest {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  return typeof record.course_id === 'string'
    && typeof record.lesson_id === 'string'
    && ['stage_entered', 'keyword_opened', 'decision_completed', 'question_answered', 'temporary_note_saved']
      .includes(String(record.kind))
    && typeof record.title === 'string'
    && typeof record.summary === 'string';
}

export function emitLearningEvent(request: LearningEventRequest): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(LEARNING_EVENT_REQUEST, { detail: request }));
}

function recordMatchesScope(value: unknown, identity: LearningScopeIdentity): value is LearningEventRecord {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  return record.schema_version === LEARNING_LEDGER_SCHEMA
    && record.owner_id === identity.ownerId
    && record.course_id === identity.courseId
    && record.lesson_id === identity.lessonId
    && typeof record.event_id === 'string'
    && typeof record.title === 'string'
    && typeof record.summary === 'string'
    && typeof record.occurred_at === 'string';
}

function draftMatchesScope(value: unknown, identity: LearningScopeIdentity): value is LearningDeskDraftRecord {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  return record.schema_version === LEARNING_DESK_DRAFT_SCHEMA
    && record.owner_id === identity.ownerId
    && record.course_id === identity.courseId
    && record.lesson_id === identity.lessonId
    && typeof record.title === 'string'
    && typeof record.body_html === 'string'
    && typeof record.body_markdown === 'string'
    && Array.isArray(record.sticky_notes)
    && Array.isArray(record.drawing_strokes)
    && typeof record.created_at === 'string'
    && typeof record.updated_at === 'string';
}

function fallbackStorage(): LearningFallbackStorage | null {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null;
  } catch {
    return null;
  }
}

export function appendLearningEventFallback(
  storage: LearningFallbackStorage,
  identity: LearningScopeIdentity,
  record: LearningEventRecord,
): void {
  const existing = readLearningEventsFallback(storage, identity);
  const next = [...existing.filter((item) => item.event_id !== record.event_id), record]
    .sort((left, right) => left.occurred_at.localeCompare(right.occurred_at))
    .slice(-FALLBACK_EVENT_LIMIT);
  storage.setItem(fallbackEventKey(identity), JSON.stringify(next));
}

export function readLearningEventsFallback(
  storage: LearningFallbackStorage,
  identity: LearningScopeIdentity,
): LearningEventRecord[] {
  try {
    const raw = storage.getItem(fallbackEventKey(identity));
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item) => recordMatchesScope(item, identity));
  } catch {
    return [];
  }
}

function writeDraftFallback(
  storage: LearningFallbackStorage,
  identity: LearningScopeIdentity,
  draft: LearningDeskDraftRecord,
): void {
  storage.setItem(fallbackDraftKey(identity), JSON.stringify(draft));
}

function readDraftFallback(
  storage: LearningFallbackStorage,
  identity: LearningScopeIdentity,
): LearningDeskDraftRecord | null {
  try {
    const raw = storage.getItem(fallbackDraftKey(identity));
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return draftMatchesScope(parsed, identity) ? parsed : null;
  } catch {
    return null;
  }
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new Error('IndexedDB is unavailable.'));
      return;
    }
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(EVENT_STORE)) {
        const events = database.createObjectStore(EVENT_STORE, { keyPath: 'event_id' });
        events.createIndex('by_scope', 'scope_key', { unique: false });
      }
      if (!database.objectStoreNames.contains(DRAFT_STORE)) {
        database.createObjectStore(DRAFT_STORE, { keyPath: 'scope_key' });
      }
      for (const [storeName, dateField] of [[EVENT_STORE, 'occurred_at'], [DRAFT_STORE, 'updated_at']] as const) {
        const store = request.transaction!.objectStore(storeName);
        if (!store.indexNames.contains('by_owner_time')) {
          store.createIndex('by_owner_time', ['owner_id', dateField], { unique: false });
        }
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error('IndexedDB failed to open.'));
    request.onblocked = () => reject(new Error('IndexedDB upgrade is blocked.'));
  });
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onabort = () => reject(transaction.error || new Error('IndexedDB transaction aborted.'));
    transaction.onerror = () => reject(transaction.error || new Error('IndexedDB transaction failed.'));
  });
}

export async function appendLearningEvent(
  identity: LearningScopeIdentity,
  request: LearningEventRequest,
): Promise<LearningEventRecord> {
  const record = createLearningEventRecord(identity, request);
  try {
    const database = await openDatabase();
    try {
      const transaction = database.transaction(EVENT_STORE, 'readwrite');
      transaction.objectStore(EVENT_STORE).put(record);
      await transactionDone(transaction);
    } finally {
      database.close();
    }
  } catch {
    const storage = fallbackStorage();
    if (!storage) throw new Error('No local learning storage is available.');
    appendLearningEventFallback(storage, identity, record);
  }
  return record;
}

export async function listLearningEvents(
  identity: LearningScopeIdentity,
): Promise<LearningEventRecord[]> {
  let indexedEvents: LearningEventRecord[] = [];
  try {
    const database = await openDatabase();
    try {
      indexedEvents = await new Promise((resolve, reject) => {
        const transaction = database.transaction(EVENT_STORE, 'readonly');
        const request = transaction.objectStore(EVENT_STORE).index('by_scope').getAll(learningScopeKey(identity));
        request.onsuccess = () => resolve(request.result.filter((item) => recordMatchesScope(item, identity)));
        request.onerror = () => reject(request.error || new Error('IndexedDB event read failed.'));
      });
    } finally {
      database.close();
    }
  } catch {
    // Fall through to the recoverable localStorage ledger.
  }
  const storage = fallbackStorage();
  const fallbackEvents = storage ? readLearningEventsFallback(storage, identity) : [];
  return [...new Map([...fallbackEvents, ...indexedEvents].map((item) => [item.event_id, item])).values()]
    .sort((left, right) => left.occurred_at.localeCompare(right.occurred_at));
}

function normalizeStickyNotes(notes: LearningDeskStickyNote[]): LearningDeskStickyNote[] {
  return notes.slice(0, 24).map((note) => ({
    note_id: normalizedText(note.note_id || makeId('note'), 160),
    body: note.body.replace(/\r\n?/g, '\n').slice(0, 1000),
    color: ['ochre', 'jade', 'cinnabar'].includes(note.color) ? note.color : 'ochre',
  }));
}

function normalizeStrokes(strokes: LearningDeskStroke[]): LearningDeskStroke[] {
  let pointBudget = 20_000;
  const result: LearningDeskStroke[] = [];
  for (const stroke of strokes.slice(0, 600)) {
    if (pointBudget <= 0) break;
    const points = stroke.points.slice(0, pointBudget).map((point) => ({
      x: Math.max(0, Math.min(1, Number(point.x) || 0)),
      y: Math.max(0, Math.min(1, Number(point.y) || 0)),
    }));
    pointBudget -= points.length;
    if (points.length === 0) continue;
    result.push({
      stroke_id: normalizedText(stroke.stroke_id || makeId('stroke'), 160),
      color: /^#[0-9a-f]{6}$/i.test(stroke.color) ? stroke.color : '#24302f',
      width: Math.max(1, Math.min(24, Number(stroke.width) || 3)),
      mode: stroke.mode === 'erase' ? 'erase' : 'ink',
      points,
    });
  }
  return result;
}

export function createLearningDeskDraft(
  identity: LearningScopeIdentity,
  input: LearningDeskDraftInput,
  existing: LearningDeskDraftRecord | null = null,
  now = new Date(),
): LearningDeskDraftRecord {
  const timestamp = now.toISOString();
  return {
    schema_version: LEARNING_DESK_DRAFT_SCHEMA,
    scope_key: learningScopeKey(identity),
    owner_id: identity.ownerId,
    course_id: identity.courseId,
    lesson_id: identity.lessonId,
    title: input.title.replace(/\r\n?/g, ' ').trim().slice(0, 160),
    body_html: input.body_html.slice(0, 80_000),
    body_markdown: input.body_markdown.replace(/\r\n?/g, '\n').slice(0, 60_000),
    sticky_notes: normalizeStickyNotes(input.sticky_notes),
    drawing_strokes: normalizeStrokes(input.drawing_strokes),
    created_at: existing?.created_at ?? timestamp,
    updated_at: timestamp,
  };
}

export async function readLearningDeskDraft(
  identity: LearningScopeIdentity,
): Promise<LearningDeskDraftRecord | null> {
  try {
    const database = await openDatabase();
    try {
      const record = await new Promise<unknown>((resolve, reject) => {
        const transaction = database.transaction(DRAFT_STORE, 'readonly');
        const request = transaction.objectStore(DRAFT_STORE).get(learningScopeKey(identity));
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error || new Error('IndexedDB draft read failed.'));
      });
      if (draftMatchesScope(record, identity)) return record;
    } finally {
      database.close();
    }
  } catch {
    // Fall through to the recoverable localStorage draft.
  }
  const storage = fallbackStorage();
  return storage ? readDraftFallback(storage, identity) : null;
}

export async function writeLearningDeskDraft(
  identity: LearningScopeIdentity,
  input: LearningDeskDraftInput,
  existing: LearningDeskDraftRecord | null,
): Promise<LearningDeskDraftRecord> {
  const draft = createLearningDeskDraft(identity, input, existing);
  try {
    const database = await openDatabase();
    try {
      const transaction = database.transaction(DRAFT_STORE, 'readwrite');
      transaction.objectStore(DRAFT_STORE).put(draft);
      await transactionDone(transaction);
    } finally {
      database.close();
    }
  } catch {
    const storage = fallbackStorage();
    if (!storage) throw new Error('No local learning storage is available.');
    writeDraftFallback(storage, identity, draft);
  }
  return draft;
}

export interface PrivateLearningSummary {
  course_id: string; lesson_id: string; title: string; body_excerpt: string; updated_at: string;
  note_count: number; stroke_count: number; quote_count: number; decision_count: number; question_count: number;
  recent_events: LearningEventRecord[];
}

export function summarizePrivateLearning(ownerId: string, drafts: unknown[], events: unknown[]): PrivateLearningSummary[] {
  const summaries = new Map<string, PrivateLearningSummary>();
  const identityFor = (value: unknown): LearningScopeIdentity | null => {
    if (!value || typeof value !== 'object') return null;
    const record = value as Record<string, unknown>;
    return record.owner_id === ownerId && typeof record.course_id === 'string' && typeof record.lesson_id === 'string'
      ? { ownerId, courseId: record.course_id, lessonId: record.lesson_id } : null;
  };
  const entry = (identity: LearningScopeIdentity, at: string) => {
    const key = learningScopeKey(identity);
    if (!summaries.has(key)) summaries.set(key, { course_id: identity.courseId, lesson_id: identity.lessonId,
      title: identity.lessonId + ' · 私人学习留痕', body_excerpt: '', updated_at: at, note_count: 0, stroke_count: 0,
      quote_count: 0, decision_count: 0, question_count: 0, recent_events: [] });
    const summary = summaries.get(key)!;
    if (at > summary.updated_at) summary.updated_at = at;
    return summary;
  };
  const seenDrafts = new Set<string>();
  for (const value of [...drafts].sort((a, b) => String((b as LearningDeskDraftRecord)?.updated_at || '').localeCompare(String((a as LearningDeskDraftRecord)?.updated_at || '')))) {
    const identity = identityFor(value);
    if (!identity || !draftMatchesScope(value, identity) || seenDrafts.has(learningScopeKey(identity))) continue;
    seenDrafts.add(learningScopeKey(identity));
    const summary = entry(identity, value.updated_at);
    Object.assign(summary, { title: value.title, body_excerpt: value.body_markdown.replace(/\s+/g, ' ').slice(0, 160),
      note_count: value.sticky_notes.length, stroke_count: value.drawing_strokes.length });
  }
  const seenEvents = new Set<string>();
  for (const value of events) {
    const identity = identityFor(value);
    if (!identity || !recordMatchesScope(value, identity) || seenEvents.has(value.event_id)) continue;
    seenEvents.add(value.event_id);
    const summary = entry(identity, value.occurred_at);
    summary.recent_events.push(value);
    if (value.kind === 'temporary_note_saved' && value.metadata?.book_id === 'shiji') summary.quote_count += 1;
    if (value.kind === 'decision_completed') summary.decision_count += 1;
    if (value.kind === 'question_answered') summary.question_count += 1;
  }
  return [...summaries.values()].map((summary) => ({ ...summary,
    recent_events: summary.recent_events.sort((a, b) => b.occurred_at.localeCompare(a.occurred_at)).slice(0, 3),
  })).sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

export async function listPrivateLearning(ownerId: string): Promise<{ items: PrivateLearningSummary[]; partial: boolean }> {
  const drafts: unknown[] = [];
  const events: unknown[] = [];
  let partial = true;
  try {
    const database = await openDatabase();
    try {
      const readRecent = (storeName: string, limit: number) => new Promise<unknown[]>((resolve, reject) => {
        const values: unknown[] = [];
        const transaction = database.transaction(storeName, 'readonly');
        const request = transaction.objectStore(storeName).index('by_owner_time')
          .openCursor(IDBKeyRange.bound([ownerId, ''], [ownerId, '\uffff']), 'prev');
        request.onsuccess = () => {
          const cursor = request.result;
          if (!cursor || values.length >= limit) { resolve(values); return; }
          values.push(cursor.value); cursor.continue();
        };
        request.onerror = () => reject(request.error || new Error('Private learning records unavailable'));
      });
      const [savedDrafts, savedEvents] = await Promise.all([readRecent(DRAFT_STORE, 100), readRecent(EVENT_STORE, 2000)]);
      drafts.push(...savedDrafts); events.push(...savedEvents);
      partial = false;
    } finally { database.close(); }
  } catch {
    // The recoverable per-owner fallback is read below; no server upload occurs.
  }
  let storage: Storage | null = null;
  try { storage = typeof window !== 'undefined' ? window.localStorage : null; } catch { /* Browser security may disable this optional mirror. */ }
  if (storage) {
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index) || '';
      if (!key.startsWith('chronovita.learning.desk.v1.' + safePart(ownerId) + '::')
          && !key.startsWith('chronovita.learning.ledger.v1.' + safePart(ownerId) + '::')) continue;
      try {
        const value: unknown = JSON.parse(storage.getItem(key) || 'null');
        if (Array.isArray(value)) events.push(...value); else drafts.push(value);
      } catch { /* A corrupt fallback entry is not counted as saved work. */ }
    }
  }
  if (partial && !drafts.length && !events.length) throw new Error('本机学习存储暂不可读取，请回到原书案或恢复浏览器存储权限。');
  return { items: summarizePrivateLearning(ownerId, drafts, events), partial };
}
