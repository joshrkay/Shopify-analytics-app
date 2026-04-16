/**
 * Service readiness helpers for E2E test setup.
 *
 * Polls health endpoints to ensure backend and frontend
 * are ready before running tests.
 */

const MAX_RETRIES = 30;
const RETRY_INTERVAL_MS = 2000;

/**
 * Wait for a URL to return a successful response.
 */
async function waitForUrl(url: string, label: string): Promise<void> {
  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(5000) });
      if (response.ok) {
        console.log(`  [ready] ${label} (attempt ${attempt})`);
        return;
      }
      console.log(`  [waiting] ${label}: ${response.status} (attempt ${attempt}/${MAX_RETRIES})`);
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      console.log(`  [waiting] ${label}: ${msg} (attempt ${attempt}/${MAX_RETRIES})`);
    }
    await new Promise(resolve => setTimeout(resolve, RETRY_INTERVAL_MS));
  }
  throw new Error(`${label} did not become ready after ${MAX_RETRIES * RETRY_INTERVAL_MS / 1000}s`);
}

/**
 * Wait for the FastAPI backend to be ready.
 */
export async function waitForBackend(): Promise<void> {
  const url = `${process.env.E2E_API_URL || 'http://localhost:8000'}/health`;
  await waitForUrl(url, 'Backend');
}

/**
 * Wait for the Vite frontend dev server to be ready.
 */
export async function waitForFrontend(): Promise<void> {
  const url = `${process.env.E2E_BASE_URL || 'http://localhost:3000'}/`;
  await waitForUrl(url, 'Frontend');
}

/**
 * Wait for the mock external services to be ready.
 */
export async function waitForMockServices(): Promise<void> {
  const services = [
    { url: 'http://localhost:9001/health', label: 'Mock Shopify' },
    { url: 'http://localhost:9002/health', label: 'Mock Airbyte' },
    { url: 'http://localhost:9003/health', label: 'Mock OpenRouter' },
  ];

  for (const { url, label } of services) {
    try {
      await waitForUrl(url, label);
    } catch {
      console.warn(`  [skip] ${label} not available — tests depending on it may fail`);
    }
  }
}

/**
 * Wait for all services required by E2E tests.
 */
export async function waitForAllServices(): Promise<void> {
  console.log('Waiting for E2E test services...');
  await waitForBackend();
  await waitForFrontend();
  await waitForMockServices();
  console.log('All services ready.');
}
