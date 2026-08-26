import { expect, test, type Page } from '@playwright/test';

const BASE_URL = (process.env.CHRONO_E2E_BASE_URL || 'http://127.0.0.1:8765').replace(/\/$/, '');
const USER_PASSWORD = process.env.CHRONO_E2E_USER_PASSWORD || '';

async function login(page: Page) {
  await page.getByLabel('课堂账号', { exact: true }).fill('student.guard.laptop');
  await page.getByLabel('密码', { exact: true }).fill(USER_PASSWORD);
  await page.getByRole('button', { name: '进入课堂' }).click();
}

test('问史卷在 390 × 844 下保持完整提问与据何而答链路', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'ask-mobile-390x844', 'This is the focused mobile ask-page check.');

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

  const lessonPath = '/courses/C-prequin-state/lessons/L103?layer=ask';
  await page.goto(lessonPath);
  await expect(page).toHaveURL(/\/login$/);
  await login(page);
  await expect(page).toHaveURL(`${BASE_URL}${lessonPath}`);

  await expect(page.locator('.chrono-lesson-masthead')).toBeHidden();
  await expect(page.getByRole('navigation', { name: '课堂四阶段' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '向史证提问', level: 2 })).toBeVisible();
  await expect(page.getByRole('button', { name: /课程学者/ })).toBeVisible();
  await expect(page.getByPlaceholder('写下你真正想追问的事…')).toBeVisible();

  const bookmark = page.locator('.chrono-ask-bookmarks button').first();
  await bookmark.click();
  await page.locator('.chrono-ask-composer').getByRole('button', { name: '发问' }).click();
  const answer = page.locator('.chrono-ask-turn .chrono-ask-answer').last();
  await expect(answer).toBeVisible();
  await expect(answer.locator('.chrono-ask-citations blockquote').first()).toBeVisible();
  await answer.getByRole('button', { name: /据何而答/ }).click();
  await expect(answer.locator('.chrono-ask-citations')).toHaveCount(0);
  await answer.getByRole('button', { name: /据何而答/ }).click();
  await expect(answer.locator('.chrono-ask-citations blockquote').first()).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
  expect(externalRequests).toEqual([]);
  expect(issues).toEqual([]);
});
