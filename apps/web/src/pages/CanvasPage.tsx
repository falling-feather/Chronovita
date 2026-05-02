import { useCallback, useEffect, useMemo, useState } from 'react';
import { takeAgentToCanvas } from '../bridge';
import {
  App,
  Button,
  Card,
  Col,
  Drawer,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Tag,
  Typography,
} from 'antd';
import ReactFlow, {
  Background,
  Connection,
  Controls,
  Edge,
  Node,
  NodeMouseHandler,
  ReactFlowProvider,
} from 'reactflow';
import 'reactflow/dist/style.css';

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

type CanvasKind = 'event' | 'figure' | 'policy' | 'place' | 'concept';

interface CanvasNode {
  node_id: string;
  kind: CanvasKind;
  label: string;
  detail: string;
  period: string;
  x: number;
  y: number;
}

interface CanvasEdge {
  edge_id: string;
  source_id: string;
  target_id: string;
  label: string;
}

interface CanvasBoard {
  board_id: string;
  title: string;
  summary: string;
  nodes: CanvasNode[];
  edges: CanvasEdge[];
}

interface UpsertNodeForm {
  kind: CanvasKind;
  label: string;
  detail?: string;
  period?: string;
}

const KIND_OPTIONS: { value: CanvasKind; label: string; color: string }[] = [
  { value: 'event', label: '事件', color: '#9F2E25' },
  { value: 'figure', label: '人物', color: '#7A5C2E' },
  { value: 'policy', label: '政策', color: '#3F5F4D' },
  { value: 'place', label: '地理', color: '#1F6F8B' },
  { value: 'concept', label: '概念', color: '#4B3F72' },
];

const KIND_MAP: Record<CanvasKind, { label: string; color: string }> = Object.fromEntries(
  KIND_OPTIONS.map((k) => [k.value, { label: k.label, color: k.color }]),
) as Record<CanvasKind, { label: string; color: string }>;

export default function CanvasPage() {
  const { message } = App.useApp();
  const [boards, setBoards] = useState<CanvasBoard[]>([]);
  const [active, setActive] = useState<CanvasBoard | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm<{ title: string; summary: string; seed: boolean }>();
  const [nodeDrawer, setNodeDrawer] = useState<{ open: boolean; node?: CanvasNode }>({ open: false });
  const [nodeForm] = Form.useForm<UpsertNodeForm>();

  const fetchBoards = useCallback(async () => {
    const r = await fetch('/api/v1/canvas/boards');
    if (r.ok) setBoards(await r.json());
  }, []);

  const refreshActive = useCallback(async (boardId: string) => {
    const r = await fetch(`/api/v1/canvas/boards/${boardId}`);
    if (r.ok) setActive(await r.json());
  }, []);

  useEffect(() => {
    fetchBoards();
  }, [fetchBoards]);

  useEffect(() => {
    const p = takeAgentToCanvas();
    if (!p) return;
    (async () => {
      const r = await fetch('/api/v1/canvas/boards', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: `论辩沉淀 · ${p.topic}`,
          summary: '由问模块双派论述与典籍引证一键沉淀',
          seed: false,
        }),
      });
      if (!r.ok) {
        message.error('沉淀谱系创建失败');
        return;
      }
      const board: CanvasBoard = await r.json();
      const bid = board.board_id;
      const addNode = async (kind: string, label: string, detail: string) => {
        const rr = await fetch(`/api/v1/canvas/boards/${bid}/nodes`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ kind, label, detail, period: '', x: 0, y: 0 }),
        });
        return rr.ok ? ((await rr.json()) as CanvasNode) : null;
      };
      const topicNode = await addNode('concept', p.topic.slice(0, 40), p.topic);
      const thinkerNode = await addNode('concept', '思辨派', p.thinker_text.slice(0, 400));
      const historianNode = await addNode('figure', '史实派', p.historian_text.slice(0, 400));
      const citeNodes = [];
      for (const c of p.citations.slice(0, 6)) {
        const n = await addNode('policy', c.title.slice(0, 40), c.excerpt);
        if (n) citeNodes.push(n);
      }
      const link = async (src: string, tgt: string, label: string) => {
        await fetch(`/api/v1/canvas/boards/${bid}/edges`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ source_id: src, target_id: tgt, label }),
        });
      };
      if (topicNode && thinkerNode) await link(topicNode.node_id, thinkerNode.node_id, '辩');
      if (topicNode && historianNode) await link(topicNode.node_id, historianNode.node_id, '证');
      for (const cn of citeNodes) {
        if (historianNode) await link(historianNode.node_id, cn.node_id, '引');
      }
      await fetch(`/api/v1/canvas/boards/${bid}/layout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ algorithm: 'layered' }),
      });
      await refreshActive(bid);
      await fetchBoards();
      message.success(`已沉淀「${p.topic}」论辩谱系`);
    })();
  }, [fetchBoards, refreshActive, message]);

  const createBoard = useCallback(async () => {
    const v = await createForm.validateFields();
    const r = await fetch('/api/v1/canvas/boards', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(v),
    });
    if (r.ok) {
      const b: CanvasBoard = await r.json();
      setActive(b);
      await fetchBoards();
      setCreateOpen(false);
      createForm.resetFields();
      message.success(`已创建：${b.title}`);
    } else {
      message.error('创建失败');
    }
  }, [createForm, fetchBoards, message]);

  const removeBoard = useCallback(
    async (id: string) => {
      const r = await fetch(`/api/v1/canvas/boards/${id}`, { method: 'DELETE' });
      if (r.ok) {
        if (active?.board_id === id) setActive(null);
        await fetchBoards();
        message.success('已删除');
      }
    },
    [active, fetchBoards, message],
  );

  const submitNode = useCallback(
    async (values: UpsertNodeForm) => {
      if (!active) return;
      const payload = {
        node_id: nodeDrawer.node?.node_id,
        kind: values.kind,
        label: values.label,
        detail: values.detail || '',
        period: values.period || '',
        x: nodeDrawer.node?.x ?? 0,
        y: nodeDrawer.node?.y ?? 0,
      };
      const r = await fetch(`/api/v1/canvas/boards/${active.board_id}/nodes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (r.ok) {
        await refreshActive(active.board_id);
        setNodeDrawer({ open: false });
        nodeForm.resetFields();
        message.success('已保存节点');
      } else {
        message.error('保存失败');
      }
    },
    [active, nodeDrawer, nodeForm, refreshActive, message],
  );

  const removeNode = useCallback(
    async (nodeId: string) => {
      if (!active) return;
      const r = await fetch(`/api/v1/canvas/boards/${active.board_id}/nodes/${nodeId}`, { method: 'DELETE' });
      if (r.ok) await refreshActive(active.board_id);
    },
    [active, refreshActive],
  );

  const onConnect = useCallback(
    async (conn: Connection) => {
      if (!active || !conn.source || !conn.target) return;
      const r = await fetch(`/api/v1/canvas/boards/${active.board_id}/edges`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_id: conn.source, target_id: conn.target, label: '' }),
      });
      if (r.ok) {
        await refreshActive(active.board_id);
        message.success('已连接');
      } else {
        message.error('连接失败');
      }
    },
    [active, refreshActive, message],
  );

  const removeEdge = useCallback(
    async (edgeId: string) => {
      if (!active) return;
      const r = await fetch(`/api/v1/canvas/boards/${active.board_id}/edges/${edgeId}`, { method: 'DELETE' });
      if (r.ok) await refreshActive(active.board_id);
    },
    [active, refreshActive],
  );

  const runLayout = useCallback(
    async (algorithm: 'layered' | 'radial') => {
      if (!active) return;
      const r = await fetch(`/api/v1/canvas/boards/${active.board_id}/layout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ algorithm }),
      });
      if (r.ok) {
        setActive(await r.json());
        message.success(`已应用布局：${algorithm}`);
      }
    },
    [active, message],
  );

  const exportBoard = useCallback(
    async (format: 'json' | 'markdown' | 'mermaid') => {
      if (!active) return;
      const r = await fetch(`/api/v1/canvas/boards/${active.board_id}/export?format=${format}`);
      if (!r.ok) {
        message.error('导出失败');
        return;
      }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const suffix = format === 'json' ? 'json' : format === 'markdown' ? 'md' : 'mmd';
      a.download = `${active.board_id}.${suffix}`;
      a.click();
      URL.revokeObjectURL(url);
      message.success(`已下载 ${format}`);
    },
    [active, message],
  );

  const flowNodes: Node[] = useMemo(() => {
    if (!active) return [];
    return active.nodes.map((n) => ({
      id: n.node_id,
      position: { x: n.x, y: n.y },
      data: { label: n.label },
      style: {
        background: KIND_MAP[n.kind].color,
        color: '#FBF6EC',
        border: '1px solid #1F1B17',
        borderRadius: 8,
        padding: '6px 12px',
        fontSize: 13,
        minWidth: 100,
        textAlign: 'center' as const,
      },
    }));
  }, [active]);

  const flowEdges: Edge[] = useMemo(() => {
    if (!active) return [];
    return active.edges.map((e) => ({
      id: e.edge_id,
      source: e.source_id,
      target: e.target_id,
      label: e.label,
      labelStyle: { fill: '#1F1B17', fontSize: 11 },
      labelBgStyle: { fill: '#F3EBDD', opacity: 0.85 },
      style: { stroke: '#7A5C2E', strokeWidth: 1.5 },
    }));
  }, [active]);

  const onNodeClick: NodeMouseHandler = useCallback(
    (_, node) => {
      const cn = active?.nodes.find((x) => x.node_id === node.id);
      if (cn) {
        nodeForm.setFieldsValue({ kind: cn.kind, label: cn.label, detail: cn.detail, period: cn.period });
        setNodeDrawer({ open: true, node: cn });
      }
    },
    [active, nodeForm],
  );

  return (
    <div>
      <Title level={3} className="chrono-title">创 · 知识谱系</Title>
      <Paragraph>
        以可拖拽节点 + 自由连线的方式沉淀历史关系网；支持自动布局与 JSON / Markdown / Mermaid 三件套导出，
        将沉浸学习沉淀为可复用的知识资产。
      </Paragraph>

      <Row gutter={16}>
        <Col span={6}>
          <Card
            title="谱系列表"
            size="small"
            extra={<Button type="primary" size="small" onClick={() => setCreateOpen(true)}>新建</Button>}
            style={{ minHeight: 540 }}
          >
            {boards.length === 0 ? (
              <Empty description="暂无谱系" />
            ) : (
              <List
                dataSource={boards}
                renderItem={(b) => (
                  <List.Item
                    actions={[
                      <Button
                        key="open"
                        type="link"
                        size="small"
                        onClick={() => refreshActive(b.board_id)}
                      >
                        打开
                      </Button>,
                      <Popconfirm key="del" title="确认删除？" onConfirm={() => removeBoard(b.board_id)}>
                        <Button type="link" size="small" danger>删除</Button>
                      </Popconfirm>,
                    ]}
                  >
                    <List.Item.Meta
                      title={
                        <Space>
                          <Text strong>{b.title}</Text>
                          {active?.board_id === b.board_id && <Tag color="#9F2E25">当前</Tag>}
                        </Space>
                      }
                      description={<Text type="secondary">{b.nodes.length} 节点 / {b.edges.length} 边</Text>}
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>

        <Col span={18}>
          {active ? (
            <Card
              title={<Text strong>{active.title}</Text>}
              extra={
                <Space wrap>
                  <Button size="small" onClick={() => { nodeForm.resetFields(); setNodeDrawer({ open: true }); }}>新增节点</Button>
                  <Button size="small" onClick={() => runLayout('layered')}>分层布局</Button>
                  <Button size="small" onClick={() => runLayout('radial')}>放射布局</Button>
                  <Button size="small" onClick={() => exportBoard('markdown')}>导出 MD</Button>
                  <Button size="small" onClick={() => exportBoard('json')}>导出 JSON</Button>
                  <Button size="small" onClick={() => exportBoard('mermaid')}>导出 Mermaid</Button>
                </Space>
              }
              style={{ background: '#FBF6EC' }}
            >
              {active.summary && <Paragraph type="secondary">{active.summary}</Paragraph>}
              <div style={{ height: 460, border: '1px solid #D9C9A8', borderRadius: 6, background: '#FFFCF5' }}>
                <ReactFlowProvider>
                  <ReactFlow
                    nodes={flowNodes}
                    edges={flowEdges}
                    onConnect={onConnect}
                    onNodeClick={onNodeClick}
                    onEdgeDoubleClick={(_, e) => removeEdge(e.id)}
                    onNodesDelete={(ns) => ns.forEach((n) => removeNode(n.id))}
                    fitView
                    proOptions={{ hideAttribution: true }}
                  >
                    <Background color="#D9C9A8" gap={16} />
                    <Controls />
                  </ReactFlow>
                </ReactFlowProvider>
              </div>
              <Paragraph type="secondary" style={{ marginTop: 8 }}>
                操作：拖动节点改位置 · 节点连接点拉到另一节点新增边 · 单击节点编辑 · 双击边删除 · 选中节点按 Delete 删除
              </Paragraph>
            </Card>
          ) : (
            <Card style={{ minHeight: 540 }}>
              <Empty description="请在左侧选择或新建一个谱系（建议勾选「内置示例」体验「大禹治水」种子谱系）" />
            </Card>
          )}
        </Col>
      </Row>

      <Modal
        title="新建知识谱系"
        open={createOpen}
        onOk={createBoard}
        onCancel={() => setCreateOpen(false)}
        okText="创建"
        cancelText="取消"
      >
        <Form form={createForm} layout="vertical" initialValues={{ title: '夏代奠基', summary: '', seed: true }}>
          <Form.Item label="标题" name="title" rules={[{ required: true, max: 60 }]}>
            <Input />
          </Form.Item>
          <Form.Item label="摘要" name="summary">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item label="初始节点" name="seed">
            <Select
              options={[
                { value: true, label: '使用「大禹治水」种子谱系（6 节点 6 边）' },
                { value: false, label: '空白谱系' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={nodeDrawer.node ? '编辑节点' : '新增节点'}
        open={nodeDrawer.open}
        onClose={() => setNodeDrawer({ open: false })}
        width={420}
        extra={
          nodeDrawer.node && (
            <Popconfirm title="删除该节点？" onConfirm={() => { removeNode(nodeDrawer.node!.node_id); setNodeDrawer({ open: false }); }}>
              <Button danger size="small">删除</Button>
            </Popconfirm>
          )
        }
      >
        <Form form={nodeForm} layout="vertical" onFinish={submitNode} initialValues={{ kind: 'event' }}>
          <Form.Item label="类型" name="kind" rules={[{ required: true }]}>
            <Select options={KIND_OPTIONS.map((k) => ({ value: k.value, label: k.label }))} />
          </Form.Item>
          <Form.Item label="标签" name="label" rules={[{ required: true, max: 40 }]}>
            <Input />
          </Form.Item>
          <Form.Item label="时期" name="period">
            <Input placeholder="如：夏·约公元前 2070" />
          </Form.Item>
          <Form.Item label="详情" name="detail">
            <TextArea rows={3} />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>保存</Button>
        </Form>
      </Drawer>
    </div>
  );
}
