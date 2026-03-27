/**
 * Playwright global teardown for full-stack E2E tests.
 *
 * Runs once after all test suites complete:
 * 1. Cleans up test data from the database
 * 2. Removes temporary key files (optional)
 */
import { FullConfig } from '@playwright/test';
import { teardownAll } from './helpers/db-seed';

async function globalTeardown(config: FullConfig) {
  console.log('\n=== E2E Global Teardown ===\n');

  // Clean up test data
  console.log('Cleaning up test data...');
  try {
    await teardownAll();
    console.log('Test data cleaned up.');
  } catch (error) {
    console.warn('Warning: Teardown failed:', error);
    // Non-fatal — CI will destroy the DB container anyway
  }

  console.log('\n=== E2E Teardown Complete ===\n');
}

export default globalTeardown;
