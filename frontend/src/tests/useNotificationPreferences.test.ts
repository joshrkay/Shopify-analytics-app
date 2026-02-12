import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/notificationsApi', () => ({
  updateNotificationPreferences: vi.fn(),
}));

import { useUpdateNotificationPreferences } from '../hooks/useNotificationPreferences';
import { updateNotificationPreferences } from '../services/notificationsApi';

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
});

describe('useUpdateNotificationPreferences edge cases', () => {
  it('rejects older debounced call when replaced by a newer request', async () => {
    vi.mocked(updateNotificationPreferences).mockResolvedValue({} as never);
    const { result } = renderHook(() => useUpdateNotificationPreferences());

    const firstCall = result.current({ quietHours: { enabled: true } } as never).catch((error) => error);
    const secondCall = result.current({ quietHours: { enabled: false } } as never);

    await act(async () => {
      vi.advanceTimersByTime(500);
      await secondCall;
    });

    await expect(firstCall).resolves.toBeInstanceOf(Error);
    await expect(firstCall).resolves.toMatchObject({ message: expect.stringContaining('Debounced update replaced') });
    expect(updateNotificationPreferences).toHaveBeenCalledTimes(1);
  });
});
