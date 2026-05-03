import { useCallback, useEffect, useState } from 'react';
import ReactFlow, {
  Background, Controls, MiniMap,
  addEdge, useEdgesState, useNodesState,
  type Connection, type Edge, type Node,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { Button, Input, Space, message } from 'antd';
import { PlusOutlined, SaveOutlined } from '@ant-design/icons';
import type { Lesson } from '../../utils/api';
import { api } from '../../utils/api';

function seedToNodes(seed: { id: string; label: string }[]): Node[] {
  return seed.map((s, i) => ({
    id: s.id,
    position: { x: 80 + (i % 3) * 220, y: 80 + Math.floor(i / 3) * 140 },
    data: { label: s.label },
    style: {
      background: '#fff', border: '1px solid var(--accent-gold)',
      borderRadius: 8, padding: 8, fontSize: 13, color: 'var(--text-dark)',
    },
  }));
}

export default function LessonCreate({ lesson }: { lesson: Lesson }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([] as Node[]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([] as Edge[]);
  const [newLabel, setNewLabel] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.canvasGet(lesson.id).then((r) => {
      if (r && r.nodes && r.nodes.length > 0) {
        setNodes(r.nodes as Node[]);
        setEdges((r.edges || []) as Edge[]);
      } else {
        setNodes(seedToNodes(lesson.seed_canvas));
        setEdges([]);
      }
    }).catch(() => {
      setNodes(seedToNodes(lesson.seed_canvas));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lesson.id]);

  const onConnect = useCallback((c: Connection) =>
    setEdges((eds) => addEdge({ ...c, animated: true, style: { stroke: '#D4A95C' } }, eds)), [setEdges]);

  const addNode = () => {
    const label = newLabel.trim();
    if (!label) return;
    const id = 'n' + Date.now();
    setNodes((ns) => [...ns, {
      id,
      position: { x: 200 + Math.random() * 200, y: 200 + Math.random() * 200 },
      data: { label },
      style: { background: '#fff', border: '1px solid var(--accent-gold)', borderRadius: 8, padding: 8, fontSize: 13 },
    }]);
    setNewLabel('');
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.canvasSave(lesson.id, { nodes, edges });
      message.success('画板已保存');
    } catch (e: any) {
      message.error('保存失败：' + e.message);
    } finally { setSaving(false); }
  };

  return (
    <div className="chrono-card" style={{ padding: 0, overflow: 'hidden' }}>
      <div style={{ padding: 14, borderBottom: '1px solid var(--border-soft)', display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <Space>
          <Input value={newLabel} placeholder="新节点标签…" onChange={(e) => setNewLabel(e.target.value)}
                 onPressEnter={addNode} style={{ width: 200 }} />
          <Button icon={<PlusOutlined />} onClick={addNode}>加节点</Button>
        </Space>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: 'var(--text-mute)' }}>拖动节点 · 从节点圆点连线 · 点击 Backspace 删除</span>
        <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={save}>保存到云端</Button>
      </div>
      <div style={{ height: 560, background: 'var(--bg-warm-soft)' }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          fitView
        >
          <Background gap={20} color="#E5E7EB" />
          <Controls />
          <MiniMap pannable />
        </ReactFlow>
      </div>
    </div>
  );
}
