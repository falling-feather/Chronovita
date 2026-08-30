import type {
  GameNarrativeMessage,
  ScenarioReleasePin,
  GameSession,
  ScenarioNpcDialogueV1,
} from '../../utils/api';
import { publicAssetUrl } from '../../runtime';
import type { ScenarioNpcDialogueRoute } from './ScenarioNpcDialogue';

export interface GameSceneAsset {
  lessonId: string;
  title: string;
  place: string;
  time: string;
  alt: string;
  source960: string;
  source1600: string;
  palette: 'flood' | 'qin' | 'generic';
}

export interface AdventureRound {
  turnNo: number;
  player: string;
  narration: string;
}

export type EndingTone = 'positive' | 'mixed' | 'negative';

const GAME_SCENE_ROOT = '/assets/game-scenes';

const GAME_SCENES: Record<string, GameSceneAsset> = {
  L101: {
    lessonId: 'L101',
    title: '河畔议事 · 连雨未歇',
    place: '洪泛平原与低地聚落',
    time: '约公元前21世纪的课堂情境',
    alt: '暴雨后的河道、低地聚落与协作治水现场教学插画',
    source960: publicAssetUrl(`${GAME_SCENE_ROOT}/L101-flood-council-960.webp`),
    source1600: publicAssetUrl(`${GAME_SCENE_ROOT}/L101-flood-council-1600.webp`),
    palette: 'flood',
  },
  L103: {
    lessonId: 'L103',
    title: '秦廷议法 · 新令将行',
    place: '战国秦国的改革议事空间',
    time: '公元前4世纪的课堂情境',
    alt: '战国秦土木议事空间、简牍与农田城墙教学插画',
    source960: publicAssetUrl(`${GAME_SCENE_ROOT}/L103-qin-reform-council-960.webp`),
    source1600: publicAssetUrl(`${GAME_SCENE_ROOT}/L103-qin-reform-council-1600.webp`),
    palette: 'qin',
  },
};

const GENERIC_SCENE: GameSceneAsset = {
  lessonId: '',
  title: '历史议事现场',
  place: '本课历史情境',
  time: '课堂推演',
  alt: '',
  source960: '',
  source1600: '',
  palette: 'generic',
};

export function gameSceneForLesson(lessonId: string): GameSceneAsset {
  return GAME_SCENES[lessonId] ?? { ...GENERIC_SCENE, lessonId };
}

export function groupAdventureRounds(history: GameNarrativeMessage[]): AdventureRound[] {
  const byTurn = new Map<number, AdventureRound>();
  for (const message of history) {
    const turnNo = Math.max(0, message.turn_no);
    const current = byTurn.get(turnNo) ?? { turnNo, player: '', narration: '' };
    if (message.role === 'player') {
      current.player = appendParagraph(current.player, message.text);
    } else {
      current.narration = appendParagraph(current.narration, message.text);
    }
    byTurn.set(turnNo, current);
  }
  return [...byTurn.values()]
    .filter((round) => round.player || round.narration)
    .sort((left, right) => left.turnNo - right.turnNo);
}

export function endingTone(
  endingId: string | null | undefined,
  status: GameSession['status'],
): EndingTone {
  if (status === 'failed' || status === 'abandoned') return 'negative';
  const normalized = (endingId ?? '').toLowerCase();
  if (/(failure|breakdown|collapse|uncontrolled|lost)/.test(normalized)) return 'negative';
  if (/(balanced|water-controlled|durable|credible)/.test(normalized)) return 'positive';
  return 'mixed';
}

export function roundLabel(turnNo: number): string {
  if (turnNo <= 0) return '序章';
  return `第 ${turnNo} 回合`;
}

export function choiceMark(index: number): string {
  return ['壹', '贰', '叁', '肆', '伍', '陆', '柒', '捌', '玖'][index] ?? String(index + 1);
}

export function scenarioNpcDialogueRoute(
  dialogue: Pick<ScenarioNpcDialogueV1, 'route_source' | 'route_reason'>,
): ScenarioNpcDialogueRoute {
  if (dialogue.route_source === 'external_api') return 'api-assisted';
  if (dialogue.route_source === 'fallback') return 'safe-fallback';
  return dialogue.route_reason === 'fixed_action_local'
    ? 'local-script'
    : 'local-evidence';
}

export function mergeScenarioNpcDialogues(
  current: ScenarioNpcDialogueV1[],
  incoming: ScenarioNpcDialogueV1[],
): ScenarioNpcDialogueV1[] {
  if (incoming.length === 0) return current;
  const byTurnId = new Map(current.map((dialogue) => [dialogue.turn_id, dialogue]));
  for (const dialogue of incoming) byTurnId.set(dialogue.turn_id, dialogue);
  return [...byTurnId.values()].sort((left, right) => (
    left.turn_no - right.turn_no || left.turn_id.localeCompare(right.turn_id)
  ));
}

export function scenarioNpcDialogueMatchesSession(
  dialogue: ScenarioNpcDialogueV1,
  session: GameSession,
  releasePin: ScenarioReleasePin,
): boolean {
  const turn = session.turns.find((item) => item.turn_id === dialogue.turn_id);
  return dialogue.session_id === session.session_id
    && dialogue.turn_no === turn?.turn_no
    && dialogue.course_id === session.course_id
    && dialogue.lesson_id === session.lesson_id
    && dialogue.course_content_version === session.course_content_version
    && dialogue.course_checksum === session.course_checksum
    && dialogue.scenario_id === session.scenario_id
    && dialogue.scenario_version === session.scenario_version
    && dialogue.scenario_checksum === session.scenario_checksum
    && dialogue.release_id === releasePin.release_id
    && dialogue.release_no === releasePin.release_no
    && dialogue.release_checksum === releasePin.release_checksum;
}

function appendParagraph(current: string, next: string): string {
  const value = next.trim();
  if (!value) return current;
  return current ? `${current}\n\n${value}` : value;
}
