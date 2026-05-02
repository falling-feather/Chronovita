import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  App,
  Button,
  Card,
  Checkbox,
  Col,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Popconfirm,
  Progress,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

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

interface ClassroomTask {
  task_id: string;
  title: string;
  scenario_id: string;
  teacher_notes: string;
  preset_state: Record<string, number>;
  must_visit_nodes: string[];
  accepted_terminals: string[];
  recommended_path: string[];
  created_at: string;
}

interface SubmissionItem {
  playthrough_id: string;
  student_name: string | null;
  is_terminal: boolean;
  terminal_node_id: string | null;
  terminal_accepted: boolean;
  must_visit_hit_count: number;
  must_visit_total: number;
  recommended_match_ratio: number;
  history: string[];
  created_at: string;
  updated_at: string;
  summary: string;
}

interface SubmissionsAggregate {
  task: ClassroomTask;
  submissions: SubmissionItem[];
  node_visit_counts: Record<string, number>;
  edge_traverse_counts: Record<string, number>;
  terminal_distribution: Record<string, number>;
  total_count: number;
  accepted_count: number;
}

function maxValue(v: StateVar): number {
  return (1 << v.bits) - 1;
}

export default function ClassroomPage() {
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<ClassroomTask[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [open, setOpen] = useState(false);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [form] = Form.useForm();
  const [replayTask, setReplayTask] = useState<ClassroomTask | null>(null);
  const [replay, setReplay] = useState<SubmissionsAggregate | null>(null);
  const [replayLoading, setReplayLoading] = useState(false);

  const openReplay = useCallback(
    async (t: ClassroomTask) => {
      setReplayTask(t);
      setReplayLoading(true);
      try {
        const r = await fetch(`/api/v1/classroom/tasks/${t.task_id}/submissions`);
        if (!r.ok) {
          message.error('拉取作业失败');
          setReplay(null);
          return;
        }
        setReplay(await r.json());
      } finally {
        setReplayLoading(false);
      }
    },
    [message],
  );

  const refresh = useCallback(async () => {
    const r = await fetch('/api/v1/classroom/tasks');
    if (r.ok) setTasks(await r.json());
  }, []);

  useEffect(() => {
    refresh();
    fetch('/api/v1/sandbox/scenarios')
      .then((r) => r.json())
      .then((d: Scenario[]) => setScenarios(d))
      .catch(() => message.error('剧本列表拉取失败'));
  }, [refresh, message]);

  const onScenarioChange = useCallback(
    async (scenarioId: string) => {
      const sc = scenarios.find((s) => s.scenario_id === scenarioId);
      if (!sc) return;
      setScenario(sc);
      const presetInit: Record<string, number> = {};
      sc.state_vars.forEach((v) => {
        presetInit[v.key] = v.initial;
      });
      form.setFieldsValue({
        preset_state: presetInit,
        must_visit_nodes: [],
        accepted_terminals: [],
        recommended_path: [],
      });
    },
    [scenarios, form],
  );

  const submit = useCallback(async () => {
    const values = await form.validateFields();
    const body = {
      title: values.title,
      scenario_id: values.scenario_id,
      teacher_notes: values.teacher_notes ?? '',
      preset_state: values.preset_state ?? {},
      must_visit_nodes: values.must_visit_nodes ?? [],
      accepted_terminals: values.accepted_terminals ?? [],
      recommended_path: values.recommended_path ?? [],
    };
    const r = await fetch('/api/v1/classroom/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      message.error(`创建失败：${err.detail ?? r.status}`);
      return;
    }
    const task: ClassroomTask = await r.json();
    setOpen(false);
    form.resetFields();
    setScenario(null);
    await refresh();
    modal.success({
      title: '任务创建成功',
      content: (
        <div>
          <Paragraph>请将以下任务 ID 分享给学生（学生在沙盘页打开同剧本即自动加载）：</Paragraph>
          <Paragraph copyable={{ text: task.task_id }}>
            <Text code>{task.task_id}</Text>
          </Paragraph>
          <Paragraph copyable={{ text: `${window.location.origin}/sandbox?task=${task.task_id}` }}>
            <Text code>{`${window.location.origin}/sandbox?task=${task.task_id}`}</Text>
          </Paragraph>
        </div>
      ),
    });
  }, [form, refresh, message, modal]);

  const remove = useCallback(
    async (taskId: string) => {
      const r = await fetch(`/api/v1/classroom/tasks/${taskId}`, { method: 'DELETE' });
      if (!r.ok) {
        message.error('删除失败');
        return;
      }
      message.success('已删除');
      await refresh();
    },
    [refresh, message],
  );

  const terminalChoices = useMemo(
    () => scenario?.nodes.filter((n) => n.is_terminal) ?? [],
    [scenario],
  );

  return (
    <div>
      <Title level={3} className="chrono-title">课 · 老师预设</Title>
      <Paragraph>
        老师可在此预调剧本初始状态、勾选课堂必经节点与合格终局、画出推荐路径，
        并生成任务 ID 分享给学生。学生在沙盘页带 <Text code>?task=任务ID</Text> 打开剧本即可按预设开局，
        终局后可一键提交「验收任务」由系统自动比对。
      </Paragraph>

      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" onClick={() => setOpen(true)}>
          新建课堂任务
        </Button>
        <Button onClick={refresh}>刷新</Button>
      </Space>

      {tasks.length === 0 ? (
        <Empty description="尚无课堂任务，新建一个吧" />
      ) : (
        <List
          grid={{ gutter: 16, column: 2 }}
          dataSource={tasks}
          renderItem={(t) => (
            <List.Item>
              <Card
                title={
                  <Space>
                    <Text strong>{t.title}</Text>
                    <Tag color="#7A5C2E">{t.scenario_id}</Tag>
                  </Space>
                }
                extra={
                  <Space>
                    <Button size="small" onClick={() => openReplay(t)}>
                      作业回放
                    </Button>
                    <Button size="small" onClick={() => navigate(`/sandbox?task=${t.task_id}`)}>
                      去推演
                    </Button>
                    <Popconfirm title="删除此任务？" onConfirm={() => remove(t.task_id)}>
                      <Button size="small" danger>
                        删除
                      </Button>
                    </Popconfirm>
                  </Space>
                }
              >
                <Paragraph type="secondary" style={{ marginBottom: 8 }}>
                  任务 ID：<Text code copyable>{t.task_id}</Text>
                </Paragraph>
                {t.teacher_notes && <Paragraph>{t.teacher_notes}</Paragraph>}
                <Paragraph style={{ marginBottom: 4 }}>
                  <Text strong>必经节点：</Text>
                  {t.must_visit_nodes.length === 0
                    ? '—'
                    : t.must_visit_nodes.map((n) => (
                        <Tag key={n} color="#3F5F4D">
                          {n}
                        </Tag>
                      ))}
                </Paragraph>
                <Paragraph style={{ marginBottom: 4 }}>
                  <Text strong>合格终局：</Text>
                  {t.accepted_terminals.length === 0
                    ? '不限'
                    : t.accepted_terminals.map((n) => (
                        <Tag key={n} color="#9F2E25">
                          {n}
                        </Tag>
                      ))}
                </Paragraph>
                <Paragraph style={{ marginBottom: 0 }}>
                  <Text strong>推荐路径长度：</Text>
                  {t.recommended_path.length}
                </Paragraph>
              </Card>
            </List.Item>
          )}
        />
      )}

      <Drawer
        title="新建课堂任务"
        width={620}
        open={open}
        onClose={() => {
          setOpen(false);
          form.resetFields();
          setScenario(null);
        }}
        extra={
          <Space>
            <Button
              onClick={() => {
                setOpen(false);
                form.resetFields();
                setScenario(null);
              }}
            >
              取消
            </Button>
            <Button type="primary" onClick={submit}>
              保存
            </Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="title"
            label="任务标题"
            rules={[{ required: true, message: '请填写任务标题' }]}
          >
            <Input placeholder="如：大禹治水 · 第一节课" />
          </Form.Item>
          <Form.Item
            name="scenario_id"
            label="剧本"
            rules={[{ required: true, message: '请选择剧本' }]}
          >
            <Select
              placeholder="选择沙盘剧本"
              options={scenarios.map((s) => ({
                value: s.scenario_id,
                label: `${s.title} · ${s.period}`,
              }))}
              onChange={onScenarioChange}
            />
          </Form.Item>
          <Form.Item name="teacher_notes" label="老师备注（学生可见）">
            <TextArea rows={3} placeholder="本节课希望学生关注的史脉重点……" />
          </Form.Item>

          {scenario && (
            <>
              <Card size="small" title="预调初始状态" style={{ marginBottom: 16 }}>
                <Row gutter={[12, 12]}>
                  {scenario.state_vars.map((v) => (
                    <Col span={12} key={v.key}>
                      <Form.Item
                        name={['preset_state', v.key]}
                        label={
                          <Space>
                            <Text strong>{v.label}</Text>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              0–{maxValue(v)}
                            </Text>
                          </Space>
                        }
                        tooltip={v.description}
                        style={{ marginBottom: 0 }}
                      >
                        <InputNumber min={0} max={maxValue(v)} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  ))}
                </Row>
              </Card>

              <Form.Item name="must_visit_nodes" label="必经节点（可多选）">
                <Checkbox.Group
                  options={scenario.nodes.map((n) => ({
                    label: `${n.title}${n.is_terminal ? ' ⛩' : ''}（${n.node_id}）`,
                    value: n.node_id,
                  }))}
                />
              </Form.Item>

              <Form.Item name="accepted_terminals" label="合格终局（不勾即不限）">
                <Checkbox.Group
                  options={terminalChoices.map((n) => ({
                    label: `${n.title}（${n.node_id}）`,
                    value: n.node_id,
                  }))}
                />
              </Form.Item>

              <Form.Item
                name="recommended_path"
                label="推荐路径（按顺序选择边 ID，匹配率会显示给学生）"
              >
                <Select
                  mode="multiple"
                  placeholder="按教学顺序勾选边"
                  options={scenario.edges.map((e) => ({
                    value: e.edge_id,
                    label: `${e.label} · ${e.from_node} → ${e.to_node}`,
                  }))}
                />
              </Form.Item>
            </>
          )}
        </Form>
      </Drawer>

      <Drawer
        title={replayTask ? `作业回放：${replayTask.title}` : '作业回放'}
        width={760}
        open={!!replayTask}
        onClose={() => {
          setReplayTask(null);
          setReplay(null);
        }}
        loading={replayLoading}
      >
        {replay ? (
          replay.total_count === 0 ? (
            <Empty description="尚无学生提交，分享任务链接给学生后再来查看吧" />
          ) : (
            <>
              <Row gutter={16} style={{ marginBottom: 16 }}>
                <Col span={8}>
                  <Statistic title="提交总数" value={replay.total_count} />
                </Col>
                <Col span={8}>
                  <Statistic
                    title="合格人次"
                    value={replay.accepted_count}
                    suffix={` / ${replay.total_count}`}
                    valueStyle={{ color: '#3F5F4D' }}
                  />
                </Col>
                <Col span={8}>
                  <Statistic
                    title="合格率"
                    value={
                      replay.total_count === 0
                        ? 0
                        : Math.round((replay.accepted_count / replay.total_count) * 100)
                    }
                    suffix="%"
                    valueStyle={{ color: '#7A5C2E' }}
                  />
                </Col>
              </Row>

              <Card size="small" title="终局分布" style={{ marginBottom: 12 }}>
                <Space wrap>
                  {Object.entries(replay.terminal_distribution).map(([nid, c]) => (
                    <Tag key={nid} color="#9F2E25">
                      {nid} × {c}
                    </Tag>
                  ))}
                </Space>
              </Card>

              <Card size="small" title="节点访问热力（前 10）" style={{ marginBottom: 12 }}>
                <Space direction="vertical" style={{ width: '100%' }}>
                  {Object.entries(replay.node_visit_counts)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 10)
                    .map(([nid, c]) => (
                      <Row key={nid} gutter={8} align="middle">
                        <Col span={8}>
                          <Text code>{nid}</Text>
                        </Col>
                        <Col span={16}>
                          <Progress
                            percent={Math.round((c / replay.total_count) * 100)}
                            size="small"
                            strokeColor="#7A5C2E"
                            format={() => `${c} 次`}
                          />
                        </Col>
                      </Row>
                    ))}
                </Space>
              </Card>

              <Card size="small" title="边遍历热力（前 10）" style={{ marginBottom: 12 }}>
                <Space direction="vertical" style={{ width: '100%' }}>
                  {Object.entries(replay.edge_traverse_counts)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 10)
                    .map(([eid, c]) => (
                      <Row key={eid} gutter={8} align="middle">
                        <Col span={8}>
                          <Text code>{eid}</Text>
                        </Col>
                        <Col span={16}>
                          <Progress
                            percent={Math.round((c / replay.total_count) * 100)}
                            size="small"
                            strokeColor="#3F5F4D"
                            format={() => `${c} 次`}
                          />
                        </Col>
                      </Row>
                    ))}
                </Space>
              </Card>

              <Table<SubmissionItem>
                rowKey="playthrough_id"
                size="small"
                pagination={{ pageSize: 8 }}
                dataSource={replay.submissions}
                columns={[
                  {
                    title: '学生',
                    dataIndex: 'student_name',
                    render: (n: string | null) => n || <Text type="secondary">匿名</Text>,
                  },
                  {
                    title: '终局',
                    render: (_, r) =>
                      r.is_terminal ? (
                        <Tag color={r.terminal_accepted ? '#3F5F4D' : '#9F2E25'}>
                          {r.terminal_node_id ?? '—'}
                        </Tag>
                      ) : (
                        <Tag>未抵达</Tag>
                      ),
                  },
                  {
                    title: '必经',
                    render: (_, r) => `${r.must_visit_hit_count} / ${r.must_visit_total}`,
                  },
                  {
                    title: '推荐路径',
                    dataIndex: 'recommended_match_ratio',
                    render: (v: number) => `${Math.round(v * 100)}%`,
                  },
                  {
                    title: '提交时间',
                    dataIndex: 'updated_at',
                    render: (t: string) => new Date(t).toLocaleString(),
                  },
                ]}
                expandable={{
                  expandedRowRender: (r) => (
                    <Space direction="vertical" style={{ width: '100%' }} size={4}>
                      <Text type="secondary">{r.summary}</Text>
                      <div>
                        <Text strong>路径：</Text>
                        {r.history.map((nid, i) => (
                          <span key={i}>
                            <Tag color="#7A5C2E">{nid}</Tag>
                            {i < r.history.length - 1 ? '→ ' : ''}
                          </span>
                        ))}
                      </div>
                    </Space>
                  ),
                }}
              />
            </>
          )
        ) : null}
      </Drawer>
    </div>
  );
}
