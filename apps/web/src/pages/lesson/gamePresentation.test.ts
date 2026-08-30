import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import type { GameNarrativeMessage, ScenarioNpcDialogueV1 } from '../../utils/api';
import {
  choiceMark,
  endingTone,
  gameSceneForLesson,
  groupAdventureRounds,
  mergeScenarioNpcDialogues,
  roundLabel,
  scenarioNpcDialogueMatchesSession,
  scenarioNpcDialogueRoute,
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

  it('maps internal dialogue provenance to student-facing presentation routes', () => {
    expect(scenarioNpcDialogueRoute({
      route_source: 'local_state',
      route_reason: 'fixed_action_local',
    })).toBe('local-script');
    expect(scenarioNpcDialogueRoute({
      route_source: 'local_state',
      route_reason: 'free_input_local',
    })).toBe('local-evidence');
    expect(scenarioNpcDialogueRoute({
      route_source: 'external_api',
      route_reason: 'free_input_external_polish',
    })).toBe('api-assisted');
    expect(scenarioNpcDialogueRoute({
      route_source: 'fallback',
      route_reason: 'external_unavailable',
    })).toBe('safe-fallback');
  });

  it('merges restored and submitted dialogue by turn without duplicates', () => {
    const first = dialogueFixture('turn-1', 1, '原回应');
    const replaced = dialogueFixture('turn-1', 1, '幂等恢复后的回应');
    const second = dialogueFixture('turn-2', 2, '第二回合回应');
    const merged = mergeScenarioNpcDialogues([second, first], [replaced]);
    expect(merged.map((item) => [item.turn_id, item.text])).toEqual([
      ['turn-1', '幂等恢复后的回应'],
      ['turn-2', '第二回合回应'],
    ]);
  });

  it('rejects a dialogue projection that is not pinned to the restored session', () => {
    const dialogue = dialogueFixture('turn-1', 1, '人物回应');
    const session = {
      session_id: 'session-1', user_id: 'student-1', course_id: 'course-1', lesson_id: 'lesson-1',
      scenario_id: 'scenario-1', scenario_version: 1, course_content_version: 1,
      course_checksum: 'b'.repeat(64), scenario_checksum: 'c'.repeat(64),
      status: 'active' as const, revision: 2, current_turn: 1, current_state: {}, npc_states: [],
      turns: [{
        turn_id: 'turn-1', session_id: 'session-1', client_action_id: 'client-1', turn_no: 1,
        status: 'applied' as const, raw_input: '行动', action_source: 'fixed' as const,
        classified_action_id: 'action-1', state_before: {}, state_after: {}, state_changes: [],
        npc_changes: [], triggered_event_ids: [], narrative: '局势', created_at: '2026-01-01T00:00:00Z',
      }],
      triggered_event_ids: [], available_action_ids: [], available_choices: [], summary: '局势',
      history: [], ending_id: null, dossier_id: null, started_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z', ended_at: null,
    };
    const pin = {
      release_id: 'release-1', release_no: 1, release_checksum: 'a'.repeat(64),
      course_id: 'course-1', lesson_id: 'lesson-1', course_content_version: 1,
      course_checksum: 'b'.repeat(64), scenario_version: 1, scenario_checksum: 'c'.repeat(64),
    };
    expect(scenarioNpcDialogueMatchesSession(dialogue, session, pin)).toBe(true);
    expect(scenarioNpcDialogueMatchesSession(
      { ...dialogue, release_checksum: '9'.repeat(64) },
      session,
      pin,
    )).toBe(false);
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

function dialogueFixture(turnId: string, turnNo: number, text: string): ScenarioNpcDialogueV1 {
  return {
    schema_version: 'scenario-npc-dialogue/v1',
    session_id: 'session-1', turn_id: turnId, turn_no: turnNo,
    node_id: 'node-1', action_id: 'action-1', binding_id: 'binding-1',
    person_id: 'person-1', display_name: '人物', role: '课堂人物',
    persona_kind: 'historical_person', portrait_asset_key: null,
    text, disclaimer: '角色化教学表达，不是史料原话。',
    route_source: 'local_state', route_reason: 'fixed_action_local',
    release_id: 'release-1', release_no: 1, release_checksum: 'a'.repeat(64),
    course_id: 'course-1', lesson_id: 'lesson-1',
    course_content_version: 1, course_checksum: 'b'.repeat(64),
    scenario_id: 'scenario-1', scenario_version: 1, scenario_checksum: 'c'.repeat(64),
    persona_pack_id: 'persona-1', persona_pack_version: 1,
    persona_pack_checksum: 'd'.repeat(64), evidence_corpus_id: 'evidence-1',
    evidence_version: 1, evidence_checksum: 'e'.repeat(64),
    used_passage_ids: ['passage-1'], used_slot_ids: [], used_boundary_ids: ['boundary-1'],
    provider: '', model: '', fallback_reason: '', basis_checksum: 'f'.repeat(64),
    output_checksum: '0'.repeat(64),
  };
}
