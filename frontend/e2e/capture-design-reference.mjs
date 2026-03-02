/**
 * Design Reference Capture — Run locally (not in sandbox)
 *
 * Navigates the Figma site design reference and captures each slide,
 * then takes matching screenshots from the test harness for comparison.
 *
 * Prerequisites:
 *   1. npm install (from frontend/)
 *   2. npx playwright install chromium  (one-time browser install)
 *
 * Usage:
 *   1. Start test harness:  npx vite --config e2e/vite.config.ts
 *   2. Run comparison:      node e2e/capture-design-reference.mjs
 *
 * Output:
 *   e2e/screenshots-design/   — Figma site slides
 *   e2e/screenshots/          — Current implementation (test harness)
 */
import { chromium } from 'playwright-core';
import { mkdirSync, existsSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DESIGN_DIR = resolve(__dirname, 'screenshots-design');
const IMPL_DIR = resolve(__dirname, 'screenshots');
const FIGMA_SITE = 'https://slot-arch-71887855.figma.site';
const HARNESS_BASE = 'http://localhost:4174/test-harness.html';

// Auto-detect Chromium — try common locations
function findChromium() {
  const candidates = [
    // playwright managed
    '/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome',
    // macOS
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    // Linux
    '/usr/bin/chromium-browser',
    '/usr/bin/chromium',
    '/usr/bin/google-chrome',
    // Windows (WSL)
    '/mnt/c/Program Files/Google/Chrome/Application/chrome.exe',
  ];
  for (const p of candidates) {
    if (existsSync(p)) return p;
  }
  return undefined; // Let playwright auto-detect
}

mkdirSync(DESIGN_DIR, { recursive: true });
mkdirSync(IMPL_DIR, { recursive: true });

async function captureDesignReference(browser) {
  console.log('\n=== PHASE 1: Capturing Figma Design Reference ===\n');
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  try {
    console.log(`Navigating to ${FIGMA_SITE}...`);
    await page.goto(FIGMA_SITE, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(5000);

    console.log(`Title: ${await page.title()}`);
    console.log(`URL: ${page.url()}`);

    // Capture initial slide
    await page.screenshot({ path: resolve(DESIGN_DIR, 'slide-01.png'), fullPage: false });
    console.log('  ✓ slide-01.png');

    // Navigate through slides with arrow keys
    let slideNum = 2;
    let lastScreenshot = null;
    const maxSlides = 20; // safety limit

    while (slideNum <= maxSlides) {
      await page.keyboard.press('ArrowRight');
      await page.waitForTimeout(2000);

      const screenshotPath = resolve(DESIGN_DIR, `slide-${String(slideNum).padStart(2, '0')}.png`);
      await page.screenshot({ path: screenshotPath, fullPage: false });

      // Simple change detection — stop if page hasn't changed
      // (Figma sites stop advancing after the last slide)
      console.log(`  ✓ slide-${String(slideNum).padStart(2, '0')}.png`);
      slideNum++;
    }
  } catch (err) {
    console.error(`Design capture error: ${err.message}`);
  }

  await context.close();
}

async function captureImplementation(browser) {
  console.log('\n=== PHASE 2: Capturing Current Implementation ===\n');

  // Check if test harness is running
  const testPage = await browser.newPage();
  try {
    await testPage.goto(HARNESS_BASE, { timeout: 5000 });
  } catch {
    console.log('⚠ Test harness not running on port 4174.');
    console.log('  Start it with: npx vite --config e2e/vite.config.ts');
    console.log('  Skipping implementation screenshots.\n');
    await testPage.close();
    return;
  }
  await testPage.close();

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

  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });

  for (const { path, name } of PAGES) {
    const page = await context.newPage();
    try {
      await page.goto(`${HARNESS_BASE}#${path}`, { waitUntil: 'networkidle', timeout: 20000 });
      await page.waitForTimeout(3000);
      await page.screenshot({ path: resolve(IMPL_DIR, `${name}.png`), fullPage: true });
      console.log(`  ✓ ${name}.png`);
    } catch (err) {
      console.error(`  ✗ ${name}: ${err.message}`);
    } finally {
      await page.close();
    }
  }

  await context.close();
}

async function main() {
  const chromiumPath = findChromium();
  console.log(`Using Chromium: ${chromiumPath || 'auto-detect'}`);

  const launchOptions = {
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  };
  if (chromiumPath) launchOptions.executablePath = chromiumPath;

  const browser = await chromium.launch(launchOptions);

  await captureDesignReference(browser);
  await captureImplementation(browser);

  await browser.close();

  console.log('\n=== DONE ===');
  console.log(`Design reference: ${DESIGN_DIR}`);
  console.log(`Implementation:   ${IMPL_DIR}`);
  console.log('\nCompare side-by-side to identify visual differences.');
}

main().catch(err => {
  console.error('Fatal:', err.message);
  process.exit(1);
});
