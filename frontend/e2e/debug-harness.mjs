/**
 * Debug script — opens the test harness and captures console errors.
 */
import { chromium } from 'playwright-core';

const CHROMIUM_PATH = '/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome';
const URL = 'http://localhost:4174/test-harness.html#/';

async function main() {
  const browser = await chromium.launch({
    executablePath: CHROMIUM_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

  // Capture ALL console messages
  page.on('console', (msg) => {
    const type = msg.type();
    if (type === 'error' || type === 'warning') {
      console.log(`[${type}] ${msg.text()}`);
    }
  });

  // Capture page errors
  page.on('pageerror', (err) => {
    console.log(`[PAGE ERROR] ${err.message}`);
    console.log(err.stack);
  });

  console.log(`Navigating to ${URL}...`);
  await page.goto(URL, { waitUntil: 'networkidle', timeout: 20000 });
  await page.waitForTimeout(5000);

  // Check what rendered
  const bodyHTML = await page.locator('body').innerHTML();
  console.log('\n--- Body HTML (first 2000 chars) ---');
  console.log(bodyHTML.substring(0, 2000));

  const rootHTML = await page.locator('#root').innerHTML();
  console.log('\n--- #root HTML (first 2000 chars) ---');
  console.log(rootHTML.substring(0, 2000));

  await browser.close();
}

main().catch(console.error);
