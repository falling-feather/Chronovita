import type {
  LearningEventSnapshot,
  LearningSubmissionRequest,
} from '../../utils/api';
import type {
  LearningDeskDraftRecord,
  LearningEventRecord,
  LearningScopeIdentity,
} from './learningLedger';

const PENDING_SUBMISSION_SCHEMA = 'pending-learning-submission/v1' as const;

export interface SubmissionStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

interface PendingSubmissionEnvelope {
  schema_version: typeof PENDING_SUBMISSION_SCHEMA;
  owner_id: string;
  request: LearningSubmissionRequest;
  frozen_at: string;
}

const safePart = (value: string) => encodeURIComponent(value.trim() || '_');

export function pendingSubmissionStorageKey(identity: LearningScopeIdentity): string {
  return [
    'chronovita.learning.pending-submission.v1',
    safePart(identity.ownerId),
    safePart(identity.courseId),
    safePart(identity.lessonId),
  ].join('.');
}

export function createClientSubmissionId(): string {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
  return `submit-${suffix}`.slice(0, 64);
}

export function createClientFeedbackId(): string {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
  return `feedback-${suffix}`.slice(0, 64);
}

function eventSnapshot(event: LearningEventRecord): LearningEventSnapshot {
  return {
    event_id: event.event_id,
    kind: event.kind,
    title: event.title,
    summary: event.summary,
    metadata: event.metadata ?? {},
    occurred_at: event.occurred_at,
  };
}

export function buildLearningSubmissionRequest(
  draft: LearningDeskDraftRecord,
  events: LearningEventRecord[],
  clientSubmissionId = createClientSubmissionId(),
): LearningSubmissionRequest {
  return {
    schema_version: 'learning-submission-request/v1',
    client_submission_id: clientSubmissionId,
    course_id: draft.course_id,
    lesson_id: draft.lesson_id,
    title: draft.title || '我的历史学习书案',
    body_markdown: draft.body_markdown,
    sticky_notes: draft.sticky_notes,
    drawing_strokes: draft.drawing_strokes,
    learning_events: events.slice(-240).map(eventSnapshot),
    local_draft_updated_at: draft.updated_at,
  };
}

export function writePendingSubmission(
  storage: SubmissionStorage,
  identity: LearningScopeIdentity,
  request: LearningSubmissionRequest,
  frozenAt = new Date().toISOString(),
): void {
  if (request.course_id !== identity.courseId || request.lesson_id !== identity.lessonId) {
    throw new Error('Pending learning submission scope does not match the active lesson.');
  }
  const envelope: PendingSubmissionEnvelope = {
    schema_version: PENDING_SUBMISSION_SCHEMA,
    owner_id: identity.ownerId,
    request,
    frozen_at: frozenAt,
  };
  storage.setItem(pendingSubmissionStorageKey(identity), JSON.stringify(envelope));
}

export function readPendingSubmission(
  storage: SubmissionStorage,
  identity: LearningScopeIdentity,
): LearningSubmissionRequest | null {
  try {
    const raw = storage.getItem(pendingSubmissionStorageKey(identity));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<PendingSubmissionEnvelope>;
    const request = parsed.request;
    if (
      parsed.schema_version !== PENDING_SUBMISSION_SCHEMA
      || parsed.owner_id !== identity.ownerId
      || !request
      || request.schema_version !== 'learning-submission-request/v1'
      || request.course_id !== identity.courseId
      || request.lesson_id !== identity.lessonId
      || typeof request.client_submission_id !== 'string'
      || typeof request.local_draft_updated_at !== 'string'
      || !Array.isArray(request.sticky_notes)
      || !Array.isArray(request.drawing_strokes)
      || !Array.isArray(request.learning_events)
    ) {
      return null;
    }
    return request;
  } catch {
    return null;
  }
}

export function clearPendingSubmission(
  storage: SubmissionStorage,
  identity: LearningScopeIdentity,
): void {
  storage.removeItem(pendingSubmissionStorageKey(identity));
}
