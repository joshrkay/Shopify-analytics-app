import { defineConfig, devices } from '@playwright/test';
import path from 'path';

/**
 * Full-stack E2E Playwright configuration.
 *
 * Runs Chromium against a real FastAPI backend + Vite frontend,
 * with PostgreSQL and external services mocked.
 *
 * Usage:
 *   npx playwright test --config tests/e2e/playwright.config.ts
 *   npx playwright test --config tests/e2e/playwright.config.ts suites/p0-critical/
 */
export default defineConfig({
  testDir: path.join(__dirname, 'suites'),
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'html',
  timeout: 30_000,
  expect: {
    timeout: 10_000,
  },

  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: process.env.CI ? 'retain-on-failure' : 'off',
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
  },

  projects: [
    {
      name: 'p0-critical',
      testDir: path.join(__dirname, 'suites', 'p0-critical'),
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'p1-major',
      testDir: path.join(__dirname, 'suites', 'p1-major'),
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'p2-extended',
      testDir: path.join(__dirname, 'suites', 'p2-extended'),
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  globalSetup: path.join(__dirname, 'global-setup.ts'),
  globalTeardown: path.join(__dirname, 'global-teardown.ts'),
});
