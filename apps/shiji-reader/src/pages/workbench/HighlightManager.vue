<template>
  <main class="workbench-layout">
    <section class="panel">
      <p class="eyebrow">工作台 / 文本高亮</p>
      <h1>高亮规则</h1>
      <p class="muted">
        高亮层负责把人物、地点、事件、注释、异文等内容投射回正文。这里先搭规则浏览、类型筛选和阅读页联动。
      </p>
    </section>

    <section class="panel">
      <div class="section-heading">
        <h2>类型筛选</h2>
        <span class="counter">{{ visibleHighlights.length }} / {{ highlights.length }}</span>
      </div>
      <div class="filter-grid wide">
        <label v-for="type in highlightTypes" :key="type">
          <input v-model="enabledTypes" type="checkbox" :value="type" />
          {{ typeLabel(type) }}
        </label>
      </div>
    </section>

    <section class="workspace-grid">
      <aside class="panel">
        <h2>高亮锚点</h2>
        <p v-if="loading">正在加载高亮...</p>
        <p v-else-if="error" class="error-text">{{ error }}</p>
        <div v-else class="record-list">
          <button
            v-for="highlight in visibleHighlights"
            :key="highlight.id"
            class="record-button"
            :class="{ active: selectedId === highlight.id }"
            type="button"
            @click="selectedId = highlight.id"
          >
            <span>
              <i class="color-dot" :class="`highlight-${highlight.color}`" />
              {{ typeLabel(highlight.type) }} · {{ highlight.start }}-{{ highlight.end }}
            </span>
            <strong>{{ highlight.text }}</strong>
            <small>{{ highlight.passage_id }}</small>
          </button>
        </div>
      </aside>

      <section class="panel inspector-panel" v-if="activeHighlight">
        <div class="section-heading">
          <div>
            <p class="eyebrow">{{ typeLabel(activeHighlight.type) }}</p>
            <h2>{{ activeHighlight.text }}</h2>
          </div>
          <RouterLink class="secondary-action" :to="`/reader/${activeHighlight.passage_id}`">
            阅读页预览
          </RouterLink>
        </div>

        <div class="highlight-preview-line">
          <span>前文</span>
          <button
            class="highlight-token"
            :class="`highlight-${activeHighlight.color}`"
            type="button"
          >
            {{ activeHighlight.text }}
            <small>{{ activeHighlight.label }}</small>
          </button>
          <span>后文</span>
        </div>

        <div class="form-grid">
          <label>
            <span>目标 ID</span>
            <input :value="activeHighlight.target_id" readonly />
          </label>
          <label>
            <span>颜色层</span>
            <input :value="activeHighlight.color" readonly />
          </label>
          <label>
            <span>所属段落</span>
            <input :value="activeHighlight.passage_id" readonly />
          </label>
          <label>
            <span>锚点范围</span>
            <input :value="`${activeHighlight.start} - ${activeHighlight.end}`" readonly />
          </label>
        </div>

        <article class="note-preview">
          <h3>后续写回接口</h3>
          <p>
            正式接入内容后，高亮应由实体识别、注释锚点、异文范围和人工修订共同生成，并保留人工覆盖优先级。
          </p>
        </article>
      </section>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { type TextHighlight, getWorkbenchHighlights } from "../../services/api";

const highlights = ref<TextHighlight[]>([]);
const selectedId = ref("");
const enabledTypes = ref(["person", "place", "annotation", "variant", "event"]);
const loading = ref(true);
const error = ref("");

const highlightTypes = computed(() => {
  return [...new Set(highlights.value.map((item) => item.type))];
});

const visibleHighlights = computed(() => {
  return highlights.value.filter((item) => enabledTypes.value.includes(item.type));
});

const activeHighlight = computed(() => {
  return visibleHighlights.value.find((item) => item.id === selectedId.value) ?? visibleHighlights.value[0] ?? null;
});

onMounted(async () => {
  try {
    highlights.value = await getWorkbenchHighlights();
    selectedId.value = highlights.value[0]?.id ?? "";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
});

function typeLabel(type: string) {
  const labels: Record<string, string> = {
    person: "人物",
    place: "地点",
    annotation: "注释",
    variant: "异文",
    event: "事件",
  };
  return labels[type] ?? type;
}
</script>
