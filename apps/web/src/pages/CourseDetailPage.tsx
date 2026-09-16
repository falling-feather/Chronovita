import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Alert, Button, Spin } from 'antd';
import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  CheckOutlined,
  ClockCircleOutlined,
  EnvironmentOutlined,
} from '@ant-design/icons';
import type { CourseDetail, ProgressItem } from '../utils/api';
import { api } from '../utils/api';
import { CLASSROOM_STAGES } from '../features/classroom/classroomModel';
import CourseCoverPicture from '../features/courses/CourseCoverPicture';
import { readingComplete, readingLabel, resumeLayer } from '../features/classroom/readingProgress';

export default function CourseDetailPage() {
  const { courseId = '' } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState<CourseDetail | null>(null);
  const [progress, setProgress] = useState<ProgressItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [progressUnavailable, setProgressUnavailable] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    setProgressUnavailable(false);
    Promise.all([
      api.course(courseId),
      api.progressList().then((response) => response.items).catch(() => {
        if (active) setProgressUnavailable(true);
        return [];
      }),
    ]).then(([course, items]) => {
      if (!active) return;
      setData(course);
      setProgress(items);
    }).catch((failure) => {
      if (active) {
        setData(null);
        setError(failure instanceof Error ? failure.message : '课程载入失败，请重试。');
      }
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [courseId, retry]);

  const progressByLesson = useMemo(
    () => new Map(progress.map((item) => [item.lesson_id, item])),
    [progress],
  );

  if (loading) return <div className="chrono-page-loading"><Spin /><span>正在展开课程路线…</span></div>;
  if (!data) return <Alert type="warning" showIcon message={error || '课程暂不可用'}
    action={<Button onClick={() => setRetry((value) => value + 1)}>重试</Button>} />;

  const course = data.summary;
  const firstFlagship = data.lessons[0];

  return (
    <div className="chrono-course-route-page">
      {progressUnavailable ? <Alert type="warning" showIcon message="阅读记录暂未载入，当前不显示完成度。"
        action={<Button onClick={() => setRetry((value) => value + 1)}>重试</Button>} /> : null}
      <button className="chrono-back-link" type="button" onClick={() => nav('/courses')}>
        <ArrowLeftOutlined /> 返回课程中心
      </button>

      <header className="chrono-course-route-hero chrono-course-route-hero-v2">
        <CourseCoverPicture
          className="chrono-course-route-art"
          courseId={course.id}
          width={1440}
          eager
          fallbackColor={course.cover_color}
        />
        <div className="chrono-course-route-copy">
          <h1>{course.title}</h1>
          <p className="chrono-course-subtitle">{course.subtitle}</p>
          <p className="chrono-course-identity">{course.section} · 历史主题课程</p>
          {data.intro ? <p>{data.intro}</p> : null}
        </div>
        <aside>
          <ClockCircleOutlined />
          <strong>{data.lessons.length} 个课时节点</strong>
          <span>按教师课时顺序学习</span>
          {firstFlagship ? (
            <Button
              type="primary"
              onClick={() => nav(`/courses/${course.id}/lessons/${firstFlagship.id}?layer=watch`)}
            >
              从第一课开始 <ArrowRightOutlined />
            </Button>
          ) : null}
        </aside>
      </header>

      <section className="chrono-route-stage-plan" aria-label="课堂阶段时间安排">
        {CLASSROOM_STAGES.map((stage) => (
          <article key={stage.layer}>
            <span>{stage.index}</span>
            <div>
              <strong>{stage.title} · {stage.duration}</strong>
              <p>{stage.purpose}</p>
            </div>
          </article>
        ))}
      </section>

      <section className="chrono-route-board" aria-labelledby="route-heading">
        <div className="chrono-route-board-heading">
          <div>
            <h2 id="route-heading">沿着早期国家形成的线索前进</h2>
          </div>
          <p>每个节点都从踏勘材料开始，经过抉择和追问，最后留下自己的历史解释。</p>
        </div>
        <div className="chrono-route-contours" aria-hidden="true" />
        <ol className="chrono-route-nodes">
          {data.lessons.map((lesson, index) => {
            const item = progressByLesson.get(lesson.id);
            const percent = readingComplete(item) ? 100 : 0;
            return (
              <li key={lesson.id}>
                <div className="chrono-route-marker">
                  {percent === 100 ? <CheckOutlined /> : <span>{String(index + 1).padStart(2, '0')}</span>}
                </div>
                <article
                  role="link"
                  tabIndex={0}
                  aria-label={`${item ? '继续' : '进入'}课时：${lesson.title}`}
                  onClick={() => nav(`/courses/${course.id}/lessons/${lesson.id}?layer=${item ? resumeLayer(item) : 'watch'}`)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      nav(`/courses/${course.id}/lessons/${lesson.id}?layer=${item ? resumeLayer(item) : 'watch'}`);
                    }
                  }}
                >
                  <div className="chrono-route-node-meta">
                    <span>{lesson.num}</span>
                    <span className="chrono-route-node-kind">教师课文</span>
                    <span><ClockCircleOutlined /> {lesson.duration}</span>
                  </div>
                  <h3>{lesson.title}</h3>
                  <p>按本课课文、人物与关键词阅读。</p>
                  <div className="chrono-route-node-progress">
                    <span>{progressUnavailable ? '阅读状态未知' : readingLabel(item)}</span>
                    <Button type="link">
                      {item ? '继续学习' : '进入课时'} <ArrowRightOutlined />
                    </Button>
                  </div>
                </article>
                {index < data.lessons.length - 1 ? <div className="chrono-route-connector" aria-hidden="true" /> : null}
              </li>
            );
          })}
        </ol>
        <div className="chrono-route-legend">
          <EnvironmentOutlined /> 路线用于表达课程结构，不代表历史事件只有单一路径。
        </div>
      </section>
    </div>
  );
}
