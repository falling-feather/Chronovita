import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Collapse,
  Divider,
  Empty,
  Input,
  InputNumber,
  Popconfirm,
  Progress,
  Segmented,
  Select,
  Space,
  Switch,
  Tabs,
  Tag,
  Tooltip,
} from 'antd';
import {
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  FileAddOutlined,
  FlagOutlined,
  LockOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SaveOutlined,
  SlidersOutlined,
  TeamOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import {
  api,
  type LessonSourceRecord,
  type RuntimeScenarioRecord,
  type ScenarioAuthorDraft,
  type ScenarioDraftAction,
  type ScenarioDraftCondition,
  type ScenarioDraftEffect,
  type ScenarioDraftEnding,
  type ScenarioDraftEvent,
  type ScenarioDraftNpc,
  type ScenarioDraftRecord,
  type ScenarioDraftValidationReport,
  type ScenarioDraftVariable,
  type SealedScenarioTemplate,
} from '../../utils/api';
import { toast } from '../../utils/toast';
import {
  COMPARISON_OPTIONS,
  SCENARIO_TYPE_OPTIONS,
  conditionSummary,
  createAction,
  createCondition,
  createEffect,
  createEnding,
  createEvent,
  createNpc,
  createScenarioDraft,
  createVariable,
  effectSummary,
  linesToList,
  listToLines,
  nextStableId,
  safeFileBase,
  scenarioTypeLabel,
  validationIssueText,
} from './scenarioRuleModel';
import AssetPublicationPanel from './AssetPublicationPanel';

const { TextArea } = Input;
const LOCAL_SCENARIO_KEY = 'chrono.admin.content.scenario.v1';
const gridStyle = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))',
  gap: 12,
};

interface ScenarioRuleEditorProps {
  token: string;
  sourceLessons: LessonSourceRecord[];
  runtimeScenarios: RuntimeScenarioRecord[];
  onRefreshRuntimeScenarios: () => Promise<void>;
}

interface ConditionRowsProps {
  items: ScenarioDraftCondition[];
  variables: ScenarioDraftVariable[];
  npcs: ScenarioDraftNpc[];
  onChange: (items: ScenarioDraftCondition[]) => void;
}

interface EffectRowsProps {
  items: ScenarioDraftEffect[];
  variables: ScenarioDraftVariable[];
  npcs: ScenarioDraftNpc[];
  onChange: (items: ScenarioDraftEffect[]) => void;
}

export default function ScenarioRuleEditor({
  token,
  sourceLessons,
  runtimeScenarios,
  onRefreshRuntimeScenarios,
}: ScenarioRuleEditorProps) {
  const [draft, setDraft] = useState<ScenarioAuthorDraft>(() => readLocalDraft());
  const [drafts, setDrafts] = useState<ScenarioDraftRecord[]>([]);
  const [selectedDraft, setSelectedDraft] = useState<string>();
  const [report, setReport] = useState<ScenarioDraftValidationReport | null>(null);
  const [sealed, setSealed] = useState<SealedScenarioTemplate | null>(null);
  const [sealedRecord, setSealedRecord] = useState<RuntimeScenarioRecord | null>(null);
  const [dirty, setDirty] = useState(() => Boolean(localStorage.getItem(LOCAL_SCENARIO_KEY)));
  const [busy, setBusy] = useState('');
  const [localSavedAt, setLocalSavedAt] = useState('');
  const previewRef = useRef<HTMLDivElement | null>(null);
  const editGenerationRef = useRef(0);
  const draftRefreshSequenceRef = useRef(0);
  const currentTokenRef = useRef(token);
  currentTokenRef.current = token;

  const lessonScenarios = useMemo(
    () => runtimeScenarios.filter((item) => (
      item.descriptor.course_id === draft.course_id
      && item.descriptor.lesson_id === draft.lesson_id
    )),
    [draft.course_id, draft.lesson_id, runtimeScenarios],
  );
  const currentScenarioVersions = useMemo(
    () => lessonScenarios
      .filter((item) => item.descriptor.artifact_id === draft.scenario_id)
      .sort((left, right) => (
        right.descriptor.version - left.descriptor.version
        || right.descriptor.checksum.localeCompare(left.descriptor.checksum)
      )),
    [draft.scenario_id, lessonScenarios],
  );
  const latestScenarioRecord = currentScenarioVersions[0];
  const scenarioPublicationVersions = useMemo(
    () => currentScenarioVersions.map((item) => ({
      version: item.descriptor.version,
      checksum: item.descriptor.checksum,
      title: item.title,
      sealedAt: sealed?.scenario_version === item.descriptor.version
        && sealed.checksum === item.descriptor.checksum
        ? sealed.sealed_at
        : undefined,
      sealedBy: sealed?.scenario_version === item.descriptor.version
        && sealed.checksum === item.descriptor.checksum
        ? sealed.sealed_by
        : undefined,
    })),
    [currentScenarioVersions, sealed],
  );
  const scenarioIdError = contractIdError(draft.scenario_id);

  useEffect(() => {
    localStorage.setItem(LOCAL_SCENARIO_KEY, JSON.stringify(draft));
    setLocalSavedAt(new Date().toLocaleTimeString());
  }, [draft]);

  useEffect(() => {
    const sequence = ++draftRefreshSequenceRef.current;
    setDrafts([]);
    setSelectedDraft(undefined);
    if (!token) return;
    const timer = window.setTimeout(() => {
      void api.adminScenarioDrafts(token)
        .then((result) => {
          if (draftRefreshSequenceRef.current === sequence) setDrafts(result.items);
        })
        .catch(() => {
          // The parent editor reports authentication failures for the shared content refresh.
        });
    }, 350);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const updateDraft = (patch: Partial<ScenarioAuthorDraft>) => {
    editGenerationRef.current += 1;
    setDraft((current) => ({ ...current, ...patch }));
    setDirty(true);
    setReport(null);
    setSealed(null);
    setSealedRecord(null);
  };

  const confirmReplaceDraft = () => (
    !dirty || window.confirm('当前关卡还有未保存到服务器的修改。继续后会放弃这些修改，是否继续？')
  );

  const assertDraftUnchanged = (generation: number) => {
    if (editGenerationRef.current !== generation) {
      throw new Error('请求期间内容发生了修改，请重新保存后再继续');
    }
  };

  const assertTokenUnchanged = (requestToken: string) => {
    if (currentTokenRef.current !== requestToken) {
      throw new Error('Admin token 已变化，旧请求结果已忽略，请在当前身份下重新操作');
    }
  };

  const refreshDrafts = async (silent = false) => {
    if (!token) return;
    const requestToken = token;
    const sequence = draftRefreshSequenceRef.current;
    if (!silent) setBusy('refresh');
    try {
      const result = await api.adminScenarioDrafts(requestToken);
      if (
        currentTokenRef.current !== requestToken
        || draftRefreshSequenceRef.current !== sequence
      ) return;
      setDrafts(result.items);
    } catch (error: any) {
      if (!silent && draftRefreshSequenceRef.current === sequence) {
        toast.error(error?.message || '关卡草稿库读取失败');
      }
    } finally {
      if (!silent) setBusy('');
    }
  };

  const createNew = async () => {
    if (!confirmReplaceDraft()) return;
    const requestToken = token;
    setBusy('template');
    try {
      const template = requestToken
        ? await api.adminScenarioTemplate(requestToken)
        : createScenarioDraft();
      assertTokenUnchanged(requestToken);
      setDraft({
        ...template,
        scenario_id: `scenario-${Date.now().toString(36)}`,
        revision: 0,
        created_at: null,
        updated_at: null,
        created_by: null,
        updated_by: null,
      });
      setSelectedDraft(undefined);
      setReport(null);
      setSealed(null);
      setSealedRecord(null);
      setDirty(true);
      editGenerationRef.current += 1;
      toast.success('新关卡规则已创建');
    } catch (error: any) {
      toast.error(error?.message || '关卡模板载入失败');
    } finally {
      setBusy('');
    }
  };

  const loadSelectedDraft = async () => {
    if (!selectedDraft || !ensureToken(token)) return;
    if (!confirmReplaceDraft()) return;
    const requestToken = token;
    setBusy('load');
    try {
      const item = await api.adminScenarioDraft(requestToken, selectedDraft);
      assertTokenUnchanged(requestToken);
      setDraft(item);
      setReport(null);
      setSealed(null);
      setSealedRecord(null);
      setDirty(false);
      editGenerationRef.current += 1;
      toast.success('关卡草稿已打开');
    } catch (error: any) {
      toast.error(error?.message || '关卡草稿打开失败');
    } finally {
      setBusy('');
    }
  };

  const persistDraft = async () => {
    if (!ensureToken(token)) throw new Error('请先填写 Admin token');
    const requestToken = token;
    const idError = contractIdError(draft.scenario_id);
    if (idError) throw new Error(`关卡 ID：${idError}`);
    const generation = editGenerationRef.current;
    const result = await api.adminSaveScenarioDraft(requestToken, draft);
    assertTokenUnchanged(requestToken);
    if (editGenerationRef.current !== generation) {
      setDraft((current) => current.scenario_id === result.item.scenario_id ? ({
        ...current,
        revision: result.item.revision,
        created_at: result.item.created_at,
        updated_at: result.item.updated_at,
        created_by: result.item.created_by,
        updated_by: result.item.updated_by,
      }) : current);
      setSelectedDraft(result.item.scenario_id);
      setDirty(true);
      const library = await api.adminScenarioDrafts(requestToken);
      assertTokenUnchanged(requestToken);
      setDrafts(library.items);
      throw new Error('请求期间内容发生了修改，服务器已保留旧快照；请再次保存当前内容');
    }
    setDraft(result.item);
    setDirty(false);
    setSelectedDraft(result.item.scenario_id);
    const library = await api.adminScenarioDrafts(requestToken);
    assertTokenUnchanged(requestToken);
    setDrafts(library.items);
    return result.item;
  };

  const saveDraft = async () => {
    setBusy('save');
    try {
      await persistDraft();
      toast.success('关卡草稿已保存到服务器');
    } catch (error: any) {
      toast.error(error?.message || '关卡草稿保存失败');
    } finally {
      setBusy('');
    }
  };

  const validateDraft = async () => {
    setBusy('validate');
    try {
      const saved = await persistDraft();
      const requestToken = token;
      const generation = editGenerationRef.current;
      const result = await api.adminValidateScenarioDraft(requestToken, saved.scenario_id);
      assertTokenUnchanged(requestToken);
      assertDraftUnchanged(generation);
      setReport(result.report);
      if (result.report.valid) toast.success('关卡规则校验通过');
      else toast.warning('仍有阻断项，请按校验结果调整');
    } catch (error: any) {
      toast.error(error?.message || '关卡规则校验失败');
    } finally {
      setBusy('');
    }
  };

  const sealDraft = async () => {
    setBusy('seal');
    try {
      const saved = await persistDraft();
      const requestToken = token;
      const generation = editGenerationRef.current;
      const validation = await api.adminValidateScenarioDraft(requestToken, saved.scenario_id);
      assertTokenUnchanged(requestToken);
      assertDraftUnchanged(generation);
      setReport(validation.report);
      if (!validation.report.valid) {
        toast.warning('请先处理阻断项，再封存关卡');
        return;
      }
      const result = await api.adminSealScenarioDraft(requestToken, saved.scenario_id);
      assertTokenUnchanged(requestToken);
      assertDraftUnchanged(generation);
      setSealed(result.item);
      setSealedRecord(result.record);
      await onRefreshRuntimeScenarios();
      assertTokenUnchanged(requestToken);
      toast.success(
        result.idempotent
          ? `内容未变化，继续使用封存版本 v${result.item.scenario_version}`
          : `关卡已封存为 v${result.item.scenario_version}`,
      );
    } catch (error: any) {
      toast.error(error?.message || '关卡封存失败');
    } finally {
      setBusy('');
    }
  };

  const applySourceLesson = (lessonId: string) => {
    const source = sourceLessons.find((item) => item.lesson_id === lessonId);
    if (!source) return;
    updateDraft({
      course_id: source.course_id,
      lesson_id: source.lesson_id,
      title: draft.title === '历史抉择局' ? `${source.title}·历史抉择局` : draft.title,
    });
  };

  const exportDraft = () => {
    downloadJson(
      `${safeFileBase(draft.title, draft.scenario_id)}-关卡草稿.json`,
      draft,
    );
    toast.success('关卡草稿已导出');
  };

  const exportSealed = async () => {
    const record = sealedRecord || latestScenarioRecord;
    if (!ensureToken(token) || !record) return;
    const requestToken = token;
    setBusy('export-sealed');
    try {
      const blob = await api.adminRuntimeScenarioFile(requestToken, record.descriptor);
      assertTokenUnchanged(requestToken);
      downloadBlob(
        `${safeFileBase(record.title, record.descriptor.artifact_id)}-关卡封存-v${String(record.descriptor.version).padStart(3, '0')}.json`,
        blob,
      );
      toast.success('1:1 封存文件已导出');
    } catch (error: any) {
      toast.error(error?.message || '封存文件读取失败');
    } finally {
      setBusy('');
    }
  };

  const focusPreview = () => previewRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });

  const basicTab = (
    <div style={{ display: 'grid', gap: 14 }}>
      <label>
        <FieldLabel>从课程清单带入</FieldLabel>
        <Select
          aria-label="选择关联课时"
          showSearch
          allowClear
          optionFilterProp="label"
          placeholder="选择已经整理好的课程与课时"
          style={{ width: '100%' }}
          onChange={applySourceLesson}
          options={sourceLessons.map((item) => ({
            value: item.lesson_id,
            label: `${item.course_title || item.course_id} / ${item.title} · ${item.lesson_id}`,
          }))}
        />
      </label>
      <div style={gridStyle}>
        <label>
          <FieldLabel>关卡 ID</FieldLabel>
          <Input
            aria-label="关卡 ID"
            status={scenarioIdError ? 'error' : undefined}
            value={draft.scenario_id}
            onChange={(event) => updateDraft({ scenario_id: event.target.value })}
          />
          {scenarioIdError && <div style={{ color: '#cf1322', fontSize: 12, marginTop: 4 }}>{scenarioIdError}</div>}
        </label>
        <LabeledInput label="课程 ID" ariaLabel="关卡课程 ID" value={draft.course_id} onChange={(course_id) => updateDraft({ course_id })} />
        <LabeledInput label="课时 ID" ariaLabel="关卡课时 ID" value={draft.lesson_id} onChange={(lesson_id) => updateDraft({ lesson_id })} />
        <LabeledInput label="关卡标题" ariaLabel="关卡标题" value={draft.title} onChange={(title) => updateDraft({ title })} />
        <label>
          <FieldLabel>关卡类型</FieldLabel>
          <Select aria-label="关卡类型" value={draft.scenario_type} style={{ width: '100%' }} options={SCENARIO_TYPE_OPTIONS} onChange={(scenario_type) => updateDraft({ scenario_type })} />
        </label>
        <label>
          <FieldLabel>最大回合</FieldLabel>
          <InputNumber aria-label="最大回合" min={1} max={50} value={draft.max_turns} style={{ width: '100%' }} onChange={(value) => updateDraft({ max_turns: Number(value || 1) })} />
        </label>
      </div>
      <LabeledInput label="学生身份" ariaLabel="学生身份" value={draft.student_role} onChange={(student_role) => updateDraft({ student_role })} />
      <LabeledTextArea label="关卡目标" ariaLabel="关卡目标" value={draft.objective} onChange={(objective) => updateDraft({ objective })} minRows={3} />
      <LabeledTextArea label="开场局势" ariaLabel="开场局势" value={draft.opening} onChange={(opening) => updateDraft({ opening })} minRows={5} />
    </div>
  );

  const variablesTab = (
    <div>
      <SectionHeading icon={<SlidersOutlined />} title="局势指标" action={(
        <Button icon={<PlusOutlined />} onClick={() => updateDraft({
          variables: [...draft.variables, createVariable(
            nextStableId('variable', draft.variables.map((item) => item.variable_id)),
          )],
        })}>添加指标</Button>
      )} />
      {draft.variables.length ? draft.variables.map((item, index) => (
        <RuleBlock key={`${item.variable_id}-${index}`} title={item.label || `指标 ${index + 1}`} onRemove={() => updateDraft({ variables: removeAt(draft.variables, index) })}>
          <div style={gridStyle}>
            <LabeledInput label="指标 ID" ariaLabel={`指标 ${index + 1} ID`} value={item.variable_id} onChange={(variable_id) => updateVariable(index, { variable_id })} />
            <LabeledInput label="显示名称" ariaLabel={`指标 ${index + 1} 名称`} value={item.label} onChange={(label) => updateVariable(index, { label })} />
            <NumberInput label="初始值" ariaLabel={`指标 ${index + 1} 初始值`} value={item.initial} onChange={(initial) => updateVariable(index, { initial })} />
            <NumberInput label="最小值" ariaLabel={`指标 ${index + 1} 最小值`} value={item.minimum} onChange={(minimum) => updateVariable(index, { minimum })} />
            <NumberInput label="最大值" ariaLabel={`指标 ${index + 1} 最大值`} value={item.maximum} onChange={(maximum) => updateVariable(index, { maximum })} />
          </div>
          <LabeledTextArea label="指标说明" ariaLabel={`指标 ${index + 1} 说明`} value={item.description} onChange={(description) => updateVariable(index, { description })} minRows={2} />
        </RuleBlock>
      )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="至少添加一个局势指标" />}

      <Divider />
      <SectionHeading icon={<TeamOutlined />} title="关卡人物" action={(
        <Button icon={<PlusOutlined />} onClick={() => updateDraft({
          npcs: [...draft.npcs, createNpc(nextStableId('person', draft.npcs.map((item) => item.person_id)))],
        })}>添加人物</Button>
      )} />
      {draft.npcs.length ? draft.npcs.map((item, index) => (
        <RuleBlock key={`${item.person_id}-${index}`} title={item.display_name || `人物 ${index + 1}`} onRemove={() => updateDraft({ npcs: removeAt(draft.npcs, index) })}>
          <div style={gridStyle}>
            <LabeledInput label="人物 ID" ariaLabel={`关卡人物 ${index + 1} ID`} value={item.person_id} onChange={(person_id) => updateNpc(index, { person_id })} />
            <LabeledInput label="显示姓名" ariaLabel={`关卡人物 ${index + 1} 姓名`} value={item.display_name} onChange={(display_name) => updateNpc(index, { display_name })} />
            <LabeledInput label="身份/立场" ariaLabel={`关卡人物 ${index + 1} 身份`} value={item.role} onChange={(role) => updateNpc(index, { role })} />
            <NumberInput label="初始态度" ariaLabel={`关卡人物 ${index + 1} 态度`} min={-100} max={100} value={item.initial_attitude} onChange={(initial_attitude) => updateNpc(index, { initial_attitude })} />
            <NumberInput label="初始信任" ariaLabel={`关卡人物 ${index + 1} 信任`} min={-100} max={100} value={item.initial_trust} onChange={(initial_trust) => updateNpc(index, { initial_trust })} />
          </div>
          <LabeledTextArea label="人物 persona" ariaLabel={`关卡人物 ${index + 1} persona`} value={item.persona} onChange={(persona) => updateNpc(index, { persona })} minRows={3} />
          <LabeledTextArea label="史实边界（每行一条）" ariaLabel={`关卡人物 ${index + 1} 史实边界`} value={listToLines(item.boundaries)} onChange={(value) => updateNpc(index, { boundaries: linesToList(value) })} minRows={2} />
        </RuleBlock>
      )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本关卡暂不使用人物状态" />}
    </div>
  );

  const actionsTab = (
    <div>
      <SectionHeading icon={<ThunderboltOutlined />} title="学生行动" action={(
        <Button icon={<PlusOutlined />} onClick={() => updateDraft({
          action_rules: [...draft.action_rules, createAction(
            nextStableId('action', draft.action_rules.map((item) => item.action_id)),
            '新行动',
            draft.variables[0]?.variable_id,
          )],
        })}>添加行动</Button>
      )} />
      {draft.action_rules.length ? draft.action_rules.map((item, index) => (
        <RuleBlock key={`${item.action_id}-${index}`} title={item.label || `行动 ${index + 1}`} onRemove={() => updateDraft({ action_rules: removeAt(draft.action_rules, index) })}>
          <div style={gridStyle}>
            <LabeledInput label="行动 ID" ariaLabel={`行动 ${index + 1} ID`} value={item.action_id} onChange={(action_id) => updateAction(index, { action_id })} />
            <LabeledInput label="按钮文字" ariaLabel={`行动 ${index + 1} 按钮文字`} value={item.label} onChange={(label) => updateAction(index, { label })} />
          </div>
          <LabeledTextArea label="行动说明" ariaLabel={`行动 ${index + 1} 说明`} value={item.description} onChange={(description) => updateAction(index, { description })} minRows={2} />
          <LabeledTextArea label="行动反馈" ariaLabel={`行动 ${index + 1} 反馈`} value={item.feedback} onChange={(feedback) => updateAction(index, { feedback })} minRows={2} />
          <MiniHeading title="可用条件" />
          <ConditionRows items={item.available_when} variables={draft.variables} npcs={draft.npcs} onChange={(available_when) => updateAction(index, { available_when })} />
          <MiniHeading title="执行效果" />
          <EffectRows items={item.effects} variables={draft.variables} npcs={draft.npcs} onChange={(effects) => updateAction(index, { effects })} />
          <div style={gridStyle}>
            <LabeledTextArea label="别名（每行一条）" ariaLabel={`行动 ${index + 1} 别名`} value={listToLines(item.aliases)} onChange={(value) => updateAction(index, { aliases: linesToList(value) })} minRows={2} />
            <LabeledTextArea label="史实引用 ID（每行一条）" ariaLabel={`行动 ${index + 1} 史实引用`} value={listToLines(item.fact_refs)} onChange={(value) => updateAction(index, { fact_refs: linesToList(value) })} minRows={2} />
          </div>
        </RuleBlock>
      )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="至少添加一个学生行动" />}
    </div>
  );

  const eventsTab = (
    <div>
      <SectionHeading icon={<ThunderboltOutlined />} title="自动事件" action={(
        <Button icon={<PlusOutlined />} onClick={() => updateDraft({
          event_rules: [...draft.event_rules, createEvent(
            nextStableId('event', draft.event_rules.map((item) => item.event_id)),
            draft.variables[0]?.variable_id,
          )],
        })}>添加事件</Button>
      )} />
      {draft.event_rules.length ? draft.event_rules.map((item, index) => (
        <RuleBlock key={`${item.event_id}-${index}`} title={item.title || `事件 ${index + 1}`} onRemove={() => updateDraft({ event_rules: removeAt(draft.event_rules, index) })}>
          <div style={gridStyle}>
            <LabeledInput label="事件 ID" ariaLabel={`事件 ${index + 1} ID`} value={item.event_id} onChange={(event_id) => updateEvent(index, { event_id })} />
            <LabeledInput label="事件标题" ariaLabel={`事件 ${index + 1} 标题`} value={item.title} onChange={(title) => updateEvent(index, { title })} />
            <label><FieldLabel>触发方式</FieldLabel><Segmented block value={item.match} options={[{ label: '全部满足', value: 'all' }, { label: '任一满足', value: 'any' }]} onChange={(match) => updateEvent(index, { match: match as 'all' | 'any' })} /></label>
            <NumberInput label="优先级" ariaLabel={`事件 ${index + 1} 优先级`} value={item.priority} onChange={(priority) => updateEvent(index, { priority })} />
            <label><FieldLabel>只触发一次</FieldLabel><Switch aria-label={`事件 ${index + 1} 只触发一次`} checked={item.once} onChange={(once) => updateEvent(index, { once })} /></label>
          </div>
          <LabeledTextArea label="事件叙述" ariaLabel={`事件 ${index + 1} 叙述`} value={item.narrative} onChange={(narrative) => updateEvent(index, { narrative })} minRows={3} />
          <MiniHeading title="触发条件" />
          <ConditionRows items={item.trigger} variables={draft.variables} npcs={draft.npcs} onChange={(trigger) => updateEvent(index, { trigger })} />
          <MiniHeading title="事件效果" />
          <EffectRows items={item.effects} variables={draft.variables} npcs={draft.npcs} onChange={(effects) => updateEvent(index, { effects })} />
        </RuleBlock>
      )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有自动事件时可以留空" />}
    </div>
  );

  const endingsTab = (
    <div>
      <SectionHeading icon={<FlagOutlined />} title="结局与判定" action={(
        <Button icon={<PlusOutlined />} onClick={() => updateDraft({
          ending_rules: [...draft.ending_rules, createEnding(
            nextStableId('ending', draft.ending_rules.map((item) => item.ending_id)),
            '新结局',
            draft.variables[0]?.variable_id,
          )],
        })}>添加结局</Button>
      )} />
      {draft.ending_rules.length ? draft.ending_rules.map((item, index) => (
        <RuleBlock key={`${item.ending_id}-${index}`} title={item.title || `结局 ${index + 1}`} onRemove={() => updateDraft({ ending_rules: removeAt(draft.ending_rules, index) })}>
          <div style={gridStyle}>
            <LabeledInput label="结局 ID" ariaLabel={`结局 ${index + 1} ID`} value={item.ending_id} onChange={(ending_id) => updateEnding(index, { ending_id })} />
            <LabeledInput label="结局标题" ariaLabel={`结局 ${index + 1} 标题`} value={item.title} onChange={(title) => updateEnding(index, { title })} />
            <label><FieldLabel>判定方式</FieldLabel><Segmented block value={item.match} options={[{ label: '全部满足', value: 'all' }, { label: '任一满足', value: 'any' }]} onChange={(match) => updateEnding(index, { match: match as 'all' | 'any' })} /></label>
            <NumberInput label="优先级" ariaLabel={`结局 ${index + 1} 优先级`} value={item.priority} onChange={(priority) => updateEnding(index, { priority })} />
          </div>
          <MiniHeading title="达成条件" />
          <ConditionRows items={item.conditions} variables={draft.variables} npcs={draft.npcs} onChange={(conditions) => updateEnding(index, { conditions })} />
          <LabeledTextArea label="学生看到的结局摘要" ariaLabel={`结局 ${index + 1} 摘要`} value={item.summary} onChange={(summary) => updateEnding(index, { summary })} minRows={3} />
          <LabeledTextArea label="历史解释" ariaLabel={`结局 ${index + 1} 历史解释`} value={item.historical_explanation} onChange={(historical_explanation) => updateEnding(index, { historical_explanation })} minRows={3} />
          <div style={gridStyle}>
            <LabeledTextArea label="主要代价（每行一条）" ariaLabel={`结局 ${index + 1} 主要代价`} value={listToLines(item.major_costs)} onChange={(value) => updateEnding(index, { major_costs: linesToList(value) })} minRows={2} />
            <LabeledTextArea label="参考资料 ID（每行一条）" ariaLabel={`结局 ${index + 1} 参考资料`} value={listToLines(item.source_ref_ids)} onChange={(value) => updateEnding(index, { source_ref_ids: linesToList(value) })} minRows={2} />
          </div>
        </RuleBlock>
      )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="至少添加一个结局" />}
    </div>
  );

  const dossierTab = (
    <div style={{ display: 'grid', gap: 14 }}>
      <LabeledInput label="卷宗标题格式" ariaLabel="卷宗标题格式" value={draft.dossier_template.title_template} onChange={(title_template) => updateDraft({ dossier_template: { ...draft.dossier_template, title_template } })} />
      <div style={gridStyle}>
        <LabeledTextArea label="课时史实 ID（每行一条）" ariaLabel="关卡史实引用" value={listToLines(draft.fact_refs)} onChange={(value) => updateDraft({ fact_refs: linesToList(value) })} minRows={5} />
        <LabeledTextArea label="课时资料 ID（每行一条）" ariaLabel="关卡资料引用" value={listToLines(draft.source_ref_ids)} onChange={(value) => updateDraft({ source_ref_ids: linesToList(value) })} minRows={5} />
        <LabeledTextArea label="复盘问题（每行一条）" ariaLabel="关卡复盘问题" value={listToLines(draft.dossier_template.reflection_questions)} onChange={(value) => updateDraft({ dossier_template: { ...draft.dossier_template, reflection_questions: linesToList(value) } })} minRows={5} />
        <LabeledTextArea label="知识节点类型（每行一条）" ariaLabel="关卡知识节点类型" value={listToLines(draft.dossier_template.knowledge_node_kinds)} onChange={(value) => updateDraft({ dossier_template: { ...draft.dossier_template, knowledge_node_kinds: linesToList(value) } })} minRows={5} />
      </div>
      {draft.nodes.length > 0 && (
        <Alert type="info" showIcon message={`该草稿包含 ${draft.nodes.length} 个高级流程节点；当前表单会原样保留节点，不会重写其拓扑。`} />
      )}
    </div>
  );

  const updateVariable = (index: number, patch: Partial<ScenarioDraftVariable>) => updateDraft({ variables: replaceAt(draft.variables, index, { ...draft.variables[index], ...patch }) });
  const updateNpc = (index: number, patch: Partial<ScenarioDraftNpc>) => updateDraft({ npcs: replaceAt(draft.npcs, index, { ...draft.npcs[index], ...patch }) });
  const updateAction = (index: number, patch: Partial<ScenarioDraftAction>) => updateDraft({ action_rules: replaceAt(draft.action_rules, index, { ...draft.action_rules[index], ...patch }) });
  const updateEvent = (index: number, patch: Partial<ScenarioDraftEvent>) => updateDraft({ event_rules: replaceAt(draft.event_rules, index, { ...draft.event_rules[index], ...patch }) });
  const updateEnding = (index: number, patch: Partial<ScenarioDraftEnding>) => updateDraft({ ending_rules: replaceAt(draft.ending_rules, index, { ...draft.ending_rules[index], ...patch }) });

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 520px), 1fr))', gap: 16, alignItems: 'start' }}>
      <section className="chrono-card" style={{ padding: 16, minWidth: 0 }}>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div>
            <div className="chrono-course-eyeline">Scenario authoring</div>
            <h2 style={{ margin: '3px 0 0', fontSize: 20, letterSpacing: 0 }}>关卡规则</h2>
          </div>
          <Space size={[6, 6]} wrap>
            <Button disabled={Boolean(busy)} icon={<FileAddOutlined />} loading={busy === 'template'} onClick={createNew}>新建</Button>
            <Button disabled={Boolean(busy) || Boolean(scenarioIdError)} type="primary" icon={<SaveOutlined />} loading={busy === 'save'} onClick={saveDraft}>保存</Button>
            <Button disabled={Boolean(busy) || Boolean(scenarioIdError)} icon={<SafetyCertificateOutlined />} loading={busy === 'validate'} onClick={validateDraft}>校验</Button>
            <Button disabled={Boolean(busy) || Boolean(scenarioIdError)} icon={<LockOutlined />} loading={busy === 'seal'} onClick={sealDraft}>封存</Button>
            <Button disabled={Boolean(busy)} icon={<EyeOutlined />} onClick={focusPreview}>预览</Button>
          </Space>
        </div>

        <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
          <Select
            aria-label="关卡草稿库"
            placeholder="服务器关卡草稿库"
            showSearch
            optionFilterProp="label"
            value={selectedDraft}
            onChange={setSelectedDraft}
            disabled={Boolean(busy)}
            style={{ flex: '1 1 280px', minWidth: 0 }}
            options={drafts.map((item) => ({
              value: item.scenario_id,
              label: `${item.title || item.scenario_id} · r${item.revision}`,
            }))}
          />
          <Button disabled={Boolean(busy) || !selectedDraft} loading={busy === 'load'} onClick={loadSelectedDraft}>打开</Button>
          <Tooltip title="刷新草稿库"><Button disabled={Boolean(busy)} aria-label="刷新关卡草稿库" icon={<ReloadOutlined />} loading={busy === 'refresh'} onClick={() => refreshDrafts()} /></Tooltip>
        </div>

        <Space size={[6, 6]} wrap style={{ marginTop: 12 }}>
          <Tag color="blue">{draft.scenario_id}</Tag>
          <Tag>本地暂存 {localSavedAt}</Tag>
          {dirty && <Tag color="gold">尚未保存到服务器</Tag>}
          {draft.revision > 0 && <Tag color="green">服务器 r{draft.revision}</Tag>}
          {draft.updated_at && <Tag>{new Date(draft.updated_at).toLocaleString()}</Tag>}
          {sealed && <Tag color="green">已封存 v{sealed.scenario_version}</Tag>}
        </Space>

        {report && (
          <div style={{ marginTop: 12 }}>
            {report.valid ? (
              <Alert type="success" showIcon message="规则校验通过，可以封存" />
            ) : (
              <Alert
                type="error"
                showIcon
                message={`还有 ${report.issues.length} 个阻断项`}
                description={(
                  <div style={{ display: 'grid', gap: 5 }}>
                    {report.issues.map((issue, index) => (
                      <div key={`${issue.path}-${issue.code}-${index}`}>
                        <code>{issue.path}</code>：{validationIssueText(issue)}
                      </div>
                    ))}
                  </div>
                )}
              />
            )}
          </div>
        )}

        <fieldset disabled={Boolean(busy)} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
          <div aria-busy={Boolean(busy)} style={{ pointerEvents: busy ? 'none' : undefined }}>
            <Divider style={{ margin: '16px 0 6px' }} />
            <Tabs
              items={[
                { key: 'basic', label: '基础', children: basicTab },
                { key: 'state', label: '指标与人物', children: variablesTab },
                { key: 'actions', label: '行动', children: actionsTab },
                { key: 'events', label: '事件', children: eventsTab },
                { key: 'endings', label: '结局', children: endingsTab },
                { key: 'dossier', label: '卷宗', children: dossierTab },
              ]}
            />

            <Collapse
              size="small"
              style={{ marginTop: 16 }}
              items={[{
                key: 'guide',
                label: '字段说明',
                children: (
                  <div style={{ lineHeight: 1.75, color: 'var(--text-mute)' }}>
                    <p><strong>ID</strong>：使用英文、数字、点、下划线或短横线，至少 2 位；封存后不要把同一关卡 ID 移到其他课程或课时。</p>
                    <p><strong>局势指标</strong>：学生行动会改变的数值；初始值必须位于最小值和最大值之间。</p>
                    <p><strong>行动与事件</strong>：行动由学生主动选择，事件在条件满足时自动触发；效果可改变指标或人物态度与信任。</p>
                    <p><strong>结局</strong>：至少准备一个可达结局，并建议用“回合数达到上限”作为课堂复盘兜底。</p>
                    <p><strong>史实与资料 ID</strong>：填写课程内容包中已经登记的 facts/source refs ID；联合发布时后端会再次核对。</p>
                  </div>
                ),
              }]}
            />
          </div>
        </fieldset>
      </section>

      <aside ref={previewRef} className="chrono-card" style={{ padding: 16, minWidth: 0, scrollMarginTop: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div>
            <div className="chrono-course-eyeline">规则效果预览</div>
            <h2 style={{ margin: '3px 0 0', fontSize: 20, letterSpacing: 0 }}>{draft.title || '未命名关卡'}</h2>
          </div>
          <Space size={[6, 6]} wrap>
            <Button disabled={Boolean(busy)} icon={<DownloadOutlined />} onClick={exportDraft}>导出草稿</Button>
            <Button
              icon={<DownloadOutlined />}
              disabled={Boolean(busy) || (!sealedRecord && !latestScenarioRecord)}
              loading={busy === 'export-sealed'}
              onClick={exportSealed}
            >
              导出封存件
            </Button>
          </Space>
        </div>
        <Space size={[6, 6]} wrap style={{ marginTop: 12 }}>
          <Tag color="blue">{scenarioTypeLabel(draft.scenario_type)}</Tag>
          <Tag>{draft.student_role || '未填写学生身份'}</Tag>
          <Tag>{draft.max_turns} 回合</Tag>
        </Space>
        <div style={{ marginTop: 16, padding: '12px 0', borderTop: '1px solid var(--border-soft)', borderBottom: '1px solid var(--border-soft)', lineHeight: 1.75 }}>
          <strong>进入情境</strong>
          <div style={{ marginTop: 5, color: 'var(--text-mute)', whiteSpace: 'pre-wrap' }}>{draft.opening || '尚未填写开场局势。'}</div>
          <div style={{ marginTop: 10 }}><strong>目标</strong>：{draft.objective || '尚未填写关卡目标。'}</div>
        </div>

        <PreviewHeading title="局势指标" count={draft.variables.length} />
        {draft.variables.length ? draft.variables.map((item) => (
          <div key={item.variable_id} style={{ marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
              <strong>{item.label || item.variable_id}</strong>
              <span style={{ color: 'var(--text-mute)', fontSize: 12 }}>{item.initial} / {item.maximum}</span>
            </div>
            <Progress percent={variablePercent(item)} showInfo={false} strokeColor="#1677ff" />
            {item.description && <div style={{ color: 'var(--text-mute)', fontSize: 12 }}>{item.description}</div>}
          </div>
        )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无指标" />}

        <PreviewHeading title="可选行动" count={draft.action_rules.length} />
        {draft.action_rules.length ? draft.action_rules.map((item) => (
          <div key={item.action_id} style={{ padding: '10px 0', borderBottom: '1px solid var(--border-soft)' }}>
            <strong>{item.label || item.action_id}</strong>
            {item.description && <div style={{ color: 'var(--text-mute)', marginTop: 3 }}>{item.description}</div>}
            <Space size={[5, 5]} wrap style={{ marginTop: 7 }}>
              {item.effects.map((effect, index) => <Tag key={`${item.action_id}-effect-${index}`} color="cyan">{effectSummary(effect, draft.variables, draft.npcs)}</Tag>)}
              {!item.effects.length && <Tag>仅叙事</Tag>}
            </Space>
          </div>
        )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无行动" />}

        <PreviewHeading title="结局判定" count={draft.ending_rules.length} />
        {draft.ending_rules.length ? draft.ending_rules.map((item) => (
          <div key={item.ending_id} style={{ padding: '10px 0', borderBottom: '1px solid var(--border-soft)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
              <strong>{item.title || item.ending_id}</strong>
              <Tag>{item.match === 'all' ? '全部满足' : '任一满足'}</Tag>
            </div>
            <div style={{ color: 'var(--text-mute)', marginTop: 4 }}>{item.summary || '尚未填写结局摘要。'}</div>
            <Space size={[5, 5]} wrap style={{ marginTop: 7 }}>
              {item.conditions.map((condition, index) => <Tag key={`${item.ending_id}-condition-${index}`} color="gold">{conditionSummary(condition, draft.variables, draft.npcs)}</Tag>)}
            </Space>
          </div>
        )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无结局" />}

        <PreviewHeading title="服务器封存版本" count={lessonScenarios.length} />
        {lessonScenarios.length ? lessonScenarios.map((item) => (
          <div key={`${item.descriptor.artifact_id}-${item.descriptor.version}-${item.descriptor.checksum}`} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--border-soft)' }}>
            <div><strong>{item.title}</strong><div style={{ color: 'var(--text-mute)', fontSize: 12 }}>{item.descriptor.artifact_id}</div></div>
            <Tag color="green">v{item.descriptor.version}</Tag>
          </div>
        )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="封存后会出现在这里；发布前学生不可见" />}
        <AssetPublicationPanel
          token={token}
          assetKind="scenario"
          assetId={draft.scenario_id.trim()}
          assetTitle={draft.title.trim()}
          versions={scenarioPublicationVersions}
        />
      </aside>
    </div>
  );
}

function ConditionRows({ items, variables, npcs, onChange }: ConditionRowsProps) {
  const addCondition = () => onChange([...items, createCondition('state', variables[0]?.variable_id || '')]);
  return (
    <div style={{ display: 'grid', gap: 8, marginBottom: 12 }}>
      {items.map((item, index) => (
        <div key={index} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 120px), 1fr))', gap: 8, alignItems: 'center' }}>
          <Select aria-label={`条件 ${index + 1} 类型`} value={item.kind} options={[{ value: 'state', label: '局势指标' }, { value: 'npc', label: '人物状态' }, { value: 'turn', label: '回合数' }]} onChange={(kind) => onChange(replaceAt(items, index, createCondition(kind, kind === 'npc' ? npcs[0]?.person_id || '' : variables[0]?.variable_id || '')))} />
          {item.kind === 'state' && <Select aria-label={`条件 ${index + 1} 指标`} value={item.variable_id || undefined} placeholder="选择指标" options={variables.map((variable) => ({ value: variable.variable_id, label: variable.label || variable.variable_id }))} onChange={(variable_id) => onChange(replaceAt(items, index, { ...item, variable_id }))} />}
          {item.kind === 'npc' && <Select aria-label={`条件 ${index + 1} 人物`} value={item.person_id || undefined} placeholder="选择人物" options={npcs.map((npc) => ({ value: npc.person_id, label: npc.display_name || npc.person_id }))} onChange={(person_id) => onChange(replaceAt(items, index, { ...item, person_id }))} />}
          {item.kind === 'npc' && <Select aria-label={`条件 ${index + 1} 人物字段`} value={item.field} options={[{ value: 'attitude', label: '态度' }, { value: 'trust', label: '信任' }]} onChange={(field) => onChange(replaceAt(items, index, { ...item, field }))} />}
          {item.kind === 'turn' && <div style={{ color: 'var(--text-mute)', paddingLeft: 8 }}>当前回合</div>}
          <Select aria-label={`条件 ${index + 1} 比较方式`} value={item.operator} options={[...COMPARISON_OPTIONS]} onChange={(operator) => onChange(replaceAt(items, index, { ...item, operator }))} />
          <InputNumber aria-label={`条件 ${index + 1} 数值`} value={item.value} style={{ width: '100%' }} onChange={(value) => onChange(replaceAt(items, index, { ...item, value: Number(value || 0) }))} />
          <Tooltip title="删除条件"><Button aria-label={`删除条件 ${index + 1}`} type="text" danger icon={<DeleteOutlined />} onClick={() => onChange(removeAt(items, index))} /></Tooltip>
        </div>
      ))}
      <Button type="dashed" icon={<PlusOutlined />} onClick={addCondition}>添加条件</Button>
    </div>
  );
}

function EffectRows({ items, variables, npcs, onChange }: EffectRowsProps) {
  const addEffect = () => onChange([...items, createEffect('state', variables[0]?.variable_id || '')]);
  return (
    <div style={{ display: 'grid', gap: 8, marginBottom: 12 }}>
      {items.map((item, index) => (
        <div key={index} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 120px), 1fr))', gap: 8, alignItems: 'center' }}>
          <Select aria-label={`效果 ${index + 1} 类型`} value={item.kind} options={[{ value: 'state', label: '改变指标' }, { value: 'npc', label: '改变人物' }]} onChange={(kind) => onChange(replaceAt(items, index, createEffect(kind, kind === 'npc' ? npcs[0]?.person_id || '' : variables[0]?.variable_id || '')))} />
          {item.kind === 'state' ? (
            <Select aria-label={`效果 ${index + 1} 指标`} value={item.variable_id || undefined} placeholder="选择指标" options={variables.map((variable) => ({ value: variable.variable_id, label: variable.label || variable.variable_id }))} onChange={(variable_id) => onChange(replaceAt(items, index, { ...item, variable_id }))} />
          ) : (
            <Select aria-label={`效果 ${index + 1} 人物`} value={item.person_id || undefined} placeholder="选择人物" options={npcs.map((npc) => ({ value: npc.person_id, label: npc.display_name || npc.person_id }))} onChange={(person_id) => onChange(replaceAt(items, index, { ...item, person_id }))} />
          )}
          {item.kind === 'state' ? (
            <Select aria-label={`效果 ${index + 1} 运算`} value={item.operation} options={[{ value: 'add', label: '增加/减少' }, { value: 'set', label: '直接设为' }]} onChange={(operation) => onChange(replaceAt(items, index, { ...item, operation }))} />
          ) : (
            <InputNumber aria-label={`效果 ${index + 1} 态度变化`} addonBefore="态度" value={item.attitude_delta} style={{ width: '100%' }} onChange={(attitude_delta) => onChange(replaceAt(items, index, { ...item, attitude_delta: Number(attitude_delta || 0) }))} />
          )}
          {item.kind === 'state' ? (
            <InputNumber aria-label={`效果 ${index + 1} 数值`} value={item.value} style={{ width: '100%' }} onChange={(value) => onChange(replaceAt(items, index, { ...item, value: Number(value || 0) }))} />
          ) : (
            <InputNumber aria-label={`效果 ${index + 1} 信任变化`} addonBefore="信任" value={item.trust_delta} style={{ width: '100%' }} onChange={(trust_delta) => onChange(replaceAt(items, index, { ...item, trust_delta: Number(trust_delta || 0) }))} />
          )}
          <Tooltip title="删除效果"><Button aria-label={`删除效果 ${index + 1}`} type="text" danger icon={<DeleteOutlined />} onClick={() => onChange(removeAt(items, index))} /></Tooltip>
        </div>
      ))}
      <Button type="dashed" icon={<PlusOutlined />} onClick={addEffect}>添加效果</Button>
    </div>
  );
}

function RuleBlock({ title, onRemove, children }: { title: string; onRemove: () => void; children: React.ReactNode }) {
  return (
    <div style={{ padding: '14px 0', borderBottom: '1px solid var(--border-soft)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', marginBottom: 12 }}>
        <strong>{title}</strong>
        <Popconfirm title="删除这一项？" okText="删除" cancelText="取消" onConfirm={onRemove}>
          <Tooltip title="删除"><Button aria-label={`删除 ${title}`} type="text" danger icon={<DeleteOutlined />} /></Tooltip>
        </Popconfirm>
      </div>
      <div style={{ display: 'grid', gap: 10 }}>{children}</div>
    </div>
  );
}

function SectionHeading({ icon, title, action }: { icon: React.ReactNode; title: string; action: React.ReactNode }) {
  return <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 8 }}><div style={{ display: 'flex', gap: 7, alignItems: 'center' }}>{icon}<strong>{title}</strong></div>{action}</div>;
}

function MiniHeading({ title }: { title: string }) {
  return <div className="chrono-course-eyeline" style={{ marginTop: 4 }}>{title}</div>;
}

function PreviewHeading({ title, count }: { title: string; count: number }) {
  return <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', margin: '18px 0 8px' }}><strong>{title}</strong><Tag>{count}</Tag></div>;
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>{children}</div>;
}

function LabeledInput({ label, ariaLabel, value, onChange }: { label: string; ariaLabel: string; value: string; onChange: (value: string) => void }) {
  return <label><FieldLabel>{label}</FieldLabel><Input aria-label={ariaLabel} value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

function LabeledTextArea({ label, ariaLabel, value, onChange, minRows }: { label: string; ariaLabel: string; value: string; onChange: (value: string) => void; minRows: number }) {
  return <label><FieldLabel>{label}</FieldLabel><TextArea aria-label={ariaLabel} value={value} autoSize={{ minRows, maxRows: Math.max(minRows + 5, 8) }} onChange={(event) => onChange(event.target.value)} /></label>;
}

function NumberInput({ label, ariaLabel, value, onChange, min, max }: { label: string; ariaLabel: string; value: number; onChange: (value: number) => void; min?: number; max?: number }) {
  return <label><FieldLabel>{label}</FieldLabel><InputNumber aria-label={ariaLabel} value={value} min={min} max={max} style={{ width: '100%' }} onChange={(next) => onChange(Number(next || 0))} /></label>;
}

function replaceAt<T>(items: T[], index: number, value: T): T[] {
  return items.map((item, itemIndex) => (itemIndex === index ? value : item));
}

function removeAt<T>(items: T[], index: number): T[] {
  return items.filter((_, itemIndex) => itemIndex !== index);
}

function readLocalDraft(): ScenarioAuthorDraft {
  try {
    const raw = localStorage.getItem(LOCAL_SCENARIO_KEY);
    if (!raw) return createScenarioDraft();
    const parsed = JSON.parse(raw) as ScenarioAuthorDraft;
    if (parsed.schema_version !== 'scenario-author-draft/v1' || !parsed.scenario_id) return createScenarioDraft();
    return parsed;
  } catch {
    return createScenarioDraft();
  }
}

function ensureToken(token: string): boolean {
  if (token.trim()) return true;
  toast.warning('请先填写 Admin token');
  return false;
}

function contractIdError(value: string): string {
  const clean = value.trim();
  if (clean.length < 2) return '至少填写 2 个字符';
  if (clean.length > 64) return '最多填写 64 个字符';
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]+$/.test(clean)) {
    return '只能使用英文字母、数字、点、下划线和短横线，并以字母或数字开头';
  }
  return '';
}

function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], { type: 'application/json;charset=utf-8' });
  downloadBlob(filename, blob);
}

function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function variablePercent(item: ScenarioDraftVariable): number {
  if (item.maximum <= item.minimum) return 0;
  return Math.max(0, Math.min(100, ((item.initial - item.minimum) / (item.maximum - item.minimum)) * 100));
}
