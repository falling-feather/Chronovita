import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Input, Radio, Tag, Spin, Select, Tooltip } from 'antd';
import { SendOutlined, ReloadOutlined } from '@ant-design/icons';
import type { Lesson } from '../../utils/api';
import { api, streamAsk } from '../../utils/api';

interface Msg { role: 'user' | 'assistant'; content: string }

const DEFAULT_PEERS = ['孔子', '司马迁', '李白', '苏轼', '王安石'];

function buildGreeting(persona: 'expert' | 'peer', lesson: Lesson, peer: string): string {
  if (persona === 'expert') {
    return `你好，我是历史教师，专攻「${lesson.title}」相关的脉络与争议。你想从哪一点切入？`;
  }
  return `吾乃${peer}。今与汝相遇于「${lesson.title}」之间——汝有何疑，但问无妨。`;
}

export default function LessonAsk({ lesson }: { lesson: Lesson }) {
  const [persona, setPersona] = useState<'expert' | 'peer'>('expert');
  const peerCandidates = useMemo(() => {
    const pool = (lesson.figures || []).filter(Boolean);
    return pool.length > 0 ? pool : DEFAULT_PEERS;
  }, [lesson.figures]);
  const [peerCharacter, setPeerCharacter] = useState<string>(peerCandidates[0]);
  const [era, setEra] = useState<string>('');
  const [history, setHistory] = useState<Msg[]>([
    { role: 'assistant', content: buildGreeting('expert', lesson, peerCandidates[0]) },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [llmInfo, setLlmInfo] = useState<{ provider: string; ask_provider?: string }>({ provider: '' });
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.course(lesson.course_id).then((c) => setEra(c.summary.era_id)).catch(() => {});
  }, [lesson.course_id]);

  useEffect(() => { api.llmInfo().then(setLlmInfo).catch(() => {}); }, []);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [history, loading]);

  const resetGreeting = (p: 'expert' | 'peer', peer: string) => {
    setHistory([{ role: 'assistant', content: buildGreeting(p, lesson, peer) }]);
  };

  const onPersonaChange = (p: 'expert' | 'peer') => {
    setPersona(p);
    resetGreeting(p, peerCharacter);
  };

  const onPeerChange = (name: string) => {
    setPeerCharacter(name);
    if (persona === 'peer') resetGreeting('peer', name);
  };

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput('');
    const next: Msg[] = [...history, { role: 'user', content: text }, { role: 'assistant', content: '' }];
    setHistory(next);
    setLoading(true);
    try {
      await streamAsk(
        {
          user_message: text,
          persona,
          lesson_id: lesson.id,
          lesson_title: lesson.title,
          peer_character: persona === 'peer' ? peerCharacter : undefined,
          era: era || undefined,
          history: history.slice(-6),
        },
        (chunk) => {
          setHistory((cur) => {
            if (cur.length === 0) return cur;
            const last = cur[cur.length - 1];
            if (last.role !== 'assistant') return cur;
            // 不可变更新：避免 StrictMode 双重调用 reducer 导致 mutate 累计
            return [...cur.slice(0, -1), { ...last, content: last.content + chunk }];
          });
        },
      );
    } finally {
      setLoading(false);
    }
  };

  const suggestExpert = [
    `${lesson.title} 反映了什么历史趋势？`,
    '能否对比同时期其他文明或诸侯国？',
    '学界对此有哪些主要争议？',
    '这件事对后世产生了哪些影响？',
  ];
  const suggestPeer = [
    `请问先生，${lesson.title} 当时的实际情形是怎样的？`,
    '您对这一时期的世道人心怎么看？',
    '您与同时代的其他人物有过哪些交往？',
    '若让您给后人留一句话，您愿说什么？',
  ];
  const suggests = persona === 'expert' ? suggestExpert : suggestPeer;
  const modelLabel = llmInfo.ask_provider || llmInfo.provider || '加载中…';

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 260px', gap: 20 }}>
      <div className="chrono-card" style={{ display: 'flex', flexDirection: 'column', height: 600 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, gap: 8, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <Radio.Group size="small" value={persona} onChange={(e) => onPersonaChange(e.target.value)}>
              <Radio.Button value="expert">专家模式</Radio.Button>
              <Radio.Button value="peer">同窗模式</Radio.Button>
            </Radio.Group>
            {persona === 'peer' && (
              <Select
                size="small"
                value={peerCharacter}
                style={{ minWidth: 140 }}
                onChange={onPeerChange}
                options={peerCandidates.map((n) => ({ label: n, value: n }))}
              />
            )}
            <Tooltip title="清空当前对话">
              <Button size="small" type="text" icon={<ReloadOutlined />} onClick={() => resetGreeting(persona, peerCharacter)} />
            </Tooltip>
          </div>
          <Tag color="gold">{modelLabel}</Tag>
        </div>
        <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: 8, background: 'var(--bg-warm-soft)', borderRadius: 6 }}>
          {history.map((m, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start', marginBottom: 10 }}>
              <div style={{
                maxWidth: '78%', padding: '10px 14px', borderRadius: 10, fontSize: 13, lineHeight: 1.7,
                background: m.role === 'user' ? 'var(--accent-gold)' : '#fff',
                color: m.role === 'user' ? '#fff' : 'var(--text-dark)',
                border: m.role === 'user' ? 'none' : '1px solid var(--border-soft)',
                whiteSpace: 'pre-wrap',
              }}>
                {m.content || (loading && i === history.length - 1 ? <Spin size="small" /> : '')}
              </div>
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          <Input.TextArea
            rows={2}
            value={input}
            placeholder={loading ? '正在回答…' : `向${persona === 'peer' ? peerCharacter : '历史教师'}提问，按 Ctrl+Enter 发送`}
            disabled={loading}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={(e) => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); send(); } }}
          />
          <Button type="primary" icon={<SendOutlined />} loading={loading} onClick={send}>发送</Button>
        </div>
      </div>

      <div className="chrono-card">
        <div className="chrono-title" style={{ fontSize: 14, marginBottom: 12 }}>
          {persona === 'expert' ? '建议追问' : `请教 ${peerCharacter}`}
        </div>
        {suggests.map((q) => (
          <div key={q} className="chrono-chip" style={{ display: 'block', marginBottom: 8, cursor: 'pointer', borderRadius: 6 }}
               onClick={() => setInput(q)}>{q}</div>
        ))}
        {persona === 'peer' && (
          <div style={{ marginTop: 16, fontSize: 11, color: 'var(--text-mute)', lineHeight: 1.6 }}>
            提示：同窗模式下 {peerCharacter} 只知晓其所处时代之前的事；问及后世他将以「未之闻也」相答。
          </div>
        )}
      </div>
    </div>
  );
}
