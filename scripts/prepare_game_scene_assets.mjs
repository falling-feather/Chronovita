import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const parseArgs = () => {
  const args = process.argv.slice(2);
  const value = (name) => {
    const index = args.indexOf(name);
    return index >= 0 ? args[index + 1] : undefined;
  };
  return {
    dayuSource: value('--dayu-source'),
    shangyangSource: value('--shangyang-source'),
    outputDir: value('--output-dir'),
  };
};

async function loadSharp() {
  try {
    return (await import('sharp')).default;
  } catch (error) {
    const moduleRoot = process.env.CHRONOVITA_NODE_MODULES;
    if (!moduleRoot) throw error;
    const entry = path.join(moduleRoot, 'sharp', 'dist', 'index.mjs');
    return (await import(pathToFileURL(entry).href)).default;
  }
}

const sha256 = (buffer) => createHash('sha256').update(buffer).digest('hex');

const SCENES = [
  {
    lessonId: 'L101',
    slug: 'flood-council',
    sourceArg: 'dayuSource',
    generatedId: 'exec-2e0cc5a6-3db5-44e5-ad1f-32eeb2f4e9b7',
    alt: '暴雨后的河道、低地聚落与协作治水现场教学插画',
    promptBrief: '早期青铜时代洪泛平原、低地聚落与治水协作；左中部留暗色界面空间。',
  },
  {
    lessonId: 'L103',
    slug: 'qin-reform-council',
    sourceArg: 'shangyangSource',
    generatedId: 'exec-74d22702-c8f7-4417-895a-f68cef930cec',
    alt: '战国秦土木议事空间、简牍与农田城墙教学插画',
    promptBrief: '战国秦夯土行政空间、简牍、度量与农田；左中部留暗色界面空间。',
  },
];

const { dayuSource, shangyangSource, outputDir } = parseArgs();
if (!dayuSource || !shangyangSource || !outputDir) {
  throw new Error(
    'Usage: node scripts/prepare_game_scene_assets.mjs '
      + '--dayu-source <png> --shangyang-source <png> --output-dir <dir>',
  );
}

const sharp = await loadSharp();
const sources = { dayuSource, shangyangSource };
const outputRoot = path.resolve(outputDir);
await mkdir(outputRoot, { recursive: true });

const manifest = {
  schema: 'chronovita-game-scene-assets/v1',
  processor: { sharp: sharp.versions.sharp, vips: sharp.versions.vips },
  source_policy: 'Original imagegen PNG files remain outside Git. Generated IDs, source hashes, prompts briefs, final dimensions and final hashes are recorded here.',
  post_processing: 'Auto-orient, crop only to the exact 16:9 canvas, resize with Lanczos3, convert to sRGB and encode responsive WebP variants.',
  scenes: {},
};

for (const scene of SCENES) {
  const sourcePath = path.resolve(sources[scene.sourceArg]);
  const sourceBuffer = await readFile(sourcePath);
  const source = sharp(sourceBuffer, { failOn: 'error' }).rotate();
  const sourceMeta = await source.metadata();
  if (sourceMeta.width !== 1672 || sourceMeta.height !== 941) {
    throw new Error(
      `${scene.lessonId} source must be 1672x941, received ${sourceMeta.width}x${sourceMeta.height}`,
    );
  }

  const sceneManifest = {
    lesson_id: scene.lessonId,
    generated_id: scene.generatedId,
    alt: scene.alt,
    prompt_brief: scene.promptBrief,
    source: {
      width: sourceMeta.width,
      height: sourceMeta.height,
      bytes: sourceBuffer.byteLength,
      sha256: sha256(sourceBuffer),
    },
    variants: [],
  };

  for (const variant of [
    { width: 960, height: 540, quality: 82 },
    { width: 1600, height: 900, quality: 88 },
  ]) {
    const buffer = await sharp(sourceBuffer, { failOn: 'error' })
      .rotate()
      .resize(variant.width, variant.height, {
        fit: 'cover',
        position: 'centre',
        kernel: sharp.kernel.lanczos3,
      })
      .toColourspace('srgb')
      .webp({ quality: variant.quality, effort: 6, smartSubsample: true })
      .toBuffer();
    const file = `${scene.lessonId}-${scene.slug}-${variant.width}.webp`;
    await writeFile(path.join(outputRoot, file), buffer);
    const finalMeta = await sharp(buffer, { failOn: 'error' }).metadata();
    if (
      finalMeta.format !== 'webp'
      || finalMeta.width !== variant.width
      || finalMeta.height !== variant.height
    ) {
      throw new Error(`${file} failed format or dimension validation`);
    }
    sceneManifest.variants.push({
      file,
      format: 'webp',
      width: variant.width,
      height: variant.height,
      bytes: buffer.byteLength,
      sha256: sha256(buffer),
    });
  }

  manifest.scenes[scene.lessonId] = sceneManifest;
}

await writeFile(
  path.join(outputRoot, 'manifest.json'),
  `${JSON.stringify(manifest, null, 2)}\n`,
  'utf8',
);

const variants = Object.values(manifest.scenes).flatMap((scene) => scene.variants);
process.stdout.write(`${JSON.stringify({
  ok: true,
  scenes: Object.keys(manifest.scenes).length,
  assets: variants.length,
  totalBytes: variants.reduce((sum, variant) => sum + variant.bytes, 0),
}, null, 2)}\n`);
