<template>
  <main class="page-shell scan-reader">
    <section class="panel" v-if="page">
      <div class="reader-toolbar">
        <div>
          <p class="eyebrow">{{ page.book.title }} / {{ page.version.label }}</p>
          <h1>{{ page.source.file_label }} · PDF 第 {{ page.source.pdf_page }} 页</h1>
        </div>
        <div class="reader-actions">
          <RouterLink
            v-if="neighbors?.previous_page_id"
            class="text-link"
            :to="`/reader/scan/${neighbors.previous_page_id}`"
          >
            上一页
          </RouterLink>
          <RouterLink
            v-if="neighbors?.next_page_id"
            class="text-link"
            :to="`/reader/scan/${neighbors.next_page_id}`"
          >
            下一页
          </RouterLink>
          <RouterLink class="text-link" :to="`/books/${page.book.id}`">返回目录</RouterLink>
          <RouterLink
            class="text-link"
            :to="{ path: '/workbench/ocr', query: { page: page.id } }"
          >
            进入校对
          </RouterLink>
        </div>
      </div>

      <div class="reading-meta">
        <span>{{ page.version.provider }}</span>
        <span v-if="neighbors">本版本第 {{ neighbors.position }} / {{ neighbors.total }} 页</span>
        <span>{{ statusLabel(page.transcription.status) }}</span>
        <span>{{ page.ocr.metrics.character_count }} 字</span>
        <span>{{ Math.round(page.ocr.metrics.average_confidence * 100) }}%</span>
        <span v-if="page.mapping.status !== 'unmapped'">
          映射{{ mappingStatusLabel(page.mapping.status) }}
        </span>
        <span v-if="page.mapping.volume_title || page.mapping.volume_no">
          {{ page.mapping.volume_title || `卷 ${page.mapping.volume_no}` }}
        </span>
      </div>
    </section>

    <section class="panel scan-toolbar" v-if="page">
      <label>
        <span>缩放</span>
        <input v-model.number="zoom" type="range" min="60" max="180" step="10" />
        <output>{{ zoom }}%</output>
      </label>
      <label>
        <input v-model="showBoxes" type="checkbox" />
        <span>识别框</span>
      </label>
      <div class="segmented-control">
        <button :class="{ active: textMode === 'ocr' }" type="button" @click="textMode = 'ocr'">
          OCR 原文
        </button>
        <button
          :class="{ active: textMode === 'corrected' }"
          type="button"
          @click="textMode = 'corrected'"
        >
          校定文本
        </button>
      </div>
    </section>

    <section class="scan-reader-grid" v-if="page">
      <div class="scan-image-band">
        <div class="scan-image-stage" :style="{ width: `${zoom}%` }">
          <div class="ocr-image-frame">
            <img
              :src="getOcrWorkspacePageImageUrl(page.id)"
              :alt="page.reader.display_label"
              @load="handlePreviewLoad"
            />
            <template v-if="showBoxes">
              <div
                v-for="block in page.ocr.blocks"
                :key="block.id"
                class="ocr-image-box"
                :class="{ uncertain: block.confidence < 0.6 }"
                :style="overlayStyle(block)"
              >
                <span>{{ block.order }}</span>
              </div>
            </template>
          </div>
        </div>
      </div>

      <article class="panel scan-text">
        <p class="eyebrow">{{ textMode === "ocr" ? "忠实转录层" : "人工校定层" }}</p>
        <p class="vertical-source-text">{{ displayedText }}</p>
        <section
          class="manual-reading-content"
          v-if="page.manual_content.summary || page.manual_content.keywords.length"
        >
          <p class="eyebrow">人工阅读补丁</p>
          <p v-if="page.manual_content.summary" class="manual-summary">
            {{ page.manual_content.summary }}
          </p>
          <div class="manual-keywords" v-if="page.manual_content.keywords.length">
            <span v-for="keyword in page.manual_content.keywords" :key="keyword.id">
              {{ keywordTypeLabel(keyword.type) }} · {{ keyword.text }}
            </span>
          </div>
        </section>
        <dl class="source-details">
          <dt>来源</dt>
          <dd><a :href="page.source.item_url" target="_blank" rel="noreferrer">馆藏条目</a></dd>
          <dt>版本</dt>
          <dd>{{ page.version.label }}</dd>
          <dt>分册</dt>
          <dd>{{ page.source.file_label }}</dd>
          <dt>页码</dt>
          <dd>{{ page.source.pdf_page }} / {{ page.source.pdf_page_count }}</dd>
          <template v-if="page.mapping.status !== 'unmapped'">
            <dt>映射状态</dt>
            <dd>{{ mappingStatusLabel(page.mapping.status) }}</dd>
            <template v-if="page.mapping.canonical_unit_id">
              <dt>规范单元</dt>
              <dd>{{ page.mapping.canonical_unit_id }}</dd>
            </template>
            <dt v-if="page.mapping.volume_title || page.mapping.volume_no">卷篇</dt>
            <dd v-if="page.mapping.volume_title || page.mapping.volume_no">
              {{ page.mapping.volume_title || `卷 ${page.mapping.volume_no}` }}
              <template v-if="page.mapping.chapter_title">
                · {{ page.mapping.chapter_title }}
              </template>
            </dd>
            <template v-else-if="page.mapping.chapter_title">
              <dt>篇章</dt>
              <dd>{{ page.mapping.chapter_title }}</dd>
            </template>
            <dt>来源页标</dt>
            <dd>
              {{ page.mapping.source_leaf_label || "待标" }}
              <template v-if="page.mapping.leaf_side">
                · {{ leafSideLabel(page.mapping.leaf_side) }}
              </template>
            </dd>
          </template>
        </dl>

        <div class="parallel-pages" v-if="parallelPages.length">
          <p class="eyebrow">同一规范单元的其他版本</p>
          <RouterLink
            v-for="parallel in parallelPages"
            :key="parallel.id"
            :to="`/reader/scan/${parallel.id}`"
          >
            <strong>{{ parallel.version_label }}</strong>
            <span>
              {{ parallel.source_file_label }} · PDF 第 {{ parallel.pdf_page }} 页 ·
              映射{{ mappingStatusLabel(parallel.mapping_status) }}
            </span>
          </RouterLink>
        </div>
      </article>
    </section>

    <section class="panel" v-else>
      <p v-if="loading">正在加载影印页...</p>
      <p v-else class="error-text">{{ error || "影印页不存在。" }}</p>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";

import {
  type OcrBlock,
  type OcrManualKeyword,
  type OcrPageNeighbors,
  type OcrParallelPage,
  type OcrWorkspacePage,
  getOcrWorkspacePage,
  getOcrWorkspacePageImageUrl,
  getOcrWorkspacePageNeighbors,
  getOcrWorkspacePageParallels,
} from "../services/api";

const route = useRoute();
const page = ref<OcrWorkspacePage | null>(null);
const neighbors = ref<OcrPageNeighbors | null>(null);
const parallelPages = ref<OcrParallelPage[]>([]);
const loading = ref(true);
const error = ref("");
const zoom = ref(100);
const showBoxes = ref(false);
const textMode = ref<"ocr" | "corrected">("corrected");
const previewSize = ref({ width: 1, height: 1 });

const displayedText = computed(() => {
  if (!page.value) {
    return "";
  }
  if (textMode.value === "corrected") {
    return page.value.transcription.corrected_text || page.value.transcription.raw_text;
  }
  return page.value.transcription.raw_text;
});

watch(
  () => route.params.pageId,
  async (pageId) => {
    loading.value = true;
    error.value = "";
    page.value = null;
    neighbors.value = null;
    parallelPages.value = [];
    try {
      const [pagePayload, neighborPayload, parallelPayload] = await Promise.all([
        getOcrWorkspacePage(String(pageId)),
        getOcrWorkspacePageNeighbors(String(pageId)),
        getOcrWorkspacePageParallels(String(pageId)),
      ]);
      page.value = pagePayload;
      neighbors.value = neighborPayload;
      parallelPages.value = parallelPayload;
    } catch (err) {
      error.value = err instanceof Error ? err.message : "加载失败";
    } finally {
      loading.value = false;
    }
  },
  { immediate: true },
);

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

function leafSideLabel(side: string) {
  return {
    recto: "正面",
    verso: "背面",
    unknown: "不详",
  }[side] ?? side;
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
</script>

<style scoped>
.scan-reader {
  max-width: 1500px;
}

.reader-actions {
  display: flex;
  gap: 14px;
}

.scan-toolbar {
  align-items: center;
  display: flex;
  gap: 22px;
}

.scan-toolbar label {
  align-items: center;
  display: flex;
  font-family: sans-serif;
  gap: 8px;
}

.scan-toolbar .segmented-control {
  margin-left: auto;
  min-width: 230px;
}

.scan-reader-grid {
  display: grid;
  gap: 18px;
  grid-template-columns: minmax(0, 1.5fr) minmax(320px, 0.5fr);
}

.scan-image-band {
  background: #302f2b;
  min-height: 70vh;
  overflow: auto;
  padding: 24px;
}

.scan-image-stage {
  margin: 0 auto;
  max-width: 1500px;
  min-width: 60%;
}

.scan-text {
  align-self: start;
  position: sticky;
  top: 86px;
}

.vertical-source-text {
  line-height: 2;
  white-space: pre-wrap;
}

.manual-reading-content {
  background: var(--jade-soft);
  border: 1px solid var(--line);
  border-radius: 6px;
  margin-top: 20px;
  padding: 14px;
}

.manual-summary {
  line-height: 1.8;
  margin: 8px 0 0;
}

.manual-keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 10px;
}

.manual-keywords span {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--jade-dark);
  font-family: sans-serif;
  font-size: 11px;
  padding: 4px 8px;
}

.source-details {
  border-top: 1px solid var(--line);
  display: grid;
  gap: 8px;
  grid-template-columns: 54px minmax(0, 1fr);
  margin: 24px 0 0;
  padding-top: 16px;
}

.source-details dt {
  color: var(--muted);
}

.source-details dd {
  margin: 0;
}

.parallel-pages {
  border-top: 1px solid var(--line);
  display: grid;
  gap: 1px;
  margin-top: 22px;
  padding-top: 18px;
}

.parallel-pages a {
  color: inherit;
  display: grid;
  gap: 3px;
  padding: 10px 0;
  text-decoration: none;
}

.parallel-pages a + a {
  border-top: 1px solid var(--line);
}

.parallel-pages span {
  color: var(--muted);
  font-size: 13px;
}

@media (max-width: 980px) {
  .scan-reader-grid {
    grid-template-columns: 1fr;
  }

  .scan-text {
    position: static;
  }
}

@media (max-width: 640px) {
  .reader-actions {
    flex-wrap: wrap;
  }

  .scan-toolbar {
    align-items: stretch;
    display: grid;
    gap: 16px;
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .scan-toolbar label {
    min-width: 0;
  }

  .scan-toolbar label:first-child {
    display: grid;
    grid-template-columns: auto minmax(90px, 1fr) auto;
  }

  .scan-toolbar input[type="range"] {
    min-width: 0;
    width: 100%;
  }

  .scan-toolbar .segmented-control {
    grid-column: 1 / -1;
    margin-left: 0;
    min-width: 0;
    width: 100%;
  }

  .scan-image-band {
    min-height: 60vh;
    padding: 12px;
  }
}
</style>
