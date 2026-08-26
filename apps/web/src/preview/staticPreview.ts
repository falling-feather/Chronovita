import type {
  CourseDetail,
  CourseSummary,
  Era,
  Lesson,
  LessonPresentationResponse,
} from '../utils/api';
import { publicAssetUrl } from '../runtime';

interface StaticPreviewDataset {
  schema_version: 'chronovita-pages-preview/v1';
  release_identity: string;
  eras: Era[];
  courses: CourseSummary[];
  course_details: Record<string, CourseDetail>;
  lessons: Record<string, Lesson>;
  presentations: Record<string, LessonPresentationResponse>;
}

let datasetPromise: Promise<StaticPreviewDataset> | null = null;

function dataset(): Promise<StaticPreviewDataset> {
  if (!datasetPromise) {
    datasetPromise = fetch(publicAssetUrl('/preview/preview-data-v1.json'))
      .then(async (response) => {
        if (!response.ok) throw new Error(`静态课程数据载入失败（${response.status}）`);
        return response.json() as Promise<StaticPreviewDataset>;
      });
  }
  return datasetPromise;
}

function presentationWithPublicAssets(
  response: LessonPresentationResponse,
): LessonPresentationResponse {
  return {
    ...response,
    asset_urls: {
      video: publicAssetUrl(response.asset_urls.video),
      poster: publicAssetUrl(response.asset_urls.poster),
      transcript: publicAssetUrl(response.asset_urls.transcript),
    },
  };
}

function staticPreviewUnavailable(path: string): never {
  throw new Error(`GitHub Pages 只读预览未连接课堂服务：${path}`);
}

export async function staticPreviewJsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method || 'GET').toUpperCase();
  if (method !== 'GET') return staticPreviewUnavailable(path);

  const source = await dataset();
  const url = new URL(path, 'https://chronovita.preview.invalid');
  const pathname = url.pathname.replace(/\/$/, '') || '/';

  if (pathname === '/courses/eras') return { items: source.eras } as T;

  if (pathname === '/courses') {
    const era = url.searchParams.get('era');
    const section = url.searchParams.get('section');
    const q = url.searchParams.get('q')?.trim().toLocaleLowerCase('zh-CN');
    const items = source.courses.filter((course) => (
      (!era || era === 'all' || course.era_id === era)
      && (!section || section === 'all' || course.section === section)
      && (!q || course.title.toLocaleLowerCase('zh-CN').includes(q)
        || course.subtitle.toLocaleLowerCase('zh-CN').includes(q))
    ));
    return { items, total: items.length } as T;
  }

  if (pathname === '/learning/progress') return { items: [] } as T;
  if (pathname === '/learning/progress/latest') return { item: null } as T;

  const presentationMatch = pathname.match(/^\/courses\/([^/]+)\/lessons\/([^/]+)\/presentation$/);
  if (presentationMatch) {
    const key = `${decodeURIComponent(presentationMatch[1])}/${decodeURIComponent(presentationMatch[2])}`;
    const response = source.presentations[key];
    if (!response) return staticPreviewUnavailable(path);
    return presentationWithPublicAssets(response) as T;
  }

  const lessonMatch = pathname.match(/^\/courses\/([^/]+)\/lessons\/([^/]+)$/);
  if (lessonMatch) {
    const key = `${decodeURIComponent(lessonMatch[1])}/${decodeURIComponent(lessonMatch[2])}`;
    const lesson = source.lessons[key];
    if (!lesson) return staticPreviewUnavailable(path);
    return lesson as T;
  }

  const courseMatch = pathname.match(/^\/courses\/([^/]+)$/);
  if (courseMatch) {
    const course = source.course_details[decodeURIComponent(courseMatch[1])];
    if (!course) return staticPreviewUnavailable(path);
    return course as T;
  }

  return staticPreviewUnavailable(path);
}
