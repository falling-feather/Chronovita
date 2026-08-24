import { expect, test, type Page } from '@playwright/test';

const BASE_URL = (process.env.CHRONO_E2E_BASE_URL || 'http://127.0.0.1:8765').replace(/\/$/, '');
const USER_PASSWORD = process.env.CHRONO_E2E_USER_PASSWORD || '';

function desktopSuffix(projectName: string) {
  return projectName === 'classroom-1920x1080' ? 'fullhd' : 'laptop';
}

async function login(page: Page, projectName: string) {
  await page.getByLabel('账号').fill(`student.guard.${desktopSuffix(projectName)}`);
  await page.getByLabel('密码').fill(USER_PASSWORD);
  await page.getByRole('button', { name: '进入我的工作区' }).click();
}

function collectRuntimeIssues(page: Page) {
  const issues: string[] = [];
  page.on('console', (message) => {
    if (message.type() !== 'error' && message.type() !== 'warning') return;
    if (message.text() === 'Failed to load resource: the server responded with a status of 401 (Unauthorized)') return;
    issues.push(`${message.type()}: ${message.text()}`);
  });
  page.on('pageerror', (error) => issues.push(`pageerror: ${error.message}`));
  page.on('response', (response) => {
    if (response.status() >= 500) issues.push(`http ${response.status()}: ${response.url()}`);
  });
  return issues;
}

test('桌面首页减弱动态且山河图可完整键盘操作', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === 'ask-mobile-390x844', 'Desktop visual-quality gate.');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const issues = collectRuntimeIssues(page);
  const requestedScripts: string[] = [];
  page.on('request', (request) => {
    if (request.resourceType() === 'script') requestedScripts.push(request.url());
  });

  await page.goto('/');
  await expect(page).toHaveURL(/\/login$/);
  await login(page, testInfo.project.name);
  await expect(page).toHaveURL(`${BASE_URL}/`);

  await expect(page.getByRole('heading', { name: '拨动天光，进入历史现场' })).toBeVisible();
  await expect(page.locator('.chrono-sundial-scene')).toHaveClass(/is-fallback/);
  await expect(page.locator('.chrono-sundial-fallback')).toBeVisible();
  expect(requestedScripts.some((url) => url.includes('three.module-'))).toBe(false);

  await page.getByRole('button', { name: '浏览课程' }).click();
  await expect(page).toHaveURL(`${BASE_URL}/courses`);
  const map = page.getByRole('img', { name: /时代课堂地图/ });
  await expect(map).toBeVisible();
  await map.focus();
  await page.keyboard.press('+');
  await expect(page.locator('.chrono-eramap-zoom-level')).toHaveText('124%');
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('Home');
  await expect(page.locator('.chrono-eramap-zoom-level')).toHaveText('100%');

  const firstCity = page.locator('.chrono-city-node').first();
  await firstCity.focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('.chrono-map-city-card.is-visible')).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
  expect(issues).toEqual([]);
});

test('WebGL 不可用时日晷静态降级且旗舰课入口不受阻', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'classroom-1366x768', 'One desktop project is sufficient for WebGL failure injection.');
  await page.addInitScript(() => {
    const originalGetContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function getContext(type: string, ...args: unknown[]) {
      if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') return null;
      return Reflect.apply(originalGetContext, this, [type, ...args]);
    } as typeof HTMLCanvasElement.prototype.getContext;
  });

  await page.goto('/');
  await expect(page).toHaveURL(/\/login$/);
  await login(page, testInfo.project.name);
  await expect(page).toHaveURL(`${BASE_URL}/`);

  await expect(page.locator('.chrono-sundial-scene')).toHaveClass(/is-fallback/);
  await expect(page.locator('.chrono-sundial-fallback')).toBeVisible();
  await expect(page.getByRole('button', { name: /进入旗舰课堂|继续上次学习/ })).toBeEnabled();
  await expect(page.getByRole('button', { name: '浏览课程' })).toBeEnabled();
});
