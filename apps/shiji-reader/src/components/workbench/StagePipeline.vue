<template>
  <div class="stage-pipeline" role="list" aria-label="八阶段生产流程">
    <button
      v-for="stage in stages"
      :key="stage.id"
      class="stage-step"
      :class="[`stage-${stageState(stage)}`, { selected: selectedStage === stage.id }]"
      type="button"
      role="listitem"
      :aria-pressed="selectedStage === stage.id"
      :title="stage.note"
      @click="$emit('select', selectedStage === stage.id ? '' : stage.id)"
    >
      <span class="stage-marker" aria-hidden="true">
        <Check v-if="stageState(stage) === 'complete'" :size="14" :stroke-width="2.5" />
        <span v-else>{{ stage.order }}</span>
      </span>
      <span class="stage-copy">
        <strong>{{ stage.label }}</strong>
        <small>
          {{ stage.completion_rate === null ? "暂无任务" : `${formatRate(stage.completion_rate)}%` }}
        </small>
      </span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { Check } from "@lucide/vue";

import type { ProductionDashboardStage } from "../../services/api";

defineProps<{
  stages: ProductionDashboardStage[];
  selectedStage: string;
}>();

defineEmits<{
  select: [stageId: string];
}>();

function stageState(stage: ProductionDashboardStage) {
  if (stage.total > 0 && stage.passed >= stage.total) {
    return "complete";
  }
  if (stage.blocked > 0 || stage.rework > 0) {
    return "attention";
  }
  if (stage.active > 0 || stage.ready > 0) {
    return "active";
  }
  return "waiting";
}

function formatRate(value: number) {
  return value % 1 === 0 ? value.toFixed(0) : value.toFixed(1);
}
</script>

<style scoped>
.stage-pipeline {
  display: grid;
  grid-template-columns: repeat(8, minmax(100px, 1fr));
  overflow-x: auto;
  padding: 2px 0 6px;
}

.stage-step {
  align-items: center;
  background: transparent;
  border: 0;
  color: var(--muted);
  cursor: pointer;
  display: grid;
  gap: 8px;
  grid-template-columns: 30px minmax(0, 1fr);
  min-width: 122px;
  padding: 8px 13px 8px 0;
  position: relative;
  text-align: left;
}

.stage-step::after {
  background: var(--line-strong);
  content: "";
  height: 1px;
  left: 30px;
  position: absolute;
  right: 0;
  top: 23px;
  z-index: 0;
}

.stage-step:last-child::after {
  display: none;
}

.stage-marker {
  align-items: center;
  background: var(--surface);
  border: 1px solid var(--line-strong);
  border-radius: 999px;
  display: inline-flex;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  height: 30px;
  justify-content: center;
  position: relative;
  width: 30px;
  z-index: 1;
}

.stage-copy {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.stage-copy strong {
  color: var(--ink-secondary);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.35;
}

.stage-copy small {
  color: var(--muted-light);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.stage-complete .stage-marker {
  background: var(--jade);
  border-color: var(--jade);
  color: #fff;
}

.stage-complete::after {
  background: var(--jade);
}

.stage-active .stage-marker {
  border-color: var(--jade);
  box-shadow: inset 0 0 0 3px var(--jade-soft);
  color: var(--jade-dark);
}

.stage-attention .stage-marker {
  background: var(--cinnabar-soft);
  border-color: var(--cinnabar);
  color: var(--cinnabar);
}

.stage-step:hover .stage-copy strong,
.stage-step.selected .stage-copy strong {
  color: var(--jade-dark);
}

.stage-step.selected {
  background: var(--jade-wash);
  border-radius: 4px;
}
</style>
