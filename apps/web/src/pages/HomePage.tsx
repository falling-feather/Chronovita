import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import { Button } from 'antd';
import {
  ArrowRightOutlined,
  ClockCircleOutlined,
  FileDoneOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import type { CourseDetail, ProgressItem } from '../utils/api';
import { api } from '../utils/api';
import {
  CLASSROOM_STAGES,
  isFlagshipLesson,
  progressLayerLabel,
} from '../features/classroom/classroomModel';
import ChronoscopeScene from '../features/visual/ChronoscopeScene';
import { getSolarPresentation } from '../features/visual/sundialModel';

const FLAGSHIP_COURSE_ID = 'C-prequin-state';
const HISTORY_SCROLL = [
  {
    id: 'preqin',
    name: '先秦',
    years: '约前 2070—前 221',
    cover: '/assets/courses/covers/C-prequin-state-720.webp',
  },
  {
    id: 'qinhan',
    name: '秦汉',
    years: '前 221—220',
    cover: '/assets/courses/covers/C-qinhan-founding-720.webp',
  },
  {
    id: 'weijin',
    name: '魏晋南北朝',
    years: '220—589',
    cover: '/assets/courses/covers/C-weijin-fusion-720.webp',
  },
  {
    id: 'suitang',
    name: '隋唐',
    years: '581—907',
    cover: '/assets/courses/covers/C-suitang-tang-720.webp',
  },
  {
    id: 'songyuan',
    name: '宋元',
    years: '960—1368',
    cover: '/assets/courses/covers/C-songyuan-song-720.webp',
  },
  {
    id: 'mingqing',
    name: '明清',
    years: '1368—1912',
    cover: '/assets/courses/covers/C-mingqing-late-720.webp',
  },
] as const;

export default function HomePage() {
  const nav = useNavigate();
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [resume, setResume] = useState<ProgressItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeEra, setActiveEra] = useState(0);
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
  const stageStyle = { '--chrono-era-angle': `${activeEra * 3}deg` } as CSSProperties;

  return (
    <div
      className="chrono-home-v3"
      data-solar-period={solar.period}
      data-active-era={HISTORY_SCROLL[activeEra].id}
      style={stageStyle}
    >
      <div className="chrono-home-panorama" aria-hidden="true">
        <img
          src="/assets/entry/home-history-panorama-1366.webp"
          srcSet="/assets/entry/home-history-panorama-1366.webp 1366w, /assets/entry/home-history-panorama-1920.webp 1920w"
          sizes="100vw"
          alt=""
          decoding="async"
        />
      </div>
      <div className="chrono-home-time-wash" aria-hidden="true" />
      <div className="chrono-home-depth-lines" aria-hidden="true"><span /><span /><span /></div>

      <section className="chrono-home-stage" aria-labelledby="chrono-home-title">
        <div className="chrono-home-copy-v3">
          <h1 id="chrono-home-title">拨动天光，进入历史现场</h1>
          <p>观察证据，作出选择，召见古人，写下你的历史判断。</p>
          <div className="chrono-home-actions-v3">
            <Button type="primary" size="large" onClick={() => nav(resumePath)}>
              {resume ? '继续学习' : '进入旗舰课堂'}
              <ArrowRightOutlined />
            </Button>
            <Button size="large" onClick={() => nav('/courses')}>浏览课程</Button>
          </div>
          <div className="chrono-home-resume-v3" aria-live="polite">
            <FileDoneOutlined />
            {loading ? (
              <span>正在读取课堂记录…</span>
            ) : resume ? (
              <span>上次停在「{progressLayerLabel(resume.last_layer)}」· {resume.title}</span>
            ) : (
              <span>从“大禹治水”开始第一份历史卷宗</span>
            )}
          </div>
          <ol className="chrono-home-stages-v3" aria-label="课堂四阶段">
            {CLASSROOM_STAGES.map((stage, index) => (
              <li key={stage.layer}>
                <span>{String(index + 1).padStart(2, '0')}</span>
                <strong>{stage.title}</strong>
              </li>
            ))}
          </ol>
        </div>

        <div className="chrono-home-chronoscope">
          <ChronoscopeScene solar={solar} activeEra={activeEra} />
          <div className="chrono-home-local-time" aria-label={`本地时间 ${solar.timeLabel}，${solar.label}`}>
            <ClockCircleOutlined />
            <time dateTime={now.toISOString()}>{solar.timeLabel}</time>
            <span>{solar.label}</span>
          </div>
          <p className="chrono-home-installation-note">原创历史教学装置 · 非出土器物复原</p>
        </div>
      </section>

      <nav className="chrono-home-era-rail" aria-label="中国历史课程时代长卷">
        <ol>
          {HISTORY_SCROLL.map((era, index) => (
            <li key={era.id} className={index === activeEra ? 'is-current' : ''}>
              <button
                type="button"
                aria-current={index === activeEra ? 'step' : undefined}
                onPointerEnter={() => setActiveEra(index)}
                onFocus={() => setActiveEra(index)}
                onClick={() => nav(`/courses?era=${era.id}`)}
              >
                <img src={era.cover} alt="" loading="eager" decoding="async" />
                <span><strong>{era.name}</strong><small>{era.years}</small></span>
              </button>
            </li>
          ))}
        </ol>
        <button type="button" className="chrono-home-open-scroll" onClick={() => nav('/courses')}>
          <span>展开全卷</span><ArrowRightOutlined />
        </button>
      </nav>
    </div>
  );
}
