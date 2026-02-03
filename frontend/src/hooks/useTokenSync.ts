import { useEffect } from 'react';
import { useAuth, useAuthUser } from '@frontegg/react';

/**
 * Ensures Frontegg JWT token is synced to localStorage with the key
 * expected by our API clients (jwt_token).
 *
 * Frontegg stores tokens internally - this hook extracts the accessToken
 * from Frontegg's auth state and syncs it to localStorage.
 */
export function useTokenSync() {
  const { isAuthenticated } = useAuth();
  const { accessToken } = useAuthUser();

  useEffect(() => {
    if (isAuthenticated && accessToken) {
      // Sync Frontegg's accessToken to localStorage with our expected key
      localStorage.setItem('jwt_token', accessToken);
      console.log('✅ JWT token synced to localStorage');
    } else if (!isAuthenticated) {
      // Clear token on logout
      localStorage.removeItem('jwt_token');
    }
  }, [isAuthenticated, accessToken]);
}
