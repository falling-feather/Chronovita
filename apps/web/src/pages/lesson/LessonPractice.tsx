import { useEffect, useState } from 'react';
import { Alert, Button, Spin, Tag } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { Lesson } from '../../utils/api';
import { api } from '../../utils/api';

interface SandboxState {
  scenario: { id: string; title: string; intro: string };
  node: any;
  state: Record<string, number>;
  ending?: string | null;
  feedback?: string | null;
}

export default function LessonPractice({ lesson }: { lesson: Lesson }) {
  const sid = lesson.sandbox_id;
  const [data, setData] = useState<SandboxState | null>(null);
  const [loading, setLoading] = useState(false);

  const reset = async () => {
    if (!sid) return;
    setLoading(true);
    try {
      const r = await api.sandboxGet(sid);
      setData({ ...r, feedback: null, ending: null });
    } finally { setLoading(false); }
  };

  useEffect(() => { reset(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [sid]);

  if (!sid) {
    return <Alert type="info" message="本节暂未配套决策沙盘" description="可前往「商鞅变法」一节体验完整剧本，或在后续版本等待新剧本上线。" />;
  }
  if (loading || !data) return <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>;

  const onChoose = async (choiceKey: string) => {
    if (data.ending) return;
    setLoading(true);
    try {
      const r = await api.sandboxStep(sid, { node_id: data.node.id, choice: choiceKey, state: data.state });
      setData({
        ...data,
        node: r.next_node || data.node,
        state: r.state,
        feedback: r.feedback,
        ending: r.ending,
      });
    } finally { setLoading(false); }
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 260px', gap: 20 }}>
      <div className="chrono-card">
        <div style={{ marginBottom: 10 }}>
          <Tag color="gold">决策沙盘</Tag>
          <span className="chrono-title" style={{ fontSize: 16, marginLeft: 8 }}>{data.scenario.title}</span>
        </div>
        <div style={{ color: 'var(--text-mute)', fontSize: 12, marginBottom: 16 }}>{data.scenario.intro}</div>

        {data.feedback && (
          <Alert type="info" showIcon message={data.feedback} style={{ marginBottom: 14 }} />
        )}

        <div style={{ background: 'var(--bg-warm-soft)', padding: 16, borderRadius: 6, marginBottom: 16 }}>
          <div className="chrono-title" style={{ fontSize: 16, marginBottom: 8 }}>{data.node.title}</div>
          <div style={{ fontSize: 14, color: 'var(--text-dark)', lineHeight: 1.8 }}>{data.node.narration}</div>
        </div>

        {data.ending ? (
          <Alert type="success" showIcon message="本剧本结束" description={data.ending} />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {(data.node.choices || []).map((c: any) => (
              <Button key={c.key} block size="large" onClick={() => onChoose(c.key)} style={{ textAlign: 'left' }}>
                <span style={{ color: 'var(--accent-gold)', marginRight: 8 }}>{c.key}.</span>{c.label}
              </Button>
            ))}
          </div>
        )}

        <div style={{ marginTop: 16 }}>
          <Button icon={<ReloadOutlined />} onClick={reset}>重新开始</Button>
        </div>
      </div>

      <div className="chrono-card">
        <div className="chrono-title" style={{ fontSize: 14, marginBottom: 12 }}>当前态势</div>
        {Object.entries(data.state).map(([k, v]) => (
          <div key={k} style={{ marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-mute)' }}>
              <span>{k}</span><span>{v}</span>
            </div>
            <div style={{ height: 6, background: 'var(--border-soft)', borderRadius: 3, overflow: 'hidden', marginTop: 4 }}>
              <div style={{ width: `${v}%`, height: '100%', background: 'var(--accent-gold)' }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
