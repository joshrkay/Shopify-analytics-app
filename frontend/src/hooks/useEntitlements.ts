/**
 * useEntitlements Hook
 *
 * Custom hook to fetch and manage entitlements state.
 * Fetches /api/billing/entitlements only after token is ready.
 */

import { useState, useEffect, useCallback } from 'react';
import { fetchEntitlements, type EntitlementsResponse } from '../services/entitlementsApi';

interface UseEntitlementsResult {
  entitlements: EntitlementsResponse | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

/**
 * Hook to fetch entitlements once auth token is ready.
 */
export function useEntitlements(isTokenReady = true): UseEntitlementsResult {
  const [entitlements, setEntitlements] = useState<EntitlementsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadEntitlements = useCallback(async () => {
    if (!isTokenReady) {
      setLoading(true);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await fetchEntitlements();
      setEntitlements(data);
    } catch (err) {
      console.error('Failed to fetch entitlements:', err);
      setError(err instanceof Error ? err.message : 'Failed to load entitlements');
    } finally {
      setLoading(false);
    }
  }, [isTokenReady]);

  useEffect(() => {
    loadEntitlements();
  }, [loadEntitlements]);

  return {
    entitlements,
    loading,
    error,
    refetch: loadEntitlements,
  };
}
