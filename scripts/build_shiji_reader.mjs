import { spawnSync } from 'node:child_process';
import { cpSync, existsSync, realpathSync, rmSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const [major, minor, patch] = process.versions.node.split('.').map(Number);
if (major < 24 || (major === 24 && (minor < 20 || (minor === 20 && patch < 0)))) {
  throw new Error('阅读器构建需要 Node.js 24.20.0 或更新版本。');
}
const root = realpathSync(resolve(dirname(fileURLToPath(import.meta.url)), '..'));
const reader = join(root, 'apps', 'shiji-reader');
const publicRoot = realpathSync(join(root, 'apps', 'web', 'public'));
const destination = resolve(publicRoot, 'shiji-reader');
if (relative(publicRoot, destination) !== 'shiji-reader') throw new Error('阅读器输出路径不正确。');
if (existsSync(destination) && realpathSync(destination) !== destination) {
  throw new Error('阅读器输出不得是指向其他目录的链接。');
}
const npmCli = process.env.npm_execpath;
if (!npmCli || !existsSync(npmCli)) throw new Error('请通过 npm run build:reader 或主前端 build 执行。');
function npm(args) {
  const result = spawnSync(process.execPath, [npmCli, ...args], { cwd: reader, stdio: 'inherit' });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}
if (!existsSync(join(reader, 'node_modules', '.package-lock.json'))) npm(['ci', '--no-audit', '--no-fund']);
npm(['run', 'build']);
const output = realpathSync(join(reader, 'dist'));
if (!existsSync(join(output, 'index.html'))) throw new Error('阅读器构建未生成入口。');
// This directory is a generated bundle, never a content or user-data directory.
if (existsSync(destination)) rmSync(destination, { recursive: true });
cpSync(output, destination, { recursive: true });
console.log('《史记》阅读器已重建，过期构建文件已移除。');
