import type { CSSProperties, ReactNode } from 'react';

export type InlineMark = 'bold' | 'highlight' | 'keyword' | 'red' | 'blue' | 'gold' | 'large' | 'small';

export interface MarkupSegment {
  text: string;
  marks: InlineMark[];
}

export interface ContentBlock {
  level: 0 | 1 | 2 | 3;
  text: string;
}

const tokenMarks: Record<string, InlineMark> = {
  red: 'red',
  blue: 'blue',
  gold: 'gold',
  large: 'large',
  small: 'small',
  红色: 'red',
  蓝色: 'blue',
  金色: 'gold',
  大字: 'large',
  小字: 'small',
};

const colorStyles: Partial<Record<InlineMark, CSSProperties>> = {
  red: { color: '#9F2D20' },
  blue: { color: '#315F91' },
  gold: { color: '#8B641B' },
};

const sizeStyles: Partial<Record<InlineMark, CSSProperties>> = {
  large: { fontSize: '1.14em' },
  small: { fontSize: '0.88em' },
};

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

export function parseContentBlock(value: string): ContentBlock {
  const match = value.match(/^\s*(#{1,3})\s+(.+)$/);
  if (!match) return { level: 0, text: value };
  return { level: match[1].length as ContentBlock['level'], text: match[2].trim() };
}

export function stripInlineMarkup(value: string): string {
  return stripCustomMarkup(value)
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/==([^=]+)==/g, '$1')
    .replace(/【([^】]+)】/g, '$1')
    .replace(/^\s*#{1,3}\s+/gm, '');
}

export function parseContentMarkup(value: string): MarkupSegment[] {
  return mergeAdjacentSegments(parseInline(value, []));
}

export function renderContentMarkup(value: string): ReactNode[] {
  return parseContentMarkup(value).map((segment, index) => {
    let node: ReactNode = segment.text;
    const colorStyle = mergeMarkStyles(segment.marks, colorStyles);
    const sizeStyle = mergeMarkStyles(segment.marks, sizeStyles);

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
    if (colorStyle) {
      node = <span style={colorStyle}>{node}</span>;
    }
    if (sizeStyle) {
      node = <span style={sizeStyle}>{node}</span>;
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
    if (segment.marks.includes('red')) html = `<span class="text-red">${html}</span>`;
    if (segment.marks.includes('blue')) html = `<span class="text-blue">${html}</span>`;
    if (segment.marks.includes('gold')) html = `<span class="text-gold">${html}</span>`;
    if (segment.marks.includes('large')) html = `<span class="text-large">${html}</span>`;
    if (segment.marks.includes('small')) html = `<span class="text-small">${html}</span>`;
    if (segment.marks.includes('bold')) html = `<strong>${html}</strong>`;
    return html;
  }).join('');
}

function parseInline(value: string, inheritedMarks: InlineMark[]): MarkupSegment[] {
  const segments: MarkupSegment[] = [];
  let index = 0;
  let activeMarks = [...inheritedMarks];
  let buffer = '';

  const flush = () => {
    if (!buffer) return;
    segments.push({ text: buffer, marks: uniqueMarks(activeMarks) });
    buffer = '';
  };

  while (index < value.length) {
    if (value.startsWith('**', index)) {
      flush();
      activeMarks = toggleMark(activeMarks, 'bold');
      index += 2;
      continue;
    }

    if (value.startsWith('==', index)) {
      flush();
      activeMarks = toggleMark(activeMarks, 'highlight');
      index += 2;
      continue;
    }

    if (value[index] === '【') {
      const end = value.indexOf('】', index + 1);
      if (end > index) {
        flush();
        segments.push(...parseInline(value.slice(index + 1, end), appendMark(activeMarks, 'keyword')));
        index = end + 1;
        continue;
      }
    }

    const custom = readCustomToken(value, index);
    if (custom) {
      flush();
      segments.push(...parseInline(custom.text, appendMark(activeMarks, custom.mark)));
      index = custom.end;
      continue;
    }

    buffer += value[index];
    index += 1;
  }

  flush();
  return segments;
}

function readCustomToken(value: string, start: number): { end: number; mark: InlineMark; text: string } | null {
  if (!value.startsWith('{{', start)) return null;
  const end = value.indexOf('}}', start + 2);
  if (end < 0) return null;
  const content = value.slice(start + 2, end);
  const separator = content.indexOf(':');
  if (separator < 0) return null;
  const token = content.slice(0, separator).trim();
  const mark = tokenMarks[token];
  if (!mark) return null;
  return { end: end + 2, mark, text: content.slice(separator + 1) };
}

function stripCustomMarkup(value: string): string {
  let current = value;
  let previous = '';
  while (current !== previous) {
    previous = current;
    current = current.replace(/\{\{\s*([^:}]{1,12})\s*:\s*([^{}]*)\}\}/g, (full, token, text) => {
      return tokenMarks[String(token).trim()] ? String(text) : String(full);
    });
  }
  return current;
}

function appendMark(marks: InlineMark[], mark: InlineMark): InlineMark[] {
  return marks.includes(mark) ? marks : [...marks, mark];
}

function toggleMark(marks: InlineMark[], mark: InlineMark): InlineMark[] {
  return marks.includes(mark) ? marks.filter((item) => item !== mark) : [...marks, mark];
}

function uniqueMarks(marks: InlineMark[]): InlineMark[] {
  return Array.from(new Set(marks));
}

function mergeAdjacentSegments(segments: MarkupSegment[]): MarkupSegment[] {
  const merged: MarkupSegment[] = [];
  segments.forEach((segment) => {
    const previous = merged[merged.length - 1];
    if (previous && marksKey(previous.marks) === marksKey(segment.marks)) {
      previous.text += segment.text;
    } else {
      merged.push({ ...segment });
    }
  });
  return merged;
}

function marksKey(marks: InlineMark[]): string {
  return uniqueMarks(marks).sort().join('|');
}

function mergeMarkStyles(marks: InlineMark[], source: Partial<Record<InlineMark, CSSProperties>>): CSSProperties | null {
  const style = marks.reduce<CSSProperties>((record, mark) => ({ ...record, ...source[mark] }), {});
  return Object.keys(style).length > 0 ? style : null;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
