import { useEffect, useMemo, useState } from 'react';
import { Button, Spin, Tag } from 'antd';
import {
  ArrowRightOutlined,
  CompassOutlined,
  FileDoneOutlined,
  RadarChartOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import type { CourseDetail, ProgressItem } from '../utils/api';
import { api } from '../utils/api';
import {
  CLASSROOM_PRINCIPLES,
  CLASSROOM_STAGES,
  isFlagshipLesson,
  progressLayerLabel,
} from '../features/classroom/classroomModel';

const FLAGSHIP_COURSE_ID = 'C-prequin-state';

export default function HomePage() {
  const nav = useNavigate();
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [resume, setResume] = useState<ProgressItem | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    Promise.all([
      api.course(FLAGSHIP_COURSE_ID).catch(() => null),
      api.progressLatest().then((response) => response.item).catch(() => null),
    ]).then(([nextCourse, nextResume]) => {
      if (!active) return;
      setCourse(nextCourse);
      setResume(nextResume);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, []);

  const flagships = useMemo(
    () => course?.lessons.filter((lesson) => isFlagshipLesson(lesson.id)) ?? [],
    [course],
  );

  const resumePath = resume?.course_id
    ? `/courses/${resume.course_id}/lessons/${resume.lesson_id}?layer=${resume.last_layer}`
    : flagships[0]
      ? `/courses/${FLAGSHIP_COURSE_ID}/lessons/${flagships[0].id}?layer=watch`
      : `/courses/${FLAGSHIP_COURSE_ID}`;

  return (
    <div className="chrono-classroom-home">
      <section className="chrono-classroom-hero">
        <div className="chrono-classroom-hero-copy">
          <span className="chrono-eyebrow">七年级 · 本地课堂 · 35–45 分钟</span>
          <h1>走进历史现场，留下有依据的判断</h1>
          <p>
            从材料踏勘开始，在六回合抉择中观察局势变化；再召见人物与专家，
            最终把选择、代价和证据整理成自己的史官卷宗。
          </p>
          <div className="chrono-classroom-hero-actions">
            <Button type="primary" size="large" onClick={() => nav(resumePath)}>
              {resume ? '继续上次学习' : '进入旗舰课堂'} <ArrowRightOutlined />
            </Button>
            <Button size="large" onClick={() => nav(`/courses/${FLAGSHIP_COURSE_ID}`)}>
              查看课程路线
            </Button>
          </div>
          {resume ? (
            <div className="chrono-resume-line">
              <FileDoneOutlined />
              <span>上次停在「{progressLayerLabel(resume.last_layer)}」阶段 · {resume.title}</span>
            </div>
          ) : null}
        </div>
        <div className="chrono-classroom-hero-map" aria-label="四阶段课堂路线">
          <div className="chrono-orbit" aria-hidden="true" />
          <CompassOutlined className="chrono-hero-compass" />
          <ol>
            {CLASSROOM_STAGES.map((stage) => (
              <li key={stage.layer}>
                <span>{stage.index}</span>
                <div><strong>{stage.title}</strong><small>{stage.verb}</small></div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="chrono-principles" aria-labelledby="principle-heading">
        <div className="chrono-section-heading">
          <div>
            <span>课堂方法</span>
            <h2 id="principle-heading">观察、干预、反馈、复盘形成一个闭环</h2>
          </div>
          <RadarChartOutlined />
        </div>
        <div className="chrono-principle-grid">
          {CLASSROOM_PRINCIPLES.map((principle, index) => (
            <article key={principle.title}>
              <span>0{index + 1}</span>
              <h3>{principle.title}</h3>
              <p>{principle.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="chrono-flagships" aria-labelledby="flagship-heading">
        <div className="chrono-section-heading">
          <div>
            <span>双旗舰课程</span>
            <h2 id="flagship-heading">两种历史难题，同一套证据化学习流程</h2>
          </div>
          <Button type="link" onClick={() => nav(`/courses/${FLAGSHIP_COURSE_ID}`)}>
            查看完整路线 <ArrowRightOutlined />
          </Button>
        </div>
        {loading ? (
          <div className="chrono-flagship-loading"><Spin /><span>正在读取正式课程发布…</span></div>
        ) : (
          <div className="chrono-flagship-grid">
            {flagships.map((lesson, index) => (
              <article key={lesson.id} className={`chrono-flagship-card flagship-${index + 1}`}>
                <div className="chrono-flagship-mapline" aria-hidden="true">
                  <span /><span /><span /><span />
                </div>
                <div className="chrono-flagship-meta">
                  <Tag>{lesson.id}</Tag>
                  <span>{lesson.duration} · 六回合历史抉择</span>
                </div>
                <h3>{lesson.title}</h3>
                <p>{index === 0
                  ? '从洪水记忆与多层证据出发，讨论公共协作、权威形成和治理代价。'
                  : '从传世叙事、量器铭文与秦简出发，比较富国强兵、制度信用和社会代价。'}</p>
                <div className="chrono-flagship-stages">
                  {CLASSROOM_STAGES.map((stage) => <span key={stage.layer}>{stage.title}</span>)}
                </div>
                <Button
                  type="primary"
                  onClick={() => nav(`/courses/${FLAGSHIP_COURSE_ID}/lessons/${lesson.id}?layer=watch`)}
                >
                  开始踏勘 <ArrowRightOutlined />
                </Button>
              </article>
            ))}
            {!loading && flagships.length === 0 ? (
              <div className="chrono-empty">正式课程发布暂不可读，请教师检查本地课程包。</div>
            ) : null}
          </div>
        )}
      </section>
    </div>
  );
}
