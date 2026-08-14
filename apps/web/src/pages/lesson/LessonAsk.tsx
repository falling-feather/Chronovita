import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Input, Radio, Select, Spin, Tag } from 'antd';
import {
  BookOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SendOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import type {
  Lesson,
  LessonPresentationResponse,
  RagAnswer,
  RagPersonaMode,
} from '../../utils/api';
import { api, streamAsk } from '../../utils/api';
import { lessonQuestionSeeds } from '../../features/classroom/classroomModel';
import RagAnswerCard from '../../features/classroom/RagAnswerCard';

interface LegacyMessage { role: 'user' | 'assistant'; content: string }

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
      presentation={presentation}
      initialQuestion={initialQuestion}
      initialPersonId={initialPersonId}
    />
  );
}

function EvidenceLessonAsk({
  lesson,
  presentation,
  initialQuestion,
  initialPersonId,
}: {
  lesson: Lesson;
  presentation: LessonPresentationResponse;
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
  const [answers, setAnswers] = useState<Array<{ question: string; answer: RagAnswer }>>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setAnswers([]);
    setError('');
  }, [lesson.id]);

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
        ...(persona === 'person' ? { person_id: personId } : {}),
        question: prompt,
      });
      setAnswers((current) => [...current, { question: prompt, answer }]);
      setQuestion('');
    } catch (askError) {
      setError(askError instanceof Error ? askError.message.replace(/^\d{3}\s+/, '') : '证据问答暂不可用');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="chrono-consult-layout">
      <section className="chrono-consult-main">
        <header>
          <div>
            <Tag color="gold" icon={<BookOutlined />}>结构化 RAG</Tag>
            <h2>依据当前课程证据回答</h2>
            <p>服务端锁定课程、课时与当前发布；回答只能引用本次召回片段。</p>
          </div>
          <div className="chrono-consult-release">
            <SafetyCertificateOutlined />
            <span>发布 #{presentation.release_no}</span>
            <code>{presentation.release_checksum.slice(0, 10)}</code>
          </div>
        </header>

        <div className="chrono-consult-history" aria-live="polite">
          {answers.length === 0 ? (
            <div className="chrono-consult-empty">
              <BookOutlined />
              <strong>先从一条可核验的问题开始</strong>
              <span>你会看到回答、引用片段、来源、发布版本与不确定性。</span>
            </div>
          ) : answers.map((item, index) => (
            <div className="chrono-consult-turn" key={`${item.answer.release_checksum}-${index}`}>
              <div className="chrono-consult-question"><span>我的追问</span><p>{item.question}</p></div>
              <RagAnswerCard answer={item.answer} />
            </div>
          ))}
          {loading ? <div className="chrono-consult-loading"><Spin /><span>正在召回并核对引用…</span></div> : null}
        </div>

        {error ? <Alert type="warning" showIcon closable message={error} onClose={() => setError('')} /> : null}

        <form
          className="chrono-consult-composer"
          onSubmit={(event) => { event.preventDefault(); void ask(); }}
        >
          <div className="chrono-consult-mode">
            <Radio.Group
              value={persona}
              onChange={(event) => setPersona(event.target.value)}
              optionType="button"
              buttonStyle="solid"
              options={[
                { label: '课程专家', value: 'expert' },
                { label: '课程人物 / 群体', value: 'person', disabled: people.length === 0 },
              ]}
            />
            {persona === 'person' ? (
              <Select
                value={personId}
                onChange={setPersonId}
                aria-label="选择课程人物"
                options={people.map((person) => ({
                  value: person.person_id!,
                  label: `${person.name} · ${person.role || '课程人物'}`,
                }))}
              />
            ) : null}
          </div>
          <div className="chrono-consult-input">
            <Input.TextArea
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
              showCount
              placeholder="追问史料边界、选择代价或人物立场"
            />
            <Button type="primary" htmlType="submit" icon={<SendOutlined />} loading={loading} disabled={!question.trim()}>
              提问
            </Button>
          </div>
        </form>
      </section>

      <aside className="chrono-consult-aside">
        <section>
          <h3>建议追问</h3>
          {seeds.map((seed) => (
            <button key={seed} type="button" onClick={() => setQuestion(seed)}>{seed}</button>
          ))}
        </section>
        <section>
          <h3><TeamOutlined /> 人物知识边界</h3>
          {persona === 'person' ? (
            <>
              <strong>{people.find((person) => person.person_id === personId)?.name}</strong>
              <p>{people.find((person) => person.person_id === personId)?.summary}</p>
              <ul>
                {(people.find((person) => person.person_id === personId)?.boundaries ?? []).slice(0, 3).map((boundary) => (
                  <li key={boundary}>{boundary}</li>
                ))}
              </ul>
              <Alert type="info" showIcon message="角色化教学表达，不是史料原话。" />
            </>
          ) : <p>专家模式仍只依据当前课程证据，不使用模型常识补写。</p>}
        </section>
      </aside>
    </div>
  );
}

function LegacyLessonAsk({ lesson }: { lesson: Lesson }) {
  const [history, setHistory] = useState<LegacyMessage[]>([
    { role: 'assistant', content: `当前课时尚未绑定证据库。我会通过兼容问答围绕“${lesson.title}”回应，并明确这是旧课程路径。` },
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
    } catch (error) {
      setHistory((current) => {
        const message = error instanceof Error ? error.message : '兼容问答不可用';
        return [...current.slice(0, -1), { role: 'assistant', content: message }];
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="chrono-legacy-ask chrono-card">
      <Alert
        type="info"
        showIcon
        message="兼容课程问答"
        description="本课未绑定 V3 证据库，因此不会显示结构化引用卡。L101、L103 及以后具备证据库的课程使用正式 RAG。"
      />
      <div className="chrono-legacy-ask-history">
        {history.map((message, index) => (
          <div key={index} className={message.role}>{message.content || (loading ? <Spin size="small" /> : '')}</div>
        ))}
      </div>
      <div className="chrono-consult-input">
        <Input.TextArea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          autoSize={{ minRows: 2, maxRows: 5 }}
          onPressEnter={(event) => { if (!event.shiftKey) { event.preventDefault(); void send(); } }}
        />
        <Button type="primary" icon={<SendOutlined />} onClick={() => void send()} loading={loading}>提问</Button>
        <Button icon={<ReloadOutlined />} onClick={() => setHistory(history.slice(0, 1))}>清空</Button>
      </div>
    </div>
  );
}
