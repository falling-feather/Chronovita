import { createHash } from 'node:crypto';
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const parseArgs = () => {
  const args = process.argv.slice(2);
  const value = (name) => {
    const index = args.indexOf(name);
    return index >= 0 ? args[index + 1] : undefined;
  };
  return {
    sourceDir: value('--source-dir'),
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

const variants = [
  { width: 720, avifQuality: 52, webpQuality: 78 },
  { width: 1440, avifQuality: 58, webpQuality: 82 },
];

const { sourceDir, outputDir } = parseArgs();
if (!sourceDir || !outputDir) {
  throw new Error('Usage: node scripts/prepare_course_cover_assets.mjs --source-dir <dir> --output-dir <dir>');
}

const sharp = await loadSharp();
const sourceRoot = path.resolve(sourceDir);
const outputRoot = path.resolve(outputDir);
await mkdir(outputRoot, { recursive: true });

const sourceFiles = (await readdir(sourceRoot))
  .filter((name) => /^C-[a-z0-9-]+\.png$/i.test(name))
  .sort((left, right) => left.localeCompare(right));

if (sourceFiles.length !== 15) {
  throw new Error(`Expected 15 course PNG sources, found ${sourceFiles.length} in ${sourceRoot}`);
}

const manifest = {
  schema: 'chronovita-course-cover-assets/v1',
  processor: {
    sharp: sharp.versions.sharp,
    vips: sharp.versions.vips,
  },
  source_policy: 'Original imagegen PNGs remain outside Git; prompts and generated IDs are recorded in project documentation.',
  aspect_ratio: '16:9',
  courses: {},
};

for (const sourceName of sourceFiles) {
  const courseId = path.basename(sourceName, '.png');
  const sourcePath = path.join(sourceRoot, sourceName);
  const sourceBuffer = await readFile(sourcePath);
  const source = sharp(sourceBuffer, { failOn: 'error' }).rotate();
  const metadata = await source.metadata();
  const courseAssets = {
    source: {
      width: metadata.width,
      height: metadata.height,
      bytes: sourceBuffer.byteLength,
      sha256: hash(sourceBuffer),
    },
    variants: [],
  };

  for (const variant of variants) {
    const height = Math.round((variant.width * 9) / 16);
    const base = sharp(sourceBuffer, { failOn: 'error' })
      .rotate()
      .resize(variant.width, height, {
        fit: 'cover',
        position: 'centre',
        withoutEnlargement: true,
      });

    const outputs = [
      {
        format: 'avif',
        buffer: await base.clone().avif({ quality: variant.avifQuality, effort: 6, chromaSubsampling: '4:2:0' }).toBuffer(),
      },
      {
        format: 'webp',
        buffer: await base.clone().webp({ quality: variant.webpQuality, effort: 6, smartSubsample: true }).toBuffer(),
      },
    ];

    for (const output of outputs) {
      const file = `${courseId}-${variant.width}.${output.format}`;
      await writeFile(path.join(outputRoot, file), output.buffer);
      courseAssets.variants.push({
        width: variant.width,
        height,
        format: output.format,
        file,
        bytes: output.buffer.byteLength,
        sha256: hash(output.buffer),
      });
    }
  }

  manifest.courses[courseId] = courseAssets;
}

await writeFile(
  path.join(outputRoot, 'manifest.json'),
  `${JSON.stringify(manifest, null, 2)}\n`,
  'utf8',
);

const totalBytes = Object.values(manifest.courses)
  .flatMap((course) => course.variants)
  .reduce((sum, item) => sum + item.bytes, 0);

process.stdout.write(`${JSON.stringify({ ok: true, courses: sourceFiles.length, assets: sourceFiles.length * variants.length * 2, totalBytes }, null, 2)}\n`);
