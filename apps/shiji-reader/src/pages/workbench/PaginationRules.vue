<template>
  <main class="workbench-layout">
    <section class="panel">
      <p class="eyebrow">工作台 / 分段分页</p>
      <h1>阅读模式与分页规则</h1>
      <p class="muted">
        分段用于注释、异文和实体锚定；分页用于模拟书页式阅读和后续影印图像对齐。当前先用样章数据验证两种模式的接口与页面结构。
      </p>
    </section>

    <section class="workspace-grid">
      <aside class="panel">
        <h2>阅读模式</h2>
        <div class="mode-list">
          <button
            v-for="mode in framework?.reading_modes ?? []"
            :key="mode.id"
            class="mode-option"
            :class="{ active: activeMode === mode.id }"
            type="button"
            @click="activeMode = mode.id"
          >
            <span>{{ mode.name }}</span>
            <small>{{ mode.description }}</small>
          </button>
        </div>

        <div class="rule-stack">
          <article>
            <h3>段落规则</h3>
            <p>以可解释的语义段为最小阅读单元，保存 start/end 偏移，供注释、高亮和异文共用。</p>
          </article>
          <article>
            <h3>分页规则</h3>
            <p>以 page_id 管理虚拟页，未来可和影印图页、OCR 版面坐标、页码索引绑定。</p>
          </article>
          <article>
            <h3>排序规则</h3>
            <p>书籍、卷、篇、段落统一使用 sort_order，避免后续跨版本比较时丢失原始次序。</p>
          </article>
        </div>
      </aside>

      <section class="panel inspector-panel">
        <div class="section-heading">
          <div>
            <p class="eyebrow">样章预览</p>
            <h2>{{ payload?.passage.title ?? "等待加载" }}</h2>
          </div>
          <RouterLink
            class="secondary-action"
            :to="{ name: 'reader-passage', params: { passageId }, query: { mode: activeMode } }"
          >
            打开阅读页
          </RouterLink>
        </div>

        <p v-if="loading">正在加载分页预览...</p>
        <p v-else-if="error" class="error-text">{{ error }}</p>
        <div v-else-if="payload" class="page-preview">
          <div class="reading-meta">
            <span>当前模式：{{ activeMode === "segment" ? "分段" : "分页" }}</span>
            <span>页码：{{ payload.reading.page.page_no }} / {{ payload.reading.page.total_pages }}</span>
            <span>段落数：{{ payload.reading.segments.length }}</span>
          </div>

          <article class="page-sheet">
            <p>{{ payload.text }}</p>
          </article>

          <div class="segment-list expanded">
            <button
              v-for="segment in payload.reading.segments"
              :key="segment.id"
              type="button"
              :class="{ active: selectedSegmentId === segment.id }"
              @click="selectedSegmentId = segment.id"
            >
              <strong>{{ segment.label }}</strong>
              <small>{{ segment.start }} - {{ segment.end }}</small>
            </button>
          </div>
        </div>
      </section>
    </section>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue";

import {
  type PassagePayload,
  type WorkbenchFramework,
  getPassage,
  getWorkbenchFramework,
} from "../../services/api";

const passageId = "shiji-xiangyu-0001";
const activeMode = ref<"segment" | "page">("segment");
const selectedSegmentId = ref("");
const framework = ref<WorkbenchFramework | null>(null);
const payload = ref<PassagePayload | null>(null);
const loading = ref(true);
const error = ref("");

onMounted(async () => {
  try {
    framework.value = await getWorkbenchFramework();
    await loadPreview();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
});

watch(activeMode, async () => {
  await loadPreview();
});

async function loadPreview() {
  loading.value = true;
  error.value = "";
  try {
    payload.value = await getPassage(passageId, activeMode.value);
    selectedSegmentId.value = payload.value.reading.segments[0]?.id ?? "";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
}
</script>
