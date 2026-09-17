<template>
  <aside class="catalog-panel" :class="{ collapsed }">
    <template v-if="collapsed">
      <button class="rail-action primary" type="button" title="展开目录" @click="$emit('toggle')">
        <BookOpenText :size="20" />
        <span class="sr-only">展开目录</span>
      </button>
      <button class="rail-action" type="button" title="展开目录" @click="$emit('toggle')">
        <PanelLeftOpen :size="18" />
        <span class="sr-only">展开目录</span>
      </button>
      <span class="rail-caption">目录</span>
    </template>

    <template v-else>
      <header class="panel-heading">
        <div>
          <strong>目录</strong>
          <span>{{ readerOnlyBuild ? "《史记》成品阅读" : "《史记》OCR 导入" }}</span>
        </div>
        <button type="button" title="收起目录" aria-label="收起目录" @click="$emit('toggle')">
          <PanelLeftClose :size="18" />
        </button>
      </header>

      <section class="shiji-import-ledger" aria-label="史记应用总账">
        <div><strong>{{ formatNumber(totalVolumeCount) }}</strong><span>全书卷数</span></div>
        <div><strong>{{ formatNumber(appliedVolumeCount) }}</strong><span>已应用卷</span></div>
        <p>
          {{ applicationStatus?.label ?? "AI整理 / 人类未校" }} · 目录按卷读取；正文按当前篇章加载。
          <span v-if="!readerOnlyBuild && coverageGap > 0">另有 {{ formatNumber(coverageGap) }} 页仅在逐页书影入口中。</span>
        </p>
      </section>

      <div class="catalog-search">
        <Search :size="15" />
        <input v-model.trim="query" type="search" :placeholder="readerOnlyBuild ? '检索卷次或篇章' : '检索篇章或 OCR 批次'" />
      </div>

      <nav class="catalog-tree shiji-volume-tree" aria-label="《史记》130 卷阅读目录">
        <section v-for="group in categoryGroups" :key="group.id" class="catalog-category">
          <header class="catalog-category-heading">
            <strong>{{ group.label }}</strong>
            <small>{{ group.volumes.length }} 卷</small>
          </header>
          <section v-for="volume in group.volumes" :key="volume.id" class="catalog-section volume-section">
            <button
              class="section-toggle volume-toggle"
              type="button"
              :aria-expanded="isOpen(volume.volumeNo)"
              @click="toggleVolume(volume.volumeNo)"
            >
              <ChevronDown :size="15" :class="{ closed: !isOpen(volume.volumeNo) }" />
              <span class="catalog-group-copy">
                <strong>卷 {{ volume.volumeNo }} · {{ volume.title }}</strong>
                <small>{{ volume.preview || volume.chapterType || volumeStatusLabel(volume) }}</small>
              </span>
              <span>{{ volume.chapterCount || "—" }}</span>
            </button>
            <RouterLink
              v-if="volume.available"
              class="volume-open-link"
              :to="{ name: 'reader-volume', params: { volumeNo: volume.volumeNo } }"
              @click.stop
            >
              <BookOpenText :size="13" />
              打开本卷
            </RouterLink>
            <div v-if="isOpen(volume.volumeNo)" class="chapter-list">
              <p v-if="isLoading(volume.volumeNo)" class="catalog-inline-state">正在加载卷内章节…</p>
              <p v-else-if="volumeErrors[volume.volumeNo]" class="catalog-inline-state error-text">
                {{ volumeErrors[volume.volumeNo] }}
                <button type="button" @click.stop="loadVolume(volume.volumeNo)">重试</button>
              </p>
              <div v-for="entry in entriesForVolume(volume.volumeNo)" :key="entry.passage_id" class="catalog-entry-group">
                <RouterLink
                  :class="{ active: entry.passage_id === activePassageId }"
                  :to="passageLink(entry)"
                  :aria-current="entry.passage_id === activePassageId ? 'page' : undefined"
                >
                  <span class="chapter-marker"></span>
                  <span class="chapter-copy">
                    <span>{{ entry.title }}</span>
                    <small v-if="entry.preview_simplified || entry.preview_traditional">
                      {{ entry.preview_simplified || entry.preview_traditional }}
                    </small>
                  </span>
                  <small>{{ entry.sequence }}</small>
                </RouterLink>
                <div v-if="entry.commentary?.available" class="commentary-directory-entry">
                  <span class="chapter-marker"></span>
                  <span class="chapter-copy">
                    <span>注文</span>
                    <small>{{ entry.commentary.preview_simplified || entry.commentary.preview_traditional || "注文已迁移，待单独阅读" }}</small>
                  </span>
                </div>
                <div v-if="entry.mixed?.available" class="commentary-directory-entry mixed-directory-entry">
                  <span class="chapter-marker"></span>
                  <span class="chapter-copy">
                    <span>{{ entry.mixed.title_simplified || entry.mixed.title_traditional || "正文／注文待拆分" }}</span>
                    <small>{{ entry.mixed.preview_simplified || entry.mixed.preview_traditional || "存在正文与注文混合片段，待逐句拆分" }}</small>
                  </span>
                </div>
              </div>
              <p
                v-if="!isLoading(volume.volumeNo) && !volumeErrors[volume.volumeNo] && !entriesForVolume(volume.volumeNo).length"
                class="catalog-inline-state"
              >
                本卷尚未有可打开的 application_ready 篇章。
              </p>
            </div>
          </section>
        </section>
        <p v-if="!filteredVolumes.length" class="catalog-inline-state">没有匹配的卷或篇章。</p>
      </nav>

      <footer v-if="!readerOnlyBuild" class="catalog-footer shiji-catalog-footer">
      <RouterLink to="/books/shiji">
        <ScanSearch :size="15" />
        <span>查看全部 {{ formatNumber(ocrPageTotal) }} 个 OCR 页</span>
      </RouterLink>
      </footer>
    </template>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  BookOpenText,
  ChevronDown,
  PanelLeftClose,
  PanelLeftOpen,
  ScanSearch,
  Search,
} from "@lucide/vue";

import type { ReaderManifestEntry } from "../../../services/api";
import type { ShijiApplicationStatus, ShijiVolumeSummary } from "../../../services/shiji-reader-contracts";

const props = defineProps<{
  collapsed: boolean;
  volumes: ShijiVolumeSummary[];
  catalogEntries: ReaderManifestEntry[];
  loadedEntries: Record<number, ReaderManifestEntry[]>;
  activePassageId: string;
  activeVolumeNo: number;
  selectedVersionId: string;
  ocrPageTotal: number;
  continuousPageTotal: number;
  totalVolumeCount: number;
  applicationStatus?: ShijiApplicationStatus;
  loadingVolumeNos: number[];
  volumeErrors: Record<number, string>;
}>();

const emit = defineEmits<{
  toggle: [];
  "load-volume": [volumeNo: number];
}>();

const readerOnlyBuild = import.meta.env.VITE_READER_ONLY === "true";
const query = ref("");
const openVolumes = ref<number[]>([]);
const coverageGap = computed(() => Math.max(0, props.ocrPageTotal - props.continuousPageTotal));
const appliedVolumeCount = computed(() => props.volumes.filter((volume) => volume.available).length);

const filteredVolumes = computed(() => {
  const keyword = query.value.toLocaleLowerCase();
  if (!keyword) {
    return props.volumes;
  }
  return props.volumes.filter((volume) => {
    const entries = entriesForSearch(volume.volumeNo);
    return [volume.title, volume.chapterType, String(volume.volumeNo), ...entries.flatMap((entry) => [
      entry.title,
      entry.chapter_title,
      String(entry.sequence),
    ])].some((value) => value.toLocaleLowerCase().includes(keyword));
  });
});

const categoryGroups = computed(() => {
  const groups = new Map<string, { id: string; label: string; volumes: ShijiVolumeSummary[] }>();
  for (const volume of filteredVolumes.value) {
    const id = volume.categoryId || volume.chapterType || "uncategorized";
    const label = volume.categoryLabel || volume.chapterType || "未分类";
    const group = groups.get(id) ?? { id, label, volumes: [] };
    group.volumes.push(volume);
    groups.set(id, group);
  }
  return [...groups.values()].sort((left, right) => {
    const order = ["benji", "table", "treatise", "hereditary-house", "biography", "uncategorized"];
    return (order.indexOf(left.id) < 0 ? 99 : order.indexOf(left.id))
      - (order.indexOf(right.id) < 0 ? 99 : order.indexOf(right.id));
  });
});

watch(
  () => [props.activePassageId, props.activeVolumeNo, props.volumes] as const,
  () => {
    const currentVolume = props.activeVolumeNo || props.volumes.find((volume) =>
      entriesForVolume(volume.volumeNo).some((entry) => entry.passage_id === props.activePassageId),
    )?.volumeNo;
    if (currentVolume && !openVolumes.value.includes(currentVolume)) {
      openVolumes.value = [currentVolume];
      loadVolume(currentVolume);
    } else if (!openVolumes.value.length && props.volumes[0]) {
      openVolumes.value = [props.volumes[0].volumeNo];
      loadVolume(props.volumes[0].volumeNo);
    }
  },
  { immediate: true },
);

watch(query, (value) => {
  if (value) {
    openVolumes.value = filteredVolumes.value.map((volume) => volume.volumeNo);
    if (filteredVolumes.value.length === 1) {
      loadVolume(filteredVolumes.value[0].volumeNo);
    }
  }
});

function isOpen(volumeNo: number) {
  return openVolumes.value.includes(volumeNo);
}

function toggleVolume(volumeNo: number) {
  if (isOpen(volumeNo)) {
    openVolumes.value = openVolumes.value.filter((id) => id !== volumeNo);
    return;
  }
  openVolumes.value = [...openVolumes.value, volumeNo];
  loadVolume(volumeNo);
}

function loadVolume(volumeNo: number) {
  if (!isVolumeLoaded(volumeNo) && !isLoading(volumeNo)) {
    emit("load-volume", volumeNo);
  }
}

function entriesForVolume(volumeNo: number) {
  return props.loadedEntries[volumeNo] ?? [];
}

function entriesForSearch(volumeNo: number) {
  if (Object.prototype.hasOwnProperty.call(props.loadedEntries, volumeNo)) {
    return entriesForVolume(volumeNo);
  }
  return props.catalogEntries.filter((entry) => entry.volume_no === volumeNo);
}

function isVolumeLoaded(volumeNo: number) {
  return Object.prototype.hasOwnProperty.call(props.loadedEntries, volumeNo);
}

function isLoading(volumeNo: number) {
  return props.loadingVolumeNos.includes(volumeNo);
}

function volumeStatusLabel(volume: ShijiVolumeSummary) {
  if (volume.available) {
    return isVolumeLoaded(volume.volumeNo) ? `${volume.chapterCount} 章已载入` : "已应用 · 点击载入章节";
  }
  return "尚未应用";
}

function passageLink(entry: ReaderManifestEntry) {
  const availableVersionIds = entry.available_versions.map((version) => version.id);
  return {
    name: "reader-passage",
    params: { passageId: entry.passage_id },
    query: availableVersionIds.includes(props.selectedVersionId)
      ? { version: props.selectedVersionId }
      : undefined,
  };
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-CN").format(value);
}
</script>

<style scoped>
.shiji-volume-tree {
  overflow-y: auto;
}

.catalog-category-heading {
  align-items: baseline;
  background: var(--paper-deep);
  border-bottom: 1px solid var(--line-soft);
  display: flex;
  justify-content: space-between;
  padding: 11px 18px 8px 18px;
}

.catalog-category-heading strong {
  color: var(--jade-dark);
  font-family: var(--font-serif);
  font-size: 13px;
}

.catalog-category-heading small {
  color: var(--muted);
  font-size: 11px;
}

.volume-section {
  border-bottom: 1px solid var(--line-soft);
}

.volume-toggle {
  min-height: 54px;
  text-align: left;
}

.volume-toggle .catalog-group-copy {
  min-width: 0;
}

.volume-toggle strong,
.volume-toggle small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.volume-toggle strong {
  color: var(--ink);
  font-family: var(--font-serif);
  font-size: 13px;
}

.volume-toggle small {
  color: var(--muted);
  font-size: 11px;
  margin-top: 3px;
}

.chapter-copy {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.chapter-copy small {
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chapter-copy em {
  color: var(--jade-dark);
  font-size: 10px;
  font-style: normal;
}

.commentary-directory-entry {
  align-items: center;
  color: var(--muted);
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr);
  gap: 8px;
  margin: 0 18px 6px 38px;
  padding: 5px 0 5px 9px;
}

.commentary-directory-entry .chapter-marker {
  border-color: var(--gold);
}

.mixed-directory-entry {
  color: var(--cinnabar);
  font-style: italic;
}

.mixed-directory-entry .chapter-marker {
  border-color: var(--cinnabar);
}

.volume-open-link {
  align-items: center;
  color: var(--jade-dark);
  display: inline-flex;
  font-size: 11px;
  gap: 4px;
  margin: 0 18px 6px 38px;
  text-decoration: none;
}

.volume-open-link:hover {
  text-decoration: underline;
}

.catalog-inline-state {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.6;
  margin: 0;
  padding: 10px 18px 10px 38px;
}

.catalog-inline-state button {
  background: transparent;
  border: 0;
  color: var(--jade-dark);
  cursor: pointer;
  font-size: 12px;
  margin-left: 5px;
  padding: 0;
  text-decoration: underline;
}
</style>
