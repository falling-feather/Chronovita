import type { ReactNode } from 'react';

export interface MarkupSegment {
  text: string;
  marks: Array<'bold' | 'highlight' | 'keyword'>;
}

export function extractMarkedKeywords(value: string): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  Array.from(value.matchAll(/【([^】]{1,40})】/g)).forEach((match) => {
    const word = match[1].trim();
    if (word && !seen.has(word)) {
      seen.add(word);
      result.push(word);
    }
  });
  return result;
}

export function stripInlineMarkup(value: string): string {
  return value
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/==([^=]+)==/g, '$1')
    .replace(/【([^】]+)】/g, '$1');
}

export function parseContentMarkup(value: string): MarkupSegment[] {
  const segments: MarkupSegment[] = [];
  let index = 0;
  let bold = false;
  let highlight = false;
  let buffer = '';

  const flush = () => {
    if (!buffer) return;
    const marks: MarkupSegment['marks'] = [];
    if (bold) marks.push('bold');
    if (highlight) marks.push('highlight');
    segments.push({ text: buffer, marks });
    buffer = '';
  };

  while (index < value.length) {
    if (value.startsWith('**', index)) {
      flush();
      bold = !bold;
      index += 2;
      continue;
    }
    if (value.startsWith('==', index)) {
      flush();
      highlight = !highlight;
      index += 2;
      continue;
    }
    if (value[index] === '【') {
      const end = value.indexOf('】', index + 1);
      if (end > index) {
        flush();
        const marks: MarkupSegment['marks'] = ['keyword'];
        if (bold) marks.push('bold');
        if (highlight) marks.push('highlight');
        segments.push({ text: value.slice(index + 1, end), marks });
        index = end + 1;
        continue;
      }
    }
    buffer += value[index];
    index += 1;
  }
  flush();
  return segments;
}

export function renderContentMarkup(value: string): ReactNode[] {
  return parseContentMarkup(value).map((segment, index) => {
    let node: ReactNode = segment.text;
    if (segment.marks.includes('keyword')) {
      node = (
        <span style={{ color: 'var(--accent-bronze)', fontWeight: 700, borderBottom: '1px solid rgba(176, 120, 54, 0.35)' }}>
          {node}
        </span>
      );
    }
    if (segment.marks.includes('highlight')) {
      node = (
        <mark style={{ color: '#9F2D20', background: 'rgba(198, 65, 47, 0.12)', borderRadius: 3, padding: '0 3px' }}>
          {node}
        </mark>
      );
    }
    if (segment.marks.includes('bold')) {
      node = <strong>{node}</strong>;
    }
    return <span key={`${segment.text}-${index}`}>{node}</span>;
  });
}

export function renderMarkupHtml(value: string): string {
  return parseContentMarkup(value).map((segment) => {
    let html = escapeHtml(segment.text);
    if (segment.marks.includes('keyword')) html = `<span class="keyword">${html}</span>`;
    if (segment.marks.includes('highlight')) html = `<mark>${html}</mark>`;
    if (segment.marks.includes('bold')) html = `<strong>${html}</strong>`;
    return html;
  }).join('');
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
