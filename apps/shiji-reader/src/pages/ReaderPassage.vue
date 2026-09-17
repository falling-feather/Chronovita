<template>
  <main class="shiji-reader-page">
    <div
      class="reader-app"
      :class="[
        `theme-${preferences.theme}`,
        { 'texture-disabled': !preferences.showTexture },
      ]"
    >
      <section v-if="loading" class="shiji-reader-state">
        <LoaderCircle :size="24" class="spin" />
        <strong>正在载入《史记》阅读段</strong>
        <span>先读取当前正文，目录与书影随后按卷载入…</span>
      </section>

      <section v-else-if="error || !payload" class="shiji-reader-state error-state">
        <CircleAlert :size="26" />
        <strong>当前阅读段无法载入</strong>
        <span>{{ error || "未找到阅读内容。" }}</span>
        <RouterLink to="/books/shiji">返回《史记》目录</RouterLink>
      </section>

      <template v-else>
        <main
          class="reader-shell"
          :class="{
            'catalog-is-collapsed': catalogCollapsed,
            'function-is-collapsed': functionCollapsed,
          }"
        >
          <ShijiCatalogPanel
            :collapsed="catalogCollapsed"
            :volumes="navigation?.volumes ?? []"
            :catalog-entries="navigation?.entries ?? []"
            :loaded-entries="volumeEntries"
            :active-passage-id="payload.passage.id"
            :active-volume-no="activeVolumeNo"
            :selected-version-id="selectedVersion"
            :ocr-page-total="ocrPageTotal"
            :continuous-page-total="continuousPageTotal"
            :total-volume-count="navigation?.totalVolumes ?? 130"
            :application-status="navigation?.applicationStatus ?? passageApplicationStatus"
            :loading-volume-nos="loadingVolumeNos"
            :volume-errors="volumeErrors"
            @toggle="catalogCollapsed = !catalogCollapsed"
            @load-volume="loadVolume"
          />

          <section
            ref="workspaceRef"
            class="reading-workspace"
            :class="{
              'display-is-hidden': !displayVisible,
              'panes-swapped': panesSwapped,
            }"
            :style="{ '--leading-share': `${leadingShare}%` }"
          >
            <ShijiReadingPane
              ref="readingPaneRef"
              :payload="payload"
              :units="units"
              :active-unit-index="activeUnitIndex"
              :preferences="preferences"
              @previous="movePassage('previous')"
              @next="movePassage('next')"
              @open-knowledge="openKnowledge"
              @focus-unit="activeUnitIndex = $event"
              @reading-position="readingPosition = $event"
              @update-preferences="updatePreferences"
            />

            <button
              v-if="displayVisible"
              class="workspace-divider"
              type="button"
              aria-label="拖动调整正文区与展示区宽度"
              title="拖动调整分栏；也可用左右方向键"
              @pointerdown="startResize"
              @keydown="resizeByKeyboard"
            ><span></span></button>

            <ShijiDisplayPane
              v-if="displayVisible"
              :mode="displayMode"
              :page-ids="pageIds"
              :version-name="payload.current_version.name"
              :reading-position="readingPosition"
              :active-page="activePageIndex"
              :active-unit-label="activeUnit?.label ?? '当前段'"
              :active-unit-id="activeUnit?.id ?? ''"
              :entities="payload.entities ?? []"
              :sources="payload.sources ?? []"
              :selected-knowledge-id="selectedKnowledgeId"
              :historical-map="payload.chapter_runtime?.historical_map ?? null"
              :map-scene="mapScene"
              :map-scene-id="mapSceneId"
              :map-scene-loading="mapSceneLoading"
              :map-scene-error="mapSceneError"
              @change-mode="handleModeChange"
              @collapse="displayVisible = false"
              @select-knowledge="selectedKnowledgeId = $event"
              @select-map-scene="loadMapScene"
              @focus-unit="focusReadingUnit"
            />

            <button v-else class="display-restore" type="button" @click="displayVisible = true">
              <PanelRightOpen :size="17" />
              <span>打开展示区</span>
            </button>
          </section>

          <ShijiFunctionPanel
            :collapsed="functionCollapsed"
            :preferences="preferences"
            :display-mode="displayMode"
            :display-visible="displayVisible"
            :panes-swapped="panesSwapped"
            :selected-knowledge-id="selectedKnowledgeId"
            :entities="payload.entities ?? []"
            :translation-available="translationAvailable"
            :annotation-available="Boolean(payload.highlights.length)"
            :versions="payload.available_versions"
            :selected-version-id="selectedVersion"
            @toggle="functionCollapsed = !functionCollapsed"
            @update-preferences="updatePreferences"
            @change-mode="handleModeChange"
            @toggle-display="displayVisible = !displayVisible"
            @swap-panes="swapPanes"
            @select-knowledge="openKnowledge"
            @change-version="changeVersion"
          />
        </main>

        <ShijiFloatingAssistant :passage-title="payload.passage.title" @scroll-top="scrollToTop" />
      </template>

      <Transition name="toast">
        <div v-if="toast" class="app-toast" role="status">{{ toast }}</div>
      </Transition>
    </div>
  </main>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import { CircleAlert, LoaderCircle, PanelRightOpen } from "@lucide/vue";
import { useRoute, useRouter } from "vue-router";

import ShijiCatalogPanel from "../components/reader/shiji/ShijiCatalogPanel.vue";
import ShijiDisplayPane from "../components/reader/shiji/ShijiDisplayPane.vue";
import ShijiFloatingAssistant from "../components/reader/shiji/ShijiFloatingAssistant.vue";
import ShijiFunctionPanel from "../components/reader/shiji/ShijiFunctionPanel.vue";
import ShijiReadingPane from "../components/reader/shiji/ShijiReadingPane.vue";
import { buildShijiReadingUnits } from "../components/reader/shiji/adapters";
import type {
  ShijiDisplayMode,
  ShijiReaderPreferences,
} from "../components/reader/shiji/types";
import {
  type PassagePayload,
  type ReaderManifestEntry,
  type ReaderSequenceTarget,
  type ShijiMapScene,
  getOcrWorkspacePageCount,
} from "../services/api";
import {
  getShijiMapScene,
  getShijiReaderNavigation,
  getShijiReaderPassage,
  getShijiVolumeEntries,
} from "../services/shiji-reader-client";
import {
  activeShijiFacsimilePageId,
  mergeShijiFacsimilePageIds,
  shijiSceneFacsimileStages,
} from "../services/shiji-map-sync";
import type {
  ShijiApplicationStatus,
  ShijiReaderNavigation,
} from "../services/shiji-reader-contracts";
import { attachNavigationToPassage } from "../services/shiji-reader-contracts";

const route = useRoute();
const router = useRouter();
const payload = ref<PassagePayload | null>(null);
const navigation = ref<ShijiReaderNavigation | null>(null);
const volumeEntries = ref<Record<number, ReaderManifestEntry[]>>({});
const loading = ref(true);
const error = ref("");
const selectedVersion = ref("");
const ocrPageTotal = ref(0);
const catalogCollapsed = ref(false);
const functionCollapsed = ref(false);
const displayVisible = ref(true);
const readerOnlyBuild = import.meta.env.VITE_READER_ONLY === "true";
const displayMode = ref<ShijiDisplayMode>(readerOnlyBuild ? "encyclopedia" : "document");
const panesSwapped = ref(false);
const selectedKnowledgeId = ref("");
const activeUnitIndex = ref(0);
const readingPosition = ref(0);
const leadingShare = ref(58);
const workspaceRef = ref<HTMLElement | null>(null);
const readingPaneRef = ref<InstanceType<typeof ShijiReadingPane> | null>(null);
const toast = ref("");
let toastTimer: ReturnType<typeof setTimeout> | undefined;
let activeResizeCleanup: (() => void) | undefined;
let loadRequestId = 0;
let mapSceneRequestId = 0;
let navigationRequest: Promise<void> | undefined;
const loadingVolumeNos = ref<number[]>([]);
const volumeErrors = ref<Record<number, string>>({});
const mapScene = ref<ShijiMapScene | null>(null);
const mapSceneId = ref("");
const mapSceneLoading = ref(false);
const mapSceneError = ref("");

const preferences = ref<ShijiReaderPreferences>({
  theme: "paper",
  textVariant: "traditional",
  fontSize: 22,
  lineHeight: 2.05,
  paragraphSpacing: 1.15,
  showTexture: true,
  showPunctuation: true,
  showTranslation: false,
  showAnnotations: true,
});

const units = computed(() => payload.value ? buildShijiReadingUnits(payload.value) : []);
const activeUnit = computed(() => units.value[activeUnitIndex.value]);
const translationAvailable = computed(() => units.value.some((unit) => Boolean(unit.translation)));
const passageApplicationStatus = computed<ShijiApplicationStatus>(() => {
  const value = (payload.value as (PassagePayload & { application_status?: ShijiApplicationStatus }) | null)
    ?.application_status;
  return value ?? {
    state: "application_ready",
    label: "AI整理 / 人类未校",
    aiStatus: payload.value?.publication?.ai_status ?? "AI初筛完成",
    humanStatus: payload.value?.publication?.human_status ?? "人类待检查",
    isApplicationReady: true,
  };
});
const activeVolumeNo = computed(() =>
  payload.value?.reader_sequence?.volume.number
  ?? navigation.value?.entries.find((entry) => entry.passage_id === payload.value?.passage.id)?.volume_no
  ?? 0,
);
const continuousPageTotal = computed(() => {
  const ids = new Set<string>();
  Object.values(volumeEntries.value).forEach((entries) => entries.forEach((entry) =>
    entry.available_versions.forEach((version) => version.page_ids?.forEach((pageId) => ids.add(pageId))),
  ));
  pageIds.value.forEach((pageId) => ids.add(pageId));
  return ids.size;
});
const basePageIds = computed(() => {
  if (!payload.value) {
    return [];
  }
  const direct = payload.value.current_version.page_ids ?? [];
  if (direct.length) {
    return direct;
  }
  const entry = volumeEntries.value[activeVolumeNo.value]?.find(
    (item) => item.passage_id === payload.value?.passage.id,
  ) ?? navigation.value?.entries.find((item) => item.passage_id === payload.value?.passage.id);
  const version = entry?.available_versions.find((item) => item.id === selectedVersion.value);
  if (version?.page_ids?.length) {
    return version.page_ids;
  }
  const fallback = payload.value.reading.page.page_id;
  return fallback ? [fallback] : [];
});
const sceneFacsimileStages = computed(() => (
  shijiSceneFacsimileStages(
    mapScene.value?.narrative_sequence?.stages ?? [],
    selectedVersion.value,
  )
));
const pageIds = computed(() => mergeShijiFacsimilePageIds(
  basePageIds.value,
  mapScene.value?.narrative_sequence?.stages ?? [],
  selectedVersion.value,
));
const activeFacsimilePageId = computed(() => activeShijiFacsimilePageId(
  mapScene.value?.narrative_sequence?.stages ?? [],
  selectedVersion.value,
  activeUnit.value?.id ?? "",
));
const activePageIndex = computed(() => {
  const scenePageIndex = pageIds.value.indexOf(activeFacsimilePageId.value);
  if (scenePageIndex >= 0) return scenePageIndex;
  const basePageId = basePageIds.value[activeUnit.value?.pageIndex ?? 0];
  const basePageIndex = pageIds.value.indexOf(basePageId);
  return basePageIndex >= 0 ? basePageIndex : 0;
});

async function loadPassage() {
  const requestId = ++loadRequestId;
  loading.value = true;
  error.value = "";
  resetMapScene();
  try {
    const passageId = String(route.params.passageId);
    const versionId = typeof route.query.version === "string" ? route.query.version : undefined;
    const nextPayload = await getShijiReaderPassage(passageId, "segment", versionId);
    if (requestId !== loadRequestId) {
      return;
    }
    if (nextPayload.passage.book_id !== "shiji") {
      throw new Error("本轮阅读器只开放《史记》内容。");
    }
    payload.value = nextPayload;
    selectedVersion.value = nextPayload.current_version.id;
    selectedKnowledgeId.value = nextPayload.entities?.[0]?.id ?? "";
    activeUnitIndex.value = 0;
    readingPosition.value = 0;
    if (firstMapScene(nextPayload)) {
      void loadFirstMapScene(nextPayload);
    }
    loading.value = false;
    await nextTick();
    readingPaneRef.value?.scrollToTop();
    void loadSupplementaryData(nextPayload.reader_sequence?.volume.number);
  } catch (caught) {
    if (requestId !== loadRequestId) {
      return;
    }
    payload.value = null;
    error.value = caught instanceof Error ? caught.message : "加载失败";
  } finally {
    if (requestId === loadRequestId) {
      loading.value = false;
    }
  }
}

function loadSupplementaryData(volumeNo?: number) {
  if (!navigationRequest && !navigation.value) {
    const pageCountRequest = readerOnlyBuild
      ? Promise.resolve({ count: 0 })
      : getOcrWorkspacePageCount({ bookId: "shiji" }).catch(() => ({ count: 0 }));
    navigationRequest = Promise.all([
      getShijiReaderNavigation("shiji"),
      pageCountRequest,
    ])
      .then(([nextNavigation, countPayload]) => {
        navigation.value = nextNavigation;
        if (payload.value) {
          payload.value = attachNavigationToPassage(payload.value, nextNavigation);
        }
        ocrPageTotal.value = countPayload.count;
      })
      .catch(() => undefined)
      .finally(() => {
        navigationRequest = undefined;
      });
  }
  const request = navigationRequest ?? Promise.resolve();
  return request.then(() => {
    const targetVolumeNo = volumeNo ?? activeVolumeNo.value;
    if (targetVolumeNo > 0) {
      return loadVolume(targetVolumeNo);
    }
    return undefined;
  });
}

async function loadVolume(volumeNo: number) {
  if (volumeEntries.value[volumeNo] || loadingVolumeNos.value.includes(volumeNo)) {
    return;
  }
  loadingVolumeNos.value = [...loadingVolumeNos.value, volumeNo];
  volumeErrors.value = { ...volumeErrors.value, [volumeNo]: "" };
  try {
    const entries = await getShijiVolumeEntries(volumeNo, "shiji");
    volumeEntries.value = { ...volumeEntries.value, [volumeNo]: entries };
  } catch (caught) {
    volumeErrors.value = {
      ...volumeErrors.value,
      [volumeNo]: caught instanceof Error ? caught.message : "卷内章节加载失败",
    };
  } finally {
    loadingVolumeNos.value = loadingVolumeNos.value.filter((item) => item !== volumeNo);
  }
}

function movePassage(direction: "previous" | "next") {
  const target = payload.value?.reader_sequence?.[direction];
  if (!target) {
    announce(direction === "previous" ? "已经是当前索引的第一段。" : "已经是当前索引的最后一段。");
    return;
  }
  router.push(passageLink(target));
}

function passageLink(target: ReaderSequenceTarget) {
  const query = target.available_version_ids.includes(selectedVersion.value)
    ? { version: selectedVersion.value }
    : undefined;
  return {
    name: "reader-passage",
    params: { passageId: target.passage_id },
    query,
  };
}

function changeVersion(versionId: string) {
  if (!payload.value || versionId === selectedVersion.value) {
    return;
  }
  router.push({
    name: "reader-passage",
    params: { passageId: payload.value.passage.id },
    query: { version: versionId },
  });
}

function updatePreferences(next: Partial<ShijiReaderPreferences>) {
  preferences.value = { ...preferences.value, ...next };
  window.localStorage.setItem("shiji-reader-preferences", JSON.stringify(preferences.value));
}

function handleModeChange(mode: ShijiDisplayMode) {
  displayMode.value = mode;
  displayVisible.value = true;
  if (mode === "map") {
    void loadFirstMapScene();
  }
}

function resetMapScene() {
  mapSceneRequestId += 1;
  mapScene.value = null;
  mapSceneId.value = "";
  mapSceneLoading.value = false;
  mapSceneError.value = "";
}

function firstMapScene(nextPayload = payload.value) {
  return nextPayload?.chapter_runtime?.historical_map?.curated_scenes[0];
}

async function loadFirstMapScene(nextPayload = payload.value) {
  const scene = firstMapScene(nextPayload);
  if (scene?.api_path) {
    await loadMapScene(scene.api_path);
  }
}

async function loadMapScene(apiPath: string) {
  if (!apiPath) {
    return;
  }
  const requestId = ++mapSceneRequestId;
  mapSceneId.value = apiPath;
  mapSceneLoading.value = true;
  mapSceneError.value = "";
  try {
    const nextScene = await getShijiMapScene(apiPath);
    if (requestId !== mapSceneRequestId) {
      return;
    }
    mapScene.value = nextScene;
  } catch (caught) {
    if (requestId !== mapSceneRequestId) {
      return;
    }
    mapScene.value = null;
    mapSceneError.value = caught instanceof Error ? caught.message : "场景详情加载失败";
  } finally {
    if (requestId === mapSceneRequestId) {
      mapSceneLoading.value = false;
    }
  }
}

function swapPanes() {
  panesSwapped.value = !panesSwapped.value;
  announce(panesSwapped.value ? "展示区已移到左侧，阅读区已移到右侧。" : "阅读区已恢复到左侧。");
}

function openKnowledge(id: string) {
  selectedKnowledgeId.value = id;
  displayMode.value = "encyclopedia";
  displayVisible.value = true;
}

function startResize(event: PointerEvent) {
  const workspace = workspaceRef.value;
  if (!workspace) {
    return;
  }
  event.preventDefault();
  activeResizeCleanup?.();
  const divider = event.currentTarget as HTMLElement;
  divider.setPointerCapture(event.pointerId);

  const move = (moveEvent: PointerEvent) => {
    const rect = workspace.getBoundingClientRect();
    const raw = ((moveEvent.clientX - rect.left) / rect.width) * 100;
    leadingShare.value = Math.min(68, Math.max(32, raw));
  };
  const stop = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", stop);
    window.removeEventListener("pointercancel", stop);
    if (divider.hasPointerCapture(event.pointerId)) {
      divider.releasePointerCapture(event.pointerId);
    }
    activeResizeCleanup = undefined;
  };
  activeResizeCleanup = stop;
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", stop);
  window.addEventListener("pointercancel", stop);
}

function resizeByKeyboard(event: KeyboardEvent) {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
    return;
  }
  event.preventDefault();
  const direction = event.key === "ArrowLeft" ? -1 : 1;
  leadingShare.value = Math.min(68, Math.max(32, leadingShare.value + direction * 2));
}

function scrollToTop() {
  readingPaneRef.value?.scrollToTop();
  announce("已回到当前段落顶部。");
}

function focusReadingUnit(unitId: string) {
  const index = units.value.findIndex((unit) => unit.id === unitId);
  if (index < 0) {
    return;
  }
  activeUnitIndex.value = index;
  readingPosition.value = index / Math.max(1, units.value.length - 1);
  void nextTick(() => readingPaneRef.value?.scrollToUnit(unitId));
}

function announce(message: string) {
  toast.value = message;
  if (toastTimer) {
    clearTimeout(toastTimer);
  }
  toastTimer = window.setTimeout(() => { toast.value = ""; }, 2600);
}

function restorePreferences() {
  try {
    const saved = window.localStorage.getItem("shiji-reader-preferences");
    if (saved) {
      preferences.value = { ...preferences.value, ...JSON.parse(saved) };
    }
  } catch {
    window.localStorage.removeItem("shiji-reader-preferences");
  }
}

watch(() => [route.params.passageId, route.query.version], loadPassage);

onMounted(() => {
  restorePreferences();
  if (window.matchMedia("(max-width: 1080px)").matches) {
    catalogCollapsed.value = true;
    functionCollapsed.value = true;
  }
  if (window.matchMedia("(max-width: 780px)").matches) {
    displayVisible.value = false;
  }
  void loadPassage();
});

onBeforeUnmount(() => {
  if (toastTimer) clearTimeout(toastTimer);
  activeResizeCleanup?.();
});
</script>

<style src="../styles/shiji-reader-concept.css"></style>
<style src="../styles/shiji-reader-overrides.css"></style>
