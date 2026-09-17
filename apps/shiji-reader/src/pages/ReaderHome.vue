<template>
  <main class="home-layout library-page">
    <header class="library-header">
      <div>
        <p class="eyebrow">史海 · 当前阅读范围</p>
        <h1>《史记》专题</h1>
      </div>
      <dl class="library-totals" aria-label="馆藏统计">
        <div>
          <dt>当前史书</dt>
          <dd>{{ books.length || "—" }}</dd>
        </div>
        <div>
          <dt>已接版本</dt>
          <dd>{{ featuredBook?.version_count ?? "—" }}</dd>
        </div>
        <div>
          <dt>OCR 页</dt>
          <dd>{{ formatNumber(ocrPageTotal) }}</dd>
        </div>
      </dl>
    </header>

    <section v-if="featuredBook" class="current-reading">
      <div class="current-reading-icon" aria-hidden="true">
        <BookOpenText :size="22" />
      </div>
      <div class="current-reading-copy">
        <span>当前主书</span>
        <strong>《{{ featuredBook.title }}》</strong>
        <small>{{ featuredBook.author }} · {{ featuredBook.period }}</small>
      </div>
      <div class="current-reading-meta">
        <span>{{ featuredBook.version_count ?? 0 }} 个版本</span>
        <span>{{ formatNumber(featuredBook.ocr_page_count ?? 0) }} 页 OCR</span>
      </div>
      <RouterLink class="primary-action" :to="`/books/${featuredBook.id}`">
        进入书目
        <ArrowRight :size="16" aria-hidden="true" />
      </RouterLink>
    </section>

    <section class="library-browser" aria-labelledby="library-title">
      <div class="library-toolbar">
        <div>
          <h2 id="library-title">当前开放</h2>
          <span>本轮仅《史记》</span>
        </div>
        <label class="search-field">
          <Search :size="17" aria-hidden="true" />
          <input v-model.trim="query" type="search" placeholder="搜索《史记》" />
        </label>
        <div class="filter-tabs" role="group" aria-label="馆藏状态">
          <button
            v-for="option in filterOptions"
            :key="option.id"
            type="button"
            :class="{ active: statusFilter === option.id }"
            @click="statusFilter = option.id"
          >
            {{ option.label }}
          </button>
        </div>
      </div>

      <p v-if="loading" class="library-state">正在加载...</p>
      <p v-else-if="error" class="error-text library-state">{{ error }}</p>
      <p v-else-if="!filteredBooks.length" class="library-state">没有匹配的史书。</p>

      <div v-else class="book-table">
        <div class="book-table-head" aria-hidden="true">
          <span>书名</span>
          <span>版本</span>
          <span>影印</span>
          <span>OCR</span>
          <span>状态</span>
          <span></span>
        </div>
        <RouterLink
          v-for="(book, index) in filteredBooks"
          :key="book.id"
          class="book-row"
          :to="`/books/${book.id}`"
        >
          <div class="book-title-cell">
            <span>{{ String(index + 1).padStart(2, "0") }}</span>
            <div>
              <strong>《{{ book.title }}》</strong>
              <small>{{ book.author }} · {{ book.period }}</small>
            </div>
          </div>
          <span class="book-metric">{{ book.version_count ?? 0 }}</span>
          <span class="book-metric">{{ book.scan_file_count ?? 0 }}</span>
          <span class="book-metric">{{ formatNumber(book.ocr_page_count ?? 0) }}</span>
          <span class="book-status" :class="`status-${statusGroup(book)}`">
            {{ statusLabel(book.status) }}
          </span>
          <ChevronRight class="book-row-arrow" :size="18" aria-hidden="true" />
        </RouterLink>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ArrowRight, BookOpenText, ChevronRight, Search } from "@lucide/vue";

import { type Book, getBooks } from "../services/api";

type StatusFilter = "all" | "ready" | "progress" | "planned";

const books = ref<Book[]>([]);
const loading = ref(true);
const error = ref("");
const query = ref("");
const statusFilter = ref<StatusFilter>("all");

const filterOptions: Array<{ id: StatusFilter; label: string }> = [
  { id: "all", label: "全部" },
  { id: "ready", label: "可阅读" },
  { id: "progress", label: "整理中" },
  { id: "planned", label: "待接入" },
];

const featuredBook = computed(() => books.value.find((book) => book.id === "shiji"));
const ocrPageTotal = computed(() =>
  books.value.reduce((total, book) => total + (book.ocr_page_count ?? 0), 0),
);

const filteredBooks = computed(() => {
  const keyword = query.value.toLocaleLowerCase();
  return books.value.filter((book) => {
    const matchesQuery =
      !keyword ||
      [book.title, book.author, book.period].some((value) =>
        value.toLocaleLowerCase().includes(keyword),
      );
    const matchesStatus =
      statusFilter.value === "all" || statusGroup(book) === statusFilter.value;
    return matchesQuery && matchesStatus;
  });
});

onMounted(async () => {
  try {
    books.value = (await getBooks()).filter((book) => book.id === "shiji");
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
});

function statusGroup(book: Book): Exclude<StatusFilter, "all"> {
  if (book.available) {
    return "ready";
  }
  return book.status === "planned" ? "planned" : "progress";
}

function statusLabel(status: string) {
  return {
    ocr_in_progress: "OCR 整理中",
    scans_ready: "书影已入库",
    scans_partial: "书影获取中",
    sources_selected: "版本已定",
    planned: "待接入",
  }[status] ?? status;
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-CN").format(value);
}
</script>
