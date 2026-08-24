import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import type { GameNarrativeMessage } from '../../utils/api';
import {
  choiceMark,
  endingTone,
  gameSceneForLesson,
  groupAdventureRounds,
  roundLabel,
} from './gamePresentation';

describe('game presentation model', () => {
  it('groups opening and turn dialogue without losing context', () => {
    const history: GameNarrativeMessage[] = [
      { role: 'system', text: '河道漫出旧岸。', turn_no: 0 },
      { role: 'narrator', text: '众人等待议事。', turn_no: 0 },
      { role: 'player', text: '先踏勘支流。', turn_no: 1 },
      { role: 'narrator', text: '水势仍涨，但地形逐渐清晰。', turn_no: 1 },
    ];
    expect(groupAdventureRounds(history)).toEqual([
      { turnNo: 0, player: '', narration: '河道漫出旧岸。\n\n众人等待议事。' },
      { turnNo: 1, player: '先踏勘支流。', narration: '水势仍涨，但地形逐渐清晰。' },
    ]);
  });

  it('keeps positive endings narrow and treats costly outcomes as mixed', () => {
    expect(endingTone('ending-balanced-success', 'completed')).toBe('positive');
    expect(endingTone('ending-balanced-reform', 'completed')).toBe('positive');
    expect(endingTone('ending-costly-success', 'completed')).toBe('mixed');
    expect(endingTone('ending-negotiated-compromise', 'completed')).toBe('mixed');
    expect(endingTone('ending-governance-failure', 'completed')).toBe('negative');
    expect(endingTone(null, 'failed')).toBe('negative');
  });

  it('provides concise round and choice labels', () => {
    expect(roundLabel(0)).toBe('序章');
    expect(roundLabel(4)).toBe('第 4 回合');
    expect(choiceMark(0)).toBe('壹');
    expect(choiceMark(8)).toBe('玖');
    expect(choiceMark(9)).toBe('10');
  });

  it('binds both flagship lessons to checked responsive scene assets', async () => {
    const publicRoot = path.resolve(process.cwd(), 'public');
    const manifest = JSON.parse(await readFile(
      path.join(publicRoot, 'assets/game-scenes/manifest.json'),
      'utf8',
    )) as {
      schema: string;
      scenes: Record<string, {
        variants: Array<{ file: string; width: number; height: number; sha256: string }>;
      }>;
    };
    expect(manifest.schema).toBe('chronovita-game-scene-assets/v1');
    for (const lessonId of ['L101', 'L103']) {
      const scene = gameSceneForLesson(lessonId);
      const variants = manifest.scenes[lessonId].variants;
      expect(variants.map((variant) => [variant.width, variant.height])).toEqual([
        [960, 540],
        [1600, 900],
      ]);
      expect(scene.source960.endsWith(variants[0].file)).toBe(true);
      expect(scene.source1600.endsWith(variants[1].file)).toBe(true);
      for (const variant of variants) {
        const buffer = await readFile(path.join(publicRoot, 'assets/game-scenes', variant.file));
        expect(createHash('sha256').update(buffer).digest('hex')).toBe(variant.sha256);
      }
    }
  });
});
