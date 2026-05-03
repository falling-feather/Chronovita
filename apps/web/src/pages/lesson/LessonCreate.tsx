import { useCallback, useEffect, useState } from 'react';
import ReactFlow, {
  Background, Controls, MiniMap,
  addEdge, useEdgesState, useNodesState,
  type Connection, type Edge, type Node,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { Button, Input, Space, message } from 'antd';
import { PlusOutlined, SaveOutlined, ThunderboltOutlined } from '@ant-design/icons';
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
  const [generating, setGenerating] = useState(false);

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

  const aiGenerate = async () => {
    setGenerating(true);
    try {
      const r = await api.canvasGenerate({
        lesson_id: lesson.id,
        lesson_title: lesson.title,
        abstract: (lesson as any).abstract || (lesson as any).intro || '',
        keywords: (lesson as any).keywords || [],
        seed: nodes.map((n) => String((n.data as any)?.label || '')).filter(Boolean),
      });
      const existing = new Set(nodes.map((n) => String((n.data as any)?.label || '').trim()));
      const idMap: Record<string, string> = {};
      const fresh: Node[] = [];
      (r.nodes || []).forEach((nd: any, i: number) => {
        const label = String(nd.label || '').trim();
        if (!label || existing.has(label)) {
          // 复用已有同名节点 id
          const found = nodes.find((n) => String((n.data as any)?.label || '').trim() === label);
          if (found) idMap[nd.id] = found.id;
          return;
        }
        const newId = 'ai_' + Date.now() + '_' + i;
        idMap[nd.id] = newId;
        fresh.push({
          id: newId,
          position: { x: 120 + (i % 4) * 200 + Math.random() * 40, y: 320 + Math.floor(i / 4) * 130 + Math.random() * 40 },
          data: { label: label + (nd.category ? `（${nd.category}）` : '') },
          style: { background: '#FFFBEC', border: '1px dashed var(--accent-gold)', borderRadius: 8, padding: 8, fontSize: 13 },
        });
        existing.add(label);
      });
      setNodes((ns) => [...ns, ...fresh]);
      const existingEdges = new Set(edges.map((e) => `${e.source}->${e.target}`));
      const freshEdges: Edge[] = [];
      (r.edges || []).forEach((ed: any, i: number) => {
        const src = idMap[ed.from]; const dst = idMap[ed.to];
        if (!src || !dst || src === dst) return;
        const key = `${src}->${dst}`;
        if (existingEdges.has(key)) return;
        existingEdges.add(key);
        freshEdges.push({
          id: 'ae_' + Date.now() + '_' + i, source: src, target: dst,
          label: ed.label || undefined, animated: true,
          style: { stroke: '#D4A95C', strokeDasharray: '4 3' },
          labelStyle: { fontSize: 11, fill: 'var(--text-mute)' },
        });
      });
      setEdges((es) => [...es, ...freshEdges]);
      message.success(`AI 已扩充 ${fresh.length} 个节点 / ${freshEdges.length} 条关系`);
    } catch (e: any) {
      message.error('生成失败：' + e.message);
    } finally { setGenerating(false); }
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
        <Button icon={<ThunderboltOutlined />} loading={generating} onClick={aiGenerate}>AI 扩充图谱</Button>
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
