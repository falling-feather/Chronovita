<template>
  <header class="top-bar">
    <div class="brand-group">
      <RouterLink class="brand" to="/books/shiji" aria-label="史海史记目录">
        <span class="brand-seal">史</span><strong>史海</strong>
      </RouterLink>
      <nav class="top-navigation" aria-label="主功能区">
        <RouterLink to="/books/shiji">典籍</RouterLink>
        <RouterLink class="active" to="/books/shiji">阅读</RouterLink>
        <RouterLink v-if="!readerOnlyBuild" to="/workbench">工作台</RouterLink>
      </nav>
    </div>

    <div class="current-work" aria-label="当前篇章">
      <span></span><strong>史记 · {{ chapterTitle }}</strong><span></span>
    </div>

    <div class="top-utilities">
      <button type="button" aria-label="搜索" title="搜索" @click="$emit('announce', '全书搜索将在后续接入《史记》索引。')">
        <Search :size="18" />
      </button>
      <button type="button" aria-label="收藏当前段落" title="收藏" @click="toggleBookmark">
        <Bookmark :size="18" :fill="bookmarked ? 'currentColor' : 'none'" />
      </button>
      <button type="button" aria-label="阅读历史" title="阅读历史" @click="$emit('announce', '阅读历史将在后续版本接入。')">
        <History :size="18" />
      </button>
      <button type="button" aria-label="阅读设置" title="阅读设置" @click="$emit('open-settings')">
        <Settings2 :size="18" />
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { Bookmark, History, Search, Settings2 } from "@lucide/vue";

defineProps<{ chapterTitle: string }>();
const emit = defineEmits<{ announce: [message: string]; "open-settings": [] }>();
const bookmarked = ref(false);
const readerOnlyBuild = import.meta.env.VITE_READER_ONLY === "true";

function toggleBookmark() {
  bookmarked.value = !bookmarked.value;
  emit("announce", bookmarked.value ? "已在当前浏览会话收藏本段。" : "已取消当前浏览会话收藏。");
}
</script>
