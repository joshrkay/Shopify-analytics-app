/**
 * Session Token Hook
 *
 * Manages Shopify session token retrieval and caching.
 * Session tokens are used for authentication in embedded apps.
 */

import { useState, useCallback, useEffect } from 'react';
import { useAppBridge } from '@shopify/app-bridge-react';
import { getSessionToken } from '@shopify/app-bridge-utils';

interface SessionTokenCache {
  token: string;
  expiresAt: number;
}

// Cache with 60-second buffer before expiry
const CACHE_BUFFER_MS = 60 * 1000;

export function useSessionToken() {
  const app = useAppBridge();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [cache, setCache] = useState<SessionTokenCache | null>(null);

  const getToken = useCallback(async (): Promise<string | null> => {
    // If app is not available (not embedded), return null
    if (!app) {
      return null;
    }

    // Check if we have a valid cached token
    if (cache && cache.expiresAt > Date.now() + CACHE_BUFFER_MS) {
      return cache.token;
    }

    setIsLoading(true);
    setError(null);

    try {
      // Get session token from App Bridge
      const token = await getSessionToken(app);

      if (!token) {
        return null;
      }

      // Parse token to get expiry (JWT format)
      // Tokens are typically valid for 1 hour, but we'll use a conservative 50 minutes
      const expiresAt = Date.now() + 50 * 60 * 1000;

      // Cache the token
      setCache({ token, expiresAt });

      return token;
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Failed to get session token');
      setError(error);
      console.error('Session token error:', error);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [app, cache]);

  // Clear cache when app changes (e.g., navigation)
  useEffect(() => {
    setCache(null);
  }, [app]);

  return { getToken, isLoading, error };
}
