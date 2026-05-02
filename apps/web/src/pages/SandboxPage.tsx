import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Divider,
  Empty,
  List,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Steps,
  Tag,
  Typography,
} from 'antd';

const { Title, Paragraph, Text } = Typography;

interface StateVar {
  key: string;
  label: string;
  kind: 'bool' | 'scale';
  bits: number;
  initial: number;
  description: string;
}

interface DagNode {
  node_id: string;
  title: string;
  narrative: string;
  is_terminal: boolean;
}

interface Scenario {
  scenario_id: string;
  title: string;
  period: string;
  summary: string;
  state_vars: StateVar[];
  nodes: DagNode[];
  start_node: string;
}

interface BranchOption {
  edge_id: string;
  label: string;
  target_node_id: string;
  target_title: string;
  preview_narrative: string;
  state_after: Record<string, number>;
}

interface PlaythroughSnapshot {
  playthrough_id: string;
  scenario_id: string;
  current_node_id: string;
  current_node_title: string;
  current_narrative: string;
  state: Record<string, number>;
  state_bits: number;
  history: string[];
  is_terminal: boolean;
  created_at: string;
  updated_at: string;
}

const STAT_COLORS: Record<string, string> = {
  strategy: '#7A5C2E',
  morale: '#3F5F4D',
  flood: '#9F2E25',
  nine_zhou: '#1F1B17',
};

function maxValue(v: StateVar): number {
  return (1 << v.bits) - 1;
}

function describeValue(v: StateVar, value: number): string {
  if (v.kind === 'bool') return value ? '是' : '否';
  if (v.key === 'strategy') {
    return ['未定', '承父之堵', '改弦疏导', '堵疏并举'][value] ?? String(value);
  }
  return `${value} / ${maxValue(v)}`;
}

export default function SandboxPage() {
  const { message } = App.useApp();

  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [snapshot, setSnapshot] = useState<PlaythroughSnapshot | null>(null);
  const [branches, setBranches] = useState<BranchOption[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch('/api/v1/sandbox/scenarios')
      .then((r) => r.json())
      .then((data: Scenario[]) => {
        setScenarios(data);
        if (data.length > 0) {
          setSelectedId(data[0].scenario_id);
          setScenario(data[0]);
        }
      })
      .catch(() => message.error('剧本列表拉取失败'));
  }, [message]);

  const fetchBranches = useCallback(async (pid: string) => {
    const r = await fetch(`/api/v1/sandbox/playthroughs/${pid}/branches`);
    if (!r.ok) {
      setBranches([]);
      return;
    }
    setBranches(await r.json());
  }, []);

  const startPlaythrough = useCallback(async () => {
    if (!selectedId) return;
    setLoading(true);
    try {
      const r = await fetch(`/api/v1/sandbox/playthroughs?scenario_id=${selectedId}`, {
        method: 'POST',
      });
      if (!r.ok) {
        message.error('开始推演失败');
        return;
      }
      const snap: PlaythroughSnapshot = await r.json();
      setSnapshot(snap);
      await fetchBranches(snap.playthrough_id);
      message.success(`已开始推演：${snap.current_node_title}`);
    } finally {
      setLoading(false);
    }
  }, [selectedId, fetchBranches, message]);

  const advance = useCallback(
    async (edgeId: string) => {
      if (!snapshot) return;
      setLoading(true);
      try {
        const r = await fetch(
          `/api/v1/sandbox/playthroughs/${snapshot.playthrough_id}/advance`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ edge_id: edgeId }),
          },
        );
        if (!r.ok) {
          message.error('选择失败');
          return;
        }
        const snap: PlaythroughSnapshot = await r.json();
        setSnapshot(snap);
        if (snap.is_terminal) {
          setBranches([]);
          message.success(`抵达终局：${snap.current_node_title}`);
        } else {
          await fetchBranches(snap.playthrough_id);
        }
      } finally {
        setLoading(false);
      }
    },
    [snapshot, fetchBranches, message],
  );

  useEffect(() => {
    if (!selectedId) return;
    const sc = scenarios.find((s) => s.scenario_id === selectedId);
    if (sc) setScenario(sc);
    setSnapshot(null);
    setBranches([]);
  }, [selectedId, scenarios]);

  const historyTitles = useMemo(() => {
    if (!scenario || !snapshot) return [];
    const map = new Map(scenario.nodes.map((n) => [n.node_id, n.title]));
    return snapshot.history.map((nid) => map.get(nid) ?? nid);
  }, [scenario, snapshot]);

  return (
    <div>
      <Title level={3} className="chrono-title">练 · 沙盘推演</Title>
      <Paragraph>
        以有向无环图编排史脉节点，按位压缩状态变量（治水策略 / 民心 / 河患 / 九州划定），
        通过记忆化动态规划缓存「(节点, 状态位)」组合，支撑平行分支探索。
      </Paragraph>

      <Space style={{ marginBottom: 16 }}>
        <Select
          style={{ width: 260 }}
          value={selectedId ?? undefined}
          options={scenarios.map((s) => ({ label: `${s.title} · ${s.period}`, value: s.scenario_id }))}
          onChange={(v) => setSelectedId(v)}
          placeholder="选择剧本"
        />
        <Button type="primary" onClick={startPlaythrough} loading={loading} disabled={!selectedId}>
          开始新推演
        </Button>
      </Space>

      {scenario && (
        <Alert
          type="info"
          showIcon={false}
          style={{ marginBottom: 16, background: '#F3EBDD', border: '1px solid #D9C9A8' }}
          message={<Text strong>{scenario.title}</Text>}
          description={scenario.summary}
        />
      )}

      <Spin spinning={loading}>
        <Row gutter={16}>
          <Col span={8}>
            <Card title="状态变量">
              {snapshot && scenario ? (
                <Space direction="vertical" style={{ width: '100%' }} size="middle">
                  {scenario.state_vars.map((v) => (
                    <Statistic
                      key={v.key}
                      title={<Text type="secondary">{v.label}</Text>}
                      value={describeValue(v, snapshot.state[v.key] ?? v.initial)}
                      valueStyle={{ color: STAT_COLORS[v.key] ?? '#1F1B17', fontSize: 18 }}
                    />
                  ))}
                  <Divider style={{ margin: '8px 0' }} />
                  <Text type="secondary">状态位：{snapshot.state_bits}</Text>
                </Space>
              ) : (
                <Empty description="尚未开始推演" />
              )}
            </Card>
          </Col>

          <Col span={10}>
            <Card title={snapshot ? snapshot.current_node_title : '当前节点'}>
              {snapshot ? (
                <>
                  <Paragraph>{snapshot.current_narrative}</Paragraph>
                  <Divider orientation="left" plain>候选分支</Divider>
                  {snapshot.is_terminal ? (
                    <Tag color="#7A5C2E">推演已抵达终局</Tag>
                  ) : branches.length === 0 ? (
                    <Empty description="当前状态下无可行分支" />
                  ) : (
                    <List
                      dataSource={branches}
                      renderItem={(b) => (
                        <List.Item
                          actions={[
                            <Button key="go" type="primary" onClick={() => advance(b.edge_id)}>
                              选择
                            </Button>,
                          ]}
                        >
                          <List.Item.Meta
                            title={
                              <Space>
                                <Text strong>{b.label}</Text>
                                <Tag color="#3F5F4D">→ {b.target_title}</Tag>
                              </Space>
                            }
                            description={b.preview_narrative}
                          />
                        </List.Item>
                      )}
                    />
                  )}
                </>
              ) : (
                <Empty description="选择剧本并点击「开始新推演」" />
              )}
            </Card>
          </Col>

          <Col span={6}>
            <Card title="时间线">
              {snapshot ? (
                <Steps
                  direction="vertical"
                  size="small"
                  current={historyTitles.length - 1}
                  items={historyTitles.map((title) => ({ title }))}
                />
              ) : (
                <Empty description="—" />
              )}
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  );
}
