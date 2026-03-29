/**
 * Playwright global setup for full-stack E2E tests.
 *
 * Runs once before all test suites:
 * 1. Generates RSA key pair (if not exists)
 * 2. Waits for backend + frontend to be ready
 * 3. Seeds baseline test data
 */
import { FullConfig } from '@playwright/test';
import { getKeyPair } from './helpers/jwt-generator';
import { waitForAllServices } from './helpers/wait-for-services';
import { seedBaseline } from './helpers/db-seed';

async function globalSetup(config: FullConfig) {
  console.log('\n=== E2E Global Setup ===\n');

  // Step 1: Ensure RSA keys exist for JWT signing
  console.log('1. Generating RSA key pair...');
  const { publicKey } = getKeyPair();
  console.log('   Key pair ready.');

  // Step 2: Wait for all services to be ready
  console.log('2. Waiting for services...');
  try {
    await waitForAllServices();
  } catch (error) {
    console.error('ERROR: Services not ready. Make sure to run:');
    console.error('  ./tests/e2e/scripts/setup-e2e.sh');
    throw error;
  }

  // Step 3: Seed baseline test data
  console.log('3. Seeding baseline test data...');
  try {
    await seedBaseline();
    console.log('   Baseline data seeded.');
  } catch (error) {
    // Check if baseline data already exists from a previous run
    const apiBase = process.env.E2E_API_URL || 'http://localhost:8000';
    try {
      const check = await fetch(`${apiBase}/api/test/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ table: 'plans', tenant_id: 'e2e-tenant-pro-001' }),
      });
      if (check.ok) {
        console.warn('   Seed failed but baseline data already exists — continuing.');
      } else {
        console.error('   Seed failed and no baseline data exists — aborting.');
        throw error;
      }
    } catch {
      console.error('   Seed failed and cannot verify baseline data — aborting.');
      throw error;
    }
  }

  console.log('\n=== E2E Setup Complete ===\n');
}

export default globalSetup;
