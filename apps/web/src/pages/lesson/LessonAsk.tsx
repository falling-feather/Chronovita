import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Input, Spin } from 'antd';
import type { TextAreaRef } from 'antd/es/input/TextArea';
import {
  CheckOutlined,
  DownOutlined,
  ReloadOutlined,
  SendOutlined,
} from '@ant-design/icons';
import type {
  Lesson,
  LessonPresentationResponse,
  PersonCard,
  RagAnswer,
  RagPersonaMode,
} from '../../utils/api';
import { api, streamAsk } from '../../utils/api';
import {
  answerSpeaker,
  friendlyAskError,
} from '../../features/classroom/askPresentation';
import { lessonQuestionSeeds } from '../../features/classroom/classroomModel';
import {
  companionPortraitFor,
  companionPortraitUrl,
} from '../../features/classroom/companionPortraitAssets';
import RagAnswerCard from '../../features/classroom/RagAnswerCard';
import { emitLearningEvent } from '../../features/classroom/learningLedger';
import './LessonAsk.css';

interface LegacyMessage { role: 'user' | 'assistant'; content: string }
interface AskTurn { question: string; answer: RagAnswer }

function PersonaPortrait({ lessonId, person }: { lessonId: string; person: PersonCard | null }) {
  if (!person) return <span className="chrono-ask-scholar-seal" aria-hidden="true">学</span>;
  const asset = companionPortraitFor(lessonId, person);
  if (!asset) return <span className="chrono-ask-scholar-seal" aria-hidden="true">人</span>;
  return (
    <span className="chrono-ask-persona-portrait" aria-hidden="true">
      <img
        src={companionPortraitUrl(asset, 256)}
        srcSet={`${companionPortraitUrl(asset, 256)} 1x, ${companionPortraitUrl(asset, 512)} 2x`}
        alt=""
        draggable={false}
      />
    </span>
  );
}

export default function LessonAsk({
  lesson,
  presentation,
  initialQuestion,
  initialPersonId,
}: {
  lesson: Lesson;
  presentation: LessonPresentationResponse | null;
  initialQuestion?: string;
  initialPersonId?: string;
}) {
  if (!presentation) return <LegacyLessonAsk lesson={lesson} />;
  return (
    <EvidenceLessonAsk
      lesson={lesson}
      initialQuestion={initialQuestion}
      initialPersonId={initialPersonId}
    />
  );
}

function EvidenceLessonAsk({
  lesson,
  initialQuestion,
  initialPersonId,
}: {
  lesson: Lesson;
  initialQuestion?: string;
  initialPersonId?: string;
}) {
  const people = useMemo(
    () => (lesson.people ?? []).filter((person) => Boolean(person.person_id)),
    [lesson.people],
  );
  const seeds = useMemo(() => lessonQuestionSeeds(lesson), [lesson]);
  const initialPerson = people.find((person) => person.person_id === initialPersonId);
  const [persona, setPersona] = useState<RagPersonaMode>(initialPerson ? 'person' : 'expert');
  const [personId, setPersonId] = useState(initialPerson?.person_id ?? people[0]?.person_id ?? '');
  const [question, setQuestion] = useState(initialQuestion || seeds[0] || '');
  const [answers, setAnswers] = useState<AskTurn[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const historyRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<TextAreaRef>(null);
  const personPickerRef = useRef<HTMLDetailsElement>(null);

  const selectedPerson = people.find((person) => person.person_id === personId) ?? people[0] ?? null;

  useEffect(() => {
    setAnswers([]);
    setError('');
    setPersona('expert');
    setPersonId(people[0]?.person_id ?? '');
    setQuestion(seeds[0] ?? '');
  }, [lesson.id]);

  useEffect(() => {
    if (!initialQuestion?.trim()) return;
    setQuestion(initialQuestion.trim());
  }, [initialQuestion]);

  useEffect(() => {
    const nextPerson = people.find((person) => person.person_id === initialPersonId);
    if (!nextPerson?.person_id) return;
    setPersonId(nextPerson.person_id);
    setPersona('person');
  }, [initialPersonId, people]);

  useEffect(() => {
    const history = historyRef.current;
    if (!history || answers.length === 0) return undefined;
    const frame = window.requestAnimationFrame(() => {
      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      history.scrollTo({ top: history.scrollHeight, behavior: reduceMotion ? 'auto' : 'smooth' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [answers.length, loading]);

  const chooseQuestion = (nextQuestion: string) => {
    setQuestion(nextQuestion);
    setError('');
    window.requestAnimationFrame(() => inputRef.current?.focus());
  };

  const choosePerson = (person: PersonCard) => {
    if (!person.person_id) return;
    setPersonId(person.person_id);
    setPersona('person');
    setError('');
    personPickerRef.current?.removeAttribute('open');
  };

  const ask = async () => {
    const prompt = question.trim();
    if (!prompt || loading) return;
    setLoading(true);
    setError('');
    try {
      const answer = await api.ragAsk({
        course_id: lesson.course_id,
        lesson_id: lesson.id,
        persona_mode: persona,
        ...(persona === 'person' && personId ? { person_id: personId } : {}),
        question: prompt,
      });
      setAnswers((current) => [...current, { question: prompt, answer }]);
      const speaker = answerSpeaker(answer, people);
      emitLearningEvent({
        course_id: lesson.course_id,
        lesson_id: lesson.id,
        kind: 'question_answered',
        title: `问${speaker.name}：${prompt}`,
        summary: answer.body,
        metadata: {
          persona: answer.persona_mode,
          citation_count: answer.citations.length,
          supported: answer.answer_source !== 'insufficient_evidence',
        },
      });
      setQuestion('');
      window.requestAnimationFrame(() => inputRef.current?.focus());
    } catch (askError) {
      setError(friendlyAskError(askError));
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="chrono-ask-stage" aria-labelledby="chrono-ask-title">
      <div className="chrono-ask-scroll">
        <header className="chrono-ask-scroll-header">
          <div className="chrono-ask-heading">
            <h2 id="chrono-ask-title">向史证提问</h2>
            <p>问人物，问制度，也问一段叙述能证明什么。</p>
          </div>

          <div className="chrono-ask-persona-shell">
            <div className="chrono-ask-personas" aria-label="选择回答身份">
              <button
                type="button"
                className={persona === 'expert' ? 'active' : undefined}
                aria-pressed={persona === 'expert'}
                onClick={() => { setPersona('expert'); setError(''); }}
              >
                <PersonaPortrait lessonId={lesson.id} person={null} />
                <span><strong>课程学者</strong><small>不采用人物口吻</small></span>
                {persona === 'expert' ? <CheckOutlined /> : null}
              </button>

              {selectedPerson ? (
                <details
                  ref={personPickerRef}
                  className={persona === 'person' ? 'chrono-ask-person-picker active' : 'chrono-ask-person-picker'}
                >
                  <summary aria-label="选择课程人物">
                    <PersonaPortrait lessonId={lesson.id} person={selectedPerson} />
                    <span><strong>{selectedPerson.name}</strong><small>{selectedPerson.role || '课程人物'}</small></span>
                    {persona === 'person' ? <CheckOutlined /> : <DownOutlined />}
                  </summary>
                  <div className="chrono-ask-person-menu" role="listbox" aria-label="本课人物">
                    {people.map((person) => (
                      <button
                        type="button"
                        role="option"
                        aria-selected={persona === 'person' && person.person_id === personId}
                        key={person.person_id}
                        onClick={() => choosePerson(person)}
                      >
                        <PersonaPortrait lessonId={lesson.id} person={person} />
                        <span><strong>{person.name}</strong><small>{person.role || '课程人物'}</small></span>
                      </button>
                    ))}
                  </div>
                </details>
              ) : null}
            </div>
            {persona === 'person' ? <small>角色化教学表达，不是史料原话。</small> : null}
          </div>
        </header>

        <div className="chrono-ask-history" ref={historyRef} aria-live="polite">
          {answers.length === 0 ? (
            <div className="chrono-ask-empty">
              <span aria-hidden="true">问</span>
              <strong>从真正好奇的地方开始</strong>
              <p>材料能支持什么、不能证明什么，都可以追问。</p>
            </div>
          ) : answers.map((item, index) => {
            const speaker = answerSpeaker(item.answer, people);
            return (
              <section className="chrono-ask-turn" key={`${item.answer.evidence_checksum}-${index}`}>
                <aside className="chrono-ask-question">
                  <span>我问</span>
                  <p>{item.question}</p>
                </aside>
                <RagAnswerCard
                  answer={item.answer}
                  speakerName={speaker.name}
                  speakerRole={speaker.role}
                  defaultCitationsOpen={index === answers.length - 1}
                />
              </section>
            );
          })}
          {loading ? (
            <div className="chrono-ask-loading">
              <i aria-hidden="true" />
              <span>正在翻检本课材料，核对能够采用的依据…</span>
            </div>
          ) : null}
        </div>

        {error ? (
          <div className="chrono-ask-error" role="alert">
            <span>{error}</span>
            <button type="button" onClick={() => setError('')}>知道了</button>
          </div>
        ) : null}

        <form
          className="chrono-ask-composer"
          onSubmit={(event) => { event.preventDefault(); void ask(); }}
        >
          <div className="chrono-ask-bookmarks" aria-label="可以从这些问题开始">
            {seeds.slice(0, 3).map((seed) => (
              <button key={seed} type="button" onClick={() => chooseQuestion(seed)}>{seed}</button>
            ))}
          </div>
          <div className="chrono-ask-writing-strip">
            <label htmlFor="chrono-ask-input">写下你的问题</label>
            <Input.TextArea
              ref={inputRef}
              id="chrono-ask-input"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onPressEnter={(event) => {
                if (!event.shiftKey) {
                  event.preventDefault();
                  void ask();
                }
              }}
              autoSize={{ minRows: 2, maxRows: 5 }}
              maxLength={400}
              placeholder="写下你真正想追问的事…"
            />
            <Button
              className="chrono-ask-send"
              type="primary"
              htmlType="submit"
              icon={<SendOutlined />}
              loading={loading}
              disabled={!question.trim()}
            >
              发问
            </Button>
          </div>
          <small>Enter 发问 · Shift + Enter 换行</small>
        </form>
      </div>
    </section>
  );
}

function LegacyLessonAsk({ lesson }: { lesson: Lesson }) {
  const [history, setHistory] = useState<LegacyMessage[]>([
    {
      role: 'assistant',
      content: `“${lesson.title}”的逐条材料仍在整理。这里的回答只用于启发追问，不会冒充已经核验的历史结论。`,
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput('');
    setHistory((current) => [...current, { role: 'user', content: text }, { role: 'assistant', content: '' }]);
    setLoading(true);
    try {
      await streamAsk(
        {
          user_message: text,
          persona: 'expert',
          lesson_id: lesson.id,
          lesson_title: lesson.title,
          history: history.slice(-6),
        },
        (chunk) => setHistory((current) => {
          const last = current.at(-1);
          if (!last || last.role !== 'assistant') return current;
          return [...current.slice(0, -1), { ...last, content: last.content + chunk }];
        }),
      );
    } catch (sendError) {
      setHistory((current) => [
        ...current.slice(0, -1),
        { role: 'assistant', content: friendlyAskError(sendError) },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="chrono-ask-stage is-legacy" aria-labelledby="chrono-legacy-ask-title">
      <div className="chrono-ask-scroll">
        <header className="chrono-ask-scroll-header">
          <div className="chrono-ask-heading">
            <h2 id="chrono-legacy-ask-title">围绕本课继续追问</h2>
            <p>本课证据夹页尚未开放，回答只用于启发思考。</p>
          </div>
        </header>
        <div className="chrono-legacy-ask-history" aria-live="polite">
          {history.map((message, index) => (
            <div key={index} className={`chrono-legacy-turn ${message.role}`}>
              {message.content || (loading ? <Spin size="small" /> : '')}
            </div>
          ))}
        </div>
        <form className="chrono-ask-composer" onSubmit={(event) => { event.preventDefault(); void send(); }}>
          <div className="chrono-ask-writing-strip">
            <label htmlFor="chrono-legacy-ask-input">写下你的问题</label>
            <Input.TextArea
              id="chrono-legacy-ask-input"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              autoSize={{ minRows: 2, maxRows: 5 }}
              maxLength={400}
              placeholder="先写下你想弄清楚的问题…"
              onPressEnter={(event) => {
                if (!event.shiftKey) { event.preventDefault(); void send(); }
              }}
            />
            <Button type="primary" htmlType="submit" icon={<SendOutlined />} loading={loading} disabled={!input.trim()}>
              发问
            </Button>
            <Button icon={<ReloadOutlined />} onClick={() => setHistory((current) => current.slice(0, 1))}>
              清空
            </Button>
          </div>
        </form>
      </div>
    </section>
  );
}
