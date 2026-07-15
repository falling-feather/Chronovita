import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Input, Progress, Spin, Tag, Tooltip } from 'antd';
import {
  EditOutlined,
  HistoryOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SendOutlined,
} from '@ant-design/icons';
import type {
  GameScenarioSummary,
  GameSession,
  Lesson,
  LessonScenarioRef,
  ScenarioReleasePin,
} from '../../utils/api';
import { api } from '../../utils/api';
import { loadJSON, removeKey, saveJSON } from '../../utils/storage';

interface GameBinding {
  scenario: LessonScenarioRef;
  pin: ScenarioReleasePin;
  identity: string;
  storageKey: string;
}

interface StoredGameReference {
  schema_version: 'game-session-ref/v1';
  identity: string;
  client_request_id: string;
  session_id?: string;
  scenario?: GameScenarioSummary;
}

interface FreeInputNotice {
  kind: 'clarification_required' | 'rejected' | 'provider_unavailable';
  message: string;
}

export function PublishedGamePractice({
  lesson,
  scenario,
}: {
  lesson: Lesson;
  scenario: LessonScenarioRef;
}) {
  const binding = useMemo(
    () => buildBinding(lesson, scenario),
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
  return <PinnedGamePlayer key={binding.identity} lesson={lesson} binding={binding} />;
}

function PinnedGamePlayer({ lesson, binding }: { lesson: Lesson; binding: GameBinding }) {
  const [scenario, setScenario] = useState<GameScenarioSummary | null>(null);
  const [session, setSession] = useState<GameSession | null>(null);
  const [booting, setBooting] = useState(true);
  const [actingMode, setActingMode] = useState<'fixed' | 'free' | null>(null);
  const [freeInput, setFreeInput] = useState('');
  const [freeInputNotice, setFreeInputNotice] = useState<FreeInputNotice | null>(null);
  const [error, setError] = useState('');
  const [resumed, setResumed] = useState(false);
  const requestGeneration = useRef(0);
  const stageRef = useRef<HTMLDivElement>(null);

  const openSession = useCallback(async (fresh = false) => {
    const generation = requestGeneration.current + 1;
    requestGeneration.current = generation;
    setBooting(true);
    setError('');
    if (fresh) {
      setFreeInput('');
      setFreeInputNotice(null);
    }

    let stored = fresh
      ? null
      : loadJSON<StoredGameReference | null>(binding.storageKey, null);
    if (!isStoredReference(stored, binding.identity)) {
      removeKey(binding.storageKey);
      stored = null;
    }

    try {
      const clientRequestId = stored?.client_request_id || createRequestId('start');
      const pending: StoredGameReference = {
        schema_version: 'game-session-ref/v1',
        identity: binding.identity,
        client_request_id: clientRequestId,
      };
      if (!stored) persistPendingReference(binding.storageKey, pending);
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
      saveJSON<StoredGameReference>(binding.storageKey, {
        ...pending,
        session_id: started.session.session_id,
        scenario: started.scenario,
      });
      setScenario(started.scenario);
      setSession(started.session);
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
    if (stageRef.current) stageRef.current.scrollTop = stageRef.current.scrollHeight;
  }, [session?.history.length]);

  const acting = actingMode !== null;

  const restoreSession = async (sessionId: string) => {
    try {
      const restored = await api.gameSession(sessionId);
      assertSessionIdentity(restored, binding);
      setSession(restored);
    } catch {
      // Keep the last verified session visible when refresh also fails.
    }
  };

  const chooseAction = async (actionId: string) => {
    if (!session || session.status !== 'active' || acting) return;
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
        setFreeInput('');
      } else {
        setFreeInputNotice({ kind: response.kind, message: response.message });
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
      <div className="chrono-game-loading">
        <div>
          <Spin />
          <span>正在载入历史现场...</span>
        </div>
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
        action={<Button onClick={() => void openSession()}>重试</Button>}
      />
    );
  }

  const progress = Math.min(100, Math.round((session.current_turn / scenario.max_turns) * 100));
  const choices = session.available_action_ids.map((actionId, index) => ({
    actionId,
    label: session.available_choices[index] || actionId,
  }));
  const terminal = session.status !== 'active';

  return (
    <div className="chrono-game-layout">
      <section className="chrono-game-main" aria-label="历史抉择关卡">
        <header className="chrono-game-header">
          <div className="chrono-game-heading">
            <Tag color="gold" icon={<HistoryOutlined />}>历史抉择</Tag>
            <h2>{scenario.title}</h2>
            <span>{lesson.era || lesson.unit}</span>
          </div>
          <Tooltip title="开始一段新的关卡记录">
            <Button
              icon={<ReloadOutlined />}
              loading={booting}
              disabled={acting}
              onClick={() => void openSession(true)}
            >
              重新开始
            </Button>
          </Tooltip>
        </header>

        <div className="chrono-game-objective">
          <span>你的身份</span>
          <strong>{scenario.student_role}</strong>
          <p>{scenario.objective}</p>
        </div>

        <div ref={stageRef} className="chrono-game-history" aria-live="polite">
          {session.history.map((message, index) => (
            <div
              className={`chrono-game-message chrono-game-message-${message.role}`}
              key={`${message.turn_no}-${message.role}-${index}`}
            >
              {message.role === 'player' ? <span>我的行动</span> : null}
              <p>{message.text}</p>
            </div>
          ))}
          {acting ? (
            <div className="chrono-game-thinking">
              <Spin size="small" />
              {actingMode === 'free' ? '正在理解并推演...' : '规则正在推演...'}
            </div>
          ) : null}
        </div>

        {error ? <Alert type="warning" showIcon message={error} closable onClose={() => setError('')} /> : null}

        {terminal ? (
          <Alert
            type={session.status === 'completed' ? 'success' : 'warning'}
            showIcon
            message={session.status === 'completed' ? '本次推演已完成' : '本次推演已结束'}
            description={session.summary}
          />
        ) : (
          <div className="chrono-game-action-panel">
            <div className="chrono-game-actions">
              {choices.map((choice, index) => (
                <Button
                  key={choice.actionId}
                  disabled={acting}
                  onClick={() => void chooseAction(choice.actionId)}
                >
                  <span>{index + 1}</span>
                  {choice.label}
                </Button>
              ))}
            </div>
            <form
              className="chrono-game-free-input"
              onSubmit={(event) => {
                event.preventDefault();
                void submitFreeInput();
              }}
            >
              <label htmlFor="chrono-game-free-action">
                <EditOutlined />
                自拟行动
              </label>
              <div>
                <Input.TextArea
                  id="chrono-game-free-action"
                  aria-label="自拟历史行动"
                  autoSize={{ minRows: 1, maxRows: 3 }}
                  disabled={acting}
                  maxLength={400}
                  placeholder="写下你想采取的行动"
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
                  提交
                </Button>
              </div>
            </form>
            {freeInputNotice ? (
              <Alert
                className="chrono-game-free-notice"
                type={freeInputNotice.kind === 'clarification_required' ? 'info' : 'warning'}
                showIcon
                closable
                message={freeInputNotice.message}
                onClose={() => setFreeInputNotice(null)}
              />
            ) : null}
          </div>
        )}
      </section>

      <aside className="chrono-game-aside">
        <div className="chrono-game-progress">
          <div>
            <span>推演进度</span>
            <strong>{session.current_turn} / {scenario.max_turns}</strong>
          </div>
          <Progress percent={progress} showInfo={false} strokeColor="#9C2F2F" />
        </div>
        <div className="chrono-game-status">
          <SafetyCertificateOutlined />
          <div>
            <strong>{resumed ? '已恢复学习记录' : '学习记录已保存'}</strong>
            <span>发布 #{scenario.release_no}</span>
          </div>
        </div>
        <div className="chrono-game-keywords">
          <h3>本课关键词</h3>
          <div>
            {lesson.keywords.map((keyword) => <Tag key={keyword.word}>{keyword.word}</Tag>)}
          </div>
        </div>
      </aside>
    </div>
  );
}

function buildBinding(lesson: Lesson, scenario: LessonScenarioRef): GameBinding | null {
  if (
    !lesson.release_id
    || typeof lesson.release_no !== 'number'
    || !lesson.release_checksum
    || typeof lesson.content_version !== 'number'
    || lesson.content_version < 1
    || !lesson.content_checksum
    || scenario.scenario_version < 1
    || !scenario.checksum
    || lesson.primary_scenario_id !== scenario.scenario_id
  ) {
    return null;
  }
  const pin: ScenarioReleasePin = {
    release_id: lesson.release_id,
    release_no: lesson.release_no,
    release_checksum: lesson.release_checksum,
    course_id: lesson.course_id,
    lesson_id: lesson.id,
    course_content_version: lesson.content_version,
    course_checksum: lesson.content_checksum,
    scenario_version: scenario.scenario_version,
    scenario_checksum: scenario.checksum,
  };
  const identity = [
    pin.release_id,
    pin.release_no,
    pin.release_checksum,
    pin.course_id,
    pin.lesson_id,
    pin.course_content_version,
    pin.course_checksum,
    scenario.scenario_id,
    pin.scenario_version,
    pin.scenario_checksum,
  ].join('|');
  const storageKey = `game-session.v1.${[
    pin.course_id,
    pin.lesson_id,
    pin.release_id,
    scenario.scenario_id,
    String(pin.scenario_version),
    pin.course_checksum.slice(0, 12),
    pin.scenario_checksum.slice(0, 12),
  ].map(encodeURIComponent).join('.')}`;
  return { scenario, pin, identity, storageKey };
}

function assertSessionIdentity(session: GameSession, binding: GameBinding): void {
  const actual = [
    session.course_id,
    session.lesson_id,
    session.course_content_version,
    session.course_checksum,
    session.scenario_id,
    session.scenario_version,
    session.scenario_checksum,
  ];
  const expected = [
    binding.pin.course_id,
    binding.pin.lesson_id,
    binding.pin.course_content_version,
    binding.pin.course_checksum,
    binding.scenario.scenario_id,
    binding.pin.scenario_version,
    binding.pin.scenario_checksum,
  ];
  if (actual.some((value, index) => value !== expected[index])) {
    throw new Error('服务器返回的学习会话与当前课时版本不一致。');
  }
}

function assertScenarioIdentity(scenario: GameScenarioSummary, binding: GameBinding): void {
  if (
    scenario.audience !== 'published'
    || scenario.release_id !== binding.pin.release_id
    || scenario.release_no !== binding.pin.release_no
    || scenario.release_checksum !== binding.pin.release_checksum
    || scenario.course_id !== binding.pin.course_id
    || scenario.lesson_id !== binding.pin.lesson_id
    || scenario.scenario_id !== binding.scenario.scenario_id
    || scenario.scenario_version !== binding.pin.scenario_version
    || scenario.scenario_checksum !== binding.pin.scenario_checksum
  ) {
    throw new Error('服务器返回的互动关卡与当前课时发布版本不一致。');
  }
}

function isStoredReference(
  value: StoredGameReference | null,
  identity: string,
): value is StoredGameReference {
  return Boolean(
    value
    && value.schema_version === 'game-session-ref/v1'
    && value.identity === identity
    && typeof value.client_request_id === 'string'
    && value.client_request_id.length > 0,
  );
}

function persistPendingReference(
  storageKey: string,
  reference: StoredGameReference,
): void {
  saveJSON(storageKey, reference);
  const persisted = loadJSON<StoredGameReference | null>(storageKey, null);
  if (
    !isStoredReference(persisted, reference.identity)
    || persisted.client_request_id !== reference.client_request_id
    || persisted.session_id !== reference.session_id
  ) {
    throw new Error('浏览器无法保存学习记录，请允许本站使用本地存储后重试。');
  }
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
