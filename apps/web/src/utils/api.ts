// 统一的 API 客户端 · v0.2.0
import { IS_STATIC_PREVIEW } from '../runtime';
import { staticPreviewJsonFetch } from '../preview/staticPreview';

const BASE = '/api/v1';

// Accounts 模式以这个非秘密哨兵表示“使用浏览器 HttpOnly Cookie”。旧的
// legacy-local 模式仍可显式传入共享令牌，二者不会同时发送。
export const COOKIE_AUTH_CREDENTIAL = '__chronovita_http_only_cookie__';

interface ApiValidationIssue {
  loc?: Array<string | number>;
  msg?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(status: number, message: string, code?: string) {
    super(`${status} ${message}`);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

function localizeValidationMessage(message: string): string {
  if (message.includes('String should match pattern')) return '只能使用英文字母、数字、点、下划线和短横线';
  if (message.includes('at least 2 characters')) return '至少需要 2 个字符';
  if (message.includes('at most 64 characters')) return '最多允许 64 个字符';
  if (message.includes('Field required')) return '该字段为必填项';
  return message.replace(/^Value error,\s*/i, '');
}

export async function apiResponseError(response: Response): Promise<ApiError> {
  const raw = await response.text();
  let message = raw || response.statusText;
  let code: string | undefined;
  try {
    const parsed = JSON.parse(raw) as {
      detail?: string | { message?: string; code?: string } | ApiValidationIssue[];
    };
    if (typeof parsed.detail === 'string') {
      message = parsed.detail;
    } else if (Array.isArray(parsed.detail)) {
      message = parsed.detail.map((issue) => {
        const field = (issue.loc || []).filter((part) => part !== 'body').join('.');
        const detail = localizeValidationMessage(issue.msg || '字段校验失败');
        return field ? `${field}：${detail}` : detail;
      }).join('；');
    } else if (parsed.detail?.message) {
      message = parsed.detail.message;
      code = parsed.detail.code;
    }
  } catch {
    // Keep the raw response when an upstream proxy does not return JSON.
  }
  return new ApiError(response.status, message, code);
}

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  if (IS_STATIC_PREVIEW) return staticPreviewJsonFetch<T>(path, init);
  const r = await fetch(BASE + path, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });
  if (!r.ok) {
    if (r.status === 401) {
      window.dispatchEvent(new Event('chronovita:session-invalid'));
    }
    throw await apiResponseError(r);
  }
  return r.json() as Promise<T>;
}

async function adminFetch<T>(token: string, path: string, init?: RequestInit): Promise<T> {
  const credentialHeaders: Record<string, string> = token === COOKIE_AUTH_CREDENTIAL
    ? {}
    : { Authorization: `Bearer ${token}` };
  return jsonFetch<T>(path, {
    ...init,
    headers: {
      ...credentialHeaders,
      ...(init?.headers || {}),
    },
  });
}

async function adminFile(token: string, path: string): Promise<Blob> {
  const credentialHeaders: Record<string, string> = token === COOKIE_AUTH_CREDENTIAL
    ? {}
    : { Authorization: `Bearer ${token}` };
  const response = await fetch(BASE + path, {
    credentials: 'include',
    headers: credentialHeaders,
  });
  if (!response.ok) {
    if (response.status === 401) {
      window.dispatchEvent(new Event('chronovita:session-invalid'));
    }
    throw await apiResponseError(response);
  }
  return response.blob();
}

export interface Era { id: string; name: string; period: string; summary: string }
export interface CourseSummary {
  id: string; era_id: string; title: string; subtitle: string;
  cover_color: string; section: string; lesson_count: number;
}
export interface LessonSummary { id: string; num: string; title: string; duration: string; state: string }
export interface CourseDetail {
  summary: CourseSummary; intro: string; lessons: LessonSummary[];
}
export interface Keyword { word: string; pinyin: string; gloss: string }
export interface PersonCard {
  person_id?: string; name: string; role?: string; summary?: string;
  persona?: string; boundaries?: string[];
}
export interface MapPoint {
  label: string; region?: string; lat?: number | null; lng?: number | null; note?: string; kind?: string;
}
export interface SourceRef {
  title: string; source?: string; url_or_path?: string; citation_note?: string; reliability?: string;
}
export interface MaterialPlaceholder {
  title?: string; objective?: string; notes?: string; assets?: string[];
}
export interface LessonContentPackage {
  lesson_id: string; title: string; unit: string; era: string; body: string[];
  course_id?: string; course_title?: string; era_id?: string; section?: string;
  lesson_no?: string; duration?: string; abstract?: string;
  keywords?: Keyword[]; people?: PersonCard[]; map_points?: MapPoint[]; source_refs?: SourceRef[];
  facts?: string[]; qa_points?: string[]; level_goals?: string[];
  saga_material?: MaterialPlaceholder; sandbox_material?: MaterialPlaceholder;
  seed_canvas?: { id?: string; label: string; note?: string }[];
  teacher_notes?: string;
  status?: 'draft' | 'sealed'; version?: number;
  created_at?: string | null; updated_at?: string | null; sealed_at?: string | null; sealed_by?: string | null;
  checksum?: string | null;
}
export interface ContentFileRecord {
  lesson_id: string; title: string; status: string; version: number; path: string;
  updated_at?: string | null; sealed_at?: string | null; sealed_by?: string | null; checksum?: string | null;
}
export type ContentWorkflowState =
  | 'draft'
  | 'validated'
  | 'in_review'
  | 'changes_requested'
  | 'approved'
  | 'sealed'
  | 'published';
export interface ContentValidationIssue {
  code: string; severity: 'error' | 'warning'; field: string; message: string;
}
export interface ContentValidationReport {
  schema_version: string; validator_version: string; lesson_id: string;
  draft_fingerprint: string; valid: boolean; issues: ContentValidationIssue[];
  validated_at: string; validated_by: string;
}
export interface ContentWorkflowRecord {
  lesson_id: string; course_id: string; state: ContentWorkflowState; revision: number;
  draft_fingerprint: string; validation?: ContentValidationReport | null;
  sealed_version?: number | null; sealed_checksum?: string | null;
  published_course_id?: string | null; published_version?: number | null;
  published_release_id?: string | null; updated_at: string; checksum: string;
}
export interface RuntimeArtifactDescriptor {
  kind: 'course-package' | 'scenario-template';
  schema_version: 'course-package/v1' | 'scenario-template/v1';
  artifact_id: string; course_id: string; lesson_id: string;
  version: number; checksum: string; path: string;
}
export interface SupplementArtifactDescriptor {
  kind: 'evidence-corpus' | 'lesson-presentation';
  schema_version: 'evidence-corpus/v1' | 'lesson-presentation/v1';
  artifact_id: string; course_id: string; lesson_id: string;
  version: number; checksum: string; path: string;
}
export interface CourseReleaseItemV1 {
  lesson_id: string; course_id: string; content_version: number;
  source_path: string; source_checksum: string; package_path: string;
  package_checksum: string; package_schema: string;
}
export interface CourseReleaseItemV2 {
  lesson_id: string; course_id: string; content_version: number;
  source_path: string; source_checksum: string;
  course_package: RuntimeArtifactDescriptor;
  scenarios: RuntimeArtifactDescriptor[];
  primary_scenario_id?: string | null;
  audience: 'published';
}
export interface CourseReleaseItemV3 extends CourseReleaseItemV2 {
  evidence_corpus: SupplementArtifactDescriptor;
  lesson_presentation: SupplementArtifactDescriptor;
}
export type CourseReleaseItem = CourseReleaseItemV1 | CourseReleaseItemV2 | CourseReleaseItemV3;
export interface CourseReleaseManifest {
  schema_version: string; release_id: string; release_no: number; course_id: string;
  operation: 'bootstrap' | 'publish' | 'rollback'; parent_release_id?: string | null;
  restored_from_release_id?: string | null; created_at: string; created_by: string;
  note: string; items: CourseReleaseItem[]; checksum: string;
}
export type ArchiveFileKind =
  | 'release-manifest'
  | 'sealed-lesson'
  | 'course-package'
  | 'scenario-template'
  | 'evidence-corpus'
  | 'lesson-presentation'
  | 'format-layer'
  | 'teacher-markdown'
  | 'preview-html';
export interface CourseArchiveFile {
  path: string; kind: ArchiveFileKind; media_type: string;
  size_bytes: number; blob_sha256: string; lesson_id?: string | null;
  artifact_id?: string | null; artifact_version?: number | null;
  schema_version?: string | null; contract_checksum?: string | null;
}
export interface CourseArchiveScenario {
  scenario_id: string; scenario_version: number;
  scenario_checksum: string; primary: boolean;
}
export interface CourseArchiveLesson {
  lesson_id: string; title: string; content_version: number;
  source_checksum: string; course_package_id: string;
  course_package_checksum: string; scenarios: CourseArchiveScenario[];
  files: string[];
}
export interface CourseArchiveManifest {
  schema_version: 'course-archive/v1';
  course_id: string; course_title: string;
  release_schema_version: string; release_id: string; release_no: number;
  release_checksum: string; release_operation: CourseReleaseManifest['operation'];
  release_created_at: string; release_created_by: string; release_note: string;
  renderer: {
    schema_version: 'archive-renderer/v1';
    renderer_id: string; renderer_version: number; style_profile: string;
  };
  manifest_path: string;
  lessons: CourseArchiveLesson[]; files: CourseArchiveFile[];
  file_count: number; total_size_bytes: number;
  archive_id: string; archive_checksum: string; archive_path: string;
  manifest_checksum: string;
}
export type ContentAssetKind = 'person' | 'keyword' | 'scenario';
export type ContentAssetArchiveFileKind =
  | 'sealed-person'
  | 'sealed-keyword'
  | 'sealed-scenario';
export interface ContentAssetArchiveFile {
  path: string; kind: ContentAssetArchiveFileKind;
  media_type: 'application/json'; size_bytes: number;
  blob_sha256: string; schema_version: string; contract_checksum: string;
}
export interface ContentAssetArchiveManifest {
  schema_version: 'content-asset-archive/v1';
  asset_kind: ContentAssetKind; asset_id: string; title: string; version: number;
  source_schema_version: 'person-profile/v1' | 'keyword-profile/v1' | 'scenario-template/v1';
  source_checksum: string; sealed_at: string; sealed_by: string;
  files: ContentAssetArchiveFile[]; file_count: number; total_size_bytes: number;
  archive_id: string; archive_checksum: string; archive_path: string;
  manifest_checksum: string;
}
export type PublicationMode = 'pull_request' | 'direct_commit';
export type PublicationStatus =
  | 'requested'
  | 'preparing'
  | 'pushing'
  | 'commit_created'
  | 'ref_updated'
  | 'pr_open'
  | 'succeeded'
  | 'failed_retryable'
  | 'failed_terminal';
export interface CourseArchivePublishRequest {
  schema_version: 'course-archive-publish-request/v1';
  binding_id: string; course_id: string; release_id: string;
  expected_release_checksum: string; archive_id: string;
  expected_archive_checksum: string; mode: PublicationMode;
  client_request_id: string; change_summary: string;
  direct_commit_confirmed: boolean;
}
export interface ContentAssetArchivePublishRequest {
  schema_version: 'content-asset-archive-publish-request/v1';
  binding_id: string; asset_kind: ContentAssetKind; asset_id: string;
  version: number; expected_source_checksum: string; archive_id: string;
  expected_archive_checksum: string; mode: PublicationMode;
  client_request_id: string; change_summary: string;
  direct_commit_confirmed: boolean;
}
export interface GitRepositoryBinding {
  schema_version: 'git-repository-binding/v1';
  binding_id: string; provider: 'github'; repository_id: number;
  owner: string; repository: string; visibility: 'private';
  base_branch: string; root_prefix: string; asset_root_prefix?: string | null;
  credential_kind: 'github_app' | 'fine_grained_token';
  installation_id?: number | null; allowed_modes: PublicationMode[];
}
export interface GitPublicationIntent {
  schema_version: 'git-publication-intent/v1';
  publication_id: string; operation_key: string;
  binding: GitRepositoryBinding; request: CourseArchivePublishRequest;
  requested_at: string; requested_by: string; checksum: string;
}
export interface GitPublicationRecord {
  schema_version: 'git-publication-record/v1';
  intent: GitPublicationIntent; status: PublicationStatus;
  attempt: number; revision: number; branch_ref: string;
  base_sha?: string | null; tree_sha?: string | null; commit_sha?: string | null;
  pull_request_number?: number | null; pull_request_url?: string | null;
  last_error_code?: string | null; last_error_at?: string | null;
  updated_at: string; completed_at?: string | null; checksum: string;
}
export interface AssetGitPublicationIntent {
  schema_version: 'git-publication-intent/v1';
  publication_id: string; operation_key: string;
  binding: GitRepositoryBinding; request: ContentAssetArchivePublishRequest;
  requested_at: string; requested_by: string; checksum: string;
}
export interface AssetGitPublicationRecord {
  schema_version: 'git-publication-record/v1';
  intent: AssetGitPublicationIntent; status: PublicationStatus;
  attempt: number; revision: number; branch_ref: string;
  base_sha?: string | null; tree_sha?: string | null; commit_sha?: string | null;
  pull_request_number?: number | null; pull_request_url?: string | null;
  last_error_code?: string | null; last_error_at?: string | null;
  updated_at: string; completed_at?: string | null; checksum: string;
}
export interface PublicationResponse {
  publication: GitPublicationRecord; reused: boolean;
}
export interface AssetPublicationResponse {
  publication: AssetGitPublicationRecord; reused: boolean;
}
export interface WorkflowResponse {
  workflow: ContentWorkflowRecord; report?: ContentValidationReport | null;
}
export interface ReleaseResponse {
  release: CourseReleaseManifest; workflow?: ContentWorkflowRecord | null;
}
export interface LessonSourceRecord {
  lesson_id: string; course_id: string; course_title: string; title: string;
  lesson_no: string; era_id: string; era: string; source: string;
}
export interface ContentAssetRecord {
  asset_id: string; title: string; kind: 'person' | 'keyword'; path: string;
  status: 'draft' | 'sealed'; version: number;
  updated_at?: string | null; sealed_at?: string | null;
  sealed_by?: string | null; checksum?: string | null;
}
export interface ContentAssetValidationIssue {
  code: string; severity: 'error' | 'warning'; field: string; message: string;
}
export interface ContentAssetValidationReport {
  schema_version: 'content-asset-validation/v1';
  kind: 'person' | 'keyword'; asset_id: string; valid: boolean;
  issues: ContentAssetValidationIssue[]; validated_at: string;
}
export interface PersonProfilePackage {
  schema_version?: 'person-profile/v1';
  asset_id: string; name: string; role?: string; era?: string; summary?: string; persona?: string;
  boundaries?: string[]; keywords?: string[]; related_lessons?: string[]; source_refs?: SourceRef[];
  teacher_notes?: string; status?: 'draft' | 'sealed'; version?: number;
  created_at?: string | null; updated_at?: string | null;
  sealed_at?: string | null; sealed_by?: string | null; checksum?: string | null;
}
export interface KeywordProfilePackage {
  schema_version?: 'keyword-profile/v1';
  asset_id: string; word: string; pinyin?: string; gloss?: string; era?: string; category?: string;
  examples?: string[]; related_people?: string[]; related_lessons?: string[]; source_refs?: SourceRef[];
  teacher_notes?: string; status?: 'draft' | 'sealed'; version?: number;
  created_at?: string | null; updated_at?: string | null;
  sealed_at?: string | null; sealed_by?: string | null; checksum?: string | null;
}
export type ScenarioType = 'crisis_governance' | 'institutional_reform' | 'council';
export type ScenarioConditionKind = 'state' | 'turn' | 'npc';
export type ScenarioEffectKind = 'state' | 'npc';
export type ScenarioComparisonOperator = 'lt' | 'lte' | 'eq' | 'gte' | 'gt';
export interface ScenarioDraftVariable {
  variable_id: string; label: string; description: string;
  initial: number; minimum: number; maximum: number;
}
export interface ScenarioDraftNpc {
  person_id: string; display_name: string; role: string; persona: string;
  boundaries: string[]; initial_attitude: number; initial_trust: number; fact_refs: string[];
}
export interface ScenarioDraftCondition {
  kind: ScenarioConditionKind; variable_id: string; person_id: string;
  field: 'attitude' | 'trust'; operator: ScenarioComparisonOperator; value: number;
}
export interface ScenarioDraftEffect {
  kind: ScenarioEffectKind; variable_id: string; person_id: string;
  operation: 'add' | 'set'; value: number; attitude_delta: number; trust_delta: number;
  reveal_fact_refs: string[];
}
export interface ScenarioDraftAction {
  action_id: string; label: string; description: string; aliases: string[];
  available_when: ScenarioDraftCondition[]; effects: ScenarioDraftEffect[];
  feedback: string; fact_refs: string[]; next_node_id?: string | null;
}
export interface ScenarioDraftEvent {
  event_id: string; title: string; match: 'all' | 'any';
  trigger: ScenarioDraftCondition[]; effects: ScenarioDraftEffect[];
  narrative: string; once: boolean; priority: number; fact_refs: string[];
}
export interface ScenarioDraftEnding {
  ending_id: string; title: string; match: 'all' | 'any';
  conditions: ScenarioDraftCondition[]; summary: string; historical_explanation: string;
  major_costs: string[]; source_ref_ids: string[]; fact_refs: string[]; priority: number;
}
export interface ScenarioDraftNode {
  node_id: string; title: string; narration: string;
  action_ids: string[]; ending_id?: string | null;
}
export interface ScenarioDraftDossier {
  title_template: string; reflection_questions: string[]; knowledge_node_kinds: string[];
}
export interface ScenarioCompatibility {
  kind: string; source_id: string; source_version: string; source_checksum?: string | null;
  notes: string; unresolved_refs: string[]; legacy_materials: unknown[];
  legacy_id_map: Record<string, string>;
}
export interface ScenarioAuthorDraft {
  schema_version: 'scenario-author-draft/v1'; scenario_id: string;
  course_id: string; lesson_id: string; title: string; scenario_type: ScenarioType;
  student_role: string; objective: string; opening: string; max_turns: number;
  variables: ScenarioDraftVariable[]; npcs: ScenarioDraftNpc[];
  action_rules: ScenarioDraftAction[]; event_rules: ScenarioDraftEvent[];
  ending_rules: ScenarioDraftEnding[]; start_node_id?: string | null;
  nodes: ScenarioDraftNode[]; fact_refs: string[]; source_ref_ids: string[];
  dossier_template: ScenarioDraftDossier; compatibility: ScenarioCompatibility;
  revision: number; created_at?: string | null; updated_at?: string | null;
  created_by?: string | null; updated_by?: string | null;
}
export interface ScenarioDraftRecord {
  scenario_id: string; course_id: string; lesson_id: string; title: string;
  scenario_type: ScenarioType; revision: number; updated_at?: string | null; updated_by?: string | null;
}
export interface ScenarioDraftValidationIssue { path: string; code: string; message: string }
export interface ScenarioDraftValidationReport {
  valid: boolean; issues: ScenarioDraftValidationIssue[];
  variable_count: number; npc_count: number; action_count: number;
  event_count: number; ending_count: number;
}
export interface RuntimeScenarioRecord {
  descriptor: RuntimeArtifactDescriptor; title: string; scenario_type: ScenarioType;
  student_role: string; objective: string;
}
export type SealedScenarioTemplate = Record<string, unknown> & {
  scenario_id: string; scenario_version: number; status: 'sealed';
  course_id: string; lesson_id: string; title: string; scenario_type: ScenarioType;
  sealed_at: string; sealed_by: string; checksum: string;
};
export interface ScenarioReleaseSelection {
  scenario_id: string; scenario_version: number; scenario_checksum: string; primary: boolean;
}
export interface LessonScenarioRef {
  scenario_id: string; scenario_version: number; checksum: string; primary: boolean;
}
export interface Lesson {
  id: string; course_id: string; num: string; title: string;
  duration: string; abstract: string; body: string[];
  keywords: Keyword[]; figures: string[];
  sandbox_id: string | null;
  seed_canvas: { id: string; label: string }[];
  unit?: string; era?: string;
  people?: PersonCard[]; map_points?: MapPoint[]; source_refs?: SourceRef[];
  facts?: string[]; qa_points?: string[]; level_goals?: string[];
  saga_material?: MaterialPlaceholder | null; sandbox_material?: MaterialPlaceholder | null;
  content_status?: string; content_version?: number; sealed_at?: string | null; sealed_by?: string | null;
  content_checksum?: string | null;
  release_id?: string | null; release_no?: number | null; release_checksum?: string | null;
  scenario_refs: LessonScenarioRef[]; primary_scenario_id: string | null;
}

export interface LessonPresentation {
  schema_version: 'lesson-presentation/v1'; presentation_id: string;
  course_id: string; lesson_id: string; presentation_version: number;
  status: 'sealed'; title: string; estimated_minutes: number;
  phase_minutes: {
    observe: number; decide: number; consult: number; dossier: number;
  };
  video_path: string; poster_path: string; transcript_path: string;
  video_duration_seconds: number; video_width: 1920; video_height: 1080;
  video_fps: 30; video_sha256: string; poster_sha256: string;
  transcript_sha256: string; skip_allowed: true; accessibility_note: string;
  sealed_at: string; sealed_by: string; checksum: string;
}
export interface LessonPresentationResponse {
  release_id: string; release_no: number; release_checksum: string;
  presentation: LessonPresentation;
  asset_urls: { video: string; poster: string; transcript: string };
}

export type EvidenceWorkflowState =
  | 'draft'
  | 'validated'
  | 'in_review'
  | 'changes_requested'
  | 'approved'
  | 'sealed';
export type EvidenceSourceKind =
  | 'curriculum'
  | 'textbook'
  | 'primary_source'
  | 'archaeology'
  | 'museum'
  | 'research'
  | 'other';
export type EvidenceKind =
  | 'curriculum_goal'
  | 'transmitted_text'
  | 'archaeological_evidence'
  | 'scholarly_interpretation'
  | 'teaching_explanation'
  | 'boundary_note';
export type EvidenceCertainty = 'consensus' | 'interpretation' | 'legend' | 'disputed';
export interface EvidenceSource {
  source_id: string; title: string; kind: EvidenceSourceKind;
  author_or_institution: string; publisher: string; published_year: number | null;
  url_or_path: string; locator: string; citation_note: string;
  reliability: 'reviewed' | 'disputed'; rights_note: string;
}
export interface EvidencePassage {
  passage_id: string; source_id: string; title: string; text: string; summary: string;
  fact_ids: string[]; person_ids: string[]; keywords: string[];
  evidence_kind: EvidenceKind; certainty: EvidenceCertainty;
  chronology_note: string; teaching_note: string;
}
export interface EvidenceDraft {
  schema_version: 'evidence-corpus-draft/v1'; corpus_id: string;
  course_id: string; lesson_id: string; title: string; scope_note: string;
  sources: EvidenceSource[]; passages: EvidencePassage[]; revision: number;
  created_at: string | null; updated_at: string | null;
  created_by: string | null; updated_by: string | null;
}
export interface EvidenceValidationIssue {
  code: string; severity: 'error' | 'warning'; field: string; message: string;
}
export interface EvidenceValidationReport {
  schema_version: 'evidence-validation/v1'; validator_version: string;
  corpus_id: string; course_id: string; lesson_id: string;
  draft_revision: number; draft_fingerprint: string; valid: boolean;
  issues: EvidenceValidationIssue[]; source_count: number; passage_count: number;
  validated_at: string; validated_by: string;
}
export interface EvidenceWorkflowEvent {
  sequence: number; action: string; from_state: EvidenceWorkflowState;
  to_state: EvidenceWorkflowState; actor: string; note: string;
  occurred_at: string; draft_revision: number; draft_fingerprint: string;
  sealed_version: number | null;
}
export interface EvidenceWorkflowRecord {
  schema_version: 'evidence-workflow/v1'; corpus_id: string;
  course_id: string; lesson_id: string; state: EvidenceWorkflowState;
  revision: number; draft_revision: number; draft_fingerprint: string;
  validation: EvidenceValidationReport | null; sealed_version: number | null;
  sealed_checksum: string | null; updated_at: string;
  history: EvidenceWorkflowEvent[]; checksum: string;
}
export interface RuntimeEvidenceRecord {
  descriptor: SupplementArtifactDescriptor; title: string;
  source_count: number; passage_count: number;
}
export interface RuntimePresentationRecord {
  descriptor: SupplementArtifactDescriptor; title: string;
  estimated_minutes: number; video_duration_seconds: number;
}
export interface EvidenceReleaseSelection {
  corpus_id: string; corpus_version: number; corpus_checksum: string;
}
export interface PresentationReleaseSelection {
  presentation_id: string; presentation_version: number; presentation_checksum: string;
}

export type RagPersonaMode = 'expert' | 'person';
export interface RagAskRequest {
  course_id: string; lesson_id: string; persona_mode: RagPersonaMode;
  person_id?: string; question: string;
}
export interface RagCitation {
  citation_id: string; passage_id: string; source_id: string;
  source_title: string; locator: string; excerpt: string;
  relevance: number; certainty: 'consensus' | 'interpretation' | 'legend' | 'disputed';
}
export interface RagAnswer {
  schema_version: 'rag-answer/v1';
  answer_source: 'model' | 'extractive' | 'insufficient_evidence';
  retrieval_mode: 'hybrid' | 'lexical';
  body: string; persona_mode: RagPersonaMode; person_id: string | null;
  role_disclaimer: string | null; citations: RagCitation[];
  retrieved_passage_ids: string[]; course_id: string; lesson_id: string;
  release_id: string; release_no: number; release_checksum: string;
  evidence_corpus_id: string; evidence_version: number; evidence_checksum: string;
  uncertainty: 'low' | 'medium' | 'high';
}

export interface ScenarioReleasePin {
  release_id: string; release_no: number; release_checksum: string;
  course_id: string; lesson_id: string;
  course_content_version: number; course_checksum: string;
  scenario_version: number; scenario_checksum: string;
}
export interface GameScenarioSummary {
  scenario_id: string; scenario_version: number; scenario_checksum: string;
  course_id: string; lesson_id: string; title: string; scenario_type: string;
  student_role: string; objective: string; max_turns: number;
  variables: Array<{
    variable_id: string; label: string; description: string;
    initial: number; minimum: number; maximum: number;
  }>;
  npcs: Array<{
    person_id: string; display_name: string; role: string;
    initial_attitude: number; initial_trust: number;
  }>;
  audience: 'development' | 'published';
  release_id: string | null; release_no: number | null; release_checksum: string | null;
}
export interface GameNarrativeMessage {
  role: 'system' | 'player' | 'narrator'; text: string; turn_no: number;
}
export interface GameNpcState {
  person_id: string; attitude: number; trust: number;
  known_fact_refs: string[]; last_basis_refs: string[];
  flags: Record<string, string | number | boolean>; updated_turn: number;
}
export interface GameStateChange {
  variable_id: string; before: number; after: number; delta: number;
}
export interface GameNpcChange {
  person_id: string; attitude_before: number; attitude_after: number;
  trust_before: number; trust_after: number; revealed_fact_refs: string[];
}
export interface GameTurn {
  turn_id: string; session_id: string; client_action_id: string; turn_no: number;
  status: 'applied' | 'rejected' | 'failed'; raw_input: string;
  action_source: 'fixed' | 'free_input' | 'fallback'; classified_action_id: string;
  state_before: Record<string, number>; state_after: Record<string, number>;
  state_changes: GameStateChange[]; npc_changes: GameNpcChange[];
  triggered_event_ids: string[]; narrative: string; created_at: string;
}
export interface GameSession {
  session_id: string; user_id: string; course_id: string; lesson_id: string;
  scenario_id: string; scenario_version: number;
  course_content_version: number; course_checksum: string; scenario_checksum: string;
  status: 'active' | 'completed' | 'abandoned' | 'failed';
  revision: number; current_turn: number; current_state: Record<string, number>;
  npc_states: GameNpcState[]; turns: GameTurn[]; triggered_event_ids: string[];
  available_action_ids: string[]; available_choices: string[];
  summary: string; history: GameNarrativeMessage[]; ending_id: string | null;
  dossier_id: string | null;
  started_at: string; updated_at: string; ended_at: string | null;
}
export interface GameStartRequest {
  scenario_id: string; client_request_id: string; release_pin?: ScenarioReleasePin;
}
export interface GameStartResponse {
  scenario: GameScenarioSummary; session: GameSession; session_storage: 'sqlite-json';
}
export interface GameTurnResponse {
  session: GameSession;
  turn: { turn_id: string; narrative: string; classified_action_id: string };
  action_feedback: string; triggered_event_ids: string[]; ending_id: string | null;
}
export interface GameAvailableAction {
  action_id: string; label: string; description: string;
}
export interface GameFreeInputResponse {
  schema_version: 'free-input-result/v1';
  kind: 'advanced' | 'clarification_required' | 'rejected' | 'provider_unavailable';
  reason_code: string | null;
  message: string;
  available_actions: GameAvailableAction[];
  result: GameTurnResponse | null;
}
export interface GameDossierChoice {
  turn_id: string; turn_no: number; action_id: string; choice: string; consequence: string;
}
export interface GameDossierStateSnapshot {
  turn_no: number; state: Record<string, number>;
}
export interface GameDossierKnowledgeNode {
  node_id: string; label: string;
  kind: 'person' | 'event' | 'place' | 'concept' | 'cause' | 'consequence';
  summary: string; source_ref_ids: string[];
}
export interface GameDossierKnowledgeEdge {
  edge_id: string; source_node_id: string; target_node_id: string;
  relation: string; explanation: string; source_ref_ids: string[];
}
export interface GameDossier {
  schema_version: 'dossier/v1'; dossier_id: string; session_id: string; user_id: string;
  course_id: string; lesson_id: string; scenario_id: string;
  course_content_version: number; scenario_version: number;
  course_checksum: string; scenario_checksum: string; status: 'draft' | 'final';
  title: string; ending_id: string; strategy_summary: string;
  key_choices: GameDossierChoice[]; state_trajectory: GameDossierStateSnapshot[];
  major_costs: string[]; historical_explanation: string;
  knowledge_nodes: GameDossierKnowledgeNode[]; knowledge_edges: GameDossierKnowledgeEdge[];
  follow_up_questions: string[]; reflection_notes: string[];
  fact_refs: string[]; source_ref_ids: string[]; generated_at: string; checksum: string | null;
}
export interface CanvasPayload {
  nodes: unknown[]; edges: unknown[];
}
export interface CanvasDocument extends CanvasPayload {
  schema_version: 'canvas/v1'; found: boolean; revision: number;
}
export interface CanvasSaveRequest extends CanvasPayload {
  expected_revision: number;
}
export interface CanvasGeneratedNode {
  id: string; label: string; category?: string;
}
export interface CanvasGeneratedEdge {
  from: string; to: string; label?: string;
}
export interface CanvasGeneratedGraph {
  nodes: CanvasGeneratedNode[]; edges: CanvasGeneratedEdge[];
}

export type LearningCompletionStatus = 'in_review' | 'changes_requested' | 'completed';
export interface LearningStickyNote {
  note_id: string; body: string; color: 'ochre' | 'jade' | 'cinnabar';
}
export interface LearningDrawingStroke {
  stroke_id: string; color: string; width: number; mode: 'ink' | 'erase';
  points: Array<{ x: number; y: number }>;
}
export interface LearningEventSnapshot {
  event_id: string;
  kind: 'stage_entered' | 'keyword_opened' | 'decision_completed' | 'question_answered' | 'temporary_note_saved';
  title: string; summary: string;
  metadata?: Record<string, string | number | boolean | null>;
  occurred_at: string;
}
export interface LearningCanvasSnapshot {
  schema_version: 'learning-canvas-snapshot/v1'; found: boolean; revision: number;
  nodes: unknown[]; edges: unknown[];
}
export interface LearningSubmissionRequest {
  schema_version: 'learning-submission-request/v1';
  client_submission_id: string; course_id: string; lesson_id: string;
  title: string; body_markdown: string;
  sticky_notes: LearningStickyNote[]; drawing_strokes: LearningDrawingStroke[];
  learning_events: LearningEventSnapshot[]; local_draft_updated_at: string;
}
export interface LearningSubmission {
  schema_version: 'learning-submission/v1';
  submission_id: string; client_submission_id: string; student_id: string;
  course_id: string; lesson_id: string; version: number; title: string;
  body_markdown: string; sticky_notes: LearningStickyNote[];
  drawing_strokes: LearningDrawingStroke[]; learning_events: LearningEventSnapshot[];
  canvas: LearningCanvasSnapshot; local_draft_updated_at: string; submitted_at: string;
  source_payload_checksum: string; checksum: string;
}
export interface LearningFeedback {
  schema_version: 'learning-feedback/v1'; feedback_id: string;
  client_feedback_id: string; submission_id: string; sequence: number;
  teacher_id: string; teacher_display_name: string;
  completion_status: LearningCompletionStatus; comment: string;
  created_at: string; source_payload_checksum: string; checksum: string;
}
export interface LearningSubmissionListItem {
  submission_id: string; student_id: string; student_display_name: string;
  student_username?: string | null; course_id: string; lesson_id: string;
  version: number; title: string; body_excerpt: string;
  sticky_note_count: number; stroke_count: number; event_count: number;
  canvas_node_count: number; submitted_at: string; checksum: string;
  latest_feedback?: LearningFeedback | null;
}
export interface LearningSubmissionDetail {
  submission: LearningSubmission; student_display_name: string;
  student_username?: string | null; feedback: LearningFeedback[];
}
export interface LearningFeedbackRequest {
  schema_version: 'learning-feedback-request/v1'; client_feedback_id: string;
  completion_status: LearningCompletionStatus; comment: string;
}

function learningSubmissionQuery(params: {
  student_id?: string; course_id?: string; lesson_id?: string; limit?: number;
}): string {
  const query = new URLSearchParams();
  if (params.student_id) query.set('student_id', params.student_id);
  if (params.course_id) query.set('course_id', params.course_id);
  if (params.lesson_id) query.set('lesson_id', params.lesson_id);
  if (params.limit) query.set('limit', String(params.limit));
  const rendered = query.toString();
  return rendered ? `?${rendered}` : '';
}

export const api = {
  eras: () => jsonFetch<{ items: Era[] }>('/courses/eras'),
  courses: (params: { era?: string; section?: string; q?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.era && params.era !== 'all') qs.set('era', params.era);
    if (params.section && params.section !== 'all') qs.set('section', params.section);
    if (params.q) qs.set('q', params.q);
    const s = qs.toString();
    return jsonFetch<{ items: CourseSummary[]; total: number }>(`/courses/${s ? '?' + s : ''}`);
  },
  course: (id: string) => jsonFetch<CourseDetail>(`/courses/${id}`),
  lesson: (cid: string, lid: string) => jsonFetch<Lesson>(`/courses/${cid}/lessons/${lid}`),
  lessonPresentation: (cid: string, lid: string) =>
    jsonFetch<LessonPresentationResponse>(
      `/courses/${encodeURIComponent(cid)}/lessons/${encodeURIComponent(lid)}/presentation`,
    ),
  ragAsk: (body: RagAskRequest) => jsonFetch<RagAnswer>('/practice/ask/rag', {
    method: 'POST', body: JSON.stringify(body),
  }),
  gameStart: (body: GameStartRequest) =>
    jsonFetch<GameStartResponse>('/practice/game/sessions', {
      method: 'POST', body: JSON.stringify(body),
    }),
  gameSession: (sessionId: string) =>
    jsonFetch<GameSession>(`/practice/game/sessions/${encodeURIComponent(sessionId)}`),
  gameTurn: (
    sessionId: string,
    body: {
      client_action_id: string; action_id: string; expected_revision: number;
    },
  ) => jsonFetch<GameTurnResponse>(
    `/practice/game/sessions/${encodeURIComponent(sessionId)}/turns`,
    { method: 'POST', body: JSON.stringify(body) },
  ),
  gameFreeInput: (
    sessionId: string,
    body: { client_action_id: string; raw_input: string; expected_revision: number },
  ) => jsonFetch<GameFreeInputResponse>(
    `/practice/game/sessions/${encodeURIComponent(sessionId)}/free-input`,
    { method: 'POST', body: JSON.stringify(body) },
  ),
  gameDossier: (sessionId: string) =>
    jsonFetch<GameDossier>(
      `/practice/game/sessions/${encodeURIComponent(sessionId)}/dossier`,
    ),
  llmInfo: () => jsonFetch<{ provider: string; ask_provider?: string }>('/practice/llm/info'),
  sandboxGet: (sid: string) => jsonFetch<any>(`/practice/sandbox/${sid}`),
  sandboxStep: (sid: string, body: { node_id: string; choice: string; state: Record<string, number> }) =>
    jsonFetch<any>(`/practice/sandbox/${sid}/step`, { method: 'POST', body: JSON.stringify(body) }),
  canvasGet: (lid: string) => jsonFetch<CanvasDocument>(`/practice/canvas/${lid}`),
  canvasSave: (lid: string, payload: CanvasSaveRequest) =>
    jsonFetch<CanvasDocument>(`/practice/canvas/${lid}`, { method: 'PUT', body: JSON.stringify(payload) }),
  canvasGenerate: (body: { lesson_id: string; lesson_title: string; abstract: string; keywords: string[]; seed: string[] }) =>
    jsonFetch<CanvasGeneratedGraph>(`/practice/canvas/generate`, { method: 'POST', body: JSON.stringify(body) }),
  sagaTemplates: () => jsonFetch<{ items: SagaTemplate[] }>(`/practice/saga/templates`),
  sagaStart: (lesson_id: string) => jsonFetch<SagaState>(`/practice/saga/start`, { method: 'POST', body: JSON.stringify({ lesson_id }) }),
  sagaGet: (saga_id: string) => jsonFetch<SagaState>(`/practice/saga/${saga_id}`),
  progressList: () => jsonFetch<{ items: ProgressItem[] }>(`/learning/progress`),
  progressLatest: () => jsonFetch<{ item: ProgressItem | null }>(`/learning/progress/latest`),
  progressGet: (lesson_id: string) => jsonFetch<{ item: ProgressItem | null }>(`/learning/progress/${lesson_id}`),
  progressTouch: (body: { lesson_id: string; layer: string; completed?: boolean }) =>
    jsonFetch<{ ok: boolean; item: ProgressItem }>(`/learning/progress/touch`, { method: 'POST', body: JSON.stringify(body) }),
  learningSubmissions: (params: { course_id?: string; lesson_id?: string; limit?: number } = {}) =>
    jsonFetch<{ items: LearningSubmissionListItem[] }>(
      `/learning/submissions${learningSubmissionQuery(params)}`,
    ),
  learningSubmission: (submissionId: string) =>
    jsonFetch<LearningSubmissionDetail>(
      `/learning/submissions/${encodeURIComponent(submissionId)}`,
    ),
  learningSubmit: (body: LearningSubmissionRequest) =>
    jsonFetch<{ submission: LearningSubmission; reused: boolean }>(
      '/learning/submissions',
      { method: 'POST', body: JSON.stringify(body) },
    ),
  learningReviewSubmissions: (params: {
    student_id?: string; course_id?: string; lesson_id?: string; limit?: number;
  } = {}) => jsonFetch<{ items: LearningSubmissionListItem[] }>(
    `/learning/review/submissions${learningSubmissionQuery(params)}`,
  ),
  learningReviewSubmission: (submissionId: string) =>
    jsonFetch<LearningSubmissionDetail>(
      `/learning/review/submissions/${encodeURIComponent(submissionId)}`,
    ),
  learningReviewFeedback: (submissionId: string, body: LearningFeedbackRequest) =>
    jsonFetch<{ feedback: LearningFeedback; reused: boolean }>(
      `/learning/review/submissions/${encodeURIComponent(submissionId)}/feedback`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  adminContentTemplate: (token: string) => adminFetch<LessonContentPackage>(token, '/admin/content/template'),
  adminContentSourceLessons: (token: string) => adminFetch<{ items: LessonSourceRecord[] }>(token, '/admin/content/source-lessons'),
  adminContentSourceLesson: (token: string, lesson_id: string) =>
    adminFetch<LessonContentPackage>(token, `/admin/content/source-lessons/${lesson_id}`),
  adminContentDrafts: (token: string) => adminFetch<{ items: ContentFileRecord[] }>(token, '/admin/content/drafts'),
  adminContentDraft: (token: string, lesson_id: string) =>
    adminFetch<LessonContentPackage>(token, `/admin/content/drafts/${lesson_id}`),
  adminContentPreview: (token: string, body: LessonContentPackage) =>
    adminFetch<{ item: LessonContentPackage }>(token, '/admin/content/preview', { method: 'POST', body: JSON.stringify(body) }),
  adminContentSaveDraft: (token: string, body: LessonContentPackage) =>
    adminFetch<{ item: LessonContentPackage; workflow: ContentWorkflowRecord }>(
      token,
      '/admin/content/drafts',
      { method: 'POST', body: JSON.stringify(body) },
    ),
  adminContentWorkflow: (token: string, lesson_id: string) =>
    adminFetch<WorkflowResponse>(token, `/admin/content/drafts/${lesson_id}/workflow`),
  adminContentValidate: (token: string, lesson_id: string) =>
    adminFetch<WorkflowResponse>(token, `/admin/content/drafts/${lesson_id}/validate`, {
      method: 'POST', body: JSON.stringify({}),
    }),
  adminContentSubmitReview: (token: string, lesson_id: string, note: string) =>
    adminFetch<WorkflowResponse>(token, `/admin/content/drafts/${lesson_id}/submit-review`, {
      method: 'POST', body: JSON.stringify({ note }),
    }),
  adminContentReview: (
    token: string,
    lesson_id: string,
    decision: 'approve' | 'changes_requested',
    note: string,
  ) => adminFetch<WorkflowResponse>(token, `/admin/content/drafts/${lesson_id}/review`, {
    method: 'POST', body: JSON.stringify({ decision, note }),
  }),
  adminContentSeal: (token: string, lesson_id: string) =>
    adminFetch<{
      item: LessonContentPackage;
      record: { path: string };
      workflow: ContentWorkflowRecord;
    }>(
      token,
      `/admin/content/drafts/${lesson_id}/seal`,
      { method: 'POST', body: JSON.stringify({}) },
    ),
  adminContentPublish: (
    token: string,
    lesson_id: string,
    version: number,
    note: string,
    scenarios?: ScenarioReleaseSelection[] | null,
    evidence?: EvidenceReleaseSelection | null,
    presentation?: PresentationReleaseSelection | null,
  ) => adminFetch<ReleaseResponse>(
    token,
    `/admin/content/sealed/${lesson_id}/versions/${version}/publish`,
    {
      method: 'POST',
      body: JSON.stringify({
        note,
        ...(scenarios === undefined ? {} : { scenarios }),
        ...(evidence === undefined ? {} : { evidence }),
        ...(presentation === undefined ? {} : { presentation }),
      }),
    },
  ),
  adminContentReleases: (token: string, course_id: string) =>
    adminFetch<{ items: CourseReleaseManifest[] }>(
      token,
      `/admin/content/releases?course_id=${encodeURIComponent(course_id)}`,
    ),
  adminContentCurrentRelease: (token: string, course_id: string) =>
    adminFetch<ReleaseResponse>(token, `/admin/content/releases/${course_id}/current`),
  adminContentArchivePreview: (
    token: string,
    course_id: string,
    release_id: string,
  ) => adminFetch<{ archive: CourseArchiveManifest; download_url: string }>(
    token,
    `/admin/content/releases/${encodeURIComponent(course_id)}`
      + `/${encodeURIComponent(release_id)}/archive-preview`,
    { method: 'POST' },
  ),
  adminContentArchiveFile: (
    token: string,
    course_id: string,
    release_id: string,
  ) => adminFile(
    token,
    `/admin/content/releases/${encodeURIComponent(course_id)}`
      + `/${encodeURIComponent(release_id)}/archive.zip`,
  ),
  adminContentPublications: (
    token: string,
    filters?: {
      course_id?: string;
      release_id?: string;
      publication_status?: PublicationStatus;
    },
  ) => {
    const query = new URLSearchParams();
    if (filters?.course_id) query.set('course_id', filters.course_id);
    if (filters?.release_id) query.set('release_id', filters.release_id);
    if (filters?.publication_status) {
      query.set('publication_status', filters.publication_status);
    }
    const suffix = query.size ? `?${query.toString()}` : '';
    return adminFetch<{ items: GitPublicationRecord[] }>(
      token,
      `/admin/content/publications${suffix}`,
    );
  },
  adminContentPublication: (token: string, publication_id: string) =>
    adminFetch<PublicationResponse>(
      token,
      `/admin/content/publications/${encodeURIComponent(publication_id)}`,
    ),
  adminCreateContentPublication: (
    token: string,
    body: CourseArchivePublishRequest,
  ) => adminFetch<PublicationResponse>(token, '/admin/content/publications', {
    method: 'POST',
    body: JSON.stringify(body),
  }),
  adminRetryContentPublication: (
    token: string,
    publication_id: string,
    expected_revision: number,
  ) => adminFetch<PublicationResponse>(
    token,
    `/admin/content/publications/${encodeURIComponent(publication_id)}/retry`,
    {
      method: 'POST',
      body: JSON.stringify({ expected_revision }),
    },
  ),
  adminContentRollback: (
    token: string,
    course_id: string,
    target_release_id: string,
    note: string,
  ) => adminFetch<ReleaseResponse>(token, `/admin/content/releases/${course_id}/rollback`, {
    method: 'POST', body: JSON.stringify({ note, target_release_id }),
  }),
  adminContentAssets: (token: string, kind?: 'person' | 'keyword') =>
    adminFetch<{ items: ContentAssetRecord[] }>(token, `/admin/content/assets${kind ? `?kind=${kind}` : ''}`),
  adminPersonTemplate: (token: string) => adminFetch<PersonProfilePackage>(token, '/admin/content/assets/people/template'),
  adminPersonAsset: (token: string, asset_id: string) =>
    adminFetch<PersonProfilePackage>(token, `/admin/content/assets/people/${encodeURIComponent(asset_id)}`),
  adminSavePersonAsset: (token: string, body: PersonProfilePackage) =>
    adminFetch<{ item: PersonProfilePackage }>(token, '/admin/content/assets/people', { method: 'POST', body: JSON.stringify(body) }),
  adminValidatePersonAsset: (token: string, asset_id: string) =>
    adminFetch<{ report: ContentAssetValidationReport }>(
      token,
      `/admin/content/assets/people/${encodeURIComponent(asset_id)}/validate`,
      { method: 'POST' },
    ),
  adminSealPersonAsset: (token: string, asset_id: string) =>
    adminFetch<{
      item: PersonProfilePackage; record: ContentAssetRecord; idempotent: boolean;
    }>(
      token,
      `/admin/content/assets/people/${encodeURIComponent(asset_id)}/seal`,
      { method: 'POST' },
    ),
  adminPersonAssetVersions: (token: string, asset_id: string) =>
    adminFetch<{ items: ContentAssetRecord[] }>(
      token,
      `/admin/content/assets/people/${encodeURIComponent(asset_id)}/versions`,
    ),
  adminPersonAssetVersion: (token: string, asset_id: string, version: number) =>
    adminFetch<PersonProfilePackage>(
      token,
      `/admin/content/assets/people/${encodeURIComponent(asset_id)}/versions/${version}`,
    ),
  adminKeywordTemplate: (token: string) => adminFetch<KeywordProfilePackage>(token, '/admin/content/assets/keywords/template'),
  adminKeywordAsset: (token: string, asset_id: string) =>
    adminFetch<KeywordProfilePackage>(token, `/admin/content/assets/keywords/${encodeURIComponent(asset_id)}`),
  adminSaveKeywordAsset: (token: string, body: KeywordProfilePackage) =>
    adminFetch<{ item: KeywordProfilePackage }>(token, '/admin/content/assets/keywords', { method: 'POST', body: JSON.stringify(body) }),
  adminValidateKeywordAsset: (token: string, asset_id: string) =>
    adminFetch<{ report: ContentAssetValidationReport }>(
      token,
      `/admin/content/assets/keywords/${encodeURIComponent(asset_id)}/validate`,
      { method: 'POST' },
    ),
  adminSealKeywordAsset: (token: string, asset_id: string) =>
    adminFetch<{
      item: KeywordProfilePackage; record: ContentAssetRecord; idempotent: boolean;
    }>(
      token,
      `/admin/content/assets/keywords/${encodeURIComponent(asset_id)}/seal`,
      { method: 'POST' },
    ),
  adminKeywordAssetVersions: (token: string, asset_id: string) =>
    adminFetch<{ items: ContentAssetRecord[] }>(
      token,
      `/admin/content/assets/keywords/${encodeURIComponent(asset_id)}/versions`,
    ),
  adminKeywordAssetVersion: (token: string, asset_id: string, version: number) =>
    adminFetch<KeywordProfilePackage>(
      token,
      `/admin/content/assets/keywords/${encodeURIComponent(asset_id)}/versions/${version}`,
    ),
  adminContentAssetArchivePreview: (
    token: string,
    asset_kind: ContentAssetKind,
    asset_id: string,
    version: number,
    source_checksum: string,
  ) => {
    const query = new URLSearchParams({ source_checksum });
    return adminFetch<{ archive: ContentAssetArchiveManifest; download_url: string }>(
      token,
      `/admin/content/asset-archives/${asset_kind}/${encodeURIComponent(asset_id)}`
        + `/versions/${version}/preview?${query.toString()}`,
      { method: 'POST' },
    );
  },
  adminContentAssetArchiveFile: (
    token: string,
    asset_kind: ContentAssetKind,
    asset_id: string,
    version: number,
    source_checksum: string,
  ) => {
    const query = new URLSearchParams({ source_checksum });
    return adminFile(
      token,
      `/admin/content/asset-archives/${asset_kind}/${encodeURIComponent(asset_id)}`
        + `/versions/${version}/archive.zip?${query.toString()}`,
    );
  },
  adminContentAssetPublications: (
    token: string,
    filters?: {
      asset_kind?: ContentAssetKind;
      asset_id?: string;
      asset_version?: number;
      publication_status?: PublicationStatus;
    },
  ) => {
    const query = new URLSearchParams();
    if (filters?.asset_kind) query.set('asset_kind', filters.asset_kind);
    if (filters?.asset_id) query.set('asset_id', filters.asset_id);
    if (filters?.asset_version !== undefined) {
      query.set('asset_version', String(filters.asset_version));
    }
    if (filters?.publication_status) {
      query.set('publication_status', filters.publication_status);
    }
    const suffix = query.size ? `?${query.toString()}` : '';
    return adminFetch<{ items: AssetGitPublicationRecord[] }>(
      token,
      `/admin/content/asset-publications${suffix}`,
    );
  },
  adminContentAssetPublication: (token: string, publication_id: string) =>
    adminFetch<AssetPublicationResponse>(
      token,
      `/admin/content/asset-publications/${encodeURIComponent(publication_id)}`,
    ),
  adminCreateContentAssetPublication: (
    token: string,
    body: ContentAssetArchivePublishRequest,
  ) => adminFetch<AssetPublicationResponse>(token, '/admin/content/asset-publications', {
    method: 'POST',
    body: JSON.stringify(body),
  }),
  adminRetryContentAssetPublication: (
    token: string,
    publication_id: string,
    expected_revision: number,
  ) => adminFetch<AssetPublicationResponse>(
    token,
    `/admin/content/asset-publications/${encodeURIComponent(publication_id)}/retry`,
    {
      method: 'POST',
      body: JSON.stringify({ expected_revision }),
    },
  ),
  adminEvidenceDrafts: (token: string) =>
    adminFetch<{ items: EvidenceDraft[] }>(token, '/admin/content/evidence-drafts'),
  adminEvidenceDraft: (token: string, corpus_id: string) =>
    adminFetch<{ item: EvidenceDraft; workflow: EvidenceWorkflowRecord | null }>(
      token,
      `/admin/content/evidence-drafts/${encodeURIComponent(corpus_id)}`,
    ),
  adminSaveEvidenceDraft: (token: string, body: EvidenceDraft) =>
    adminFetch<{ item: EvidenceDraft; workflow: EvidenceWorkflowRecord }>(
      token,
      '/admin/content/evidence-drafts',
      { method: 'POST', body: JSON.stringify(body) },
    ),
  adminUpdateEvidenceDraft: (token: string, body: EvidenceDraft) =>
    adminFetch<{ item: EvidenceDraft; workflow: EvidenceWorkflowRecord }>(
      token,
      `/admin/content/evidence-drafts/${encodeURIComponent(body.corpus_id)}`,
      { method: 'PUT', body: JSON.stringify(body) },
    ),
  adminValidateEvidenceDraft: (token: string, corpus_id: string) =>
    adminFetch<{ workflow: EvidenceWorkflowRecord; report: EvidenceValidationReport | null }>(
      token,
      `/admin/content/evidence-drafts/${encodeURIComponent(corpus_id)}/validate`,
      { method: 'POST', body: JSON.stringify({}) },
    ),
  adminSubmitEvidenceReview: (token: string, corpus_id: string, note: string) =>
    adminFetch<{ workflow: EvidenceWorkflowRecord; report: EvidenceValidationReport | null }>(
      token,
      `/admin/content/evidence-drafts/${encodeURIComponent(corpus_id)}/submit-review`,
      { method: 'POST', body: JSON.stringify({ note }) },
    ),
  adminReviewEvidenceDraft: (
    token: string,
    corpus_id: string,
    decision: 'approve' | 'changes_requested',
    note: string,
  ) => adminFetch<{ workflow: EvidenceWorkflowRecord; report: EvidenceValidationReport | null }>(
    token,
    `/admin/content/evidence-drafts/${encodeURIComponent(corpus_id)}/review`,
    { method: 'POST', body: JSON.stringify({ decision, note }) },
  ),
  adminSealEvidenceDraft: (token: string, corpus_id: string) =>
    adminFetch<{
      item: Record<string, unknown>; record: RuntimeEvidenceRecord;
      workflow: EvidenceWorkflowRecord; idempotent: boolean;
    }>(
      token,
      `/admin/content/evidence-drafts/${encodeURIComponent(corpus_id)}/seal`,
      { method: 'POST', body: JSON.stringify({}) },
    ),
  adminRuntimeEvidence: (token: string) =>
    adminFetch<{ items: RuntimeEvidenceRecord[] }>(token, '/admin/content/runtime-evidence'),
  adminLessonPresentations: (token: string) =>
    adminFetch<{ items: RuntimePresentationRecord[] }>(
      token,
      '/admin/content/lesson-presentations',
    ),
  adminStageLessonPresentation: (token: string, body: LessonPresentation) =>
    adminFetch<{ record: RuntimePresentationRecord }>(
      token,
      '/admin/content/lesson-presentations',
      { method: 'POST', body: JSON.stringify(body) },
    ),
  adminScenarioTemplate: (token: string) =>
    adminFetch<ScenarioAuthorDraft>(token, '/admin/content/scenario-drafts/template'),
  adminScenarioDrafts: (token: string) =>
    adminFetch<{ items: ScenarioDraftRecord[] }>(token, '/admin/content/scenario-drafts'),
  adminScenarioDraft: (token: string, scenario_id: string) =>
    adminFetch<ScenarioAuthorDraft>(token, `/admin/content/scenario-drafts/${encodeURIComponent(scenario_id)}`),
  adminSaveScenarioDraft: (token: string, body: ScenarioAuthorDraft) =>
    adminFetch<{ item: ScenarioAuthorDraft }>(token, '/admin/content/scenario-drafts', {
      method: 'POST', body: JSON.stringify(body),
    }),
  adminValidateScenarioDraft: (token: string, scenario_id: string) =>
    adminFetch<{ report: ScenarioDraftValidationReport }>(
      token,
      `/admin/content/scenario-drafts/${encodeURIComponent(scenario_id)}/validate`,
      { method: 'POST' },
    ),
  adminSealScenarioDraft: (token: string, scenario_id: string) =>
    adminFetch<{
      item: SealedScenarioTemplate; record: RuntimeScenarioRecord; idempotent: boolean;
    }>(
      token,
      `/admin/content/scenario-drafts/${encodeURIComponent(scenario_id)}/seal`,
      { method: 'POST' },
    ),
  adminRuntimeScenarios: (token: string) =>
    adminFetch<{ items: RuntimeScenarioRecord[] }>(token, '/admin/content/runtime-scenarios'),
  adminRuntimeScenario: (token: string, descriptor: RuntimeArtifactDescriptor) => {
    const query = new URLSearchParams({
      course_id: descriptor.course_id,
      lesson_id: descriptor.lesson_id,
      scenario_checksum: descriptor.checksum,
    });
    return adminFetch<{ item: SealedScenarioTemplate; descriptor: RuntimeArtifactDescriptor }>(
      token,
      `/admin/content/runtime-scenarios/${encodeURIComponent(descriptor.artifact_id)}`
        + `/versions/${descriptor.version}?${query.toString()}`,
    );
  },
  adminRuntimeScenarioFile: (token: string, descriptor: RuntimeArtifactDescriptor) => {
    const query = new URLSearchParams({
      course_id: descriptor.course_id,
      lesson_id: descriptor.lesson_id,
      scenario_checksum: descriptor.checksum,
    });
    return adminFile(
      token,
      `/admin/content/runtime-scenarios/${encodeURIComponent(descriptor.artifact_id)}`
        + `/versions/${descriptor.version}/file?${query.toString()}`,
    );
  },
};

export interface ProgressItem {
  lesson_id: string;
  course_id?: string;
  title?: string;
  last_layer: string;
  layers: { watch: boolean; practice: boolean; ask: boolean; create: boolean };
  updated_at: string;
}

export interface SagaTemplate {
  lesson_id: string; title: string; era: string; persona: string; keywords: string[];
}
export interface SagaEntity { name: string; type: string; desc: string }
export interface SagaState {
  saga_id: string; lesson_id: string; title: string; era: string; persona: string;
  history: { role: 'narrator' | 'player'; text: string }[];
  summary: string; choices: string[]; flags: Record<string, any>;
  entities: SagaEntity[]; step: number; ended: boolean; keywords: string[];
}

// Saga · 流式行动（与 streamAsk 同形式；末尾会出现 \n\n[META]{...json...}）
export async function streamSagaAct(
  saga_id: string,
  action: string,
  onChunk: (text: string) => void,
): Promise<void> {
  const r = await fetch(BASE + `/practice/saga/${saga_id}/act`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  });
  if (!r.ok || !r.body) {
    onChunk(`[请求失败 ${r.status}]`);
    return;
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder('utf-8');
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    if (value) onChunk(decoder.decode(value, { stream: true }));
  }
}

// 流式聊天（手动读 ReadableStream）
export async function streamAsk(
  body: {
    user_message: string;
    persona?: 'expert' | 'peer';
    lesson_id?: string;
    lesson_title?: string;
    peer_character?: string;
    peer_intro?: string;
    era?: string;
    history?: { role: 'user' | 'assistant'; content: string }[];
  },
  onChunk: (text: string) => void,
): Promise<void> {
  const r = await fetch(BASE + '/practice/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok || !r.body) {
    onChunk(`[请求失败 ${r.status}]`);
    return;
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder('utf-8');
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    if (value) onChunk(decoder.decode(value, { stream: true }));
  }
}
