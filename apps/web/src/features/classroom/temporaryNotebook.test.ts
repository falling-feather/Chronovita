import { describe, expect, it } from 'vitest';
import {
  TEMPORARY_NOTEBOOK_MAX_LENGTH,
  clearTemporaryNotebook,
  normalizeTemporaryNotebookBody,
  readTemporaryNotebook,
  temporaryNotebookStorageKey,
  writeTemporaryNotebook,
  type TemporaryNotebookStorage,
} from './temporaryNotebook';

class MemoryStorage implements TemporaryNotebookStorage {
  readonly items = new Map<string, string>();
  getItem(key: string) { return this.items.get(key) ?? null; }
  setItem(key: string, value: string) { this.items.set(key, value); }
  removeItem(key: string) { this.items.delete(key); }
}

const identity = { ownerId: 'student/a', courseId: 'C-prequin-state', lessonId: 'L101' };

describe('temporary notebook', () => {
  it('separates notes by account, course and lesson', () => {
    expect(temporaryNotebookStorageKey(identity)).toContain('student%2Fa');
    expect(temporaryNotebookStorageKey({ ...identity, ownerId: 'student-b' }))
      .not.toBe(temporaryNotebookStorageKey(identity));
    expect(temporaryNotebookStorageKey({ ...identity, lessonId: 'L103' }))
      .not.toBe(temporaryNotebookStorageKey(identity));
  });

  it('persists a validated v1 record and preserves its creation time', () => {
    const storage = new MemoryStorage();
    const first = writeTemporaryNotebook(storage, identity, '第一行\r\n第二行', new Date('2026-08-24T10:00:00Z'));
    const second = writeTemporaryNotebook(storage, identity, '继续记录', new Date('2026-08-24T10:05:00Z'));
    expect(first.persisted).toBe(true);
    expect(second.record.created_at).toBe(first.record.created_at);
    expect(readTemporaryNotebook(storage, identity)).toEqual(second.record);
  });

  it('rejects mismatched data and bounds note length', () => {
    const storage = new MemoryStorage();
    storage.setItem(temporaryNotebookStorageKey(identity), JSON.stringify({
      schema_version: 'temporary-notebook/v1',
      owner_id: 'somebody-else',
      course_id: identity.courseId,
      lesson_id: identity.lessonId,
      body: '不应串号',
      created_at: '2026-08-24T10:00:00Z',
      updated_at: '2026-08-24T10:00:00Z',
    }));
    expect(readTemporaryNotebook(storage, identity)).toBeNull();
    expect(normalizeTemporaryNotebookBody('x'.repeat(TEMPORARY_NOTEBOOK_MAX_LENGTH + 10)))
      .toHaveLength(TEMPORARY_NOTEBOOK_MAX_LENGTH);
  });

  it('removes an emptied note instead of leaving a blank saved record', () => {
    const storage = new MemoryStorage();
    writeTemporaryNotebook(storage, identity, '待清除');
    expect(clearTemporaryNotebook(storage, identity)).toBe(true);
    expect(readTemporaryNotebook(storage, identity)).toBeNull();
  });
});
