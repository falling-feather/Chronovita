import { useEffect, useRef, useState } from 'react';
import { Button, Input, Radio, Tag, Spin } from 'antd';
import { SendOutlined } from '@ant-design/icons';
import type { Lesson } from '../../utils/api';
import { api, streamAsk } from '../../utils/api';

interface Msg { role: 'user' | 'assistant'; content: string }

export default function LessonAsk({ lesson }: { lesson: Lesson }) {
  const [persona, setPersona] = useState<'expert' | 'peer'>('expert');
  const [history, setHistory] = useState<Msg[]>([
    { role: 'assistant', content: `你好，我是${persona === 'expert' ? '历史教师' : '同窗'}。围绕「${lesson.title}」你想问什么？` },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [provider, setProvider] = useState<string>('');
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => { api.llmInfo().then((r) => setProvider(r.provider)).catch(() => {}); }, []);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [history, loading]);

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
          history: history.slice(-6),
        },
        (chunk) => {
          setHistory((cur) => {
            const copy = cur.slice();
            const last = copy[copy.length - 1];
            if (last && last.role === 'assistant') last.content += chunk;
            return copy;
          });
        },
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 240px', gap: 20 }}>
      <div className="chrono-card" style={{ display: 'flex', flexDirection: 'column', height: 600 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <Radio.Group size="small" value={persona} onChange={(e) => setPersona(e.target.value)}>
            <Radio.Button value="expert">专家模式</Radio.Button>
            <Radio.Button value="peer">同窗模式</Radio.Button>
          </Radio.Group>
          <Tag>{provider || '加载中…'}</Tag>
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
            placeholder={loading ? '正在回答…' : '输入你的问题，按 Ctrl+Enter 发送'}
            disabled={loading}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={(e) => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); send(); } }}
          />
          <Button type="primary" icon={<SendOutlined />} loading={loading} onClick={send}>发送</Button>
        </div>
      </div>

      <div className="chrono-card">
        <div className="chrono-title" style={{ fontSize: 14, marginBottom: 12 }}>建议追问</div>
        {[
          `${lesson.title} 反映了什么历史趋势？`,
          '这一时期生产力发生了哪些变化？',
          '能否对比同时期其他诸侯国？',
          '这件事对后世产生了哪些影响？',
        ].map((q) => (
          <div key={q} className="chrono-chip" style={{ display: 'block', marginBottom: 8, cursor: 'pointer', borderRadius: 6 }}
               onClick={() => setInput(q)}>{q}</div>
        ))}
      </div>
    </div>
  );
}
