import { useEffect, useRef, useState } from 'react';
import { Button, Input, Segmented } from 'antd';
import {
  BoldOutlined,
  EditOutlined,
  ItalicOutlined,
  OrderedListOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import {
  markdownToSafeHtml,
  richHtmlToMarkdown,
  sanitizeDeskHtml,
} from './learningDeskDocument';

type EditorMode = 'visual' | 'markdown';

export default function LearningDeskEditor({
  title,
  html,
  markdown,
  onTitleChange,
  onDocumentChange,
}: {
  title: string;
  html: string;
  markdown: string;
  onTitleChange: (value: string) => void;
  onDocumentChange: (next: { html: string; markdown: string }) => void;
}) {
  const editorRef = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<EditorMode>('visual');

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor || document.activeElement === editor) return;
    const safe = sanitizeDeskHtml(html);
    if (editor.innerHTML !== safe) editor.innerHTML = safe;
  }, [html, mode]);

  const syncVisual = () => {
    const editor = editorRef.current;
    if (!editor) return;
    const nextHtml = sanitizeDeskHtml(editor.innerHTML);
    onDocumentChange({ html: nextHtml, markdown: richHtmlToMarkdown(nextHtml) });
  };

  const command = (name: string, value?: string) => {
    editorRef.current?.focus();
    document.execCommand(name, false, value);
    syncVisual();
  };

  const changeMode = (nextMode: EditorMode) => {
    if (nextMode === 'visual') {
      onDocumentChange({ html: markdownToSafeHtml(markdown), markdown });
    } else {
      syncVisual();
    }
    setMode(nextMode);
  };

  return (
    <section className="chrono-desk-editor" aria-label="学习卷宗正文编辑器">
      <header className="chrono-desk-editor-header">
        <Input
          className="chrono-desk-title-input"
          aria-label="学习卷宗标题"
          value={title}
          maxLength={160}
          onChange={(event) => onTitleChange(event.target.value)}
        />
        <Segmented
          value={mode}
          aria-label="正文编辑模式"
          options={[
            { label: '所见即所得', value: 'visual' },
            { label: 'Markdown', value: 'markdown' },
          ]}
          onChange={(value) => changeMode(value as EditorMode)}
        />
      </header>

      {mode === 'visual' ? (
        <>
          <div className="chrono-desk-formatbar" aria-label="正文格式">
            <Button size="small" icon={<BoldOutlined />} aria-label="加粗" onClick={() => command('bold')} />
            <Button size="small" icon={<ItalicOutlined />} aria-label="斜体" onClick={() => command('italic')} />
            <Button size="small" onClick={() => command('formatBlock', 'h2')}>标题</Button>
            <Button size="small" onClick={() => command('formatBlock', 'blockquote')}>引证</Button>
            <Button size="small" icon={<UnorderedListOutlined />} onClick={() => command('insertUnorderedList')}>条目</Button>
            <Button size="small" icon={<OrderedListOutlined />} onClick={() => command('insertOrderedList')}>步骤</Button>
          </div>
          <div
            ref={editorRef}
            className="chrono-desk-rich-editor chrono-serif"
            contentEditable
            role="textbox"
            aria-multiline="true"
            aria-label="所见即所得正文"
            suppressContentEditableWarning
            onInput={syncVisual}
            onBlur={syncVisual}
            onPaste={(event) => {
              event.preventDefault();
              document.execCommand('insertText', false, event.clipboardData.getData('text/plain'));
            }}
          />
        </>
      ) : (
        <label className="chrono-desk-markdown-shell">
          <span><EditOutlined /> Markdown 正文</span>
          <Input.TextArea
            value={markdown}
            maxLength={60_000}
            autoSize={{ minRows: 18 }}
            onChange={(event) => onDocumentChange({
              markdown: event.target.value,
              html: markdownToSafeHtml(event.target.value),
            })}
          />
        </label>
      )}
    </section>
  );
}
