import type { PersonCard, RagAnswer } from '../../utils/api';

export interface AskSpeaker {
  name: string;
  role: string;
  person: PersonCard | null;
}

export function answerSpeaker(
  answer: Pick<RagAnswer, 'persona_mode' | 'person_id'>,
  people: readonly PersonCard[],
): AskSpeaker {
  if (answer.persona_mode !== 'person' || !answer.person_id) {
    return { name: '课程学者', role: '不采用人物口吻', person: null };
  }
  const person = people.find((candidate) => candidate.person_id === answer.person_id) ?? null;
  return {
    name: person?.name || '课程人物',
    role: person?.role || '课程人物',
    person,
  };
}

export function studentAnswerOrigin(answer: Pick<RagAnswer, 'answer_source'>): string {
  if (answer.answer_source === 'insufficient_evidence') return '当前材料暂不能回答';
  if (answer.answer_source === 'extractive') return '据本课材料摘录';
  return '据本课材料整理';
}

export function answerBoundaryNote(
  answer: Pick<RagAnswer, 'answer_source' | 'uncertainty' | 'citations'>,
): string {
  if (answer.answer_source === 'insufficient_evidence' || answer.citations.length === 0) {
    return '本课材料还不能支持这个问题。可以缩小到人物、制度、材料年代或史实边界后再问。';
  }
  const certainty = new Set(answer.citations.map((citation) => citation.certainty));
  if (certainty.has('legend')) {
    return '这能帮助理解传说怎样讲述过去，不能直接当作事件发生时的现场记录。';
  }
  if (certainty.has('disputed')) {
    return '材料能支持一种解释，但学界仍有争议，结论需要保留余地。';
  }
  if (answer.uncertainty === 'high') {
    return '现有材料只支持有限判断，不能据此补齐人物动机或全部现场细节。';
  }
  if (answer.uncertainty === 'medium') {
    return '这能支持一种有依据的解释，材料年代、立场与细节仍需分开判断。';
  }
  return '当前材料对这项判断支持较充分，但史料记载仍不等于完整复原历史现场。';
}

export function evidenceDisclosureLabel(citationCount: number): string {
  if (citationCount <= 0) return '据何而答 · 暂无可用材料';
  return `据何而答 · ${citationCount} 条材料`;
}

export function friendlyAskError(error: unknown): string {
  const message = error instanceof Error ? error.message : '';
  if (/trusted origin|origin/i.test(message)) {
    return '课堂连接尚未建立，请刷新页面后再试。';
  }
  if (/401|登录|认证|unauthor/i.test(message)) {
    return '登录状态已经失效，请重新登录后继续提问。';
  }
  if (/fetch|network|failed to fetch|timeout|timed out|网络/i.test(message)) {
    return '暂时没有连上课堂服务。问题仍留在输入框中，可以稍后重试。';
  }
  return '这次没有得到回答，请稍后再试。';
}
