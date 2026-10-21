<template>
  <div class="bar-chart">
    <div class="chart-legend" aria-label="状态图例">
      <span v-for="item in legend" :key="item.key">
        <i :class="`tone-${item.key}`" aria-hidden="true"></i>{{ item.label }}
      </span>
    </div>

    <div class="bar-rows">
      <button
        v-for="stage in stages"
        :key="stage.id"
        class="bar-row"
        :class="{ selected: selectedStage === stage.id }"
        type="button"
        :aria-pressed="selectedStage === stage.id"
        @click="$emit('select', selectedStage === stage.id ? '' : stage.id)"
      >
        <span class="bar-label">{{ stage.label }}</span>
        <span class="bar-track" aria-hidden="true">
          <span
            v-for="item in legend"
            v-show="stage[item.key] > 0"
            :key="item.key"
            class="bar-segment"
            :class="`tone-${item.key}`"
            :style="segmentStyle(stage, item.key)"
            :title="`${item.label}：${formatNumber(stage[item.key])} ${stage.unit}`"
          ></span>
        </span>
        <span class="bar-value">
          <strong>{{ formatRate(stage.completion_rate) }}</strong>
          <small>{{ formatNumber(stage.total) }} {{ stage.unit }}</small>
        </span>
        <span class="sr-only">{{ accessibleSummary(stage) }}</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { CSSProperties } from "vue";

import type { ProductionDashboardStage } from "../../services/api";

type StageCountKey = "passed" | "active" | "ready" | "rework" | "blocked" | "waiting";

const props = defineProps<{
  stages: ProductionDashboardStage[];
  selectedStage: string;
}>();

defineEmits<{
  select: [stageId: string];
}>();

const legend: Array<{ key: StageCountKey; label: string }> = [
  { key: "passed", label: "已通过" },
  { key: "active", label: "执行中" },
  { key: "ready", label: "待领取" },
  { key: "rework", label: "返工" },
  { key: "blocked", label: "阻塞" },
  { key: "waiting", label: "未解锁" },
];

const numberFormatter = new Intl.NumberFormat("zh-CN");

function segmentStyle(stage: ProductionDashboardStage, key: StageCountKey): CSSProperties {
  const percent = stage.total > 0 ? (stage[key] / stage.total) * 100 : 0;
  return {
    flexBasis: `${percent}%`,
    minWidth: stage[key] > 0 ? "2px" : "0",
  };
}

function formatNumber(value: number) {
  return numberFormatter.format(value);
}

function formatRate(value: number | null) {
  if (value === null) {
    return "—";
  }
  const digits = value % 1 === 0 ? 0 : 1;
  return `${value.toFixed(digits)}%`;
}

function accessibleSummary(stage: ProductionDashboardStage) {
  const details = legend
    .filter((item) => stage[item.key] > 0)
    .map((item) => `${item.label}${formatNumber(stage[item.key])}${stage.unit}`)
    .join("，");
  return `${stage.label}，完成率${formatRate(stage.completion_rate)}，${details}`;
}
</script>

<style scoped>
.bar-chart {
  display: grid;
  gap: 16px;
}

.chart-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
}

.chart-legend span {
  align-items: center;
  color: var(--muted);
  display: inline-flex;
  font-size: 10px;
  gap: 5px;
}

.chart-legend i {
  border-radius: 2px;
  height: 8px;
  width: 8px;
}

.bar-rows {
  display: grid;
  gap: 7px;
}

.bar-row {
  align-items: center;
  background: transparent;
  border: 0;
  border-radius: 4px;
  cursor: pointer;
  display: grid;
  gap: 10px;
  grid-template-columns: 104px minmax(120px, 1fr) 70px;
  min-height: 31px;
  padding: 3px 5px;
  text-align: left;
}

.bar-row:hover,
.bar-row.selected {
  background: var(--jade-wash);
}

.bar-label {
  color: var(--ink-secondary);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bar-track {
  background: var(--surface-muted);
  border: 1px solid var(--line-soft);
  border-radius: 3px;
  display: flex;
  height: 16px;
  overflow: hidden;
  width: 100%;
}

.bar-segment {
  flex-grow: 0;
  flex-shrink: 1;
  height: 100%;
}

.bar-value {
  display: grid;
  justify-items: end;
  line-height: 1.2;
}

.bar-value strong {
  color: var(--ink-secondary);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.bar-value small {
  color: var(--muted-light);
  font-size: 9px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.tone-passed {
  background: var(--jade);
}

.tone-active {
  background: #4c78a8;
}

.tone-ready {
  background: #c6923b;
}

.tone-rework {
  background: var(--cinnabar);
}

.tone-blocked {
  background: #6f3029;
}

.tone-waiting {
  background: #dfe6e3;
}

.sr-only {
  height: 1px;
  margin: -1px;
  overflow: hidden;
  padding: 0;
  position: absolute;
  width: 1px;
  clip: rect(0, 0, 0, 0);
}

@media (max-width: 560px) {
  .bar-row {
    gap: 7px;
    grid-template-columns: 78px minmax(100px, 1fr) 54px;
  }

  .bar-label {
    font-size: 10px;
  }

  .bar-value small {
    display: none;
  }
}
</style>
