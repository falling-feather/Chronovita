import { createHash } from 'node:crypto';
import { readFile, readdir, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(fileURLToPath(new URL('../', import.meta.url)));
const ledgerPath = path.join(root, 'assets', 'visual-release-v1.json');
const publicAssetRoot = path.join(root, 'apps', 'web', 'public', 'assets');
const distRoot = path.join(root, 'apps', 'web', 'dist');
const errors = [];

function fail(message) {
  errors.push(message);
}

function assertEqual(actual, expected, label) {
  if (actual !== expected) fail(`${label}: expected ${expected}, received ${actual}`);
}

function sha256(buffer) {
  return createHash('sha256').update(buffer).digest('hex');
}

function inside(base, target) {
  const relative = path.relative(base, target);
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
}

async function readCheckedFile(relativePath, expectedBytes, expectedHash, label) {
  const absolutePath = path.resolve(root, relativePath);
  if (!inside(root, absolutePath)) {
    fail(`${label}: path escapes repository root (${relativePath})`);
    return null;
  }
  try {
    const bytes = await readFile(absolutePath);
    assertEqual(bytes.length, expectedBytes, `${label} bytes`);
    assertEqual(sha256(bytes), expectedHash, `${label} sha256`);
    return { absolutePath, bytes };
  } catch (error) {
    fail(`${label}: ${error instanceof Error ? error.message : String(error)}`);
    return null;
  }
}

function collectOutputs(value, outputs = []) {
  if (Array.isArray(value)) {
    value.forEach((entry) => collectOutputs(entry, outputs));
    return outputs;
  }
  if (!value || typeof value !== 'object') return outputs;
  if (
    typeof value.file === 'string'
    && Number.isInteger(value.bytes)
    && typeof value.sha256 === 'string'
  ) {
    outputs.push(value);
  }
  Object.values(value).forEach((entry) => collectOutputs(entry, outputs));
  return outputs;
}

async function walkFiles(directory) {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const absolutePath = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await walkFiles(absolutePath));
    else if (entry.isFile()) files.push(absolutePath);
  }
  return files;
}

const ledger = JSON.parse(await readFile(ledgerPath, 'utf8'));
const packageJson = JSON.parse(await readFile(path.join(root, 'apps', 'web', 'package.json'), 'utf8'));
const packageLock = JSON.parse(await readFile(path.join(root, 'apps', 'web', 'package-lock.json'), 'utf8'));

assertEqual(ledger.schema, 'chronovita-visual-release/v1', 'visual ledger schema');
assertEqual(ledger.release_version, packageJson.version, 'visual ledger release version');

let familyOutputCount = 0;
let familyOutputBytes = 0;
for (const family of ledger.families) {
  if (!family.source_type || !family.rights_note) {
    fail(`${family.id}: source type and rights note are required`);
  }
  const checked = await readCheckedFile(
    family.manifest_path,
    family.manifest_bytes,
    family.manifest_sha256,
    `${family.id} manifest`,
  );
  if (!checked) continue;
  const manifest = JSON.parse(checked.bytes.toString('utf8'));
  assertEqual(manifest.schema, family.manifest_schema, `${family.id} manifest schema`);
  const outputs = collectOutputs(manifest);
  if (family.id === 'home-era-subjects') {
    for (const output of outputs) {
      assertEqual(output.alpha?.min, 0, `${family.id}/${output.file} alpha min`);
      assertEqual(output.alpha?.max, 255, `${family.id}/${output.file} alpha max`);
    }
  }
  assertEqual(outputs.length, family.output_count, `${family.id} output count`);
  const manifestDirectory = path.dirname(checked.absolutePath);
  let outputBytes = 0;
  for (const output of outputs) {
    const outputPath = path.resolve(manifestDirectory, output.file);
    if (!inside(manifestDirectory, outputPath)) {
      fail(`${family.id}: output path escapes its asset directory (${output.file})`);
      continue;
    }
    try {
      const bytes = await readFile(outputPath);
      assertEqual(bytes.length, output.bytes, `${family.id}/${output.file} bytes`);
      assertEqual(sha256(bytes), output.sha256, `${family.id}/${output.file} sha256`);
      outputBytes += bytes.length;
    } catch (error) {
      fail(`${family.id}/${output.file}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  assertEqual(outputBytes, family.output_bytes, `${family.id} output bytes`);
  familyOutputCount += outputs.length;
  familyOutputBytes += outputBytes;
}

for (const asset of ledger.standalone_assets) {
  if (!asset.source_type || !asset.rights_note) {
    fail(`${asset.id}: source type and rights note are required`);
  }
  await readCheckedFile(asset.path, asset.bytes, asset.sha256, asset.id);
}
for (const asset of ledger.procedural_assets) {
  if (!asset.runtime_license || !asset.fallback) {
    fail(`${asset.id}: runtime license and fallback are required`);
  }
  for (const source of asset.source_files) {
    await readCheckedFile(source.path, source.bytes, source.sha256, `${asset.id}/${source.path}`);
  }
}

assertEqual(packageJson.dependencies.three, '0.185.1', 'Three.js package pin');
assertEqual(packageLock.packages['node_modules/three']?.version, '0.185.1', 'Three.js lock version');
assertEqual(packageLock.packages['node_modules/three']?.license, 'MIT', 'Three.js lock license');

const publicFiles = await walkFiles(publicAssetRoot);
const publicAssetBytes = (
  await Promise.all(publicFiles.map(async (file) => (await stat(file)).size))
).reduce((sum, size) => sum + size, 0);
if (publicAssetBytes > ledger.budgets.public_visual_assets_bytes) {
  fail(`public visual assets exceed budget: ${publicAssetBytes} > ${ledger.budgets.public_visual_assets_bytes}`);
}

const distFiles = await walkFiles(distRoot);
const distRows = await Promise.all(distFiles.map(async (file) => ({
  file,
  bytes: (await stat(file)).size,
})));
const distBytes = distRows.reduce((sum, row) => sum + row.bytes, 0);
if (distBytes > ledger.budgets.dist_total_bytes) {
  fail(`web dist exceeds budget: ${distBytes} > ${ledger.budgets.dist_total_bytes}`);
}

const indexHtml = await readFile(path.join(distRoot, 'index.html'), 'utf8');
const entryPaths = [...indexHtml.matchAll(/(?:src|href)="\/([^"?#]+)"/g)]
  .map((match) => match[1])
  .filter((value, index, values) => value.startsWith('assets/') && values.indexOf(value) === index);
let initialEntryBytes = 0;
for (const relativePath of entryPaths) {
  const absolutePath = path.resolve(distRoot, relativePath);
  if (!inside(distRoot, absolutePath)) {
    fail(`initial entry path escapes dist: ${relativePath}`);
    continue;
  }
  try {
    initialEntryBytes += (await stat(absolutePath)).size;
  } catch (error) {
    fail(`initial entry missing (${relativePath}): ${error instanceof Error ? error.message : String(error)}`);
  }
}
if (initialEntryBytes > ledger.budgets.initial_entry_raw_bytes) {
  fail(`initial entry exceeds budget: ${initialEntryBytes} > ${ledger.budgets.initial_entry_raw_bytes}`);
}

const jsRows = distRows.filter((row) => row.file.endsWith('.js'));
const cssRows = distRows.filter((row) => row.file.endsWith('.css'));
const threeRows = jsRows.filter((row) => /^three\.(?:module|webgpu)-/.test(path.basename(row.file)));
assertEqual(threeRows.length, 1, 'lazy Three.js chunk count');
for (const row of threeRows) {
  if (row.bytes > ledger.budgets.three_chunk_bytes) {
    fail(`Three.js chunk exceeds budget: ${row.bytes} > ${ledger.budgets.three_chunk_bytes}`);
  }
  if (entryPaths.includes(path.relative(distRoot, row.file).replaceAll('\\', '/'))) {
    fail('Three.js must remain outside the initial entry preload list');
  }
}
for (const row of jsRows.filter((entry) => !threeRows.includes(entry))) {
  if (row.bytes > ledger.budgets.largest_non_three_js_chunk_bytes) {
    fail(`${path.basename(row.file)} exceeds JS chunk budget: ${row.bytes}`);
  }
}
for (const row of cssRows) {
  if (row.bytes > ledger.budgets.largest_css_chunk_bytes) {
    fail(`${path.basename(row.file)} exceeds CSS chunk budget: ${row.bytes}`);
  }
}

const summary = {
  ok: errors.length === 0,
  release_version: ledger.release_version,
  visual_outputs: familyOutputCount + ledger.standalone_assets.length,
  checked_family_output_bytes: familyOutputBytes,
  public_visual_assets_bytes: publicAssetBytes,
  dist_bytes: distBytes,
  initial_entry_raw_bytes: initialEntryBytes,
  initial_entry_files: entryPaths.length,
  largest_non_three_js_chunk_bytes: Math.max(...jsRows.filter((row) => !threeRows.includes(row)).map((row) => row.bytes)),
  three_chunk_bytes: threeRows[0]?.bytes ?? 0,
  largest_css_chunk_bytes: Math.max(...cssRows.map((row) => row.bytes)),
  errors,
};

console.log(JSON.stringify(summary, null, 2));
if (errors.length > 0) process.exitCode = 1;
