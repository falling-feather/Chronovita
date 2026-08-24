import { expect, test, type Page } from '@playwright/test';

const BASE_URL = (process.env.CHRONO_E2E_BASE_URL || 'http://127.0.0.1:8765').replace(/\/$/, '');
const USER_PASSWORD = process.env.CHRONO_E2E_USER_PASSWORD || '';

async function login(page: Page) {
  await page.getByLabel('账号').fill('student.guard.laptop');
  await page.getByLabel('密码').fill(USER_PASSWORD);
  await page.getByRole('button', { name: '进入我的工作区' }).click();
}

test('学习书案在 390 × 844 下可编辑、可恢复并切换全部工具', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'ask-mobile-390x844', 'This is the focused mobile learning-desk check.');

  const issues: string[] = [];
  const externalRequests: string[] = [];
  const classroomOrigin = new URL(BASE_URL).origin;
  page.on('console', (message) => {
    if (message.type() !== 'error' && message.type() !== 'warning') return;
    if (message.text() === 'Failed to load resource: the server responded with a status of 401 (Unauthorized)') return;
    issues.push(`${message.type()}: ${message.text()}`);
  });
  page.on('pageerror', (error) => issues.push(`pageerror: ${error.message}`));
  page.on('response', (response) => {
    if (response.status() >= 500) issues.push(`http ${response.status()}: ${response.url()}`);
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if ((url.protocol === 'http:' || url.protocol === 'https:') && url.origin !== classroomOrigin) {
      externalRequests.push(url.href);
      await route.abort('blockedbyclient');
      return;
    }
    await route.continue();
  });

  const lessonPath = '/courses/C-prequin-state/lessons/L101?layer=create';
  await page.goto(lessonPath);
  await expect(page).toHaveURL(/\/login$/);
  await login(page);
  await expect(page).toHaveURL(`${BASE_URL}${lessonPath}`);

  await expect(page.getByRole('region', { name: '学习书案' })).toBeVisible();
  const title = page.getByRole('textbox', { name: '学习卷宗标题' });
  await title.fill('移动端历史判断');
  await page.getByRole('button', { name: /新便签/ }).click();
  await page.getByRole('textbox', { name: '便签内容' }).last().fill('先记下证据，再形成结论。');
  await expect(page.locator('.chrono-desk-save-state')).toContainText('本机已保存');

  await page.locator('.chrono-desk-tools button').filter({ hasText: '手写与绘图' }).click();
  await expect(page.getByRole('region', { name: '手写与绘图' })).toBeVisible();
  const drawingCanvas = page.getByLabel('可以使用鼠标、触控笔或手指书写的画布');
  await expect(drawingCanvas).toBeVisible();
  const drawingBox = await drawingCanvas.boundingBox();
  expect(drawingBox).not.toBeNull();
  if (drawingBox) {
    await page.mouse.move(drawingBox.x + 36, drawingBox.y + 58);
    await page.mouse.down();
    await page.mouse.move(drawingBox.x + 148, drawingBox.y + 122, { steps: 8 });
    await page.mouse.up();
  }
  await expect(page.getByRole('button', { name: /撤回/ })).toBeEnabled();
  await expect(page.locator('.chrono-desk-save-state')).toContainText('本机已保存');

  await page.locator('.chrono-desk-tools button').filter({ hasText: '知识导图' }).click();
  await expect(page.getByRole('region', { name: '知识画板' })).toBeVisible();

  await page.locator('.chrono-desk-tools button').filter({ hasText: '学习轨迹' }).click();
  await expect(page.getByRole('region', { name: '前三阶段学习轨迹' })).toBeVisible();

  await page.reload();
  await expect(page.getByRole('textbox', { name: '学习卷宗标题' })).toHaveValue('移动端历史判断');
  await page.locator('.chrono-desk-tools button').filter({ hasText: '手写与绘图' }).click();
  await expect(page.getByRole('button', { name: /撤回/ })).toBeEnabled();
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
  expect(externalRequests).toEqual([]);
  expect(issues).toEqual([]);
});
