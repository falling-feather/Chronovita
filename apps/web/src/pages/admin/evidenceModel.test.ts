import { describe, expect, it } from 'vitest';
import type { EvidenceDraft, LessonContentPackage } from '../../utils/api';
import {
  createEvidenceDraft,
  createEvidencePassage,
  createEvidenceSource,
  createLessonPresentation,
  lessonEvidenceBindings,
  normalizeEvidenceDraft,
  signLessonPresentation,
} from './evidenceModel';

describe('evidence authoring model', () => {
  it('normalizes stable identities and passage bindings before a CAS save', () => {
    const sourceA = { ...createEvidenceSource(1), source_id: 'source-z' };
    const sourceB = { ...createEvidenceSource(2), source_id: 'source-a' };
    const passage = {
      ...createEvidencePassage(1, 'source-a'),
      fact_ids: ['fact-z', 'fact-a', 'fact-z'],
      person_ids: ['person-b', 'person-a', 'person-b'],
      keywords: [' 夏史 ', '考古', '夏史'],
    };
    const draft: EvidenceDraft = {
      ...createEvidenceDraft(),
      sources: [sourceA, sourceB],
      passages: [{ ...passage, passage_id: 'passage-z' }, { ...passage, passage_id: 'passage-a' }],
    };

    const normalized = normalizeEvidenceDraft(draft);

    expect(normalized.sources.map((item) => item.source_id)).toEqual(['source-a', 'source-z']);
    expect(normalized.passages.map((item) => item.passage_id)).toEqual(['passage-a', 'passage-z']);
    expect(normalized.passages[0].fact_ids).toEqual(['fact-a', 'fact-z']);
    expect(normalized.passages[0].person_ids).toEqual(['person-a', 'person-b']);
    expect(normalized.passages[0].keywords).toEqual(['夏史', '考古']);
  });

  it('uses the same canonical presentation checksum as the Python contract', async () => {
    const presentation = createLessonPresentation('C-prequin-state', 'L101', 1);
    presentation.sealed_at = '2026-01-02T03:04:05.000Z';

    const signed = await signLessonPresentation(presentation);

    expect(signed.checksum).toBe('ff821f310d73afce439d02567879ce1750d28c4fea57187223724d81130bc3af');
  });

  it('derives the fact ids used by the frozen course package', async () => {
    const packageItem = {
      facts: ['【传世文献】《史记·夏本纪》由西汉司马迁撰成，距离传统所说的禹时代很远，具体叙事需要与其他材料互证。'],
      people: [],
    } as unknown as LessonContentPackage;

    const bindings = await lessonEvidenceBindings(packageItem);

    expect(bindings.facts[0].id).toBe('fact-98a8d039');
  });
});
