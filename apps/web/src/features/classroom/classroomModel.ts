import type { Lesson, LessonPresentationResponse } from '../../utils/api';

export type ClassroomLayer = 'watch' | 'practice' | 'ask' | 'create';

export interface ClassroomStage {
  layer: ClassroomLayer;
  index: number;
  title: string;
  verb: string;
  duration: string;
  purpose: string;
}

export const CLASSROOM_STAGES: ClassroomStage[] = [
  {
    layer: 'watch', index: 1, title: '踏勘', verb: '观察证据', duration: '8–10 分钟',
    purpose: '阅读课文、辨认材料层次并观看课堂短片',
  },
  {
    layer: 'practice', index: 2, title: '抉择', verb: '干预局势', duration: '12–15 分钟',
    purpose: '在六回合关卡中权衡目标、代价与群体处境',
  },
  {
    layer: 'ask', index: 3, title: '召见', verb: '追问依据', duration: '5–8 分钟',
    purpose: '向专家或课程人物提问，并核对证据引用',
  },
  {
    layer: 'create', index: 4, title: '卷宗', verb: '复盘解释', duration: '8–10 分钟',
    purpose: '整理选择轨迹、历史解释并导入知识画板',
  },
];

export const CLASSROOM_PRINCIPLES = [
  { title: '可观察', description: '传说、文献、考古与教学解释分层呈现。' },
  { title: '可干预', description: '在历史约束中做出选择，不预设唯一正确答案。' },
  { title: '可反馈', description: '变量、人物信任、事件与代价随回合变化。' },
  { title: '可复盘', description: '把关键选择、证据与解释沉淀为个人卷宗。' },
] as const;

export const FLAGSHIP_LESSON_IDS = new Set(['L101', 'L103']);

export function isFlagshipLesson(lessonId: string): boolean {
  return FLAGSHIP_LESSON_IDS.has(lessonId);
}

export function classroomStage(layer: string | null | undefined): ClassroomStage {
  return CLASSROOM_STAGES.find((stage) => stage.layer === layer) ?? CLASSROOM_STAGES[0];
}

export function presentationStageDuration(
  stage: ClassroomStage,
  presentation?: LessonPresentationResponse | null,
): string {
  if (!presentation) return stage.duration;
  const key = {
    watch: 'observe', practice: 'decide', ask: 'consult', create: 'dossier',
  }[stage.layer] as keyof LessonPresentationResponse['presentation']['phase_minutes'];
  return `${presentation.presentation.phase_minutes[key]} 分钟`;
}

export function lessonQuestionSeeds(lesson: Lesson): string[] {
  const explicit = (lesson.qa_points ?? []).map((question) => question.trim()).filter(Boolean);
  if (explicit.length > 0) return explicit.slice(0, 4);
  return [
    `${lesson.title}中哪些判断有直接材料支持？`,
    '这项选择保护了谁，又让谁承担了代价？',
    '如果证据发生变化，哪一项历史解释需要修改？',
  ];
}

export function progressLayerLabel(layer: string): string {
  return classroomStage(layer).title;
}
