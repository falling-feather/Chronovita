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
        <template v-else-if="mode === 'map' && !disableMap">
          <ShijiMapAvailable
            v-if="historicalMap?.curated_scenes.length"
            key="map-ready"
            :active-unit-label="activeUnitLabel"
            :active-unit-id="activeUnitId"
            :map="historicalMap"
            :scene="mapScene"
            :selected-scene-id="mapSceneId"
            :scene-loading="mapSceneLoading"
            :scene-error="mapSceneError"
            @select-scene="$emit('select-map-scene', $event)"
            @focus-unit="$emit('focus-unit', $event)"
          />
          <ShijiMapMissing
            v-else
            key="map-missing"
            :active-unit-label="activeUnitLabel"
            :active-unit-id="activeUnitId"
            :map="historicalMap"
          />
        </template>
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
import { BookCopy, Map, PanelRightClose, ScanSearch } from "@lucide/vue";

import type {
  ContentSource,
  KnowledgeEntity,
  ShijiMapScene,
  ShijiMapSummary,
} from "../../../services/api";
import type { ShijiDisplayMode } from "./types";
import ShijiKeywordEncyclopedia from "./ShijiKeywordEncyclopedia.vue";
import ShijiMapMissing from "./ShijiMapMissing.vue";
import ShijiMapAvailable from "./ShijiMapAvailable.vue";

const readerOnlyBuild = import.meta.env.VITE_READER_ONLY === "true";
const disableMap = import.meta.env.VITE_DISABLE_MAP === "true";
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
  historicalMap?: ShijiMapSummary | null;
  mapScene: ShijiMapScene | null;
  mapSceneId: string;
  mapSceneLoading: boolean;
  mapSceneError: string;
}>();

defineEmits<{
  "change-mode": [mode: ShijiDisplayMode];
  collapse: [];
  "select-knowledge": [id: string];
  "select-map-scene": [apiPath: string];
  "focus-unit": [unitId: string];
}>();

const tabs: Array<{ id: ShijiDisplayMode; label: string; icon: typeof BookCopy }> = [
  ...(!readerOnlyBuild ? [{ id: "document" as const, label: "文献", icon: ScanSearch }] : []),
  ...(!disableMap ? [{ id: "map" as const, label: "历史地图", icon: Map }] : []),
  { id: "encyclopedia", label: "关键词百科", icon: BookCopy },
];
</script>
