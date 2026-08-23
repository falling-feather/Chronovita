import { useEffect, useMemo, useState } from 'react';
import { Button, Spin } from 'antd';
import {
  ArrowRightOutlined,
  BookOutlined,
  CompassOutlined,
  FileDoneOutlined,
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
import SundialScene from '../features/visual/SundialScene';
import { getSolarPresentation } from '../features/visual/sundialModel';

const FLAGSHIP_COURSE_ID = 'C-prequin-state';
const HISTORY_SCROLL = [
  { id: 'preqin', name: '先秦', years: '约前 2070—前 221' },
  { id: 'qinhan', name: '秦汉', years: '前 221—220' },
  { id: 'weijin', name: '魏晋南北朝', years: '220—589' },
  { id: 'suitang', name: '隋唐', years: '581—907' },
  { id: 'songyuan', name: '宋元', years: '960—1368' },
  { id: 'mingqing', name: '明清', years: '1368—1912' },
] as const;

export default function HomePage() {
  const nav = useNavigate();
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [resume, setResume] = useState<ProgressItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

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
  const solar = useMemo(() => getSolarPresentation(now), [now]);
  const resumePath = resume?.course_id
    ? `/courses/${resume.course_id}/lessons/${resume.lesson_id}?layer=${resume.last_layer}`
    : flagships[0]
      ? `/courses/${FLAGSHIP_COURSE_ID}/lessons/${flagships[0].id}?layer=watch`
      : `/courses/${FLAGSHIP_COURSE_ID}`;

  return (
    <div className="chrono-home-v2">
      <section className="chrono-home-hero-v2" data-solar-period={solar.period}>
        <div className="chrono-home-sky" aria-hidden="true">
          <span className="chrono-home-sky-glow" />
          <span className="chrono-home-mountain mountain-back" />
          <span className="chrono-home-mountain mountain-front" />
          <span className="chrono-home-wall" />
        </div>

        <div className="chrono-home-copy-v2">
          <h1>拨动天光，进入历史现场</h1>
          <p>观察证据，作出选择，召见古人，写下你的历史判断。</p>
          <div className="chrono-home-actions-v2">
            <Button type="primary" size="large" onClick={() => nav(resumePath)}>
              {resume ? '继续上次学习' : '进入旗舰课堂'}
              <ArrowRightOutlined />
            </Button>
            <Button size="large" onClick={() => nav('/courses')}>
              浏览课程
            </Button>
          </div>
          <div className="chrono-home-resume-v2" aria-live="polite">
            <FileDoneOutlined />
            {loading ? (
              <span>正在读取你的课堂记录…</span>
            ) : resume ? (
              <span>上次停在「{progressLayerLabel(resume.last_layer)}」· {resume.title}</span>
            ) : (
              <span>从“大禹治水”开始你的第一份历史卷宗</span>
            )}
          </div>
        </div>

        <div className="chrono-home-instrument">
          <SundialScene solar={solar} />
          <div className="chrono-home-time" aria-label={`本地时间 ${solar.timeLabel}，${solar.label}`}>
            <span>此刻</span>
            <time dateTime={now.toISOString()}>{solar.timeLabel}</time>
            <strong>{solar.label}</strong>
          </div>
        </div>

        <nav className="chrono-history-scroll" aria-label="中国历史课程时代长卷">
          <div className="chrono-history-scroll-title">
            <CompassOutlined />
            <span>中国历史长卷</span>
          </div>
          <ol>
            {HISTORY_SCROLL.map((era, index) => (
              <li key={era.id} className={index === 0 ? 'is-current' : ''}>
                <button type="button" onClick={() => nav(`/courses?era=${era.id}`)}>
                  <span>{era.name}</span>
                  <small>{era.years}</small>
                </button>
              </li>
            ))}
          </ol>
          <button type="button" className="chrono-scroll-enter" onClick={() => nav('/courses')}>
            展开全卷 <ArrowRightOutlined />
          </button>
        </nav>
      </section>

      <section className="chrono-home-method" aria-labelledby="home-method-title">
        <header>
          <BookOutlined aria-hidden="true" />
          <div>
            <h2 id="home-method-title">历史不是答案陈列，而是一条判断链</h2>
            <p>四个动作在一节课内首尾相接，最后沉淀为学生自己的证据与解释。</p>
          </div>
        </header>
        <ol>
          {CLASSROOM_PRINCIPLES.map((principle, index) => (
            <li key={principle.title}>
              <span>{String(index + 1).padStart(2, '0')}</span>
              <div>
                <h3>{principle.title}</h3>
                <p>{principle.description}</p>
              </div>
            </li>
          ))}
        </ol>
        <div className="chrono-home-stage-line" aria-label="课堂四阶段">
          {CLASSROOM_STAGES.map((stage) => (
            <span key={stage.layer}>
              <b>{stage.title}</b>
              <small>{stage.verb}</small>
            </span>
          ))}
        </div>
      </section>

      <section className="chrono-home-flagships-v2" aria-labelledby="home-flagship-title">
        <header>
          <div>
            <h2 id="home-flagship-title">从两场改变秩序的难题开始</h2>
            <p>一场关乎洪水与共同体，一场关乎制度、强国与代价。</p>
          </div>
          <Button type="text" onClick={() => nav(`/courses/${FLAGSHIP_COURSE_ID}`)}>
            查看课程路线 <ArrowRightOutlined />
          </Button>
        </header>

        {loading ? (
          <div className="chrono-home-loading"><Spin /><span>正在读取正式课程发布…</span></div>
        ) : flagships.length > 0 ? (
          <div className="chrono-home-flagship-list">
            {flagships.map((lesson, index) => (
              <article key={lesson.id} className={`is-flagship-${index + 1}`}>
                <div className="chrono-home-flagship-number">0{index + 1}</div>
                <div className="chrono-home-flagship-copy">
                  <span>{lesson.id} · {lesson.duration} · 六回合历史抉择</span>
                  <h3>{lesson.title}</h3>
                  <p>{index === 0
                    ? '从洪水记忆与多层证据出发，讨论公共协作、权威形成和治理代价。'
                    : '从传世叙事、量器铭文与秦简出发，比较富国强兵、制度信用和社会代价。'}</p>
                </div>
                <Button
                  className="chrono-home-flagship-action"
                  type="text"
                  aria-label={`进入课程：${lesson.title}`}
                  onClick={() => nav(`/courses/${FLAGSHIP_COURSE_ID}/lessons/${lesson.id}?layer=watch`)}
                >
                  进入 <ArrowRightOutlined />
                </Button>
              </article>
            ))}
          </div>
        ) : (
          <div className="chrono-empty">正式课程发布暂不可读，请教师检查本地课程包。</div>
        )}
      </section>
    </div>
  );
}
