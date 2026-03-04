/**
 * Visual Smoke Test — Takes screenshots of every major app page.
 *
 * Uses the pre-cached Chromium binary directly. No browser download needed.
 * Connects to the Vite dev server running the test harness (port 4174).
 *
 * Usage:
 *   1. Start test harness: node e2e/start-server.mjs
 *   2. Run screenshots:    node e2e/take-screenshots.mjs
 */
import { chromium } from 'playwright-core';
import { mkdirSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SCREENSHOTS_DIR = resolve(__dirname, 'screenshots');
const CHROMIUM_PATH = '/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome';
const BASE = 'http://localhost:4174/test-harness.html';

mkdirSync(SCREENSHOTS_DIR, { recursive: true });

const PAGES = [
  { path: '/', name: '01-dashboard-home' },
  { path: '/analytics', name: '02-analytics' },
  { path: '/insights', name: '03-insights-feed' },
  { path: '/sources', name: '04-data-sources' },
  { path: '/attribution', name: '05-attribution' },
  { path: '/orders', name: '06-orders' },
  { path: '/dashboards', name: '07-dashboard-list' },
  { path: '/settings', name: '08-settings' },
  { path: '/approvals', name: '09-approvals' },
  { path: '/whats-new', name: '10-whats-new' },
  { path: '/billing/checkout', name: '11-billing' },
  { path: '/paywall', name: '12-paywall' },
];

async function main() {
  console.log('Launching Chromium...');
  const browser = await chromium.launch({
    executablePath: CHROMIUM_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
  });

  let passed = 0;
  let failed = 0;

  for (const { path, name } of PAGES) {
    const page = await context.newPage();
    try {
      const url = `${BASE}#${path}`;
      console.log(`  Navigating to ${path}...`);
      await page.goto(url, { waitUntil: 'networkidle', timeout: 20000 });
      await page.waitForTimeout(3000); // Let React + Vite HMR settle

      const screenshotPath = resolve(SCREENSHOTS_DIR, `${name}.png`);
      await page.screenshot({ path: screenshotPath, fullPage: true });
      console.log(`  ✓ ${name}.png saved`);
      passed++;
    } catch (err) {
      console.error(`  ✗ ${name} FAILED: ${err.message}`);
      try {
        await page.screenshot({
          path: resolve(SCREENSHOTS_DIR, `${name}-error.png`),
          fullPage: true,
        });
      } catch {}
      failed++;
    } finally {
      await page.close();
    }
  }

  await browser.close();
  console.log(`\nDone: ${passed} passed, ${failed} failed`);
  console.log(`Screenshots saved to: ${SCREENSHOTS_DIR}`);
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
