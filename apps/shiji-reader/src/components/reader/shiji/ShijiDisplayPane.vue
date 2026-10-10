<template>
  <section class="display-pane">
    <header class="display-header">
      <div class="display-tabs" role="tablist" aria-label="展示区内容">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          role="tab"
          :aria-selected="mode === tab.id"
          :class="{ active: mode === tab.id }"
          @click="$emit('change-mode', tab.id)"
        >
          <component :is="tab.icon" :size="16" />
          {{ tab.label }}
        </button>
      </div>
      <button class="collapse-display" type="button" title="收起展示区" @click="$emit('collapse')">
        <PanelRightClose :size="18" />
        <span class="sr-only">收起展示区</span>
      </button>
    </header>

    <div class="display-content">
      <Transition name="display-swap" mode="out-in">
        <ShijiDocumentViewer
          v-if="!readerOnlyBuild && mode === 'document'"
          key="document"
          :page-ids="pageIds"
          :version-name="versionName"
          :reading-position="readingPosition"
          :active-page="activePage"
        />
        <ShijiKeywordEncyclopedia
          v-else
          key="encyclopedia"
          :items="entities"
          :sources="sources"
          :selected-id="selectedKnowledgeId"
          @select="$emit('select-knowledge', $event)"
        />
      </Transition>
    </div>
  </section>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from "vue";
import { BookCopy, PanelRightClose, ScanSearch } from "@lucide/vue";

import type {
  ContentSource,
  KnowledgeEntity,
} from "../../../services/api";
import type { ShijiDisplayMode } from "./types";
import ShijiKeywordEncyclopedia from "./ShijiKeywordEncyclopedia.vue";

const readerOnlyBuild = import.meta.env.VITE_READER_ONLY === "true";
const ShijiDocumentViewer = readerOnlyBuild
  ? null
  : defineAsyncComponent(() => import("./ShijiDocumentViewer.vue"));

defineProps<{
  mode: ShijiDisplayMode;
  pageIds: string[];
  versionName: string;
  readingPosition: number;
  activePage: number;
  activeUnitLabel: string;
  activeUnitId: string;
  entities: KnowledgeEntity[];
  sources: ContentSource[];
  selectedKnowledgeId: string;
}>();

defineEmits<{
  "change-mode": [mode: ShijiDisplayMode];
  collapse: [];
  "select-knowledge": [id: string];
  "focus-unit": [unitId: string];
}>();

const tabs: Array<{ id: ShijiDisplayMode; label: string; icon: typeof BookCopy }> = [
  ...(!readerOnlyBuild ? [{ id: "document" as const, label: "文献", icon: ScanSearch }] : []),
  { id: "encyclopedia", label: "关键词百科", icon: BookCopy },
];
</script>
