export interface ShijiChapterSummary {
  id: string;
  title: string;
  title_traditional?: string;
  preview?: string;
  runtime_path?: string;
}

export interface ShijiVolumeSummary {
  volume_no: number;
  volume_id: string;
  title: string;
  title_traditional?: string;
  category?: string;
  status?: string;
  preview?: string;
  chapters: ShijiChapterSummary[];
}

export interface ShijiNavigation {
  book_id: string;
  title: string;
  application_status: string;
  publication: { ai_status?: string; human_status?: string; state?: string };
  manifest_sha256: string;
  total_volumes: number;
  volumes: ShijiVolumeSummary[];
}

export interface ShijiSentence {
  sentence_id: string;
  simplified?: string;
  traditional?: string;
  translation?: string;
  raw_ocr?: string | null;
  raw_ocr_available?: boolean;
  source_span_ids?: string[];
  source_layer?: string;
}

export interface ShijiChapterPayload {
  chapter_id: string;
  sentences?: ShijiSentence[];
  source?: Record<string, unknown>;
  annotation_warnings?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface ShijiChapterResponse {
  book_id: string;
  volume: { volume_no: number; volume_id: string; title: string; category?: string };
  manifest_sha256: string;
  chapter_meta: ShijiChapterSummary;
  payload: { chapter?: ShijiChapterPayload; [key: string]: unknown };
}

async function readJson<T>(path: string): Promise<T> {
  const response = await fetch(`/api/v1/shiji${path}`, { credentials: 'include' });
  if (!response.ok) {
    let detail = `《史记》阅读请求失败（${response.status}）`;
    try {
      const body = await response.json() as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Keep the stable fallback message.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export function getShijiNavigation() {
  return readJson<ShijiNavigation>('/manifest');
}

export function getShijiChapter(chapterId: string) {
  return readJson<ShijiChapterResponse>(`/chapters/${encodeURIComponent(chapterId)}?sentence_limit=2000`);
}
