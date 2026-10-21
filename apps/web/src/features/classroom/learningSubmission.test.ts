import { describe, expect, it } from 'vitest';
import type { LearningDeskDraftRecord, LearningEventRecord } from './learningLedger';
import {
  buildLearningSubmissionRequest,
  clearPendingSubmission,
  pendingSubmissionStorageKey,
  readPendingSubmission,
  writePendingSubmission,
  type SubmissionStorage,
} from './learningSubmission';

class MemoryStorage implements SubmissionStorage {
  private readonly values = new Map<string, string>();
  getItem(key: string) { return this.values.get(key) ?? null; }
  setItem(key: string, value: string) { this.values.set(key, value); }
  removeItem(key: string) { this.values.delete(key); }
}

const identity = { ownerId: 'student/a', courseId: 'C-prequin-state', lessonId: 'L101' };
const draft: LearningDeskDraftRecord = {
  schema_version: 'learning-desk-draft/v1',
  scope_key: 'student%2Fa::C-prequin-state::L101',
  owner_id: identity.ownerId,
  course_id: identity.courseId,
  lesson_id: identity.lessonId,
  title: '大禹治水学习书案',
  body_html: '<h2>判断</h2>',
  body_markdown: '## 判断\n疏导与协作。',
  sticky_notes: [{ note_id: 'note-1', body: '比较代价', color: 'ochre' }],
  drawing_strokes: [],
  created_at: '2026-08-24T00:00:00.000Z',
  updated_at: '2026-08-24T00:30:00.000Z',
};
const event: LearningEventRecord = {
  schema_version: 'learning-ledger/v1',
  event_id: 'event-1',
  scope_key: draft.scope_key,
  owner_id: identity.ownerId,
  course_id: identity.courseId,
  lesson_id: identity.lessonId,
  kind: 'keyword_opened',
  title: '查看关键词：疏导',
  summary: '让水有序下泄。',
  metadata: { keyword: '疏导' },
  occurred_at: '2026-08-24T00:10:00.000Z',
};

describe('learning submission snapshot', () => {
  it('freezes only the server contract fields from the local draft and ledger', () => {
    const request = buildLearningSubmissionRequest(draft, [event], 'submit-test-1');
    expect(request.client_submission_id).toBe('submit-test-1');
    expect(request).not.toHaveProperty('body_html');
    expect(request.learning_events[0].metadata).toEqual({ keyword: '疏导' });
    expect(request.local_draft_updated_at).toBe(draft.updated_at);
  });

  it('persists an exact retry payload and clears it only after confirmation', () => {
    const storage = new MemoryStorage();
    const request = buildLearningSubmissionRequest(draft, [event], 'submit-test-2');
    writePendingSubmission(storage, identity, request, '2026-08-24T01:00:00.000Z');
    expect(readPendingSubmission(storage, identity)).toEqual(request);
    expect(pendingSubmissionStorageKey(identity)).toContain('student%2Fa');
    clearPendingSubmission(storage, identity);
    expect(readPendingSubmission(storage, identity)).toBeNull();
  });

  it('rejects a pending payload from another lesson scope', () => {
    const storage = new MemoryStorage();
    const request = buildLearningSubmissionRequest(draft, [], 'submit-test-3');
    expect(() => writePendingSubmission(
      storage,
      { ...identity, lessonId: 'L103' },
      request,
    )).toThrow(/scope/i);
  });
});
