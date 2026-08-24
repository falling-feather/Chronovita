import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type FocusEvent,
  type PointerEvent,
} from 'react';
import { Button } from 'antd';
import { ArrowRightOutlined, FileDoneOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import type { CourseDetail, ProgressItem } from '../utils/api';
import { api } from '../utils/api';
import {
  CLASSROOM_STAGES,
  isFlagshipLesson,
  progressLayerLabel,
} from '../features/classroom/classroomModel';
import ChronoscopeScene from '../features/visual/ChronoscopeScene';
import {
  HOME_ERAS,
  homeEraAsset,
  nextHomeEraIndex,
  type HomeEraPresentation,
} from '../features/visual/homeEraModel';

const FLAGSHIP_COURSE_ID = 'C-prequin-state';
const AUTO_ERA_INTERVAL_MS = 7_000;

type IntroPhase = 'dial' | 'ribbon' | 'settle' | 'done';
type IntroRenderer = 'loading' | 'webgpu' | 'webgl2' | 'fallback' | 'skipped';

function EraSubjectStage({ era }: { era: HomeEraPresentation }) {
  return (
    <div className="chrono-home-era-preview" aria-live="polite">
      <div className="chrono-home-era-orbits" aria-hidden="true">
        <span /><span /><span />
      </div>
      <picture key={era.id} className="chrono-home-era-subject">
        <source
          srcSet={`${homeEraAsset(era, 640)} 640w, ${homeEraAsset(era, 1280)} 1280w`}
          sizes="(max-width: 680px) 72vw, 54vw"
          type="image/webp"
        />
        <img
          src={homeEraAsset(era, 1280)}
          alt={era.subjectAlt}
          width="1280"
          height="1280"
          decoding="async"
        />
      </picture>
      <div className="chrono-home-era-meta">
        <span className="chrono-home-era-rule" aria-hidden="true" />
        <h2>{era.name}</h2>
        <time>{era.years}</time>
        <p>{era.caption}</p>
        <small>原创教学视觉 · 非精确复原</small>
      </div>
    </div>
  );
}

interface EraRailProps {
  activeEra: number;
  paused: boolean;
  onActiveEra: (index: number) => void;
  onPause: (paused: boolean) => void;
  onOpenEra: (era: HomeEraPresentation) => void;
}

function EraRail({ activeEra, paused, onActiveEra, onPause, onOpenEra }: EraRailProps) {
  const handleBlur = (event: FocusEvent<HTMLElement>) => {
    if (!event.currentTarget.contains(event.relatedTarget)) onPause(false);
  };

  const renderEra = (era: HomeEraPresentation, index: number, interactive: boolean) => {
    const contents = (
      <>
        <img src={era.cover} alt="" loading="eager" decoding="async" />
        <span><strong>{era.name}</strong><small>{era.years}</small></span>
      </>
    );
    return (
      <li key={`${interactive ? 'primary' : 'loop'}-${era.id}`} className={index === activeEra ? 'is-current' : ''}>
        {interactive ? (
          <button
            type="button"
            aria-current={index === activeEra ? 'step' : undefined}
            onPointerEnter={() => onActiveEra(index)}
            onFocus={() => onActiveEra(index)}
            onClick={() => onOpenEra(era)}
          >
            {contents}
          </button>
        ) : (
          <div
            className="chrono-home-era-loop-card"
            onPointerEnter={() => onActiveEra(index)}
            onClick={() => onOpenEra(era)}
          >
            {contents}
          </div>
        )}
      </li>
    );
  };

  return (
    <nav
      className={`chrono-home-era-rail${paused ? ' is-paused' : ''}`}
      aria-label="中国历史课程时代长卷"
      onPointerEnter={() => onPause(true)}
      onPointerLeave={() => onPause(false)}
      onFocusCapture={() => onPause(true)}
      onBlurCapture={handleBlur}
    >
      <div className="chrono-home-era-track">
        <ol>{HOME_ERAS.map((era, index) => renderEra(era, index, true))}</ol>
        <ol aria-hidden="true">{HOME_ERAS.map((era, index) => renderEra(era, index, false))}</ol>
      </div>
    </nav>
  );
}

function HomeIntro({
  phase,
  onRenderer,
}: {
  phase: Exclude<IntroPhase, 'done'>;
  onRenderer: (state: Exclude<IntroRenderer, 'loading' | 'skipped'>) => void;
}) {
  return (
    <div className={`chrono-home-intro is-${phase}`} aria-hidden="true">
      <div className="chrono-home-intro-dial">
        <ChronoscopeScene onReady={onRenderer} />
      </div>
      <div className="chrono-home-intro-ribbon">
        {HOME_ERAS.map((era) => (
          <span key={era.id}><img src={era.cover} alt="" /></span>
        ))}
      </div>
      <div className="chrono-home-intro-scan" />
    </div>
  );
}

export default function HomePage() {
  const nav = useNavigate();
  const stageRef = useRef<HTMLElement>(null);
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [resume, setResume] = useState<ProgressItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeEra, setActiveEra] = useState(0);
  const [railPaused, setRailPaused] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(() => (
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  ));
  const [introPhase, setIntroPhase] = useState<IntroPhase>(() => (
    window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'done' : 'dial'
  ));
  const [introRenderer, setIntroRenderer] = useState<IntroRenderer>(() => (
    window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'skipped' : 'loading'
  ));

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = () => {
      setReducedMotion(media.matches);
      if (media.matches) {
        setIntroRenderer('skipped');
        setIntroPhase('done');
      }
    };
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  useEffect(() => {
    if (reducedMotion) return undefined;
    const ribbonTimer = window.setTimeout(() => setIntroPhase('ribbon'), 1_050);
    const settleTimer = window.setTimeout(() => setIntroPhase('settle'), 1_720);
    const doneTimer = window.setTimeout(() => setIntroPhase('done'), 2_550);
    const clearTimers = () => {
      window.clearTimeout(ribbonTimer);
      window.clearTimeout(settleTimer);
      window.clearTimeout(doneTimer);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      clearTimers();
      setIntroPhase('done');
    };
    window.addEventListener('keydown', onKeyDown);
    return () => {
      clearTimers();
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [reducedMotion]);

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

  useEffect(() => {
    if (railPaused || reducedMotion || introPhase !== 'done') return undefined;
    const timer = window.setInterval(() => {
      setActiveEra((current) => nextHomeEraIndex(current));
    }, AUTO_ERA_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [introPhase, railPaused, reducedMotion]);

  useEffect(() => {
    const nextEra = HOME_ERAS[nextHomeEraIndex(activeEra)];
    const preload = new Image();
    preload.src = homeEraAsset(nextEra, 1280);
  }, [activeEra]);

  const flagships = useMemo(
    () => course?.lessons.filter((lesson) => isFlagshipLesson(lesson.id)) ?? [],
    [course],
  );
  const resumePath = resume?.course_id
    ? `/courses/${resume.course_id}/lessons/${resume.lesson_id}?layer=${resume.last_layer}`
    : flagships[0]
      ? `/courses/${FLAGSHIP_COURSE_ID}/lessons/${flagships[0].id}?layer=watch`
      : `/courses/${FLAGSHIP_COURSE_ID}`;
  const era = HOME_ERAS[activeEra];
  const stageStyle = { '--chrono-era-index': activeEra } as CSSProperties;

  const onPointerMove = (event: PointerEvent<HTMLElement>) => {
    if (reducedMotion) return;
    const host = stageRef.current;
    if (!host) return;
    const rect = host.getBoundingClientRect();
    host.style.setProperty('--chrono-pointer-x', `${((event.clientX - rect.left) / rect.width) - 0.5}`);
    host.style.setProperty('--chrono-pointer-y', `${((event.clientY - rect.top) / rect.height) - 0.5}`);
  };
  const resetPointer = () => {
    const host = stageRef.current;
    host?.style.setProperty('--chrono-pointer-x', '0');
    host?.style.setProperty('--chrono-pointer-y', '0');
  };
  const onIntroRenderer = useCallback((state: 'webgpu' | 'webgl2' | 'fallback') => {
    setIntroRenderer(state);
  }, []);

  return (
    <div
      className={`chrono-home-v4${introPhase === 'done' ? ' is-ready' : ' is-intro-running'}`}
      data-active-era={era.id}
      data-intro-phase={introPhase}
      data-intro-renderer={introRenderer}
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
      <div className="chrono-home-future-grid" aria-hidden="true" />

      <section
        ref={stageRef}
        className="chrono-home-stage"
        aria-labelledby="chrono-home-title"
        onPointerMove={onPointerMove}
        onPointerLeave={resetPointer}
      >
        <div className="chrono-home-copy-v4">
          <h1 id="chrono-home-title">拨动天光，进入历史现场</h1>
          <p>观察证据，作出选择，召见古人，写下你的历史判断。</p>
          <div className="chrono-home-actions-v4">
            <Button type="primary" size="large" onClick={() => nav(resumePath)}>
              {resume ? '继续学习' : '进入旗舰课堂'}
              <ArrowRightOutlined />
            </Button>
            <Button size="large" onClick={() => nav('/courses')}>浏览课程</Button>
          </div>
          <div className="chrono-home-resume-v4" aria-live="polite">
            <FileDoneOutlined />
            {loading ? (
              <span>正在读取课堂记录…</span>
            ) : resume ? (
              <span>上次停在「{progressLayerLabel(resume.last_layer)}」· {resume.title}</span>
            ) : (
              <span>从“大禹治水”开始第一份历史卷宗</span>
            )}
          </div>
          <ol className="chrono-home-stages-v4" aria-label="课堂四阶段">
            {CLASSROOM_STAGES.map((stage, index) => (
              <li key={stage.layer}>
                <span>{String(index + 1).padStart(2, '0')}</span>
                <strong>{stage.title}</strong>
              </li>
            ))}
          </ol>
        </div>

        <EraSubjectStage era={era} />
      </section>

      <EraRail
        activeEra={activeEra}
        paused={railPaused || introPhase !== 'done'}
        onActiveEra={setActiveEra}
        onPause={setRailPaused}
        onOpenEra={(nextEra) => nav(`/courses?era=${nextEra.id}`)}
      />

      {introPhase !== 'done' ? (
        <HomeIntro phase={introPhase} onRenderer={onIntroRenderer} />
      ) : null}
    </div>
  );
}
