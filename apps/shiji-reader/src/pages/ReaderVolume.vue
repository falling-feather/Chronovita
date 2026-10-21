<template>
  <main class="shiji-volume-route">
    <section v-if="loading" class="shiji-volume-state">
      <LoaderCircle :size="24" class="spin" />
      <strong>正在打开《史记》卷入口</strong>
      <span>先读取本卷目录，不等待全书正文。</span>
    </section>

    <section v-else-if="error" class="shiji-volume-state error-state">
      <CircleAlert :size="26" />
      <strong>本卷入口暂时无法打开</strong>
      <span>{{ error }}</span>
      <RouterLink to="/books/shiji">返回《史记》目录</RouterLink>
    </section>

    <section v-else-if="volume" class="shiji-volume-state">
      <p class="eyebrow">《史记》阅读入口</p>
      <strong>卷 {{ volume.volumeNo }} · {{ volume.title }}</strong>
      <span>{{ volume.chapterType }} · {{ volumeStatus }}</span>
      <p v-if="!volume.available || !entries.length" class="volume-pending-copy">
        本卷尚未有可打开的 application_ready 篇章；目录与其他已应用卷仍可继续阅读。
      </p>
      <RouterLink class="volume-back-link" to="/books/shiji">返回《史记》目录</RouterLink>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { CircleAlert, LoaderCircle } from "@lucide/vue";
import { useRoute, useRouter } from "vue-router";

import { getShijiReaderNavigation, getShijiVolumeEntries } from "../services/shiji-reader-client";
import { SHIJI_VOLUME_COUNT, type ShijiVolumeSummary } from "../services/shiji-reader-contracts";

const route = useRoute();
const router = useRouter();
const loading = ref(true);
const error = ref("");
const volume = ref<ShijiVolumeSummary | null>(null);
const entries = ref<Awaited<ReturnType<typeof getShijiVolumeEntries>>>([]);

const volumeNo = computed(() => {
  const raw = Array.isArray(route.params.volumeNo) ? route.params.volumeNo[0] : route.params.volumeNo;
  const parsed = Number(raw);
  return Number.isInteger(parsed) ? parsed : 0;
});

const volumeStatus = computed(() =>
  volume.value?.available
    ? "application_ready · 可进入连续阅读"
    : "尚未 application_ready",
);

watch(volumeNo, () => {
  void openVolume();
}, { immediate: true });

async function openVolume() {
  loading.value = true;
  error.value = "";
  volume.value = null;
  entries.value = [];
  if (volumeNo.value < 1 || volumeNo.value > SHIJI_VOLUME_COUNT) {
    error.value = `卷号必须在 1—${SHIJI_VOLUME_COUNT} 之间。`;
    loading.value = false;
    return;
  }

  try {
    const navigation = await getShijiReaderNavigation("shiji");
    const selected = navigation.volumes.find((item) => item.volumeNo === volumeNo.value);
    if (!selected) {
      throw new Error(`未找到卷 ${volumeNo.value} 的目录元数据。`);
    }
    volume.value = selected;
    entries.value = await getShijiVolumeEntries(volumeNo.value, "shiji");
    if (entries.value[0]) {
      await router.replace({
        name: "reader-passage",
        params: { passageId: entries.value[0].passage_id },
      });
      return;
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "卷入口加载失败";
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.shiji-volume-route {
  align-items: center;
  background: var(--paper, #f5f0e8);
  display: flex;
  min-height: 100vh;
  justify-content: center;
  padding: 32px;
}

.shiji-volume-state {
  align-items: center;
  background: var(--surface, #fffdf8);
  border: 1px solid var(--line, #d8d0c4);
  border-radius: 12px;
  box-shadow: 0 16px 40px rgb(49 41 31 / 8%);
  color: var(--ink, #2b2924);
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 520px;
  padding: 42px 48px;
  text-align: center;
}

.shiji-volume-state strong {
  font-family: var(--font-serif, serif);
  font-size: 22px;
}

.shiji-volume-state span,
.volume-pending-copy {
  color: var(--muted, #777066);
  line-height: 1.7;
}

.volume-pending-copy {
  margin: 4px 0 0;
}

.shiji-volume-state a {
  color: var(--jade-dark, #356b5b);
  text-decoration: none;
}

.shiji-volume-state a:hover {
  text-decoration: underline;
}

.volume-back-link {
  margin-top: 6px;
}

.spin {
  animation: shiji-volume-spin 1s linear infinite;
}

@keyframes shiji-volume-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
