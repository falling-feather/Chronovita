import { describe, expect, it } from 'vitest';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import {
  COURSE_COVER_IDS,
  COURSE_COVER_META,
  courseCoverUrl,
  isCourseCoverId,
} from './courseCoverAssets';

describe('course cover assets', () => {
  it('binds exactly one cover identity to each current course', () => {
    expect(COURSE_COVER_IDS).toHaveLength(15);
    expect(new Set(COURSE_COVER_IDS).size).toBe(15);
    expect(Object.keys(COURSE_COVER_META).sort()).toEqual([...COURSE_COVER_IDS].sort());
  });

  it('builds deterministic AVIF and WebP paths', () => {
    expect(courseCoverUrl('C-prequin-state', 720, 'avif'))
      .toBe('/assets/courses/covers/C-prequin-state-720.avif');
    expect(courseCoverUrl('C-mingqing-late', 1440, 'webp'))
      .toBe('/assets/courses/covers/C-mingqing-late-1440.webp');
  });

  it('rejects courses without a packaged asset', () => {
    expect(isCourseCoverId('C-prequin-state')).toBe(true);
    expect(isCourseCoverId('C-future-placeholder')).toBe(false);
  });

  it('keeps every packaged variant present and checksum-bound', () => {
    const assetRoot = new URL('../../../public/assets/courses/covers/', import.meta.url);
    const manifest = JSON.parse(readFileSync(new URL('manifest.json', assetRoot), 'utf8')) as {
      schema: string;
      courses: Record<string, {
        variants: Array<{ file: string; bytes: number; sha256: string }>;
      }>;
    };

    expect(manifest.schema).toBe('chronovita-course-cover-assets/v1');
    expect(Object.keys(manifest.courses).sort()).toEqual([...COURSE_COVER_IDS].sort());

    for (const courseId of COURSE_COVER_IDS) {
      const variants = manifest.courses[courseId].variants;
      expect(variants).toHaveLength(4);
      for (const variant of variants) {
        const buffer = readFileSync(new URL(variant.file, assetRoot));
        expect(buffer.byteLength).toBe(variant.bytes);
        expect(createHash('sha256').update(buffer).digest('hex')).toBe(variant.sha256);
      }
    }
  });
});
