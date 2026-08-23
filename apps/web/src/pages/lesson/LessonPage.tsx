import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Alert, Button, Spin } from 'antd';
import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { api, type Lesson, type LessonPresentationResponse } from '../../utils/api';
import {
  CLASSROOM_STAGES,
  classroomStage,
  presentationStageDuration,
  type ClassroomLayer,
} from '../../features/classroom/classroomModel';
import LessonCompanion from '../../features/classroom/LessonCompanion';
import CourseCoverPicture from '../../features/courses/CourseCoverPicture';
import LessonWatch, { LessonWatchMedia } from './LessonWatch';
import LessonAsk from './LessonAsk';
import LessonPractice from './LessonPractice';

const LessonCreate = lazy(() => import('./LessonCreate'));
const VALID_LAYERS = new Set(CLASSROOM_STAGES.map((stage) => stage.layer));

export default function LessonPage() {
  const { courseId = '', lessonId = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const requestedLayer = params.get('layer');
  const layer = (VALID_LAYERS.has(requestedLayer as ClassroomLayer) ? requestedLayer : 'watch') as ClassroomLayer;
  const nav = useNavigate();
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [presentation, setPresentation] = useState<LessonPresentationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    Promise.all([
      api.lesson(courseId, lessonId),
      api.lessonPresentation(courseId, lessonId).catch(() => null),
    ]).then(([nextLesson, nextPresentation]) => {
      if (!active) return;
      setLesson(nextLesson);
      setPresentation(nextPresentation);
    }).catch((loadError) => {
      if (!active) return;
      setLesson(null);
      setPresentation(null);
      setError(loadError instanceof Error ? loadError.message.replace(/^\d{3}\s+/, '') : '课时载入失败');
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [courseId, lessonId]);

  useEffect(() => {
    if (!lessonId) return;
    api.progressTouch({ lesson_id: lessonId, layer }).catch(() => {});
  }, [lessonId, layer]);

  const openLayer = useCallback((nextLayer: ClassroomLayer, options?: { question?: string; personId?: string }) => {
    setParams((current) => {
      const next = new URLSearchParams(current);
      next.set('layer', nextLayer);
      if (options?.question) next.set('question', options.question);
      else next.delete('question');
      if (options?.personId) next.set('person', options.personId);
      else next.delete('person');
      return next;
    }, { replace: true });
  }, [setParams]);

  const activeStage = classroomStage(layer);
  const stageIndex = CLASSROOM_STAGES.findIndex((stage) => stage.layer === layer);
  const nextStage = CLASSROOM_STAGES[stageIndex + 1];
  const previousStage = CLASSROOM_STAGES[stageIndex - 1];

  const content = useMemo(() => {
    if (!lesson) return null;
    if (layer === 'watch') return <LessonWatch lesson={lesson} />;
    if (layer === 'practice') {
      return <LessonPractice lesson={lesson} onOpenDossier={() => openLayer('create')} />;
    }
    if (layer === 'ask') {
      return (
        <LessonAsk
          lesson={lesson}
          presentation={presentation}
          initialQuestion={params.get('question') ?? undefined}
          initialPersonId={params.get('person') ?? undefined}
        />
      );
    }
    return (
      <Suspense fallback={<div className="chrono-create-loading"><Spin /></div>}>
        <LessonCreate
          key={lesson.id}
          lesson={lesson}
          active
          onOpenPractice={() => openLayer('practice')}
        />
      </Suspense>
    );
  }, [layer, lesson, openLayer, params, presentation]);

  if (loading) return <div className="chrono-page-loading"><Spin /><span>正在核对课时发布…</span></div>;
  if (!lesson) {
    return <Alert type="error" showIcon message="课时暂不可用" description={error || '没有找到当前课时。'} />;
  }

  return (
    <div className="chrono-lesson-classroom">
      <button className="chrono-back-link" type="button" onClick={() => nav(`/courses/${courseId}`)}>
        <ArrowLeftOutlined /> 返回课程路线
      </button>

      <header className="chrono-lesson-masthead">
        <CourseCoverPicture
          courseId={lesson.course_id || courseId}
          width={1440}
          eager
          fallbackColor="#354b50"
          className="chrono-lesson-masthead-art"
        />
        <div className="chrono-lesson-masthead-copy">
          <h1>{lesson.title}</h1>
          <span>{lesson.num} · {lesson.era || lesson.unit}</span>
          <p>{lesson.abstract}</p>
        </div>
        <div className="chrono-lesson-release">
          {presentation ? (
            <>
              <SafetyCertificateOutlined />
              <div>
                <strong>正式课堂资料</strong>
                <span>课文、短片、情境与依据已完成校验</span>
              </div>
              <span className="chrono-lesson-release-state">可学习</span>
            </>
          ) : (
            <>
              <ClockCircleOutlined />
              <div><strong>基础课堂资料</strong><span>沿用四阶段学习流程</span></div>
            </>
          )}
        </div>
      </header>

      {layer === 'watch' ? <LessonWatchMedia lesson={lesson} presentation={presentation} /> : null}

      <nav className="chrono-stage-rail" aria-label="课堂四阶段">
        {CLASSROOM_STAGES.map((stage) => {
          const active = stage.layer === layer;
          const visited = stage.index < activeStage.index;
          return (
            <button
              key={stage.layer}
              type="button"
              className={`${active ? 'active' : ''}${visited ? ' visited' : ''}`}
              aria-current={active ? 'step' : undefined}
              onClick={() => openLayer(stage.layer)}
            >
              <span className="chrono-stage-number">{visited ? <CheckCircleOutlined /> : stage.index}</span>
              <span><strong>{stage.title}</strong><small>{stage.verb}</small></span>
              <time>{presentationStageDuration(stage, presentation)}</time>
            </button>
          );
        })}
      </nav>

      <div className={`chrono-lesson-workspace${layer === 'ask' ? ' consult-wide' : ''}${layer === 'watch' ? ' observe-wide' : ''}`}>
        <main>{content}</main>
        {layer !== 'ask' && layer !== 'watch' ? (
          <LessonCompanion
            lesson={lesson}
            presentation={presentation}
            onOpenConsult={(question, personId) => openLayer('ask', { question, personId })}
          />
        ) : null}
      </div>

      <footer className="chrono-stage-footer">
        <div>
          <span>当前阶段</span>
          <strong>{activeStage.title} · {activeStage.purpose}</strong>
        </div>
        <div>
          {previousStage ? (
            <Button onClick={() => openLayer(previousStage.layer)}>
              <ArrowLeftOutlined /> {previousStage.title}
            </Button>
          ) : null}
          {nextStage ? (
            <Button type="primary" onClick={() => openLayer(nextStage.layer)}>
              进入{nextStage.title} <ArrowRightOutlined />
            </Button>
          ) : null}
        </div>
      </footer>
    </div>
  );
}
