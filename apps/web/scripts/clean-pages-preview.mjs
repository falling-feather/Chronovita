import { rm } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
await rm(path.join(webRoot, 'public', 'preview', 'media'), { recursive: true, force: true });
