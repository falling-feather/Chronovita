<template>
  <div class="trend-chart">
    <div class="trend-legend" aria-label="趋势图例">
      <span><i class="line-passed" aria-hidden="true"></i>累计通过页次</span>
      <span><i class="line-started" aria-hidden="true"></i>当日启动页次</span>
    </div>

    <svg
      class="trend-svg"
      viewBox="0 0 640 230"
      role="img"
      :aria-label="chartLabel"
      preserveAspectRatio="none"
    >
      <g class="grid-lines" aria-hidden="true">
        <line v-for="tick in yTicks" :key="tick.value" x1="48" x2="624" :y1="tick.y" :y2="tick.y" />
      </g>
      <g class="axis-labels" aria-hidden="true">
        <text v-for="tick in yTicks" :key="tick.value" x="42" :y="tick.y + 3" text-anchor="end">
          {{ compact(tick.value) }}
        </text>
        <text v-for="tick in xTicks" :key="tick.index" :x="tick.x" y="221" text-anchor="middle">
          {{ tick.label }}
        </text>
      </g>
      <path v-if="areaPath" class="passed-area" :d="areaPath" aria-hidden="true" />
      <polyline
        v-if="passedPoints"
        class="passed-line"
        :points="passedPoints"
        fill="none"
        aria-hidden="true"
      />
      <polyline
        v-if="startedPoints"
        class="started-line"
        :points="startedPoints"
        fill="none"
        aria-hidden="true"
      />
      <g v-if="lastPoint" class="last-point" aria-hidden="true">
        <circle :cx="lastPoint.x" :cy="lastPoint.y" r="4" />
        <text :x="Math.min(588, lastPoint.x + 8)" :y="Math.max(16, lastPoint.y - 9)">
          {{ compact(lastPoint.value) }}
        </text>
      </g>
    </svg>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

import type { ProductionDashboardTrendPoint } from "../../services/api";

const props = defineProps<{
  points: ProductionDashboardTrendPoint[];
}>();

const left = 48;
const right = 624;
const top = 12;
const bottom = 202;

const maxValue = computed(() => {
  const raw = Math.max(
    1,
    ...props.points.flatMap((point) => [point.cumulative_passed, point.started]),
  );
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  return Math.ceil(raw / magnitude) * magnitude;
});

const coordinates = computed(() =>
  props.points.map((point, index) => ({
    point,
    x: scaleX(index),
    passedY: scaleY(point.cumulative_passed),
    startedY: scaleY(point.started),
  })),
);

const passedPoints = computed(() =>
  coordinates.value.map((item) => `${item.x},${item.passedY}`).join(" "),
);

const startedPoints = computed(() =>
  coordinates.value.map((item) => `${item.x},${item.startedY}`).join(" "),
);

const areaPath = computed(() => {
  if (!coordinates.value.length) {
    return "";
  }
  const first = coordinates.value[0];
  const last = coordinates.value[coordinates.value.length - 1];
  const path = coordinates.value.map((item) => `${item.x} ${item.passedY}`).join(" L ");
  return `M ${first.x} ${bottom} L ${path} L ${last.x} ${bottom} Z`;
});

const yTicks = computed(() =>
  [0, 0.25, 0.5, 0.75, 1].map((ratio) => ({
    value: Math.round(maxValue.value * (1 - ratio)),
    y: top + (bottom - top) * ratio,
  })),
);

const xTicks = computed(() => {
  const last = props.points.length - 1;
  if (last < 0) {
    return [];
  }
  return [...new Set([0, Math.round(last / 2), last])].map((index) => ({
    index,
    x: scaleX(index),
    label: formatDate(props.points[index].date),
  }));
});

const lastPoint = computed(() => {
  const last = coordinates.value[coordinates.value.length - 1];
  return last
    ? { x: last.x, y: last.passedY, value: last.point.cumulative_passed }
    : null;
});

const chartLabel = computed(() => {
  const first = props.points[0];
  const last = props.points[props.points.length - 1];
  if (!first || !last) {
    return "暂无生产趋势数据";
  }
  return `${formatDate(first.date)} 至 ${formatDate(last.date)}，累计通过页次由 ${compact(first.cumulative_passed)} 变化至 ${compact(last.cumulative_passed)}`;
});

function scaleX(index: number) {
  return props.points.length <= 1
    ? left
    : left + (index / (props.points.length - 1)) * (right - left);
}

function scaleY(value: number) {
  return bottom - (value / maxValue.value) * (bottom - top);
}

function compact(value: number) {
  return new Intl.NumberFormat("zh-CN", {
    notation: value >= 10000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(value);
}

function formatDate(value: string) {
  const date = new Date(`${value}T00:00:00`);
  return `${date.getMonth() + 1}/${date.getDate()}`;
}
</script>

<style scoped>
.trend-chart {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.trend-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
}

.trend-legend span {
  align-items: center;
  color: var(--muted);
  display: inline-flex;
  font-size: 10px;
  gap: 6px;
}

.trend-legend i {
  display: inline-block;
  width: 18px;
}

.line-passed {
  border-top: 2px solid var(--jade);
}

.line-started {
  border-top: 2px dashed #6f88a1;
}

.trend-svg {
  display: block;
  height: 230px;
  overflow: visible;
  width: 100%;
}

.grid-lines line {
  stroke: var(--line-soft);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.axis-labels text,
.last-point text {
  fill: var(--muted);
  font-family: var(--font-sans);
  font-size: 9px;
}

.passed-area {
  fill: rgba(23, 106, 84, 0.08);
}

.passed-line {
  stroke: var(--jade);
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2.5;
  vector-effect: non-scaling-stroke;
}

.started-line {
  stroke: #6f88a1;
  stroke-dasharray: 5 4;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.5;
  vector-effect: non-scaling-stroke;
}

.last-point circle {
  fill: var(--surface);
  stroke: var(--jade);
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}
</style>
