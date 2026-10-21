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
    floodSource: value('--flood-source'),
    qinSource: value('--qin-source'),
    hanSource: value('--han-source'),
    tangSource: value('--tang-source'),
    panoramaSource: value('--panorama-source'),
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

const GALLERY_SCENES = [
  {
    id: 'flood',
    sourceArg: 'floodSource',
    generatedId: 'exec-69f4d4c5-73b1-4728-8c41-2af38228120c',
    alt: '河谷中的治水共同体协作分流教学插画',
    promptBrief: '早期治水共同体、分流河道、木构水工与集体劳动；原创教学插画。',
  },
  {
    id: 'qin-reform',
    sourceArg: 'qinSource',
    generatedId: 'exec-97985f9b-cf1c-4d2b-8709-cc1af45620db',
    alt: '战国秦制度辩论与社会承受者教学插画',
    promptBrief: '战国秦夯土木构议事空间、简牍、官员与制度承受者；原创教学插画。',
  },
  {
    id: 'han-caravan',
    sourceArg: 'hanSource',
    generatedId: 'exec-2a135e3d-89ac-4298-8860-7430b7202d8c',
    alt: '汉代西行商旅在绿洲商议路线教学插画',
    promptBrief: '汉代西行商旅、双峰驼、关塞与跨地域交流；原创教学插画。',
  },
  {
    id: 'tang-city',
    sourceArg: 'tangSource',
    generatedId: 'exec-162162c1-141c-47ec-8536-ac7e7cd44d7f',
    alt: '唐代城市街巷与文化交流教学插画',
    promptBrief: '唐代城市街巷、市场、行旅与文化交流；原创教学插画。',
  },
];

const PANORAMA = {
  id: 'history-panorama',
  sourceArg: 'panoramaSource',
  generatedId: 'exec-c3d422c8-8a69-49b2-878b-6ad38632a0ed',
  alt: '从治水河谷延展到城市与长城的中国历史教学长卷',
  promptBrief: '治水、秦制、汉代交通、唐宋城市与山河长城连续成卷；原创教学插画。',
};

const options = parseArgs();
const required = [
  'floodSource',
  'qinSource',
  'hanSource',
  'tangSource',
  'panoramaSource',
  'outputDir',
];
if (required.some((name) => !options[name])) {
  throw new Error(
    'Usage: node scripts/prepare_entry_visual_assets.mjs '
      + '--flood-source <png> --qin-source <png> --han-source <png> '
      + '--tang-source <png> --panorama-source <png> --output-dir <dir>',
  );
}

const sharp = await loadSharp();
const outputRoot = path.resolve(options.outputDir);
await mkdir(outputRoot, { recursive: true });

const manifest = {
  schema: 'chronovita-entry-visual-assets/v1',
  processor: { sharp: sharp.versions.sharp, vips: sharp.versions.vips },
  source_policy: 'Original imagegen PNG files remain outside Git. Generated IDs, source hashes, prompt briefs, final dimensions and final hashes are recorded here.',
  historical_boundary: 'Every scene is an original teaching illustration and must not be described as a primary source, photograph, exact reconstruction, or historical portrait.',
  post_processing: 'Auto-orient, crop only to the declared responsive canvas, resize with Lanczos3, convert to sRGB and encode local WebP variants.',
  gallery: {},
  panorama: null,
};

for (const scene of GALLERY_SCENES) {
  const sourcePath = path.resolve(options[scene.sourceArg]);
  const sourceBuffer = await readFile(sourcePath);
  const sourceMeta = await sharp(sourceBuffer, { failOn: 'error' }).rotate().metadata();
  if (sourceMeta.width !== 1024 || sourceMeta.height !== 1536) {
    throw new Error(`${scene.id} source must be 1024x1536, received ${sourceMeta.width}x${sourceMeta.height}`);
  }

  const entry = {
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
    { width: 420, height: 630, quality: 82 },
    { width: 640, height: 960, quality: 88 },
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
    const file = `login-${scene.id}-${variant.width}.webp`;
    await writeFile(path.join(outputRoot, file), buffer);
    entry.variants.push({
      file,
      format: 'webp',
      width: variant.width,
      height: variant.height,
      bytes: buffer.byteLength,
      sha256: sha256(buffer),
    });
  }
  manifest.gallery[scene.id] = entry;
}

{
  const sourcePath = path.resolve(options[PANORAMA.sourceArg]);
  const sourceBuffer = await readFile(sourcePath);
  const sourceMeta = await sharp(sourceBuffer, { failOn: 'error' }).rotate().metadata();
  if (sourceMeta.width !== 1672 || sourceMeta.height !== 941) {
    throw new Error(`panorama source must be 1672x941, received ${sourceMeta.width}x${sourceMeta.height}`);
  }
  const entry = {
    generated_id: PANORAMA.generatedId,
    alt: PANORAMA.alt,
    prompt_brief: PANORAMA.promptBrief,
    source: {
      width: sourceMeta.width,
      height: sourceMeta.height,
      bytes: sourceBuffer.byteLength,
      sha256: sha256(sourceBuffer),
    },
    variants: [],
  };
  for (const variant of [
    { width: 1366, height: 768, quality: 84 },
    { width: 1920, height: 1080, quality: 88 },
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
    const file = `home-history-panorama-${variant.width}.webp`;
    await writeFile(path.join(outputRoot, file), buffer);
    entry.variants.push({
      file,
      format: 'webp',
      width: variant.width,
      height: variant.height,
      bytes: buffer.byteLength,
      sha256: sha256(buffer),
    });
  }
  manifest.panorama = entry;
}

await writeFile(
  path.join(outputRoot, 'manifest.json'),
  `${JSON.stringify(manifest, null, 2)}\n`,
  'utf8',
);

const variants = [
  ...Object.values(manifest.gallery).flatMap((entry) => entry.variants),
  ...manifest.panorama.variants,
];
process.stdout.write(`${JSON.stringify({
  ok: true,
  galleryScenes: GALLERY_SCENES.length,
  assets: variants.length,
  totalBytes: variants.reduce((sum, variant) => sum + variant.bytes, 0),
}, null, 2)}\n`);
