import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Drawer,
  Empty,
  Input,
  List,
  Row,
  Space,
  Tag,
  Typography,
} from 'antd';

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

interface Citation {
  source_id: string;
  title: string;
  excerpt: string;
  relevance: number;
}

interface DialogueMessage {
  role: 'user' | 'thinker' | 'historian';
  content: string;
  citations: Citation[];
}

interface DialogueSession {
  session_id: string;
  topic: string;
  messages: DialogueMessage[];
}

interface StreamChunk {
  persona: 'thinker' | 'historian';
  delta: string;
  done: boolean;
  citations: Citation[];
}

const PERSONA_LABEL: Record<string, string> = {
  thinker: '思辨流派 · 子思',
  historian: '史实流派 · 仲尼',
  user: '你',
};

const PERSONA_COLOR: Record<string, string> = {
  thinker: '#7A5C2E',
  historian: '#3F5F4D',
  user: '#9F2E25',
};

export default function AgentPage() {
  const { message } = App.useApp();
  const [topic, setTopic] = useState('大禹治水的功过');
  const [session, setSession] = useState<DialogueSession | null>(null);
  const [question, setQuestion] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [thinkerBuf, setThinkerBuf] = useState('');
  const [historianBuf, setHistorianBuf] = useState('');
  const [pendingCitations, setPendingCitations] = useState<Citation[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [activeCitations, setActiveCitations] = useState<Citation[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  const startSession = useCallback(async () => {
    if (!topic.trim()) {
      message.error('请填写讨论主题');
      return;
    }
    const r = await fetch('/api/v1/agent/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic }),
    });
    if (!r.ok) {
      message.error('开启会话失败');
      return;
    }
    const sess: DialogueSession = await r.json();
    setSession(sess);
    setThinkerBuf('');
    setHistorianBuf('');
    setPendingCitations([]);
    message.success(`会话已开启：${sess.topic}`);
  }, [topic, message]);

  const ask = useCallback(async () => {
    if (!session) {
      message.warning('请先开启会话');
      return;
    }
    if (!question.trim()) return;
    const userQ = question.trim();
    setQuestion('');
    setStreaming(true);
    setThinkerBuf('');
    setHistorianBuf('');
    setPendingCitations([]);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const resp = await fetch(`/api/v1/agent/sessions/${session.session_id}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: userQ }),
        signal: ctrl.signal,
      });
      if (!resp.ok || !resp.body) {
        message.error('提问失败');
        setStreaming(false);
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buf = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parts = buf.split('\n\n');
        buf = parts.pop() ?? '';
        for (const part of parts) {
          for (const line of part.split('\n')) {
            if (!line.startsWith('data:')) continue;
            const payload = line.slice(5).trim();
            if (!payload || payload === '{}') continue;
            try {
              const ch: StreamChunk = JSON.parse(payload);
              if (ch.persona === 'thinker') {
                setThinkerBuf((s) => s + ch.delta);
              } else {
                setHistorianBuf((s) => s + ch.delta);
              }
              if (ch.done && ch.citations.length > 0) {
                setPendingCitations(ch.citations);
              }
            } catch {
              /* ignore parse errors */
            }
          }
        }
      }
      const sr = await fetch(`/api/v1/agent/sessions/${session.session_id}`);
      if (sr.ok) setSession(await sr.json());
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }, [session, question, message]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const renderMessage = (m: DialogueMessage, idx: number) => (
    <List.Item key={idx} style={{ alignItems: 'flex-start' }}>
      <List.Item.Meta
        title={
          <Space>
            <Tag color={PERSONA_COLOR[m.role]}>{PERSONA_LABEL[m.role]}</Tag>
            {m.citations.length > 0 && (
              <Button
                type="link"
                size="small"
                onClick={() => {
                  setActiveCitations(m.citations);
                  setDrawerOpen(true);
                }}
              >
                查看引证 ({m.citations.length})
              </Button>
            )}
          </Space>
        }
        description={<div style={{ whiteSpace: 'pre-wrap', color: '#1F1B17' }}>{m.content}</div>}
      />
    </List.Item>
  );

  return (
    <div>
      <Title level={3} className="chrono-title">问 · 双模智者</Title>
      <Paragraph>
        左栏「思辨流派」抛出反问与多元解读，右栏「史实流派」援引典籍佐证，
        两者并置以制衡 LLM 单一叙事，引证条目可侧拉抽屉复核。
      </Paragraph>

      <Space style={{ marginBottom: 12, width: '100%' }}>
        <Input
          style={{ width: 360 }}
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="讨论主题"
          maxLength={120}
        />
        <Button type="primary" onClick={startSession} disabled={streaming}>
          开启 / 重置会话
        </Button>
        {session && <Tag color="#3F5F4D">会话 {session.session_id}</Tag>}
      </Space>

      {!session && <Alert type="warning" message="请先点击「开启会话」" showIcon style={{ marginBottom: 12 }} />}

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card
            title={<Text strong style={{ color: '#7A5C2E' }}>思辨流派 · 子思</Text>}
            style={{ minHeight: 240, background: '#FBF6EC' }}
          >
            {thinkerBuf ? (
              <div style={{ whiteSpace: 'pre-wrap' }}>{thinkerBuf}{streaming && <span>▍</span>}</div>
            ) : (
              <Empty description="等待提问" />
            )}
          </Card>
        </Col>
        <Col span={12}>
          <Card
            title={
              <Space>
                <Text strong style={{ color: '#3F5F4D' }}>史实流派 · 仲尼</Text>
                {pendingCitations.length > 0 && (
                  <Button
                    type="link"
                    size="small"
                    onClick={() => {
                      setActiveCitations(pendingCitations);
                      setDrawerOpen(true);
                    }}
                  >
                    查看引证 ({pendingCitations.length})
                  </Button>
                )}
              </Space>
            }
            style={{ minHeight: 240, background: '#FBF6EC' }}
          >
            {historianBuf ? (
              <div style={{ whiteSpace: 'pre-wrap' }}>{historianBuf}{streaming && <span>▍</span>}</div>
            ) : (
              <Empty description="等待提问" />
            )}
          </Card>
        </Col>
      </Row>

      <Space.Compact style={{ width: '100%', marginBottom: 16 }}>
        <TextArea
          rows={2}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="向两位智者同时提问..."
          disabled={!session || streaming}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              ask();
            }
          }}
        />
        <Button type="primary" onClick={ask} loading={streaming} disabled={!session || !question.trim()}>
          提问
        </Button>
      </Space.Compact>

      <Card title="历史消息" size="small">
        {session && session.messages.length > 0 ? (
          <List dataSource={session.messages} renderItem={renderMessage} split />
        ) : (
          <Empty description="暂无消息" />
        )}
      </Card>

      <Drawer
        title="引证抽屉"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={460}
      >
        <List
          dataSource={activeCitations}
          renderItem={(c) => (
            <List.Item>
              <List.Item.Meta
                title={
                  <Space>
                    <Text strong>{c.title}</Text>
                    <Tag color="#7A5C2E">相关度 {c.relevance.toFixed(2)}</Tag>
                  </Space>
                }
                description={<Text>{c.excerpt}</Text>}
              />
            </List.Item>
          )}
        />
      </Drawer>
    </div>
  );
}
