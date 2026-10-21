export const TEMPORARY_NOTEBOOK_SCHEMA = 'temporary-notebook/v1' as const;
export const TEMPORARY_NOTEBOOK_EVENT = 'chronovita:temporary-notebook-updated';
export const TEMPORARY_NOTEBOOK_MAX_LENGTH = 6000;

export interface TemporaryNotebookIdentity {
  ownerId: string;
  courseId: string;
  lessonId: string;
}

export interface TemporaryNotebookRecord {
  schema_version: typeof TEMPORARY_NOTEBOOK_SCHEMA;
  owner_id: string;
  course_id: string;
  lesson_id: string;
  body: string;
  created_at: string;
  updated_at: string;
}

export interface TemporaryNotebookStorage {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
  removeItem: (key: string) => void;
}

const safePart = (value: string) => encodeURIComponent(value.trim() || '_');

export function temporaryNotebookStorageKey(identity: TemporaryNotebookIdentity): string {
  return [
    'chronovita.learning.temporary-notebook.v1',
    safePart(identity.ownerId),
    safePart(identity.courseId),
    safePart(identity.lessonId),
  ].join('.');
}

export function normalizeTemporaryNotebookBody(body: string): string {
  return body.replace(/\r\n?/g, '\n').slice(0, TEMPORARY_NOTEBOOK_MAX_LENGTH);
}

function recordMatches(
  value: unknown,
  identity: TemporaryNotebookIdentity,
): value is TemporaryNotebookRecord {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  return record.schema_version === TEMPORARY_NOTEBOOK_SCHEMA
    && record.owner_id === identity.ownerId
    && record.course_id === identity.courseId
    && record.lesson_id === identity.lessonId
    && typeof record.body === 'string'
    && typeof record.created_at === 'string'
    && typeof record.updated_at === 'string';
}

export function readTemporaryNotebook(
  storage: TemporaryNotebookStorage,
  identity: TemporaryNotebookIdentity,
): TemporaryNotebookRecord | null {
  try {
    const raw = storage.getItem(temporaryNotebookStorageKey(identity));
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (!recordMatches(value, identity)) return null;
    return { ...value, body: normalizeTemporaryNotebookBody(value.body) };
  } catch {
    return null;
  }
}

export function writeTemporaryNotebook(
  storage: TemporaryNotebookStorage,
  identity: TemporaryNotebookIdentity,
  body: string,
  now = new Date(),
): { record: TemporaryNotebookRecord; persisted: boolean } {
  const existing = readTemporaryNotebook(storage, identity);
  const timestamp = now.toISOString();
  const record: TemporaryNotebookRecord = {
    schema_version: TEMPORARY_NOTEBOOK_SCHEMA,
    owner_id: identity.ownerId,
    course_id: identity.courseId,
    lesson_id: identity.lessonId,
    body: normalizeTemporaryNotebookBody(body),
    created_at: existing?.created_at ?? timestamp,
    updated_at: timestamp,
  };
  try {
    storage.setItem(temporaryNotebookStorageKey(identity), JSON.stringify(record));
    return { record, persisted: true };
  } catch {
    return { record, persisted: false };
  }
}

export function clearTemporaryNotebook(
  storage: TemporaryNotebookStorage,
  identity: TemporaryNotebookIdentity,
): boolean {
  try {
    storage.removeItem(temporaryNotebookStorageKey(identity));
    return true;
  } catch {
    return false;
  }
}
