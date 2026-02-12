import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  getNotificationPreferences,
  getPerformanceAlerts,
  updateNotificationPreferences,
  updatePerformanceAlert,
} from '../services/notificationsApi';
import type { NotificationPreferences, PerformanceAlert } from '../types/settingsTypes';

export function useNotificationPreferences() {
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isMountedRef = useRef(true);

  useEffect(() => () => {
    isMountedRef.current = false;
  }, []);

  const refetch = useCallback(async () => {
    try {
      if (isMountedRef.current) {
        setIsLoading(true);
        setError(null);
      }

      const nextPreferences = await getNotificationPreferences();

      if (isMountedRef.current) {
        setPreferences(nextPreferences);
      }
    } catch (err) {
      if (isMountedRef.current) {
        setError(err instanceof Error ? err.message : 'Failed to load notification preferences');
      }
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { preferences, isLoading, error, refetch, setPreferences };
}

export function useUpdateNotificationPreferences() {
  return useMemo(() => {
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    let pendingReject: ((reason?: unknown) => void) | undefined;

    return (prefs: Partial<NotificationPreferences>) =>
      new Promise<NotificationPreferences>((resolve, reject) => {
        if (timeoutId) clearTimeout(timeoutId);
        if (pendingReject) pendingReject(new Error('Debounced update replaced by a newer request.'));

        pendingReject = reject;
        timeoutId = setTimeout(async () => {
          try {
            const updatedPreferences = await updateNotificationPreferences(prefs);
            pendingReject = undefined;
            resolve(updatedPreferences);
          } catch (err) {
            pendingReject = undefined;
            reject(err);
          }
        }, 500);
      });
  }, []);
}

export function usePerformanceAlerts() {
  const [alerts, setAlerts] = useState<PerformanceAlert[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const isMountedRef = useRef(true);

  useEffect(() => () => {
    isMountedRef.current = false;
  }, []);

  const refetch = useCallback(async () => {
    if (isMountedRef.current) {
      setIsLoading(true);
    }
    try {
      const nextAlerts = await getPerformanceAlerts();
      if (isMountedRef.current) {
        setAlerts(nextAlerts);
      }
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { alerts, isLoading, refetch };
}

export function useUpdatePerformanceAlert() {
  return useCallback((alertId: string, alert: Partial<PerformanceAlert>) => updatePerformanceAlert(alertId, alert), []);
}
