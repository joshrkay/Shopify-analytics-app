import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright E2E test configuration for MarkInsight.
 *
 * Run with: npx playwright test
 * Debug with: npx playwright test --debug
 * UI mode:    npm run test:e2e:ui
 *
 * Note: Do not use process.env.CI to disable webServer — many dev environments
 * (including IDEs) set CI=true, which would skip Vite and cause ERR_CONNECTION_REFUSED.
 */
const inGithubActions = !!process.env.GITHUB_ACTIONS;

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? 'github' : 'html',
  use: {
    // 127.0.0.1 avoids ::1 vs IPv4 mismatches on some hosts
    baseURL: process.env.BASE_URL || 'http://127.0.0.1:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  /* Start Vite before tests everywhere except GitHub Actions (where you provide your own URL). */
  webServer: inGithubActions
    ? undefined
    : {
        // Bind IPv4 explicitly — Playwright's readiness probe uses 127.0.0.1; default Vite
        // "localhost" can be IPv6-only (::1) on some systems and never answer the probe.
        command: 'npx vite --host 127.0.0.1 --port 3000',
        url: 'http://127.0.0.1:3000',
        reuseExistingServer: true,
        timeout: 120_000,
        stdout: 'pipe',
        stderr: 'pipe',
      },
});
