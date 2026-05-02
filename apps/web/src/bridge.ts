const KEYS = {
  recallToSandbox: 'chrono.bridge.recall->sandbox',
  sandboxToAgent: 'chrono.bridge.sandbox->agent',
  agentToCanvas: 'chrono.bridge.agent->canvas',
} as const;

export interface RecallToSandboxPayload {
  chapter_id: string;
  title: string;
  keywords: string[];
  history_context: string;
}

export interface SandboxToAgentPayload {
  scenario_title: string;
  ending_summary: string;
  keywords: string[];
}

export interface AgentToCanvasPayload {
  topic: string;
  thinker_text: string;
  historian_text: string;
  citations: { title: string; excerpt: string }[];
}

export function setRecallToSandbox(p: RecallToSandboxPayload) {
  sessionStorage.setItem(KEYS.recallToSandbox, JSON.stringify(p));
}
export function takeRecallToSandbox(): RecallToSandboxPayload | null {
  const raw = sessionStorage.getItem(KEYS.recallToSandbox);
  if (!raw) return null;
  sessionStorage.removeItem(KEYS.recallToSandbox);
  try {
    return JSON.parse(raw) as RecallToSandboxPayload;
  } catch {
    return null;
  }
}

export function setSandboxToAgent(p: SandboxToAgentPayload) {
  sessionStorage.setItem(KEYS.sandboxToAgent, JSON.stringify(p));
}
export function takeSandboxToAgent(): SandboxToAgentPayload | null {
  const raw = sessionStorage.getItem(KEYS.sandboxToAgent);
  if (!raw) return null;
  sessionStorage.removeItem(KEYS.sandboxToAgent);
  try {
    return JSON.parse(raw) as SandboxToAgentPayload;
  } catch {
    return null;
  }
}

export function setAgentToCanvas(p: AgentToCanvasPayload) {
  sessionStorage.setItem(KEYS.agentToCanvas, JSON.stringify(p));
}
export function takeAgentToCanvas(): AgentToCanvasPayload | null {
  const raw = sessionStorage.getItem(KEYS.agentToCanvas);
  if (!raw) return null;
  sessionStorage.removeItem(KEYS.agentToCanvas);
  try {
    return JSON.parse(raw) as AgentToCanvasPayload;
  } catch {
    return null;
  }
}
