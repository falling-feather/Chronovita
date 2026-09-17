<template>
  <main class="workbench-layout workbench-home">
    <header class="workbench-page-header">
      <div>
        <p class="eyebrow">开发端</p>
        <h1>工作台</h1>
      </div>
      <RouterLink class="secondary-action" to="/books/shiji">
        <BookOpenText :size="16" aria-hidden="true" />
        查看《史记》
      </RouterLink>
    </header>

    <section class="summary-strip" aria-label="工作台统计">
      <article>
        <span>文献来源</span>
        <strong>{{ summary?.sources.total ?? "—" }}</strong>
      </article>
      <article>
        <span>OCR 页面</span>
        <strong>{{ formatMetric(summary?.ocr.workspace_pages) }}</strong>
      </article>
      <article>
        <span>对齐候选</span>
        <strong>{{ formatMetric(summary?.alignments.candidates) }}</strong>
      </article>
      <article>
        <span>异文待审</span>
        <strong>{{ formatMetric(summary?.variants.reviewing) }}</strong>
      </article>
      <article>
        <span>文本注释</span>
        <strong>{{ formatMetric(summary?.annotations.total) }}</strong>
      </article>
    </section>

    <section v-if="!error" class="next-actions" aria-labelledby="next-actions-title">
      <div class="next-actions-heading">
        <h2 id="next-actions-title">当前行动</h2>
        <span v-if="!loading">{{ nextActions.length }} 项</span>
      </div>

      <p v-if="loading" class="library-state">正在加载...</p>
      <template v-else>
        <ol v-if="nextActions.length" class="next-action-list">
          <li
            v-for="(action, index) in nextActions"
            :key="`${index}-${action}`"
            class="next-action-row"
          >
            <span class="next-action-index" aria-hidden="true">{{ index + 1 }}</span>
            <span class="next-action-text">{{ action }}</span>
          </li>
        </ol>
        <p v-else class="library-state">当前没有待处理行动。</p>
      </template>
    </section>

    <section class="module-directory" aria-labelledby="module-title">
      <div class="module-directory-heading">
        <h2 id="module-title">功能模块</h2>
        <span>{{ framework?.modules.length ?? 0 }} 项</span>
      </div>

      <p v-if="loading" class="library-state">正在加载...</p>
      <p v-else-if="error" class="error-text library-state">{{ error }}</p>
      <div v-else class="module-list">
        <RouterLink
          v-for="module in framework?.modules"
          :key="module.id"
          class="module-row"
          :to="moduleLink(module.id)"
        >
          <span class="module-icon" aria-hidden="true">
            <component :is="moduleIcon(module.id)" :size="18" />
          </span>
          <strong>{{ module.name }}</strong>
          <span class="module-value">{{ moduleMetric(module.id) }}</span>
          <span class="module-status">{{ statusLabel(module.status) }}</span>
          <ChevronRight :size="18" aria-hidden="true" />
        </RouterLink>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, type Component } from "vue";
import {
  BookOpenText,
  ChevronRight,
  Database,
  GitCompareArrows,
  Highlighter,
  MessageSquareText,
  PanelsTopLeft,
  ScanText,
} from "@lucide/vue";

import {
  type WorkbenchFramework,
  type WorkbenchSummary,
  getWorkbenchFramework,
  getWorkbenchSummary,
} from "../../services/api";

const summary = ref<WorkbenchSummary | null>(null);
const framework = ref<WorkbenchFramework | null>(null);
const loading = ref(true);
const error = ref("");
const nextActions = computed(() => (summary.value?.next_actions ?? []).slice(0, 4));

const moduleIcons: Record<string, Component> = {
  sources: Database,
  ocr: ScanText,
  alignments: GitCompareArrows,
  variants: GitCompareArrows,
  annotations: MessageSquareText,
  highlights: Highlighter,
  passages: PanelsTopLeft,
};

onMounted(async () => {
  try {
    const [summaryPayload, frameworkPayload] = await Promise.all([
      getWorkbenchSummary(),
      getWorkbenchFramework(),
    ]);
    summary.value = summaryPayload;
    framework.value = frameworkPayload;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
});

function moduleLink(moduleId: string) {
  const links: Record<string, string> = {
    sources: "/workbench/sources",
    annotations: "/workbench/annotations",
    highlights: "/workbench/highlights",
    passages: "/workbench/pagination",
    variants: "/workbench/variants",
    alignments: "/workbench/alignments",
    ocr: "/workbench/ocr",
  };
  return links[moduleId] ?? "/workbench";
}

function moduleIcon(moduleId: string) {
  return moduleIcons[moduleId] ?? PanelsTopLeft;
}

function moduleMetric(moduleId: string) {
  if (!summary.value) {
    return "—";
  }
  const metrics: Record<string, string | number | undefined> = {
    sources: summary.value.sources.total,
    ocr: summary.value.ocr.workspace_pages,
    alignments: summary.value.alignments.candidates,
    variants: summary.value.variants.total,
    annotations: summary.value.annotations.total,
    highlights: summary.value.highlights.total,
    passages: summary.value.pagination.modes,
  };
  return formatMetric(metrics[moduleId]);
}

function formatMetric(value: string | number | undefined) {
  return typeof value === "number" ? new Intl.NumberFormat("zh-CN").format(value) : (value ?? "—");
}

function statusLabel(status: string) {
  return {
    ready: "可用",
    prototype: "原型",
    planned: "计划中",
    active: "进行中",
  }[status] ?? status;
}
</script>

<style scoped>
.workbench-home {
  max-width: 1240px;
}

.summary-strip {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 6px;
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.summary-strip article {
  border-right: 1px solid var(--line);
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 18px 20px;
}

.summary-strip article:last-child {
  border-right: 0;
}

.summary-strip span {
  color: var(--muted);
  font-size: 12px;
}

.summary-strip strong {
  font-size: 25px;
  line-height: 1;
}

.next-actions {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 6px;
  min-height: 116px;
}

.next-actions-heading {
  align-items: center;
  border-bottom: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  min-height: 58px;
  padding: 0 18px;
}

.next-actions-heading h2 {
  font-size: 17px;
  margin: 0;
}

.next-actions-heading span {
  color: var(--muted);
  font-size: 12px;
}

.next-action-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.next-action-row {
  align-items: start;
  border-bottom: 1px solid var(--line-soft);
  display: grid;
  gap: 12px;
  grid-template-columns: 24px minmax(0, 1fr);
  min-height: 56px;
  padding: 14px 18px;
}

.next-action-row:last-child {
  border-bottom: 0;
}

.next-action-index {
  color: var(--muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  line-height: 20px;
  padding-top: 1px;
  text-align: center;
}

.next-action-text {
  color: var(--ink-secondary);
  font-size: 14px;
  line-height: 1.45;
  min-width: 0;
  overflow-wrap: anywhere;
  white-space: normal;
}

.module-directory {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 6px;
}

.module-directory-heading {
  align-items: center;
  border-bottom: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  min-height: 58px;
  padding: 0 18px;
}

.module-directory-heading h2 {
  font-size: 17px;
  margin: 0;
}

.module-directory-heading span {
  color: var(--muted);
  font-size: 12px;
}

.module-list {
  display: grid;
}

.module-row {
  align-items: center;
  border-bottom: 1px solid var(--line-soft);
  display: grid;
  gap: 14px;
  grid-template-columns: 34px minmax(180px, 1fr) 100px 90px 18px;
  min-height: 60px;
  padding: 8px 18px;
}

.module-row:last-child {
  border-bottom: 0;
}

.module-row:hover {
  background: var(--jade-wash);
}

.module-icon {
  align-items: center;
  background: var(--jade-soft);
  border-radius: 4px;
  color: var(--jade);
  display: inline-flex;
  height: 32px;
  justify-content: center;
  width: 32px;
}

.module-value {
  color: var(--ink-secondary);
  font-variant-numeric: tabular-nums;
}

.module-status {
  color: var(--jade);
  font-size: 12px;
}

@media (max-width: 760px) {
  .summary-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .summary-strip article,
  .summary-strip article:last-child {
    border-bottom: 1px solid var(--line);
    border-right: 1px solid var(--line);
  }

  .summary-strip article:nth-child(2n) {
    border-right: 0;
  }

  .module-row {
    grid-template-columns: 34px minmax(0, 1fr) auto 18px;
  }

  .module-value {
    display: none;
  }

  .next-actions-heading {
    min-height: 52px;
    padding: 0 14px;
  }

  .next-action-row {
    gap: 10px;
    grid-template-columns: 22px minmax(0, 1fr);
    padding: 12px 14px;
  }

  .next-action-text {
    font-size: 13px;
    line-height: 1.5;
  }
}
</style>
