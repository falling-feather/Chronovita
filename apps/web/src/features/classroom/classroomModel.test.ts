import { describe, expect, it } from 'vitest';
import {
  CLASSROOM_STAGES,
  classroomStage,
  isFlagshipLesson,
  presentationStageDuration,
} from './classroomModel';

describe('classroomModel', () => {
  it('keeps the four classroom stages in the published order', () => {
    expect(CLASSROOM_STAGES.map((stage) => stage.layer)).toEqual([
      'watch', 'practice', 'ask', 'create',
    ]);
    expect(classroomStage('unknown').title).toBe('踏勘');
  });

  it('only marks the two formal flagship lessons', () => {
    expect(isFlagshipLesson('L101')).toBe(true);
    expect(isFlagshipLesson('L103')).toBe(true);
    expect(isFlagshipLesson('dayu-flood-control')).toBe(false);
  });

  it('uses exact presentation timings when a V3 presentation is bound', () => {
    const presentation = {
      presentation: {
        phase_minutes: { observe: 9, decide: 14, consult: 7, dossier: 10 },
      },
    } as never;
    expect(presentationStageDuration(CLASSROOM_STAGES[1], presentation)).toBe('14 分钟');
  });
});
