import type { GameDossier } from '../../utils/api';
import type { LearningDeskStickyNote } from './learningLedger';

const ALLOWED_TAGS = new Set([
  'P', 'BR', 'STRONG', 'EM', 'U', 'MARK', 'H2', 'H3', 'UL', 'OL', 'LI', 'BLOCKQUOTE',
]);

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderInlineMarkdown(value: string): string {
  return escapeHtml(value)
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/==([^=\n]+)==/g, '<mark>$1</mark>')
    .replace(/\*([^*\n]+)\*/g, '<em>$1</em>');
}

export function markdownToSafeHtml(markdown: string): string {
  const output: string[] = [];
  const lines = markdown.replace(/\r\n?/g, '\n').slice(0, 60_000).split('\n');
  let list: 'ul' | 'ol' | null = null;

  const closeList = () => {
    if (!list) return;
    output.push(`</${list}>`);
    list = null;
  };

  for (const line of lines) {
    const unordered = /^[-*]\s+(.+)$/.exec(line);
    const ordered = /^\d+[.)]\s+(.+)$/.exec(line);
    if (unordered || ordered) {
      const nextList = unordered ? 'ul' : 'ol';
      if (list !== nextList) {
        closeList();
        list = nextList;
        output.push(`<${nextList}>`);
      }
      output.push(`<li>${renderInlineMarkdown((unordered || ordered)?.[1] ?? '')}</li>`);
      continue;
    }
    closeList();
    if (!line.trim()) {
      output.push('<p><br></p>');
    } else if (line.startsWith('### ')) {
      output.push(`<h3>${renderInlineMarkdown(line.slice(4))}</h3>`);
    } else if (line.startsWith('## ')) {
      output.push(`<h2>${renderInlineMarkdown(line.slice(3))}</h2>`);
    } else if (line.startsWith('# ')) {
      output.push(`<h2>${renderInlineMarkdown(line.slice(2))}</h2>`);
    } else if (line.startsWith('> ')) {
      output.push(`<blockquote>${renderInlineMarkdown(line.slice(2))}</blockquote>`);
    } else {
      output.push(`<p>${renderInlineMarkdown(line)}</p>`);
    }
  }
  closeList();
  return output.join('');
}

function decodeEntities(value: string): string {
  return value
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'");
}

export function richHtmlToMarkdown(html: string): string {
  return decodeEntities(html)
    .replace(/<\s*br\s*\/?\s*>/gi, '\n')
    .replace(/<\s*(strong|b)\s*>/gi, '**')
    .replace(/<\s*\/\s*(strong|b)\s*>/gi, '**')
    .replace(/<\s*(em|i)\s*>/gi, '*')
    .replace(/<\s*\/\s*(em|i)\s*>/gi, '*')
    .replace(/<\s*mark\s*>/gi, '==')
    .replace(/<\s*\/\s*mark\s*>/gi, '==')
    .replace(/<\s*h2\s*>/gi, '\n## ')
    .replace(/<\s*\/\s*h2\s*>/gi, '\n')
    .replace(/<\s*h3\s*>/gi, '\n### ')
    .replace(/<\s*\/\s*h3\s*>/gi, '\n')
    .replace(/<\s*blockquote\s*>/gi, '\n> ')
    .replace(/<\s*\/\s*blockquote\s*>/gi, '\n')
    .replace(/<\s*li\s*>/gi, '\n- ')
    .replace(/<\s*\/\s*li\s*>/gi, '')
    .replace(/<\s*\/\s*(p|div|ul|ol)\s*>/gi, '\n')
    .replace(/<[^>]*>/g, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
    .slice(0, 60_000);
}

export function sanitizeDeskHtml(html: string): string {
  const source = html.slice(0, 80_000);
  if (typeof DOMParser === 'undefined') {
    return markdownToSafeHtml(richHtmlToMarkdown(source));
  }
  const document = new DOMParser().parseFromString(`<div>${source}</div>`, 'text/html');
  const root = document.body.firstElementChild;
  if (!root) return '';

  const cleanNode = (node: Node): string => {
    if (node.nodeType === Node.TEXT_NODE) return escapeHtml(node.textContent ?? '');
    if (!(node instanceof Element)) return '';
    const children = [...node.childNodes].map(cleanNode).join('');
    if (!ALLOWED_TAGS.has(node.tagName)) return children;
    const tag = node.tagName.toLowerCase();
    return tag === 'br' ? '<br>' : `<${tag}>${children}</${tag}>`;
  };

  return [...root.childNodes].map(cleanNode).join('').slice(0, 80_000);
}

export interface LearningDeskSeed {
  title: string;
  bodyMarkdown: string;
  bodyHtml: string;
  stickyNotes: LearningDeskStickyNote[];
}

export function buildLearningDeskSeed({
  lessonTitle,
  temporaryNote,
  dossier,
}: {
  lessonTitle: string;
  temporaryNote: string;
  dossier: GameDossier | null;
}): LearningDeskSeed {
  const lines = [
    `# ${lessonTitle} · 我的学习卷宗`,
    '',
    '## 我的判断',
    '写下你对本课核心问题的判断，并用课文、推演或问史材料说明理由。',
  ];
  if (temporaryNote.trim()) {
    lines.push('', '## 随手记', temporaryNote.trim());
  }
  if (dossier) {
    lines.push('', '## 推演回看', dossier.strategy_summary || '本次推演已形成选择记录。');
    for (const choice of dossier.key_choices) {
      lines.push(`- 第 ${choice.turn_no} 回合：${choice.choice}${choice.consequence ? `——${choice.consequence}` : ''}`);
    }
    if (dossier.historical_explanation.trim()) {
      lines.push('', '## 历史解释', dossier.historical_explanation.trim());
    }
  }
  const bodyMarkdown = lines.join('\n');
  const stickyNotes: LearningDeskStickyNote[] = temporaryNote.trim() ? [{
    note_id: 'seed:temporary-note',
    body: temporaryNote.trim().slice(0, 1000),
    color: 'ochre',
  }] : [];
  return {
    title: `${lessonTitle} · 学习卷宗`,
    bodyMarkdown,
    bodyHtml: markdownToSafeHtml(bodyMarkdown),
    stickyNotes,
  };
}
