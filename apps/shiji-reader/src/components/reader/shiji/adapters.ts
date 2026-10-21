import type {
  KnowledgeEntity,
  PassagePayload,
  ReaderManifestEntry,
  TextHighlight,
} from "../../../services/api";
import type {
  ShijiCatalogGroup,
  ShijiInlinePart,
  ShijiReadingUnit,
} from "./types";

const sentenceEndings = new Set(["。", "！", "？", "；", "!", "?", ";", "\n"]);
const maximumUnitLength = 180;

export function buildShijiReadingUnits(payload: PassagePayload): ShijiReadingUnit[] {
  const runtime = payload.chapter_runtime;
  if (runtime?.applies_to_current_version && runtime.sentences.length) {
    const readerSentences = runtime.sentences.filter((sentence) =>
      sentence.content_layer !== "commentary"
      && sentence.content_layer !== "paratext"
      && sentence.content_layer !== "mixed",
    );
    const sentences = readerSentences.length ? readerSentences : runtime.sentences;
    return sentences.map((sentence, index) => ({
      id: sentence.sentence_id,
      label: `章节句读 · 第 ${index + 1} 句`,
      original: sentence.punctuated_text,
      rawOriginal: sentence.original_text,
      simplified: sentence.simplified_text,
      translation: sentence.translation,
      start: sentence.utf16_start,
      end: sentence.utf16_end,
      pageIndex: sentence.page_index ?? pageIndexForRawOffset(
        sentence.raw_start,
        payload.reading.segments,
        payload.current_version.page_ids?.length ?? 0,
      ),
    }));
  }
  const segments = payload.reading.segments.length
    ? payload.reading.segments
    : [
        {
          id: `${payload.passage.id}-text`,
          label: "当前段",
          start: 0,
          end: payload.text.length,
        },
      ];
  const pageIds = payload.current_version.page_ids ?? [];
  const units: ShijiReadingUnit[] = [];

  segments.forEach((segment, segmentIndex) => {
    const segmentText = payload.text.slice(segment.start, segment.end);
    const ranges = splitDisplayRanges(segmentText);
    if (!ranges.length && segmentText) {
      ranges.push([0, segmentText.length]);
    }
    ranges.forEach(([localStart, localEnd], unitIndex) => {
      const start = segment.start + localStart;
      const end = segment.start + localEnd;
      units.push({
        id: `${segment.id}-${unitIndex + 1}`,
        label: ranges.length === 1 ? segment.label : `${segment.label} · ${unitIndex + 1}`,
        original: payload.text.slice(start, end),
        translation: "",
        start,
        end,
        pageIndex: pageIndexForSegment(segmentIndex, segments.length, pageIds.length),
      });
    });
  });

  return units;
}

export function buildInlineParts(
  unit: ShijiReadingUnit,
  highlights: TextHighlight[],
  entities: KnowledgeEntity[],
  textVariant: "traditional" | "simplified" = "traditional",
): ShijiInlinePart[] {
  const raw = unit.rawOriginal ?? unit.original;
  const display = textVariant === "simplified" && unit.simplified
    ? unit.simplified
    : unit.original;
  const entityById = new Map(entities.map((entity) => [entity.id, entity]));
  const located = highlights
    .filter((highlight) => highlight.start >= unit.start && highlight.end <= unit.end)
    .filter((highlight) => highlight.end > highlight.start)
    .sort((left, right) => left.start - right.start || right.end - left.end);
  const parts: ShijiInlinePart[] = [];
  let cursor = unit.start;
  let displayCursor = 0;

  for (const highlight of located) {
    if (highlight.start < cursor) {
      continue;
    }
    if (highlight.start > cursor) {
      const nextDisplay = selectedDisplayIndexForRawBoundary(
        raw,
        unit.original,
        display,
        highlight.start - unit.start,
      );
      parts.push({ text: display.slice(displayCursor, nextDisplay) });
      displayCursor = nextDisplay;
    }
    const highlightDisplayEnd = selectedDisplayIndexForRawBoundary(
      raw,
      unit.original,
      display,
      highlight.end - unit.start,
    );
    const entity = entityById.get(highlight.target_id);
    parts.push({
      text: display.slice(displayCursor, highlightDisplayEnd),
      highlight,
      entity,
      detailBelow: entity ? explicitPersonDetail(entity) : undefined,
    });
    cursor = highlight.end;
    displayCursor = highlightDisplayEnd;
  }

  if (cursor < unit.end) {
    parts.push({ text: display.slice(displayCursor) });
  }
  return parts.length ? parts : [{ text: display }];
}

export function buildCatalogGroups(entries: ReaderManifestEntry[]): ShijiCatalogGroup[] {
  const legacy: ReaderManifestEntry[] = [];
  const baina: ReaderManifestEntry[] = [];
  const siku: ReaderManifestEntry[] = [];
  const other: ReaderManifestEntry[] = [];

  for (const entry of entries) {
    const ids = entry.available_versions.map((version) => version.id);
    if (!entry.passage_id.startsWith("v2-")) {
      legacy.push(entry);
    } else if (ids.includes("baina-ia-mirror")) {
      baina.push(entry);
    } else if (ids.includes("siku-quanshu-ia-zju")) {
      siku.push(entry);
    } else {
      other.push(entry);
    }
  }

  return [
    {
      id: "formal",
      label: "篇章内容",
      description: "既有正式内容包",
      entries: legacy,
    },
    {
      id: "baina",
      label: "百衲本识读文本",
      description: "连续文本索引 · 未审查",
      entries: baina,
    },
    {
      id: "siku",
      label: "四库本识读文本",
      description: "连续文本索引 · 未审查",
      entries: siku,
    },
    {
      id: "other",
      label: "其他导入段",
      description: "连续文本索引",
      entries: other,
    },
  ].filter((group) => group.entries.length);
}

export function explicitPersonDetail(entity: KnowledgeEntity): string | undefined {
  if (entity.type !== "person") {
    return undefined;
  }
  const fact = entity.facts.find((item) =>
    /生卒|年齡|年龄|時年|时年|lifespan|\bage\b/i.test(item.field),
  );
  if (!fact || (typeof fact.value !== "string" && typeof fact.value !== "number")) {
    return undefined;
  }
  return String(fact.value);
}

function pageIndexForSegment(segmentIndex: number, segmentCount: number, pageCount: number) {
  if (pageCount <= 1 || segmentCount <= 1) {
    return 0;
  }
  if (pageCount === segmentCount) {
    return segmentIndex;
  }
  return Math.min(
    pageCount - 1,
    Math.round((segmentIndex / Math.max(1, segmentCount - 1)) * (pageCount - 1)),
  );
}

function pageIndexForRawOffset(
  offset: number,
  segments: PassagePayload["reading"]["segments"],
  pageCount: number,
) {
  const segmentIndex = Math.max(
    0,
    segments.findIndex((segment) => segment.start <= offset && offset < segment.end),
  );
  return pageIndexForSegment(segmentIndex, segments.length, pageCount);
}

function selectedDisplayIndexForRawBoundary(
  raw: string,
  punctuated: string,
  selected: string,
  boundary: number,
) {
  const punctuatedIndex = displayIndexForRawBoundary(raw, punctuated, boundary);
  if (selected.length === punctuated.length) {
    return punctuatedIndex;
  }
  return Math.round((punctuatedIndex / Math.max(1, punctuated.length)) * selected.length);
}

function displayIndexForRawBoundary(raw: string, punctuated: string, boundary: number) {
  if (raw === punctuated) {
    return boundary;
  }
  let rawIndex = 0;
  for (let displayIndex = 0; displayIndex < punctuated.length; displayIndex += 1) {
    if (rawIndex >= boundary) {
      return displayIndex;
    }
    if (punctuated[displayIndex] === raw[rawIndex]) {
      rawIndex += 1;
    }
  }
  return punctuated.length;
}

function splitDisplayRanges(text: string): Array<[number, number]> {
  const ranges: Array<[number, number]> = [];
  let start = 0;
  let length = 0;

  for (let index = 0; index < text.length; index += 1) {
    length += 1;
    const character = text[index];
    const atBoundary = sentenceEndings.has(character) || length >= maximumUnitLength;
    if (!atBoundary) {
      continue;
    }
    const end = index + 1;
    if (text.slice(start, end).trim()) {
      ranges.push([start, end]);
    }
    start = end;
    length = 0;
  }

  if (start < text.length && text.slice(start).trim()) {
    ranges.push([start, text.length]);
  }
  return ranges;
}
