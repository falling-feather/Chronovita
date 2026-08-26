import { publicAssetUrl } from '../../runtime';

export const COURSE_COVER_IDS = [
  'C-prequin-state',
  'C-prequin-thought',
  'C-prequin-unify',
  'C-qinhan-founding',
  'C-qinhan-thought',
  'C-weijin-fusion',
  'C-suitang-system',
  'C-suitang-tang',
  'C-suitang-culture',
  'C-songyuan-song',
  'C-songyuan-mongol',
  'C-mingqing-system',
  'C-mingqing-global',
  'C-mingqing-thought',
  'C-mingqing-late',
] as const;

export type CourseCoverId = (typeof COURSE_COVER_IDS)[number];
export type CourseCoverWidth = 720 | 1440;

interface CourseCoverMeta {
  focus: string;
}

const COURSE_COVER_ID_SET = new Set<string>(COURSE_COVER_IDS);
const COURSE_COVER_ROOT = '/assets/courses/covers';

export const COURSE_COVER_META: Record<CourseCoverId, CourseCoverMeta> = {
  'C-prequin-state': { focus: '50% 58%' },
  'C-prequin-thought': { focus: '54% 56%' },
  'C-prequin-unify': { focus: '50% 52%' },
  'C-qinhan-founding': { focus: '52% 56%' },
  'C-qinhan-thought': { focus: '55% 54%' },
  'C-weijin-fusion': { focus: '50% 57%' },
  'C-suitang-system': { focus: '53% 54%' },
  'C-suitang-tang': { focus: '52% 54%' },
  'C-suitang-culture': { focus: '53% 56%' },
  'C-songyuan-song': { focus: '52% 54%' },
  'C-songyuan-mongol': { focus: '50% 57%' },
  'C-mingqing-system': { focus: '52% 55%' },
  'C-mingqing-global': { focus: '52% 55%' },
  'C-mingqing-thought': { focus: '52% 57%' },
  'C-mingqing-late': { focus: '51% 56%' },
};

export function isCourseCoverId(courseId: string): courseId is CourseCoverId {
  return COURSE_COVER_ID_SET.has(courseId);
}

export function courseCoverUrl(courseId: CourseCoverId, width: CourseCoverWidth, format: 'avif' | 'webp') {
  return publicAssetUrl(`${COURSE_COVER_ROOT}/${courseId}-${width}.${format}`);
}
