import { describe, expect, it } from 'vitest';
import type { ProgressItem } from '../../utils/api';
import { readingComplete, readingLabel, resumeLayer } from './readingProgress';

const record: ProgressItem = {
  lesson_id: 'L101', last_layer: 'create', updated_at: '2026-09-16T00:00:00Z',
  layers: { watch: true, practice: true, ask: true, create: true },
};

describe('truthful reading records', () => {
  it('does not turn legacy four-stage flags into current reading completion', () => {
    expect(readingComplete(record)).toBe(false);
    expect(resumeLayer(record)).toBe('watch');
  });
  it('only confirms a current version and explains stale or removed lessons', () => {
    expect(readingComplete({ ...record, reading_status: 'completed' })).toBe(true);
    expect(readingComplete({ ...record, reading_status: 'outdated' })).toBe(false);
    expect(readingLabel({ ...record, reading_status: 'unavailable' })).toContain('撤下');
    expect(resumeLayer({ ...record, reading_status: 'reading' })).toBe('create');
  });
});
