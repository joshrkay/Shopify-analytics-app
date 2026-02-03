import { useEffect } from 'react';
import { useAuth } from '@frontegg/react';

/**
 * Ensures Frontegg JWT token is synced to localStorage with the key
 * expected by our API clients (jwt_token).
 *
 * Frontegg's tokenStorageKey config doesn't always work with embedded login,
 * so we manually extract the token from Frontegg's context and sync it.
 */
export function useTokenSync() {
  const { isAuthenticated, user } = useAuth();

  useEffect(() => {
    if (isAuthenticated) {
      // Try multiple methods to get the token
      let token: string | null = null;

      // Method 1: Check if already in localStorage (from tokenStorageKey config)
      token = localStorage.getItem('jwt_token');

      // Method 2: Try Frontegg global state (if available)
      if (!token) {
        try {
          const fronteggGlobal = (window as any).FronteggProvider || (window as any).Frontegg;
          if (fronteggGlobal?.auth?.accessToken) {
            token = fronteggGlobal.auth.accessToken;
          }
        } catch (e) {
          // Frontegg global not available
        }
      }

      // Method 3: Check user object
      if (!token && user) {
        token = (user as any).accessToken || (user as any).token || null;
      }

      // Method 4: Check all localStorage for Frontegg keys
      if (!token) {
        const fronteggKeys = Object.keys(localStorage).filter(k =>
          k.includes('frontegg') || k.includes('Frontegg') || k.includes('token')
        );
        for (const key of fronteggKeys) {
          const value = localStorage.getItem(key);
          if (value && value.startsWith('eyJ')) { // JWT tokens start with eyJ
            token = value;
            console.log(`Found token in localStorage key: ${key}`);
            break;
          }
        }
      }

      if (token) {
        localStorage.setItem('jwt_token', token);
        console.log('✅ JWT token synced to localStorage');
        console.log('Token preview:', token.substring(0, 50) + '...');
      } else {
        console.warn('⚠️ User authenticated but no JWT token found');
        console.log('Available localStorage keys:', Object.keys(localStorage));
        console.log('User object keys:', user ? Object.keys(user) : 'no user');
      }
    } else {
      // Clear token on logout
      localStorage.removeItem('jwt_token');
    }
  }, [isAuthenticated, user]);
}
