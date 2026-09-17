<template>
  <main class="workbench-layout">
    <section class="panel">
      <p class="eyebrow">工作台 / OCR 校对</p>
      <h1>OCR 搭建与小样本测试</h1>
      <p class="muted">
        已接入黄善夫本《史记》第三册真实书影。竖排原图作为主识别结果，旋转结果仅用于补充召回比较。
      </p>
    </section>

    <section class="task-grid">
      <article v-for="provider in environment?.providers" :key="provider.id">
        <h2>{{ provider.name }}</h2>
        <strong>{{ provider.installed ? "可用" : "未装" }}</strong>
        <p>{{ provider.description }}</p>
        <small v-if="provider.version">
          {{ provider.version }} · {{ provider.model_profile }}
        </small>
      </article>
    </section>

    <section class="workspace-grid">
      <aside class="panel">
        <div class="section-heading">
          <h2>样页</h2>
          <span class="counter">{{ samples.length }}</span>
        </div>
        <p v-if="loading">正在加载 OCR 样页...</p>
        <p v-else-if="error" class="error-text">{{ error }}</p>
        <div v-else class="record-list">
          <button
            v-for="sample in samples"
            :key="sample.id"
            class="record-button"
            :class="{ active: selectedPageId === sample.id }"
            type="button"
            @click="selectSample(sample)"
          >
            <span>{{ sample.status }} · 第 {{ sample.page_no }} 页</span>
            <strong>{{ sample.title }}</strong>
            <small>{{ sample.source_version }}</small>
          </button>
        </div>

        <div class="mode-card" v-if="environment">
          <span>测试引擎</span>
          <div class="segmented-control three">
            <button
              v-for="provider in environment.providers"
              :key="provider.id"
              type="button"
              :class="{ active: selectedProvider === provider.id }"
              :disabled="!provider.installed"
              @click="selectedProvider = provider.id"
            >
              {{ provider.name }}
            </button>
          </div>
        </div>

        <button
          class="primary-action button-reset full-action"
          type="button"
          :disabled="running"
          @click="runSmokeTest"
        >
          {{ running ? "正在识别..." : "运行 OCR 测试" }}
        </button>
      </aside>

      <section class="panel inspector-panel" v-if="activeSample">
        <div class="section-heading">
          <div>
            <p class="eyebrow">{{ activeSample.image_path }}</p>
            <h2>{{ activeSample.title }}</h2>
          </div>
          <span class="status-badge">{{ activeSample.status }}</span>
        </div>

        <div class="ocr-preview">
          <div v-if="isRealSample" class="ocr-image-frame">
            <img
              :src="getOcrSampleImageUrl(activeSample.id)"
              :alt="activeSample.title"
              @load="handlePreviewLoad"
            />
            <div
              v-for="block in result?.blocks ?? []"
              :key="block.id"
              class="ocr-image-box"
              :class="{ uncertain: block.confidence < 0.6 }"
              :style="overlayStyle(block)"
              :title="`${block.order}. ${block.text} (${Math.round(block.confidence * 100)}%)`"
            >
              <span>{{ block.order }}</span>
            </div>
          </div>
          <div v-else class="scan-sheet">
            <div
              v-for="block in activeSample.blocks"
              :key="block.id"
              class="ocr-box"
              :style="blockStyle(block)"
            >
              {{ block.text }}
            </div>
          </div>
          <article class="note-preview">
            <h3>期望文本</h3>
            <p>{{ activeSample.expected_text || "尚未建立人工校定文本。" }}</p>
          </article>
        </div>

        <section class="ocr-result" v-if="result">
          <div class="section-heading">
            <h2>测试结果</h2>
            <span class="status-badge">{{ result.status }}</span>
          </div>
          <div class="metric-row">
            <span>文本块 {{ result.metrics.block_count }}</span>
            <span>字符 {{ result.metrics.character_count }}</span>
            <span>均值 {{ Math.round(result.metrics.average_confidence * 100) }}%</span>
            <span v-if="result.metrics.low_confidence_count !== undefined">
              低置信 {{ result.metrics.low_confidence_count }}
            </span>
            <span v-if="result.metrics.elapsed_seconds !== undefined">
              {{ result.metrics.elapsed_seconds }} 秒
            </span>
            <span>问题 {{ result.metrics.issue_count }}</span>
          </div>
          <p>{{ result.message }}</p>
          <article class="note-preview">
            <h3>识别文本</h3>
            <p>{{ result.plain_text || "当前引擎未返回识别文本。" }}</p>
          </article>
          <div class="record-list">
            <article v-for="issue in result.issues" :key="issue.type + issue.message" class="issue-row">
              <span>{{ issue.severity }} · {{ issue.type }}</span>
              <p>{{ issue.message }}</p>
            </article>
          </div>
        </section>
      </section>
    </section>

    <section class="panel" v-if="environment">
      <div class="section-heading">
        <h2>OCR 流程</h2>
        <span class="counter">{{ environment.workflow.length }}</span>
      </div>
      <div class="timeline-grid">
        <article v-for="step in environment.workflow" :key="step.id">
          <span>{{ step.status }}</span>
          <h3>{{ step.name }}</h3>
          <p>{{ step.description }}</p>
        </article>
      </div>
    </section>

    <section class="panel" v-if="environment">
      <div class="section-heading">
        <h2>错误分类</h2>
        <span class="counter">{{ environment.issue_types.length }}</span>
      </div>
      <div class="framework-grid">
        <article v-for="issue in environment.issue_types" :key="issue.id" class="module-card">
          <span>{{ issue.id }}</span>
          <h3>{{ issue.name }}</h3>
          <p>{{ issue.description }}</p>
        </article>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import {
  type OcrBlock,
  type OcrEnvironment,
  type OcrSamplePage,
  type OcrSmokeResult,
  getOcrEnvironment,
  getOcrSampleImageUrl,
  getOcrSamples,
  runOcrSmokeTest,
} from "../../services/api";

const environment = ref<OcrEnvironment | null>(null);
const samples = ref<OcrSamplePage[]>([]);
const selectedPageId = ref("");
const selectedProvider = ref("mock");
const result = ref<OcrSmokeResult | null>(null);
const previewSize = ref({ width: 1, height: 1 });
const loading = ref(true);
const running = ref(false);
const error = ref("");

const activeSample = computed(() => {
  return samples.value.find((sample) => sample.id === selectedPageId.value) ?? null;
});

onMounted(async () => {
  try {
    const [environmentPayload, samplesPayload] = await Promise.all([
      getOcrEnvironment(),
      getOcrSamples(),
    ]);
    environment.value = environmentPayload;
    samples.value = samplesPayload;
    selectedProvider.value = environmentPayload.default_provider;
    const realSample = samplesPayload.find((sample) => sample.status === "real_sample_ready");
    selectedPageId.value =
      environmentPayload.default_provider === "paddleocr" && realSample
        ? realSample.id
        : (samplesPayload[0]?.id ?? "");
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
});

async function runSmokeTest() {
  if (!selectedPageId.value || running.value) {
    return;
  }
  running.value = true;
  error.value = "";
  try {
    result.value = await runOcrSmokeTest(selectedPageId.value, selectedProvider.value);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "OCR 运行失败";
  } finally {
    running.value = false;
  }
}

function selectSample(sample: OcrSamplePage) {
  selectedPageId.value = sample.id;
  result.value = null;
  if (sample.status === "real_sample_ready") {
    const paddle = environment.value?.providers.find((provider) => provider.id === "paddleocr");
    if (paddle?.installed) {
      selectedProvider.value = "paddleocr";
    }
  } else {
    selectedProvider.value = "mock";
  }
}

const isRealSample = computed(() => activeSample.value?.status === "real_sample_ready");

function handlePreviewLoad(event: Event) {
  const image = event.target as HTMLImageElement;
  previewSize.value = {
    width: image.naturalWidth || 1,
    height: image.naturalHeight || 1,
  };
}

function overlayStyle(block: OcrBlock) {
  const [x1, y1, x2, y2] = block.bbox;
  return {
    left: `${(x1 / previewSize.value.width) * 100}%`,
    top: `${(y1 / previewSize.value.height) * 100}%`,
    width: `${((x2 - x1) / previewSize.value.width) * 100}%`,
    height: `${((y2 - y1) / previewSize.value.height) * 100}%`,
  };
}

function blockStyle(block: OcrBlock) {
  const [x1, y1, x2, y2] = block.bbox;
  return {
    left: `${x1 / 3}px`,
    top: `${y1 / 3}px`,
    width: `${Math.max((x2 - x1) / 3, 18)}px`,
    height: `${Math.max((y2 - y1) / 3, 80)}px`,
  };
}
</script>
