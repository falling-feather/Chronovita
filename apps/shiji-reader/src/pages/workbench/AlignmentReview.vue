<template>
  <main class="workbench-layout">
    <section class="panel">
      <div class="section-heading">
        <div>
          <p class="eyebrow">工作台 / 版本对齐</p>
          <h1>跨版本页候选</h1>
        </div>
        <span class="status-badge">{{ activeManifest?.candidates.length ?? 0 }} 条</span>
      </div>
      <div class="metric-row" v-if="activeManifest">
        <span>互为最佳 {{ activeManifest.summary.mutual_best }}</span>
        <span>边界风险 {{ activeManifest.summary.boundary_risk_candidates }}</span>
        <span>基准页 {{ activeManifest.summary.base_pages }}</span>
        <span>对照页 {{ activeManifest.summary.compare_pages }}</span>
      </div>
    </section>

    <section class="alignment-layout">
      <aside class="panel">
        <div class="form-grid">
          <label>
            <span>候选清单</span>
            <select v-model="manifestKey" @change="loadManifest">
              <option v-for="manifest in manifests" :key="manifest.key" :value="manifest.key">
                {{ manifest.book_id }} · {{ manifest.base_version_id }}
              </option>
            </select>
          </label>
          <label>
            <span>审核状态</span>
            <select v-model="statusFilter">
              <option value="">全部</option>
              <option value="auto">机器候选</option>
              <option value="reviewing">复核中</option>
              <option value="segmentation_required">需分段</option>
              <option value="approved">已通过</option>
              <option value="rejected">已退回</option>
            </select>
          </label>
          <label>
            <span>候选类型</span>
            <select v-model="priorityFilter">
              <option value="">全部</option>
              <option value="high">高优先</option>
              <option value="normal">常规</option>
              <option value="segmentation_required">需分段</option>
            </select>
          </label>
        </div>

        <p v-if="loading">正在加载候选...</p>
        <p v-else-if="error" class="error-text">{{ error }}</p>
        <div v-else class="record-list alignment-list">
          <button
            v-for="candidate in filteredCandidates"
            :key="candidate.id"
            class="record-button"
            :class="{ active: activeCandidate?.id === candidate.id }"
            type="button"
            @click="selectCandidate(candidate)"
          >
            <span>
              {{ reviewStatusLabel(candidate.review.status) }} ·
              {{ priorityLabel(candidate.review_priority) }}
            </span>
            <strong>PDF {{ candidate.base_pdf_page }} ↔ {{ candidate.compare_pdf_page }}</strong>
            <small>得分 {{ formatScore(candidate.score) }}</small>
          </button>
        </div>
      </aside>

      <section class="panel alignment-inspector" v-if="activeCandidate">
        <div class="section-heading">
          <div>
            <p class="eyebrow">{{ activeCandidate.book_id }}</p>
            <h2>PDF {{ activeCandidate.base_pdf_page }} ↔ {{ activeCandidate.compare_pdf_page }}</h2>
          </div>
          <span class="status-badge">
            {{ reviewStatusLabel(activeCandidate.review.status) }}
          </span>
        </div>

        <div class="alignment-pair">
          <section>
            <p class="eyebrow">基准版本</p>
            <strong>{{ activeCandidate.base_version_id }}</strong>
            <span>{{ activeCandidate.base_source_file_label }}</span>
            <RouterLink :to="`/reader/scan/${activeCandidate.base_page_id}`">
              打开 PDF 第 {{ activeCandidate.base_pdf_page }} 页
            </RouterLink>
          </section>
          <section>
            <p class="eyebrow">对照版本</p>
            <strong>{{ activeCandidate.compare_version_id }}</strong>
            <span>{{ activeCandidate.compare_source_file_label }}</span>
            <RouterLink :to="`/reader/scan/${activeCandidate.compare_page_id}`">
              打开 PDF 第 {{ activeCandidate.compare_pdf_page }} 页
            </RouterLink>
          </section>
        </div>

        <div class="metric-row alignment-metrics">
          <span>综合 {{ formatScore(activeCandidate.score) }}</span>
          <span>序列 {{ formatScore(activeCandidate.metrics.sequence_ratio) }}</span>
          <span>包含 {{ formatScore(activeCandidate.metrics.containment) }}</span>
          <span>领先 {{ formatScore(activeCandidate.top_margin) }}</span>
          <span>{{ activeCandidate.mutual_best ? "互为最佳" : "单向候选" }}</span>
        </div>

        <div class="boundary-band" v-if="activeCandidate.boundary_risk">
          <strong>需要段落级分割</strong>
          <span v-for="reason in activeCandidate.boundary_reasons" :key="reason">
            {{ boundaryReasonLabel(reason) }}
          </span>
        </div>

        <div class="evidence-grid">
          <section>
            <p class="eyebrow">基准证据</p>
            <p>{{ activeCandidate.evidence.base_excerpt }}</p>
          </section>
          <section>
            <p class="eyebrow">对照证据</p>
            <p>{{ activeCandidate.evidence.compare_excerpt }}</p>
          </section>
        </div>

        <div class="form-grid review-form">
          <label>
            <span>审核状态</span>
            <select v-model="reviewStatus">
              <option value="auto">机器候选</option>
              <option value="reviewing">复核中</option>
              <option value="segmentation_required">需分段</option>
              <option value="approved" :disabled="activeCandidate.boundary_risk">
                已通过
              </option>
              <option value="rejected">已退回</option>
            </select>
          </label>
          <label class="toggle-field">
            <input v-model="visualChecked" type="checkbox" />
            <span>图像已核验</span>
          </label>
          <label class="wide-field">
            <span>审核备注</span>
            <textarea v-model="reviewNote" rows="4"></textarea>
          </label>
        </div>
        <div class="action-row">
          <button
            class="primary-action button-reset"
            type="button"
            :disabled="saving"
            @click="saveReview"
          >
            {{ saving ? "保存中..." : "保存审核" }}
          </button>
          <span v-if="saveMessage" class="save-message">{{ saveMessage }}</span>
          <span v-if="activeCandidate.review.revisions.length">
            {{ activeCandidate.review.revisions.length }} 次修订
          </span>
        </div>
      </section>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import {
  type AlignmentCandidate,
  type AlignmentManifest,
  type AlignmentManifestSummary,
  getAlignmentManifest,
  getAlignmentManifests,
  saveAlignmentReview,
} from "../../services/api";

const manifests = ref<AlignmentManifestSummary[]>([]);
const activeManifest = ref<AlignmentManifest | null>(null);
const activeCandidate = ref<AlignmentCandidate | null>(null);
const manifestKey = ref("");
const statusFilter = ref("");
const priorityFilter = ref("");
const reviewStatus = ref("auto");
const reviewNote = ref("");
const visualChecked = ref(false);
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const saveMessage = ref("");

const filteredCandidates = computed(() => {
  const candidates = activeManifest.value?.candidates ?? [];
  return candidates.filter(
    (candidate) =>
      (!statusFilter.value || candidate.review.status === statusFilter.value) &&
      (!priorityFilter.value || candidate.review_priority === priorityFilter.value),
  );
});

onMounted(async () => {
  try {
    manifests.value = await getAlignmentManifests();
    if (manifests.value[0]) {
      manifestKey.value = manifests.value[0].key;
      await loadManifest();
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
});

async function loadManifest() {
  if (!manifestKey.value) {
    activeManifest.value = null;
    activeCandidate.value = null;
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    activeManifest.value = await getAlignmentManifest(manifestKey.value);
    const first = activeManifest.value.candidates[0] ?? null;
    selectCandidate(first);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "候选清单加载失败";
  } finally {
    loading.value = false;
  }
}

function selectCandidate(candidate: AlignmentCandidate | null) {
  activeCandidate.value = candidate;
  reviewStatus.value = candidate?.review.status ?? "auto";
  reviewNote.value = candidate?.review.note ?? "";
  visualChecked.value = candidate?.review.visual_checked ?? false;
  saveMessage.value = "";
}

async function saveReview() {
  if (!activeCandidate.value || saving.value) {
    return;
  }
  saving.value = true;
  error.value = "";
  saveMessage.value = "";
  try {
    const review = await saveAlignmentReview(
      manifestKey.value,
      activeCandidate.value.id,
      {
        status: reviewStatus.value,
        note: reviewNote.value,
        visual_checked: visualChecked.value,
        editor: "alignment-workbench",
      },
    );
    activeCandidate.value = { ...activeCandidate.value, review };
    if (activeManifest.value) {
      activeManifest.value.candidates = activeManifest.value.candidates.map((candidate) =>
        candidate.id === activeCandidate.value?.id
          ? (activeCandidate.value as AlignmentCandidate)
          : candidate,
      );
    }
    saveMessage.value = "审核已保存。";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "审核保存失败";
  } finally {
    saving.value = false;
  }
}

function formatScore(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function reviewStatusLabel(status: string) {
  return {
    auto: "机器候选",
    reviewing: "复核中",
    segmentation_required: "需分段",
    approved: "已通过",
    rejected: "已退回",
  }[status] ?? status;
}

function priorityLabel(priority: string) {
  return {
    high: "高优先",
    normal: "常规",
    segmentation_required: "需分段",
  }[priority] ?? priority;
}

function boundaryReasonLabel(reason: string) {
  return {
    base_page_spans_compare_previous: "基准页跨对照前页",
    base_page_spans_compare_next: "基准页跨对照后页",
    compare_page_spans_base_previous: "对照页跨基准前页",
    compare_page_spans_base_next: "对照页跨基准后页",
    multiple_base_pages_share_top_compare_page: "多个基准页指向同一对照页",
  }[reason] ?? reason;
}
</script>

<style scoped>
.alignment-layout {
  display: grid;
  gap: 18px;
  grid-template-columns: minmax(280px, 0.34fr) minmax(0, 1fr);
}

.alignment-list {
  margin-top: 16px;
  max-height: 72vh;
  overflow: auto;
}

.alignment-inspector {
  align-self: start;
}

.alignment-pair,
.evidence-grid {
  display: grid;
  gap: 18px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-top: 18px;
}

.alignment-pair section,
.evidence-grid section {
  border-left: 3px solid #9c3027;
  display: grid;
  gap: 7px;
  padding-left: 14px;
}

.alignment-pair span {
  color: var(--muted);
}

.alignment-metrics {
  margin-top: 18px;
}

.boundary-band {
  background: #f4e5d0;
  border-left: 4px solid #a45b20;
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  margin-top: 18px;
  padding: 12px 14px;
}

.evidence-grid p:last-child {
  line-height: 1.9;
  margin: 0;
  overflow-wrap: anywhere;
}

.review-form {
  grid-template-columns: minmax(180px, 0.35fr) minmax(180px, 0.35fr);
  margin-top: 22px;
}

.review-form .wide-field {
  grid-column: 1 / -1;
}

@media (max-width: 900px) {
  .alignment-layout,
  .alignment-pair,
  .evidence-grid,
  .review-form {
    grid-template-columns: 1fr;
  }

  .review-form .wide-field {
    grid-column: auto;
  }
}
</style>
