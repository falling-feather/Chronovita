import { expect, test } from '@playwright/test';

const password = process.env.CHRONO_E2E_USER_PASSWORD || '';

test('完整阅读器可读正文、保存设置、查看真实书影并刷新恢复', async ({ page }, info) => {
  test.skip(info.project.name === 'ask-mobile-390x844', '分栏与书影在两种桌面尺寸集中检查。');
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/shiji');
  await page.getByLabel('课堂账号', { exact: true }).fill('student.guard.laptop');
  await page.getByLabel('密码', { exact: true }).fill(password);
  await page.getByRole('button', { name: '进入课堂' }).click();
  const reader = page.frameLocator('iframe[title="《史记》完整文献阅读器"]');
  await expect(reader.locator('.sentence-original').first()).toBeVisible();
  await expect(reader.getByRole('tab', { name: '历史地图' })).toHaveCount(0);
  if (await reader.getByRole('button', { name: '展开功能区', exact: true }).isVisible()) {
    await reader.getByRole('button', { name: '展开功能区', exact: true }).click();
  }
  await reader.getByLabel('主题模式').selectOption('night');
  await expect(reader.locator('.reader-app')).toHaveClass(/theme-night/);
  await reader.getByRole('button', { name: '简体', exact: true }).click();
  await page.reload();
  await expect(reader.locator('.reader-app')).toHaveClass(/theme-night/);
  const image = reader.locator('.scan-sheet-media img').first();
  await expect(image).toBeVisible();
  await expect.poll(() => image.evaluate((element) => (element as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  await reader.locator('.scan-sheet-media').first().click();
  await expect(reader.locator('.vertical-source-text')).not.toBeEmpty();
  await reader.getByRole('link', { name: '返回目录', exact: true }).click();
  await expect(reader.getByRole('heading', { name: '《史记》', exact: true })).toBeVisible();
  await reader.getByRole('tab', { name: /版本/ }).click();
  await expect(reader.locator('.version-row')).toHaveCount(2);
  expect(errors).toEqual([]);
});

test('西周不调用商鞅旧互动，当前书案仍能编辑', async ({ page }) => {
  await page.goto('/courses/C-prequin-state/lessons/L103?layer=practice');
  await page.getByLabel('课堂账号', { exact: true }).fill('student.guard.laptop');
  await page.getByLabel('密码', { exact: true }).fill(password);
  await page.getByRole('button', { name: '进入课堂' }).click();
  await expect(page.locator('.chrono-lesson-masthead h1')).toHaveText('西周分封与宗法');
  await expect(page.getByText('本课互动资料尚未对齐教师新稿')).toBeVisible();
  await expect(page.locator('.chrono-adventure-stage')).toHaveCount(0);
  await page.getByRole('button', { name: '打开学习书案', exact: true }).click();
  await expect(page.getByRole('region', { name: '学习书案' })).toBeVisible();
});
