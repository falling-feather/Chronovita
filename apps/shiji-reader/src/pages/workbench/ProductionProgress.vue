<template>
  <main class="workbench-layout production-progress">
    <header class="progress-header">
      <div>
        <h1>生产进度</h1>
        <p>从文献就绪到阅读器暂存，查看标准自动批次的八阶段状态。</p>
      </div>
      <div class="header-actions">
        <span class="live-status">
          <i aria-hidden="true"></i>
          {{ freshnessLabel }}
        </span>
        <button class="secondary-action" type="button" :disabled="refreshing" @click="loadDashboard()">
          <RefreshCw :size="15" :class="{ spinning: refreshing }" aria-hidden="true" />
          {{ refreshing ? "更新中" : "刷新" }}
        </button>
      </div>
    </header>

    <div class="dashboard-overview-row" :class="{ ready: dashboard }">
      <section class="filter-panel" aria-label="生产进度筛选">
        <label>
          <span>文献</span>
          <select v-model="selectedBook" @change="changeBook">
            <option value="">全部 {{ dashboard?.filters.books.length ?? 0 }} 部</option>
            <option v-for="book in dashboard?.filters.books" :key="book.id" :value="book.id">
              {{ book.title }} · {{ book.item_count }} 批
            </option>
          </select>
        </label>
        <label>
          <span>具体条目</span>
          <select v-model="selectedItem" @change="changeItem">
            <option value="">全部批次</option>
            <option v-for="item in dashboard?.filters.items" :key="item.id" :value="item.id">
              {{ selectedBook ? item.label : `${item.book_title} · ${item.label}` }}
            </option>
          </select>
        </label>
        <label class="search-control">
          <span>快捷查找</span>
          <span class="search-box">
            <Search :size="15" aria-hidden="true" />
            <input v-model.trim="searchText" type="search" placeholder="书名、批次编号或阶段" />
          </span>
        </label>
        <button
          v-if="selectedBook || selectedItem || selectedStage || searchText"
          class="clear-button"
          type="button"
          @click="clearFilters"
        >
          清除筛选
        </button>
      </section>

      <section v-if="dashboard" class="summary-grid" aria-label="当前任务摘要">
        <article>
          <span>标准阶段任务</span>
          <strong>{{ formatNumber(dashboard.overview.task_total) }}</strong>
          <small>{{ scopeLabel }}</small>
        </article>
        <article class="summary-passed">
          <span>已通过</span>
          <strong>{{ formatNumber(dashboard.overview.task_passed) }}</strong>
          <small>AI 阶段门禁通过</small>
        </article>
        <article class="summary-active">
          <span>执行中</span>
          <strong>{{ formatNumber(dashboard.overview.task_active) }}</strong>
          <small>另有 {{ formatNumber(dashboard.overview.task_ready) }} 项待领取</small>
        </article>
        <article class="summary-rework">
          <span>返工 / 阻塞</span>
          <strong>
            {{ formatNumber(dashboard.overview.task_rework + dashboard.overview.task_blocked) }}
          </strong>
          <small>{{ dashboard.overview.task_blocked }} 项处于阻塞</small>
        </article>
      </section>
    </div>

    <p v-if="loading" class="loading-panel dashboard-state">正在读取生产队列...</p>
    <section v-else-if="error" class="error-panel dashboard-state" role="alert">
      <AlertCircle :size="20" aria-hidden="true" />
      <div>
        <strong>生产进度暂时无法读取</strong>
        <p>{{ error }}</p>
      </div>
      <button class="secondary-action" type="button" @click="loadDashboard()">重试</button>
    </section>

    <template v-else-if="dashboard">
      <section class="scope-card" aria-labelledby="scope-title">
        <div class="scope-heading">
          <div>
            <p class="eyebrow">统计口径</p>
            <h2 id="scope-title">四层进度分开观测</h2>
          </div>
          <span class="info-trigger" title="任务数、页次和 OCR 唯一页采用不同分母">
            <Info :size="16" aria-hidden="true" />
            口径说明
          </span>
        </div>
        <div class="scope-metrics">
          <article>
            <span>上游资料 / OCR 门禁</span>
            <strong>
              {{ dashboard.overview.source_books_completed }}/{{ dashboard.overview.source_books_total }} 部
            </strong>
            <small>
              OCR {{ formatNumber(dashboard.overview.ocr_pages_completed) }}/{{ formatNumber(dashboard.overview.ocr_pages_total) }} 唯一页
            </small>
          </article>
          <article>
            <span>全量页对投产覆盖</span>
            <strong>{{ formatPercent(dashboard.overview.corpus_coverage_percent, 2) }}</strong>
            <small>
              {{ formatNumber(dashboard.overview.materialized_pairs) }}/{{ formatNumber(dashboard.overview.available_pairs) }} 对
            </small>
          </article>
          <article>
            <span>已投产队列页次通过</span>
            <strong>{{ formatPercent(dashboard.overview.queue_pass_percent, 1) }}</strong>
            <small>六个生产阶段按 page_count 加权</small>
          </article>
          <article>
            <span>阅读器暂存覆盖</span>
            <strong>{{ formatPercent(dashboard.overview.staged_coverage_percent, 2) }}</strong>
            <small>{{ formatNumber(dashboard.overview.staged_pairs) }} 对进入 workbench 暂存</small>
          </article>
        </div>
        <p v-if="dashboard.overview.item_selected" class="selection-note">
          当前条目含 {{ dashboard.overview.selected_pairs }} 对书影；上方“全量页对投产覆盖”仍保持整部史书口径。
        </p>
      </section>

      <section class="pipeline-card" aria-labelledby="pipeline-title">
        <div class="card-heading compact-heading">
          <div>
            <h2 id="pipeline-title">阶段总览</h2>
            <p>点击阶段可筛选下方批次明细。</p>
          </div>
          <span>{{ dashboard.status_label }}</span>
        </div>
        <StagePipeline
          :stages="dashboard.stages"
          :selected-stage="selectedStage"
          @select="changeStage"
        />
      </section>

      <section class="chart-grid" aria-label="生产进度图表">
        <article class="chart-card">
          <div class="card-heading">
            <div>
              <h2>各阶段状态分布</h2>
              <p>来源按部、OCR 按唯一页，生产阶段按页次归一化显示。</p>
            </div>
          </div>
          <StageStatusBarChart
            :stages="dashboard.stages"
            :selected-stage="selectedStage"
            @select="changeStage"
          />
        </article>

        <article class="chart-card trend-card">
          <div class="card-heading">
            <div>
              <h2>生产通过趋势</h2>
              <p>返工会从累计通过页次中扣回。</p>
            </div>
            <div class="range-switch" aria-label="趋势时间范围">
              <button
                v-for="days in trendOptions"
                :key="days"
                type="button"
                :class="{ active: trendDays === days }"
                @click="changeTrendDays(days)"
              >
                {{ days }} 天
              </button>
            </div>
          </div>
          <ProgressTrendChart :points="dashboard.trend" />
        </article>
      </section>

      <section class="alert-strip" aria-labelledby="alert-title">
        <div class="alert-title">
          <TriangleAlert :size="16" aria-hidden="true" />
          <h2 id="alert-title">当前关注</h2>
        </div>
        <article
          v-for="alert in dashboard.alerts"
          :key="`${alert.stage_id}-${alert.level}`"
          :class="`alert-${alert.level}`"
        >
          <span>{{ alert.label }}</span>
          <strong>{{ alert.detail ?? `${formatNumber(alert.count)} 页次` }}</strong>
        </article>
        <p v-if="!dashboard.alerts.length" class="no-alerts">当前没有返工、阻塞或待领取积压。</p>
      </section>

      <section class="batch-card" aria-labelledby="batch-title">
        <div class="card-heading batch-heading">
          <div>
            <h2 id="batch-title">批次明细</h2>
            <p>{{ filteredRows.length }} / {{ dashboard.rows.length }} 个批次</p>
          </div>
          <span v-if="selectedStage" class="active-filter">
            {{ stageLabel(selectedStage) }}
            <button type="button" aria-label="清除阶段筛选" @click="changeStage('')">×</button>
          </span>
        </div>
        <div class="batch-table-wrap">
          <table class="batch-table">
            <thead>
              <tr>
                <th>文献</th>
                <th>具体条目</th>
                <th>当前阶段</th>
                <th>阶段进度</th>
                <th>状态</th>
                <th>更新时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in pagedRows" :key="row.id">
                <td><strong>{{ row.book_title }}</strong></td>
                <td>
                  <button class="batch-link" type="button" @click="selectRow(row)">
                    {{ row.label }}
                    <ArrowUpRight :size="13" aria-hidden="true" />
                  </button>
                  <small>{{ row.id }}</small>
                </td>
                <td>{{ stageLabel(row.current_stage) }}</td>
                <td>
                  <span class="mini-progress" aria-hidden="true">
                    <i :style="{ width: `${((row.passed_stages + 2) / 8) * 100}%` }"></i>
                  </span>
                  <small>{{ row.passed_stages + 2 }} / 8</small>
                </td>
                <td>
                  <span class="state-badge" :class="`state-${row.state}`">
                    {{ stateLabel(row.state) }}
                  </span>
                </td>
                <td>{{ formatDateTime(row.updated_at) }}</td>
              </tr>
              <tr v-if="!pagedRows.length">
                <td class="empty-table" colspan="6">没有符合当前筛选条件的批次。</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="filteredRows.length > visibleLimit" class="table-footer">
          <span>仅显示前 {{ visibleLimit }} 项</span>
          <button class="text-link" type="button" @click="visibleLimit += pageSize">继续显示</button>
        </div>
      </section>

      <footer class="dashboard-footnote">
        <Info :size="14" aria-hidden="true" />
        DATA 通过仅表示阅读器工作台暂存；所有 AI 结果仍是“AI初筛完成/人类待检查”，不等于人工校定或正式发布。
      </footer>
    </template>
  </main>
</template>

<script setup lang="ts">
import {
  AlertCircle,
  ArrowUpRight,
  Info,
  RefreshCw,
  Search,
  TriangleAlert,
} from "@lucide/vue";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import ProgressTrendChart from "../../components/workbench/ProgressTrendChart.vue";
import StagePipeline from "../../components/workbench/StagePipeline.vue";
import StageStatusBarChart from "../../components/workbench/StageStatusBarChart.vue";
import {
  type ProductionDashboard,
  type ProductionDashboardItem,
  type ProductionTaskState,
  getProductionDashboard,
} from "../../services/api";

const route = useRoute();
const router = useRouter();
const dashboard = ref<ProductionDashboard | null>(null);
const loading = ref(true);
const refreshing = ref(false);
const error = ref("");
const selectedBook = ref("");
const selectedItem = ref("");
const selectedStage = ref("");
const searchText = ref("");
const trendDays = ref<7 | 14 | 30>(14);
const visibleLimit = ref(8);
const pageSize = 8;
const trendOptions = [7, 14, 30] as const;
let pollTimer: number | undefined;
let loadSequence = 0;

const numberFormatter = new Intl.NumberFormat("zh-CN");

const scopeLabel = computed(() => {
  if (selectedItem.value) {
    return dashboard.value?.filters.items.find((item) => item.id === selectedItem.value)?.label ?? "所选批次";
  }
  if (selectedBook.value) {
    return dashboard.value?.filters.books.find((book) => book.id === selectedBook.value)?.title ?? "所选文献";
  }
  return `${dashboard.value?.overview.materialized_batch_count ?? 0} 个标准自动批次`;
});

const freshnessLabel = computed(() => {
  const value = dashboard.value?.freshness.queue_updated_at;
  if (!value) {
    return "30 秒自动刷新";
  }
  const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) {
    return `${seconds} 秒前更新`;
  }
  if (seconds < 3600) {
    return `${Math.floor(seconds / 60)} 分钟前更新`;
  }
  return formatDateTime(value);
});

const filteredRows = computed(() => {
  if (!dashboard.value) {
    return [];
  }
  const needle = searchText.value.trim().toLocaleLowerCase("zh-CN");
  return dashboard.value.rows.filter((row) => {
    const stageMatch = !selectedStage.value || row.current_stage === selectedStage.value;
    const textMatch =
      !needle ||
      [row.book_title, row.label, row.id, stageLabel(row.current_stage), stateLabel(row.state)]
        .join(" ")
        .toLocaleLowerCase("zh-CN")
        .includes(needle);
    return stageMatch && textMatch;
  });
});

const pagedRows = computed(() => filteredRows.value.slice(0, visibleLimit.value));

watch(
  [
    () => route.query.book,
    () => route.query.item,
    () => route.query.days,
  ],
  () => {
    selectedBook.value = queryValue(route.query.book);
    selectedItem.value = queryValue(route.query.item);
    trendDays.value = parseTrendDays(route.query.days);
    void loadDashboard();
  },
  { immediate: true },
);

watch(
  () => route.query.stage,
  (value) => {
    selectedStage.value = queryValue(value);
    visibleLimit.value = pageSize;
  },
  { immediate: true },
);

watch(searchText, () => {
  visibleLimit.value = pageSize;
});

onMounted(() => {
  pollTimer = window.setInterval(() => {
    if (!document.hidden) {
      void loadDashboard(true);
    }
  }, 30_000);
  document.addEventListener("visibilitychange", handleVisibilityChange);
});

onBeforeUnmount(() => {
  if (pollTimer !== undefined) {
    window.clearInterval(pollTimer);
  }
  document.removeEventListener("visibilitychange", handleVisibilityChange);
});

async function loadDashboard(silent = false) {
  const sequence = ++loadSequence;
  if (!silent && !dashboard.value) {
    loading.value = true;
  }
  refreshing.value = true;
  error.value = "";
  try {
    const payload = await getProductionDashboard({
      bookId: selectedBook.value || undefined,
      itemId: selectedItem.value || undefined,
      trendDays: trendDays.value,
    });
    if (sequence === loadSequence) {
      dashboard.value = payload;
    }
  } catch (caught) {
    if (sequence === loadSequence) {
      error.value = caught instanceof Error ? caught.message : "加载失败";
    }
  } finally {
    if (sequence === loadSequence) {
      loading.value = false;
      refreshing.value = false;
    }
  }
}

function changeBook() {
  selectedItem.value = "";
  void replaceQuery({ book: selectedBook.value, item: "" });
}

function changeItem() {
  void replaceQuery({ item: selectedItem.value });
}

function changeStage(stageId: string) {
  selectedStage.value = stageId;
  void replaceQuery({ stage: stageId });
}

function changeTrendDays(days: 7 | 14 | 30) {
  trendDays.value = days;
  void replaceQuery({ days: String(days) });
}

function clearFilters() {
  selectedBook.value = "";
  selectedItem.value = "";
  selectedStage.value = "";
  searchText.value = "";
  void router.replace({ query: { days: String(trendDays.value) } });
}

function selectRow(row: ProductionDashboardItem) {
  selectedBook.value = row.book_id;
  selectedItem.value = row.id;
  void replaceQuery({ book: row.book_id, item: row.id });
}

function replaceQuery(values: Record<string, string>) {
  const query = { ...route.query };
  for (const [key, value] of Object.entries(values)) {
    if (value) {
      query[key] = value;
    } else {
      delete query[key];
    }
  }
  return router.replace({ query });
}

function handleVisibilityChange() {
  if (!document.hidden) {
    void loadDashboard(true);
  }
}

function queryValue(value: unknown) {
  return typeof value === "string" ? value : "";
}

function parseTrendDays(value: unknown): 7 | 14 | 30 {
  const parsed = Number(queryValue(value));
  return parsed === 7 || parsed === 30 ? parsed : 14;
}

function formatNumber(value: number) {
  return numberFormatter.format(value);
}

function formatPercent(value: number | null, digits: number) {
  return value === null ? "—" : `${value.toFixed(digits)}%`;
}

function formatDateTime(value: string) {
  if (!value) {
    return "—";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function stageLabel(stageId: string) {
  return dashboard.value?.stages.find((stage) => stage.id === stageId)?.label ?? stageId;
}

function stateLabel(state: ProductionTaskState) {
  return {
    passed: "已通过",
    processing: "执行中",
    claimed: "已领取",
    ready: "待领取",
    waiting: "未解锁",
    rework: "返工",
    blocked: "阻塞",
  }[state];
}
</script>

<style scoped>
.production-progress {
  gap: 14px;
  max-width: 1460px;
}

.progress-header {
  align-items: flex-end;
  border-bottom: 1px solid var(--line);
  display: flex;
  gap: 18px;
  justify-content: space-between;
  padding: 2px 0 16px;
}

.progress-header h1,
.progress-header p {
  margin: 0;
}

.progress-header h1 {
  font-family: var(--font-serif);
  font-size: 29px;
}

.progress-header > div:first-child > p:last-child {
  color: var(--muted);
  font-size: 13px;
  margin-top: 7px;
}

.dashboard-overview-row {
  display: grid;
}

.dashboard-overview-row.ready {
  align-items: stretch;
  gap: 12px;
  grid-template-columns: minmax(420px, 0.95fr) minmax(600px, 1.25fr);
}

.header-actions,
.live-status {
  align-items: center;
  display: flex;
  gap: 9px;
}

.live-status {
  color: var(--muted);
  font-size: 11px;
  white-space: nowrap;
}

.live-status i {
  background: #2d8b6d;
  border-radius: 999px;
  box-shadow: 0 0 0 4px rgba(45, 139, 109, 0.1);
  height: 7px;
  width: 7px;
}

.spinning {
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.filter-panel {
  align-items: end;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 6px;
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(120px, 0.7fr) minmax(180px, 1.15fr) minmax(180px, 1fr) auto;
  padding: 13px 15px;
}

.filter-panel label {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.filter-panel label > span:first-child {
  color: var(--muted);
  font-size: 10px;
  font-weight: 600;
}

.filter-panel select,
.search-box {
  background: var(--surface-muted);
  border: 1px solid var(--line);
  border-radius: 4px;
  color: var(--ink-secondary);
  min-height: 36px;
}

.filter-panel select {
  padding: 6px 9px;
  width: 100%;
}

.search-box {
  align-items: center;
  display: flex;
  gap: 7px;
  padding: 0 9px;
}

.search-box svg {
  color: var(--muted-light);
  flex: 0 0 auto;
}

.search-box input {
  background: transparent;
  border: 0;
  color: var(--ink);
  min-width: 0;
  outline: 0;
  width: 100%;
}

.clear-button,
.info-trigger {
  color: var(--jade);
  font-size: 11px;
}

.clear-button {
  background: transparent;
  border: 0;
  cursor: pointer;
  min-height: 36px;
  padding: 6px 3px;
}

.dashboard-state {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 6px;
  min-height: 240px;
}

.error-panel {
  align-items: center;
  color: var(--cinnabar);
  display: flex;
  gap: 14px;
  justify-content: center;
}

.error-panel p {
  color: var(--muted);
  margin: 4px 0 0;
}

.summary-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.dashboard-overview-row .summary-grid {
  gap: 0;
}

.summary-grid article {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 6px;
  display: grid;
  gap: 6px;
  min-height: 100px;
  padding: 15px 17px;
  position: relative;
}

.dashboard-overview-row .summary-grid article {
  border-radius: 0;
  border-right: 0;
  min-height: auto;
}

.dashboard-overview-row .summary-grid article:first-child {
  border-radius: 6px 0 0 6px;
}

.dashboard-overview-row .summary-grid article:last-child {
  border-radius: 0 6px 6px 0;
  border-right: 1px solid var(--line);
}

.summary-grid article::before {
  background: var(--line-strong);
  content: "";
  inset: 0 auto 0 0;
  position: absolute;
  width: 3px;
}

.summary-grid .summary-passed::before { background: var(--jade); }
.summary-grid .summary-active::before { background: #4c78a8; }
.summary-grid .summary-rework::before { background: var(--cinnabar); }

.summary-grid span,
.summary-grid small {
  color: var(--muted);
  font-size: 10px;
}

.summary-grid strong {
  font-size: 26px;
  font-variant-numeric: tabular-nums;
  line-height: 1.05;
}

.summary-grid small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scope-card,
.pipeline-card,
.chart-card,
.alert-strip,
.batch-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 6px;
}

.scope-card {
  display: grid;
  gap: 13px;
  padding: 15px 17px;
}

.scope-heading,
.card-heading,
.alert-title {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
}

.scope-heading h2,
.scope-heading p,
.card-heading h2,
.card-heading p,
.alert-title h2 {
  margin: 0;
}

.scope-heading h2,
.card-heading h2,
.alert-title h2 {
  font-size: 15px;
}

.info-trigger {
  align-items: center;
  cursor: help;
  display: inline-flex;
  gap: 5px;
}

.scope-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.scope-metrics article {
  border-left: 1px solid var(--line-soft);
  display: grid;
  gap: 5px;
  padding: 2px 16px;
}

.scope-metrics article:first-child {
  border-left: 0;
  padding-left: 0;
}

.scope-metrics article:last-child {
  padding-right: 0;
}

.scope-metrics span,
.scope-metrics small {
  color: var(--muted);
  font-size: 10px;
}

.scope-metrics strong {
  font-size: 19px;
  font-variant-numeric: tabular-nums;
}

.scope-metrics small {
  line-height: 1.45;
}

.selection-note {
  background: var(--jade-wash);
  border-left: 2px solid var(--jade);
  color: var(--muted);
  font-size: 11px;
  margin: 0;
  padding: 7px 9px;
}

.pipeline-card {
  display: grid;
  gap: 9px;
  padding: 14px 16px 10px;
}

.card-heading p {
  color: var(--muted);
  font-size: 10px;
  margin-top: 4px;
}

.compact-heading > span {
  background: var(--jade-soft);
  border-radius: 999px;
  color: var(--jade-dark);
  font-size: 10px;
  padding: 5px 8px;
}

.chart-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr);
}

.chart-card {
  display: grid;
  gap: 14px;
  min-width: 0;
  padding: 15px 17px;
}

.range-switch {
  background: var(--surface-muted);
  border: 1px solid var(--line);
  border-radius: 4px;
  display: flex;
  padding: 2px;
}

.range-switch button {
  background: transparent;
  border: 0;
  border-radius: 3px;
  color: var(--muted);
  cursor: pointer;
  font-size: 9px;
  padding: 5px 7px;
}

.range-switch button.active {
  background: var(--surface);
  box-shadow: 0 1px 3px rgba(31, 51, 44, 0.12);
  color: var(--ink);
  font-weight: 600;
}

.alert-strip {
  align-items: stretch;
  display: grid;
  gap: 0;
  grid-template-columns: 150px repeat(3, minmax(0, 1fr));
  min-height: 58px;
  overflow: hidden;
}

.alert-title {
  justify-content: flex-start;
  padding: 12px 15px;
}

.alert-title svg {
  color: var(--cinnabar);
}

.alert-strip article {
  border-left: 1px solid var(--line-soft);
  display: grid;
  gap: 3px;
  padding: 11px 15px;
}

.alert-strip article span {
  color: var(--muted);
  font-size: 10px;
}

.alert-strip article strong {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.alert-danger { box-shadow: inset 3px 0 0 var(--cinnabar); }
.alert-warning { box-shadow: inset 3px 0 0 #c6923b; }
.alert-info { box-shadow: inset 3px 0 0 var(--jade); }

.no-alerts {
  align-self: center;
  color: var(--muted);
  font-size: 11px;
  grid-column: 2 / -1;
  margin: 0;
}

.batch-card {
  min-width: 0;
  overflow: hidden;
}

.batch-heading {
  min-height: 59px;
  padding: 10px 16px;
}

.active-filter {
  align-items: center;
  background: var(--jade-soft);
  border-radius: 999px;
  color: var(--jade-dark);
  display: inline-flex;
  font-size: 10px;
  gap: 6px;
  padding: 5px 8px;
}

.active-filter button {
  background: transparent;
  border: 0;
  color: inherit;
  cursor: pointer;
  font-size: 15px;
  line-height: 1;
  padding: 0;
}

.batch-table-wrap {
  overflow-x: auto;
}

.batch-table {
  border-collapse: collapse;
  font-size: 11px;
  min-width: 820px;
  width: 100%;
}

.batch-table th {
  background: var(--surface-muted);
  color: var(--muted);
  font-size: 9px;
  font-weight: 600;
  text-align: left;
}

.batch-table th,
.batch-table td {
  border-top: 1px solid var(--line-soft);
  padding: 9px 14px;
  vertical-align: middle;
}

.batch-table tbody tr:hover {
  background: var(--jade-wash);
}

.batch-table td:nth-child(1) { width: 100px; }
.batch-table td:nth-child(2) { width: 230px; }
.batch-table td:nth-child(3) { width: 130px; }
.batch-table td:nth-child(4) { width: 150px; }
.batch-table td:nth-child(5) { width: 85px; }
.batch-table td:nth-child(6) { color: var(--muted); width: 100px; }

.batch-link {
  align-items: center;
  background: transparent;
  border: 0;
  color: var(--jade-dark);
  cursor: pointer;
  display: inline-flex;
  font-weight: 600;
  gap: 4px;
  padding: 0;
}

.batch-table td small {
  color: var(--muted-light);
  display: block;
  font-size: 9px;
  margin-top: 3px;
}

.mini-progress {
  background: var(--line-soft);
  border-radius: 999px;
  display: inline-block;
  height: 5px;
  margin-right: 6px;
  overflow: hidden;
  vertical-align: middle;
  width: 70px;
}

.mini-progress i {
  background: var(--jade);
  display: block;
  height: 100%;
}

.state-badge {
  border-radius: 999px;
  display: inline-flex;
  font-size: 9px;
  padding: 4px 7px;
  white-space: nowrap;
}

.state-passed { background: var(--jade-soft); color: var(--jade-dark); }
.state-processing,
.state-claimed { background: #e8eff7; color: #375d83; }
.state-ready { background: #f7f0e4; color: var(--amber); }
.state-rework,
.state-blocked { background: var(--cinnabar-soft); color: var(--cinnabar); }
.state-waiting { background: var(--surface-muted); color: var(--muted); }

.empty-table {
  color: var(--muted);
  padding: 28px !important;
  text-align: center;
}

.table-footer {
  align-items: center;
  border-top: 1px solid var(--line-soft);
  color: var(--muted);
  display: flex;
  font-size: 10px;
  justify-content: center;
  min-height: 44px;
}

.table-footer .text-link {
  font-size: 10px;
  margin-left: 7px;
}

.dashboard-footnote {
  align-items: flex-start;
  color: var(--muted);
  display: flex;
  font-size: 10px;
  gap: 7px;
  line-height: 1.5;
  padding: 1px 3px;
}

.dashboard-footnote svg {
  color: var(--jade);
  flex: 0 0 auto;
  margin-top: 1px;
}

@media (max-width: 1080px) {
  .dashboard-overview-row.ready {
    grid-template-columns: 1fr;
  }

  .filter-panel {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .clear-button {
    justify-self: start;
  }

  .chart-grid {
    grid-template-columns: 1fr;
  }

  .alert-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .alert-title {
    grid-column: 1 / -1;
  }

  .alert-strip article:first-of-type {
    border-left: 0;
  }
}

@media (max-width: 760px) {
  .progress-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .header-actions {
    justify-content: space-between;
    width: 100%;
  }

  .summary-grid,
  .scope-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .dashboard-overview-row .summary-grid {
    gap: 12px;
  }

  .dashboard-overview-row .summary-grid article,
  .dashboard-overview-row .summary-grid article:first-child,
  .dashboard-overview-row .summary-grid article:last-child {
    border: 1px solid var(--line);
    border-radius: 6px;
  }

  .scope-metrics article,
  .scope-metrics article:first-child,
  .scope-metrics article:last-child {
    border-left: 0;
    border-top: 1px solid var(--line-soft);
    padding: 11px 4px;
  }

  .scope-metrics article:nth-child(-n + 2) {
    border-top: 0;
  }

  .alert-strip {
    grid-template-columns: 1fr;
  }

  .alert-title,
  .alert-strip article,
  .no-alerts {
    border-left: 0;
    border-top: 1px solid var(--line-soft);
    grid-column: auto;
  }

  .alert-title {
    border-top: 0;
  }
}

@media (max-width: 560px) {
  .filter-panel,
  .summary-grid,
  .scope-metrics {
    grid-template-columns: 1fr;
  }

  .summary-grid article {
    min-height: 88px;
  }

  .scope-metrics article,
  .scope-metrics article:nth-child(-n + 2) {
    border-top: 1px solid var(--line-soft);
  }

  .scope-metrics article:first-child {
    border-top: 0;
  }

  .card-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .range-switch {
    align-self: stretch;
  }

  .range-switch button {
    flex: 1;
  }
}
</style>
