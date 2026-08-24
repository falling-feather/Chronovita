import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Drawer, Empty, Progress, Spin, Tag } from 'antd';
import {
  ArrowRightOutlined,
  BookOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  FileDoneOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import CourseCoverPicture from '../features/courses/CourseCoverPicture';
import {
  api,
  type LearningSubmissionDetail,
  type LearningSubmissionListItem,
  type ProgressItem,
} from '../utils/api';
import './LearningPage.css';

const LearningSubmissionViewer = lazy(
  () => import('../features/classroom/LearningSubmissionViewer'),
);

const LAYER_LABEL: Record<string, string> = {
  watch: '踏勘', practice: '抉择', ask: '召见', create: '书案',
};

const LESSON_LABELS: Record<string, string> = {
  L101: '大禹治水：洪水记忆与早期国家',
  L103: '商鞅变法：富国强兵与制度代价',
};

function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const diff = (Date.now() - date.getTime()) / 1000;
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.max(1, Math.floor(diff / 60))} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} 天前`;
  return date.toLocaleDateString('zh-CN');
}

function progressPct(item: ProgressItem): number {
  return Math.round([
    item.layers.watch,
    item.layers.practice,
    item.layers.ask,
    item.layers.create,
  ].filter(Boolean).length * 25);
}

function feedbackLabel(item: LearningSubmissionListItem): { label: string; color: string } {
  const status = item.latest_feedback?.completion_status;
  if (status === 'completed') return { label: '教师确认完成', color: 'green' };
  if (status === 'changes_requested') return { label: '教师建议修改', color: 'volcano' };
  if (status === 'in_review') return { label: '教师已查看', color: 'gold' };
  return { label: '等待教师查看', color: 'default' };
}

export default function LearningPage() {
  const auth = useAuth();
  const nav = useNavigate();
  const [tab, setTab] = useState<'progress' | 'submissions'>('progress');
  const [items, setItems] = useState<ProgressItem[]>([]);
  const [submissions, setSubmissions] = useState<LearningSubmissionListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState<LearningSubmissionDetail | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    Promise.all([
      api.progressList(),
      auth.mode === 'accounts'
        ? api.learningSubmissions({ limit: 100 })
        : Promise.resolve({ items: [] as LearningSubmissionListItem[] }),
    ]).then(([progress, submitted]) => {
      if (!active) return;
      setItems(progress.items || []);
      setSubmissions(submitted.items || []);
    }).catch((loadError) => {
      if (active) setError(loadError instanceof Error ? loadError.message.replace(/^\d{3}\s+/, '') : '学习记录载入失败');
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [auth.mode]);

  const stats = useMemo(() => ({
    lessons: items.length,
    completedLessons: items.filter((item) => progressPct(item) === 100).length,
    submissions: submissions.length,
    feedback: submissions.filter((item) => item.latest_feedback).length,
  }), [items, submissions]);

  const openDetail = async (submissionId: string) => {
    setDetailOpen(true);
    setDetailLoading(true);
    try {
      setDetail(await api.learningSubmission(submissionId));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message.replace(/^\d{3}\s+/, '') : '成果版本载入失败');
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <div className="chrono-learning-page">
      <header className="chrono-learning-hero">
        <div className="chrono-learning-hero-mark" aria-hidden="true"><span>学</span></div>
        <div className="chrono-learning-hero-copy">
          <p>PERSONAL · HISTORY DESK</p>
          <h1>{auth.principal?.display_name ?? '本地学徒'}的学习长卷</h1>
          <span>继续课堂、整理本机书案，并查看你主动提交给教师的成果与反馈。</span>
        </div>
        <dl>
          <div><dt>{stats.lessons}</dt><dd>学习课时</dd></div>
          <div><dt>{stats.completedLessons}</dt><dd>完成四阶段</dd></div>
          <div><dt>{stats.submissions}</dt><dd>提交版本</dd></div>
          <div><dt>{stats.feedback}</dt><dd>教师反馈</dd></div>
        </dl>
      </header>

      {error ? <Alert type="warning" showIcon closable message={error} onClose={() => setError('')} /> : null}

      <nav className="chrono-learning-tabs" aria-label="学习记录分类">
        <button type="button" className={tab === 'progress' ? 'active' : ''} onClick={() => setTab('progress')}>
          <BookOutlined /> 学习进程 <span>{items.length}</span>
        </button>
        <button type="button" className={tab === 'submissions' ? 'active' : ''} onClick={() => setTab('submissions')}>
          <FileDoneOutlined /> 已提交成果 <span>{submissions.length}</span>
        </button>
      </nav>

      {loading ? (
        <div className="chrono-learning-loading"><Spin /><span>正在展开学习长卷…</span></div>
      ) : tab === 'progress' ? (
        items.length > 0 ? (
          <section className="chrono-learning-progress-grid">
            {items.map((item) => {
              const pct = progressPct(item);
              return (
                <article key={item.lesson_id}>
                  <CourseCoverPicture
                    courseId={item.course_id || 'C-prequin-state'}
                    width={720}
                    fallbackColor="#69553e"
                  />
                  <div>
                    <p>{item.lesson_id} · 上次进入{LAYER_LABEL[item.last_layer] ?? item.last_layer}</p>
                    <h2>{item.title ?? LESSON_LABELS[item.lesson_id] ?? item.lesson_id}</h2>
                    <div className="chrono-learning-stage-marks">
                      {(['watch', 'practice', 'ask', 'create'] as const).map((layer) => (
                        <span className={item.layers[layer] ? 'done' : ''} key={layer}>
                          {item.layers[layer] ? <CheckCircleOutlined /> : <ClockCircleOutlined />}
                          {LAYER_LABEL[layer]}
                        </span>
                      ))}
                    </div>
                    <Progress percent={pct} showInfo={false} strokeColor="#b7873f" trailColor="rgba(57, 72, 68, .1)" />
                    <footer>
                      <time>{formatTime(item.updated_at)}</time>
                      <Button type="link" onClick={() => item.course_id
                        ? nav(`/courses/${item.course_id}/lessons/${item.lesson_id}?layer=${item.last_layer}`)
                        : nav('/courses')}
                      >继续学习 <ArrowRightOutlined /></Button>
                    </footer>
                  </div>
                </article>
              );
            })}
          </section>
        ) : (
          <Empty description="还没有学习记录">
            <Button type="primary" onClick={() => nav('/courses')}>选择第一门课程</Button>
          </Empty>
        )
      ) : submissions.length > 0 ? (
        <section className="chrono-learning-submission-grid">
          {submissions.map((item) => {
            const feedback = feedbackLabel(item);
            return (
              <article key={item.submission_id}>
                <header>
                  <span>第 {item.version} 版</span>
                  <Tag color={feedback.color}>{feedback.label}</Tag>
                </header>
                <h2>{item.title}</h2>
                <p>{LESSON_LABELS[item.lesson_id] ?? item.lesson_id}</p>
                <blockquote>{item.body_excerpt || '本版主要由便签、笔迹或导图构成。'}</blockquote>
                <dl>
                  <div><dt>{item.sticky_note_count}</dt><dd>便签</dd></div>
                  <div><dt>{item.stroke_count}</dt><dd>笔迹</dd></div>
                  <div><dt>{item.canvas_node_count}</dt><dd>节点</dd></div>
                  <div><dt>{item.event_count}</dt><dd>轨迹</dd></div>
                </dl>
                <footer>
                  <time>{new Date(item.submitted_at).toLocaleString('zh-CN')}</time>
                  <Button type="primary" ghost onClick={() => void openDetail(item.submission_id)}>查看版本</Button>
                </footer>
              </article>
            );
          })}
        </section>
      ) : (
        <Empty description={auth.mode === 'accounts' ? '还没有明确提交的学习成果' : '兼容模式不能提交版本化学习成果'}>
          <Button type="primary" onClick={() => nav('/courses')}>进入课程书案</Button>
        </Empty>
      )}

      <Drawer
        title="学习成果版本"
        width="min(980px, 96vw)"
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
      >
        {detailLoading ? (
          <div className="chrono-learning-loading"><Spin /><span>正在展开成果版本…</span></div>
        ) : detail ? (
          <Suspense fallback={<div className="chrono-learning-loading"><Spin /></div>}>
            <LearningSubmissionViewer detail={detail} showStudent={false} />
          </Suspense>
        ) : <Empty description="成果版本暂不可用" />}
      </Drawer>
    </div>
  );
}
