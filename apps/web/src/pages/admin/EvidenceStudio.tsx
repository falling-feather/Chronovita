import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Divider,
  Empty,
  Input,
  InputNumber,
  Select,
  Space,
  Tag,
  Tooltip,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  FileAddOutlined,
  LockOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SaveOutlined,
  SendOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons';
import {
  ApiError,
  api,
  type EvidenceCertainty,
  type ContentFileRecord,
  type EvidenceDraft,
  type EvidenceKind,
  type EvidencePassage,
  type EvidenceSource,
  type EvidenceSourceKind,
  type EvidenceValidationReport,
  type EvidenceWorkflowRecord,
  type LessonPresentation,
  type LessonSourceRecord,
  type RuntimeEvidenceRecord,
  type RuntimePresentationRecord,
} from '../../utils/api';
import { toast } from '../../utils/toast';
import {
  createEvidenceDraft,
  createEvidencePassage,
  createEvidenceSource,
  createLessonPresentation,
  lessonEvidenceBindings,
  normalizeEvidenceDraft,
  signLessonPresentation,
  supplementKey,
  type LessonEvidenceBinding,
} from './evidenceModel';

const { TextArea } = Input;

const SOURCE_KIND_OPTIONS: Array<{ value: EvidenceSourceKind; label: string }> = [
  { value: 'curriculum', label: '课程标准' },
  { value: 'textbook', label: '教材/目录' },
  { value: 'primary_source', label: '传世文献' },
  { value: 'archaeology', label: '考古材料' },
  { value: 'museum', label: '博物馆/公共机构' },
  { value: 'research', label: '现代研究' },
  { value: 'other', label: '其他' },
];

const EVIDENCE_KIND_OPTIONS: Array<{ value: EvidenceKind; label: string }> = [
  { value: 'curriculum_goal', label: '课程目标' },
  { value: 'transmitted_text', label: '传世文本' },
  { value: 'archaeological_evidence', label: '考古证据' },
  { value: 'scholarly_interpretation', label: '学术解释' },
  { value: 'teaching_explanation', label: '教学解释' },
  { value: 'boundary_note', label: '边界说明' },
];

const CERTAINTY_OPTIONS: Array<{ value: EvidenceCertainty; label: string }> = [
  { value: 'consensus', label: '共识' },
  { value: 'interpretation', label: '解释' },
  { value: 'legend', label: '传说' },
  { value: 'disputed', label: '有争议' },
];

const WORKFLOW_META: Record<EvidenceWorkflowRecord['state'], { label: string; color: string }> = {
  draft: { label: '草稿', color: 'default' },
  validated: { label: '校验通过', color: 'cyan' },
  in_review: { label: '待独立审校', color: 'gold' },
  changes_requested: { label: '已退回', color: 'orange' },
  approved: { label: '审校通过', color: 'green' },
  sealed: { label: '已封存', color: 'blue' },
};

interface EvidenceStudioProps {
  token: string;
  canAuthor: boolean;
  canReview: boolean;
  canPublish: boolean;
  sourceLessons: LessonSourceRecord[];
  courseDrafts: ContentFileRecord[];
  runtimeEvidence: RuntimeEvidenceRecord[];
  runtimePresentations: RuntimePresentationRecord[];
  onRefreshArtifacts: () => Promise<void>;
}

function displayError(error: unknown, fallback: string): string {
  if (error instanceof Error) return error.message;
  return fallback;
}

function isEditableState(workflow: EvidenceWorkflowRecord | null): boolean {
  return !workflow || ['draft', 'validated', 'changes_requested'].includes(workflow.state);
}

function checksumLabel(value: string): string {
  return value ? `${value.slice(0, 10)}…` : '未生成';
}

export default function EvidenceStudio({
  token,
  canAuthor,
  canReview,
  canPublish,
  sourceLessons,
  courseDrafts,
  runtimeEvidence,
  runtimePresentations,
  onRefreshArtifacts,
}: EvidenceStudioProps) {
  const firstLesson = sourceLessons.find((item) => item.lesson_id === 'L101') || sourceLessons[0];
  const [drafts, setDrafts] = useState<EvidenceDraft[]>([]);
  const [selectedDraftId, setSelectedDraftId] = useState<string>();
  const [draft, setDraft] = useState<EvidenceDraft>(() => createEvidenceDraft(
    firstLesson?.course_id,
    firstLesson?.lesson_id,
  ));
  const [workflow, setWorkflow] = useState<EvidenceWorkflowRecord | null>(null);
  const [report, setReport] = useState<EvidenceValidationReport | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState('');
  const [staleConflict, setStaleConflict] = useState(false);
  const [factBindings, setFactBindings] = useState<LessonEvidenceBinding[]>([]);
  const [personBindings, setPersonBindings] = useState<LessonEvidenceBinding[]>([]);
  const [presentation, setPresentation] = useState<LessonPresentation>(() => (
    createLessonPresentation(firstLesson?.course_id, firstLesson?.lesson_id)
  ));
  const loadSequenceRef = useRef(0);

  const editable = canAuthor && isEditableState(workflow);
  const lessonEvidence = useMemo(() => runtimeEvidence.filter((item) => (
    item.descriptor.course_id === draft.course_id
    && item.descriptor.lesson_id === draft.lesson_id
  )), [draft.course_id, draft.lesson_id, runtimeEvidence]);
  const lessonPresentations = useMemo(() => runtimePresentations.filter((item) => (
    item.descriptor.course_id === draft.course_id
    && item.descriptor.lesson_id === draft.lesson_id
  )), [draft.course_id, draft.lesson_id, runtimePresentations]);
  const sourceOptions = draft.sources.map((source) => ({
    value: source.source_id,
    label: `${source.title || '未命名来源'} · ${source.source_id}`,
  }));
  const courseDraftTitles = useMemo(
    () => new Map(courseDrafts.map((item) => [item.lesson_id, item.title])),
    [courseDrafts],
  );
  const factOptions = factBindings.map((item) => ({
    value: item.id,
    label: `${item.id} · ${item.label}`,
  }));
  const personOptions = personBindings.map((item) => ({
    value: item.id,
    label: `${item.id} · ${item.label}`,
  }));

  const refreshDrafts = async (silent = false) => {
    if (!token) return;
    try {
      const response = await api.adminEvidenceDrafts(token);
      setDrafts(response.items);
    } catch (error) {
      if (!silent) toast.error(displayError(error, '证据草稿库读取失败'));
    }
  };

  useEffect(() => {
    void refreshDrafts(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    const sequence = ++loadSequenceRef.current;
    if (!token || !draft.lesson_id) {
      setFactBindings([]);
      setPersonBindings([]);
      return;
    }
    void api.adminContentDraft(token, draft.lesson_id)
      .catch(() => api.adminContentSourceLesson(token, draft.lesson_id))
      .then(lessonEvidenceBindings)
      .then((bindings) => {
        if (sequence !== loadSequenceRef.current) return;
        setFactBindings(bindings.facts);
        setPersonBindings(bindings.people);
      })
      .catch(() => {
        if (sequence !== loadSequenceRef.current) return;
        setFactBindings([]);
        setPersonBindings([]);
      });
  }, [draft.lesson_id, token]);

  const patchDraft = (patch: Partial<EvidenceDraft>) => {
    setDraft((current) => ({ ...current, ...patch }));
    setReport(null);
    setStaleConflict(false);
  };

  const patchSource = (index: number, patch: Partial<EvidenceSource>) => {
    patchDraft({
      sources: draft.sources.map((item, currentIndex) => (
        currentIndex === index ? { ...item, ...patch } : item
      )),
    });
  };

  const patchPassage = (index: number, patch: Partial<EvidencePassage>) => {
    patchDraft({
      passages: draft.passages.map((item, currentIndex) => (
        currentIndex === index ? { ...item, ...patch } : item
      )),
    });
  };

  const newDraft = (lessonId?: string) => {
    const lesson = sourceLessons.find((item) => item.lesson_id === lessonId)
      || sourceLessons.find((item) => item.lesson_id === draft.lesson_id)
      || firstLesson;
    const next = createEvidenceDraft(lesson?.course_id, lesson?.lesson_id);
    setDraft(next);
    setWorkflow(null);
    setReport(null);
    setSelectedDraftId(undefined);
    setStaleConflict(false);
    setPresentation(createLessonPresentation(next.course_id, next.lesson_id));
  };

  const changeLesson = (lessonId: string) => {
    const lesson = sourceLessons.find((item) => item.lesson_id === lessonId);
    if (!lesson || draft.revision > 0) return;
    const next = createEvidenceDraft(lesson.course_id, lesson.lesson_id);
    setDraft(next);
    setPresentation(createLessonPresentation(lesson.course_id, lesson.lesson_id));
  };

  const loadDraft = async (corpusId = selectedDraftId) => {
    if (!corpusId) return;
    setBusy('load');
    try {
      const response = await api.adminEvidenceDraft(token, corpusId);
      setDraft(response.item);
      setWorkflow(response.workflow);
      setReport(response.workflow?.validation || null);
      setSelectedDraftId(corpusId);
      setStaleConflict(false);
      const nextVersion = Math.max(
        0,
        ...runtimePresentations
          .filter((item) => item.descriptor.course_id === response.item.course_id
            && item.descriptor.lesson_id === response.item.lesson_id)
          .map((item) => item.descriptor.version),
      ) + 1;
      setPresentation(createLessonPresentation(
        response.item.course_id,
        response.item.lesson_id,
        nextVersion,
      ));
    } catch (error) {
      toast.error(displayError(error, '证据草稿读取失败'));
    } finally {
      setBusy('');
    }
  };

  const saveDraft = async (): Promise<EvidenceDraft | null> => {
    if (!editable) return null;
    setBusy('save');
    try {
      const payload = normalizeEvidenceDraft(draft);
      const response = payload.revision === 0
        ? await api.adminSaveEvidenceDraft(token, payload)
        : await api.adminUpdateEvidenceDraft(token, payload);
      setDraft(response.item);
      setWorkflow(response.workflow);
      setReport(response.workflow.validation);
      setSelectedDraftId(response.item.corpus_id);
      setStaleConflict(false);
      await refreshDrafts(true);
      toast.success(`证据草稿已保存 · 修订 ${response.item.revision}`);
      return response.item;
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setStaleConflict(true);
        toast.error('服务器草稿已更新；请重新载入后再继续，当前内容不会覆盖服务器版本');
      } else {
        toast.error(displayError(error, '证据草稿保存失败'));
      }
      return null;
    } finally {
      setBusy('');
    }
  };

  const validateDraft = async () => {
    if (draft.revision === 0) {
      toast.warning('请先保存证据草稿，再执行校验');
      return;
    }
    setBusy('validate');
    try {
      const response = await api.adminValidateEvidenceDraft(token, draft.corpus_id);
      setWorkflow(response.workflow);
      setReport(response.report);
      toast.success(response.report?.valid ? '证据绑定校验通过' : '校验完成，请处理阻断项');
    } catch (error) {
      toast.error(displayError(error, '证据校验失败'));
    } finally {
      setBusy('');
    }
  };

  const submitReview = async () => {
    setBusy('submit');
    try {
      const response = await api.adminSubmitEvidenceReview(token, draft.corpus_id, note);
      setWorkflow(response.workflow);
      setReport(response.report);
      toast.success('证据草稿已送交独立审校');
    } catch (error) {
      toast.error(displayError(error, '送审失败'));
    } finally {
      setBusy('');
    }
  };

  const review = async (decision: 'approve' | 'changes_requested') => {
    if (decision === 'changes_requested' && !note.trim()) {
      toast.warning('退回修改时请填写审校意见');
      return;
    }
    setBusy(decision);
    try {
      const response = await api.adminReviewEvidenceDraft(
        token,
        draft.corpus_id,
        decision,
        note,
      );
      setWorkflow(response.workflow);
      setReport(response.report);
      toast.success(decision === 'approve' ? '独立审校已通过' : '已退回作者修改');
    } catch (error) {
      toast.error(displayError(error, '审校操作失败'));
    } finally {
      setBusy('');
    }
  };

  const seal = async () => {
    setBusy('seal');
    try {
      const response = await api.adminSealEvidenceDraft(token, draft.corpus_id);
      setWorkflow(response.workflow);
      await Promise.all([refreshDrafts(true), onRefreshArtifacts()]);
      toast.success(response.idempotent
        ? `继续使用证据库 v${response.record.descriptor.version}`
        : `证据库已封存为 v${response.record.descriptor.version}`);
    } catch (error) {
      toast.error(displayError(error, '证据库封存失败'));
    } finally {
      setBusy('');
    }
  };

  const patchPresentation = (patch: Partial<LessonPresentation>) => {
    setPresentation((current) => ({ ...current, ...patch, checksum: '0'.repeat(64) }));
  };

  const stagePresentation = async () => {
    setBusy('presentation');
    try {
      const estimated = Object.values(presentation.phase_minutes)
        .reduce((sum, minutes) => sum + minutes, 0);
      const signed = await signLessonPresentation({
        ...presentation,
        estimated_minutes: estimated,
        sealed_at: new Date().toISOString(),
      });
      const response = await api.adminStageLessonPresentation(token, signed);
      setPresentation(signed);
      await onRefreshArtifacts();
      toast.success(`展示资源已校验并封存为 v${response.record.descriptor.version}`);
    } catch (error) {
      toast.error(displayError(
        error,
        '展示资源封存失败；请检查文件路径、SHA-256 与 45–60 秒媒体约束',
      ));
    } finally {
      setBusy('');
    }
  };

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <section className="chrono-card" style={{ padding: 18 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div style={{ maxWidth: 760 }}>
            <div className="chrono-course-eyeline">Evidence corpus · course-release/v3</div>
            <h2 className="chrono-title" style={{ margin: '6px 0 8px', fontSize: 24 }}>证据资料库与展示发布</h2>
            <div style={{ color: 'var(--text-mute)', lineHeight: 1.75 }}>
              逐项绑定来源、稳定片段、课程事实与人物边界；作者、审校者、管理员分别完成送审、批准和不可变封存。这里不抓取网页，也不处理 PDF/OCR。
            </div>
          </div>
          <Space size={[6, 6]} wrap>
            <Tag color="blue">资料草稿 {drafts.length}</Tag>
            <Tag color="cyan">封存语料 {runtimeEvidence.length}</Tag>
            <Tag color="gold">展示资源 {runtimePresentations.length}</Tag>
          </Space>
        </div>
      </section>

      {staleConflict && (
        <Alert
          type="error"
          showIcon
          message="检测到旧修订，已阻止覆盖"
          description="另一账号或页面已经更新这份证据草稿。请重新载入服务器版本，再人工合并仍需保留的内容。"
          action={<Button danger onClick={() => loadDraft(draft.corpus_id)}>重新载入</Button>}
        />
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 420px), 1fr))', gap: 16, alignItems: 'start', minWidth: 0 }}>
        <fieldset
          className="chrono-card"
          disabled={Boolean(busy)}
          aria-busy={Boolean(busy)}
          style={{ border: 0, margin: 0, minWidth: 0, padding: 18 }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
            <div>
              <div className="chrono-course-eyeline">资料库草稿</div>
              <div style={{ marginTop: 6 }}>
                {workflow ? (
                  <Space size={[6, 6]} wrap>
                    <Tag color={WORKFLOW_META[workflow.state].color}>{WORKFLOW_META[workflow.state].label}</Tag>
                    <Tag>草稿修订 {draft.revision}</Tag>
                    {workflow.sealed_version && <Tag color="blue">不可变 v{workflow.sealed_version}</Tag>}
                  </Space>
                ) : <Tag>尚未保存</Tag>}
              </div>
            </div>
            <Space wrap>
              <Button icon={<FileAddOutlined />} disabled={!canAuthor} onClick={() => newDraft()}>新建</Button>
              <Button type="primary" icon={<SaveOutlined />} disabled={!editable} loading={busy === 'save'} onClick={saveDraft}>保存修订</Button>
            </Space>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))', gap: 12 }}>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>正式课时</div>
              <Select
                aria-label="证据正式课时"
                showSearch
                optionFilterProp="label"
                value={draft.lesson_id}
                disabled={!editable || draft.revision > 0}
                onChange={changeLesson}
                options={sourceLessons.map((item) => ({
                  value: item.lesson_id,
                  label: `${item.lesson_id} · ${item.course_title} · ${courseDraftTitles.get(item.lesson_id) || item.title}`,
                }))}
                style={{ width: '100%' }}
              />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>语料库 ID</div>
              <Input aria-label="证据库 ID" value={draft.corpus_id} disabled={!editable || draft.revision > 0} onChange={(event) => patchDraft({ corpus_id: event.target.value })} />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>课程 ID</div>
              <Input aria-label="证据课程 ID" value={draft.course_id} disabled />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>标题</div>
              <Input aria-label="证据库标题" value={draft.title} disabled={!editable} onChange={(event) => patchDraft({ title: event.target.value })} />
            </label>
          </div>
          <label>
            <div className="chrono-course-eyeline" style={{ margin: '12px 0 6px' }}>适用范围与史实边界</div>
            <TextArea aria-label="证据库范围" value={draft.scope_note} disabled={!editable} onChange={(event) => patchDraft({ scope_note: event.target.value })} autoSize={{ minRows: 3, maxRows: 7 }} />
          </label>

          <Divider style={{ margin: '18px 0 12px' }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', marginBottom: 10 }}>
            <div>
              <div className="chrono-course-eyeline">可复核来源</div>
              <div style={{ color: 'var(--text-mute)', fontSize: 12, marginTop: 4 }}>正式课建议 8–12 项；权利说明和定位信息随发布固化。</div>
            </div>
            <Button icon={<PlusOutlined />} disabled={!editable} onClick={() => patchDraft({ sources: [...draft.sources, createEvidenceSource(draft.sources.length + 1)] })}>添加来源</Button>
          </div>
          <div style={{ display: 'grid', gap: 10 }}>
            {draft.sources.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未添加来源" />}
            {draft.sources.map((source, index) => (
              <details key={`${source.source_id}-${index}`} open={draft.sources.length <= 2} style={{ border: '1px solid var(--border-soft)', borderRadius: 8, padding: 12, background: 'var(--bg-warm-soft)' }}>
                <summary style={{ cursor: 'pointer', fontWeight: 650 }}>
                  {String(index + 1).padStart(2, '0')} · {source.title || '未命名来源'} <Tag style={{ marginLeft: 8 }}>{source.source_id}</Tag>
                </summary>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 210px), 1fr))', gap: 10, marginTop: 12 }}>
                  <Input aria-label={`来源 ${index + 1} ID`} value={source.source_id} disabled={!editable} placeholder="source-id" onChange={(event) => patchSource(index, { source_id: event.target.value })} />
                  <Input aria-label={`来源 ${index + 1} 标题`} value={source.title} disabled={!editable} placeholder="来源标题" onChange={(event) => patchSource(index, { title: event.target.value })} />
                  <Select aria-label={`来源 ${index + 1} 类型`} value={source.kind} disabled={!editable} options={SOURCE_KIND_OPTIONS} onChange={(value) => patchSource(index, { kind: value })} />
                  <Input aria-label={`来源 ${index + 1} 作者`} value={source.author_or_institution} disabled={!editable} placeholder="作者或机构" onChange={(event) => patchSource(index, { author_or_institution: event.target.value })} />
                  <Input aria-label={`来源 ${index + 1} 出版者`} value={source.publisher} disabled={!editable} placeholder="出版者" onChange={(event) => patchSource(index, { publisher: event.target.value })} />
                  <InputNumber aria-label={`来源 ${index + 1} 年代`} value={source.published_year} disabled={!editable} placeholder="出版年（可空）" min={-3000} max={3000} style={{ width: '100%' }} onChange={(value) => patchSource(index, { published_year: value })} />
                  <Select aria-label={`来源 ${index + 1} 可靠性`} value={source.reliability} disabled={!editable} options={[{ value: 'reviewed', label: '已审阅' }, { value: 'disputed', label: '有争议' }]} onChange={(value) => patchSource(index, { reliability: value })} />
                  <Input aria-label={`来源 ${index + 1} 定位`} value={source.locator} disabled={!editable} placeholder="页码、章节或馆藏定位" onChange={(event) => patchSource(index, { locator: event.target.value })} />
                </div>
                <Input aria-label={`来源 ${index + 1} 路径`} value={source.url_or_path} disabled={!editable} placeholder="公开 URL 或项目内路径" style={{ marginTop: 10 }} onChange={(event) => patchSource(index, { url_or_path: event.target.value })} />
                <TextArea aria-label={`来源 ${index + 1} 引用说明`} value={source.citation_note} disabled={!editable} placeholder="该来源支持什么，不支持什么" autoSize={{ minRows: 2, maxRows: 5 }} style={{ marginTop: 10 }} onChange={(event) => patchSource(index, { citation_note: event.target.value })} />
                <TextArea aria-label={`来源 ${index + 1} 权利说明`} value={source.rights_note} disabled={!editable} autoSize={{ minRows: 2, maxRows: 4 }} style={{ marginTop: 10 }} onChange={(event) => patchSource(index, { rights_note: event.target.value })} />
                {editable && <Button danger type="text" style={{ marginTop: 8 }} onClick={() => patchDraft({ sources: draft.sources.filter((_, current) => current !== index) })}>移除此来源</Button>}
              </details>
            ))}
          </div>

          <Divider style={{ margin: '18px 0 12px' }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', marginBottom: 10 }}>
            <div>
              <div className="chrono-course-eyeline">稳定证据片段</div>
              <div style={{ color: 'var(--text-mute)', fontSize: 12, marginTop: 4 }}>正式课建议 25–40 段；事实与人物 ID 来自当前课时契约，不信任自由文本标题。</div>
            </div>
            <Button icon={<PlusOutlined />} disabled={!editable} onClick={() => patchDraft({ passages: [...draft.passages, createEvidencePassage(draft.passages.length + 1, draft.sources[0]?.source_id)] })}>添加片段</Button>
          </div>
          <div style={{ display: 'grid', gap: 10 }}>
            {draft.passages.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未添加证据片段" />}
            {draft.passages.map((passage, index) => (
              <details key={`${passage.passage_id}-${index}`} open={draft.passages.length <= 2} style={{ border: '1px solid var(--border-soft)', borderRadius: 8, padding: 12 }}>
                <summary style={{ cursor: 'pointer', fontWeight: 650 }}>
                  {String(index + 1).padStart(2, '0')} · {passage.title || '未命名片段'} <Tag style={{ marginLeft: 8 }}>{passage.passage_id}</Tag>
                </summary>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 210px), 1fr))', gap: 10, marginTop: 12 }}>
                  <Input aria-label={`片段 ${index + 1} ID`} value={passage.passage_id} disabled={!editable} placeholder="passage-id" onChange={(event) => patchPassage(index, { passage_id: event.target.value })} />
                  <Input aria-label={`片段 ${index + 1} 标题`} value={passage.title} disabled={!editable} placeholder="片段标题" onChange={(event) => patchPassage(index, { title: event.target.value })} />
                  <Select aria-label={`片段 ${index + 1} 来源`} value={passage.source_id || undefined} disabled={!editable} placeholder="绑定一个来源" showSearch optionFilterProp="label" options={sourceOptions} onChange={(value) => patchPassage(index, { source_id: value })} />
                  <Select aria-label={`片段 ${index + 1} 材料类型`} value={passage.evidence_kind} disabled={!editable} options={EVIDENCE_KIND_OPTIONS} onChange={(value) => patchPassage(index, { evidence_kind: value })} />
                  <Select aria-label={`片段 ${index + 1} 确定性`} value={passage.certainty} disabled={!editable} options={CERTAINTY_OPTIONS} onChange={(value) => patchPassage(index, { certainty: value })} />
                </div>
                <TextArea aria-label={`片段 ${index + 1} 正文`} value={passage.text} disabled={!editable} placeholder="必要摘录或项目自写证据表述" autoSize={{ minRows: 3, maxRows: 8 }} style={{ marginTop: 10 }} onChange={(event) => patchPassage(index, { text: event.target.value })} />
                <TextArea aria-label={`片段 ${index + 1} 摘要`} value={passage.summary} disabled={!editable} placeholder="面向七年级学生的自写摘要" autoSize={{ minRows: 2, maxRows: 5 }} style={{ marginTop: 10 }} onChange={(event) => patchPassage(index, { summary: event.target.value })} />
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 240px), 1fr))', gap: 10, marginTop: 10 }}>
                  <Select aria-label={`片段 ${index + 1} 事实绑定`} mode="tags" value={passage.fact_ids} disabled={!editable} placeholder="至少绑定一项课程事实" options={factOptions} optionFilterProp="label" onChange={(value) => patchPassage(index, { fact_ids: value })} />
                  <Select aria-label={`片段 ${index + 1} 人物绑定`} mode="tags" value={passage.person_ids} disabled={!editable} placeholder="可选人物边界" options={personOptions} optionFilterProp="label" onChange={(value) => patchPassage(index, { person_ids: value })} />
                  <Select aria-label={`片段 ${index + 1} 关键词`} mode="tags" tokenSeparators={['，', ',']} value={passage.keywords} disabled={!editable} placeholder="关键词" onChange={(value) => patchPassage(index, { keywords: value })} />
                </div>
                <TextArea aria-label={`片段 ${index + 1} 年代边界`} value={passage.chronology_note} disabled={!editable} placeholder="年代边界" autoSize={{ minRows: 2, maxRows: 4 }} style={{ marginTop: 10 }} onChange={(event) => patchPassage(index, { chronology_note: event.target.value })} />
                <TextArea aria-label={`片段 ${index + 1} 教学说明`} value={passage.teaching_note} disabled={!editable} placeholder="可选教学提示" autoSize={{ minRows: 2, maxRows: 4 }} style={{ marginTop: 10 }} onChange={(event) => patchPassage(index, { teaching_note: event.target.value })} />
                {editable && <Button danger type="text" style={{ marginTop: 8 }} onClick={() => patchDraft({ passages: draft.passages.filter((_, current) => current !== index) })}>移除此片段</Button>}
              </details>
            ))}
          </div>
        </fieldset>

        <aside style={{ display: 'grid', gap: 16, minWidth: 0 }}>
          <section className="chrono-card" style={{ padding: 16 }}>
            <div className="chrono-course-eyeline" style={{ marginBottom: 8 }}>草稿库</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <Select aria-label="证据草稿库" value={selectedDraftId} placeholder="打开已有证据草稿" showSearch optionFilterProp="label" style={{ flex: 1 }} options={drafts.map((item) => ({ value: item.corpus_id, label: `${item.title || item.corpus_id} · r${item.revision}` }))} onChange={setSelectedDraftId} />
              <Button loading={busy === 'load'} disabled={!selectedDraftId} onClick={() => loadDraft()}>打开</Button>
              <Tooltip title="刷新草稿库"><Button aria-label="刷新证据草稿库" icon={<ReloadOutlined />} onClick={() => refreshDrafts()} /></Tooltip>
            </div>
          </section>

          <section className="chrono-card" style={{ padding: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <div className="chrono-course-eyeline">校验 · 审校 · 封存</div>
              {workflow && <Tag color={WORKFLOW_META[workflow.state].color}>{WORKFLOW_META[workflow.state].label}</Tag>}
            </div>
            <Space size={[6, 8]} wrap>
              <Button icon={<SafetyCertificateOutlined />} loading={busy === 'validate'} disabled={!canAuthor || draft.revision === 0 || !isEditableState(workflow)} onClick={validateDraft}>校验</Button>
              <Button icon={<SendOutlined />} loading={busy === 'submit'} disabled={!canAuthor || !workflow || !['validated', 'changes_requested'].includes(workflow.state)} onClick={submitReview}>送审</Button>
              <Button icon={<CheckCircleOutlined />} loading={busy === 'approve'} disabled={!canReview || workflow?.state !== 'in_review'} onClick={() => review('approve')}>通过</Button>
              <Button danger icon={<CloseCircleOutlined />} loading={busy === 'changes_requested'} disabled={!canReview || workflow?.state !== 'in_review'} onClick={() => review('changes_requested')}>退回</Button>
              <Button icon={<LockOutlined />} loading={busy === 'seal'} disabled={!canPublish || workflow?.state !== 'approved'} onClick={seal}>封存</Button>
            </Space>
            <TextArea aria-label="证据审校备注" value={note} placeholder="送审、审校或封存说明；退回时必填" autoSize={{ minRows: 2, maxRows: 5 }} style={{ marginTop: 10 }} onChange={(event) => setNote(event.target.value)} />
            {report && (
              <Alert
                style={{ marginTop: 12 }}
                type={!report.valid ? 'error' : report.issues.length ? 'warning' : 'success'}
                showIcon
                message={report.valid ? `校验通过 · ${report.source_count} 项来源 / ${report.passage_count} 个片段` : `存在 ${report.issues.filter((item) => item.severity === 'error').length} 个阻断项`}
                description={report.issues.length ? (
                  <div style={{ display: 'grid', gap: 6, marginTop: 6 }}>
                    {report.issues.map((issue, index) => (
                      <div key={`${issue.code}-${issue.field}-${index}`} style={{ fontSize: 12 }}>
                        <Tag color={issue.severity === 'error' ? 'red' : 'gold'}>{issue.severity === 'error' ? '阻断' : '建议'}</Tag>
                        <code>{issue.field}</code> · {issue.message}
                      </div>
                    ))}
                  </div>
                ) : undefined}
              />
            )}
            {workflow?.history.length ? (
              <details style={{ marginTop: 12 }}>
                <summary className="chrono-course-eyeline" style={{ cursor: 'pointer' }}>审校留痕</summary>
                <div style={{ display: 'grid', gap: 7, marginTop: 9 }}>
                  {workflow.history.slice().reverse().slice(0, 6).map((event) => (
                    <div key={event.sequence} style={{ fontSize: 12, lineHeight: 1.55 }}>
                      <strong>#{event.sequence} · {WORKFLOW_META[event.to_state].label}</strong>
                      <div style={{ color: 'var(--text-mute)' }}>{event.actor} · {new Date(event.occurred_at).toLocaleString()}</div>
                      {event.note && <div>{event.note}</div>}
                    </div>
                  ))}
                </div>
              </details>
            ) : null}
          </section>

          <section className="chrono-card" style={{ padding: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', marginBottom: 8 }}>
              <div className="chrono-course-eyeline">不可变发布资源</div>
              <Tooltip title="刷新资源目录"><Button aria-label="刷新证据展示资源" type="text" icon={<ReloadOutlined />} onClick={onRefreshArtifacts} /></Tooltip>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-mute)', marginBottom: 8 }}>{draft.course_id} / {draft.lesson_id}</div>
            <div style={{ display: 'grid', gap: 7 }}>
              {lessonEvidence.map((item) => (
                <div key={supplementKey(item)} style={{ borderLeft: '3px solid var(--color-jade)', paddingLeft: 9 }}>
                  <strong>{item.title}</strong>
                  <div style={{ fontSize: 12, color: 'var(--text-mute)' }}>证据 v{item.descriptor.version} · {item.source_count} 来源 / {item.passage_count} 片段 · {checksumLabel(item.descriptor.checksum)}</div>
                </div>
              ))}
              {lessonPresentations.map((item) => (
                <div key={supplementKey(item)} style={{ borderLeft: '3px solid var(--color-gold)', paddingLeft: 9 }}>
                  <strong>{item.title}</strong>
                  <div style={{ fontSize: 12, color: 'var(--text-mute)' }}>展示 v{item.descriptor.version} · {item.video_duration_seconds}s · {checksumLabel(item.descriptor.checksum)}</div>
                </div>
              ))}
              {!lessonEvidence.length && !lessonPresentations.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前课时暂无封存资源" />}
            </div>
          </section>
        </aside>
      </div>

      <section className="chrono-card" style={{ padding: 18 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap', marginBottom: 14 }}>
          <div style={{ maxWidth: 720 }}>
            <div className="chrono-course-eyeline">LessonPresentationV1</div>
            <h3 className="chrono-title" style={{ margin: '6px 0 6px', fontSize: 20 }}>课堂短片与四阶段展示资源</h3>
            <div style={{ color: 'var(--text-mute)', lineHeight: 1.7 }}>管理员登记本地、已完成的 MP4 / poster / 文字稿。服务端会重新计算三个文件的 SHA-256；路径漂移、文件损坏或时长越界会直接阻止封存。</div>
          </div>
          <Space wrap>
            <Button icon={<ReloadOutlined />} disabled={!canPublish} onClick={() => setPresentation(createLessonPresentation(draft.course_id, draft.lesson_id, Math.max(0, ...lessonPresentations.map((item) => item.descriptor.version)) + 1))}>生成下一版本表单</Button>
            <Button type="primary" icon={<VideoCameraOutlined />} disabled={!canPublish} loading={busy === 'presentation'} onClick={stagePresentation}>校验并封存展示资源</Button>
          </Space>
        </div>
        <fieldset disabled={!canPublish || Boolean(busy)} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 210px), 1fr))', gap: 10 }}>
            <Input aria-label="展示资源 ID" value={presentation.presentation_id} placeholder="presentation-id" onChange={(event) => patchPresentation({ presentation_id: event.target.value })} />
            <Input aria-label="展示资源标题" value={presentation.title} placeholder="展示标题" onChange={(event) => patchPresentation({ title: event.target.value })} />
            <Input aria-label="展示资源课程 ID" value={presentation.course_id} disabled />
            <Input aria-label="展示资源课时 ID" value={presentation.lesson_id} disabled />
            <InputNumber aria-label="展示资源版本" min={1} value={presentation.presentation_version} style={{ width: '100%' }} onChange={(value) => value && setPresentation(createLessonPresentation(presentation.course_id, presentation.lesson_id, value))} />
            <InputNumber aria-label="短片时长" min={45} max={60} step={0.1} value={presentation.video_duration_seconds} addonAfter="秒" style={{ width: '100%' }} onChange={(value) => patchPresentation({ video_duration_seconds: value || 45 })} />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(120px, 1fr))', gap: 10, marginTop: 10, overflowX: 'auto' }}>
            {(['observe', 'decide', 'consult', 'dossier'] as const).map((phase) => (
              <label key={phase}>
                <div className="chrono-course-eyeline" style={{ marginBottom: 5 }}>{({ observe: '踏勘', decide: '抉择', consult: '召见', dossier: '卷宗' })[phase]}</div>
                <InputNumber aria-label={`阶段 ${phase}`} min={phase === 'decide' ? 12 : phase === 'consult' ? 5 : 8} max={phase === 'decide' ? 15 : phase === 'consult' ? 8 : 10} value={presentation.phase_minutes[phase]} addonAfter="分钟" style={{ width: '100%' }} onChange={(value) => patchPresentation({ phase_minutes: { ...presentation.phase_minutes, [phase]: value || 0 } })} />
              </label>
            ))}
          </div>
          <div style={{ display: 'grid', gap: 9, marginTop: 12 }}>
            {([
              ['video_path', 'video_sha256', 'MP4 路径', 'MP4 SHA-256'],
              ['poster_path', 'poster_sha256', 'Poster 路径', 'Poster SHA-256'],
              ['transcript_path', 'transcript_sha256', '文字稿路径', '文字稿 SHA-256'],
            ] as const).map(([pathField, hashField, pathLabel, hashLabel]) => (
              <div key={pathField} style={{ display: 'grid', gridTemplateColumns: 'minmax(240px, 1.5fr) minmax(260px, 1fr)', gap: 9 }}>
                <Input aria-label={pathLabel} value={presentation[pathField]} placeholder={pathLabel} onChange={(event) => patchPresentation({ [pathField]: event.target.value })} />
                <Input aria-label={hashLabel} value={presentation[hashField]} placeholder="64 位小写 SHA-256" onChange={(event) => patchPresentation({ [hashField]: event.target.value.trim().toLowerCase() })} />
              </div>
            ))}
          </div>
          <TextArea aria-label="展示无障碍说明" value={presentation.accessibility_note} autoSize={{ minRows: 2, maxRows: 5 }} style={{ marginTop: 10 }} onChange={(event) => patchPresentation({ accessibility_note: event.target.value })} />
          <Space size={[6, 6]} wrap style={{ marginTop: 10 }}>
            <Tag>1920 × 1080</Tag><Tag>30 fps</Tag><Tag>允许跳过</Tag>
            <Tag color="blue">四阶段合计 {Object.values(presentation.phase_minutes).reduce((sum, value) => sum + value, 0)} 分钟</Tag>
            <Tag color="cyan">契约 {checksumLabel(presentation.checksum)}</Tag>
          </Space>
        </fieldset>
      </section>
    </div>
  );
}
