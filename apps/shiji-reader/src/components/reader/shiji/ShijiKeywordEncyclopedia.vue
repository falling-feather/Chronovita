<template>
  <div class="encyclopedia-mode" :class="{ 'keyword-index-is-collapsed': !indexOpen }">
    <aside v-if="indexOpen" class="keyword-index">
      <div class="keyword-index-heading">
        <strong>关键词索引</strong>
        <button type="button" title="隐藏关键词索引" aria-label="隐藏关键词索引" @click="indexOpen = false">
          <PanelLeftClose :size="15" />
        </button>
      </div>
      <label class="keyword-search">
        <Search :size="15" />
        <input v-model.trim="query" type="search" placeholder="检索当前段关键词" />
      </label>
      <div class="keyword-filters">
        <button
          v-for="type in types"
          :key="type"
          type="button"
          :class="{ active: activeType === type }"
          @click="activeType = type"
        >
          {{ type }}
        </button>
      </div>
      <div class="keyword-list">
        <button
          v-for="item in filteredItems"
          :key="item.id"
          type="button"
          :class="{ active: item.id === activeItem?.id }"
          @click="$emit('select', item.id)"
        >
          <span>{{ item.display_name.slice(0, 1) }}</span>
          <div>
            <strong>{{ item.display_name }}</strong>
            <small>{{ typeLabel(item.type) }} · {{ item.status === "confirmed" ? "已确认" : "待检查" }}</small>
          </div>
          <ChevronRight :size="15" />
        </button>
        <p v-if="!filteredItems.length" class="keyword-empty">当前筛选没有关键词。</p>
      </div>
    </aside>

    <button
      v-else
      class="keyword-index-restore"
      type="button"
      title="展开关键词索引"
      aria-label="展开关键词索引"
      @click="indexOpen = true"
    >
      <PanelLeftOpen :size="16" />
      <span>关键词</span>
    </button>

    <article v-if="activeItem" class="knowledge-detail">
      <header>
        <div class="knowledge-monogram">{{ activeItem.display_name.slice(0, 1) }}</div>
        <div>
          <span>{{ typeLabel(activeItem.type) }}</span>
          <h2>{{ activeItem.display_name }}</h2>
          <p>{{ aliasText(activeItem) }}</p>
          <small class="knowledge-lifespan">
            {{ activeItem.status === "confirmed" ? "已确认条目" : "AI 候选 · 人类待检查" }}
          </small>
        </div>
      </header>
      <blockquote>{{ activeItem.summary || "当前只登记了文本锚点，尚无经过审核的百科释义。" }}</blockquote>
      <section>
        <h3>当前段信息</h3>
        <p>
          文本出现：{{ activeItem.surface || activeItem.name }}；候选置信度
          {{ Math.round(activeItem.confidence * 100) }}%。本轮不补写未审核的历史事实。
        </p>
      </section>
      <section v-if="activeItem.facts.length">
        <h3>已登记事实</h3>
        <dl class="knowledge-facts">
          <template v-for="fact in activeItem.facts" :key="fact.field">
            <dt>{{ fact.field }}</dt>
            <dd>
              {{ fact.value }}
              <small>{{ fact.status === "confirmed" ? "已确认" : "待检查" }}</small>
            </dd>
          </template>
        </dl>
      </section>
      <section v-if="linkedSources.length" class="external-knowledge">
        <div class="external-knowledge-heading">
          <h3>已登记来源</h3>
          <span>与项目释义分层</span>
        </div>
        <div class="knowledge-sources">
          <component
            :is="source.url ? 'a' : 'div'"
            v-for="source in linkedSources"
            :key="source.id"
            :href="source.url || undefined"
            :target="source.url ? '_blank' : undefined"
            :rel="source.url ? 'noreferrer' : undefined"
          >
            <span>{{ source.title }}</span>
            <small>{{ source.locator || source.source_type }}</small>
            <ExternalLink v-if="source.url" :size="13" />
          </component>
        </div>
      </section>
      <footer>
        <CircleAlert :size="15" />
        <span>候选关键词与外部来源分层展示 · 不等同于人工百科</span>
      </footer>
    </article>

    <article v-else class="knowledge-detail keyword-detail-empty">
      <CircleAlert :size="24" />
      <h2>当前段没有关键词候选</h2>
      <p>本轮不会根据当前正文临时生成百科内容。</p>
    </article>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  ChevronRight,
  CircleAlert,
  ExternalLink,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
} from "@lucide/vue";

import type { ContentSource, KnowledgeEntity } from "../../../services/api";

const props = defineProps<{
  items: KnowledgeEntity[];
  sources: ContentSource[];
  selectedId: string;
}>();

const emit = defineEmits<{ select: [id: string] }>();

const query = ref("");
const activeType = ref("全部");
const indexOpen = ref(false);
const types = ["全部", "人物", "地名", "事件", "官职 / 概念"];

const activeItem = computed(
  () => props.items.find((item) => item.id === props.selectedId) ?? props.items[0] ?? null,
);

const filteredItems = computed(() => {
  const keyword = query.value.toLocaleLowerCase();
  return props.items.filter((item) => {
    const label = typeLabel(item.type);
    const matchesType = activeType.value === "全部" || label === activeType.value;
    const matchesQuery =
      !keyword ||
      [item.name, item.display_name, item.aliases.join(" "), item.summary]
        .join(" ")
        .toLocaleLowerCase()
        .includes(keyword);
    return matchesType && matchesQuery;
  });
});

const linkedSources = computed(() => {
  if (!activeItem.value) {
    return [];
  }
  const ids = new Set(activeItem.value.source_ref_ids);
  return props.sources.filter((source) => ids.has(source.id));
});

watch(
  () => props.items,
  (items) => {
    if (items.length && !items.some((item) => item.id === props.selectedId)) {
      emit("select", items[0].id);
    }
  },
  { immediate: true },
);

function typeLabel(type: KnowledgeEntity["type"]) {
  return {
    person: "人物",
    place: "地名",
    event: "事件",
    concept: "官职 / 概念",
  }[type];
}

function aliasText(item: KnowledgeEntity) {
  return item.aliases.length ? `又称：${item.aliases.join("、")}` : item.name;
}
</script>
