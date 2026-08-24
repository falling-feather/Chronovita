import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const args = process.argv.slice(2);
const value = (name) => {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : undefined;
};
const sourceArg = value('--source');
const outputArg = value('--output-dir');

if (!sourceArg || !outputArg) {
  throw new Error('Usage: node scripts/prepare_home_chronodial_assets.mjs --source <png> --output-dir <dir>');
}

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
const sharp = await loadSharp();
const sourcePath = path.resolve(sourceArg);
const outputRoot = path.resolve(outputArg);
const sourceBuffer = await readFile(sourcePath);
const sourceMeta = await sharp(sourceBuffer, { failOn: 'error' }).rotate().metadata();
if (!sourceMeta.width || !sourceMeta.height || Math.abs(sourceMeta.width - sourceMeta.height) > 2) {
  throw new Error(`Chronodial source must be square, received ${sourceMeta.width}x${sourceMeta.height}`);
}

await mkdir(outputRoot, { recursive: true });
const outputs = [];
const record = async (file, buffer, kind) => {
  await writeFile(path.join(outputRoot, file), buffer);
  const metadata = await sharp(buffer, { failOn: 'error' }).metadata();
  outputs.push({
    kind,
    file,
    width: metadata.width,
    height: metadata.height,
    format: metadata.format,
    bytes: buffer.byteLength,
    sha256: sha256(buffer),
  });
};

const base = sharp(sourceBuffer, { failOn: 'error' })
  .rotate()
  .resize(1024, 1024, { fit: 'cover', kernel: sharp.kernel.lanczos3 });
const albedo = await base
  .clone()
  .modulate({ saturation: 0.9, brightness: 0.94 })
  .sharpen({ sigma: 1.05, m1: 0.5, m2: 1.2 })
  .webp({ quality: 91, effort: 6, smartSubsample: true })
  .toBuffer();
await record('chronodial-albedo-1024.webp', albedo, 'albedo-and-static-fallback');

const bump = await base
  .clone()
  .greyscale()
  .normalize({ lower: 2, upper: 98 })
  .sharpen({ sigma: 0.72, m1: 0.65, m2: 1.3 })
  .webp({ quality: 88, effort: 6 })
  .toBuffer();
await record('chronodial-bump-1024.webp', bump, 'bump');

const roughness = await base
  .clone()
  .greyscale()
  .blur(1.35)
  .linear(-0.54, 210)
  .webp({ quality: 86, effort: 6 })
  .toBuffer();
await record('chronodial-roughness-1024.webp', roughness, 'roughness');

const manifest = {
  schema: 'chronovita-home-chronodial-assets/v1',
  generated_id: 'exec-9443ef4c-5cdf-4f43-99b1-1fce47b2b8dd',
  prompt_brief: '正交俯视的现代历史仪青铜盘面：精密刻槽、旧化金属、绿锈、玉色轴承与少量朱砂定位点；无指针、无可读文字。',
  source_policy: 'Original imagegen PNG remains outside Git. Generated ID, source hash, deterministic derivatives and final hashes are recorded here.',
  license: 'Original AI-assisted visual produced for Chronovita; it is a fictional teaching instrument, not an excavated-object reconstruction.',
  source: {
    width: sourceMeta.width,
    height: sourceMeta.height,
    bytes: sourceBuffer.byteLength,
    sha256: sha256(sourceBuffer),
  },
  processor: { sharp: sharp.versions.sharp, vips: sharp.versions.vips },
  post_processing: 'Resize and colour-balance albedo, derive normalized grayscale bump, and derive blurred inverted roughness. All maps use identical UV space.',
  outputs,
};

await writeFile(path.join(outputRoot, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
process.stdout.write(`${JSON.stringify({
  ok: true,
  outputs: outputs.length,
  totalBytes: outputs.reduce((sum, output) => sum + output.bytes, 0),
}, null, 2)}\n`);
