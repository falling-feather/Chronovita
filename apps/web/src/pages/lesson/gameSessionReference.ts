import type {
  GameDossier,
  GameScenarioSummary,
  GameSession,
  Lesson,
  LessonScenarioRef,
  ScenarioReleasePin,
} from '../../utils/api';
import { loadJSON, removeKey, saveJSON } from '../../utils/storage';

export interface GameBinding {
  scenario: LessonScenarioRef;
  pin: ScenarioReleasePin;
  identity: string;
  storageKey: string;
}

export interface StoredGameReference {
  schema_version: 'game-session-ref/v1';
  identity: string;
  client_request_id: string;
  session_id?: string;
  scenario?: GameScenarioSummary;
}

export interface StoredStartedGameReference extends StoredGameReference {
  session_id: string;
}

export function buildGameBinding(
  lesson: Lesson,
  scenario: LessonScenarioRef,
): GameBinding | null {
  if (
    !lesson.release_id
    || typeof lesson.release_no !== 'number'
    || !lesson.release_checksum
    || typeof lesson.content_version !== 'number'
    || lesson.content_version < 1
    || !lesson.content_checksum
    || scenario.scenario_version < 1
    || !scenario.checksum
    || lesson.primary_scenario_id !== scenario.scenario_id
  ) {
    return null;
  }
  const pin: ScenarioReleasePin = {
    release_id: lesson.release_id,
    release_no: lesson.release_no,
    release_checksum: lesson.release_checksum,
    course_id: lesson.course_id,
    lesson_id: lesson.id,
    course_content_version: lesson.content_version,
    course_checksum: lesson.content_checksum,
    scenario_version: scenario.scenario_version,
    scenario_checksum: scenario.checksum,
  };
  const identity = [
    pin.release_id,
    pin.release_no,
    pin.release_checksum,
    pin.course_id,
    pin.lesson_id,
    pin.course_content_version,
    pin.course_checksum,
    scenario.scenario_id,
    pin.scenario_version,
    pin.scenario_checksum,
  ].join('|');
  const storageKey = `game-session.v1.${[
    pin.course_id,
    pin.lesson_id,
    pin.release_id,
    scenario.scenario_id,
    String(pin.scenario_version),
    pin.course_checksum.slice(0, 12),
    pin.scenario_checksum.slice(0, 12),
  ].map(encodeURIComponent).join('.')}`;
  return { scenario, pin, identity, storageKey };
}

export function readStoredGameReference(
  binding: GameBinding,
): StoredGameReference | null {
  const stored = loadJSON<StoredGameReference | null>(binding.storageKey, null);
  if (isStoredGameReference(stored, binding.identity)) return stored;
  removeKey(binding.storageKey);
  return null;
}

export function readStoredStartedGameReference(
  binding: GameBinding,
): StoredStartedGameReference | null {
  const stored = readStoredGameReference(binding);
  if (!stored || typeof stored.session_id !== 'string' || !stored.session_id.trim()) {
    return null;
  }
  return stored as StoredStartedGameReference;
}

export function clearStoredGameReference(binding: GameBinding): void {
  removeKey(binding.storageKey);
}

export function persistPendingGameReference(
  binding: GameBinding,
  reference: StoredGameReference,
): void {
  saveJSON(binding.storageKey, reference);
  const persisted = loadJSON<StoredGameReference | null>(binding.storageKey, null);
  if (
    !isStoredGameReference(persisted, reference.identity)
    || persisted.client_request_id !== reference.client_request_id
    || persisted.session_id !== reference.session_id
  ) {
    throw new Error('浏览器无法保存学习记录，请允许本站使用本地存储后重试。');
  }
}

export function assertSessionIdentity(
  session: GameSession,
  binding: GameBinding,
): void {
  const actual = [
    session.course_id,
    session.lesson_id,
    session.course_content_version,
    session.course_checksum,
    session.scenario_id,
    session.scenario_version,
    session.scenario_checksum,
  ];
  const expected = [
    binding.pin.course_id,
    binding.pin.lesson_id,
    binding.pin.course_content_version,
    binding.pin.course_checksum,
    binding.scenario.scenario_id,
    binding.pin.scenario_version,
    binding.pin.scenario_checksum,
  ];
  if (actual.some((value, index) => value !== expected[index])) {
    throw new Error('服务器返回的学习会话与当前课时版本不一致。');
  }
}

export function assertScenarioIdentity(
  scenario: GameScenarioSummary,
  binding: GameBinding,
): void {
  if (
    scenario.audience !== 'published'
    || scenario.release_id !== binding.pin.release_id
    || scenario.release_no !== binding.pin.release_no
    || scenario.release_checksum !== binding.pin.release_checksum
    || scenario.course_id !== binding.pin.course_id
    || scenario.lesson_id !== binding.pin.lesson_id
    || scenario.scenario_id !== binding.scenario.scenario_id
    || scenario.scenario_version !== binding.pin.scenario_version
    || scenario.scenario_checksum !== binding.pin.scenario_checksum
  ) {
    throw new Error('服务器返回的互动关卡与当前课时发布版本不一致。');
  }
}

export function assertDossierIdentity(
  dossier: GameDossier,
  session: GameSession,
  binding: GameBinding,
): void {
  if (
    session.status !== 'completed'
    || !session.ended_at
    || dossier.status !== 'final'
    || dossier.schema_version !== 'dossier/v1'
    || !dossier.checksum
    || !session.dossier_id
    || dossier.dossier_id !== session.dossier_id
    || dossier.session_id !== session.session_id
    || dossier.user_id !== session.user_id
    || dossier.course_id !== binding.pin.course_id
    || dossier.lesson_id !== binding.pin.lesson_id
    || dossier.scenario_id !== binding.scenario.scenario_id
    || dossier.course_content_version !== binding.pin.course_content_version
    || dossier.scenario_version !== binding.pin.scenario_version
    || dossier.course_checksum !== binding.pin.course_checksum
    || dossier.scenario_checksum !== binding.pin.scenario_checksum
    || dossier.ending_id !== session.ending_id
    || !Array.isArray(dossier.key_choices)
    || !Array.isArray(dossier.major_costs)
    || !Array.isArray(dossier.knowledge_nodes)
    || !Array.isArray(dossier.knowledge_edges)
    || !Array.isArray(dossier.follow_up_questions)
  ) {
    throw new Error('服务器返回的史官卷宗与当前课时版本不一致。');
  }
}

function isStoredGameReference(
  value: StoredGameReference | null,
  identity: string,
): value is StoredGameReference {
  return Boolean(
    value
    && value.schema_version === 'game-session-ref/v1'
    && value.identity === identity
    && typeof value.client_request_id === 'string'
    && value.client_request_id.length > 0,
  );
}
