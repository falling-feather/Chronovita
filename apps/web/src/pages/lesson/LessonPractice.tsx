import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Input, Spin, Tag, Tooltip } from 'antd';
import { ReloadOutlined, SendOutlined, ReadOutlined } from '@ant-design/icons';
import type { Lesson, SagaState, SagaEntity } from '../../utils/api';
import { api, streamSagaAct } from '../../utils/api';

const SAGA_LESSON_IDS = new Set([
  // 先秦
  'L101', 'L102', 'L103', 'L104', 'L105',
  // 秦汉 · 一统肇基
  'L401', 'L402', 'L403',
  // 秦汉 · 两汉思想与科技
  'L501', 'L502', 'L503',
]);

interface Paragraph {
  role: 'narrator' | 'player';
  text: string;
  typing?: boolean;
  visible?: number;
}

export default function LessonPractice({ lesson }: { lesson: Lesson }) {
  const hasSaga = SAGA_LESSON_IDS.has(lesson.id);
  if (!hasSaga) return <FallbackSandbox lesson={lesson} />;
  return <SagaPlayer lesson={lesson} />;
}

function SagaPlayer({ lesson }: { lesson: Lesson }) {
  const [state, setState] = useState<SagaState | null>(null);
  const [paragraphs, setParagraphs] = useState<Paragraph[]>([]);
  const [entities, setEntities] = useState<SagaEntity[]>([]);
  const [choices, setChoices] = useState<string[]>([]);
  const [free, setFree] = useState('');
  const [loading, setLoading] = useState(false);
  const [bootLoading, setBootLoading] = useState(false);
  const [ended, setEnded] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const typeTimer = useRef<number | null>(null);

  const start = async () => {
    setBootLoading(true);
    try {
      const s = await api.sagaStart(lesson.id);
      setState(s);
      setEntities(s.entities);
      setChoices(s.choices);
      setEnded(s.ended);
      setParagraphs([{ role: 'narrator', text: s.history[0].text, typing: true, visible: 0 }]);
      startTypewriter(0, s.history[0].text);
    } finally { setBootLoading(false); }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { start(); return () => { if (typeTimer.current) window.clearInterval(typeTimer.current); }; }, [lesson.id]);

  function startTypewriter(idx: number, fullText: string) {
    if (typeTimer.current) window.clearInterval(typeTimer.current);
    let pos = 0;
    typeTimer.current = window.setInterval(() => {
      pos += 2;
      setParagraphs(prev => {
        const arr = [...prev];
        if (!arr[idx]) return prev;
        arr[idx] = { ...arr[idx], visible: Math.min(pos, fullText.length) };
        if (pos >= fullText.length) {
          arr[idx].typing = false;
          if (typeTimer.current) { window.clearInterval(typeTimer.current); typeTimer.current = null; }
        }
        return arr;
      });
      if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }, 28);
  }

  function skipTypewriter() {
    if (typeTimer.current) { window.clearInterval(typeTimer.current); typeTimer.current = null; }
    setParagraphs(prev => prev.map(p => ({ ...p, typing: false, visible: p.text.length })));
  }

  const submit = async (action: string) => {
    if (!state || loading || ended) return;
    skipTypewriter();
    const playerIdx = paragraphs.length;
    const narratorIdx = playerIdx + 1;
    setParagraphs(prev => [
      ...prev,
      { role: 'player', text: action, typing: false, visible: action.length },
      { role: 'narrator', text: '', typing: true, visible: 0 },
    ]);
    setChoices([]);
    setLoading(true);
    setFree('');

    let buf = '';
    let meta: any = null;
    try {
      await streamSagaAct(state.saga_id, action, (chunk) => {
        buf += chunk;
        const idx = buf.indexOf('\n\n[META]');
        let narrative = buf;
        if (idx >= 0) {
          narrative = buf.slice(0, idx);
          const metaJson = buf.slice(idx + '\n\n[META]'.length).trim();
          try { meta = JSON.parse(metaJson); } catch { /* 流未完整 */ }
        }
        setParagraphs(prev => {
          const arr = [...prev];
          if (!arr[narratorIdx]) return prev;
          arr[narratorIdx] = { ...arr[narratorIdx], text: narrative, visible: narrative.length };
          return arr;
        });
        if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      });
    } finally {
      setLoading(false);
      setParagraphs(prev => {
        const arr = [...prev];
        if (arr[narratorIdx]) arr[narratorIdx] = { ...arr[narratorIdx], typing: false };
        return arr;
      });
      if (meta) {
        if (Array.isArray(meta.choices)) setChoices(meta.choices);
        if (Array.isArray(meta.entities)) setEntities(meta.entities);
        if (meta.ended) setEnded(true);
      }
    }
  };

  if (bootLoading || !state) {
    return <div style={{ textAlign: 'center', padding: 64 }}><Spin tip="正在生成开场..." /></div>;
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 280px', gap: 20 }}>
      <div className="chrono-card" style={{ display: 'flex', flexDirection: 'column', minHeight: 580 }}>
        <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <Tag color="gold" icon={<ReadOutlined />}>互动小说</Tag>
            <span className="chrono-title" style={{ fontSize: 16, marginLeft: 8 }}>{state.title}</span>
            <span style={{ marginLeft: 12, fontSize: 12, color: 'var(--text-mute)' }}>{state.era}</span>
          </div>
          <Tooltip title="重新开始本剧本"><Button size="small" icon={<ReloadOutlined />} onClick={start} /></Tooltip>
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-mute)', marginBottom: 14, fontStyle: 'italic' }}>
          身份｜{state.persona}
        </div>

        <div ref={scrollRef} className="chrono-saga-stage" onClick={skipTypewriter}>
          {paragraphs.map((p, i) => {
            const visText = p.visible !== undefined ? p.text.slice(0, p.visible) : p.text;
            if (p.role === 'player') {
              return (
                <div key={i} className="chrono-saga-player">
                  <div className="chrono-saga-player-tag">我的行动</div>
                  <div className="chrono-saga-player-text">{p.text}</div>
                </div>
              );
            }
            const lines = visText.split('\n');
            return (
              <div key={i} className="chrono-saga-narrator">
                {lines.map((line, j) => (
                  <p key={j}>{line}{p.typing && j === lines.length - 1 && <span className="chrono-saga-caret">▍</span>}</p>
                ))}
              </div>
            );
          })}
          {loading && (
            <div style={{ textAlign: 'center', color: 'var(--text-mute)', fontSize: 12, marginTop: 8 }}>
              <Spin size="small" /> &nbsp;正在续写...
            </div>
          )}
        </div>

        {ended ? (
          <Alert type="success" showIcon message="本剧本告一段落" description="你可以「重新开始」体验不同选择带来的历史分岔。" style={{ marginTop: 14 }} />
        ) : (
          <div style={{ marginTop: 14 }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
              {choices.map((c, i) => (
                <Button key={i} disabled={loading} onClick={() => submit(c)}
                  style={{ whiteSpace: 'normal', height: 'auto', padding: '8px 14px', textAlign: 'left', maxWidth: '100%' }}>
                  <span style={{ color: 'var(--accent-gold)', marginRight: 6 }}>{i + 1}.</span>{c}
                </Button>
              ))}
            </div>
            <Input.TextArea
              value={free}
              onChange={e => setFree(e.target.value)}
              placeholder="或写下自由行动（按 Ctrl+Enter 提交）"
              autoSize={{ minRows: 2, maxRows: 4 }}
              disabled={loading}
              onPressEnter={(e) => {
                if ((e.ctrlKey || e.metaKey) && free.trim()) submit(free.trim());
              }}
            />
            <div style={{ marginTop: 8, textAlign: 'right' }}>
              <Button type="primary" icon={<SendOutlined />} loading={loading} disabled={!free.trim()} onClick={() => submit(free.trim())}>
                提交
              </Button>
            </div>
          </div>
        )}
      </div>

      <div>
        <div className="chrono-card" style={{ marginBottom: 16 }}>
          <div className="chrono-title" style={{ fontSize: 14, marginBottom: 10 }}>本节关键词</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {state.keywords.map(k => <Tag key={k}>{k}</Tag>)}
          </div>
        </div>
        <div className="chrono-card">
          <div className="chrono-title" style={{ fontSize: 14, marginBottom: 10 }}>
            已出场实体 <span style={{ fontSize: 11, color: 'var(--text-mute)', fontWeight: 'normal' }}>· LLM 提取</span>
          </div>
          {entities.length === 0 ? (
            <div style={{ fontSize: 12, color: 'var(--text-mute)' }}>暂无</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {entities.map(e => (
                <div key={e.name} style={{ borderLeft: '3px solid var(--accent-gold)', paddingLeft: 8 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-dark)' }}>
                    {e.name} <Tag color="gold" style={{ marginLeft: 4, fontSize: 10 }}>{e.type}</Tag>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-mute)', lineHeight: 1.5 }}>{e.desc}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function FallbackSandbox({ lesson }: { lesson: Lesson }) {
  const sid = lesson.sandbox_id;
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const reset = async () => {
    if (!sid) return;
    setLoading(true);
    try { const r = await api.sandboxGet(sid); setData({ ...r, feedback: null, ending: null }); }
    finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { reset(); }, [sid]);

  if (!sid) return <Alert type="info" message="本节暂未配套互动剧本" description="后续版本将为本节生成动态互动小说。" />;
  if (loading || !data) return <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>;

  const onChoose = async (key: string) => {
    setLoading(true);
    try {
      const r = await api.sandboxStep(sid, { node_id: data.node.id, choice: key, state: data.state });
      setData({ ...data, node: r.next_node || data.node, state: r.state, feedback: r.feedback, ending: r.ending });
    } finally { setLoading(false); }
  };
  return (
    <div className="chrono-card">
      <Tag color="gold">决策沙盘</Tag>
      <div className="chrono-title" style={{ fontSize: 16, margin: '8px 0' }}>{data.scenario.title}</div>
      <div style={{ fontSize: 12, color: 'var(--text-mute)', marginBottom: 12 }}>{data.scenario.intro}</div>
      {data.feedback && <Alert type="info" message={data.feedback} style={{ marginBottom: 12 }} />}
      <div style={{ background: 'var(--bg-warm-soft)', padding: 14, borderRadius: 6, marginBottom: 14 }}>
        <div className="chrono-title" style={{ fontSize: 15, marginBottom: 6 }}>{data.node.title}</div>
        <div style={{ lineHeight: 1.8 }}>{data.node.narration}</div>
      </div>
      {data.ending ? <Alert type="success" message="结局" description={data.ending} /> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {(data.node.choices || []).map((c: any) => (
            <Button key={c.key} block onClick={() => onChoose(c.key)} style={{ textAlign: 'left' }}>
              <span style={{ color: 'var(--accent-gold)', marginRight: 8 }}>{c.key}.</span>{c.label}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}
