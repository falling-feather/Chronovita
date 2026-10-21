import type {
  EvidenceDraft,
  EvidencePassage,
  EvidenceSource,
  LessonContentPackage,
  LessonPresentation,
  RuntimeEvidenceRecord,
  RuntimePresentationRecord,
  SupplementArtifactDescriptor,
} from '../../utils/api';

const ZERO_CHECKSUM = '0'.repeat(64);

export function uniqueSorted(values: string[]): string[] {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean))).sort();
}

export function normalizeEvidenceDraft(draft: EvidenceDraft): EvidenceDraft {
  return {
    ...draft,
    sources: draft.sources
      .map((source) => ({ ...source }))
      .sort((left, right) => left.source_id.localeCompare(right.source_id)),
    passages: draft.passages
      .map((passage) => ({
        ...passage,
        fact_ids: uniqueSorted(passage.fact_ids),
        person_ids: uniqueSorted(passage.person_ids),
        keywords: uniqueSorted(passage.keywords),
      }))
      .sort((left, right) => left.passage_id.localeCompare(right.passage_id)),
  };
}

export function createEvidenceDraft(
  courseId = 'C-prequin-state',
  lessonId = 'L101',
): EvidenceDraft {
  return {
    schema_version: 'evidence-corpus-draft/v1',
    corpus_id: `${lessonId.toLowerCase()}-evidence-draft`,
    course_id: courseId,
    lesson_id: lessonId,
    title: `${lessonId} 课程证据库`,
    scope_note: '说明本证据库适用的课程、材料层次、可得结论与不可越过的史实边界。',
    sources: [],
    passages: [],
    revision: 0,
    created_at: null,
    updated_at: null,
    created_by: null,
    updated_by: null,
  };
}

export function createEvidenceSource(index: number): EvidenceSource {
  return {
    source_id: `source-${String(index).padStart(2, '0')}`,
    title: '',
    kind: 'other',
    author_or_institution: '',
    publisher: '',
    published_year: null,
    url_or_path: '',
    locator: '',
    citation_note: '',
    reliability: 'reviewed',
    rights_note: '仅保存必要摘录、自写摘要和出处，不复制受版权保护的整章内容。',
  };
}

export function createEvidencePassage(index: number, sourceId = ''): EvidencePassage {
  return {
    passage_id: `passage-${String(index).padStart(3, '0')}`,
    source_id: sourceId,
    title: '',
    text: '',
    summary: '',
    fact_ids: [],
    person_ids: [],
    keywords: [],
    evidence_kind: 'teaching_explanation',
    certainty: 'interpretation',
    chronology_note: '请说明材料年代与所讨论历史时期之间的关系。',
    teaching_note: '',
  };
}

export function supplementKey(
  record: RuntimeEvidenceRecord | RuntimePresentationRecord | SupplementArtifactDescriptor,
): string {
  const descriptor = 'descriptor' in record ? record.descriptor : record;
  return `${descriptor.artifact_id}@${descriptor.version}:${descriptor.checksum}`;
}

function pythonCanonicalJson(value: unknown, key = ''): string {
  if (value === null) return 'null';
  if (typeof value === 'string') return JSON.stringify(value);
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error('展示资源不能包含非有限数字');
    if (key === 'video_duration_seconds' && Number.isInteger(value)) return `${value}.0`;
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => pythonCanonicalJson(item)).join(',')}]`;
  }
  if (typeof value === 'object') {
    const object = value as Record<string, unknown>;
    const keys = Object.keys(object)
      .filter((item) => object[item] !== undefined)
      .sort();
    return `{${keys.map((item) => (
      `${JSON.stringify(item)}:${pythonCanonicalJson(object[item], item)}`
    )).join(',')}}`;
  }
  throw new Error('展示资源包含无法签名的字段');
}

async function digestHex(algorithm: 'SHA-1' | 'SHA-256', value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest(algorithm, bytes);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

export async function signLessonPresentation(
  presentation: Omit<LessonPresentation, 'checksum'> | LessonPresentation,
): Promise<LessonPresentation> {
  const sealedAt = presentation.sealed_at.replace(
    /\.(\d{3})Z$/,
    (_, milliseconds: string) => milliseconds === '000' ? 'Z' : `.${milliseconds}000Z`,
  );
  const provisional = {
    ...presentation,
    sealed_at: sealedAt,
    checksum: null,
  } as unknown as Record<string, unknown>;
  const checksum = await digestHex('SHA-256', pythonCanonicalJson(provisional));
  return { ...presentation, checksum } as LessonPresentation;
}

export function createLessonPresentation(
  courseId = 'C-prequin-state',
  lessonId = 'L101',
  version = 1,
): LessonPresentation {
  const root = `media/lessons/${lessonId}/v${String(version).padStart(3, '0')}`;
  return {
    schema_version: 'lesson-presentation/v1',
    presentation_id: `${lessonId.toLowerCase()}-presentation`,
    course_id: courseId,
    lesson_id: lessonId,
    presentation_version: version,
    status: 'sealed',
    title: `${lessonId} 课堂导入短片`,
    estimated_minutes: 39,
    phase_minutes: { observe: 9, decide: 14, consult: 7, dossier: 9 },
    video_path: `${root}/intro.mp4`,
    poster_path: `${root}/poster.webp`,
    transcript_path: `${root}/transcript.md`,
    video_duration_seconds: 50,
    video_width: 1920,
    video_height: 1080,
    video_fps: 30,
    video_sha256: ZERO_CHECKSUM,
    poster_sha256: ZERO_CHECKSUM,
    transcript_sha256: ZERO_CHECKSUM,
    skip_allowed: true,
    accessibility_note: '提供完整中文字幕、可访问文字稿、本地 poster，并允许学生跳过短片。',
    sealed_at: new Date().toISOString(),
    sealed_by: 'classroom-admin',
    checksum: ZERO_CHECKSUM,
  };
}

async function stableId(prefix: string, seed: string): Promise<string> {
  const digest = await digestHex('SHA-1', seed);
  return `${prefix}-${digest.slice(0, 8)}`;
}

export interface LessonEvidenceBinding {
  id: string;
  label: string;
}

export async function lessonEvidenceBindings(packageItem: LessonContentPackage): Promise<{
  facts: LessonEvidenceBinding[];
  people: LessonEvidenceBinding[];
}> {
  const facts = await Promise.all((packageItem.facts || []).map(async (statement) => ({
    id: await stableId('fact', statement.trim()),
    label: statement.trim(),
  })));
  const people = await Promise.all((packageItem.people || []).map(async (person) => {
    const seed = JSON.stringify([
      person.name || '',
      person.role || '',
      person.summary || '',
      person.persona || '',
      person.boundaries || [],
    ]);
    return {
      id: await stableId('person', seed),
      label: `${person.name}${person.role ? ` · ${person.role}` : ''}`,
    };
  }));
  return { facts, people };
}
