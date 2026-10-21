import { describe, expect, it } from 'vitest';
import type { RagAnswer } from '../../utils/api';
import {
  answerBoundaryNote,
  answerSpeaker,
  evidenceDisclosureLabel,
  friendlyAskError,
  studentAnswerOrigin,
} from './askPresentation';

const answer = (overrides: Partial<RagAnswer> = {}): RagAnswer => ({
  schema_version: 'rag-answer/v1',
  answer_source: 'model',
  retrieval_mode: 'hybrid',
  body: '回答',
  persona_mode: 'expert',
  person_id: null,
  role_disclaimer: null,
  citations: [{
    citation_id: 'c1', passage_id: 'p1', source_id: 's1', source_title: '史料',
    locator: '卷一', excerpt: '片段', relevance: 0.9, certainty: 'consensus',
  }],
  retrieved_passage_ids: ['p1'],
  course_id: 'C-prequin-state', lesson_id: 'L103',
  release_id: 'r1', release_no: 1, release_checksum: 'a'.repeat(64),
  evidence_corpus_id: 'e1', evidence_version: 1, evidence_checksum: 'b'.repeat(64),
  uncertainty: 'low',
  ...overrides,
});

describe('ask presentation', () => {
  it('resolves published people without exposing persona implementation text', () => {
    expect(answerSpeaker(answer(), [])).toMatchObject({ name: '课程学者', person: null });
    expect(answerSpeaker(answer({ persona_mode: 'person', person_id: 'shangyang' }), [
      { person_id: 'shangyang', name: '商鞅', role: '左庶长' },
    ])).toMatchObject({ name: '商鞅', role: '左庶长' });
  });

  it('turns answer internals into plain student language', () => {
    expect(studentAnswerOrigin(answer())).toBe('据本课材料整理');
    expect(studentAnswerOrigin(answer({ answer_source: 'extractive' }))).toBe('据本课材料摘录');
    expect(studentAnswerOrigin(answer({ answer_source: 'insufficient_evidence' }))).toBe('当前材料暂不能回答');
    expect(answerBoundaryNote(answer())).toContain('支持较充分');
    expect(answerBoundaryNote(answer({
      citations: [{ ...answer().citations[0], certainty: 'legend' }],
    }))).toContain('传说');
    expect(answerBoundaryNote(answer({ answer_source: 'insufficient_evidence', citations: [] }))).toContain('缩小');
  });

  it('labels evidence and sanitizes infrastructure failures', () => {
    expect(evidenceDisclosureLabel(2)).toBe('据何而答 · 2 条材料');
    expect(evidenceDisclosureLabel(0)).toBe('据何而答 · 暂无可用材料');
    expect(friendlyAskError(new Error('Cookie-authenticated writes require a trusted Origin.')))
      .toBe('课堂连接尚未建立，请刷新页面后再试。');
    expect(friendlyAskError(new Error('500 provider detail leaked')))
      .toBe('这次没有得到回答，请稍后再试。');
  });
});
