import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Input } from 'antd';
import {
  BookOutlined,
  CheckOutlined,
  CloseOutlined,
  EditOutlined,
  LoadingOutlined,
  MessageOutlined,
  SendOutlined,
} from '@ant-design/icons';
import { useAuth } from '../../auth/AuthContext';
import type {
  Lesson,
  LessonPresentationResponse,
  PersonCard,
  RagAnswer,
  RagPersonaMode,
} from '../../utils/api';
import { api } from '../../utils/api';
import { lessonQuestionSeeds } from './classroomModel';
import {
  companionPortraitFor,
  companionPortraitUrl,
  type CompanionPortraitAsset,
} from './companionPortraitAssets';
import RagAnswerCard from './RagAnswerCard';
import {
  TEMPORARY_NOTEBOOK_EVENT,
  TEMPORARY_NOTEBOOK_MAX_LENGTH,
  clearTemporaryNotebook,
  readTemporaryNotebook,
  temporaryNotebookStorageKey,
  writeTemporaryNotebook,
  type TemporaryNotebookIdentity,
} from './temporaryNotebook';

const EXPERT_VALUE = '__expert__';
type CompanionPane = 'ask' | 'notebook';
type NoteStatus = 'idle' | 'saving' | 'saved' | 'error';

function CompanionFigure({
  asset,
  name,
  compact = false,
}: {
  asset: CompanionPortraitAsset | null;
  name: string;
  compact?: boolean;
}) {
  if (!asset) {
    return <span className={`chrono-companion-seal${compact ? ' compact' : ''}`} aria-hidden="true">问</span>;
  }
  return (
    <img
      className={compact ? 'compact' : undefined}
      src={companionPortraitUrl(asset, 256)}
      srcSet={`${companionPortraitUrl(asset, 256)} 1x, ${companionPortraitUrl(asset, 512)} 2x`}
      alt={asset.alt || `${name}教学立绘`}
      draggable={false}
    />
  );
}

function speakerName(person: PersonCard | null): string {
  return person?.name || '课程向导';
}

export default function LessonCompanion({
  lesson,
  presentation,
  onOpenConsult,
}: {
  lesson: Lesson;
  presentation: LessonPresentationResponse | null;
  onOpenConsult: (question?: string, personId?: string) => void;
}) {
  const auth = useAuth();
  const seeds = useMemo(() => lessonQuestionSeeds(lesson), [lesson]);
  const people = useMemo(
    () => (lesson.people ?? []).filter((person) => Boolean(person.person_id)),
    [lesson.people],
  );
  const defaultSpeaker = people[0]?.person_id ?? EXPERT_VALUE;
  const ownerId = auth.principal?.user_id ?? (auth.mode === 'legacy-local' ? 'legacy-local' : 'anonymous');
  const noteIdentity = useMemo<TemporaryNotebookIdentity>(() => ({
    ownerId,
    courseId: lesson.course_id,
    lessonId: lesson.id,
  }), [lesson.course_id, lesson.id, ownerId]);
  const noteIdentityKey = useMemo(
    () => temporaryNotebookStorageKey(noteIdentity),
    [noteIdentity],
  );

  const [open, setOpen] = useState(false);
  const [pane, setPane] = useState<CompanionPane>('ask');
  const [speaker, setSpeaker] = useState(defaultSpeaker);
  const [question, setQuestion] = useState(seeds[0] ?? '');
  const [answer, setAnswer] = useState<RagAnswer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const [noteStatus, setNoteStatus] = useState<NoteStatus>('idle');
  const [loadedNoteKey, setLoadedNoteKey] = useState('');

  const selectedPerson = people.find((person) => person.person_id === speaker) ?? null;
  const selectedAsset = selectedPerson ? companionPortraitFor(lesson.id, selectedPerson) : null;
  const selectedName = speakerName(selectedPerson);

  useEffect(() => {
    setSpeaker(defaultSpeaker);
    setQuestion(seeds[0] ?? '');
    setAnswer(null);
    setError('');
    setOpen(false);
    setPane('ask');
  }, [defaultSpeaker, lesson.id, seeds]);

  useEffect(() => {
    const record = readTemporaryNotebook(window.localStorage, noteIdentity);
    setNote(record?.body ?? '');
    setNoteStatus(record ? 'saved' : 'idle');
    setLoadedNoteKey(noteIdentityKey);
  }, [noteIdentity, noteIdentityKey]);

  useEffect(() => {
    if (loadedNoteKey !== noteIdentityKey) return undefined;
    setNoteStatus('saving');
    const timer = window.setTimeout(() => {
      if (!note.trim()) {
        const cleared = clearTemporaryNotebook(window.localStorage, noteIdentity);
        setNoteStatus(cleared ? 'idle' : 'error');
        window.dispatchEvent(new CustomEvent(TEMPORARY_NOTEBOOK_EVENT));
        return;
      }
      const result = writeTemporaryNotebook(window.localStorage, noteIdentity, note);
      setNoteStatus(result.persisted ? 'saved' : 'error');
      window.dispatchEvent(new CustomEvent(TEMPORARY_NOTEBOOK_EVENT, {
        detail: result.record,
      }));
    }, 260);
    return () => window.clearTimeout(timer);
  }, [loadedNoteKey, note, noteIdentity, noteIdentityKey]);

  useEffect(() => {
    if (!open) return undefined;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [open]);

  const changeSpeaker = (value: string) => {
    setSpeaker(value);
    setAnswer(null);
    setError('');
    setPane('ask');
  };

  const ask = async () => {
    const prompt = question.trim();
    if (!prompt || loading || !presentation) return;
    const personaMode: RagPersonaMode = speaker === EXPERT_VALUE ? 'expert' : 'person';
    setLoading(true);
    setError('');
    try {
      const result = await api.ragAsk({
        course_id: lesson.course_id,
        lesson_id: lesson.id,
        persona_mode: personaMode,
        ...(personaMode === 'person' ? { person_id: speaker } : {}),
        question: prompt,
      });
      setAnswer(result);
    } catch (askError) {
      setError(askError instanceof Error
        ? askError.message.replace(/^\d{3}\s+/, '')
        : '当前问答暂不可用，请稍后再试。');
    } finally {
      setLoading(false);
    }
  };

  return (
    <aside className={`chrono-companion-float${open ? ' is-open' : ''}`} aria-label="随行助教与临时笔记">
      {!open ? (
        <button
          type="button"
          className="chrono-companion-launcher"
          aria-label={`打开${selectedName}随行助教`}
          aria-expanded="false"
          aria-controls="chrono-companion-panel"
          onClick={() => setOpen(true)}
        >
          <span className="chrono-companion-launcher-figure">
            <CompanionFigure asset={selectedAsset} name={selectedName} />
          </span>
          <span className="chrono-companion-launcher-copy">
            <small><MessageOutlined /> 随行助教</small>
            <strong>{selectedName}</strong>
          </span>
          {note.trim() ? <span className="chrono-companion-note-dot" title="本课已有临时笔记"><EditOutlined /></span> : null}
        </button>
      ) : (
        <section
          id="chrono-companion-panel"
          className="chrono-companion-panel"
          role="dialog"
          aria-modal="false"
          aria-label={`${selectedName}随行助教`}
        >
          <header className="chrono-companion-panel-header">
            <div className="chrono-companion-panel-figure">
              <CompanionFigure asset={selectedAsset} name={selectedName} />
            </div>
            <div className="chrono-companion-panel-title">
              <span>随行助教 · 教学角色</span>
              <strong>{selectedName}</strong>
              <p>{selectedPerson?.role || '依据本课材料帮助你辨析问题'}</p>
            </div>
            <button type="button" className="chrono-companion-close" aria-label="收起随行助教" onClick={() => setOpen(false)}>
              <CloseOutlined />
            </button>
          </header>

          <div className="chrono-companion-personas" role="list" aria-label="切换助教身份">
            {people.map((person) => {
              const asset = companionPortraitFor(lesson.id, person);
              const active = person.person_id === speaker;
              return (
                <button
                  type="button"
                  role="listitem"
                  key={person.person_id}
                  className={active ? 'active' : undefined}
                  aria-pressed={active}
                  title={`${person.name}${person.role ? ` · ${person.role}` : ''}`}
                  onClick={() => changeSpeaker(person.person_id!)}
                >
                  <span><CompanionFigure asset={asset} name={person.name} compact /></span>
                  <small>{person.name.replace(/（.*?）/g, '')}</small>
                </button>
              );
            })}
            <button
              type="button"
              role="listitem"
              className={speaker === EXPERT_VALUE ? 'active' : undefined}
              aria-pressed={speaker === EXPERT_VALUE}
              title="课程向导 · 不采用人物口吻"
              onClick={() => changeSpeaker(EXPERT_VALUE)}
            >
              <span><CompanionFigure asset={null} name="课程向导" compact /></span>
              <small>向导</small>
            </button>
          </div>

          <nav className="chrono-companion-tabs" aria-label="助教功能">
            <button type="button" className={pane === 'ask' ? 'active' : undefined} onClick={() => setPane('ask')}>
              <MessageOutlined /> 问一问
            </button>
            <button type="button" className={pane === 'notebook' ? 'active' : undefined} onClick={() => setPane('notebook')}>
              <EditOutlined /> 临时笔记 {note.trim() ? <i /> : null}
            </button>
          </nav>

          {pane === 'ask' ? (
            <div className="chrono-companion-pane chrono-companion-ask-pane">
              {!presentation ? (
                <div className="chrono-companion-simple-state">
                  <BookOutlined />
                  <strong>本课使用基础问答</strong>
                  <p>进入“召见”阶段继续提问。</p>
                  <Button onClick={() => onOpenConsult()}>前往召见</Button>
                </div>
              ) : (
                <>
                  <div className="chrono-companion-seeds">
                    {seeds.slice(0, 2).map((seed) => (
                      <button key={seed} type="button" onClick={() => { setQuestion(seed); setAnswer(null); }}>
                        {seed}
                      </button>
                    ))}
                  </div>
                  <Input.TextArea
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    onPressEnter={(event) => {
                      if (!event.shiftKey) {
                        event.preventDefault();
                        void ask();
                      }
                    }}
                    autoSize={{ minRows: 2, maxRows: 4 }}
                    maxLength={400}
                    placeholder={`向${selectedName}追问本课人物、材料或选择代价`}
                  />
                  <Button
                    block
                    type="primary"
                    icon={<SendOutlined />}
                    loading={loading}
                    disabled={!question.trim()}
                    onClick={() => void ask()}
                  >
                    提问
                  </Button>
                  {selectedPerson ? <small className="chrono-companion-role-note">角色化教学表达，不是史料原话。</small> : null}
                  {error ? <Alert type="warning" showIcon message={error} /> : null}
                  <div className="chrono-companion-answer" aria-live="polite">
                    {answer ? <RagAnswerCard answer={answer} compact /> : null}
                  </div>
                  <button
                    type="button"
                    className="chrono-companion-expand-link"
                    onClick={() => onOpenConsult(question, speaker === EXPERT_VALUE ? undefined : speaker)}
                  >
                    在“召见”中展开对话 →
                  </button>
                </>
              )}
            </div>
          ) : (
            <div className="chrono-companion-pane chrono-companion-notebook-pane">
              <header>
                <div>
                  <strong>本课随手记</strong>
                  <span>切换阶段不会丢失，进入“卷宗”后会直接出现。</span>
                </div>
                <span className={`chrono-note-status ${noteStatus}`} aria-live="polite">
                  {noteStatus === 'saving' ? <><LoadingOutlined spin /> 保存中</> : null}
                  {noteStatus === 'saved' ? <><CheckOutlined /> 已存本机</> : null}
                  {noteStatus === 'error' ? '本机保存失败' : null}
                  {noteStatus === 'idle' ? '等待记录' : null}
                </span>
              </header>
              <Input.TextArea
                value={note}
                onChange={(event) => setNote(event.target.value)}
                rows={11}
                maxLength={TEMPORARY_NOTEBOOK_MAX_LENGTH}
                showCount
                placeholder="记下疑问、证据、选择理由或稍后想写进卷宗的话……"
              />
              <p>仅保存在当前浏览器，并按账号与课时分开；不会因为助教问答失败而丢失。</p>
            </div>
          )}
        </section>
      )}
    </aside>
  );
}
