import type { ShijiMapNarrativeStage } from "./api";

export function shijiSentenceFamily(sentenceId: string) {
  if (/-body-\d+/.test(sentenceId)) return "body";
  if (/-p\d{4}-s\d{3}$/.test(sentenceId)) return "page";
  if (/-c\d{3}-y\d{3}$/.test(sentenceId)) return "chapter-year";
  if (/-t\d{3}-u\d{3}$/.test(sentenceId)) return "chapter-table";
  if (/-c\d{3}-s\d{3}(?:-\d{2})?$/.test(sentenceId)) return "chapter";
  if (/-sentence-\d{3,5}(?:--long-\d{2}|-\d{2})?$/.test(sentenceId)) return "volume-sentence";
  if (/-reference-\d{4,5}$/.test(sentenceId)) return "reference";
  return "other";
}

export function shijiSentenceOrdinal(sentenceId: string) {
  const body = sentenceId.match(/-body-(\d{5})(?:--long-(\d{2})|-(\d{2}))?$/);
  if (body) return Number(body[1]) * 100 + Number(body[2] ?? body[3] ?? 0);
  const page = sentenceId.match(/-p(\d{4})-s(\d{3})$/);
  if (page) return Number(page[1]) * 1000 + Number(page[2]);
  const chapterYear = sentenceId.match(/-c\d{3}-y(\d{3})$/);
  if (chapterYear) return 1000 - Number(chapterYear[1]);
  const chapterTable = sentenceId.match(/-t(\d{3})-u(\d{3})$/);
  if (chapterTable) return Number(chapterTable[1]) * 1000 + Number(chapterTable[2]);
  const chapter = sentenceId.match(/-c\d{3}-s(\d{3})(?:-(\d{2}))?$/);
  if (chapter) return Number(chapter[1]) * 100 + Number(chapter[2] ?? 0);
  const volumeSentence = sentenceId.match(/-sentence-(\d{3,5})(?:--long-(\d{2})|-(\d{2}))?$/);
  if (volumeSentence) {
    return Number(volumeSentence[1]) * 100 + Number(volumeSentence[2] ?? volumeSentence[3] ?? 0);
  }
  const reference = sentenceId.match(/-reference-(\d{4,5})$/);
  if (reference) return Number(reference[1]);
  return null;
}

export function shijiStageSentenceId(stage: ShijiMapNarrativeStage) {
  return stage.runtime_sentence_id ?? stage.reading_anchor.sentence_id ?? "";
}

export function shijiStageIndexForSentence(
  stages: ShijiMapNarrativeStage[],
  activeSentenceId: string,
) {
  const activeFamily = shijiSentenceFamily(activeSentenceId);
  const activeOrdinal = shijiSentenceOrdinal(activeSentenceId);
  if (activeOrdinal === null) return 0;

  let nextIndex = 0;
  stages.forEach((stage, index) => {
    const stageSentenceId = shijiStageSentenceId(stage);
    const stageOrdinal = shijiSentenceOrdinal(stageSentenceId);
    if (
      shijiSentenceFamily(stageSentenceId) === activeFamily
      && stageOrdinal !== null
      && activeOrdinal >= stageOrdinal
    ) nextIndex = index;
  });
  return nextIndex;
}

export function shijiSceneFacsimileStages(
  stages: ShijiMapNarrativeStage[],
  selectedVersion: string,
) {
  return stages.filter((stage) => (
    Boolean(stage.reading_anchor.page_id)
    && stage.reading_anchor.version_id === selectedVersion
  ));
}

export function shijiPageOrdinal(pageId: string) {
  const match = pageId.match(/p(\d{4})$/);
  return match ? Number(match[1]) : Number.MAX_SAFE_INTEGER;
}

export function mergeShijiFacsimilePageIds(
  basePageIds: string[],
  stages: ShijiMapNarrativeStage[],
  selectedVersion: string,
) {
  const combined = [
    ...basePageIds,
    ...shijiSceneFacsimileStages(stages, selectedVersion)
      .map((stage) => stage.reading_anchor.page_id),
  ];
  return [...new Set(combined)].sort((left, right) => (
    shijiPageOrdinal(left) - shijiPageOrdinal(right)
  ));
}

export function activeShijiFacsimilePageId(
  stages: ShijiMapNarrativeStage[],
  selectedVersion: string,
  activeSentenceId: string,
) {
  const activeOrdinal = shijiSentenceOrdinal(activeSentenceId);
  if (activeOrdinal === null) return "";

  let pageId = "";
  for (const stage of shijiSceneFacsimileStages(stages, selectedVersion)) {
    const stageOrdinal = shijiSentenceOrdinal(shijiStageSentenceId(stage));
    if (stageOrdinal !== null && activeOrdinal >= stageOrdinal) {
      pageId = stage.reading_anchor.page_id;
    }
  }
  return pageId;
}
