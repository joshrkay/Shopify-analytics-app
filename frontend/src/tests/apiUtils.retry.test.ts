import { describe, it, expect, vi, afterEach } from 'vitest';
import { fetchWithRetry } from '../services/apiUtils';

describe('fetchWithRetry', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('retries GET requests on 503 and eventually succeeds', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('temporary', { status: 503 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));

    const response = await fetchWithRetry('/api/example', { method: 'GET' }, { maxRetries: 2, baseDelayMs: 1 });

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('does not retry non-GET requests', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('temporary', { status: 503 }));

    const response = await fetchWithRetry('/api/example', { method: 'POST' }, { maxRetries: 2, baseDelayMs: 1 });

    expect(response.status).toBe(503);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
