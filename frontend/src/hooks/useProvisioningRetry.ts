/**
 * useProvisioningRetry
 *
 * Wraps async API calls that may fail with TENANT_NOT_PROVISIONED (403).
 * When the error is detected the hook:
 *   1. Calls POST /api/auth/provision to explicitly drive the ClerkSyncService
 *      provisioning flow on the backend.
 *   2. Retries the original call with exponential back-off.
 *   3. Exposes `isProvisioning` so the UI can show a "Setting up your
 *      account…" banner instead of a blank error screen.
 *
 * Usage:
 *   const { execute, isProvisioning } = useProvisioningRetry();
 *   const data = await execute(() => fetchSomething());
 */

import { useCallback, useRef, useState } from 'react';
import { API_BASE_URL, createHeadersAsync, isProvisioningError } from '../services/apiUtils';

const MAX_RETRIES = 5;
const BASE_DELAY_MS = 1000;

async function callProvisionEndpoint(): Promise<void> {
  const headers = await createHeadersAsync();
  const res = await fetch(`${API_BASE_URL}/api/auth/provision`, {
    method: 'POST',
    headers,
  });
  if (!res.ok) {
    const body: { detail?: string } = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Provision failed: ${res.status}`);
  }
}

export function useProvisioningRetry() {
  const [isProvisioning, setIsProvisioning] = useState(false);
  // Track how many provision attempts we've made for the current call so
  // callers can surface "still setting up…" vs a hard failure.
  const provisionAttemptsRef = useRef(0);

  const execute = useCallback(async <T>(fn: () => Promise<T>): Promise<T> => {
    provisionAttemptsRef.current = 0;

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const result = await fn();
        // Success — clear provisioning state.
        if (isProvisioning) setIsProvisioning(false);
        provisionAttemptsRef.current = 0;
        return result;
      } catch (err) {
        const isLastAttempt = attempt === MAX_RETRIES;

        if (!isProvisioningError(err) || isLastAttempt) {
          setIsProvisioning(false);
          throw err;
        }

        // Provisioning error on a non-final attempt.
        setIsProvisioning(true);
        provisionAttemptsRef.current += 1;

        // Explicitly trigger provisioning on the backend, then wait before
        // retrying.  If the provision call itself fails we log and continue —
        // the next fn() call may still work if a concurrent request beat us.
        try {
          await callProvisionEndpoint();
        } catch (provisionErr) {
          console.warn(
            '[useProvisioningRetry] /api/auth/provision call failed — will still retry:',
            provisionErr,
          );
        }

        // Exponential back-off: 1 s, 2 s, 4 s, 8 s, 16 s
        await new Promise<void>((resolve) =>
          setTimeout(resolve, BASE_DELAY_MS * Math.pow(2, attempt)),
        );
      }
    }

    // Unreachable — the loop always throws or returns above.
    throw new Error('useProvisioningRetry: max retries exceeded');
  }, [isProvisioning]);

  return { execute, isProvisioning };
}
