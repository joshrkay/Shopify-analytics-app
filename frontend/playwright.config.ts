import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright E2E test configuration for MarkInsight.
 *
 * Local (default): starts Vite on 127.0.0.1:3000 automatically.
 *
 * Production / staging: set BASE_URL to your deployed origin (https://...).
 * Local webServer is skipped so tests hit the real site (Clerk key already in the prod build).
 *
 *   BASE_URL=https://app.example.com npm run test:e2e:prod
 *   BASE_URL=https://app.example.com npm run test:e2e:prod:ui
 *
 * Watch the real Chromium window (not just the Playwright panel):
 *   npm run test:e2e:visual
 *   BASE_URL=https://app.example.com npm run test:e2e:visual
 * In UI mode, turn ON "Show browser" in the left sidebar (eye / browser icon).
 * Optional: npm run test:e2e:visual:ui — then enable "Show browser" before Run all.
 *
 * Optional: PLAYWRIGHT_SKIP_WEB_SERVER=1 to reuse an already-running local dev server
 * with a custom BASE_URL (e.g. http://127.0.0.1:3000).
 *
 * Note: Do not use process.env.CI to disable webServer — many IDEs set CI=true.
 */
const inGithubActions = !!process.env.GITHUB_ACTIONS;

const defaultBase = 'http://127.0.0.1:3000';
const baseURL = process.env.BASE_URL || process.env.E2E_BASE_URL || defaultBase;

function isLocalBaseUrl(url: string): boolean {
  try {
    const { hostname } = new URL(url);
    return hostname === 'localhost' || hostname === '127.0.0.1';
  } catch {
    return false;
  }
}

const skipWebServer =
  inGithubActions ||
  process.env.PLAYWRIGHT_SKIP_WEB_SERVER === '1' ||
  !isLocalBaseUrl(baseURL);

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? 'github' : 'html',
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: skipWebServer
    ? undefined
    : {
        command: 'npx vite --host 127.0.0.1 --port 3000',
        url: 'http://127.0.0.1:3000',
        reuseExistingServer: true,
        timeout: 120_000,
        stdout: 'pipe',
        stderr: 'pipe',
      },
});
