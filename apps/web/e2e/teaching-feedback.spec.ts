import { expect, test, type Page } from '@playwright/test';

const password = process.env.CHRONO_E2E_USER_PASSWORD || '';
async function login(page: Page, username: string) {
  await page.goto('/login');
  await page.getByLabel('课堂账号', { exact: true }).fill(username);
  await page.getByLabel('密码', { exact: true }).fill(password);
  await page.getByRole('button', { name: '进入课堂' }).click();
}

async function chooseOption(page: Page, fieldName: string, name: string) {
  // Ant Design virtualizes its hidden accessibility option list; select the
  // visible popup content, as a pointer user does, rather than a hidden mirror.
  const listId = await page.getByRole('combobox', { name: fieldName, exact: true }).getAttribute('aria-controls');
  if (!listId) throw new Error('Select did not expose its controlled popup');
  await page.locator('.ant-select-dropdown').filter({ has: page.locator('[id="' + listId + '"]') })
    .getByText(name, { exact: true }).click();
}

async function openSelect(page: Page, name: string) {
  const field = page.getByRole('combobox', { name, exact: true });
  await field.focus();
  await field.press('ArrowDown');
}

test('教师任务经学生明确提交后可按三项评价并由学生回看', async ({ browser }, info) => {
  test.skip(info.project.name !== 'classroom-1366x768', '任务闭环检查一次；阅读与书案另覆盖其他视口。');
  const title = '史料与治理判断 ' + Date.now();
  const feedback = '已引用材料。继续说明选择如何影响不同群体。';
  const teacherContext = await browser.newContext();
  const studentContext = await browser.newContext();
  try {
    const teacher = await teacherContext.newPage();
    await login(teacher, 'teacher.e2e.laptop');
    await teacher.getByRole('combobox', { name: '任务课时', exact: true }).fill('大禹治水');
    await chooseOption(teacher, '任务课时', '1.1 · 大禹治水');
    await teacher.getByLabel('课堂任务标题', { exact: true }).fill(title);
    await teacher.getByLabel('课堂任务要求', { exact: true }).fill('引用课文或原始史料，解释治水选择与协作代价。');
    await teacher.getByRole('button', { name: '发布课堂任务', exact: true }).click();
    await expect(teacher.getByRole('region', { name: '课堂任务管理' })).toContainText(title);
    const student = await studentContext.newPage();
    await login(student, 'student.task.laptop');
    await student.goto('/courses/C-prequin-state/lessons/L101?layer=create');
    await openSelect(student, '选择提交的课堂任务');
    await chooseOption(student, '选择提交的课堂任务', title);
    await student.getByLabel('学习卷宗标题', { exact: true }).fill(title + ' · 我的解释');
    await student.getByLabel('所见即所得正文', { exact: true }).fill('我认为治水需要先了解地形，再公开协作方案。材料是后人的记述，不能当作禹时代现场记录。');
    await expect(student.locator('.chrono-desk-save-state')).toContainText('本机已保存');
    await teacher.getByRole('button', { name: '刷新成果队列', exact: true }).click();
    await expect(teacher.locator('.chrono-review-queue-list')).not.toContainText(title + ' · 我的解释');
    await student.getByRole('button', { name: /提交本次成果|提交新版本/ }).click();
    const submittedResponse = student.waitForResponse((response) => response.url().endsWith('/api/v1/learning/submissions')
      && response.request().method() === 'POST');
    await student.getByRole('button', { name: '确认提交', exact: true }).click();
    const uploaded = await submittedResponse;
    expect(uploaded.status()).toBe(201);
    const uploadedRecord = (await uploaded.json()).submission;
    expect(uploadedRecord.title).toBe(title + ' · 我的解释');
    expect(uploadedRecord.task.title).toBe(title);
    await expect(student.locator('.chrono-desk-submit-state')).toContainText('教师可见');
    await teacher.getByRole('button', { name: '刷新成果队列', exact: true }).click();
    await teacher.locator('.chrono-review-queue-list > button').filter({ hasText: title + ' · 我的解释' }).click();
    await expect(teacher.locator('.chrono-submission-viewer')).toContainText('提交对应课堂任务：' + title);
    await openSelect(teacher, '史实与历史边界');
    await chooseOption(teacher, '史实与历史边界', '有依据支持');
    await openSelect(teacher, '材料与出处');
    await chooseOption(teacher, '材料与出处', '逐步形成');
    await teacher.getByLabel('教师具体反馈', { exact: true }).fill(feedback);
    await teacher.getByRole('button', { name: '追加反馈' }).click();
    await expect(teacher.locator('.chrono-submission-feedback')).toContainText(feedback);
    await student.goto('/learning?tab=submissions');
    const card = student.locator('.chrono-learning-submission-grid > article').filter({ hasText: title + ' · 我的解释' });
    await card.getByRole('button', { name: '查看版本', exact: true }).click();
    await expect(student.locator('.chrono-submission-viewer')).toContainText(feedback);
    await expect(student.locator('.chrono-submission-viewer')).toContainText('史实与历史边界：有依据支持');
    await expect(student.locator('.chrono-submission-viewer')).toContainText('材料与出处：逐步形成');
  } finally {
    await Promise.allSettled([teacherContext.close(), studentContext.close()]);
  }
});
