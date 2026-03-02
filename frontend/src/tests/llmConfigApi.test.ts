import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/apiUtils', () => ({
  API_BASE_URL: '',
  createHeadersAsync: vi.fn().mockResolvedValue({ Authorization: 'Bearer token' }),
  handleResponse: vi.fn(async (res: Response) => res.json()),
}));

import {
  getAIConfiguration,
  getAIUsageStats,
  setApiKey,
  testConnection,
  updateFeatureFlags,
} from '../services/llmConfigApi';

beforeEach(() => {
  vi.clearAllMocks();
  global.fetch = vi.fn().mockResolvedValue({ ok: true, json: vi.fn().mockResolvedValue({}) });
});

describe('llmConfigApi', () => {
  it('getAIConfiguration never returns raw key', async () => {
    const payload = { provider: 'openai', hasApiKey: true, connectionStatus: 'connected', enabledFeatures: {} };
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: vi.fn().mockResolvedValue(payload) });
    const result = await getAIConfiguration();
    expect(result).not.toHaveProperty('apiKey');
  });

  it('setApiKey returns stub response (backend not yet implemented)', async () => {
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const result = await setApiKey('openai', 'secret');
    expect(result).toEqual({ success: false });
    consoleSpy.mockRestore();
  });

  it('testConnection returns stub error status (backend not yet implemented)', async () => {
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const result = await testConnection();
    expect(result).toEqual({ status: 'error', message: 'Feature not yet available' });
    consoleSpy.mockRestore();
  });

  it('getAIUsageStats returns metric counts', async () => {
    const payload = { requestsThisMonth: 1, requestsLimit: 2, insightsGenerated: 3, recommendationsGenerated: 4, predictionsGenerated: 5 };
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: vi.fn().mockResolvedValue(payload) });
    await expect(getAIUsageStats()).resolves.toEqual(payload);
  });

  it('updateFeatureFlags falls back to getAIConfiguration (backend not yet implemented)', async () => {
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const configPayload = { provider: 'openai', hasApiKey: false, connectionStatus: 'disconnected', enabledFeatures: {} };
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: vi.fn().mockResolvedValue(configPayload) });
    const result = await updateFeatureFlags({ predictions: true });
    // updateFeatureFlags is a stub that calls getAIConfiguration() internally
    expect(global.fetch).toHaveBeenCalledWith('/api/llm/config', expect.objectContaining({ method: 'GET' }));
    expect(result).toEqual(configPayload);
    consoleSpy.mockRestore();
  });
});
