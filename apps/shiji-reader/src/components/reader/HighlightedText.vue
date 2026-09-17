<template>
  <div class="classical-text">
    <template v-for="segment in segments" :key="segment.key">
      <button
        v-if="segment.highlights.length"
        class="highlight-token"
        :class="segmentClass(segment.highlights[0].color)"
        :title="segment.highlights.map((item) => item.label).join(' / ')"
        type="button"
        @mouseenter="$emit('select', segment.highlights[0])"
        @click="$emit('select', segment.highlights[0])"
      >
        {{ segment.text }}
        <span>{{ segment.highlights.map((item) => item.label).join("/") }}</span>
      </button>
      <span v-else>{{ segment.text }}</span>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

import type { TextHighlight } from "../../services/api";

const props = defineProps<{
  text: string;
  highlights: TextHighlight[];
}>();

defineEmits<{
  select: [highlight: TextHighlight];
}>();

interface TextSegment {
  key: string;
  text: string;
  highlights: TextHighlight[];
}

const segments = computed<TextSegment[]>(() => {
  const grouped = new Map<string, TextHighlight[]>();
  for (const item of props.highlights) {
    const key = `${item.start}:${item.end}`;
    const existing = grouped.get(key) ?? [];
    existing.push(item);
    grouped.set(key, existing);
  }

  const ranges = [...grouped.entries()]
    .map(([key, items]) => {
      const [start, end] = key.split(":").map(Number);
      return { start, end, items };
    })
    .sort((a, b) => a.start - b.start || b.end - a.end);

  const result: TextSegment[] = [];
  let cursor = 0;
  for (const range of ranges) {
    if (range.start < cursor || range.end <= range.start) {
      continue;
    }
    if (range.start > cursor) {
      result.push({
        key: `plain-${cursor}-${range.start}`,
        text: props.text.slice(cursor, range.start),
        highlights: [],
      });
    }
    result.push({
      key: `highlight-${range.start}-${range.end}`,
      text: props.text.slice(range.start, range.end),
      highlights: range.items,
    });
    cursor = range.end;
  }
  if (cursor < props.text.length) {
    result.push({
      key: `plain-${cursor}-${props.text.length}`,
      text: props.text.slice(cursor),
      highlights: [],
    });
  }
  return result;
});

function segmentClass(color: string) {
  return `highlight-${color}`;
}
</script>
