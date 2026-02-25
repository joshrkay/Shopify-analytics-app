import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/apiUtils', () => ({
  API_BASE_URL: '',
  createHeadersAsync: vi.fn().mockResolvedValue({ Authorization: 'Bearer token' }),
  handleResponse: vi.fn(async (res: Response) => res.json()),
}));

import {
  getNotificationPreferences,
  getPerformanceAlerts,
  testNotification,
  updateNotificationPreferences,
  updatePerformanceAlert,
} from '../services/notificationsApi';

const BACKEND_PREFS = {
  preferences: [
    { event_type: 'sync_completed', in_app_enabled: true, email_enabled: false },
    { event_type: 'connector_failed', in_app_enabled: true, email_enabled: true },
    { event_type: 'insight_generated', in_app_enabled: false, email_enabled: false },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: vi.fn().mockResolvedValue(BACKEND_PREFS),
  });
});

describe('notificationsApi', () => {
  it('getNotificationPreferences maps backend format to frontend shape', async () => {
    const prefs = await getNotificationPreferences();

    // deliveryMethods proxy via insight_generated
    expect(prefs.deliveryMethods.inApp).toBe(false);
    expect(prefs.deliveryMethods.email).toBe(false);
    expect(prefs.deliveryMethods.sms).toBe(false);

    // syncNotifications mapped from backend event types
    expect(prefs.syncNotifications.syncCompleted.email).toBe(false);
    expect(prefs.syncNotifications.syncFailed.email).toBe(true);
    expect(prefs.syncNotifications.connectionLost.inApp).toBe(true);

    // Untracked fields default safely
    expect(Array.isArray(prefs.performanceAlerts)).toBe(true);
    expect(Array.isArray(prefs.reportSchedules)).toBe(true);
    expect(prefs.quietHours.enabled).toBe(false);

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/notifications/preferences',
      expect.objectContaining({ headers: expect.anything() }),
    );
  });

  it('updateNotificationPreferences sends only mapped event types', async () => {
    await updateNotificationPreferences({
      deliveryMethods: { inApp: true, email: false, sms: false, slack: false },
      syncNotifications: {
        syncCompleted: { inApp: true, email: true, sms: false, slack: false },
        syncFailed: { inApp: false, email: false, sms: false, slack: false },
        sourceAdded: { inApp: true, email: true, sms: false, slack: false },
        connectionLost: { inApp: false, email: false, sms: false, slack: false },
      },
    });

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/notifications/preferences',
      expect.objectContaining({
        method: 'PUT',
        body: expect.stringContaining('"event_type"'),
      }),
    );

    const call = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    const sent = JSON.parse(call[1].body);
    // Should include insight_generated (from deliveryMethods), sync_completed, connector_failed
    const types = sent.preferences.map((p: { event_type: string }) => p.event_type);
    expect(types).toContain('insight_generated');
    expect(types).toContain('sync_completed');
    expect(types).toContain('connector_failed');
  });

  it('getPerformanceAlerts returns empty array (no backend support yet)', async () => {
    const alerts = await getPerformanceAlerts();
    expect(alerts).toEqual([]);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('updatePerformanceAlert throws (not yet implemented)', async () => {
    await expect(updatePerformanceAlert('a1', { threshold: '> 10m' })).rejects.toThrow();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('testNotification returns {success:false} without network call', async () => {
    const result = await testNotification('email');
    expect(result).toEqual({ success: false });
    expect(global.fetch).not.toHaveBeenCalled();
  });
});
