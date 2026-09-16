import { afterEach, expect, test, vi } from 'vitest';

afterEach(() => { vi.unstubAllGlobals(); vi.resetModules(); });

test('失败的目录请求可以重试，成功后复用只读快照', async () => {
  const fetch = vi.fn().mockRejectedValueOnce(new TypeError('offline'))
    .mockResolvedValue({ ok: true, json: async () => ({ eras: [] }) });
  vi.stubGlobal('fetch', fetch);
  const { staticPreviewJsonFetch } = await import('./staticPreview');
  await expect(staticPreviewJsonFetch('/courses/eras')).rejects.toThrow('offline');
  await expect(staticPreviewJsonFetch('/courses/eras')).resolves.toEqual({ items: [] });
  await staticPreviewJsonFetch('/courses/eras');
  expect(fetch).toHaveBeenCalledTimes(2);
  await expect(staticPreviewJsonFetch('/profile/', { method: 'PUT' })).rejects.toThrow('只读预览');
  expect(fetch).toHaveBeenCalledTimes(2);
});

test('静态目录可按教师人物和关键词组合搜索', async () => {
  const course = { id: 'C-example', title: '早期国家', subtitle: '', era_id: 'prequin' };
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({
    courses: [course], lessons: { L101: { course_id: course.id, title: '夏朝', abstract: '',
      keywords: [{ word: '家天下' }], people: [{ name: '禹' }] } },
  }) }));
  const { staticPreviewJsonFetch } = await import('./staticPreview');
  await expect(staticPreviewJsonFetch('/courses?q=禹%20家天下')).resolves.toEqual({ items: [course], total: 1 });
  await expect(staticPreviewJsonFetch('/courses?q=唐太宗')).resolves.toEqual({ items: [], total: 0 });
});
