import { useEffect, useMemo, useState } from 'react';
import { Button, Divider, Empty, Input, Select, Space, Tag } from 'antd';
import {
  DownloadOutlined,
  EyeOutlined,
  FileTextOutlined,
  LockOutlined,
  ReloadOutlined,
  SaveOutlined,
} from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { api, type ContentFileRecord, type LessonContentPackage } from '../utils/api';
import { toast } from '../utils/toast';

const { TextArea } = Input;
const TOKEN_KEY = 'chrono.admin.token';
const LOCAL_DRAFT_KEY = 'chrono.admin.content.editor.v1';

interface EditorState {
  lesson_id: string;
  course_id: string;
  course_title: string;
  title: string;
  unit: string;
  era: string;
  era_id: string;
  section: string;
  lesson_no: string;
  duration: string;
  bodyText: string;
  keywordsText: string;
  focusText: string;
  qaText: string;
  goalsText: string;
  peopleText: string;
  mapText: string;
  sourcesText: string;
  sagaTitle: string;
  sagaObjective: string;
  sagaNotes: string;
  sandboxTitle: string;
  sandboxObjective: string;
  sandboxNotes: string;
  teacher_notes: string;
}

const baseInputStyle = { minWidth: 0 };

function newEditor(): EditorState {
  const stamp = Date.now().toString().slice(-8);
  return {
    lesson_id: `lesson-${stamp}`,
    course_id: 'C-content-studio',
    course_title: '内容工作室',
    title: '',
    unit: '',
    era: '',
    era_id: 'content',
    section: '内容包',
    lesson_no: 'A1',
    duration: '08:00',
    bodyText: '',
    keywordsText: '',
    focusText: '',
    qaText: '',
    goalsText: '',
    peopleText: '',
    mapText: '',
    sourcesText: '',
    sagaTitle: '',
    sagaObjective: '',
    sagaNotes: '',
    sandboxTitle: '',
    sandboxObjective: '',
    sandboxNotes: '',
    teacher_notes: '',
  };
}

function readLocalEditor(): EditorState {
  const saved = localStorage.getItem(LOCAL_DRAFT_KEY);
  if (!saved) return newEditor();
  try {
    return { ...newEditor(), ...(JSON.parse(saved) as Partial<EditorState>) };
  } catch {
    return newEditor();
  }
}

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function splitLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function splitParagraphs(value: string): string[] {
  return value
    .split(/\n\s*\n/)
    .map((item) => item.trim().replace(/【([^】]+)】/g, '$1'))
    .filter(Boolean);
}

function unique(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  values.forEach((value) => {
    const key = value.trim();
    if (key && !seen.has(key)) {
      seen.add(key);
      result.push(key);
    }
  });
  return result;
}

function extractMarkedKeywords(value: string): string[] {
  return unique(Array.from(value.matchAll(/【([^】]{1,40})】/g)).map((match) => match[1].trim()));
}

function parseKeywordLine(line: string) {
  const parts = line.includes('|')
    ? line.split('|').map((item) => item.trim())
    : line.split(/[：:]/).map((item) => item.trim());
  return {
    word: parts[0] || line.trim(),
    pinyin: line.includes('|') ? parts[1] || '' : '',
    gloss: line.includes('|') ? parts.slice(2).join(' | ') : parts.slice(1).join(': '),
  };
}

function parseKeywords(editor: EditorState) {
  const explicitLines = editor.keywordsText
    .split(/\r?\n|,|，|、/)
    .map((item) => item.trim())
    .filter(Boolean);
  const explicit = explicitLines.map(parseKeywordLine);
  const marked = extractMarkedKeywords(editor.bodyText)
    .filter((word) => !explicit.some((item) => item.word === word))
    .map((word) => ({ word, pinyin: '', gloss: '' }));
  return [...explicit, ...marked].filter((item) => item.word);
}

function parsePipeRecords(value: string, keys: string[]) {
  return splitLines(value).map((line) => {
    const parts = line.split('|').map((item) => item.trim());
    return keys.reduce<Record<string, string>>((record, key, index) => {
      record[key] = parts[index] || '';
      return record;
    }, {});
  });
}

function packageToEditor(item: LessonContentPackage): EditorState {
  return {
    ...newEditor(),
    lesson_id: item.lesson_id,
    course_id: item.course_id || 'C-content-studio',
    course_title: item.course_title || item.unit || '',
    title: item.title,
    unit: item.unit,
    era: item.era,
    era_id: item.era_id || 'content',
    section: item.section || '内容包',
    lesson_no: item.lesson_no || 'A1',
    duration: item.duration || '08:00',
    bodyText: (item.body || []).join('\n\n'),
    keywordsText: (item.keywords || [])
      .map((keyword) => [keyword.word, keyword.pinyin, keyword.gloss].filter(Boolean).join(' | '))
      .join('\n'),
    focusText: (item.facts || []).join('\n'),
    qaText: (item.qa_points || []).join('\n'),
    goalsText: (item.level_goals || []).join('\n'),
    peopleText: (item.people || [])
      .map((person) => [person.name, person.role, person.summary, person.persona].filter(Boolean).join(' | '))
      .join('\n'),
    mapText: (item.map_points || [])
      .map((point) => [point.label, point.region, point.note, point.kind].filter(Boolean).join(' | '))
      .join('\n'),
    sourcesText: (item.source_refs || [])
      .map((source) => [source.title, source.source, source.url_or_path, source.citation_note].filter(Boolean).join(' | '))
      .join('\n'),
    sagaTitle: item.saga_material?.title || '',
    sagaObjective: item.saga_material?.objective || '',
    sagaNotes: item.saga_material?.notes || '',
    sandboxTitle: item.sandbox_material?.title || '',
    sandboxObjective: item.sandbox_material?.objective || '',
    sandboxNotes: item.sandbox_material?.notes || '',
    teacher_notes: item.teacher_notes || '',
  };
}

function buildPayload(editor: EditorState): LessonContentPackage {
  const required = [editor.lesson_id, editor.course_id, editor.title, editor.unit, editor.era];
  if (required.some((value) => !value.trim())) {
    throw new Error('请补齐 ID、课程、标题、单元和时代');
  }
  const keywords = parseKeywords(editor);
  const people = parsePipeRecords(editor.peopleText, ['name', 'role', 'summary', 'persona'])
    .filter((item) => item.name)
    .map((item) => ({ name: item.name, role: item.role, summary: item.summary, persona: item.persona }));
  const mapPoints = parsePipeRecords(editor.mapText, ['label', 'region', 'note', 'kind'])
    .filter((item) => item.label)
    .map((item) => ({ label: item.label, region: item.region, note: item.note, kind: item.kind || 'site' }));
  const sourceRefs = parsePipeRecords(editor.sourcesText, ['title', 'source', 'url_or_path', 'citation_note'])
    .filter((item) => item.title)
    .map((item) => ({ title: item.title, source: item.source, url_or_path: item.url_or_path, citation_note: item.citation_note }));
  return {
    lesson_id: editor.lesson_id.trim(),
    course_id: editor.course_id.trim(),
    course_title: editor.course_title.trim() || editor.unit.trim(),
    title: editor.title.trim(),
    unit: editor.unit.trim(),
    era: editor.era.trim(),
    era_id: editor.era_id.trim() || 'content',
    section: editor.section.trim() || '内容包',
    lesson_no: editor.lesson_no.trim() || 'A1',
    duration: editor.duration.trim() || '08:00',
    body: splitParagraphs(editor.bodyText),
    keywords,
    people,
    map_points: mapPoints,
    source_refs: sourceRefs,
    facts: splitLines(editor.focusText),
    qa_points: splitLines(editor.qaText),
    level_goals: splitLines(editor.goalsText),
    saga_material: {
      title: editor.sagaTitle.trim(),
      objective: editor.sagaObjective.trim(),
      notes: editor.sagaNotes.trim(),
      assets: [],
    },
    sandbox_material: {
      title: editor.sandboxTitle.trim(),
      objective: editor.sandboxObjective.trim(),
      notes: editor.sandboxNotes.trim(),
      assets: [],
    },
    seed_canvas: keywords.slice(0, 6).map((keyword, index) => ({ id: `k${index + 1}`, label: keyword.word })),
    teacher_notes: editor.teacher_notes.trim(),
    status: 'draft',
    version: 0,
  };
}

function applyBodyParsing(editor: EditorState): EditorState {
  const keywordText = unique([...splitLines(editor.keywordsText), ...extractMarkedKeywords(editor.bodyText)]).join('\n');
  const focus: string[] = [];
  const qa: string[] = [];
  const goals: string[] = [];
  splitLines(editor.bodyText).forEach((line) => {
    const normalized = line.replace(/^[-*]\s*/, '').trim();
    const match = normalized.match(/^(重点|事实|史实|问题|追问|目标|关卡)[:：]\s*(.+)$/);
    if (!match) return;
    if (['重点', '事实', '史实'].includes(match[1])) focus.push(match[2]);
    if (['问题', '追问'].includes(match[1])) qa.push(match[2]);
    if (['目标', '关卡'].includes(match[1])) goals.push(match[2]);
  });
  return {
    ...editor,
    keywordsText: keywordText,
    focusText: unique([...splitLines(editor.focusText), ...focus]).join('\n'),
    qaText: unique([...splitLines(editor.qaText), ...qa]).join('\n'),
    goalsText: unique([...splitLines(editor.goalsText), ...goals]).join('\n'),
  };
}

function downloadJson(item: LessonContentPackage) {
  const suffix = item.status === 'sealed' ? `v${String(item.version || 1).padStart(3, '0')}` : 'draft';
  const blob = new Blob([formatJson(item) + '\n'], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${item.lesson_id}-${suffix}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

export default function AdminContentPage() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || 'dev-admin-token');
  const [sealedBy, setSealedBy] = useState('admin');
  const [editor, setEditor] = useState<EditorState>(() => readLocalEditor());
  const [preview, setPreview] = useState<LessonContentPackage | null>(null);
  const [drafts, setDrafts] = useState<ContentFileRecord[]>([]);
  const [selectedDraft, setSelectedDraft] = useState<string>();
  const [sealedPath, setSealedPath] = useState('');
  const [localSavedAt, setLocalSavedAt] = useState('');
  const [serverSavedAt, setServerSavedAt] = useState('');
  const [busy, setBusy] = useState('');

  const currentPayload = useMemo(() => {
    try {
      return buildPayload(editor);
    } catch {
      return null;
    }
  }, [editor]);

  useEffect(() => {
    localStorage.setItem(LOCAL_DRAFT_KEY, JSON.stringify(editor));
    setLocalSavedAt(new Date().toLocaleTimeString());
  }, [editor]);

  useEffect(() => {
    void refreshDrafts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const rememberToken = (value: string) => {
    setToken(value);
    localStorage.setItem(TOKEN_KEY, value);
  };

  const updateEditor = (patch: Partial<EditorState>) => {
    setEditor((current) => ({ ...current, ...patch }));
    setSealedPath('');
  };

  const refreshDrafts = async () => {
    setBusy('drafts');
    try {
      const res = await api.adminContentDrafts(token);
      setDrafts(res.items);
    } catch (err: any) {
      toast.error(err?.message || '草稿库读取失败');
    } finally {
      setBusy('');
    }
  };

  const createNew = () => {
    const item = newEditor();
    setEditor(item);
    setPreview(null);
    setSelectedDraft(undefined);
    setSealedPath('');
    setServerSavedAt('');
    toast.success('新内容已创建');
  };

  const loadTemplate = async () => {
    setBusy('template');
    try {
      const item = await api.adminContentTemplate(token);
      setEditor(packageToEditor(item));
      setPreview(item);
      setSelectedDraft(undefined);
      setSealedPath('');
      toast.success('模板已载入');
    } catch (err: any) {
      toast.error(err?.message || '模板载入失败');
    } finally {
      setBusy('');
    }
  };

  const loadSelectedDraft = async () => {
    if (!selectedDraft) return;
    setBusy('load');
    try {
      const item = await api.adminContentDraft(token, selectedDraft);
      setEditor(packageToEditor(item));
      setPreview(item);
      setSealedPath('');
      setServerSavedAt(item.updated_at ? new Date(item.updated_at).toLocaleString() : '');
      toast.success('草稿已打开');
    } catch (err: any) {
      toast.error(err?.message || '草稿打开失败');
    } finally {
      setBusy('');
    }
  };

  const parseFocusBlocks = () => {
    setEditor((current) => applyBodyParsing(current));
    toast.success('重点块已解析');
  };

  const previewContent = async () => {
    setBusy('preview');
    try {
      const payload = buildPayload(editor);
      const res = await api.adminContentPreview(token, payload);
      setPreview(res.item);
      setSealedPath('');
      toast.success('预览已更新');
    } catch (err: any) {
      toast.error(err?.message || '预览失败');
    } finally {
      setBusy('');
    }
  };

  const saveDraft = async () => {
    setBusy('save');
    try {
      const payload = buildPayload(editor);
      const res = await api.adminContentSaveDraft(token, payload);
      setPreview(res.item);
      setServerSavedAt(res.item.updated_at ? new Date(res.item.updated_at).toLocaleString() : new Date().toLocaleString());
      setSealedPath('');
      await refreshDrafts();
      toast.success('草稿已保存');
    } catch (err: any) {
      toast.error(err?.message || '草稿保存失败');
    } finally {
      setBusy('');
    }
  };

  const sealDraft = async () => {
    setBusy('seal');
    try {
      const payload = buildPayload(editor);
      await api.adminContentSaveDraft(token, payload);
      const res = await api.adminContentSeal(token, payload.lesson_id, sealedBy || 'admin');
      setPreview(res.item);
      setSealedPath(res.record.path);
      setServerSavedAt(res.item.updated_at ? new Date(res.item.updated_at).toLocaleString() : new Date().toLocaleString());
      await refreshDrafts();
      downloadJson(res.item);
      toast.success('内容已封存');
    } catch (err: any) {
      toast.error(err?.message || '封存失败');
    } finally {
      setBusy('');
    }
  };

  const exportCurrent = () => {
    try {
      downloadJson(preview || buildPayload(editor));
      toast.success('JSON 已导出');
    } catch (err: any) {
      toast.error(err?.message || '导出失败');
    }
  };

  return (
    <div className="chrono-page" style={{ maxWidth: 1320, margin: '0 auto' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 320px), 1fr))', gap: 16, alignItems: 'end', marginBottom: 18 }}>
        <div>
          <div className="chrono-course-eyeline">
            <span>Admin</span>
            <span>/api/v1/admin/content</span>
          </div>
          <h1 className="chrono-title" style={{ margin: 0 }}>内容编辑器</h1>
        </div>
        <Space wrap style={{ justifyContent: 'flex-end', maxWidth: '100%' }}>
          <Input.Password
            aria-label="Admin token"
            value={token}
            onChange={(event) => rememberToken(event.target.value)}
            style={{ width: 220 }}
          />
          <Input
            aria-label="Sealed by"
            value={sealedBy}
            onChange={(event) => setSealedBy(event.target.value)}
            style={{ width: 140 }}
          />
        </Space>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 420px), 1fr))', gap: 16, alignItems: 'start' }}>
        <section className="chrono-card" style={{ padding: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))', gap: 12 }}>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>课时 ID</div>
              <Input aria-label="课时 ID" value={editor.lesson_id} onChange={(event) => updateEditor({ lesson_id: event.target.value })} />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>课程 ID</div>
              <Input aria-label="课程 ID" value={editor.course_id} onChange={(event) => updateEditor({ course_id: event.target.value })} />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>课程名</div>
              <Input aria-label="课程名" value={editor.course_title} onChange={(event) => updateEditor({ course_title: event.target.value })} />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>标题</div>
              <Input aria-label="课时标题" value={editor.title} onChange={(event) => updateEditor({ title: event.target.value })} />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>单元</div>
              <Input aria-label="单元" value={editor.unit} onChange={(event) => updateEditor({ unit: event.target.value })} />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>时代</div>
              <Input aria-label="时代" value={editor.era} onChange={(event) => updateEditor({ era: event.target.value })} />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>课号</div>
              <Input aria-label="课号" value={editor.lesson_no} onChange={(event) => updateEditor({ lesson_no: event.target.value })} />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>时长</div>
              <Input aria-label="时长" value={editor.duration} onChange={(event) => updateEditor({ duration: event.target.value })} />
            </label>
          </div>

          <Divider style={{ margin: '16px 0 12px' }} />
          <div className="chrono-title" style={{ fontSize: 16, marginBottom: 10 }}>正文</div>
          <TextArea
            aria-label="课文正文"
            value={editor.bodyText}
            onChange={(event) => updateEditor({ bodyText: event.target.value })}
            autoSize={{ minRows: 10, maxRows: 18 }}
            style={{ ...baseInputStyle, fontSize: 15, lineHeight: 1.8 }}
          />

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: 12, marginTop: 14 }}>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>关键词</div>
              <TextArea
                aria-label="关键词"
                value={editor.keywordsText}
                onChange={(event) => updateEditor({ keywordsText: event.target.value })}
                autoSize={{ minRows: 5, maxRows: 9 }}
              />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>重点块</div>
              <TextArea
                aria-label="重点块"
                value={editor.focusText}
                onChange={(event) => updateEditor({ focusText: event.target.value })}
                autoSize={{ minRows: 5, maxRows: 9 }}
              />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>可追问</div>
              <TextArea
                aria-label="可追问"
                value={editor.qaText}
                onChange={(event) => updateEditor({ qaText: event.target.value })}
                autoSize={{ minRows: 5, maxRows: 9 }}
              />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>关卡目标</div>
              <TextArea
                aria-label="关卡目标"
                value={editor.goalsText}
                onChange={(event) => updateEditor({ goalsText: event.target.value })}
                autoSize={{ minRows: 5, maxRows: 9 }}
              />
            </label>
          </div>

          <Divider style={{ margin: '16px 0 12px' }} />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 280px), 1fr))', gap: 12 }}>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>人物</div>
              <TextArea aria-label="人物" value={editor.peopleText} onChange={(event) => updateEditor({ peopleText: event.target.value })} autoSize={{ minRows: 4, maxRows: 8 }} />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>地图点</div>
              <TextArea aria-label="地图点" value={editor.mapText} onChange={(event) => updateEditor({ mapText: event.target.value })} autoSize={{ minRows: 4, maxRows: 8 }} />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>参考资料</div>
              <TextArea aria-label="参考资料" value={editor.sourcesText} onChange={(event) => updateEditor({ sourcesText: event.target.value })} autoSize={{ minRows: 4, maxRows: 8 }} />
            </label>
          </div>

          <details style={{ marginTop: 14 }}>
            <summary className="chrono-course-eyeline">AI 素材</summary>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 240px), 1fr))', gap: 12, marginTop: 10 }}>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>Saga</div>
                <Input aria-label="Saga 标题" value={editor.sagaTitle} onChange={(event) => updateEditor({ sagaTitle: event.target.value })} />
              </label>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>Saga 目标</div>
                <Input aria-label="Saga 目标" value={editor.sagaObjective} onChange={(event) => updateEditor({ sagaObjective: event.target.value })} />
              </label>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>Sandbox</div>
                <Input aria-label="Sandbox 标题" value={editor.sandboxTitle} onChange={(event) => updateEditor({ sandboxTitle: event.target.value })} />
              </label>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>Sandbox 目标</div>
                <Input aria-label="Sandbox 目标" value={editor.sandboxObjective} onChange={(event) => updateEditor({ sandboxObjective: event.target.value })} />
              </label>
            </div>
            <TextArea aria-label="备注" value={editor.teacher_notes} onChange={(event) => updateEditor({ teacher_notes: event.target.value })} autoSize={{ minRows: 3, maxRows: 6 }} style={{ marginTop: 10 }} />
          </details>
        </section>

        <aside className="chrono-card" style={{ padding: 16 }}>
          <Space wrap style={{ marginBottom: 12 }}>
            <Button icon={<FileTextOutlined />} onClick={createNew}>新建</Button>
            <Button icon={<FileTextOutlined />} loading={busy === 'template'} onClick={loadTemplate}>模板</Button>
            <Button icon={<ReloadOutlined />} onClick={parseFocusBlocks}>解析重点</Button>
            <Button icon={<EyeOutlined />} loading={busy === 'preview'} onClick={previewContent}>预览</Button>
            <Button type="primary" icon={<SaveOutlined />} loading={busy === 'save'} onClick={saveDraft}>保存草稿</Button>
            <Button danger icon={<LockOutlined />} loading={busy === 'seal'} onClick={sealDraft}>封存</Button>
            <Button icon={<DownloadOutlined />} onClick={exportCurrent}>导出</Button>
          </Space>

          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <Select
              aria-label="草稿库"
              placeholder="草稿库"
              value={selectedDraft}
              onChange={setSelectedDraft}
              showSearch
              style={{ flex: 1 }}
              options={drafts.map((draft) => ({
                value: draft.lesson_id,
                label: `${draft.title || draft.lesson_id} · ${draft.lesson_id}`,
              }))}
            />
            <Button loading={busy === 'load'} disabled={!selectedDraft} onClick={loadSelectedDraft}>打开</Button>
            <Button icon={<ReloadOutlined />} loading={busy === 'drafts'} onClick={refreshDrafts} />
          </div>

          <Space size={[6, 6]} wrap style={{ marginBottom: 12 }}>
            <Tag color="blue">{editor.lesson_id}</Tag>
            {localSavedAt && <Tag>本地暂存 {localSavedAt}</Tag>}
            {serverSavedAt && <Tag color="green">服务器草稿 {serverSavedAt}</Tag>}
            {preview?.status === 'sealed' && <Tag color="green">sealed v{preview.version}</Tag>}
          </Space>

          {sealedPath && (
            <div style={{ marginBottom: 12 }}>
              <Tag color="green">{sealedPath}</Tag>
              {preview && (
                <div style={{ marginTop: 8 }}>
                  <Link to={`/courses/${preview.course_id || 'C-content-studio'}/lessons/${preview.lesson_id}?layer=watch`}>
                    打开课程页
                  </Link>
                </div>
              )}
            </div>
          )}

          <Divider style={{ margin: '12px 0' }} />
          {preview || currentPayload ? (
            <div style={{ color: 'var(--text-dark)', lineHeight: 1.75 }}>
              <strong>{(preview || currentPayload)?.title || '未命名课时'}</strong>
              <div style={{ color: 'var(--text-mute)', fontSize: 12 }}>
                {(preview || currentPayload)?.unit} · {(preview || currentPayload)?.era}
              </div>
              <Space size={[6, 6]} wrap style={{ marginTop: 12 }}>
                <Tag>正文 {(preview || currentPayload)?.body?.length ?? 0}</Tag>
                <Tag>关键词 {(preview || currentPayload)?.keywords?.length ?? 0}</Tag>
                <Tag>重点 {(preview || currentPayload)?.facts?.length ?? 0}</Tag>
                <Tag>人物 {(preview || currentPayload)?.people?.length ?? 0}</Tag>
                <Tag>资料 {(preview || currentPayload)?.source_refs?.length ?? 0}</Tag>
              </Space>
              <details style={{ marginTop: 14 }}>
                <summary className="chrono-course-eyeline">JSON</summary>
                <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: '10px 0 0', fontSize: 11, color: 'var(--text-mute)' }}>
                  {formatJson(preview || currentPayload)}
                </pre>
              </details>
            </div>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无预览" />
          )}
        </aside>
      </div>
    </div>
  );
}
