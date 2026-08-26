import { Empty, Tag } from 'antd';
import {
  ApartmentOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  EditOutlined,
  FileTextOutlined,
  HistoryOutlined,
  MessageOutlined,
} from '@ant-design/icons';
import ReactFlow, { Background, Controls, type Edge, type Node } from 'reactflow';
import 'reactflow/dist/style.css';
import type {
  LearningCompletionStatus,
  LearningDrawingStroke,
  LearningSubmissionDetail,
} from '../../utils/api';
import { markdownToSafeHtml } from './learningDeskDocument';
import './LearningSubmissionViewer.css';

const STATUS_LABEL: Record<LearningCompletionStatus, string> = {
  in_review: '待继续批阅',
  changes_requested: '建议修改',
  completed: '已完成',
};

const STATUS_COLOR: Record<LearningCompletionStatus, string> = {
  in_review: 'gold',
  changes_requested: 'volcano',
  completed: 'green',
};

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

function strokePath(stroke: LearningDrawingStroke): string {
  return stroke.points.map((point, index) => (
    `${index === 0 ? 'M' : 'L'} ${point.x * 1000} ${point.y * 600}`
  )).join(' ');
}

function safeCanvasNodes(items: unknown[]): Node[] {
  return items.flatMap((item) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return [];
    const candidate = item as Record<string, unknown>;
    const position = candidate.position as Record<string, unknown> | undefined;
    const data = candidate.data as Record<string, unknown> | undefined;
    if (
      typeof candidate.id !== 'string'
      || typeof position?.x !== 'number'
      || typeof position?.y !== 'number'
      || typeof data?.label !== 'string'
    ) return [];
    return [{
      id: candidate.id,
      position: { x: position.x, y: position.y },
      data: { label: data.label },
      style: {
        border: '1px solid #b48a49',
        borderRadius: 4,
        background: '#fffaf0',
        color: '#24302f',
        fontFamily: 'STKaiti, KaiTi, serif',
      },
    }];
  });
}

function safeCanvasEdges(items: unknown[], nodeIds: Set<string>): Edge[] {
  return items.flatMap((item) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return [];
    const candidate = item as Record<string, unknown>;
    if (
      typeof candidate.id !== 'string'
      || typeof candidate.source !== 'string'
      || typeof candidate.target !== 'string'
      || !nodeIds.has(candidate.source)
      || !nodeIds.has(candidate.target)
    ) return [];
    return [{
      id: candidate.id,
      source: candidate.source,
      target: candidate.target,
      label: typeof candidate.label === 'string' ? candidate.label : undefined,
      style: { stroke: '#987443' },
      labelStyle: { fill: '#594b38', fontSize: 11 },
    }];
  });
}

export default function LearningSubmissionViewer({
  detail,
  showStudent = true,
}: {
  detail: LearningSubmissionDetail;
  showStudent?: boolean;
}) {
  const { submission, feedback } = detail;
  const canvasNodes = safeCanvasNodes(submission.canvas.nodes);
  const canvasEdges = safeCanvasEdges(
    submission.canvas.edges,
    new Set(canvasNodes.map((node) => node.id)),
  );
  const latestFeedback = feedback.at(-1) ?? null;

  return (
    <article className="chrono-submission-viewer">
      <header className="chrono-submission-viewer-head">
        <div>
          <p>{showStudent ? `${detail.student_display_name} · ` : ''}{submission.course_id} / {submission.lesson_id}</p>
          <h2>{submission.title}</h2>
          <span>第 {submission.version} 版 · {formatDateTime(submission.submitted_at)}</span>
        </div>
        <div className="chrono-submission-viewer-status">
          {latestFeedback ? (
            <Tag color={STATUS_COLOR[latestFeedback.completion_status]}>
              {STATUS_LABEL[latestFeedback.completion_status]}
            </Tag>
          ) : <Tag icon={<ClockCircleOutlined />} color="gold">等待教师查看</Tag>}
          <small>校验 {submission.checksum.slice(0, 10)}</small>
        </div>
      </header>

      <div className="chrono-submission-facts">
        <span><FileTextOutlined /> {submission.body_markdown.length} 字符正文</span>
        <span><EditOutlined /> {submission.sticky_notes.length} 张便签</span>
        <span><HistoryOutlined /> {submission.learning_events.length} 条轨迹</span>
        <span><ApartmentOutlined /> {canvasNodes.length} 个导图节点</span>
      </div>

      <section className="chrono-submission-section">
        <div className="chrono-submission-section-title"><FileTextOutlined /><h3>学习正文</h3></div>
        {submission.body_markdown.trim() ? (
          <div
            className="chrono-submission-paper"
            dangerouslySetInnerHTML={{ __html: markdownToSafeHtml(submission.body_markdown) }}
          />
        ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="这一版没有正文" />}
      </section>

      <div className="chrono-submission-pair">
        <section className="chrono-submission-section">
          <div className="chrono-submission-section-title"><EditOutlined /><h3>便签</h3></div>
          {submission.sticky_notes.length > 0 ? (
            <div className="chrono-submission-stickies">
              {submission.sticky_notes.map((note) => (
                <blockquote className={note.color} key={note.note_id}>{note.body || '空白便签'}</blockquote>
              ))}
            </div>
          ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有便签" />}
        </section>

        <section className="chrono-submission-section">
          <div className="chrono-submission-section-title"><EditOutlined /><h3>手写与绘图</h3></div>
          {submission.drawing_strokes.length > 0 ? (
            <svg className="chrono-submission-drawing" viewBox="0 0 1000 600" role="img" aria-label="学生手写与绘图快照">
              <rect width="1000" height="600" fill="#fbf5e6" />
              {submission.drawing_strokes.map((stroke) => (
                <path
                  key={stroke.stroke_id}
                  d={strokePath(stroke)}
                  fill="none"
                  stroke={stroke.mode === 'erase' ? '#fbf5e6' : stroke.color}
                  strokeWidth={stroke.width * 2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              ))}
            </svg>
          ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有手写笔迹" />}
        </section>
      </div>

      <section className="chrono-submission-section">
        <div className="chrono-submission-section-title"><ApartmentOutlined /><h3>知识导图快照</h3></div>
        {submission.canvas.found && canvasNodes.length > 0 ? (
          <div className="chrono-submission-canvas" aria-label="只读知识导图快照">
            <ReactFlow
              nodes={canvasNodes}
              edges={canvasEdges}
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable
              fitView
            >
              <Background gap={22} color="#dfd3bb" />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
        ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="提交时没有可用的导图快照" />}
      </section>

      <section className="chrono-submission-section">
        <div className="chrono-submission-section-title"><HistoryOutlined /><h3>学习轨迹</h3></div>
        {submission.learning_events.length > 0 ? (
          <ol className="chrono-submission-trail">
            {[...submission.learning_events].reverse().map((event) => (
              <li key={event.event_id}>
                <time>{formatDateTime(event.occurred_at)}</time>
                <div><strong>{event.title}</strong><p>{event.summary}</p></div>
              </li>
            ))}
          </ol>
        ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有学习轨迹" />}
      </section>

      <section className="chrono-submission-section chrono-submission-feedback">
        <div className="chrono-submission-section-title"><MessageOutlined /><h3>教师反馈</h3></div>
        {feedback.length > 0 ? (
          <ol>
            {[...feedback].reverse().map((item) => (
              <li key={item.feedback_id}>
                <div>
                  <strong>{item.teacher_display_name}</strong>
                  <Tag color={STATUS_COLOR[item.completion_status]}>{STATUS_LABEL[item.completion_status]}</Tag>
                  <time>{formatDateTime(item.created_at)}</time>
                </div>
                <p>{item.comment}</p>
              </li>
            ))}
          </ol>
        ) : (
          <div className="chrono-submission-awaiting"><CheckCircleOutlined /> 本版已安全提交，等待教师反馈。</div>
        )}
      </section>
    </article>
  );
}
