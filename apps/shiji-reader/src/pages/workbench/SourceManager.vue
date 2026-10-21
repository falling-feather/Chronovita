<template>
  <main class="workbench-layout">
    <section class="panel">
      <p class="eyebrow">工作台 / 文献来源</p>
      <h1>资料搜集与版本登记</h1>
      <p class="muted">
        集中维护二十四史影印、文本与注本的版本信息、馆藏号、获取进度和使用条件。后续十四史的双版本计划已经进入此处，可从定版一路追踪到下载校验与 OCR 入库。
      </p>
    </section>

    <section class="workspace-grid">
      <aside class="panel">
        <div class="section-heading">
          <h2>候选来源</h2>
          <span class="counter">{{ filteredSources.length }} / {{ sources.length }}</span>
        </div>
        <div class="form-grid source-filter-grid">
          <label>
            <span>搜索</span>
            <input v-model.trim="sourceQuery" type="search" placeholder="史书、版本或馆藏号" />
          </label>
          <label>
            <span>获取阶段</span>
            <select v-model="stageFilter">
              <option value="">全部</option>
              <option value="ocr_trial">OCR 试验</option>
              <option value="to_collect">待寻找</option>
              <option value="researching">调研中</option>
              <option value="planned">已定版</option>
              <option value="blocked_network">网络支线暂缓</option>
              <option value="cataloged">已建清单</option>
              <option value="collecting">获取中</option>
              <option value="verified">已校验</option>
              <option value="collected">已收集</option>
              <option value="rejected">暂不使用</option>
            </select>
          </label>
        </div>
        <p v-if="loading">正在加载来源候选...</p>
        <p v-else-if="error" class="error-text">{{ error }}</p>
        <p v-else-if="!filteredSources.length" class="muted">没有符合条件的来源。</p>
        <div v-else class="record-list">
          <button
            v-for="source in filteredSources"
            :key="source.id"
            class="record-button"
            :class="{ active: selectedId === source.id }"
            type="button"
            @click="selectedId = source.id"
          >
            <span>{{ source.priority }} · {{ typeLabel(source.source_type) }} · {{ statusLabel(source.status) }}</span>
            <strong>{{ source.title }}</strong>
            <small>{{ source.usage }}</small>
          </button>
        </div>
      </aside>

      <section class="panel inspector-panel" v-if="activeSource">
        <div class="section-heading">
          <div>
            <p class="eyebrow">{{ activeSource.book_id }} · {{ activeSource.file_status }}</p>
            <h2>{{ activeSource.title }}</h2>
          </div>
          <span class="status-badge">{{ statusLabel(activeSource.status) }}</span>
        </div>

        <div class="form-grid">
          <label>
            <span>资料类型</span>
            <input :value="typeLabel(activeSource.source_type)" readonly />
          </label>
          <label>
            <span>优先级</span>
            <input :value="activeSource.priority" readonly />
          </label>
          <label>
            <span>用途</span>
            <input :value="activeSource.usage" readonly />
          </label>
          <label>
            <span>获取阶段</span>
            <input :value="statusLabel(activeSource.status)" readonly />
          </label>
          <label>
            <span>编目审核</span>
            <select v-model="reviewStatus">
              <option value="unreviewed">待审核</option>
              <option value="reviewing">审核中</option>
              <option value="accepted">已接受</option>
              <option value="rejected">已退回</option>
            </select>
          </label>
          <label class="full-field">
            <span>利用条件</span>
            <textarea :value="activeSource.license_status" rows="3" readonly />
          </label>
        </div>

        <article class="note-preview">
          <h3>整理备注</h3>
          <p>{{ activeSource.note }}</p>
        </article>

        <section class="intake-checklist">
          <h3>收到资料时先检查</h3>
          <label v-for="item in checklist" :key="item">
            <input v-model="checkedItems" type="checkbox" :value="item" />
            {{ item }}
          </label>
        </section>

        <label class="textarea-field">
          <span>编目审核备注</span>
          <textarea v-model="draftNote" rows="5" />
        </label>
        <button
          class="primary-action button-reset"
          type="button"
          :disabled="saving"
          @click="saveReview"
        >
          {{ saving ? "正在保存" : "保存审核" }}
        </button>
        <p v-if="saveMessage" class="save-message">{{ saveMessage }}</p>
      </section>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import {
  type SourceCandidate,
  getWorkbenchSources,
  saveWorkbenchSourceReview,
} from "../../services/api";

const sources = ref<SourceCandidate[]>([]);
const selectedId = ref("");
const sourceQuery = ref("");
const stageFilter = ref("");
const reviewStatus = ref<SourceCandidate["review"]["status"]>("unreviewed");
const checkedItems = ref<string[]>([]);
const draftNote = ref("");
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const saveMessage = ref("");

const checklist = [
  "来源链接或馆藏信息明确",
  "版权/授权状态可判断",
  "页码、卷次、篇名完整",
  "影印清晰度适合 OCR",
  "可和另一个版本定位到同一段落",
];

const activeSource = computed(() => {
  return sources.value.find((source) => source.id === selectedId.value) ?? null;
});

const filteredSources = computed(() => {
  const query = sourceQuery.value.toLocaleLowerCase();
  return sources.value.filter((source) => {
    const matchesStage = !stageFilter.value || source.status === stageFilter.value;
    const haystack = [
      source.book_id,
      source.title,
      source.note,
      source.file_status,
    ]
      .join(" ")
      .toLocaleLowerCase();
    return matchesStage && (!query || haystack.includes(query));
  });
});

watch(activeSource, (source) => {
  reviewStatus.value = source?.review.status ?? "unreviewed";
  checkedItems.value = [...(source?.review.checklist ?? [])];
  draftNote.value = source?.review.note ?? "";
  saveMessage.value = "";
});

watch(filteredSources, (filtered) => {
  if (!filtered.some((source) => source.id === selectedId.value)) {
    selectedId.value = filtered[0]?.id ?? "";
  }
});

onMounted(async () => {
  try {
    sources.value = await getWorkbenchSources();
    selectedId.value = sources.value[0]?.id ?? "";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
});

async function saveReview() {
  if (!activeSource.value || saving.value) {
    return;
  }
  saving.value = true;
  saveMessage.value = "";
  try {
    const saved = await saveWorkbenchSourceReview(activeSource.value.id, {
      status: reviewStatus.value,
      checklist: checkedItems.value,
      note: draftNote.value,
      updated_by: "workbench",
    });
    const index = sources.value.findIndex((source) => source.id === saved.id);
    if (index >= 0) {
      sources.value[index] = saved;
    }
    saveMessage.value = "审核状态、检查项和备注已写入来源工作区。";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "保存失败";
  } finally {
    saving.value = false;
  }
}

function typeLabel(type: string) {
  const labels: Record<string, string> = {
    scan: "影印页",
    iiif_scan_pdf: "IIIF 影印 PDF",
    text: "文本",
    annotation: "注释",
  };
  return labels[type] ?? type;
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    ocr_trial: "OCR 试验",
    to_collect: "待寻找",
    researching: "调研中",
    planned: "已定版",
    blocked_network: "网络支线暂缓",
    cataloged: "已建清单",
    collecting: "获取中",
    verified: "已校验",
    collected: "已收集",
    rejected: "暂不使用",
  };
  return labels[status] ?? status;
}
</script>

<style scoped>
.source-filter-grid {
  grid-template-columns: 1fr;
  margin-bottom: 14px;
}
</style>
