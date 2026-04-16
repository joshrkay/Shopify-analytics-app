/**
 * Custom assertion helpers for E2E tests.
 *
 * Provides higher-level assertions for common UI patterns
 * like toasts, error states, loading states, and data matching.
 */
import { Page, expect, Locator } from '@playwright/test';
import { toast, banner, loading, emptyState } from './selectors';

/**
 * Assert that a toast notification appears with the expected message.
 */
export async function expectToast(page: Page, message: string | RegExp, options?: { timeout?: number }) {
  const toastLocator = page.locator(toast.root);
  await expect(toastLocator).toBeVisible({ timeout: options?.timeout || 5000 });

  const messageLocator = page.locator(toast.message);
  if (typeof message === 'string') {
    await expect(messageLocator).toContainText(message);
  } else {
    await expect(messageLocator).toHaveText(message);
  }
}

/**
 * Assert that a toast error appears.
 */
export async function expectToastError(page: Page, message?: string | RegExp) {
  const errorToast = page.locator(toast.error);
  await expect(errorToast).toBeVisible({ timeout: 5000 });
  if (message) {
    const messageLocator = page.locator(`${toast.error} ${toast.message}`);
    if (typeof message === 'string') {
      await expect(messageLocator).toContainText(message);
    } else {
      await expect(messageLocator).toHaveText(message);
    }
  }
}

/**
 * Assert that a critical banner appears with expected content.
 */
export async function expectErrorBanner(page: Page, content?: string | RegExp) {
  const bannerLocator = page.locator(banner.critical);
  await expect(bannerLocator).toBeVisible({ timeout: 5000 });
  if (content) {
    if (typeof content === 'string') {
      await expect(bannerLocator).toContainText(content);
    } else {
      await expect(bannerLocator).toHaveText(content);
    }
  }
}

/**
 * Assert that a success banner appears.
 */
export async function expectSuccessBanner(page: Page, content?: string | RegExp) {
  const bannerLocator = page.locator(banner.success);
  await expect(bannerLocator).toBeVisible({ timeout: 5000 });
  if (content) {
    await expect(bannerLocator).toContainText(typeof content === 'string' ? content : '');
  }
}

/**
 * Wait for loading indicators to disappear.
 */
export async function waitForLoadingComplete(page: Page, options?: { timeout?: number }) {
  const timeout = options?.timeout || 15000;

  // Wait for spinners to disappear
  const spinner = page.locator(loading.spinner);
  if (await spinner.isVisible()) {
    await expect(spinner).not.toBeVisible({ timeout });
  }

  // Wait for skeleton pages to disappear
  const skeleton = page.locator(loading.skeletonPage);
  if (await skeleton.isVisible()) {
    await expect(skeleton).not.toBeVisible({ timeout });
  }
}

/**
 * Assert that an empty state is displayed.
 */
export async function expectEmptyState(page: Page, heading?: string) {
  const empty = page.locator(emptyState.root);
  await expect(empty).toBeVisible({ timeout: 5000 });
  if (heading) {
    await expect(page.locator(emptyState.heading)).toContainText(heading);
  }
}

/**
 * Assert that the page redirected to the paywall.
 */
export async function expectPaywallRedirect(page: Page, feature?: string) {
  await page.waitForURL(/\/paywall/, { timeout: 5000 });
  expect(page.url()).toContain('/paywall');
  if (feature) {
    expect(page.url()).toContain(`feature=${feature}`);
  }
}

/**
 * Assert that the page is on a specific URL path.
 */
export async function expectUrl(page: Page, path: string | RegExp, options?: { timeout?: number }) {
  if (typeof path === 'string') {
    await page.waitForURL(`**${path}`, { timeout: options?.timeout || 5000 });
  } else {
    await page.waitForURL(path, { timeout: options?.timeout || 5000 });
  }
}

/**
 * Assert that API data matches what's displayed in the UI.
 * Compares an API response value with a page locator's text content.
 */
export async function expectDataMatch(
  locator: Locator,
  expectedValue: string | number,
  options?: { timeout?: number },
) {
  const expected = String(expectedValue);
  await expect(locator).toContainText(expected, { timeout: options?.timeout || 5000 });
}

/**
 * Assert that a table has a specific number of rows.
 */
export async function expectTableRowCount(
  page: Page,
  tableSelector: string,
  rowSelector: string,
  count: number,
) {
  const rows = page.locator(`${tableSelector} ${rowSelector}`);
  await expect(rows).toHaveCount(count, { timeout: 5000 });
}

/**
 * Assert that the page title matches.
 */
export async function expectPageTitle(page: Page, title: string | RegExp) {
  const heading = page.locator('h1').first();
  if (typeof title === 'string') {
    await expect(heading).toContainText(title, { timeout: 5000 });
  } else {
    await expect(heading).toHaveText(title, { timeout: 5000 });
  }
}
