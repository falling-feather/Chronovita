<template>
  <div class="floating-tools">
    <Transition name="assistant-drawer">
      <section v-if="chatOpen" class="assistant-panel" aria-label="司马迁史记助教聊天框">
        <header>
          <div class="mentor-identity">
            <span class="mentor-sprite mentor-sprite-small" :class="`state-${mentorState}`" aria-hidden="true"></span>
            <div><strong>司马迁 · 史记助教</strong><small>前端预留 · 尚未接入模型</small></div>
          </div>
          <button type="button" aria-label="关闭史记助教" @click="chatOpen = false"><X :size="17" /></button>
        </header>

        <div class="mentor-introduction">
          <span class="mentor-sprite mentor-sprite-hero" :class="`state-${mentorState}`" aria-hidden="true"></span>
          <div>
            <p>当前阅读《{{ passageTitle }}》。我可以在正式接入后结合原文、真实书影与已审核资料回答。</p>
            <small>无可见底色的 AI 历史启发形象，并非司马迁真实肖像。</small>
          </div>
        </div>

        <div ref="messageList" class="assistant-messages" aria-live="polite">
          <article v-for="message in messages" :key="message.id" :class="message.role">
            <span
              v-if="message.role === 'assistant'"
              class="mentor-sprite mentor-sprite-message"
              :class="`state-${message.state ?? 'explaining'}`"
              aria-hidden="true"
            ></span>
            <div><p>{{ message.text }}</p><time>{{ message.time }}</time></div>
          </article>
        </div>

        <form class="assistant-composer" @submit.prevent="sendMessage">
          <input v-model.trim="question" type="text" placeholder="就当前文字、人物或书影提问…" @focus="mentorState = 'listening'" />
          <button type="submit" :disabled="!question" aria-label="发送问题"><Send :size="16" /></button>
        </form>
      </section>
    </Transition>

    <Transition name="quick-menu">
      <div v-if="menuOpen && !chatOpen" class="floating-menu">
        <button type="button" @click="openChat">
          <span class="mentor-sprite mentor-sprite-menu state-explaining" aria-hidden="true"></span>
          <span>司马迁助教</span>
        </button>
        <button type="button" @click="scrollTop"><ArrowUp :size="17" /><span>回到顶部</span></button>
      </div>
    </Transition>

    <button
      class="floating-launcher"
      type="button"
      :aria-expanded="menuOpen || chatOpen"
      aria-label="快捷功能"
      title="快捷功能"
      @click="toggleLauncher"
    >
      <span class="mentor-sprite mentor-sprite-launcher state-encouraging" aria-hidden="true"></span>
      <span>{{ chatOpen ? "司马迁助教" : "快捷功能" }}</span>
      <X v-if="menuOpen || chatOpen" :size="15" />
      <ChevronUp v-else :size="15" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref } from "vue";
import { ArrowUp, ChevronUp, Send, X } from "@lucide/vue";

type MentorState = "listening" | "explaining" | "thinking" | "encouraging";
interface ChatMessage {
  id: number;
  role: "assistant" | "user";
  text: string;
  time: string;
  state?: MentorState;
}

defineProps<{ passageTitle: string }>();
const emit = defineEmits<{ "scroll-top": [] }>();

const menuOpen = ref(false);
const chatOpen = ref(false);
const question = ref("");
const messageList = ref<HTMLElement | null>(null);
const mentorState = ref<MentorState>("explaining");
let responseTimer: ReturnType<typeof setTimeout> | undefined;
let resetTimer: ReturnType<typeof setTimeout> | undefined;

const messages = ref<ChatMessage[]>([
  {
    id: 1,
    role: "assistant",
    text: "本轮只使用《史记》成品正文与既有候选层，内容仍待人工检查。正式回答时会逐项标明出处。",
    time: "刚刚",
    state: "explaining",
  },
]);

function toggleLauncher() {
  if (chatOpen.value) {
    chatOpen.value = false;
    return;
  }
  menuOpen.value = !menuOpen.value;
}

function openChat() {
  menuOpen.value = false;
  chatOpen.value = true;
  mentorState.value = "explaining";
}

function scrollTop() {
  menuOpen.value = false;
  emit("scroll-top");
}

async function sendMessage() {
  if (!question.value) {
    return;
  }
  messages.value.push({ id: Date.now(), role: "user", text: question.value, time: "现在" });
  question.value = "";
  mentorState.value = "thinking";
  await scrollMessagesToEnd();
  if (responseTimer) {
    clearTimeout(responseTimer);
  }
  responseTimer = window.setTimeout(async () => {
    messages.value.push({
      id: Date.now() + 1,
      role: "assistant",
      text: "助教模型尚未接入。当前页面只演示对话结构；不会把待审正文或关键词候选包装成历史结论。",
      time: "现在",
      state: "encouraging",
    });
    mentorState.value = "encouraging";
    await scrollMessagesToEnd();
    resetTimer = window.setTimeout(() => { mentorState.value = "listening"; }, 1800);
  }, 520);
}

async function scrollMessagesToEnd() {
  await nextTick();
  messageList.value?.scrollTo({ top: messageList.value.scrollHeight, behavior: "smooth" });
}

onBeforeUnmount(() => {
  if (responseTimer) clearTimeout(responseTimer);
  if (resetTimer) clearTimeout(resetTimer);
});
</script>
