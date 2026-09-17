<template>
  <article ref="scrollContainer" class="reading-pane" @scroll.passive="handleReadingScroll">
    <header class="reading-header">
      <div class="chapter-context">
        <span>史记</span>
        <i></i>
        <span>{{ chapterType }}</span>
        <i></i>
        <span>{{ volumeLabel }}</span>
      </div>
      <h1>{{ payload.passage.title }}</h1>
      <div class="passage-meta">
        <span>{{ payload.current_version.name }}</span>
        <span v-if="payload.reader_sequence">
          第 {{ payload.reader_sequence.position }} / {{ payload.reader_sequence.total }} 段
        </span>
      </div>
    </header>

    <div class="reading-modebar">
      <div class="reading-mode-switch" role="group" aria-label="译读模式">
        <button
          type="button"
          :class="{ active: preferences.showTranslation && translationAvailable }"
          :disabled="!translationAvailable"
          :title="translationAvailable ? '显示逐句译文' : '当前篇章尚未接入译文'"
          @click="updatePreference('showTranslation', true)"
        >
          <BookOpenCheck :size="14" />
          {{ translationAvailable ? "逐句译读" : "译文待接入" }}
        </button>
        <button
          type="button"
          :class="{ active: !preferences.showTranslation || !translationAvailable }"
          @click="updatePreference('showTranslation', false)"
        >
          <AlignLeft :size="14" />
          仅原文
        </button>
      </div>
      <div class="shiji-reading-status">
        <strong>AI整理 / 人类未校</strong>
        <small>
          {{ payload.publication?.ai_status ?? "AI初筛完成" }} ·
          {{ payload.publication?.human_status ?? "人类待检查" }}
        </small>
      </div>
      <button
        class="annotation-toggle"
        type="button"
        :aria-pressed="preferences.showAnnotations"
        :disabled="!payload.highlights.length"
        @click="updatePreference('showAnnotations', !preferences.showAnnotations)"
      >
        <Tags :size="14" />
        {{ preferences.showAnnotations ? "隐藏标注" : "显示标注" }}
      </button>
    </div>

    <ol
      class="sentence-reader"
      :class="{ 'translation-hidden': !preferences.showTranslation || !translationAvailable }"
      :style="{
        '--reader-font-size': `${preferences.fontSize}px`,
        '--reader-line-height': preferences.lineHeight,
        '--sentence-space': `${preferences.paragraphSpacing}em`,
      }"
    >
      <li
        v-for="(unit, index) in units"
        :key="unit.id"
        :ref="(element) => setUnitElement(element, index)"
        class="sentence-unit"
        :class="{ active: index === activeUnitIndex }"
        :data-unit-id="unit.id"
        :data-unit-index="index"
        :data-page-index="unit.pageIndex"
      >
        <span class="sentence-number">{{ String(index + 1).padStart(2, "0") }}</span>

        <section class="sentence-original" :aria-label="`第 ${index + 1} 个阅读单元原文`">
          <p>
            <template v-for="(part, partIndex) in inlineParts(unit)" :key="`${unit.id}-${partIndex}`">
              <button
                v-if="part.highlight && preferences.showAnnotations"
                class="inline-annotation interactive"
                :class="[
                  annotationClass(part.highlight.type),
                  { 'has-under-detail': part.detailBelow },
                ]"
                type="button"
                :title="annotationTitle(part.highlight, part.entity)"
                @click="$emit('open-knowledge', part.highlight.target_id)"
              >
                <span class="inline-annotation-text">{{ displayText(part.text) }}</span>
                <small v-if="part.detailBelow" class="inline-under-detail">
                  {{ part.detailBelow }}
                </small>
              </button>
              <template v-else>{{ displayText(part.text) }}</template>
            </template>
          </p>
          <small class="reading-unit-source">{{ unit.label }}</small>
        </section>

        <section
          v-if="preferences.showTranslation && unit.translation"
          class="sentence-translation"
          :aria-label="`第 ${index + 1} 个阅读单元译文`"
        >
          <span>译</span>
          <p>{{ unit.translation }}</p>
        </section>
      </li>
    </ol>

    <aside class="reading-note">
      <span>导入边界</span>
      <p>
        当前正文优先来自 application_ready 运行时；页面拆分只用于阅读呈现，不修改原始字符。
        译文、实体和来源锚点沿用已发布数据，内容状态仍为“人类待检查”。
      </p>
    </aside>

    <footer class="passage-navigation">
      <button type="button" :disabled="!payload.reader_sequence?.previous" @click="$emit('previous')">
        <ChevronLeft :size="16" />
        上一段
      </button>
      <span>已显示 {{ units.length }} 个阅读单元</span>
      <button type="button" :disabled="!payload.reader_sequence?.next" @click="$emit('next')">
        下一段
        <ChevronRight :size="16" />
      </button>
    </footer>
  </article>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  AlignLeft,
  BookOpenCheck,
  ChevronLeft,
  ChevronRight,
  Tags,
} from "@lucide/vue";

import type {
  KnowledgeEntity,
  PassagePayload,
  TextHighlight,
} from "../../../services/api";
import { buildInlineParts } from "./adapters";
import type {
  ShijiReaderPreferences,
  ShijiReadingUnit,
} from "./types";

const props = defineProps<{
  payload: PassagePayload;
  units: ShijiReadingUnit[];
  activeUnitIndex: number;
  preferences: ShijiReaderPreferences;
}>();

const emit = defineEmits<{
  previous: [];
  next: [];
  "open-knowledge": [id: string];
  "focus-unit": [index: number];
  "reading-position": [position: number];
  "update-preferences": [next: Partial<ShijiReaderPreferences>];
}>();

const scrollContainer = ref<HTMLElement | null>(null);
const unitElements: Array<HTMLElement | undefined> = [];
let scrollFrame = 0;

const entities = computed(() => props.payload.entities ?? []);
const translationAvailable = computed(() => props.units.some((unit) => Boolean(unit.translation)));
const chapterType = computed(
  () => props.payload.reader_sequence?.chapter.type || "正文",
);
const volumeLabel = computed(() => {
  const volume = props.payload.reader_sequence?.volume;
  return volume ? `卷${volume.number}` : "当前卷篇";
});

function inlineParts(unit: ShijiReadingUnit) {
  return buildInlineParts(
    unit,
    props.payload.highlights,
    entities.value,
    props.preferences.textVariant,
  );
}

function updatePreference<Key extends keyof ShijiReaderPreferences>(
  key: Key,
  value: ShijiReaderPreferences[Key],
) {
  emit("update-preferences", { [key]: value } as Partial<ShijiReaderPreferences>);
}

function setUnitElement(element: unknown, index: number) {
  unitElements[index] = element instanceof HTMLElement ? element : undefined;
}

function handleReadingScroll() {
  if (scrollFrame) {
    return;
  }
  scrollFrame = window.requestAnimationFrame(() => {
    scrollFrame = 0;
    reportReadingPosition();
  });
}

function reportReadingPosition() {
  const container = scrollContainer.value;
  if (!container || !unitElements.length) {
    return;
  }
  const containerRect = container.getBoundingClientRect();
  const focusLine = containerRect.top + Math.min(containerRect.height * 0.38, 250);
  const anchors = unitElements
    .map((element, index) => (element ? { index, rect: element.getBoundingClientRect() } : undefined))
    .filter((item): item is { index: number; rect: DOMRect } => Boolean(item));
  if (!anchors.length) {
    return;
  }

  // At either physical edge there is not enough scroll range to place the
  // requested sentence on the normal 38% focus line. Keep the first and last
  // units authoritative instead of letting an adjacent short unit win.
  const maxScrollTop = Math.max(0, container.scrollHeight - container.clientHeight);
  if (container.scrollTop <= 2) {
    emit("focus-unit", anchors[0].index);
    emit("reading-position", 0);
    return;
  }
  if (maxScrollTop > 0 && container.scrollTop >= maxScrollTop - 2) {
    const lastIndex = anchors[anchors.length - 1].index;
    emit("focus-unit", lastIndex);
    emit("reading-position", 1);
    return;
  }

  let focusedIndex = anchors[0].index;
  let fractionalIndex = focusedIndex;
  for (let index = 0; index < anchors.length; index += 1) {
    const current = anchors[index];
    const next = anchors[index + 1];
    if (!next || focusLine < next.rect.top) {
      focusedIndex = current.index;
      const distance = Math.max(1, (next?.rect.top ?? current.rect.bottom) - current.rect.top);
      fractionalIndex = current.index + Math.min(0.999, Math.max(0, (focusLine - current.rect.top) / distance));
      break;
    }
  }

  emit("focus-unit", focusedIndex);
  emit("reading-position", fractionalIndex / Math.max(1, props.units.length - 1));
}

function annotationClass(type: string) {
  return `annotation-${type === "concept" ? "term" : type}`;
}

function annotationTitle(highlight: TextHighlight, entity?: KnowledgeEntity) {
  const status = highlight.status === "confirmed" ? "已确认" : "人类待检查";
  return `${entity?.display_name ?? highlight.label} · ${highlight.label} · ${status}`;
}

function displayText(value: string) {
  if (props.preferences.showPunctuation) {
    return value;
  }
  return value.replace(/[，。！？：；、“”‘’（）]/g, " ");
}

function scrollToTop() {
  scrollContainer.value?.scrollTo({ top: 0, behavior: "smooth" });
  emit("focus-unit", 0);
  emit("reading-position", 0);
}

function scrollToUnit(unitId: string) {
  const index = props.units.findIndex((unit) => unit.id === unitId);
  const container = scrollContainer.value;
  const element = index >= 0 ? unitElements[index] : undefined;
  if (!container || !element) {
    return;
  }
  const containerRect = container.getBoundingClientRect();
  const elementRect = element.getBoundingClientRect();
  const focusOffset = Math.min(containerRect.height * 0.38, 250);
  const top = container.scrollTop + elementRect.top - containerRect.top - focusOffset + 1;
  // Map-stage selection is a bidirectional synchronization event. A smooth
  // scroll emits many intermediate reading positions; those positions can in
  // turn advance the map away from the stage the reader explicitly selected.
  // Land on the target atomically so the next scroll report confirms the same
  // sentence instead of feeding an in-flight position back into the map.
  container.scrollTo({ top: Math.max(0, top), behavior: "auto" });
  emit("focus-unit", index);
  emit("reading-position", index / Math.max(1, props.units.length - 1));
}

watch(
  () => props.payload.passage.id,
  async () => {
    unitElements.length = 0;
    await nextTick();
    reportReadingPosition();
  },
);

onMounted(async () => {
  await nextTick();
  reportReadingPosition();
});

onBeforeUnmount(() => {
  if (scrollFrame) {
    window.cancelAnimationFrame(scrollFrame);
  }
});

defineExpose({ scrollToTop, scrollToUnit });
</script>
