import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
  COMPANION_PORTRAIT_ASSETS,
  companionPortraitFor,
  companionPortraitUrl,
} from './companionPortraitAssets';

describe('companion portrait assets', () => {
  it('binds all eleven flagship personas and resolves parenthetical aliases', () => {
    expect(COMPANION_PORTRAIT_ASSETS).toHaveLength(11);
    expect(new Set(COMPANION_PORTRAIT_ASSETS.map((asset) => `${asset.lessonId}:${asset.name}`)).size)
      .toBe(11);
    expect(companionPortraitFor('L101', { name: '益' })?.slug).toBe('yi');
    expect(companionPortraitFor('L103', { name: '商鞅' })?.slug).toBe('shang-yang');
    expect(companionPortraitFor('L102', { name: '禹' })).toBeNull();
  });

  it('builds deterministic responsive portrait paths', () => {
    const yu = companionPortraitFor('L101', { name: '禹' });
    expect(yu).not.toBeNull();
    expect(companionPortraitUrl(yu!, 256)).toBe('/assets/companions/portraits/L101-yu-256.webp');
    expect(companionPortraitUrl(yu!, 512)).toBe('/assets/companions/portraits/L101-yu-512.webp');
  });

  it('keeps every packaged portrait present and checksum-bound', () => {
    const assetRoot = new URL('../../../public/assets/companions/portraits/', import.meta.url);
    const manifest = JSON.parse(readFileSync(new URL('manifest.json', assetRoot), 'utf8')) as {
      schema: string;
      lessons: Record<string, {
        portraits: Record<string, {
          variants: Array<{ file: string; bytes: number; sha256: string }>;
        }>;
      }>;
    };

    expect(manifest.schema).toBe('chronovita-companion-portrait-assets/v1');
    for (const asset of COMPANION_PORTRAIT_ASSETS) {
      const variants = manifest.lessons[asset.lessonId]?.portraits[asset.slug]?.variants;
      expect(variants).toHaveLength(2);
      for (const variant of variants) {
        const buffer = readFileSync(new URL(variant.file, assetRoot));
        expect(buffer.byteLength).toBe(variant.bytes);
        expect(createHash('sha256').update(buffer).digest('hex')).toBe(variant.sha256);
      }
    }
  });
});
