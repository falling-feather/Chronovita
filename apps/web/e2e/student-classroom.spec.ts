import {
  expect,
  test,
  type Browser,
  type Page,
  type Route,
  type TestInfo,
} from '@playwright/test';

interface FlagshipLesson {
  lessonId: 'L101' | 'L103';
  title: string;
  freeInput: string;
  question: string;
  personMode: boolean;
}

const COURSE_ID = 'C-prequin-state';
const USER_PASSWORD = process.env.CHRONO_E2E_USER_PASSWORD || '';
const ADMIN_USERNAME = process.env.CHRONO_E2E_ADMIN_USERNAME || 'classroom.admin';
const ADMIN_PASSWORD = process.env.CHRONO_E2E_ADMIN_PASSWORD || '';
const BASE_URL = (process.env.CHRONO_E2E_BASE_URL || 'http://127.0.0.1:8765').replace(/\/$/, '');

const FLAGSHIPS: FlagshipLesson[] = [
  {
    lessonId: 'L101',
    title: '大禹治水',
    freeInput: '踏勘',
    question: '积石峡洪水为什么不能直接证明大禹和夏朝？',
    personMode: false,
  },
  {
    lessonId: 'L103',
    title: '西周分封与宗法',
    freeInput: '听取意见',
    question: '为何不能把睡虎地秦简都说成我的亲笔法令？',
    personMode: true,
  },
];

function projectSuffix(testInfo: TestInfo): 'laptop' | 'fullhd' {
  return testInfo.project.name.includes('1920') ? 'fullhd' : 'laptop';
}

function studentUsername(lessonId: FlagshipLesson['lessonId'], testInfo: TestInfo) {
  return `student.${lessonId.toLowerCase()}.${projectSuffix(testInfo)}`;
}

async function login(page: Page, username: string, password: string) {
  await page.getByLabel('课堂账号', { exact: true }).fill(username);
  await page.getByLabel('密码', { exact: true }).fill(password);
  await page.getByRole('button', { name: '进入课堂' }).click();
}

interface ExpectedRuntimeFailures {
  dialogueRequest: boolean;
}

function observeRuntimeHealth(
  page: Page,
  expectedFailures: ExpectedRuntimeFailures = { dialogueRequest: false },
) {
  const issues: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning') {
      const text = message.text();
      if (text === 'Failed to load resource: the server responded with a status of 401 (Unauthorized)') {
        return;
      }
      if (text.includes('status of 404') && /\/presentation$/.test(message.location().url)) {
        return; // No media is published for the current teacher text yet.
      }
      if (expectedFailures.dialogueRequest && /Failed to load resource.*ERR_FAILED/.test(text)) {
        return;
      }
      const source = message.location().url;
      issues.push(`console.${message.type()}: ${text}${source ? ` @ ${source}` : ''}`);
    }
  });
  page.on('pageerror', (error) => issues.push(`pageerror: ${error.message}`));
  page.on('response', (response) => {
    if (response.status() >= 500) issues.push(`http ${response.status()}: ${response.url()}`);
  });
  return issues;
}

async function keepClassroomLocalOnly(page: Page) {
  const externalRequests: string[] = [];
  const classroomOrigin = new URL(BASE_URL).origin;
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if ((url.protocol === 'http:' || url.protocol === 'https:') && url.origin !== classroomOrigin) {
      externalRequests.push(url.href);
      await route.abort('blockedbyclient');
      return;
    }
    await route.continue();
  });
  return externalRequests;
}

async function expectNoHorizontalOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
}

async function openStage(page: Page, name: '抉择' | '召见' | '卷宗') {
  await page.locator('.chrono-stage-rail').getByRole('button', { name: new RegExp(name) }).click();
  await expect(page).toHaveURL(new RegExp(`layer=${name === '抉择' ? 'practice' : name === '召见' ? 'ask' : 'create'}`));
}

interface RenderedNpcDialogue {
  responseLabel: string;
  speech: string;
}

async function expectNpcDialogue(page: Page, turnNo: number): Promise<RenderedNpcDialogue> {
  const dialogue = page.getByRole('article', { name: `第 ${turnNo} 回合人物回应` });
  await expect(dialogue).toBeVisible();
  await expect(dialogue.getByText('你的陈策', { exact: true })).toBeVisible();
  await expect(dialogue.getByText('局势', { exact: true })).toBeVisible();
  await expect(dialogue.getByText('角色化教学表达，不是史料原话。', { exact: true }))
    .toBeVisible();
  const response = dialogue.locator('.chrono-scenario-dialogue__response');
  await expect(response).toHaveAttribute('aria-label', /.+的回应/);
  const responseLabel = await response.getAttribute('aria-label');
  const speech = (await dialogue.locator('.chrono-scenario-dialogue__voice blockquote').innerText()).trim();
  expect(responseLabel).toBeTruthy();
  expect(speech).not.toBe('');
  return { responseLabel: responseLabel!, speech };
}

async function failDialogueRequest(route: Route) {
  await route.abort('failed');
}

async function exerciseFlagship(page: Page, lesson: FlagshipLesson, testInfo: TestInfo) {
  const expectedFailures: ExpectedRuntimeFailures = { dialogueRequest: false };
  const issues = observeRuntimeHealth(page, expectedFailures);
  const externalRequests = await keepClassroomLocalOnly(page);
  const lessonPath = `/courses/${COURSE_ID}/lessons/${lesson.lessonId}`;

  await page.goto(lessonPath);
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText('登录后返回原页面')).toBeVisible();
  await login(page, studentUsername(lesson.lessonId, testInfo), USER_PASSWORD);

  await expect(page).toHaveURL(`${BASE_URL}${lessonPath}`);
  await expect(page.getByRole('heading', { name: lesson.title, level: 1 })).toBeVisible();
  await expect(page.locator('.chrono-cinema-screen video')).toHaveCount(0);
  await expect(page.getByText('教师课文', { exact: true })).toBeVisible();
  await expect(page.getByText('本课暂未配备导读短片')).toBeVisible();
  await expectNoHorizontalOverflow(page);

  await page.reload();
  await expect(page).toHaveURL(`${BASE_URL}${lessonPath}`);
  await expect(page.getByRole('heading', { name: lesson.title, level: 1 })).toBeVisible();
  await expect(page).not.toHaveURL(/\/login$/);

  await openStage(page, '抉择');
  await expect(page.getByRole('region', { name: '历史情景推演' })).toBeVisible();
  const progress = page.locator('.chrono-adventure-round-seal strong');
  await expect(progress).toHaveText('0');

  await page.getByLabel('自拟历史行动').fill(lesson.freeInput);
  const firstAdvance = page.waitForResponse((response) => (
    response.request().method() === 'POST'
    && response.url().includes('/api/v1/practice/game/sessions/')
    && response.url().endsWith('/free-input')
  ));
  await page.locator('.chrono-adventure-free-input').getByRole('button', { name: '呈上议策' }).click();
  await expect(progress).toHaveText('1');
  const firstAdvanceBody = await (await firstAdvance).json();
  expect(firstAdvanceBody).toMatchObject({
    kind: 'advanced',
    result: {
      npc_dialogue: {
        schema_version: 'scenario-npc-dialogue/v1',
        session_id: expect.any(String),
        turn_no: 1,
        persona_pack_id: expect.any(String),
        evidence_corpus_id: expect.any(String),
        disclaimer: '角色化教学表达，不是史料原话。',
      },
    },
  });
  await expectNpcDialogue(page, 1);

  for (let turn = 2; turn <= 6; turn += 1) {
    await page.locator('.chrono-adventure-choices button').first().click();
    await expect(progress).toHaveText(`${turn}`);
    const renderedDialogue = await expectNpcDialogue(page, turn);
    if (turn === 3) {
      await page.reload();
      await expect(progress).toHaveText('3');
      await expect(page.getByText('已续接上次议事')).toBeVisible();
      const restoredDialogue = await expectNpcDialogue(page, 3);
      expect(restoredDialogue).toEqual(renderedDialogue);
    }
    if (
      turn === 4
      && lesson.lessonId === 'L101'
      && testInfo.project.name === 'classroom-1366x768'
    ) {
      expectedFailures.dialogueRequest = true;
      await page.route(
        '**/api/v1/practice/game/sessions/*/dialogues',
        failDialogueRequest,
      );
      await page.reload();
      await expect(progress).toHaveText('4');
      await expect(page.locator('.chrono-adventure-narrative')).toBeVisible();
      await expect(page.locator('.chrono-adventure-narrator')).not.toBeEmpty();
      await expect(page.getByRole('article', { name: '第 4 回合人物回应' })).toHaveCount(0);
      await page.unroute(
        '**/api/v1/practice/game/sessions/*/dialogues',
        failDialogueRequest,
      );
      expectedFailures.dialogueRequest = false;
    }
  }
  await expect(page.locator('.chrono-adventure-ending')).toBeVisible();
  await expect(page.getByRole('button', { name: '整理史官卷宗' })).toBeVisible();
  await expectNoHorizontalOverflow(page);

  await openStage(page, '召见');
  if (lesson.personMode) {
    await page.locator('.chrono-ask-person-picker > summary').click();
    await page.locator('.chrono-ask-person-menu button').first().click();
    await expect(page.locator('.chrono-ask-person-picker')).toHaveClass(/active/);
  }
  const question = page.getByPlaceholder('写下你真正想追问的事…');
  await question.fill(lesson.question);
  await page.locator('.chrono-ask-composer').getByRole('button', { name: '发问' }).click();
  const answer = page.locator('.chrono-ask-turn .chrono-ask-answer').last();
  await expect(answer).toBeVisible();
  await expect(page.getByText(/混合检索|词法回退|证据库 v|校验 [a-f0-9]{8}/)).toHaveCount(0);
  if (lesson.personMode) {
    await expect(answer.getByText('当前材料暂不能回答')).toBeVisible();
    await expect(answer).toContainText('超出了当前人物已经审校的知识范围');
    await expect(answer.locator('.chrono-ask-citations')).toHaveCount(0);
    await expect(answer.getByRole('button', { name: '据何而答 · 暂无可用材料' })).toBeDisabled();
    await expect(answer.getByText('角色化教学表达，不是史料原话。', { exact: true }))
      .toBeVisible();
  } else {
    await expect(answer.locator('.chrono-ask-citations blockquote').first()).toBeVisible();
    await expect(answer.getByText(/据本课材料/)).toBeVisible();
    await answer.getByRole('button', { name: /据何而答/ }).click();
    await expect(answer.locator('.chrono-ask-citations')).toHaveCount(0);
    await answer.getByRole('button', { name: /据何而答/ }).click();
    await expect(answer.locator('.chrono-ask-citations blockquote').first()).toBeVisible();
  }
  await expectNoHorizontalOverflow(page);

  await openStage(page, '卷宗');
  await expect(page.getByRole('region', { name: '史官卷宗' })).toBeVisible();
  await expect(page.getByText('已封卷')).toBeVisible();
  await expect(page.getByRole('region', { name: '学习书案' })).toBeVisible();
  const deskTitle = page.getByRole('textbox', { name: '学习卷宗标题' });
  await expect(deskTitle).toBeVisible();
  await deskTitle.fill(`${lesson.title} · 我的学习卷宗`);
  await expect(page.locator('.chrono-desk-save-state')).toContainText('本机已保存');
  const importButton = page.getByRole('button', { name: /导入知识节点|已导入画板/ });
  await expect(importButton).toBeVisible();
  const alreadyImported = (await importButton.innerText()).includes('已导入画板');
  if (!alreadyImported) await importButton.click();
  await expect(page.getByRole('button', { name: '已导入画板' })).toBeVisible();
  await expect(page.locator('.chrono-canvas-save-status')).toContainText(
    alreadyImported ? /已保存|画板已就绪/ : '已保存',
  );
  await page.locator('.chrono-desk-tools button').filter({ hasText: '学习轨迹' }).click();
  await expect(page.getByRole('region', { name: '前三阶段学习轨迹' })).toContainText('自由陈策');

  await page.reload();
  await expect(page.getByRole('button', { name: '已导入画板' })).toBeVisible();
  await expect(page.locator('.chrono-canvas-save-status')).toContainText(/已保存|画板已就绪/);
  await expect(page.getByRole('textbox', { name: '学习卷宗标题' }))
    .toHaveValue(`${lesson.title} · 我的学习卷宗`);
  const submitButton = page.getByRole('button', { name: /提交本次成果|提交新版本|重试上次提交/ });
  await submitButton.click();
  await page.getByRole('button', { name: '确认提交' }).click();
  await expect(page.locator('.chrono-desk-submit-state')).toContainText('教师可见');
  await page.getByRole('button', { name: '版本记录' }).click();
  await expect(page.getByText('教师只会看到这些版本')).toBeVisible();
  await expect(page.locator('.chrono-submission-viewer')).toBeVisible();
  await page.getByRole('button', { name: 'Close' }).click();
  await expectNoHorizontalOverflow(page);

  await page.goto('/admin/accounts');
  await expect(page).toHaveURL(/\/forbidden/);
  await expect(page.getByText('当前身份不能进入这个工作区')).toBeVisible();

  expect(externalRequests, 'The offline classroom must not request internet resources.').toEqual([]);
  expect(issues, 'The browser console and application responses must stay clean.').toEqual([]);
}

for (const lesson of FLAGSHIPS) {
  test(`${lesson.lessonId} ${lesson.title} completes the offline classroom chain`, async ({ page }, testInfo) => {
    test.skip(testInfo.project.name === 'ask-mobile-390x844', 'The mobile project has a focused ask-page journey.');
    await exerciseFlagship(page, lesson, testInfo);
  });
}

test('teacher reviews only an explicitly submitted learning version', async ({ browser }, testInfo) => {
  test.skip(testInfo.project.name !== 'classroom-1366x768', 'The feedback chain needs one browser viewport.');
  const suffix = projectSuffix(testInfo);
  const submissionTitle = `E2E 学习成果 ${Date.now()}`;
  const studentContext = await browser.newContext({ baseURL: BASE_URL });
  try {
    const studentPage = await studentContext.newPage();
    await studentPage.goto('/login');
    await login(studentPage, `student.guard.${suffix}`, USER_PASSWORD);
    await expect(studentPage).toHaveURL(`${BASE_URL}/`);
    const submitted = await studentContext.request.post(`${BASE_URL}/api/v1/learning/submissions`, {
      headers: { Origin: BASE_URL },
      data: {
        schema_version: 'learning-submission-request/v1',
        client_submission_id: `submit-e2e-${Date.now()}`,
        course_id: COURSE_ID,
        lesson_id: 'L101',
        title: submissionTitle,
        body_markdown: '## 我的判断\n疏导、协作与责任必须放在同一条因果链中理解。',
        sticky_notes: [{ note_id: 'e2e-note', body: '比较工程路径与组织代价', color: 'ochre' }],
        drawing_strokes: [],
        learning_events: [],
        local_draft_updated_at: new Date().toISOString(),
      },
    });
    expect(submitted.status(), await submitted.text()).toBe(201);
  } finally {
    await studentContext.close();
  }

  const teacherContext = await browser.newContext({ baseURL: BASE_URL });
  try {
    const page = await teacherContext.newPage();
    const issues = observeRuntimeHealth(page);
    await page.goto('/login');
    await login(page, `teacher.e2e.${suffix}`, USER_PASSWORD);
    await expect(page).toHaveURL(/\/teacher\/learning$/);
    await expect(page.getByTestId('learning-review')).toBeVisible();
    await page.locator('.chrono-review-queue-list > button').filter({ hasText: submissionTitle }).click();
    await expect(page.locator('.chrono-submission-viewer')).toContainText(submissionTitle);
    await page.getByLabel('教师反馈编辑器').getByText('确认完成', { exact: true }).click();
    const feedback = `证据与因果链已经清楚，可继续比较不同治理路径的代价。${Date.now()}`;
    await page.getByPlaceholder(/指出证据使用/).fill(feedback);
    await page.getByRole('button', { name: '追加反馈' }).click();
    await expect(page.locator('.chrono-submission-feedback')).toContainText(feedback);
    expect(issues).toEqual([]);
  } finally {
    await teacherContext.close();
  }
});

async function verifyRoleWorkspace(
  browser: Browser,
  username: string,
  password: string,
  expectedPath: RegExp,
  expectedTestId: string,
) {
  const context = await browser.newContext({ baseURL: BASE_URL });
  const page = await context.newPage();
  const issues = observeRuntimeHealth(page);
  try {
    await page.goto('/login');
    await login(page, username, password);
    await expect(page).toHaveURL(expectedPath);
    await expect(page.getByTestId(expectedTestId)).toBeVisible();
    expect(issues).toEqual([]);
  } finally {
    await context.close();
  }
}

test('teacher, reviewer and administrator land only in their permitted workspaces', async ({ browser }, testInfo) => {
  test.skip(testInfo.project.name !== 'classroom-1366x768', 'The role matrix needs one browser viewport.');
  const suffix = projectSuffix(testInfo);
  await verifyRoleWorkspace(
    browser,
    `teacher.e2e.${suffix}`,
    USER_PASSWORD,
    /\/teacher\/learning$/,
    'learning-review',
  );
  await verifyRoleWorkspace(
    browser,
    `reviewer.e2e.${suffix}`,
    USER_PASSWORD,
    /\/admin\/content$/,
    'admin-content-editor',
  );
  await verifyRoleWorkspace(
    browser,
    ADMIN_USERNAME,
    ADMIN_PASSWORD,
    /\/admin\/accounts$/,
    'account-management',
  );
});
