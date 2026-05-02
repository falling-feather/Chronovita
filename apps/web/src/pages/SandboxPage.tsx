import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { takeRecallToSandbox, setSandboxToAgent } from '../bridge';
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Divider,
  Empty,
  Input,
  List,
  Modal,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Steps,
  Tag,
  Typography,
} from 'antd';
import ReactFlow, {
  Background,
  Controls,
  Edge,
  Node,
  Position,
  ReactFlowProvider,
} from 'reactflow';
import 'reactflow/dist/style.css';

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

interface DagEdge {
  edge_id: string;
  from_node: string;
  to_node: string;
  label: string;
}

interface Scenario {
  scenario_id: string;
  title: string;
  period: string;
  summary: string;
  state_vars: StateVar[];
  nodes: DagNode[];
  edges: DagEdge[];
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

interface ClassroomTaskLite {
  task_id: string;
  title: string;
  scenario_id: string;
  teacher_notes: string;
  preset_state: Record<string, number>;
  must_visit_nodes: string[];
  accepted_terminals: string[];
  recommended_path: string[];
}

interface TaskCheckResult {
  task_id: string;
  playthrough_id: string;
  is_terminal: boolean;
  terminal_node_id: string | null;
  visited_nodes: string[];
  must_visit_hit: string[];
  must_visit_miss: string[];
  terminal_accepted: boolean;
  recommended_match_ratio: number;
  summary: string;
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
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const taskParam = searchParams.get('task');

  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [snapshot, setSnapshot] = useState<PlaythroughSnapshot | null>(null);
  const [branches, setBranches] = useState<BranchOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [incoming, setIncoming] = useState<{ title: string; keywords: string[] } | null>(null);
  const [task, setTask] = useState<ClassroomTaskLite | null>(null);
  const [studentName, setStudentName] = useState<string>(() => sessionStorage.getItem('chrono.student_name') ?? '');

  useEffect(() => {
    const p = takeRecallToSandbox();
    if (p) {
      setIncoming({ title: p.title, keywords: p.keywords });
      message.info(`已接收看模块素材：${p.title}`);
    }
  }, [message]);

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
    if (task && task.scenario_id === selectedId && !studentName.trim()) {
      message.warning('任务模式请先填写学生姓名');
      return;
    }
    setLoading(true);
    try {
      const params = new URLSearchParams({ scenario_id: selectedId });
      if (task && task.scenario_id === selectedId) {
        params.set('task_id', task.task_id);
        params.set('student_name', studentName.trim());
      }
      const r = await fetch(`/api/v1/sandbox/playthroughs?${params.toString()}`, {
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
  }, [selectedId, fetchBranches, message, task, studentName]);

  const checkTask = useCallback(async () => {
    if (!task || !snapshot) return;
    const r = await fetch(
      `/api/v1/classroom/tasks/${task.task_id}/check?playthrough_id=${snapshot.playthrough_id}`,
    );
    if (!r.ok) {
      message.error('验收失败');
      return;
    }
    const res: TaskCheckResult = await r.json();
    modal.info({
      title: `任务验收：${task.title}`,
      width: 560,
      content: (
        <div>
          <Paragraph>{res.summary}</Paragraph>
          <Paragraph style={{ marginBottom: 8 }}>
            <Text strong>终局合格：</Text>
            <Tag color={res.terminal_accepted ? '#3F5F4D' : '#9F2E25'}>
              {res.terminal_accepted ? '是' : '否'}
            </Tag>
          </Paragraph>
          <Paragraph style={{ marginBottom: 8 }}>
            <Text strong>推荐路径匹配率：</Text>
            <Progress
              percent={Math.round(res.recommended_match_ratio * 100)}
              size="small"
              strokeColor="#7A5C2E"
            />
          </Paragraph>
          <Paragraph style={{ marginBottom: 8 }}>
            <Text strong>必经命中：</Text>
            {res.must_visit_hit.length === 0
              ? '—'
              : res.must_visit_hit.map((n) => (
                  <Tag key={n} color="#3F5F4D">
                    {n}
                  </Tag>
                ))}
          </Paragraph>
          <Paragraph>
            <Text strong>必经缺漏：</Text>
            {res.must_visit_miss.length === 0
              ? '—'
              : res.must_visit_miss.map((n) => (
                  <Tag key={n} color="#9F2E25">
                    {n}
                  </Tag>
                ))}
          </Paragraph>
        </div>
      ),
    });
  }, [task, snapshot, message, modal]);

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

  const visitedSet = useMemo(
    () => new Set(snapshot?.history ?? []),
    [snapshot],
  );

  const branchEdgeIds = useMemo(
    () => new Set(branches.map((b) => b.edge_id)),
    [branches],
  );

  const branchTargetIds = useMemo(
    () => new Set(branches.map((b) => b.target_node_id)),
    [branches],
  );

  const flowNodes: Node[] = useMemo(() => {
    if (!scenario) return [];
    const nodeIds = scenario.nodes.map((n) => n.node_id);
    const indexOf: Record<string, number> = {};
    nodeIds.forEach((id, i) => { indexOf[id] = i; });
    const layer: Record<string, number> = {};
    layer[scenario.start_node] = 0;
    let progress = true;
    while (progress) {
      progress = false;
      for (const e of scenario.edges) {
        if (layer[e.from_node] === undefined) continue;
        const next = layer[e.from_node] + 1;
        if (layer[e.to_node] === undefined || layer[e.to_node] < next) {
          layer[e.to_node] = next;
          progress = true;
        }
      }
    }
    const byLayer: Record<number, string[]> = {};
    for (const id of nodeIds) {
      const l = layer[id] ?? 0;
      (byLayer[l] = byLayer[l] || []).push(id);
    }
    return scenario.nodes.map((n) => {
      const l = layer[n.node_id] ?? 0;
      const col = byLayer[l].indexOf(n.node_id);
      const rowCount = byLayer[l].length;
      const isCurrent = snapshot?.current_node_id === n.node_id;
      const isVisited = visitedSet.has(n.node_id);
      const isReachable = branchTargetIds.has(n.node_id);
      const bg = isCurrent
        ? '#9F2E25'
        : isVisited
          ? '#3F5F4D'
          : isReachable
            ? '#7A5C2E'
            : n.is_terminal
              ? '#1F1B17'
              : '#F3EBDD';
      const color = bg === '#F3EBDD' ? '#1F1B17' : '#F3EBDD';
      return {
        id: n.node_id,
        position: { x: l * 220, y: col * 90 - (rowCount - 1) * 45 },
        data: { label: n.title + (n.is_terminal ? ' ⛩' : '') },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        style: {
          background: bg,
          color,
          border: isCurrent ? '2px solid #1F1B17' : '1px solid #D9C9A8',
          borderRadius: 6,
          padding: 8,
          fontSize: 12,
          width: 140,
          textAlign: 'center' as const,
        },
      };
    });
  }, [scenario, snapshot, visitedSet, branchTargetIds]);

  const flowEdges: Edge[] = useMemo(() => {
    if (!scenario) return [];
    return scenario.edges.map((e) => {
      const isOption = branchEdgeIds.has(e.edge_id);
      return {
        id: e.edge_id,
        source: e.from_node,
        target: e.to_node,
        label: e.label,
        animated: isOption,
        style: {
          stroke: isOption ? '#9F2E25' : '#D9C9A8',
          strokeWidth: isOption ? 2 : 1,
        },
        labelStyle: { fill: '#1F1B17', fontSize: 10 },
        labelBgStyle: { fill: '#F3EBDD', opacity: 0.85 },
      };
    });
  }, [scenario, branchEdgeIds]);

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

      {task && (
        <Alert
          type="warning"
          style={{ marginBottom: 16 }}
          message={<Space><Text strong>课堂任务：{task.title}</Text><Tag color="#7A5C2E">{task.task_id}</Tag></Space>}
          description={
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              {task.teacher_notes && <Text>{task.teacher_notes}</Text>}
              <Space>
                <Text>学生姓名：</Text>
                <Input
                  size="small"
                  style={{ width: 160 }}
                  value={studentName}
                  placeholder="必填"
                  onChange={(e) => {
                    setStudentName(e.target.value);
                    sessionStorage.setItem('chrono.student_name', e.target.value);
                  }}
                />
              </Space>
              <Text type="secondary">
                必经节点：{task.must_visit_nodes.length === 0 ? '—' : task.must_visit_nodes.join(' / ')} ·
                合格终局：{task.accepted_terminals.length === 0 ? '不限' : task.accepted_terminals.join(' / ')}
              </Text>
              {snapshot && (
                <Text type="secondary">
                  进度：{task.must_visit_nodes.filter((n) => snapshot.history.includes(n)).length} /{' '}
                  {task.must_visit_nodes.length} 必经已抵达
                </Text>
              )}
              <Button
                size="small"
                onClick={() => {
                  setTask(null);
                  setSearchParams({});
                }}
              >
                退出任务模式
              </Button>
            </Space>
          }
        />
      )}

      {incoming && (
        <Alert
          type="success"
          style={{ marginBottom: 16 }}
          message={`来自看模块的素材：${incoming.title}`}
          description={`关键词：${incoming.keywords.join(' / ')}（已记录，将在送入问模块时一并携带）`}
          closable
          onClose={() => setIncoming(null)}
        />
      )}

      <Spin spinning={loading}>
        <Card title="DAG 史脉图（红=当前，赭=可选分支，墨=已访问，黑=终局）" style={{ marginBottom: 16 }}>
          <div style={{ height: 340, background: '#FBF6EC', border: '1px solid #D9C9A8', borderRadius: 4 }}>
            {scenario ? (
              <ReactFlowProvider>
                <ReactFlow
                  nodes={flowNodes}
                  edges={flowEdges}
                  fitView
                  nodesDraggable={false}
                  nodesConnectable={false}
                  elementsSelectable={false}
                  panOnDrag
                  zoomOnScroll
                  proOptions={{ hideAttribution: true }}
                >
                  <Background color="#D9C9A8" gap={16} />
                  <Controls showInteractive={false} />
                </ReactFlow>
              </ReactFlowProvider>
            ) : (
              <Empty description="选择剧本后渲染" style={{ padding: 80 }} />
            )}
          </div>
        </Card>

        <Row gutter={16}>
          <Col span={6}>
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

          <Col span={12}>
            <Card title={snapshot ? snapshot.current_node_title : '当前节点'}>
              {snapshot ? (
                <>
                  <Paragraph>{snapshot.current_narrative}</Paragraph>
                  <Divider orientation="left" plain>候选分支</Divider>
                  {snapshot.is_terminal ? (
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Tag color="#7A5C2E">推演已抵达终局</Tag>
                      {task && (
                        <Button onClick={checkTask}>验收任务</Button>
                      )}
                      <Button
                        type="primary"
                        onClick={() => {
                          if (!scenario || !snapshot) return;
                          const kws = incoming?.keywords?.length
                            ? incoming.keywords
                            : Array.from(new Set([scenario.title, snapshot.current_node_title]));
                          setSandboxToAgent({
                            scenario_title: scenario.title,
                            ending_summary: `${snapshot.current_node_title}：${snapshot.current_narrative}`,
                            keywords: kws,
                          });
                          message.success('已携带推演终局送往「问 · 双模智者」');
                          navigate('/agent');
                        }}
                      >
                        送入问模块 →
                      </Button>
                    </Space>
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
