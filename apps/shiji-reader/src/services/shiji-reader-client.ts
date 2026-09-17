import {
  ApiRequestError,
  getPassage,
  getReaderManifest,
  requestJson,
  type PassagePayload,
  type ReaderManifestEntry,
} from "./api.ts";
import {
  SHIJI_BOOK_ID,
  entriesForVolume,
  isApplicationReadyPayload,
  normalizeMapScene,
  normalizeShijiNavigation,
  normalizeShijiPassage,
  type ShijiReaderNavigation,
} from "./shiji-reader-contracts.ts";
import type { ShijiMapScene } from "./api.ts";

const navigationCache = new Map<string, Promise<ShijiReaderNavigation>>();
const volumeCache = new Map<string, Promise<ReaderManifestEntry[]>>();
const passageCache = new Map<string, Promise<PassagePayload>>();
const mapSceneCache = new Map<string, Promise<ShijiMapScene>>();

export function getShijiReaderNavigation(bookId = SHIJI_BOOK_ID): Promise<ShijiReaderNavigation> {
  const cached = navigationCache.get(bookId);
  if (cached) {
    return cached;
  }
  const request = loadNavigation(bookId).catch((error) => {
    navigationCache.delete(bookId);
    throw error;
  });
  navigationCache.set(bookId, request);
  return request;
}

export function getShijiVolumeEntries(
  volumeNo: number,
  bookId = SHIJI_BOOK_ID,
): Promise<ReaderManifestEntry[]> {
  const key = `${bookId}:${volumeNo}`;
  const cached = volumeCache.get(key);
  if (cached) {
    return cached;
  }
  const request = loadVolumeEntries(volumeNo, bookId).catch((error) => {
    volumeCache.delete(key);
    throw error;
  });
  volumeCache.set(key, request);
  return request;
}

export function getShijiReaderPassage(
  passageId: string,
  mode = "segment",
  versionId?: string,
): Promise<PassagePayload> {
  const key = `${passageId}:${mode}:${versionId ?? ""}`;
  const cached = passageCache.get(key);
  if (cached) {
    return cached;
  }
  const request = loadPassage(passageId, mode, versionId).catch((error) => {
    passageCache.delete(key);
    throw error;
  });
  passageCache.set(key, request);
  return request;
}

export function clearShijiReaderCache() {
  navigationCache.clear();
  volumeCache.clear();
  passageCache.clear();
  mapSceneCache.clear();
}

export function normalizeShijiMapApiPath(apiPath: string): string {
  if (apiPath.startsWith("/api/v1/")) {
    return apiPath.slice("/api/v1".length);
  }
  if (apiPath === "/api/v1") {
    return "/";
  }
  return apiPath;
}

export function getShijiMapScene(apiPath: string): Promise<ShijiMapScene> {
  const requestPath = normalizeShijiMapApiPath(apiPath);
  const cached = mapSceneCache.get(requestPath);
  if (cached) {
    return cached;
  }
  const request = requestJson<unknown>(requestPath)
    .then((value) => normalizeMapScene(value))
    .catch((error) => {
      mapSceneCache.delete(requestPath);
      throw error;
    });
  mapSceneCache.set(requestPath, request);
  return request;
}

async function loadNavigation(bookId: string): Promise<ShijiReaderNavigation> {
  const [applicationManifestPath, ...compatibilityManifestPaths] = applicationManifestPathsFor(bookId);
  let applicationError: unknown;
  try {
    const applicationValue = await requestJson<unknown>(applicationManifestPath);
    return normalizeShijiNavigation(applicationValue, bookId);
  } catch (error) {
    applicationError = error;
  }

  try {
    const legacyValue = await getReaderManifest(bookId, "navigation");
    const navigation = normalizeShijiNavigation(legacyValue, bookId);
    if (isApplicationReadyPayload(legacyValue) || navigation.entries.length === 0) {
      return navigation;
    }
    const compatibilityValue = await firstSuccessful(compatibilityManifestPaths).catch(() => undefined);
    return compatibilityValue === undefined
      ? navigation
      : normalizeShijiNavigation(compatibilityValue, bookId);
  } catch (legacyError) {
    const compatibilityValue = await firstSuccessful(compatibilityManifestPaths).catch(() => undefined);
    if (compatibilityValue !== undefined) {
      return normalizeShijiNavigation(compatibilityValue, bookId);
    }
    throw legacyError instanceof Error
      ? legacyError
      : applicationError instanceof Error
        ? applicationError
        : new Error("史记目录加载失败");
  }
}

async function loadVolumeEntries(volumeNo: number, bookId: string): Promise<ReaderManifestEntry[]> {
  const navigation = await getShijiReaderNavigation(bookId);
  const localEntries = entriesForVolume(navigation, volumeNo);
  if (localEntries.length) {
    return localEntries;
  }

  const volume = navigation.volumes.find((item) => item.volumeNo === volumeNo);
  const value = await firstSuccessful(volumePaths(bookId, volume?.id ?? `shiji-juan-${String(volumeNo).padStart(3, "0")}`)).catch(() => undefined);
  if (value === undefined) {
    return [];
  }
  return entriesForVolume(normalizeShijiNavigation(value, bookId), volumeNo);
}

async function loadPassage(
  passageId: string,
  mode: string,
  versionId?: string,
): Promise<PassagePayload> {
  const applicationValue = await firstSuccessful(applicationChapterPaths(passageId)).catch(() => undefined);
  if (applicationValue !== undefined) {
    return normalizeShijiPassage(applicationValue, passageId);
  }

  try {
    const value = await getPassage(passageId, mode, versionId);
    return normalizeShijiPassage(value, passageId);
  } catch (error) {
    if (!(error instanceof ApiRequestError) || error.status !== 404) {
      throw error;
    }
  }

  const paths = passagePaths(passageId, mode, versionId);
  const value = await firstSuccessful(paths);
  return normalizeShijiPassage(value, passageId);
}

async function firstSuccessful(paths: string[]): Promise<unknown> {
  let lastError: unknown;
  for (const path of paths) {
    try {
      return await requestJson<unknown>(path);
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError instanceof Error ? lastError : new Error("阅读器接口不可用");
}

function applicationManifestPathsFor(bookId: string): string[] {
  const encodedBookId = encodeURIComponent(bookId);
  return [
    `/reader/books/${encodedBookId}/application-manifest`,
    `/reader/books/${encodedBookId}/application-manifest?view=navigation`,
    `/reader/books/${encodedBookId}/manifest?view=application`,
  ];
}

function volumePaths(bookId: string, volumeId: string): string[] {
  const encodedBookId = encodeURIComponent(bookId);
  const encodedVolumeId = encodeURIComponent(volumeId);
  return [
    `/reader/books/${encodedBookId}/volumes/${encodedVolumeId}`,
    `/reader/books/${encodedBookId}/volumes/${encodedVolumeId}?view=navigation`,
    `/reader/books/${encodedBookId}/application/volumes/${encodedVolumeId}?view=navigation`,
  ];
}

function passagePaths(passageId: string, mode: string, versionId?: string): string[] {
  const encodedId = encodeURIComponent(passageId);
  const params = new URLSearchParams({ mode });
  if (versionId) {
    params.set("version_id", versionId);
  }
  return [
    `/reader/passages/${encodedId}/runtime?${params.toString()}`,
    `/reader/application/passages/${encodedId}?${params.toString()}`,
  ];
}

function applicationChapterPaths(passageId: string): string[] {
  const match = passageId.match(/^(shiji-juan-\d{3})(?:-(.+)|:(chapter:\d+))$/);
  if (!match) {
    return [];
  }
  const [, volumeId, dashedChapterId, colonChapterId] = match;
  const chapterId = dashedChapterId ?? colonChapterId;
  return [
    `/reader/books/shiji/volumes/${encodeURIComponent(volumeId)}/chapters/${encodeURIComponent(passageId)}`,
    `/reader/books/shiji/volumes/${encodeURIComponent(volumeId)}/chapters/${encodeURIComponent(chapterId)}`,
  ];
}
