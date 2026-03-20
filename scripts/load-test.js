/**
 * k6 load test for MarkInsight API.
 *
 * Usage:
 *   k6 run scripts/load-test.js
 *   k6 run --vus 20 --duration 60s scripts/load-test.js
 *   K6_BASE_URL=https://app.markinsight.net K6_AUTH_TOKEN=<token> k6 run scripts/load-test.js
 *
 * Requires: k6 (https://k6.io/docs/getting-started/installation/)
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Configuration
const BASE_URL = __ENV.K6_BASE_URL || 'http://localhost:10000';
const AUTH_TOKEN = __ENV.K6_AUTH_TOKEN || '';

const errorRate = new Rate('errors');
const healthLatency = new Trend('health_latency', true);
const entitlementsLatency = new Trend('entitlements_latency', true);
const catalogLatency = new Trend('catalog_latency', true);

export const options = {
  stages: [
    { duration: '10s', target: 5 },   // Ramp up
    { duration: '30s', target: 10 },   // Steady state
    { duration: '10s', target: 0 },    // Ramp down
  ],
  thresholds: {
    health_latency: ['p(95)<500'],        // Health: p95 < 500ms
    entitlements_latency: ['p(95)<1000'],  // Entitlements: p95 < 1s
    catalog_latency: ['p(95)<1000'],       // Catalog: p95 < 1s
    errors: ['rate<0.1'],                  // Error rate < 10%
  },
};

function headers() {
  const h = { 'Content-Type': 'application/json' };
  if (AUTH_TOKEN) {
    h['Authorization'] = `Bearer ${AUTH_TOKEN}`;
  }
  return h;
}

export default function () {
  // 1. Health check (no auth required)
  const healthRes = http.get(`${BASE_URL}/health`);
  healthLatency.add(healthRes.timings.duration);
  check(healthRes, { 'health 200': (r) => r.status === 200 });
  errorRate.add(healthRes.status !== 200);

  // Only run authenticated endpoints if we have a token
  if (AUTH_TOKEN) {
    // 2. Entitlements
    const entRes = http.get(`${BASE_URL}/api/billing/entitlements`, {
      headers: headers(),
    });
    entitlementsLatency.add(entRes.timings.duration);
    check(entRes, { 'entitlements 200': (r) => r.status === 200 });
    errorRate.add(entRes.status !== 200);

    // 3. Source catalog
    const catRes = http.get(`${BASE_URL}/api/sources/catalog`, {
      headers: headers(),
    });
    catalogLatency.add(catRes.timings.duration);
    check(catRes, { 'catalog 200': (r) => r.status === 200 });
    errorRate.add(catRes.status !== 200);
  }

  sleep(1);
}
