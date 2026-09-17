<template>
  <aside class="function-panel" :class="{ collapsed }">
    <template v-if="collapsed">
      <button class="rail-action" type="button" title="展开功能区" @click="$emit('toggle')">
        <PanelRightOpen :size="18" />
        <span class="sr-only">展开功能区</span>
      </button>
      <button class="rail-action primary" type="button" title="阅读设置" @click="$emit('toggle')">
        <BookOpenText :size="19" />
        <span class="sr-only">阅读设置</span>
      </button>
      <button class="rail-action" type="button" title="展示区切换" @click="$emit('toggle')">
        <MonitorUp :size="19" />
        <span class="sr-only">展示区切换</span>
      </button>
      <button class="rail-action" type="button" title="关键词百科" @click="openKnowledgePanel">
        <UserRound :size="19" />
        <span class="sr-only">关键词百科</span>
      </button>
      <span class="rail-caption">功能</span>
    </template>

    <template v-else>
      <header class="panel-heading">
        <div><strong>功能</strong><span>阅读细节与上下文</span></div>
        <button type="button" title="收起功能区" aria-label="收起功能区" @click="$emit('toggle')">
          <PanelRightClose :size="18" />
        </button>
      </header>

      <div class="function-scroll">
        <section class="function-group">
          <h2><BookOpenText :size="16" /> 阅读设置</h2>
          <label class="setting-row" v-if="versions.length">
            <span>当前版本</span>
            <select
              :value="selectedVersionId"
              @change="$emit('change-version', ($event.target as HTMLSelectElement).value)"
            >
              <option v-for="version in versions" :key="version.id" :value="version.id">
                {{ version.name }}
              </option>
            </select>
          </label>
          <label class="setting-row">
            <span>主题模式</span>
            <select
              :value="preferences.theme"
              @change="updatePreference('theme', ($event.target as HTMLSelectElement).value)"
            >
              <option value="paper">护眼纸张</option>
              <option value="white">清晰白页</option>
              <option value="night">夜间墨色</option>
            </select>
          </label>
          <label class="setting-row toggle-row">
            <span>背景纹理</span>
            <input
              type="checkbox"
              :checked="preferences.showTexture"
              @change="updatePreference('showTexture', ($event.target as HTMLInputElement).checked)"
            />
          </label>
          <div class="setting-block">
            <span>字形</span>
            <div class="mini-segmented">
              <button
                type="button"
                :class="{ active: preferences.textVariant === 'simplified' }"
                @click="updatePreference('textVariant', 'simplified')"
              >简体</button>
              <button
                type="button"
                :class="{ active: preferences.textVariant === 'traditional' }"
                @click="updatePreference('textVariant', 'traditional')"
              >繁体原文</button>
            </div>
          </div>
          <label class="setting-row toggle-row">
            <span>显示标点</span>
            <input
              type="checkbox"
              :checked="preferences.showPunctuation"
              @change="updatePreference('showPunctuation', ($event.target as HTMLInputElement).checked)"
            />
          </label>
          <label class="setting-row toggle-row" :title="translationAvailable ? '' : '本轮没有导入译文'">
            <span>逐句译文</span>
            <input
              type="checkbox"
              :checked="preferences.showTranslation && translationAvailable"
              :disabled="!translationAvailable"
              @change="updatePreference('showTranslation', ($event.target as HTMLInputElement).checked)"
            />
          </label>
          <label class="setting-row toggle-row">
            <span>内容标注</span>
            <input
              type="checkbox"
              :checked="preferences.showAnnotations"
              :disabled="!annotationAvailable"
              @change="updatePreference('showAnnotations', ($event.target as HTMLInputElement).checked)"
            />
          </label>
        </section>

        <section class="function-group">
          <h2><TextCursorInput :size="16" /> 字号与行距</h2>
          <div class="font-stepper">
            <button type="button" @click="changeFontSize(-1)">A−</button>
            <strong>{{ preferences.fontSize }} px</strong>
            <button type="button" @click="changeFontSize(1)">A＋</button>
          </div>
          <label class="range-setting">
            <span>行距 <output>{{ preferences.lineHeight.toFixed(2) }}</output></span>
            <input
              type="range"
              min="1.6"
              max="2.5"
              step="0.05"
              :value="preferences.lineHeight"
              @input="updatePreference('lineHeight', Number(($event.target as HTMLInputElement).value))"
            />
          </label>
          <label class="range-setting">
            <span>段间距 <output>{{ preferences.paragraphSpacing.toFixed(1) }} em</output></span>
            <input
              type="range"
              min="0.6"
              max="2"
              step="0.1"
              :value="preferences.paragraphSpacing"
              @input="updatePreference('paragraphSpacing', Number(($event.target as HTMLInputElement).value))"
            />
          </label>
        </section>

        <section class="function-group">
          <h2><MonitorUp :size="16" /> 展示区切换</h2>
          <label class="setting-row toggle-row">
            <span>显示展示区</span>
            <input type="checkbox" :checked="displayVisible" @change="$emit('toggle-display')" />
          </label>
          <button
            class="swap-layout-button"
            type="button"
            :aria-pressed="panesSwapped"
            @click="$emit('swap-panes')"
          >
            <ArrowLeftRight :size="17" />
            <span>
              <strong>交换阅读区与展示区</strong>
              <small>{{ panesSwapped ? "当前：展示在左，阅读在右" : "当前：阅读在左，展示在右" }}</small>
            </span>
          </button>
          <div class="display-mode-list">
            <button
              v-for="item in displayModes"
              :key="item.id"
              type="button"
              :class="{ active: displayMode === item.id }"
              @click="$emit('change-mode', item.id)"
            >
              <component :is="item.icon" :size="17" />
              <span>{{ item.label }}</span>
              <Check v-if="displayMode === item.id" :size="15" />
            </button>
          </div>
        </section>

        <section class="function-group knowledge-shortcut">
          <h2><UserRound :size="16" /> 关键词百科</h2>
          <select
            v-if="entities.length"
            :value="selectedKnowledgeId"
            @change="$emit('select-knowledge', ($event.target as HTMLSelectElement).value)"
          >
            <option v-for="entity in entities" :key="entity.id" :value="entity.id">
              {{ entity.display_name }} · {{ entity.status === "confirmed" ? "已确认" : "待检查" }}
            </option>
          </select>
          <p v-else class="function-empty-note">当前段没有关键词候选。</p>
          <button v-if="selectedEntity" class="person-preview" type="button" @click="openKnowledgePanel">
            <span>{{ selectedEntity.display_name.slice(0, 1) }}</span>
            <div><strong>{{ selectedEntity.display_name }}</strong><small>查看当前段候选资料</small></div>
            <ChevronRight :size="15" />
          </button>
        </section>
      </div>
    </template>
  </aside>
</template>

<script setup lang="ts">
import { computed } from "vue";
import {
  ArrowLeftRight,
  BookCopy,
  BookOpenText,
  Check,
  ChevronRight,
  Map,
  MonitorUp,
  PanelRightClose,
  PanelRightOpen,
  ScanSearch,
  TextCursorInput,
  UserRound,
} from "@lucide/vue";

import type { KnowledgeEntity, VersionInfo } from "../../../services/api";
import type { ShijiDisplayMode, ShijiReaderPreferences } from "./types";

const props = defineProps<{
  collapsed: boolean;
  preferences: ShijiReaderPreferences;
  displayMode: ShijiDisplayMode;
  displayVisible: boolean;
  panesSwapped: boolean;
  selectedKnowledgeId: string;
  entities: KnowledgeEntity[];
  translationAvailable: boolean;
  annotationAvailable: boolean;
  versions: VersionInfo[];
  selectedVersionId: string;
}>();

const emit = defineEmits<{
  toggle: [];
  "update-preferences": [next: Partial<ShijiReaderPreferences>];
  "change-mode": [mode: ShijiDisplayMode];
  "toggle-display": [];
  "swap-panes": [];
  "select-knowledge": [id: string];
  "change-version": [versionId: string];
}>();

const readerOnlyBuild = import.meta.env.VITE_READER_ONLY === "true";
const disableMap = import.meta.env.VITE_DISABLE_MAP === "true";
const displayModes: Array<{ id: ShijiDisplayMode; label: string; icon: typeof BookCopy }> = [
  ...(!readerOnlyBuild ? [{ id: "document" as const, label: "文献", icon: ScanSearch }] : []),
  ...(!disableMap ? [{ id: "map" as const, label: "历史地图", icon: Map }] : []),
  { id: "encyclopedia", label: "关键词百科", icon: BookCopy },
];

const selectedEntity = computed(
  () => props.entities.find((entity) => entity.id === props.selectedKnowledgeId) ?? props.entities[0],
);

function updatePreference<Key extends keyof ShijiReaderPreferences>(key: Key, value: unknown) {
  emit("update-preferences", { [key]: value } as Partial<ShijiReaderPreferences>);
}

function changeFontSize(direction: number) {
  updatePreference("fontSize", Math.min(30, Math.max(17, props.preferences.fontSize + direction)));
}

function openKnowledgePanel() {
  if (selectedEntity.value) {
    emit("select-knowledge", selectedEntity.value.id);
  }
  emit("change-mode", "encyclopedia");
}
</script>
