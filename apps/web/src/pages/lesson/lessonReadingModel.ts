import type { Keyword } from '../../utils/api';

export interface ReadingTextToken {
  text: string;
  keyword?: Keyword;
}

interface ReadingKeywordTerm {
  text: string;
  keyword: Keyword;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function normalizeReadingKeywords(keywords: Keyword[]): Keyword[] {
  const seen = new Set<string>();
  return keywords
    .filter((keyword) => keyword.word.trim())
    .filter((keyword) => {
      const word = keyword.word.trim();
      if (seen.has(word)) return false;
      seen.add(word);
      return true;
    })
    .map((keyword) => ({ ...keyword, word: keyword.word.trim() }))
    .sort((left, right) => right.word.length - left.word.length || left.word.localeCompare(right.word, 'zh-CN'));
}

function readingKeywordTerms(keywords: Keyword[]): ReadingKeywordTerm[] {
  const byTerm = new Map<string, Keyword>();
  normalizeReadingKeywords(keywords).forEach((keyword) => {
    const terms = [keyword.word, ...keyword.word.split(/[、与及和]/)]
      .map((term) => term.trim())
      .filter((term) => term.length >= 2);
    terms.forEach((term) => {
      if (!byTerm.has(term)) byTerm.set(term, keyword);
    });
  });
  return Array.from(byTerm, ([text, keyword]) => ({ text, keyword }))
    .sort((left, right) => right.text.length - left.text.length || left.text.localeCompare(right.text, 'zh-CN'));
}

export function splitReadingText(value: string, keywords: Keyword[]): ReadingTextToken[] {
  const terms = readingKeywordTerms(keywords);
  if (!value || terms.length === 0) return value ? [{ text: value }] : [];

  const byWord = new Map(terms.map((term) => [term.text, term.keyword]));
  const pattern = new RegExp(`(${terms.map((term) => escapeRegExp(term.text)).join('|')})`, 'g');

  return value
    .split(pattern)
    .filter(Boolean)
    .map((text) => ({ text, keyword: byWord.get(text) }));
}
