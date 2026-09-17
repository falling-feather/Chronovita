<template>
  <main class="workbench-layout">
    <section class="panel">
      <div class="section-heading">
        <div>
          <p class="eyebrow">工作台 / 版本对勘</p>
          <h1>异文审核</h1>
        </div>
        <div class="variant-actions">
          <label>
            <span>状态</span>
            <select v-model="statusFilter" @change="loadVariants">
              <option value="">当前候选</option>
              <option value="auto">待审核</option>
              <option value="reviewing">复核中</option>
              <option value="approved">已通过</option>
              <option value="rejected">已驳回</option>
              <option value="superseded">已失效</option>
            </select>
          </label>
          <button
            class="secondary-action button-reset"
            type="button"
            :disabled="loading"
            @click="loadVariants"
          >
            刷新
          </button>
        </div>
      </div>
      <div class="metric-row">
        <span>候选 {{ variants.length }}</span>
        <span>真实映射 {{ realVariantCount }}</span>
        <span>待审核 {{ pendingCount }}</span>
        <span>已通过 {{ approvedCount }}</span>
      </div>
    </section>

    <section class="panel">
      <p v-if="loading">正在加载异文候选...</p>
      <p v-else-if="error" class="error-text">{{ error }}</p>
      <p v-else-if="!variants.length" class="muted">当前筛选条件下没有异文候选。</p>
      <div v-else class="variant-table">
        <article v-for="variant in variants" :key="variant.id" class="variant-row">
          <div class="variant-heading">
            <div>
              <p class="eyebrow">
                {{ variantTypeLabel(variant.variant_type) }} ·
                {{ statusLabel(variant.status) }}
              </p>
              <h2>{{ variant.canonical_unit_id || variant.passage_id }}</h2>
            </div>
            <div class="confidence">{{ Math.round(variant.confidence * 100) }}%</div>
          </div>

          <div class="variant-comparison">
            <section>
              <span>{{ variant.base_version_label || "基准版本" }}</span>
              <strong>{{ variant.base_text || "∅" }}</strong>
              <small v-if="variant.base_text_source">
                {{ textSourceLabel(variant.base_text_source) }}
              </small>
              <RouterLink
                v-if="variant.base_page_id"
                class="text-link"
                :to="`/reader/scan/${variant.base_page_id}`"
              >
                查看基准书影
              </RouterLink>
            </section>
            <section>
              <span>{{ variant.compare_version_label || "对照版本" }}</span>
              <strong>{{ variant.compare_text || "∅" }}</strong>
              <small v-if="variant.compare_text_source">
                {{ textSourceLabel(variant.compare_text_source) }}
              </small>
              <RouterLink
                v-if="variant.compare_page_id"
                class="text-link"
                :to="`/reader/scan/${variant.compare_page_id}`"
              >
                查看对照书影
              </RouterLink>
            </section>
          </div>

          <div class="variant-review-form" v-if="variant.source_type === 'ocr_mapping'">
            <label>
              <span>审核状态</span>
              <select v-model="reviewDrafts[variant.id].status">
                <option value="reviewing">复核中</option>
                <option value="approved">通过</option>
                <option value="rejected">驳回</option>
              </select>
            </label>
            <label class="note-field">
              <span>审核备注</span>
              <textarea v-model="reviewDrafts[variant.id].note" rows="2"></textarea>
            </label>
            <button
              class="primary-action button-reset"
              type="button"
              :disabled="savingId === variant.id"
              @click="saveReview(variant)"
            >
              {{ savingId === variant.id ? "保存中..." : "保存审核" }}
            </button>
            <span v-if="saveMessages[variant.id]" class="save-message">
              {{ saveMessages[variant.id] }}
            </span>
          </div>
          <p v-else class="muted sample-note">{{ variant.note }}</p>
        </article>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import {
  type VariantReading,
  getWorkbenchVariants,
  reviewWorkbenchVariant,
} from "../../services/api";

interface ReviewDraft {
  status: string;
  note: string;
}

const variants = ref<VariantReading[]>([]);
const reviewDrafts = ref<Record<string, ReviewDraft>>({});
const saveMessages = ref<Record<string, string>>({});
const statusFilter = ref("");
const savingId = ref("");
const loading = ref(true);
const error = ref("");

const realVariantCount = computed(
  () => variants.value.filter((variant) => variant.source_type === "ocr_mapping").length,
);
const pendingCount = computed(
  () => variants.value.filter((variant) => variant.status === "auto").length,
);
const approvedCount = computed(
  () => variants.value.filter((variant) => variant.status === "approved").length,
);

onMounted(loadVariants);

async function loadVariants() {
  loading.value = true;
  error.value = "";
  try {
    variants.value = await getWorkbenchVariants({
      status: statusFilter.value || undefined,
    });
    reviewDrafts.value = Object.fromEntries(
      variants.value.map((variant) => [
        variant.id,
        {
          status: reviewableStatus(variant.status),
          note: variant.note || "",
        },
      ]),
    );
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
}

async function saveReview(variant: VariantReading) {
  const draft = reviewDrafts.value[variant.id];
  if (!draft || savingId.value) {
    return;
  }
  savingId.value = variant.id;
  saveMessages.value[variant.id] = "";
  try {
    const saved = await reviewWorkbenchVariant(variant.id, {
      status: draft.status,
      note: draft.note,
      editor: "workbench",
    });
    const index = variants.value.findIndex((item) => item.id === variant.id);
    if (index >= 0) {
      variants.value[index] = { ...saved, source_type: "ocr_mapping" };
    }
    saveMessages.value[variant.id] = "审核已保存并写入修订记录。";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "审核保存失败";
  } finally {
    savingId.value = "";
  }
}

function reviewableStatus(status: string) {
  return ["reviewing", "approved", "rejected"].includes(status)
    ? status
    : "reviewing";
}

function statusLabel(status: string) {
  return {
    auto: "待审核",
    reviewing: "复核中",
    approved: "已通过",
    rejected: "已驳回",
    superseded: "已失效",
  }[status] ?? status;
}

function variantTypeLabel(type: string) {
  return {
    substitution: "字词替换",
    omission_in_compare: "对照本脱文",
    addition_in_compare: "对照本增文",
    word_diff: "字词差异",
    punctuation_diff: "句读差异",
  }[type] ?? type;
}

function textSourceLabel(source: string) {
  return source === "corrected" ? "人工校定层" : "OCR 忠实转录层";
}
</script>

<style scoped>
.variant-actions,
.variant-actions label {
  align-items: center;
  display: flex;
  gap: 8px;
}

.variant-actions label {
  color: var(--muted);
  font-family: sans-serif;
  font-size: 12px;
}

.variant-table {
  display: grid;
}

.variant-row {
  border-top: 1px solid var(--line);
  display: grid;
  gap: 16px;
  padding: 20px 0;
}

.variant-row:first-child {
  border-top: 0;
  padding-top: 0;
}

.variant-heading {
  align-items: start;
  display: flex;
  gap: 16px;
  justify-content: space-between;
}

.variant-heading h2,
.variant-heading p {
  margin: 0;
}

.confidence {
  color: var(--jade);
  font-family: sans-serif;
  font-size: 18px;
  font-weight: 700;
}

.variant-comparison {
  display: grid;
  gap: 18px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.variant-comparison section {
  border-left: 3px solid var(--line-strong);
  display: grid;
  gap: 8px;
  padding-left: 12px;
}

.variant-comparison span,
.variant-comparison small {
  color: var(--muted);
  font-family: sans-serif;
  font-size: 12px;
}

.variant-comparison strong {
  font-size: 24px;
  font-weight: 600;
}

.variant-review-form {
  align-items: end;
  display: grid;
  gap: 12px;
  grid-template-columns: 150px minmax(260px, 1fr) auto;
}

.variant-review-form label {
  display: grid;
  gap: 6px;
}

.variant-review-form label > span {
  color: var(--muted);
  font-family: sans-serif;
  font-size: 12px;
}

.variant-review-form textarea {
  min-height: 68px;
}

.variant-review-form .save-message {
  grid-column: 1 / -1;
}

.sample-note {
  margin: 0;
}

@media (max-width: 760px) {
  .section-heading,
  .variant-actions {
    align-items: stretch;
  }

  .variant-actions {
    flex-direction: column;
  }

  .variant-actions label,
  .variant-actions select,
  .variant-actions button {
    width: 100%;
  }

  .variant-comparison,
  .variant-review-form {
    grid-template-columns: 1fr;
  }
}
</style>
