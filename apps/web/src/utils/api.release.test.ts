import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  api,
  COOKIE_AUTH_CREDENTIAL,
  evidenceReleaseSelectionFromDescriptor,
  type EvidenceReleaseSelectionV1,
  type EvidenceSupplementDescriptorV1,
  type EvidenceSupplementDescriptorV2,
} from './api';


function installFetchRecorder() {
  const fetchMock = vi.fn(async (
    _input: RequestInfo | URL,
    _init?: RequestInit,
  ) => new Response(JSON.stringify({ release: {} }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  }));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}


function publishBody(fetchMock: ReturnType<typeof installFetchRecorder>) {
  const init = fetchMock.mock.calls[0]?.[1];
  if (!init?.body) throw new Error('publish request did not contain a body');
  return JSON.parse(String(init.body)) as {
    note: string;
    evidence?: Record<string, unknown>;
  };
}


describe('evidence release publication compatibility', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('keeps the omitted schema version compatible with the V1 backend default', async () => {
    const fetchMock = installFetchRecorder();
    const legacyV1Selection: EvidenceReleaseSelectionV1 = {
      corpus_id: 'shangyang-evidence',
      corpus_version: 1,
      corpus_checksum: '1'.repeat(64),
    };

    await api.adminContentPublish(
      COOKIE_AUTH_CREDENTIAL,
      'L103',
      1,
      'legacy V1 publication',
      undefined,
      legacyV1Selection,
    );

    expect(publishBody(fetchMock).evidence).toEqual({
      corpus_id: 'shangyang-evidence',
      corpus_version: 1,
      corpus_checksum: '1'.repeat(64),
    });
  });

  it('copies a selected runtime V2 descriptor schema into the publish request', async () => {
    const fetchMock = installFetchRecorder();
    const descriptor: EvidenceSupplementDescriptorV2 = {
      kind: 'evidence-corpus',
      schema_version: 'evidence-corpus/v2',
      artifact_id: 'shangyang-evidence',
      course_id: 'C-prequin-state',
      lesson_id: 'L103',
      version: 2,
      checksum: '2'.repeat(64),
      path: 'runtime/v2/evidence/example.json',
    };
    const selection = evidenceReleaseSelectionFromDescriptor(descriptor);

    await api.adminContentPublish(
      COOKIE_AUTH_CREDENTIAL,
      'L103',
      2,
      'V2 publication',
      undefined,
      selection,
    );

    expect(publishBody(fetchMock).evidence).toEqual({
      corpus_id: 'shangyang-evidence',
      corpus_version: 2,
      corpus_checksum: '2'.repeat(64),
      schema_version: 'evidence-corpus/v2',
    });
  });

  it('preserves an explicitly selected V1 runtime descriptor as V1', () => {
    const descriptor: EvidenceSupplementDescriptorV1 = {
      kind: 'evidence-corpus',
      schema_version: 'evidence-corpus/v1',
      artifact_id: 'shangyang-evidence',
      course_id: 'C-prequin-state',
      lesson_id: 'L103',
      version: 1,
      checksum: '3'.repeat(64),
      path: 'runtime/v1/evidence/example.json',
    };

    expect(evidenceReleaseSelectionFromDescriptor(descriptor)).toEqual({
      corpus_id: 'shangyang-evidence',
      corpus_version: 1,
      corpus_checksum: '3'.repeat(64),
      schema_version: 'evidence-corpus/v1',
    });
  });
});
