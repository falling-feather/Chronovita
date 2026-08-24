import { describe, expect, it } from 'vitest';
import {
  appendLearningEventFallback,
  createLearningDeskDraft,
  createLearningEventRecord,
  learningScopeKey,
  readLearningEventsFallback,
  type LearningFallbackStorage,
} from './learningLedger';

class MemoryStorage implements LearningFallbackStorage {
  readonly items = new Map<string, string>();
  getItem(key: string) { return this.items.get(key) ?? null; }
  setItem(key: string, value: string) { this.items.set(key, value); }
}

const identity = {
  ownerId: 'student/chronovita',
  courseId: 'C-prequin-state',
  lessonId: 'L101',
};

describe('learning ledger', () => {
  it('isolates every record by account, course and lesson', () => {
    expect(learningScopeKey(identity)).toContain('student%2Fchronovita');
    expect(learningScopeKey({ ...identity, ownerId: 'student-b' }))
      .not.toBe(learningScopeKey(identity));
    expect(learningScopeKey({ ...identity, lessonId: 'L103' }))
      .not.toBe(learningScopeKey(identity));
  });

  it('rejects a request that tries to cross the authenticated lesson boundary', () => {
    expect(() => createLearningEventRecord(identity, {
      course_id: identity.courseId,
      lesson_id: 'L103',
      kind: 'question_answered',
      title: '问史',
      summary: '不应写入另一课时。',
    })).toThrow(/scope/);
  });

  it('reads only validated owner-scoped fallback events', () => {
    const storage = new MemoryStorage();
    const first = createLearningEventRecord(identity, {
      course_id: identity.courseId,
      lesson_id: identity.lessonId,
      kind: 'keyword_opened',
      title: '展开词条',
      summary: '查看“疏导”的解释。',
    }, new Date('2026-08-24T10:00:00Z'), 'event:one');
    appendLearningEventFallback(storage, identity, first);

    const foreign = { ...first, event_id: 'event:foreign', owner_id: 'student-b' };
    const key = [...storage.items.keys()][0];
    storage.setItem(key, JSON.stringify([first, foreign, { broken: true }]));

    expect(readLearningEventsFallback(storage, identity)).toEqual([first]);
  });

  it('normalizes drafts and bounds untrusted drawing input', () => {
    const points = Array.from({ length: 20_100 }, (_, index) => ({
      x: index % 2 === 0 ? -2 : 3,
      y: Number.NaN,
    }));
    const draft = createLearningDeskDraft(identity, {
      title: `  学习卷宗 ${'x'.repeat(200)}  `,
      body_html: '<p>正文</p>',
      body_markdown: '正文',
      sticky_notes: Array.from({ length: 30 }, (_, index) => ({
        note_id: `note-${index}`,
        body: '便签',
        color: 'ochre' as const,
      })),
      drawing_strokes: [{
        stroke_id: 'stroke-one',
        color: 'not-a-color',
        width: 99,
        mode: 'ink',
        points,
      }],
    }, null, new Date('2026-08-24T10:00:00Z'));

    expect(draft.title.length).toBeLessThanOrEqual(160);
    expect(draft.sticky_notes).toHaveLength(24);
    expect(draft.drawing_strokes[0].points).toHaveLength(20_000);
    expect(draft.drawing_strokes[0].points[0]).toEqual({ x: 0, y: 0 });
    expect(draft.drawing_strokes[0].points[1]).toEqual({ x: 1, y: 0 });
    expect(draft.drawing_strokes[0].color).toBe('#24302f');
    expect(draft.drawing_strokes[0].width).toBe(24);
  });
});
