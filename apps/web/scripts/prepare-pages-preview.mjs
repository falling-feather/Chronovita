import { createHash } from 'node:crypto';
import { copyFile, mkdir, readFile, rm } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repositoryRoot = path.resolve(webRoot, '..', '..');
const dataPath = path.join(webRoot, 'public', 'preview', 'preview-data-v1.json');
const mediaRoot = path.join(webRoot, 'public', 'preview', 'media');
const payload = JSON.parse(await readFile(dataPath, 'utf8'));

await rm(mediaRoot, { recursive: true, force: true });

for (const response of Object.values(payload.presentations)) {
  const presentation = response.presentation;
  const lessonId = presentation.lesson_id;
  await mkdir(path.join(mediaRoot, lessonId), { recursive: true });

  for (const [asset, sourceKey, checksumKey] of [
    ['video', 'video_path', 'video_sha256'],
    ['poster', 'poster_path', 'poster_sha256'],
    ['transcript', 'transcript_path', 'transcript_sha256'],
  ]) {
    const source = path.join(repositoryRoot, 'content', presentation[sourceKey]);
    const targetUrl = response.asset_urls[asset].replace(/^\/+/, '');
    const target = path.join(webRoot, 'public', targetUrl);
    const bytes = await readFile(source);
    const digest = createHash('sha256').update(bytes).digest('hex');
    if (digest !== presentation[checksumKey]) {
      throw new Error(`${lessonId} ${asset} checksum mismatch: ${digest}`);
    }
    await mkdir(path.dirname(target), { recursive: true });
    await copyFile(source, target);
  }
}

console.log(`Prepared ${Object.keys(payload.presentations).length} immutable lesson presentations.`);
