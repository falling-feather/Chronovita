import { describe, expect, it } from 'vitest';
import { HOME_ERAS, homeEraAsset, nextHomeEraIndex } from './homeEraModel';

describe('home era presentation', () => {
  it('keeps one complete presentation record per supported era', () => {
    expect(HOME_ERAS).toHaveLength(6);
    expect(new Set(HOME_ERAS.map((era) => era.id)).size).toBe(6);
    for (const era of HOME_ERAS) {
      expect(era.name).toBeTruthy();
      expect(era.years).toBeTruthy();
      expect(era.caption).toBeTruthy();
      expect(homeEraAsset(era, 640)).toBe(`${era.subjectBase}-640.webp`);
      expect(homeEraAsset(era, 1280)).toBe(`${era.subjectBase}-1280.webp`);
    }
  });

  it('advances deterministically and loops at the final era', () => {
    expect(nextHomeEraIndex(0)).toBe(1);
    expect(nextHomeEraIndex(HOME_ERAS.length - 1)).toBe(0);
    expect(nextHomeEraIndex(Number.NaN)).toBe(0);
  });
});
