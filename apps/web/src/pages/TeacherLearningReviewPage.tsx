import { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Empty, Input, Radio, Spin, Tag } from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  FileSearchOutlined,
  MessageOutlined,
  ReloadOutlined,
  SendOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import LearningSubmissionViewer from '../features/classroom/LearningSubmissionViewer';
import { createClientFeedbackId } from '../features/classroom/learningSubmission';
import {
  api,
  type LearningCompletionStatus,
  type LearningFeedbackRequest,
  type LearningSubmissionDetail,
  type LearningSubmissionListItem,
} from '../utils/api';
import './TeacherLearningReviewPage.css';

const STATUS_LABEL: Record<LearningCompletionStatus, string> = {
  in_review: '继续观察',
  changes_requested: '建议修改',
  completed: '确认完成',
};

const LESSON_LABELS: Record<string, string> = {
  L101: '大禹治水：洪水记忆与早期国家',
  L103: '商鞅变法：富国强兵与制度代价',
};

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message.replace(/^\d{3}\s+/, '') : '请求失败，请稍后重试。';
}

export default function TeacherLearningReviewPage() {
  const [items, setItems] = useState<LearningSubmissionListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState<LearningSubmissionDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [completionStatus, setCompletionStatus] = useState<LearningCompletionStatus>('in_review');
  const [comment, setComment] = useState('');
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  const [pendingFeedback, setPendingFeedback] = useState<{
    submissionId: string; request: LearningFeedbackRequest;
  } | null>(null);

  const loadQueue = useCallback(async (preserveSelection = true) => {
    setLoading(true);
    setError('');
    try {
      const response = await api.learningReviewSubmissions({ limit: 100 });
      setItems(response.items);
      setSelectedId((current) => (
        preserveSelection && response.items.some((item) => item.submission_id === current)
          ? current
          : response.items[0]?.submission_id ?? ''
      ));
    } catch (loadError) {
      setError(errorMessage(loadError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadQueue(false); }, [loadQueue]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return undefined;
    }
    let active = true;
    setComment('');
    setDetailLoading(true);
    api.learningReviewSubmission(selectedId)
      .then((response) => {
        if (!active) return;
        setDetail(response);
        const latest = response.feedback.at(-1);
        setCompletionStatus(latest?.completion_status ?? 'in_review');
      })
      .catch((loadError) => {
        if (active) setError(errorMessage(loadError));
      })
      .finally(() => {
        if (active) setDetailLoading(false);
      });
    return () => { active = false; };
  }, [selectedId]);

  const filteredItems = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase('zh-CN');
    if (!needle) return items;
    return items.filter((item) => [
      item.student_display_name,
      item.student_username ?? '',
      item.title,
      item.lesson_id,
      LESSON_LABELS[item.lesson_id] ?? '',
    ].some((value) => value.toLocaleLowerCase('zh-CN').includes(needle)));
  }, [items, query]);

  const stats = useMemo(() => ({
    total: items.length,
    awaiting: items.filter((item) => !item.latest_feedback).length,
    changes: items.filter((item) => item.latest_feedback?.completion_status === 'changes_requested').length,
    completed: items.filter((item) => item.latest_feedback?.completion_status === 'completed').length,
  }), [items]);

  const sendFeedback = async () => {
    if (!selectedId || feedbackLoading) return;
    const trimmed = comment.trim();
    let pending = pendingFeedback?.submissionId === selectedId ? pendingFeedback : null;
    if (!pending) {
      if (!trimmed) {
        setError('请先写下具体反馈，再发送给学生。');
        return;
      }
      pending = {
        submissionId: selectedId,
        request: {
          schema_version: 'learning-feedback-request/v1',
          client_feedback_id: createClientFeedbackId(),
          completion_status: completionStatus,
          comment: trimmed,
        },
      };
      setPendingFeedback(pending);
    }

    setFeedbackLoading(true);
    setError('');
    try {
      await api.learningReviewFeedback(pending.submissionId, pending.request);
      setPendingFeedback(null);
      setComment('');
      const refreshed = await api.learningReviewSubmission(selectedId);
      setDetail(refreshed);
      await loadQueue(true);
    } catch (submitError) {
      setError(`反馈尚未得到服务器确认：${errorMessage(submitError)}。再次发送会原样重试，不会覆盖既有反馈。`);
    } finally {
      setFeedbackLoading(false);
    }
  };

  return (
    <div className="chrono-review-page" data-testid="learning-review">
      <header className="chrono-review-hero">
        <div className="chrono-review-orbit" aria-hidden="true"><span /><span /><span /></div>
        <div>
          <p>TEACHER · LEARNING ARCHIVE</p>
          <h1>学生学习成果</h1>
          <span>这里只呈现学生明确提交的不可变版本；本机草稿和未确认上传始终对教师不可见。</span>
        </div>
        <dl>
          <div><dt>{stats.total}</dt><dd>提交版本</dd></div>
          <div><dt>{stats.awaiting}</dt><dd>等待查看</dd></div>
          <div><dt>{stats.changes}</dt><dd>建议修改</dd></div>
          <div><dt>{stats.completed}</dt><dd>确认完成</dd></div>
        </dl>
      </header>

      {error ? <Alert closable type="warning" showIcon message={error} onClose={() => setError('')} /> : null}

      <div className="chrono-review-layout">
        <aside className="chrono-review-queue">
          <header>
            <div><TeamOutlined /><strong>成果队列</strong></div>
            <Button type="text" icon={<ReloadOutlined />} loading={loading} aria-label="刷新成果队列" onClick={() => void loadQueue()} />
          </header>
          <Input
            allowClear
            prefix={<FileSearchOutlined />}
            value={query}
            placeholder="搜索学生、课时或标题"
            onChange={(event) => setQuery(event.target.value)}
          />
          <div className="chrono-review-queue-list">
            {loading ? (
              <div className="chrono-review-loading"><Spin /><span>正在调阅成果…</span></div>
            ) : filteredItems.length > 0 ? filteredItems.map((item) => (
              <button
                type="button"
                key={item.submission_id}
                className={selectedId === item.submission_id ? 'active' : ''}
                onClick={() => setSelectedId(item.submission_id)}
              >
                <div>
                  <span>{item.student_display_name}</span>
                  <small>{formatDateTime(item.submitted_at)}</small>
                </div>
                <strong>{item.title}</strong>
                <p>{LESSON_LABELS[item.lesson_id] ?? item.lesson_id} · 第 {item.version} 版</p>
                {item.latest_feedback ? (
                  <Tag color={item.latest_feedback.completion_status === 'completed' ? 'green' : item.latest_feedback.completion_status === 'changes_requested' ? 'volcano' : 'gold'}>
                    {STATUS_LABEL[item.latest_feedback.completion_status]}
                  </Tag>
                ) : <Tag icon={<ClockCircleOutlined />}>未反馈</Tag>}
              </button>
            )) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的提交版本" />
            )}
          </div>
        </aside>

        <main className="chrono-review-workspace">
          {!selectedId ? (
            <Empty description="学生提交成果后会出现在这里" />
          ) : detailLoading ? (
            <div className="chrono-review-loading is-large"><Spin /><span>正在展开学习书案…</span></div>
          ) : detail ? (
            <>
              <section className="chrono-review-feedback-composer" aria-label="教师反馈编辑器">
                <div className="chrono-review-feedback-title">
                  <div><MessageOutlined /><span><strong>写给 {detail.student_display_name}</strong><small>反馈按时间追加，不覆盖此前记录</small></span></div>
                  {pendingFeedback?.submissionId === selectedId ? <Tag color="gold">等待重试</Tag> : null}
                </div>
                <Radio.Group
                  optionType="button"
                  buttonStyle="solid"
                  value={completionStatus}
                  options={([
                    ['in_review', '继续观察'],
                    ['changes_requested', '建议修改'],
                    ['completed', '确认完成'],
                  ] as const).map(([value, label]) => ({ value, label }))}
                  onChange={(event) => setCompletionStatus(event.target.value)}
                  disabled={Boolean(pendingFeedback?.submissionId === selectedId)}
                />
                <Input.TextArea
                  value={comment}
                  maxLength={4000}
                  showCount
                  autoSize={{ minRows: 3, maxRows: 8 }}
                  placeholder="指出证据使用、因果解释或历史边界中值得肯定和需要继续修改的地方。"
                  disabled={Boolean(pendingFeedback?.submissionId === selectedId)}
                  onChange={(event) => setComment(event.target.value)}
                />
                <div>
                  <span>{pendingFeedback?.submissionId === selectedId
                    ? '将原样重试上一次反馈，避免网络中断产生重复记录。'
                    : '学生能在自己的成果版本中看到教师姓名、状态与完整反馈。'}</span>
                  <Button
                    type="primary"
                    icon={completionStatus === 'completed' ? <CheckCircleOutlined /> : <SendOutlined />}
                    loading={feedbackLoading}
                    disabled={!comment.trim() && pendingFeedback?.submissionId !== selectedId}
                    onClick={() => void sendFeedback()}
                  >{pendingFeedback?.submissionId === selectedId ? '重试发送' : '追加反馈'}</Button>
                </div>
              </section>
              <LearningSubmissionViewer detail={detail} />
            </>
          ) : (
            <Empty description="当前成果暂时无法读取" />
          )}
        </main>
      </div>
    </div>
  );
}
