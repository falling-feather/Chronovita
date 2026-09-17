<template>
  <main class="workbench-layout">
    <section class="panel">
      <p class="eyebrow">工作台 / 文本注释</p>
      <h1>注释管理</h1>
      <p class="muted">
        维护字词、句段、地点和人物注释的锚点。当前读取样章示例数据，先验证注释定位、审核状态和阅读页展示关系。
      </p>
    </section>

    <section class="workspace-grid">
      <aside class="panel">
        <div class="section-heading">
          <h2>注释条目</h2>
          <span class="counter">{{ annotations.length }}</span>
        </div>
        <p v-if="loading">正在加载注释...</p>
        <p v-else-if="error" class="error-text">{{ error }}</p>
        <div v-else class="record-list">
          <button
            v-for="annotation in annotations"
            :key="annotation.id"
            class="record-button"
            :class="{ active: selectedId === annotation.id }"
            type="button"
            @click="selectAnnotation(annotation)"
          >
            <span>{{ annotation.annotation_type ?? "note" }} · {{ localStatus(annotation) }}</span>
            <strong>{{ annotation.anchor_text }}</strong>
            <small>{{ annotation.passage_id }}</small>
          </button>
        </div>
      </aside>

      <section class="panel inspector-panel" v-if="activeAnnotation">
        <div class="section-heading">
          <div>
            <p class="eyebrow">{{ activeAnnotation.passage_id }}</p>
            <h2>{{ activeAnnotation.anchor_text }}</h2>
          </div>
          <RouterLink class="secondary-action" :to="`/reader/${activeAnnotation.passage_id}`">
            定位阅读页
          </RouterLink>
        </div>

        <div class="form-grid">
          <label>
            <span>锚点范围</span>
            <input :value="rangeLabel(activeAnnotation.anchor_range)" readonly />
          </label>
          <label>
            <span>注释类型</span>
            <input :value="activeAnnotation.annotation_type ?? 'general_note'" readonly />
          </label>
          <label>
            <span>来源</span>
            <input :value="activeAnnotation.source" readonly />
          </label>
          <label>
            <span>审核状态</span>
            <select v-model="selectedStatus" @change="applyStatus(selectedStatus)">
              <option value="draft">草稿</option>
              <option value="reviewing">审核中</option>
              <option value="approved">已通过</option>
              <option value="rejected">退回</option>
            </select>
          </label>
        </div>

        <article class="note-preview">
          <h3>注释正文</h3>
          <p>{{ activeAnnotation.text }}</p>
        </article>

        <label class="textarea-field">
          <span>校勘备注</span>
          <textarea v-model="reviewNote" rows="5" />
        </label>

        <div class="action-row compact">
          <button class="primary-action button-reset" type="button" @click="applyStatus('approved')">
            标记通过
          </button>
          <button class="secondary-action button-reset" type="button" @click="applyStatus('reviewing')">
            放入审核
          </button>
        </div>
      </section>

      <section class="panel inspector-panel" v-else>
        <h2>暂无注释</h2>
        <p class="muted">接入正式文本后，这里会列出所有待审核注释锚点。</p>
      </section>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import { type Annotation, getWorkbenchAnnotations } from "../../services/api";

type WorkbenchAnnotation = Annotation & { passage_id: string };

const annotations = ref<WorkbenchAnnotation[]>([]);
const selectedId = ref("");
const selectedStatus = ref("draft");
const reviewNote = ref("用于记录人工审核意见，后续接入写回接口。");
const statusDraft = reactive<Record<string, string>>({});
const loading = ref(true);
const error = ref("");

const activeAnnotation = computed(() => {
  return annotations.value.find((item) => item.id === selectedId.value) ?? null;
});

onMounted(async () => {
  try {
    annotations.value = await getWorkbenchAnnotations();
    if (annotations.value.length) {
      selectAnnotation(annotations.value[0]);
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
});

function selectAnnotation(annotation: WorkbenchAnnotation) {
  selectedId.value = annotation.id;
  selectedStatus.value = localStatus(annotation);
}

function localStatus(annotation: WorkbenchAnnotation) {
  return statusDraft[annotation.id] ?? annotation.status;
}

function applyStatus(status: string) {
  if (!activeAnnotation.value) {
    return;
  }
  statusDraft[activeAnnotation.value.id] = status;
  selectedStatus.value = status;
}

function rangeLabel(range?: [number, number]) {
  return range ? `${range[0]} - ${range[1]}` : "未绑定";
}
</script>
