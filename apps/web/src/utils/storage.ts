/**
 * 轻量本地存储封装。后端持久化接入前的临时兜底。
 * 命名空间：所有 key 以 `chronovita.` 开头。
 */
const NS = 'chronovita.';

export function loadJSON<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(NS + key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function saveJSON<T>(key: string, value: T): void {
  try {
    localStorage.setItem(NS + key, JSON.stringify(value));
  } catch {
    /* quota / privacy mode → 静默失败 */
  }
}

export function removeKey(key: string): void {
  try { localStorage.removeItem(NS + key); } catch { /* noop */ }
}
