import { useMemo } from 'react';
import { Button, Empty, Space, Tag } from 'antd';
import { EditOutlined, ExportOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import LessonWatch from './lesson/LessonWatch';
import type { Lesson, LessonContentPackage } from '../utils/api';
import { ADMIN_CONTENT_PREVIEW_KEY } from '../utils/adminContentStorage';

function readPreview(): LessonContentPackage | null {
  const raw = localStorage.getItem(ADMIN_CONTENT_PREVIEW_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as LessonContentPackage;
  } catch {
    return null;
  }
}

function toLesson(item: LessonContentPackage): Lesson {
  return {
    id: item.lesson_id,
    course_id: item.course_id || 'C-content-studio',
    num: item.lesson_no || 'PREVIEW',
    title: item.title,
    duration: item.duration || '08:00',
    abstract: item.abstract || item.body?.[0] || '',
    body: item.body || [],
    keywords: item.keywords || [],
    figures: (item.people || []).map((person) => person.name),
    sandbox_id: null,
    seed_canvas: (item.seed_canvas || []).map((node) => ({ id: node.id || node.label, label: node.label })),
    unit: item.unit,
    era: item.era,
    people: item.people || [],
    map_points: item.map_points || [],
    source_refs: item.source_refs || [],
    facts: item.facts || [],
    qa_points: item.qa_points || [],
    level_goals: item.level_goals || [],
    saga_material: item.saga_material || null,
    sandbox_material: item.sandbox_material || null,
    content_status: item.status || 'draft',
    content_version: item.version || 0,
    sealed_at: item.sealed_at || null,
    sealed_by: item.sealed_by || null,
    content_checksum: item.checksum || null,
    scenario_refs: [],
    primary_scenario_id: null,
  };
}

export default function AdminContentPreviewPage() {
  const payload = useMemo(readPreview, []);
  const lesson = useMemo(() => (payload ? toLesson(payload) : null), [payload]);

  if (!payload || !lesson) {
    return (
      <div className="chrono-page" style={{ maxWidth: 960, margin: '0 auto' }}>
        <div className="chrono-card" style={{ padding: 28 }}>
          <Empty description="暂无可预览内容" />
          <div style={{ textAlign: 'center', marginTop: 16 }}>
            <Link to="/admin/content">
              <Button type="primary" icon={<EditOutlined />}>返回编辑器</Button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="chrono-page" style={{ maxWidth: 1320, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
        <div>
          <div className="chrono-course-eyeline">
            <span>Admin Preview</span>
            <span>{payload.lesson_id}</span>
          </div>
          <h1 className="chrono-title" style={{ margin: 0 }}>课程预览</h1>
        </div>
        <Space wrap>
          <Tag color={payload.status === 'sealed' ? 'green' : 'gold'}>{payload.status || 'draft'}</Tag>
          <Tag>{payload.course_title || payload.course_id}</Tag>
          <Link to="/admin/content">
            <Button icon={<EditOutlined />}>返回编辑器</Button>
          </Link>
          <Link to={`/courses/${payload.course_id || 'C-content-studio'}/lessons/${payload.lesson_id}?layer=watch`}>
            <Button icon={<ExportOutlined />}>正式课程页</Button>
          </Link>
        </Space>
      </div>
      <LessonWatch lesson={lesson} />
    </div>
  );
}
