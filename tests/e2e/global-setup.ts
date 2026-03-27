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
    console.warn('   Warning: Seed failed (may already exist):', error);
    // Non-fatal — data may already be seeded from a previous run
  }

  console.log('\n=== E2E Setup Complete ===\n');
}

export default globalSetup;
