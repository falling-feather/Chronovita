import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Tabs, Spin } from 'antd';
import { api, type Lesson } from '../../utils/api';
import LessonWatch from './LessonWatch';
import LessonAsk from './LessonAsk';
import LessonPractice from './LessonPractice';
import LessonCreate from './LessonCreate';

const LAYERS = [
  { key: 'watch',    label: '看 · 沉浸叙事' },
  { key: 'practice', label: '练 · 决策沙盘' },
  { key: 'ask',      label: '问 · 跨时对话' },
  { key: 'create',   label: '创 · 知识画板' },
];

export default function LessonPage() {
  const { courseId = '', lessonId = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const layer = params.get('layer') || 'watch';
  const nav = useNavigate();
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.lesson(courseId, lessonId).then(setLesson).finally(() => setLoading(false));
  }, [courseId, lessonId]);

  // 学习进度打点：每次 lessonId 或 layer 变更，touch 一次
  useEffect(() => {
    if (!lessonId) return;
    api.progressTouch({ lesson_id: lessonId, layer: layer as any }).catch(() => {});
  }, [lessonId, layer]);

  const items = useMemo(() => LAYERS.map((l) => ({
    key: l.key,
    label: l.label,
    children: !lesson ? null :
      l.key === 'watch'    ? <LessonWatch lesson={lesson} /> :
      l.key === 'practice' ? <LessonPractice lesson={lesson} /> :
      l.key === 'ask'      ? <LessonAsk lesson={lesson} /> :
                              <LessonCreate lesson={lesson} />,
  })), [lesson]);

  if (loading || !lesson) return <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>;

  return (
    <div style={{ maxWidth: 1392, margin: '0 auto' }}>
      <div style={{ marginBottom: 12 }}>
        <a onClick={() => nav(`/courses/${courseId}`)} style={{ color: 'var(--text-mute)', fontSize: 12 }}>
          ← 返回课程详情
        </a>
      </div>
      <Tabs
        size="large"
        activeKey={layer}
        onChange={(k) => {
          const next = new URLSearchParams(params);
          next.set('layer', k);
          setParams(next, { replace: true });
        }}
        items={items}
      />
    </div>
  );
}
