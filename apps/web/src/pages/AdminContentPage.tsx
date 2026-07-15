import { useEffect, useMemo, useRef, useState } from 'react';
import type { MouseEvent, ReactNode } from 'react';
import type { TextAreaRef } from 'antd/es/input/TextArea';
import { Button, Divider, Empty, Input, Segmented, Select, Space, Tag, Tooltip } from 'antd';
import {
  BgColorsOutlined,
  BoldOutlined,
  BookOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  DownloadOutlined,
  EyeOutlined,
  FileTextOutlined,
  FontColorsOutlined,
  FontSizeOutlined,
  HighlightOutlined,
  LockOutlined,
  ReloadOutlined,
  RocketOutlined,
  RollbackOutlined,
  SafetyCertificateOutlined,
  SaveOutlined,
  SendOutlined,
  TagsOutlined,
} from '@ant-design/icons';
import { Link, useNavigate } from 'react-router-dom';
import {
  api,
  type ContentWorkflowRecord,
  type ContentAssetRecord,
  type ContentFileRecord,
  type CourseReleaseManifest,
  type KeywordProfilePackage,
  type LessonContentPackage,
  type LessonSourceRecord,
  type PersonProfilePackage,
  type RuntimeScenarioRecord,
} from '../utils/api';
import { ADMIN_CONTENT_PREVIEW_KEY } from '../utils/adminContentStorage';
import { parseContentBlock, parseContentMarkup, renderMarkupHtml, stripInlineMarkup } from '../utils/contentMarkup';
import { toast } from '../utils/toast';
import ScenarioRuleEditor from './admin/ScenarioRuleEditor';

const { TextArea } = Input;
const TOKEN_KEY = 'chrono.admin.token';
const LOCAL_DRAFT_KEY = 'chrono.admin.content.editor.v1';
const LOCAL_PERSON_KEY = 'chrono.admin.content.person.v1';
const LOCAL_KEYWORD_KEY = 'chrono.admin.content.keyword.v1';
const EDITOR_MODE_KEY = 'chrono.admin.content.mode.v1';

type EditorMode = 'lesson' | 'person' | 'keyword' | 'scenario';
type BodyInlineFormat = 'bold' | 'highlight' | 'keyword' | 'red' | 'blue' | 'gold' | 'large' | 'small';
type BodyBlockFormat = 'paragraph' | 'heading1' | 'heading2' | 'heading3' | 'focus' | 'question' | 'goal';

const WORKFLOW_STATE_META: Record<ContentWorkflowRecord['state'], { label: string; color: string }> = {
  draft: { label: '草稿', color: 'default' },
  validated: { label: '校验通过', color: 'cyan' },
  in_review: { label: '待审', color: 'gold' },
  changes_requested: { label: '已退回', color: 'orange' },
  approved: { label: '审校通过', color: 'green' },
  sealed: { label: '已封存', color: 'blue' },
  published: { label: '已发布', color: 'green' },
};

const VALIDATION_ISSUE_TEXT: Record<string, string> = {
  required_text: '标题、单元和时代均需填写。',
  body_required: '至少需要一段有效正文。',
  body_depth: '建议主课文至少包含三段正文。',
  keywords_required: '至少需要一个关键词。',
  keyword_incomplete: '每个关键词都需要词语和面向学生的释义。',
  keyword_depth: '建议主课文准备五个关键词。',
  duplicate_keywords: '关键词中存在重复项。',
  people_required: '至少需要一位相关历史人物。',
  person_incomplete: '每位人物都需要姓名和面向学生的简介。',
  person_ai_boundary: '建议补充人物 persona 与时代边界，供后续人物智能体使用。',
  people_depth: '建议主课文准备两位相关人物。',
  duplicate_people: '人物列表中存在重复项。',
  facts_required: '至少需要一条可约束 AI 的史实边界。',
  facts_depth: '建议主课文准备五条史实边界。',
  sources_required: '至少需要一条可复核参考资料。',
  source_incomplete: '每条资料都需要标题，以及来源或链接/路径。',
  sources_depth: '建议主课文准备两条独立资料。',
  qa_points_missing: '建议补充可问答知识点。',
  level_goals_missing: '建议补充学习或关卡目标。',
  map_points_missing: '涉及空间关系时，建议补充地图点。',
  interactive_objective_missing: '建议预留 saga 或 sandbox 的互动目标。',
  v1_contract: '内容无法转换为课程运行契约，请检查字段。',
};

interface TextSelectionRange {
  start: number;
  end: number;
}

interface BodyContextMenuState {
  x: number;
  y: number;
  selection: TextSelectionRange;
}

interface EditorState {
  lesson_id: string;
  course_id: string;
  course_title: string;
  title: string;
  unit: string;
  era: string;
  era_id: string;
  section: string;
  lesson_no: string;
  duration: string;
  bodyText: string;
  keywordsText: string;
  focusText: string;
  qaText: string;
  goalsText: string;
  peopleText: string;
  mapText: string;
  sourcesText: string;
  sagaTitle: string;
  sagaObjective: string;
  sagaNotes: string;
  sandboxTitle: string;
  sandboxObjective: string;
  sandboxNotes: string;
  teacher_notes: string;
}

interface PersonEditorState {
  asset_id: string;
  name: string;
  role: string;
  era: string;
  summary: string;
  persona: string;
  boundariesText: string;
  keywordsText: string;
  relatedLessonsText: string;
  sourcesText: string;
  teacher_notes: string;
}

interface KeywordEditorState {
  asset_id: string;
  word: string;
  pinyin: string;
  gloss: string;
  era: string;
  category: string;
  examplesText: string;
  relatedPeopleText: string;
  relatedLessonsText: string;
  sourcesText: string;
  teacher_notes: string;
}

const baseInputStyle = { minWidth: 0 };

const inlineFormatTokens: Record<BodyInlineFormat, { prefix: string; suffix: string; placeholder: string }> = {
  bold: { prefix: '**', suffix: '**', placeholder: '加粗文字' },
  highlight: { prefix: '==', suffix: '==', placeholder: '标红文字' },
  keyword: { prefix: '【', suffix: '】', placeholder: '关键词' },
  red: { prefix: '{{红色:', suffix: '}}', placeholder: '红色标识' },
  blue: { prefix: '{{蓝色:', suffix: '}}', placeholder: '蓝色标识' },
  gold: { prefix: '{{金色:', suffix: '}}', placeholder: '金色标识' },
  large: { prefix: '{{大字:', suffix: '}}', placeholder: '大字号文字' },
  small: { prefix: '{{小字:', suffix: '}}', placeholder: '小字号说明' },
};

const headingOptions = [
  { label: '正文段落', value: 'paragraph' },
  { label: '一级标题', value: 'heading1' },
  { label: '二级标题', value: 'heading2' },
  { label: '三级标题', value: 'heading3' },
];

const sizeOptions = [
  { label: '大字', value: 'large' },
  { label: '小字', value: 'small' },
];

const colorOptions = [
  { label: '红色', value: 'red' },
  { label: '蓝色', value: 'blue' },
  { label: '金色', value: 'gold' },
];

const ERA_GUIDE = [
  { id: 'origins', name: '文明起源', needs: '遗址、器物、早期聚落、考古资料来源' },
  { id: 'early-state', name: '早期国家', needs: '传说与史实边界、王权形成、部族关系、地图点' },
  { id: 'spring-autumn', name: '春秋战国', needs: '制度变法、诸侯竞争、思想人物、抉择变量' },
  { id: 'qin-han', name: '秦汉', needs: '统一制度、郡县/中央集权、人物立场、政策后果' },
  { id: 'wei-jin', name: '魏晋南北朝', needs: '政权分合、民族交流、士族人物、空间迁徙' },
  { id: 'sui-tang', name: '隋唐', needs: '制度整合、开放交流、边疆与都城、文化人物' },
  { id: 'song-yuan', name: '宋元', needs: '经济网络、技术传播、制度争议、多民族互动' },
  { id: 'ming-qing', name: '明清', needs: '海疆边疆、财政制度、思想转型、全球联系' },
  { id: 'modern', name: '近现代', needs: '危机回应、改革方案、社会群体、史料争议' },
  { id: 'contemporary', name: '当代中国', needs: '政策节点、社会变化、生活史材料、资料可靠性' },
];

const LESSON_BLUEPRINTS = [
  { id: 'L101', era_id: 'early-state', era: '早期国家', course_id: 'C-early-state', course_title: '早期国家的形成', lesson_no: 'L101', title: '大禹治水与早期国家', unit: '洪水、部族与国家起源', section: 'P0 主线' },
  { id: 'L103', era_id: 'spring-autumn', era: '春秋战国', course_id: 'C-spring-autumn', course_title: '春秋战国的制度竞争', lesson_no: 'L103', title: '商鞅变法', unit: '变法阻力与制度选择', section: 'P0 主线' },
  { id: 'L302', era_id: 'qin-han', era: '秦汉', course_id: 'C-qin-han', course_title: '大一统帝国的建立', lesson_no: 'L302', title: '秦王嬴政与统一战争', unit: '战略、地图与诸侯', section: 'P0 主线' },
  { id: 'L303', era_id: 'qin-han', era: '秦汉', course_id: 'C-qin-han', course_title: '大一统帝国的建立', lesson_no: 'L303', title: '始皇帝与中央集权帝国', unit: '郡县、书同文与车同轨', section: 'P0 主线' },
  { id: 'L401', era_id: 'qin-han', era: '秦汉', course_id: 'C-qin-han-transition', course_title: '秦汉之际的抉择', lesson_no: 'L401', title: '秦的速亡与楚汉相争', unit: '多人立场与结局推演', section: 'P0 主线' },
  { id: 'L402', era_id: 'qin-han', era: '秦汉', course_id: 'C-western-han', course_title: '西汉国家治理', lesson_no: 'L402', title: '文景之治与汉武大一统', unit: '政策组合与双模态问答', section: 'P0 主线' },
  { id: 'L701', era_id: 'sui-tang', era: '隋唐', course_id: 'C-tang', course_title: '开放的隋唐世界', lesson_no: 'L701', title: '贞观之治', unit: '唐太宗与魏征同窗问答', section: 'P0 主线' },
  { id: 'L703', era_id: 'sui-tang', era: '隋唐', course_id: 'C-tang', course_title: '开放的隋唐世界', lesson_no: 'L703', title: '安史之乱与藩镇', unit: '盛唐断裂与坏结局推演', section: 'P0 主线' },
  { id: 'L803', era_id: 'sui-tang', era: '隋唐', course_id: 'C-silk-road', course_title: '丝路与世界中的长安', lesson_no: 'L803', title: '丝绸之路与世界中的长安', unit: '地图展开与开放交流', section: 'P0 主线' },
];

function newEditor(): EditorState {
  const stamp = Date.now().toString().slice(-8);
  return {
    lesson_id: `lesson-${stamp}`,
    course_id: 'C-content-studio',
    course_title: '内容工作室',
    title: '',
    unit: '',
    era: '',
    era_id: 'content',
    section: '内容包',
    lesson_no: 'A1',
    duration: '08:00',
    bodyText: '',
    keywordsText: '',
    focusText: '',
    qaText: '',
    goalsText: '',
    peopleText: '',
    mapText: '',
    sourcesText: '',
    sagaTitle: '',
    sagaObjective: '',
    sagaNotes: '',
    sandboxTitle: '',
    sandboxObjective: '',
    sandboxNotes: '',
    teacher_notes: '',
  };
}

function newPersonEditor(): PersonEditorState {
  return {
    asset_id: 'person-sample',
    name: '',
    role: '',
    era: '',
    summary: '',
    persona: '',
    boundariesText: '',
    keywordsText: '',
    relatedLessonsText: '',
    sourcesText: '',
    teacher_notes: '',
  };
}

function newKeywordEditor(): KeywordEditorState {
  return {
    asset_id: 'keyword-sample',
    word: '',
    pinyin: '',
    gloss: '',
    era: '',
    category: '',
    examplesText: '',
    relatedPeopleText: '',
    relatedLessonsText: '',
    sourcesText: '',
    teacher_notes: '',
  };
}

function readEditorMode(): EditorMode {
  const saved = localStorage.getItem(EDITOR_MODE_KEY);
  return saved === 'lesson' || saved === 'person' || saved === 'keyword' || saved === 'scenario'
    ? saved
    : 'lesson';
}

function readLocalEditor(): EditorState {
  const saved = localStorage.getItem(LOCAL_DRAFT_KEY);
  if (!saved) return newEditor();
  try {
    return { ...newEditor(), ...(JSON.parse(saved) as Partial<EditorState>) };
  } catch {
    return newEditor();
  }
}

function readLocalPersonEditor(): PersonEditorState {
  const saved = localStorage.getItem(LOCAL_PERSON_KEY);
  if (!saved) return newPersonEditor();
  try {
    return { ...newPersonEditor(), ...(JSON.parse(saved) as Partial<PersonEditorState>) };
  } catch {
    return newPersonEditor();
  }
}

function readLocalKeywordEditor(): KeywordEditorState {
  const saved = localStorage.getItem(LOCAL_KEYWORD_KEY);
  if (!saved) return newKeywordEditor();
  try {
    return { ...newKeywordEditor(), ...(JSON.parse(saved) as Partial<KeywordEditorState>) };
  } catch {
    return newKeywordEditor();
  }
}

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function splitLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function splitParagraphs(value: string): string[] {
  return value
    .split(/\n\s*\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function unique(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  values.forEach((value) => {
    const key = value.trim();
    if (key && !seen.has(key)) {
      seen.add(key);
      result.push(key);
    }
  });
  return result;
}

function extractMarkedKeywords(value: string): string[] {
  return unique(Array.from(value.matchAll(/【([^】]{1,40})】/g)).map((match) => match[1].trim()));
}

function parseKeywordLine(line: string) {
  const parts = line.includes('|')
    ? line.split('|').map((item) => item.trim())
    : line.split(/[：:]/).map((item) => item.trim());
  const hasPinyinColumn = line.includes('|') && parts.length >= 3;
  return {
    word: parts[0] || line.trim(),
    pinyin: hasPinyinColumn ? parts[1] || '' : '',
    gloss: line.includes('|')
      ? parts.slice(hasPinyinColumn ? 2 : 1).join(' | ')
      : parts.slice(1).join(': '),
  };
}

function parseKeywords(editor: EditorState) {
  const explicitLines = editor.keywordsText
    .split(/\r?\n|,|，|、/)
    .map((item) => item.trim())
    .filter(Boolean);
  const explicit = explicitLines.map(parseKeywordLine);
  const marked = extractMarkedKeywords(editor.bodyText)
    .filter((word) => !explicit.some((item) => item.word === word))
    .map((word) => ({ word, pinyin: '', gloss: '' }));
  return [...explicit, ...marked].filter((item) => item.word);
}

function parsePipeRecords(value: string, keys: string[]) {
  return splitLines(value).map((line) => {
    const parts = line.split('|').map((item) => item.trim());
    return keys.reduce<Record<string, string>>((record, key, index) => {
      record[key] = parts[index] || '';
      return record;
    }, {});
  });
}

function packageToEditor(item: LessonContentPackage): EditorState {
  return {
    ...newEditor(),
    lesson_id: item.lesson_id,
    course_id: item.course_id || 'C-content-studio',
    course_title: item.course_title || item.unit || '',
    title: item.title,
    unit: item.unit,
    era: item.era,
    era_id: item.era_id || 'content',
    section: item.section || '内容包',
    lesson_no: item.lesson_no || 'A1',
    duration: item.duration || '08:00',
    bodyText: (item.body || []).join('\n\n'),
    keywordsText: (item.keywords || [])
      .map((keyword) => [keyword.word, keyword.pinyin, keyword.gloss].filter(Boolean).join(' | '))
      .join('\n'),
    focusText: (item.facts || []).join('\n'),
    qaText: (item.qa_points || []).join('\n'),
    goalsText: (item.level_goals || []).join('\n'),
    peopleText: (item.people || [])
      .map((person) => [person.name, person.role, person.summary, person.persona].filter(Boolean).join(' | '))
      .join('\n'),
    mapText: (item.map_points || [])
      .map((point) => [point.label, point.region, point.note, point.kind].filter(Boolean).join(' | '))
      .join('\n'),
    sourcesText: (item.source_refs || [])
      .map((source) => [source.title, source.source, source.url_or_path, source.citation_note].filter(Boolean).join(' | '))
      .join('\n'),
    sagaTitle: item.saga_material?.title || '',
    sagaObjective: item.saga_material?.objective || '',
    sagaNotes: item.saga_material?.notes || '',
    sandboxTitle: item.sandbox_material?.title || '',
    sandboxObjective: item.sandbox_material?.objective || '',
    sandboxNotes: item.sandbox_material?.notes || '',
    teacher_notes: item.teacher_notes || '',
  };
}

function personToEditor(item: PersonProfilePackage): PersonEditorState {
  return {
    asset_id: item.asset_id,
    name: item.name,
    role: item.role || '',
    era: item.era || '',
    summary: item.summary || '',
    persona: item.persona || '',
    boundariesText: (item.boundaries || []).join('\n'),
    keywordsText: (item.keywords || []).join('\n'),
    relatedLessonsText: (item.related_lessons || []).join('\n'),
    sourcesText: (item.source_refs || [])
      .map((source) => [source.title, source.source, source.url_or_path, source.citation_note].filter(Boolean).join(' | '))
      .join('\n'),
    teacher_notes: item.teacher_notes || '',
  };
}

function keywordToEditor(item: KeywordProfilePackage): KeywordEditorState {
  return {
    asset_id: item.asset_id,
    word: item.word,
    pinyin: item.pinyin || '',
    gloss: item.gloss || '',
    era: item.era || '',
    category: item.category || '',
    examplesText: (item.examples || []).join('\n'),
    relatedPeopleText: (item.related_people || []).join('\n'),
    relatedLessonsText: (item.related_lessons || []).join('\n'),
    sourcesText: (item.source_refs || [])
      .map((source) => [source.title, source.source, source.url_or_path, source.citation_note].filter(Boolean).join(' | '))
      .join('\n'),
    teacher_notes: item.teacher_notes || '',
  };
}

function buildPayload(editor: EditorState): LessonContentPackage {
  const required = [editor.lesson_id, editor.course_id, editor.title, editor.unit, editor.era];
  if (required.some((value) => !value.trim())) {
    throw new Error('请补齐 ID、课程、标题、单元和时代');
  }
  const keywords = parseKeywords(editor);
  const people = parsePipeRecords(editor.peopleText, ['name', 'role', 'summary', 'persona'])
    .filter((item) => item.name)
    .map((item) => ({ name: item.name, role: item.role, summary: item.summary, persona: item.persona }));
  const mapPoints = parsePipeRecords(editor.mapText, ['label', 'region', 'note', 'kind'])
    .filter((item) => item.label)
    .map((item) => ({ label: item.label, region: item.region, note: item.note, kind: item.kind || 'site' }));
  const sourceRefs = parsePipeRecords(editor.sourcesText, ['title', 'source', 'url_or_path', 'citation_note'])
    .filter((item) => item.title)
    .map((item) => ({ title: item.title, source: item.source, url_or_path: item.url_or_path, citation_note: item.citation_note }));
  return {
    lesson_id: editor.lesson_id.trim(),
    course_id: editor.course_id.trim(),
    course_title: editor.course_title.trim() || editor.unit.trim(),
    title: editor.title.trim(),
    unit: editor.unit.trim(),
    era: editor.era.trim(),
    era_id: editor.era_id.trim() || 'content',
    section: editor.section.trim() || '内容包',
    lesson_no: editor.lesson_no.trim() || 'A1',
    duration: editor.duration.trim() || '08:00',
    body: splitParagraphs(editor.bodyText),
    keywords,
    people,
    map_points: mapPoints,
    source_refs: sourceRefs,
    facts: splitLines(editor.focusText),
    qa_points: splitLines(editor.qaText),
    level_goals: splitLines(editor.goalsText),
    saga_material: {
      title: editor.sagaTitle.trim(),
      objective: editor.sagaObjective.trim(),
      notes: editor.sagaNotes.trim(),
      assets: [],
    },
    sandbox_material: {
      title: editor.sandboxTitle.trim(),
      objective: editor.sandboxObjective.trim(),
      notes: editor.sandboxNotes.trim(),
      assets: [],
    },
    seed_canvas: keywords.slice(0, 6).map((keyword, index) => ({ id: `k${index + 1}`, label: keyword.word })),
    teacher_notes: editor.teacher_notes.trim(),
    status: 'draft',
    version: 0,
  };
}

function buildPersonAsset(editor: PersonEditorState): PersonProfilePackage {
  if (!editor.asset_id.trim() || !editor.name.trim()) {
    throw new Error('请补齐档案 ID 和人物姓名');
  }
  const sourceRefs = parsePipeRecords(editor.sourcesText, ['title', 'source', 'url_or_path', 'citation_note'])
    .filter((item) => item.title)
    .map((item) => ({ title: item.title, source: item.source, url_or_path: item.url_or_path, citation_note: item.citation_note }));
  return {
    asset_id: editor.asset_id.trim(),
    name: editor.name.trim(),
    role: editor.role.trim(),
    era: editor.era.trim(),
    summary: editor.summary.trim(),
    persona: editor.persona.trim(),
    boundaries: splitLines(editor.boundariesText),
    keywords: splitLines(editor.keywordsText),
    related_lessons: splitLines(editor.relatedLessonsText),
    source_refs: sourceRefs,
    teacher_notes: editor.teacher_notes.trim(),
    status: 'draft',
    version: 0,
  };
}

function buildKeywordAsset(editor: KeywordEditorState): KeywordProfilePackage {
  if (!editor.asset_id.trim() || !editor.word.trim() || !editor.gloss.trim()) {
    throw new Error('请补齐档案 ID、关键词和解释');
  }
  const sourceRefs = parsePipeRecords(editor.sourcesText, ['title', 'source', 'url_or_path', 'citation_note'])
    .filter((item) => item.title)
    .map((item) => ({ title: item.title, source: item.source, url_or_path: item.url_or_path, citation_note: item.citation_note }));
  return {
    asset_id: editor.asset_id.trim(),
    word: editor.word.trim(),
    pinyin: editor.pinyin.trim(),
    gloss: editor.gloss.trim(),
    era: editor.era.trim(),
    category: editor.category.trim(),
    examples: splitLines(editor.examplesText),
    related_people: splitLines(editor.relatedPeopleText),
    related_lessons: splitLines(editor.relatedLessonsText),
    source_refs: sourceRefs,
    teacher_notes: editor.teacher_notes.trim(),
    status: 'draft',
    version: 0,
  };
}

function applyBodyParsing(editor: EditorState): EditorState {
  const keywordText = unique([...splitLines(editor.keywordsText), ...extractMarkedKeywords(editor.bodyText)]).join('\n');
  const focus: string[] = [];
  const qa: string[] = [];
  const goals: string[] = [];
  splitLines(editor.bodyText).forEach((line) => {
    const normalized = line.replace(/^[-*]\s*/, '').trim();
    const match = normalized.match(/^(重点|事实|史实|问题|追问|目标|关卡)[:：]\s*(.+)$/);
    if (!match) return;
    if (['重点', '事实', '史实'].includes(match[1])) focus.push(match[2]);
    if (['问题', '追问'].includes(match[1])) qa.push(match[2]);
    if (['目标', '关卡'].includes(match[1])) goals.push(match[2]);
  });
  return {
    ...editor,
    keywordsText: keywordText,
    focusText: unique([...splitLines(editor.focusText), ...focus]).join('\n'),
    qaText: unique([...splitLines(editor.qaText), ...qa]).join('\n'),
    goalsText: unique([...splitLines(editor.goalsText), ...goals]).join('\n'),
  };
}

function downloadText(filename: string, text: string, type = 'application/json;charset=utf-8') {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function safeFileBase(value: string, fallback: string): string {
  return (stripInlineMarkup(value).trim() || fallback)
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, '')
    .replace(/\s+/g, ' ')
    .slice(0, 80);
}

function exportContentBundle(item: LessonContentPackage) {
  const base = safeFileBase(item.title, item.lesson_id);
  const formatLayer = {
    lesson_id: item.lesson_id,
    syntax: {
      bold: '**文字**',
      highlight: '==标红文字==',
      keyword: '【关键词】',
      heading: '# 一级标题 / ## 二级标题 / ### 三级标题',
      colors: '{{红色:文字}} / {{蓝色:文字}} / {{金色:文字}}',
      font_size: '{{大字:文字}} / {{小字:文字}}',
    },
    paragraphs: (item.body || []).map((paragraph, index) => {
      const block = parseContentBlock(paragraph);
      return {
        index,
        raw: paragraph,
        block: block.level > 0 ? `heading_${block.level}` : 'paragraph',
        text: block.text,
        segments: parseContentMarkup(block.text).filter((segment) => segment.marks.length > 0),
      };
    }),
  };
  downloadText(`${base}.json`, formatJson(item) + '\n');
  downloadText(`${base}-格式层.json`, formatJson(formatLayer) + '\n');
  downloadText(`${base}-预览.html`, buildPreviewHtml(item), 'text/html;charset=utf-8');
  downloadText(`${base}-教师稿.md`, buildTeacherMarkdown(item), 'text/markdown;charset=utf-8');
}

function exportPersonAsset(item: PersonProfilePackage) {
  const base = safeFileBase(`${item.name}-人物档案`, item.asset_id);
  downloadText(`${base}.json`, formatJson(item) + '\n');
}

function exportKeywordAsset(item: KeywordProfilePackage) {
  const base = safeFileBase(`${item.word}-关键词档案`, item.asset_id);
  downloadText(`${base}.json`, formatJson(item) + '\n');
}

function buildTeacherMarkdown(item: LessonContentPackage): string {
  return [
    `# ${stripInlineMarkup(item.title)}`,
    '',
    `- lesson_id: ${item.lesson_id}`,
    `- course_id: ${item.course_id}`,
    `- unit: ${item.unit}`,
    `- era: ${item.era}`,
    `- status: ${item.status || 'draft'}`,
    '',
    '## 正文',
    ...(item.body || []).map((paragraph) => `\n${paragraph}`),
    '',
    '## 关键词',
    ...(item.keywords || []).map((keyword) => `- ${keyword.word}${keyword.gloss ? `：${keyword.gloss}` : ''}`),
    '',
    '## 重点块',
    ...(item.facts || []).map((fact) => `- ${fact}`),
    '',
  ].join('\n');
}

function buildPreviewBlockHtml(paragraph: string): string {
  const block = parseContentBlock(paragraph);
  if (block.level > 0) {
    const tag = block.level === 1 ? 'h2' : block.level === 2 ? 'h3' : 'h4';
    return `<${tag}>${renderMarkupHtml(block.text)}</${tag}>`;
  }
  return `<p>${renderMarkupHtml(paragraph)}</p>`;
}

function buildPreviewHtml(item: LessonContentPackage): string {
  const body = (item.body || []).map(buildPreviewBlockHtml).join('\n');
  const keywords = (item.keywords || []).map((keyword) => `<li><strong>${escapeHtml(keyword.word)}</strong>${keyword.gloss ? `：${escapeHtml(keyword.gloss)}` : ''}</li>`).join('');
  const people = (item.people || []).map((person) => `<li><strong>${escapeHtml(person.name)}</strong>${person.role ? ` · ${escapeHtml(person.role)}` : ''}<br>${escapeHtml(person.summary || '')}</li>`).join('');
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(stripInlineMarkup(item.title))}</title>
  <style>
    body { margin: 0; padding: 40px; background: #F7F1E6; color: #2E2418; font-family: "Noto Serif SC", "Microsoft YaHei", serif; }
    main { max-width: 880px; margin: 0 auto; background: #FFFDF7; border: 1px solid #E6D9C3; border-radius: 8px; padding: 34px; }
    h1 { margin: 0 0 8px; font-size: 32px; }
    h2, h3, h4 { margin: 24px 0 10px; line-height: 1.45; }
    h2 { font-size: 24px; }
    h3 { font-size: 21px; }
    h4 { font-size: 18px; }
    .meta { color: #796C5A; margin-bottom: 24px; }
    p { font-size: 17px; line-height: 2; text-indent: 2em; }
    .keyword { color: #9B642E; font-weight: 700; border-bottom: 1px solid rgba(155,100,46,.35); }
    mark { color: #9F2D20; background: rgba(198,65,47,.14); border-radius: 3px; padding: 0 3px; }
    .text-red { color: #9F2D20; }
    .text-blue { color: #315F91; }
    .text-gold { color: #8B641B; }
    .text-large { font-size: 1.14em; }
    .text-small { font-size: .88em; }
    aside { margin-top: 28px; display: grid; gap: 18px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
    section { background: #F8F2E8; border-radius: 6px; padding: 16px; }
    li { margin: 8px 0; line-height: 1.6; }
  </style>
</head>
<body>
  <main>
    <h1>${escapeHtml(stripInlineMarkup(item.title))}</h1>
    <div class="meta">${escapeHtml(item.lesson_no || '')} · ${escapeHtml(item.unit)} · ${escapeHtml(item.era)} · ${escapeHtml(item.duration || '')}</div>
    ${body}
    <aside>
      <section><h2>关键词</h2><ul>${keywords}</ul></section>
      <section><h2>人物</h2><ul>${people}</ul></section>
    </aside>
  </main>
</body>
</html>`;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function clampSelection(selection: TextSelectionRange, length: number): TextSelectionRange {
  const start = Math.max(0, Math.min(selection.start, length));
  const end = Math.max(start, Math.min(selection.end, length));
  return { start, end };
}

function formatBodyLine(line: string, format: BodyBlockFormat): string {
  const clean = line.replace(/^\s*#{1,6}\s+/, '').replace(/^\s*(重点|问题|目标)[:：]\s*/, '').trim();
  if (format === 'paragraph') return clean || '正文段落';
  if (format === 'heading1') return `# ${clean || '一级标题'}`;
  if (format === 'heading2') return `## ${clean || '二级标题'}`;
  if (format === 'heading3') return `### ${clean || '三级标题'}`;
  if (format === 'focus') return `重点：${clean || '重点内容'}`;
  if (format === 'question') return `问题：${clean || '可追问问题'}`;
  return `目标：${clean || '关卡目标'}`;
}

function isNotFoundError(error: unknown): boolean {
  return error instanceof Error && error.message.startsWith('404 ');
}

function releaseOperationLabel(operation: CourseReleaseManifest['operation']): string {
  if (operation === 'bootstrap') return '初始快照';
  if (operation === 'rollback') return '回滚快照';
  return '正式发布';
}

export default function AdminContentPage() {
  const navigate = useNavigate();
  const [editorMode, setEditorMode] = useState<EditorMode>(() => readEditorMode());
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || import.meta.env.VITE_ADMIN_TOKEN || '');
  const [editor, setEditor] = useState<EditorState>(() => readLocalEditor());
  const [personEditor, setPersonEditor] = useState<PersonEditorState>(() => readLocalPersonEditor());
  const [keywordEditor, setKeywordEditor] = useState<KeywordEditorState>(() => readLocalKeywordEditor());
  const [preview, setPreview] = useState<LessonContentPackage | null>(null);
  const [workflow, setWorkflow] = useState<ContentWorkflowRecord | null>(null);
  const [releases, setReleases] = useState<CourseReleaseManifest[]>([]);
  const [currentRelease, setCurrentRelease] = useState<CourseReleaseManifest | null>(null);
  const [selectedRelease, setSelectedRelease] = useState<string>();
  const [reviewNote, setReviewNote] = useState('');
  const [drafts, setDrafts] = useState<ContentFileRecord[]>([]);
  const [sourceLessons, setSourceLessons] = useState<LessonSourceRecord[]>([]);
  const [assets, setAssets] = useState<ContentAssetRecord[]>([]);
  const [runtimeScenarios, setRuntimeScenarios] = useState<RuntimeScenarioRecord[]>([]);
  const [selectedDraft, setSelectedDraft] = useState<string>();
  const [selectedSourceLesson, setSelectedSourceLesson] = useState<string>();
  const [selectedPersonAsset, setSelectedPersonAsset] = useState<string>();
  const [selectedKeywordAsset, setSelectedKeywordAsset] = useState<string>();
  const [showGuide, setShowGuide] = useState(false);
  const [sealedPath, setSealedPath] = useState('');
  const [localSavedAt, setLocalSavedAt] = useState('');
  const [serverSavedAt, setServerSavedAt] = useState('');
  const [assetSavedAt, setAssetSavedAt] = useState('');
  const [busy, setBusy] = useState('');
  const bodyTextAreaRef = useRef<TextAreaRef | null>(null);
  const bodySelectionRef = useRef<TextSelectionRange>({ start: 0, end: 0 });
  const tokenRefreshSequenceRef = useRef(0);
  const [bodyContextMenu, setBodyContextMenu] = useState<BodyContextMenuState | null>(null);
  const activeWorkflow = workflow?.lesson_id === editor.lesson_id
    && workflow.course_id === editor.course_id
    ? workflow
    : null;
  const activeRelease = currentRelease?.course_id === editor.course_id ? currentRelease : null;

  const rememberEditorMode = (value: EditorMode) => {
    setEditorMode(value);
    localStorage.setItem(EDITOR_MODE_KEY, value);
  };

  const currentPayload = useMemo(() => {
    try {
      return buildPayload(editor);
    } catch {
      return null;
    }
  }, [editor]);

  const currentPersonAsset = useMemo(() => {
    try {
      return buildPersonAsset(personEditor);
    } catch {
      return null;
    }
  }, [personEditor]);

  const currentKeywordAsset = useMemo(() => {
    try {
      return buildKeywordAsset(keywordEditor);
    } catch {
      return null;
    }
  }, [keywordEditor]);

  useEffect(() => {
    localStorage.setItem(LOCAL_DRAFT_KEY, JSON.stringify(editor));
    setLocalSavedAt(new Date().toLocaleTimeString());
  }, [editor]);

  useEffect(() => {
    localStorage.setItem(LOCAL_PERSON_KEY, JSON.stringify(personEditor));
  }, [personEditor]);

  useEffect(() => {
    localStorage.setItem(LOCAL_KEYWORD_KEY, JSON.stringify(keywordEditor));
  }, [keywordEditor]);

  useEffect(() => {
    const sequence = ++tokenRefreshSequenceRef.current;
    setDrafts([]);
    setSourceLessons([]);
    setAssets([]);
    setRuntimeScenarios([]);
    if (!token) {
      return;
    }
    const timer = window.setTimeout(() => {
      void Promise.all([
        api.adminContentDrafts(token),
        api.adminContentSourceLessons(token),
        api.adminContentAssets(token),
        api.adminRuntimeScenarios(token),
      ]).then(([draftResult, sourceResult, assetResult, scenarioResult]) => {
        if (tokenRefreshSequenceRef.current !== sequence) return;
        setDrafts(draftResult.items);
        setSourceLessons(sourceResult.items);
        setAssets(assetResult.items);
        setRuntimeScenarios(scenarioResult.items);
      }).catch((error: any) => {
        if (tokenRefreshSequenceRef.current === sequence) {
          toast.error(error?.message || '管理员内容库读取失败');
        }
      });
    }, 350);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    if (!bodyContextMenu) return;
    const closeMenu = () => setBodyContextMenu(null);
    window.addEventListener('click', closeMenu);
    window.addEventListener('keydown', closeMenu);
    window.addEventListener('scroll', closeMenu, true);
    return () => {
      window.removeEventListener('click', closeMenu);
      window.removeEventListener('keydown', closeMenu);
      window.removeEventListener('scroll', closeMenu, true);
    };
  }, [bodyContextMenu]);

  const rememberToken = (value: string) => {
    setToken(value);
    localStorage.setItem(TOKEN_KEY, value);
  };

  const updateEditor = (patch: Partial<EditorState>) => {
    setEditor((current) => ({ ...current, ...patch }));
    setSealedPath('');
  };

  const updatePersonEditor = (patch: Partial<PersonEditorState>) => {
    setPersonEditor((current) => ({ ...current, ...patch }));
    setAssetSavedAt('');
  };

  const updateKeywordEditor = (patch: Partial<KeywordEditorState>) => {
    setKeywordEditor((current) => ({ ...current, ...patch }));
    setAssetSavedAt('');
  };

  const getBodyTextArea = () => bodyTextAreaRef.current?.resizableTextArea?.textArea ?? null;

  const rememberBodySelection = () => {
    const textarea = getBodyTextArea();
    if (!textarea) return;
    bodySelectionRef.current = { start: textarea.selectionStart, end: textarea.selectionEnd };
  };

  const rememberBodySelectionSoon = () => {
    window.requestAnimationFrame(rememberBodySelection);
  };

  const activeBodySelection = (override?: TextSelectionRange) => {
    const textarea = getBodyTextArea();
    if (override) return clampSelection(override, editor.bodyText.length);
    const liveSelection = textarea ? { start: textarea.selectionStart, end: textarea.selectionEnd } : null;
    const savedSelection = bodySelectionRef.current;
    const selection = liveSelection && liveSelection.start !== liveSelection.end
      ? liveSelection
      : savedSelection.start !== savedSelection.end
        ? savedSelection
        : liveSelection ?? savedSelection;
    return clampSelection(selection, editor.bodyText.length);
  };

  const replaceBodyRange = (selection: TextSelectionRange, nextText: string, selectStart: number, selectEnd: number) => {
    const nextBody = `${editor.bodyText.slice(0, selection.start)}${nextText}${editor.bodyText.slice(selection.end)}`;
    updateEditor({ bodyText: nextBody });
    setBodyContextMenu(null);
    window.requestAnimationFrame(() => {
      const textarea = getBodyTextArea();
      if (!textarea) return;
      textarea.focus();
      textarea.setSelectionRange(selectStart, selectEnd);
      bodySelectionRef.current = { start: selectStart, end: selectEnd };
    });
  };

  const applyBodyInlineFormat = (format: BodyInlineFormat, selectionOverride?: TextSelectionRange) => {
    const token = inlineFormatTokens[format];
    const selection = activeBodySelection(selectionOverride);
    const selected = editor.bodyText.slice(selection.start, selection.end) || token.placeholder;
    const nextText = `${token.prefix}${selected}${token.suffix}`;
    const innerStart = selection.start + token.prefix.length;
    replaceBodyRange(selection, nextText, innerStart, innerStart + selected.length);
  };

  const applyBodyBlockFormat = (format: BodyBlockFormat, selectionOverride?: TextSelectionRange) => {
    const selection = activeBodySelection(selectionOverride);
    const lineStart = editor.bodyText.lastIndexOf('\n', Math.max(0, selection.start - 1)) + 1;
    const nextBreak = editor.bodyText.indexOf('\n', selection.end);
    const lineEnd = nextBreak >= 0 ? nextBreak : editor.bodyText.length;
    const blockSelection = { start: lineStart, end: lineEnd };
    const currentBlock = editor.bodyText.slice(lineStart, lineEnd);
    const nextText = (currentBlock ? currentBlock.split('\n') : ['']).map((line) => formatBodyLine(line, format)).join('\n');
    replaceBodyRange(blockSelection, nextText, lineStart, lineStart + nextText.length);
  };

  const handleBodyContextMenu = (event: MouseEvent<HTMLTextAreaElement>) => {
    event.preventDefault();
    const liveSelection = { start: event.currentTarget.selectionStart, end: event.currentTarget.selectionEnd };
    const savedSelection = bodySelectionRef.current;
    const selection = liveSelection.start !== liveSelection.end
      ? liveSelection
      : savedSelection.start !== savedSelection.end
        ? savedSelection
        : liveSelection;
    bodySelectionRef.current = selection;
    setBodyContextMenu({
      x: Math.max(8, Math.min(event.clientX, window.innerWidth - 248)),
      y: Math.max(8, Math.min(event.clientY, window.innerHeight - 270)),
      selection,
    });
  };

  const renderFormatButton = (
    format: BodyInlineFormat,
    label: string,
    icon: ReactNode,
    selectionOverride?: TextSelectionRange,
  ) => (
    <Tooltip title={label}>
      <Button
        size="small"
        icon={icon}
        onMouseDown={(event) => {
          event.preventDefault();
          rememberBodySelection();
        }}
        onClick={() => applyBodyInlineFormat(format, selectionOverride)}
      >
        {label}
      </Button>
    </Tooltip>
  );

  const refreshDrafts = async () => {
    setBusy('drafts');
    try {
      const res = await api.adminContentDrafts(token);
      setDrafts(res.items);
    } catch (err: any) {
      toast.error(err?.message || '草稿库读取失败');
    } finally {
      setBusy('');
    }
  };

  const refreshAssets = async () => {
    try {
      const res = await api.adminContentAssets(token);
      setAssets(res.items);
    } catch (err: any) {
      toast.error(err?.message || '资料档案读取失败');
    }
  };

  const refreshRuntimeScenarios = async () => {
    if (!token) {
      setRuntimeScenarios([]);
      return;
    }
    try {
      const res = await api.adminRuntimeScenarios(token);
      setRuntimeScenarios(res.items);
    } catch (err: any) {
      toast.error(err?.message || '封存关卡读取失败');
    }
  };

  const clearReleaseState = () => {
    setWorkflow(null);
    setReleases([]);
    setCurrentRelease(null);
    setSelectedRelease(undefined);
    setReviewNote('');
  };

  const refreshReleaseState = async (courseId: string) => {
    if (!token || !courseId) {
      setReleases([]);
      setCurrentRelease(null);
      return;
    }
    const currentPromise = api.adminContentCurrentRelease(token, courseId)
      .then((response) => response.release)
      .catch((error: unknown) => {
        if (isNotFoundError(error)) return null;
        throw error;
      });
    const [history, current] = await Promise.all([
      api.adminContentReleases(token, courseId),
      currentPromise,
    ]);
    setReleases(history.items);
    setCurrentRelease(current);
    setSelectedRelease((selected) => (
      selected && history.items.some((item) => item.release_id === selected)
        ? selected
        : undefined
    ));
  };

  const refreshWorkflowState = async (lessonId: string, courseId: string) => {
    if (!token || !lessonId) {
      clearReleaseState();
      return;
    }
    const workflowPromise = api.adminContentWorkflow(token, lessonId)
      .then((response) => response.workflow)
      .catch((error: unknown) => {
        if (isNotFoundError(error)) return null;
        throw error;
      });
    const [nextWorkflow] = await Promise.all([
      workflowPromise,
      refreshReleaseState(courseId),
    ]);
    setWorkflow(nextWorkflow);
  };

  useEffect(() => {
    if (!token) {
      clearReleaseState();
      return;
    }
    const timer = window.setTimeout(() => {
      void refreshWorkflowState(editor.lesson_id, editor.course_id);
    }, 350);
    return () => window.clearTimeout(timer);
    // Reconcile the initial local draft after authentication; later lesson switches load explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const createNew = () => {
    const item = newEditor();
    setEditor(item);
    setPreview(null);
    setSelectedDraft(undefined);
    setSealedPath('');
    setServerSavedAt('');
    clearReleaseState();
    toast.success('新内容已创建');
  };

  const loadTemplate = async () => {
    setBusy('template');
    try {
      const item = await api.adminContentTemplate(token);
      setEditor(packageToEditor(item));
      setPreview(item);
      setSelectedDraft(undefined);
      setSealedPath('');
      clearReleaseState();
      toast.success('模板已载入');
    } catch (err: any) {
      toast.error(err?.message || '模板载入失败');
    } finally {
      setBusy('');
    }
  };

  const loadSourceLesson = async () => {
    if (!selectedSourceLesson) return;
    setBusy('source');
    try {
      const item = await api.adminContentSourceLesson(token, selectedSourceLesson);
      setEditor(packageToEditor(item));
      setPreview(item);
      setSelectedDraft(undefined);
      setSealedPath('');
      setServerSavedAt('');
      clearReleaseState();
      toast.success('已读取课程初稿');
    } catch (err: any) {
      toast.error(err?.message || '课程初稿读取失败');
    } finally {
      setBusy('');
    }
  };

  const loadPersonTemplate = async () => {
    setBusy('person-template');
    try {
      const item = await api.adminPersonTemplate(token);
      setPersonEditor(personToEditor(item));
      setSelectedPersonAsset(undefined);
      toast.success('人物模板已载入');
    } catch (err: any) {
      toast.error(err?.message || '人物模板载入失败');
    } finally {
      setBusy('');
    }
  };

  const loadKeywordTemplate = async () => {
    setBusy('keyword-template');
    try {
      const item = await api.adminKeywordTemplate(token);
      setKeywordEditor(keywordToEditor(item));
      setSelectedKeywordAsset(undefined);
      toast.success('关键词模板已载入');
    } catch (err: any) {
      toast.error(err?.message || '关键词模板载入失败');
    } finally {
      setBusy('');
    }
  };

  const loadPersonAsset = async () => {
    if (!selectedPersonAsset) return;
    setBusy('person-load');
    try {
      const item = await api.adminPersonAsset(token, selectedPersonAsset);
      setPersonEditor(personToEditor(item));
      setAssetSavedAt(item.updated_at ? new Date(item.updated_at).toLocaleString() : '');
      toast.success('人物档案已打开');
    } catch (err: any) {
      toast.error(err?.message || '人物档案打开失败');
    } finally {
      setBusy('');
    }
  };

  const loadKeywordAsset = async () => {
    if (!selectedKeywordAsset) return;
    setBusy('keyword-load');
    try {
      const item = await api.adminKeywordAsset(token, selectedKeywordAsset);
      setKeywordEditor(keywordToEditor(item));
      setAssetSavedAt(item.updated_at ? new Date(item.updated_at).toLocaleString() : '');
      toast.success('关键词档案已打开');
    } catch (err: any) {
      toast.error(err?.message || '关键词档案打开失败');
    } finally {
      setBusy('');
    }
  };

  const loadSelectedDraft = async () => {
    if (!selectedDraft) return;
    setBusy('load');
    try {
      const item = await api.adminContentDraft(token, selectedDraft);
      setEditor(packageToEditor(item));
      setPreview(item);
      setSealedPath('');
      setServerSavedAt(item.updated_at ? new Date(item.updated_at).toLocaleString() : '');
      await refreshWorkflowState(item.lesson_id, item.course_id || '');
      toast.success('草稿已打开');
    } catch (err: any) {
      toast.error(err?.message || '草稿打开失败');
    } finally {
      setBusy('');
    }
  };

  const parseFocusBlocks = () => {
    setEditor((current) => applyBodyParsing(current));
    toast.success('重点块已解析');
  };

  const applyBlueprint = (blueprintId: string) => {
    const blueprint = LESSON_BLUEPRINTS.find((item) => item.id === blueprintId);
    if (!blueprint) return;
    const lessonId = `${blueprint.id.toLowerCase()}-${Date.now().toString().slice(-6)}`;
    updateEditor({
      lesson_id: lessonId,
      course_id: blueprint.course_id,
      course_title: blueprint.course_title,
      title: blueprint.title,
      unit: blueprint.unit,
      era: blueprint.era,
      era_id: blueprint.era_id,
      section: blueprint.section,
      lesson_no: blueprint.lesson_no,
    });
    clearReleaseState();
    toast.success('课程规划已填入');
  };

  const previewContent = async () => {
    setBusy('preview');
    try {
      const payload = buildPayload(editor);
      const res = await api.adminContentPreview(token, payload);
      setPreview(res.item);
      setSealedPath('');
      localStorage.setItem(ADMIN_CONTENT_PREVIEW_KEY, JSON.stringify(res.item));
      toast.success('预览已更新');
      navigate('/admin/content/preview');
    } catch (err: any) {
      toast.error(err?.message || '预览失败');
    } finally {
      setBusy('');
    }
  };

  const persistCurrentDraft = async () => {
    const payload = buildPayload(editor);
    const res = await api.adminContentSaveDraft(token, payload);
    setPreview(res.item);
    setWorkflow(res.workflow);
    setServerSavedAt(
      res.item.updated_at
        ? new Date(res.item.updated_at).toLocaleString()
        : new Date().toLocaleString(),
    );
    setSealedPath('');
    const draftList = await api.adminContentDrafts(token);
    setDrafts(draftList.items);
    return { payload, response: res };
  };

  const saveDraft = async () => {
    setBusy('save');
    try {
      await persistCurrentDraft();
      toast.success('草稿已保存');
    } catch (err: any) {
      toast.error(err?.message || '草稿保存失败');
    } finally {
      setBusy('');
    }
  };

  const validateDraft = async () => {
    setBusy('validate');
    try {
      const { payload } = await persistCurrentDraft();
      const res = await api.adminContentValidate(
        token,
        payload.lesson_id,
      );
      setWorkflow(res.workflow);
      await refreshReleaseState(payload.course_id || '');
      if (res.report?.valid) {
        toast.success('最低发布校验已通过');
      } else {
        toast.warning('仍有阻断项，请按校验结果补充内容');
      }
    } catch (err: any) {
      toast.error(err?.message || '内容校验失败');
    } finally {
      setBusy('');
    }
  };

  const submitReview = async () => {
    setBusy('submit-review');
    try {
      const { payload } = await persistCurrentDraft();
      const res = await api.adminContentSubmitReview(
        token,
        payload.lesson_id,
        reviewNote,
      );
      setWorkflow(res.workflow);
      toast.success('已提交审校');
    } catch (err: any) {
      toast.error(err?.message || '提交审校失败');
    } finally {
      setBusy('');
    }
  };

  const reviewDraft = async (decision: 'approve' | 'changes_requested') => {
    setBusy(decision === 'approve' ? 'approve' : 'request-changes');
    try {
      const res = await api.adminContentReview(
        token,
        editor.lesson_id,
        decision,
        reviewNote,
      );
      setWorkflow(res.workflow);
      toast.success(decision === 'approve' ? '审校已通过' : '已退回修改');
    } catch (err: any) {
      toast.error(err?.message || '审校操作失败');
    } finally {
      setBusy('');
    }
  };

  const savePersonAsset = async () => {
    setBusy('person-save');
    try {
      const payload = buildPersonAsset(personEditor);
      const res = await api.adminSavePersonAsset(token, payload);
      setPersonEditor(personToEditor(res.item));
      setAssetSavedAt(res.item.updated_at ? new Date(res.item.updated_at).toLocaleString() : new Date().toLocaleString());
      await refreshAssets();
      toast.success('人物档案已保存');
    } catch (err: any) {
      toast.error(err?.message || '人物档案保存失败');
    } finally {
      setBusy('');
    }
  };

  const saveKeywordAsset = async () => {
    setBusy('keyword-save');
    try {
      const payload = buildKeywordAsset(keywordEditor);
      const res = await api.adminSaveKeywordAsset(token, payload);
      setKeywordEditor(keywordToEditor(res.item));
      setAssetSavedAt(res.item.updated_at ? new Date(res.item.updated_at).toLocaleString() : new Date().toLocaleString());
      await refreshAssets();
      toast.success('关键词档案已保存');
    } catch (err: any) {
      toast.error(err?.message || '关键词档案保存失败');
    } finally {
      setBusy('');
    }
  };

  const sealDraft = async () => {
    setBusy('seal');
    try {
      const { payload } = await persistCurrentDraft();
      const res = await api.adminContentSeal(
        token,
        payload.lesson_id,
      );
      setPreview(res.item);
      setWorkflow(res.workflow);
      setSealedPath(res.record.path);
      setServerSavedAt(res.item.updated_at ? new Date(res.item.updated_at).toLocaleString() : new Date().toLocaleString());
      await refreshReleaseState(payload.course_id || '');
      toast.success('内容已封存，发布后学生端才会更新');
    } catch (err: any) {
      toast.error(err?.message || '封存失败');
    } finally {
      setBusy('');
    }
  };

  const publishSealed = async () => {
    if (!activeWorkflow?.sealed_version) return;
    setBusy('publish');
    try {
      const res = await api.adminContentPublish(
        token,
        activeWorkflow.lesson_id,
        activeWorkflow.sealed_version,
        reviewNote,
      );
      if (res.workflow) setWorkflow(res.workflow);
      setCurrentRelease(res.release);
      await refreshReleaseState(activeWorkflow.course_id);
      toast.success(`已发布课程版本 ${res.release.release_no}`);
    } catch (err: any) {
      toast.error(err?.message || '发布失败');
    } finally {
      setBusy('');
    }
  };

  const rollbackRelease = async () => {
    if (!selectedRelease || !activeWorkflow) return;
    setBusy('rollback');
    try {
      const res = await api.adminContentRollback(
        token,
        activeWorkflow.course_id,
        selectedRelease,
        reviewNote,
      );
      setCurrentRelease(res.release);
      await refreshWorkflowState(activeWorkflow.lesson_id, activeWorkflow.course_id);
      setSelectedRelease(undefined);
      toast.success(`已回滚并生成发布版本 ${res.release.release_no}`);
    } catch (err: any) {
      toast.error(err?.message || '回滚失败');
    } finally {
      setBusy('');
    }
  };

  const exportCurrent = () => {
    try {
      exportContentBundle(preview || buildPayload(editor));
      toast.success('文件包已导出');
    } catch (err: any) {
      toast.error(err?.message || '导出失败');
    }
  };

  const exportCurrentPerson = () => {
    try {
      exportPersonAsset(buildPersonAsset(personEditor));
      toast.success('人物档案已导出');
    } catch (err: any) {
      toast.error(err?.message || '人物档案导出失败');
    }
  };

  const exportCurrentKeyword = () => {
    try {
      exportKeywordAsset(buildKeywordAsset(keywordEditor));
      toast.success('关键词档案已导出');
    } catch (err: any) {
      toast.error(err?.message || '关键词档案导出失败');
    }
  };

  return (
    <div className="chrono-page" style={{ maxWidth: 1320, margin: '0 auto' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 320px), 1fr))', gap: 16, alignItems: 'end', marginBottom: 18 }}>
        <div>
          <div className="chrono-course-eyeline">
            <span>Admin</span>
            <span>/api/v1/admin/content</span>
          </div>
          <h1 className="chrono-title" style={{ margin: 0 }}>内容编辑器</h1>
        </div>
        <Space wrap style={{ justifyContent: 'flex-end', maxWidth: '100%' }}>
          <Input.Password
            aria-label="Admin token"
            value={token}
            onChange={(event) => rememberToken(event.target.value)}
            style={{ width: 220 }}
          />
        </Space>
      </div>

      <div className="chrono-card" style={{ padding: 12, marginBottom: 16 }}>
        <div className="chrono-course-eyeline" style={{ marginBottom: 8 }}>编辑对象</div>
        <Segmented
          value={editorMode}
          onChange={(value) => rememberEditorMode(value as EditorMode)}
          options={[
            { label: '课程内容', value: 'lesson' },
            { label: '人物档案', value: 'person' },
            { label: '关键词档案', value: 'keyword' },
            { label: '关卡规则', value: 'scenario' },
          ]}
        />
      </div>

      {editorMode === 'lesson' && (
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 420px), 1fr))', gap: 16, alignItems: 'start' }}>
        <section className="chrono-card" style={{ padding: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))', gap: 12 }}>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>课时 ID</div>
              <Input aria-label="课时 ID" value={editor.lesson_id} onChange={(event) => updateEditor({ lesson_id: event.target.value })} />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>课程 ID</div>
              <Input aria-label="课程 ID" value={editor.course_id} onChange={(event) => updateEditor({ course_id: event.target.value })} />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>课程名</div>
              <Input aria-label="课程名" value={editor.course_title} onChange={(event) => updateEditor({ course_title: event.target.value })} />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>标题</div>
              <Input aria-label="课时标题" value={editor.title} onChange={(event) => updateEditor({ title: event.target.value })} />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>单元</div>
              <Input aria-label="单元" value={editor.unit} onChange={(event) => updateEditor({ unit: event.target.value })} />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>时代</div>
              <Input aria-label="时代" value={editor.era} onChange={(event) => updateEditor({ era: event.target.value })} />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>课号</div>
              <Input aria-label="课号" value={editor.lesson_no} onChange={(event) => updateEditor({ lesson_no: event.target.value })} />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>时长</div>
              <Input aria-label="时长" value={editor.duration} onChange={(event) => updateEditor({ duration: event.target.value })} />
            </label>
          </div>

          <Divider style={{ margin: '16px 0 12px' }} />
          <div className="chrono-title" style={{ fontSize: 16, marginBottom: 10 }}>正文</div>
          <div
            style={{
              display: 'flex',
              gap: 8,
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              marginBottom: 8,
              padding: 8,
              border: '1px solid var(--border-soft)',
              borderRadius: 6,
              background: 'rgba(255, 253, 247, 0.72)',
            }}
          >
            <Space size={[6, 6]} wrap>
              {renderFormatButton('bold', '加粗', <BoldOutlined />)}
              {renderFormatButton('highlight', '标红', <HighlightOutlined />)}
              {renderFormatButton('keyword', '关键词', <TagsOutlined />)}
              <Select
                size="small"
                aria-label="标题级别"
                placeholder="标题级别"
                style={{ width: 116 }}
                onMouseDown={rememberBodySelection}
                onChange={(value) => applyBodyBlockFormat(value as BodyBlockFormat)}
                options={headingOptions}
              />
              <Select
                size="small"
                aria-label="字号"
                placeholder="字号"
                suffixIcon={<FontSizeOutlined />}
                style={{ width: 92 }}
                onMouseDown={rememberBodySelection}
                onChange={(value) => applyBodyInlineFormat(value as BodyInlineFormat)}
                options={sizeOptions}
              />
              <Select
                size="small"
                aria-label="标识颜色"
                placeholder="颜色"
                suffixIcon={<FontColorsOutlined />}
                style={{ width: 96 }}
                onMouseDown={rememberBodySelection}
                onChange={(value) => applyBodyInlineFormat(value as BodyInlineFormat)}
                options={colorOptions}
              />
              <Button size="small" icon={<BgColorsOutlined />} onMouseDown={(event) => { event.preventDefault(); rememberBodySelection(); }} onClick={() => applyBodyBlockFormat('focus')}>重点</Button>
              <Button size="small" onMouseDown={(event) => { event.preventDefault(); rememberBodySelection(); }} onClick={() => applyBodyBlockFormat('question')}>问题</Button>
              <Button size="small" onMouseDown={(event) => { event.preventDefault(); rememberBodySelection(); }} onClick={() => applyBodyBlockFormat('goal')}>目标</Button>
            </Space>
            <span style={{ color: 'var(--text-mute)', fontSize: 12 }}>选中文本后点按钮，或在正文里右键打开快捷格式菜单</span>
          </div>
          <TextArea
            ref={bodyTextAreaRef}
            aria-label="课文正文"
            value={editor.bodyText}
            onChange={(event) => updateEditor({ bodyText: event.target.value })}
            onSelect={rememberBodySelection}
            onKeyUp={rememberBodySelectionSoon}
            onMouseUp={rememberBodySelectionSoon}
            onClick={rememberBodySelectionSoon}
            onContextMenu={handleBodyContextMenu}
            autoSize={{ minRows: 10, maxRows: 18 }}
            style={{ ...baseInputStyle, fontSize: 15, lineHeight: 1.8 }}
          />
          {bodyContextMenu && (
            <div
              role="menu"
              aria-label="正文格式快捷菜单"
              onMouseDown={(event) => event.preventDefault()}
              onClick={(event) => event.stopPropagation()}
              style={{
                position: 'fixed',
                left: bodyContextMenu.x,
                top: bodyContextMenu.y,
                zIndex: 2400,
                width: 236,
                padding: 10,
                border: '1px solid var(--border-soft)',
                borderRadius: 6,
                background: 'var(--bg-card)',
                boxShadow: '0 14px 34px rgba(36, 28, 19, 0.18)',
              }}
            >
              <div className="chrono-course-eyeline" style={{ marginBottom: 8 }}>格式快捷菜单</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 6 }}>
                {renderFormatButton('bold', '加粗', <BoldOutlined />, bodyContextMenu.selection)}
                {renderFormatButton('highlight', '标红', <HighlightOutlined />, bodyContextMenu.selection)}
                {renderFormatButton('keyword', '关键词', <TagsOutlined />, bodyContextMenu.selection)}
                {renderFormatButton('large', '大字', <FontSizeOutlined />, bodyContextMenu.selection)}
                {renderFormatButton('red', '红色', <FontColorsOutlined />, bodyContextMenu.selection)}
                {renderFormatButton('blue', '蓝色', <FontColorsOutlined />, bodyContextMenu.selection)}
              </div>
              <Divider style={{ margin: '10px 0' }} />
              <Space size={[6, 6]} wrap>
                <Button size="small" onClick={() => applyBodyBlockFormat('heading2', bodyContextMenu.selection)}>二级标题</Button>
                <Button size="small" onClick={() => applyBodyBlockFormat('heading3', bodyContextMenu.selection)}>三级标题</Button>
                <Button size="small" onClick={() => applyBodyBlockFormat('focus', bodyContextMenu.selection)}>重点</Button>
                <Button size="small" onClick={() => applyBodyBlockFormat('question', bodyContextMenu.selection)}>问题</Button>
              </Space>
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: 12, marginTop: 14 }}>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>关键词</div>
              <TextArea
                aria-label="关键词"
                value={editor.keywordsText}
                onChange={(event) => updateEditor({ keywordsText: event.target.value })}
                autoSize={{ minRows: 5, maxRows: 9 }}
              />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>重点块</div>
              <TextArea
                aria-label="重点块"
                value={editor.focusText}
                onChange={(event) => updateEditor({ focusText: event.target.value })}
                autoSize={{ minRows: 5, maxRows: 9 }}
              />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>可追问</div>
              <TextArea
                aria-label="可追问"
                value={editor.qaText}
                onChange={(event) => updateEditor({ qaText: event.target.value })}
                autoSize={{ minRows: 5, maxRows: 9 }}
              />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>关卡目标</div>
              <TextArea
                aria-label="关卡目标"
                value={editor.goalsText}
                onChange={(event) => updateEditor({ goalsText: event.target.value })}
                autoSize={{ minRows: 5, maxRows: 9 }}
              />
            </label>
          </div>

          <Divider style={{ margin: '16px 0 12px' }} />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 280px), 1fr))', gap: 12 }}>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>人物</div>
              <TextArea aria-label="人物" value={editor.peopleText} onChange={(event) => updateEditor({ peopleText: event.target.value })} autoSize={{ minRows: 4, maxRows: 8 }} />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>地图点</div>
              <TextArea aria-label="地图点" value={editor.mapText} onChange={(event) => updateEditor({ mapText: event.target.value })} autoSize={{ minRows: 4, maxRows: 8 }} />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>参考资料</div>
              <TextArea aria-label="参考资料" value={editor.sourcesText} onChange={(event) => updateEditor({ sourcesText: event.target.value })} autoSize={{ minRows: 4, maxRows: 8 }} />
            </label>
          </div>

          <details style={{ marginTop: 14 }}>
            <summary className="chrono-course-eyeline">AI 素材</summary>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 240px), 1fr))', gap: 12, marginTop: 10 }}>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>Saga</div>
                <Input aria-label="Saga 标题" value={editor.sagaTitle} onChange={(event) => updateEditor({ sagaTitle: event.target.value })} />
              </label>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>Saga 目标</div>
                <Input aria-label="Saga 目标" value={editor.sagaObjective} onChange={(event) => updateEditor({ sagaObjective: event.target.value })} />
              </label>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>Sandbox</div>
                <Input aria-label="Sandbox 标题" value={editor.sandboxTitle} onChange={(event) => updateEditor({ sandboxTitle: event.target.value })} />
              </label>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>Sandbox 目标</div>
                <Input aria-label="Sandbox 目标" value={editor.sandboxObjective} onChange={(event) => updateEditor({ sandboxObjective: event.target.value })} />
              </label>
            </div>
            <TextArea aria-label="备注" value={editor.teacher_notes} onChange={(event) => updateEditor({ teacher_notes: event.target.value })} autoSize={{ minRows: 3, maxRows: 6 }} style={{ marginTop: 10 }} />
          </details>
        </section>

        <aside className="chrono-card" style={{ padding: 16 }}>
          <div style={{ marginBottom: 12 }}>
            <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>课程规划</div>
            <Select
              aria-label="课程规划"
              placeholder="选择已整理的课程路径"
              showSearch
              optionFilterProp="label"
              style={{ width: '100%' }}
              onChange={applyBlueprint}
              options={LESSON_BLUEPRINTS.map((item) => ({
                value: item.id,
                label: `${item.lesson_no} · ${item.era} · ${item.title}`,
              }))}
            />
          </div>

          <div style={{ marginBottom: 12 }}>
            <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>已有课程初稿</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <Select
                aria-label="已有课程初稿"
                placeholder="读取已实装课程的一稿"
                showSearch
                optionFilterProp="label"
                value={selectedSourceLesson}
                onChange={setSelectedSourceLesson}
                style={{ flex: 1 }}
                options={sourceLessons.map((item) => ({
                  value: item.lesson_id,
                  label: `${item.lesson_id} · ${item.lesson_no} · ${item.course_title} · ${item.title}`,
                }))}
              />
              <Button loading={busy === 'source'} disabled={!selectedSourceLesson} onClick={loadSourceLesson}>读取</Button>
            </div>
          </div>

          <Space wrap style={{ marginBottom: 12 }}>
            <Button icon={<FileTextOutlined />} onClick={createNew}>新建</Button>
            <Button icon={<FileTextOutlined />} loading={busy === 'template'} onClick={loadTemplate}>模板</Button>
            <Button icon={<BookOutlined />} onClick={() => setShowGuide((value) => !value)}>文档</Button>
            <Button icon={<ReloadOutlined />} onClick={parseFocusBlocks}>解析重点</Button>
            <Button icon={<EyeOutlined />} loading={busy === 'preview'} onClick={previewContent}>预览</Button>
            <Button type="primary" icon={<SaveOutlined />} loading={busy === 'save'} onClick={saveDraft}>保存草稿</Button>
            <Button icon={<DownloadOutlined />} onClick={exportCurrent}>导出文件包</Button>
          </Space>

          {showGuide && (
            <div style={{ border: '1px solid var(--border-soft)', borderRadius: 6, padding: 12, marginBottom: 12, background: 'var(--bg-warm-soft)' }}>
              <div className="chrono-title" style={{ fontSize: 14, marginBottom: 8 }}>教师填写文档</div>
              <div style={{ fontSize: 12, color: 'var(--text-mute)', lineHeight: 1.7 }}>
                <p><strong>课程 ID</strong>：同一门课共用，例如 <code>C-qin-han</code>。选“课程规划”会自动填写。</p>
                <p><strong>课时 ID</strong>：每节课唯一，只用英文、数字、短横线；封存文件会用它命名。</p>
                <p><strong>正文语法</strong>：优先用正文上方工具条或右键快捷菜单；底层会写成 <code>【关键词】</code>、<code>**加粗**</code>、<code>==标红==</code>、<code>{'{{红色:文字}}'}</code>、<code>{'{{大字:文字}}'}</code>、<code>## 标题</code>，封存和导出会保留这些格式层标记。</p>
                <p><strong>关键词</strong>：一行一条，可写“词语 | 释义”或“词语 | 拼音 | 释义”。<strong>人物/地图点/资料</strong>同样一行一条，用 <code>|</code> 分列。人物：姓名 | 身份 | 摘要 | persona。地图：地点 | 区域 | 说明 | 类型。资料：标题 | 来源 | 链接 | 引文说明。</p>
                <p><strong>保存草稿</strong>：写入 <code>content/drafts</code>，可在草稿库重新打开。内容需依次完成校验、审校通过和封存；只有点击发布后，学生课程页才会更新。</p>
                <div style={{ marginTop: 8 }}>
                  <strong>时代写作要求</strong>
                  <ul style={{ paddingLeft: 18, margin: '6px 0 0' }}>
                    {ERA_GUIDE.map((item) => (
                      <li key={item.id}><span style={{ color: 'var(--text-dark)' }}>{item.name}</span>：{item.needs}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}

          <div style={{ borderTop: '1px solid var(--border-soft)', borderBottom: '1px solid var(--border-soft)', padding: '12px 0', marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', marginBottom: 10, flexWrap: 'wrap' }}>
              <div className="chrono-course-eyeline">审校与发布</div>
              <Space size={[6, 6]} wrap>
                {activeWorkflow ? (
                  <Tag color={WORKFLOW_STATE_META[activeWorkflow.state].color}>
                    {WORKFLOW_STATE_META[activeWorkflow.state].label}
                  </Tag>
                ) : (
                  <Tag>尚未保存</Tag>
                )}
                {activeWorkflow && <Tag>修订 {activeWorkflow.revision}</Tag>}
                {activeWorkflow?.sealed_version && <Tag color="blue">封存 v{activeWorkflow.sealed_version}</Tag>}
                {activeWorkflow?.published_version && <Tag color="green">线上 v{activeWorkflow.published_version}</Tag>}
              </Space>
            </div>

            <Space size={[6, 8]} wrap style={{ marginBottom: 10 }}>
              <Button
                icon={<SafetyCertificateOutlined />}
                loading={busy === 'validate'}
                onClick={validateDraft}
              >
                校验
              </Button>
              <Button
                icon={<SendOutlined />}
                loading={busy === 'submit-review'}
                disabled={!activeWorkflow || !['validated', 'changes_requested'].includes(activeWorkflow.state)}
                onClick={submitReview}
              >
                提交审校
              </Button>
              <Button
                icon={<CheckCircleOutlined />}
                loading={busy === 'approve'}
                disabled={activeWorkflow?.state !== 'in_review'}
                onClick={() => reviewDraft('approve')}
              >
                通过
              </Button>
              <Button
                danger
                icon={<CloseCircleOutlined />}
                loading={busy === 'request-changes'}
                disabled={activeWorkflow?.state !== 'in_review' || !reviewNote.trim()}
                onClick={() => reviewDraft('changes_requested')}
              >
                退回
              </Button>
              <Button
                icon={<LockOutlined />}
                loading={busy === 'seal'}
                disabled={activeWorkflow?.state !== 'approved'}
                onClick={sealDraft}
              >
                封存
              </Button>
              <Button
                type="primary"
                icon={<RocketOutlined />}
                loading={busy === 'publish'}
                disabled={activeWorkflow?.state !== 'sealed' || !activeWorkflow.sealed_version}
                onClick={publishSealed}
              >
                发布
              </Button>
            </Space>

            <TextArea
              aria-label="审校与发布备注"
              placeholder="审校或发布备注；退回时必须填写"
              autoSize={{ minRows: 2, maxRows: 4 }}
              value={reviewNote}
              onChange={(event) => setReviewNote(event.target.value)}
              style={{ marginBottom: 10 }}
            />

            {activeWorkflow?.validation?.issues && activeWorkflow.validation.issues.length > 0 && (
              <div style={{ display: 'grid', gap: 6, marginBottom: 10 }}>
                {activeWorkflow.validation.issues.map((issue, index) => (
                  <div key={`${issue.code}-${issue.field}-${index}`} style={{ display: 'flex', gap: 6, alignItems: 'flex-start', fontSize: 12, lineHeight: 1.55 }}>
                    <Tag color={issue.severity === 'error' ? 'red' : 'gold'} style={{ margin: 0 }}>
                      {issue.severity === 'error' ? '阻断' : '建议'}
                    </Tag>
                    <span>
                      <code>{issue.field}</code>：{VALIDATION_ISSUE_TEXT[issue.code] || issue.message}
                    </span>
                  </div>
                ))}
              </div>
            )}

            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              {activeRelease ? (
                <Tag color="green">当前发布 #{activeRelease.release_no} · {releaseOperationLabel(activeRelease.operation)}</Tag>
              ) : (
                <Tag>暂无课程发布清单</Tag>
              )}
              <Select
                aria-label="历史发布版本"
                placeholder="选择历史发布版本"
                value={selectedRelease}
                onChange={setSelectedRelease}
                style={{ flex: '1 1 220px', minWidth: 0 }}
                options={releases
                  .filter((item) => item.release_id !== activeRelease?.release_id)
                  .slice()
                  .reverse()
                  .map((item) => ({
                    value: item.release_id,
                    label: `#${item.release_no} · ${releaseOperationLabel(item.operation)} · ${item.items.length} 节`,
                  }))}
              />
              <Button
                danger
                icon={<RollbackOutlined />}
                loading={busy === 'rollback'}
                disabled={!selectedRelease || !activeWorkflow}
                onClick={rollbackRelease}
              >
                回滚
              </Button>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <Select
              aria-label="草稿库"
              placeholder="草稿库"
              value={selectedDraft}
                onChange={setSelectedDraft}
                showSearch
                optionFilterProp="label"
                style={{ flex: 1 }}
              options={drafts.map((draft) => ({
                value: draft.lesson_id,
                label: `${draft.title || draft.lesson_id} · ${draft.lesson_id}`,
              }))}
            />
            <Button loading={busy === 'load'} disabled={!selectedDraft} onClick={loadSelectedDraft}>打开</Button>
            <Button icon={<ReloadOutlined />} loading={busy === 'drafts'} onClick={refreshDrafts} />
          </div>

          <Space size={[6, 6]} wrap style={{ marginBottom: 12 }}>
            <Tag color="blue">{editor.lesson_id}</Tag>
            {localSavedAt && <Tag>本地暂存 {localSavedAt}</Tag>}
            {serverSavedAt && <Tag color="green">服务器草稿 {serverSavedAt}</Tag>}
            {preview?.status === 'sealed' && <Tag color="green">sealed v{preview.version}</Tag>}
          </Space>

          {sealedPath && (
            <div style={{ marginBottom: 12 }}>
              <Tag color="green">{sealedPath}</Tag>
            </div>
          )}

          {activeWorkflow?.published_version && (
            <div style={{ marginBottom: 12 }}>
              <Link to={`/courses/${activeWorkflow.course_id}/lessons/${activeWorkflow.lesson_id}?layer=watch`}>
                打开已发布课程页 v{activeWorkflow.published_version}
              </Link>
            </div>
          )}

          <Divider style={{ margin: '12px 0' }} />
          {preview || currentPayload ? (
            <div style={{ color: 'var(--text-dark)', lineHeight: 1.75 }}>
              <strong>{(preview || currentPayload)?.title || '未命名课时'}</strong>
              <div style={{ color: 'var(--text-mute)', fontSize: 12 }}>
                {(preview || currentPayload)?.unit} · {(preview || currentPayload)?.era}
              </div>
              <Space size={[6, 6]} wrap style={{ marginTop: 12 }}>
                <Tag>正文 {(preview || currentPayload)?.body?.length ?? 0}</Tag>
                <Tag>关键词 {(preview || currentPayload)?.keywords?.length ?? 0}</Tag>
                <Tag>重点 {(preview || currentPayload)?.facts?.length ?? 0}</Tag>
                <Tag>人物 {(preview || currentPayload)?.people?.length ?? 0}</Tag>
                <Tag>资料 {(preview || currentPayload)?.source_refs?.length ?? 0}</Tag>
              </Space>
              <details style={{ marginTop: 14 }}>
                <summary className="chrono-course-eyeline">JSON</summary>
                <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: '10px 0 0', fontSize: 11, color: 'var(--text-mute)' }}>
                  {formatJson(preview || currentPayload)}
                </pre>
              </details>
            </div>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无预览" />
          )}
        </aside>
      </div>
      )}

      {editorMode === 'scenario' && (
        <ScenarioRuleEditor
          token={token}
          sourceLessons={sourceLessons}
          runtimeScenarios={runtimeScenarios}
          onRefreshRuntimeScenarios={refreshRuntimeScenarios}
        />
      )}

      {editorMode === 'person' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(min(100%, 360px), 0.45fr)', gap: 16, alignItems: 'start' }}>
          <section className="chrono-card" style={{ padding: 16 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))', gap: 12 }}>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>档案 ID</div>
                <Input aria-label="人物档案 ID" value={personEditor.asset_id} onChange={(event) => updatePersonEditor({ asset_id: event.target.value })} />
              </label>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>人物姓名</div>
                <Input aria-label="人物姓名" value={personEditor.name} onChange={(event) => updatePersonEditor({ name: event.target.value })} />
              </label>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>身份/立场</div>
                <Input aria-label="人物身份" value={personEditor.role} onChange={(event) => updatePersonEditor({ role: event.target.value })} />
              </label>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>时代</div>
                <Input aria-label="人物时代" value={personEditor.era} onChange={(event) => updatePersonEditor({ era: event.target.value })} />
              </label>
            </div>
            <Divider style={{ margin: '16px 0 12px' }} />
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>学生可读摘要</div>
              <TextArea aria-label="人物摘要" value={personEditor.summary} onChange={(event) => updatePersonEditor({ summary: event.target.value })} autoSize={{ minRows: 4, maxRows: 8 }} />
            </label>
            <label>
              <div className="chrono-course-eyeline" style={{ margin: '12px 0 6px' }}>AI persona</div>
              <TextArea aria-label="人物 persona" value={personEditor.persona} onChange={(event) => updatePersonEditor({ persona: event.target.value })} autoSize={{ minRows: 5, maxRows: 9 }} />
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: 12, marginTop: 12 }}>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>史实边界</div>
                <TextArea aria-label="人物史实边界" value={personEditor.boundariesText} onChange={(event) => updatePersonEditor({ boundariesText: event.target.value })} autoSize={{ minRows: 4, maxRows: 8 }} />
              </label>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>关联关键词</div>
                <TextArea aria-label="人物关联关键词" value={personEditor.keywordsText} onChange={(event) => updatePersonEditor({ keywordsText: event.target.value })} autoSize={{ minRows: 4, maxRows: 8 }} />
              </label>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>关联课时</div>
                <TextArea aria-label="人物关联课时" value={personEditor.relatedLessonsText} onChange={(event) => updatePersonEditor({ relatedLessonsText: event.target.value })} autoSize={{ minRows: 4, maxRows: 8 }} />
              </label>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>参考资料</div>
                <TextArea aria-label="人物参考资料" value={personEditor.sourcesText} onChange={(event) => updatePersonEditor({ sourcesText: event.target.value })} autoSize={{ minRows: 4, maxRows: 8 }} />
              </label>
            </div>
            <label>
              <div className="chrono-course-eyeline" style={{ margin: '12px 0 6px' }}>教师备注</div>
              <TextArea aria-label="人物教师备注" value={personEditor.teacher_notes} onChange={(event) => updatePersonEditor({ teacher_notes: event.target.value })} autoSize={{ minRows: 3, maxRows: 6 }} />
            </label>
          </section>

          <aside className="chrono-card" style={{ padding: 16 }}>
            <Space wrap style={{ marginBottom: 12 }}>
              <Button icon={<FileTextOutlined />} onClick={loadPersonTemplate} loading={busy === 'person-template'}>模板</Button>
              <Button type="primary" icon={<SaveOutlined />} onClick={savePersonAsset} loading={busy === 'person-save'}>保存档案</Button>
              <Button icon={<DownloadOutlined />} onClick={exportCurrentPerson}>导出</Button>
              <Button icon={<ReloadOutlined />} onClick={refreshAssets}>刷新</Button>
            </Space>
            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              <Select
                aria-label="人物档案库"
                placeholder="人物档案库"
                value={selectedPersonAsset}
                onChange={setSelectedPersonAsset}
                showSearch
                optionFilterProp="label"
                style={{ flex: 1 }}
                options={assets.filter((item) => item.kind === 'person').map((item) => ({
                  value: item.asset_id,
                  label: `${item.title} · ${item.asset_id}`,
                }))}
              />
              <Button loading={busy === 'person-load'} disabled={!selectedPersonAsset} onClick={loadPersonAsset}>打开</Button>
            </div>
            <Space size={[6, 6]} wrap style={{ marginBottom: 12 }}>
              <Tag color="blue">{personEditor.asset_id}</Tag>
              {assetSavedAt && <Tag color="green">已保存 {assetSavedAt}</Tag>}
            </Space>
            {currentPersonAsset ? (
              <div style={{ lineHeight: 1.75 }}>
                <strong>{currentPersonAsset.name}</strong>
                <div style={{ color: 'var(--text-mute)', fontSize: 12 }}>{currentPersonAsset.era} · {currentPersonAsset.role}</div>
                <Space size={[6, 6]} wrap style={{ marginTop: 12 }}>
                  <Tag>边界 {currentPersonAsset.boundaries?.length ?? 0}</Tag>
                  <Tag>关键词 {currentPersonAsset.keywords?.length ?? 0}</Tag>
                  <Tag>课时 {currentPersonAsset.related_lessons?.length ?? 0}</Tag>
                  <Tag>资料 {currentPersonAsset.source_refs?.length ?? 0}</Tag>
                </Space>
              </div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请填写人物姓名" />
            )}
          </aside>
        </div>
      )}

      {editorMode === 'keyword' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(min(100%, 360px), 0.45fr)', gap: 16, alignItems: 'start' }}>
          <section className="chrono-card" style={{ padding: 16 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))', gap: 12 }}>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>档案 ID</div>
                <Input aria-label="关键词档案 ID" value={keywordEditor.asset_id} onChange={(event) => updateKeywordEditor({ asset_id: event.target.value })} />
              </label>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>关键词</div>
                <Input aria-label="关键词词条" value={keywordEditor.word} onChange={(event) => updateKeywordEditor({ word: event.target.value })} />
              </label>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>拼音</div>
                <Input aria-label="关键词拼音" value={keywordEditor.pinyin} onChange={(event) => updateKeywordEditor({ pinyin: event.target.value })} />
              </label>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>分类</div>
                <Input aria-label="关键词分类" value={keywordEditor.category} onChange={(event) => updateKeywordEditor({ category: event.target.value })} />
              </label>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>时代</div>
                <Input aria-label="关键词时代" value={keywordEditor.era} onChange={(event) => updateKeywordEditor({ era: event.target.value })} />
              </label>
            </div>
            <Divider style={{ margin: '16px 0 12px' }} />
            <label>
              <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>学生可读解释</div>
              <TextArea aria-label="关键词解释" value={keywordEditor.gloss} onChange={(event) => updateKeywordEditor({ gloss: event.target.value })} autoSize={{ minRows: 4, maxRows: 8 }} />
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: 12, marginTop: 12 }}>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>课堂用法</div>
                <TextArea aria-label="关键词课堂用法" value={keywordEditor.examplesText} onChange={(event) => updateKeywordEditor({ examplesText: event.target.value })} autoSize={{ minRows: 4, maxRows: 8 }} />
              </label>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>关联人物</div>
                <TextArea aria-label="关键词关联人物" value={keywordEditor.relatedPeopleText} onChange={(event) => updateKeywordEditor({ relatedPeopleText: event.target.value })} autoSize={{ minRows: 4, maxRows: 8 }} />
              </label>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>关联课时</div>
                <TextArea aria-label="关键词关联课时" value={keywordEditor.relatedLessonsText} onChange={(event) => updateKeywordEditor({ relatedLessonsText: event.target.value })} autoSize={{ minRows: 4, maxRows: 8 }} />
              </label>
              <label>
                <div className="chrono-course-eyeline" style={{ marginBottom: 6 }}>参考资料</div>
                <TextArea aria-label="关键词参考资料" value={keywordEditor.sourcesText} onChange={(event) => updateKeywordEditor({ sourcesText: event.target.value })} autoSize={{ minRows: 4, maxRows: 8 }} />
              </label>
            </div>
            <label>
              <div className="chrono-course-eyeline" style={{ margin: '12px 0 6px' }}>教师备注</div>
              <TextArea aria-label="关键词教师备注" value={keywordEditor.teacher_notes} onChange={(event) => updateKeywordEditor({ teacher_notes: event.target.value })} autoSize={{ minRows: 3, maxRows: 6 }} />
            </label>
          </section>

          <aside className="chrono-card" style={{ padding: 16 }}>
            <Space wrap style={{ marginBottom: 12 }}>
              <Button icon={<FileTextOutlined />} onClick={loadKeywordTemplate} loading={busy === 'keyword-template'}>模板</Button>
              <Button type="primary" icon={<SaveOutlined />} onClick={saveKeywordAsset} loading={busy === 'keyword-save'}>保存档案</Button>
              <Button icon={<DownloadOutlined />} onClick={exportCurrentKeyword}>导出</Button>
              <Button icon={<ReloadOutlined />} onClick={refreshAssets}>刷新</Button>
            </Space>
            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              <Select
                aria-label="关键词档案库"
                placeholder="关键词档案库"
                value={selectedKeywordAsset}
                onChange={setSelectedKeywordAsset}
                showSearch
                optionFilterProp="label"
                style={{ flex: 1 }}
                options={assets.filter((item) => item.kind === 'keyword').map((item) => ({
                  value: item.asset_id,
                  label: `${item.title} · ${item.asset_id}`,
                }))}
              />
              <Button loading={busy === 'keyword-load'} disabled={!selectedKeywordAsset} onClick={loadKeywordAsset}>打开</Button>
            </div>
            <Space size={[6, 6]} wrap style={{ marginBottom: 12 }}>
              <Tag color="blue">{keywordEditor.asset_id}</Tag>
              {assetSavedAt && <Tag color="green">已保存 {assetSavedAt}</Tag>}
            </Space>
            {currentKeywordAsset ? (
              <div style={{ lineHeight: 1.75 }}>
                <strong>{currentKeywordAsset.word}</strong>
                <div style={{ color: 'var(--text-mute)', fontSize: 12 }}>{currentKeywordAsset.era} · {currentKeywordAsset.category}</div>
                <Space size={[6, 6]} wrap style={{ marginTop: 12 }}>
                  <Tag>用法 {currentKeywordAsset.examples?.length ?? 0}</Tag>
                  <Tag>人物 {currentKeywordAsset.related_people?.length ?? 0}</Tag>
                  <Tag>课时 {currentKeywordAsset.related_lessons?.length ?? 0}</Tag>
                  <Tag>资料 {currentKeywordAsset.source_refs?.length ?? 0}</Tag>
                </Space>
              </div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请填写关键词和解释" />
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
