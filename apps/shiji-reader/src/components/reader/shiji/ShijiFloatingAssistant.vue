<template>
  <div class="floating-tools">
    <Transition name="assistant-drawer">
      <section v-if="chatOpen" class="assistant-panel" aria-label="司马迁史记助教聊天框">
        <header>
          <div class="mentor-identity">
            <span class="mentor-sprite mentor-sprite-small" :class="`state-${mentorState}`" aria-hidden="true"></span>
            <div><strong>{{ persona === 'historian' ? '司马迁 · 教学形象' : '史料阅读学者' }}</strong><small>依据当前篇章，复用课堂 AI 配置</small></div>
          </div>
          <button type="button" aria-label="关闭史记助教" @click="chatOpen = false"><X :size="17" /></button>
        </header>

        <div class="mentor-introduction">
          <span class="mentor-sprite mentor-sprite-hero" :class="`state-${mentorState}`" aria-hidden="true"></span>
          <div>
            <p>当前阅读《{{ passageTitle }}》。可以问原文含义、人物与判断依据。</p>
            <small>无可见底色的 AI 历史启发形象，并非司马迁真实肖像。</small>
            <select v-model="persona" aria-label="助教回答视角"><option value="historian">司马迁教学视角</option><option value="scholar">现代学者视角</option></select>
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
            <div><p>{{ message.text }}</p><time>{{ message.origin || message.time }}</time>
              <details v-if="message.citations?.length"><summary>查看原句依据</summary>
                <blockquote v-for="citation in message.citations" :key="citation.quote_text">{{ citation.passage_title }}：{{ citation.quote_text }}</blockquote>
              </details>
            </div>
          </article>
        </div>

        <form class="assistant-composer" @submit.prevent="sendMessage">
          <input v-model.trim="question" type="text" maxlength="400" placeholder="就当前文字、人物或书影提问…" @focus="mentorState = 'listening'" />
          <button type="submit" :disabled="!question || loading" aria-label="发送问题"><Send :size="16" /></button>
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
import { nextTick, onBeforeUnmount, ref, watch } from "vue";
import { ArrowUp, ChevronUp, Send, X } from "@lucide/vue";
import { askReader } from "../../../services/api";

type MentorState = "listening" | "explaining" | "thinking" | "encouraging";
interface ChatMessage {
  id: number;
  role: "assistant" | "user";
  text: string;
  time: string;
  state?: MentorState;
  citations?: Array<{ passage_title: string; quote_text: string }>;
  origin?: string;
}

const props = defineProps<{ passageTitle: string; passageId: string; sentenceId?: string }>();
const emit = defineEmits<{ "scroll-top": [] }>();

const menuOpen = ref(false);
const chatOpen = ref(false);
const question = ref("");
const messageList = ref<HTMLElement | null>(null);
const mentorState = ref<MentorState>("explaining");
const loading = ref(false);
const persona = ref<'historian' | 'scholar'>('historian');
let generation = 0;

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
  if (!question.value || loading.value) {
    return;
  }
  const prompt = question.value;
  const id = ++generation;
  messages.value.push({ id: Date.now(), role: "user", text: prompt, time: "现在" });
  messages.value = messages.value.slice(-24);
  question.value = "";
  loading.value = true;
  mentorState.value = "thinking";
  await scrollMessagesToEnd();
  try {
    const answer = await askReader({ passage_id: props.passageId, sentence_id: props.sentenceId, question: prompt, persona_mode: persona.value });
    if (id !== generation) return;
    messages.value.push({
      id: Date.now() + 1, role: 'assistant', text: answer.body, time: '现在', state: 'explaining',
      citations: answer.citations, origin: answer.answer_source === 'model' ? '在线依据材料解释' : answer.model_notice || '本地材料回应',
    });
    messages.value.push({ id: Date.now() + 2, role: 'assistant', text: answer.disclaimer, time: '教学说明', state: 'listening' });
    await scrollMessagesToEnd();
  } catch {
    if (id !== generation) return;
    question.value = prompt;
    messages.value.push({ id: Date.now() + 1, role: 'assistant', text: '当前没有连上课堂助教，问题已保留。请稍后重试。', time: '现在' });
  } finally {
    if (id === generation) { loading.value = false; mentorState.value = 'listening'; }
  }
}

async function scrollMessagesToEnd() {
  await nextTick();
  messageList.value?.scrollTo({ top: messageList.value.scrollHeight, behavior: "smooth" });
}

onBeforeUnmount(() => {
  generation += 1;
});
watch(() => props.passageId, () => { generation += 1; loading.value = false; messages.value = []; question.value = ''; });
</script>
