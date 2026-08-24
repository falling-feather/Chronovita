import { describe, expect, it } from 'vitest';
import {
  buildLearningDeskSeed,
  markdownToSafeHtml,
  richHtmlToMarkdown,
  sanitizeDeskHtml,
} from './learningDeskDocument';

describe('learning desk document', () => {
  it('renders a small safe Markdown dialect', () => {
    const html = markdownToSafeHtml('## 判断\n**疏导**与==协作==\n- 证据一');
    expect(html).toContain('<h2>判断</h2>');
    expect(html).toContain('<strong>疏导</strong>');
    expect(html).toContain('<mark>协作</mark>');
    expect(html).toContain('<ul><li>证据一</li></ul>');
  });

  it('escapes raw HTML and removes unsafe rich markup', () => {
    expect(markdownToSafeHtml('<img src=x onerror=alert(1)>')).not.toContain('<img');
    const cleaned = sanitizeDeskHtml('<p>可留</p><script>alert(1)</script><img src=x><strong>重点</strong>');
    expect(cleaned).not.toContain('<script');
    expect(cleaned).not.toContain('<img');
    expect(cleaned).toContain('可留');
    expect(cleaned).toContain('<strong>重点</strong>');
  });

  it('keeps the two editing representations mutually convertible', () => {
    const markdown = richHtmlToMarkdown('<h2>结论</h2><p><strong>制度</strong>也有代价</p>');
    expect(markdown).toContain('## 结论');
    expect(markdown).toContain('**制度**也有代价');
  });

  it('seeds an empty desk from the lesson and temporary notebook', () => {
    const seed = buildLearningDeskSeed({
      lessonTitle: '大禹治水',
      temporaryNote: '疏导不是唯一按钮。',
      dossier: null,
    });
    expect(seed.title).toContain('大禹治水');
    expect(seed.bodyMarkdown).toContain('随手记');
    expect(seed.stickyNotes[0].body).toBe('疏导不是唯一按钮。');
  });
});
