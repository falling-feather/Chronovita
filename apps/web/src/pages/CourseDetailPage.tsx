import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button, Progress, Spin } from 'antd';
import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  CheckOutlined,
  ClockCircleOutlined,
  EnvironmentOutlined,
} from '@ant-design/icons';
import type { CourseDetail, ProgressItem } from '../utils/api';
import { api } from '../utils/api';
import { CLASSROOM_STAGES, isFlagshipLesson } from '../features/classroom/classroomModel';

export default function CourseDetailPage() {
  const { courseId = '' } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState<CourseDetail | null>(null);
  const [progress, setProgress] = useState<ProgressItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([
      api.course(courseId),
      api.progressList().then((response) => response.items).catch(() => []),
    ]).then(([course, items]) => {
      if (!active) return;
      setData(course);
      setProgress(items);
    }).catch(() => {
      if (active) setData(null);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [courseId]);

  const progressByLesson = useMemo(
    () => new Map(progress.map((item) => [item.lesson_id, item])),
    [progress],
  );

  if (loading) return <div className="chrono-page-loading"><Spin /><span>正在展开课程路线…</span></div>;
  if (!data) return <div className="chrono-empty">课程不存在或当前发布暂不可读。</div>;

  const course = data.summary;
  const flagshipCount = data.lessons.filter((lesson) => isFlagshipLesson(lesson.id)).length;
  const firstFlagship = data.lessons.find((lesson) => isFlagshipLesson(lesson.id)) ?? data.lessons[0];

  return (
    <div className="chrono-course-route-page">
      <button className="chrono-back-link" type="button" onClick={() => nav('/courses')}>
        <ArrowLeftOutlined /> 返回课程中心
      </button>

      <header className="chrono-course-route-hero chrono-course-route-hero-v2">
        <div className="chrono-course-route-copy">
          <h1>{course.title}</h1>
          <p className="chrono-course-subtitle">{course.subtitle}</p>
          <p className="chrono-course-identity">{course.section} · 历史主题课程</p>
          <p>{data.intro}</p>
        </div>
        <aside>
          <ClockCircleOutlined />
          <strong>{data.lessons.length} 个课时节点</strong>
          <span>{flagshipCount} 门旗舰课 · 每门约 35—45 分钟</span>
          {firstFlagship ? (
            <Button
              type="primary"
              onClick={() => nav(`/courses/${course.id}/lessons/${firstFlagship.id}?layer=watch`)}
            >
              从旗舰课开始 <ArrowRightOutlined />
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
            const flagship = isFlagshipLesson(lesson.id);
            const item = progressByLesson.get(lesson.id);
            const completedStages = item ? Object.values(item.layers).filter(Boolean).length : 0;
            const percent = completedStages * 25;
            return (
              <li key={lesson.id} className={flagship ? 'flagship' : ''}>
                <div className="chrono-route-marker">
                  {percent === 100 ? <CheckOutlined /> : <span>{String(index + 1).padStart(2, '0')}</span>}
                </div>
                <article
                  role="link"
                  tabIndex={0}
                  aria-label={`${item ? '继续' : '进入'}课时：${lesson.title}`}
                  onClick={() => nav(`/courses/${course.id}/lessons/${lesson.id}?layer=${item?.last_layer ?? 'watch'}`)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      nav(`/courses/${course.id}/lessons/${lesson.id}?layer=${item?.last_layer ?? 'watch'}`);
                    }
                  }}
                >
                  <div className="chrono-route-node-meta">
                    <span>{lesson.num}</span>
                    <span className="chrono-route-node-kind">{flagship ? '旗舰课堂' : '课程节点'}</span>
                    <span><ClockCircleOutlined /> {lesson.duration}</span>
                  </div>
                  <h3>{lesson.title}</h3>
                  <p>{flagship
                    ? '踏勘材料、完成六回合抉择、召见人物并生成史官卷宗。'
                    : '沿用课程目录内容，可继续使用看、练、问、创兼容学习流程。'}</p>
                  <div className="chrono-route-node-progress">
                    <Progress percent={percent} showInfo={false} strokeColor="#65AAA0" />
                    <span>{item ? `已完成 ${completedStages} / 4 阶段` : '尚未开始'}</span>
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
