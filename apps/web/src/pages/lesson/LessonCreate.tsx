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
import { Alert, Button, Drawer, Input, Popconfirm, Spin, Tag, Tooltip, message } from 'antd';
import {
  ApartmentOutlined,
  BookOutlined,
  CheckCircleFilled,
  CloudSyncOutlined,
  DeleteOutlined,
  EditOutlined,
  ExclamationCircleFilled,
  FileDoneOutlined,
  HistoryOutlined,
  ReadOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SaveOutlined,
  SendOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import type {
  CanvasDocument,
  CanvasGeneratedEdge,
  CanvasGeneratedNode,
  GameDossier,
  GameDossierKnowledgeNode,
  Lesson,
  LearningSubmissionDetail,
  LearningSubmissionListItem,
  LearningSubmissionRequest,
} from '../../utils/api';
import { api } from '../../utils/api';
import { useAuth } from '../../auth/AuthContext';
import {
  assertDossierIdentity,
  assertScenarioIdentity,
  assertSessionIdentity,
  buildGameBinding,
  readStoredStartedGameReference,
  type GameBinding,
} from './gameSessionReference';
import { projectDossierKnowledge } from '../../features/classroom/dossierProjection';
import {
  TEMPORARY_NOTEBOOK_EVENT,
  readTemporaryNotebook,
  temporaryNotebookStorageKey,
  type TemporaryNotebookIdentity,
} from '../../features/classroom/temporaryNotebook';
import {
  LEARNING_LEDGER_UPDATED,
  listLearningEvents,
  readLearningDeskDraft,
  writeLearningDeskDraft,
  type LearningDeskDraftRecord,
  type LearningDeskStickyNote,
  type LearningDeskStroke,
  type LearningEventRecord,
} from '../../features/classroom/learningLedger';
import {
  buildLearningDeskSeed,
  markdownToSafeHtml,
} from '../../features/classroom/learningDeskDocument';
import LearningDeskEditor from '../../features/classroom/LearningDeskEditor';
import LearningDeskDrawing from '../../features/classroom/LearningDeskDrawing';
import LearningSubmissionViewer from '../../features/classroom/LearningSubmissionViewer';
import {
  buildLearningSubmissionRequest,
  clearPendingSubmission,
  readPendingSubmission,
  writePendingSubmission,
} from '../../features/classroom/learningSubmission';
import './LessonCreate.css';

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
type DeskTool = 'write' | 'draw' | 'map' | 'trail';
type DeskSaveStatus = 'loading' | 'idle' | 'saving' | 'saved' | 'error';
type SubmissionStatus = 'idle' | 'preparing' | 'submitting' | 'error';
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
  const projection = projectDossierKnowledge(dossier);
  const knownNodeIds = new Set(currentNodes.map((node) => node.id));
  const knownEdgeIds = new Set(currentEdges.map((edge) => edge.id));
  const baseY = currentNodes.length > 0
    ? Math.max(...currentNodes.map((node) => node.position.y)) + 160
    : 80;

  const importedNodes: CanvasNode[] = [];
  for (const [index, item] of projection.nodes.entries()) {
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
  for (const item of projection.edges) {
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
  const projection = projectDossierKnowledge(dossier);
  if (projection.nodes.length === 0) return false;
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edgeIds = new Set(edges.map((edge) => edge.id));
  return projection.nodes.every(
    (node) => nodeIds.has(dossierNodeId(dossier, node.node_id)),
  ) && projection.edges.every(
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
  const auth = useAuth();
  const noteOwnerId = auth.principal?.user_id ?? (auth.mode === 'legacy-local' ? 'legacy-local' : 'anonymous');
  const temporaryNoteIdentity = useMemo<TemporaryNotebookIdentity>(() => ({
    ownerId: noteOwnerId,
    courseId: lesson.course_id,
    lessonId: lesson.id,
  }), [lesson.course_id, lesson.id, noteOwnerId]);
  const temporaryNoteKey = useMemo(
    () => temporaryNotebookStorageKey(temporaryNoteIdentity),
    [temporaryNoteIdentity],
  );
  const [temporaryNote, setTemporaryNote] = useState('');
  const [temporaryNoteUpdatedAt, setTemporaryNoteUpdatedAt] = useState('');
  const [temporaryNoteLoadedKey, setTemporaryNoteLoadedKey] = useState('');
  const [deskTool, setDeskTool] = useState<DeskTool>('write');
  const [deskDraft, setDeskDraft] = useState<LearningDeskDraftRecord | null>(null);
  const [deskTitle, setDeskTitle] = useState('');
  const [deskBodyHtml, setDeskBodyHtml] = useState('');
  const [deskBodyMarkdown, setDeskBodyMarkdown] = useState('');
  const [stickyNotes, setStickyNotes] = useState<LearningDeskStickyNote[]>([]);
  const [drawingStrokes, setDrawingStrokes] = useState<LearningDeskStroke[]>([]);
  const [learningEvents, setLearningEvents] = useState<LearningEventRecord[]>([]);
  const [deskSaveStatus, setDeskSaveStatus] = useState<DeskSaveStatus>('loading');
  const [deskSavedAt, setDeskSavedAt] = useState<Date | null>(null);
  const [deskDirtyToken, setDeskDirtyToken] = useState(0);
  const [deskHydrated, setDeskHydrated] = useState(false);
  const [submissionStatus, setSubmissionStatus] = useState<SubmissionStatus>('idle');
  const [submissionError, setSubmissionError] = useState('');
  const [submissionItems, setSubmissionItems] = useState<LearningSubmissionListItem[]>([]);
  const [submissionListLoading, setSubmissionListLoading] = useState(false);
  const [submissionHistoryOpen, setSubmissionHistoryOpen] = useState(false);
  const [submissionDetail, setSubmissionDetail] = useState<LearningSubmissionDetail | null>(null);
  const [submissionDetailLoading, setSubmissionDetailLoading] = useState(false);
  const [pendingSubmission, setPendingSubmission] = useState<LearningSubmissionRequest | null>(null);
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
  const deskSaveTimerRef = useRef<number | null>(null);
  const deskLoadGenerationRef = useRef(0);

  const loadSubmissions = useCallback(async () => {
    if (auth.mode !== 'accounts') {
      setSubmissionItems([]);
      return [];
    }
    setSubmissionListLoading(true);
    try {
      const response = await api.learningSubmissions({
        course_id: lesson.course_id,
        lesson_id: lesson.id,
        limit: 50,
      });
      setSubmissionItems(response.items);
      return response.items;
    } catch (error) {
      setSubmissionError(errorMessage(error));
      return [];
    } finally {
      setSubmissionListLoading(false);
    }
  }, [auth.mode, lesson.course_id, lesson.id]);

  useEffect(() => {
    if (auth.mode !== 'accounts') {
      setPendingSubmission(null);
      return;
    }
    try {
      setPendingSubmission(readPendingSubmission(window.localStorage, temporaryNoteIdentity));
    } catch {
      setPendingSubmission(null);
    }
    void loadSubmissions();
  }, [auth.mode, loadSubmissions, temporaryNoteIdentity]);

  useEffect(() => {
    const refresh = () => {
      const record = readTemporaryNotebook(window.localStorage, temporaryNoteIdentity);
      setTemporaryNote(record?.body ?? '');
      setTemporaryNoteUpdatedAt(record?.body.trim() ? record.updated_at : '');
      setTemporaryNoteLoadedKey(temporaryNoteKey);
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === temporaryNoteKey) refresh();
    };
    refresh();
    window.addEventListener(TEMPORARY_NOTEBOOK_EVENT, refresh);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener(TEMPORARY_NOTEBOOK_EVENT, refresh);
      window.removeEventListener('storage', onStorage);
    };
  }, [temporaryNoteIdentity, temporaryNoteKey]);

  useEffect(() => {
    if (temporaryNoteLoadedKey !== temporaryNoteKey) return undefined;
    const generation = deskLoadGenerationRef.current + 1;
    deskLoadGenerationRef.current = generation;
    if (deskSaveTimerRef.current !== null) {
      window.clearTimeout(deskSaveTimerRef.current);
      deskSaveTimerRef.current = null;
    }
    setDeskHydrated(false);
    setDeskSaveStatus('loading');
    setDeskDirtyToken(0);

    Promise.all([
      readLearningDeskDraft(temporaryNoteIdentity),
      listLearningEvents(temporaryNoteIdentity),
    ]).then(([record, events]) => {
      if (deskLoadGenerationRef.current !== generation) return;
      const seed = buildLearningDeskSeed({
        lessonTitle: lesson.title,
        temporaryNote,
        dossier: null,
      });
      setDeskDraft(record);
      setDeskTitle(record?.title ?? seed.title);
      setDeskBodyHtml(record?.body_html ?? seed.bodyHtml);
      setDeskBodyMarkdown(record?.body_markdown ?? seed.bodyMarkdown);
      setStickyNotes(record?.sticky_notes ?? seed.stickyNotes);
      setDrawingStrokes(record?.drawing_strokes ?? []);
      setLearningEvents(events);
      setDeskSavedAt(record ? new Date(record.updated_at) : null);
      setDeskSaveStatus(record ? 'saved' : 'idle');
      setDeskHydrated(true);
    }).catch(() => {
      if (deskLoadGenerationRef.current !== generation) return;
      setDeskSaveStatus('error');
      setDeskHydrated(true);
    });

    return () => {
      deskLoadGenerationRef.current += 1;
      if (deskSaveTimerRef.current !== null) {
        window.clearTimeout(deskSaveTimerRef.current);
        deskSaveTimerRef.current = null;
      }
    };
  }, [lesson.title, temporaryNoteIdentity, temporaryNoteKey, temporaryNoteLoadedKey]);

  useEffect(() => {
    const refresh = () => {
      void listLearningEvents(temporaryNoteIdentity).then(setLearningEvents);
    };
    window.addEventListener(LEARNING_LEDGER_UPDATED, refresh);
    return () => window.removeEventListener(LEARNING_LEDGER_UPDATED, refresh);
  }, [temporaryNoteIdentity]);

  useEffect(() => {
    if (!deskHydrated || deskDirtyToken === 0) return undefined;
    setDeskSaveStatus('saving');
    if (deskSaveTimerRef.current !== null) window.clearTimeout(deskSaveTimerRef.current);
    const generation = deskLoadGenerationRef.current;
    deskSaveTimerRef.current = window.setTimeout(() => {
      deskSaveTimerRef.current = null;
      void writeLearningDeskDraft(temporaryNoteIdentity, {
        title: deskTitle,
        body_html: deskBodyHtml,
        body_markdown: deskBodyMarkdown,
        sticky_notes: stickyNotes,
        drawing_strokes: drawingStrokes,
      }, deskDraft).then((saved) => {
        if (deskLoadGenerationRef.current !== generation) return;
        setDeskDraft(saved);
        setDeskSavedAt(new Date(saved.updated_at));
        setDeskSaveStatus('saved');
      }).catch(() => {
        if (deskLoadGenerationRef.current === generation) setDeskSaveStatus('error');
      });
    }, 520);
    return () => {
      if (deskSaveTimerRef.current !== null) {
        window.clearTimeout(deskSaveTimerRef.current);
        deskSaveTimerRef.current = null;
      }
    };
  }, [
    deskBodyHtml,
    deskBodyMarkdown,
    deskDirtyToken,
    deskHydrated,
    deskTitle,
    drawingStrokes,
    stickyNotes,
    temporaryNoteIdentity,
  ]);

  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);

  useEffect(() => {
    edgesRef.current = edges;
  }, [edges]);

  useEffect(() => {
    setFlowReady(false);
    if (!active || deskTool !== 'map' || canvasPhase === 'loading' || canvasPhase === 'error') return;

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
  }, [active, canvasPhase, deskTool]);

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

  const saveNow = async (): Promise<boolean> => {
    if (canvasPhase !== 'ready') return false;
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    return performSave(
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

  const markDeskDirty = useCallback(() => {
    setDeskDirtyToken((current) => current + 1);
    setDeskSaveStatus('saving');
  }, []);

  const changeDeskTitle = (value: string) => {
    setDeskTitle(value);
    markDeskDirty();
  };

  const changeDeskDocument = (next: { html: string; markdown: string }) => {
    setDeskBodyHtml(next.html);
    setDeskBodyMarkdown(next.markdown);
    markDeskDirty();
  };

  const changeDrawing = (next: LearningDeskStroke[]) => {
    setDrawingStrokes(next);
    markDeskDirty();
  };

  const addStickyNote = () => {
    const colors: LearningDeskStickyNote['color'][] = ['ochre', 'jade', 'cinnabar'];
    setStickyNotes((current) => [...current, {
      note_id: `note:${Date.now().toString(36)}:${Math.random().toString(36).slice(2)}`,
      body: '',
      color: colors[current.length % colors.length],
    }]);
    markDeskDirty();
  };

  const updateStickyNote = (noteId: string, body: string) => {
    setStickyNotes((current) => current.map(
      (note) => note.note_id === noteId ? { ...note, body } : note,
    ));
    markDeskDirty();
  };

  const removeStickyNote = (noteId: string) => {
    setStickyNotes((current) => current.filter((note) => note.note_id !== noteId));
    markDeskDirty();
  };

  const temporaryNoteImported = Boolean(temporaryNote.trim()) && stickyNotes.some(
    (note) => note.body.trim() === temporaryNote.trim(),
  );

  const importTemporaryNote = () => {
    const body = temporaryNote.trim();
    if (!body || temporaryNoteImported) return;
    const nextMarkdown = `${deskBodyMarkdown.trim()}\n\n## 临时笔记\n${body}`.trim();
    setDeskBodyMarkdown(nextMarkdown);
    setDeskBodyHtml(markdownToSafeHtml(nextMarkdown));
    setStickyNotes((current) => [...current, {
      note_id: `temporary:${temporaryNoteUpdatedAt || Date.now().toString(36)}`,
      body: body.slice(0, 1000),
      color: 'ochre',
    }]);
    markDeskDirty();
    setDeskTool('write');
  };

  const dossierInDesk = Boolean(dossier) && stickyNotes.some(
    (note) => note.note_id === `dossier:${dossier?.dossier_id}`,
  );

  const importDossierToDesk = () => {
    if (!dossier || dossierInDesk) return;
    const choiceLines = dossier.key_choices.map(
      (choice) => `- 第 ${choice.turn_no} 回合：${choice.choice}${choice.consequence ? `——${choice.consequence}` : ''}`,
    );
    const parts = [
      deskBodyMarkdown.trim(),
      `## 推演回看：${dossier.title}`,
      dossier.strategy_summary,
      ...choiceLines,
      '## 历史解释',
      dossier.historical_explanation,
    ].filter(Boolean);
    const nextMarkdown = parts.join('\n\n');
    setDeskBodyMarkdown(nextMarkdown);
    setDeskBodyHtml(markdownToSafeHtml(nextMarkdown));
    setStickyNotes((current) => [...current, {
      note_id: `dossier:${dossier.dossier_id}`,
      body: dossier.strategy_summary.slice(0, 1000),
      color: 'jade',
    }]);
    markDeskDirty();
    setDeskTool('write');
  };

  const saveDeskNow = async (): Promise<LearningDeskDraftRecord | null> => {
    if (!deskHydrated) return null;
    if (deskSaveTimerRef.current !== null) {
      window.clearTimeout(deskSaveTimerRef.current);
      deskSaveTimerRef.current = null;
    }
    setDeskSaveStatus('saving');
    try {
      const saved = await writeLearningDeskDraft(temporaryNoteIdentity, {
        title: deskTitle,
        body_html: deskBodyHtml,
        body_markdown: deskBodyMarkdown,
        sticky_notes: stickyNotes,
        drawing_strokes: drawingStrokes,
      }, deskDraft);
      setDeskDraft(saved);
      setDeskSavedAt(new Date(saved.updated_at));
      setDeskSaveStatus('saved');
      return saved;
    } catch {
      setDeskSaveStatus('error');
      return null;
    }
  };

  const openSubmissionDetail = async (submissionId: string) => {
    setSubmissionDetailLoading(true);
    try {
      const detail = await api.learningSubmission(submissionId);
      setSubmissionDetail(detail);
    } catch (error) {
      message.error(`成果版本读取失败：${errorMessage(error)}`);
    } finally {
      setSubmissionDetailLoading(false);
    }
  };

  const openSubmissionHistory = async () => {
    setSubmissionHistoryOpen(true);
    const items = await loadSubmissions();
    const first = items[0] ?? submissionItems[0];
    if (first) await openSubmissionDetail(first.submission_id);
  };

  const submitLearningWork = async () => {
    if (submissionStatus === 'preparing' || submissionStatus === 'submitting') return;
    if (auth.mode !== 'accounts') {
      setSubmissionStatus('error');
      setSubmissionError('请使用统一账户登录后提交；本机草稿仍然保留。');
      return;
    }

    setSubmissionError('');
    let request = pendingSubmission;
    try {
      if (!request) {
        setSubmissionStatus('preparing');
        const savedDraft = await saveDeskNow();
        if (!savedDraft) throw new Error('本机草稿尚未保存成功，请先重试保存。');
        if (canvasPhase === 'loading') throw new Error('知识导图仍在载入，请稍候再提交。');
        if (canvasPhase === 'conflict' || canvasPhase === 'error') {
          throw new Error('知识导图尚未安全同步，请先恢复画板再提交。');
        }
        if (canvasPhase === 'ready' && !(await saveNow())) {
          throw new Error('知识导图尚未安全同步，请先重试保存。');
        }
        const latestEvents = await listLearningEvents(temporaryNoteIdentity);
        setLearningEvents(latestEvents);
        request = buildLearningSubmissionRequest(savedDraft, latestEvents);
        setPendingSubmission(request);
        try {
          writePendingSubmission(window.localStorage, temporaryNoteIdentity, request);
        } catch {
          // The in-memory retry snapshot is still enough for this page session.
        }
      }

      setSubmissionStatus('submitting');
      const result = await api.learningSubmit(request);
      try {
        clearPendingSubmission(window.localStorage, temporaryNoteIdentity);
      } catch {
        // Storage cleanup cannot invalidate a server-confirmed submission.
      }
      setPendingSubmission(null);
      setSubmissionStatus('idle');
      const items = await loadSubmissions();
      const submitted = items.find(
        (item) => item.submission_id === result.submission.submission_id,
      );
      if (!submitted) {
        setSubmissionItems((current) => [{
          submission_id: result.submission.submission_id,
          student_id: result.submission.student_id,
          student_display_name: auth.principal?.display_name ?? '我',
          student_username: auth.principal?.username,
          course_id: result.submission.course_id,
          lesson_id: result.submission.lesson_id,
          version: result.submission.version,
          title: result.submission.title,
          body_excerpt: result.submission.body_markdown.replace(/\s+/g, ' ').slice(0, 180),
          sticky_note_count: result.submission.sticky_notes.length,
          stroke_count: result.submission.drawing_strokes.length,
          event_count: result.submission.learning_events.length,
          canvas_node_count: result.submission.canvas.nodes.length,
          submitted_at: result.submission.submitted_at,
          checksum: result.submission.checksum,
          latest_feedback: null,
        }, ...current]);
      }
      setSubmissionError('');
      message.success(result.reused
        ? `已确认第 ${result.submission.version} 版成果，无需重复提交`
        : `第 ${result.submission.version} 版学习成果已提交给教师`);
    } catch (error) {
      setSubmissionStatus('error');
      setSubmissionError(errorMessage(error));
    }
  };

  const deskSaveLabel = deskSaveStatus === 'loading'
    ? '正在展开书案…'
    : deskSaveStatus === 'saving'
      ? '正在保存本机草稿…'
      : deskSaveStatus === 'error'
        ? '本机保存失败'
        : deskSaveStatus === 'saved' && deskSavedAt
          ? `本机已保存 ${formatHm(deskSavedAt)}`
          : '尚未产生修改';
  const latestSubmission = submissionItems[0] ?? null;
  const submissionBusy = submissionStatus === 'preparing' || submissionStatus === 'submitting';
  const submissionButtonLabel = pendingSubmission
    ? '重试上次提交'
    : latestSubmission
      ? '提交新版本'
      : '提交本次成果';

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
      <section className="chrono-learning-desk" aria-labelledby="chrono-learning-desk-title">
        <header className="chrono-learning-desk-masthead">
          <div>
            <span className="chrono-learning-desk-seal" aria-hidden="true">录</span>
            <div>
              <p>第四阶段 · 你的历史学习成果</p>
              <h2 id="chrono-learning-desk-title">学习书案</h2>
              <span>正文、便签、手绘、导图与前三阶段留痕，在这里汇成一份可继续修改的个人卷宗。</span>
            </div>
          </div>
          <div className="chrono-desk-publish-control">
            <div className={`chrono-desk-save-state ${deskSaveStatus}`} aria-live="polite">
              {deskSaveStatus === 'saving' ? <CloudSyncOutlined spin /> : <SaveOutlined />}
              <span>{deskSaveLabel}</span>
              {deskSaveStatus === 'error' ? (
                <Button size="small" type="link" onClick={() => void saveDeskNow()}>重试</Button>
              ) : null}
            </div>
            <div className="chrono-desk-submit-state">
              <div>
                <strong>{latestSubmission ? `教师可见 · 第 ${latestSubmission.version} 版` : '尚未提交给教师'}</strong>
                <span>{latestSubmission
                  ? `${formatHm(new Date(latestSubmission.submitted_at))} 提交${latestSubmission.latest_feedback ? ' · 已有反馈' : ' · 等待反馈'}`
                  : '本机自动保存不等于提交，只有你确认后教师才能看到。'}</span>
              </div>
              <div>
                <Button
                  ghost
                  icon={<ReadOutlined />}
                  loading={submissionListLoading}
                  onClick={() => void openSubmissionHistory()}
                >版本记录</Button>
                <Popconfirm
                  title={pendingSubmission ? '重试被冻结的上次提交？' : '确认提交当前学习成果？'}
                  description={pendingSubmission
                    ? '将原样重试上次内容，避免网络中断产生重复版本。'
                    : '提交后生成不可变版本；你仍可继续编辑并提交下一版。'}
                  okText="确认提交"
                  cancelText="继续编辑"
                  onConfirm={() => submitLearningWork()}
                >
                  <Button
                    type="primary"
                    icon={<SendOutlined />}
                    loading={submissionBusy}
                    disabled={!deskHydrated || auth.mode !== 'accounts'}
                  >{submissionButtonLabel}</Button>
                </Popconfirm>
              </div>
            </div>
          </div>
        </header>

        {submissionError ? (
          <Alert
            banner
            closable
            type="warning"
            message={pendingSubmission ? '上次提交尚未获得服务器确认，本机保留了完全相同的重试副本。' : '学习成果暂未提交，本机草稿保持不变。'}
            description={submissionError}
            onClose={() => {
              setSubmissionError('');
              if (submissionStatus === 'error') setSubmissionStatus('idle');
            }}
          />
        ) : null}

        <div className="chrono-learning-desk-shell">
          <aside className="chrono-desk-inbox" aria-label="本课材料匣">
            <header>
              <span>材料匣</span>
              <strong>{learningEvents.length} 条学习留痕</strong>
            </header>

            <article className={temporaryNote.trim() ? '' : 'is-empty'}>
              <div><EditOutlined /><strong>临时笔记</strong></div>
              <p>{temporaryNote.trim() || '助教浮窗中的随手记会出现在这里。'}</p>
              {temporaryNoteUpdatedAt ? <time>{formatHm(new Date(temporaryNoteUpdatedAt))} 更新</time> : null}
              <Button
                size="small"
                disabled={!temporaryNote.trim() || temporaryNoteImported}
                onClick={importTemporaryNote}
              >{temporaryNoteImported ? '已收入正文' : '收入正文'}</Button>
            </article>

            <article className={dossier ? '' : 'is-empty'}>
              <div><FileDoneOutlined /><strong>推演卷宗</strong></div>
              <p>{dossier?.strategy_summary || '完成历史抉择后，可把选择与解释整理进正文。'}</p>
              <Button
                size="small"
                disabled={!dossier || dossierInDesk}
                onClick={importDossierToDesk}
              >{dossierInDesk ? '已收入正文' : '整理进正文'}</Button>
            </article>

            <article>
              <div><ApartmentOutlined /><strong>知识导图</strong></div>
              <p>{nodes.length} 个节点，{edges.length} 条关系。导图继续同步到后端学习资产。</p>
              {renderSaveStatus()}
            </article>
          </aside>

          <div className="chrono-desk-workspace">
            <nav className="chrono-desk-tools" aria-label="书案工具">
              {([
                ['write', '正文与便签', <BookOutlined key="write-icon" />],
                ['draw', '手写与绘图', <EditOutlined key="draw-icon" />],
                ['map', '知识导图', <ApartmentOutlined key="map-icon" />],
                ['trail', '学习轨迹', <HistoryOutlined key="trail-icon" />],
              ] as const).map(([tool, label, icon]) => (
                <button
                  type="button"
                  key={tool}
                  className={deskTool === tool ? 'active' : ''}
                  aria-pressed={deskTool === tool}
                  onClick={() => setDeskTool(tool)}
                >
                  {icon}<span>{label}</span>
                </button>
              ))}
            </nav>

            {!deskHydrated ? (
              <div className="chrono-create-loading"><Spin /><span>正在展开你的书案…</span></div>
            ) : deskTool === 'write' ? (
              <div className="chrono-desk-writing-layout">
                <LearningDeskEditor
                  title={deskTitle}
                  html={deskBodyHtml}
                  markdown={deskBodyMarkdown}
                  onTitleChange={changeDeskTitle}
                  onDocumentChange={changeDeskDocument}
                />
                <aside className="chrono-desk-stickies" aria-label="书案便签">
                  <header>
                    <div><strong>便签</strong><span>拖思路之前，先把它写下来</span></div>
                    <Button size="small" icon={<PlusOutlined />} onClick={addStickyNote}>新便签</Button>
                  </header>
                  <div>
                    {stickyNotes.length > 0 ? stickyNotes.map((note) => (
                      <article className={note.color} key={note.note_id}>
                        <Input.TextArea
                          aria-label="便签内容"
                          value={note.body}
                          maxLength={1000}
                          autoSize={{ minRows: 4 }}
                          onChange={(event) => updateStickyNote(note.note_id, event.target.value)}
                        />
                        <Button
                          type="text"
                          size="small"
                          danger
                          aria-label="删除便签"
                          icon={<DeleteOutlined />}
                          onClick={() => removeStickyNote(note.note_id)}
                        />
                      </article>
                    )) : (
                      <button type="button" className="chrono-desk-empty-sticky" onClick={addStickyNote}>
                        <PlusOutlined /> 添加第一张便签
                      </button>
                    )}
                  </div>
                </aside>
              </div>
            ) : deskTool === 'draw' ? (
              <LearningDeskDrawing strokes={drawingStrokes} onChange={changeDrawing} />
            ) : deskTool === 'trail' ? (
              <section className="chrono-learning-trail" aria-label="前三阶段学习轨迹">
                <header>
                  <div><span>自动留痕</span><h3>这份判断是怎样形成的</h3></div>
                  <p>这里只记录当前账号在本课中的学习动作，不记录登录凭据，也不会替你编写结论。</p>
                </header>
                {learningEvents.length > 0 ? (
                  <ol>
                    {[...learningEvents].reverse().map((event) => (
                      <li className={`kind-${event.kind}`} key={event.event_id}>
                        <time>{formatHm(new Date(event.occurred_at))}</time>
                        <span aria-hidden="true" />
                        <div><strong>{event.title}</strong><p>{event.summary}</p></div>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <div className="chrono-learning-trail-empty">回到踏勘、抉择或召见进行学习，这里会自动形成轨迹。</div>
                )}
              </section>
            ) : canvasPhase === 'error' ? (
              <Alert
                type="error"
                showIcon
                message="知识导图未能安全载入"
                description={canvasError}
                action={<Button icon={<ReloadOutlined />} onClick={() => void loadCanvas()}>重试</Button>}
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
                    action={<Button size="small" icon={<ReloadOutlined />} onClick={() => void loadCanvas()}>载入最新版本</Button>}
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
                      >添加</Button>
                    </Tooltip>
                  </div>
                  <Button
                    icon={<ThunderboltOutlined />}
                    loading={generating}
                    disabled={canvasPhase !== 'ready'}
                    onClick={() => void aiGenerate()}
                  >AI 扩充</Button>
                  <div className="chrono-canvas-toolbar-spacer" />
                  {renderSaveStatus()}
                </div>
                <div ref={canvasStageRef} className="chrono-canvas-stage">
                  {canvasPhase === 'loading' || !flowReady ? (
                    <div className="chrono-create-loading"><Spin /></div>
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
        </div>
      </section>

      <DossierPanel
        state={dossierState}
        canvasPhase={canvasPhase}
        imported={dossierImported}
        onImport={importDossier}
        onRetry={() => void loadDossier()}
        onOpenPractice={onOpenPractice}
      />

      <Drawer
        title="我的成果版本"
        width="min(1080px, 96vw)"
        open={submissionHistoryOpen}
        onClose={() => setSubmissionHistoryOpen(false)}
      >
        <div className="chrono-submission-history">
          <aside aria-label="成果版本列表">
            <div className="chrono-submission-history-intro">
              <strong>教师只会看到这些版本</strong>
              <span>本机草稿与失败的提交不会出现在教师队列。</span>
            </div>
            {submissionListLoading ? <Spin size="small" /> : submissionItems.length > 0 ? (
              submissionItems.map((item) => (
                <button
                  type="button"
                  key={item.submission_id}
                  className={submissionDetail?.submission.submission_id === item.submission_id ? 'active' : ''}
                  onClick={() => void openSubmissionDetail(item.submission_id)}
                >
                  <span>第 {item.version} 版</span>
                  <strong>{item.title}</strong>
                  <small>{new Date(item.submitted_at).toLocaleString('zh-CN')}</small>
                  {item.latest_feedback ? <Tag color={item.latest_feedback.completion_status === 'completed' ? 'green' : 'gold'}>已有反馈</Tag> : null}
                </button>
              ))
            ) : (
              <div className="chrono-submission-history-empty">还没有提交版本。</div>
            )}
          </aside>
          <main>
            {submissionDetailLoading ? (
              <div className="chrono-create-loading"><Spin /><span>正在展开成果版本…</span></div>
            ) : submissionDetail ? (
              <LearningSubmissionViewer detail={submissionDetail} showStudent={false} />
            ) : (
              <div className="chrono-submission-history-empty">选择一个版本查看完整内容与教师反馈。</div>
            )}
          </main>
        </div>
      </Drawer>
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
  const projection = projectDossierKnowledge(dossier);
  const hasKnowledge = projection.nodes.length > 0;
  return (
    <section className="chrono-dossier-band chrono-dossier-archive" aria-label="史官卷宗">
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
      <details>
        <summary>
          <span>展开完整史官卷宗</span>
          <small>{dossier.key_choices.length} 项选择 · {projection.nodes.length} 个知识节点 · {dossier.follow_up_questions.length} 个追问</small>
        </summary>
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
                ? `${projection.nodes.length} 个知识节点，${projection.edges.length} 条关系${projection.derived ? '（由封卷内容整理）' : ''}`
                : '本次卷宗没有可导入的知识节点'}
            </div>
          </div>
        </div>
      </details>
    </section>
  );
}
