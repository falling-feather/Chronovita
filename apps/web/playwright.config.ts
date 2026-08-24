import { defineConfig } from '@playwright/test';

const browserChannel = process.env.CHRONO_E2E_BROWSER_CHANNEL?.trim();

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global.setup.ts',
  outputDir: 'test-results',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 120_000,
  expect: { timeout: 20_000 },
  reporter: process.env.CI
    ? [['line'], ['html', { outputFolder: 'playwright-report', open: 'never' }]]
    : [['list']],
  use: {
    baseURL: process.env.CHRONO_E2E_BASE_URL || 'http://127.0.0.1:8765',
    channel: browserChannel || undefined,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'classroom-1366x768',
      use: { viewport: { width: 1366, height: 768 } },
    },
    {
      name: 'classroom-1920x1080',
      use: { viewport: { width: 1920, height: 1080 } },
    },
    {
      name: 'ask-mobile-390x844',
      use: { viewport: { width: 390, height: 844 } },
    },
  ],
});
