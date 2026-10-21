import { describe, expect, it } from 'vitest';
import type { Keyword } from '../../utils/api';
import { normalizeReadingKeywords, splitReadingText } from './lessonReadingModel';

const keyword = (word: string): Keyword => ({ word, pinyin: '', gloss: `${word}的解释` });

describe('lessonReadingModel', () => {
  it('matches longer course terms before their shorter aliases', () => {
    const result = splitReadingText('大禹治水与治水叙事', [keyword('治水'), keyword('大禹治水')]);
    expect(result.map((item) => [item.text, item.keyword?.word])).toEqual([
      ['大禹治水', '大禹治水'],
      ['与', undefined],
      ['治水', '治水'],
      ['叙事', undefined],
    ]);
  });

  it('keeps repeated keywords interactive without changing surrounding text', () => {
    const result = splitReadingText('二里头不是夏史的同义词，二里头仍是重要线索。', [keyword('二里头')]);
    expect(result.filter((item) => item.keyword).map((item) => item.text)).toEqual(['二里头', '二里头']);
    expect(result.map((item) => item.text).join('')).toBe('二里头不是夏史的同义词，二里头仍是重要线索。');
  });

  it('escapes punctuation and removes duplicate or empty entries', () => {
    const normalized = normalizeReadingKeywords([keyword(''), keyword('A+B'), keyword('A+B')]);
    expect(normalized.map((item) => item.word)).toEqual(['A+B']);
    expect(splitReadingText('比较 A+B。', normalized).find((item) => item.keyword)?.text).toBe('A+B');
  });

  it('maps meaningful compound-term aliases back to the published glossary entry', () => {
    const result = splitReadingText('什伍组织加强了连带责任。', [keyword('什伍与连带责任')]);
    expect(result.filter((item) => item.keyword).map((item) => [item.text, item.keyword?.word])).toEqual([
      ['什伍', '什伍与连带责任'],
      ['连带责任', '什伍与连带责任'],
    ]);
  });
});
