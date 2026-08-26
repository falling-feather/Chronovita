import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Input, Spin, Tooltip } from 'antd';
import {
  BookOutlined,
  CheckOutlined,
  CompassOutlined,
  EditOutlined,
  FileDoneOutlined,
  HistoryOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SendOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import type {
  GameAvailableAction,
  GameDossier,
  GameScenarioSummary,
  GameSession,
  Lesson,
  LessonScenarioRef,
} from '../../utils/api';
import { api } from '../../utils/api';
import {
  companionPortraitFor,
  companionPortraitUrl,
} from '../../features/classroom/companionPortraitAssets';
import {
  assertScenarioIdentity,
  assertSessionIdentity,
  buildGameBinding,
  clearStoredGameReference,
  persistPendingGameReference,
  readStoredGameReference,
  type GameBinding,
  type StoredGameReference,
} from './gameSessionReference';
import {
  choiceMark,
  endingTone,
  gameSceneForLesson,
  groupAdventureRounds,
  roundLabel,
} from './gamePresentation';
import { emitLearningEvent } from '../../features/classroom/learningLedger';

interface FreeInputNotice {
  kind: 'clarification_required' | 'rejected' | 'provider_unavailable';
  message: string;
  actions: GameAvailableAction[];
}

export function PublishedGamePractice({
  lesson,
  scenario,
  onOpenDossier,
}: {
  lesson: Lesson;
  scenario: LessonScenarioRef;
  onOpenDossier?: () => void;
}) {
  const binding = useMemo(
    () => buildGameBinding(lesson, scenario),
    [lesson, scenario],
  );

  if (!binding) {
    return (
      <Alert
        type="error"
        showIcon
        message="互动关卡发布信息不完整"
        description="当前课时与关卡版本无法完成一致性校验，请联系课程管理员重新发布。"
      />
    );
  }
  return (
    <PinnedGamePlayer
      key={binding.identity}
      lesson={lesson}
      binding={binding}
      onOpenDossier={onOpenDossier}
    />
  );
}

function PinnedGamePlayer({
  lesson,
  binding,
  onOpenDossier,
}: {
  lesson: Lesson;
  binding: GameBinding;
  onOpenDossier?: () => void;
}) {
  const [scenario, setScenario] = useState<GameScenarioSummary | null>(null);
  const [session, setSession] = useState<GameSession | null>(null);
  const [dossier, setDossier] = useState<GameDossier | null>(null);
  const [booting, setBooting] = useState(true);
  const [actingMode, setActingMode] = useState<'fixed' | 'free' | null>(null);
  const [freeInput, setFreeInput] = useState('');
  const [freeInputNotice, setFreeInputNotice] = useState<FreeInputNotice | null>(null);
  const [lastFeedback, setLastFeedback] = useState('');
  const [lastEventIds, setLastEventIds] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [resumed, setResumed] = useState(false);
  const [selectedTurnNo, setSelectedTurnNo] = useState(0);
  const requestGeneration = useRef(0);

  const openSession = useCallback(async (fresh = false) => {
    const generation = requestGeneration.current + 1;
    requestGeneration.current = generation;
    setBooting(true);
    setError('');
    if (fresh) {
      clearStoredGameReference(binding);
      setSession(null);
      setDossier(null);
      setFreeInput('');
      setFreeInputNotice(null);
      setLastFeedback('');
      setLastEventIds([]);
      setSelectedTurnNo(0);
    }

    const stored = fresh ? null : readStoredGameReference(binding);

    try {
      const clientRequestId = stored?.client_request_id || createRequestId('start');
      const pending: StoredGameReference = {
        schema_version: 'game-session-ref/v1',
        identity: binding.identity,
        client_request_id: clientRequestId,
      };
      if (!stored) persistPendingGameReference(binding, pending);
      const started = await api.gameStart({
        scenario_id: binding.scenario.scenario_id,
        client_request_id: clientRequestId,
        release_pin: binding.pin,
      });
      assertScenarioIdentity(started.scenario, binding);
      assertSessionIdentity(started.session, binding);
      if (stored?.session_id && started.session.session_id !== stored.session_id) {
        throw new Error('服务器恢复的学习记录与浏览器保存的会话不一致。');
      }
      if (requestGeneration.current !== generation) return;
      persistPendingGameReference(binding, {
        ...pending,
        session_id: started.session.session_id,
        scenario: started.scenario,
      });
      setScenario(started.scenario);
      setSession(started.session);
      setSelectedTurnNo(started.session.current_turn);
      setResumed(Boolean(stored?.session_id));
    } catch (openError) {
      if (requestGeneration.current !== generation) return;
      setError(errorMessage(openError));
    } finally {
      if (requestGeneration.current === generation) setBooting(false);
    }
  }, [binding]);

  useEffect(() => {
    void openSession();
    return () => { requestGeneration.current += 1; };
  }, [openSession]);

  useEffect(() => {
    if (!session || session.status === 'active' || !session.dossier_id) {
      setDossier(null);
      return undefined;
    }
    let active = true;
    api.gameDossier(session.session_id)
      .then((nextDossier) => {
        if (active) setDossier(nextDossier);
      })
      .catch(() => {
        if (active) setDossier(null);
      });
    return () => { active = false; };
  }, [session]);

  const acting = actingMode !== null;
  const rounds = useMemo(
    () => groupAdventureRounds(session?.history ?? []),
    [session?.history],
  );
  const selectedRound = rounds.find((round) => round.turnNo === selectedTurnNo)
    ?? rounds.at(-1)
    ?? null;
  const scene = gameSceneForLesson(lesson.id);

  const restoreSession = async (sessionId: string) => {
    try {
      const restored = await api.gameSession(sessionId);
      assertSessionIdentity(restored, binding);
      setSession(restored);
      setSelectedTurnNo(restored.current_turn);
    } catch {
      // Keep the last verified session visible when refresh also fails.
    }
  };

  const chooseAction = async (actionId: string) => {
    if (!session || session.status !== 'active' || acting) return;
    const actionIndex = session.available_action_ids.indexOf(actionId);
    const actionLabel = session.available_choices[actionIndex] || actionId;
    setActingMode('fixed');
    setError('');
    setFreeInputNotice(null);
    try {
      const result = await api.gameTurn(session.session_id, {
        client_action_id: createRequestId('turn'),
        action_id: actionId,
        expected_revision: session.revision,
      });
      assertSessionIdentity(result.session, binding);
      setSession(result.session);
      setSelectedTurnNo(result.session.current_turn);
      setLastFeedback(result.action_feedback);
      setLastEventIds(result.triggered_event_ids);
      emitLearningEvent({
        course_id: lesson.course_id,
        lesson_id: lesson.id,
        kind: 'decision_completed',
        title: `第 ${result.session.current_turn} 回合：${actionLabel}`,
        summary: result.action_feedback || result.session.summary || '局势已经推进。',
        metadata: {
          turn: result.session.current_turn,
          action_source: 'fixed',
          completed: result.session.status === 'completed',
        },
      });
    } catch (actionError) {
      await restoreSession(session.session_id);
      setError(errorMessage(actionError));
    } finally {
      setActingMode(null);
    }
  };

  const submitFreeInput = async () => {
    const rawInput = freeInput.trim();
    if (!session || session.status !== 'active' || acting || !rawInput) return;
    setActingMode('free');
    setError('');
    setFreeInputNotice(null);
    try {
      const response = await api.gameFreeInput(session.session_id, {
        client_action_id: createRequestId('turn'),
        raw_input: rawInput,
        expected_revision: session.revision,
      });
      if (response.kind === 'advanced') {
        if (!response.result) throw new Error('服务器没有返回已完成的回合。');
        assertSessionIdentity(response.result.session, binding);
        setSession(response.result.session);
        setSelectedTurnNo(response.result.session.current_turn);
        setFreeInput('');
        setLastFeedback(response.result.action_feedback);
        setLastEventIds(response.result.triggered_event_ids);
        emitLearningEvent({
          course_id: lesson.course_id,
          lesson_id: lesson.id,
          kind: 'decision_completed',
          title: `第 ${response.result.session.current_turn} 回合：自由陈策`,
          summary: `${rawInput}\n${response.result.action_feedback || response.result.session.summary || '局势已经推进。'}`,
          metadata: {
            turn: response.result.session.current_turn,
            action_source: 'free_input',
            completed: response.result.session.status === 'completed',
          },
        });
      } else {
        setFreeInputNotice({
          kind: response.kind,
          message: response.message,
          actions: response.available_actions,
        });
      }
    } catch (actionError) {
      await restoreSession(session.session_id);
      setError(errorMessage(actionError));
    } finally {
      setActingMode(null);
    }
  };

  if (booting && !session) {
    return (
      <div className={`chrono-adventure-loading ${scene.palette}`}>
        {scene.source960 ? <img src={scene.source960} alt="" aria-hidden="true" /> : null}
        <div><Spin /><span>正在铺开历史现场…</span></div>
      </div>
    );
  }
  if (!session || !scenario) {
    return (
      <Alert
        type="error"
        showIcon
        message="互动关卡暂时无法载入"
        description={error || '未能建立经过版本校验的学习会话。'}
        action={(
          <div className="chrono-game-error-actions">
            <Button onClick={() => void openSession()}>重试恢复</Button>
            <Button type="primary" onClick={() => void openSession(true)}>建立新记录</Button>
          </div>
        )}
      />
    );
  }

  const terminal = session.status !== 'active';
  const lastTurn = session.turns.at(-1);
  const choices = session.available_action_ids.map((actionId, index) => ({
    actionId,
    label: session.available_choices[index] || actionId,
  }));
  const outcomeTone = endingTone(dossier?.ending_id ?? session.ending_id, session.status);
  const variableById = new Map(scenario.variables.map((variable) => [variable.variable_id, variable]));
  const npcById = new Map(scenario.npcs.map((npc) => [npc.person_id, npc]));

  return (
    <section className={`chrono-adventure chrono-adventure-${scene.palette}`} aria-label="历史情景推演">
      {scene.source960 ? (
        <picture className="chrono-adventure-scene" aria-hidden="true">
          <source media="(min-width: 1000px)" srcSet={scene.source1600} />
          <img src={scene.source960} alt="" />
        </picture>
      ) : null}
      <div className="chrono-adventure-vignette" aria-hidden="true" />

      <header className="chrono-adventure-header">
        <div className="chrono-adventure-place">
          <span><CompassOutlined /> {scene.place}</span>
          <strong>{scene.title}</strong>
          <small>{scene.time} · 教学情境插画</small>
        </div>
        <div className="chrono-adventure-round-seal" aria-label={`当前第 ${session.current_turn} 回合，共 ${scenario.max_turns} 回合`}>
          <span>回合</span>
          <strong>{session.current_turn}</strong>
          <small>/ {scenario.max_turns}</small>
        </div>
        <Tooltip title="放弃当前记录并重新开始">
          <Button
            className="chrono-adventure-restart"
            icon={<ReloadOutlined />}
            loading={booting}
            disabled={acting}
            onClick={() => void openSession(true)}
          >
            重新推演
          </Button>
        </Tooltip>
      </header>

      <div className="chrono-adventure-body">
        <main className="chrono-adventure-scroll">
          <div className="chrono-adventure-scroll-edge" aria-hidden="true" />
          <div className="chrono-adventure-brief">
            <span><HistoryOutlined /> 你的身份</span>
            <strong>{scenario.student_role}</strong>
            <p>{scenario.objective}</p>
          </div>

          <nav className="chrono-adventure-turns" aria-label="回合记录">
            {rounds.map((round) => (
              <button
                key={round.turnNo}
                type="button"
                className={round.turnNo === selectedRound?.turnNo ? 'active' : ''}
                aria-current={round.turnNo === selectedRound?.turnNo ? 'step' : undefined}
                onClick={() => setSelectedTurnNo(round.turnNo)}
              >
                <span>{round.turnNo === 0 ? '引' : round.turnNo}</span>
                <small>{roundLabel(round.turnNo)}</small>
              </button>
            ))}
            {Array.from({ length: Math.max(0, scenario.max_turns - session.current_turn) }, (_, index) => (
              <span className="future" key={`future-${session.current_turn + index + 1}`}>
                {session.current_turn + index + 1}
              </span>
            ))}
          </nav>

          <article
            key={`round-${selectedRound?.turnNo ?? 0}`}
            className="chrono-adventure-narrative"
            aria-live="polite"
          >
            <header>
              <div>
                <span>{roundLabel(selectedRound?.turnNo ?? 0)}</span>
                <strong>{selectedRound?.turnNo === session.current_turn ? '此刻局势' : '回看议事记录'}</strong>
              </div>
              {selectedRound && selectedRound.turnNo !== session.current_turn ? (
                <button type="button" onClick={() => setSelectedTurnNo(session.current_turn)}>回到当前</button>
              ) : null}
            </header>
            {selectedRound?.player ? (
              <blockquote>
                <span>你的陈策</span>
                <p>{selectedRound.player}</p>
              </blockquote>
            ) : null}
            <div className="chrono-adventure-narrator">
              <BookOutlined />
              <p>{selectedRound?.narration || session.summary}</p>
            </div>
            {acting ? (
              <div className="chrono-adventure-thinking">
                <Spin size="small" />
                <span>{actingMode === 'free' ? '正在理解你的陈策，并核对本轮规则…' : '正在结算局势与人物反馈…'}</span>
              </div>
            ) : null}
          </article>

          {selectedRound?.turnNo === session.current_turn && (lastFeedback || lastEventIds.length > 0) ? (
            <div className="chrono-adventure-feedback">
              <strong>本轮回响</strong>
              <span>{lastFeedback || '局势已按课堂规则更新。'}</span>
              {lastEventIds.length > 0 ? <small>触发 {lastEventIds.length} 项情境事件</small> : null}
            </div>
          ) : null}

          {error ? (
            <Alert
              className="chrono-adventure-alert"
              type="warning"
              showIcon
              message={error}
              closable
              onClose={() => setError('')}
            />
          ) : null}

          {terminal ? (
            <section className={`chrono-adventure-ending ${outcomeTone}`}>
              <div className="chrono-adventure-ending-seal">
                {outcomeTone === 'positive' ? <CheckOutlined /> : <HistoryOutlined />}
              </div>
              <div className="chrono-adventure-ending-copy">
                <span>{outcomeLabel(outcomeTone)}</span>
                <h3>{dossier?.title || '六轮已尽，史官落笔'}</h3>
                <p>{session.summary}</p>
                {dossier?.major_costs.length ? (
                  <ul>{dossier.major_costs.slice(0, 3).map((cost) => <li key={cost}>{cost}</li>)}</ul>
                ) : null}
              </div>
              <div className="chrono-adventure-ending-actions">
                {session.dossier_id && onOpenDossier ? (
                  <Button type="primary" icon={<FileDoneOutlined />} onClick={onOpenDossier}>
                    整理史官卷宗
                  </Button>
                ) : null}
                <Button icon={<ReloadOutlined />} onClick={() => void openSession(true)}>重新推演</Button>
              </div>
            </section>
          ) : (
            <section className="chrono-adventure-decisions" aria-label="本轮行动">
              <header>
                <div>
                  <span>第 {session.current_turn + 1} 回合</span>
                  <h3>此刻，你准备如何行动？</h3>
                </div>
                <small>预设行动可离线完成</small>
              </header>
              <div className="chrono-adventure-choices">
                {choices.map((choice, index) => (
                  <button
                    key={choice.actionId}
                    type="button"
                    disabled={acting}
                    onClick={() => void chooseAction(choice.actionId)}
                  >
                    <span>{choiceMark(index)}</span>
                    <strong>{choice.label}</strong>
                    <small>按课堂规则结算</small>
                  </button>
                ))}
              </div>

              <form
                className="chrono-adventure-free-input"
                onSubmit={(event) => {
                  event.preventDefault();
                  void submitFreeInput();
                }}
              >
                <label htmlFor="chrono-game-free-action">
                  <EditOutlined />
                  <span><strong>自行陈策</strong><small>用自己的话提出行动</small></span>
                </label>
                <Input.TextArea
                  id="chrono-game-free-action"
                  aria-label="自拟历史行动"
                  autoSize={{ minRows: 2, maxRows: 4 }}
                  disabled={acting}
                  maxLength={400}
                  placeholder="例如：先让各聚落共同标出低地，再决定从哪里分流……"
                  showCount
                  value={freeInput}
                  onChange={(event) => setFreeInput(event.target.value)}
                  onPressEnter={(event) => {
                    if (!event.shiftKey) {
                      event.preventDefault();
                      void submitFreeInput();
                    }
                  }}
                />
                <Button
                  type="primary"
                  htmlType="submit"
                  icon={<SendOutlined />}
                  loading={actingMode === 'free'}
                  disabled={acting || !freeInput.trim()}
                >
                  呈上议策
                </Button>
                <p>自由陈策只会在本轮可用行动与已审校史实边界内理解；无法确认时不会消耗回合。</p>
              </form>

              {freeInputNotice ? (
                <div className={`chrono-adventure-free-notice ${freeInputNotice.kind}`}>
                  <strong>{freeInputNotice.kind === 'clarification_required' ? '请再说具体一些' : '本轮尚未推进'}</strong>
                  <p>{freeInputNotice.message}</p>
                  {freeInputNotice.actions.length > 0 ? (
                    <div>
                      <span>也可以直接采用：</span>
                      {freeInputNotice.actions.slice(0, 4).map((action) => (
                        <button
                          key={action.action_id}
                          type="button"
                          disabled={acting}
                          onClick={() => void chooseAction(action.action_id)}
                        >
                          {action.label}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </section>
          )}
        </main>

        <aside className="chrono-adventure-council" aria-label="局势与人物">
          <div className="chrono-adventure-save-state">
            <SafetyCertificateOutlined />
            <span>
              <strong>{resumed ? '已续接上次议事' : '回合记录已保存'}</strong>
              <small>退出页面后可继续</small>
            </span>
          </div>

          <section className="chrono-adventure-state">
            <header><span>局势六象</span><small>课堂模型</small></header>
            {scenario.variables.map((variable) => {
              const value = session.current_state[variable.variable_id] ?? variable.initial;
              const change = lastTurn?.state_changes.find((item) => item.variable_id === variable.variable_id);
              const range = variable.maximum - variable.minimum;
              const rawPercent = range > 0
                ? Math.max(0, Math.min(100, ((value - variable.minimum) / range) * 100))
                : 0;
              const percent = isLowerBetter(variable.label) ? 100 - rawPercent : rawPercent;
              return (
                <div key={variable.variable_id} title={variable.description}>
                  <span>{variable.label}</span>
                  <strong>{formatNumber(value)}</strong>
                  <em className={change && change.delta < 0 ? 'negative' : 'positive'}>
                    {change ? formatDelta(change.delta) : '—'}
                  </em>
                  <i><b style={{ width: `${percent}%` }} /></i>
                </div>
              );
            })}
          </section>

          {scenario.npcs.length > 0 ? (
            <section className="chrono-adventure-people">
              <header><span><TeamOutlined /> 议事席</span><small>信任</small></header>
              <div>
                {session.npc_states.map((npcState) => {
                  const npc = npcById.get(npcState.person_id);
                  const portrait = npc ? companionPortraitFor(lesson.id, { name: npc.display_name }) : null;
                  const change = lastTurn?.npc_changes.find((item) => item.person_id === npcState.person_id);
                  return (
                    <article key={npcState.person_id}>
                      {portrait ? (
                        <picture>
                          <source media="(min-resolution: 1.5dppx)" srcSet={companionPortraitUrl(portrait, 512)} />
                          <img src={companionPortraitUrl(portrait, 256)} alt={portrait.alt} loading="lazy" />
                        </picture>
                      ) : <span className="chrono-adventure-person-fallback">史</span>}
                      <div>
                        <strong>{npc?.display_name || npcState.person_id}</strong>
                        <small>{npc?.role}</small>
                      </div>
                      <b>{formatNumber(npcState.trust)}</b>
                      {change ? (
                        <em className={change.trust_after < change.trust_before ? 'negative' : 'positive'}>
                          {formatDelta(change.trust_after - change.trust_before)}
                        </em>
                      ) : null}
                    </article>
                  );
                })}
              </div>
            </section>
          ) : null}

          {lastTurn && lastTurn.state_changes.length > 0 ? (
            <section className="chrono-adventure-deltas">
              <header>本回合变化</header>
              <div>
                {lastTurn.state_changes.map((change) => (
                  <span key={change.variable_id}>
                    {variableById.get(change.variable_id)?.label || change.variable_id}
                    <b className={change.delta < 0 ? 'negative' : 'positive'}>{formatDelta(change.delta)}</b>
                  </span>
                ))}
              </div>
            </section>
          ) : null}
        </aside>
      </div>
    </section>
  );
}

function outcomeLabel(tone: 'positive' | 'mixed' | 'negative'): string {
  if (tone === 'positive') return '平衡路径 · 阶段成功';
  if (tone === 'negative') return '推演结局 · 需要复盘';
  return '推演结局 · 成果与代价并存';
}

function isLowerBetter(label: string): boolean {
  return /(风险|压力|阻力|损耗|伤亡)/.test(label);
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function formatDelta(value: number): string {
  if (value === 0) return '±0';
  return `${value > 0 ? '+' : ''}${formatNumber(value)}`;
}

function createRequestId(kind: 'start' | 'turn'): string {
  const randomPart = typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `web-${kind}-${randomPart}`;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message.replace(/^\d{3}\s+/, '') : '请求失败，请稍后重试。';
}
