import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Input, Select, Tag } from 'antd';
import { MessageOutlined, SendOutlined, TeamOutlined } from '@ant-design/icons';
import type {
  Lesson,
  LessonPresentationResponse,
  RagAnswer,
  RagPersonaMode,
} from '../../utils/api';
import { api } from '../../utils/api';
import { lessonQuestionSeeds } from './classroomModel';
import RagAnswerCard from './RagAnswerCard';

const EXPERT_VALUE = '__expert__';

export default function LessonCompanion({
  lesson,
  presentation,
  onOpenConsult,
}: {
  lesson: Lesson;
  presentation: LessonPresentationResponse | null;
  onOpenConsult: (question?: string, personId?: string) => void;
}) {
  const seeds = useMemo(() => lessonQuestionSeeds(lesson), [lesson]);
  const people = useMemo(
    () => (lesson.people ?? []).filter((person) => Boolean(person.person_id)),
    [lesson.people],
  );
  const [speaker, setSpeaker] = useState(EXPERT_VALUE);
  const [question, setQuestion] = useState(seeds[0] ?? '');
  const [answer, setAnswer] = useState<RagAnswer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setSpeaker(EXPERT_VALUE);
    setQuestion(seeds[0] ?? '');
    setAnswer(null);
    setError('');
  }, [lesson.id, seeds]);

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
      setError(askError instanceof Error ? askError.message.replace(/^\d{3}\s+/, '') : '证据问答暂不可用');
    } finally {
      setLoading(false);
    }
  };

  return (
    <aside className="chrono-companion" aria-label="随行助教">
      <header>
        <div className="chrono-companion-mark"><MessageOutlined /></div>
        <div>
          <strong>随行助教</strong>
          <span>{presentation ? '只依据当前发布课程作答' : '当前课时使用兼容问答'}</span>
        </div>
      </header>

      {!presentation ? (
        <Alert
          type="info"
          showIcon
          message="本课尚未绑定证据库"
          description="可进入召见阶段使用兼容问答。"
          action={<Button size="small" onClick={() => onOpenConsult()}>进入召见</Button>}
        />
      ) : (
        <>
          <label className="chrono-companion-field">
            <span><TeamOutlined /> 召见对象</span>
            <Select
              size="small"
              value={speaker}
              onChange={(value) => { setSpeaker(value); setAnswer(null); }}
              options={[
                { value: EXPERT_VALUE, label: '课程专家' },
                ...people.map((person) => ({
                  value: person.person_id!,
                  label: `${person.name}${person.role ? ` · ${person.role}` : ''}`,
                })),
              ]}
            />
          </label>
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
            placeholder="追问材料、人物或制度代价"
          />
          <Button
            block
            type="primary"
            icon={<SendOutlined />}
            loading={loading}
            disabled={!question.trim()}
            onClick={() => void ask()}
          >
            依据证据回答
          </Button>
          {error ? <Alert type="warning" showIcon message={error} /> : null}
          {answer ? <RagAnswerCard answer={answer} compact /> : (
            <div className="chrono-companion-boundary">
              <Tag>当前发布 #{presentation.release_no}</Tag>
              <p>无足够片段时会明确返回“依据不足”，不会用模型常识补写。</p>
            </div>
          )}
          <Button
            type="link"
            onClick={() => onOpenConsult(question, speaker === EXPERT_VALUE ? undefined : speaker)}
          >
            在召见阶段展开查看 →
          </Button>
        </>
      )}
    </aside>
  );
}
