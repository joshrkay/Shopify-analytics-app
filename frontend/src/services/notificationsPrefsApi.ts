/**
 * Notification Preferences API Service
 *
 * Fetches and saves per-event-type notification preferences for the current user.
 *
 * Backend routes (backend/src/api/routes/notifications.py):
 *   GET /api/notifications/preferences  → get current user's preferences
 *   PUT /api/notifications/preferences  → upsert preferences
 *
 * Each preference row controls two channels:
 *   in_app_enabled  — whether the notification appears in the in-app inbox
 *   email_enabled   — whether an email is sent for this event type
 *
 * Defaults (when no DB row exists): both channels enabled = true.
 */

import { API_BASE_URL, createHeadersAsync, handleResponse } from './apiUtils';

// ---------------------------------------------------------------------------
// Types (mirror Pydantic schemas in backend/src/api/schemas/notifications.py)
// ---------------------------------------------------------------------------

export interface NotificationPreferenceItem {
  event_type: string;
  in_app_enabled: boolean;
  email_enabled: boolean;
}

export interface NotificationPreferencesResponse {
  preferences: NotificationPreferenceItem[];
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/**
 * Fetch notification preferences for the current user.
 * Returns one row per event type (10 total). Missing rows default to enabled.
 */
export async function getNotificationPreferences(): Promise<NotificationPreferencesResponse> {
  const headers = await createHeadersAsync();
  const response = await fetch(
    `${API_BASE_URL}/api/notifications/preferences`,
    { method: 'GET', headers },
  );
  return handleResponse<NotificationPreferencesResponse>(response);
}

/**
 * Save notification preferences for the current user.
 * Upserts all provided rows; unspecified event types retain existing values.
 */
export async function updateNotificationPreferences(
  preferences: NotificationPreferenceItem[],
): Promise<NotificationPreferencesResponse> {
  const headers = await createHeadersAsync();
  const response = await fetch(
    `${API_BASE_URL}/api/notifications/preferences`,
    {
      method: 'PUT',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify({ preferences }),
    },
  );
  return handleResponse<NotificationPreferencesResponse>(response);
}
