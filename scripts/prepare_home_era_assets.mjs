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
    preqin: value('--preqin-source'),
    qinhan: value('--qinhan-source'),
    weijin: value('--weijin-source'),
    suitang: value('--suitang-source'),
    songyuan: value('--songyuan-source'),
    mingqing: value('--mingqing-source'),
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
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const smoothstep = (value) => {
  const x = clamp(value, 0, 1);
  return x * x * (3 - (2 * x));
};

const ERAS = [
  {
    id: 'preqin',
    arg: 'preqin',
    generated_id: 'exec-2e0197a7-1502-4594-928b-63041ed0af98',
    alt: '青铜礼器、甲骨片与河纹组成的先秦原创教学主体',
    prompt_brief: '先秦：青铜礼器、甲骨片与河纹；原创教学美术，不复原具体出土器物。',
  },
  {
    id: 'qinhan',
    arg: 'qinhan',
    generated_id: 'exec-b3bfb3b1-91d9-4b7f-adf2-7f4a26b4234d',
    alt: '甲士、铜马与印玺组成的秦汉原创教学主体',
    prompt_brief: '秦汉：甲士、铜马与印玺；原创教学美术，不复原具体俑像。',
  },
  {
    id: 'weijin',
    arg: 'weijin',
    generated_id: 'exec-8c08b1f6-b451-471d-bbe2-247b2e46d9e9',
    alt: '持卷士人、石窟构件与飞带组成的魏晋南北朝原创教学主体',
    prompt_brief: '魏晋南北朝：匿名士人、石窟构件与飞带；原创角色化教学美术。',
  },
  {
    id: 'suitang',
    arg: 'suitang',
    generated_id: 'exec-28c93790-c112-47da-8784-8becffaf2460',
    alt: '三彩风格骆驼、行囊与飘带组成的隋唐原创教学主体',
    prompt_brief: '隋唐：三彩风格骆驼、丝路行囊与飘带；原创教学美术。',
  },
  {
    id: 'songyuan',
    arg: 'songyuan',
    generated_id: 'exec-e26805bb-316e-4bcd-86f1-1544182dfc5b',
    alt: '海船、青瓷与司南意象组成的宋元原创教学主体',
    prompt_brief: '宋元：海船、青瓷与司南意象；原创教学美术，不作精确船型复原。',
  },
  {
    id: 'mingqing',
    arg: 'mingqing',
    generated_id: 'exec-9bc53419-ea45-4eb8-b365-3c56f147371c',
    alt: '青花瓷、长城城台与线装书组成的明清原创教学主体',
    prompt_brief: '明清：青花瓷、长城城台与线装书；原创教学美术。',
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
    if (maximum - minimum <= 4 && tone >= 222) {
      histogram.set(tone, (histogram.get(tone) ?? 0) + 1);
    }
  }

  const ranked = [...histogram.entries()].sort((left, right) => right[1] - left[1]);
  const tones = [];
  for (const [tone] of ranked) {
    if (tones.every((current) => Math.abs(current - tone) >= 4)) tones.push(tone);
    if (tones.length === 2) break;
  }
  if (tones.length !== 2) {
    throw new Error(`Unable to identify both checkerboard tones: ${tones.join(', ')}`);
  }
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
    const nearestTone = backgroundTones.reduce((best, tone) => (
      Math.hypot(red - tone, green - tone, blue - tone)
        < Math.hypot(red - best, green - best, blue - best) ? tone : best
    ));
    const nearestDistance = Math.hypot(
      red - nearestTone,
      green - nearestTone,
      blue - nearestTone,
    );
    const alpha = Math.round(smoothstep((nearestDistance - 9) / 26) * 255);
    if (alpha <= 8) {
      rgba[targetOffset] = 0;
      rgba[targetOffset + 1] = 0;
      rgba[targetOffset + 2] = 0;
      rgba[targetOffset + 3] = 0;
      continue;
    }
    const opacity = alpha / 255;
    const removeMatte = (channel) => clamp(Math.round(
      (channel - ((1 - opacity) * nearestTone)) / opacity,
    ), 0, 255);
    rgba[targetOffset] = alpha < 250 ? removeMatte(red) : red;
    rgba[targetOffset + 1] = alpha < 250 ? removeMatte(green) : green;
    rgba[targetOffset + 2] = alpha < 250 ? removeMatte(blue) : blue;
    rgba[targetOffset + 3] = alpha;
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
  if (right < left || bottom < top) throw new Error('Era source contains no visible pixels');
  const margin = 10;
  return {
    left: Math.max(0, left - margin),
    top: Math.max(0, top - margin),
    width: Math.min(width - 1, right + margin) - Math.max(0, left - margin) + 1,
    height: Math.min(height - 1, bottom + margin) - Math.max(0, top - margin) + 1,
  };
}

const options = parseArgs();
if (!options.outputDir || ERAS.some((era) => !options[era.arg])) {
  throw new Error('Usage: node scripts/prepare_home_era_assets.mjs --preqin-source <png> --qinhan-source <png> --weijin-source <png> --suitang-source <png> --songyuan-source <png> --mingqing-source <png> --output-dir <dir>');
}

const sharp = await loadSharp();
const outputRoot = path.resolve(options.outputDir);
await mkdir(outputRoot, { recursive: true });

const manifest = {
  schema: 'chronovita-home-era-assets/v1',
  processor: { sharp: sharp.versions.sharp, vips: sharp.versions.vips },
  source_policy: 'Original imagegen PNG files remain outside Git. Generated IDs, prompts, source hashes, post-processing and final hashes are recorded here.',
  license: 'Original AI-assisted teaching artwork produced for Chronovita; not an exact reconstruction of named archaeological objects or historical portraits.',
  post_processing: 'Detect the two neutral checkerboard tones, derive a feathered alpha matte from colour distance, crop visible bounds, and fit to transparent square WebP canvases.',
  eras: {},
};

for (const era of ERAS) {
  const sourcePath = path.resolve(options[era.arg]);
  const sourceBuffer = await readFile(sourcePath);
  const source = sharp(sourceBuffer, { failOn: 'error' }).rotate();
  const { data: rgb, info } = await source.raw().toBuffer({ resolveWithObject: true });
  const backgroundTones = detectNeutralBackgrounds(rgb, info.width, info.height, info.channels);
  const rgba = makeAlpha(rgb, info.width, info.height, info.channels, backgroundTones);
  const bounds = alphaBounds(rgba, info.width, info.height);
  const entry = {
    generated_id: era.generated_id,
    alt: era.alt,
    prompt_brief: era.prompt_brief,
    source: {
      width: info.width,
      height: info.height,
      bytes: sourceBuffer.byteLength,
      sha256: sha256(sourceBuffer),
      detected_background_tones: backgroundTones,
      visible_bounds: bounds,
    },
    variants: [],
  };

  for (const variant of [
    { size: 640, quality: 84 },
    { size: 1280, quality: 90 },
  ]) {
    const buffer = await sharp(rgba, {
      raw: { width: info.width, height: info.height, channels: 4 },
    })
      .extract(bounds)
      .resize(variant.size, variant.size, {
        fit: 'contain',
        background: { r: 0, g: 0, b: 0, alpha: 0 },
        withoutEnlargement: false,
        kernel: sharp.kernel.lanczos3,
      })
      .webp({ quality: variant.quality, alphaQuality: 98, effort: 6, smartSubsample: true })
      .toBuffer();
    const file = `${era.id}-${variant.size}.webp`;
    await writeFile(path.join(outputRoot, file), buffer);
    const metadata = await sharp(buffer, { failOn: 'error' }).metadata();
    const stats = await sharp(buffer, { failOn: 'error' }).stats();
    const alpha = stats.channels[3];
    if (!metadata.hasAlpha || metadata.width !== variant.size || metadata.height !== variant.size || !alpha || alpha.min !== 0 || alpha.max !== 255) {
      throw new Error(`${file} failed alpha or dimension validation`);
    }
    entry.variants.push({
      width: variant.size,
      height: variant.size,
      format: 'webp',
      file,
      bytes: buffer.byteLength,
      sha256: sha256(buffer),
      alpha: { min: alpha.min, max: alpha.max },
    });
  }
  manifest.eras[era.id] = entry;
}

await writeFile(path.join(outputRoot, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
const assets = Object.values(manifest.eras).flatMap((era) => era.variants);
process.stdout.write(`${JSON.stringify({
  ok: true,
  eras: Object.keys(manifest.eras).length,
  assets: assets.length,
  totalBytes: assets.reduce((sum, asset) => sum + asset.bytes, 0),
}, null, 2)}\n`);
