import type { NotificationPreferences, DeliveryMethods } from '../types/settingsTypes';
import { API_BASE_URL, createHeadersAsync, handleResponse } from './apiUtils';

// ─── Backend types (snake_case from GET/PUT /api/notifications/preferences) ───

interface BackendPreferenceItem {
  event_type: string;
  in_app_enabled: boolean;
  email_enabled: boolean;
}

interface BackendPreferencesResponse {
  preferences: BackendPreferenceItem[];
}

// ─── Mapping helpers ──────────────────────────────────────────────────────────

/** Backend event_type values */
const EVT = {
  CONNECTOR_FAILED: 'connector_failed',
  SYNC_COMPLETED: 'sync_completed',
  INSIGHT_GENERATED: 'insight_generated',
} as const;

/**
 * Convert a BackendPreferenceItem list into the frontend NotificationPreferences shape.
 *
 * Mapping:
 *  sync_completed   → syncNotifications.syncCompleted
 *  connector_failed → syncNotifications.syncFailed + syncNotifications.connectionLost
 *  insight_generated → deliveryMethods (used as global proxy)
 *
 * Fields with no backend counterpart (sms, slack, sourceAdded,
 * performanceAlerts, reportSchedules, quietHours) are filled with defaults.
 */
function backendToFrontend(items: BackendPreferenceItem[]): NotificationPreferences {
  const find = (eventType: string): BackendPreferenceItem | undefined =>
    items.find(i => i.event_type === eventType);

  const toDelivery = (item: BackendPreferenceItem | undefined): DeliveryMethods => ({
    inApp: item?.in_app_enabled ?? true,
    email: item?.email_enabled ?? true,
    sms: false,
    slack: false,
  });

  const global = find(EVT.INSIGHT_GENERATED);
  const syncFailed = find(EVT.CONNECTOR_FAILED);
  const syncCompleted = find(EVT.SYNC_COMPLETED);

  return {
    deliveryMethods: toDelivery(global),
    syncNotifications: {
      syncCompleted: toDelivery(syncCompleted),
      syncFailed: toDelivery(syncFailed),
      // sourceAdded has no backend event type yet — default to enabled
      sourceAdded: { inApp: true, email: true, sms: false, slack: false },
      // connectionLost shares the connector_failed event type
      connectionLost: toDelivery(syncFailed),
    },
    performanceAlerts: [],
    reportSchedules: [],
    quietHours: {
      enabled: false,
      startTime: '22:00',
      endTime: '08:00',
      days: ['Sat', 'Sun'],
      allowCritical: true,
    },
  };
}

/**
 * Extract the backend preference items that we can derive from a
 * NotificationPreferences update. Only sends the event types we map.
 */
function frontendToBackend(prefs: Partial<NotificationPreferences>): BackendPreferenceItem[] {
  const items: BackendPreferenceItem[] = [];

  if (prefs.deliveryMethods) {
    // insight_generated acts as the global proxy
    items.push({
      event_type: EVT.INSIGHT_GENERATED,
      in_app_enabled: prefs.deliveryMethods.inApp,
      email_enabled: prefs.deliveryMethods.email,
    });
  }

  if (prefs.syncNotifications?.syncCompleted) {
    items.push({
      event_type: EVT.SYNC_COMPLETED,
      in_app_enabled: prefs.syncNotifications.syncCompleted.inApp,
      email_enabled: prefs.syncNotifications.syncCompleted.email,
    });
  }

  if (prefs.syncNotifications?.syncFailed) {
    items.push({
      event_type: EVT.CONNECTOR_FAILED,
      in_app_enabled: prefs.syncNotifications.syncFailed.inApp,
      email_enabled: prefs.syncNotifications.syncFailed.email,
    });
  }

  return items;
}

// ─── Public API ───────────────────────────────────────────────────────────────

export async function getNotificationPreferences(): Promise<NotificationPreferences> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/notifications/preferences`, { headers });
  const data = await handleResponse<BackendPreferencesResponse>(response);
  return backendToFrontend(data.preferences);
}

export async function updateNotificationPreferences(
  prefs: Partial<NotificationPreferences>,
): Promise<NotificationPreferences> {
  const headers = await createHeadersAsync();
  const body = frontendToBackend(prefs);

  const response = await fetch(`${API_BASE_URL}/api/notifications/preferences`, {
    method: 'PUT',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify({ preferences: body }),
  });

  const data = await handleResponse<BackendPreferencesResponse>(response);
  return backendToFrontend(data.preferences);
}

/**
 * Performance alerts and test-notification have no backend implementation.
 * These stubs return safe defaults without console.warn noise.
 */
export async function getPerformanceAlerts() {
  return [];
}

export async function updatePerformanceAlert(
  _alertId: string,
  _alert: unknown,
) {
  throw new Error('Performance alert updates are not yet available');
}

export async function testNotification(_channel: string): Promise<{ success: boolean }> {
  return { success: false };
}

// ─── Notification Center API ─────────────────────────────────────────────────

export interface NotificationItem {
  id: string;
  event_type: string;
  importance: string;
  title: string;
  message: string;
  action_url: string | null;
  entity_type: string | null;
  entity_id: string | null;
  status: string;
  created_at: string;
  read_at: string | null;
}

interface NotificationListResponse {
  notifications: NotificationItem[];
  total: number;
  unread_count: number;
}

interface UnreadCountResponse {
  count: number;
}

export async function getNotifications(
  limit = 20,
  offset = 0,
): Promise<NotificationListResponse> {
  const headers = await createHeadersAsync();
  const response = await fetch(
    `${API_BASE_URL}/api/notifications?limit=${limit}&offset=${offset}`,
    { headers },
  );
  return handleResponse<NotificationListResponse>(response);
}

export async function getUnreadCount(): Promise<number> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/notifications/unread/count`, {
    headers,
  });
  const data = await handleResponse<UnreadCountResponse>(response);
  return data.count;
}

export async function markAsRead(notificationId: string): Promise<void> {
  const headers = await createHeadersAsync();
  await fetch(`${API_BASE_URL}/api/notifications/${notificationId}/read`, {
    method: 'PATCH',
    headers,
  });
}

export async function markAllAsRead(): Promise<number> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/notifications/read-all`, {
    method: 'POST',
    headers,
  });
  const data = await handleResponse<{ marked_count: number }>(response);
  return data.marked_count;
}
