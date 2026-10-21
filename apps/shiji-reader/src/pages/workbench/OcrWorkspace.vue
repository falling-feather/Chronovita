<template>
  <main class="workbench-layout ocr-workbench">
    <header class="ocr-page-header">
      <div>
        <p class="eyebrow">OCR 校对</p>
        <h1>影印校对台</h1>
      </div>
      <div class="ocr-header-actions">
        <dl v-if="summary" class="ocr-primary-metrics">
          <div>
            <dt>已识别</dt>
            <dd>{{ summary.completed_pages }}</dd>
          </div>
          <div>
            <dt>待校对</dt>
            <dd>{{ summary.unreviewed_pages }}</dd>
          </div>
          <div>
            <dt>未映射</dt>
            <dd>{{ summary.unmapped_mapping_pages }}</dd>
          </div>
          <div>
            <dt>异文候选</dt>
            <dd>{{ summary.variant_candidates }}</dd>
          </div>
        </dl>
        <button
          class="icon-button"
          type="button"
          :disabled="refreshing"
          :title="refreshing ? '刷新中' : '刷新进度'"
          :aria-label="refreshing ? '刷新中' : '刷新进度'"
          @click="refreshProgress"
        >
          <RefreshCw :size="17" :class="{ spinning: refreshing }" aria-hidden="true" />
        </button>
      </div>
    </header>

    <section class="ocr-filter-bar" aria-label="OCR 页筛选">
      <label>
        <span>史书</span>
        <select v-model="bookFilter" @change="handleBookFilterChange">
          <option value="">全部</option>
          <option v-for="book in books" :key="book.id" :value="book.id">
            {{ book.title }}（{{ formatNumber(book.page_count) }}）
          </option>
        </select>
      </label>
      <label>
        <span>版本</span>
        <select v-model="versionFilter" :disabled="!bookFilter" @change="resetAndLoadPages">
          <option value="">全部</option>
          <option v-for="version in versions" :key="version.id" :value="version.id">
            {{ version.name }}（{{ formatNumber(version.page_count) }}）
          </option>
        </select>
      </label>
      <label>
        <span>校对状态</span>
        <select v-model="statusFilter" @change="resetAndLoadPages">
          <option value="">全部</option>
          <option value="unreviewed">待校对</option>
          <option value="reviewing">校对中</option>
          <option value="approved">已通过</option>
          <option value="rejected">退回</option>
        </select>
      </label>
      <label>
        <span>质量</span>
        <select v-model="qualityFilter" @change="resetAndLoadPages">
          <option value="">全部</option>
          <option value="blank_candidate">空白候选</option>
          <option value="low_confidence">低置信</option>
          <option value="typical">常规页</option>
        </select>
      </label>
      <label>
        <span>映射</span>
        <select v-model="mappingFilter" @change="resetAndLoadPages">
          <option value="">全部</option>
          <option value="unmapped">未映射</option>
          <option value="draft">机器草稿</option>
          <option value="reviewing">复核中</option>
          <option value="approved">已通过</option>
        </select>
      </label>
    </section>
    <p class="ocr-filter-summary">{{ filterDescription }}</p>

    <details v-if="runningBatches.length" class="batch-monitor">
      <summary>运行中批次 {{ runningBatches.length }}</summary>
      <div class="batch-progress-list">
        <article v-for="batch in runningBatches" :key="batch.id">
          <div>
            <strong>{{ batch.id }}</strong>
            <span>{{ batch.completed_pages }} / {{ batch.total_pages }} 页</span>
          </div>
          <progress :value="batch.completed_pages" :max="batch.total_pages" />
        </article>
      </div>
    </details>

    <section class="workspace-grid ocr-workspace-grid">
      <aside class="panel ocr-page-browser">
        <div class="section-heading">
          <h2>页记录</h2>
          <span class="counter">{{ formatNumber(totalRecords) }}</span>
        </div>

        <details class="review-sample" v-if="reviewSample">
          <summary>固定人工抽检 · {{ reviewSample.summary.pages }} 页</summary>
          <div class="benchmark-strip" v-if="benchmark">
            <span>有校定参考 {{ benchmark.summary.evaluated_pages }}</span>
            <span>正式金标准 {{ benchmark.summary.approved_pages }}</span>
            <span>空文本 {{ benchmark.summary.zero_reference_pages }}</span>
            <span>暂定 CER {{ formatCer(benchmark.summary.provisional_cer) }}</span>
            <span>正式 CER {{ formatCer(benchmark.summary.approved_cer) }}</span>
          </div>
          <div class="review-sample-list">
            <button
              v-for="samplePage in reviewSample.pages"
              :key="samplePage.page_id"
              class="sample-page-button"
              :class="{ active: selectedPageId === samplePage.page_id }"
              type="button"
              @click="selectPage(samplePage.page_id)"
            >
              <span>{{ samplePage.priority }} · {{ qualityLabel(samplePage.sample_category) }}</span>
              <strong>{{ samplePage.source_file_label }} · 第 {{ samplePage.source_page }} 页</strong>
            </button>
          </div>
        </details>

        <p v-if="loading">正在加载页记录...</p>
        <p v-else-if="error" class="error-text">{{ error }}</p>
        <div v-else class="record-list ocr-page-list">
          <button
            v-for="page in pages"
            :key="page.id"
            class="record-button"
            :class="{ active: selectedPageId === page.id }"
            type="button"
            @click="selectPage(page.id)"
          >
            <span>PDF {{ page.pdf_page }} · {{ statusLabel(page.review_status) }}</span>
            <strong>{{ page.book_title }} · {{ page.source_file_label }}</strong>
            <small>{{ page.version_label }}</small>
            <small>
              {{ qualityLabel(page.quality_band) }} ·
              {{ Math.round(page.average_confidence * 100) }}% ·
              {{ mappingStatusLabel(page.mapping_status) }}
            </small>
          </button>
        </div>
        <div class="page-controls" v-if="totalRecords > pageSize">
          <button
            class="secondary-action button-reset"
            type="button"
            :disabled="pageNumber <= 1 || loading"
            @click="changePage(pageNumber - 1)"
          >
            上一页
          </button>
          <span>第 {{ pageNumber }} / {{ totalPages }} 页</span>
          <button
            class="secondary-action button-reset"
            type="button"
            :disabled="pageNumber >= totalPages || loading"
            @click="changePage(pageNumber + 1)"
          >
            下一页
          </button>
        </div>
      </aside>

      <section class="panel inspector-panel" v-if="activePage">
        <div class="section-heading">
          <div>
            <p class="eyebrow">
              {{ activePage.book.title }} / {{ activePage.version.label }}
            </p>
            <h2>{{ activePage.source.file_label }} · PDF 第 {{ activePage.source.pdf_page }} 页</h2>
          </div>
          <span class="status-badge">{{ statusLabel(activePage.transcription.status) }}</span>
        </div>

        <div class="editor-toolbar">
          <label class="toggle-field">
            <input v-model="showBoxes" type="checkbox" />
            <span>识别框</span>
          </label>
          <RouterLink class="text-link" :to="`/reader/scan/${activePage.id}`">
            <ExternalLink :size="15" aria-hidden="true" />
            影印阅读器
          </RouterLink>
        </div>

        <div class="ocr-editor-grid">
          <div class="ocr-image-frame">
            <img
              :src="getOcrWorkspacePageImageUrl(activePage.id)"
              :alt="activePage.reader.display_label"
              @load="handlePreviewLoad"
            />
            <template v-if="showBoxes">
              <div
                v-for="block in activePage.ocr.blocks"
                :key="block.id"
                class="ocr-image-box"
                :class="{ uncertain: block.confidence < 0.6 }"
                :style="overlayStyle(block)"
                :title="`${block.order}. ${block.text}`"
              >
                <span>{{ block.order }}</span>
              </div>
            </template>
          </div>

          <div class="editor-fields">
            <label class="textarea-field">
              <span>校定文本</span>
              <textarea ref="correctedTextArea" v-model="correctedText" rows="18"></textarea>
            </label>

            <div class="form-grid">
              <label>
                <span>审核状态</span>
                <select v-model="reviewStatus">
                  <option value="unreviewed">待校对</option>
                  <option value="reviewing">校对中</option>
                  <option value="approved">已通过</option>
                  <option value="rejected">退回</option>
                </select>
              </label>
              <label>
                <span>模型置信度</span>
                <input
                  :value="`${Math.round(activePage.ocr.metrics.average_confidence * 100)}%`"
                  disabled
                />
              </label>
            </div>

            <div class="issue-picker" v-if="environment">
              <label v-for="issue in environment.issue_types" :key="issue.id">
                <input v-model="selectedIssues" type="checkbox" :value="issue.id" />
                <span>{{ issue.name }}</span>
              </label>
            </div>

            <section class="manual-content-editor" aria-label="人工阅读补丁">
              <div>
                <strong>人工阅读补丁</strong>
                <small>人工内容优先保留，不覆盖 raw OCR。</small>
              </div>
              <label class="textarea-field">
                <span>本页 / 段落梗概</span>
                <textarea
                  v-model="manualSummary"
                  rows="3"
                  maxlength="2000"
                  placeholder="概括本页核心内容，供阅读器上下文使用。"
                ></textarea>
              </label>
              <div class="manual-keyword-composer">
                <label>
                  <span>关键词文字</span>
                  <input
                    v-model.trim="manualKeywordDraft"
                    placeholder="也可先在校定文本中选中文字"
                    @keydown.enter.prevent="addManualKeyword"
                  />
                </label>
                <label>
                  <span>类型</span>
                  <select v-model="manualKeywordType">
                    <option value="person">人物</option>
                    <option value="place">地名</option>
                    <option value="office">官职</option>
                    <option value="time">时间</option>
                    <option value="book">书名</option>
                    <option value="event">事件</option>
                    <option value="concept">概念</option>
                    <option value="keyword">关键词</option>
                  </select>
                </label>
                <button
                  class="secondary-action button-reset"
                  type="button"
                  @click="addManualKeyword"
                >
                  添加关键词
                </button>
              </div>
              <div class="manual-keyword-list" v-if="manualKeywords.length">
                <div v-for="keyword in manualKeywords" :key="keyword.id">
                  <span>{{ keywordTypeLabel(keyword.type) }}</span>
                  <strong>{{ keyword.text }}</strong>
                  <small>{{ keyword.start }}–{{ keyword.end }}</small>
                  <button
                    class="button-reset"
                    type="button"
                    @click="removeManualKeyword(keyword.id)"
                  >
                    移除
                  </button>
                </div>
              </div>
              <p v-if="manualContentMessage" class="field-message">
                {{ manualContentMessage }}
              </p>
            </section>

            <label class="textarea-field">
              <span>校勘备注</span>
              <textarea v-model="reviewNote" rows="3"></textarea>
            </label>

            <button
              class="primary-action button-reset"
              type="button"
              :disabled="saving"
              @click="saveReview"
            >
              <Save :size="16" aria-hidden="true" />
              {{ saving ? "正在保存..." : "保存校定" }}
            </button>
            <p v-if="saveMessage" class="save-message">{{ saveMessage }}</p>
          </div>
        </div>

        <details>
          <summary>来源与修订记录</summary>
          <div class="provenance-grid">
            <span>来源记录</span><code>{{ activePage.source.record_id }}</code>
            <span>校验</span>
            <code>{{ activePage.source.checksum_algorithm }} {{ activePage.source.checksum }}</code>
            <span>模型</span><code>{{ activePage.ocr.model_profile }}</code>
            <span>修订</span><code>{{ activePage.revisions.length }}</code>
          </div>
        </details>

        <details class="mapping-editor">
          <summary>卷页映射 · {{ mappingStatusLabel(mappingStatus) }}</summary>
          <div class="mapping-form">
            <div class="form-grid mapping-grid">
              <label class="wide-field">
                <span>规范单元 ID</span>
                <input v-model.trim="canonicalUnitId" />
              </label>
              <label>
                <span>卷次</span>
                <input v-model.number="mappingVolumeNo" type="number" min="1" />
              </label>
              <label>
                <span>映射状态</span>
                <select v-model="mappingStatus">
                  <option value="unmapped">未映射</option>
                  <option value="draft">草稿</option>
                  <option value="reviewing">复核中</option>
                  <option value="approved">已通过</option>
                </select>
              </label>
              <label>
                <span>卷名</span>
                <input v-model.trim="mappingVolumeTitle" />
              </label>
              <label>
                <span>篇章</span>
                <input v-model.trim="mappingChapterTitle" />
              </label>
              <label>
                <span>原书叶码</span>
                <input v-model.trim="sourceLeafLabel" />
              </label>
              <label>
                <span>叶面</span>
                <select v-model="leafSide">
                  <option value="">未标</option>
                  <option value="recto">正面</option>
                  <option value="verso">背面</option>
                  <option value="unknown">不详</option>
                </select>
              </label>
            </div>
            <label class="textarea-field">
              <span>映射备注</span>
              <textarea v-model="mappingNote" rows="3"></textarea>
            </label>
            <div class="mapping-actions">
              <button
                class="primary-action button-reset"
                type="button"
                :disabled="mappingSaving"
                @click="saveMapping"
              >
                <Save :size="16" aria-hidden="true" />
                {{ mappingSaving ? "正在保存..." : "保存卷页映射" }}
              </button>
              <span v-if="activePage.mapping.revisions.length">
                {{ activePage.mapping.revisions.length }} 次映射修订
              </span>
              <span v-if="mappingMessage" class="save-message">{{ mappingMessage }}</span>
            </div>
          </div>

          <div class="parallel-pages" v-if="parallelPages.length">
            <p class="eyebrow">同一规范单元的其他版本</p>
            <div
              v-for="parallel in parallelPages"
              :key="parallel.id"
              class="parallel-page-row"
            >
              <RouterLink :to="`/reader/scan/${parallel.id}`">
                <strong>{{ parallel.version_label }}</strong>
                <span>
                  {{ parallel.source_file_label }} · PDF 第 {{ parallel.pdf_page }} 页 ·
                  映射{{ mappingStatusLabel(parallel.mapping_status) }}
                </span>
              </RouterLink>
              <button
                class="secondary-action button-reset"
                type="button"
                :disabled="variantGeneratingId === parallel.id"
                @click="generateVariants(parallel)"
              >
                {{ variantGeneratingId === parallel.id ? "生成中..." : "生成异文" }}
              </button>
            </div>
            <div class="mapping-actions" v-if="variantMessage">
              <span class="save-message">{{ variantMessage }}</span>
              <RouterLink class="text-link" to="/workbench/variants">查看异文审核</RouterLink>
            </div>
          </div>
        </details>
      </section>

      <section class="panel inspector-panel empty-editor" v-else>
        <p>{{ loading ? "正在加载..." : "当前筛选条件下没有 OCR 页。" }}</p>
      </section>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ExternalLink, RefreshCw, Save } from "@lucide/vue";
import { useRoute } from "vue-router";

import {
  type OcrBatch,
  type OcrBenchmark,
  type OcrBlock,
  type OcrEnvironment,
  type OcrManualKeyword,
  type OcrPageFilterBook,
  type OcrPageFilterVersion,
  type OcrParallelPage,
  type OcrReviewSample,
  type OcrWorkspacePage,
  type OcrWorkspacePageSummary,
  type OcrWorkspaceSummary,
  generateWorkbenchVariants,
  getOcrBatches,
  getOcrEnvironment,
  getOcrReviewSample,
  getOcrReviewSampleMetrics,
  getOcrWorkspacePage,
  getOcrWorkspacePageCount,
  getOcrWorkspacePageFilterOptions,
  getOcrWorkspacePageImageUrl,
  getOcrWorkspacePageParallels,
  getOcrWorkspacePages,
  getOcrWorkspaceSummary,
  saveOcrWorkspacePageMapping,
  saveOcrWorkspacePage,
} from "../../services/api";

const environment = ref<OcrEnvironment | null>(null);
const batches = ref<OcrBatch[]>([]);
const reviewSample = ref<OcrReviewSample | null>(null);
const benchmark = ref<OcrBenchmark | null>(null);
const route = useRoute();
const summary = ref<OcrWorkspaceSummary | null>(null);
const pages = ref<OcrWorkspacePageSummary[]>([]);
const books = ref<OcrPageFilterBook[]>([]);
const versions = ref<OcrPageFilterVersion[]>([]);
const activePage = ref<OcrWorkspacePage | null>(null);
const selectedPageId = ref("");
const bookFilter = ref("");
const versionFilter = ref("");
const statusFilter = ref("unreviewed");
const qualityFilter = ref("");
const mappingFilter = ref("");
const pageNumber = ref(1);
const pageSize = 50;
const totalRecords = ref(0);
const correctedText = ref("");
const correctedTextArea = ref<HTMLTextAreaElement | null>(null);
const reviewStatus = ref("unreviewed");
const reviewNote = ref("");
const selectedIssues = ref<string[]>([]);
const manualSummary = ref("");
const manualKeywords = ref<OcrManualKeyword[]>([]);
const manualKeywordDraft = ref("");
const manualKeywordType = ref<OcrManualKeyword["type"]>("person");
const manualContentMessage = ref("");
const parallelPages = ref<OcrParallelPage[]>([]);
const canonicalUnitId = ref("");
const mappingVolumeNo = ref<number | null>(null);
const mappingVolumeTitle = ref("");
const mappingChapterTitle = ref("");
const sourceLeafLabel = ref("");
const leafSide = ref("");
const mappingStatus = ref("unmapped");
const mappingNote = ref("");
const showBoxes = ref(false);
const previewSize = ref({ width: 1, height: 1 });
const loading = ref(true);
const refreshing = ref(false);
const saving = ref(false);
const mappingSaving = ref(false);
const error = ref("");
const saveMessage = ref("");
const mappingMessage = ref("");
const variantGeneratingId = ref("");
const variantMessage = ref("");

const totalPages = computed(() =>
  Math.max(1, Math.ceil(totalRecords.value / pageSize)),
);

const runningBatches = computed(() =>
  batches.value.filter((batch) => batch.status === "running"),
);

const filterDescription = computed(() => {
  const book = books.value.find((item) => item.id === bookFilter.value);
  const version = versions.value.find((item) => item.id === versionFilter.value);
  const scope = [
    book?.title ?? "全部史书",
    version?.name ?? "全部版本",
    statusFilter.value ? statusLabel(statusFilter.value) : "全部校对状态",
    qualityFilter.value ? qualityLabel(qualityFilter.value) : "全部质量",
    mappingFilter.value ? mappingStatusLabel(mappingFilter.value) : "全部映射状态",
  ].join(" · ");
  return `当前范围：${scope}；数据库命中 ${formatNumber(totalRecords.value)} 页，当前仅加载 ${pages.value.length} 条。`;
});

onMounted(async () => {
  const requestedPageId = String(route.query.page ?? "");
  try {
    const primaryPayload = Promise.all([
      getOcrEnvironment(),
      getOcrWorkspacePageFilterOptions(),
    ]);
    const pageIndex = loadPageIndex(!requestedPageId);
    const [[environmentPayload, filterPayload]] = await Promise.all([
      primaryPayload,
      pageIndex,
    ]);
    environment.value = environmentPayload;
    books.value = filterPayload.books;
    if (requestedPageId) {
      await selectPage(requestedPageId);
    }
    void loadSupplementaryData();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
});

async function loadSupplementaryData() {
  const [summaryResult, sampleResult, benchmarkResult, batchResult] =
    await Promise.allSettled([
      getOcrWorkspaceSummary(),
      getOcrReviewSample(),
      getOcrReviewSampleMetrics(),
      getOcrBatches(),
    ]);
  if (summaryResult.status === "fulfilled") {
    summary.value = summaryResult.value;
  }
  if (sampleResult.status === "fulfilled") {
    reviewSample.value = sampleResult.value;
  }
  if (benchmarkResult.status === "fulfilled") {
    benchmark.value = benchmarkResult.value;
  }
  if (batchResult.status === "fulfilled") {
    batches.value = batchResult.value;
  }
}

async function refreshProgress() {
  refreshing.value = true;
  try {
    const [summaryPayload, batchPayload, benchmarkPayload] = await Promise.all([
      getOcrWorkspaceSummary(),
      getOcrBatches(),
      getOcrReviewSampleMetrics().catch(() => null),
    ]);
    summary.value = summaryPayload;
    batches.value = batchPayload;
    benchmark.value = benchmarkPayload;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "进度刷新失败";
  } finally {
    refreshing.value = false;
  }
}

async function loadPageIndex(selectFirst = true) {
  loading.value = true;
  error.value = "";
  try {
    const filters = {
      bookId: bookFilter.value || undefined,
      versionId: versionFilter.value || undefined,
      reviewStatus: statusFilter.value || undefined,
      mappingStatus: mappingFilter.value || undefined,
      qualityBand: qualityFilter.value || undefined,
    };
    const [pagePayload, countPayload] = await Promise.all([
      getOcrWorkspacePages({
        ...filters,
        limit: pageSize,
        offset: (pageNumber.value - 1) * pageSize,
      }),
      getOcrWorkspacePageCount(filters),
    ]);
    pages.value = pagePayload;
    totalRecords.value = countPayload.count;
    if (pageNumber.value > totalPages.value) {
      pageNumber.value = totalPages.value;
      await loadPageIndex(selectFirst);
      return;
    }
    if (pagePayload[0] && selectFirst) {
      const preferred = pagePayload.find((page) => page.id === selectedPageId.value);
      await selectPage(preferred?.id ?? pagePayload[0].id);
    } else if (!pagePayload[0]) {
      selectedPageId.value = "";
      activePage.value = null;
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "页记录加载失败";
  } finally {
    loading.value = false;
  }
}

async function handleBookFilterChange() {
  versionFilter.value = "";
  versions.value =
    books.value.find((book) => book.id === bookFilter.value)?.versions ?? [];
  await resetAndLoadPages();
}

async function resetAndLoadPages() {
  pageNumber.value = 1;
  await loadPageIndex();
}

async function changePage(nextPage: number) {
  pageNumber.value = Math.min(Math.max(nextPage, 1), totalPages.value);
  await loadPageIndex();
}

async function selectPage(pageId: string) {
  selectedPageId.value = pageId;
  saveMessage.value = "";
  manualContentMessage.value = "";
  mappingMessage.value = "";
  variantMessage.value = "";
  try {
    const [page, parallels] = await Promise.all([
      getOcrWorkspacePage(pageId),
      getOcrWorkspacePageParallels(pageId),
    ]);
    activePage.value = page;
    parallelPages.value = parallels;
    correctedText.value = page.transcription.corrected_text || page.transcription.raw_text;
    reviewStatus.value = page.transcription.status;
    reviewNote.value = page.transcription.note || "";
    selectedIssues.value = [...(page.transcription.issue_types || [])];
    manualSummary.value = page.manual_content?.summary || "";
    manualKeywords.value = [...(page.manual_content?.keywords || [])];
    canonicalUnitId.value = page.mapping.canonical_unit_id;
    mappingVolumeNo.value = page.mapping.volume_no;
    mappingVolumeTitle.value = page.mapping.volume_title;
    mappingChapterTitle.value = page.mapping.chapter_title;
    sourceLeafLabel.value = page.mapping.source_leaf_label;
    leafSide.value = page.mapping.leaf_side;
    mappingStatus.value = page.mapping.status;
    mappingNote.value = page.mapping.note;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "页记录加载失败";
  }
}

async function generateVariants(parallel: OcrParallelPage) {
  if (!activePage.value || variantGeneratingId.value) {
    return;
  }
  variantGeneratingId.value = parallel.id;
  variantMessage.value = "";
  try {
    const result = await generateWorkbenchVariants(activePage.value.id, parallel.id);
    variantMessage.value = result.truncated
      ? `检测到 ${result.differences} 处差异，已生成前 ${result.generated_candidates} 条候选。`
      : `已生成 ${result.generated_candidates} 条异文候选。`;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "异文生成失败";
  } finally {
    variantGeneratingId.value = "";
  }
}

async function saveMapping() {
  if (!activePage.value || mappingSaving.value) {
    return;
  }
  mappingSaving.value = true;
  mappingMessage.value = "";
  try {
    const mapping = await saveOcrWorkspacePageMapping(activePage.value.id, {
      canonical_unit_id: canonicalUnitId.value,
      volume_no: mappingVolumeNo.value || null,
      volume_title: mappingVolumeTitle.value,
      chapter_title: mappingChapterTitle.value,
      source_leaf_label: sourceLeafLabel.value,
      leaf_side: leafSide.value,
      status: mappingStatus.value,
      note: mappingNote.value,
      editor: "workbench",
    });
    activePage.value = { ...activePage.value, mapping };
    [parallelPages.value, summary.value] = await Promise.all([
      getOcrWorkspacePageParallels(activePage.value.id),
      getOcrWorkspaceSummary(),
    ]);
    mappingMessage.value = "映射已保存并写入修订记录。";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "映射保存失败";
  } finally {
    mappingSaving.value = false;
  }
}

function addManualKeyword() {
  manualContentMessage.value = "";
  const textarea = correctedTextArea.value;
  const selectionStart = textarea?.selectionStart ?? 0;
  const selectionEnd = textarea?.selectionEnd ?? selectionStart;
  const rawSelectedText =
    selectionEnd > selectionStart
      ? correctedText.value.slice(selectionStart, selectionEnd)
      : "";
  const selectedText = rawSelectedText.trim();
  const text = (selectedText || manualKeywordDraft.value).trim();
  if (!text) {
    manualContentMessage.value = "请先选择校定文本，或输入关键词文字。";
    return;
  }

  const selectedLeadingSpace = rawSelectedText.length - rawSelectedText.trimStart().length;
  let start = selectedText
    ? selectionStart + selectedLeadingSpace
    : correctedText.value.indexOf(text);
  if (start < 0) {
    manualContentMessage.value = "关键词必须存在于当前校定文本中。";
    return;
  }
  if (
    manualKeywords.value.some(
      (keyword) => keyword.start === start && keyword.text === text,
    )
  ) {
    manualContentMessage.value = "该位置已经添加了相同关键词。";
    return;
  }
  manualKeywords.value.push({
    id: `manual-keyword-${Date.now()}-${manualKeywords.value.length + 1}`,
    text,
    type: manualKeywordType.value,
    start,
    end: start + text.length,
    note: "",
    status: "human_confirmed",
  });
  manualKeywordDraft.value = "";
  manualContentMessage.value = `已添加“${text}”，保存校定后生效。`;
}

function removeManualKeyword(keywordId: string) {
  manualKeywords.value = manualKeywords.value.filter(
    (keyword) => keyword.id !== keywordId,
  );
  manualContentMessage.value = "已从待保存列表移除。";
}

function rebaseManualKeywords(): OcrManualKeyword[] {
  return manualKeywords.value.map((keyword) => {
    if (correctedText.value.slice(keyword.start, keyword.end) === keyword.text) {
      return keyword;
    }
    const candidates: number[] = [];
    let cursor = correctedText.value.indexOf(keyword.text);
    while (cursor >= 0) {
      candidates.push(cursor);
      cursor = correctedText.value.indexOf(keyword.text, cursor + 1);
    }
    if (!candidates.length) {
      throw new Error(`人工关键词“${keyword.text}”已不在校定文本中，请移除或重新添加。`);
    }
    const start = candidates.reduce((closest, candidate) =>
      Math.abs(candidate - keyword.start) < Math.abs(closest - keyword.start)
        ? candidate
        : closest,
    );
    return { ...keyword, start, end: start + keyword.text.length };
  });
}

async function saveReview() {
  if (!activePage.value || saving.value) {
    return;
  }
  saving.value = true;
  saveMessage.value = "";
  try {
    const rebasedKeywords = rebaseManualKeywords();
    manualKeywords.value = rebasedKeywords;
    const saved = await saveOcrWorkspacePage(activePage.value.id, {
      corrected_text: correctedText.value,
      status: reviewStatus.value,
      note: reviewNote.value,
      issue_types: selectedIssues.value,
      editor: "workbench",
      manual_content: {
        summary: manualSummary.value,
        keywords: rebasedKeywords,
        editor: "workbench",
      },
    });
    activePage.value = saved;
    await loadPageIndex();
    saveMessage.value = "校定、关键词与梗概已保存，并写入人工修订记录。";
    void loadSupplementaryData();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "保存失败";
  } finally {
    saving.value = false;
  }
}

function handlePreviewLoad(event: Event) {
  const image = event.target as HTMLImageElement;
  previewSize.value = {
    width: image.naturalWidth || 1,
    height: image.naturalHeight || 1,
  };
}

function overlayStyle(block: OcrBlock) {
  const [x1, y1, x2, y2] = block.bbox;
  return {
    left: `${(x1 / previewSize.value.width) * 100}%`,
    top: `${(y1 / previewSize.value.height) * 100}%`,
    width: `${((x2 - x1) / previewSize.value.width) * 100}%`,
    height: `${((y2 - y1) / previewSize.value.height) * 100}%`,
  };
}

function statusLabel(status: string) {
  return {
    unreviewed: "待校对",
    reviewing: "校对中",
    approved: "已通过",
    rejected: "退回",
  }[status] ?? status;
}

function qualityLabel(quality: string) {
  return {
    blank_candidate: "空白候选",
    low_confidence: "低置信",
    typical: "常规页",
  }[quality] ?? quality;
}

function mappingStatusLabel(status: string) {
  return {
    unmapped: "未映射",
    draft: "草稿",
    reviewing: "复核中",
    approved: "已通过",
  }[status] ?? status;
}

function keywordTypeLabel(type: OcrManualKeyword["type"]) {
  return {
    person: "人物",
    place: "地名",
    office: "官职",
    time: "时间",
    book: "书名",
    event: "事件",
    concept: "概念",
    keyword: "关键词",
  }[type];
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatCer(value: number | null) {
  return value === null ? "—" : `${(value * 100).toFixed(2)}%`;
}
</script>

<style scoped>
.ocr-filter-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-bottom: 14px;
}

.batch-progress-list {
  display: grid;
  gap: 8px;
  margin-top: 14px;
}

.batch-progress-list article {
  display: grid;
  gap: 6px;
}

.batch-progress-list article div {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
}

.batch-progress-list strong {
  font-family: sans-serif;
  font-size: 12px;
  overflow-wrap: anywhere;
}

.batch-progress-list span {
  color: var(--muted);
  flex: 0 0 auto;
  font-family: sans-serif;
  font-size: 12px;
}

.batch-progress-list progress {
  accent-color: var(--jade);
  width: 100%;
}

.ocr-page-list {
  max-height: 70vh;
  overflow: auto;
}

.review-sample {
  border-bottom: 1px solid var(--line);
  margin-bottom: 14px;
  padding-bottom: 14px;
}

.review-sample summary {
  color: var(--jade-dark);
  cursor: pointer;
  font-family: sans-serif;
  font-size: 13px;
}

.review-sample-list {
  display: grid;
  gap: 6px;
  margin-top: 10px;
}

.benchmark-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  margin-top: 10px;
}

.benchmark-strip span {
  color: var(--muted);
  font-family: sans-serif;
  font-size: 11px;
}

.sample-page-button {
  background: transparent;
  border: 1px solid var(--line);
  border-radius: 4px;
  color: var(--ink);
  display: grid;
  gap: 3px;
  padding: 8px;
  text-align: left;
}

.sample-page-button span {
  color: var(--muted);
  font-size: 11px;
}

.sample-page-button.active {
  border-color: var(--jade);
  box-shadow: inset 3px 0 0 var(--jade);
}

.page-controls {
  align-items: center;
  display: flex;
  font-family: sans-serif;
  font-size: 12px;
  gap: 8px;
  justify-content: space-between;
  margin-top: 12px;
}

.editor-toolbar {
  align-items: center;
  display: flex;
  justify-content: space-between;
}

.toggle-field,
.issue-picker label {
  align-items: center;
  display: flex;
  font-family: sans-serif;
  gap: 7px;
}

.ocr-editor-grid {
  display: grid;
  gap: 18px;
  grid-template-columns: minmax(300px, 0.9fr) minmax(360px, 1.1fr);
}

.editor-fields {
  align-content: start;
  display: grid;
  gap: 14px;
}

.editor-fields textarea {
  font-family: "Noto Serif SC", "Songti SC", serif;
  line-height: 1.8;
}

.issue-picker {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.save-message {
  color: var(--jade);
  margin: 0;
}

.provenance-grid {
  display: grid;
  gap: 8px 12px;
  grid-template-columns: 72px minmax(0, 1fr);
  margin-top: 12px;
}

.provenance-grid code {
  overflow-wrap: anywhere;
}

.empty-editor {
  min-height: 320px;
}

.mapping-editor {
  border-top: 1px solid var(--line);
  margin-top: 20px;
  padding-top: 16px;
}

.mapping-editor summary {
  color: var(--jade-dark);
  cursor: pointer;
  font-family: sans-serif;
  font-weight: 700;
}

.mapping-form {
  display: grid;
  gap: 14px;
  margin-top: 16px;
}

.mapping-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.mapping-grid .wide-field {
  grid-column: 1 / -1;
}

.mapping-actions {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  font-family: sans-serif;
  font-size: 12px;
  gap: 12px;
}

.parallel-pages {
  border-top: 1px solid var(--line);
  display: grid;
  gap: 1px;
  margin-top: 18px;
  padding-top: 16px;
}

.parallel-page-row {
  align-items: center;
  color: inherit;
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(0, 1fr) auto;
  padding: 10px 0;
}

.parallel-page-row a {
  color: inherit;
  display: grid;
  gap: 4px;
  grid-template-columns: minmax(180px, 0.7fr) minmax(0, 1.3fr);
  text-decoration: none;
}

.parallel-page-row + .parallel-page-row {
  border-top: 1px solid var(--line);
}

.parallel-page-row span {
  color: var(--muted);
}

@media (max-width: 1100px) {
  .ocr-editor-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 620px) {
  .ocr-filter-grid {
    grid-template-columns: 1fr;
  }

  .mapping-grid,
  .parallel-page-row,
  .parallel-page-row a {
    grid-template-columns: 1fr;
  }
}

.ocr-workbench {
  max-width: 1760px;
}

.ocr-page-header {
  align-items: flex-end;
  border-bottom: 1px solid var(--line);
  display: flex;
  gap: 20px;
  justify-content: space-between;
  padding: 2px 0 16px;
}

.ocr-page-header h1 {
  font-size: 28px;
  line-height: 1.2;
  margin: 0;
}

.ocr-header-actions {
  align-items: center;
  display: flex;
  gap: 14px;
}

.ocr-primary-metrics {
  display: flex;
  gap: 22px;
  margin: 0;
}

.ocr-primary-metrics div {
  border-left: 1px solid var(--line-strong);
  display: grid;
  gap: 2px;
  min-width: 68px;
  padding-left: 11px;
}

.ocr-primary-metrics dt {
  color: var(--muted);
  font-size: 10px;
}

.ocr-primary-metrics dd {
  font-size: 17px;
  font-weight: 700;
  margin: 0;
}

.icon-button {
  align-items: center;
  background: var(--surface);
  border: 1px solid var(--line-strong);
  border-radius: 4px;
  color: var(--ink-secondary);
  cursor: pointer;
  display: inline-flex;
  height: 36px;
  justify-content: center;
  padding: 0;
  width: 36px;
}

.icon-button:hover {
  border-color: var(--jade);
  color: var(--jade);
}

.icon-button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.spinning {
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.ocr-filter-bar {
  align-items: end;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 6px;
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(5, minmax(120px, 1fr));
  padding: 12px 14px;
}

.ocr-filter-bar label {
  display: grid;
  gap: 5px;
}

.ocr-filter-bar label > span {
  color: var(--muted);
  font-size: 10px;
  font-weight: 600;
}

.ocr-filter-bar select {
  background: var(--surface);
  border: 1px solid var(--line-strong);
  border-radius: 4px;
  color: var(--ink);
  font-size: 12px;
  min-height: 34px;
  padding: 6px 8px;
  width: 100%;
}

.ocr-filter-bar select:focus {
  border-color: var(--jade);
}

.ocr-filter-summary {
  color: var(--muted);
  font-family: sans-serif;
  font-size: 12px;
  margin: -4px 2px 0;
}

.manual-content-editor {
  background: color-mix(in srgb, var(--jade-soft) 38%, var(--surface));
  border: 1px solid var(--line);
  border-radius: 6px;
  display: grid;
  gap: 12px;
  padding: 14px;
}

.manual-content-editor > div:first-child {
  align-items: baseline;
  display: flex;
  gap: 10px;
  justify-content: space-between;
}

.manual-content-editor small,
.field-message {
  color: var(--muted);
  font-family: sans-serif;
  font-size: 11px;
}

.manual-keyword-composer {
  align-items: end;
  display: grid;
  gap: 8px;
  grid-template-columns: minmax(0, 1fr) 110px auto;
}

.manual-keyword-composer label {
  display: grid;
  gap: 5px;
}

.manual-keyword-composer label > span {
  color: var(--muted);
  font-family: sans-serif;
  font-size: 11px;
}

.manual-keyword-composer input,
.manual-keyword-composer select {
  min-height: 36px;
}

.manual-keyword-list {
  display: grid;
  gap: 6px;
}

.manual-keyword-list > div {
  align-items: center;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 4px;
  display: grid;
  gap: 8px;
  grid-template-columns: 58px minmax(0, 1fr) auto auto;
  padding: 7px 9px;
}

.manual-keyword-list span {
  color: var(--jade-dark);
  font-family: sans-serif;
  font-size: 11px;
}

.manual-keyword-list button {
  color: var(--cinnabar);
  font-size: 11px;
}

.field-message {
  margin: 0;
}

.batch-monitor {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 6px;
  font-size: 12px;
  padding: 10px 14px;
}

.batch-monitor > summary {
  color: var(--jade-dark);
  cursor: pointer;
  font-weight: 600;
}

.batch-progress-list {
  margin-top: 12px;
}

.batch-progress-list article {
  background: transparent;
  border: 0;
  padding: 0;
}

.batch-progress-list span,
.benchmark-strip span,
.sample-page-button span {
  color: var(--muted);
}

.batch-progress-list progress {
  accent-color: var(--jade);
}

.ocr-workspace-grid {
  gap: 14px;
  grid-template-columns: 320px minmax(0, 1fr);
}

.ocr-page-browser {
  align-content: start;
  overflow: hidden;
  padding: 0;
}

.ocr-page-browser > .section-heading {
  border-bottom: 1px solid var(--line);
  min-height: 54px;
  padding: 10px 14px;
}

.ocr-page-browser h2 {
  font-size: 16px;
}

.review-sample {
  border-bottom: 1px solid var(--line);
  margin: 0;
  padding: 11px 14px;
}

.review-sample summary {
  color: var(--jade-dark);
  font-size: 12px;
}

.review-sample-list {
  margin-top: 9px;
}

.sample-page-button {
  border-color: var(--line);
  color: var(--ink);
}

.sample-page-button.active {
  border-color: var(--jade);
  box-shadow: inset 3px 0 0 var(--jade);
}

.ocr-page-browser > p {
  color: var(--muted);
  padding: 10px 14px;
}

.ocr-page-list {
  max-height: calc(100vh - 310px);
  min-height: 360px;
  overflow: auto;
  padding: 8px;
}

.ocr-page-list .record-button {
  border: 0;
  border-bottom: 1px solid var(--line-soft);
  border-radius: 3px;
  margin: 0;
  padding: 10px 9px;
}

.ocr-page-list .record-button.active {
  background: var(--jade-wash);
  box-shadow: inset 3px 0 0 var(--jade);
}

.ocr-page-list .record-button strong {
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.ocr-page-list .record-button small {
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.ocr-page-browser > .page-controls {
  border-top: 1px solid var(--line);
  padding: 10px;
}

.ocr-page-browser > .page-controls button {
  font-size: 11px;
  min-height: 32px;
  padding: 6px 8px;
}

.ocr-workspace-grid > .inspector-panel {
  padding: 16px;
}

.ocr-workspace-grid .inspector-panel > .section-heading {
  border-bottom: 1px solid var(--line-soft);
  padding-bottom: 12px;
}

.ocr-workspace-grid .inspector-panel h2 {
  font-size: 16px;
  line-height: 1.35;
  margin: 0;
  overflow-wrap: anywhere;
}

.editor-toolbar {
  min-height: 30px;
}

.toggle-field,
.issue-picker label {
  color: var(--ink-secondary);
  font-size: 12px;
}

.ocr-editor-grid {
  gap: 14px;
  grid-template-columns: minmax(300px, 0.92fr) minmax(340px, 1.08fr);
}

.ocr-editor-grid .ocr-image-frame {
  max-height: 74vh;
  overflow: auto;
}

.editor-fields {
  gap: 11px;
}

.editor-fields textarea {
  font-family: var(--font-serif);
  line-height: 1.85;
}

.editor-fields > .textarea-field:first-child textarea {
  min-height: 430px;
}

.issue-picker {
  gap: 6px 10px;
}

.issue-picker label {
  background: var(--surface-muted);
  border-radius: 3px;
  padding: 5px 7px;
}

.save-message {
  color: var(--jade);
  font-size: 12px;
}

.inspector-panel details {
  border-top: 1px solid var(--line);
  margin: 0;
  padding-top: 12px;
}

.inspector-panel details > summary {
  color: var(--ink-secondary);
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
}

.provenance-grid {
  font-size: 11px;
}

.mapping-editor {
  margin-top: 0;
  padding-top: 12px;
}

.mapping-editor summary {
  color: var(--ink-secondary);
}

.mapping-form {
  margin-top: 14px;
}

.parallel-pages {
  border-top-color: var(--line);
}

.parallel-page-row + .parallel-page-row {
  border-top-color: var(--line-soft);
}

.empty-editor {
  align-items: center;
  color: var(--muted);
  justify-items: center;
  min-height: 520px;
}

@media (max-width: 1250px) {
  .ocr-editor-grid {
    grid-template-columns: 1fr;
  }

  .ocr-editor-grid .ocr-image-frame {
    max-height: 560px;
  }
}

@media (max-width: 980px) {
  .ocr-page-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .ocr-header-actions {
    justify-content: space-between;
    width: 100%;
  }

  .ocr-filter-bar {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .ocr-workspace-grid {
    grid-template-columns: 1fr;
  }

  .ocr-page-list {
    max-height: 360px;
    min-height: 0;
  }
}

@media (max-width: 640px) {
  .ocr-primary-metrics {
    display: grid;
    flex: 1;
    gap: 10px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .ocr-primary-metrics div {
    min-width: 0;
  }

  .ocr-filter-bar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .ocr-workspace-grid > .inspector-panel {
    padding: 13px;
  }

  .mapping-grid,
  .issue-picker,
  .manual-keyword-composer,
  .manual-keyword-list > div,
  .parallel-page-row,
  .parallel-page-row a {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 440px) {
  .ocr-filter-bar {
    grid-template-columns: 1fr;
  }
}
</style>
