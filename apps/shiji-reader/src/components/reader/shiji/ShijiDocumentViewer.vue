<template>
  <div class="document-mode">
    <div class="document-toolbar">
      <div>
        <strong>{{ versionName }}</strong>
        <span>《史记》真实 OCR 书影 · 右起左行连续拼接</span>
      </div>
      <button
        class="document-follow"
        type="button"
        :class="{ active: followReading }"
        :aria-pressed="followReading"
        :disabled="!pageIds.length"
        @click="toggleFollow"
      >
        <LocateFixed :size="14" />
        {{ followReading ? `跟随正文 · 第 ${activePageIndex + 1} 叶` : "恢复跟随" }}
      </button>
      <div class="document-actions" aria-label="书影缩放">
        <button type="button" title="缩小书影" @click="changeZoom(-10)">
          <Minus :size="15" />
        </button>
        <output>{{ zoom }}%</output>
        <button type="button" title="放大书影" @click="changeZoom(10)">
          <Plus :size="15" />
        </button>
        <button
          type="button"
          :class="{ active: fitPage }"
          :title="fitPage ? '恢复手动缩放' : '适合窗口'"
          @click="fitPage = !fitPage"
        >
          <Maximize2 :size="15" />
        </button>
      </div>
    </div>

    <figure v-if="pageIds.length" class="document-stage document-only">
      <div
        ref="stripViewport"
        class="scan-strip-viewport"
        :class="{ 'manual-strip': !followReading }"
        aria-label="《史记》连续书影，右起左行"
        @wheel.passive="pauseFollowing"
        @scroll.passive="handleStripScroll"
        @pointerdown="startStripDrag"
        @pointermove="moveStripDrag"
        @pointerup="stopStripDrag"
        @pointercancel="stopStripDrag"
      >
        <div class="scan-strip">
          <figure
            v-for="(pageId, index) in pageIds"
            :key="pageId"
            class="scan-sheet"
            :class="{ active: index === activePageIndex }"
            :data-page-id="pageId"
          >
            <RouterLink class="scan-sheet-media" :to="`/reader/scan/${pageId}`" title="打开逐页书影">
              <img
                :src="getOcrWorkspacePageImageUrl(pageId)"
                :alt="`《史记》OCR 书影第 ${index + 1} 叶`"
                :class="{ 'fit-page': fitPage }"
                :style="fitPage ? undefined : { height: `${zoom}%` }"
                draggable="false"
                loading="lazy"
              />
            </RouterLink>
            <figcaption>{{ shortPageId(pageId) }}</figcaption>
          </figure>
        </div>
      </div>
      <figcaption>
        <ScanLine :size="14" />
        <span v-if="followReading">
          正文滚动联动 · 当前第 {{ activePageIndex + 1 }} / {{ pageIds.length }} 叶
        </span>
        <span v-else>手动浏览书带 · 点击“恢复跟随”重新同步</span>
      </figcaption>
    </figure>

    <section v-else class="document-empty-state">
      <ScanLine :size="28" />
      <strong>当前段尚未登记书影页</strong>
      <p>文献模式不会用 OCR 文本或占位图替代书影。</p>
    </section>

    <footer class="document-pagination">
      <button type="button" :disabled="manualPageIndex <= 0" @click="selectPage(manualPageIndex - 1)">
        <ChevronLeft :size="15" />
        上一叶
      </button>
      <span>{{ pageIds.length }} 叶连续书带 · 点击书影查看原始页</span>
      <button
        type="button"
        :disabled="manualPageIndex >= pageIds.length - 1"
        @click="selectPage(manualPageIndex + 1)"
      >
        下一叶
        <ChevronRight :size="15" />
      </button>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  ChevronLeft,
  ChevronRight,
  LocateFixed,
  Maximize2,
  Minus,
  Plus,
  ScanLine,
} from "@lucide/vue";

import { getOcrWorkspacePageImageUrl } from "../../../services/api";

const props = defineProps<{
  pageIds: string[];
  versionName: string;
  readingPosition: number;
  activePage: number;
}>();

const stripViewport = ref<HTMLElement | null>(null);
const manualPageIndex = ref(0);
const zoom = ref(92);
const fitPage = ref(true);
const followReading = ref(true);
let dragPointerId: number | undefined;
let dragStartX = 0;
let dragStartScroll = 0;
const handleWindowResize = () => syncToReading();

const followedPageIndex = computed(() =>
  Math.min(props.pageIds.length - 1, Math.max(0, props.activePage)),
);
const activePageIndex = computed(() =>
  followReading.value ? followedPageIndex.value : manualPageIndex.value,
);

function toggleFollow() {
  followReading.value = !followReading.value;
  if (followReading.value) {
    manualPageIndex.value = followedPageIndex.value;
    syncToReading("smooth");
  }
}

function pauseFollowing() {
  if (followReading.value) {
    manualPageIndex.value = followedPageIndex.value;
    followReading.value = false;
  }
}

function syncToReading(behavior: ScrollBehavior = "auto") {
  if (!followReading.value || !props.pageIds.length) {
    return;
  }
  manualPageIndex.value = followedPageIndex.value;
  const progress = props.pageIds.length > 1
    ? followedPageIndex.value / (props.pageIds.length - 1)
    : props.readingPosition;
  if (stripViewport.value) {
    scrollToProgress(progress, behavior);
  } else {
    void nextTick(() => scrollToProgress(progress, behavior));
  }
}

function scrollToProgress(progress: number, behavior: ScrollBehavior = "auto") {
  const viewport = stripViewport.value;
  if (!viewport) {
    return;
  }
  const maximum = Math.max(0, viewport.scrollWidth - viewport.clientWidth);
  viewport.scrollTo({
    left: maximum * (1 - Math.min(1, Math.max(0, progress))),
    behavior,
  });
}

function handleStripScroll() {
  const viewport = stripViewport.value;
  if (!viewport || followReading.value || !props.pageIds.length) {
    return;
  }
  const maximum = Math.max(1, viewport.scrollWidth - viewport.clientWidth);
  const progress = 1 - viewport.scrollLeft / maximum;
  manualPageIndex.value = Math.min(
    props.pageIds.length - 1,
    Math.max(0, Math.round(progress * (props.pageIds.length - 1))),
  );
}

function startStripDrag(event: PointerEvent) {
  if (event.button !== 0) {
    return;
  }
  const viewport = stripViewport.value;
  if (!viewport) {
    return;
  }
  pauseFollowing();
  dragPointerId = event.pointerId;
  dragStartX = event.clientX;
  dragStartScroll = viewport.scrollLeft;
  viewport.setPointerCapture(event.pointerId);
}

function moveStripDrag(event: PointerEvent) {
  const viewport = stripViewport.value;
  if (!viewport || dragPointerId !== event.pointerId) {
    return;
  }
  viewport.scrollLeft = dragStartScroll - (event.clientX - dragStartX);
}

function stopStripDrag(event: PointerEvent) {
  const viewport = stripViewport.value;
  if (!viewport || dragPointerId !== event.pointerId) {
    return;
  }
  if (viewport.hasPointerCapture(event.pointerId)) {
    viewport.releasePointerCapture(event.pointerId);
  }
  dragPointerId = undefined;
}

function selectPage(index: number) {
  if (!props.pageIds.length) {
    return;
  }
  followReading.value = false;
  manualPageIndex.value = Math.min(props.pageIds.length - 1, Math.max(0, index));
  const progress = props.pageIds.length > 1
    ? manualPageIndex.value / (props.pageIds.length - 1)
    : 0;
  scrollToProgress(progress, "smooth");
}

function changeZoom(delta: number) {
  fitPage.value = false;
  zoom.value = Math.min(170, Math.max(60, zoom.value + delta));
}

function shortPageId(pageId: string) {
  const match = pageId.match(/p\d+$/);
  return match ? match[0] : pageId;
}

watch(
  () => [props.activePage, props.readingPosition, props.pageIds] as const,
  () => syncToReading(),
  { immediate: true, deep: true },
);

onMounted(() => {
  syncToReading();
  window.addEventListener("resize", handleWindowResize);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleWindowResize);
});
</script>
