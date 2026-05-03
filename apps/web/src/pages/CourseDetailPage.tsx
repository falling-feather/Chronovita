import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button, Tag, Spin, Progress } from 'antd';
import { PlayCircleOutlined, RightOutlined } from '@ant-design/icons';
import { api, type CourseDetail } from '../utils/api';

export default function CourseDetailPage() {
  const { courseId = '' } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState<CourseDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.course(courseId).then(setData).finally(() => setLoading(false));
  }, [courseId]);

  if (loading) return <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>;
  if (!data) return <div style={{ padding: 24 }}>课程不存在</div>;
  const c = data.summary;

  return (
    <div style={{ maxWidth: 1280, margin: '0 auto' }}>
      <div style={{ marginBottom: 16 }}>
        <a onClick={() => nav('/courses')} style={{ color: 'var(--text-mute)', fontSize: 12 }}>← 返回课程中心</a>
      </div>

      <div className="chrono-card-warm" style={{ marginBottom: 24, padding: 28 }}>
        <Tag color="gold">{c.section}</Tag>
        <h1 className="chrono-title" style={{ fontSize: 30, margin: '8px 0' }}>{c.title}</h1>
        <div style={{ color: 'var(--text-mute)', marginBottom: 14 }}>{c.subtitle}</div>
        <p style={{ color: 'var(--text-dark)', fontSize: 14, lineHeight: 1.8, margin: 0 }}>{data.intro}</p>
        <div style={{ marginTop: 18, display: 'flex', alignItems: 'center', gap: 16 }}>
          <Progress percent={0} strokeColor="var(--accent-gold)" style={{ flex: 1, maxWidth: 320 }} showInfo={false} />
          <span style={{ fontSize: 12, color: 'var(--text-mute)' }}>共 {c.lesson_count} 节 · 进度 0%</span>
          {data.lessons.length > 0 && (
            <Button type="primary"
                    icon={<PlayCircleOutlined />}
                    onClick={() => nav(`/courses/${c.id}/lessons/${data.lessons[0].id}?layer=watch`)}>
              开始学习
            </Button>
          )}
        </div>
      </div>

      <h3 className="chrono-title" style={{ fontSize: 18, marginBottom: 12 }}>章节目录</h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {data.lessons.length === 0 && <div className="chrono-empty">课时内容将在后续版本上线</div>}
        {data.lessons.map((l) => (
          <div key={l.id} className="chrono-card"
               style={{ display: 'flex', alignItems: 'center', gap: 16, cursor: 'pointer' }}
               onClick={() => nav(`/courses/${c.id}/lessons/${l.id}?layer=watch`)}>
            <div style={{ fontSize: 14, color: 'var(--accent-gold)', fontWeight: 600, width: 48 }}>{l.num}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 15, color: 'var(--text-dark)' }}>{l.title}</div>
              <div style={{ fontSize: 12, color: 'var(--text-mute)', marginTop: 2 }}>时长 {l.duration} · 看 / 练 / 问 / 创 四层</div>
            </div>
            <RightOutlined style={{ color: 'var(--text-disabled)' }} />
          </div>
        ))}
      </div>
    </div>
  );
}
