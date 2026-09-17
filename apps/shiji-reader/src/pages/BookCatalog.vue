<template>
  <main class="page-shell book-catalog">
    <header v-if="book" class="catalog-header">
      <RouterLink class="breadcrumb-link" to="/">
        <ChevronLeft :size="16" aria-hidden="true" />
        《史记》专题
      </RouterLink>
      <div class="catalog-title-row">
        <div>
          <h1>《{{ book.title }}》</h1>
          <p>{{ book.author }} · {{ book.period }}</p>
        </div>
        <div class="catalog-primary-actions">
          <RouterLink v-if="firstPassage" class="primary-action" :to="`/reader/${firstPassage.id}`">
            <BookOpenText :size="17" aria-hidden="true" />
            进入连续阅读
          </RouterLink>
          <RouterLink v-if="ocrPages[0]" class="secondary-action" :to="`/reader/scan/${ocrPages[0].id}`">
            <ScanSearch :size="16" aria-hidden="true" />
            查看首个 OCR 页
          </RouterLink>
        </div>
      </div>
      <div class="reading-meta">
        <span>{{ statusLabel(book.status) }}</span>
        <span>{{ book.version_count ?? 0 }} 个版本</span>
        <span>{{ book.scan_file_count ?? 0 }} 个影印文件</span>
        <span>{{ formatNumber(ocrPageCount || book.ocr_page_count || 0) }} 页 OCR · 未审查</span>
      </div>
    </header>

    <section v-if="loading" class="panel loading-panel">
      <p>正在加载...</p>
    </section>
    <section v-else-if="error" class="panel loading-panel">
      <p class="error-text">{{ error }}</p>
    </section>

    <template v-else-if="book">
      <section v-if="toc?.v2_summary" class="shiji-import-summary" aria-label="史记 OCR 导入说明">
        <div>
          <span>OCR 全书导入</span>
          <strong>{{ formatNumber(ocrPageCount) }} 页</strong>
          <small>百衲本 4,782 页 · 四库本 6,560 页</small>
        </div>
        <div>
          <span>连续文本索引</span>
          <strong>{{ formatNumber(toc.v2_summary.pages) }} 页</strong>
          <small>{{ formatNumber(toc.v2_summary.reader_passages) }} 段 · {{ formatNumber(toc.v2_summary.source_batches) }} 批</small>
        </div>
        <p>
          两个入口均保持“人类待检查”。另有
          {{ formatNumber(Math.max(0, ocrPageCount - toc.v2_summary.pages)) }} 页已进入逐页书影，
          尚未进入当前连续文本索引。
        </p>
      </section>

      <div class="catalog-tabs" role="tablist" aria-label="书目内容">
        <button
          type="button"
          role="tab"
          :aria-selected="activeTab === 'pages'"
          :disabled="!ocrPageCount"
          :class="{ active: activeTab === 'pages' }"
          @click="activeTab = 'pages'"
        >
          影印页 <span>{{ ocrPageCount }}</span>
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="activeTab === 'versions'"
          :disabled="!versions.length"
          :class="{ active: activeTab === 'versions' }"
          @click="activeTab = 'versions'"
        >
          版本 <span>{{ versions.length }}</span>
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="activeTab === 'toc'"
          :disabled="!toc?.volumes.length"
          :class="{ active: activeTab === 'toc' }"
          @click="activeTab = 'toc'"
        >
          目录 <span>{{ toc?.volumes.length ?? 0 }}</span>
        </button>
      </div>

      <section v-if="activeTab === 'pages' && ocrPageCount" class="catalog-surface">
        <div class="catalog-toolbar">
          <div>
            <h2>已识别影印页</h2>
            <span>{{ ocrPageCount }} 页</span>
          </div>
          <label class="compact-select">
            <span>版本</span>
            <select v-model="ocrVersionFilter" @change="handleOcrVersionChange">
              <option value="">全部版本</option>
              <option v-for="version in ocrVersions" :key="version.id" :value="version.id">
                {{ version.name }}
              </option>
            </select>
          </label>
        </div>

        <div v-if="ocrPages.length" class="scan-page-list">
          <RouterLink
            v-for="page in ocrPages"
            :key="page.id"
            class="scan-page-link"
            :to="`/reader/scan/${page.id}`"
          >
            <span>{{ page.source_file_label }}</span>
            <strong>PDF 第 {{ page.pdf_page }} 页</strong>
            <small>{{ page.version_label }}</small>
            <small>{{ reviewStatusLabel(page.review_status) }} · {{ page.character_count }} 字</small>
            <ChevronRight :size="17" aria-hidden="true" />
          </RouterLink>
        </div>
        <p v-else class="empty-state">当前版本尚无 OCR 页。</p>

        <div v-if="ocrPageCount > ocrPageSize" class="page-controls">
          <button
            class="icon-text-button"
            type="button"
            :disabled="ocrPageNumber <= 1"
            @click="changeOcrPage(ocrPageNumber - 1)"
          >
            <ChevronLeft :size="16" aria-hidden="true" />
            上一页
          </button>
          <span>{{ ocrPageNumber }} / {{ ocrTotalPages }}</span>
          <button
            class="icon-text-button"
            type="button"
            :disabled="ocrPageNumber >= ocrTotalPages"
            @click="changeOcrPage(ocrPageNumber + 1)"
          >
            下一页
            <ChevronRight :size="16" aria-hidden="true" />
          </button>
        </div>
      </section>

      <section v-else-if="activeTab === 'versions' && versions.length" class="catalog-surface">
        <div class="catalog-toolbar">
          <div>
            <h2>影印版本</h2>
            <span>{{ versions.length }} 套</span>
          </div>
        </div>
        <div class="version-table">
          <div class="version-table-head" aria-hidden="true">
            <span>版本</span>
            <span>来源</span>
            <span>文件</span>
            <span>OCR</span>
            <span>状态</span>
          </div>
          <article v-for="version in versions" :key="version.id" class="version-row">
            <strong>{{ version.name }}</strong>
            <span>{{ version.provider || "待登记" }}</span>
            <span>{{ version.file_count ?? 0 }} {{ version.file_unit ?? "册" }}</span>
            <span>{{ version.ocr_page_count ?? 0 }} 页</span>
            <em>{{ availabilityLabel(version.availability) }}</em>
          </article>
        </div>
      </section>

      <section v-else-if="activeTab === 'toc' && toc?.volumes.length" class="catalog-surface">
        <div class="catalog-toolbar">
          <div>
            <h2>{{ hasTextPassages ? "文本目录" : "分册目录" }}</h2>
            <span>{{ toc.volumes.length }} 卷册</span>
          </div>
          <button
            v-if="toc.volumes.length > volumeLimit"
            class="icon-text-button"
            type="button"
            @click="showAllVolumes = !showAllVolumes"
          >
            {{ showAllVolumes ? "收起" : "展开全部" }}
          </button>
        </div>
        <div class="toc-list">
          <article v-for="volume in visibleVolumes" :key="volume.id" class="toc-volume">
            <div class="toc-volume-title">
              <span>卷 {{ volume.volume_no }}</span>
              <strong>{{ volume.title }}</strong>
              <small>{{ volume.chapter_type }}</small>
            </div>
            <div v-if="volume.passages.length" class="toc-passages">
              <RouterLink
                v-for="passage in visiblePassages(volume)"
                :key="passage.id"
                class="passage-link"
                :to="`/reader/${passage.id}`"
              >
                <span>{{ passage.sort_order }}</span>
                {{ passage.title }}
                <ChevronRight :size="16" aria-hidden="true" />
              </RouterLink>
              <button
                v-if="volume.passages.length > passageLimit"
                class="toc-more-button"
                type="button"
                @click="toggleVolumePassages(volume.id)"
              >
                {{ expandedVolumeIds.includes(volume.id) ? "收起本卷" : `展开其余 ${volume.passages.length - passageLimit} 段` }}
              </button>
            </div>
            <span v-else class="pending-label">待 OCR</span>
          </article>
        </div>
      </section>

      <section v-else class="catalog-surface empty-catalog">
        <Layers3 :size="26" aria-hidden="true" />
        <h2>影印待入库</h2>
        <p>{{ statusLabel(book.status) }}</p>
      </section>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { BookOpenText, ChevronLeft, ChevronRight, Layers3, ScanSearch } from "@lucide/vue";
import { useRoute } from "vue-router";

import {
  type Book,
  type BookToc,
  type OcrWorkspacePageSummary,
  type VersionInfo,
  getBooks,
  getBookToc,
  getBookVersions,
  getOcrWorkspacePageCount,
  getOcrWorkspacePages,
} from "../services/api";

type CatalogTab = "pages" | "versions" | "toc";

const route = useRoute();
const book = ref<Book | null>(null);
const toc = ref<BookToc | null>(null);
const versions = ref<VersionInfo[]>([]);
const ocrPages = ref<OcrWorkspacePageSummary[]>([]);
const ocrPageCount = ref(0);
const ocrPageNumber = ref(1);
const ocrPageSize = 50;
const ocrVersionFilter = ref("");
const activeTab = ref<CatalogTab>("pages");
const loading = ref(true);
const error = ref("");
const showAllVolumes = ref(false);
const volumeLimit = 24;
const passageLimit = 24;
const expandedVolumeIds = ref<string[]>([]);

const visibleVolumes = computed(() => {
  if (!toc.value || showAllVolumes.value) {
    return toc.value?.volumes ?? [];
  }
  return toc.value.volumes.slice(0, volumeLimit);
});

const hasTextPassages = computed(
  () => toc.value?.volumes.some((volume) => volume.passages.length > 0) ?? false,
);

const ocrTotalPages = computed(() =>
  Math.max(1, Math.ceil(ocrPageCount.value / ocrPageSize)),
);

const ocrVersions = computed(() =>
  versions.value.filter((version) => (version.ocr_page_count ?? 0) > 0),
);

const firstPassage = computed(() =>
  toc.value?.volumes.flatMap((volume) => volume.passages)[0] ?? null,
);

onMounted(async () => {
  const bookId = String(route.params.bookId);
  try {
    const [
      books,
      versionPayload,
      tocPayload,
      pagePayload,
      pageCountPayload,
    ] = await Promise.all([
      getBooks(),
      getBookVersions(bookId).catch(() => []),
      getBookToc(bookId).catch(() => null),
      getOcrWorkspacePages({ bookId, limit: ocrPageSize, offset: 0 }).catch(() => []),
      getOcrWorkspacePageCount({ bookId }).catch(() => ({ count: 0 })),
    ]);
    book.value = books.find((item) => item.id === bookId) ?? null;
    if (!book.value) {
      throw new Error("未找到这部史书。");
    }
    if ((book.value.version_count ?? 0) > 0) {
      versions.value = versionPayload;
    }
    if (book.value.available) {
      toc.value = tocPayload;
      ocrPages.value = pagePayload;
      ocrPageCount.value = pageCountPayload.count;
    }
    activeTab.value = firstPassage.value
      ? "toc"
      : ocrPageCount.value
        ? "pages"
        : versions.value.length
          ? "versions"
          : "toc";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
});

async function changeOcrPage(nextPage: number) {
  if (!book.value) {
    return;
  }
  ocrPageNumber.value = Math.min(Math.max(nextPage, 1), ocrTotalPages.value);
  ocrPages.value = await getOcrWorkspacePages({
    bookId: book.value.id,
    versionId: ocrVersionFilter.value || undefined,
    limit: ocrPageSize,
    offset: (ocrPageNumber.value - 1) * ocrPageSize,
  });
}

async function handleOcrVersionChange() {
  if (!book.value) {
    return;
  }
  ocrPageNumber.value = 1;
  const filters = {
    bookId: book.value.id,
    versionId: ocrVersionFilter.value || undefined,
  };
  const [pagePayload, countPayload] = await Promise.all([
    getOcrWorkspacePages({ ...filters, limit: ocrPageSize, offset: 0 }),
    getOcrWorkspacePageCount(filters),
  ]);
  ocrPages.value = pagePayload;
  ocrPageCount.value = countPayload.count;
}

function visiblePassages(volume: BookToc["volumes"][number]) {
  return expandedVolumeIds.value.includes(volume.id)
    ? volume.passages
    : volume.passages.slice(0, passageLimit);
}

function toggleVolumePassages(volumeId: string) {
  expandedVolumeIds.value = expandedVolumeIds.value.includes(volumeId)
    ? expandedVolumeIds.value.filter((id) => id !== volumeId)
    : [...expandedVolumeIds.value, volumeId];
}

function statusLabel(status: string) {
  return {
    ocr_in_progress: "OCR 整理中",
    scans_ready: "书影已入库",
    scans_partial: "书影获取中",
    sources_selected: "版本已定",
    planned: "资料待接入",
  }[status] ?? status;
}

function availabilityLabel(status?: string) {
  return {
    ready: "已校验",
    partial: "校验中",
    planned: "待下载",
  }[status ?? ""] ?? "待核验";
}

function reviewStatusLabel(status: string) {
  return {
    unreviewed: "待校对",
    reviewing: "校对中",
    approved: "已通过",
    rejected: "退回",
  }[status] ?? status;
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-CN").format(value);
}
</script>

<style scoped>
.book-catalog {
  max-width: 1280px;
}

.catalog-header {
  border-bottom: 1px solid var(--line);
  padding: 4px 0 22px;
}

.breadcrumb-link {
  align-items: center;
  color: var(--muted);
  display: inline-flex;
  font-size: 13px;
  gap: 4px;
  margin-bottom: 16px;
}

.catalog-title-row {
  align-items: flex-end;
  display: flex;
  gap: 20px;
  justify-content: space-between;
}

.catalog-title-row h1,
.catalog-title-row p {
  margin: 0;
}

.catalog-primary-actions {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
  justify-content: flex-end;
}

.secondary-action {
  align-items: center;
  border: 1px solid var(--line);
  border-radius: 4px;
  color: var(--ink-secondary);
  display: inline-flex;
  font-size: 13px;
  gap: 7px;
  min-height: 38px;
  padding: 0 12px;
}

.secondary-action:hover {
  border-color: var(--jade);
  color: var(--jade-dark);
}

.shiji-import-summary {
  background: var(--surface);
  border: 1px solid var(--line);
  border-left: 3px solid var(--cinnabar);
  border-radius: 5px;
  display: grid;
  gap: 12px 28px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  padding: 16px 18px;
}

.shiji-import-summary > div {
  display: grid;
  gap: 3px;
}

.shiji-import-summary span,
.shiji-import-summary small,
.shiji-import-summary p {
  color: var(--muted);
  font-size: 12px;
}

.shiji-import-summary strong {
  color: var(--ink);
  font-family: var(--font-serif);
  font-size: 22px;
}

.shiji-import-summary p {
  border-top: 1px solid var(--line-soft);
  grid-column: 1 / -1;
  line-height: 1.7;
  margin: 0;
  padding-top: 11px;
}

.catalog-title-row h1 {
  font-family: var(--font-serif);
  font-size: 34px;
  line-height: 1.25;
}

.catalog-title-row p {
  color: var(--muted);
  font-size: 14px;
  margin-top: 6px;
}

.catalog-tabs {
  border-bottom: 1px solid var(--line);
  display: flex;
  gap: 24px;
}

.catalog-tabs button {
  background: transparent;
  border: 0;
  border-bottom: 2px solid transparent;
  color: var(--muted);
  cursor: pointer;
  font-weight: 600;
  margin-bottom: -1px;
  min-height: 46px;
  padding: 0 2px;
}

.catalog-tabs button span {
  color: var(--muted-light);
  font-size: 12px;
  margin-left: 5px;
}

.catalog-tabs button.active {
  border-bottom-color: var(--jade);
  color: var(--ink);
}

.catalog-tabs button:disabled {
  cursor: default;
  opacity: 0.42;
}

.catalog-surface {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 6px;
  min-width: 0;
}

.catalog-toolbar {
  align-items: center;
  border-bottom: 1px solid var(--line);
  display: flex;
  gap: 18px;
  justify-content: space-between;
  min-height: 64px;
  padding: 12px 18px;
}

.catalog-toolbar h2,
.catalog-toolbar span {
  margin: 0;
}

.catalog-toolbar h2 {
  font-size: 17px;
}

.catalog-toolbar > div > span {
  color: var(--muted);
  font-size: 12px;
}

.compact-select {
  align-items: center;
  display: flex;
  font-size: 12px;
  gap: 8px;
}

.compact-select select {
  min-width: 210px;
}

.scan-page-list {
  display: grid;
}

.scan-page-link {
  align-items: center;
  border-bottom: 1px solid var(--line-soft);
  display: grid;
  gap: 14px;
  grid-template-columns: minmax(180px, 1.2fr) 120px minmax(170px, 1fr) 130px 18px;
  min-height: 58px;
  padding: 10px 18px;
}

.scan-page-link:last-child {
  border-bottom: 0;
}

.scan-page-link:hover {
  background: var(--jade-wash);
}

.scan-page-link strong {
  font-size: 13px;
}

.scan-page-link small,
.scan-page-link > span {
  color: var(--muted);
  font-size: 12px;
}

.version-table {
  display: grid;
}

.version-table-head,
.version-row {
  align-items: center;
  display: grid;
  gap: 16px;
  grid-template-columns: minmax(240px, 1.4fr) minmax(180px, 1fr) 100px 100px 90px;
  padding: 0 18px;
}

.version-table-head {
  background: var(--surface-muted);
  color: var(--muted);
  font-size: 12px;
  min-height: 38px;
}

.version-row {
  border-top: 1px solid var(--line-soft);
  min-height: 60px;
}

.version-row span {
  color: var(--muted);
  font-size: 13px;
}

.version-row em {
  color: var(--jade);
  font-size: 12px;
  font-style: normal;
}

.toc-list {
  display: grid;
}

.toc-volume {
  align-items: start;
  border-bottom: 1px solid var(--line-soft);
  display: grid;
  gap: 20px;
  grid-template-columns: minmax(220px, 0.42fr) minmax(0, 1fr) auto;
  padding: 16px 18px;
}

.toc-volume:last-child {
  border-bottom: 0;
}

.toc-volume-title {
  display: grid;
  gap: 3px;
}

.toc-volume-title > span,
.toc-volume-title small {
  color: var(--muted);
  font-size: 12px;
}

.toc-volume-title strong {
  font-family: var(--font-serif);
  font-size: 17px;
}

.toc-passages {
  display: grid;
  gap: 6px;
}

.passage-link {
  align-items: center;
  border: 0;
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) 16px;
  padding: 7px 8px;
}

.passage-link:hover {
  background: var(--jade-wash);
}

.toc-more-button {
  background: var(--surface-muted);
  border: 1px solid var(--line);
  border-radius: 4px;
  color: var(--jade-dark);
  cursor: pointer;
  font-size: 12px;
  justify-self: start;
  margin: 4px 8px;
  padding: 7px 10px;
}

.pending-label {
  color: var(--muted);
  font-size: 12px;
  padding-top: 4px;
}

.page-controls {
  border-top: 1px solid var(--line);
  margin: 0;
  padding: 12px 18px;
}

.empty-catalog {
  align-items: center;
  color: var(--muted);
  display: grid;
  justify-items: center;
  min-height: 240px;
  padding: 32px;
  text-align: center;
}

.empty-catalog h2,
.empty-catalog p {
  margin: 6px 0 0;
}

@media (max-width: 760px) {
  .catalog-title-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .catalog-title-row .primary-action {
    width: 100%;
  }

  .catalog-primary-actions,
  .catalog-primary-actions .secondary-action {
    justify-content: center;
    width: 100%;
  }

  .shiji-import-summary {
    grid-template-columns: 1fr;
  }

  .shiji-import-summary p {
    grid-column: 1;
  }

  .catalog-tabs {
    gap: 16px;
    overflow-x: auto;
  }

  .catalog-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .compact-select,
  .compact-select select {
    width: 100%;
  }

  .scan-page-link,
  .version-row,
  .toc-volume {
    grid-template-columns: 1fr;
  }

  .scan-page-link {
    gap: 5px;
    padding: 13px 16px;
  }

  .scan-page-link svg,
  .version-table-head {
    display: none;
  }

  .version-row {
    gap: 5px;
    padding: 14px 16px;
  }

  .toc-volume {
    gap: 10px;
  }
}
</style>
