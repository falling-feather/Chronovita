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
  throw new Error('Usage: node scripts/prepare_ask_paper_asset.mjs --source <png> --output-dir <dir>');
}

async function loadSharp() {
  try {
    return (await import('sharp')).default;
  } catch (error) {
    const moduleRoot = process.env.CHRONOVITA_NODE_MODULES;
    if (!moduleRoot) throw error;
    return (await import(pathToFileURL(path.join(moduleRoot, 'sharp', 'dist', 'index.mjs')).href)).default;
  }
}

const sha256 = (buffer) => createHash('sha256').update(buffer).digest('hex');
const sharp = await loadSharp();
const sourcePath = path.resolve(sourceArg);
const outputDir = path.resolve(outputArg);
const source = await readFile(sourcePath);
const metadata = await sharp(source, { failOn: 'error' }).metadata();

if (!metadata.width || !metadata.height || metadata.width !== metadata.height || metadata.width < 1024) {
  throw new Error(`Ask paper source must be square and at least 1024px; received ${metadata.width}x${metadata.height}`);
}

const paper = await sharp(source, { failOn: 'error' })
  .rotate()
  .resize(1024, 1024, { fit: 'cover', kernel: sharp.kernel.lanczos3 })
  .toColourspace('srgb')
  .webp({ quality: 82, effort: 6, smartSubsample: true })
  .toBuffer();

await mkdir(outputDir, { recursive: true });
await writeFile(path.join(outputDir, 'xuan-paper-1024.webp'), paper);

const manifest = {
  schema: 'chronovita-ask-paper-asset/v1',
  generated_id: 'exec-3d400407-9e28-49ea-bd71-7256de286f23',
  use: 'Low-contrast xuan paper material for the code-native Ask scroll and citation leaves.',
  prompt_brief: 'Warm flat xuan paper, natural mulberry fibres, no text, symbols, objects, shadows or strong stains.',
  source: {
    width: metadata.width,
    height: metadata.height,
    bytes: source.byteLength,
    sha256: sha256(source),
  },
  output: {
    file: 'xuan-paper-1024.webp',
    width: 1024,
    height: 1024,
    bytes: paper.byteLength,
    sha256: sha256(paper),
  },
  processor: { sharp: sharp.versions.sharp, vips: sharp.versions.vips },
};

await writeFile(path.join(outputDir, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
process.stdout.write(`${JSON.stringify({ ok: true, ...manifest.output }, null, 2)}\n`);
