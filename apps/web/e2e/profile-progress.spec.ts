import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const BASE = process.env.CHRONO_E2E_BASE_URL || 'http://127.0.0.1:8765';
const PASSWORD = process.env.CHRONO_E2E_USER_PASSWORD || '';

test('个人资料、阅读确认、反馈入口与改密退出形成真实闭环', async ({ page, playwright }, testInfo) => {
  test.skip(testInfo.project.name === 'classroom-1920x1080', 'Profile is checked on desktop and mobile.');
  const admin = await playwright.request.newContext({ baseURL: BASE, extraHTTPHeaders: { Origin: BASE } });
  const login = await admin.post('/api/v1/auth/login', { data: {
    username: process.env.CHRONO_E2E_ADMIN_USERNAME || 'classroom.admin',
    password: process.env.CHRONO_E2E_ADMIN_PASSWORD || '',
  } });
  expect(login.ok()).toBeTruthy();
  const username = `profile.qa.${Date.now()}`;
  const created = await admin.post('/api/v1/auth/users', { data: {
    username, password: PASSWORD, display_name: '资料验收', roles: ['student'],
  } });
  expect(created.status()).toBe(201);
  await admin.dispose();
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/login');
  await page.getByLabel('课堂账号', { exact: true }).fill(username);
  await page.getByLabel('密码', { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: '进入课堂' }).click();
  await page.goto('/profile');
  await page.getByLabel('昵称', { exact: true }).fill('已保存的新昵称');
  await page.getByLabel('联系邮箱（可选）').fill('student@example.com');
  await page.getByLabel('个性签名').fill('阅读原文，再核对依据。');
  await page.getByLabel('头像', { exact: true }).setInputFiles({
    name: 'avatar.webp', mimeType: 'image/webp',
    buffer: readFileSync(new URL('../public/assets/ui/ask/xuan-paper-1024.webp', import.meta.url)),
  });
  await page.getByRole('button', { name: '移除头像' }).waitFor();
  await page.getByRole('button', { name: '保存修改', exact: true }).click();
  await expect(page.locator('.chrono-account-trigger')).toContainText('已保存的新昵称');
  await expect(page.locator('.chrono-account-trigger img')).toHaveAttribute('src', /^data:image\/webp;base64,/);
  await page.reload();
  await expect(page.getByLabel('昵称', { exact: true })).toHaveValue('已保存的新昵称');
  expect(await page.evaluate(() => document.documentElement.scrollWidth
    <= document.documentElement.clientWidth + 1)).toBeTruthy();
  await page.screenshot({ path: join(tmpdir(), `chronovita-profile-${testInfo.project.name}.png`), fullPage: true });
  await page.getByRole('button', { name: '阅读偏好', exact: true }).click();
  await page.getByText('大字', { exact: true }).click();
  await page.getByRole('button', { name: '保存修改', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('与账号资料一致');

  await page.goto('/courses/C-prequin-state/lessons/L101?layer=watch');
  await expect(page.locator('.chrono-reading-body p').first()).toHaveCSS('font-size', '22px');
  let rejected = false;
  await page.route('**/api/v1/learning/progress/touch', async (route) => {
    if (route.request().postDataJSON()?.completed && !rejected) {
      rejected = true; await route.abort('failed');
    } else await route.continue();
  });
  const confirm = page.getByRole('button', { name: '我已读完这篇课文', exact: true });
  await confirm.click();
  await expect(page.locator('.chrono-lesson-workspace .ant-alert')).toBeVisible();
  await page.unroute('**/api/v1/learning/progress/touch');
  await confirm.click();
  await expect(page.getByRole('button', { name: '已确认读完当前课文' })).toBeDisabled();
  await page.reload();
  await expect(page.getByRole('button', { name: '已确认读完当前课文' })).toBeDisabled();
  await page.goto('/learning');
  await expect(page.locator('.chrono-learning-hero')).toContainText('1/46');
  await expect(page.locator('.chrono-user-slot .ant-badge-dot')).toHaveCount(0);
  await page.getByRole('button', { name: '查看教师反馈', exact: true }).click();
  await expect(page).toHaveURL(/tab=submissions/);

  await page.goto('/profile');
  await page.getByRole('button', { name: '账号与数据', exact: true }).click();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: '导出个人资料' }).click();
  expect((await download).suggestedFilename()).toBe('Chronovita-个人资料.json');
  await page.getByLabel('当前密码', { exact: true }).fill(PASSWORD);
  await page.getByLabel('新密码', { exact: true }).fill(PASSWORD + '-new');
  await page.getByLabel('确认新密码', { exact: true }).fill(PASSWORD + '-new');
  await page.getByRole('button', { name: '修改密码并退出' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel('课堂账号', { exact: true }).fill(username);
  await page.getByLabel('密码', { exact: true }).fill(PASSWORD + '-new');
  await page.getByRole('button', { name: '进入课堂' }).click();
  await page.goto('/profile');
  await page.route('**/api/v1/auth/logout', (route) => route.abort('failed'));
  await page.getByRole('button', { name: '退出登录', exact: true }).click();
  await expect(page.getByText('退出请求未完成，账号仍可能在线。请恢复网络后重试。')).toBeVisible();
  await expect(page).toHaveURL(/\/profile$/);
  await page.unroute('**/api/v1/auth/logout');
  await page.getByRole('button', { name: '退出登录', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.reload();
  await expect(page.getByLabel('课堂账号', { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
