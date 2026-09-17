import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Drawer, Empty, Spin, Tag } from 'antd';
import {
  ArrowRightOutlined,
  BookOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  FileDoneOutlined,
} from '@ant-design/icons';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { readingComplete, readingLabel, resumeLayer } from '../features/classroom/readingProgress';
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
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') === 'submissions' ? 'submissions' : 'progress';
  const setTab = (value: string) => setParams(value === 'submissions' ? { tab: value } : {}, { replace: true });
  const [totalLessons, setTotalLessons] = useState(0);
  const [retry, setRetry] = useState(0);
  const [items, setItems] = useState<ProgressItem[]>([]);
  const [submissions, setSubmissions] = useState<LearningSubmissionListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState<LearningSubmissionDetail | null>(null);
  const owner = auth.principal?.user_id ?? auth.mode;
  const [loadedOwner, setLoadedOwner] = useState<string | null>(null);
  const hasCurrentData = loadedOwner !== null && loadedOwner === owner;

  useEffect(() => {
    setItems([]); setSubmissions([]); setDetail(null); setDetailOpen(false);
    setLoadedOwner(null);
  }, [owner]);

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
      setTotalLessons(progress.total_lessons ?? 0);
      setSubmissions(submitted.items || []);
      setLoadedOwner(owner);
    }).catch((loadError) => {
      if (active) setError(loadError instanceof TypeError ? '网络连接失败，学习记录暂不可用，请重试。'
        : loadError instanceof Error ? loadError.message.replace(/^\d{3}\s+/, '') : '学习记录载入失败');
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [auth.mode, owner, retry]);

  const currentItems = useMemo(
    () => items.filter((item) => item.reading_status !== 'unavailable'),
    [items],
  );
  const archivedItems = useMemo(
    () => items.filter((item) => item.reading_status === 'unavailable'),
    [items],
  );
  const stats = useMemo(() => ({
    lessons: currentItems.length,
    completedLessons: items.filter(readingComplete).length,
    submissions: submissions.length,
    feedback: submissions.filter((item) => item.latest_feedback).length,
  }), [currentItems.length, items, submissions]);

  const openDetail = async (submissionId: string) => {
    setDetail(null);
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
          <span>阅读统计只记录本人确认的当前课文，不代表测验掌握度；互动完成标记仅是历史活动记录。</span>
        </div>
        <dl>
          <div><dt>{hasCurrentData ? stats.lessons : '—'}</dt><dd>有活动记录的当前课号</dd></div>
          <div><dt>{hasCurrentData ? `${stats.completedLessons}/${totalLessons}` : '—'}</dt><dd>本人确认已读当前课文</dd></div>
          <div><dt>{hasCurrentData ? stats.submissions : '—'}</dt><dd>已载入提交版本（最多 100）</dd></div>
          <div><dt>{hasCurrentData ? stats.feedback : '—'}</dt><dd>其中有教师反馈</dd></div>
        </dl>
      </header>

      {error ? <Alert type="warning" showIcon message={error} action={<Button onClick={() => setRetry((value) => value + 1)}>重试</Button>} /> : null}

      <nav className="chrono-learning-tabs" aria-label="学习记录分类">
        <button type="button" className={tab === 'progress' ? 'active' : ''} onClick={() => setTab('progress')}>
          <BookOutlined /> 学习进程 <span>{currentItems.length}</span>
        </button>
        <button type="button" className={tab === 'submissions' ? 'active' : ''} onClick={() => setTab('submissions')}>
          <FileDoneOutlined /> 已提交成果 <span>{submissions.length}</span>
        </button>
      </nav>

      {loading || (loadedOwner !== null && !hasCurrentData) ? (
        <div className="chrono-learning-loading"><Spin /><span>正在展开学习长卷…</span></div>
      ) : !hasCurrentData && error ? <Empty description="学习记录暂不可用，恢复连接后可重试。" /> : tab === 'progress' ? (
        currentItems.length > 0 ? (
          <>
          <section className="chrono-learning-progress-grid">
            {currentItems.map((item) => {
              return (
                <article key={item.lesson_id}>
                  <CourseCoverPicture
                    courseId={item.course_id || 'C-prequin-state'}
                    width={720}
                    fallbackColor="#69553e"
                  />
                  <div>
                    <p>{item.lesson_id} · 上次进入{LAYER_LABEL[item.last_layer] ?? item.last_layer}</p>
                    <h2>{item.title ?? item.lesson_id}</h2>
                    <div className="chrono-learning-stage-marks">
                      <span>{readingLabel(item)}</span>
                      {(['practice', 'ask', 'create'] as const).map((layer) => (
                        <span className={item.layers[layer] ? 'done' : ''} key={layer}>
                          {item.layers[layer] ? <CheckCircleOutlined /> : <ClockCircleOutlined />}
                          {LAYER_LABEL[layer]}{item.layers[layer] ? '有完成记录' : '无完成记录'}
                        </span>
                      ))}
                    </div>
                    <footer>
                      <time>{formatTime(item.updated_at)}</time>
                      <Button type="link" disabled={item.reading_status === 'unavailable'} onClick={() => item.course_id
                        ? nav(`/courses/${item.course_id}/lessons/${item.lesson_id}?layer=${resumeLayer(item)}`)
                        : nav('/courses')}
                      >继续学习 <ArrowRightOutlined /></Button>
                    </footer>
                  </div>
                </article>
              );
            })}
          </section>
          {archivedItems.length > 0 ? (
            <Alert
              type="info"
              showIcon
              message={`另有 ${archivedItems.length} 条历史课号记录已撤下`}
              description="这些记录保留用于审计，不计入当前课程进度，也不会作为继续学习入口。"
            />
          ) : null}
          </>
        ) : (
          <Empty description={archivedItems.length > 0 ? '当前课表暂无活动记录（历史课号已撤下）' : '还没有学习记录'}>
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
                <p>{item.lesson_title ?? `已撤下课时 ${item.lesson_id}`}</p>
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
