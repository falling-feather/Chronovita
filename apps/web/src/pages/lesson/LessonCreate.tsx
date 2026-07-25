import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { Alert, Button, Input, Spin, Tag, Tooltip, message } from 'antd';
import {
  ApartmentOutlined,
  CheckCircleFilled,
  CloudSyncOutlined,
  ExclamationCircleFilled,
  FileDoneOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import type {
  CanvasDocument,
  CanvasGeneratedEdge,
  CanvasGeneratedNode,
  GameDossier,
  GameDossierKnowledgeNode,
  Lesson,
} from '../../utils/api';
import { api } from '../../utils/api';
import {
  assertDossierIdentity,
  assertScenarioIdentity,
  assertSessionIdentity,
  buildGameBinding,
  readStoredStartedGameReference,
  type GameBinding,
} from './gameSessionReference';

interface CanvasNodeData {
  label: string;
  ai_source_label?: string;
  dossier_kind?: GameDossierKnowledgeNode['kind'];
  dossier_summary?: string;
  source_ref_ids?: string[];
  dossier_id?: string;
  session_id?: string;
  dossier_checksum?: string;
}

interface CanvasEdgeData {
  dossier_explanation?: string;
  source_ref_ids?: string[];
  dossier_id?: string;
  session_id?: string;
  dossier_checksum?: string;
}

type CanvasNode = Node<CanvasNodeData>;
type CanvasEdge = Edge<CanvasEdgeData>;
type CanvasPhase = 'loading' | 'ready' | 'error' | 'conflict';
type AutoSaveStatus = 'idle' | 'saving' | 'saved' | 'error';
type DossierState =
  | { phase: 'idle' }
  | { phase: 'loading' }
  | { phase: 'none'; message: string; canResume: boolean }
  | { phase: 'error'; message: string }
  | { phase: 'ready'; dossier: GameDossier };

interface CanvasGraph {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
}

const DOSSIER_KIND_STYLES: Record<
  GameDossierKnowledgeNode['kind'],
  { background: string; border: string }
> = {
  person: { background: '#F4F0FF', border: '#7565A8' },
  event: { background: '#FFF7E8', border: '#B87528' },
  place: { background: '#EDF6F2', border: '#3F7968' },
  concept: { background: '#EEF3FA', border: '#52759B' },
  cause: { background: '#FDF0F0', border: '#A34B4B' },
  consequence: { background: '#F3F5E9', border: '#6E7E3B' },
};

function formatHm(date: Date): string {
  const hh = String(date.getHours()).padStart(2, '0');
  const mm = String(date.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
}

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message.replace(/^\d{3}\s+/, '')
    : '请求失败，请稍后重试。';
}

function seedToNodes(seed: { id: string; label: string }[]): CanvasNode[] {
  return seed.map((item, index) => ({
    id: item.id,
    position: {
      x: 80 + (index % 3) * 220,
      y: 80 + Math.floor(index / 3) * 140,
    },
    data: { label: item.label },
    style: {
      background: '#FFFFFF',
      border: '1px solid var(--accent-gold)',
      borderRadius: 6,
      padding: 8,
      fontSize: 13,
      color: 'var(--text-dark)',
    },
  }));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isCanvasNode(value: unknown): value is CanvasNode {
  if (!isRecord(value) || typeof value.id !== 'string' || !value.id) return false;
  if (!isRecord(value.position)) return false;
  if (
    typeof value.position.x !== 'number'
    || !Number.isFinite(value.position.x)
    || typeof value.position.y !== 'number'
    || !Number.isFinite(value.position.y)
  ) {
    return false;
  }
  return isRecord(value.data) && typeof value.data.label === 'string';
}

function isCanvasEdge(value: unknown): value is CanvasEdge {
  return Boolean(
    isRecord(value)
    && typeof value.id === 'string'
    && value.id
    && typeof value.source === 'string'
    && value.source
    && typeof value.target === 'string'
    && value.target,
  );
}

function parseCanvasDocument(document: CanvasDocument): {
  found: boolean;
  revision: number;
  graph: CanvasGraph;
} {
  if (
    !isRecord(document)
    || document.schema_version !== 'canvas/v1'
    || typeof document.found !== 'boolean'
    || !Number.isInteger(document.revision)
    || document.revision < 0
    || !Array.isArray(document.nodes)
    || !Array.isArray(document.edges)
    || document.nodes.some((node) => !isCanvasNode(node))
    || document.edges.some((edge) => !isCanvasEdge(edge))
  ) {
    throw new Error('服务器返回的画板存档格式不正确。');
  }
  if (
    (!document.found && document.revision !== 0)
    || (document.found && document.revision < 1)
  ) {
    throw new Error('服务器返回的画板版本不正确。');
  }

  const nodes = document.nodes as CanvasNode[];
  const edges = document.edges as CanvasEdge[];
  const nodeIds = new Set<string>();
  for (const node of nodes) {
    if (nodeIds.has(node.id)) throw new Error('画板存档包含重复节点。');
    nodeIds.add(node.id);
  }
  const edgeIds = new Set<string>();
  for (const edge of edges) {
    if (edgeIds.has(edge.id)) throw new Error('画板存档包含重复关系。');
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) {
      throw new Error('画板存档包含无法连接的关系。');
    }
    edgeIds.add(edge.id);
  }
  return { found: document.found, revision: document.revision, graph: { nodes, edges } };
}

function isGeneratedNode(value: CanvasGeneratedNode): boolean {
  return Boolean(value && typeof value.id === 'string' && typeof value.label === 'string');
}

function isGeneratedEdge(value: CanvasGeneratedEdge): boolean {
  return Boolean(
    value
    && typeof value.from === 'string'
    && typeof value.to === 'string',
  );
}

function canvasNodeLabel(node: CanvasNode): string {
  return typeof node.data?.label === 'string' ? node.data.label.trim() : '';
}

function createLocalNodeId(): string {
  const suffix = typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `student:${suffix}`;
}

function dossierNodeId(dossier: GameDossier, nodeId: string): string {
  return `dossier:${dossier.course_checksum}:node:${nodeId}`;
}

function dossierEdgeId(dossier: GameDossier, edgeId: string): string {
  return `dossier:${dossier.course_checksum}:edge:${edgeId}`;
}

function mergeDossierGraph(
  dossier: GameDossier,
  currentNodes: CanvasNode[],
  currentEdges: CanvasEdge[],
): CanvasGraph & { addedNodes: number; addedEdges: number } {
  const knownNodeIds = new Set(currentNodes.map((node) => node.id));
  const knownEdgeIds = new Set(currentEdges.map((edge) => edge.id));
  const baseY = currentNodes.length > 0
    ? Math.max(...currentNodes.map((node) => node.position.y)) + 160
    : 80;

  const importedNodes: CanvasNode[] = [];
  for (const [index, item] of dossier.knowledge_nodes.entries()) {
    const id = dossierNodeId(dossier, item.node_id);
    if (knownNodeIds.has(id)) continue;
    const palette = DOSSIER_KIND_STYLES[item.kind];
    importedNodes.push({
      id,
      position: {
        x: 80 + (index % 3) * 240,
        y: baseY + Math.floor(index / 3) * 150,
      },
      data: {
        label: item.label,
        dossier_kind: item.kind,
        dossier_summary: item.summary,
        source_ref_ids: item.source_ref_ids,
        dossier_id: dossier.dossier_id,
        session_id: dossier.session_id,
        dossier_checksum: dossier.checksum || undefined,
      },
      style: {
        background: palette.background,
        border: `1px solid ${palette.border}`,
        borderRadius: 6,
        padding: 10,
        color: 'var(--text-dark)',
        fontSize: 13,
      },
    });
    knownNodeIds.add(id);
  }

  const importedEdges: CanvasEdge[] = [];
  for (const item of dossier.knowledge_edges) {
    const id = dossierEdgeId(dossier, item.edge_id);
    if (knownEdgeIds.has(id)) continue;
    const source = dossierNodeId(dossier, item.source_node_id);
    const target = dossierNodeId(dossier, item.target_node_id);
    if (!knownNodeIds.has(source) || !knownNodeIds.has(target)) continue;
    importedEdges.push({
      id,
      source,
      target,
      label: item.relation,
      data: {
        dossier_explanation: item.explanation,
        source_ref_ids: item.source_ref_ids,
        dossier_id: dossier.dossier_id,
        session_id: dossier.session_id,
        dossier_checksum: dossier.checksum || undefined,
      },
      animated: false,
      style: { stroke: '#7B6F61' },
      labelStyle: { fontSize: 11, fill: 'var(--text-mute)' },
    });
    knownEdgeIds.add(id);
  }

  return {
    nodes: [...currentNodes, ...importedNodes],
    edges: [...currentEdges, ...importedEdges],
    addedNodes: importedNodes.length,
    addedEdges: importedEdges.length,
  };
}

function isDossierImported(
  dossier: GameDossier,
  nodes: CanvasNode[],
  edges: CanvasEdge[],
): boolean {
  if (dossier.knowledge_nodes.length === 0) return false;
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edgeIds = new Set(edges.map((edge) => edge.id));
  return dossier.knowledge_nodes.every(
    (node) => nodeIds.has(dossierNodeId(dossier, node.node_id)),
  ) && dossier.knowledge_edges.every(
    (edge) => edgeIds.has(dossierEdgeId(dossier, edge.edge_id)),
  );
}

export default function LessonCreate({
  lesson,
  active,
  onOpenPractice,
}: {
  lesson: Lesson;
  active: boolean;
  onOpenPractice?: () => void;
}) {
  const [nodes, setNodes, applyNodeChanges] = useNodesState<CanvasNodeData>([]);
  const [edges, setEdges, applyEdgeChanges] = useEdgesState<CanvasEdgeData>([]);
  const [newLabel, setNewLabel] = useState('');
  const [generating, setGenerating] = useState(false);
  const [canvasPhase, setCanvasPhase] = useState<CanvasPhase>('loading');
  const [canvasError, setCanvasError] = useState('');
  const [autoStatus, setAutoStatus] = useState<AutoSaveStatus>('idle');
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [dirtyToken, setDirtyToken] = useState(0);
  const [dossierState, setDossierState] = useState<DossierState>({ phase: 'idle' });
  const [flowReady, setFlowReady] = useState(false);

  const nodesRef = useRef<CanvasNode[]>([]);
  const edgesRef = useRef<CanvasEdge[]>([]);
  const canvasStageRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<number | null>(null);
  const canvasLoadGenerationRef = useRef(0);
  const dossierLoadGenerationRef = useRef(0);
  const lessonIdRef = useRef(lesson.id);
  const canvasRevisionRef = useRef(0);
  const editVersionRef = useRef(0);
  const saveQueueRef = useRef<Promise<void>>(Promise.resolve());
  const errorNotifiedRef = useRef(false);

  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);

  useEffect(() => {
    edgesRef.current = edges;
  }, [edges]);

  useEffect(() => {
    setFlowReady(false);
    if (!active || canvasPhase === 'loading' || canvasPhase === 'error') return;

    const stage = canvasStageRef.current;
    if (!stage) return;

    const updateReadiness = () => {
      const rect = stage.getBoundingClientRect();
      setFlowReady(rect.width > 0 && rect.height > 0);
    };
    updateReadiness();

    const observer = new ResizeObserver(updateReadiness);
    observer.observe(stage);
    return () => observer.disconnect();
  }, [active, canvasPhase]);

  const loadCanvas = useCallback(async () => {
    const pendingSaves = saveQueueRef.current;
    const generation = canvasLoadGenerationRef.current + 1;
    canvasLoadGenerationRef.current = generation;
    lessonIdRef.current = lesson.id;
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    saveQueueRef.current = Promise.resolve();
    canvasRevisionRef.current = 0;
    editVersionRef.current = 0;
    errorNotifiedRef.current = false;
    setGenerating(false);
    setNewLabel('');
    setCanvasPhase('loading');
    setCanvasError('');
    setAutoStatus('idle');
    setSavedAt(null);
    setDirtyToken(0);
    nodesRef.current = [];
    edgesRef.current = [];
    setNodes([]);
    setEdges([]);

    try {
      await pendingSaves;
      if (
        canvasLoadGenerationRef.current !== generation
        || lessonIdRef.current !== lesson.id
      ) {
        return;
      }
      const response = await api.canvasGet(lesson.id);
      const parsed = parseCanvasDocument(response);
      if (
        canvasLoadGenerationRef.current !== generation
        || lessonIdRef.current !== lesson.id
      ) {
        return;
      }
      const graph = parsed.found
        ? parsed.graph
        : { nodes: seedToNodes(lesson.seed_canvas), edges: [] };
      canvasRevisionRef.current = parsed.revision;
      nodesRef.current = graph.nodes;
      edgesRef.current = graph.edges;
      setNodes(graph.nodes);
      setEdges(graph.edges);
      setCanvasPhase('ready');
    } catch (error) {
      if (
        canvasLoadGenerationRef.current !== generation
        || lessonIdRef.current !== lesson.id
      ) {
        return;
      }
      setCanvasError(errorMessage(error));
      setCanvasPhase('error');
    }
  }, [lesson.id, lesson.seed_canvas, setEdges, setNodes]);

  useEffect(() => {
    void loadCanvas();
    return () => {
      canvasLoadGenerationRef.current += 1;
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [loadCanvas]);

  const performSave = useCallback(async (
    currentNodes: CanvasNode[],
    currentEdges: CanvasEdge[],
    editVersion: number,
  ): Promise<boolean> => {
    const lessonId = lesson.id;
    const loadGeneration = canvasLoadGenerationRef.current;
    if (lessonIdRef.current !== lessonId) return false;
    setAutoStatus('saving');

    let savedRevision: number | null = null;
    const queued = saveQueueRef.current.then(async () => {
      if (
        lessonIdRef.current !== lessonId
        || canvasLoadGenerationRef.current !== loadGeneration
      ) {
        return;
      }
      const expectedRevision = canvasRevisionRef.current;
      const response = await api.canvasSave(lessonId, {
        expected_revision: expectedRevision,
        nodes: currentNodes,
        edges: currentEdges,
      });
      const parsed = parseCanvasDocument(response);
      if (
        lessonIdRef.current !== lessonId
        || canvasLoadGenerationRef.current !== loadGeneration
      ) {
        return;
      }
      if (!parsed.found || parsed.revision !== expectedRevision + 1) {
        throw new Error('服务器没有确认新的画板版本。');
      }
      canvasRevisionRef.current = parsed.revision;
      savedRevision = parsed.revision;
    });
    saveQueueRef.current = queued.then(() => undefined, () => undefined);

    try {
      await queued;
      if (
        savedRevision !== null
        && lessonIdRef.current === lessonId
        && canvasLoadGenerationRef.current === loadGeneration
        && editVersionRef.current === editVersion
      ) {
        setSavedAt(new Date());
        setAutoStatus('saved');
        errorNotifiedRef.current = false;
      }
      return savedRevision !== null;
    } catch (error) {
      if (
        lessonIdRef.current !== lessonId
        || canvasLoadGenerationRef.current !== loadGeneration
        || editVersionRef.current !== editVersion
      ) {
        return false;
      }
      const detail = errorMessage(error);
      setAutoStatus('error');
      if (/^409\b/.test(error instanceof Error ? error.message : '')) {
        setCanvasError(detail);
        setCanvasPhase('conflict');
      } else if (!errorNotifiedRef.current) {
        errorNotifiedRef.current = true;
        message.error(`画板保存失败：${detail}`);
      }
      return false;
    }
  }, [lesson.id]);

  useEffect(() => {
    if (canvasPhase !== 'ready' || dirtyToken === 0) return;
    editVersionRef.current += 1;
    const editVersion = editVersionRef.current;
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null;
      void performSave(nodesRef.current, edgesRef.current, editVersion);
    }, 800);
    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [canvasPhase, dirtyToken, performSave]);

  const primaryScenario = useMemo(
    () => lesson.scenario_refs?.find(
      (scenario) => scenario.primary && scenario.scenario_id === lesson.primary_scenario_id,
    ) || null,
    [lesson.primary_scenario_id, lesson.scenario_refs],
  );
  const binding = useMemo<GameBinding | null>(
    () => primaryScenario ? buildGameBinding(lesson, primaryScenario) : null,
    [lesson, primaryScenario],
  );

  const loadDossier = useCallback(async () => {
    const generation = dossierLoadGenerationRef.current + 1;
    dossierLoadGenerationRef.current = generation;
    setDossierState({ phase: 'loading' });

    if (!primaryScenario) {
      setDossierState({
        phase: 'none',
        message: '本课时尚未发布可生成卷宗的历史抉择关卡。',
        canResume: false,
      });
      return;
    }
    if (!binding) {
      setDossierState({
        phase: 'error',
        message: '当前课时的发布身份不完整，无法安全读取卷宗。',
      });
      return;
    }
    const stored = readStoredStartedGameReference(binding);
    if (!stored) {
      setDossierState({
        phase: 'none',
        message: '完成本课的历史抉择后，史官卷宗会出现在这里。',
        canResume: true,
      });
      return;
    }

    try {
      const started = await api.gameStart({
        scenario_id: binding.scenario.scenario_id,
        client_request_id: stored.client_request_id,
        release_pin: binding.pin,
      });
      assertScenarioIdentity(started.scenario, binding);
      assertSessionIdentity(started.session, binding);
      if (started.session.session_id !== stored.session_id) {
        throw new Error('服务器恢复的学习记录与当前浏览器会话不一致。');
      }
      if (started.session.status === 'active') {
        if (dossierLoadGenerationRef.current === generation) {
          setDossierState({
            phase: 'none',
            message: '这次历史抉择尚未完成，继续推演后即可整理卷宗。',
            canResume: true,
          });
        }
        return;
      }
      if (started.session.status !== 'completed') {
        if (dossierLoadGenerationRef.current === generation) {
          setDossierState({
            phase: 'none',
            message: '这次推演没有形成可封存的最终卷宗。',
            canResume: true,
          });
        }
        return;
      }
      if (
        !started.session.ended_at
        || !started.session.ending_id
        || !started.session.dossier_id
      ) {
        throw new Error('完成态学习记录缺少最终卷宗身份。');
      }

      const dossier = await api.gameDossier(started.session.session_id);
      assertDossierIdentity(dossier, started.session, binding);
      if (dossierLoadGenerationRef.current !== generation) return;
      setDossierState({ phase: 'ready', dossier });
    } catch (error) {
      if (dossierLoadGenerationRef.current !== generation) return;
      setDossierState({ phase: 'error', message: errorMessage(error) });
    }
  }, [binding, primaryScenario]);

  useEffect(() => {
    if (!active) {
      dossierLoadGenerationRef.current += 1;
      return;
    }
    void loadDossier();
    return () => {
      dossierLoadGenerationRef.current += 1;
    };
  }, [active, loadDossier]);

  const markCanvasDirty = useCallback(() => {
    setDirtyToken((current) => current + 1);
  }, []);

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    applyNodeChanges(changes);
    if (changes.some((change) => change.type !== 'select' && change.type !== 'dimensions')) {
      markCanvasDirty();
    }
  }, [applyNodeChanges, markCanvasDirty]);

  const onEdgesChange = useCallback((changes: EdgeChange[]) => {
    applyEdgeChanges(changes);
    if (changes.some((change) => change.type !== 'select')) {
      markCanvasDirty();
    }
  }, [applyEdgeChanges, markCanvasDirty]);

  const onConnect = useCallback((connection: Connection) => {
    setEdges((current) => addEdge({
      ...connection,
      animated: true,
      style: { stroke: '#D4A95C' },
    }, current));
    markCanvasDirty();
  }, [markCanvasDirty, setEdges]);

  const addNode = () => {
    const label = newLabel.trim();
    if (!label || canvasPhase !== 'ready') return;
    setNodes((current) => [...current, {
      id: createLocalNodeId(),
      position: {
        x: 180 + Math.random() * 240,
        y: 180 + Math.random() * 240,
      },
      data: { label },
      style: {
        background: '#FFFFFF',
        border: '1px solid var(--accent-gold)',
        borderRadius: 6,
        padding: 8,
        fontSize: 13,
      },
    }]);
    setNewLabel('');
    markCanvasDirty();
  };

  const aiGenerate = async () => {
    if (canvasPhase !== 'ready' || generating) return;
    const generation = canvasLoadGenerationRef.current;
    const lessonId = lesson.id;
    setGenerating(true);
    try {
      const sourceNodes = nodesRef.current;
      const response = await api.canvasGenerate({
        lesson_id: lesson.id,
        lesson_title: lesson.title,
        abstract: lesson.abstract || '',
        keywords: lesson.keywords.map((keyword) => keyword.word),
        seed: sourceNodes.map(canvasNodeLabel).filter(Boolean),
      });
      if (
        generation !== canvasLoadGenerationRef.current
        || lessonId !== lessonIdRef.current
        || canvasPhase !== 'ready'
      ) {
        return;
      }

      const latestNodes = nodesRef.current;
      const latestEdges = edgesRef.current;
      const labelToNodeId = new Map<string, string>();
      latestNodes.forEach((node) => {
        const label = typeof node.data.ai_source_label === 'string'
          ? node.data.ai_source_label.trim() || canvasNodeLabel(node)
          : canvasNodeLabel(node);
        if (label && !labelToNodeId.has(label)) labelToNodeId.set(label, node.id);
      });
      const sourceIdMap = new Map<string, string>();
      const generatedAt = Date.now();
      const freshNodes: CanvasNode[] = [];
      response.nodes.filter(isGeneratedNode).forEach((item, index) => {
        const label = item.label.trim();
        if (!label) return;
        const existingId = labelToNodeId.get(label);
        if (existingId) {
          sourceIdMap.set(item.id, existingId);
          return;
        }
        const id = `ai:${generatedAt}:${index}`;
        sourceIdMap.set(item.id, id);
        labelToNodeId.set(label, id);
        freshNodes.push({
          id,
          position: {
            x: 100 + (index % 4) * 210,
            y: 320 + Math.floor(index / 4) * 140,
          },
          data: {
            label: item.category ? `${label}（${item.category}）` : label,
            ai_source_label: label,
          },
          style: {
            background: '#FFFBEC',
            border: '1px dashed var(--accent-gold)',
            borderRadius: 6,
            padding: 8,
            fontSize: 13,
          },
        });
      });

      const knownEdgeIds = new Set(latestEdges.map((edge) => edge.id));
      const freshEdges: CanvasEdge[] = [];
      response.edges.filter(isGeneratedEdge).forEach((item, index) => {
        const source = sourceIdMap.get(item.from);
        const target = sourceIdMap.get(item.to);
        if (!source || !target || source === target) return;
        const id = `ai:${generatedAt}:edge:${index}`;
        if (knownEdgeIds.has(id)) return;
        knownEdgeIds.add(id);
        freshEdges.push({
          id,
          source,
          target,
          label: item.label || undefined,
          animated: true,
          style: { stroke: '#D4A95C', strokeDasharray: '4 3' },
          labelStyle: { fontSize: 11, fill: 'var(--text-mute)' },
        });
      });

      const nextNodes = [...latestNodes, ...freshNodes];
      const nextEdges = [...latestEdges, ...freshEdges];
      nodesRef.current = nextNodes;
      edgesRef.current = nextEdges;
      setNodes(nextNodes);
      setEdges(nextEdges);
      markCanvasDirty();
      message.success(`已扩充 ${freshNodes.length} 个节点和 ${freshEdges.length} 条关系`);
    } catch (error) {
      message.error(`生成失败：${errorMessage(error)}`);
    } finally {
      if (
        generation === canvasLoadGenerationRef.current
        && lessonId === lessonIdRef.current
      ) {
        setGenerating(false);
      }
    }
  };

  const saveNow = async () => {
    if (canvasPhase !== 'ready') return;
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    await performSave(
      nodesRef.current,
      edgesRef.current,
      editVersionRef.current,
    );
  };

  const importDossier = () => {
    if (canvasPhase !== 'ready' || dossierState.phase !== 'ready') return;
    const merged = mergeDossierGraph(
      dossierState.dossier,
      nodesRef.current,
      edgesRef.current,
    );
    if (merged.addedNodes === 0 && merged.addedEdges === 0) {
      message.info('这份卷宗已经在画板中。');
      return;
    }
    nodesRef.current = merged.nodes;
    edgesRef.current = merged.edges;
    setNodes(merged.nodes);
    setEdges(merged.edges);
    markCanvasDirty();
    message.success(`已导入 ${merged.addedNodes} 个节点和 ${merged.addedEdges} 条关系`);
  };

  const dossier = dossierState.phase === 'ready' ? dossierState.dossier : null;
  const dossierImported = dossier
    ? isDossierImported(dossier, nodes, edges)
    : false;

  const renderSaveStatus = () => {
    if (canvasPhase === 'loading') {
      return <span className="chrono-canvas-save-status">加载中...</span>;
    }
    if (canvasPhase === 'conflict') {
      return (
        <Button
          size="small"
          type="link"
          danger
          icon={<ReloadOutlined />}
          onClick={() => void loadCanvas()}
        >
          重新载入
        </Button>
      );
    }
    if (autoStatus === 'saving') {
      return (
        <span className="chrono-canvas-save-status">
          <CloudSyncOutlined spin /> 保存中...
        </span>
      );
    }
    if (autoStatus === 'error') {
      return (
        <Button
          size="small"
          type="link"
          danger
          icon={<ExclamationCircleFilled />}
          onClick={() => void saveNow()}
        >
          保存失败，重试
        </Button>
      );
    }
    if (autoStatus === 'saved' && savedAt) {
      return (
        <span className="chrono-canvas-save-status">
          <CheckCircleFilled /> 已保存 {formatHm(savedAt)}
        </span>
      );
    }
    return <span className="chrono-canvas-save-status">画板已就绪</span>;
  };

  return (
    <div className="chrono-create-layout">
      <DossierPanel
        state={dossierState}
        canvasPhase={canvasPhase}
        imported={dossierImported}
        onImport={importDossier}
        onRetry={() => void loadDossier()}
        onOpenPractice={onOpenPractice}
      />

      {canvasPhase === 'error' ? (
        <Alert
          type="error"
          showIcon
          message="知识画板未能安全载入"
          description={canvasError}
          action={(
            <Button icon={<ReloadOutlined />} onClick={() => void loadCanvas()}>
              重试
            </Button>
          )}
        />
      ) : (
        <section className="chrono-canvas-tool" aria-label="知识画板">
          {canvasPhase === 'conflict' ? (
            <Alert
              banner
              type="warning"
              showIcon
              message="检测到其他页面保存的新版本，本页改动尚未写入。"
              description={canvasError}
              action={(
                <Button size="small" icon={<ReloadOutlined />} onClick={() => void loadCanvas()}>
                  载入最新版本
                </Button>
              )}
            />
          ) : null}
          <div className="chrono-canvas-toolbar">
            <div className="chrono-canvas-add">
              <Input
                aria-label="新节点名称"
                value={newLabel}
                placeholder="新节点名称"
                disabled={canvasPhase !== 'ready'}
                onChange={(event) => setNewLabel(event.target.value)}
                onPressEnter={addNode}
              />
              <Tooltip title="添加知识节点">
                <Button
                  icon={<PlusOutlined />}
                  disabled={canvasPhase !== 'ready' || !newLabel.trim()}
                  onClick={addNode}
                >
                  添加
                </Button>
              </Tooltip>
            </div>
            <Button
              icon={<ThunderboltOutlined />}
              loading={generating}
              disabled={canvasPhase !== 'ready'}
              onClick={() => void aiGenerate()}
            >
              AI 扩充
            </Button>
            <div className="chrono-canvas-toolbar-spacer" />
            {renderSaveStatus()}
          </div>
          <div ref={canvasStageRef} className="chrono-canvas-stage">
            {canvasPhase === 'loading' || !flowReady ? (
              <div className="chrono-create-loading">
                <Spin />
              </div>
            ) : (
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodesDraggable={canvasPhase === 'ready'}
                nodesConnectable={canvasPhase === 'ready'}
                elementsSelectable={canvasPhase === 'ready'}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                fitView
              >
                <Background gap={20} color="#E5E7EB" />
                <Controls />
                <MiniMap pannable />
              </ReactFlow>
            )}
          </div>
        </section>
      )}
    </div>
  );
}

function DossierPanel({
  state,
  canvasPhase,
  imported,
  onImport,
  onRetry,
  onOpenPractice,
}: {
  state: DossierState;
  canvasPhase: CanvasPhase;
  imported: boolean;
  onImport: () => void;
  onRetry: () => void;
  onOpenPractice?: () => void;
}) {
  if (state.phase === 'idle' || state.phase === 'loading') {
    return (
      <div className="chrono-dossier-loading">
        <Spin size="small" />
        <span>正在核对本课卷宗...</span>
      </div>
    );
  }
  if (state.phase === 'error') {
    return (
      <Alert
        type="warning"
        showIcon
        message="史官卷宗暂时无法读取"
        description={state.message}
        action={<Button icon={<ReloadOutlined />} onClick={onRetry}>重试</Button>}
      />
    );
  }
  if (state.phase === 'none') {
    return (
      <Alert
        type="info"
        showIcon
        message="史官卷宗"
        description={state.message}
        action={state.canResume && onOpenPractice ? (
          <Button icon={<SafetyCertificateOutlined />} onClick={onOpenPractice}>
            进入推演
          </Button>
        ) : undefined}
      />
    );
  }

  const { dossier } = state;
  const hasKnowledge = dossier.knowledge_nodes.length > 0;
  return (
    <section className="chrono-dossier-band" aria-label="史官卷宗">
      <header className="chrono-dossier-header">
        <div>
          <Tag color="gold" icon={<FileDoneOutlined />}>史官卷宗</Tag>
          <Tag color="green">已封卷</Tag>
          <h2>{dossier.title}</h2>
          <p>{dossier.strategy_summary || '本次推演已形成可复核的历史选择记录。'}</p>
        </div>
        <Button
          type="primary"
          icon={<ApartmentOutlined />}
          disabled={!hasKnowledge || imported || canvasPhase !== 'ready'}
          onClick={onImport}
        >
          {imported ? '已导入画板' : '导入知识节点'}
        </Button>
      </header>

      <div className="chrono-dossier-grid">
        <div className="chrono-dossier-section">
          <h3>关键选择</h3>
          {dossier.key_choices.length > 0 ? (
            <ol className="chrono-dossier-choices">
              {dossier.key_choices.map((choice) => (
                <li key={choice.turn_id}>
                  <span>第 {choice.turn_no} 回合</span>
                  <strong>{choice.choice}</strong>
                  {choice.consequence ? <p>{choice.consequence}</p> : null}
                </li>
              ))}
            </ol>
          ) : <p className="chrono-dossier-muted">本次卷宗没有关键选择记录。</p>}
        </div>

        <div className="chrono-dossier-section">
          <h3>历史解释</h3>
          <p>{dossier.historical_explanation || '教师尚未配置本结局的历史解释。'}</p>
          {dossier.major_costs.length > 0 ? (
            <div className="chrono-dossier-costs">
              <span>主要代价</span>
              {dossier.major_costs.map((cost) => <Tag key={cost}>{cost}</Tag>)}
            </div>
          ) : null}
        </div>

        <div className="chrono-dossier-section">
          <h3>继续追问</h3>
          {dossier.follow_up_questions.length > 0 ? (
            <ul className="chrono-dossier-questions">
              {dossier.follow_up_questions.map((question) => (
                <li key={question}>{question}</li>
              ))}
            </ul>
          ) : <p className="chrono-dossier-muted">本次卷宗没有追加追问。</p>}
          <div className="chrono-dossier-knowledge-count">
            <ApartmentOutlined />
            {hasKnowledge
              ? `${dossier.knowledge_nodes.length} 个知识节点，${dossier.knowledge_edges.length} 条关系`
              : '本次卷宗没有可导入的知识节点'}
          </div>
        </div>
      </div>
    </section>
  );
}
