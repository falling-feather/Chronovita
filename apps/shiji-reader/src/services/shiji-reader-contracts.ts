import type {
  Annotation,
  ContentSource,
  KnowledgeFact,
  KnowledgeEntity,
  PassagePayload,
  PassageReading,
  PublicationReview,
  ReaderManifestEntry,
  ReaderManifestVersionInfo,
  ReaderSequence,
  ReaderSequenceTarget,
  ReadingMode,
  ShijiChapterRuntime,
  ShijiKnowledgeSummary,
  ShijiMapContextBasemap,
  ShijiMapContextBinding,
  ShijiMapContextPoint,
  ShijiMapPlacePoint,
  ShijiMapScene,
  ShijiMapSceneSummary,
  ShijiMapSummary,
  ShijiSpatialMarker,
  ShijiMapTimelineEvent,
  ShijiMapValidTime,
  TextHighlight,
  UncertainItem,
  VariantReading,
  VersionInfo,
} from "./api";

export const SHIJI_BOOK_ID = "shiji";
export const SHIJI_VOLUME_COUNT = 130;

export type ShijiReaderDataSource = "application" | "legacy";

export interface ShijiApplicationStatus {
  state: string;
  label: "AI整理 / 人类未校";
  aiStatus: string;
  humanStatus: string;
  isApplicationReady: boolean;
}

export interface ShijiVolumeSummary {
  id: string;
  volumeNo: number;
  title: string;
  categoryId?: string;
  categoryLabel?: string;
  preview?: string;
  chapterType: string;
  status: string;
  chapterCount: number;
  appliedChapterCount: number;
  available: boolean;
}

export interface ShijiReaderNavigation {
  bookId: string;
  bookTitle: string;
  manifestId: string;
  totalPassages: number;
  totalVolumes: number;
  entries: ReaderManifestEntry[];
  volumes: ShijiVolumeSummary[];
  publication?: PublicationReview;
  applicationStatus: ShijiApplicationStatus;
  source: ShijiReaderDataSource;
}

type JsonObject = Record<string, unknown>;

const EMPTY_GROUPS = {
  persons: [],
  places: [],
  events: [],
  concepts: [],
};

export function isApplicationReadyPayload(value: unknown): boolean {
  const object = asObject(value);
  if (object.artifact_type === "shiji_application_manifest" || object.artifact_type === "shiji_application_volume_runtime") {
    return true;
  }
  const nested = asObject(object.application ?? object.runtime ?? object.publication);
  if (asObject(object.publication).state === "application_ready") {
    return true;
  }
  const state = firstText(
    object.application_status,
    object.applicationState,
    object.status,
    nested.status,
    nested.state,
  );
  return state === "application_ready" || state === "runtime_compiled" || state === "reader_available";
}

export function normalizeApplicationStatus(value: unknown): ShijiApplicationStatus {
  const object = asObject(value);
  const publication = asObject(object.publication ?? object.review ?? object.application);
  const state = firstText(
    publication.status,
    publication.state,
    object.application_status,
    object.applicationState,
    object.status,
    "application_ready",
  );
  const aiStatus = firstText(
    publication.ai_status,
    publication.aiStatus,
    "AI初筛完成",
  );
  const humanStatus = firstText(
    publication.human_status,
    publication.humanStatus,
    "人类待检查",
  );
  return {
    state,
    label: "AI整理 / 人类未校",
    aiStatus,
    humanStatus,
    isApplicationReady: state === "application_ready" || state === "runtime_compiled" || state === "reader_available",
  };
}

export function normalizeShijiNavigation(
  value: unknown,
  bookId = SHIJI_BOOK_ID,
): ShijiReaderNavigation {
  const root = Array.isArray(value) ? { entries: value } : asObject(value);
  const rawEntries = arrayValue(root.entries ?? root.passages ?? root.chapters);
  const entryList: ReaderManifestEntry[] = [];
  const entryIds = new Set<string>();
  const volumeMetadata = new Map<number, JsonObject>();

  for (const rawVolume of arrayValue(root.volumes)) {
    collectVolumeMetadata(rawVolume, volumeMetadata);
    collectNestedEntries(rawVolume, undefined, entryList, entryIds);
  }
  for (const rawEntry of rawEntries) {
    addEntry(rawEntry, undefined, entryList, entryIds);
  }

  entryList.sort((left, right) => left.sequence - right.sequence || left.passage_id.localeCompare(right.passage_id));
  entryList.forEach((entry, index) => {
    if (!entry.previous_id && index > 0) {
      entry.previous_id = entryList[index - 1].passage_id;
    }
    if (!entry.next_id && index + 1 < entryList.length) {
      entry.next_id = entryList[index + 1].passage_id;
    }
  });

  const summary = asObject(root.summary);
  const requestedVolumeCount = numberValue(
    root.total_volumes,
    root.total_volume_count,
    root.volume_count,
    summary.total_volumes,
    summary.volume_count,
  );
  const totalVolumes = bookId === SHIJI_BOOK_ID
    ? Math.max(SHIJI_VOLUME_COUNT, requestedVolumeCount ?? 0, ...entryList.map((entry) => entry.volume_no))
    : Math.max(requestedVolumeCount ?? 0, ...entryList.map((entry) => entry.volume_no), 0);
  const entriesByVolume = new Map<number, ReaderManifestEntry[]>();
  for (const entry of entryList) {
    const entries = entriesByVolume.get(entry.volume_no) ?? [];
    entries.push(entry);
    entriesByVolume.set(entry.volume_no, entries);
  }
  const volumes = Array.from({ length: totalVolumes }, (_, index) => {
    const volumeNo = index + 1;
    const entries = entriesByVolume.get(volumeNo) ?? [];
    const metadata = volumeMetadata.get(volumeNo);
    const chapterType = firstText(
      metadata?.chapter_type,
      metadata?.chapterType,
      entries[0]?.chapter_type,
      "待接入",
    );
    const status = firstText(
      metadata?.status,
      entries.length ? "application_ready" : "not_applied",
    );
    return {
      id: firstText(metadata?.id, metadata?.volume_id, entries[0]?.volume_id, `${bookId}-volume-${String(volumeNo).padStart(3, "0")}`),
      volumeNo,
      title: firstText(metadata?.title, metadata?.volume_title, metadata?.title_traditional, metadata?.title_simplified, entries[0]?.volume_title, `卷 ${volumeNo}`),
      categoryId: firstText(
        metadata?.category_id,
        metadata?.categoryId,
        entries[0]?.category_id,
        metadata?.work_type,
        metadata?.chapter_type,
      ),
      categoryLabel: firstText(
        metadata?.category_title_simplified,
        metadata?.category_title_traditional,
        entries[0]?.category_title_simplified,
        entries[0]?.category_title_traditional,
        metadata?.chapter_type,
        "未分类",
      ),
      preview: firstText(
        metadata?.preview_simplified,
        metadata?.preview_traditional,
        entries[0]?.preview_simplified,
        entries[0]?.preview_traditional,
      ),
      chapterType,
      status,
      chapterCount: numberValue(metadata?.chapter_count, metadata?.chapterCount) ?? entries.length,
      appliedChapterCount: entries.length,
      available: entries.length > 0 || status === "application_ready" || status === "runtime_compiled" || status === "reader_available",
    } satisfies ShijiVolumeSummary;
  });

  const publication = normalizePublication(root.publication ?? root.review);
  const applicationStatus = normalizeApplicationStatus(root);
  return {
    bookId: firstText(root.book_id, root.bookId, bookId),
    bookTitle: firstText(root.book_title, root.bookTitle, "史记"),
    manifestId: firstText(root.manifest_id, root.manifestId, `${bookId}-application-reader`),
    totalPassages: numberValue(root.total_passages, root.totalPassages, summary.total_passages) ?? entryList.length,
    totalVolumes,
    entries: entryList,
    volumes,
    publication,
    applicationStatus,
    source: isApplicationReadyPayload(root) ? "application" : "legacy",
  };
}

export function normalizeShijiPassage(
  value: unknown,
  passageId = "unknown-passage",
): PassagePayload {
  const root = asObject(value);
  const nested = asObject(root.application ?? root.reader ?? root.runtime_payload);
  const chapterSource = asObject(root.chapter ?? nested.chapter);
  const volumeSource = asObject(root.volume ?? nested.volume);
  const passageSource = asObject(root.passage ?? nested.passage ?? chapterSource);
  const runtimeSource = asObject(
    root.chapter_runtime ?? root.chapterRuntime ?? root.runtime ?? nested.runtime ?? chapterSource,
  );
  const rawSentences = normalizeSentences(
    runtimeSource.sentences ?? chapterSource.sentences ?? root.sentences ?? nested.sentences ?? root.units,
    passageId,
  );
  const bodyFacsimileSentences = rawSentences.filter((sentence) =>
    sentence.content_layer !== "commentary"
    && sentence.content_layer !== "paratext"
    && sentence.content_layer !== "mixed",
  );
  const facsimileSentences = bodyFacsimileSentences.length
    ? bodyFacsimileSentences
    : rawSentences;
  const anchors = [
    ...arrayValue(chapterSource.source_anchors),
    ...arrayValue(root.source_page_refs),
    ...arrayValue(volumeSource.source_page_refs),
  ];
  const firstAnchor = asObject(anchors[0]);
  const inferredVersionId = firstText(firstAnchor.version_id, "application-primary");
  const explicitCurrentVersion = root.current_version
    ?? root.currentVersion
    ?? nested.current_version
    ?? root.version;
  const currentVersion = normalizeVersion(
    explicitCurrentVersion ?? {
      id: inferredVersionId,
      name: inferredVersionId,
    },
    inferredVersionId,
  );
  const anchorBySpan = new Map<string, JsonObject>();
  const facsimileAnchorVersionIds = new Set<string>();
  const facsimileAnchorByVersionAndOrdinal = new Map<string, JsonObject>();
  const facsimileAnchorByUniqueOrdinal = new Map<string, JsonObject>();
  const ambiguousFacsimileOrdinals = new Set<string>();
  anchors.forEach((item) => {
    const anchor = asObject(item);
    const spanId = firstText(anchor.source_span_id);
    const pageId = firstText(anchor.page_id, anchor.pageId);
    const versionId = firstText(anchor.version_id, anchor.versionId);
    if (spanId) {
      anchorBySpan.set(spanId, anchor);
    }
    const ordinal = pageOrdinalToken(pageId) || pageOrdinalToken(spanId);
    if (!ordinal) {
      return;
    }
    if (versionId) {
      facsimileAnchorVersionIds.add(versionId);
      facsimileAnchorByVersionAndOrdinal.set(`${versionId}:${ordinal}`, anchor);
    }
    const existing = facsimileAnchorByUniqueOrdinal.get(ordinal);
    if (!existing) {
      facsimileAnchorByUniqueOrdinal.set(ordinal, anchor);
    } else if (firstText(existing.page_id, existing.pageId) !== pageId) {
      ambiguousFacsimileOrdinals.add(ordinal);
    }
  });
  ambiguousFacsimileOrdinals.forEach((ordinal) => facsimileAnchorByUniqueOrdinal.delete(ordinal));

  const equivalentFacsimileAnchor = (sourceSpanId: string): JsonObject | undefined => {
    const ordinal = pageOrdinalToken(sourceSpanId);
    if (!ordinal) {
      return undefined;
    }
    const matchingVersionIds = [...facsimileAnchorVersionIds]
      .filter((versionId) => sourceSpanId.includes(versionId))
      .sort((left, right) => right.length - left.length);
    for (const versionId of matchingVersionIds) {
      const anchor = facsimileAnchorByVersionAndOrdinal.get(`${versionId}:${ordinal}`);
      if (anchor) {
        return anchor;
      }
    }
    return facsimileAnchorByUniqueOrdinal.get(ordinal);
  };
  const sentenceAnchors: JsonObject[] = [];
  const seenSentencePages = new Set<string>();
  facsimileSentences.forEach((sentence) => sentence.source_span_ids?.forEach((sourceSpanId) => {
    const anchor = anchorBySpan.get(sourceSpanId) ?? equivalentFacsimileAnchor(sourceSpanId);
    const pageId = firstText(anchor?.page_id, anchor?.pageId);
    if (anchor && pageId && !seenSentencePages.has(pageId)) {
      seenSentencePages.add(pageId);
      sentenceAnchors.push(anchor);
    }
  }));
  const explicitPageIds = currentVersion.page_ids ?? [];
  const selectedVersionId = currentVersion.id === "application-primary"
    ? inferredVersionId
    : currentVersion.id;
  const selectedAnchors = explicitPageIds.length
    ? anchors.filter((item) => explicitPageIds.includes(firstText(asObject(item).page_id, asObject(item).pageId)))
    : sentenceAnchors.length
      ? sentenceAnchors
      : anchors.filter((item) => {
          const versionId = firstText(asObject(item).version_id);
          return !versionId || versionId === selectedVersionId;
        });
  const pageIds = normalizePageIds(
    currentVersion.page_ids,
    root.pages,
    asObject(root.reading).page,
    selectedAnchors,
  );
  if (pageIds.length && !currentVersion.page_ids?.length) {
    currentVersion.page_ids = pageIds;
  }
  const selectedSourceVersions = new Set(
    selectedAnchors
      .map((item) => firstText(asObject(item).version_id))
      .filter(Boolean),
  );
  if (explicitCurrentVersion === undefined && selectedSourceVersions.size > 1) {
    currentVersion.id = "application-primary";
    currentVersion.name = "应用正文 · 多版本来源书影";
  }
  const availableVersions = normalizeVersions(
    root.available_versions ?? root.availableVersions ?? nested.available_versions ?? root.versions,
    currentVersion,
  );
  const pageIndexById = new Map(pageIds.map((pageId, index) => [pageId, index]));
  const pageIndexBySpan = new Map<string, number>();
  const pageIndexByVersionAndOrdinal = new Map<string, number>();
  const pageIndexByUniqueOrdinal = new Map<string, number>();
  const ambiguousPageOrdinals = new Set<string>();
  const anchorVersionIds = new Set<string>();
  anchors.forEach((item) => {
    const anchor = asObject(item);
    const spanId = firstText(anchor.source_span_id);
    const pageId = firstText(anchor.page_id, anchor.pageId);
    const versionId = firstText(anchor.version_id, anchor.versionId);
    const pageIndex = pageIndexById.get(pageId);
    if (spanId && pageIndex !== undefined) {
      pageIndexBySpan.set(spanId, pageIndex);
    }
    if (pageIndex === undefined) {
      return;
    }
    if (versionId) {
      anchorVersionIds.add(versionId);
    }
    const ordinal = pageOrdinalToken(pageId) || pageOrdinalToken(spanId);
    if (!ordinal) {
      return;
    }
    if (versionId) {
      pageIndexByVersionAndOrdinal.set(`${versionId}:${ordinal}`, pageIndex);
    }
    const existing = pageIndexByUniqueOrdinal.get(ordinal);
    if (existing === undefined) {
      pageIndexByUniqueOrdinal.set(ordinal, pageIndex);
    } else if (existing !== pageIndex) {
      ambiguousPageOrdinals.add(ordinal);
    }
  });
  ambiguousPageOrdinals.forEach((ordinal) => pageIndexByUniqueOrdinal.delete(ordinal));
  const sentences = rawSentences.map((sentence) => ({
    ...sentence,
    page_index: sentence.page_index ?? sentence.source_span_ids?.map((id) =>
      pageIndexBySpan.get(id)
      ?? pageIndexForEquivalentSourceSpan(
        id,
        anchorVersionIds,
        pageIndexByVersionAndOrdinal,
        pageIndexByUniqueOrdinal,
      ))
      .find((index): index is number => index !== undefined),
  }));

  const text = firstText(
    root.text,
    nested.text,
    sentences.map((sentence) => sentence.punctuated_text).join("\n"),
  );
  const reading = normalizeReading(
    root.reading ?? nested.reading,
    text,
    sentences,
    pageIds,
    passageId,
  );
  const sequence = normalizeSequence(
    root.reader_sequence ?? root.readerSequence ?? nested.reader_sequence ?? root.sequence,
    passageId,
    currentVersion.id,
  );
  const compactEntities = root.entities ?? nested.entities ?? volumeSource.entities;
  const entityCandidates = root.entity_candidates
    ?? nested.entity_candidates
    ?? chapterSource.entity_candidates
    ?? volumeSource.entity_candidates;
  const compactEntityItems = arrayValue(compactEntities);
  const entities = compactEntityItems.length
    ? normalizeEntities(compactEntityItems)
    : normalizeEntities(entityCandidates, true);
  const publication = normalizePublication(
    root.publication ?? volumeSource.publication ?? nested.publication ?? runtimeSource.publication,
  );
  const applicationStatus = normalizeApplicationStatus(
    root.publication ?? volumeSource.publication ?? root.application_status ?? runtimeSource,
  );
  const chapterRuntime = sentences.length
    ? normalizeRuntime(runtimeSource, sentences, passageId, currentVersion.id, root)
    : undefined;
  const highlights = normalizeHighlights(
    root.highlights ?? nested.highlights,
    sentences,
    entities,
  );

  const passage = {
    id: firstText(passageSource.id, passageSource.passage_id, passageSource.chapter_id, root.passage_id, root.chapter_id, passageId),
    book_id: firstText(passageSource.book_id, volumeSource.book_id, root.book_id, nested.book_id, SHIJI_BOOK_ID),
    book_title: firstText(passageSource.book_title, volumeSource.book_title, root.book_title, "史记"),
    volume_id: firstText(passageSource.volume_id, volumeSource.volume_id, root.volume_id, "shiji-volume-unknown"),
    title: firstText(passageSource.title, passageSource.title_traditional, passageSource.title_simplified, root.title, root.chapter_title, chapterSource.title_traditional, chapterSource.title_simplified, passageId),
    sort_order: numberValue(passageSource.sort_order, root.sort_order) ?? sequence?.current.sequence ?? 0,
    previous_id: nullableText(passageSource.previous_id, sequence?.previous?.passage_id),
    next_id: nullableText(passageSource.next_id, sequence?.next?.passage_id),
  };

  return {
    ...root,
    passage,
    current_version: currentVersion,
    available_versions: availableVersions,
    reading,
    reader_sequence: sequence,
    reader_config: normalizeReaderConfig(root.reader_config ?? nested.reader_config),
    text,
    highlights,
    variants: arrayValue(root.variants ?? nested.variants) as VariantReading[],
    annotations: arrayValue(root.annotations ?? nested.annotations) as Annotation[],
    mentions: normalizeMentions(root.mentions ?? nested.mentions),
    publication,
    sources: arrayValue(root.sources ?? nested.sources) as ContentSource[],
    entities,
    uncertain_items: arrayValue(root.uncertain_items ?? root.uncertainItems ?? nested.uncertain_items) as UncertainItem[],
    chapter_runtime: chapterRuntime,
    application_status: applicationStatus,
  } as PassagePayload;
}

export function entriesForVolume(
  navigation: ShijiReaderNavigation,
  volumeNo: number,
): ReaderManifestEntry[] {
  return navigation.entries
    .filter((entry) => entry.volume_no === volumeNo)
    .sort((left, right) => left.sequence - right.sequence);
}

export function findVolumeForPassage(
  navigation: ShijiReaderNavigation,
  passageId: string,
): ShijiVolumeSummary | undefined {
  const entry = navigation.entries.find((item) => item.passage_id === passageId);
  return entry ? navigation.volumes.find((volume) => volume.volumeNo === entry.volume_no) : undefined;
}

export function attachNavigationToPassage(
  payload: PassagePayload,
  navigation: ShijiReaderNavigation,
): PassagePayload {
  const entry = navigation.entries.find((item) => item.passage_id === payload.passage.id);
  if (!entry) {
    return payload;
  }
  const entryIndex = navigation.entries.indexOf(entry);
  const availableVersionIds = entry.available_versions.map((version) => version.id);
  const target = (targetEntry: ReaderManifestEntry | undefined): ReaderSequenceTarget | null => {
    if (!targetEntry) {
      return null;
    }
    return {
      passage_id: targetEntry.passage_id,
      sequence: targetEntry.sequence,
      title: targetEntry.title,
      available_version_ids: targetEntry.available_versions.map((version) => version.id),
    };
  };
  const sequence: ReaderSequence = {
    manifest_id: navigation.manifestId,
    book_id: navigation.bookId,
    book_title: navigation.bookTitle,
    position: entry.sequence,
    total: navigation.totalPassages,
    volume: {
      id: entry.volume_id,
      number: entry.volume_no,
      title: entry.volume_title,
    },
    chapter: {
      id: entry.chapter_id,
      title: entry.chapter_title,
      type: entry.chapter_type,
    },
    current: {
      passage_id: entry.passage_id,
      sequence: entry.sequence,
      title: entry.title,
      available_version_ids: availableVersionIds,
    },
    previous: target(navigation.entries[entryIndex - 1]),
    next: target(navigation.entries[entryIndex + 1]),
    selected_version_id: payload.current_version.id,
    available_version_ids: availableVersionIds,
  };
  return {
    ...payload,
    passage: {
      ...payload.passage,
      volume_id: entry.volume_id,
      previous_id: entry.previous_id,
      next_id: entry.next_id,
    },
    reader_sequence: sequence,
  };
}

function collectVolumeMetadata(value: unknown, output: Map<number, JsonObject>) {
  const volume = asObject(value);
  const volumeNo = numberValue(
    volume.volume_no,
    volume.volumeNo,
    volume.juan_no,
    volume.juanNo,
    volume.number,
    asObject(volume.volume).volume_no,
  );
  if (volumeNo === undefined || volumeNo < 1) {
    return;
  }
  output.set(volumeNo, volume);
}

function collectNestedEntries(
  value: unknown,
  fallbackVolume: JsonObject | undefined,
  output: ReaderManifestEntry[],
  ids: Set<string>,
) {
  const object = asObject(value);
  const volume = object.volume
    ? asObject(object.volume)
    : numberValue(object.volume_no, object.volumeNo, object.juan_no, object.juanNo, object.number) !== undefined
      ? object
      : fallbackVolume;
  const nested = [
    ...arrayValue(object.entries),
    ...arrayValue(object.passages),
    ...arrayValue(object.chapters),
  ];
  for (const child of nested) {
    const childObject = asObject(child);
    if (hasPassageId(childObject)) {
      addEntry(childObject, volume, output, ids);
    } else {
      collectNestedEntries(childObject, volume, output, ids);
    }
  }
}

function addEntry(
  value: unknown,
  fallbackVolume: JsonObject | undefined,
  output: ReaderManifestEntry[],
  ids: Set<string>,
) {
  const entry = normalizeEntry(value, fallbackVolume, output.length + 1);
  if (!entry || ids.has(entry.passage_id)) {
    return;
  }
  ids.add(entry.passage_id);
  output.push(entry);
}

function normalizeEntry(
  value: unknown,
  fallbackVolume: JsonObject | undefined,
  fallbackSequence: number,
): ReaderManifestEntry | undefined {
  const object = asObject(value);
  if (!hasPassageId(object)) {
    return undefined;
  }
  const chapter = asObject(object.chapter);
  const volume = asObject(object.volume);
  const fallback = fallbackVolume ?? {};
  const volumeNo = numberValue(
    object.volume_no,
    object.volumeNo,
    object.juan_no,
    object.juanNo,
    volume.volume_no,
    volume.volumeNo,
    volume.juan_no,
    volume.juanNo,
    fallback.volume_no,
    fallback.volumeNo,
    fallback.juan_no,
    fallback.juanNo,
  ) ?? 0;
  const availableVersions = normalizeManifestVersions(
    object.available_versions ?? object.availableVersions ?? object.versions,
  );
  return {
    sequence: numberValue(object.sequence, object.sort_order, object.sortOrder) ?? fallbackSequence,
    passage_id: firstText(object.passage_id, object.passageId, object.id, object.chapter_id, object.chapterId),
    volume_id: firstText(object.volume_id, object.volumeId, volume.id, fallback.id, fallback.volume_id, `shiji-volume-${volumeNo}`),
    volume_no: volumeNo,
    volume_title: firstText(object.volume_title, object.volumeTitle, volume.title, volume.title_traditional, volume.title_simplified, fallback.title, fallback.title_traditional, `卷 ${volumeNo}`),
    work_type: firstText(object.work_type, object.workType, volume.work_type, fallback.work_type),
    category_id: firstText(object.category_id, object.categoryId, volume.category_id, fallback.category_id),
    category_title_traditional: firstText(
      object.category_title_traditional,
      object.categoryTitleTraditional,
      volume.category_title_traditional,
      fallback.category_title_traditional,
    ),
    category_title_simplified: firstText(
      object.category_title_simplified,
      object.categoryTitleSimplified,
      volume.category_title_simplified,
      fallback.category_title_simplified,
    ),
    chapter_id: firstText(object.chapter_id, object.chapterId, chapter.id, `${firstText(object.passage_id, object.passageId, object.id, object.chapter_id)}-chapter`),
    chapter_title: firstText(object.chapter_title, object.chapterTitle, chapter.title, object.title, object.title_traditional, object.title_simplified, "未命名篇章"),
    chapter_type: firstText(object.chapter_type, object.chapterType, chapter.type, fallback.chapter_type, "篇章"),
    title: firstText(object.title, object.name, object.title_traditional, object.title_simplified, chapter.title, object.chapter_title, object.passage_id, object.chapter_id),
    preview_traditional: firstText(
      object.preview_traditional,
      object.previewTraditional,
      chapter.preview_traditional,
      chapter.previewTraditional,
    ),
    preview_simplified: firstText(
      object.preview_simplified,
      object.previewSimplified,
      chapter.preview_simplified,
      chapter.previewSimplified,
    ),
    commentary: normalizeDirectoryCommentary(
      object.commentary ?? chapter.commentary,
    ),
    mixed: normalizeDirectoryCommentary(
      object.mixed ?? chapter.mixed,
    ),
    previous_id: nullableText(object.previous_id, object.previousId, asObject(object.previous).passage_id, asObject(object.previous).id),
    next_id: nullableText(object.next_id, object.nextId, asObject(object.next).passage_id, asObject(object.next).id),
    available_versions: availableVersions,
  };
}

function normalizeDirectoryCommentary(value: unknown): ReaderManifestEntry["commentary"] {
  const object = asObject(value);
  if (!Object.keys(object).length) {
    return undefined;
  }
  return {
    available: Boolean(object.available ?? arrayValue(object.sentence_ids ?? object.sentenceIds).length),
    title_traditional: firstText(object.title_traditional, object.titleTraditional, "注文"),
    title_simplified: firstText(object.title_simplified, object.titleSimplified, "注文"),
    preview_traditional: firstText(object.preview_traditional, object.previewTraditional),
    preview_simplified: firstText(object.preview_simplified, object.previewSimplified),
    sentence_ids: arrayValue(object.sentence_ids ?? object.sentenceIds).filter(
      (item): item is string => typeof item === "string" && item.length > 0,
    ),
  };
}

function normalizeManifestVersions(value: unknown): ReaderManifestVersionInfo[] {
  const versions = arrayValue(value).map((item): ReaderManifestVersionInfo | undefined => {
    const object = asObject(item);
    const id = firstText(object.id, object.version_id, object.versionId);
    if (!id) {
      return undefined;
    }
    return {
      id,
      name: firstText(object.name, object.label, id),
      current: Boolean(object.current ?? object.is_current),
      page_ids: stringArray(object.page_ids ?? object.pageIds),
      ocr_batch_ids: stringArray(object.ocr_batch_ids ?? object.ocrBatchIds),
      source_ref_ids: stringArray(object.source_ref_ids ?? object.sourceRefIds),
    };
  }).filter((item): item is ReaderManifestVersionInfo => Boolean(item));
  return versions.length ? versions : [{ id: "application-primary", name: "应用文本", current: true }];
}

function normalizeVersion(value: unknown, fallbackId: string): VersionInfo {
  const object = typeof value === "string" ? { id: value, name: value } : asObject(value);
  return {
    ...object,
    id: firstText(object.id, object.version_id, fallbackId),
    name: firstText(object.name, object.label, object.version_id, fallbackId),
    page_ids: stringArray(object.page_ids ?? object.pageIds),
    ocr_batch_ids: stringArray(object.ocr_batch_ids ?? object.ocrBatchIds),
    source_ref_ids: stringArray(object.source_ref_ids ?? object.sourceRefIds),
  } as VersionInfo;
}

function normalizeVersions(value: unknown, current: VersionInfo): VersionInfo[] {
  const versions = arrayValue(value).map((item) => normalizeVersion(item, current.id));
  const seen = new Set<string>();
  const result = versions.filter((version) => {
    if (!version.id || seen.has(version.id)) {
      return false;
    }
    seen.add(version.id);
    return true;
  });
  if (!seen.has(current.id)) {
    result.unshift(current);
  }
  return result.length ? result : [current];
}

function normalizePageIds(...values: unknown[]): string[] {
  const ids: string[] = [];
  for (const value of values) {
    if (Array.isArray(value)) {
      ids.push(...stringArray(value));
      for (const item of value) {
        const object = asObject(item);
        const id = firstText(object.page_id, object.pageId, object.id);
        if (id) {
          ids.push(id);
        }
      }
      continue;
    }
    for (const item of arrayValue(value)) {
      const object = asObject(item);
      const id = firstText(object.page_id, object.pageId, object.id);
      if (id) {
        ids.push(id);
      }
    }
  }
  return [...new Set(ids)];
}

function normalizeSentences(value: unknown, passageId: string) {
  let cursor = 0;
  return arrayValue(value).map((item, index) => {
    const object = asObject(item);
    const original = firstText(object.original_text, object.original, object.raw_text, object.traditional, object.text);
    const punctuated = firstText(
      object.punctuated_text,
      object.punctuated_traditional,
      object.punctuated,
      object.traditional_text,
      original,
    );
    const simplified = firstText(object.simplified_text, object.simplified, punctuated);
    const rawRange = Array.isArray(object.raw_range) ? object.raw_range : [];
    const rawStart = numberValue(object.raw_start, object.rawStart, rawRange[0]) ?? cursor;
    const rawEnd = numberValue(object.raw_end, object.rawEnd, rawRange[1]) ?? rawStart + original.length;
    const utf16Start = numberValue(object.utf16_start, object.utf16Start, object.start) ?? cursor;
    const utf16End = numberValue(object.utf16_end, object.utf16End, object.end) ?? utf16Start + punctuated.length;
    cursor = utf16End + 1;
    return {
      sentence_id: firstText(object.sentence_id, object.sentenceId, object.id, `${passageId}--s${String(index + 1).padStart(6, "0")}`),
      raw_start: rawStart,
      raw_end: Math.max(rawStart + 1, rawEnd),
      utf16_start: utf16Start,
      utf16_end: Math.max(utf16Start + 1, utf16End),
      original_text: original,
      punctuated_text: punctuated,
      simplified_text: simplified,
      translation: firstText(object.translation, object.translated_text, object.translation_text, ""),
      content_layer: firstText(object.content_layer, object.contentLayer, "body") as "body" | "commentary" | "paratext" | "mixed",
      source_layer: typeof object.source_layer === "string" ? object.source_layer : null,
      source_layers: stringArray(object.source_layers ?? object.sourceLayers),
      section_ids: stringArray(object.section_ids ?? object.sectionIds),
      source_span_ids: stringArray(object.source_span_ids ?? object.sourceSpanIds),
      page_index: numberValue(object.page_index, object.pageIndex),
      entity_mentions: arrayValue(object.entity_mentions ?? object.entityMentions) as Array<Record<string, unknown>>,
    };
  }).filter((sentence) => sentence.punctuated_text.length > 0);
}

function normalizeEntities(value: unknown, candidateOnly = false): KnowledgeEntity[] {
  return arrayValue(value).map((item) => {
    const object = asObject(item);
    const type = firstText(object.type, "concept");
    const displayName = firstText(object.display_name, object.displayName, object.name, object.surface, object.canonical_name, object.candidate_id, "未命名实体");
    const facts = normalizeFacts(object.facts);
    const status = candidateOnly ? "uncertain" : normalizeEntityStatus(object);
    return {
      ...object,
      id: firstText(object.id, object.entity_id, object.candidate_id, displayName),
      type: type === "person" || type === "place" || type === "event" ? type : "concept",
      name: firstText(object.name, object.surface, object.canonical_name, displayName),
      display_name: displayName,
      aliases: stringArray(object.aliases),
      summary: firstText(object.summary, "当前仅登记了正文实体候选，待人工检查。"),
      source_ref_ids: stringArray(object.source_ref_ids ?? object.sourceRefIds ?? object.sourceSpanIds ?? object.source_span_ids),
      confidence: numberValue(object.confidence) ?? 0.5,
      status,
      facts,
      mention_id: firstText(object.mention_id, object.mentionId, object.sentence_id),
      surface: firstText(object.surface, object.name, displayName),
    } as KnowledgeEntity;
  });
}

function normalizeEntityStatus(object: JsonObject): KnowledgeEntity["status"] {
  const rawStatus = firstText(object.status, object.review_status, object.reviewStatus).toLowerCase();
  const humanStatus = firstText(object.human_status, object.humanStatus).toLowerCase();
  if (rawStatus === "confirmed" || rawStatus === "verified" || rawStatus === "passed"
    || humanStatus.includes("已校") || humanStatus.includes("已完成")
    || humanStatus.includes("verified") || humanStatus.includes("confirmed")) {
    return "confirmed";
  }
  if (rawStatus === "likely" || rawStatus === "probable") {
    return "likely";
  }
  return "uncertain";
}

function normalizeFacts(value: unknown): KnowledgeFact[] {
  return arrayValue(value).map((item, index) => {
    const object = asObject(item);
    const rawValue = object.value;
    const normalizedValue = typeof rawValue === "string" || typeof rawValue === "number" || typeof rawValue === "boolean"
      ? rawValue
      : firstText(rawValue, object.text, "未提供");
    return {
      field: firstText(object.field, object.label, object.name, "事实 " + String(index + 1)),
      value: normalizedValue,
      source_ref_ids: stringArray(object.source_ref_ids ?? object.sourceRefIds ?? object.source_ids ?? object.sourceIds),
      confidence: numberValue(object.confidence) ?? 0.5,
      status: object.status === "confirmed"
        ? "confirmed"
        : object.status === "likely"
          ? "likely"
          : "uncertain",
      note: firstText(object.note, object.warning, ""),
    } satisfies KnowledgeFact;
  });
}

export function normalizeKnowledge(value: unknown): ShijiKnowledgeSummary | undefined {
  const object = asObject(value);
  if (!Object.keys(object).length) {
    return undefined;
  }
  const dictionary = asObject(object.dictionary ?? object.entity_dictionary_ref ?? object.entityDictionaryRef);
  return {
    availability: firstText(object.availability, object.status, "unavailable"),
    warning: nullableText(object.warning, object.message),
    dictionary: firstText(dictionary.path, dictionary.uri) || firstText(dictionary.sha256)
      ? {
          path: firstText(dictionary.path, dictionary.uri),
          sha256: firstText(dictionary.sha256),
        }
      : null,
    entity_ids: stringArray(object.entity_ids ?? object.entityIds),
    mention_ids: stringArray(object.mention_ids ?? object.mentionIds),
    unresolved_mention_count: numberValue(
      object.unresolved_mention_count,
      object.unresolvedMentionCount,
      object.unresolved,
    ) ?? (Array.isArray(object.unresolved) ? object.unresolved.length : 0),
    ai_status: nullableText(object.ai_status, object.aiStatus),
    human_status: nullableText(object.human_status, object.humanStatus),
  };
}

export function normalizeMapSummary(value: unknown): ShijiMapSummary | null {
  const object = asObject(value);
  if (!Object.keys(object).length) {
    return null;
  }
  const volumeIndex = asObject(object.volume_index ?? object.volumeIndex);
  const missingState = asObject(object.missing_state ?? object.missingState);
  const contextPoints = arrayValue(object.context_points ?? object.contextPoints)
    .map((item) => normalizeMapContextPoint(item))
    .filter((item): item is ShijiMapContextPoint => Boolean(item));
  return {
    availability: firstText(object.availability, object.status, "missing"),
    warning: nullableText(object.warning, object.message),
    coverage_state: nullableText(object.coverage_state, object.coverageState),
    volume_index: firstText(volumeIndex.path) || firstText(volumeIndex.sha256)
      ? {
          path: firstText(volumeIndex.path),
          sha256: firstText(volumeIndex.sha256),
        }
      : null,
    chapter_candidate_count: numberValue(
      object.chapter_candidate_count,
      object.chapterCandidateCount,
    ) ?? 0,
    curated_scenes: arrayValue(object.curated_scenes ?? object.curatedScenes)
      .map((item) => normalizeMapSceneSummary(item))
      .filter((item): item is ShijiMapSceneSummary => Boolean(item)),
    spatial_state: normalizeSpatialState(object.spatial_state ?? object.spatialState),
    animation_available: object.animation_available === true || object.animationAvailable === true,
    display_message: nullableText(object.display_message, object.displayMessage),
    event_markers: arrayValue(object.event_markers ?? object.eventMarkers)
      .map((item) => normalizeSpatialMarker(item, "event"))
      .filter((item): item is ShijiSpatialMarker => Boolean(item)),
    place_markers: arrayValue(object.place_markers ?? object.placeMarkers)
      .map((item) => normalizeSpatialMarker(item, "place"))
      .filter((item): item is ShijiSpatialMarker => Boolean(item)),
    place_candidate_count: numberValue(
      object.place_candidate_count,
      object.placeCandidateCount,
    ) ?? 0,
    place_markers_omitted: numberValue(
      object.place_markers_omitted,
      object.placeMarkersOmitted,
    ) ?? 0,
    context_points: contextPoints,
    context_point_count: Math.max(
      contextPoints.length,
      numberValue(object.context_point_count, object.contextPointCount) ?? 0,
    ),
    context_basemap: normalizeMapContextBasemap(
      object.context_basemap ?? object.contextBasemap,
    ),
    review_status: nullableText(object.review_status, object.reviewStatus),
    missing_state: {
      reasons: stringArray(missingState.reasons),
      curation_states: stringArray(missingState.curation_states ?? missingState.curationStates),
    },
  };
}

function normalizeMapSceneSummary(value: unknown): ShijiMapSceneSummary | undefined {
  const object = asObject(value);
  const sceneId = firstText(object.scene_id, object.sceneId, object.id);
  const apiPath = firstText(object.api_path, object.apiPath);
  if (!sceneId || !apiPath) {
    return undefined;
  }
  return {
    scene_id: sceneId,
    title: firstText(object.title, sceneId),
    render_ready: object.render_ready === true || object.renderReady === true,
    render_mode: firstText(object.render_mode, object.renderMode, "event_card_only"),
    human_status: firstText(object.human_status, object.humanStatus, "人类待检查"),
    api_path: apiPath,
  };
}

export function normalizeMapScene(value: unknown, fallbackSceneId = "unknown-scene"): ShijiMapScene {
  const object = asObject(value);
  const validTime = normalizeMapValidTime(object.valid_time ?? object.validTime);
  return {
    ...object,
    scene_id: firstText(object.scene_id, object.sceneId, fallbackSceneId),
    title: firstText(object.title, firstText(object.scene_id, fallbackSceneId)),
    summary: firstText(object.summary, "当前场景尚无摘要。"),
    render_ready: object.render_ready === true || object.renderReady === true,
    render_mode: firstText(object.render_mode, object.renderMode, "event_card_only"),
    human_status: firstText(object.human_status, object.humanStatus, "人类待检查"),
    readiness_reason: firstText(object.readiness_reason, object.readinessReason, ""),
    valid_time: validTime,
    timeline: normalizeMapTimeline(object.timeline),
    place_points: arrayValue(object.place_points ?? object.placePoints).map(normalizeMapPlacePoint),
    source_ids: stringArray(object.source_ids ?? object.sourceIds),
    historical_boundaries: arrayValue(object.historical_boundaries ?? object.historicalBoundaries),
    routes: arrayValue(object.routes),
    force_ranges: arrayValue(object.force_ranges ?? object.forceRanges),
    unresolved: arrayValue(object.unresolved).map((item) => asObject(item)),
  };
}

function normalizeMapValidTime(value: unknown): ShijiMapValidTime | null {
  const object = asObject(value);
  if (!Object.keys(object).length) {
    return null;
  }
  return {
    original_label: firstText(object.original_label, object.originalLabel, object.label, "未标注年代"),
    proleptic_year_start: numberValue(object.proleptic_year_start, object.prolepticYearStart) ?? null,
    proleptic_year_end: numberValue(object.proleptic_year_end, object.prolepticYearEnd) ?? null,
    precision: firstText(object.precision, "unknown"),
    confidence: firstText(object.confidence, "unknown"),
    source_ids: stringArray(object.source_ids ?? object.sourceIds),
  };
}

function normalizeMapPlacePoint(value: unknown): ShijiMapPlacePoint {
  const object = asObject(value);
  const geometrySource = asObject(object.geometry);
  const coordinates = Array.isArray(geometrySource.coordinates)
    ? geometrySource.coordinates.filter((item): item is number => typeof item === "number" && Number.isFinite(item))
    : [];
  const geometry = firstText(geometrySource.type) && coordinates.length >= 2
    ? { type: firstText(geometrySource.type), coordinates }
    : null;
  return {
    point_id: firstText(object.point_id, object.pointId, object.id, "unknown-point"),
    label: firstText(object.label, object.name, "未命名点位"),
    short_label: firstText(object.short_label, object.shortLabel) || undefined,
    historical_name: firstText(object.historical_name, object.historicalName, object.label, ""),
    geometry,
    crs: firstText(object.crs, object.coordinate_reference_system, object.coordinateReferenceSystem),
    geometry_role: firstText(object.geometry_role, object.geometryRole, "place"),
    applicable_time: normalizeMapValidTime(object.applicable_time ?? object.applicableTime),
    confidence: stringRecord(object.confidence),
    source_ids: stringArray(object.source_ids ?? object.sourceIds),
    renderable: object.renderable === true,
  };
}

function normalizeMapTimeline(value: unknown): ShijiMapTimelineEvent[] {
  return arrayValue(value).map((item, index) => {
    const object = asObject(item);
    return {
      event_id: firstText(object.event_id, object.eventId, object.id, "event-" + String(index + 1)),
      order: numberValue(object.order) ?? index + 1,
      label: firstText(object.label, object.title, "未命名事件"),
      time: normalizeMapValidTime(object.time),
      anchor_ids: stringArray(object.anchor_ids ?? object.anchorIds),
      place_point_ids: stringArray(object.place_point_ids ?? object.placePointIds),
      source_ids: stringArray(object.source_ids ?? object.sourceIds),
      confidence: firstText(object.confidence, "unknown"),
      spatial_effect: firstText(object.spatial_effect, object.spatialEffect, ""),
    };
  });
}

function stringRecord(value: unknown): Record<string, string> {
  const object = asObject(value);
  return Object.fromEntries(
    Object.entries(object).map(([key, item]) => [key, firstText(item)]),
  );
}

function normalizeHighlights(
  value: unknown,
  sentences: ReturnType<typeof normalizeSentences>,
  entities: KnowledgeEntity[],
): TextHighlight[] {
  const existing = arrayValue(value) as TextHighlight[];
  if (existing.length) {
    return existing;
  }
  const entityTypes = new Map(entities.map((entity) => [entity.id, entity.type]));
  return sentences.flatMap((sentence): TextHighlight[] => (sentence.entity_mentions?.map((item, index): TextHighlight | undefined => {
    const mention = asObject(item);
    const start = numberValue(mention.start, mention.normalized_start) ?? 0;
    const end = numberValue(mention.end, mention.normalized_end) ?? start;
    const targetId = firstText(mention.entity_id, mention.entityId);
    if (!targetId || end <= start) {
      return undefined;
    }
    const type = entityTypes.get(targetId) ?? "concept";
    return {
      id: firstText(mention.mention_id, mention.mentionId, `${sentence.sentence_id}-mention-${index + 1}`),
      version_id: undefined,
      type,
      label: type === "person" ? "人物" : type === "place" ? "地名" : type === "event" ? "事件" : "关键词",
      start: sentence.utf16_start + start,
      end: sentence.utf16_start + end,
      text: firstText(mention.surface, ""),
      target_id: targetId,
      color: type === "person" ? "amber" : type === "place" ? "green" : type === "event" ? "blue" : "purple",
      confidence: numberValue(mention.confidence) ?? 0.5,
      status: mention.status === "confirmed" ? "confirmed" : "uncertain",
    } as TextHighlight;
  }).filter((item): item is TextHighlight => Boolean(item)) ?? []));
}

function normalizeChapterLayer(value: unknown): ShijiChapterRuntime["commentary"] {
  const object = asObject(value);
  if (!Object.keys(object).length) {
    return undefined;
  }
  return {
    title_traditional: firstText(object.title_traditional, object.titleTraditional),
    title_simplified: firstText(object.title_simplified, object.titleSimplified),
    sentences: arrayValue(object.sentences) as NonNullable<ShijiChapterRuntime["commentary"]>["sentences"],
    sentence_ids: stringArray(object.sentence_ids ?? object.sentenceIds),
  };
}

function pageOrdinalToken(value: string): string {
  const match = value.match(/(?:^|[-:])p(\d{3,})(?:$|[-:])/i);
  return match ? `p${match[1]}` : "";
}

function pageIndexForEquivalentSourceSpan(
  sourceSpanId: string,
  versionIds: Set<string>,
  pageIndexByVersionAndOrdinal: Map<string, number>,
  pageIndexByUniqueOrdinal: Map<string, number>,
): number | undefined {
  const ordinal = pageOrdinalToken(sourceSpanId);
  if (!ordinal) {
    return undefined;
  }
  const matchingVersionIds = [...versionIds]
    .filter((versionId) => sourceSpanId.includes(versionId))
    .sort((left, right) => right.length - left.length);
  for (const versionId of matchingVersionIds) {
    const pageIndex = pageIndexByVersionAndOrdinal.get(`${versionId}:${ordinal}`);
    if (pageIndex !== undefined) {
      return pageIndex;
    }
  }
  return pageIndexByUniqueOrdinal.get(ordinal);
}

function normalizeSpatialState(value: unknown): ShijiMapSummary["spatial_state"] {
  return value === "event_animation"
    || value === "place_context"
    || value === "no_spatial_content"
    ? value
    : null;
}

function normalizeSpatialMarker(
  value: unknown,
  expectedKind: "event" | "place",
): ShijiSpatialMarker | undefined {
  const object = asObject(value);
  const markerId = firstText(object.marker_id, object.markerId);
  const label = firstText(object.label, object.name);
  const firstSentenceId = firstText(object.first_sentence_id, object.firstSentenceId);
  if (!markerId || !label || !firstSentenceId) {
    return undefined;
  }
  const rawScope = firstText(object.spatial_scope, object.spatialScope);
  const spatialScope: ShijiSpatialMarker["spatial_scope"] =
    rawScope === "event_candidate"
    || rawScope === "historical_title_or_fief_context"
    || rawScope === "historical_region_context"
    || rawScope === "historical_polity_context"
    || rawScope === "curated_place_name"
      ? rawScope
      : "unresolved_place_name";
  const rawAnchorScope = firstText(object.anchor_scope, object.anchorScope);
  const anchorScope: ShijiSpatialMarker["anchor_scope"] =
    rawAnchorScope === "chapter_title" || rawAnchorScope === "volume_title"
      ? rawAnchorScope
      : "body_sentence";
  return {
    marker_id: markerId,
    kind: expectedKind,
    spatial_scope: spatialScope,
    anchor_scope: anchorScope,
    source_context: nullableText(object.source_context, object.sourceContext),
    label,
    surface_forms: stringArray(object.surface_forms ?? object.surfaceForms),
    entity_id: nullableText(object.entity_id, object.entityId),
    first_sentence_id: firstSentenceId,
    sentence_ids: stringArray(object.sentence_ids ?? object.sentenceIds),
    mention_count: numberValue(object.mention_count, object.mentionCount) ?? 1,
    excerpt_traditional: firstText(object.excerpt_traditional, object.excerptTraditional),
    excerpt_simplified: firstText(object.excerpt_simplified, object.excerptSimplified),
    source_basis: stringArray(object.source_basis ?? object.sourceBasis),
    source_ref_ids: stringArray(object.source_ref_ids ?? object.sourceRefIds),
    confidence: numberValue(object.confidence) ?? 0,
    review_status: firstText(object.review_status, object.reviewStatus, "人类待检查"),
    coordinate_status: "unlocated",
    render_role: expectedKind === "event" ? "textual_event_marker" : "textual_place_marker",
    render_ready: false,
    not_claims: stringArray(object.not_claims ?? object.notClaims),
  };
}

function normalizeMapContextBinding(value: unknown): ShijiMapContextBinding | undefined {
  const object = asObject(value);
  const bindingId = firstText(object.binding_id, object.bindingId);
  const markerId = firstText(object.marker_id, object.markerId);
  const contextId = firstText(object.context_id, object.contextId);
  const firstSentenceId = firstText(object.first_sentence_id, object.firstSentenceId);
  if (!bindingId || !markerId || !contextId || !firstSentenceId) {
    return undefined;
  }
  return {
    binding_id: bindingId,
    marker_id: markerId,
    context_id: contextId,
    matched_label: firstText(object.matched_label, object.matchedLabel),
    first_sentence_id: firstSentenceId,
    sentence_ids: stringArray(object.sentence_ids ?? object.sentenceIds),
    mention_count: numberValue(object.mention_count, object.mentionCount) ?? 1,
    excerpt_traditional: firstText(object.excerpt_traditional, object.excerptTraditional),
    excerpt_simplified: firstText(object.excerpt_simplified, object.excerptSimplified),
  };
}

function normalizeMapContextPoint(value: unknown): ShijiMapContextPoint | undefined {
  const object = asObject(value);
  const geometry = asObject(object.geometry);
  const rawCoordinates = arrayValue(geometry.coordinates);
  const longitude = numberValue(rawCoordinates[0]);
  const latitude = numberValue(rawCoordinates[1]);
  const contextId = firstText(object.context_id, object.contextId);
  const canonicalName = firstText(object.canonical_name, object.canonicalName);
  if (
    !contextId
    || !canonicalName
    || geometry.type !== "Point"
    || longitude === undefined
    || latitude === undefined
    || longitude < -180
    || longitude > 180
    || latitude < -90
    || latitude > 90
    || object.render_ready !== true
  ) {
    return undefined;
  }
  const rawRole = firstText(object.coordinate_role, object.coordinateRole);
  const coordinateRole: ShijiMapContextPoint["coordinate_role"] =
    rawRole === "historical_place_context"
    || rawRole === "historical_site_context"
    || rawRole === "historical_landmark_context"
    || rawRole === "modern_place_context"
    || rawRole === "modern_protected_site_context"
    || rawRole === "physical_feature_context"
      ? rawRole
      : "modern_place_context";
  const rawConfidence = firstText(object.confidence);
  const confidence: ShijiMapContextPoint["confidence"] =
    rawConfidence === "low" || rawConfidence === "high" ? rawConfidence : "medium";
  const curation = asObject(object.curation);
  return {
    context_id: contextId,
    canonical_name: canonicalName,
    applies_to_labels: stringArray(object.applies_to_labels ?? object.appliesToLabels),
    display_name: firstText(object.display_name, object.displayName, canonicalName),
    geometry: { type: "Point", coordinates: [longitude, latitude] },
    crs: "EPSG:4326",
    coordinate_order: "longitude_latitude",
    coordinate_role: coordinateRole,
    historical_equivalence: firstText(
      object.historical_equivalence,
      object.historicalEquivalence,
    ),
    confidence,
    source_ids: stringArray(object.source_ids ?? object.sourceIds),
    source_evidence: asObject(object.source_evidence ?? object.sourceEvidence),
    curation: {
      decision_set_id: firstText(curation.decision_set_id, curation.decisionSetId),
      decision_reason: firstText(curation.decision_reason, curation.decisionReason),
      ai_status: firstText(curation.ai_status, curation.aiStatus),
      human_status: firstText(curation.human_status, curation.humanStatus),
    },
    render_role: "context_point_only",
    render_ready: true,
    not_claims: stringArray(object.not_claims ?? object.notClaims),
    bindings: arrayValue(object.bindings)
      .map((item) => normalizeMapContextBinding(item))
      .filter((item): item is ShijiMapContextBinding => Boolean(item)),
  };
}

function normalizeMapContextBasemap(value: unknown): ShijiMapContextBasemap | null {
  const object = asObject(value);
  const rawDimensions = arrayValue(object.dimensions);
  const rawBbox = arrayValue(object.bbox_wgs84 ?? object.bboxWgs84);
  const width = numberValue(rawDimensions[0]);
  const height = numberValue(rawDimensions[1]);
  const west = numberValue(rawBbox[0]);
  const south = numberValue(rawBbox[1]);
  const east = numberValue(rawBbox[2]);
  const north = numberValue(rawBbox[3]);
  const assetUrl = firstText(object.asset_url, object.assetUrl);
  if (
    !assetUrl
    || object.render_ready !== true
    || width === undefined
    || height === undefined
    || west === undefined
    || south === undefined
    || east === undefined
    || north === undefined
  ) {
    return null;
  }
  return {
    asset_path: firstText(object.asset_path, object.assetPath),
    asset_url: assetUrl,
    sha256: firstText(object.sha256),
    mime_type: "image/jpeg",
    dimensions: [width, height],
    bbox_wgs84: [west, south, east, north],
    crs: "EPSG:4326",
    coordinate_order: "longitude_latitude",
    title: firstText(object.title, "地形语境底图"),
    subtitle: firstText(object.subtitle),
    source_ids: stringArray(object.source_ids ?? object.sourceIds),
    attribution: firstText(object.attribution),
    render_ready: true,
    not_claims: stringArray(object.not_claims ?? object.notClaims),
  };
}

function normalizeRuntime(
  source: JsonObject,
  sentences: ReturnType<typeof normalizeSentences>,
  passageId: string,
  versionId: string,
  root: JsonObject,
): ShijiChapterRuntime {
  const dictionary = asObject(source.entity_dictionary_ref ?? source.entityDictionaryRef);
  return {
    ...source,
    schema_version: 1,
    artifact_type: "shiji_chapter_runtime",
    chapter_id: firstText(source.chapter_id, source.chapterId, passageId),
    primary_version_id: firstText(source.primary_version_id, source.primaryVersionId, versionId),
    applies_to_current_version: source.applies_to_current_version !== false,
    runtime_sha256: firstText(source.runtime_sha256, source.runtimeSha256, ""),
    sentences: sentences.map((sentence) => ({ ...sentence })),
    commentary: normalizeChapterLayer(source.commentary),
    mixed: normalizeChapterLayer(source.mixed),
    paratext: normalizeChapterLayer(source.paratext),
    sections: Array.isArray(source.sections) ? source.sections as Array<Record<string, unknown>> : undefined,
    entity_dictionary_ref: {
      path: firstText(dictionary.path, ""),
      sha256: firstText(dictionary.sha256, ""),
      entity_ids: stringArray(dictionary.entity_ids ?? dictionary.entityIds),
    },
    knowledge: normalizeKnowledge(source.knowledge ?? root.knowledge),
    mention_index: Array.isArray(source.mention_index)
      ? source.mention_index as Array<Record<string, unknown>>
      : Array.isArray(root.mentions)
        ? root.mentions as Array<Record<string, unknown>>
        : undefined,
    historical_map: normalizeMapSummary(source.historical_map ?? root.historical_map),
  };
}

function normalizeReading(
  value: unknown,
  text: string,
  sentences: ReturnType<typeof normalizeSentences>,
  pageIds: string[],
  passageId: string,
): PassageReading {
  const object = asObject(value);
  const page = asObject(object.page);
  const rawSegments = arrayValue(object.segments).map((item, index) => {
    const segment = asObject(item);
    const start = numberValue(segment.start, segment.raw_start) ?? 0;
    const end = numberValue(segment.end, segment.raw_end) ?? text.length;
    return {
      id: firstText(segment.id, `${passageId}-segment-${index + 1}`),
      label: firstText(segment.label, `第 ${index + 1} 段`),
      start,
      end: Math.max(start, end),
    };
  });
  const segments = rawSegments.length
    ? rawSegments
    : sentences.map((sentence, index) => ({
        id: sentence.sentence_id,
        label: `章节句读 · 第 ${index + 1} 句`,
        start: sentence.utf16_start,
        end: sentence.utf16_end,
      }));
  return {
    mode: firstText(object.mode, "segment") as "segment" | "page",
    page: {
      page_id: firstText(page.page_id, page.pageId, pageIds[0], ""),
      page_no: numberValue(page.page_no, page.pageNo) ?? 1,
      total_pages: numberValue(page.total_pages, page.totalPages) ?? Math.max(1, pageIds.length),
      passage_ids: stringArray(page.passage_ids ?? page.passageIds),
    },
    segments,
  };
}

function normalizeSequence(value: unknown, passageId: string, versionId: string): ReaderSequence | undefined {
  const object = asObject(value);
  if (!Object.keys(object).length) {
    return undefined;
  }
  const current = normalizeTarget(object.current, passageId, numberValue(object.position) ?? 1);
  const previous = object.previous ? normalizeTarget(object.previous, "", 0) : null;
  const next = object.next ? normalizeTarget(object.next, "", 0) : null;
  return {
    manifest_id: firstText(object.manifest_id, object.manifestId, "shiji-application-reader"),
    book_id: firstText(object.book_id, object.bookId, SHIJI_BOOK_ID),
    book_title: firstText(object.book_title, object.bookTitle, "史记"),
    position: numberValue(object.position) ?? current.sequence,
    total: numberValue(object.total, object.total_passages) ?? current.sequence,
    volume: {
      id: firstText(asObject(object.volume).id, "shiji-volume-unknown"),
      number: numberValue(asObject(object.volume).number, asObject(object.volume).volume_no) ?? 0,
      title: firstText(asObject(object.volume).title, "当前卷"),
    },
    chapter: {
      id: firstText(asObject(object.chapter).id, "shiji-chapter-unknown"),
      title: firstText(asObject(object.chapter).title, "当前篇章"),
      type: firstText(asObject(object.chapter).type, "篇章"),
    },
    current: { ...current, available_version_ids: current.available_version_ids.length ? current.available_version_ids : [versionId] },
    previous,
    next,
    selected_version_id: firstText(object.selected_version_id, object.selectedVersionId, versionId),
    available_version_ids: stringArray(object.available_version_ids ?? object.availableVersionIds),
  };
}

function normalizeTarget(value: unknown, fallbackId: string, fallbackSequence: number): ReaderSequenceTarget {
  const object = asObject(value);
  return {
    passage_id: firstText(object.passage_id, object.passageId, object.id, fallbackId),
    sequence: numberValue(object.sequence, object.position) ?? fallbackSequence,
    title: firstText(object.title, object.name, "未命名篇章"),
    available_version_ids: stringArray(object.available_version_ids ?? object.availableVersionIds),
  };
}

function normalizeReaderConfig(value: unknown) {
  const object = asObject(value);
  const modes = arrayValue(object.available_modes ?? object.availableModes) as ReadingMode[];
  return {
    default_mode: firstText(object.default_mode, object.defaultMode, "segment"),
    available_modes: modes.length ? modes : [
      { id: "segment", name: "分段", description: "按句读或逻辑段阅读" },
      { id: "page", name: "分页", description: "按书影页阅读" },
    ],
    context_tabs: stringArray(object.context_tabs ?? object.contextTabs),
  };
}

function normalizeMentions(value: unknown) {
  const object = asObject(value);
  return {
    ...EMPTY_GROUPS,
    persons: arrayValue(object.persons) as KnowledgeEntity[],
    places: arrayValue(object.places) as KnowledgeEntity[],
    events: arrayValue(object.events) as KnowledgeEntity[],
    concepts: arrayValue(object.concepts) as KnowledgeEntity[],
  };
}

function normalizePublication(value: unknown): PublicationReview | undefined {
  if (!value || typeof value !== "object") {
    return undefined;
  }
  const object = asObject(value);
  const aiStatus = firstText(object.ai_status, object.aiStatus, "AI初筛完成");
  const humanStatus = firstText(object.human_status, object.humanStatus, "人类待检查");
  const stages = arrayValue(object.stages) as PublicationReview["stages"];
  return {
    ai_status: aiStatus as PublicationReview["ai_status"],
    human_status: humanStatus as PublicationReview["human_status"],
    stages,
    human_reviewed_by: nullableText(object.human_reviewed_by, object.humanReviewedBy),
    updated_at: firstText(object.updated_at, object.updatedAt, new Date(0).toISOString()),
  };
}

function hasPassageId(value: JsonObject) {
  return Boolean(firstText(value.passage_id, value.passageId, value.id, value.chapter_id, value.chapterId));
}

function asObject(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : {};
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function stringArray(value: unknown): string[] {
  return arrayValue(value).filter((item): item is string => typeof item === "string" && item.length > 0);
}

function firstText(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      return value;
    }
    if (typeof value === "number" && Number.isFinite(value)) {
      return String(value);
    }
  }
  return "";
}

function nullableText(...values: unknown[]): string | null {
  const value = firstText(...values);
  return value || null;
}

function numberValue(...values: unknown[]): number | undefined {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
    if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) {
      return Number(value);
    }
  }
  return undefined;
}
