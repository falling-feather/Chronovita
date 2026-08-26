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

const hash = (buffer) => createHash('sha256').update(buffer).digest('hex');
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const smoothstep = (value) => {
  const x = clamp(value, 0, 1);
  return x * x * (3 - (2 * x));
};

const SHEETS = [
  {
    key: 'L101',
    arg: 'dayuSource',
    generated_id: 'exec-c9025302-ed91-4e2b-b4f3-1c438859dc21',
    portraits: [
      { slug: 'yu', name: '禹', role: '治水共同体的协调者', cell: 0 },
      { slug: 'gun', name: '鲧', role: '前期治水主事者', cell: 1 },
      { slug: 'yi', name: '益（伯益）', role: '协作与观察者', cell: 2 },
      { slug: 'settlement-representative', name: '聚落代表', role: '受洪水影响的聚落意见群体', cell: 3 },
      { slug: 'flood-worker', name: '治水劳作者', role: '承担勘察、开渠与运输的劳动群体', cell: 4 },
    ],
  },
  {
    key: 'L103',
    arg: 'shangyangSource',
    generated_id: 'exec-df0f9257-e25e-4e53-a293-7dc9125450ee',
    portraits: [
      { slug: 'shang-yang', name: '商鞅', role: '制度改革的主张者与执行者', cell: 0 },
      { slug: 'duke-xiao', name: '秦孝公', role: '改革的政治支持者', cell: 1 },
      { slug: 'hereditary-aristocrat', name: '旧贵族代表', role: '既有身份与特权的维护者', cell: 2 },
      { slug: 'farming-household', name: '农耕家庭代表', role: '承担耕作、赋役与连带责任的家庭', cell: 3 },
      { slug: 'merit-soldier', name: '军功士卒', role: '以战功争取身份上升的军士', cell: 4 },
      { slug: 'county-clerk', name: '县廷吏员', role: '执行户籍、法令与行政记录的基层吏员', cell: 5 },
    ],
  },
];

function detectNeutralBackgrounds(rgb, width, height, channels) {
  const histogram = new Map();
  for (let index = 0; index < width * height; index += 1) {
    const offset = index * channels;
    const red = rgb[offset];
    const green = rgb[offset + 1];
    const blue = rgb[offset + 2];
    const maximum = Math.max(red, green, blue);
    const minimum = Math.min(red, green, blue);
    const tone = Math.round((red + green + blue) / 3);
    if (maximum - minimum <= 3 && tone >= 228) {
      histogram.set(tone, (histogram.get(tone) ?? 0) + 1);
    }
  }

  const ranked = [...histogram.entries()].sort((left, right) => right[1] - left[1]);
  const tones = [];
  for (const [tone] of ranked) {
    if (tones.every((current) => Math.abs(current - tone) >= 5)) tones.push(tone);
    if (tones.length === 2) break;
  }
  if (tones.length !== 2) throw new Error(`Unable to identify both checkerboard tones: ${tones.join(', ')}`);
  return tones.sort((left, right) => left - right);
}

function makeAlpha(rgb, width, height, channels, backgroundTones) {
  const rgba = Buffer.alloc(width * height * 4);
  for (let index = 0; index < width * height; index += 1) {
    const sourceOffset = index * channels;
    const targetOffset = index * 4;
    const red = rgb[sourceOffset];
    const green = rgb[sourceOffset + 1];
    const blue = rgb[sourceOffset + 2];
    const nearestDistance = Math.min(...backgroundTones.map((tone) => Math.hypot(
      red - tone,
      green - tone,
      blue - tone,
    )));
    // Image generation may paint a faint anti-aliased grid between both neutral
    // checkerboard tones. A ten-point dead zone removes that grid while the
    // 24-point feather preserves garment, hair and tool edges.
    const alpha = Math.round(smoothstep((nearestDistance - 10) / 24) * 255);
    rgba[targetOffset] = red;
    rgba[targetOffset + 1] = green;
    rgba[targetOffset + 2] = blue;
    rgba[targetOffset + 3] = alpha <= 8 ? 0 : alpha;
  }
  return rgba;
}

function alphaBounds(rgba, width, height, threshold = 18) {
  let left = width;
  let right = -1;
  let top = height;
  let bottom = -1;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (rgba[((y * width) + x) * 4 + 3] <= threshold) continue;
      left = Math.min(left, x);
      right = Math.max(right, x);
      top = Math.min(top, y);
      bottom = Math.max(bottom, y);
    }
  }
  if (right < left || bottom < top) throw new Error('Portrait cell contains no visible pixels');
  const margin = 8;
  return {
    left: Math.max(0, left - margin),
    top: Math.max(0, top - margin),
    width: Math.min(width - 1, right + margin) - Math.max(0, left - margin) + 1,
    height: Math.min(height - 1, bottom + margin) - Math.max(0, top - margin) + 1,
  };
}

const { dayuSource, shangyangSource, outputDir } = parseArgs();
if (!dayuSource || !shangyangSource || !outputDir) {
  throw new Error('Usage: node scripts/prepare_companion_portrait_assets.mjs --dayu-source <png> --shangyang-source <png> --output-dir <dir>');
}

const sources = { dayuSource, shangyangSource };
const sharp = await loadSharp();
const outputRoot = path.resolve(outputDir);
await mkdir(outputRoot, { recursive: true });

const manifest = {
  schema: 'chronovita-companion-portrait-assets/v1',
  processor: { sharp: sharp.versions.sharp, vips: sharp.versions.vips },
  source_policy: 'Original imagegen PNG sprite sheets remain outside Git. Generated IDs, source hashes, crop cells, post-processing and final hashes are recorded here.',
  post_processing: 'Detect the two neutral checkerboard tones, derive a feathered alpha matte from colour distance, crop each 3x2 cell, and fit to a transparent 4:5 canvas.',
  lessons: {},
};

for (const sheet of SHEETS) {
  const sourcePath = path.resolve(sources[sheet.arg]);
  const sourceBuffer = await readFile(sourcePath);
  const source = sharp(sourceBuffer, { failOn: 'error' }).rotate();
  const metadata = await source.metadata();
  if (metadata.width !== 1536 || metadata.height !== 1024) {
    throw new Error(`${sheet.key} source must be 1536x1024, received ${metadata.width}x${metadata.height}`);
  }
  const { data: rgb, info } = await source.raw().toBuffer({ resolveWithObject: true });
  const backgroundTones = detectNeutralBackgrounds(rgb, info.width, info.height, info.channels);
  const rgba = makeAlpha(rgb, info.width, info.height, info.channels, backgroundTones);
  const cellWidth = info.width / 3;
  const cellHeight = info.height / 2;
  const lesson = {
    generated_id: sheet.generated_id,
    source: {
      width: info.width,
      height: info.height,
      bytes: sourceBuffer.byteLength,
      sha256: hash(sourceBuffer),
      detected_background_tones: backgroundTones,
    },
    portraits: {},
  };

  for (const portrait of sheet.portraits) {
    const cellX = portrait.cell % 3;
    const cellY = Math.floor(portrait.cell / 3);
    const cellRgba = await sharp(rgba, {
      raw: { width: info.width, height: info.height, channels: 4 },
    }).extract({
      left: cellX * cellWidth,
      top: cellY * cellHeight,
      width: cellWidth,
      height: cellHeight,
    }).raw().toBuffer();
    const bounds = alphaBounds(cellRgba, cellWidth, cellHeight);
    const portraitManifest = {
      name: portrait.name,
      role: portrait.role,
      source_cell: portrait.cell,
      source_bounds: bounds,
      variants: [],
    };

    for (const variant of [
      { width: 256, height: 320, quality: 82 },
      { width: 512, height: 640, quality: 88 },
    ]) {
      const buffer = await sharp(cellRgba, {
        raw: { width: cellWidth, height: cellHeight, channels: 4 },
      })
        .extract(bounds)
        .resize(variant.width, variant.height, {
          fit: 'contain',
          background: { r: 0, g: 0, b: 0, alpha: 0 },
          withoutEnlargement: false,
        })
        .webp({ quality: variant.quality, alphaQuality: 95, effort: 6, smartSubsample: true })
        .toBuffer();
      const file = `${sheet.key}-${portrait.slug}-${variant.width}.webp`;
      await writeFile(path.join(outputRoot, file), buffer);
      const finalMeta = await sharp(buffer).metadata();
      if (!finalMeta.hasAlpha || finalMeta.width !== variant.width || finalMeta.height !== variant.height) {
        throw new Error(`${file} failed alpha or dimension validation`);
      }
      portraitManifest.variants.push({
        width: variant.width,
        height: variant.height,
        format: 'webp',
        file,
        bytes: buffer.byteLength,
        sha256: hash(buffer),
      });
    }
    lesson.portraits[portrait.slug] = portraitManifest;
  }
  manifest.lessons[sheet.key] = lesson;
}

await writeFile(path.join(outputRoot, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
const assets = Object.values(manifest.lessons)
  .flatMap((lesson) => Object.values(lesson.portraits))
  .flatMap((portrait) => portrait.variants);
process.stdout.write(`${JSON.stringify({ ok: true, portraits: assets.length / 2, assets: assets.length, totalBytes: assets.reduce((sum, asset) => sum + asset.bytes, 0) }, null, 2)}\n`);
